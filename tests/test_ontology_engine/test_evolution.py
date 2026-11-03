"""
Unit tests for Dynamic Ontology Evolution Agent (Phase 5).
Verifies CandidateConcept clustering, Palantir structural compliance,
graph impact analysis, unified diff generation, and hot-reload approval.
"""

import tempfile
from pathlib import Path
import pytest
import yaml

from ontology_engine.manager import OntologyManager
from ontology_engine.evolution import (
    CandidateConcept,
    ConceptCluster,
    EvolutionProposal,
    EvolutionService,
    EvolutionStore,
    GraphImpactAnalyzer,
    SchemaEvolutionGenerator,
    SemanticConceptClusterer,
)


@pytest.fixture
def temp_store(tmp_path):
    """Fixture providing a fresh EvolutionStore in a temporary directory."""
    db_file = tmp_path / "test_evolution.db"
    return EvolutionStore(db_path=db_file)


@pytest.fixture
def temp_ontology_manager(tmp_path):
    """Fixture providing an OntologyManager with a mock schema directory."""
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir(parents=True)
    
    healthtech_content = {
        "name": "healthtech",
        "version": "1.0.0",
        "description": "Mock healthtech schema for testing",
        "entities": [
            {
                "name": "Patient",
                "label": "Patient",
                "description": "Patient entity",
                "properties": [
                    {"name": "patient_id", "type": "string", "required": True, "unique": True},
                    {"name": "name", "type": "string", "required": True},
                ],
            },
            {
                "name": "Medication",
                "label": "Medication",
                "description": "Medication entity",
                "properties": [
                    {"name": "medication_id", "type": "string", "required": True, "unique": True},
                    {"name": "name", "type": "string", "required": True},
                ],
            },
        ],
        "relationships": [
            {
                "name": "PRESCRIBED",
                "source": "Patient",
                "target": "Medication",
                "description": "Patient prescribed medication",
                "properties": [],
            }
        ],
    }

    schema_file = schemas_dir / "healthtech.yaml"
    with open(schema_file, "w") as f:
        yaml.dump(healthtech_content, f)

    return OntologyManager(schemas_dir=schemas_dir)


def test_evolution_store_seeding_and_recording(temp_store):
    """Verify default seeding and candidate accumulation."""
    candidates = temp_store.list_candidates()
    assert len(candidates) >= 3
    
    ae = next((c for c in candidates if c.name == "AdverseEvent"), None)
    assert ae is not None
    assert ae.occurrences >= 4
    assert len(ae.context_snippets) > 0

    # Record new occurrence
    updated = temp_store.record_candidate(
        name="AdverseEvent",
        category="entity",
        context="New clinical trial note on AdverseEvent",
        source_doc="note_999.txt",
        properties=["reporter_role"],
    )
    assert updated.occurrences == ae.occurrences + 1
    assert "reporter_role" in updated.suggested_properties
    assert "note_999.txt" in updated.source_docs

    # Record brand-new concept
    new_cand = temp_store.record_candidate(
        name="GenomicBiomarker",
        category="entity",
        context="Detected EGFR mutation as key GenomicBiomarker",
        source_doc="genomics_01.vcf",
        properties=["gene_symbol", "variant_allele"],
    )
    assert new_cand.occurrences == 1
    assert new_cand.name == "GenomicBiomarker"

    # Test dismissal
    assert temp_store.dismiss_candidate("GenomicBiomarker") is True
    active = temp_store.list_candidates(status="NEW")
    assert not any(c.name == "GenomicBiomarker" for c in active)


def test_semantic_concept_clustering(temp_store):
    """Verify clustering groups synonym concepts into canonical clusters."""
    candidates = [
        CandidateConcept(name="AdverseEvent", category="entity", occurrences=4, context_snippets=["AE 1"], suggested_properties=["severity"]),
        CandidateConcept(name="SideEffect", category="entity", occurrences=2, context_snippets=["SE 1"], suggested_properties=["duration"]),
        CandidateConcept(name="ClinicalTrial", category="entity", occurrences=3, context_snippets=["CT 1"], suggested_properties=["phase"]),
    ]

    clusters = SemanticConceptClusterer.cluster_candidates(candidates)
    assert len(clusters) == 2

    ae_cluster = next((c for c in clusters if c.canonical_name == "AdverseEvent"), None)
    assert ae_cluster is not None
    assert ae_cluster.total_occurrences == 6
    assert set(ae_cluster.member_names) == {"AdverseEvent", "SideEffect"}
    assert "severity" in ae_cluster.suggested_properties
    assert "duration" in ae_cluster.suggested_properties

    ct_cluster = next((c for c in clusters if c.canonical_name == "ClinicalTrial"), None)
    assert ct_cluster is not None
    assert ct_cluster.total_occurrences == 3


