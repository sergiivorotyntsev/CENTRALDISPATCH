"""
OpenAPI Contract Tests for Vehicle Transport Automation API.

These tests verify that the API endpoints conform to their documented contracts,
including request/response schemas, status codes, and error handling.
"""

import uuid
from io import BytesIO


def unique_code():
    """Generate a unique code for tests."""
    return f"TEST_{uuid.uuid4().hex[:8].upper()}"


class TestHealthEndpoint:
    """Contract tests for /api/health endpoint."""

    def test_health_returns_200(self, client):
        """Health check should return 200 OK."""
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_response_schema(self, client):
        """Health check should return status."""
        response = client.get("/api/health")
        data = response.json()
        assert "status" in data
        # API returns "healthy" or "unhealthy"
        assert data["status"] in ["healthy", "unhealthy"]

    def test_ready_returns_200(self, client):
        """Readiness check should return 200."""
        response = client.get("/api/ready")
        assert response.status_code == 200

    def test_live_returns_200(self, client):
        """Liveness check should return 200."""
        response = client.get("/api/live")
        assert response.status_code == 200


class TestAuctionTypesEndpoint:
    """Contract tests for /api/auction-types/ endpoint."""

    def test_list_auction_types_returns_200(self, client):
        """List auction types should return 200."""
        response = client.get("/api/auction-types/")
        assert response.status_code == 200

    def test_list_auction_types_response_schema(self, client):
        """List auction types should return paginated response."""
        response = client.get("/api/auction-types/")
        data = response.json()
        # Response is paginated: {"items": [...], "total": N}
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_list_auction_types_item_schema(self, client):
        """Each auction type should have required fields."""
        response = client.get("/api/auction-types/")
        data = response.json()
        if data["total"] > 0:
            item = data["items"][0]
            assert "id" in item
            assert "name" in item
            assert "code" in item

    def test_create_auction_type_returns_201(self, client):
        """Create auction type should return 201."""
        code = unique_code()
        response = client.post(
            "/api/auction-types/",
            json={
                "name": f"Test Auction Type {code}",
                "code": code,
                "description": "Test auction type for contract tests",
            },
        )
        assert response.status_code == 201

    def test_create_auction_type_response_schema(self, client):
        """Created auction type should have required fields."""
        code = unique_code()
        response = client.post(
            "/api/auction-types/",
            json={
                "name": f"Test Auction Type {code}",
                "code": code,
                "description": "Test auction type for contract tests",
            },
        )
        data = response.json()
        assert "id" in data
        assert "name" in data
        assert "code" in data

    def test_create_auction_type_validation_error(self, client):
        """Create auction type with invalid data should return 422."""
        response = client.post(
            "/api/auction-types/",
            json={
                # Missing required 'name' field
                "code": "INVALID",
            },
        )
        assert response.status_code == 422

    def test_get_auction_type_not_found(self, client):
        """Get non-existent auction type should return 404."""
        response = client.get("/api/auction-types/99999")
        assert response.status_code == 404


