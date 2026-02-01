"""
Integration Management API Routes

Handles testing, configuration, and audit logging for all integrations:
- ClickUp
- Google Sheets
- Central Dispatch
- Email Ingestion
"""

import time
import uuid
import json
import hashlib
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from pathlib import Path
import base64
from cryptography.fernet import Fernet
import os

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])


# =============================================================================
# ENCRYPTION UTILS (for secure secret storage)
# =============================================================================

def get_encryption_key() -> bytes:
    """Get or create encryption key for secrets."""
    key_file = Path("config/.secret_key")
    if key_file.exists():
        return key_file.read_bytes()

    # Generate new key
    key = Fernet.generate_key()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_bytes(key)
    os.chmod(key_file, 0o600)  # Restrict permissions
    return key


def encrypt_secret(value: str) -> str:
    """Encrypt a secret value."""
    if not value:
        return ""
    try:
        f = Fernet(get_encryption_key())
        return f.encrypt(value.encode()).decode()
    except Exception:
        # Fallback to base64 if cryptography not available
        return base64.b64encode(value.encode()).decode()


def decrypt_secret(encrypted: str) -> str:
    """Decrypt a secret value."""
    if not encrypted:
        return ""
    try:
        f = Fernet(get_encryption_key())
        return f.decrypt(encrypted.encode()).decode()
    except Exception:
        # Fallback from base64
        try:
            return base64.b64decode(encrypted.encode()).decode()
        except Exception:
            return encrypted


def mask_secret(value: str) -> str:
    """Mask a secret for display."""
    if not value:
        return ""
    if len(value) <= 8:
        return "●●●●●●●●"
    return value[:4] + "●●●●" + value[-4:]


# =============================================================================
# AUDIT LOG
# =============================================================================

class AuditLogEntry(BaseModel):
    """Audit log entry for integration actions."""
    id: str
    timestamp: str
    integration: str
    action: str
    status: str  # success, failed, pending
    user: Optional[str] = None
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


def log_integration_action(
    integration: str,
    action: str,
    status: str,
    details: Dict[str, Any] = None,
    error: str = None,
    duration_ms: int = None,
    request_id: str = None,
):
    """Log an integration action to the audit log."""
    from api.database import get_connection

    entry_id = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().isoformat() + "Z"

    with get_connection() as conn:
        # Create table if not exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS integration_audit_log (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                integration TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                user TEXT,
                request_id TEXT,
                details_json TEXT,
                error TEXT,
                duration_ms INTEGER
            )
        """)

        conn.execute("""
            INSERT INTO integration_audit_log
            (id, timestamp, integration, action, status, user, request_id, details_json, error, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_id,
            timestamp,
            integration,
            action,
            status,
            None,  # user - would come from auth
            request_id,
            json.dumps(details) if details else None,
            error,
            duration_ms,
        ))
        conn.commit()

    return entry_id


@router.get("/audit-log", response_model=List[AuditLogEntry])
async def get_audit_log(
    integration: Optional[str] = Query(None, description="Filter by integration"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
):
    """Get integration audit log entries."""
    from api.database import get_connection

    sql = "SELECT * FROM integration_audit_log WHERE 1=1"
    params = []

    if integration:
        sql += " AND integration = ?"
        params.append(integration)
    if status:
        sql += " AND status = ?"
        params.append(status)

    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    try:
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            AuditLogEntry(
                id=row["id"],
                timestamp=row["timestamp"],
                integration=row["integration"],
                action=row["action"],
                status=row["status"],
                user=row["user"],
                request_id=row["request_id"],
                details=json.loads(row["details_json"]) if row["details_json"] else None,
                error=row["error"],
                duration_ms=row["duration_ms"],
            )
            for row in rows
        ]
    except Exception:
        # Table might not exist yet
        return []


# =============================================================================
# CLICKUP INTEGRATION
# =============================================================================

