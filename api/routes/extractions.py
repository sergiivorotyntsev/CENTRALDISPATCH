"""
Extractions API Routes

Run and manage extraction runs on documents.
"""

import time
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from api.models import (
    ExtractionRunRepository,
    DocumentRepository,
    AuctionTypeRepository,
    ModelVersionRepository,
    ReviewItemRepository,
    ExtractionRun,
    RunStatus,
)

router = APIRouter(prefix="/api/extractions", tags=["Extractions"])


def generate_order_id(make: str, model: str, sale_date: datetime = None) -> str:
    """
    Generate custom Order ID in format: MMDD + MAKE(3) + MODEL(1) + SEQ

    Example: February 1st + Jeep Grand Cherokee = 21JEEG1
    - 21 = Month 2, Day 1 (concatenated, not padded)
    - JEE = First 3 letters of Make (JEEP)
    - G = First letter of Model (GRAND)
    - 1 = Sequence number (incremented for duplicates)

    Args:
        make: Vehicle make (e.g., "Jeep", "Toyota")
        model: Vehicle model (e.g., "Grand Cherokee", "Camry")
        sale_date: Date to use (defaults to today)

    Returns:
        Order ID string like "21JEEG1"
    """
    if sale_date is None:
        sale_date = datetime.now()

    # Month + Day (as digits, e.g., February 1 = "21")
    month = str(sale_date.month)  # 1-12, no zero padding
    day = str(sale_date.day)      # 1-31, no zero padding
    date_part = month + day

    # Make: first 3 letters, uppercase
    make_clean = ''.join(c for c in make.upper() if c.isalpha())[:3]
    make_part = make_clean.ljust(3, 'X')  # Pad with X if too short

    # Model: first letter, uppercase
    model_clean = ''.join(c for c in model.upper() if c.isalpha())
    model_part = model_clean[0] if model_clean else 'X'

    # Base ID without sequence
    base_id = f"{date_part}{make_part}{model_part}"

    # Find next sequence number by checking existing runs
    from api.database import get_connection
    with get_connection() as conn:
        # Count existing orders with same base
        result = conn.execute(
            """SELECT COUNT(*) FROM extraction_runs
               WHERE outputs_json LIKE ?
               AND date(created_at) = date(?)""",
            (f'%"order_id": "{base_id}%', sale_date.strftime('%Y-%m-%d'))
        ).fetchone()
        seq = (result[0] if result else 0) + 1

    return f"{base_id}{seq}"


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ExtractionRunRequest(BaseModel):
    """Request model for running extraction."""
    document_id: int = Field(..., description="Document ID to extract from")
    force_ml: bool = Field(False, description="Force ML extraction even if no active model")


class ExtractionRunResponse(BaseModel):
    """Response model for extraction run."""
    id: int
    uuid: str
    document_id: int
    document_filename: Optional[str] = None
    auction_type_id: int
    auction_type_code: Optional[str] = None
    extractor_kind: str = "rule"
    model_version_id: Optional[int] = None
    model_version_tag: Optional[str] = None
    status: str = "pending"
    extraction_score: Optional[float] = None
    outputs: Optional[dict] = None
    errors: Optional[list] = None
    processing_time_ms: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

    class Config:
        from_attributes = True


class ExtractionRunListResponse(BaseModel):
    """Response model for extraction run list."""
    items: List[ExtractionRunResponse]
    total: int


class ExtractionFieldOutput(BaseModel):
    """A single extracted field."""
    source_key: str
    internal_key: Optional[str] = None
    cd_key: Optional[str] = None
    value: Optional[str] = None
    confidence: Optional[float] = None
    source_location: Optional[str] = None


class ExtractionDetailResponse(BaseModel):
    """Detailed extraction response with field-level outputs."""
    run: ExtractionRunResponse
    fields: List[ExtractionFieldOutput]
    raw_text_preview: Optional[str] = None


# =============================================================================
# EXTRACTION LOGIC
# =============================================================================

