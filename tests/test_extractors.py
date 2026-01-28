"""Tests for PDF extractors."""
import pytest
from unittest.mock import Mock, patch

from extractors.base import BaseExtractor
from extractors.iaa import IAAExtractor
from extractors.manheim import ManheimExtractor
from extractors.copart import CopartExtractor
from extractors import ExtractorManager
from models.vehicle import AuctionSource, VehicleType


class TestBaseExtractor:
    """Tests for BaseExtractor utility methods."""

    def test_extract_vin_valid(self):
        """Test VIN extraction with valid 17-char VIN."""
        text = "Vehicle VIN: 1HGBH41JXMN109186 is ready"
        vin = BaseExtractor.extract_vin(text)
        assert vin == "1HGBH41JXMN109186"

    def test_extract_vin_no_match(self):
        """Test VIN extraction with no valid VIN."""
        text = "No VIN here, just some text"
        vin = BaseExtractor.extract_vin(text)
        assert vin is None

    def test_extract_vin_excludes_invalid(self):
        """Test that VINs with I, O, Q are not matched."""
        # VINs cannot contain I, O, or Q
        text = "Invalid VIN: 1HGBH41JOMN109186"  # Contains O
        vin = BaseExtractor.extract_vin(text)
        assert vin is None

    def test_extract_phone(self):
        """Test phone number extraction."""
        test_cases = [
            ("Call us at (555) 123-4567", "(555) 123-4567"),
            ("Phone: 555-123-4567", "555-123-4567"),
            ("Contact: 555.123.4567", "555.123.4567"),
        ]
        for text, expected in test_cases:
            result = BaseExtractor.extract_phone(text)
            assert result is not None, f"Failed to extract from: {text}"

    def test_extract_zip(self):
        """Test ZIP code extraction."""
        text = "Address: 123 Main St, City, ST 12345-6789"
        zip_code = BaseExtractor.extract_zip(text)
        assert zip_code == "12345-6789"

        text2 = "ZIP: 90210"
        zip_code2 = BaseExtractor.extract_zip(text2)
        assert zip_code2 == "90210"

    def test_detect_vehicle_type_suv(self):
        """Test SUV detection."""
        suv_cases = [
            ("VOLVO", "XC90"),
            ("JEEP", "CHEROKEE"),
            ("FORD", "EXPLORER"),
            ("HYUNDAI", "TUCSON"),
        ]
        for make, model in suv_cases:
            result = BaseExtractor.detect_vehicle_type(make, model)
            assert result == VehicleType.SUV, f"Failed for {make} {model}"

    def test_detect_vehicle_type_car(self):
        """Test car detection."""
        car_cases = [
            ("ALFA ROMEO", "GIULIA"),
            ("MERCEDES", "E 300"),
            ("TOYOTA", "CAMRY"),
        ]
        for make, model in car_cases:
            result = BaseExtractor.detect_vehicle_type(make, model)
            assert result == VehicleType.CAR, f"Failed for {make} {model}"

    def test_detect_vehicle_type_truck(self):
        """Test truck detection."""
        truck_cases = [
            ("FORD", "F-150"),
            ("CHEVROLET", "SILVERADO"),
            ("RAM", "1500 TRUCK"),
        ]
        for make, model in truck_cases:
            result = BaseExtractor.detect_vehicle_type(make, model)
            assert result == VehicleType.TRUCK, f"Failed for {make} {model}"

    def test_extract_year(self):
        """Test year extraction."""
        text = "2023 Toyota Camry"
        year = BaseExtractor.extract_year(text)
        assert year == 2023

        text2 = "Model year: 1999"
        year2 = BaseExtractor.extract_year(text2)
        assert year2 == 1999

    def test_extract_mileage(self):
        """Test mileage extraction."""
        test_cases = [
            ("Mileage: 45,678", 45678),
            ("Mileage: 123456", 123456),
            ("45,678 Miles", 45678),
        ]
        for text, expected in test_cases:
            result = BaseExtractor.extract_mileage(text)
            assert result == expected, f"Failed for: {text}"

    def test_extract_amount(self):
        """Test amount extraction."""
        test_cases = [
            ("Total: $1,234.56", 1234.56),
            ("Price $999", 999.0),
            ("Amount Due: $45,678.90", 45678.90),
        ]
        for text, expected in test_cases:
            result = BaseExtractor.extract_amount(text)
            assert result == expected, f"Failed for: {text}"


