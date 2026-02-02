"""
Documents API Routes

Upload and manage documents for extraction and training.
"""

import os
import hashlib
import tempfile
from typing import Optional, List
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.models import (
    DocumentRepository,
    AuctionTypeRepository,
    Document,
    DatasetSplit,
)

router = APIRouter(prefix="/api/documents", tags=["Documents"])

# Upload directory
UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class DocumentResponse(BaseModel):
    """Response model for document."""
    id: int
    uuid: str
    auction_type_id: int
    auction_type_code: Optional[str] = None
    dataset_split: str
    filename: str
    file_size: Optional[int] = None
    sha256: Optional[str] = None
    mime_type: str = "application/pdf"
    page_count: Optional[int] = None
    has_ocr: bool = False
    source: str = "upload"  # upload, email, batch, test_lab
    created_at: Optional[str] = None
    uploaded_by: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Response model for document list."""
    items: List[DocumentResponse]
    total: int
    train_count: int = 0
    test_count: int = 0


class DocumentUploadResponse(BaseModel):
    """Response model for document upload."""
    document: DocumentResponse
    is_duplicate: bool = False
    raw_text_preview: Optional[str] = None

    # Extraction run info (auto-created on upload)
    run_id: Optional[int] = None
    run_status: Optional[str] = None
    needs_ocr: bool = False
    text_length: int = 0

    # Classification info
    detected_source: Optional[str] = None
    classification_score: Optional[float] = None


class DocumentStatsResponse(BaseModel):
    """Response model for document statistics."""
    auction_type_id: int
    auction_type_name: str
    train_count: int
    test_count: int
    total: int


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(..., description="PDF document to upload"),
    auction_type_id: Optional[int] = Form(None, description="Auction type ID (optional, auto-detect if not provided)"),
    dataset_split: str = Form("train", description="Dataset split: train or test"),
    uploaded_by: Optional[str] = Form(None, description="Uploader identifier"),
    auto_extract: bool = Form(True, description="Automatically run extraction after upload"),
    source: str = Form("upload", description="Source: upload, email, batch, test_lab"),
    is_test: bool = Form(False, description="Mark as test document (blocks export)"),
    auto_classify: bool = Form(True, description="Auto-detect auction type from document"),
):
    """
    Upload a document for extraction and training.

    The document is associated with an auction type and marked as train or test.
    Duplicate detection is performed using SHA256 hash.

    Parameters:
    - auction_type_id: Optional. If not provided, document will be auto-classified.
    - auto_classify: If true (default), auto-detect auction type from document content.
    - source: upload (manual), email (ingestion), batch (bulk), test_lab (sandbox)
    - is_test: If true, document cannot be exported to Central Dispatch

    IMPORTANT: This endpoint automatically creates an ExtractionRun after upload.
    - If text_length >= 100: runs extraction, status = needs_review
    - If text_length < 100: marks as manual_required (needs OCR)
    """
    from api.models import ExtractionRunRepository

    # We'll validate auction_type after classification if needed
    auction_type = None
    if auction_type_id:
        auction_type = AuctionTypeRepository.get_by_id(auction_type_id)
        if not auction_type:
            raise HTTPException(status_code=400, detail="Invalid auction_type_id")

    # Validate dataset split
    if dataset_split not in ("train", "test"):
        raise HTTPException(status_code=400, detail="dataset_split must be 'train' or 'test'")

    # Validate source
    valid_sources = ("upload", "email", "batch", "test_lab")
    if source not in valid_sources:
        raise HTTPException(status_code=400, detail=f"source must be one of: {', '.join(valid_sources)}")

    # Auto-set is_test for test_lab source
    if source == "test_lab":
        is_test = True

    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Calculate SHA256
    sha256 = hashlib.sha256(content).hexdigest()

    # Check for duplicate
    existing = DocumentRepository.get_by_sha256(sha256)
    if existing:
        # For duplicates, get the existing auction type and run info
        existing_auction_type = AuctionTypeRepository.get_by_id(existing.auction_type_id)
        from api.database import get_connection
        with get_connection() as conn:
            run_row = conn.execute(
                "SELECT id, status FROM extraction_runs WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
                (existing.id,)
            ).fetchone()

        # If auto_extract is enabled and no successful run exists, create a new extraction run
        new_run_id = None
        new_run_status = None
        if auto_extract:
            # Check if we should re-extract (no run, or last run failed)
            should_reextract = not run_row or run_row["status"] in ("failed", "manual_required")
            if should_reextract:
                from api.models import ExtractionRunRepository
                new_run_id = ExtractionRunRepository.create(
                    document_id=existing.id,
                    auction_type_id=existing.auction_type_id,
                    extractor_kind="rule",
                )
                # Run extraction
                try:
                    from api.routes.extractions import run_extraction
                    run_extraction(new_run_id, existing.id, existing.auction_type_id, "rule", None)
                    run = ExtractionRunRepository.get_by_id(new_run_id)
                    new_run_status = run.status if run else "failed"
                except Exception as e:
                    ExtractionRunRepository.update(
                        new_run_id,
                        status="failed",
                        error_message=str(e),
                    )
                    new_run_status = "failed"

        return DocumentUploadResponse(
            document=DocumentResponse(
                **existing.__dict__,
                auction_type_code=existing_auction_type.code if existing_auction_type else None,
            ),
            is_duplicate=True,
            run_id=new_run_id or (run_row["id"] if run_row else None),
            run_status=new_run_status or (run_row["status"] if run_row else None),
        )

    # Validate PDF structure BEFORE saving (P0 requirement)
    import io
    page_count = 0
    raw_text = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid PDF: Document has no pages"
                )
            # Extract text to validate PDF is readable
            text_parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            raw_text = "\n".join(text_parts)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid PDF: {str(e)}. Please upload a valid PDF document."
        )

    # Save file only after validation passed
    file_path = UPLOAD_DIR / f"{sha256[:16]}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(content)

    # Determine if OCR is needed (text too short)
    text_length = len(raw_text) if raw_text else 0
    needs_ocr = text_length < 100

    # Auto-classify document if auction_type not provided
    detected_source = None
    classification_score = None
    if auto_classify and not auction_type_id and raw_text and text_length >= 100:
        try:
            from extractors import ExtractorManager
            manager = ExtractorManager()
            classification = manager.classify(str(file_path))
            if classification:
                detected_source = classification.source.value
                classification_score = round(classification.score * 100, 1)
                # Map detected source to auction type
                detected_type = AuctionTypeRepository.get_by_code(detected_source.upper())
                if detected_type:
                    auction_type_id = detected_type.id
                    auction_type = detected_type
        except Exception as e:
            # Classification failed, continue without it
            pass

    # If still no auction type, use "OTHER" as fallback
    if not auction_type_id:
        other_type = AuctionTypeRepository.get_by_code("OTHER")
        if other_type:
            auction_type_id = other_type.id
            auction_type = other_type
        else:
            # Create "OTHER" if doesn't exist
            auction_type_id = 4  # Default to ID 4
            auction_type = AuctionTypeRepository.get_by_id(4)

    # Create document record with all fields
    doc_id = DocumentRepository.create(
        auction_type_id=auction_type_id,
        dataset_split=dataset_split,
        filename=file.filename,
        file_path=str(file_path),
        file_size=file_size,
        sha256=sha256,
        raw_text=raw_text,
        uploaded_by=uploaded_by,
        source=source,
        is_test=is_test,
        page_count=page_count,
    )

    doc = DocumentRepository.get_by_id(doc_id)

    # Auto-create extraction run
    run_id = None
    run_status = None
    # Keep detected_source and classification_score from earlier auto-classification

    if auto_extract:
        # Create extraction run
        run_id = ExtractionRunRepository.create(
            document_id=doc_id,
            auction_type_id=auction_type_id,
            extractor_kind="rule",
        )

        if needs_ocr:
            # Mark as manual_required - can't extract without OCR
            ExtractionRunRepository.update(
                run_id,
                status="manual_required",
                error_message="Document has insufficient text for extraction. OCR processing required.",
            )
            run_status = "manual_required"
        else:
            # Run classification if not already done
            try:
                if not detected_source:
                    from extractors import ExtractorManager
                    manager = ExtractorManager()
                    classification = manager.classify(str(file_path))
                    if classification:
                        detected_source = classification.source.value
                        classification_score = round(classification.score * 100, 1)

                # Run extraction
                from api.routes.extractions import run_extraction
                run_extraction(run_id, doc_id, auction_type_id, "rule", None)

                # Get updated status
                run = ExtractionRunRepository.get_by_id(run_id)
                run_status = run.status if run else "failed"
            except Exception as e:
                # Mark as failed if extraction crashes
                ExtractionRunRepository.update(
                    run_id,
                    status="failed",
                    error_message=str(e),
                )
                run_status = "failed"

    return DocumentUploadResponse(
        document=DocumentResponse(
            **doc.__dict__,
            auction_type_code=auction_type.code if auction_type else None,
        ),
        is_duplicate=False,
        raw_text_preview=raw_text[:500] if raw_text else None,
        run_id=run_id,
        run_status=run_status,
        needs_ocr=needs_ocr,
        text_length=text_length,
        detected_source=detected_source,
        classification_score=classification_score,
    )


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    auction_type_id: Optional[int] = Query(None, description="Filter by auction type"),
    dataset_split: Optional[str] = Query(None, description="Filter by split: train or test"),
    exclude_test_lab: bool = Query(True, description="Exclude Test Lab documents from list"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List documents with optional filtering."""
    if auction_type_id:
        docs = DocumentRepository.list_by_auction_type(
            auction_type_id=auction_type_id,
            dataset_split=dataset_split,
            limit=limit,
            offset=offset,
        )
        counts = DocumentRepository.count_by_auction_type(auction_type_id)
    else:
        # List all documents (need to implement in repository)
        from api.database import get_connection
        sql = "SELECT * FROM documents WHERE 1=1"
        params = []

        if dataset_split:
            sql += " AND dataset_split = ?"
            params.append(dataset_split)

        # Exclude Test Lab documents by default for production Documents page
        if exclude_test_lab:
            sql += " AND (is_test IS NULL OR is_test = 0)"
            sql += " AND (source IS NULL OR source != 'test_lab')"

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            docs = [Document(**dict(row)) for row in rows]

            # Get counts (also excluding test lab docs)
            count_filter = ""
            if exclude_test_lab:
                count_filter = " AND (is_test IS NULL OR is_test = 0) AND (source IS NULL OR source != 'test_lab')"

            train_count = conn.execute(
                f"SELECT COUNT(*) FROM documents WHERE dataset_split = 'train'{count_filter}"
            ).fetchone()[0]
            test_count = conn.execute(
                f"SELECT COUNT(*) FROM documents WHERE dataset_split = 'test'{count_filter}"
            ).fetchone()[0]
            counts = {"train": train_count, "test": test_count}

    # Enrich with auction type codes
    items = []
    for doc in docs:
        at = AuctionTypeRepository.get_by_id(doc.auction_type_id)
        items.append(DocumentResponse(
            **doc.__dict__,
            auction_type_code=at.code if at else None,
        ))

    return DocumentListResponse(
        items=items,
        total=len(items),
        train_count=counts.get("train", 0),
        test_count=counts.get("test", 0),
    )


