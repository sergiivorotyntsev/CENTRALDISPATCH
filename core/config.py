"""Centralized configuration management with validation."""
import os
import re
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


def _mask_secret(value: str, visible_chars: int = 4) -> str:
    """Mask a secret value for logging, showing only first few chars."""
    if not value:
        return "<empty>"
    if len(value) <= visible_chars:
        return "*" * len(value)
    return value[:visible_chars] + "*" * (len(value) - visible_chars)


@dataclass
class EmailConfig:
    """Email/IMAP configuration."""
    provider: str = "imap"  # "imap" or "graph"
    imap_server: str = ""
    imap_port: int = 993
    address: str = ""
    password: str = ""
    folder: str = "INBOX"
    check_interval: int = 60
    from_filter: Optional[str] = None
    subject_filter: Optional[str] = None

    # OAuth2/Graph settings (for M365)
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    def validate(self) -> List[str]:
        """Validate email configuration, return list of errors."""
        errors = []

        if self.provider == "imap":
            if not self.imap_server:
                errors.append("EMAIL_IMAP_SERVER is required for IMAP provider")
            if not self.address:
                errors.append("EMAIL_ADDRESS is required")
            if not self.password and not (self.client_id and self.client_secret):
                errors.append("EMAIL_PASSWORD or OAuth2 credentials required")
        elif self.provider == "graph":
            if not self.tenant_id:
                errors.append("EMAIL_TENANT_ID is required for Graph provider")
            if not self.client_id:
                errors.append("EMAIL_CLIENT_ID is required for Graph provider")
            if not self.client_secret:
                errors.append("EMAIL_CLIENT_SECRET is required for Graph provider")
            if not self.address:
                errors.append("EMAIL_ADDRESS is required")
        else:
            errors.append(f"Unknown EMAIL_PROVIDER: {self.provider}")

        return errors

    def __repr__(self) -> str:
        return (f"EmailConfig(provider={self.provider}, server={self.imap_server}, "
                f"address={self.address}, password={_mask_secret(self.password)})")


@dataclass
class ClickUpConfig:
    """ClickUp API configuration."""
    token: str = ""
    list_id: str = ""

    # Custom field IDs (optional, for stable field binding)
    field_id_vin: Optional[str] = None
    field_id_lot: Optional[str] = None
    field_id_gate_pass: Optional[str] = None
    field_id_auction: Optional[str] = None
    field_id_pickup_address: Optional[str] = None

    def validate(self) -> List[str]:
        """Validate ClickUp configuration, return list of errors."""
        errors = []
        if not self.token:
            errors.append("CLICKUP_TOKEN is required")
        if not self.list_id:
            errors.append("CLICKUP_LIST_ID is required")
        return errors

    def __repr__(self) -> str:
        return f"ClickUpConfig(token={_mask_secret(self.token)}, list_id={self.list_id})"


@dataclass
class CentralDispatchConfig:
    """Central Dispatch API configuration."""
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    marketplace_id: int = 10000

    def validate(self) -> List[str]:
        """Validate CD configuration, return list of errors."""
        errors = []
        if self.enabled:
            if not self.client_id:
                errors.append("CD_CLIENT_ID is required when CD is enabled")
            if not self.client_secret:
                errors.append("CD_CLIENT_SECRET is required when CD is enabled")
        return errors

    def __repr__(self) -> str:
        return (f"CentralDispatchConfig(enabled={self.enabled}, "
                f"client_id={_mask_secret(self.client_id)}, marketplace_id={self.marketplace_id})")


@dataclass
class StorageConfig:
    """Storage/persistence configuration."""
    idempotency_db_path: str = "processed_emails.db"
    temp_dir: str = "/tmp/dispatch"

    def validate(self) -> List[str]:
        """Validate storage configuration, return list of errors."""
        errors = []
        # Ensure parent directory exists or can be created
        db_parent = Path(self.idempotency_db_path).parent
        if str(db_parent) != "." and not db_parent.exists():
            try:
                db_parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create idempotency DB directory: {e}")
        return errors


