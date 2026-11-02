"""
Unit tests for CKP KnowledgeReconciler and Self-Healing Knowledge Agent.
Validates multi-metric entity matching, atomic graph merger, SQLite audit trail, and rollbacks.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent_harness.reconciler import (
    KnowledgeReconciler,
    DuplicateCandidate,
    MergeAuditRecord,
    ReconciliationAuditStore,
    levenshtein_distance,
    normalized_levenshtein_similarity,
    jaro_winkler_similarity,
    cosine_similarity,
)


# ---------------------------------------------------------------------------
# String Distance & Similarity Tests
# ---------------------------------------------------------------------------
def test_levenshtein_similarity():
    """Verify Levenshtein distance and normalized similarity."""
    assert levenshtein_distance("kitten", "sitting") == 3
    assert normalized_levenshtein_similarity("kitten", "kitten") == 1.0
    assert normalized_levenshtein_similarity("Lisinopril", "Lisinopril 10mg") > 0.6
    assert normalized_levenshtein_similarity("", "abc") == 0.0


def test_jaro_winkler_similarity():
    """Verify Jaro-Winkler prefix-weighted similarity."""
    assert jaro_winkler_similarity("martha", "marhta") > 0.9
    assert jaro_winkler_similarity("dwayne", "duane") > 0.8
    assert jaro_winkler_similarity("apple", "orange") < 0.6
    assert jaro_winkler_similarity("same", "same") == 1.0


def test_cosine_similarity():
    """Verify vector cosine similarity calculation."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    assert cosine_similarity(v1, v2) == 1.0
    assert cosine_similarity(v1, v3) == 0.0
    assert cosine_similarity([], []) == 0.0


# ---------------------------------------------------------------------------
# Multi-Metric Entity Matching Tests
# ---------------------------------------------------------------------------
def test_calculate_entity_similarity_exact_normalized():
    """Normalized exact match returns 1.0 even with punctuation/casing."""
    reconciler = KnowledgeReconciler()
    node_a = {"name": "Dr. John A. Smith, M.D."}
    node_b = {"name": "dr john a smith md"}
    score, reasons = reconciler.calculate_entity_similarity(node_a, node_b)
    assert score == 1.0
    assert any("Exact normalized" in r for r in reasons)


def test_calculate_entity_similarity_unique_id():
    """Matching unique medical or administrative identifier returns 1.0."""
    reconciler = KnowledgeReconciler()
    node_a = {"name": "Jane Doe", "mrn": "MRN-90210", "specialty": "Cardiology"}
    node_b = {"name": "J. Doe", "mrn": "MRN-90210", "specialty": "Cardiology"}
    score, reasons = reconciler.calculate_entity_similarity(node_a, node_b)
    assert score == 1.0
    assert any("MRN-90210" in r for r in reasons)


def test_calculate_entity_similarity_fuzzy_and_properties():
    """Fuzzy name match + overlapping properties yields high score."""
    reconciler = KnowledgeReconciler()
    node_a = {"name": "Metformin Hydrochloride", "dosage": "500mg", "frequency": "Daily"}
    node_b = {"name": "Metformin HCL", "dosage": "500mg", "frequency": "Daily"}
    score, reasons = reconciler.calculate_entity_similarity(node_a, node_b)
    assert score >= 0.75
    assert len(reasons) >= 1


def test_calculate_entity_similarity_dissimilar():
    """Completely unrelated entities yield low score."""
    reconciler = KnowledgeReconciler()
    node_a = {"name": "Lisinopril", "category": "ACE Inhibitor"}
    node_b = {"name": "Amlodipine", "category": "Calcium Channel Blocker"}
    score, _ = reconciler.calculate_entity_similarity(node_a, node_b)
    assert score < 0.6


