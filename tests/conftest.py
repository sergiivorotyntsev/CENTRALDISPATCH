"""
Pytest configuration and shared fixtures.
"""

import os
import sys
import tempfile
from pathlib import Path

# Set environment variables BEFORE any imports that might use them
TEST_DB_PATH = tempfile.mktemp(suffix=".db")
TEST_AUTH_CONFIG_PATH = tempfile.mktemp(suffix=".json")

os.environ["DATABASE_PATH"] = TEST_DB_PATH
os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["UPLOADS_DIR"] = tempfile.mkdtemp()
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["AUTH_CONFIG_PATH"] = TEST_AUTH_CONFIG_PATH

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables (already set at module level)."""
    yield
    # Cleanup
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    if os.path.exists(TEST_AUTH_CONFIG_PATH):
        os.remove(TEST_AUTH_CONFIG_PATH)


@pytest.fixture(scope="session")
def app():
    """Create FastAPI test application."""
    from api.main import app

    return app


@pytest.fixture(scope="session")
def client(app):
    """Create test client."""
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture(scope="session")
def auth_headers(app):
    """Get authentication headers for API requests."""
    from api.auth import UserRole, create_token, create_user

    # Create test admin user
    try:
        create_user("test-admin", "test-password", UserRole.ADMIN)
    except Exception:
        pass  # User may already exist

    token = create_token("test-admin", "admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def auth_client(app, auth_headers):
    """Create authenticated test client."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.headers.update(auth_headers)
    return client


@pytest.fixture
def sample_pdf_bytes():
    """Generate minimal valid PDF bytes for testing."""
    # Minimal PDF structure
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Test) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000206 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
300
%%EOF"""


@pytest.fixture
def db_connection():
    """Get database connection for test assertions."""
    from api.models import get_connection

    with get_connection() as conn:
        yield conn


@pytest.fixture
def clean_db(db_connection):
    """Clean database tables before test."""
    tables = [
        "documents",
        "extraction_runs",
        "extracted_vehicles",
        "review_corrections",
        "training_examples",
        "export_history",
        "email_activity",
        "email_rules",
    ]
    for table in tables:
        try:
            db_connection.execute(f"DELETE FROM {table}")
        except Exception:
            pass  # Table might not exist
    db_connection.commit()
    yield
