"""
Unit tests for CKP Enterprise Access Gate — AuthService.
Validates passcode verification, JWT issuance/validation, and quota enforcement.
"""

import time
import pytest
from backend.auth.service import AuthService, AccessRole, DEMO_QUERY_LIMIT, ADMIN_KEY, DEMO_CODE


@pytest.fixture
def auth_service():
    """Fresh instance of AuthService for each test."""
    return AuthService()


def test_verify_passcode_admin(auth_service):
    """Admin passcode matches ADMIN role."""
    role = auth_service.verify_passcode(ADMIN_KEY)
    assert role == AccessRole.ADMIN


def test_verify_passcode_demo(auth_service):
    """Demo code matches DEMO role."""
    role = auth_service.verify_passcode(DEMO_CODE)
    assert role == AccessRole.DEMO


def test_verify_passcode_invalid(auth_service):
    """Wrong passcode returns None."""
    assert auth_service.verify_passcode("wrong-passcode") is None
    assert auth_service.verify_passcode("") is None


def test_jwt_issuance_and_decoding(auth_service):
    """Tokens issued can be successfully decoded."""
    session_id = "test-session-123"
    token = auth_service.issue_token(AccessRole.ADMIN, session_id)
    assert isinstance(token, str)

    payload = auth_service.decode_token(token)
    assert payload is not None
    assert payload.role == AccessRole.ADMIN
    assert payload.session_id == session_id
    assert payload.expires_at > time.time()


def test_jwt_invalid_token(auth_service):
    """Malformed or tampered tokens return None."""
    assert auth_service.decode_token("not-a-token") is None
    assert auth_service.decode_token("header.payload.signature") is None


def test_demo_quota_consumption(auth_service):
    """Demo sessions are subject to strict per-session query caps."""
    session_id = "demo-session-456"
    auth_service.issue_token(AccessRole.DEMO, session_id)

    # Initial quota check
    info = auth_service.get_quota_info(session_id)
    assert info["role"] == "demo"
    assert info["queries_used"] == 0
    assert info["queries_remaining"] == DEMO_QUERY_LIMIT
    assert info["query_limit"] == DEMO_QUERY_LIMIT

    # Consume all queries
    for i in range(DEMO_QUERY_LIMIT):
        allowed, used, limit = auth_service.consume_query(session_id)
        assert allowed is True
        assert used == i + 1

    # Remaining should now be 0
    info_after = auth_service.get_quota_info(session_id)
    assert info_after["queries_remaining"] == 0

    # Next query must be blocked (429)
    allowed, used, limit = auth_service.consume_query(session_id)
    assert allowed is False
    assert used == DEMO_QUERY_LIMIT


def test_admin_unlimited_quota(auth_service):
    """Admin sessions have unlimited query quota."""
    session_id = "admin-session-789"
    auth_service.issue_token(AccessRole.ADMIN, session_id)

    # Consuming past normal limit is permitted
    for _ in range(DEMO_QUERY_LIMIT + 5):
        allowed, used, limit = auth_service.consume_query(session_id)
        assert allowed is True

    info = auth_service.get_quota_info(session_id)
    assert info["role"] == "admin"
    assert info["queries_remaining"] == -1  # indicates unlimited


def test_session_revocation(auth_service):
    """Revoking a session invalidates its quota and status."""
    session_id = "revoke-me"
    auth_service.issue_token(AccessRole.DEMO, session_id)
    assert auth_service.revoke_session(session_id) is True

    # Quota check on revoked session denies access
    allowed, _, _ = auth_service.check_quota(session_id)
    assert allowed is False

    # Second revoke returns False
    assert auth_service.revoke_session(session_id) is False