# ---------------------------------------------------------------------------
# Scan Duplicates Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_duplicates_in_memory():
    """Scan detects duplicate pairs in node list and selects canonical node."""
    reconciler = KnowledgeReconciler(default_threshold=0.8)
    nodes = [
        {"id": "node-1", "name": "Dr. Sarah Connor", "specialty": "Neurology", "_label": "Doctor"},
        {"id": "node-2", "name": "Dr. Sarah Connor, MD", "specialty": "Neurology", "hospital": "General", "_label": "Doctor"},
        {"id": "node-3", "name": "Dr. Bruce Banner", "specialty": "Genetics", "_label": "Doctor"},
    ]

    candidates = await reconciler.scan_duplicates(nodes=nodes)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.entity_label == "Doctor"
    assert cand.canonical_id == "node-2"  # More properties
    assert cand.source_id == "node-1"
    assert cand.similarity_score >= 0.8


# ---------------------------------------------------------------------------
# SQLite Audit Store Tests
# ---------------------------------------------------------------------------
def test_reconciliation_audit_store(tmp_path):
    """Test SQLite audit trail recording, querying, and reverting."""
    db_file = str(tmp_path / "test_audit.db")
    store = ReconciliationAuditStore(db_path=db_file)

    record = MergeAuditRecord(
        entity_label="Medication",
        canonical_id="med-1",
        duplicate_id="med-2",
        canonical_name="Lisinopril",
        duplicate_name="Lisinopril 10mg",
        similarity_score=0.92,
        match_reasons=["High name similarity"],
        original_duplicate_props={"name": "Lisinopril 10mg", "strength": "10mg"},
        original_relationships=[{"rel_type": "PRESCRIBED_FOR", "direction": "out"}],
        qdrant_points_updated=3,
    )

    store.record_merge(record)

    # Fetch by ID
    fetched = store.get_merge(record.merge_id)
    assert fetched is not None
    assert fetched.canonical_name == "Lisinopril"
    assert fetched.duplicate_name == "Lisinopril 10mg"
    assert fetched.status == "merged"
    assert fetched.qdrant_points_updated == 3

    # List
    history = store.list_merges(limit=10)
    assert len(history) == 1
    assert history[0].merge_id == record.merge_id

    # Mark reverted
    assert store.mark_reverted(record.merge_id) is True
    reverted = store.get_merge(record.merge_id)
    assert reverted.status == "reverted"


# ---------------------------------------------------------------------------
# Execution & Rollback Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_merge_and_rollback(tmp_path):
    """Verify merge execution with mocked graph/vector backends and subsequent rollback."""
    db_file = str(tmp_path / "test_audit.db")
    store = ReconciliationAuditStore(db_path=db_file)

    # Mock Neo4j driver
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    # Mock Qdrant client
    mock_qdrant = AsyncMock()
    mock_point = MagicMock()
    mock_point.id = "point-1"
    mock_point.payload = {"entities": ["Aspirin 81mg", "Patient-1"]}
    mock_qdrant.scroll = AsyncMock(return_value=([mock_point], None))
    mock_qdrant.set_payload = AsyncMock()

    reconciler = KnowledgeReconciler(
        neo4j_driver=mock_driver,
        qdrant_client=mock_qdrant,
        audit_store=store,
    )

    candidate = DuplicateCandidate(
        source_id="med-dup",
        canonical_id="med-canon",
        entity_label="Medication",
        source_name="Aspirin 81mg",
        canonical_name="Aspirin Low Dose",
        similarity_score=0.91,
        match_reasons=["Name similarity"],
        source_props={"name": "Aspirin 81mg", "form": "Tablet"},
        canonical_props={"name": "Aspirin Low Dose", "category": "Analgesic"},
    )

    # 1. Execute Merge
    audit = await reconciler.execute_merge(candidate, dry_run=False)
    assert audit.status == "merged"
    assert audit.canonical_id == "med-canon"
    assert mock_qdrant.set_payload.called

    # Check audit persisted
    persisted = store.get_merge(audit.merge_id)
    assert persisted is not None

    # 2. Rollback Merge
    rollback_success = await reconciler.rollback_merge(audit.merge_id)
    assert rollback_success is True
    assert mock_session.run.called  # create node was invoked

    # Status should now be reverted
    assert store.get_merge(audit.merge_id).status == "reverted"
