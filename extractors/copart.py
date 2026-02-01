"""Copart document extractor."""

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


class CopartExtractor(BaseExtractor):
    """Extractor for Copart Sales Receipt/Bill of Sale documents."""

    @property
    def source(self) -> AuctionSource:
        return AuctionSource.COPART

    @property
    def indicators(self) -> list:
        return [
            "Copart",
            "Sales Receipt/Bill of Sale",
            "SOLD THROUGH COPART",
            "MEMBER:",
            "PHYSICAL ADDRESS OF LOT",
            "LOT#",
            "copart.com",
        ]

    @property
    def indicator_weights(self) -> dict:
        return {
            "Copart": 2.0,
            "SOLD THROUGH COPART": 3.0,
            "Sales Receipt/Bill of Sale": 1.5,
            "MEMBER:": 1.0,
            "PHYSICAL ADDRESS OF LOT": 1.5,
            "LOT#": 1.0,
            "copart.com": 2.0,
        }

    def extract(self, pdf_path: str) -> Optional[AuctionInvoice]:
        text = self.extract_text(pdf_path)
        if not self.can_extract(text):
            return None

        invoice = AuctionInvoice(source=self.source, buyer_id="", buyer_name="")

        member_match = re.search(r"MEMBER[:\s]+(\d+)", text)
        if member_match:
            invoice.buyer_id = member_match.group(1)

        lot_match = re.search(r"LOT#[:\s]+(\d+)", text)
        if lot_match:
            invoice.lot_number = lot_match.group(1)

        date_patterns = [r"Sale[:\s]+(\d{1,2}/\d{1,2}/\d{4})", r"(\d{1,2}/\d{1,2}/\d{4})"]
        for pattern in date_patterns:
            date_match = re.search(pattern, text)
            if date_match:
                date_str = date_match.group(1)
                for fmt in ["%m/%d/%Y", "%m/%d/%y"]:
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

        total_patterns = [
            r"Sale\s*Price\s*\$?([\d,]+\.?\d*)",
            r"Net\s*Due\s*\(USD\)\s*\$?([\d,]+\.?\d*)",
        ]
        for pattern in total_patterns:
            total_match = re.search(pattern, text, re.IGNORECASE)
            if total_match:
                try:
                    invoice.total_amount = float(total_match.group(1).replace(",", ""))
                    if invoice.total_amount > 0:
                        break
                except ValueError:
                    pass

        invoice.location_type = LocationType.ONSITE
        return invoice

    def _extract_pickup_location(self, text: str) -> Optional[Address]:
        patterns = [
            r"PHYSICAL\s*ADDRESS\s*(?:OF\s*)?LOT[:\s]+([^\n]+)\n\s*([A-Za-z\s]+)\s+([A-Z]{2})\s+(\d{5})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                return Address(
                    street=groups[0].strip(),
                    city=groups[1].strip(),
                    state=groups[2],
                    postal_code=groups[3],
                    country="US",
                    name="Copart",
                )
        return None

    def _extract_vehicle(self, text: str) -> Optional[Vehicle]:
        vehicle_patterns = [
            r"VEHICLE[:\s]+(\d{4})\s+([A-Z]+(?:\-[A-Z]+)?)\s+([A-Z0-9\s\-]+?)\s+(BLACK|WHITE|SILVER|GRAY|GREY|RED|BLUE|GREEN|BROWN|GOLD|BEIGE|TAN)",
            r"VEHICLE[:\s]+(\d{4})\s+([A-Z]+(?:\-[A-Z]+)?)\s+([A-Z0-9\s\-]+)",
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
            vehicle_type=self.detect_vehicle_type(make or "", model or ""),
        )
