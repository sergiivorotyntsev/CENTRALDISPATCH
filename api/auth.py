"""
Authentication Module

JWT-based authentication with role-based access control.

Roles:
- admin: Full access to all settings and integrations
- operator: Can view and execute, cannot modify integrations
- viewer: Read-only access

Usage:
    from api.auth import require_auth, require_admin, get_current_user

    @router.get("/settings")
    async def get_settings(user: User = Depends(require_auth)):
        ...

    @router.put("/settings")
    async def update_settings(user: User = Depends(require_admin)):
        ...
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# JWT secret key - MUST be set via environment in production
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# Auth configuration file
AUTH_CONFIG_PATH = Path(os.getenv("AUTH_CONFIG_PATH", "config/auth.json"))


def get_jwt_secret() -> str:
    """Get JWT secret key, generating one if needed for development."""
    global JWT_SECRET_KEY

    if JWT_SECRET_KEY:
        return JWT_SECRET_KEY

    # Check for secret in config file (development only)
    secret_file = Path("config/.jwt_secret")
    if secret_file.exists():
        JWT_SECRET_KEY = secret_file.read_text().strip()
        return JWT_SECRET_KEY

    # Generate new secret for development
    if os.getenv("ENVIRONMENT", "development") == "development":
        JWT_SECRET_KEY = secrets.token_hex(32)
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(JWT_SECRET_KEY)
        os.chmod(secret_file, 0o600)
        logger.warning("Generated new JWT secret for development. Set JWT_SECRET_KEY in production!")
        return JWT_SECRET_KEY

    raise ValueError("JWT_SECRET_KEY must be set in production environment")


# =============================================================================
# MODELS
# =============================================================================


class UserRole(str, Enum):
    """User roles for RBAC."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(BaseModel):
    """Authenticated user."""

    username: str
    role: UserRole
    email: Optional[str] = None
    created_at: Optional[str] = None


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # username
    role: str
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp


class TokenResponse(BaseModel):
    """Login response with token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


class LoginRequest(BaseModel):
    """Login request."""

    username: str
    password: str


class UserCreate(BaseModel):
    """Create user request."""

    username: str
    password: str
    role: UserRole = UserRole.VIEWER
    email: Optional[str] = None


# =============================================================================
# TOKEN UTILITIES
# =============================================================================


def _base64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    """Base64url decode with padding restoration."""
    import base64

    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def create_token(username: str, role: str) -> str:
    """Create a JWT token."""
    now = datetime.utcnow()
    exp = now + timedelta(hours=JWT_EXPIRATION_HOURS)

    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    # Encode header and payload
    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode())

    # Create signature
    message = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        get_jwt_secret().encode(), message.encode(), hashlib.sha256
    ).digest()
    signature_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_token(token: str) -> Optional[TokenPayload]:
    """Verify and decode a JWT token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        message = f"{header_b64}.{payload_b64}"
        expected_signature = hmac.new(
            get_jwt_secret().encode(), message.encode(), hashlib.sha256
        ).digest()

        actual_signature = _base64url_decode(signature_b64)
        if not hmac.compare_digest(expected_signature, actual_signature):
            logger.warning("Invalid token signature")
            return None

        # Decode payload
        payload_json = _base64url_decode(payload_b64).decode()
        payload_data = json.loads(payload_json)

        # Check expiration
        if payload_data.get("exp", 0) < datetime.utcnow().timestamp():
            logger.warning("Token expired")
            return None

        return TokenPayload(**payload_data)

    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        return None


# =============================================================================
# USER MANAGEMENT
# =============================================================================


