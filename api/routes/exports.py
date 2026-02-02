"""
Export API Routes

Export data to Central Dispatch API V2.
Includes:
- Field registry endpoint (single source of truth)
- Single and batch posting
- Production corrections → training ingestion
"""

import time
import json
from typing import Optional, List, Dict, Any
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
from api.listing_fields import (
    get_registry,
    build_cd_payload as build_cd_payload_v2,
    ListingField,
    FieldSection,
    ValueSource,
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
    force: bool = Query(False, description="Force re-export even if already exported"),
):
    """
    Export extraction runs to Central Dispatch API V2.

    Set dry_run=true to preview payloads without sending.
    Set sandbox=true to use CD sandbox environment.
    Set force=true to re-export already exported runs (creates new attempt).

    IDEMPOTENCY: By default, already exported runs are skipped.
    """
    from api.database import get_connection

    previews = []
    exported_count = 0
    failed_count = 0
    skipped_count = 0

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

        # IDEMPOTENCY CHECK: Skip if already exported (unless force=True)
        if run.status == "exported" and not force:
            # Check for successful export job
            with get_connection() as conn:
                existing_job = conn.execute(
                    """SELECT id, status, created_at FROM export_jobs
                       WHERE run_id = ? AND status = 'completed'
                       ORDER BY created_at DESC LIMIT 1""",
                    (run_id,)
                ).fetchone()

            if existing_job:
                previews.append(CDPayloadPreview(
                    dispatch_id="",
                    run_id=run_id,
                    payload={},
                    validation_errors=[
                        f"Already exported (job #{existing_job['id']} on {existing_job['created_at']}). "
                        "Use force=true to re-export."
                    ],
                    is_valid=False,
                ))
                skipped_count += 1
                continue

        doc = DocumentRepository.get_by_id(run.document_id)

        # TEST DOCUMENT CHECK: Block export for test documents
        if doc:
            with get_connection() as conn:
                is_test = conn.execute(
                    "SELECT is_test FROM documents WHERE id = ?",
                    (doc.id,)
                ).fetchone()
                if is_test and is_test[0]:
                    previews.append(CDPayloadPreview(
                        dispatch_id="",
                        run_id=run_id,
                        payload={},
                        validation_errors=[
                            "Test document - export to Central Dispatch is blocked. "
                            "Use production documents for real exports."
                        ],
                        is_valid=False,
                    ))
                    skipped_count += 1
                    continue

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

            # Create export job record (always creates new record for audit trail)
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
        parts = [f"Exported {exported_count}"]
        if failed_count > 0:
            parts.append(f"failed {failed_count}")
        if skipped_count > 0:
            parts.append(f"skipped {skipped_count} (already exported)")
        message = ", ".join(parts) + "."
        status = "completed" if failed_count == 0 and skipped_count == 0 else "partial"

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


# =============================================================================
# FIELD REGISTRY ENDPOINT (Single Source of Truth)
# =============================================================================

@router.get("/field-registry")
async def get_field_registry():
    """
    Get the listing field registry.

    This is the single source of truth for all CD listing fields.
    Used by frontend for form rendering and validation.
    """
    registry = get_registry()
    return registry.to_json_schema()


@router.get("/field-registry/blocking-issues/{run_id}")
async def get_blocking_issues(run_id: int):
    """
    Get blocking issues for a specific extraction run.

    Returns list of issues that prevent posting.
    """
    run = ExtractionRunRepository.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    # Get field values
    items = ReviewItemRepository.get_by_run(run_id)
    data = {}
    for item in items:
        value = item.corrected_value if item.corrected_value else item.predicted_value
        data[item.source_key] = value

    # Check if outputs_json has more data
    if run.outputs_json:
        outputs = run.outputs_json if isinstance(run.outputs_json, dict) else json.loads(run.outputs_json)
        for key, value in outputs.items():
            if key not in data:
                data[key] = value

    # Check warehouse selection
    warehouse_selected = bool(data.get("warehouse_id") or data.get("delivery_address"))

    registry = get_registry()
    issues = registry.get_blocking_issues(data, warehouse_selected=warehouse_selected)

    return {
        "run_id": run_id,
        "is_ready": len(issues) == 0,
        "issues": issues,
    }


# =============================================================================
# BATCH POSTING
# =============================================================================

class BatchPostRequest(BaseModel):
    """Batch posting request."""
    run_ids: List[int] = Field(..., description="Extraction run IDs to post")
    post_only_ready: bool = Field(True, description="Only post runs without blocking issues")
    sandbox: bool = Field(True, description="Use CD sandbox environment")


