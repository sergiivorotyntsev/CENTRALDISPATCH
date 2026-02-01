"""Manheim (Cox Automotive) document extractor."""

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


class ManheimExtractor(BaseExtractor):
    """Extractor for Manheim Bill of Sale and Vehicle Release documents."""

    @property
    def source(self) -> AuctionSource:
        return AuctionSource.MANHEIM

    @property
    def indicators(self) -> list:
        return [
            "Manheim",
            "Cox Automotive",
            "BILL OF SALE",
            "VEHICLE RELEASE",
            "Manheim.com",
            "Release ID",
            "YMMT",
            "OFFSITE VEHICLE RELEASE",
        ]

    @property
    def indicator_weights(self) -> dict:
        return {
            "Manheim": 3.0,
            "Cox Automotive": 2.0,
            "Manheim.com": 2.5,
            "BILL OF SALE": 1.0,
            "VEHICLE RELEASE": 1.5,
            "Release ID": 1.5,
            "YMMT": 1.0,
            "OFFSITE VEHICLE RELEASE": 2.0,
        }

    def extract(self, pdf_path: str) -> Optional[AuctionInvoice]:
        pages_text = self.extract_pages_text(pdf_path)
        full_text = "\n".join(pages_text)

        if not self.can_extract(full_text):
            return None

        invoice = AuctionInvoice(source=self.source, buyer_id="", buyer_name="")

        account_match = re.search(r"Account\s*#?\s*:?\s*(\d+)", full_text)
        if account_match:
            invoice.buyer_id = account_match.group(1)

        buyer_match = re.search(
            r"(?:Name|Buyer)\s+([A-Z][A-Za-z\s]+(?:INC|LLC|CORP|Inc|Llc|Corp)?)", full_text
        )
        if buyer_match:
            invoice.buyer_name = buyer_match.group(1).strip()

        date_patterns = [
            r"Sale\s*Date\s+(\d{1,2}-[A-Z]{3}-\d{4})",
            r"Sale\s*Date\s+(\d{1,2}/\d{1,2}/\d{4})",
            r"Purchase\s*Date\s+[A-Za-z]+,\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        ]
        for pattern in date_patterns:
            date_match = re.search(pattern, full_text, re.IGNORECASE)
            if date_match:
                date_str = date_match.group(1)
                for fmt in ["%d-%b-%Y", "%m/%d/%Y", "%b %d, %Y"]:
                    try:
                        invoice.sale_date = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                break

        invoice.location_type = self._detect_location_type(full_text)

        release_match = re.search(r"Release\s*ID\s+([A-Z0-9]+)", full_text)
        if release_match:
            invoice.release_id = release_match.group(1)

        work_order_match = re.search(r"Work\s*Order\s*#?\s*:?\s*(\d+)", full_text)
        if work_order_match:
            invoice.stock_number = work_order_match.group(1)

        pickup_location = self._extract_pickup_location(full_text)
        if pickup_location:
            invoice.pickup_address = pickup_location

        vehicle = self._extract_vehicle(full_text)
        if vehicle:
            invoice.vehicles.append(vehicle)

        total_match = re.search(
            r"(?:Final\s*Sale\s*Price|TOTAL|SUB\s*TOTAL)\s*\$?\s*([\d,]+\.?\d*)",
            full_text,
            re.IGNORECASE,
        )
        if total_match:
            try:
                invoice.total_amount = float(total_match.group(1).replace(",", ""))
            except ValueError:
                pass

        return invoice

    def _detect_location_type(self, text: str) -> LocationType:
        offsite_indicators = ["OFFSITE VEHICLE RELEASE", "not located at a Manheim facility"]
        for indicator in offsite_indicators:
            if indicator.lower() in text.lower():
                return LocationType.OFFSITE
        return LocationType.ONSITE

    def _extract_pickup_location(self, text: str) -> Optional[Address]:
        pickup_patterns = [
            r"Pickup\s*Location\s+Address\s+([A-Za-z\s\-]+)\n\s*(\d+[A-Za-z0-9\s\.\-]+)\n\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)",
            r"Address\s+(\d+[A-Za-z0-9\s\.\-]+)\n\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)",
        ]

        for pattern in pickup_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 5:
                    return Address(
                        name=groups[0].strip(),
                        street=groups[1].strip(),
                        city=groups[2].strip(),
                        state=groups[3],
                        postal_code=groups[4],
                        country="US",
                    )
                elif len(groups) == 4:
                    return Address(
                        street=groups[0].strip(),
                        city=groups[1].strip(),
                        state=groups[2],
                        postal_code=groups[3],
                        country="US",
                    )
        return None

    def _extract_vehicle(self, text: str) -> Optional[Vehicle]:
        ymmt_patterns = [
            r"YMMT\s+(\d{4})\s+([A-Za-z\-]+)\s+([A-Za-z0-9\s\-]+)",
            r"Vehicle\s*Information\s*\n.*?(\d{4})\s+([A-Za-z\-]+)\s+([A-Za-z0-9\s\-]+)",
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
        color_match = re.search(r"Color\s+([A-Za-z]+)", text)
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
            vehicle_type=self.detect_vehicle_type(make, model or ""),
        )