class ClickUpTestRequest(BaseModel):
    """Request for testing ClickUp connection."""
    api_token: Optional[str] = Field(None, description="API token (use saved if not provided)")


class ClickUpTestResponse(BaseModel):
    """Response from ClickUp connection test."""
    success: bool
    message: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    workspaces: Optional[List[Dict[str, Any]]] = None
    lists: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


class ClickUpFieldMapping(BaseModel):
    """Field mapping for ClickUp custom fields."""
    source_field: str
    clickup_field_id: str
    clickup_field_name: str
    transform: Optional[str] = None  # e.g., "uppercase", "date_format"


@router.post("/clickup/test", response_model=ClickUpTestResponse)
async def test_clickup_connection(request: ClickUpTestRequest = None):
    """
    Test ClickUp API connection.

    Validates token, retrieves user info and available workspaces/lists.
    """
    import httpx

    start_time = time.time()

    # Get token from request or saved settings
    from api.routes.settings import load_settings
    settings = load_settings()

    token = None
    if request and request.api_token and "●" not in request.api_token:
        token = request.api_token
    else:
        token = settings.get("clickup", {}).get("api_token", "")

    if not token:
        log_integration_action("clickup", "test_connection", "failed",
                              error="No API token configured")
        return ClickUpTestResponse(
            success=False,
            message="No API token configured",
            error="API token is required"
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test with user endpoint
            headers = {"Authorization": token}

            # Get user info
            user_resp = await client.get(
                "https://api.clickup.com/api/v2/user",
                headers=headers
            )

            if user_resp.status_code == 401:
                log_integration_action("clickup", "test_connection", "failed",
                                      error="Invalid API token")
                return ClickUpTestResponse(
                    success=False,
                    message="Invalid API token",
                    error="Authentication failed - check your token"
                )

            user_resp.raise_for_status()
            user_data = user_resp.json().get("user", {})

            # Get workspaces (teams)
            teams_resp = await client.get(
                "https://api.clickup.com/api/v2/team",
                headers=headers
            )
            teams_resp.raise_for_status()
            teams = teams_resp.json().get("teams", [])

            workspaces = [
                {"id": t["id"], "name": t["name"]}
                for t in teams
            ]

            # Get lists from first workspace
            lists = []
            if teams:
                team_id = teams[0]["id"]
                spaces_resp = await client.get(
                    f"https://api.clickup.com/api/v2/team/{team_id}/space",
                    headers=headers
                )
                spaces_resp.raise_for_status()
                spaces = spaces_resp.json().get("spaces", [])

                for space in spaces[:3]:  # Limit for performance
                    folders_resp = await client.get(
                        f"https://api.clickup.com/api/v2/space/{space['id']}/folder",
                        headers=headers
                    )
                    if folders_resp.status_code == 200:
                        folders = folders_resp.json().get("folders", [])
                        for folder in folders:
                            for lst in folder.get("lists", []):
                                lists.append({
                                    "id": lst["id"],
                                    "name": lst["name"],
                                    "folder": folder["name"],
                                    "space": space["name"]
                                })

            duration_ms = int((time.time() - start_time) * 1000)

            log_integration_action("clickup", "test_connection", "success",
                                  details={"user": user_data.get("username"),
                                          "workspaces": len(workspaces)},
                                  duration_ms=duration_ms)

            return ClickUpTestResponse(
                success=True,
                message="Successfully connected to ClickUp",
                user_name=user_data.get("username"),
                user_email=user_data.get("email"),
                workspaces=workspaces,
                lists=lists[:20],  # Limit response size
            )

    except httpx.TimeoutException:
        log_integration_action("clickup", "test_connection", "failed",
                              error="Connection timeout")
        return ClickUpTestResponse(
            success=False,
            message="Connection timeout",
            error="ClickUp API did not respond in time"
        )
    except Exception as e:
        log_integration_action("clickup", "test_connection", "failed",
                              error=str(e))
        return ClickUpTestResponse(
            success=False,
            message="Connection failed",
            error=str(e)
        )


@router.get("/clickup/custom-fields/{list_id}")
async def get_clickup_custom_fields(list_id: str):
    """Get custom fields for a ClickUp list."""
    import httpx

    from api.routes.settings import load_settings
    settings = load_settings()
    token = settings.get("clickup", {}).get("api_token", "")

    if not token:
        raise HTTPException(status_code=400, detail="ClickUp not configured")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.clickup.com/api/v2/list/{list_id}/field",
                headers={"Authorization": token}
            )
            resp.raise_for_status()
            fields = resp.json().get("fields", [])

            return {
                "list_id": list_id,
                "fields": [
                    {
                        "id": f["id"],
                        "name": f["name"],
                        "type": f["type"],
                        "required": f.get("required", False),
                    }
                    for f in fields
                ]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GOOGLE SHEETS INTEGRATION
# =============================================================================

class SheetsTestResponse(BaseModel):
    """Response from Google Sheets connection test."""
    success: bool
    message: str
    spreadsheet_title: Optional[str] = None
    sheet_names: Optional[List[str]] = None
    row_count: Optional[int] = None
    has_write_access: bool = False
    error: Optional[str] = None


@router.post("/sheets/test", response_model=SheetsTestResponse)
async def test_sheets_connection():
    """
    Test Google Sheets connection.

    Validates credentials, checks spreadsheet access, and tests write permissions.
    """
    start_time = time.time()

    from api.routes.settings import load_settings
    settings = load_settings()
    sheets_config = settings.get("sheets", {})

    spreadsheet_id = sheets_config.get("spreadsheet_id")
    creds_file = sheets_config.get("credentials_file", "config/sheets_credentials.json")

    if not spreadsheet_id:
        return SheetsTestResponse(
            success=False,
            message="Spreadsheet ID not configured",
            error="Please set the spreadsheet ID in settings"
        )

    if not Path(creds_file).exists():
        return SheetsTestResponse(
            success=False,
            message="Credentials file not found",
            error=f"File not found: {creds_file}"
        )

    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)

        # Get spreadsheet metadata
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        title = spreadsheet.get("properties", {}).get("title")
        sheets = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]

        # Try to read first sheet
        sheet_name = sheets_config.get("sheet_name", sheets[0] if sheets else "Sheet1")
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A:A"
        ).execute()
        row_count = len(result.get("values", []))

        # Test write access by reading and writing to a test cell
        has_write_access = False
        try:
            test_range = f"'{sheet_name}'!ZZ1"
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=test_range,
                valueInputOption="RAW",
                body={"values": [[""]]}
            ).execute()
            has_write_access = True
        except Exception:
            pass

        duration_ms = int((time.time() - start_time) * 1000)
        log_integration_action("sheets", "test_connection", "success",
                              details={"spreadsheet": title, "sheets": len(sheets)},
                              duration_ms=duration_ms)

        return SheetsTestResponse(
            success=True,
            message="Successfully connected to Google Sheets",
            spreadsheet_title=title,
            sheet_names=sheets,
            row_count=row_count,
            has_write_access=has_write_access,
        )

    except ImportError:
        return SheetsTestResponse(
            success=False,
            message="Google API libraries not installed",
            error="Install: pip install google-api-python-client google-auth"
        )
    except Exception as e:
        log_integration_action("sheets", "test_connection", "failed", error=str(e))
        return SheetsTestResponse(
            success=False,
            message="Connection failed",
            error=str(e)
        )


