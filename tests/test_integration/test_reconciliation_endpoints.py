"""
Integration tests for Self-Healing Knowledge Reconciler REST endpoints:
- POST /api/v2/reconciliation/scan
- POST /api/v2/reconciliation/merge
- GET /api/v2/reconciliation/audit
- POST /api/v2/reconciliation/rollback
"""

from __future__ import annotations

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.main import app
from backend.auth.service import AuthService, ADMIN_KEY, DEMO_CODE
from agent_harness.reconciler import KnowledgeReconciler, ReconciliationAuditStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def ensure_app_state(tmp_path):
    """Ensure app.state has fresh auth_service and reconciler for test isolation."""
    app.state.auth_service = AuthService()
    db_file = str(tmp_path / "test_api_audit.db")
    audit_store = ReconciliationAuditStore(db_path=db_file)

    mock_driver = MagicMock()
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    app.state.reconciler = KnowledgeReconciler(
        neo4j_driver=mock_driver,
        qdrant_client=None,
        audit_store=audit_store,
    )
    yield
    app.state.auth_service = AuthService()


@pytest.mark.asyncio
async def test_reconciliation_endpoints_lifecycle():
    """Test full reconciliation API cycle: scan, dry-run merge, actual merge, audit retrieval, rollback."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Unauthenticated scan call fails with 401
        res_unauth = await client.post("/api/v2/reconciliation/scan", json={})
        assert res_unauth.status_code == 401

        # 2. Get tokens
        auth_admin = await client.post("/api/v2/auth/verify", json={"passcode": ADMIN_KEY})
        admin_token = auth_admin.json()["token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        auth_demo = await client.post("/api/v2/auth/verify", json={"passcode": DEMO_CODE})
        demo_token = auth_demo.json()["token"]
        demo_headers = {"Authorization": f"Bearer {demo_token}"}

        # 3. Authenticated scan call succeeds (evaluators can scan)
        res_scan = await client.post(
            "/api/v2/reconciliation/scan",
            json={"threshold": 0.8},
            headers=demo_headers,
        )
        assert res_scan.status_code == 200
        assert "count" in res_scan.json()
        assert "candidates" in res_scan.json()

        # 4. Evaluator/Demo cannot execute merge (403 Forbidden)
        candidate_payload = {
            "source_id": "dr-1",
            "canonical_id": "dr-2",
            "entity_label": "Doctor",
            "source_name": "Dr. Gregory House",
            "canonical_name": "Dr. Gregory House, M.D.",
            "similarity_score": 0.94,
            "match_reasons": ["High name similarity"],
            "source_props": {"name": "Dr. Gregory House", "department": "Diagnostics"},
            "canonical_props": {"name": "Dr. Gregory House, M.D.", "specialty": "Nephrology"},
        }
        res_merge_demo = await client.post(
            "/api/v2/reconciliation/merge",
            json={"candidate": candidate_payload},
            headers=demo_headers,
        )
        assert res_merge_demo.status_code == 403

        # 5. Admin dry-run merge
        res_dry_run = await client.post(
            "/api/v2/reconciliation/merge",
            json={"candidate": candidate_payload, "dry_run": True},
            headers=admin_headers,
        )
        assert res_dry_run.status_code == 200
        assert res_dry_run.json()["dry_run"] is True
        assert res_dry_run.json()["merged_count"] == 1

        # 6. Admin actual merge
        res_merge = await client.post(
            "/api/v2/reconciliation/merge",
            json={"candidate": candidate_payload, "dry_run": False},
            headers=admin_headers,
        )
        assert res_merge.status_code == 200
        merge_data = res_merge.json()
        assert merge_data["status"] == "success"
        record = merge_data["records"][0]
        merge_id = record["merge_id"]
        assert record["status"] == "merged"

        # 7. Admin audit retrieval
        res_audit = await client.get("/api/v2/reconciliation/audit", headers=admin_headers)
        assert res_audit.status_code == 200
        audit_data = res_audit.json()
        assert audit_data["count"] >= 1
        assert any(r["merge_id"] == merge_id for r in audit_data["history"])

        # 8. Admin rollback
        res_rollback = await client.post(
            "/api/v2/reconciliation/rollback",
            json={"merge_id": merge_id},
            headers=admin_headers,
        )
        assert res_rollback.status_code == 200
        assert res_rollback.json()["status"] == "rolled_back"
