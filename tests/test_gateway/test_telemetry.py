"""
Tests for TelemetryStore — Audit logging, live pricing engine, KPI summaries, and CSV/Excel export.
"""

from __future__ import annotations

import tempfile
import pytest

from ai_gateway.telemetry import AuditLogEntry, TelemetryStore


@pytest.fixture
def temp_telemetry_store():
    """Create a temporary TelemetryStore instance."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        store = TelemetryStore(db_path=f.name)
        yield store


class TestTelemetryStore:
    """Test suite for TelemetryStore functionality."""

    def test_record_and_get_logs(self, temp_telemetry_store: TelemetryStore):
        """Should record audit logs and retrieve them with pagination."""
        entry = AuditLogEntry(
            session_id="test-session-123",
            prompt_preview="What is the treatment for hypertension?",
            model_name="gemini-2.5-flash",
            provider="gemini",
            is_smart_routed=True,
            complexity_tier="tier_1",
            intent="graph_rag",
            input_tokens=150,
            output_tokens=300,
            duration_ms=450.0,
            status="success",
            tools_called=["execute_cypher"],
            routing_reason="Tier 1 single-hop query",
        )
        call_id = temp_telemetry_store.record_call(entry)
        assert call_id == entry.call_id

        # Query logs
        result = temp_telemetry_store.get_logs(limit=10, offset=0)
        assert result["total"] == 1
        assert len(result["logs"]) == 1

        log = result["logs"][0]
        assert log["call_id"] == call_id
        assert log["session_id"] == "test-session-123"
        assert log["model_name"] == "gemini-2.5-flash"
        assert log["is_smart_routed"] is True
        assert log["complexity_tier"] == "tier_1"
        assert log["total_cost_usd"] > 0.0
        assert log["tools_called"] == ["execute_cypher"]

    def test_filtering_and_search(self, temp_telemetry_store: TelemetryStore):
        """Should filter by model, smart routing flag, and text search."""
        temp_telemetry_store.record_call(AuditLogEntry(
            session_id="sess-a",
            prompt_preview="Query Metformin patient data",
            model_name="gemini-2.5-flash",
            is_smart_routed=True,
        ))
        temp_telemetry_store.record_call(AuditLogEntry(
            session_id="sess-b",
            prompt_preview="Deep clinical synthesis",
            model_name="claude-3-5-sonnet",
            is_smart_routed=False,
        ))

        # Filter by model
        res_flash = temp_telemetry_store.get_logs(model="flash")
        assert res_flash["total"] == 1
        assert res_flash["logs"][0]["model_name"] == "gemini-2.5-flash"

        # Filter by smart_routed
        res_routed = temp_telemetry_store.get_logs(smart_routed=True)
        assert res_routed["total"] == 1
        assert res_routed["logs"][0]["session_id"] == "sess-a"

        # Search prompt
        res_search = temp_telemetry_store.get_logs(search="Metformin")
        assert res_search["total"] == 1
        assert "Metformin" in res_search["logs"][0]["prompt_preview"]

    def test_summary_and_ai_economics(self, temp_telemetry_store: TelemetryStore):
        """Summary should compute aggregated KPIs and AI economics cost savings."""
        temp_telemetry_store.record_call(AuditLogEntry(
            model_name="gemini-2.5-flash",
            is_smart_routed=True,
            complexity_tier="tier_1",
            input_tokens=1000,
            output_tokens=2000,
            duration_ms=300.0,
        ))
        temp_telemetry_store.record_call(AuditLogEntry(
            model_name="gemini-2.5-pro",
            is_smart_routed=True,
            complexity_tier="tier_2",
            input_tokens=2000,
            output_tokens=4000,
            duration_ms=600.0,
        ))

        summary = temp_telemetry_store.get_summary()
        assert summary["total_requests"] == 2
        assert summary["total_tokens"] == 9000
        assert summary["smart_routed_count"] == 2
        assert summary["smart_routed_percentage"] == 100.0
        assert summary["total_spend_usd"] > 0.0
        assert summary["estimated_savings_usd"] > 0.0
        assert summary["savings_percentage"] > 0.0
        assert "tier_1" in summary["tier_distribution"]

    def test_export_csv(self, temp_telemetry_store: TelemetryStore):
        """CSV export should contain CSV headers and formatted data rows."""
        temp_telemetry_store.record_call(AuditLogEntry(
            session_id="export-test",
            prompt_preview="Export test query",
            model_name="gemini-2.5-flash",
        ))

        csv_content = temp_telemetry_store.export_csv()
        assert "call_id,timestamp,session_id" in csv_content
        assert "export-test" in csv_content
        assert "gemini-2.5-flash" in csv_content

    def test_export_excel_xml(self, temp_telemetry_store: TelemetryStore):
        """Excel export should produce valid XML Spreadsheet 2003 content."""
        temp_telemetry_store.record_call(AuditLogEntry(
            session_id="excel-test",
            prompt_preview="Excel test query",
            model_name="gemini-2.5-flash",
        ))

        xml_content = temp_telemetry_store.export_excel_xml()
        assert '<?xml version="1.0"?>' in xml_content
        assert '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"' in xml_content
        assert 'excel-test' in xml_content
