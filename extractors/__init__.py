"""Extractor manager - auto-detects document type and uses appropriate extractor."""
from typing import Optional, List

from extractors.base import BaseExtractor
from extractors.iaa import IAAExtractor
from extractors.manheim import ManheimExtractor
from extractors.copart import CopartExtractor
from models.vehicle import AuctionInvoice


class ExtractorManager:
    """Manages multiple extractors and auto-detects document types."""

    def __init__(self):
        self.extractors: List[BaseExtractor] = [
            IAAExtractor(),
            ManheimExtractor(),
            CopartExtractor()
        ]

    def extract(self, pdf_path: str) -> Optional[AuctionInvoice]:
        """Extract data from a PDF, auto-detecting the document type."""
        for extractor in self.extractors:
            try:
                text = extractor.extract_text(pdf_path)
                if extractor.can_extract(text):
                    result = extractor.extract(pdf_path)
                    if result:
                        return result
            except Exception as e:
                print(f"Extractor {extractor.__class__.__name__} failed: {e}")
                continue
        return None

    def get_extractor_for_text(self, text: str) -> Optional[BaseExtractor]:
        for extractor in self.extractors:
            if extractor.can_extract(text):
                return extractor
        return None


def extract_from_pdf(pdf_path: str) -> Optional[AuctionInvoice]:
    """Extract auction invoice data from a PDF file."""
    manager = ExtractorManager()
    return manager.extract(pdf_path)
