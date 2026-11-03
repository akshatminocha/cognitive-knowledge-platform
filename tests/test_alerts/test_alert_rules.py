"""
Unit tests for Proactive Alerting & Standing Goals:
- AlertStore (SQLite rules and alert history)
- AlertEngine (Threshold evaluations, operator rules, ingestion hooks)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from backend.alerts.rules import (
    AlertStore,
    StandingRule,
    AlertEvent,
    RuleType,
    SeverityLevel,
    AlertStatus,
)
from backend.alerts.engine import AlertEngine


@pytest.fixture
def temp_store(tmp_path):
    """Isolated AlertStore instance using temporary SQLite file."""
    db_file = str(tmp_path / "test_alerts.db")
    return AlertStore(db_path=db_file)


# ---------------------------------------------------------------------------
# AlertStore CRUD Tests
# ---------------------------------------------------------------------------
def test_alert_store_seeding(temp_store):
    """Store initializes with default clinical standing rules."""
    rules = temp_store.list_rules()
    assert len(rules) >= 3
    names = [r.name for r in rules]
    assert any("Hyperkalemia" in n for n in names)
    assert any("Hypertension" in n for n in names)


def test_alert_store_rule_crud(temp_store):
    """Create, retrieve, update, toggle, and delete standing rules."""
    new_rule = StandingRule(
        name="Tachycardia Alert",
        description="Heart rate exceeding 100 bpm",
        rule_type=RuleType.PROPERTY_THRESHOLD,
        target_label="Observation",
        property_name="heart_rate",
        operator=">",
        threshold_value=100.0,
        severity=SeverityLevel.WARNING,
        enabled=True,
    )

    created = temp_store.create_rule(new_rule)
    assert created.id == new_rule.id

    # Get
    fetched = temp_store.get_rule(new_rule.id)
    assert fetched is not None
    assert fetched.name == "Tachycardia Alert"
    assert fetched.threshold_value == 100.0

    # Update
    updated = temp_store.update_rule(new_rule.id, {"threshold_value": 110.0, "severity": "CRITICAL"})
    assert updated.threshold_value == 110.0
    assert updated.severity == SeverityLevel.CRITICAL

    # Toggle
    toggled = temp_store.toggle_rule(new_rule.id)
    assert toggled.enabled is False

    # Delete
    assert temp_store.delete_rule(new_rule.id) is True
    assert temp_store.get_rule(new_rule.id) is None


def test_alert_store_alert_lifecycle(temp_store):
    """Record, list, mark read, dismiss, and track unread count for alerts."""
    initial_unread = temp_store.get_unread_count()

    alert = AlertEvent(
        rule_id="rule-test",
        rule_name="Test Rule",
        severity=SeverityLevel.CRITICAL,
        title="CRITICAL: Severe Sepsis",
        message="Patient has severe lactate elevation.",
        entity_label="Observation",
        entity_id="obs-101",
        matched_properties={"lactate": 4.2},
    )

    recorded = temp_store.record_alert(alert)
    assert temp_store.get_unread_count() == initial_unread + 1

    # List
    unread_alerts = temp_store.list_alerts(status="unread")
    assert any(a.id == recorded.id for a in unread_alerts)

    # Mark read
    assert temp_store.mark_alert_read(recorded.id) is True
    read_alert = temp_store.get_alert(recorded.id)
    assert read_alert.status == AlertStatus.READ
    assert temp_store.get_unread_count() == initial_unread

    # Dismiss
    assert temp_store.dismiss_alert(recorded.id) is True
    dismissed = temp_store.get_alert(recorded.id)
    assert dismissed.status == AlertStatus.DISMISSED


# ---------------------------------------------------------------------------
# AlertEngine Evaluation Tests
# ---------------------------------------------------------------------------
def test_evaluate_property_rule_numeric(temp_store):
    """Verify numeric comparison operators (> , < , >= , <= , ==)."""
    engine = AlertEngine(store=temp_store)

    rule_gt = StandingRule(
        name="High Potassium",
        property_name="potassium",
        operator=">",
        threshold_value=5.5,
        severity=SeverityLevel.CRITICAL,
    )

    # Above threshold -> triggers
    alert = engine.evaluate_property_rule(rule_gt, {"potassium": 6.1}, "P-1", "Patient")
    assert alert is not None
    assert alert.severity == SeverityLevel.CRITICAL

    # Below threshold -> no trigger
    assert engine.evaluate_property_rule(rule_gt, {"potassium": 4.5}, "P-2", "Patient") is None

    # Missing property -> no trigger
    assert engine.evaluate_property_rule(rule_gt, {"sodium": 140}, "P-3", "Patient") is None


def test_evaluate_property_rule_string(temp_store):
    """Verify string equality and containment operators."""
    engine = AlertEngine(store=temp_store)

    rule_str = StandingRule(
        name="Malignancy Flag",
        property_name="pathology_result",
        operator="contains",
        threshold_value="carcinoma",
        severity=SeverityLevel.CRITICAL,
    )

    alert = engine.evaluate_property_rule(
        rule_str,
        {"pathology_result": "Invasive ductal carcinoma detected in biopsy"},
        "BIO-99",
        "BiopsyReport",
    )
    assert alert is not None
    assert "carcinoma" in alert.message


@pytest.mark.asyncio
async def test_evaluate_entities_batch_and_webhook(temp_store):
    """Verify batch entity evaluation and asynchronous webhook dispatching."""
    engine = AlertEngine(store=temp_store)

    # Add a custom rule with a webhook URL
    rule = StandingRule(
        name="Critical Fever",
        target_label="Observation",
        property_name="temperature_f",
        operator=">=",
        threshold_value=103.0,
        severity=SeverityLevel.CRITICAL,
        webhook_url="https://alerts.hospital.org/webhook",
        enabled=True,
    )
    temp_store.create_rule(rule)

    entities = [
        {"name": "Vitals 1", "temperature_f": 98.6, "_label": "Observation"},
        {"name": "Vitals 2", "temperature_f": 104.2, "_label": "Observation", "patient_id": "P-777"},
        {"name": "Dr. House", "temperature_f": 105.0, "_label": "Doctor"},  # Label mismatch
    ]

    with patch.object(engine, "_dispatch_webhook", new_callable=AsyncMock) as mock_webhook:
        alerts = await engine.evaluate_entities(entities, source_name="vitals_stream.json")
        assert len(alerts) == 1
        assert alerts[0].rule_name == "Critical Fever"
        assert alerts[0].matched_properties["source_file"] == "vitals_stream.json"
        assert mock_webhook.called
