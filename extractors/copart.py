"""Copart document extractor."""
import re
import logging
from typing import Optional
from datetime import datetime

from extractors.base import BaseExtractor
from extractors.address_parser import extract_pickup_address, extract_lines_after_label
from models.vehicle import AuctionInvoice, Vehicle, Address, AuctionSource, LocationType, VehicleType

logger = logging.getLogger(__name__)


class CopartExtractor(BaseExtractor):
    """Extractor for Copart Sales Receipt/Bill of Sale documents."""

    # Default label patterns for fields (can be overridden by learned rules)
    DEFAULT_LABELS = {
        'pickup_address': [
            r'PHYSICAL\s*ADDRESS\s*(?:OF\s*)?LOT',
            r'LOT\s*(?:LOCATION|ADDRESS)',
        ],
        'buyer_name': [
            r'MEMBER',
            r'SOLD\s*TO',
            r'BUYER',
        ],
        'seller_name': [
            r'SELLER',
            r'SOLD\s*(?:BY|THROUGH)',
        ],
    }

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

        # Load learned rules before extraction
        self.load_learned_rules()

        invoice = AuctionInvoice(source=self.source, buyer_id="", buyer_name="")

        # Extract buyer ID (MEMBER number)
        member_match = re.search(r'MEMBER[:\s]+(\d+)', text)
        if member_match:
            invoice.buyer_id = member_match.group(1)

        # Extract buyer name using learned rules or defaults
        invoice.buyer_name = self._extract_buyer_name(text)

        # Extract seller name using learned rules or defaults
        invoice.seller_name = self._extract_seller_name(text)

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

        # Extract pickup location using learned rules or defaults
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
        """Extract pickup address using learned rules or shared parser."""
        # First check for learned rules
        rule = self.get_learned_rule('pickup_address')

        if rule and rule.label_patterns:
            logger.debug(f"Using learned rule for pickup_address: {rule.label_patterns}")
            # Try learned patterns first
            for label_pattern in rule.label_patterns:
                lines = extract_lines_after_label(text, label_pattern)
                if lines:
                    # Parse address from lines
                    addr = self._parse_address_from_lines(lines, rule.exclude_patterns)
                    if addr:
                        return addr

        # Fallback to default extraction
        return extract_pickup_address(
            text,
            source="Copart",
            custom_labels=self.DEFAULT_LABELS.get('pickup_address', [])
        )

    def _parse_address_from_lines(self, lines: list, exclude_patterns: list = None) -> Optional[Address]:
        """Parse address from extracted lines."""
        if not lines:
            return None

        # Filter out excluded patterns
        if exclude_patterns:
            filtered_lines = []
            for line in lines:
                excluded = False
                for pattern in exclude_patterns:
                    if pattern.lower() in line.lower():
                        excluded = True
                        break
                if not excluded:
                    filtered_lines.append(line)
            lines = filtered_lines

        if not lines:
            return None

        # Try to parse address
        street = lines[0] if lines else ""

        # Look for city/state/zip in remaining lines
        city, state, zip_code = "", "", ""
        for line in lines[1:]:
            parsed_city, parsed_state, parsed_zip = self.parse_address(line)
            if parsed_city and parsed_state:
                city, state, zip_code = parsed_city, parsed_state, parsed_zip
                break

        if street or (city and state):
            return Address(
                name="Copart",
                street=street,
                city=city,
                state=state,
                postal_code=zip_code,
            )

        return None

    def _extract_seller_name(self, text: str) -> str:
        """Extract seller name using learned rules or defaults."""
        # Check for learned rule
        rule = self.get_learned_rule('seller_name')

        if rule and rule.label_patterns:
            for label_pattern in rule.label_patterns:
                lines = extract_lines_after_label(text, label_pattern, max_lines=3)
                if lines:
                    # Get the first non-excluded line
                    for line in lines:
                        if not rule.should_exclude(line):
                            # Clean up the seller name
                            seller = re.sub(r'\s+\d+.*$', '', line.strip())
                            if len(seller) > 2 and len(seller) < 100:
                                return seller

        # Fallback: try default patterns
        seller_patterns = [
            r'SELLER[:\s]*\n([A-Z][A-Za-z\s\-\.]+?)(?:\n|SOLD)',
            r'SELLER[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n|SOLD)',
        ]
        for pattern in seller_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                seller = match.group(1).strip()
                seller = re.sub(r'\s+\d+.*$', '', seller)
                if len(seller) > 2 and len(seller) < 100:
                    return seller

        return ""

    def _extract_buyer_name(self, text: str) -> str:
        """
        Extract buyer name from Copart document.

        In Copart documents, the buyer name typically appears on lines BELOW
        the MEMBER: line, not on the same line. Format:
            MEMBER:
            12345678
            BROADWAY MOTORING INC
        or:
            MEMBER: 12345678
            BROADWAY MOTORING INC
        """
        lines = text.split('\n')
        found_member = False
        found_member_number = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Look for MEMBER line
            if not found_member and re.search(r'MEMBER[:\s]*', stripped, re.IGNORECASE):
                found_member = True
                # Check if member number is on same line
                member_num_match = re.search(r'MEMBER[:\s]*(\d+)', stripped, re.IGNORECASE)
                if member_num_match:
                    found_member_number = True
                continue

            if found_member:
                # Skip empty lines
                if not stripped:
                    continue

                # If we haven't found the member number yet, this line might be it
                if not found_member_number and re.match(r'^\d+$', stripped):
                    found_member_number = True
                    continue

                # After member number, the next non-empty line should be the buyer name
                if found_member_number:
                    # Check if this looks like a company/person name (not a field label or number)
                    if (re.match(r'^[A-Z]', stripped) and
                        not re.match(r'^(LOT|VIN|VEHICLE|SALE|DATE|RECEIPT|TOTAL|PHYSICAL)', stripped, re.IGNORECASE) and
                        len(stripped) > 2 and len(stripped) < 100):
                        # Clean up - remove trailing numbers/dates
                        buyer_name = re.sub(r'\s+\d+.*$', '', stripped)
                        return buyer_name

                # Safety: don't search too far
                if i > 20:
                    break

        # Fallback: try traditional patterns
        buyer_name_patterns = [
            r'SOLD\s*TO[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n|MEMBER)',
            r'BUYER[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n|MEMBER)',
            r'Bill\s*To[:\s]+([A-Z][A-Za-z\s\-\.]+?)(?:\n)',
        ]
        for pattern in buyer_name_patterns:
            name_match = re.search(pattern, text, re.IGNORECASE)
            if name_match:
                buyer_name = name_match.group(1).strip()
                buyer_name = re.sub(r'\s+\d+.*$', '', buyer_name)
                if len(buyer_name) > 2 and len(buyer_name) < 100:
                    return buyer_name

        return ""

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