def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Hash password with salt."""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return hashed.hex(), salt


def _load_users() -> dict:
    """Load users from config file."""
    if not AUTH_CONFIG_PATH.exists():
        return {"users": {}}
    try:
        return json.loads(AUTH_CONFIG_PATH.read_text())
    except Exception:
        return {"users": {}}


def _save_users(data: dict) -> None:
    """Save users to config file."""
    AUTH_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_CONFIG_PATH.write_text(json.dumps(data, indent=2))
    os.chmod(AUTH_CONFIG_PATH, 0o600)


def create_user(username: str, password: str, role: UserRole, email: Optional[str] = None) -> User:
    """Create a new user."""
    data = _load_users()

    if username in data.get("users", {}):
        raise ValueError(f"User '{username}' already exists")

    password_hash, salt = _hash_password(password)

    data.setdefault("users", {})[username] = {
        "password_hash": password_hash,
        "salt": salt,
        "role": role.value,
        "email": email,
        "created_at": datetime.utcnow().isoformat(),
    }

    _save_users(data)

    return User(
        username=username,
        role=role,
        email=email,
        created_at=data["users"][username]["created_at"],
    )


def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate user and return User if valid."""
    data = _load_users()
    user_data = data.get("users", {}).get(username)

    if not user_data:
        return None

    password_hash, _ = _hash_password(password, user_data["salt"])
    if not hmac.compare_digest(password_hash, user_data["password_hash"]):
        return None

    return User(
        username=username,
        role=UserRole(user_data["role"]),
        email=user_data.get("email"),
        created_at=user_data.get("created_at"),
    )


def get_user(username: str) -> Optional[User]:
    """Get user by username."""
    data = _load_users()
    user_data = data.get("users", {}).get(username)

    if not user_data:
        return None

    return User(
        username=username,
        role=UserRole(user_data["role"]),
        email=user_data.get("email"),
        created_at=user_data.get("created_at"),
    )


def list_users() -> list[User]:
    """List all users."""
    data = _load_users()
    users = []
    for username, user_data in data.get("users", {}).items():
        users.append(
            User(
                username=username,
                role=UserRole(user_data["role"]),
                email=user_data.get("email"),
                created_at=user_data.get("created_at"),
            )
        )
    return users


def delete_user(username: str) -> bool:
    """Delete a user."""
    data = _load_users()
    if username not in data.get("users", {}):
        return False

    del data["users"][username]
    _save_users(data)
    return True


def ensure_admin_exists() -> None:
    """Ensure at least one admin user exists (for initial setup)."""
    data = _load_users()
    users = data.get("users", {})

    # Check if any admin exists
    has_admin = any(u.get("role") == "admin" for u in users.values())

    if not has_admin:
        # Create default admin (password should be changed immediately)
        default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin")
        create_user("admin", default_password, UserRole.ADMIN)
        logger.warning(
            "Created default admin user. "
            "Change the password immediately via API or set DEFAULT_ADMIN_PASSWORD env var."
        )


# =============================================================================
# FASTAPI DEPENDENCIES
# =============================================================================

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """Get current user from token (returns None if not authenticated)."""
    if not credentials:
        return None

    payload = verify_token(credentials.credentials)
    if not payload:
        return None

    user = get_user(payload.sub)
    return user


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Require authentication (any role)."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user(payload.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def require_admin(user: User = Depends(require_auth)) -> User:
    """Require admin role."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_operator(user: User = Depends(require_auth)) -> User:
    """Require operator or admin role."""
    if user.role not in [UserRole.ADMIN, UserRole.OPERATOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator access required",
        )
    return user


def check_permission(user: User, resource: str, action: str) -> bool:
    """Check if user has permission for action on resource.

    Permission matrix:
    - admin: all actions on all resources
    - operator: read, execute on all resources; write on non-sensitive
    - viewer: read only
    """
    if user.role == UserRole.ADMIN:
        return True

    if user.role == UserRole.OPERATOR:
        if action in ["read", "execute"]:
            return True
        # Operators can write to non-sensitive resources
        if action == "write" and resource not in ["users", "integrations", "secrets"]:
            return True
        return False

    if user.role == UserRole.VIEWER:
        return action == "read"

    return False
