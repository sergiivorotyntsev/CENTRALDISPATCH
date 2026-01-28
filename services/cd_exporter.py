"""Central Dispatch exporter with defaults and validation.

Features:
1. Load default values from YAML config
2. Apply rules based on auction source and warehouse
3. Validate payload before sending
4. Export records from Google Sheets with READY_FOR_CD status
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml
from tenacity import retry, stop_after_attempt, wait_exponential

from services.central_dispatch import CentralDispatchClient, APIError
from services.sheets import SheetsClient, PickupRecord, PickupStatus

logger = logging.getLogger(__name__)


@dataclass
class CDDefaults:
    """Default values for Central Dispatch listings."""
    trailer_type: str = "OPEN"
    payment_method: str = "CASH_CERTIFIED_FUNDS"
    payment_location: str = "DELIVERY"
    marketplace_id: int = 10000

    # Company info (shipper)
    company_name: str = ""
    company_address: str = ""
    company_city: str = ""
    company_state: str = ""
    company_zip: str = ""
    company_phone: str = ""
    company_contact: str = ""

    # Availability
    available_date_offset_days: int = 0  # 0 = today
    expiration_days: int = 14

    # Notes templates
    pickup_instructions: str = ""
    delivery_instructions: str = ""


@dataclass
class CDRule:
    """Conditional rule for CD listings."""
    name: str
    condition: Dict[str, Any]  # e.g., {"auction_source": "COPART"}
    overrides: Dict[str, Any]  # Values to override


class CDDefaultsLoader:
    """Loads CD defaults and rules from YAML config."""

    DEFAULT_CONFIG = {
        "defaults": {
            "trailer_type": "OPEN",
            "payment_method": "CASH_CERTIFIED_FUNDS",
            "payment_location": "DELIVERY",
            "marketplace_id": 10000,
            "available_date_offset_days": 0,
            "expiration_days": 14,
        },
        "rules": [
            {
                "name": "enclosed_for_luxury",
                "condition": {"vehicle_make": ["BMW", "MERCEDES", "PORSCHE", "AUDI"]},
                "overrides": {"trailer_type": "ENCLOSED"},
            },
        ],
    }

    def __init__(self, config_file: Optional[str] = "cd_defaults.yaml"):
        self.config_file = config_file
        self.defaults = CDDefaults()
        self.rules: List[CDRule] = []
        self._load_config()

    def _load_config(self):
        """Load configuration from file or use defaults."""
        config = self.DEFAULT_CONFIG.copy()

        if self.config_file and Path(self.config_file).exists():
            try:
                with open(self.config_file) as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        config.update(file_config)
                logger.info(f"Loaded CD defaults from {self.config_file}")
            except Exception as e:
                logger.warning(f"Failed to load CD defaults: {e}")

        # Parse defaults
        defaults_dict = config.get("defaults", {})
        for key, value in defaults_dict.items():
            if hasattr(self.defaults, key):
                setattr(self.defaults, key, value)

        # Parse rules
        for rule_dict in config.get("rules", []):
            self.rules.append(CDRule(
                name=rule_dict.get("name", ""),
                condition=rule_dict.get("condition", {}),
                overrides=rule_dict.get("overrides", {}),
            ))

    def apply_rules(self, record: PickupRecord) -> Dict[str, Any]:
        """Apply rules to a record and return overrides."""
        overrides = {}

        for rule in self.rules:
            if self._matches_condition(record, rule.condition):
                logger.debug(f"Rule '{rule.name}' matched for {record.vin}")
                overrides.update(rule.overrides)

        return overrides

    @staticmethod
    def _matches_condition(record: PickupRecord, condition: Dict[str, Any]) -> bool:
        """Check if a record matches a rule condition."""
        for field_name, expected in condition.items():
            actual = getattr(record, field_name, None)

            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False

        return True


class CDPayloadValidator:
    """Validates CD listing payload before sending."""

    REQUIRED_FIELDS = [
        "trailerType",
        "availableDate",
        "price",
        "stops",
        "vehicles",
    ]

    REQUIRED_STOP_FIELDS = ["city", "state", "postalCode"]
    REQUIRED_VEHICLE_FIELDS = ["vin", "year", "make", "model"]

    def validate(self, payload: Dict[str, Any]) -> List[str]:
        """Validate payload. Returns list of error messages."""
        errors = []

        # Check required top-level fields
        for field in self.REQUIRED_FIELDS:
            if field not in payload:
                errors.append(f"Missing required field: {field}")

        # Validate stops
        stops = payload.get("stops", [])
        if len(stops) < 2:
            errors.append("At least 2 stops (pickup and delivery) required")

        for i, stop in enumerate(stops):
            for field in self.REQUIRED_STOP_FIELDS:
                if not stop.get(field):
                    errors.append(f"Stop {i + 1} missing required field: {field}")

        # Validate vehicles
        vehicles = payload.get("vehicles", [])
        if not vehicles:
            errors.append("At least 1 vehicle required")

        for i, vehicle in enumerate(vehicles):
            for field in self.REQUIRED_VEHICLE_FIELDS:
                if not vehicle.get(field):
                    errors.append(f"Vehicle {i + 1} missing required field: {field}")

            # Validate VIN format
            vin = vehicle.get("vin", "")
            if len(vin) != 17:
                errors.append(f"Vehicle {i + 1} has invalid VIN length: {len(vin)}")

        # Validate price
        price = payload.get("price", {})
        if not price.get("total") or price["total"] <= 0:
            errors.append("Price total must be greater than 0")

        return errors


class CDExporter:
    """Exports records to Central Dispatch from Google Sheets."""

    def __init__(
        self,
        cd_client: CentralDispatchClient,
        sheets_client: Optional[SheetsClient],
        defaults_loader: Optional[CDDefaultsLoader] = None,
    ):
        self.cd_client = cd_client
        self.sheets_client = sheets_client
        self.defaults_loader = defaults_loader or CDDefaultsLoader()
        self.validator = CDPayloadValidator()

    def build_listing_payload(
        self,
        record: PickupRecord,
        delivery_address: Dict[str, str],
        price: float,
    ) -> Dict[str, Any]:
        """Build CD listing payload from a pickup record."""
        defaults = self.defaults_loader.defaults
        rule_overrides = self.defaults_loader.apply_rules(record)

        # Merge defaults with overrides
        trailer_type = rule_overrides.get("trailer_type", defaults.trailer_type)

        # Calculate dates
        available_date = datetime.utcnow() + timedelta(days=defaults.available_date_offset_days)
        expiration_date = available_date + timedelta(days=defaults.expiration_days)

        # Build pickup stop
        pickup_stop = {
            "stopNumber": 1,
            "city": record.pickup_city,
            "state": record.pickup_state,
            "postalCode": record.pickup_zip,
            "country": "US",
        }
        if record.pickup_name:
            pickup_stop["locationName"] = record.pickup_name
        if record.pickup_address_raw:
            pickup_stop["address"] = record.pickup_address_raw

        # Build delivery stop
        delivery_stop = {
            "stopNumber": 2,
            "city": delivery_address.get("city", ""),
            "state": delivery_address.get("state", ""),
            "postalCode": delivery_address.get("zip", ""),
            "country": "US",
        }
        if delivery_address.get("name"):
            delivery_stop["locationName"] = delivery_address["name"]
        if delivery_address.get("address"):
            delivery_stop["address"] = delivery_address["address"]

        # Build vehicle
        vehicle = {
            "pickupStopNumber": 1,
            "dropoffStopNumber": 2,
            "vin": record.vin,
            "year": int(record.vehicle_year) if record.vehicle_year else 2020,
            "make": record.vehicle_make,
            "model": record.vehicle_model,
            "vehicleType": "SUV",  # Default
            "isInoperable": False,
        }
        if record.vehicle_color:
            vehicle["color"] = record.vehicle_color
        if record.lot_number:
            vehicle["lotNumber"] = record.lot_number

        # Build payload
        payload = {
            "trailerType": trailer_type,
            "hasInOpVehicle": False,
            "availableDate": available_date.strftime("%Y-%m-%dT00:00:00Z"),
            "expirationDate": expiration_date.strftime("%Y-%m-%dT00:00:00Z"),
            "price": {
                "total": price,
                "cod": {
                    "amount": price,
                    "paymentMethod": defaults.payment_method,
                    "paymentLocation": defaults.payment_location,
                },
            },
            "stops": [pickup_stop, delivery_stop],
            "vehicles": [vehicle],
            "marketplaces": [{"marketplaceId": defaults.marketplace_id}],
        }

        # Add transport notes with reference
        notes_parts = []
        if record.auction_source:
            if record.auction_source == "COPART" and record.lot_number:
                notes_parts.append(f"LOT#: {record.lot_number}")
            elif record.auction_source == "IAA" and record.lot_number:
                notes_parts.append(f"Stock#: {record.lot_number}")
            elif record.auction_source == "MANHEIM":
                notes_parts.append(f"Release ID: {record.lot_number}")

        if record.gate_pass:
            notes_parts.append(f"Gate Pass: {record.gate_pass}")

        if defaults.pickup_instructions:
            notes_parts.append(defaults.pickup_instructions)

        if notes_parts:
            payload["transportationReleaseNotes"] = " | ".join(notes_parts)

        return payload

    def export_record(
        self,
        record: PickupRecord,
        delivery_address: Dict[str, str],
        price: float,
        row_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Export a single record to Central Dispatch."""
        # Build payload
        payload = self.build_listing_payload(record, delivery_address, price)

        # Validate
        errors = self.validator.validate(payload)
        if errors:
            error_msg = "; ".join(errors)
            logger.error(f"Validation failed for {record.vin}: {error_msg}")

            if self.sheets_client and row_number:
                self.sheets_client.update_status(
                    row_number, PickupStatus.ERROR, error_message=f"Validation: {error_msg}"
                )

            return {"success": False, "error": error_msg}

        # Send to CD
        try:
            result = self.cd_client.create_listing_raw(payload)

            if result.get("success"):
                listing_id = result.get("listing_id", "")
                logger.info(f"Created CD listing {listing_id} for {record.vin}")

                if self.sheets_client and row_number:
                    self.sheets_client.update_status(
                        row_number,
                        PickupStatus.CD_CREATED,
                        cd_listing_id=listing_id,
                    )

                return {"success": True, "listing_id": listing_id}
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"CD API error for {record.vin}: {error_msg}")

                if self.sheets_client and row_number:
                    self.sheets_client.update_status(
                        row_number, PickupStatus.ERROR, error_message=f"CD API: {error_msg}"
                    )

                return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Exception exporting {record.vin}: {e}")
            if self.sheets_client and row_number:
                self.sheets_client.update_status(
                    row_number, PickupStatus.ERROR, error_message=str(e)
                )
            return {"success": False, "error": str(e)}

    def export_pending_from_sheets(
        self,
        delivery_address: Dict[str, str],
        default_price: float = 500.0,
    ) -> Dict[str, Any]:
        """Export all READY_FOR_CD records from Google Sheets."""
        if not self.sheets_client:
            return {"error": "Sheets client not configured"}

        records = self.sheets_client.get_records_by_status(PickupStatus.READY_FOR_CD)
        logger.info(f"Found {len(records)} records ready for CD export")

        results = {"exported": 0, "failed": 0, "errors": []}

        for row_number, record in records:
            result = self.export_record(record, delivery_address, default_price, row_number)

            if result.get("success"):
                results["exported"] += 1
            else:
                results["failed"] += 1
                results["errors"].append({
                    "vin": record.vin,
                    "error": result.get("error"),
                })

        return results


# Add create_listing_raw method to CentralDispatchClient if not exists
def _add_create_listing_raw():
    """Monkey-patch CentralDispatchClient to add create_listing_raw method."""
    from services.central_dispatch import CentralDispatchClient

    if not hasattr(CentralDispatchClient, "create_listing_raw"):
        def create_listing_raw(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            """Create a listing from raw payload dict."""
            response = self._make_request("POST", "/listings", data=payload)
            if response.status_code == 201:
                location = response.headers.get("Location", "")
                listing_id = location.split("/")[-1] if location else None
                return {
                    "success": True,
                    "listing_id": listing_id,
                    "etag": response.headers.get("ETag"),
                    "location": location,
                }
            else:
                return {"success": False, "error": response.text}

        CentralDispatchClient.create_listing_raw = create_listing_raw


_add_create_listing_raw()
