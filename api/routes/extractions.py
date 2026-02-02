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


class ExtractionMetricsResponse(BaseModel):
    """Extraction metrics for diagnostics."""
    raw_text_length: int = 0
    words_count: int = 0
    text_mode: str = "native"
    pages_count: int = 0
    detected_source: Optional[str] = None
    classification_score: float = 0.0
    classification_patterns: List[str] = []
    fields_extracted_count: int = 0
    fields_filled_count: int = 0
    required_fields_filled: int = 0
    required_fields_total: int = 0
    needs_ocr: bool = False
    has_pickup_address: bool = False
    has_vehicle_vin: bool = False
    has_vehicle_ymm: bool = False
    extractor_version: str = "1.0"
    extraction_timestamp: Optional[str] = None


class FieldSourceInfo(BaseModel):
    """Source info for a single field."""
    field_key: str
    value: Optional[str] = None
    source: str  # "EXTRACTED", "USER_OVERRIDE", "WAREHOUSE_CONST", "AUCTION_CONST", "DEFAULT"
    confidence: Optional[float] = None
    extractor_method: Optional[str] = None  # Which extraction method produced this value


class ExtractionDebugResponse(BaseModel):
    """Debug response for extraction diagnostics."""
    run_id: int
    document_id: int
    document_filename: Optional[str] = None
    auction_type: Optional[str] = None

    # Status and scoring
    status: str
    extraction_score: Optional[float] = None
    processing_time_ms: Optional[int] = None

    # Metrics
    metrics: Optional[ExtractionMetricsResponse] = None

    # Field sources - where each value came from
    field_sources: List[FieldSourceInfo] = []

    # Errors if any
    errors: Optional[list] = None

    # Raw text preview
    raw_text_preview: Optional[str] = None
    raw_text_length: int = 0

    # Classification details
    all_scores: List[dict] = []  # Scores from all extractors for comparison

    # Recommendations
    recommendations: List[str] = []


# =============================================================================
# EXTRACTION LOGIC
# =============================================================================

