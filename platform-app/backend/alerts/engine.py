"""
Alert Engine & Ingestion Event Evaluator.

Evaluates newly extracted entities, graph mutations, and standing Cypher queries
against active StandingRules, dispatching real-time alerts and webhooks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from backend.alerts.rules import (
    AlertEvent,
    AlertStatus,
    AlertStore,
    RuleType,
    SeverityLevel,
    StandingRule,
)

logger = logging.getLogger(__name__)


class AlertEngine:
    """
    Evaluator engine for Standing Goals & Proactive Alerts.
    """

    def __init__(
        self,
        store: Optional[AlertStore] = None,
        neo4j_driver: Optional[Any] = None,
    ):
        self.store = store or AlertStore()
        self.neo4j_driver = neo4j_driver

    # ---- Entity Evaluation (Property Thresholds) --------------------------

    def evaluate_property_rule(
        self,
        rule: StandingRule,
        entity_props: dict[str, Any],
        entity_id: str,
        entity_label: str,
    ) -> Optional[AlertEvent]:
        """
        Evaluate a single property-threshold rule against an entity's properties.
        Returns an AlertEvent if matched, else None.
        """
        if not rule.enabled or rule.rule_type != RuleType.PROPERTY_THRESHOLD:
            return None

        prop_name = rule.property_name
        if not prop_name or prop_name not in entity_props:
            return None

        val = entity_props[prop_name]
        threshold = rule.threshold_value
        op = rule.operator.strip()

        matched = False
        try:
            # Numeric conversion if threshold is float/int
            if isinstance(threshold, (int, float)):
                numeric_val = float(val)
                numeric_thresh = float(threshold)
                if op == ">":
                    matched = numeric_val > numeric_thresh
                elif op == ">=":
                    matched = numeric_val >= numeric_thresh
                elif op == "<":
                    matched = numeric_val < numeric_thresh
                elif op == "<=":
                    matched = numeric_val <= numeric_thresh
                elif op == "==":
                    matched = numeric_val == numeric_thresh
                elif op == "!=":
                    matched = numeric_val != numeric_thresh
            else:
                # String or general comparison
                str_val = str(val).lower().strip()
                str_thresh = str(threshold).lower().strip()
                if op == "==":
                    matched = str_val == str_thresh
                elif op == "!=":
                    matched = str_val != str_thresh
                elif op == "contains":
                    matched = str_thresh in str_val
                elif op == "in":
                    matched = str_val in str_thresh
        except (ValueError, TypeError) as e:
            logger.debug("Evaluation error for rule '%s' on value '%s': %s", rule.name, val, e)
            return None

        if not matched:
            return None

        title = f"{rule.severity.value}: {rule.name}"
        message = (
            f"Standing rule '{rule.name}' triggered for {entity_label} ({entity_id}). "
            f"Property '{prop_name}' ({val}) matched condition {op} {threshold}."
        )

        alert = AlertEvent(
            rule_id=rule.id,
            rule_name=rule.name,
            severity=rule.severity,
            title=title,
            message=message,
            entity_label=entity_label,
            entity_id=entity_id,
            matched_properties={prop_name: val, "threshold": threshold, "operator": op},
        )
        return alert

    async def evaluate_entities(
        self,
        entities: list[dict[str, Any]],
        default_label: str = "Entity",
        source_name: str = "",
    ) -> list[AlertEvent]:
        """
        Evaluate a batch of extracted entities (e.g. from file ingestion or crawler).
        High-throughput, in-memory filtered check.
        """
        rules = self.store.list_rules(enabled_only=True)
        threshold_rules = [r for r in rules if r.rule_type == RuleType.PROPERTY_THRESHOLD]

        triggered_alerts: list[AlertEvent] = []

        for entity in entities:
            lbl = entity.get("_label") or entity.get("entity_type") or default_label
            eid = str(entity.get("id") or entity.get("name") or "unknown")

            for rule in threshold_rules:
                # Target label match (case-insensitive) or wildcard '*'
                if rule.target_label != "*" and rule.target_label.lower() != lbl.lower():
                    continue

                alert = self.evaluate_property_rule(rule, entity, eid, lbl)
                if alert:
                    if source_name:
                        alert.matched_properties["source_file"] = source_name
                    # Save to persistent store
                    saved_alert = self.store.record_alert(alert)
                    triggered_alerts.append(saved_alert)

                    # Trigger webhook if specified
                    if rule.webhook_url:
                        asyncio.create_task(self._dispatch_webhook(saved_alert, rule.webhook_url))

        if triggered_alerts:
            logger.warning(
                "Triggered %d proactive standing alerts during ingestion (%s)",
                len(triggered_alerts), source_name or "batch",
            )
        return triggered_alerts

    # ---- Graph Cypher Evaluation ------------------------------------------

    async def evaluate_cypher_rules(self) -> list[AlertEvent]:
        """
        Evaluate standing Cypher graph pattern rules against Neo4j.
        """
        if not self.neo4j_driver:
            return []

        rules = self.store.list_rules(enabled_only=True)
        cypher_rules = [r for r in rules if r.rule_type == RuleType.CYPHER and r.cypher_query]

        triggered: list[AlertEvent] = []

        try:
            async with self.neo4j_driver.session() as session:
                for rule in cypher_rules:
                    try:
                        res = await session.run(rule.cypher_query)
                        records = await res.data()
                        if records:
                            for rec in records:
                                title = f"{rule.severity.value}: {rule.name}"
                                alert = AlertEvent(
                                    rule_id=rule.id,
                                    rule_name=rule.name,
                                    severity=rule.severity,
                                    title=title,
                                    message=f"Graph pattern matched for rule '{rule.name}'. Findings: {rec}",
                                    entity_label=rule.target_label,
                                    entity_id=str(rec.get("name") or rec.get("id") or "graph-match"),
                                    matched_properties=rec,
                                )
                                saved = self.store.record_alert(alert)
                                triggered.append(saved)

                                if rule.webhook_url:
                                    asyncio.create_task(self._dispatch_webhook(saved, rule.webhook_url))
                    except Exception as err:
                        logger.error("Error executing Cypher rule '%s': %s", rule.name, err)
        except Exception as e:
            logger.warning("Neo4j session unavailable for Cypher standing rules: %s", e)

        return triggered

    # ---- Webhook Dispatcher -----------------------------------------------

    async def _dispatch_webhook(self, alert: AlertEvent, webhook_url: str) -> None:
        """Asynchronously dispatch real-time webhook payload."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(webhook_url, json=alert.to_dict())
                if res.status_code >= 400:
                    logger.warning("Webhook dispatch to %s returned %d", webhook_url, res.status_code)
                else:
                    logger.info("Webhook dispatch succeeded for alert %s", alert.id[:8])
        except Exception as exc:
            logger.warning("Webhook dispatch failed to %s: %s", webhook_url, exc)