@router.get("/{id}", response_model=DocumentResponse)
async def get_document(id: int):
    """Get a single document by ID."""
    doc = DocumentRepository.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    at = AuctionTypeRepository.get_by_id(doc.auction_type_id)
    return DocumentResponse(
        **doc.__dict__,
        auction_type_code=at.code if at else None,
    )


@router.get("/{id}/text")
async def get_document_text(id: int):
    """Get the raw extracted text from a document."""
    doc = DocumentRepository.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "raw_text": doc.raw_text,
        "page_count": doc.page_count,
    }


@router.get("/{id}/file")
async def get_document_file(id: int):
    """
    Get the PDF file for viewing/downloading.

    Returns the original PDF document for display in a PDF viewer.
    """
    doc = DocumentRepository.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.file_path:
        raise HTTPException(status_code=404, detail="Document file path not found")

    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    return FileResponse(
        doc.file_path,
        media_type="application/pdf",
        filename=doc.filename,
        headers={"Content-Disposition": f"inline; filename=\"{doc.filename}\""}
    )


@router.get("/stats/by-auction-type", response_model=List[DocumentStatsResponse])
async def get_document_stats():
    """Get document counts by auction type."""
    auction_types = AuctionTypeRepository.list_all()
    stats = []

    for at in auction_types:
        counts = DocumentRepository.count_by_auction_type(at.id)
        train_count = counts.get("train", 0)
        test_count = counts.get("test", 0)
        stats.append(DocumentStatsResponse(
            auction_type_id=at.id,
            auction_type_name=at.name,
            train_count=train_count,
            test_count=test_count,
            total=train_count + test_count,
        ))

    return stats


