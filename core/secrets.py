"""
Secrets Management Module

Provides secure secret retrieval from environment variables with fallback to local settings.
In production, all secrets should be provided via environment variables.

Environment Variable Mapping:
- CLICKUP_API_TOKEN: ClickUp API token
- CD_USERNAME: Central Dispatch username
- CD_PASSWORD: Central Dispatch password
- EMAIL_PASSWORD: IMAP email password
- EMAIL_OAUTH_CLIENT_ID: OAuth2 client ID (Microsoft 365)
- EMAIL_OAUTH_CLIENT_SECRET: OAuth2 client secret
- SHEETS_CREDENTIALS_JSON: Google Sheets service account JSON (base64 encoded)
"""

import base64
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _get_env(key: str) -> Optional[str]:
    """Get environment variable value."""
    return os.getenv(key)


def _get_from_settings(key_path: str) -> Optional[str]:
    """Get value from local settings file.

    key_path is dot-separated, e.g., "clickup.api_token"
    """
    try:
        from api.routes.settings import load_settings
        settings = load_settings()

        parts = key_path.split(".")
        value = settings
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value if isinstance(value, str) else None
    except Exception:
        return None


def get_secret(name: str, settings_path: Optional[str] = None) -> str:
    """Get a secret value.

    Priority:
    1. Environment variable
    2. Local settings file (if settings_path provided)
    3. Empty string

    Args:
        name: Environment variable name
        settings_path: Optional dot-separated path in settings file

    Returns:
        Secret value or empty string if not found
    """
    # Try environment first
    value = _get_env(name)
    if value:
        logger.debug(f"Secret {name} loaded from environment")
        return value

    # Fall back to settings file
    if settings_path:
        value = _get_from_settings(settings_path)
        if value:
            logger.debug(f"Secret {name} loaded from settings ({settings_path})")
            return value

    return ""


def get_clickup_token() -> str:
    """Get ClickUp API token."""
    return get_secret("CLICKUP_API_TOKEN", "clickup.api_token")


def get_cd_credentials() -> tuple[str, str]:
    """Get Central Dispatch credentials.

    Returns:
        Tuple of (username, password)
    """
    username = get_secret("CD_USERNAME", "cd.username")
    password = get_secret("CD_PASSWORD", "cd.password")
    return username, password


def get_email_password() -> str:
    """Get email IMAP password."""
    return get_secret("EMAIL_PASSWORD", "email.password")


def get_email_oauth_credentials() -> tuple[str, str, str]:
    """Get email OAuth2 credentials.

    Returns:
        Tuple of (client_id, client_secret, tenant_id)
    """
    client_id = get_secret("EMAIL_OAUTH_CLIENT_ID", "email.oauth_client_id")
    client_secret = get_secret("EMAIL_OAUTH_CLIENT_SECRET", "email.oauth_client_secret")
    tenant_id = get_secret("EMAIL_OAUTH_TENANT_ID", "email.oauth_tenant_id")
    return client_id, client_secret, tenant_id


def get_sheets_credentials() -> Optional[dict]:
    """Get Google Sheets service account credentials.

    Supports:
    1. SHEETS_CREDENTIALS_JSON env var (base64 encoded JSON)
    2. SHEETS_CREDENTIALS_FILE env var (path to JSON file)
    3. Local settings file path

    Returns:
        Credentials dict or None if not found
    """
    # Try base64 encoded JSON from env
    creds_json = _get_env("SHEETS_CREDENTIALS_JSON")
    if creds_json:
        try:
            decoded = base64.b64decode(creds_json).decode("utf-8")
            return json.loads(decoded)
        except Exception as e:
            logger.warning(f"Failed to decode SHEETS_CREDENTIALS_JSON: {e}")

    # Try credentials file path from env
    creds_file = _get_env("SHEETS_CREDENTIALS_FILE")
    if creds_file and os.path.exists(creds_file):
        try:
            with open(creds_file) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load credentials from {creds_file}: {e}")

    # Try settings file
    creds_path = _get_from_settings("sheets.credentials_file")
    if creds_path and os.path.exists(creds_path):
        try:
            with open(creds_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load credentials from {creds_path}: {e}")

    return None


def has_secret(name: str, settings_path: Optional[str] = None) -> bool:
    """Check if a secret is configured (without revealing its value)."""
    return bool(get_secret(name, settings_path))


def mask_secret(value: str) -> str:
    """Mask a secret value for display.

    Shows first 4 and last 4 characters for long secrets,
    or **** for short secrets.
    """
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


# Environment variable documentation
ENV_VARS = {
    "CLICKUP_API_TOKEN": "ClickUp API token for task creation",
    "CD_USERNAME": "Central Dispatch API username",
    "CD_PASSWORD": "Central Dispatch API password",
    "EMAIL_PASSWORD": "Email IMAP password",
    "EMAIL_OAUTH_CLIENT_ID": "Microsoft 365 OAuth2 client ID",
    "EMAIL_OAUTH_CLIENT_SECRET": "Microsoft 365 OAuth2 client secret",
    "EMAIL_OAUTH_TENANT_ID": "Microsoft 365 tenant ID",
    "SHEETS_CREDENTIALS_JSON": "Google Sheets service account JSON (base64)",
    "SHEETS_CREDENTIALS_FILE": "Path to Google Sheets credentials JSON file",
    "JWT_SECRET_KEY": "Secret key for JWT token signing (required in production)",
    "CORS_ORIGINS": "Comma-separated list of allowed CORS origins",
}


def check_production_readiness() -> list[str]:
    """Check if all required secrets are configured for production.

    Returns list of missing or insecure configurations.
    """
    warnings = []

    # Check JWT secret
    jwt_secret = _get_env("JWT_SECRET_KEY")
    if not jwt_secret:
        warnings.append("JWT_SECRET_KEY not set - using auto-generated secret (not recommended for production)")
    elif len(jwt_secret) < 32:
        warnings.append("JWT_SECRET_KEY is too short (should be at least 32 characters)")

    # Check CORS
    cors_origins = _get_env("CORS_ORIGINS")
    if not cors_origins or cors_origins == "*":
        warnings.append("CORS_ORIGINS not set or using wildcard (not recommended for production)")

    return warnings
