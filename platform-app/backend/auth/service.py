"""
CKP Enterprise Access Gate — Authentication Service.

Implements a dual-tier passcode gate:
  - CKP_ADMIN_KEY:  full admin access (unlimited queries, all routes).
  - CKP_DEMO_CODE:  evaluator / recruiter access (capped queries, read-mostly).

Responsibilities:
  1. Passcode verification  →  POST /api/v2/auth/verify
  2. JWT issuance & validation (HS256, lightweight signed tokens)
  3. Per-session evaluator quota tracking (in-memory, server-side)
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import jwt  # PyJWT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
JWT_SECRET = os.getenv("CKP_JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = int(os.getenv("CKP_JWT_EXPIRY_SECONDS", "86400"))  # 24 h default

ADMIN_KEY = os.getenv("CKP_ADMIN_KEY", "ckp-admin-2025")
DEMO_CODE = os.getenv("CKP_DEMO_CODE", "ckp-demo")

DEMO_QUERY_LIMIT = int(os.getenv("CKP_DEMO_QUERY_LIMIT", "10"))


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------
class AccessRole(str, Enum):
    """Access tiers recognised by the gate."""

    ADMIN = "admin"
    DEMO = "demo"


@dataclass
class TokenPayload:
    """Decoded JWT payload."""

    role: AccessRole
    session_id: str
    issued_at: float
    expires_at: float


@dataclass
class SessionQuota:
    """Per-session evaluator quota tracker."""

    session_id: str
    role: AccessRole
    queries_used: int = 0
    query_limit: int = DEMO_QUERY_LIMIT
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Auth Service
# ---------------------------------------------------------------------------
class AuthService:
    """
    Server-side auth service managing passcode verification,
    JWT tokens, and evaluator quotas.
    """

    def __init__(self):
        self._sessions: dict[str, SessionQuota] = {}

    # ---- Passcode Verification -------------------------------------------

    def verify_passcode(self, passcode: str) -> Optional[AccessRole]:
        """
        Verify a passcode and return the matching role, or None.
        Constant-time comparison to mitigate timing attacks.
        """
        if secrets.compare_digest(passcode.strip(), ADMIN_KEY):
            return AccessRole.ADMIN
        if secrets.compare_digest(passcode.strip(), DEMO_CODE):
            return AccessRole.DEMO
        return None

    # ---- JWT Token Management --------------------------------------------

    def issue_token(self, role: AccessRole, session_id: str) -> str:
        """Issue a signed JWT access token."""
        now = time.time()
        payload = {
            "role": role.value,
            "sid": session_id,
            "iat": now,
            "exp": now + JWT_EXPIRY_SECONDS,
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        # Initialise quota tracker for this session
        limit = 0 if role == AccessRole.ADMIN else DEMO_QUERY_LIMIT
        self._sessions[session_id] = SessionQuota(
            session_id=session_id,
            role=role,
            query_limit=limit,
            created_at=now,
        )
        logger.info(
            "Issued %s token for session %s (limit=%s)",
            role.value, session_id[:8], limit or "unlimited",
        )
        return token

    def decode_token(self, token: str) -> Optional[TokenPayload]:
        """
        Decode and validate a JWT token.
        Returns None on any validation failure.
        """
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return TokenPayload(
                role=AccessRole(data["role"]),
                session_id=data["sid"],
                issued_at=data["iat"],
                expires_at=data["exp"],
            )
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
            logger.warning("Token validation failed: %s", exc)
            return None

    # ---- Quota Management ------------------------------------------------

    def check_quota(self, session_id: str) -> tuple[bool, int, int]:
        """
        Check whether the session has remaining queries.
        Returns (allowed, used, limit).
        Admins always pass.
        """
        quota = self._sessions.get(session_id)
        if quota is None:
            # Unknown session — deny
            return False, 0, 0
        if quota.role == AccessRole.ADMIN:
            return True, quota.queries_used, 0  # 0 ≡ unlimited
        return (
            quota.queries_used < quota.query_limit,
            quota.queries_used,
            quota.query_limit,
        )

    def consume_query(self, session_id: str) -> tuple[bool, int, int]:
        """
        Consume one query from the session quota.
        Returns (allowed, used_after, limit).
        """
        allowed, used, limit = self.check_quota(session_id)
        if not allowed:
            return False, used, limit
        quota = self._sessions[session_id]
        if quota.role == AccessRole.ADMIN:
            quota.queries_used += 1
            return True, quota.queries_used, 0
        quota.queries_used += 1
        return True, quota.queries_used, limit

    def get_quota_info(self, session_id: str) -> dict:
        """Return human-readable quota info."""
        quota = self._sessions.get(session_id)
        if not quota:
            return {"role": "unknown", "queries_used": 0, "queries_remaining": 0, "query_limit": 0}
        if quota.role == AccessRole.ADMIN:
            return {
                "role": "admin",
                "queries_used": quota.queries_used,
                "queries_remaining": -1,  # unlimited
                "query_limit": 0,
            }
        remaining = max(0, quota.query_limit - quota.queries_used)
        return {
            "role": "demo",
            "queries_used": quota.queries_used,
            "queries_remaining": remaining,
            "query_limit": quota.query_limit,
        }

    def revoke_session(self, session_id: str) -> bool:
        """Revoke a session (logout)."""
        removed = self._sessions.pop(session_id, None)
        if removed:
            logger.info("Revoked session %s", session_id[:8])
        return removed is not None

    def is_admin(self, session_id: str) -> bool:
        """Check if a session belongs to an admin."""
        quota = self._sessions.get(session_id)
        return quota is not None and quota.role == AccessRole.ADMIN
