"""Copart document extractor."""
import re
from typing import Optional
from datetime import datetime

from extractors.base import BaseExtractor
from extractors.address_parser import extract_pickup_address
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
        """Extract pickup address using shared parser."""
        # Use the shared address parser with Copart-specific labels
        return extract_pickup_address(
            text,
            source="Copart",
            custom_labels=[
                r'PHYSICAL\s*ADDRESS\s*(?:OF\s*)?LOT',
                r'LOT\s*(?:LOCATION|ADDRESS)',
                r'Copart\s+Location',
            ]
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