@dataclass
class AppConfig:
    """Main application configuration."""
    email: EmailConfig = field(default_factory=EmailConfig)
    clickup: ClickUpConfig = field(default_factory=ClickUpConfig)
    central_dispatch: CentralDispatchConfig = field(default_factory=CentralDispatchConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)

    # Runtime settings
    dry_run: bool = False
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "text"

    def validate(self, require_email: bool = True, require_clickup: bool = True) -> None:
        """Validate all configuration, raise ConfigurationError if invalid."""
        errors = []

        if require_email:
            errors.extend(self.email.validate())
        if require_clickup:
            errors.extend(self.clickup.validate())

        errors.extend(self.central_dispatch.validate())
        errors.extend(self.storage.validate())

        if errors:
            raise ConfigurationError("Configuration errors:\n  - " + "\n  - ".join(errors))

    def __repr__(self) -> str:
        return (f"AppConfig(\n  email={self.email},\n  clickup={self.clickup},\n  "
                f"central_dispatch={self.central_dispatch},\n  storage={self.storage},\n  "
                f"dry_run={self.dry_run}, log_level={self.log_level}\n)")


def load_config_from_env() -> AppConfig:
    """Load configuration from environment variables."""

    # Load .env file if present (optional dependency)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    config = AppConfig(
        email=EmailConfig(
            provider=os.getenv("EMAIL_PROVIDER", "imap"),
            imap_server=os.getenv("EMAIL_IMAP_SERVER", ""),
            imap_port=int(os.getenv("EMAIL_IMAP_PORT", "993")),
            address=os.getenv("EMAIL_ADDRESS", ""),
            password=os.getenv("EMAIL_PASSWORD", ""),
            folder=os.getenv("EMAIL_FOLDER", "INBOX"),
            check_interval=int(os.getenv("EMAIL_CHECK_INTERVAL", "60")),
            from_filter=os.getenv("EMAIL_FROM_FILTER"),
            subject_filter=os.getenv("EMAIL_SUBJECT_FILTER"),
            tenant_id=os.getenv("EMAIL_TENANT_ID"),
            client_id=os.getenv("EMAIL_CLIENT_ID"),
            client_secret=os.getenv("EMAIL_CLIENT_SECRET"),
        ),
        clickup=ClickUpConfig(
            token=os.getenv("CLICKUP_TOKEN", ""),
            list_id=os.getenv("CLICKUP_LIST_ID", ""),
            field_id_vin=os.getenv("CLICKUP_FIELD_ID_VIN"),
            field_id_lot=os.getenv("CLICKUP_FIELD_ID_LOT"),
            field_id_gate_pass=os.getenv("CLICKUP_FIELD_ID_GATE_PASS"),
            field_id_auction=os.getenv("CLICKUP_FIELD_ID_AUCTION"),
            field_id_pickup_address=os.getenv("CLICKUP_FIELD_ID_PICKUP_ADDRESS"),
        ),
        central_dispatch=CentralDispatchConfig(
            enabled=os.getenv("CD_ENABLED", "false").lower() in ("true", "1", "yes"),
            client_id=os.getenv("CD_CLIENT_ID", ""),
            client_secret=os.getenv("CD_CLIENT_SECRET", ""),
            marketplace_id=int(os.getenv("CD_MARKETPLACE_ID", "10000")),
        ),
        storage=StorageConfig(
            idempotency_db_path=os.getenv("IDEMPOTENCY_DB_PATH", "processed_emails.db"),
            temp_dir=os.getenv("TEMP_DIR", "/tmp/dispatch"),
        ),
        dry_run=os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        log_format=os.getenv("LOG_FORMAT", "text"),
    )

    return config


# Singleton config instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config_from_env()
    return _config


def reset_config() -> None:
    """Reset the global configuration (for testing)."""
    global _config
    _config = None