class BatchPostResult(BaseModel):
    """Result for a single run in batch."""
    run_id: int
    document_filename: Optional[str] = None
    status: str  # "success", "failed", "skipped", "blocked"
    message: str
    cd_listing_id: Optional[str] = None
    blocking_issues: List[str] = []


class BatchPostResponse(BaseModel):
    """Batch posting response."""
    total: int
    ready: int
    not_ready: int
    posted: int
    failed: int
    skipped: int
    results: List[BatchPostResult]


@router.post("/batch-post", response_model=BatchPostResponse)
async def batch_post(request: BatchPostRequest):
    """
    Batch post multiple extraction runs to Central Dispatch.

    Includes preflight check to show:
    - How many are ready
    - How many have blocking issues
    - Option to post only ready ones
    """
    from api.database import get_connection

    registry = get_registry()
    results = []
    ready_count = 0
    not_ready_count = 0
    posted_count = 0
    failed_count = 0
    skipped_count = 0

    for run_id in request.run_ids:
        run = ExtractionRunRepository.get_by_id(run_id)
        if not run:
            results.append(BatchPostResult(
                run_id=run_id,
                status="failed",
                message="Extraction run not found",
            ))
            failed_count += 1
            continue

        doc = DocumentRepository.get_by_id(run.document_id)

        # Check if test document
        if doc:
            with get_connection() as conn:
                is_test = conn.execute(
                    "SELECT is_test FROM documents WHERE id = ?",
                    (doc.id,)
                ).fetchone()
                if is_test and is_test[0]:
                    results.append(BatchPostResult(
                        run_id=run_id,
                        document_filename=doc.filename,
                        status="skipped",
                        message="Test document - cannot export to Central Dispatch",
                    ))
                    skipped_count += 1
                    continue

        # Check if already exported
        if run.status == "exported":
            results.append(BatchPostResult(
                run_id=run_id,
                document_filename=doc.filename if doc else None,
                status="skipped",
                message="Already exported",
            ))
            skipped_count += 1
            continue

        # Get field data
        items = ReviewItemRepository.get_by_run(run_id)
        data = {}
        for item in items:
            value = item.corrected_value if item.corrected_value else item.predicted_value
            data[item.source_key] = value

        if run.outputs_json:
            outputs = run.outputs_json if isinstance(run.outputs_json, dict) else json.loads(run.outputs_json)
            for key, value in outputs.items():
                if key not in data:
                    data[key] = value

        # Check blocking issues
        warehouse_selected = bool(data.get("warehouse_id") or data.get("delivery_address"))
        issues = registry.get_blocking_issues(data, warehouse_selected=warehouse_selected)

        if issues:
            not_ready_count += 1
            if request.post_only_ready:
                results.append(BatchPostResult(
                    run_id=run_id,
                    document_filename=doc.filename if doc else None,
                    status="blocked",
                    message="Has blocking issues",
                    blocking_issues=[i["issue"] for i in issues],
                ))
                continue
        else:
            ready_count += 1

        # Build and send payload
        payload, errors = build_cd_payload(run_id)

        if errors:
            results.append(BatchPostResult(
                run_id=run_id,
                document_filename=doc.filename if doc else None,
                status="failed",
                message="; ".join(errors),
                blocking_issues=errors,
            ))
            failed_count += 1
            continue

        # Send to CD
        success, response = send_to_cd(payload, sandbox=request.sandbox)

        # Create export job
        job_id = ExportJobRepository.create(
            run_id=run_id,
            target="central_dispatch",
            payload_json=payload,
        )

        if success:
            cd_listing_id = response.get("id") or response.get("listingId")
            ExportJobRepository.update(
                job_id,
                status="completed",
                response_json=response,
                cd_listing_id=cd_listing_id,
            )
            ExtractionRunRepository.update(run_id, status="exported")
            posted_count += 1
            results.append(BatchPostResult(
                run_id=run_id,
                document_filename=doc.filename if doc else None,
                status="success",
                message="Posted successfully",
                cd_listing_id=cd_listing_id,
            ))
        else:
            ExportJobRepository.update(
                job_id,
                status="failed",
                response_json=response,
                error_message=response.get("error", "Unknown error"),
            )
            failed_count += 1
            results.append(BatchPostResult(
                run_id=run_id,
                document_filename=doc.filename if doc else None,
                status="failed",
                message=response.get("error", "Export failed"),
            ))

    return BatchPostResponse(
        total=len(request.run_ids),
        ready=ready_count,
        not_ready=not_ready_count,
        posted=posted_count,
        failed=failed_count,
        skipped=skipped_count,
        results=results,
    )