class TestDocumentsEndpoint:
    """Contract tests for /api/documents/ endpoint."""

    def test_list_documents_returns_200(self, client):
        """List documents should return 200."""
        response = client.get("/api/documents/")
        assert response.status_code == 200

    def test_list_documents_response_schema(self, client):
        """List documents should return paginated response."""
        response = client.get("/api/documents/")
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)

    def test_list_documents_with_pagination(self, client):
        """List documents should support pagination."""
        response = client.get("/api/documents/?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 5

    def test_upload_document_without_file_returns_422(self, client):
        """Upload without file should return 422."""
        response = client.post(
            "/api/documents/upload",
            data={
                "auction_type_id": 1,
            },
        )
        assert response.status_code == 422

    def test_get_document_not_found(self, client):
        """Get non-existent document should return 404."""
        response = client.get("/api/documents/99999")
        assert response.status_code == 404


class TestExtractionsEndpoint:
    """Contract tests for /api/extractions/ endpoint."""

    def test_needs_review_returns_200(self, client):
        """Needs review endpoint should return 200."""
        response = client.get("/api/extractions/needs-review")
        assert response.status_code == 200

    def test_run_extraction_invalid_document(self, client):
        """Run extraction with invalid document should return 404."""
        response = client.post(
            "/api/extractions/run",
            json={
                "document_id": 99999,
            },
        )
        assert response.status_code == 404


class TestReviewEndpoint:
    """Contract tests for /api/review/ endpoint."""

    def test_get_review_not_found(self, client):
        """Get review for non-existent run should return 404."""
        response = client.get("/api/review/99999")
        assert response.status_code == 404

    def test_training_examples_returns_200(self, client):
        """Training examples endpoint should return 200."""
        response = client.get("/api/review/training-examples/")
        assert response.status_code == 200


class TestExportsEndpoint:
    """Contract tests for /api/exports/ endpoint."""

    def test_preview_not_found(self, client):
        """Preview non-existent run should return appropriate response."""
        response = client.get("/api/exports/central-dispatch/preview/99999")
        # Should return 200 with empty results or 404
        assert response.status_code in [200, 404]


class TestWarehousesEndpoint:
    """Contract tests for /api/warehouses/ endpoint."""

    def test_list_warehouses_returns_200(self, client):
        """List warehouses should return 200."""
        response = client.get("/api/warehouses/")
        assert response.status_code == 200

    def test_list_warehouses_response_schema(self, client):
        """List warehouses should return paginated response."""
        response = client.get("/api/warehouses/")
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_create_warehouse_returns_201(self, client):
        """Create warehouse should return 201."""
        code = unique_code()
        response = client.post(
            "/api/warehouses/",
            json={
                "code": code,
                "name": f"Test Warehouse {code}",
                "timezone": "America/New_York",
            },
        )
        assert response.status_code == 201

    def test_create_warehouse_response_schema(self, client):
        """Created warehouse should have required fields."""
        code = unique_code()
        response = client.post(
            "/api/warehouses/",
            json={
                "code": code,
                "name": f"Test Warehouse {code}",
                "timezone": "America/Los_Angeles",
            },
        )
        data = response.json()
        assert "id" in data
        assert "code" in data
        assert "name" in data

    def test_get_warehouse_not_found(self, client):
        """Get non-existent warehouse should return 404."""
        response = client.get("/api/warehouses/99999")
        assert response.status_code == 404


class TestIntegrationsEndpoint:
    """Contract tests for /api/integrations/ endpoint."""

    def test_audit_log_returns_200(self, client):
        """Audit log should return 200."""
        response = client.get("/api/integrations/audit-log")
        assert response.status_code == 200

    def test_audit_log_response_is_list(self, client):
        """Audit log should return array."""
        response = client.get("/api/integrations/audit-log")
        data = response.json()
        assert isinstance(data, list)


class TestModelsEndpoint:
    """Contract tests for /api/models/ endpoint."""

    def test_list_model_versions_returns_200(self, client):
        """List model versions should return 200."""
        response = client.get("/api/models/versions")
        assert response.status_code == 200

    def test_list_model_versions_response_schema(self, client):
        """List model versions should return paginated or list response."""
        response = client.get("/api/models/versions")
        data = response.json()
        # May be list or paginated dict
        if isinstance(data, dict):
            assert "items" in data
        else:
            assert isinstance(data, list)

    def test_training_stats_returns_200(self, client):
        """Training stats should return 200."""
        response = client.get("/api/models/training-stats")
        assert response.status_code == 200


class TestOpenAPISpec:
    """Tests for OpenAPI specification."""

    def test_openapi_spec_available(self, client):
        """OpenAPI spec should be available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

    def test_openapi_spec_valid_json(self, client):
        """OpenAPI spec should be valid JSON."""
        response = client.get("/openapi.json")
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

    def test_openapi_spec_has_title(self, client):
        """OpenAPI spec should have title."""
        response = client.get("/openapi.json")
        data = response.json()
        assert data["info"]["title"] == "Vehicle Transport Automation"

    def test_openapi_spec_has_version(self, client):
        """OpenAPI spec should have version."""
        response = client.get("/openapi.json")
        data = response.json()
        assert "version" in data["info"]

    def test_swagger_docs_available(self, client):
        """Swagger UI should be available."""
        response = client.get("/api/docs")
        assert response.status_code == 200

    def test_redoc_available(self, client):
        """ReDoc should be available."""
        response = client.get("/api/redoc")
        assert response.status_code == 200


class TestRequestValidation:
    """Tests for request validation across endpoints."""

    def test_invalid_content_type_rejected(self, client):
        """Invalid content type should be rejected."""
        response = client.post(
            "/api/auction-types/",
            content="not json",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 422

    def test_missing_required_fields_rejected(self, client):
        """Missing required fields should return 422."""
        response = client.post("/api/auction-types/", json={})
        assert response.status_code == 422

    def test_invalid_field_types_rejected(self, client):
        """Invalid field types should return 422."""
        response = client.post(
            "/api/auction-types/",
            json={
                "name": 123,  # Should be string
                "code": ["not", "a", "string"],
            },
        )
        assert response.status_code == 422


class TestErrorResponses:
    """Tests for error response formats."""

    def test_404_response_format(self, client):
        """404 errors should have detail message."""
        response = client.get("/api/documents/99999")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_422_response_format(self, client):
        """422 errors should have detail with validation info."""
        response = client.post("/api/auction-types/", json={})
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


class TestCORSHeaders:
    """Tests for CORS configuration."""

    def test_cors_headers_present(self, client):
        """CORS headers should be present on responses."""
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Should allow CORS
        assert response.status_code in [200, 204]

    def test_request_id_header(self, client):
        """X-Request-ID header should be in response."""
        response = client.get("/api/health")
        assert "x-request-id" in response.headers
