"""Google Sheets Exporter with schema management.

Features:
1. Auto-create headers from schema
2. Append records with idempotency
3. Batch write support
4. Override field handling
"""
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml

from core.config import SheetsConfig

logger = logging.getLogger(__name__)

# Schema version
SCHEMA_VERSION = 1
SCHEMA_FILE = "schemas/sheets_columns_v1.yaml"


def load_schema() -> Dict[str, Any]:
    """Load column schema from YAML file."""
    schema_path = Path(SCHEMA_FILE)
    if not schema_path.exists():
        # Use embedded minimal schema
        return {
            "version": SCHEMA_VERSION,
            "columns": [
                {"name": "run_id"},
                {"name": "row_id"},
                {"name": "processed_at"},
                {"name": "source_type"},
                {"name": "attachment_name"},
                {"name": "attachment_hash"},
                {"name": "auction"},
                {"name": "extraction_score"},
                {"name": "status"},
                {"name": "vin"},
                {"name": "vehicle_year"},
                {"name": "vehicle_make"},
                {"name": "vehicle_model"},
                {"name": "lot_number"},
                {"name": "pickup_city"},
                {"name": "pickup_state"},
                {"name": "pickup_zip"},
                {"name": "gate_pass"},
                {"name": "buyer_id"},
                {"name": "reference_id"},
                {"name": "total_amount"},
                {"name": "error"},
            ],
        }

    with open(schema_path) as f:
        return yaml.safe_load(f)


