"""
Telemetry & Audit Store — Real-time observability and cost analytics for LLM calls.

Tracks:
- call_id, timestamp, session_id, prompt_preview
- model_name, provider, is_smart_routed, complexity_tier, intent
- input_tokens, output_tokens, input_cost_usd, output_cost_usd, total_cost_usd
- duration_ms, status, tools_called, routing_reason, cascade_reason
- Executive AI Economics KPIs (spend, token consumption, tier distributions, estimated savings)
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ai_gateway.config import DEFAULT_MODELS

logger = logging.getLogger(__name__)

# Baseline frontier pricing for savings estimation (USD per token, e.g. Claude 3.5 Sonnet)
FRONTIER_BASELINE_INPUT_COST = 0.00000300   # $3.00 / 1M
FRONTIER_BASELINE_OUTPUT_COST = 0.00001500  # $15.00 / 1M


@dataclass
class AuditLogEntry:
    """A single audited LLM call record."""

    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: Optional[str] = None
    prompt_preview: str = ""
    model_name: str = "gemini-2.5-flash"
    provider: str = "gemini"
    is_smart_routed: bool = False
    complexity_tier: Optional[str] = None
    intent: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    duration_ms: float = 0.0
    status: str = "success"
    tools_called: list[str] = field(default_factory=list)
    routing_reason: Optional[str] = None
    cascade_reason: Optional[str] = None


class TelemetryStore:
    """
    Persistent SQLite-backed audit log and telemetry analytics store.
    """

    def __init__(self, db_path: str = "data/telemetry.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create telemetry tables and performance indexes."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_audit_logs (
                    call_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    session_id TEXT,
                    prompt_preview TEXT,
                    model_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    is_smart_routed INTEGER DEFAULT 0,
                    complexity_tier TEXT,
                    intent TEXT,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    input_cost_usd REAL DEFAULT 0.0,
                    output_cost_usd REAL DEFAULT 0.0,
                    total_cost_usd REAL DEFAULT 0.0,
                    duration_ms REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'success',
                    tools_called TEXT DEFAULT '[]',
                    routing_reason TEXT,
                    cascade_reason TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON llm_audit_logs (timestamp DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_model ON llm_audit_logs (model_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_session ON llm_audit_logs (session_id)")

    def calculate_costs(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> tuple[float, float, float]:
        """
        Compute input, output, and total USD costs for a given model.
        Returns: (input_cost_usd, output_cost_usd, total_cost_usd)
        """
        cfg = DEFAULT_MODELS.get(model_name)
        cost_in = cfg.cost_per_input_token if cfg else 0.000000075
        cost_out = cfg.cost_per_output_token if cfg else 0.00000030

        in_usd = round(input_tokens * cost_in, 8)
        out_usd = round(output_tokens * cost_out, 8)
        tot_usd = round(in_usd + out_usd, 8)
        return in_usd, out_usd, tot_usd

    def record_call(self, entry: AuditLogEntry) -> str:
        """
        Record an LLM audit log entry into the store.
        """
        # Automatically calculate costs if not populated
        if entry.total_cost_usd == 0.0 and (entry.input_tokens > 0 or entry.output_tokens > 0):
            in_c, out_c, tot_c = self.calculate_costs(
                entry.model_name, entry.input_tokens, entry.output_tokens
            )
            entry.input_cost_usd = in_c
            entry.output_cost_usd = out_c
            entry.total_cost_usd = tot_c

        tools_json = json.dumps(entry.tools_called)

        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO llm_audit_logs (
                    call_id, timestamp, session_id, prompt_preview, model_name, provider,
                    is_smart_routed, complexity_tier, intent, input_tokens, output_tokens,
                    input_cost_usd, output_cost_usd, total_cost_usd, duration_ms, status,
                    tools_called, routing_reason, cascade_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.call_id,
                    entry.timestamp,
                    entry.session_id,
                    entry.prompt_preview[:250],
                    entry.model_name,
                    entry.provider,
                    1 if entry.is_smart_routed else 0,
                    entry.complexity_tier,
                    entry.intent,
                    entry.input_tokens,
                    entry.output_tokens,
                    entry.input_cost_usd,
                    entry.output_cost_usd,
                    entry.total_cost_usd,
                    entry.duration_ms,
                    entry.status,
                    tools_json,
                    entry.routing_reason,
                    entry.cascade_reason,
                ),
            )
        return entry.call_id

    def get_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        model: Optional[str] = None,
        smart_routed: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Retrieve paginated audit logs with optional filtering.
        """
        query_clauses = ["1=1"]
        params: list[Any] = []

        if model:
            query_clauses.append("model_name LIKE ?")
            params.append(f"%{model}%")

        if smart_routed is not None:
            query_clauses.append("is_smart_routed = ?")
            params.append(1 if smart_routed else 0)

        if search:
            query_clauses.append("(prompt_preview LIKE ? OR session_id LIKE ? OR call_id LIKE ?)")
            term = f"%{search}%"
            params.extend([term, term, term])

        where_sql = " AND ".join(query_clauses)

        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            count_cur = conn.execute(f"SELECT COUNT(*) FROM llm_audit_logs WHERE {where_sql}", params)
            total = count_cur.fetchone()[0]

            data_sql = f"""
                SELECT * FROM llm_audit_logs
                WHERE {where_sql}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """
            data_cur = conn.execute(data_sql, params + [limit, offset])
            rows = data_cur.fetchall()

            logs = []
            for r in rows:
                item = dict(r)
                item["is_smart_routed"] = bool(item.get("is_smart_routed"))
                try:
                    item["tools_called"] = json.loads(item.get("tools_called", "[]"))
                except Exception:
                    item["tools_called"] = []
                logs.append(item)

        return {
            "logs": logs,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_summary(self) -> dict[str, Any]:
        """
        Aggregate executive KPIs: spend, tokens, latency, smart-routing savings.
        """
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT
                    COUNT(*) as total_requests,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens,
                    SUM(total_cost_usd) as total_spend_usd,
                    AVG(duration_ms) as avg_duration_ms,
                    SUM(CASE WHEN is_smart_routed = 1 THEN 1 ELSE 0 END) as smart_routed_count
                FROM llm_audit_logs
                """
            )
            agg = dict(cur.fetchone())

            total_requests = agg.get("total_requests") or 0
            total_in = agg.get("total_input_tokens") or 0
            total_out = agg.get("total_output_tokens") or 0
            total_tokens = total_in + total_out
            total_spend = round(agg.get("total_spend_usd") or 0.0, 6)
            avg_duration = round(agg.get("avg_duration_ms") or 0.0, 1)
            smart_routed_cnt = agg.get("smart_routed_count") or 0

            smart_pct = round((smart_routed_cnt / total_requests * 100), 1) if total_requests > 0 else 0.0

            # Tier distribution
            tier_cur = conn.execute(
                """
                SELECT complexity_tier, COUNT(*) as cnt
                FROM llm_audit_logs
                WHERE complexity_tier IS NOT NULL
                GROUP BY complexity_tier
                """
            )
            tier_dist = {r["complexity_tier"]: r["cnt"] for r in tier_cur.fetchall()}

            # Model distribution
            model_cur = conn.execute(
                """
                SELECT model_name, COUNT(*) as cnt
                FROM llm_audit_logs
                GROUP BY model_name
                ORDER BY cnt DESC
                """
            )
            model_dist = {r["model_name"]: r["cnt"] for r in model_cur.fetchall()}

        # AI Economics: Baseline Frontier Spend vs Actual Spend
        baseline_cost = round(
            (total_in * FRONTIER_BASELINE_INPUT_COST) + (total_out * FRONTIER_BASELINE_OUTPUT_COST),
            6,
        )
        saved_usd = max(0.0, round(baseline_cost - total_spend, 6))
        savings_pct = round((saved_usd / baseline_cost * 100), 1) if baseline_cost > 0 else 0.0

        return {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_spend_usd": total_spend,
            "avg_duration_ms": avg_duration,
            "smart_routed_count": smart_routed_cnt,
            "smart_routed_percentage": smart_pct,
            "baseline_frontier_cost_usd": baseline_cost,
            "estimated_savings_usd": saved_usd,
            "savings_percentage": savings_pct,
            "tier_distribution": tier_dist,
            "model_distribution": model_dist,
        }

    def export_csv(self) -> str:
        """
        Export all audit logs formatted as standard CSV.
        """
        output = io.StringIO()
        fieldnames = [
            "call_id",
            "timestamp",
            "session_id",
            "model_name",
            "provider",
            "is_smart_routed",
            "complexity_tier",
            "intent",
            "input_tokens",
            "output_tokens",
            "total_cost_usd",
            "duration_ms",
            "status",
            "tools_called",
            "prompt_preview",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM llm_audit_logs ORDER BY timestamp DESC")
            for r in cur.fetchall():
                row = dict(r)
                writer.writerow(row)

        return output.getvalue()

    def export_excel_xml(self) -> str:
        """
        Export audit logs formatted as native XML Spreadsheet 2003 (.xls).
        Supported natively by Microsoft Excel, Apple Numbers, and LibreOffice with styling.
        """
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM llm_audit_logs ORDER BY timestamp DESC").fetchall()

        xml = [
            '<?xml version="1.0"?>',
            '<?mso-application progid="Excel.Sheet"?>',
            '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
            ' xmlns:o="urn:schemas-microsoft-com:office:office"',
            ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
            ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"',
            ' xmlns:html="http://www.w3.org/TR/REC-html40">',
            '<Styles>',
            '<Style ss:ID="Header"><Font ss:Bold="1" ss:Color="#FFFFFF"/><Interior ss:Color="#4F46E5" ss:Pattern="Solid"/></Style>',
            '<Style ss:ID="Currency"><NumberFormat ss:Format="$#,##0.00000"/></Style>',
            '</Styles>',
            '<Worksheet ss:Name="LLM Audit Logs">',
            '<Table>',
        ]

        headers = [
            "Call ID", "Timestamp", "Session ID", "Model", "Provider",
            "Smart Routed", "Tier", "Intent", "Input Tokens", "Output Tokens",
            "Total Cost ($)", "Duration (ms)", "Status", "Prompt Preview"
        ]

        xml.append('<Row ss:StyleID="Header">')
        for h in headers:
            xml.append(f'<Cell><Data ss:Type="String">{h}</Data></Cell>')
        xml.append('</Row>')

        for r in rows:
            clean_prompt = (r["prompt_preview"] or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            xml.append('<Row>')
            xml.append(f'<Cell><Data ss:Type="String">{r["call_id"]}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="String">{r["timestamp"]}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="String">{r["session_id"] or ""}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="String">{r["model_name"]}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="String">{r["provider"]}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="String">{"Yes" if r["is_smart_routed"] else "No"}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="String">{r["complexity_tier"] or "standard"}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="String">{r["intent"] or ""}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="Number">{r["input_tokens"] or 0}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="Number">{r["output_tokens"] or 0}</Data></Cell>')
            xml.append(f'<Cell ss:StyleID="Currency"><Data ss:Type="Number">{r["total_cost_usd"] or 0.0}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="Number">{r["duration_ms"] or 0.0}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="String">{r["status"] or "success"}</Data></Cell>')
            xml.append(f'<Cell><Data ss:Type="String">{clean_prompt}</Data></Cell>')
            xml.append('</Row>')

        xml.append('</Table>')
        xml.append('</Worksheet>')
        xml.append('</Workbook>')
        return "\n".join(xml)
