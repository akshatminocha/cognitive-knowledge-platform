"""
Integration tests for Proactive Alerting & Standing Goals REST endpoints:
- GET /api/v2/alerts/rules
- POST /api/v2/alerts/rules
- PUT /api/v2/alerts/rules/{id}
- DELETE /api/v2/alerts/rules/{id}
- POST /api/v2/alerts/rules/{id}/toggle
- GET /api/v2/alerts/feed
- POST /api/v2/alerts/{id}/read
- POST /api/v2/alerts/{id}/dismiss
- GET /api/v2/alerts/unread-count
"""

from __future__ import annotations

import httpx
import pytest

from backend.main import app
from backend.auth.service import AuthService, ADMIN_KEY, DEMO_CODE
from backend.alerts.engine import AlertEngine
from backend.alerts.rules import AlertStore, AlertEvent, SeverityLevel


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def setup_app_state(tmp_path):
    """Ensure app.state has fresh auth_service and alert_engine for test isolation."""
    app.state.auth_service = AuthService()
    db_file = str(tmp_path / "test_api_alerts.db")
    store = AlertStore(db_path=db_file)
    app.state.alert_engine = AlertEngine(store=store)
    yield
    app.state.auth_service = AuthService()


@pytest.mark.asyncio
async def test_alert_rules_endpoints_lifecycle():
    """Test full rule lifecycle via REST: list, create, update, toggle, delete."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Unauthenticated request rejected
        res_unauth = await client.get("/api/v2/alerts/rules")
        assert res_unauth.status_code == 401

        # 2. Get tokens
        auth_admin = await client.post("/api/v2/auth/verify", json={"passcode": ADMIN_KEY})
        admin_token = auth_admin.json()["token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        auth_demo = await client.post("/api/v2/auth/verify", json={"passcode": DEMO_CODE})
        demo_token = auth_demo.json()["token"]
        demo_headers = {"Authorization": f"Bearer {demo_token}"}

        # 3. List rules (succeeds for demo and admin)
        res_list = await client.get("/api/v2/alerts/rules", headers=demo_headers)
        assert res_list.status_code == 200
        assert res_list.json()["count"] >= 3

        # 4. Demo cannot create a rule (403 Forbidden)
        new_rule_payload = {
            "name": "Hypoglycemia Alert",
            "description": "Blood glucose below 70 mg/dL",
            "rule_type": "property_threshold",
            "target_label": "Observation",
            "property_name": "glucose",
            "operator": "<",
            "threshold_value": 70.0,
            "severity": "CRITICAL",
        }
        res_create_demo = await client.post(
            "/api/v2/alerts/rules",
            json=new_rule_payload,
            headers=demo_headers,
        )
        assert res_create_demo.status_code == 403

        # 5. Admin creates rule
        res_create = await client.post(
            "/api/v2/alerts/rules",
            json=new_rule_payload,
            headers=admin_headers,
        )
        assert res_create.status_code == 200
        created_rule = res_create.json()
        rule_id = created_rule["id"]
        assert created_rule["name"] == "Hypoglycemia Alert"

        # 6. Admin updates rule
        res_update = await client.put(
            f"/api/v2/alerts/rules/{rule_id}",
            json={"threshold_value": 65.0},
            headers=admin_headers,
        )
        assert res_update.status_code == 200
        assert res_update.json()["threshold_value"] == 65.0

        # 7. Admin toggles rule
        res_toggle = await client.post(
            f"/api/v2/alerts/rules/{rule_id}/toggle",
            headers=admin_headers,
        )
        assert res_toggle.status_code == 200
        assert res_toggle.json()["enabled"] is False

        # 8. Admin deletes rule
        res_del = await client.delete(
            f"/api/v2/alerts/rules/{rule_id}",
            headers=admin_headers,
        )
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_alerts_feed_and_status_endpoints():
    """Test retrieving alerts feed, marking read, dismissing, and unread count."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        auth_admin = await client.post("/api/v2/auth/verify", json={"passcode": ADMIN_KEY})
        admin_token = auth_admin.json()["token"]
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Seed an alert directly in engine
        engine = app.state.alert_engine
        alert = AlertEvent(
            rule_id="test-rule-id",
            rule_name="Kidney Injury Marker",
            severity=SeverityLevel.CRITICAL,
            title="CRITICAL: Acute Kidney Injury Risk",
            message="Serum creatinine elevated > 2.0 mg/dL",
            entity_label="Observation",
            entity_id="obs-202",
            matched_properties={"creatinine": 2.4},
        )
        engine.store.record_alert(alert)

        # 1. Check unread count
        res_count = await client.get("/api/v2/alerts/unread-count", headers=headers)
        assert res_count.status_code == 200
        assert res_count.json()["unread_count"] >= 1

        # 2. Get alerts feed
        res_feed = await client.get("/api/v2/alerts/feed", headers=headers)
        assert res_feed.status_code == 200
        data = res_feed.json()
        assert data["count"] >= 1
        assert any(a["id"] == alert.id for a in data["alerts"])

        # 3. Mark alert as read
        res_read = await client.post(f"/api/v2/alerts/{alert.id}/read", headers=headers)
        assert res_read.status_code == 200
        assert res_read.json()["status"] == "read"

        # 4. Dismiss alert
        res_dismiss = await client.post(f"/api/v2/alerts/{alert.id}/dismiss", headers=headers)
        assert res_dismiss.status_code == 200
        assert res_dismiss.json()["status"] == "dismissed"