def test_schema_evolution_generator_and_palantir_rules(temp_ontology_manager):
    """Verify schema generator creates Palantir-compliant proposal with diff."""
    schema = temp_ontology_manager.load("healthtech")
    schema_path = temp_ontology_manager.schemas_dir / "healthtech.yaml"
    existing_yaml = schema_path.read_text()

    cluster = ConceptCluster(
        cluster_id="cluster_ae",
        canonical_name="AdverseEvent",
        category="entity",
        member_names=["AdverseEvent", "SideEffect"],
        total_occurrences=6,
        context_snippets=["Patient developed severe rash"],
        suggested_properties=["severity", "onset_date"],
        source_docs=["doc1.md"],
    )

    proposal = SchemaEvolutionGenerator.generate_proposal(
        schema=schema,
        cluster=cluster,
        existing_yaml=existing_yaml,
    )

    assert proposal.proposal_id.startswith("prop_")
    assert proposal.status == "PENDING"
    assert proposal.concept_name == "AdverseEvent"
    assert proposal.proposed_entity is not None
    assert proposal.proposed_entity["name"] == "AdverseEvent"

    # Check mandatory provenance properties
    prop_names = [p["name"] for p in proposal.proposed_entity["properties"]]
    assert "source_id" in prop_names
    assert "created_at" in prop_names
    assert "confidence_score" in prop_names
    assert "event_id" in prop_names

    # Check proposed relationships
    assert len(proposal.proposed_relationships) >= 1
    for rel in proposal.proposed_relationships:
        assert rel["name"].isupper()
        assert "_" in rel["name"] or rel["name"].isalpha()

    # Check diff
    assert len(proposal.diff) > 0
    assert "AdverseEvent" in proposal.diff
    assert "1.1.0" in proposal.diff


def test_graph_impact_analyzer(temp_ontology_manager):
    """Verify graph impact metrics and Palantir governance compliance scoring."""
    schema = temp_ontology_manager.load("healthtech")

    proposed_entity = {
        "name": "AdverseEvent",
        "label": "AdverseEvent",
        "properties": [
            {"name": "event_id", "type": "string"},
            {"name": "source_id", "type": "string"},
            {"name": "created_at", "type": "datetime"},
            {"name": "confidence_score", "type": "float"},
        ],
    }
    proposed_relationships = [
        {"name": "EXPERIENCED_ADVERSE_EVENT", "source": "Patient", "target": "AdverseEvent"}
    ]

    impact = GraphImpactAnalyzer.analyze_impact(
        schema=schema,
        proposed_entity=proposed_entity,
        proposed_relationships=proposed_relationships,
        candidate_occurrences=5,
    )

    assert impact["current_entities_count"] == 2
    assert impact["proposed_entities_count"] == 3
    assert impact["proposed_relationships_count"] == 2
    assert impact["palantir_governance_score"] == 100
    assert impact["fanout_risk"] == "LOW"
    assert "MINIMAL" in impact["query_performance_impact"]


def test_evolution_service_approval_and_hot_reload(temp_store, temp_ontology_manager):
    """Verify full end-to-end lifecycle: generation -> approval -> backup -> hot-reload."""
    service = EvolutionService(store=temp_store, ontology_manager=temp_ontology_manager)

    # 1. Generate proposal
    proposal = service.generate_proposal_for_cluster(
        schema_name="healthtech",
        cluster_name="AdverseEvent",
    )
    assert proposal.status == "PENDING"

    # 2. Approve and apply proposal
    res = service.approve_and_apply_proposal(proposal.proposal_id, review_notes="Approved for clinical safety")
    assert res["status"] == "APPROVED"
    assert res["schema_name"] == "healthtech"
    assert res["entities_count"] == 3

    # Verify backup exists
    backup_file = temp_ontology_manager.schemas_dir / "healthtech.yaml.bak"
    assert backup_file.exists()

    # Verify hot-reload took effect in ontology_manager
    reloaded = temp_ontology_manager.load("healthtech")
    assert "AdverseEvent" in reloaded.get_entity_names()

    # 3. Verify proposal status updated in store
    saved_prop = temp_store.get_proposal(proposal.proposal_id)
    assert saved_prop.status == "APPROVED"
    assert saved_prop.review_notes == "Approved for clinical safety"
    assert saved_prop.reviewed_at is not None


def test_evolution_service_rejection(temp_store, temp_ontology_manager):
    """Verify proposal rejection flow."""
    service = EvolutionService(store=temp_store, ontology_manager=temp_ontology_manager)

    proposal = service.generate_proposal_for_cluster(
        schema_name="healthtech",
        cluster_name="ClinicalTrial",
    )

    res = service.reject_proposal(proposal.proposal_id, reason="Not applicable for this deployment")
    assert res["status"] == "REJECTED"

    saved = temp_store.get_proposal(proposal.proposal_id)
    assert saved.status == "REJECTED"
    assert "Not applicable" in saved.review_notes