class TestIAAExtractor:
    """Tests for IAA extractor."""

    def test_can_extract_positive(self):
        """Test that IAA documents are recognized."""
        extractor = IAAExtractor()

        positive_cases = [
            "Insurance Auto Auctions - Buyer Receipt",
            "IAAI BRE Document",
            "Buyer Receipt from IAA",
        ]
        for text in positive_cases:
            assert extractor.can_extract(text), f"Should recognize: {text}"

    def test_can_extract_negative(self):
        """Test that non-IAA documents are rejected."""
        extractor = IAAExtractor()

        negative_cases = [
            "Copart Sales Receipt",
            "Manheim Bill of Sale",
            "Random document text",
        ]
        for text in negative_cases:
            assert not extractor.can_extract(text), f"Should not recognize: {text}"

    def test_source_property(self):
        """Test source property returns IAA."""
        extractor = IAAExtractor()
        assert extractor.source == AuctionSource.IAA


class TestManheimExtractor:
    """Tests for Manheim extractor."""

    def test_can_extract_positive(self):
        """Test that Manheim documents are recognized."""
        extractor = ManheimExtractor()

        positive_cases = [
            "Manheim Auto Auction",
            "Cox Automotive - Bill of Sale",
            "VEHICLE RELEASE from Manheim",
            "Visit Manheim.com",
        ]
        for text in positive_cases:
            assert extractor.can_extract(text), f"Should recognize: {text}"

    def test_can_extract_negative(self):
        """Test that non-Manheim documents are rejected."""
        extractor = ManheimExtractor()

        negative_cases = [
            "Insurance Auto Auctions",
            "Copart Sales Receipt",
            "Random document",
        ]
        for text in negative_cases:
            assert not extractor.can_extract(text), f"Should not recognize: {text}"

    def test_source_property(self):
        """Test source property returns MANHEIM."""
        extractor = ManheimExtractor()
        assert extractor.source == AuctionSource.MANHEIM


class TestCopartExtractor:
    """Tests for Copart extractor."""

    def test_can_extract_positive(self):
        """Test that Copart documents are recognized."""
        extractor = CopartExtractor()

        positive_cases = [
            "Copart - Sales Receipt",
            "Sales Receipt/Bill of Sale",
            "SOLD THROUGH COPART",
            "MEMBER: 12345",
            "PHYSICAL ADDRESS OF LOT",
        ]
        for text in positive_cases:
            assert extractor.can_extract(text), f"Should recognize: {text}"

    def test_can_extract_negative(self):
        """Test that non-Copart documents are rejected."""
        extractor = CopartExtractor()

        negative_cases = [
            "Insurance Auto Auctions",
            "Manheim Bill of Sale",
            "Random document",
        ]
        for text in negative_cases:
            assert not extractor.can_extract(text), f"Should not recognize: {text}"

    def test_source_property(self):
        """Test source property returns COPART."""
        extractor = CopartExtractor()
        assert extractor.source == AuctionSource.COPART


class TestExtractorManager:
    """Tests for ExtractorManager."""

    def test_manager_has_all_extractors(self):
        """Test that manager includes all three extractors."""
        manager = ExtractorManager()

        sources = [e.source for e in manager.extractors]
        assert AuctionSource.IAA in sources
        assert AuctionSource.MANHEIM in sources
        assert AuctionSource.COPART in sources

    def test_get_extractor_for_text_iaa(self):
        """Test extractor selection for IAA text."""
        manager = ExtractorManager()

        extractor = manager.get_extractor_for_text("Insurance Auto Auctions Buyer Receipt")
        assert extractor is not None
        assert extractor.source == AuctionSource.IAA

    def test_get_extractor_for_text_manheim(self):
        """Test extractor selection for Manheim text."""
        manager = ExtractorManager()

        extractor = manager.get_extractor_for_text("Manheim Bill of Sale")
        assert extractor is not None
        assert extractor.source == AuctionSource.MANHEIM

    def test_get_extractor_for_text_copart(self):
        """Test extractor selection for Copart text."""
        manager = ExtractorManager()

        extractor = manager.get_extractor_for_text("Copart Sales Receipt/Bill of Sale")
        assert extractor is not None
        assert extractor.source == AuctionSource.COPART

    def test_get_extractor_for_unknown_text(self):
        """Test extractor selection for unrecognized text."""
        manager = ExtractorManager()

        extractor = manager.get_extractor_for_text("Some random document")
        assert extractor is None