def run_extraction(run_id: int, document_id: int, auction_type_id: int,
                   extractor_kind: str = "rule", model_version_id: int = None):
    """
    Execute extraction on a document.

    This function is called synchronously or as a background task.
    Tracks extraction metrics and field sources for diagnostics.
    """
    start_time = time.time()

    # Initialize metrics tracking
    metrics = {
        "raw_text_length": 0,
        "words_count": 0,
        "text_mode": "native",
        "pages_count": 0,
        "detected_source": None,
        "classification_score": 0.0,
        "classification_patterns": [],
        "fields_extracted_count": 0,
        "fields_filled_count": 0,
        "required_fields_filled": 0,
        "required_fields_total": 4,  # vin, pickup_address, pickup_city, pickup_state
        "needs_ocr": False,
        "has_pickup_address": False,
        "has_vehicle_vin": False,
        "has_vehicle_ymm": False,
        "extractor_version": "1.0",
        "extraction_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Initialize field sources tracking
    field_sources = {}

    # Get document
    doc = DocumentRepository.get_by_id(document_id)
    if not doc:
        ExtractionRunRepository.update(
            run_id,
            status="failed",
            errors_json=[{"error": "Document not found"}],
            metrics_json=metrics,
        )
        return

    # Get auction type
    auction_type = AuctionTypeRepository.get_by_id(auction_type_id)
    if not auction_type:
        ExtractionRunRepository.update(
            run_id,
            status="failed",
            errors_json=[{"error": "Auction type not found"}],
            metrics_json=metrics,
        )
        return

    # Update status to processing
    ExtractionRunRepository.update(run_id, status="processing")

    try:
        # Get raw text from document
        raw_text = doc.raw_text or ""
        pages_count = 0

        if not raw_text and doc.file_path:
            # Try to extract text
            import pdfplumber
            with pdfplumber.open(doc.file_path) as pdf:
                pages_count = len(pdf.pages)
                text_parts = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                raw_text = "\n".join(text_parts)

        # Update metrics with text info
        metrics["raw_text_length"] = len(raw_text)
        metrics["words_count"] = len(raw_text.split()) if raw_text else 0
        metrics["pages_count"] = pages_count
        metrics["needs_ocr"] = len(raw_text) < 100

        if not raw_text:
            ExtractionRunRepository.update(
                run_id,
                status="failed",
                errors_json=[{"error": "Could not extract text from document"}],
                metrics_json=metrics,
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
            score, patterns = extractor.score(raw_text)
            metrics["classification_score"] = score
            metrics["classification_patterns"] = patterns[:10] if patterns else []
            metrics["detected_source"] = extractor.source.value

            result = extractor.extract_with_result(doc.file_path, raw_text)

            if result.invoice:
                inv = result.invoice
                # Map invoice to outputs with field source tracking
                outputs = {
                    "auction_source": result.source.value if result.source else auction_type.code,
                    "reference_id": inv.reference_id,
                    "buyer_id": inv.buyer_id,
                    "buyer_name": inv.buyer_name,
                    "sale_date": inv.sale_date,
                    "total_amount": inv.total_amount,
                }

                # Track field sources for base fields
                for key, value in outputs.items():
                    field_sources[key] = {
                        "value": value,
                        "source": "EXTRACTED" if value is not None else "DEFAULT",
                        "confidence": 0.7 if value is not None else 0.0,
                        "method": f"{extractor.source.value.lower()}_extractor",
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

                    pickup_fields = {
                        "pickup_name": addr.name,
                        "pickup_address": street_address,
                        "pickup_city": addr.city,
                        "pickup_state": addr.state,
                        "pickup_zip": addr.postal_code,
                        "pickup_phone": addr.phone,
                    }
                    outputs.update(pickup_fields)

                    # Track pickup field sources
                    for key, value in pickup_fields.items():
                        field_sources[key] = {
                            "value": value,
                            "source": "EXTRACTED" if value else "DEFAULT",
                            "confidence": 0.6 if value else 0.0,
                            "method": "address_extractor",
                        }

                    metrics["has_pickup_address"] = bool(street_address)

                # Vehicles
                if inv.vehicles:
                    v = inv.vehicles[0]
                    vehicle_fields = {
                        "vehicle_vin": v.vin,
                        "vehicle_year": v.year,
                        "vehicle_make": v.make,
                        "vehicle_model": v.model,
                        "vehicle_color": v.color,
                        "vehicle_lot": v.lot_number,
                        "vehicle_mileage": v.mileage,
                        "vehicle_is_inoperable": v.is_inoperable,
                    }
                    outputs.update(vehicle_fields)

                    # Track vehicle field sources
                    for key, value in vehicle_fields.items():
                        field_sources[key] = {
                            "value": value,
                            "source": "EXTRACTED" if value is not None else "DEFAULT",
                            "confidence": 0.8 if value is not None else 0.0,
                            "method": "vehicle_extractor",
                        }

                    metrics["has_vehicle_vin"] = bool(v.vin)
                    metrics["has_vehicle_ymm"] = bool(v.year and v.make and v.model)

                    # Generate custom Order ID: MMDD + Make(3) + Model(1) + Seq
                    # Example: 21JEEG1 for Feb 1, Jeep Grand Cherokee, order #1
                    try:
                        order_date = inv.sale_date or datetime.now()
                        order_id = generate_order_id(v.make, v.model, order_date)
                        outputs["order_id"] = order_id
                        field_sources["order_id"] = {
                            "value": order_id,
                            "source": "GENERATED",
                            "confidence": 1.0,
                            "method": "order_id_generator",
                        }
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

        # Calculate field metrics
        metrics["fields_extracted_count"] = len(outputs)
        metrics["fields_filled_count"] = sum(1 for v in outputs.values() if v is not None and v != "")

        # Count required fields filled
        required_fields = ["vehicle_vin", "pickup_address", "pickup_city", "pickup_state"]
        metrics["required_fields_filled"] = sum(1 for f in required_fields if outputs.get(f))

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

        # Update run with results including metrics and field sources
        ExtractionRunRepository.update(
            run_id,
            status=run_status,
            extraction_score=extraction_score,
            outputs_json=outputs,
            metrics_json=metrics,
            field_sources_json=field_sources,
            processing_time_ms=processing_time_ms,
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        # Create review items from outputs
        # CRITICAL: Always create review items for ALL configured field mappings,
        # not just the extracted fields. This ensures consistent field display.
        if True:  # Always create review items, even if outputs is empty
            _create_review_items_for_all_fields(run_id, auction_type_id, outputs or {})

    except Exception as e:
        import traceback
        error_details = {
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        # Update metrics with error info
        metrics["extraction_timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        ExtractionRunRepository.update(
            run_id,
            status="failed",
            errors_json=[error_details],
            metrics_json=metrics,
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        # Create empty review items for failed extractions so user can manually enter data
        _create_empty_review_items(run_id, auction_type_id)


def _create_review_items_for_all_fields(run_id: int, auction_type_id: int, outputs: dict):
    """
    Create review items for ALL configured field mappings.

    This ensures consistent field display - all fields appear in Review page,
    using extracted values where available and empty for fields not extracted.

    Args:
        run_id: Extraction run ID
        auction_type_id: Auction type ID for field mappings
        outputs: Dict of extracted field values (may be incomplete)
    """
    from api.database import get_connection

    # Get ALL field mappings for this auction type (ordered for consistent display)
    with get_connection() as conn:
        mappings = conn.execute(
            "SELECT * FROM field_mappings WHERE auction_type_id = ? AND is_active = TRUE ORDER BY display_order",
            (auction_type_id,)
        ).fetchall()

    # Default field set if no mappings configured
    DEFAULT_FIELDS = [
        # Key fields for Central Dispatch
        ("auction_source", "auction_source", None, False),
        ("order_id", "order_id", None, False),
        ("reference_id", "reference_id", "externalId", False),
        # Vehicle
        ("vehicle_vin", "vehicle_vin", "vehicles[0].vin", True),
        ("vehicle_year", "vehicle_year", "vehicles[0].year", True),
        ("vehicle_make", "vehicle_make", "vehicles[0].make", True),
        ("vehicle_model", "vehicle_model", "vehicles[0].model", True),
        ("vehicle_color", "vehicle_color", "vehicles[0].color", False),
        ("vehicle_lot", "vehicle_lot", "vehicles[0].lotNumber", False),
        ("vehicle_mileage", "vehicle_mileage", None, False),
        ("vehicle_is_inoperable", "vehicle_is_inoperable", "vehicles[0].isInoperable", False),
        # Pickup location
        ("pickup_name", "pickup_name", "stops[0].locationName", False),
        ("pickup_address", "pickup_address", "stops[0].address", True),
        ("pickup_city", "pickup_city", "stops[0].city", True),
        ("pickup_state", "pickup_state", "stops[0].state", True),
        ("pickup_zip", "pickup_zip", "stops[0].postalCode", True),
        ("pickup_phone", "pickup_phone", "stops[0].phone", False),
        # Delivery location (usually filled from warehouse)
        ("delivery_name", "delivery_name", "stops[1].locationName", False),
        ("delivery_address", "delivery_address", "stops[1].address", False),
        ("delivery_city", "delivery_city", "stops[1].city", False),
        ("delivery_state", "delivery_state", "stops[1].state", False),
        ("delivery_zip", "delivery_zip", "stops[1].postalCode", False),
        ("delivery_phone", "delivery_phone", "stops[1].phone", False),
        # Buyer/Sale info
        ("buyer_id", "buyer_id", None, False),
        ("buyer_name", "buyer_name", None, False),
        ("sale_date", "sale_date", None, False),
        ("total_amount", "total_amount", None, False),
    ]

    # Build list of all fields to create
    review_items = []
    used_keys = set()

    if mappings:
        # Use configured mappings
        for m in mappings:
            source_key = m["source_key"]
            used_keys.add(source_key)

            # Get value from outputs if available
            value = outputs.get(source_key)

            review_items.append({
                "source_key": source_key,
                "internal_key": m["internal_key"] or source_key,
                "cd_key": m["cd_key"],
                "predicted_value": str(value) if value is not None else None,
                "is_match_ok": False,
                "export_field": m["is_required"] or value is not None,
                "confidence": 0.5 if value is not None else 0.0,
            })
    else:
        # Use default fields
        for source_key, internal_key, cd_key, is_required in DEFAULT_FIELDS:
            used_keys.add(source_key)
            value = outputs.get(source_key)

            review_items.append({
                "source_key": source_key,
                "internal_key": internal_key,
                "cd_key": cd_key,
                "predicted_value": str(value) if value is not None else None,
                "is_match_ok": False,
                "export_field": is_required or value is not None,
                "confidence": 0.5 if value is not None else 0.0,
            })

    # Also include any extracted fields that weren't in mappings
    # (in case extraction found additional fields)
    for key, value in outputs.items():
        if key not in used_keys and value is not None:
            review_items.append({
                "source_key": key,
                "internal_key": key,
                "cd_key": None,
                "predicted_value": str(value) if value is not None else None,
                "is_match_ok": False,
                "export_field": True,
                "confidence": 0.5,
            })

    if review_items:
        ReviewItemRepository.create_batch(run_id, review_items)


def _create_empty_review_items(run_id: int, auction_type_id: int):
    """Create empty review items for manual data entry (failed extractions)."""
    _create_review_items_for_all_fields(run_id, auction_type_id, {})


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


class ExtractionUpdateRequest(BaseModel):
    """Request model for updating extraction run."""
    outputs_json: Optional[dict] = Field(None, description="Updated extracted fields")
    status: Optional[str] = Field(None, description="New status")
    warehouse_id: Optional[int] = Field(None, description="Selected warehouse ID")


@router.put("/{id}", response_model=ExtractionRunResponse)
async def update_extraction_run(id: int, data: ExtractionUpdateRequest):
    """
    Update extraction run with corrected field values or status change.

    Used by the Review & Listing page to save field edits before export.
    """
    import json

    run = ExtractionRunRepository.get_by_id(id)
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    # Can't update exported runs
    if run.status == 'exported' and data.status != 'exported':
        raise HTTPException(status_code=400, detail="Cannot modify exported extraction")

    # Build updates
    updates = {}

    if data.outputs_json is not None:
        # Merge with existing outputs
        existing_outputs = run.outputs_json or {}
        if isinstance(existing_outputs, str):
            existing_outputs = json.loads(existing_outputs)

        # Merge new outputs
        merged = {**existing_outputs, **data.outputs_json}

        # Add warehouse_id if provided
        if data.warehouse_id is not None:
            merged['warehouse_id'] = data.warehouse_id

        updates['outputs_json'] = json.dumps(merged)

    if data.status is not None:
        updates['status'] = data.status

    if updates:
        ExtractionRunRepository.update(id, **updates)

    # Reload and return
    run = ExtractionRunRepository.get_by_id(id)
    doc = DocumentRepository.get_by_id(run.document_id)
    at = AuctionTypeRepository.get_by_id(run.auction_type_id)

    return ExtractionRunResponse(
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


@router.get("/{id}/debug", response_model=ExtractionDebugResponse)
async def get_extraction_debug(id: int):
    """
    Get detailed debug information for an extraction run.

    Returns comprehensive diagnostics including:
    - Extraction metrics (text length, word count, pages)
    - Classification scores from all extractors
    - Field sources (where each value came from)
    - OCR status and recommendations
    - Raw text preview

    This endpoint is designed for troubleshooting extraction issues
    and understanding why fields may be empty or incorrect.
    """
    import os

    run = ExtractionRunRepository.get_by_id(id)
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found")

    doc = DocumentRepository.get_by_id(run.document_id)
    at = AuctionTypeRepository.get_by_id(run.auction_type_id)

    # Initialize response
    response = ExtractionDebugResponse(
        run_id=run.id,
        document_id=run.document_id,
        document_filename=doc.filename if doc else None,
        auction_type=at.code if at else None,
        status=run.status,
        extraction_score=run.extraction_score,
        processing_time_ms=run.processing_time_ms,
        errors=run.errors_json,
    )

    # Get raw text from document
    raw_text = doc.raw_text or "" if doc else ""
    response.raw_text_length = len(raw_text)
    response.raw_text_preview = raw_text[:2000] if raw_text else None

    # Load stored metrics if available
    if run.metrics_json:
        response.metrics = ExtractionMetricsResponse(**run.metrics_json)
    else:
        # Calculate metrics on the fly if not stored
        words = raw_text.split() if raw_text else []
        response.metrics = ExtractionMetricsResponse(
            raw_text_length=len(raw_text),
            words_count=len(words),
            text_mode="native",  # Assume native if not stored
            needs_ocr=len(raw_text) < 100,
        )

    # Get field sources from stored data or compute from outputs
    field_sources = []
    if run.field_sources_json:
        for key, info in run.field_sources_json.items():
            field_sources.append(FieldSourceInfo(
                field_key=key,
                value=str(info.get("value")) if info.get("value") is not None else None,
                source=info.get("source", "EXTRACTED"),
                confidence=info.get("confidence"),
                extractor_method=info.get("method"),
            ))
    elif run.outputs_json:
        # Generate field sources from outputs
        for key, value in run.outputs_json.items():
            field_sources.append(FieldSourceInfo(
                field_key=key,
                value=str(value) if value is not None else None,
                source="EXTRACTED" if value is not None else "DEFAULT",
                confidence=0.5 if value is not None else 0.0,
            ))
    response.field_sources = field_sources

    # Get classification scores from all extractors
    all_scores = []
    if doc and doc.file_path and os.path.exists(doc.file_path):
        try:
            from extractors import ExtractorManager
            manager = ExtractorManager()

            for extractor in manager.extractors:
                score, patterns = extractor.score(raw_text)
                all_scores.append({
                    "source": extractor.source.value,
                    "score": score,
                    "matched_patterns": patterns[:5] if patterns else [],
                    "is_selected": (at and extractor.source.value == at.code),
                })
        except Exception as e:
            all_scores.append({"error": str(e)})
    response.all_scores = all_scores

    # Generate recommendations
    recommendations = []

    # Check text length
    if len(raw_text) < 100:
        recommendations.append("Document has very little text. OCR may be required.")

    # Check for missing required fields
    outputs = run.outputs_json or {}
    required_fields = ["vehicle_vin", "pickup_address", "pickup_city", "pickup_state"]
    missing_required = [f for f in required_fields if not outputs.get(f)]
    if missing_required:
        recommendations.append(f"Missing required fields: {', '.join(missing_required)}")

    # Check extraction score
    if run.extraction_score and run.extraction_score < 0.3:
        recommendations.append("Low extraction score. Document format may not match expected template.")

    # Check if extractor was selected
    if not at:
        recommendations.append("No auction type assigned. Classification may have failed.")

    # Check for errors
    if run.errors_json:
        recommendations.append(f"Extraction errors occurred: {len(run.errors_json)} error(s)")

    # Check vehicle info
    if not outputs.get("vehicle_vin"):
        recommendations.append("VIN not extracted. Check if VIN is present in document.")
    if not outputs.get("vehicle_year") or not outputs.get("vehicle_make"):
        recommendations.append("Vehicle year/make/model incomplete.")

    # Check pickup address
    if not outputs.get("pickup_address"):
        recommendations.append("Pickup address not extracted. May require manual entry.")

    response.recommendations = recommendations

    return response