@router.get("/{id}/export-preview")
async def get_document_export_preview(id: int):
    """
    Get document export preview with all fields ready for Central Dispatch.

    Returns:
    - Document metadata
    - Latest extraction with all fields
    - Export validation status
    - Field mapping information
    """
    from api.database import get_connection

    doc = DocumentRepository.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    at = AuctionTypeRepository.get_by_id(doc.auction_type_id)

    # Check if document can be exported
    can_export = True
    blocking_issues = []

    if doc.is_test:
        can_export = False
        blocking_issues.append("Document is marked as test - cannot export to production")

    # Get latest extraction run
    with get_connection() as conn:
        run_row = conn.execute("""
            SELECT * FROM extraction_runs
            WHERE document_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (id,)).fetchone()

        extraction = None
        extracted_fields = {}
        if run_row:
            extraction = dict(run_row)

            # Get extraction outputs (fields)
            fields_rows = conn.execute("""
                SELECT * FROM extraction_outputs
                WHERE run_id = ?
            """, (extraction['id'],)).fetchall()

            for field_row in fields_rows:
                f = dict(field_row)
                extracted_fields[f['field_key']] = {
                    'value': f['extracted_value'],
                    'confidence': f.get('confidence', 0),
                    'source': f.get('source', 'extracted'),
                    'is_corrected': f.get('is_corrected', False),
                }

            # Check extraction status
            if extraction['status'] not in ['approved', 'reviewed']:
                can_export = False
                blocking_issues.append(f"Extraction status is '{extraction['status']}' - needs review")

        else:
            can_export = False
            blocking_issues.append("No extraction run found - please run extraction first")

        # Get field mappings for this auction type
        field_mappings = []
        mapping_rows = conn.execute("""
            SELECT * FROM field_mappings
            WHERE auction_type_id = ?
            ORDER BY display_order, cd_field_name
        """, (doc.auction_type_id,)).fetchall()

        for m_row in mapping_rows:
            m = dict(m_row)
            field_key = m['cd_field_name']
            field_data = extracted_fields.get(field_key, {})

            # Check if required field is missing
            if m.get('is_required') and not field_data.get('value'):
                can_export = False
                blocking_issues.append(f"Required field '{field_key}' is empty")

            field_mappings.append({
                'cd_field': field_key,
                'display_name': m.get('display_name', field_key),
                'source': m.get('source_type', 'extracted'),
                'is_required': m.get('is_required', False),
                'is_active': m.get('is_active', True),
                'value': field_data.get('value'),
                'confidence': field_data.get('confidence'),
                'default_value': m.get('default_value'),
            })

    return {
        'document': {
            'id': doc.id,
            'filename': doc.filename,
            'auction_type': at.code if at else None,
            'auction_type_name': at.name if at else None,
            'is_test': doc.is_test,
            'created_at': doc.created_at,
        },
        'extraction': extraction,
        'fields': field_mappings,
        'can_export': can_export,
        'blocking_issues': blocking_issues,
        'order_id': extracted_fields.get('order_id', {}).get('value'),
    }


@router.delete("/{id}", status_code=204)
async def delete_document(id: int):
    """Delete a document."""
    doc = DocumentRepository.get_by_id(id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file if exists
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    # Delete from database
    from api.database import get_connection
    with get_connection() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (id,))
        conn.commit()

    return None
