"""Base extractor class for auction invoices."""
import re
from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
import pdfplumber

from models.vehicle import AuctionInvoice, Vehicle, Address, AuctionSource, LocationType, VehicleType


class BaseExtractor(ABC):
    """Base class for auction document extractors."""

    @property
    @abstractmethod
    def source(self) -> AuctionSource:
        pass

    @abstractmethod
    def can_extract(self, text: str) -> bool:
        pass

    @abstractmethod
    def extract(self, pdf_path: str) -> Optional[AuctionInvoice]:
        pass

    def extract_text(self, pdf_path: str) -> str:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    def extract_pages_text(self, pdf_path: str) -> List[str]:
        pages = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                pages.append(page_text or "")
        return pages

    @staticmethod
    def clean_text(text: str) -> str:
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def extract_vin(text: str) -> Optional[str]:
        pattern = r'\b[A-HJ-NPR-Z0-9]{17}\b'
        match = re.search(pattern, text)
        return match.group(0) if match else None

    @staticmethod
    def extract_phone(text: str) -> Optional[str]:
        patterns = [
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            r'\d{3}[-.\s]\d{3}[-.\s]\d{4}'
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def extract_zip(text: str) -> Optional[str]:
        pattern = r'\b\d{5}(?:-\d{4})?\b'
        match = re.search(pattern, text)
        return match.group(0) if match else None

    @staticmethod
    def parse_address(text: str) -> Tuple[str, str, str]:
        pattern = r'([A-Za-z\s]+)[,\s]+([A-Z]{2})[\s.,]+(\d{5}(?:-\d{4})?)'
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip(), match.group(2), match.group(3)
        return "", "", ""

    @staticmethod
    def detect_vehicle_type(make: str, model: str) -> VehicleType:
        combined = f"{make} {model}".upper()

        suv_keywords = ['SUV', 'XC90', 'XC60', 'XC40', 'DURANGO', 'CHEROKEE',
                       'TUCSON', 'KONA', 'EXPLORER', 'TAHOE', 'SUBURBAN']
        car_keywords = ['SEDAN', 'COUPE', 'HARDTOP', 'GIULIA', 'E 300', 'CAMRY', 'ACCORD']
        truck_keywords = ['TRUCK', 'F-150', 'SILVERADO', 'RAM', 'TUNDRA']
        van_keywords = ['VAN', 'CARAVAN', 'ODYSSEY', 'SIENNA']

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
        pattern = r'\b(19|20)\d{2}\b'
        match = re.search(pattern, text)
        if match:
            return int(match.group(0))
        return None

    @staticmethod
    def extract_mileage(text: str) -> Optional[int]:
        patterns = [
            r'Mileage[:\s]+(\d{1,3}(?:,\d{3})*|\d+)',
            r'(\d{1,3}(?:,\d{3})*)\s*(?:Miles|Mi\.?)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                mileage = match.group(1).replace(',', '')
                return int(mileage)
        return None

    @staticmethod
    def extract_amount(text: str, keyword: str = None) -> Optional[float]:
        if keyword:
            pattern = rf'{keyword}[:\s]*\$?\s*([\d,]+(?:\.\d{2})?)'
        else:
            pattern = r'\$\s*([\d,]+(?:\.\d{2})?)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount = match.group(1).replace(',', '')
            return float(amount)
        return None
