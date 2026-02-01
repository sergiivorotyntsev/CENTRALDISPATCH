"""Copart document extractor."""
import re
from typing import Optional
from datetime import datetime

from extractors.base import BaseExtractor
from models.vehicle import AuctionInvoice, Vehicle, Address, AuctionSource, LocationType, VehicleType


class CopartExtractor(BaseExtractor):
    """Extractor for Copart Sales Receipt/Bill of Sale documents."""

    @property
    def source(self) -> AuctionSource:
        return AuctionSource.COPART

    @property
    def indicators(self) -> list:
        return [
            'Copart',
            'SOLD THROUGH COPART',
            'Sales Receipt/Bill of Sale',
            'MEMBER:',
            'PHYSICAL ADDRESS OF LOT',
            'LOT#',
            'copart.com',
        ]

    @property
    def indicator_weights(self) -> dict:
        return {
            'Copart': 3.0,  # Strong but not as unique
            'SOLD THROUGH COPART': 5.0,  # Very strong - unique to Copart
            'Sales Receipt/Bill of Sale': 1.0,  # Generic, reduce weight
            'MEMBER:': 1.5,
            'PHYSICAL ADDRESS OF LOT': 2.0,  # Copart specific
            'LOT#': 1.0,
            'copart.com': 4.0,  # Very strong - unique to Copart
        }

    @property
    def negative_indicators(self) -> list:
        """Indicators that suggest this is NOT a Copart document."""
        return [
            'Insurance Auto Auctions',
            'IAAI',
            'Buyer Receipt',
            'Manheim',
        ]

    def score(self, text: str) -> tuple:
        """Override score to check for negative indicators."""
        base_score, matched = super().score(text)

        # Check for negative indicators - if found, reduce score significantly
        text_lower = text.lower()
        for neg in self.negative_indicators:
            if neg.lower() in text_lower:
                # Strong negative indicator found - this is likely not Copart
                base_score *= 0.3  # Reduce score by 70%
                break

        return base_score, matched

    def extract(self, pdf_path: str) -> Optional[AuctionInvoice]:
        text = self.extract_text(pdf_path)
        if not self.can_extract(text):
            return None

        invoice = AuctionInvoice(source=self.source, buyer_id="", buyer_name="")

        # Extract buyer ID (MEMBER number)
        member_match = re.search(r'MEMBER[:\s]+(\d+)', text)
        if member_match:
            invoice.buyer_id = member_match.group(1)

        # Extract buyer name (usually appears after MEMBER number on next line)
        buyer_name_patterns = [
            # Pattern 1: Name on line after MEMBER number (most common in Copart)
            r'MEMBER[:\s]*\d+\s*\n([A-Z][A-Z\s\-\.]+(?:INC|LLC|CORP|CO)?)\s*\n',
            # Pattern 2: SOLD TO format
            r'SOLD\s*TO[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n|MEMBER)',
            # Pattern 3: BUYER format
            r'BUYER[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n|MEMBER)',
            # Pattern 4: Bill To format
            r'Bill\s*To[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n)',
        ]
        for pattern in buyer_name_patterns:
            name_match = re.search(pattern, text, re.IGNORECASE)
            if name_match:
                buyer_name = name_match.group(1).strip()
                # Clean up - remove trailing numbers/dates
                buyer_name = re.sub(r'\s+\d+.*$', '', buyer_name)
                if len(buyer_name) > 2 and len(buyer_name) < 100:
                    invoice.buyer_name = buyer_name
                    break

        lot_match = re.search(r'LOT#[:\s]+(\d+)', text)
        if lot_match:
            invoice.lot_number = lot_match.group(1)

        date_patterns = [r'Sale[:\s]+(\d{1,2}/\d{1,2}/\d{4})', r'(\d{1,2}/\d{1,2}/\d{4})']
        for pattern in date_patterns:
            date_match = re.search(pattern, text)
            if date_match:
                date_str = date_match.group(1)
                for fmt in ['%m/%d/%Y', '%m/%d/%y']:
                    try:
                        invoice.sale_date = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if invoice.sale_date:
                    break

        pickup_location = self._extract_pickup_location(text)
        if pickup_location:
            invoice.pickup_address = pickup_location

        vehicle = self._extract_vehicle(text)
        if vehicle:
            vehicle.lot_number = invoice.lot_number
            invoice.vehicles.append(vehicle)

        total_patterns = [r'Sale\s*Price\s*\$?([\d,]+\.?\d*)', r'Net\s*Due\s*\(USD\)\s*\$?([\d,]+\.?\d*)']
        for pattern in total_patterns:
            total_match = re.search(pattern, text, re.IGNORECASE)
            if total_match:
                try:
                    invoice.total_amount = float(total_match.group(1).replace(',', ''))
                    if invoice.total_amount > 0:
                        break
                except ValueError:
                    pass

        invoice.location_type = LocationType.ONSITE
        return invoice

    def _extract_pickup_location(self, text: str) -> Optional[Address]:
        # Try multiple patterns for address extraction
        # Format in document: "PHYSICAL ADDRESS OF LOT:" then "5701 WHITESIDE RD" then "SANDSTON VA 23150"
        patterns = [
            # Pattern 1: Street on one line, city/state/zip on next line (common format)
            r'PHYSICAL\s*ADDRESS\s*(?:OF\s*)?LOT[:\s]*\n?\s*([^\n]+)\n\s*([A-Za-z]+)\s+([A-Z]{2})\s+(\d{5})',
            # Pattern 2: All on same lines with colon
            r'PHYSICAL\s*ADDRESS\s*(?:OF\s*)?LOT[:\s]+([^\n]+)\n\s*([A-Za-z\s]+)\s+([A-Z]{2})\s+(\d{5})',
            # Pattern 3: Location/Address line
            r'(?:LOCATION|LOT\s*ADDRESS)[:\s]+([^\n]+)\n\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5})',
            # Pattern 4: Pick-?up location
            r'(?:PICK[\-\s]?UP|PICKUP)\s*(?:LOCATION|ADDRESS)?[:\s]+([^\n]+)\n\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5})',
        ]

        street, city, state, postal = None, None, None, None

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                groups = match.groups()
                street = groups[0].strip()
                city = groups[1].strip().rstrip(',')
                state = groups[2].upper()
                postal = groups[3]
                break

        # If standard patterns didn't work, try a more flexible approach
        if not (city and state):
            # Look for "PHYSICAL ADDRESS OF LOT" followed by any address-like text
            alt_match = re.search(
                r'PHYSICAL\s*ADDRESS\s*(?:OF\s*)?LOT[:\s]*\n?\s*'
                r'(\d+[^\n]+?)\s*\n\s*'  # Street with number
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+'  # City (one or two words)
                r'([A-Z]{2})\s+'  # State
                r'(\d{5})',  # ZIP
                text, re.IGNORECASE | re.MULTILINE
            )
            if alt_match:
                street = alt_match.group(1).strip()
                city = alt_match.group(2).strip()
                state = alt_match.group(3).upper()
                postal = alt_match.group(4)

        if not (city and state):
            return None

        # Try to extract phone number from nearby text
        phone = None
        phone_patterns = [
            r'(?:PHONE|TEL|CONTACT)[:\s]*(\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4})',
            r'(?:LOT\s*(?:PHONE|TEL))[:\s]*(\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4})',
            r'(\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4})',  # General phone pattern
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

        # Determine lot name
        lot_name = "Copart"
        lot_name_match = re.search(r'(Copart\s+[A-Za-z\s\-]+)', text, re.IGNORECASE)
        if lot_name_match:
            lot_name = lot_name_match.group(1).strip()

        return Address(
            street=street,
            city=city,
            state=state,
            postal_code=postal,
            country="US",
            name=lot_name,
            phone=phone
        )

    def _extract_vehicle(self, text: str) -> Optional[Vehicle]:
        vehicle_patterns = [
            r'VEHICLE[:\s]+(\d{4})\s+([A-Z]+(?:\-[A-Z]+)?)\s+([A-Z0-9\s\-]+?)\s+(BLACK|WHITE|SILVER|GRAY|GREY|RED|BLUE|GREEN|BROWN|GOLD|BEIGE|TAN)',
            r'VEHICLE[:\s]+(\d{4})\s+([A-Z]+(?:\-[A-Z]+)?)\s+([A-Z0-9\s\-]+)',
        ]

        year, make, model, color = None, None, None, None

        for pattern in vehicle_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                year = int(match.group(1))
                make = match.group(2).strip()
                model = match.group(3).strip()
                if len(match.groups()) > 3:
                    color = match.group(4).capitalize()
                break

        vin = self.extract_vin(text)

        if not (year and make and vin):
            return None

        mileage = self.extract_mileage(text)

        return Vehicle(
            vin=vin,
            year=year,
            make=make.title() if make else "Unknown",
            model=model.title() if model else "Unknown",
            color=color,
            mileage=mileage,
            vehicle_type=self.detect_vehicle_type(make or "", model or "")
        )
