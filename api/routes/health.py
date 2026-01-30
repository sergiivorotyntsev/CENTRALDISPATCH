"""Health check endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any
import os
from pathlib import Path

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    checks: Dict[str, Any]


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns system health status including:
    - Database connectivity
    - Required directories
    - Configuration status
    """
    checks = {}
    overall_status = "healthy"

    # Check database
    try:
        from api.database import DB_PATH
        checks["database"] = {
            "status": "ok" if DB_PATH.exists() else "not_initialized",
            "path": str(DB_PATH),
        }
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)}
        overall_status = "unhealthy"

    # Check data directories
    data_dirs = ["data", "datasets", "datasets/runs", "config"]
    for dir_name in data_dirs:
        dir_path = Path(dir_name)
        checks[f"dir_{dir_name.replace('/', '_')}"] = {
            "exists": dir_path.exists(),
            "writable": os.access(dir_path, os.W_OK) if dir_path.exists() else False,
        }

    # Check config files
    config_files = {
        "local_settings": "config/local_settings.json",
        "env_file": ".env",
        "sheets_credentials": os.getenv("SHEETS_CREDENTIALS_FILE", "config/sheets_credentials.json"),
    }
    for name, path in config_files.items():
        checks[f"config_{name}"] = {
            "exists": Path(path).exists(),
        }

    # Check export targets
    try:
        from core.config import load_local_settings
        settings = load_local_settings()
        checks["export_targets"] = {
            "enabled": settings.get("export_targets", []),
        }
    except Exception as e:
        checks["export_targets"] = {"status": "error", "error": str(e)}

    return HealthResponse(
        status=overall_status,
        version="1.0.0",
        checks=checks,
    )


@router.get("/ready")
async def readiness_check():
    """Simple readiness probe for k8s/docker."""
    return {"ready": True}


@router.get("/live")
async def liveness_check():
    """Simple liveness probe for k8s/docker."""
    return {"alive": True}