def run_extraction(run_id: int, document_id: int, auction_type_id: int,
                   extractor_kind: str = "rule", model_version_id: int = None):
    """
    Execute extraction on a document.

    This function is called synchronously or as a background task.
    """
    start_time = time.time()

    # Get document
    doc = DocumentRepository.get_by_id(document_id)
    if not doc:
        ExtractionRunRepository.update(
            run_id,
            status="failed",
            errors_json=[{"error": "Document not found"}],
        )
        return

    # Get auction type
    auction_type = AuctionTypeRepository.get_by_id(auction_type_id)
    if not auction_type:
        ExtractionRunRepository.update(
            run_id,
            status="failed",
            errors_json=[{"error": "Auction type not found"}],
        )
        return

    # Update status to processing
    ExtractionRunRepository.update(run_id, status="processing")

    try:
        # Get raw text from document
        raw_text = doc.raw_text or ""

        if not raw_text and doc.file_path:
            # Try to extract text
            import pdfplumber
            with pdfplumber.open(doc.file_path) as pdf:
                text_parts = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                raw_text = "\n".join(text_parts)

        if not raw_text:
            ExtractionRunRepository.update(
                run_id,
                status="failed",
                errors_json=[{"error": "Could not extract text from document"}],
            )
            return

        # Run extraction based on kind
        if extractor_kind == "ml" and model_version_id:
            # TODO: Implement ML extraction
            # For now, fall back to rule-based
            extractor_kind = "rule"

        # Rule-based extraction
        outputs = {}
        extraction_score = 0.0

        from extractors import ExtractorManager
        manager = ExtractorManager()

        # Classify and extract
        classification = manager.get_extractor_for_text(raw_text)
        if classification:
            extractor = classification
            result = extractor.extract_with_result(doc.file_path, raw_text)

            if result.invoice:
                inv = result.invoice
                # Map invoice to outputs
                outputs = {
                    "auction_source": result.source.value if result.source else auction_type.code,
                    "reference_id": inv.reference_id,
                    "buyer_id": inv.buyer_id,
                    "buyer_name": inv.buyer_name,
                    "sale_date": inv.sale_date,
                    "total_amount": inv.total_amount,
                }

                # Pickup address
                if inv.pickup_address:
                    addr = inv.pickup_address
                    # pickup_address should be street address; fallback to location name if no street
                    # Central Dispatch requires pickup_address, so provide best available info
                    street_address = addr.street
                    if not street_address and addr.name:
                        # Use location name as fallback (e.g., "IAA Tampa South")
                        street_address = addr.name
                    outputs.update({
                        "pickup_name": addr.name,
                        "pickup_address": street_address,
                        "pickup_city": addr.city,
                        "pickup_state": addr.state,
                        "pickup_zip": addr.postal_code,
                        "pickup_phone": addr.phone,
                    })

                # Vehicles
                if inv.vehicles:
                    v = inv.vehicles[0]
                    outputs.update({
                        "vehicle_vin": v.vin,
                        "vehicle_year": v.year,
                        "vehicle_make": v.make,
                        "vehicle_model": v.model,
                        "vehicle_color": v.color,
                        "vehicle_lot": v.lot_number,
                        "vehicle_mileage": v.mileage,
                        "vehicle_is_inoperable": v.is_inoperable,
                    })

                    # Generate custom Order ID: MMDD + Make(3) + Model(1) + Seq
                    # Example: 21JEEG1 for Feb 1, Jeep Grand Cherokee, order #1
                    try:
                        order_date = inv.sale_date or datetime.now()
                        order_id = generate_order_id(v.make, v.model, order_date)
                        outputs["order_id"] = order_id
                    except Exception as e:
                        # Don't fail extraction if order_id generation fails
                        outputs["order_id"] = None

                extraction_score = result.score

                # Update document's auction_type_id if detected source differs
                if result.source:
                    detected_source = result.source.value  # e.g., "COPART", "IAA", "MANHEIM"
                    if detected_source != auction_type.code:
                        # Find the matching auction type by code
                        detected_type = AuctionTypeRepository.get_by_code(detected_source)
                        if detected_type:
                            # Update document to use detected auction type
                            DocumentRepository.update(document_id, auction_type_id=detected_type.id)
                            # Also update the extraction run's auction_type_id
                            auction_type_id = detected_type.id
                            # Update the run as well
                            ExtractionRunRepository.update(run_id, auction_type_id=detected_type.id)

        processing_time_ms = int((time.time() - start_time) * 1000)

        # Determine status based on extraction quality
        # All successful extractions go to needs_review (P0 requirement)
        # Only after human review can a run be marked as approved/exported
        if not outputs:
            run_status = "failed"
        else:
            # Check if any required fields are missing or low confidence
            # For now, all successful extractions need review
            run_status = "needs_review"

        # Update run with results
        ExtractionRunRepository.update(
            run_id,
            status=run_status,
            extraction_score=extraction_score,
            outputs_json=outputs,
            processing_time_ms=processing_time_ms,
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        # Create review items from outputs
        if outputs:
            review_items = []
            from api.models import get_connection
            with get_connection() as conn:
                # Get field mappings for this auction type
                mappings = conn.execute(
                    "SELECT * FROM field_mappings WHERE auction_type_id = ? AND is_active = TRUE",
                    (auction_type_id,)
                ).fetchall()

                mapping_dict = {m["source_key"]: dict(m) for m in mappings}

            for source_key, value in outputs.items():
                mapping = mapping_dict.get(source_key, {})
                review_items.append({
                    "source_key": source_key,
                    "internal_key": mapping.get("internal_key", source_key),
                    "cd_key": mapping.get("cd_key"),
                    "predicted_value": str(value) if value is not None else None,
                    "is_match_ok": False,
                    "export_field": mapping.get("is_required", False) or value is not None,
                    "confidence": extraction_score,
                })

            if review_items:
                ReviewItemRepository.create_batch(run_id, review_items)

    except Exception as e:
        import traceback
        error_details = {
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        ExtractionRunRepository.update(
            run_id,
            status="failed",
            errors_json=[error_details],
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        # Create empty review items for failed extractions so user can manually enter data
        _create_empty_review_items(run_id, auction_type_id)


def _create_empty_review_items(run_id: int, auction_type_id: int):
    """Create empty review items for manual data entry."""
    from api.database import get_connection

    # Get field mappings for this auction type
    with get_connection() as conn:
        mappings = conn.execute(
            "SELECT * FROM field_mappings WHERE auction_type_id = ? AND is_active = TRUE ORDER BY display_order",
            (auction_type_id,)
        ).fetchall()

    if not mappings:
        # Use default fields if no mappings exist
        default_fields = [
            ("vehicle_vin", "vin", "vehicles[0].vin", True),
            ("vehicle_year", "year", "vehicles[0].year", False),
            ("vehicle_make", "make", "vehicles[0].make", False),
            ("vehicle_model", "model", "vehicles[0].model", False),
            ("vehicle_color", "color", "vehicles[0].color", False),
            ("vehicle_lot", "lot_number", "vehicles[0].lotNumber", False),
            ("pickup_city", "pickup_city", "stops[0].city", True),
            ("pickup_state", "pickup_state", "stops[0].state", True),
            ("pickup_zip", "pickup_postal_code", "stops[0].postalCode", True),
            ("buyer_id", "buyer_id", None, False),
            ("buyer_name", "buyer_name", None, False),
        ]

        review_items = [
            {
                "source_key": source_key,
                "internal_key": internal_key,
                "cd_key": cd_key,
                "predicted_value": None,
                "is_match_ok": False,
                "export_field": is_required,
                "confidence": 0.0,
            }
            for source_key, internal_key, cd_key, is_required in default_fields
        ]
    else:
        review_items = [
            {
                "source_key": m["source_key"],
                "internal_key": m["internal_key"],
                "cd_key": m["cd_key"],
                "predicted_value": None,
                "is_match_ok": False,
                "export_field": m["is_required"],
                "confidence": 0.0,
            }
            for m in mappings
        ]

    if review_items:
        ReviewItemRepository.create_batch(run_id, review_items)


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/run", response_model=ExtractionRunResponse, status_code=201)
async def run_extraction_endpoint(
    data: ExtractionRunRequest,
    background_tasks: BackgroundTasks,
    sync: bool = Query(True, description="Run synchronously (wait for result)"),
):
    """
    Run extraction on a document.

    Creates an extraction run and executes the extraction.
    By default runs synchronously. Set sync=false for background execution.
    """
    # Validate document
    doc = DocumentRepository.get_by_id(data.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get auction type
    auction_type = AuctionTypeRepository.get_by_id(doc.auction_type_id)
    if not auction_type:
        raise HTTPException(status_code=400, detail="Invalid auction type")

    # Check for active ML model
    extractor_kind = "rule"
    model_version_id = None

    if data.force_ml:
        active_model = ModelVersionRepository.get_active(doc.auction_type_id)
        if active_model:
            extractor_kind = "ml"
            model_version_id = active_model.id

    # Create run
    run_id = ExtractionRunRepository.create(
        document_id=data.document_id,
        auction_type_id=doc.auction_type_id,
        extractor_kind=extractor_kind,
        model_version_id=model_version_id,
    )

    if sync:
        # Run synchronously
        run_extraction(run_id, data.document_id, doc.auction_type_id,
                      extractor_kind, model_version_id)
    else:
        # Run in background
        background_tasks.add_task(
            run_extraction, run_id, data.document_id, doc.auction_type_id,
            extractor_kind, model_version_id
        )

    # Get result
    run = ExtractionRunRepository.get_by_id(run_id)

    return ExtractionRunResponse(
        id=run.id,
        uuid=run.uuid,
        document_id=run.document_id,
        document_filename=doc.filename,
        auction_type_id=run.auction_type_id,
        auction_type_code=auction_type.code,
        extractor_kind=run.extractor_kind,
        model_version_id=run.model_version_id,
        status=run.status,
        extraction_score=run.extraction_score,
        outputs=run.outputs_json,
        errors=run.errors_json,
        processing_time_ms=run.processing_time_ms,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get("/", response_model=ExtractionRunListResponse)
async def list_extraction_runs(
    document_id: Optional[int] = Query(None),
    auction_type_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List extraction runs with optional filtering."""
    from api.database import get_connection

    sql = "SELECT * FROM extraction_runs WHERE 1=1"
    params = []

    if document_id:
        sql += " AND document_id = ?"
        params.append(document_id)
    if auction_type_id:
        sql += " AND auction_type_id = ?"
        params.append(auction_type_id)
    if status:
        sql += " AND status = ?"
        params.append(status)

    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM extraction_runs WHERE 1=1"
        ).fetchone()[0]

    items = []
    for row in rows:
        data = dict(row)
        if data.get("outputs_json"):
            import json
            data["outputs_json"] = json.loads(data["outputs_json"])
        if data.get("errors_json"):
            import json
            data["errors_json"] = json.loads(data["errors_json"])

        # Get related entities
        doc = DocumentRepository.get_by_id(data["document_id"])
        at = AuctionTypeRepository.get_by_id(data["auction_type_id"])

        items.append(ExtractionRunResponse(
            id=data["id"],
            uuid=data["uuid"],
            document_id=data["document_id"],
            document_filename=doc.filename if doc else None,
            auction_type_id=data["auction_type_id"],
            auction_type_code=at.code if at else None,
            extractor_kind=data["extractor_kind"],
            model_version_id=data.get("model_version_id"),
            status=data["status"],
            extraction_score=data.get("extraction_score"),
            outputs=data.get("outputs_json"),
            errors=data.get("errors_json"),
            processing_time_ms=data.get("processing_time_ms"),
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
        ))

    return ExtractionRunListResponse(items=items, total=total)


class ExtractionStatsResponse(BaseModel):
    """Response model for extraction run statistics."""
    total: int
    last_24h: int
    by_status: dict
    by_auction_type: dict
    needs_review_count: int


@router.get("/stats", response_model=ExtractionStatsResponse)
async def get_extraction_stats():
    """
    Get extraction run statistics.

    Returns aggregate counts by status and auction type.
    """
    from api.database import get_connection
    from datetime import datetime, timedelta

    with get_connection() as conn:
        # Total count
        total = conn.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0]

        # Last 24h
        yesterday = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        last_24h = conn.execute(
            "SELECT COUNT(*) FROM extraction_runs WHERE created_at >= ?",
            (yesterday,)
        ).fetchone()[0]

        # By status
        status_rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM extraction_runs GROUP BY status"
        ).fetchall()
        by_status = {row["status"]: row["cnt"] for row in status_rows}

        # By auction type
        auction_rows = conn.execute("""
            SELECT at.code, COUNT(*) as cnt
            FROM extraction_runs er
            JOIN auction_types at ON er.auction_type_id = at.id
            GROUP BY at.code
        """).fetchall()
        by_auction_type = {row["code"]: row["cnt"] for row in auction_rows}

        # Needs review count
        needs_review_count = by_status.get("needs_review", 0)

    return ExtractionStatsResponse(
        total=total,
        last_24h=last_24h,
        by_status=by_status,
        by_auction_type=by_auction_type,
        needs_review_count=needs_review_count,
    )


@router.get("/needs-review", response_model=ExtractionRunListResponse)
async def list_runs_needing_review(
    limit: int = Query(50, ge=1, le=500),
):
    """List extraction runs that need review."""
    runs = ExtractionRunRepository.list_needs_review(limit=limit)

    items = []
    for run in runs:
        doc = DocumentRepository.get_by_id(run.document_id)
        at = AuctionTypeRepository.get_by_id(run.auction_type_id)

        items.append(ExtractionRunResponse(
            id=run.id,
            uuid=run.uuid,
            document_id=run.document_id,
            document_filename=doc.filename if doc else None,
            auction_type_id=run.auction_type_id,
            auction_type_code=at.code if at else None,
            extractor_kind=run.extractor_kind,
            model_version_id=run.model_version_id,
            status=run.status,
            extraction_score=run.extraction_score,
            outputs=run.outputs_json,
            errors=run.errors_json,
            processing_time_ms=run.processing_time_ms,
            created_at=run.created_at,
            completed_at=run.completed_at,
        ))

    return ExtractionRunListResponse(items=items, total=len(items))


@router.get("/{id}", response_model=ExtractionDetailResponse)
async def get_extraction_run(id: int):
    """Get detailed extraction run with field-level outputs."""
    run = ExtractionRunRepository.get_by_id(id)
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    doc = DocumentRepository.get_by_id(run.document_id)
    at = AuctionTypeRepository.get_by_id(run.auction_type_id)

    # Get review items (extracted fields)
    review_items = ReviewItemRepository.get_by_run(run.id)
    fields = [
        ExtractionFieldOutput(
            source_key=item.source_key,
            internal_key=item.internal_key,
            cd_key=item.cd_key,
            value=item.predicted_value,
            confidence=item.confidence,
        )
        for item in review_items
    ]

    run_response = ExtractionRunResponse(
        id=run.id,
        uuid=run.uuid,
        document_id=run.document_id,
        document_filename=doc.filename if doc else None,
        auction_type_id=run.auction_type_id,
        auction_type_code=at.code if at else None,
        extractor_kind=run.extractor_kind,
        model_version_id=run.model_version_id,
        status=run.status,
        extraction_score=run.extraction_score,
        outputs=run.outputs_json,
        errors=run.errors_json,
        processing_time_ms=run.processing_time_ms,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )

    return ExtractionDetailResponse(
        run=run_response,
        fields=fields,
        raw_text_preview=doc.raw_text[:1000] if doc and doc.raw_text else None,
    )
