"""IAA (Insurance Auto Auctions) document extractor."""
import re
from typing import Optional
from datetime import datetime

from extractors.base import BaseExtractor
from extractors.address_parser import extract_pickup_address, normalize_state
from models.vehicle import AuctionInvoice, Vehicle, Address, AuctionSource, LocationType, VehicleType


class IAAExtractor(BaseExtractor):
    """Extractor for IAA Buyer Receipt documents."""

    @property
    def source(self) -> AuctionSource:
        return AuctionSource.IAA

    @property
    def indicators(self) -> list:
        return [
            'Insurance Auto Auctions',
            'Insurance Auto Auctions Corp',
            'Buyer Receipt',
            'IAAI',
            'IAA',
            'Pick-Up Location',
            'StockNo',
            'Sold At Branch',
            'Receipt #',
        ]

    @property
    def indicator_weights(self) -> dict:
        return {
            'Insurance Auto Auctions': 5.0,  # Very strong - unique to IAA
            'Insurance Auto Auctions Corp': 5.0,  # Very strong - unique to IAA
            'Buyer Receipt': 2.0,  # Strong for IAA
            'IAAI': 3.0,
            'IAA': 2.5,  # Be careful - could match in other text
            'Pick-Up Location': 1.5,  # IAA specific format
            'StockNo': 1.5,  # IAA specific
            'Sold At Branch': 2.0,  # IAA specific
            'Receipt #': 1.0,
        }

    def extract(self, pdf_path: str) -> Optional[AuctionInvoice]:
        text = self.extract_text(pdf_path)
        if not self.can_extract(text):
            return None

        invoice = AuctionInvoice(source=self.source, buyer_id="", buyer_name="")

        # Extract receipt number
        receipt_match = re.search(r'Receipt\s*#\s*(\d+)', text)
        if receipt_match:
            invoice.receipt_number = receipt_match.group(1)

        # Extract buyer ID
        buyer_match = re.search(r'Buyer\s*#\s*(\d+)', text)
        if buyer_match:
            invoice.buyer_id = buyer_match.group(1)

        # Extract buyer name (multiple patterns)
        buyer_name_patterns = [
            r'Buyer\s*Name[:\s]+([A-Za-z][A-Za-z\s\-\.]+?)(?:\n|Buyer\s*#)',
            r'SOLD\s*TO[:\s]+([A-Za-z][A-Za-z\s\-\.]+?)(?:\n|\d)',
            r'Purchaser[:\s]+([A-Za-z][A-Za-z\s\-\.]+?)(?:\n|\d)',
            r'Bill\s*To[:\s]+([A-Za-z][A-Za-z\s\-\.]+?)(?:\n)',
        ]
        for pattern in buyer_name_patterns:
            name_match = re.search(pattern, text, re.IGNORECASE)
            if name_match:
                buyer_name = name_match.group(1).strip()
                # Clean up - remove trailing numbers/dates, keep company suffixes
                buyer_name = re.sub(r'\s+\d+.*$', '', buyer_name)
                if len(buyer_name) > 2 and len(buyer_name) < 100:
                    invoice.buyer_name = buyer_name
                    break

        # Extract sale date
        date_patterns = [
            r'Sale\s*Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
            r'Purchase\s*Date[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
            r'(\d{1,2}/\d{1,2}/\d{4})',
        ]
        for pattern in date_patterns:
            date_match = re.search(pattern, text)
            if date_match:
                try:
                    invoice.sale_date = datetime.strptime(date_match.group(1), '%m/%d/%Y')
                    break
                except ValueError:
                    continue

        # Extract pickup location with phone
        pickup_location = self._extract_pickup_location(text)
        if pickup_location:
            invoice.pickup_address = pickup_location

        # Extract stock number
        stock_match = re.search(r'StockNo\s*(\d{3}-\d+|\d+)', text)
        if stock_match:
            invoice.stock_number = stock_match.group(1)

        # Extract vehicle
        vehicle = self._extract_vehicle(text)
        if vehicle:
            invoice.vehicles.append(vehicle)

        # Extract total amount
        total_patterns = [
            r'Total\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.?\d*)',
            r'Total\s*Due[:\s]*\$?([\d,]+\.?\d*)',
            r'Amount\s*Due[:\s]*\$?([\d,]+\.?\d*)',
        ]
        for pattern in total_patterns:
            total_match = re.search(pattern, text, re.IGNORECASE)
            if total_match:
                try:
                    invoice.total_amount = float(total_match.group(1).replace(',', ''))
                    if invoice.total_amount > 0:
                        break
                except ValueError:
                    continue

        invoice.location_type = LocationType.ONSITE
        return invoice

    def _extract_pickup_location(self, text: str) -> Optional[Address]:
        """Extract pickup address using shared parser."""
        # Use the shared address parser with IAA-specific labels
        return extract_pickup_address(
            text,
            source="IAA",
            custom_labels=[
                r'Sold\s*At\s*Branch',
                r'Branch\s*Location',
            ]
        )

    def _extract_vehicle(self, text: str) -> Optional[Vehicle]:
        vehicle_pattern = r'(\d{3}-\d+)\s+(?:[A-Z]-\d+\s+)?(\d{4})\s+([A-Z]+)\s+([A-Z0-9\s]+?)\s+(White|Black|Silver|Gray|Grey|Red|Blue|Green|Brown|Gold|Beige|Tan)\s+([\d,]+)\s+([A-HJ-NPR-Z0-9]{17})'
        match = re.search(vehicle_pattern, text)

        if match:
            mileage_str = match.group(6).replace(',', '')
            mileage = int(mileage_str) if mileage_str.isdigit() else None
            make = match.group(3).strip()
            model = match.group(4).strip()

            return Vehicle(
                vin=match.group(7),
                year=int(match.group(2)),
                make=make,
                model=model,
                color=match.group(5),
                mileage=mileage,
                vehicle_type=self.detect_vehicle_type(make, model),
                lot_number=match.group(1)
            )

        vin = self.extract_vin(text)
        if vin:
            year_match = re.search(r'\b(20\d{2}|19\d{2})\s+([A-Z]+)\s+([A-Z0-9\s]+)', text)
            if year_match:
                make = year_match.group(2).strip()
                model = year_match.group(3).strip()
                return Vehicle(
                    vin=vin,
                    year=int(year_match.group(1)),
                    make=make,
                    model=model,
                    vehicle_type=self.detect_vehicle_type(make, model),
                    mileage=self.extract_mileage(text)
                )
        return None
