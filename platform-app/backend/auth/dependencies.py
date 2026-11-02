"""
CKP Enterprise Access Gate — FastAPI Dependencies.

Provides injectable dependency functions for securing API routes:
  - get_current_user     → validates JWT from Authorization header,
                           returns TokenPayload.  Required for all
                           protected endpoints.
  - require_admin        → further restricts to admin-role tokens.
  - enforce_quota        → checks & consumes one evaluator query.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.service import AuthService, TokenPayload, AccessRole

logger = logging.getLogger(__name__)

# HTTPBearer extracts `Authorization: Bearer <token>`
_bearer_scheme = HTTPBearer(auto_error=False)


def _get_auth_service(request: Request) -> AuthService:
    """Retrieve the shared AuthService from app state."""
    auth = getattr(request.app.state, "auth_service", None)
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service not initialized",
        )
    return auth


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> TokenPayload:
    """
    Validate the Bearer JWT and return the decoded TokenPayload.
    Raises 401 if the token is missing, expired, or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide an access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    auth_service = _get_auth_service(request)
    payload = auth_service.decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def require_admin(
    user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    """
    Ensure the authenticated user has admin role.
    Raises 403 if the user is a demo / evaluator session.
    """
    if user.role != AccessRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. Demo sessions cannot perform this action.",
        )
    return user


async def enforce_quota(
    request: Request,
    user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    """
    Check and consume one query from the session's evaluator quota.
    Admins pass unconditionally.  Demo sessions are limited.
    Raises 429 if the quota is exhausted.
    """
    auth_service = _get_auth_service(request)
    allowed, used, limit = auth_service.consume_query(user.session_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Demo query limit reached ({used}/{limit}). "
                "Please contact the administrator for full access."
            ),
        )
    return user
