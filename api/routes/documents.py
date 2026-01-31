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
    auction_type_id: int = Form(..., description="Auction type ID"),
    dataset_split: str = Form(..., description="Dataset split: train or test"),
    uploaded_by: Optional[str] = Form(None, description="Uploader identifier"),
):
    """
    Upload a document for extraction and training.

    The document is associated with an auction type and marked as train or test.
    Duplicate detection is performed using SHA256 hash.
    """
    # Validate auction type
    auction_type = AuctionTypeRepository.get_by_id(auction_type_id)
    if not auction_type:
        raise HTTPException(status_code=400, detail="Invalid auction_type_id")

    # Validate dataset split
    if dataset_split not in ("train", "test"):
        raise HTTPException(status_code=400, detail="dataset_split must be 'train' or 'test'")

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
        return DocumentUploadResponse(
            document=DocumentResponse(
                **existing.__dict__,
                auction_type_code=auction_type.code,
            ),
            is_duplicate=True,
        )

    # Save file
    file_path = UPLOAD_DIR / f"{sha256[:16]}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(content)

    # Extract raw text using pdfplumber
    raw_text = None
    page_count = 0
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            text_parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            raw_text = "\n".join(text_parts)
    except Exception as e:
        # Log but don't fail
        print(f"Warning: Could not extract text from PDF: {e}")

    # Create document record
    doc_id = DocumentRepository.create(
        auction_type_id=auction_type_id,
        dataset_split=dataset_split,
        filename=file.filename,
        file_path=str(file_path),
        file_size=file_size,
        sha256=sha256,
        raw_text=raw_text,
        uploaded_by=uploaded_by,
    )

    # Update page count if extracted
    if page_count > 0:
        from api.database import get_connection
        with get_connection() as conn:
            conn.execute("UPDATE documents SET page_count = ? WHERE id = ?", (page_count, doc_id))
            conn.commit()

    doc = DocumentRepository.get_by_id(doc_id)

    return DocumentUploadResponse(
        document=DocumentResponse(
            **doc.__dict__,
            auction_type_code=auction_type.code,
        ),
        is_duplicate=False,
        raw_text_preview=raw_text[:500] if raw_text else None,
    )


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    auction_type_id: Optional[int] = Query(None, description="Filter by auction type"),
    dataset_split: Optional[str] = Query(None, description="Filter by split: train or test"),
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

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            docs = [Document(**dict(row)) for row in rows]

            # Get counts
            train_count = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE dataset_split = 'train'"
            ).fetchone()[0]
            test_count = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE dataset_split = 'test'"
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