@router.post("/batch-post/preflight")
async def batch_post_preflight(run_ids: List[int]):
    """
    Preflight check for batch posting.

    Returns summary of which runs are ready and which have issues.
    Does NOT actually post anything.
    """
    from api.database import get_connection

    registry = get_registry()
    ready = []
    not_ready = []

    for run_id in run_ids:
        run = ExtractionRunRepository.get_by_id(run_id)
        if not run:
            not_ready.append({
                "run_id": run_id,
                "reason": "Run not found",
            })
            continue

        doc = DocumentRepository.get_by_id(run.document_id)

        # Check test document
        if doc:
            with get_connection() as conn:
                is_test = conn.execute(
                    "SELECT is_test FROM documents WHERE id = ?",
                    (doc.id,)
                ).fetchone()
                if is_test and is_test[0]:
                    not_ready.append({
                        "run_id": run_id,
                        "document_filename": doc.filename,
                        "reason": "Test document",
                    })
                    continue

        # Check if already exported
        if run.status == "exported":
            not_ready.append({
                "run_id": run_id,
                "document_filename": doc.filename if doc else None,
                "reason": "Already exported",
            })
            continue

        # Get field data
        items = ReviewItemRepository.get_by_run(run_id)
        data = {}
        for item in items:
            value = item.corrected_value if item.corrected_value else item.predicted_value
            data[item.source_key] = value

        if run.outputs_json:
            outputs = run.outputs_json if isinstance(run.outputs_json, dict) else json.loads(run.outputs_json)
            for key, value in outputs.items():
                if key not in data:
                    data[key] = value

        # Check blocking issues
        warehouse_selected = bool(data.get("warehouse_id") or data.get("delivery_address"))
        issues = registry.get_blocking_issues(data, warehouse_selected=warehouse_selected)

        if issues:
            not_ready.append({
                "run_id": run_id,
                "document_filename": doc.filename if doc else None,
                "issues": [i["issue"] for i in issues],
            })
        else:
            ready.append({
                "run_id": run_id,
                "document_filename": doc.filename if doc else None,
            })

    return {
        "total": len(run_ids),
        "ready_count": len(ready),
        "not_ready_count": len(not_ready),
        "ready": ready,
        "not_ready": not_ready,
    }


# =============================================================================
# PRODUCTION CORRECTIONS → TRAINING
# =============================================================================

class ProductionCorrectionItem(BaseModel):
    """Single field correction from production."""
    field_key: str
    old_value: Optional[str] = None
    new_value: str
    context_snippet: Optional[str] = None


class ProductionCorrectionsRequest(BaseModel):
    """Submit production corrections for training."""
    run_id: int
    corrections: List[ProductionCorrectionItem]
    save_to_extraction: bool = Field(True, description="Update extraction outputs_json")


class ProductionCorrectionsResponse(BaseModel):
    """Response after saving production corrections."""
    success: bool
    corrections_saved: int
    training_events_created: int
    message: str


@router.post("/production-corrections", response_model=ProductionCorrectionsResponse)
async def submit_production_corrections(request: ProductionCorrectionsRequest):
    """
    Submit production corrections for training.

    This is the SECOND training channel (primary is Test Lab).
    Production corrections:
    1. Update extraction outputs_json (if save_to_extraction=true)
    2. Create CorrectionEvent records for training
    3. Events are visible in Test Lab training dashboard

    Different from Test Lab corrections:
    - Comes from production workflow (Review & Posting)
    - Source is marked as 'production'
    - Can be toggled on/off for training
    """
    from api.database import get_connection

    run = ExtractionRunRepository.get_by_id(request.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    doc = DocumentRepository.get_by_id(run.document_id)
    at = AuctionTypeRepository.get_by_id(run.auction_type_id)

    corrections_saved = 0
    training_events_created = 0

    # Update extraction outputs_json
    if request.save_to_extraction:
        outputs = run.outputs_json if isinstance(run.outputs_json, dict) else {}
        if isinstance(run.outputs_json, str):
            outputs = json.loads(run.outputs_json)

        for correction in request.corrections:
            outputs[correction.field_key] = correction.new_value
            corrections_saved += 1

        ExtractionRunRepository.update(request.run_id, outputs_json=outputs)

    # Create production correction events in training database
    with get_connection() as conn:
        # Ensure production_corrections table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS production_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                document_id INTEGER,
                auction_type_id INTEGER,
                auction_type_code TEXT,
                field_key TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT NOT NULL,
                context_snippet TEXT,
                source TEXT DEFAULT 'production',
                applied_to_training BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                FOREIGN KEY (run_id) REFERENCES extraction_runs(id),
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
        """)

        for correction in request.corrections:
            conn.execute("""
                INSERT INTO production_corrections
                (run_id, document_id, auction_type_id, auction_type_code,
                 field_key, old_value, new_value, context_snippet)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.run_id,
                doc.id if doc else None,
                at.id if at else None,
                at.code if at else None,
                correction.field_key,
                correction.old_value,
                correction.new_value,
                correction.context_snippet,
            ))
            training_events_created += 1

        conn.commit()

    return ProductionCorrectionsResponse(
        success=True,
        corrections_saved=corrections_saved,
        training_events_created=training_events_created,
        message=f"Saved {corrections_saved} corrections, created {training_events_created} training events",
    )


