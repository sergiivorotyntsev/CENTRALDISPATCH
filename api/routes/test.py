"""Test/Sandbox endpoints for PDF upload, preview, and dry-run."""
import os
import tempfile
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

router = APIRouter()


# ----- Pydantic Models -----

class VehiclePreview(BaseModel):
    """Preview of extracted vehicle data."""
    vin: str
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    lot_number: Optional[str] = None
    mileage: Optional[int] = None
    is_operable: Optional[bool] = None
    color: Optional[str] = None


class PickupLocation(BaseModel):
    """Pickup location details."""
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone: Optional[str] = None


class ExtractionPreview(BaseModel):
    """Full extraction preview response."""
    status: str  # 'ok', 'needs_review', 'fail', 'error'
    auction: str
    confidence_score: float
    matched_patterns: List[str]
    text_length: int
    needs_ocr: bool

    # Extracted data
    vehicles: List[VehiclePreview]
    pickup_location: Optional[PickupLocation] = None
    gate_pass: Optional[str] = None
    buyer_id: Optional[str] = None
    reference_id: Optional[str] = None
    total_amount: Optional[float] = None

    # Warnings
    warnings: List[str] = []

    # File info
    attachment_hash: str
    attachment_name: str


class CDPayloadPreview(BaseModel):
    """Preview of Central Dispatch listing payload."""
    endpoint: str
    method: str
    payload: Dict[str, Any]
    validation_errors: List[str] = []
    warnings: List[str] = []


class SheetsRowPreview(BaseModel):
    """Preview of Google Sheets row."""
    columns: List[str]
    values: List[Any]
    row_dict: Dict[str, Any]


class DryRunResult(BaseModel):
    """Result of a dry run."""
    extraction: ExtractionPreview
    cd_payload: Optional[CDPayloadPreview] = None
    sheets_row: Optional[SheetsRowPreview] = None
    warehouse_routing: Optional[Dict[str, Any]] = None
    would_create: List[str]  # List of what would be created
    errors: List[str] = []


# ----- Helper Functions -----

def compute_file_hash(content: bytes) -> str:
    """Compute SHA256 hash of file content."""
    return hashlib.sha256(content).hexdigest()


def get_status_from_score(score: float) -> str:
    """Determine status based on extraction score."""
    if score >= 0.7:
        return "ok"
    elif score >= 0.3:
        return "needs_review"
    else:
        return "fail"


# ----- Endpoints -----