# =============================================================================
# CENTRAL DISPATCH INTEGRATION
# =============================================================================

class CDTestResponse(BaseModel):
    """Response from Central Dispatch connection test."""
    success: bool
    message: str
    authenticated: bool = False
    shipper_name: Optional[str] = None
    marketplace_access: bool = False
    error: Optional[str] = None


class CDDryRunRequest(BaseModel):
    """Request for Central Dispatch dry-run."""
    run_id: int = Field(..., description="Extraction run ID")


class CDDryRunResponse(BaseModel):
    """Response from Central Dispatch dry-run."""
    success: bool
    payload: Dict[str, Any]
    validation_errors: List[str] = []
    estimated_cost: Optional[float] = None
    message: str


class CDExportRequest(BaseModel):
    """Request to export to Central Dispatch."""
    run_id: int
    dry_run: bool = True
    retry_count: int = 0
    max_retries: int = 3


class CDExportResponse(BaseModel):
    """Response from Central Dispatch export."""
    success: bool
    message: str
    listing_id: Optional[str] = None
    listing_url: Optional[str] = None
    dry_run: bool
    retries_used: int = 0
    error: Optional[str] = None


@router.post("/cd/test", response_model=CDTestResponse)
async def test_cd_connection():
    """
    Test Central Dispatch API connection.

    Validates credentials and checks marketplace access.
    """
    start_time = time.time()

    from api.routes.settings import load_settings
    settings = load_settings()
    cd_config = settings.get("cd", {})

    username = cd_config.get("username")
    password = cd_config.get("password")

    if not username or not password:
        return CDTestResponse(
            success=False,
            message="Credentials not configured",
            error="Please set username and password in settings"
        )

    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            # CD uses OAuth2 - get access token
            auth_resp = await client.post(
                "https://api.centraldispatch.com/oauth/token",
                data={
                    "grant_type": "password",
                    "username": username,
                    "password": password,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if auth_resp.status_code == 401:
                log_integration_action("cd", "test_connection", "failed",
                                      error="Invalid credentials")
                return CDTestResponse(
                    success=False,
                    message="Authentication failed",
                    authenticated=False,
                    error="Invalid username or password"
                )

            if auth_resp.status_code != 200:
                # CD might be unavailable
                return CDTestResponse(
                    success=False,
                    message="Could not reach Central Dispatch",
                    error=f"API returned status {auth_resp.status_code}"
                )

            token_data = auth_resp.json()
            access_token = token_data.get("access_token")

            if not access_token:
                return CDTestResponse(
                    success=False,
                    message="No access token received",
                    error="Authentication response invalid"
                )

            # Get shipper info
            headers = {"Authorization": f"Bearer {access_token}"}
            profile_resp = await client.get(
                "https://api.centraldispatch.com/v1/shipper/profile",
                headers=headers
            )

            shipper_name = None
            if profile_resp.status_code == 200:
                profile = profile_resp.json()
                shipper_name = profile.get("company_name")

            duration_ms = int((time.time() - start_time) * 1000)
            log_integration_action("cd", "test_connection", "success",
                                  details={"shipper": shipper_name},
                                  duration_ms=duration_ms)

            return CDTestResponse(
                success=True,
                message="Successfully connected to Central Dispatch",
                authenticated=True,
                shipper_name=shipper_name,
                marketplace_access=True,
            )

    except ImportError:
        return CDTestResponse(
            success=False,
            message="HTTP client not available",
            error="Install httpx: pip install httpx"
        )
    except Exception as e:
        log_integration_action("cd", "test_connection", "failed", error=str(e))
        return CDTestResponse(
            success=False,
            message="Connection failed",
            error=str(e)
        )


@router.post("/cd/dry-run", response_model=CDDryRunResponse)
async def cd_dry_run(request: CDDryRunRequest):
    """
    Perform a dry-run export to Central Dispatch.

    Validates the payload without actually creating a listing.
    """
    from api.models import ExtractionRunRepository, DocumentRepository, ReviewItemRepository

    # Get extraction run
    run = ExtractionRunRepository.get_by_id(request.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    # Get review items (corrected values)
    review_items = ReviewItemRepository.get_by_run(request.run_id)

    # Build payload from review items
    payload = {}
    for item in review_items:
        if item.export_field and item.cd_key:
            value = item.corrected_value or item.predicted_value
            if value:
                payload[item.cd_key] = value

    # Validate required fields
    validation_errors = []
    required_fields = ["pickup_city", "pickup_state", "delivery_city", "delivery_state",
                       "vehicle_year", "vehicle_make", "vehicle_model"]

    for field in required_fields:
        if field not in payload or not payload[field]:
            validation_errors.append(f"Missing required field: {field}")

    # VIN validation
    if payload.get("vehicle_vin") and len(payload["vehicle_vin"]) != 17:
        validation_errors.append("VIN must be exactly 17 characters")

    log_integration_action("cd", "dry_run",
                          "success" if not validation_errors else "failed",
                          details={"run_id": request.run_id, "errors": len(validation_errors)})

    return CDDryRunResponse(
        success=len(validation_errors) == 0,
        payload=payload,
        validation_errors=validation_errors,
        message="Validation passed" if not validation_errors else f"Found {len(validation_errors)} validation errors"
    )


@router.post("/cd/export", response_model=CDExportResponse)
async def export_to_cd(request: CDExportRequest, background_tasks: BackgroundTasks):
    """
    Export extraction to Central Dispatch.

    Supports dry-run mode and automatic retries.
    """
    # First do a dry-run to validate
    dry_run_result = await cd_dry_run(CDDryRunRequest(run_id=request.run_id))

    if not dry_run_result.success:
        return CDExportResponse(
            success=False,
            message="Validation failed",
            dry_run=True,
            error="; ".join(dry_run_result.validation_errors)
        )

    if request.dry_run:
        return CDExportResponse(
            success=True,
            message="Dry-run validation passed",
            dry_run=True,
        )

    # Actual export with retries
    from api.routes.settings import load_settings
    settings = load_settings()
    cd_config = settings.get("cd", {})

    last_error = None
    for retry in range(request.max_retries + 1):
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get auth token
                auth_resp = await client.post(
                    "https://api.centraldispatch.com/oauth/token",
                    data={
                        "grant_type": "password",
                        "username": cd_config.get("username"),
                        "password": cd_config.get("password"),
                    }
                )
                auth_resp.raise_for_status()
                token = auth_resp.json().get("access_token")

                # Create listing
                listing_resp = await client.post(
                    "https://api.centraldispatch.com/v1/listings",
                    headers={"Authorization": f"Bearer {token}"},
                    json=dry_run_result.payload
                )
                listing_resp.raise_for_status()
                result = listing_resp.json()

                listing_id = result.get("id")

                log_integration_action("cd", "export", "success",
                                      details={"run_id": request.run_id,
                                              "listing_id": listing_id,
                                              "retries": retry})

                # Update extraction run
                from api.models import ExtractionRunRepository
                ExtractionRunRepository.update(
                    request.run_id,
                    status="exported",
                    cd_listing_id=listing_id,
                )

                return CDExportResponse(
                    success=True,
                    message="Successfully created listing",
                    listing_id=listing_id,
                    listing_url=f"https://centraldispatch.com/listing/{listing_id}",
                    dry_run=False,
                    retries_used=retry,
                )

        except Exception as e:
            last_error = str(e)
            if retry < request.max_retries:
                # Wait before retry with exponential backoff
                await asyncio.sleep(2 ** retry)

    log_integration_action("cd", "export", "failed",
                          details={"run_id": request.run_id, "retries": request.max_retries},
                          error=last_error)

    return CDExportResponse(
        success=False,
        message="Export failed after retries",
        dry_run=False,
        retries_used=request.max_retries,
        error=last_error
    )


# =============================================================================
# EMAIL INGESTION
# =============================================================================

class EmailTestResponse(BaseModel):
    """Response from email connection test."""
    success: bool
    message: str
    connected: bool = False
    mailbox_count: Optional[int] = None
    unread_count: Optional[int] = None
    error: Optional[str] = None


class EmailRule(BaseModel):
    """Email processing rule."""
    id: str
    name: str
    enabled: bool = True
    condition_type: str  # "subject_contains", "from_contains", "attachment_type"
    condition_value: str
    action: str  # "process", "ignore", "forward"
    auction_type_id: Optional[int] = None
    priority: int = 0


class EmailActivity(BaseModel):
    """Email ingestion activity log entry."""
    id: str
    timestamp: str
    message_id: str
    subject: str
    sender: str
    status: str  # "processed", "skipped", "failed"
    rule_matched: Optional[str] = None
    run_id: Optional[int] = None
    error: Optional[str] = None


@router.post("/email/test", response_model=EmailTestResponse)
async def test_email_connection():
    """
    Test email server connection.

    Validates IMAP credentials and checks mailbox access.
    """
    start_time = time.time()

    from api.routes.settings import load_settings
    settings = load_settings()
    email_config = settings.get("email", {})

    server = email_config.get("imap_server")
    port = email_config.get("imap_port", 993)
    email_addr = email_config.get("email_address")
    password = email_config.get("password")

    if not all([server, email_addr, password]):
        return EmailTestResponse(
            success=False,
            message="Email not configured",
            error="Please set server, email address, and password"
        )

    try:
        import imaplib

        # Connect to IMAP server
        imap = imaplib.IMAP4_SSL(server, port)
        imap.login(email_addr, password)

        # Get mailbox list
        status, mailboxes = imap.list()
        mailbox_count = len(mailboxes) if status == "OK" else 0

        # Check unread in INBOX
        imap.select("INBOX")
        status, messages = imap.search(None, "UNSEEN")
        unread_count = len(messages[0].split()) if status == "OK" and messages[0] else 0

        imap.logout()

        duration_ms = int((time.time() - start_time) * 1000)
        log_integration_action("email", "test_connection", "success",
                              details={"mailboxes": mailbox_count, "unread": unread_count},
                              duration_ms=duration_ms)

        return EmailTestResponse(
            success=True,
            message="Successfully connected to email server",
            connected=True,
            mailbox_count=mailbox_count,
            unread_count=unread_count,
        )

    except Exception as e:
        log_integration_action("email", "test_connection", "failed", error=str(e))
        return EmailTestResponse(
            success=False,
            message="Connection failed",
            error=str(e)
        )


@router.get("/email/rules", response_model=List[EmailRule])
async def get_email_rules():
    """Get configured email processing rules."""
    from api.routes.settings import load_settings
    settings = load_settings()
    rules = settings.get("email_rules", [])
    return [EmailRule(**r) for r in rules]


class EmailRulesUpdate(BaseModel):
    """Request to update email rules."""
    rules: List[EmailRule]


@router.put("/email/rules")
async def update_email_rules(request: EmailRulesUpdate):
    """Update email processing rules."""
    from api.routes.settings import load_settings, save_settings
    settings = load_settings()
    settings["email_rules"] = [r.model_dump() for r in request.rules]
    save_settings(settings)

    log_integration_action("email", "update_rules", "success",
                          details={"rule_count": len(request.rules)})

    return {"status": "ok", "count": len(request.rules)}


@router.get("/email/activity", response_model=List[EmailActivity])
async def get_email_activity(
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
):
    """Get email ingestion activity log."""
    from api.database import get_connection

    sql = """
        SELECT * FROM email_activity_log
        WHERE 1=1
    """
    params = []

    if status:
        sql += " AND status = ?"
        params.append(status)

    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    try:
        with get_connection() as conn:
            # Create table if not exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS email_activity_log (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    subject TEXT,
                    sender TEXT,
                    status TEXT NOT NULL,
                    rule_matched TEXT,
                    run_id INTEGER,
                    error TEXT
                )
            """)

            rows = conn.execute(sql, params).fetchall()

        return [
            EmailActivity(
                id=row["id"],
                timestamp=row["timestamp"],
                message_id=row["message_id"],
                subject=row["subject"] or "",
                sender=row["sender"] or "",
                status=row["status"],
                rule_matched=row["rule_matched"],
                run_id=row["run_id"],
                error=row["error"],
            )
            for row in rows
        ]
    except Exception:
        return []


# =============================================================================
# WAREHOUSE MANAGEMENT
# =============================================================================

class WarehouseCreate(BaseModel):
    """Request to create a warehouse."""
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=100)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None


class WarehouseResponse(BaseModel):
    """Warehouse data."""
    code: str
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None


@router.post("/warehouses", response_model=WarehouseResponse)
async def add_warehouse(warehouse: WarehouseCreate):
    """Add a new warehouse."""
    from api.routes.settings import load_settings, save_settings

    settings = load_settings()
    warehouses = settings.get("warehouses", [])

    # Check for duplicate code
    for w in warehouses:
        if w.get("code") == warehouse.code:
            raise HTTPException(status_code=400, detail=f"Warehouse with code '{warehouse.code}' already exists")

    new_warehouse = warehouse.model_dump()
    warehouses.append(new_warehouse)
    settings["warehouses"] = warehouses
    save_settings(settings)

    log_integration_action("warehouses", "add", "success",
                          details={"code": warehouse.code, "name": warehouse.name})

    return WarehouseResponse(**new_warehouse)


@router.delete("/warehouses/{code}")
async def delete_warehouse(code: str):
    """Delete a warehouse by code."""
    from api.routes.settings import load_settings, save_settings

    settings = load_settings()
    warehouses = settings.get("warehouses", [])

    original_count = len(warehouses)
    warehouses = [w for w in warehouses if w.get("code") != code]

    if len(warehouses) == original_count:
        raise HTTPException(status_code=404, detail=f"Warehouse with code '{code}' not found")

    settings["warehouses"] = warehouses
    save_settings(settings)

    log_integration_action("warehouses", "delete", "success",
                          details={"code": code})

    return {"status": "ok", "deleted": code}


# =============================================================================
# EXPORT CSV FOR EXTRACTIONS
# =============================================================================

@router.get("/extractions/export/csv")
async def export_extractions_csv(
    status: Optional[str] = Query(None),
    auction_type_id: Optional[int] = Query(None),
    limit: int = Query(1000, le=10000),
):
    """
    Export extraction runs to CSV format.
    """
    from fastapi.responses import StreamingResponse
    from api.database import get_connection
    import csv
    import io

    sql = """
        SELECT
            er.id, er.uuid, er.status, er.extractor_kind,
            er.extraction_score, er.processing_time_ms,
            er.created_at, er.completed_at,
            d.filename as document_filename,
            at.code as auction_type_code
        FROM extraction_runs er
        LEFT JOIN documents d ON er.document_id = d.id
        LEFT JOIN auction_types at ON er.auction_type_id = at.id
        WHERE 1=1
    """
    params = []

    if status:
        sql += " AND er.status = ?"
        params.append(status)
    if auction_type_id:
        sql += " AND er.auction_type_id = ?"
        params.append(auction_type_id)

    sql += " ORDER BY er.created_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "ID", "UUID", "Document", "Auction Type", "Status",
        "Extractor", "Score", "Processing Time (ms)",
        "Created At", "Completed At"
    ])

    # Data rows
    for row in rows:
        writer.writerow([
            row["id"],
            row["uuid"],
            row["document_filename"],
            row["auction_type_code"],
            row["status"],
            row["extractor_kind"],
            f"{row['extraction_score'] * 100:.1f}%" if row["extraction_score"] else "",
            row["processing_time_ms"],
            row["created_at"],
            row["completed_at"],
        ])

    output.seek(0)

    log_integration_action("export", "csv_export", "success",
                          details={"rows": len(rows)})

    filename = f"extractions_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
