"""
Export API Routes

Export data to Central Dispatch API V2.
"""

import time
import json
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from api.models import (
    ExportJobRepository,
    ExtractionRunRepository,
    DocumentRepository,
    AuctionTypeRepository,
    ReviewItemRepository,
    ExportStatus,
)

router = APIRouter(prefix="/api/exports", tags=["Exports"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class CDExportRequest(BaseModel):
    """Request to export to Central Dispatch."""
    run_ids: List[int] = Field(..., description="Extraction run IDs to export")
    dry_run: bool = Field(True, description="Preview only, don't actually send")
    sandbox: bool = Field(True, description="Use CD sandbox environment")


class CDPayloadPreview(BaseModel):
    """Preview of a CD API V2 payload."""
    dispatch_id: str
    run_id: int
    document_filename: Optional[str] = None
    payload: dict
    validation_errors: List[str] = []
    is_valid: bool = True


class CDExportResponse(BaseModel):
    """Response after CD export."""
    job_id: Optional[int] = None
    status: str
    previews: List[CDPayloadPreview] = []
    exported_count: int = 0
    failed_count: int = 0
    message: str


class ExportJobResponse(BaseModel):
    """Export job status."""
    id: int
    status: str
    target: str = "central_dispatch"
    payload_json: Optional[dict] = None
    response_json: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

    class Config:
        from_attributes = True


class ExportJobListResponse(BaseModel):
    """List of export jobs."""
    items: List[ExportJobResponse]
    total: int


# =============================================================================
# CD PAYLOAD BUILDER
# =============================================================================

def build_cd_payload(run_id: int) -> tuple[dict, List[str]]:
    """
    Build Central Dispatch API V2 payload from extraction run.

    Returns (payload, validation_errors).
    """
    run = ExtractionRunRepository.get_by_id(run_id)
    if not run:
        return {}, ["Extraction run not found"]

    doc = DocumentRepository.get_by_id(run.document_id)
    if not doc:
        return {}, ["Document not found"]

    at = AuctionTypeRepository.get_by_id(run.auction_type_id)
    if not at:
        return {}, ["Auction type not found"]

    # Get review items (with corrections applied)
    items = ReviewItemRepository.get_by_run(run_id)
    item_map = {}
    for item in items:
        if not item.export_field:
            continue
        # Use corrected value if available, else predicted
        value = item.corrected_value if item.corrected_value else item.predicted_value
        item_map[item.source_key] = value

    errors = []

    # Build dispatch_id
    dispatch_id = f"DC-{datetime.now().strftime('%Y%m%d')}-{at.code}-{run.uuid[:8].upper()}"

    # Get field values with defaults
    def get_field(key: str, default=None):
        return item_map.get(key, default)

    # Validate required fields
    required = ["vehicle_vin", "pickup_address", "pickup_city", "pickup_state", "pickup_zip"]
    for field in required:
        if not get_field(field):
            errors.append(f"Missing required field: {field}")

    # Validate VIN
    vin = get_field("vehicle_vin", "")
    if vin and len(vin) != 17:
        errors.append(f"VIN must be 17 characters, got {len(vin)}")

    # Calculate dates
    available_date = datetime.now().strftime("%Y-%m-%d")
    expiration_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    # Determine trailer type
    is_inop = get_field("vehicle_is_inoperable", False)
    if isinstance(is_inop, str):
        is_inop = is_inop.lower() in ("true", "yes", "1", "inoperable")
    trailer_type = "OPEN"

    # Build stops
    pickup_stop = {
        "stopNumber": 1,
        "locationName": get_field("pickup_name") or f"{at.name} Pickup",
        "address": get_field("pickup_address", ""),
        "city": get_field("pickup_city", ""),
        "state": get_field("pickup_state", ""),
        "postalCode": get_field("pickup_zip", ""),
        "country": "US",
        "locationType": "AUCTION",
    }

    dropoff_stop = {
        "stopNumber": 2,
        "locationName": get_field("dropoff_name", "Warehouse"),
        "address": get_field("dropoff_address", "TBD"),
        "city": get_field("dropoff_city", "TBD"),
        "state": get_field("dropoff_state", "TX"),
        "postalCode": get_field("dropoff_zip", "00000"),
        "country": "US",
        "locationType": "BUSINESS",
    }

    # Build vehicle
    vehicle = {
        "pickupStopNumber": 1,
        "dropoffStopNumber": 2,
        "vin": get_field("vehicle_vin", ""),
        "year": int(get_field("vehicle_year", 0) or 0),
        "make": get_field("vehicle_make", ""),
        "model": get_field("vehicle_model", ""),
        "isInoperable": is_inop,
    }

    if get_field("vehicle_lot"):
        vehicle["lotNumber"] = str(get_field("vehicle_lot"))

    # Build price
    total_amount = get_field("total_amount")
    try:
        price_total = float(total_amount) if total_amount else 0.0
    except (ValueError, TypeError):
        price_total = 0.0

    if price_total <= 0:
        price_total = 450.00  # Default price

    price = {
        "total": price_total,
        "cod": {
            "amount": price_total,
            "paymentMethod": "CASH",
            "paymentLocation": "DELIVERY",
        }
    }

    # Build notes
    notes_parts = []
    if get_field("reference_id"):
        notes_parts.append(f"Ref: {get_field('reference_id')}")
    if get_field("buyer_id"):
        notes_parts.append(f"Buyer: {get_field('buyer_id')}")
    notes = "; ".join(notes_parts) if notes_parts else ""

    # Full payload (CD Listings API V2)
    payload = {
        "externalId": dispatch_id,
        "trailerType": trailer_type,
        "hasInOpVehicle": is_inop,
        "availableDate": available_date,
        "expirationDate": expiration_date,
        "transportationReleaseNotes": notes,
        "price": price,
        "stops": [pickup_stop, dropoff_stop],
        "vehicles": [vehicle],
        "marketplaces": [
            {
                "marketplaceId": 12345,  # Placeholder
                "digitalOffersEnabled": True,
                "searchable": True,
                "offersAutoAcceptEnabled": False,
            }
        ],
    }

    return payload, errors


def send_to_cd(payload: dict, sandbox: bool = True) -> tuple[bool, dict]:
    """
    Send payload to Central Dispatch API V2.

    Returns (success, response_data).
    """
    import requests

    if sandbox:
        base_url = "https://api.sandbox.centraldispatch.com"
    else:
        base_url = "https://api.centraldispatch.com"

    endpoint = f"{base_url}/listings"

    # CD V2 uses Content-Type versioning
    headers = {
        "Content-Type": "application/vnd.coxauto.v2+json",
        "Accept": "application/vnd.coxauto.v2+json",
        # Note: Real implementation would include auth
        # "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=30,
        )

        if response.status_code in (200, 201):
            return True, response.json()
        else:
            return False, {
                "status_code": response.status_code,
                "error": response.text,
            }

    except requests.RequestException as e:
        return False, {"error": str(e)}


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/central-dispatch", response_model=CDExportResponse)
async def export_to_cd(
    data: CDExportRequest,
    background_tasks: BackgroundTasks,
):
    """
    Export extraction runs to Central Dispatch API V2.

    Set dry_run=true to preview payloads without sending.
    Set sandbox=true to use CD sandbox environment.
    """
    previews = []
    exported_count = 0
    failed_count = 0

    for run_id in data.run_ids:
        run = ExtractionRunRepository.get_by_id(run_id)
        if not run:
            previews.append(CDPayloadPreview(
                dispatch_id="",
                run_id=run_id,
                payload={},
                validation_errors=["Run not found"],
                is_valid=False,
            ))
            failed_count += 1
            continue

        doc = DocumentRepository.get_by_id(run.document_id)

        # Build payload
        payload, errors = build_cd_payload(run_id)
        is_valid = len(errors) == 0

        preview = CDPayloadPreview(
            dispatch_id=payload.get("externalId", ""),
            run_id=run_id,
            document_filename=doc.filename if doc else None,
            payload=payload,
            validation_errors=errors,
            is_valid=is_valid,
        )
        previews.append(preview)

        if not data.dry_run and is_valid:
            # Actually send to CD
            success, response = send_to_cd(payload, sandbox=data.sandbox)

            # Create export job record
            job_id = ExportJobRepository.create(
                run_id=run_id,
                target="central_dispatch",
                payload_json=payload,
            )

            if success:
                ExportJobRepository.update(
                    job_id,
                    status="completed",
                    response_json=response,
                )
                exported_count += 1

                # Update run status
                ExtractionRunRepository.update(run_id, status="exported")
            else:
                ExportJobRepository.update(
                    job_id,
                    status="failed",
                    response_json=response,
                    error_message=response.get("error", "Unknown error"),
                )
                failed_count += 1

    if data.dry_run:
        message = f"Dry run: {len(previews)} payloads generated. Set dry_run=false to export."
        status = "preview"
    else:
        message = f"Exported {exported_count} records. {failed_count} failed."
        status = "completed" if failed_count == 0 else "partial"

    return CDExportResponse(
        status=status,
        previews=previews,
        exported_count=exported_count,
        failed_count=failed_count,
        message=message,
    )


@router.get("/central-dispatch/preview/{run_id}", response_model=CDPayloadPreview)
async def preview_cd_payload(run_id: int):
    """
    Preview the CD API V2 payload for a single run.

    Useful for debugging before export.
    """
    run = ExtractionRunRepository.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    doc = DocumentRepository.get_by_id(run.document_id)

    payload, errors = build_cd_payload(run_id)

    return CDPayloadPreview(
        dispatch_id=payload.get("externalId", ""),
        run_id=run_id,
        document_filename=doc.filename if doc else None,
        payload=payload,
        validation_errors=errors,
        is_valid=len(errors) == 0,
    )


@router.get("/jobs", response_model=ExportJobListResponse)
async def list_export_jobs(
    status: Optional[str] = Query(None),
    target: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List export jobs with optional filtering."""
    from api.database import get_connection

    sql = "SELECT * FROM export_jobs WHERE 1=1"
    params = []

    if status:
        sql += " AND status = ?"
        params.append(status)
    if target:
        sql += " AND target = ?"
        params.append(target)

    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM export_jobs WHERE 1=1"
        ).fetchone()[0]

    items = []
    for row in rows:
        data = dict(row)
        if data.get("payload_json"):
            data["payload_json"] = json.loads(data["payload_json"])
        if data.get("response_json"):
            data["response_json"] = json.loads(data["response_json"])

        items.append(ExportJobResponse(
            id=data["id"],
            status=data["status"],
            target=data["target"],
            payload_json=data.get("payload_json"),
            response_json=data.get("response_json"),
            error_message=data.get("error_message"),
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
        ))

    return ExportJobListResponse(items=items, total=total)


@router.get("/jobs/{job_id}", response_model=ExportJobResponse)
async def get_export_job(job_id: int):
    """Get details of an export job."""
    job = ExportJobRepository.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    return ExportJobResponse(
        id=job.id,
        status=job.status,
        target=job.target,
        payload_json=job.payload_json,
        response_json=job.response_json,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.post("/jobs/{job_id}/retry", response_model=ExportJobResponse)
async def retry_export_job(job_id: int, sandbox: bool = Query(True)):
    """
    Retry a failed export job.
    """
    job = ExportJobRepository.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    if job.status != "failed":
        raise HTTPException(status_code=400, detail="Can only retry failed jobs")

    # Resend
    success, response = send_to_cd(job.payload_json, sandbox=sandbox)

    if success:
        ExportJobRepository.update(
            job_id,
            status="completed",
            response_json=response,
            error_message=None,
        )
    else:
        ExportJobRepository.update(
            job_id,
            status="failed",
            response_json=response,
            error_message=response.get("error", "Unknown error"),
        )

    job = ExportJobRepository.get_by_id(job_id)

    return ExportJobResponse(
        id=job.id,
        status=job.status,
        target=job.target,
        payload_json=job.payload_json,
        response_json=job.response_json,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )
