"""
Integration tests for Monitoring & Observability REST Endpoints.
"""

from __future__ import annotations

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.main import app
from ai_gateway.telemetry import AuditLogEntry


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_monitoring_endpoints():
    """Verify /api/v2/monitoring/logs, summary, and export endpoints."""
    # Ensure app state has gateway with telemetry store
    if not hasattr(app.state, "gateway") or app.state.gateway is None:
        from ai_gateway.gateway import GatewayClient
        app.state.gateway = GatewayClient()

    # Pre-seed a test audit log
    app.state.gateway.telemetry.record_call(AuditLogEntry(
        session_id="test-integration-sess",
        prompt_preview="Integration test query for hypertension",
        model_name="gemini-2.5-flash",
        provider="gemini",
        is_smart_routed=True,
        complexity_tier="tier_1",
        intent="graph_rag",
        input_tokens=100,
        output_tokens=200,
        duration_ms=250.0,
    ))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. GET /api/v2/monitoring/logs
        res_logs = await client.get("/api/v2/monitoring/logs?limit=10")
        assert res_logs.status_code == 200
        logs_data = res_logs.json()
        assert "logs" in logs_data
        assert "total" in logs_data
        assert logs_data["total"] >= 1
        assert any(l["session_id"] == "test-integration-sess" for l in logs_data["logs"])

        # 2. GET /api/v2/monitoring/summary
        res_summary = await client.get("/api/v2/monitoring/summary")
        assert res_summary.status_code == 200
        summary_data = res_summary.json()
        assert "total_requests" in summary_data
        assert summary_data["total_requests"] >= 1
        assert "total_tokens" in summary_data
        assert "total_spend_usd" in summary_data
        assert "estimated_savings_usd" in summary_data
        assert "savings_percentage" in summary_data

        # 3. GET /api/v2/monitoring/export (CSV)
        res_csv = await client.get("/api/v2/monitoring/export?format=csv")
        assert res_csv.status_code == 200
        assert "text/csv" in res_csv.headers.get("content-type", "")
        assert "call_id,timestamp,session_id" in res_csv.text
        assert "test-integration-sess" in res_csv.text

        # 4. GET /api/v2/monitoring/export (Excel XML)
        res_excel = await client.get("/api/v2/monitoring/export?format=excel")
        assert res_excel.status_code == 200
        assert "application/vnd.ms-excel" in res_excel.headers.get("content-type", "")
        assert '<?xml version="1.0"?>' in res_excel.text
        assert "test-integration-sess" in res_excel.text
