"""Base extractor class for auction invoices."""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import pdfplumber

from models.vehicle import (
    AuctionInvoice,
    AuctionSource,
    VehicleType,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of PDF extraction with metadata."""

    invoice: Optional[AuctionInvoice]
    source: AuctionSource
    score: float  # 0.0 to 1.0 confidence
    text_length: int
    needs_ocr: bool = False
    matched_patterns: list[str] = None

    def __post_init__(self):
        if self.matched_patterns is None:
            self.matched_patterns = []


class BaseExtractor(ABC):
    """Base class for auction document extractors."""

    # Minimum text length to consider document valid (vs scan/image)
    MIN_TEXT_LENGTH = 100

    # Score threshold for confident detection
    SCORE_THRESHOLD = 0.6

    @property
    @abstractmethod
    def source(self) -> AuctionSource:
        pass

    @property
    @abstractmethod
    def indicators(self) -> list[str]:
        """List of text patterns that indicate this document type."""
        pass

    @property
    def indicator_weights(self) -> dict:
        """Optional weights for indicators (default: equal weight)."""
        return {}

    def score(self, text: str) -> tuple[float, list[str]]:
        """
        Calculate confidence score for this extractor.
        Returns (score, matched_patterns) where score is 0.0 to 1.0.
        """
        if not text or len(text) < self.MIN_TEXT_LENGTH:
            return 0.0, []

        text_lower = text.lower()
        matched = []
        total_weight = 0.0
        matched_weight = 0.0

        for indicator in self.indicators:
            weight = self.indicator_weights.get(indicator, 1.0)
            total_weight += weight

            if indicator.lower() in text_lower:
                matched.append(indicator)
                matched_weight += weight

        if total_weight == 0:
            return 0.0, []

        score = matched_weight / total_weight
        return score, matched

    def can_extract(self, text: str) -> bool:
        """Check if this extractor can handle the document."""
        score, _ = self.score(text)
        return score >= self.SCORE_THRESHOLD

    @abstractmethod
    def extract(self, pdf_path: str) -> Optional[AuctionInvoice]:
        pass

    def extract_with_result(self, pdf_path: str, text: str = None) -> ExtractionResult:
        """Extract with full result metadata."""
        if text is None:
            text = self.extract_text(pdf_path)

        score, matched = self.score(text)
        needs_ocr = len(text) < self.MIN_TEXT_LENGTH

        if needs_ocr:
            logger.warning(f"Document has insufficient text ({len(text)} chars), may need OCR")

        invoice = None
        if score >= self.SCORE_THRESHOLD:
            try:
                invoice = self.extract(pdf_path)
            except Exception as e:
                logger.error(f"Extraction failed: {e}")

        return ExtractionResult(
            invoice=invoice,
            source=self.source,
            score=score,
            text_length=len(text),
            needs_ocr=needs_ocr,
            matched_patterns=matched,
        )

    def extract_text(self, pdf_path: str) -> str:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    def extract_pages_text(self, pdf_path: str) -> list[str]:
        pages = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                pages.append(page_text or "")
        return pages

    @staticmethod
    def clean_text(text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def extract_vin(text: str) -> Optional[str]:
        pattern = r"\b[A-HJ-NPR-Z0-9]{17}\b"
        match = re.search(pattern, text)
        return match.group(0) if match else None

    @staticmethod
    def extract_phone(text: str) -> Optional[str]:
        patterns = [r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", r"\d{3}[-.\s]\d{3}[-.\s]\d{4}"]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def extract_zip(text: str) -> Optional[str]:
        pattern = r"\b\d{5}(?:-\d{4})?\b"
        match = re.search(pattern, text)
        return match.group(0) if match else None

    @staticmethod
    def parse_address(text: str) -> tuple[str, str, str]:
        pattern = r"([A-Za-z\s]+)[,\s]+([A-Z]{2})[\s.,]+(\d{5}(?:-\d{4})?)"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip(), match.group(2), match.group(3)
        return "", "", ""

    @staticmethod
    def detect_vehicle_type(make: str, model: str) -> VehicleType:
        combined = f"{make} {model}".upper()

        suv_keywords = [
            "SUV",
            "XC90",
            "XC60",
            "XC40",
            "DURANGO",
            "CHEROKEE",
            "TUCSON",
            "KONA",
            "EXPLORER",
            "TAHOE",
            "SUBURBAN",
        ]
        car_keywords = ["SEDAN", "COUPE", "HARDTOP", "GIULIA", "E 300", "CAMRY", "ACCORD"]
        truck_keywords = ["TRUCK", "F-150", "SILVERADO", "RAM", "TUNDRA"]
        van_keywords = ["VAN", "CARAVAN", "ODYSSEY", "SIENNA"]

        for keyword in suv_keywords:
            if keyword in combined:
                return VehicleType.SUV
        for keyword in car_keywords:
            if keyword in combined:
                return VehicleType.CAR
        for keyword in truck_keywords:
            if keyword in combined:
                return VehicleType.TRUCK
        for keyword in van_keywords:
            if keyword in combined:
                return VehicleType.VAN

        return VehicleType.SUV

    @staticmethod
    def extract_year(text: str) -> Optional[int]:
        pattern = r"\b(19|20)\d{2}\b"
        match = re.search(pattern, text)
        if match:
            return int(match.group(0))
        return None

    @staticmethod
    def extract_mileage(text: str) -> Optional[int]:
        patterns = [
            # Match "Mileage: 123456" or "Mileage: 123,456" - \d+ first for non-comma numbers
            r"Mileage[:\s]+(\d+(?:,\d{3})*|\d+)",
            r"(\d{1,3}(?:,\d{3})+|\d+)\s*(?:Miles|Mi\.?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                mileage = match.group(1).replace(",", "")
                return int(mileage)
        return None

    @staticmethod
    def extract_amount(text: str, keyword: str = None) -> Optional[float]:
        if keyword:
            pattern = rf"{keyword}[:\s]*\$?\s*([\d,]+(?:\.\d{2})?)"
        else:
            pattern = r"\$\s*([\d,]+(?:\.\d{2})?)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount = match.group(1).replace(",", "")
            return float(amount)
        return None
