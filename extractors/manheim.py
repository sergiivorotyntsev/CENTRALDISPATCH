"""Manheim (Cox Automotive) document extractor."""
import re
from typing import Optional
from datetime import datetime

from extractors.base import BaseExtractor
from models.vehicle import AuctionInvoice, Vehicle, Address, AuctionSource, LocationType, VehicleType


class ManheimExtractor(BaseExtractor):
    """Extractor for Manheim Bill of Sale and Vehicle Release documents."""

    @property
    def source(self) -> AuctionSource:
        return AuctionSource.MANHEIM

    @property
    def indicators(self) -> list:
        return [
            'Manheim',
            'Cox Automotive',
            'BILL OF SALE',
            'VEHICLE RELEASE',
            'Manheim.com',
            'Release ID',
            'YMMT',
            'OFFSITE VEHICLE RELEASE',
        ]

    @property
    def indicator_weights(self) -> dict:
        return {
            'Manheim': 3.0,
            'Cox Automotive': 2.0,
            'Manheim.com': 2.5,
            'BILL OF SALE': 1.0,
            'VEHICLE RELEASE': 1.5,
            'Release ID': 1.5,
            'YMMT': 1.0,
            'OFFSITE VEHICLE RELEASE': 2.0,
        }

    def extract(self, pdf_path: str) -> Optional[AuctionInvoice]:
        pages_text = self.extract_pages_text(pdf_path)
        full_text = '\n'.join(pages_text)

        if not self.can_extract(full_text):
            return None

        invoice = AuctionInvoice(source=self.source, buyer_id="", buyer_name="")

        # Extract buyer/account ID
        account_match = re.search(r'Account\s*#?\s*:?\s*(\d+)', full_text)
        if account_match:
            invoice.buyer_id = account_match.group(1)

        # Extract buyer name (multiple patterns)
        buyer_name_patterns = [
            r'(?:Name|Buyer)[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n|Account)',
            r'SOLD\s*TO[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n|\d)',
            r'Purchaser[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n|\d)',
            r'Bill\s*To[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n)',
            r'Dealer\s*Name[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n)',
        ]
        for pattern in buyer_name_patterns:
            name_match = re.search(pattern, full_text, re.IGNORECASE)
            if name_match:
                buyer_name = name_match.group(1).strip()
                # Clean up - remove trailing numbers/dates
                buyer_name = re.sub(r'\s+\d+.*$', '', buyer_name)
                # Keep company suffixes
                if len(buyer_name) > 2 and len(buyer_name) < 100:
                    invoice.buyer_name = buyer_name
                    break

        # Extract sale date (multiple formats)
        date_patterns = [
            (r'Sale\s*Date[:\s]+(\d{1,2}-[A-Z]{3}-\d{4})', '%d-%b-%Y'),
            (r'Sale\s*Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})', '%m/%d/%Y'),
            (r'Purchase\s*Date[:\s]+[A-Za-z]+,\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', '%B %d, %Y'),
            (r'Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})', '%m/%d/%Y'),
        ]
        for pattern, fmt in date_patterns:
            date_match = re.search(pattern, full_text, re.IGNORECASE)
            if date_match:
                date_str = date_match.group(1)
                try:
                    invoice.sale_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    # Try alternative formats
                    for alt_fmt in ['%d-%b-%Y', '%m/%d/%Y', '%b %d, %Y', '%B %d, %Y']:
                        try:
                            invoice.sale_date = datetime.strptime(date_str, alt_fmt)
                            break
                        except ValueError:
                            continue
                    if invoice.sale_date:
                        break

        invoice.location_type = self._detect_location_type(full_text)

        # Extract release ID
        release_match = re.search(r'Release\s*ID[:\s]+([A-Z0-9]+)', full_text)
        if release_match:
            invoice.release_id = release_match.group(1)

        # Extract work order / stock number
        work_order_match = re.search(r'Work\s*Order\s*#?\s*:?\s*(\d+)', full_text)
        if work_order_match:
            invoice.stock_number = work_order_match.group(1)

        # Extract pickup location with phone
        pickup_location = self._extract_pickup_location(full_text)
        if pickup_location:
            invoice.pickup_address = pickup_location

        # Extract vehicle
        vehicle = self._extract_vehicle(full_text)
        if vehicle:
            invoice.vehicles.append(vehicle)

        # Extract total amount
        total_patterns = [
            r'(?:Final\s*Sale\s*Price|TOTAL|SUB\s*TOTAL)[:\s]*\$?\s*([\d,]+\.?\d*)',
            r'Amount\s*Due[:\s]*\$?\s*([\d,]+\.?\d*)',
            r'Balance\s*Due[:\s]*\$?\s*([\d,]+\.?\d*)',
        ]
        for pattern in total_patterns:
            total_match = re.search(pattern, full_text, re.IGNORECASE)
            if total_match:
                try:
                    invoice.total_amount = float(total_match.group(1).replace(',', ''))
                    if invoice.total_amount > 0:
                        break
                except ValueError:
                    continue

        return invoice

    def _detect_location_type(self, text: str) -> LocationType:
        offsite_indicators = ['OFFSITE VEHICLE RELEASE', 'not located at a Manheim facility']
        for indicator in offsite_indicators:
            if indicator.lower() in text.lower():
                return LocationType.OFFSITE
        return LocationType.ONSITE

    def _extract_pickup_location(self, text: str) -> Optional[Address]:
        # Try multiple patterns for pickup location
        pickup_patterns = [
            # Pattern with location name
            r'Pickup\s*Location\s+Address\s+([A-Za-z\s\-]+)\n\s*(\d+[A-Za-z0-9\s\.\-]+)\n\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)',
            # Pattern without location name
            r'Address[:\s]+(\d+[A-Za-z0-9\s\.\-]+)\n\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)',
            # Alternative pickup patterns
            r'(?:PICKUP|Pick[\-\s]?Up)\s*(?:Location|Address)?[:\s]*([A-Za-z\s\-]+)\n\s*(\d+[A-Za-z0-9\s\.\-]+)\n\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5})',
            # Location line
            r'Location[:\s]+([A-Za-z\s\-]+)\n([^\n]+)\n([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5})',
        ]

        name, street, city, state, postal = None, None, None, None, None

        for pattern in pickup_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 5:
                    name = groups[0].strip()
                    street = groups[1].strip()
                    city = groups[2].strip().rstrip(',')
                    state = groups[3].upper()
                    postal = groups[4]
                elif len(groups) == 4:
                    street = groups[0].strip()
                    city = groups[1].strip().rstrip(',')
                    state = groups[2].upper()
                    postal = groups[3]
                break

        if not (city and state):
            return None

        # Extract phone number
        phone = None
        phone_patterns = [
            r'(?:PHONE|TEL|CONTACT|Ph)[:\s]*(\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4})',
            r'(?:Location\s*(?:Phone|Tel))[:\s]*(\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4})',
            r'(?:Call|Contact)[:\s]*(\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4})',
            r'(\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4})',
        ]

        for pattern in phone_patterns:
            phone_match = re.search(pattern, text, re.IGNORECASE)
            if phone_match:
                phone = phone_match.group(1).strip()
                # Normalize phone format
                phone_digits = re.sub(r'\D', '', phone)
                if len(phone_digits) == 10:
                    phone = f"({phone_digits[:3]}) {phone_digits[3:6]}-{phone_digits[6:]}"
                    break

        # Determine location name
        if not name or len(name) < 3:
            manheim_match = re.search(r'(Manheim\s+[A-Za-z\s\-]+)', text, re.IGNORECASE)
            if manheim_match:
                name = manheim_match.group(1).strip()
            else:
                name = "Manheim"

        return Address(
            name=name,
            street=street,
            city=city,
            state=state,
            postal_code=postal,
            country="US",
            phone=phone
        )

    def _extract_vehicle(self, text: str) -> Optional[Vehicle]:
        ymmt_patterns = [
            r'YMMT\s+(\d{4})\s+([A-Za-z\-]+)\s+([A-Za-z0-9\s\-]+)',
            r'Vehicle\s*Information\s*\n.*?(\d{4})\s+([A-Za-z\-]+)\s+([A-Za-z0-9\s\-]+)',
        ]

        year, make, model = None, None, None

        for pattern in ymmt_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                year = int(match.group(1))
                make = match.group(2).strip()
                model = match.group(3).strip()
                break

        vin = self.extract_vin(text)

        if not (year and make and vin):
            return None

        color = None
        color_match = re.search(r'Color\s+([A-Za-z]+)', text)
        if color_match:
            color = color_match.group(1)

        mileage = self.extract_mileage(text)

        return Vehicle(
            vin=vin,
            year=year,
            make=make,
            model=model or "Unknown",
            color=color,
            mileage=mileage,
            vehicle_type=self.detect_vehicle_type(make, model or "")
        )
