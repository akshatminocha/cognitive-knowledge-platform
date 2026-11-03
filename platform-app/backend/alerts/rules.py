"""
Standing Goals & Proactive Alerting Rule Registry.

Defines:
- StandingRule: Configurable event rules (property thresholds or Cypher graph patterns)
- AlertEvent: Triggered alerts with severity levels and entity context
- AlertStore: Persistent SQLite store for active rules and alert history
"""

from __future__ import annotations

import datetime
import enum
import json
import logging
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RuleType(str, enum.Enum):
    PROPERTY_THRESHOLD = "property_threshold"
    CYPHER = "cypher"


class SeverityLevel(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertStatus(str, enum.Enum):
    UNREAD = "unread"
    READ = "read"
    DISMISSED = "dismissed"


@dataclass
class StandingRule:
    """Definition of a standing rule monitored by the alerting agent."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    rule_type: RuleType = RuleType.PROPERTY_THRESHOLD
    target_label: str = "Observation"  # Target entity label in knowledge graph
    property_name: Optional[str] = "value"
    operator: str = ">"  # >, <, >=, <=, ==, !=, contains, in
    threshold_value: Any = 5.5
    cypher_query: Optional[str] = None
    severity: SeverityLevel = SeverityLevel.WARNING
    webhook_url: Optional[str] = None
    enabled: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rule_type"] = self.rule_type.value if isinstance(self.rule_type, RuleType) else self.rule_type
        data["severity"] = self.severity.value if isinstance(self.severity, SeverityLevel) else self.severity
        return data


@dataclass
class AlertEvent:
    """Record of a triggered alert event."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str = ""
    rule_name: str = ""
    severity: SeverityLevel = SeverityLevel.WARNING
    title: str = ""
    message: str = ""
    entity_label: str = ""
    entity_id: str = ""
    matched_properties: dict[str, Any] = field(default_factory=dict)
    status: AlertStatus = AlertStatus.UNREAD
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value if isinstance(self.severity, SeverityLevel) else self.severity
        data["status"] = self.status.value if isinstance(self.status, AlertStatus) else self.status
        return data


# ---------------------------------------------------------------------------
# SQLite Alert & Rule Store
# ---------------------------------------------------------------------------
class AlertStore:
    """SQLite-backed persistent store for standing rules and alert history."""

    def __init__(self, db_path: str = "data/alerts.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._seed_default_rules()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS standing_rules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    rule_type TEXT NOT NULL,
                    target_label TEXT NOT NULL,
                    property_name TEXT,
                    operator TEXT NOT NULL,
                    threshold_value TEXT,
                    cypher_query TEXT,
                    severity TEXT NOT NULL,
                    webhook_url TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_history (
                    id TEXT PRIMARY KEY,
                    rule_id TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    entity_label TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    matched_properties TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unread',
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _seed_default_rules(self) -> None:
        """Seed initial healthcare & clinical standing rules if database is empty."""
        rules = self.list_rules()
        if rules:
            return

        default_rules = [
            StandingRule(
                id="rule-hyperkalemia",
                name="Critical Hyperkalemia Warning",
                description="Flags patients with serum potassium levels exceeding 5.5 mEq/L, indicating acute risk of cardiac arrhythmias.",
                rule_type=RuleType.PROPERTY_THRESHOLD,
                target_label="Observation",
                property_name="value",
                operator=">",
                threshold_value=5.5,
                severity=SeverityLevel.CRITICAL,
                enabled=True,
            ),
            StandingRule(
                id="rule-stage2-hypertension",
                name="Stage 2 Hypertension Alert",
                description="Flags blood pressure readings where systolic pressure reaches or exceeds 140 mmHg.",
                rule_type=RuleType.PROPERTY_THRESHOLD,
                target_label="Observation",
                property_name="systolic",
                operator=">=",
                threshold_value=140.0,
                severity=SeverityLevel.WARNING,
                enabled=True,
            ),
            StandingRule(
                id="rule-lisinopril-contraindication",
                name="Lisinopril + Angioedema Safety Flag",
                description="Flags any Patient prescribed Lisinopril who has a documented history or diagnosis of Angioedema.",
                rule_type=RuleType.CYPHER,
                target_label="Patient",
                cypher_query="MATCH (p:Patient)-[:PRESCRIBED_MEDICATION]->(m:Medication) WHERE m.name CONTAINS 'Lisinopril' MATCH (p)-[:HAS_DIAGNOSIS]->(d:Diagnosis) WHERE d.name CONTAINS 'Angioedema' RETURN p.name, m.name, d.name",
                severity=SeverityLevel.CRITICAL,
                enabled=True,
            ),
            StandingRule(
                id="rule-high-dose-metformin",
                name="High-Dose Metformin Flag",
                description="Flags metformin prescriptions with daily dosage exceeding 2000mg for renal function review.",
                rule_type=RuleType.PROPERTY_THRESHOLD,
                target_label="Medication",
                property_name="dosage_mg",
                operator=">",
                threshold_value=2000.0,
                severity=SeverityLevel.INFO,
                enabled=True,
            ),
        ]

        for rule in default_rules:
            self.create_rule(rule)
        logger.info("Seeded %d default standing rules", len(default_rules))

    # ---- Rule CRUD --------------------------------------------------------

    def create_rule(self, rule: StandingRule) -> StandingRule:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO standing_rules (
                    id, name, description, rule_type, target_label, property_name,
                    operator, threshold_value, cypher_query, severity, webhook_url,
                    enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.id,
                    rule.name,
                    rule.description,
                    rule.rule_type.value if isinstance(rule.rule_type, RuleType) else str(rule.rule_type),
                    rule.target_label,
                    rule.property_name,
                    rule.operator,
                    json.dumps(rule.threshold_value),
                    rule.cypher_query,
                    rule.severity.value if isinstance(rule.severity, SeverityLevel) else str(rule.severity),
                    rule.webhook_url,
                    1 if rule.enabled else 0,
                    rule.created_at,
                ),
            )
            conn.commit()
        return rule

    def get_rule(self, rule_id: str) -> Optional[StandingRule]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM standing_rules WHERE id = ?", (rule_id,)).fetchone()
            if not row:
                return None
            return self._row_to_rule(row)

    def list_rules(self, enabled_only: bool = False) -> list[StandingRule]:
        with self._get_connection() as conn:
            query = "SELECT * FROM standing_rules"
            params = ()
            if enabled_only:
                query += " WHERE enabled = 1"
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_rule(r) for r in rows]

    def update_rule(self, rule_id: str, updates: dict[str, Any]) -> Optional[StandingRule]:
        rule = self.get_rule(rule_id)
        if not rule:
            return None

        for k, v in updates.items():
            if hasattr(rule, k):
                if k == "rule_type" and isinstance(v, str):
                    setattr(rule, k, RuleType(v))
                elif k == "severity" and isinstance(v, str):
                    setattr(rule, k, SeverityLevel(v))
                else:
                    setattr(rule, k, v)

        return self.create_rule(rule)

    def delete_rule(self, rule_id: str) -> bool:
        with self._get_connection() as conn:
            res = conn.execute("DELETE FROM standing_rules WHERE id = ?", (rule_id,))
            conn.commit()
            return res.rowcount > 0

    def toggle_rule(self, rule_id: str) -> Optional[StandingRule]:
        rule = self.get_rule(rule_id)
        if not rule:
            return None
        rule.enabled = not rule.enabled
        return self.create_rule(rule)

    def _row_to_rule(self, row: sqlite3.Row) -> StandingRule:
        try:
            th_val = json.loads(row["threshold_value"]) if row["threshold_value"] is not None else None
        except Exception:
            th_val = row["threshold_value"]

        return StandingRule(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            rule_type=RuleType(row["rule_type"]),
            target_label=row["target_label"],
            property_name=row["property_name"],
            operator=row["operator"],
            threshold_value=th_val,
            cypher_query=row["cypher_query"],
            severity=SeverityLevel(row["severity"]),
            webhook_url=row["webhook_url"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
        )

    # ---- Alert History CRUD -----------------------------------------------

    def record_alert(self, alert: AlertEvent) -> AlertEvent:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO alert_history (
                    id, rule_id, rule_name, severity, title, message,
                    entity_label, entity_id, matched_properties, status, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.id,
                    alert.rule_id,
                    alert.rule_name,
                    alert.severity.value if isinstance(alert.severity, SeverityLevel) else str(alert.severity),
                    alert.title,
                    alert.message,
                    alert.entity_label,
                    alert.entity_id,
                    json.dumps(alert.matched_properties),
                    alert.status.value if isinstance(alert.status, AlertStatus) else str(alert.status),
                    alert.timestamp,
                ),
            )
            conn.commit()
        return alert

    def get_alert(self, alert_id: str) -> Optional[AlertEvent]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM alert_history WHERE id = ?", (alert_id,)).fetchone()
            if not row:
                return None
            return self._row_to_alert(row)

    def list_alerts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> list[AlertEvent]:
        with self._get_connection() as conn:
            conditions = []
            params = []
            if status:
                conditions.append("status = ?")
                params.append(status)
            if severity:
                conditions.append("severity = ?")
                params.append(severity)

            where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"SELECT * FROM alert_history{where_clause} ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_alert(r) for r in rows]

    def mark_alert_read(self, alert_id: str) -> bool:
        with self._get_connection() as conn:
            res = conn.execute(
                "UPDATE alert_history SET status = 'read' WHERE id = ?",
                (alert_id,),
            )
            conn.commit()
            return res.rowcount > 0

    def dismiss_alert(self, alert_id: str) -> bool:
        with self._get_connection() as conn:
            res = conn.execute(
                "UPDATE alert_history SET status = 'dismissed' WHERE id = ?",
                (alert_id,),
            )
            conn.commit()
            return res.rowcount > 0

    def get_unread_count(self) -> int:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM alert_history WHERE status = 'unread'"
            ).fetchone()
            return int(row["cnt"]) if row else 0

    def _row_to_alert(self, row: sqlite3.Row) -> AlertEvent:
        try:
            matched_props = json.loads(row["matched_properties"]) if row["matched_properties"] else {}
        except Exception:
            matched_props = {}

        return AlertEvent(
            id=row["id"],
            rule_id=row["rule_id"],
            rule_name=row["rule_name"],
            severity=SeverityLevel(row["severity"]),
            title=row["title"],
            message=row["message"],
            entity_label=row["entity_label"],
            entity_id=row["entity_id"],
            matched_properties=matched_props,
            status=AlertStatus(row["status"]),
            timestamp=row["timestamp"],
        )
