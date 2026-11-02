"""
Integration tests for Autonomous Crawler REST endpoints:
- GET /api/v2/crawler/status
- POST /api/v2/crawler/toggle
- GET /api/v2/crawler/logs
- POST /api/v2/crawler/scan-now
- POST /api/v2/crawler/webhook
"""

from __future__ import annotations

import httpx
import pytest

from backend.main import app
from backend.crawler.service import CrawlerService


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_crawler_endpoints(tmp_path):
    # Ensure app state has crawler service
    watch_dir = tmp_path / "test_incoming"
    watch_dir.mkdir(parents=True, exist_ok=True)

    if not hasattr(app.state, "crawler") or app.state.crawler is None:
        app.state.crawler = CrawlerService(watch_dir=watch_dir)

    if not hasattr(app.state, "auth_service") or app.state.auth_service is None:
        from backend.auth.service import AuthService
        app.state.auth_service = AuthService()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Obtain admin token
        auth_res = await client.post("/api/v2/auth/verify", json={"passcode": "ckp-admin-2025"})
        assert auth_res.status_code == 200
        admin_token = auth_res.json()["token"]
        auth_headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. GET /api/v2/crawler/status
        res_status = await client.get("/api/v2/crawler/status")
        assert res_status.status_code == 200
        data = res_status.json()
        assert "status" in data
        assert "connectors" in data

        # 2. POST /api/v2/crawler/toggle (pause)
        res_pause = await client.post("/api/v2/crawler/toggle", json={"action": "pause"}, headers=auth_headers)
        assert res_pause.status_code == 200
        assert res_pause.json()["status"] == "paused"

        # 3. POST /api/v2/crawler/toggle (resume)
        res_resume = await client.post("/api/v2/crawler/toggle", json={"action": "resume"}, headers=auth_headers)
        assert res_resume.status_code == 200
        assert res_resume.json()["status"] == "running"

        # 4. POST /api/v2/crawler/webhook
        res_webhook = await client.post(
            "/api/v2/crawler/webhook",
            json={
                "filename": "automated_patient_ehr.json",
                "content": '{"patient_id": "P-101", "diagnosis": "Hypertension", "medication": "Amlodipine"}',
                "metadata": {"source_system": "EpicEHR"},
            },
            headers=auth_headers,
        )
        assert res_webhook.status_code == 200
        webhook_data = res_webhook.json()
        assert webhook_data["filename"] == "automated_patient_ehr.json"
        assert webhook_data["detected_domain"] == "healthtech"
        assert webhook_data["status"] == "pending"

        # 5. GET /api/v2/crawler/logs
        res_logs = await client.get("/api/v2/crawler/logs?limit=10")
        assert res_logs.status_code == 200
        logs_data = res_logs.json()
        assert "logs" in logs_data
        assert logs_data["total"] >= 1
        assert logs_data["logs"][0]["filename"] == "automated_patient_ehr.json"

        # 6. POST /api/v2/crawler/scan-now
        res_scan = await client.post("/api/v2/crawler/scan-now", headers=auth_headers)
        assert res_scan.status_code == 200
        scan_data = res_scan.json()
        assert scan_data["status"] == "ok"
        assert "files_queued" in scan_data
