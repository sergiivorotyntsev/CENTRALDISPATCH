"""IAA (Insurance Auto Auctions) document extractor."""

import re
from datetime import datetime
from typing import Optional

from extractors.base import BaseExtractor
from models.vehicle import (
    Address,
    AuctionInvoice,
    AuctionSource,
    LocationType,
    Vehicle,
)


class IAAExtractor(BaseExtractor):
    """Extractor for IAA Buyer Receipt documents."""

    @property
    def source(self) -> AuctionSource:
        return AuctionSource.IAA

    @property
    def indicators(self) -> list:
        return [
            "Insurance Auto Auctions",
            "Buyer Receipt",
            "IAAI",
            "IAA Doc",
            "Pick-Up Location",
            "StockNo",
        ]

    @property
    def indicator_weights(self) -> dict:
        return {
            "Insurance Auto Auctions": 3.0,  # Strong indicator
            "IAAI": 2.0,
            "Buyer Receipt": 1.5,
            "IAA Doc": 2.0,
            "Pick-Up Location": 1.0,
            "StockNo": 1.0,
        }

    def extract(self, pdf_path: str) -> Optional[AuctionInvoice]:
        text = self.extract_text(pdf_path)
        if not self.can_extract(text):
            return None

        invoice = AuctionInvoice(source=self.source, buyer_id="", buyer_name="")

        receipt_match = re.search(r"Receipt\s*#\s*(\d+)", text)
        if receipt_match:
            invoice.receipt_number = receipt_match.group(1)

        buyer_match = re.search(r"Buyer\s*#\s*(\d+)", text)
        if buyer_match:
            invoice.buyer_id = buyer_match.group(1)

        buyer_name_match = re.search(r"Buyer\s*Name\s+([A-Za-z\s]+(?:Inc|LLC|Corp)?)", text)
        if buyer_name_match:
            invoice.buyer_name = buyer_name_match.group(1).strip()

        date_match = re.search(r"Sale\s*Date\s+(\d{1,2}/\d{1,2}/\d{4})", text)
        if date_match:
            try:
                invoice.sale_date = datetime.strptime(date_match.group(1), "%m/%d/%Y")
            except ValueError:
                pass

        pickup_location = self._extract_pickup_location(text)
        if pickup_location:
            invoice.pickup_address = pickup_location

        stock_match = re.search(r"StockNo\s*(\d{3}-\d+|\d+)", text)
        if stock_match:
            invoice.stock_number = stock_match.group(1)

        vehicle = self._extract_vehicle(text)
        if vehicle:
            invoice.vehicles.append(vehicle)

        total_match = re.search(r"Total\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.?\d*)", text)
        if total_match:
            try:
                invoice.total_amount = float(total_match.group(1).replace(",", ""))
            except ValueError:
                pass

        invoice.location_type = LocationType.ONSITE
        return invoice

    def _extract_pickup_location(self, text: str) -> Optional[Address]:
        location_pattern = r"Pick-Up Location[:\s]*([A-Za-z/\s\-\.]+)\n([^\n]+)\n([A-Za-z\s]+)\s+([A-Z]{2})\s+(\d{5})"
        match = re.search(location_pattern, text)

        if match:
            return Address(
                name=match.group(1).strip(),
                street=match.group(2).strip(),
                city=match.group(3).strip(),
                state=match.group(4),
                postal_code=match.group(5),
                country="US",
            )
        return None

    def _extract_vehicle(self, text: str) -> Optional[Vehicle]:
        vehicle_pattern = r"(\d{3}-\d+)\s+(?:[A-Z]-\d+\s+)?(\d{4})\s+([A-Z]+)\s+([A-Z0-9\s]+?)\s+(White|Black|Silver|Gray|Grey|Red|Blue|Green|Brown|Gold|Beige|Tan)\s+([\d,]+)\s+([A-HJ-NPR-Z0-9]{17})"
        match = re.search(vehicle_pattern, text)

        if match:
            mileage_str = match.group(6).replace(",", "")
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
                lot_number=match.group(1),
            )

        vin = self.extract_vin(text)
        if vin:
            year_match = re.search(r"\b(20\d{2}|19\d{2})\s+([A-Z]+)\s+([A-Z0-9\s]+)", text)
            if year_match:
                make = year_match.group(2).strip()
                model = year_match.group(3).strip()
                return Vehicle(
                    vin=vin,
                    year=int(year_match.group(1)),
                    make=make,
                    model=model,
                    vehicle_type=self.detect_vehicle_type(make, model),
                    mileage=self.extract_mileage(text),
                )
        return None
