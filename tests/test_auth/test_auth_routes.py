"""
Integration tests for CKP Enterprise Access Gate REST endpoints and FastAPI dependencies.
Tests:
- POST /api/v2/auth/verify
- GET /api/v2/auth/quota
- POST /api/v2/auth/logout
- Role-based authorization (require_admin, get_current_user)
- Evaluator quota enforcement (enforce_quota)
"""

from __future__ import annotations

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from backend.main import app
from backend.auth.service import AuthService, DEMO_QUERY_LIMIT, ADMIN_KEY, DEMO_CODE


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def ensure_auth_service():
    """Ensure app.state.auth_service is fresh for test isolation."""
    app.state.auth_service = AuthService()
    yield
    app.state.auth_service = AuthService()


@pytest.mark.asyncio
async def test_auth_verify_success():
    """Verify endpoint successfully authenticates valid admin and demo passcodes."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Admin verify
        res_admin = await client.post("/api/v2/auth/verify", json={"passcode": ADMIN_KEY})
        assert res_admin.status_code == 200
        data_admin = res_admin.json()
        assert data_admin["role"] == "admin"
        assert "token" in data_admin
        assert data_admin["queries_remaining"] == -1

        # Demo verify
        res_demo = await client.post("/api/v2/auth/verify", json={"passcode": DEMO_CODE})
        assert res_demo.status_code == 200
        data_demo = res_demo.json()
        assert data_demo["role"] == "demo"
        assert "token" in data_demo
        assert data_demo["queries_remaining"] == DEMO_QUERY_LIMIT


@pytest.mark.asyncio
async def test_auth_verify_failure():
    """Verify endpoint rejects invalid passcodes with 401."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        res = await client.post("/api/v2/auth/verify", json={"passcode": "wrong-code"})
        assert res.status_code == 401
        assert "Invalid passcode" in res.json()["detail"]


@pytest.mark.asyncio
async def test_auth_quota_and_logout():
    """Test retrieving session quota and revoking session on logout."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Unauthenticated quota call fails with 401
        res_unauth = await client.get("/api/v2/auth/quota")
        assert res_unauth.status_code == 401

        # 2. Authenticate as demo
        res_auth = await client.post("/api/v2/auth/verify", json={"passcode": DEMO_CODE})
        token = res_auth.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Authenticated quota call succeeds
        res_quota = await client.get("/api/v2/auth/quota", headers=headers)
        assert res_quota.status_code == 200
        assert res_quota.json()["role"] == "demo"
        assert res_quota.json()["queries_remaining"] == DEMO_QUERY_LIMIT

        # 4. Logout revokes the session
        res_logout = await client.post("/api/v2/auth/logout", headers=headers)
        assert res_logout.status_code == 200
        assert res_logout.json()["status"] == "logged_out"


@pytest.mark.asyncio
async def test_admin_route_forbidden_for_demo():
    """Demo sessions cannot access admin-only endpoints (403 Forbidden)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Obtain demo token
        res_auth = await client.post("/api/v2/auth/verify", json={"passcode": DEMO_CODE})
        token = res_auth.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt admin action (e.g., crawler toggle)
        res_admin_action = await client.post(
            "/api/v2/crawler/toggle",
            json={"action": "pause"},
            headers=headers,
        )
        assert res_admin_action.status_code == 403
        assert "Admin access required" in res_admin_action.json()["detail"]


@pytest.mark.asyncio
async def test_quota_exhaustion_on_queries():
    """Demo sessions are capped at DEMO_QUERY_LIMIT, returning 429 when exhausted."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        res_auth = await client.post("/api/v2/auth/verify", json={"passcode": DEMO_CODE})
        token = res_auth.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        session_id = res_auth.json()["session_id"]

        # Mock query execution so we only test quota gate
        from unittest.mock import MagicMock
        from ai_gateway.router import RoutingDecision, ComplexityTier, IntentType
        from agent_harness.runner import RunResult

        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=RunResult(
            query="Test question",
            final_response="Test response",
            steps=[],
            total_steps=1,
            total_duration_ms=50.0,
        ))
        mock_decision = RoutingDecision(
            tier=ComplexityTier.TIER_1,
            selected_model="gemini-3-flash-preview",
            intent=IntentType.GRAPH_RAG,
            reason="test",
            estimated_cost_tier="free",
        )

        with patch("backend.routes.resolve_routing_and_skill", return_value=(mock_runner, mock_decision, "test_skill", None)):

            # Consume up to DEMO_QUERY_LIMIT
            for i in range(DEMO_QUERY_LIMIT):
                res = await client.post(
                    "/api/v2/query",
                    json={"query": f"Test question {i}"},
                    headers=headers,
                )
                assert res.status_code == 200, f"Query {i} failed: {res.text}"

            # Next query must be blocked with 429 Too Many Requests
            res_blocked = await client.post(
                "/api/v2/query",
                json={"query": "Exhausted question"},
                headers=headers,
            )
            assert res_blocked.status_code == 429
            assert "Demo query limit reached" in res_blocked.json()["detail"]