@router.post("/upload", response_model=ExtractionPreview)
async def upload_and_extract(
    file: UploadFile = File(...),
):
    """
    Upload a PDF and extract data.

    Returns extraction preview with confidence scores and warnings.
    Does not save to any export target - use dry-run for that.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Read file content
    content = await file.read()
    file_hash = compute_file_hash(content)

    # Save to temp file for extraction
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from extractors import ExtractorManager

        manager = ExtractorManager()

        # Classify first
        classification = manager.classify(tmp_path)

        # Extract
        result = manager.extract_with_result(tmp_path)

        # Build response
        vehicles = []
        pickup_location = None
        gate_pass = None
        buyer_id = None
        reference_id = None
        total_amount = None
        warnings = []

        if result.invoice:
            inv = result.invoice

            for v in inv.vehicles:
                vehicles.append(VehiclePreview(
                    vin=v.vin,
                    year=v.year,
                    make=v.make,
                    model=v.model,
                    lot_number=v.lot_number,
                    mileage=v.mileage,
                    is_operable=v.is_operable,
                    color=v.color,
                ))

            if inv.pickup_location:
                loc = inv.pickup_location
                pickup_location = PickupLocation(
                    name=loc.name,
                    address=loc.address,
                    city=loc.city,
                    state=loc.state,
                    zip_code=loc.zip_code,
                    phone=loc.phone,
                )

            gate_pass = inv.gate_pass
            buyer_id = inv.buyer_id
            reference_id = inv.reference_id
            total_amount = inv.total_amount

            # Check for warnings
            if inv.has_missing_critical_fields():
                warnings.append("Missing critical fields - needs review")

            for v in inv.vehicles:
                if not v.vin or len(v.vin) != 17:
                    warnings.append(f"Invalid VIN: {v.vin or 'missing'}")
        else:
            warnings.append("Extraction failed - no data extracted")

        return ExtractionPreview(
            status=get_status_from_score(result.score),
            auction=classification.source.value,
            confidence_score=round(result.score * 100, 1),
            matched_patterns=classification.matched_patterns,
            text_length=result.text_length,
            needs_ocr=result.needs_ocr,
            vehicles=vehicles,
            pickup_location=pickup_location,
            gate_pass=gate_pass,
            buyer_id=buyer_id,
            reference_id=reference_id,
            total_amount=total_amount,
            warnings=warnings,
            attachment_hash=file_hash,
            attachment_name=file.filename,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

    finally:
        # Clean up temp file
        os.unlink(tmp_path)


@router.post("/preview-cd", response_model=CDPayloadPreview)
async def preview_cd_payload(
    file: UploadFile = File(...),
):
    """
    Preview the Central Dispatch listing payload.

    Shows exactly what would be sent to CD API without actually creating the listing.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    content = await file.read()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from extractors import ExtractorManager

        manager = ExtractorManager()
        result = manager.extract_with_result(tmp_path)

        if not result.invoice or not result.invoice.vehicles:
            raise HTTPException(status_code=400, detail="No vehicles extracted from PDF")

        inv = result.invoice
        vehicle = inv.vehicles[0]

        # Build CD payload
        validation_errors = []
        warnings = []

        # Check required fields
        if not vehicle.vin or len(vehicle.vin) != 17:
            validation_errors.append("Invalid or missing VIN")

        if not inv.pickup_location or not inv.pickup_location.city:
            validation_errors.append("Missing pickup location")

        # Build payload structure (based on CD Listings API V2)
        payload = {
            "vehicle": {
                "vin": vehicle.vin or "",
                "year": vehicle.year,
                "make": vehicle.make or "",
                "model": vehicle.model or "",
                "is_operable": vehicle.is_operable if vehicle.is_operable is not None else True,
            },
            "origin": {
                "city": inv.pickup_location.city if inv.pickup_location else "",
                "state": inv.pickup_location.state if inv.pickup_location else "",
                "zip": inv.pickup_location.zip_code if inv.pickup_location else "",
            },
            "destination": {
                "city": "",  # Needs warehouse routing
                "state": "",
                "zip": "",
            },
            "notes": f"Gate Pass: {inv.gate_pass}" if inv.gate_pass else "",
            "price": {
                "amount": 0,
                "type": "open",
            },
        }

        if not payload["destination"]["city"]:
            warnings.append("Destination not set - needs warehouse routing")

        return CDPayloadPreview(
            endpoint="/api/v2/listings",
            method="POST",
            payload=payload,
            validation_errors=validation_errors,
            warnings=warnings,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build CD payload: {str(e)}")
    finally:
        os.unlink(tmp_path)


@router.post("/preview-sheets-row", response_model=SheetsRowPreview)
async def preview_sheets_row(
    file: UploadFile = File(...),
):
    """
    Preview the Google Sheets row that would be written.

    Shows the exact data that would appear in the spreadsheet.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    content = await file.read()
    file_hash = compute_file_hash(content)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from extractors import ExtractorManager
        from services.sheets_exporter import load_schema

        manager = ExtractorManager()
        classification = manager.classify(tmp_path)
        result = manager.extract_with_result(tmp_path)

        # Load schema for column names
        schema = load_schema()
        column_names = [col["name"] for col in schema["columns"]]

        # Build row dict
        row_dict = {
            "run_id": "preview",
            "row_id": "preview",
            "processed_at": "preview",
            "source_type": "upload",
            "attachment_name": file.filename,
            "attachment_hash": file_hash[:16] + "...",
            "auction": classification.source.value,
            "extraction_score": round(result.score * 100, 1),
            "status": get_status_from_score(result.score),
            "matched_patterns": ", ".join(classification.matched_patterns),
        }

        if result.invoice:
            inv = result.invoice
            if inv.vehicles:
                v = inv.vehicles[0]
                row_dict.update({
                    "vin": v.vin,
                    "vehicle_year": v.year,
                    "vehicle_make": v.make,
                    "vehicle_model": v.model,
                    "lot_number": v.lot_number,
                    "mileage": v.mileage,
                    "is_operable": v.is_operable,
                    "vehicle_color": v.color,
                })

            if inv.pickup_location:
                loc = inv.pickup_location
                row_dict.update({
                    "pickup_name": loc.name,
                    "pickup_address": loc.address,
                    "pickup_city": loc.city,
                    "pickup_state": loc.state,
                    "pickup_zip": loc.zip_code,
                    "pickup_phone": loc.phone,
                })

            row_dict.update({
                "gate_pass": inv.gate_pass,
                "buyer_id": inv.buyer_id,
                "reference_id": inv.reference_id,
                "total_amount": inv.total_amount,
            })

        # Build values list in column order
        values = []
        for col in column_names:
            values.append(row_dict.get(col, ""))

        return SheetsRowPreview(
            columns=column_names,
            values=values,
            row_dict=row_dict,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build Sheets row: {str(e)}")
    finally:
        os.unlink(tmp_path)


@router.post("/dry-run", response_model=DryRunResult)
async def dry_run(
    file: UploadFile = File(...),
    include_cd: bool = Form(default=True),
    include_sheets: bool = Form(default=True),
    include_warehouse: bool = Form(default=True),
):
    """
    Perform a complete dry run of the pipeline.

    Shows what would happen if this PDF was processed, including:
    - Extraction results
    - CD payload (if enabled)
    - Sheets row (if enabled)
    - Warehouse routing (if enabled)

    Does NOT actually create anything - purely for preview.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    content = await file.read()
    file_hash = compute_file_hash(content)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from extractors import ExtractorManager
        from services.sheets_exporter import load_schema

        manager = ExtractorManager()
        classification = manager.classify(tmp_path)
        result = manager.extract_with_result(tmp_path)

        errors = []
        would_create = []

        # Build extraction preview
        vehicles = []
        pickup_location = None
        warnings = []

        if result.invoice:
            inv = result.invoice
            for v in inv.vehicles:
                vehicles.append(VehiclePreview(
                    vin=v.vin,
                    year=v.year,
                    make=v.make,
                    model=v.model,
                    lot_number=v.lot_number,
                    mileage=v.mileage,
                    is_operable=v.is_operable,
                    color=v.color,
                ))

            if inv.pickup_location:
                loc = inv.pickup_location
                pickup_location = PickupLocation(
                    name=loc.name,
                    address=loc.address,
                    city=loc.city,
                    state=loc.state,
                    zip_code=loc.zip_code,
                    phone=loc.phone,
                )

        extraction = ExtractionPreview(
            status=get_status_from_score(result.score),
            auction=classification.source.value,
            confidence_score=round(result.score * 100, 1),
            matched_patterns=classification.matched_patterns,
            text_length=result.text_length,
            needs_ocr=result.needs_ocr,
            vehicles=vehicles,
            pickup_location=pickup_location,
            gate_pass=result.invoice.gate_pass if result.invoice else None,
            buyer_id=result.invoice.buyer_id if result.invoice else None,
            reference_id=result.invoice.reference_id if result.invoice else None,
            total_amount=result.invoice.total_amount if result.invoice else None,
            warnings=warnings,
            attachment_hash=file_hash,
            attachment_name=file.filename,
        )

        # CD Payload preview
        cd_payload = None
        if include_cd and result.invoice and result.invoice.vehicles:
            vehicle = result.invoice.vehicles[0]
            inv = result.invoice

            payload = {
                "vehicle": {
                    "vin": vehicle.vin or "",
                    "year": vehicle.year,
                    "make": vehicle.make or "",
                    "model": vehicle.model or "",
                },
                "origin": {
                    "city": inv.pickup_location.city if inv.pickup_location else "",
                    "state": inv.pickup_location.state if inv.pickup_location else "",
                },
            }

            cd_payload = CDPayloadPreview(
                endpoint="/api/v2/listings",
                method="POST",
                payload=payload,
                validation_errors=[],
                warnings=[],
            )
            would_create.append("Central Dispatch listing")

        # Sheets row preview
        sheets_row = None
        if include_sheets:
            schema = load_schema()
            column_names = [col["name"] for col in schema["columns"]]

            row_dict = {
                "auction": classification.source.value,
                "extraction_score": round(result.score * 100, 1),
                "status": get_status_from_score(result.score),
                "attachment_name": file.filename,
                "attachment_hash": file_hash[:16] + "...",
            }

            if result.invoice:
                inv = result.invoice
                if inv.vehicles:
                    v = inv.vehicles[0]
                    row_dict.update({
                        "vin": v.vin,
                        "vehicle_year": v.year,
                        "vehicle_make": v.make,
                        "vehicle_model": v.model,
                    })

            values = [row_dict.get(col, "") for col in column_names]

            sheets_row = SheetsRowPreview(
                columns=column_names,
                values=values,
                row_dict=row_dict,
            )
            would_create.append("Google Sheets row")

        # Warehouse routing
        warehouse_routing = None
        if include_warehouse and result.invoice and result.invoice.pickup_location:
            # For now, just show what we'd route
            loc = result.invoice.pickup_location
            warehouse_routing = {
                "pickup_location": {
                    "city": loc.city,
                    "state": loc.state,
                    "zip": loc.zip_code,
                },
                "message": "Warehouse routing would be determined based on pickup location",
            }

        return DryRunResult(
            extraction=extraction,
            cd_payload=cd_payload,
            sheets_row=sheets_row,
            warehouse_routing=warehouse_routing,
            would_create=would_create,
            errors=errors,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dry run failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


@router.post("/classify")
async def classify_pdf(file: UploadFile = File(...)):
    """
    Classify a PDF to determine the auction source.

    Returns classification scores from all extractors.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    content = await file.read()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from extractors import ExtractorManager

        manager = ExtractorManager()
        all_scores = manager.get_all_scores(tmp_path)

        return {
            "filename": file.filename,
            "scores": [
                {
                    "source": source.value,
                    "score": round(score * 100, 1),
                    "patterns": patterns,
                }
                for source, score, patterns in all_scores
            ],
            "best_match": all_scores[0][0].value if all_scores else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")
    finally:
        os.unlink(tmp_path)
