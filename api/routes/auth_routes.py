"""
Authentication API Routes

Endpoints:
- POST /api/auth/login - Login and get JWT token
- POST /api/auth/register - Register new user (admin only)
- GET /api/auth/me - Get current user info
- GET /api/auth/users - List users (admin only)
- DELETE /api/auth/users/{username} - Delete user (admin only)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import (
    LoginRequest,
    TokenResponse,
    User,
    UserCreate,
    UserRole,
    authenticate_user,
    create_token,
    create_user,
    delete_user,
    list_users,
    require_admin,
    require_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT token.

    Returns access token valid for JWT_EXPIRATION_HOURS (default 24).
    """
    user = authenticate_user(request.username, request.password)

    if not user:
        logger.warning(f"Failed login attempt for user: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_token(user.username, user.role.value)

    logger.info(f"User logged in: {user.username} (role: {user.role.value})")

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=24 * 3600,  # seconds
        user=user,
    )


@router.get("/me", response_model=User)
async def get_current_user_info(user: User = Depends(require_auth)):
    """Get current authenticated user information."""
    return user


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register_user(request: UserCreate, admin: User = Depends(require_admin)):
    """
    Register a new user.

    Requires admin role. Available roles:
    - admin: Full access
    - operator: Execute and view, limited write
    - viewer: Read-only access
    """
    try:
        user = create_user(
            username=request.username,
            password=request.password,
            role=request.role,
            email=request.email,
        )
        logger.info(f"User created: {user.username} (role: {user.role.value}) by {admin.username}")
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/users", response_model=list[User])
async def get_users(admin: User = Depends(require_admin)):
    """List all users. Requires admin role."""
    return list_users()


@router.delete("/users/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(username: str, admin: User = Depends(require_admin)):
    """Delete a user. Requires admin role. Cannot delete yourself."""
    if username == admin.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    if not delete_user(username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found",
        )

    logger.info(f"User deleted: {username} by {admin.username}")


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    current_password: str,
    new_password: str,
    user: User = Depends(require_auth),
):
    """Change current user's password."""
    from api.auth import _hash_password, _load_users, _save_users

    # Verify current password
    if not authenticate_user(user.username, current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Update password
    data = _load_users()
    password_hash, salt = _hash_password(new_password)
    data["users"][user.username]["password_hash"] = password_hash
    data["users"][user.username]["salt"] = salt
    _save_users(data)

    logger.info(f"Password changed for user: {user.username}")