class SheetsExporter:
    """Exports extraction results to Google Sheets."""

    def __init__(self, config: SheetsConfig):
        self.config = config
        self.schema = load_schema()
        self.column_names = [col["name"] for col in self.schema["columns"]]
        self._service = None
        self._sheet_id = None

    def _get_service(self):
        """Get or create Google Sheets API service."""
        if self._service is not None:
            return self._service

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            # Try service account credentials
            creds_path = Path(self.config.credentials_file)
            if creds_path.exists():
                creds = service_account.Credentials.from_service_account_file(
                    str(creds_path),
                    scopes=["https://www.googleapis.com/auth/spreadsheets"],
                )
                self._service = build("sheets", "v4", credentials=creds)
                return self._service
            else:
                raise FileNotFoundError(f"Credentials file not found: {creds_path}")

        except ImportError:
            raise ImportError(
                "Google Sheets dependencies not installed. "
                "Run: pip install google-auth google-api-python-client"
            )

    def _get_sheet_id(self) -> int:
        """Get the sheet ID for the configured sheet name."""
        if self._sheet_id is not None:
            return self._sheet_id

        service = self._get_service()
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=self.config.spreadsheet_id
        ).execute()

        for sheet in spreadsheet.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("title") == self.config.sheet_name:
                self._sheet_id = props.get("sheetId")
                return self._sheet_id

        # Sheet not found, create it
        logger.info(f"Creating sheet: {self.config.sheet_name}")
        self._create_sheet()
        return self._sheet_id

    def _create_sheet(self):
        """Create a new sheet with headers."""
        service = self._get_service()

        # Add sheet
        request = {
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": self.config.sheet_name,
                        }
                    }
                }
            ]
        }
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=self.config.spreadsheet_id,
            body=request,
        ).execute()

        self._sheet_id = result["replies"][0]["addSheet"]["properties"]["sheetId"]

        # Add headers
        self.ensure_headers()

    def ensure_headers(self) -> bool:
        """Ensure headers exist in the sheet. Returns True if headers were created."""
        service = self._get_service()

        # Check if first row has headers
        range_name = f"{self.config.sheet_name}!A1:{chr(64 + len(self.column_names))}1"
        result = service.spreadsheets().values().get(
            spreadsheetId=self.config.spreadsheet_id,
            range=range_name,
        ).execute()

        values = result.get("values", [])
        if values and values[0]:
            # Headers exist
            existing = values[0]
            if existing == self.column_names:
                return False  # Headers already correct

            # Check if we need to update
            if len(existing) < len(self.column_names):
                logger.warning("Existing headers incomplete, will add missing columns")

        # Write headers
        service.spreadsheets().values().update(
            spreadsheetId=self.config.spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body={"values": [self.column_names]},
        ).execute()

        # Format headers (bold)
        try:
            self._format_headers()
        except Exception as e:
            logger.warning(f"Could not format headers: {e}")

        return True

    def _format_headers(self):
        """Apply formatting to header row."""
        service = self._get_service()
        sheet_id = self._get_sheet_id()

        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {
                                "red": 0.9,
                                "green": 0.9,
                                "blue": 0.9,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
        ]

        service.spreadsheets().batchUpdate(
            spreadsheetId=self.config.spreadsheet_id,
            body={"requests": requests},
        ).execute()

    def _record_to_row(self, record: Dict[str, Any], run_id: str = None) -> List[Any]:
        """Convert a record dict to a row list matching schema columns."""
        row_id = str(uuid.uuid4())[:8]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Set defaults
        record.setdefault("run_id", run_id or "manual")
        record.setdefault("row_id", row_id)
        record.setdefault("processed_at", now)
        record.setdefault("source_type", "batch")

        row = []
        for col_name in self.column_names:
            value = record.get(col_name, "")

            # Handle special types
            if value is None:
                value = ""
            elif isinstance(value, bool):
                value = "TRUE" if value else "FALSE"
            elif isinstance(value, (list, dict)):
                value = str(value)
            elif isinstance(value, float):
                value = round(value, 2)

            row.append(value)

        return row

    def append_record(self, record: Dict[str, Any], run_id: str = None) -> bool:
        """Append a single record to the sheet."""
        self.ensure_headers()

        service = self._get_service()
        row = self._record_to_row(record, run_id)

        range_name = f"{self.config.sheet_name}!A:A"
        service.spreadsheets().values().append(
            spreadsheetId=self.config.spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        return True

    def write_batch(self, records: List[Dict[str, Any]], run_id: str = None) -> int:
        """Write multiple records to the sheet. Returns count of rows written."""
        if not records:
            return 0

        self.ensure_headers()

        service = self._get_service()
        rows = [self._record_to_row(record, run_id) for record in records]

        range_name = f"{self.config.sheet_name}!A:A"
        service.spreadsheets().values().append(
            spreadsheetId=self.config.spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()

        logger.info(f"Written {len(rows)} rows to {self.config.sheet_name}")
        return len(rows)

    def find_by_hash(self, attachment_hash: str) -> Optional[int]:
        """Find a row by attachment hash. Returns row number or None."""
        service = self._get_service()

        # Find the hash column index
        try:
            hash_col_idx = self.column_names.index("attachment_hash")
        except ValueError:
            return None

        col_letter = chr(65 + hash_col_idx)  # A, B, C, etc.
        range_name = f"{self.config.sheet_name}!{col_letter}:{col_letter}"

        result = service.spreadsheets().values().get(
            spreadsheetId=self.config.spreadsheet_id,
            range=range_name,
        ).execute()

        values = result.get("values", [])
        for i, row in enumerate(values):
            if row and row[0] == attachment_hash:
                return i + 1  # 1-indexed

        return None

    def is_duplicate(self, attachment_hash: str) -> bool:
        """Check if a record with this hash already exists."""
        return self.find_by_hash(attachment_hash) is not None

    def get_overrides(self, attachment_hash: str) -> Dict[str, Any]:
        """Get manual override values for a record."""
        service = self._get_service()
        row_num = self.find_by_hash(attachment_hash)

        if not row_num:
            return {}

        # Get the full row
        range_name = f"{self.config.sheet_name}!A{row_num}:{chr(64 + len(self.column_names))}{row_num}"
        result = service.spreadsheets().values().get(
            spreadsheetId=self.config.spreadsheet_id,
            range=range_name,
        ).execute()

        values = result.get("values", [[]])[0]
        if not values:
            return {}

        # Extract override columns
        overrides = {}
        override_cols = ["override_vin", "override_pickup_address", "override_notes", "override_auction"]
        for col_name in override_cols:
            try:
                idx = self.column_names.index(col_name)
                if idx < len(values) and values[idx]:
                    # Remove 'override_' prefix for the key
                    key = col_name.replace("override_", "")
                    overrides[key] = values[idx]
            except ValueError:
                pass

        return overrides
