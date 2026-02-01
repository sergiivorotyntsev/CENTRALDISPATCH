"""IAA (Insurance Auto Auctions) document extractor."""
import re
from typing import Optional
from datetime import datetime

from extractors.base import BaseExtractor
from models.vehicle import AuctionInvoice, Vehicle, Address, AuctionSource, LocationType, VehicleType

# US State name to abbreviation mapping
STATE_ABBREVS = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
    'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
    'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
    'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO',
    'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
    'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH',
    'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT',
    'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY',
    'district of columbia': 'DC',
}


def normalize_state(state_str: str) -> str:
    """Convert state name to two-letter abbreviation."""
    if not state_str:
        return ""
    state_str = state_str.strip()
    # Already an abbreviation
    if len(state_str) == 2 and state_str.upper().isalpha():
        return state_str.upper()
    # Look up full name
    return STATE_ABBREVS.get(state_str.lower(), state_str.upper()[:2])


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
        # IAA format example:
        # Pick-Up Location:
        # Flint
        # 3088 S. Dye Rd
        # Flint Michigan 48507
        # (810) 720-0981

        name, street, city, state, postal, phone = None, None, None, None, None, None

        # First, try the most flexible approach - find the pickup section and parse line by line
        # This handles various whitespace and formatting issues from PDF extraction
        pickup_section = re.search(
            r'Pick[-\s]?Up\s*Location[:\s]*(.+?)(?:Stock|Invoice|Sale\s*Date|Buyer|Receipt|\n\s*\n)',
            text, re.IGNORECASE | re.DOTALL
        )

        if pickup_section:
            section_text = pickup_section.group(1)
            # Split by newlines and filter empty lines
            lines = [l.strip() for l in section_text.split('\n') if l.strip()]

            if len(lines) >= 1:
                # First line is usually the branch/location name (e.g., "Flint")
                name = lines[0]

            if len(lines) >= 2:
                # Second line is usually street address
                street = lines[1]

            # Look for city/state/zip pattern in remaining lines
            for i, line in enumerate(lines[2:] if len(lines) > 2 else lines):
                # Try "City State ZIP" format (e.g., "Flint Michigan 48507")
                addr_match = re.match(
                    r'([A-Za-z][A-Za-z\s]*?)\s+([A-Za-z]{2,})\s+(\d{5}(?:-\d{4})?)',
                    line
                )
                if addr_match:
                    city = addr_match.group(1).strip()
                    state = normalize_state(addr_match.group(2))
                    postal = addr_match.group(3)
                    # Check next line for phone
                    next_idx = i + 3 if len(lines) > 2 else i + 1
                    if len(lines) > next_idx:
                        phone_match = re.search(
                            r'\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}',
                            lines[next_idx]
                        )
                        if phone_match:
                            phone = phone_match.group(0)
                    break

                # Also try "City, State ZIP" format
                addr_match2 = re.match(
                    r'([A-Za-z][A-Za-z\s]*?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)',
                    line
                )
                if addr_match2:
                    city = addr_match2.group(1).strip()
                    state = addr_match2.group(2)
                    postal = addr_match2.group(3)
                    break

        # If flexible approach didn't work, try regex patterns
        if not (city and state):
            patterns = [
                # Pattern 1: With full state name (e.g., "Flint Michigan 48507")
                r'Pick[-\s]?Up\s*Location[:\s]*\n?\s*([A-Za-z][A-Za-z/\s\-\.]*)\n\s*([^\n]+)\n\s*([A-Za-z]+)\s+([A-Za-z]+)\s+(\d{5})',
                # Pattern 2: Standard format with state abbreviation
                r'Pick[-\s]?Up\s*Location[:\s]*\n?\s*([A-Za-z][A-Za-z/\s\-\.]*)\n\s*([^\n]+)\n\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5})',
                # Pattern 3: Inline format
                r'(?:PICKUP|Pick[-\s]?Up)\s*(?:Location|Address)?[:\s]+([A-Za-z][A-Za-z\s\-]+),\s*([^\n,]+),\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5})',
            ]

            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    groups = match.groups()
                    name = groups[0].strip()
                    street = groups[1].strip()
                    city = groups[2].strip().rstrip(',')
                    state = normalize_state(groups[3])
                    postal = groups[4]
                    break

        # Final fallback - look for any address-like pattern near "Pick-Up"
        if not (city and state):
            # Try to find address pattern anywhere after Pick-Up Location
            after_pickup = re.search(r'Pick[-\s]?Up\s*Location[:\s]*(.{50,500})', text, re.IGNORECASE | re.DOTALL)
            if after_pickup:
                section = after_pickup.group(1)
                # Look for ZIP code and work backwards
                zip_match = re.search(r'([A-Za-z][A-Za-z\s]*?)\s+([A-Za-z]{2,})\s+(\d{5})', section)
                if zip_match:
                    city = zip_match.group(1).strip()
                    state = normalize_state(zip_match.group(2))
                    postal = zip_match.group(3)
                    # Try to find street before this
                    before_city = section[:zip_match.start()]
                    street_lines = [l.strip() for l in before_city.split('\n') if l.strip() and re.search(r'\d', l)]
                    if street_lines:
                        street = street_lines[-1]

        if not (city and state):
            return None

        # Extract phone number if not found yet
        if not phone:
            # Look for phone near the pickup location section
            phone_section = text
            if pickup_section:
                # Search within and slightly after the pickup section
                start = pickup_section.start()
                end = min(pickup_section.end() + 200, len(text))
                phone_section = text[start:end]

            phone_patterns = [
                r'\((\d{3})\)\s*(\d{3})[-\.\s]?(\d{4})',  # (810) 720-0981 format
                r'(\d{3})[-\.\s](\d{3})[-\.\s](\d{4})',   # 810-720-0981 format
                r'(?:PHONE|TEL|CONTACT|Ph)[:\s]*\(?\s*(\d{3})\s*\)?[\s\-\.]*(\d{3})[\s\-\.]*(\d{4})',
            ]

            for pattern in phone_patterns:
                phone_match = re.search(pattern, phone_section, re.IGNORECASE)
                if phone_match:
                    groups = phone_match.groups()
                    if len(groups) == 3:
                        phone = f"({groups[0]}) {groups[1]}-{groups[2]}"
                    else:
                        phone = phone_match.group(0)
                    break

        # Normalize phone format if we have digits
        if phone and not re.match(r'\(\d{3}\)\s*\d{3}-\d{4}', phone):
            phone_digits = re.sub(r'\D', '', phone)
            if len(phone_digits) == 10:
                phone = f"({phone_digits[:3]}) {phone_digits[3:6]}-{phone_digits[6:]}"

        # Clean up name - add IAA prefix if not present
        if name:
            name = name.strip()
            if 'IAA' not in name.upper() and not name.lower().startswith('insurance'):
                name = f"IAA {name}"
        else:
            name = "IAA"

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