@router.get("/production-corrections")
async def list_production_corrections(
    auction_type_code: Optional[str] = None,
    applied: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """
    List production corrections (for Test Lab dashboard).

    Shows corrections from production workflow that can be used for training.
    """
    from api.database import get_connection

    with get_connection() as conn:
        # Check if table exists
        table_exists = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='production_corrections'
        """).fetchone()

        if not table_exists:
            return {
                "items": [],
                "total": 0,
                "applied_count": 0,
                "pending_count": 0,
            }

        sql = "SELECT * FROM production_corrections WHERE 1=1"
        params = []

        if auction_type_code:
            sql += " AND auction_type_code = ?"
            params.append(auction_type_code)

        if applied is not None:
            sql += " AND applied_to_training = ?"
            params.append(applied)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()

        # Get counts
        total = conn.execute(
            "SELECT COUNT(*) FROM production_corrections"
        ).fetchone()[0]
        applied_count = conn.execute(
            "SELECT COUNT(*) FROM production_corrections WHERE applied_to_training = TRUE"
        ).fetchone()[0]
        pending_count = total - applied_count

    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "applied_count": applied_count,
        "pending_count": pending_count,
    }


@router.post("/production-corrections/apply-to-training")
async def apply_production_corrections_to_training(
    correction_ids: List[int] = None,
    apply_all_pending: bool = False,
):
    """
    Apply production corrections to training rules.

    This integrates production corrections into the training system.
    """
    from api.database import get_connection
    from api.training_db import get_session
    from services.training_service import TrainingService

    if not correction_ids and not apply_all_pending:
        raise HTTPException(
            status_code=400,
            detail="Either provide correction_ids or set apply_all_pending=true"
        )

    with get_connection() as conn:
        if apply_all_pending:
            rows = conn.execute("""
                SELECT * FROM production_corrections
                WHERE applied_to_training = FALSE
            """).fetchall()
        else:
            placeholders = ",".join("?" * len(correction_ids))
            rows = conn.execute(f"""
                SELECT * FROM production_corrections
                WHERE id IN ({placeholders}) AND applied_to_training = FALSE
            """, correction_ids).fetchall()

        if not rows:
            return {
                "success": True,
                "applied_count": 0,
                "message": "No corrections to apply",
            }

        # Group by auction type for training
        by_auction = {}
        for row in rows:
            at_code = row["auction_type_code"]
            if at_code not in by_auction:
                by_auction[at_code] = []
            by_auction[at_code].append(dict(row))

        applied_count = 0

        # Apply to training service
        session = next(get_session())
        try:
            service = TrainingService(session)

            for at_code, corrections in by_auction.items():
                for corr in corrections:
                    # Create training example from production correction
                    service.save_corrections(
                        run_id=corr["run_id"],
                        corrections=[{
                            "field_key": corr["field_key"],
                            "predicted_value": corr["old_value"],
                            "corrected_value": corr["new_value"],
                            "was_correct": False,
                        }],
                        mark_validated=True,
                        source="production",
                    )
                    applied_count += 1

            # Mark as applied
            for row in rows:
                conn.execute(
                    "UPDATE production_corrections SET applied_to_training = TRUE WHERE id = ?",
                    (row["id"],)
                )
            conn.commit()

        finally:
            session.close()

    return {
        "success": True,
        "applied_count": applied_count,
        "message": f"Applied {applied_count} production corrections to training",
    }
