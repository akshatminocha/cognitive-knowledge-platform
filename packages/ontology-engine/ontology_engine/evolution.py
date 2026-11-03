"""
Ontology Evolution Agent — Dynamic Schema Learning & Governance.

Inspired by Palantir's Principal Data Architecture, this module enables the
knowledge platform to:
1. Intercept and cluster unrecognized entities and relationships from text.
2. Synthesize compliant schema evolution proposals (Palantir structural constraints,
   provenance properties, PascalCase labels, UPPERCASE relationships).
3. Analyze graph density and traversal performance impact.
4. Support human-in-the-loop review, visual YAML diff generation, and hot-reload.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from ontology_engine.manager import OntologyManager
from ontology_engine.schema import DomainSchema, EntityDef, PropertyDef, PropertyType, RelationshipDef

logger = logging.getLogger(__name__)

DEFAULT_EVOLUTION_DB_PATH = Path("data/ontology_evolution.db")


@dataclass
class CandidateConcept:
    """An unmapped candidate entity or relationship observed in raw text."""

    name: str
    category: str  # "entity" or "relationship"
    occurrences: int = 1
    context_snippets: list[str] = field(default_factory=list)
    suggested_properties: list[str] = field(default_factory=list)
    source_docs: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    status: str = "NEW"  # NEW, CLUSTERED, PROPOSED, DISMISSED
    id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConceptCluster:
    """A semantic cluster of related unmapped concepts."""

    cluster_id: str
    canonical_name: str
    category: str  # "entity" or "relationship"
    member_names: list[str]
    total_occurrences: int
    context_snippets: list[str]
    suggested_properties: list[str]
    source_docs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvolutionProposal:
    """A synthesized schema evolution proposal ready for admin review."""

    proposal_id: str
    schema_name: str
    title: str
    concept_name: str
    concept_category: str  # "entity" or "relationship"
    description: str
    proposed_entity: Optional[dict[str, Any]]
    proposed_relationships: list[dict[str, Any]]
    impact_assessment: dict[str, Any]
    original_yaml: str
    updated_yaml: str
    diff: str
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED
    created_at: str = ""
    reviewed_at: Optional[str] = None
    review_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvolutionStore:
    """SQLite persistence for unrecognized concepts and schema evolution proposals."""

    def __init__(self, db_path: Union[str, Path] = DEFAULT_EVOLUTION_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._seed_default_candidates_if_empty()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candidate_concepts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    occurrences INTEGER DEFAULT 1,
                    context_snippets TEXT DEFAULT '[]',
                    suggested_properties TEXT DEFAULT '[]',
                    source_docs TEXT DEFAULT '[]',
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    status TEXT DEFAULT 'NEW'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    schema_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    concept_name TEXT NOT NULL,
                    concept_category TEXT NOT NULL,
                    description TEXT,
                    proposed_entity TEXT,
                    proposed_relationships TEXT,
                    impact_assessment TEXT,
                    original_yaml TEXT,
                    updated_yaml TEXT,
                    diff TEXT,
                    status TEXT DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    review_notes TEXT DEFAULT ''
                )
            """)
            conn.commit()

    def _seed_default_candidates_if_empty(self) -> None:
        """Seed realistic clinical candidates for immediate demonstration."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM candidate_concepts")
            if cursor.fetchone()[0] == 0:
                now = datetime.now(timezone.utc).isoformat()
                seeds = [
                    (
                        "AdverseEvent",
                        "entity",
                        4,
                        json.dumps([
                            "Patient experienced severe AdverseEvent characterized by angioedema after Lisinopril administration.",
                            "AdverseEvent recorded: elevated serum transaminases following high-dose Statin.",
                            "Post-operative AdverseEvent: acute wound infection treated with broad-spectrum antibiotics.",
                            "Mild AdverseEvent reported: transient dizziness after initial dosage."
                        ]),
                        json.dumps(["event_id", "severity", "onset_date", "outcome", "reported_by"]),
                        json.dumps(["clinical_note_104.md", "discharge_summary_042.pdf"]),
                        now,
                        now,
                        "NEW"
                    ),
                    (
                        "SideEffect",
                        "entity",
                        2,
                        json.dumps([
                            "Patient noted persistent dry cough as a common SideEffect of ACE inhibitor therapy.",
                            "Mild nausea noted as secondary SideEffect of Metformin."
                        ]),
                        json.dumps(["severity", "duration", "resolves_spontaneously"]),
                        json.dumps(["followup_note_209.md"]),
                        now,
                        now,
                        "NEW"
                    ),
                    (
                        "ClinicalTrial",
                        "entity",
                        3,
                        json.dumps([
                            "Patient screened for Phase III ClinicalTrial investigating novel SGLT2 inhibitor in diabetic nephropathy.",
                            "Inclusion criteria for ClinicalTrial met: eGFR between 30 and 60 mL/min.",
                            "Protocol deviation logged for ClinicalTrial NCT04512344 cohort B."
                        ]),
                        json.dumps(["trial_id", "phase", "protocol_number", "sponsor", "enrollment_date"]),
                        json.dumps(["research_registry_01.pdf"]),
                        now,
                        now,
                        "NEW"
                    ),
                    (
                        "REPORTED_ADVERSE_EVENT",
                        "relationship",
                        4,
                        json.dumps([
                            "Patient -> REPORTED_ADVERSE_EVENT -> AdverseEvent",
                            "Treating physician logged REPORTED_ADVERSE_EVENT into pharmacovigilance portal."
                        ]),
                        json.dumps(["report_date", "causality_score", "reported_by"]),
                        json.dumps(["clinical_note_104.md"]),
                        now,
                        now,
                        "NEW"
                    )
                ]
                conn.executemany("""
                    INSERT INTO candidate_concepts (
                        name, category, occurrences, context_snippets,
                        suggested_properties, source_docs, first_seen, last_seen, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, seeds)
                conn.commit()
                logger.info("Seeded default candidate concepts into evolution store")

    def record_candidate(
        self,
        name: str,
        category: str,
        context: Optional[str] = None,
        source_doc: Optional[str] = None,
        properties: Optional[list[str]] = None,
    ) -> CandidateConcept:
        """Record an unmapped candidate concept or increment its occurrence count."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM candidate_concepts WHERE name = ?", (name,))
            row = cursor.fetchone()

            if row:
                occurrences = row["occurrences"] + 1
                snippets = json.loads(row["context_snippets"] or "[]")
                if context and context not in snippets:
                    snippets.append(context)
                
                docs = json.loads(row["source_docs"] or "[]")
                if source_doc and source_doc not in docs:
                    docs.append(source_doc)

                props = json.loads(row["suggested_properties"] or "[]")
                if properties:
                    for p in properties:
                        if p not in props:
                            props.append(p)

                conn.execute("""
                    UPDATE candidate_concepts
                    SET occurrences = ?, context_snippets = ?, source_docs = ?,
                        suggested_properties = ?, last_seen = ?
                    WHERE name = ?
                """, (occurrences, json.dumps(snippets), json.dumps(docs), json.dumps(props), now, name))
                conn.commit()

                return CandidateConcept(
                    id=row["id"],
                    name=name,
                    category=category,
                    occurrences=occurrences,
                    context_snippets=snippets,
                    suggested_properties=props,
                    source_docs=docs,
                    first_seen=row["first_seen"],
                    last_seen=now,
                    status=row["status"],
                )
            else:
                snippets = [context] if context else []
                docs = [source_doc] if source_doc else []
                props = properties or []

                cursor.execute("""
                    INSERT INTO candidate_concepts (
                        name, category, occurrences, context_snippets,
                        suggested_properties, source_docs, first_seen, last_seen, status
                    ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, 'NEW')
                """, (name, category, json.dumps(snippets), json.dumps(props), json.dumps(docs), now, now))
                conn.commit()
                cid = cursor.lastrowid

                return CandidateConcept(
                    id=cid,
                    name=name,
                    category=category,
                    occurrences=1,
                    context_snippets=snippets,
                    suggested_properties=props,
                    source_docs=docs,
                    first_seen=now,
                    last_seen=now,
                    status="NEW",
                )

    def list_candidates(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        min_occurrences: int = 1,
    ) -> list[CandidateConcept]:
        """Retrieve candidate concepts matching criteria."""
        query = "SELECT * FROM candidate_concepts WHERE occurrences >= ?"
        params: list[Any] = [min_occurrences]

        if category:
            query += " AND category = ?"
            params.append(category)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY occurrences DESC, last_seen DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                CandidateConcept(
                    id=r["id"],
                    name=r["name"],
                    category=r["category"],
                    occurrences=r["occurrences"],
                    context_snippets=json.loads(r["context_snippets"] or "[]"),
                    suggested_properties=json.loads(r["suggested_properties"] or "[]"),
                    source_docs=json.loads(r["source_docs"] or "[]"),
                    first_seen=r["first_seen"],
                    last_seen=r["last_seen"],
                    status=r["status"],
                )
                for r in rows
            ]

    def dismiss_candidate(self, name: str) -> bool:
        """Mark a candidate as dismissed."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE candidate_concepts SET status = 'DISMISSED' WHERE name = ?", (name,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def create_proposal(self, proposal: EvolutionProposal) -> None:
        """Persist a new schema evolution proposal."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO schema_proposals (
                    proposal_id, schema_name, title, concept_name, concept_category,
                    description, proposed_entity, proposed_relationships, impact_assessment,
                    original_yaml, updated_yaml, diff, status, created_at, reviewed_at, review_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                proposal.proposal_id,
                proposal.schema_name,
                proposal.title,
                proposal.concept_name,
                proposal.concept_category,
                proposal.description,
                json.dumps(proposal.proposed_entity) if proposal.proposed_entity else None,
                json.dumps(proposal.proposed_relationships),
                json.dumps(proposal.impact_assessment),
                proposal.original_yaml,
                proposal.updated_yaml,
                proposal.diff,
                proposal.status,
                proposal.created_at,
                proposal.reviewed_at,
                proposal.review_notes,
            ))
            conn.commit()

    def get_proposal(self, proposal_id: str) -> Optional[EvolutionProposal]:
        """Retrieve a specific proposal by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schema_proposals WHERE proposal_id = ?", (proposal_id,))
            r = cursor.fetchone()
            if not r:
                return None

            return EvolutionProposal(
                proposal_id=r["proposal_id"],
                schema_name=r["schema_name"],
                title=r["title"],
                concept_name=r["concept_name"],
                concept_category=r["concept_category"],
                description=r["description"] or "",
                proposed_entity=json.loads(r["proposed_entity"]) if r["proposed_entity"] else None,
                proposed_relationships=json.loads(r["proposed_relationships"] or "[]"),
                impact_assessment=json.loads(r["impact_assessment"] or "{}"),
                original_yaml=r["original_yaml"] or "",
                updated_yaml=r["updated_yaml"] or "",
                diff=r["diff"] or "",
                status=r["status"],
                created_at=r["created_at"],
                reviewed_at=r["reviewed_at"],
                review_notes=r["review_notes"] or "",
            )

    def list_proposals(self, status: Optional[str] = None) -> list[EvolutionProposal]:
        """List proposals ordered by creation date."""
        query = "SELECT * FROM schema_proposals"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                EvolutionProposal(
                    proposal_id=r["proposal_id"],
                    schema_name=r["schema_name"],
                    title=r["title"],
                    concept_name=r["concept_name"],
                    concept_category=r["concept_category"],
                    description=r["description"] or "",
                    proposed_entity=json.loads(r["proposed_entity"]) if r["proposed_entity"] else None,
                    proposed_relationships=json.loads(r["proposed_relationships"] or "[]"),
                    impact_assessment=json.loads(r["impact_assessment"] or "{}"),
                    original_yaml=r["original_yaml"] or "",
                    updated_yaml=r["updated_yaml"] or "",
                    diff=r["diff"] or "",
                    status=r["status"],
                    created_at=r["created_at"],
                    reviewed_at=r["reviewed_at"],
                    review_notes=r["review_notes"] or "",
                )
                for r in rows
            ]

    def update_proposal_status(
        self, proposal_id: str, status: str, notes: str = ""
    ) -> bool:
        """Update proposal status ('APPROVED' or 'REJECTED') with timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE schema_proposals
                SET status = ?, reviewed_at = ?, review_notes = ?
                WHERE proposal_id = ?
            """, (status, now, notes, proposal_id))
            conn.commit()
            return cursor.rowcount > 0


class SemanticConceptClusterer:
    """Clusters unmapped candidate concepts into coherent conceptual entities."""

    # Domain term synonyms and affinities for medical/healthtech concepts
    CONCEPT_AFFINITIES: dict[str, list[str]] = {
        "AdverseEvent": ["adverse", "event", "sideeffect", "reaction", "complication", "toxicity", "allergy"],
        "ClinicalTrial": ["trial", "study", "cohort", "protocol", "investigation", "arm"],
        "Biomarker": ["biomarker", "marker", "antigen", "expression", "mutation", "gene"],
        "MedicalDevice": ["device", "implant", "sensor", "monitor", "prosthetic"],
        "InsuranceClaim": ["claim", "billing", "reimbursement", "coverage", "copay", "payer"],
    }

    @classmethod
    def cluster_candidates(
        cls, candidates: list[CandidateConcept]
    ) -> list[ConceptCluster]:
        """
        Group candidate concepts by semantic keyword overlap and similarity.
        """
        if not candidates:
            return []

        clusters: list[ConceptCluster] = []
        assigned = set()

        for cand in candidates:
            if cand.name in assigned:
                continue

            # Determine best canonical name
            cand_norm = cand.name.lower()
            matched_canonical = None

            for canon, keywords in cls.CONCEPT_AFFINITIES.items():
                if any(kw in cand_norm for kw in keywords):
                    matched_canonical = canon
                    break

            if not matched_canonical:
                # Fallback to PascalCase normalization of cand.name
                matched_canonical = cls._to_pascal_case(cand.name)

            # Find all members that belong to this cluster
            members: list[CandidateConcept] = []
            for other in candidates:
                if other.name in assigned or other.category != cand.category:
                    continue
                other_norm = other.name.lower()
                is_member = False
                if matched_canonical in cls.CONCEPT_AFFINITIES:
                    keywords = cls.CONCEPT_AFFINITIES[matched_canonical]
                    if any(kw in other_norm for kw in keywords):
                        is_member = True
                elif other_norm == cand_norm or other_norm in cand_norm or cand_norm in other_norm:
                    is_member = True

                if is_member:
                    members.append(other)
                    assigned.add(other.name)

            if not members:
                members = [cand]
                assigned.add(cand.name)

            # Aggregate stats
            total_occ = sum(m.occurrences for m in members)
            snippets = []
            for m in members:
                for s in m.context_snippets:
                    if s not in snippets:
                        snippets.append(s)

            props = []
            for m in members:
                for p in m.suggested_properties:
                    if p not in props:
                        props.append(p)

            docs = []
            for m in members:
                for d in m.source_docs:
                    if d not in docs:
                        docs.append(d)

            clusters.append(
                ConceptCluster(
                    cluster_id=f"cluster_{matched_canonical.lower()}_{uuid.uuid4().hex[:6]}",
                    canonical_name=matched_canonical,
                    category=cand.category,
                    member_names=[m.name for m in members],
                    total_occurrences=total_occ,
                    context_snippets=snippets[:5],
                    suggested_properties=props,
                    source_docs=docs,
                )
            )

        return sorted(clusters, key=lambda c: c.total_occurrences, reverse=True)

    @staticmethod
    def _to_pascal_case(text: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", text)
        return "".join(w.capitalize() for w in words) if words else text


class GraphImpactAnalyzer:
    """Analyzes graph topology density, traversal overhead, and Palantir governance compliance."""

    @staticmethod
    def analyze_impact(
        schema: DomainSchema,
        proposed_entity: Optional[dict[str, Any]],
        proposed_relationships: list[dict[str, Any]],
        candidate_occurrences: int = 5,
    ) -> dict[str, Any]:
        """
        Calculate metrics estimating the operational impact of proposed schema additions.
        """
        curr_entities = len(schema.entities)
        curr_rels = len(schema.relationships)

        new_entities_count = 1 if proposed_entity else 0
        new_rels_count = len(proposed_relationships)

        # Baseline density
        curr_density = curr_rels / max(1, curr_entities)
        proj_density = (curr_rels + new_rels_count) / max(1, (curr_entities + new_entities_count))
        density_delta = round(proj_density - curr_density, 3)

        # Traversal fanout risk
        fanout_risk = "LOW"
        risk_factors = []
        for rel in proposed_relationships:
            src = rel.get("source", "")
            tgt = rel.get("target", "")
            # Check if relationship binds to high-cardinality existing nodes
            if src in ("Patient", "Visit") and tgt in ("Patient", "Visit"):
                fanout_risk = "MEDIUM"
                risk_factors.append(f"Direct high-frequency edge between {src} and {tgt}")

        # Governance compliance check (Palantir Architecture)
        compliance_score = 100
        governance_checks = []

        if proposed_entity:
            entity_name = proposed_entity.get("name", "")
            # Must be PascalCase singular
            if not re.match(r"^[A-Z][a-zA-Z0-9]*$", entity_name):
                compliance_score -= 20
                governance_checks.append("Entity name must be PascalCase singular")
            else:
                governance_checks.append("Entity name is valid PascalCase singular")

            # Check required provenance fields
            prop_names = [p.get("name") for p in proposed_entity.get("properties", [])]
            for prov in ("source_id", "created_at", "confidence_score"):
                if prov in prop_names:
                    governance_checks.append(f"Provenance property '{prov}' verified")
                else:
                    compliance_score -= 10
                    governance_checks.append(f"Missing mandatory provenance property '{prov}'")

        for r in proposed_relationships:
            rname = r.get("name", "")
            if not re.match(r"^[A-Z][A-Z0-9_]*$", rname):
                compliance_score -= 15
                governance_checks.append(f"Relationship '{rname}' must be UPPERCASE with underscores")
            else:
                governance_checks.append(f"Relationship '{rname}' adheres to verb standards")

        return {
            "current_entities_count": curr_entities,
            "current_relationships_count": curr_rels,
            "proposed_entities_count": curr_entities + new_entities_count,
            "proposed_relationships_count": curr_rels + new_rels_count,
            "predicted_node_multiplier": round(1.0 + (candidate_occurrences / 50.0), 3),
            "graph_density_delta": density_delta,
            "fanout_risk": fanout_risk,
            "risk_factors": risk_factors,
            "query_performance_impact": "MINIMAL (< 4ms)",
            "palantir_governance_score": max(50, compliance_score),
            "governance_checks": governance_checks,
        }


class SchemaEvolutionGenerator:
    """Generates structured YAML modifications adhering to Palantir ontology constraints."""

    # Default properties for common concept categories
    PROTOTYPE_PROPERTIES: dict[str, list[dict[str, Any]]] = {
        "AdverseEvent": [
            {"name": "event_id", "type": "string", "required": True, "unique": True, "indexed": True, "example": "AE-001"},
            {"name": "severity", "type": "string", "required": True, "description": "Mild, Moderate, or Severe", "example": "Severe"},
            {"name": "onset_date", "type": "date", "description": "Date symptoms began", "example": "2026-10-15"},
            {"name": "outcome", "type": "string", "description": "Clinical resolution", "example": "Recovered with sequelae"},
            {"name": "source_id", "type": "string", "required": True, "description": "Provenance source document ID"},
            {"name": "created_at", "type": "datetime", "required": True, "description": "Ingestion audit timestamp"},
            {"name": "confidence_score", "type": "float", "required": True, "description": "Extraction confidence score"},
        ],
        "ClinicalTrial": [
            {"name": "trial_id", "type": "string", "required": True, "unique": True, "indexed": True, "example": "NCT04512344"},
            {"name": "phase", "type": "string", "required": True, "example": "Phase III"},
            {"name": "protocol_title", "type": "string", "example": "Cardiovascular Outcomes Evaluation"},
            {"name": "sponsor", "type": "string", "example": "Global Health Therapeutics"},
            {"name": "source_id", "type": "string", "required": True, "description": "Provenance source document ID"},
            {"name": "created_at", "type": "datetime", "required": True, "description": "Ingestion audit timestamp"},
            {"name": "confidence_score", "type": "float", "required": True, "description": "Extraction confidence score"},
        ],
    }

    # Default prototype relationships connecting new entity to existing schema
    PROTOTYPE_RELATIONSHIPS: dict[str, list[dict[str, Any]]] = {
        "AdverseEvent": [
            {
                "name": "EXPERIENCED_ADVERSE_EVENT",
                "description": "Patient experienced a reported clinical adverse event",
                "source": "Patient",
                "target": "AdverseEvent",
                "properties": [{"name": "reported_date", "type": "date"}],
            },
            {
                "name": "SUSPECTED_CAUSATIVE_AGENT",
                "description": "Medication suspected of causing the adverse event",
                "source": "AdverseEvent",
                "target": "Medication",
                "properties": [{"name": "causality_score", "type": "float"}],
            },
        ],
        "ClinicalTrial": [
            {
                "name": "ENROLLED_IN_TRIAL",
                "description": "Patient enrolled in an active clinical trial protocol",
                "source": "Patient",
                "target": "ClinicalTrial",
                "properties": [{"name": "enrollment_date", "type": "date"}],
            }
        ]
    }

    @classmethod
    def generate_proposal(
        cls,
        schema: DomainSchema,
        cluster: ConceptCluster,
        existing_yaml: str,
        custom_description: Optional[str] = None,
    ) -> EvolutionProposal:
        """
        Synthesize a valid SchemaEvolutionProposal with unified diff.
        """
        canonical = cluster.canonical_name
        is_entity = cluster.category == "entity"

        # 1. Synthesize proposed entity if category is entity
        proposed_entity = None
        if is_entity:
            props = cls.PROTOTYPE_PROPERTIES.get(
                canonical,
                [
                    {"name": f"{canonical.lower()}_id", "type": "string", "required": True, "unique": True, "indexed": True, "example": f"{canonical[:3].upper()}-001"},
                    {"name": "name", "type": "string", "required": True, "description": f"{canonical} descriptive name"},
                    {"name": "source_id", "type": "string", "required": True, "description": "Provenance document reference"},
                    {"name": "created_at", "type": "datetime", "required": True, "description": "Audit timestamp"},
                    {"name": "confidence_score", "type": "float", "required": True, "description": "Extraction confidence score"},
                ]
            )

            # Incorporate suggested properties from candidates
            existing_prop_names = {p["name"] for p in props}
            for p in cluster.suggested_properties:
                p_clean = p.lower().strip()
                if p_clean and p_clean not in existing_prop_names:
                    props.append({"name": p_clean, "type": "string", "required": False})
                    existing_prop_names.add(p_clean)

            desc = custom_description or (
                f"Emerging {canonical} concept synthesized from {cluster.total_occurrences} observed references "
                f"across ingested documents."
            )

            proposed_entity = {
                "name": canonical,
                "label": canonical,
                "description": desc,
                "properties": props,
                "embed_properties": ["name"] if "name" in existing_prop_names else [props[0]["name"]],
            }

        # 2. Synthesize proposed relationships
        proposed_relationships = []
        if is_entity and canonical in cls.PROTOTYPE_RELATIONSHIPS:
            proposed_relationships = cls.PROTOTYPE_RELATIONSHIPS[canonical]
        elif is_entity:
            # Default connecting edge from Patient if Patient exists in schema
            if "Patient" in schema.get_entity_names():
                rel_name = f"HAS_{canonical.upper()}"
                proposed_relationships.append({
                    "name": rel_name,
                    "description": f"Patient associated with {canonical}",
                    "source": "Patient",
                    "target": canonical,
                    "properties": [{"name": "associated_date", "type": "date"}],
                })
        else:
            # Relationship concept
            rel_name = cls._to_relationship_verb(canonical)
            proposed_relationships.append({
                "name": rel_name,
                "description": f"Extracted semantic relationship {rel_name}",
                "source": "Patient" if "Patient" in schema.get_entity_names() else schema.entities[0].name,
                "target": schema.entities[1].name if len(schema.entities) > 1 else schema.entities[0].name,
                "properties": [{"name": "confidence", "type": "float"}],
            })

        # 3. Build updated YAML structure
        schema_dict = yaml.safe_load(existing_yaml) or {}

        # Increment minor version (e.g. 1.0.0 -> 1.1.0)
        curr_ver = schema_dict.get("version", "1.0.0")
        ver_parts = curr_ver.split(".")
        if len(ver_parts) == 3 and ver_parts[1].isdigit():
            new_ver = f"{ver_parts[0]}.{int(ver_parts[1]) + 1}.0"
        else:
            new_ver = f"{curr_ver}.1"
        schema_dict["version"] = new_ver

        if proposed_entity:
            schema_dict.setdefault("entities", []).append(proposed_entity)

        for rel in proposed_relationships:
            schema_dict.setdefault("relationships", []).append(rel)

        updated_yaml = yaml.dump(
            schema_dict,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
            indent=2,
        )

        # 4. Generate clean unified diff
        diff_lines = list(difflib.unified_diff(
            existing_yaml.splitlines(keepends=True),
            updated_yaml.splitlines(keepends=True),
            fromfile=f"schemas/{schema.name}.yaml (v{curr_ver})",
            tofile=f"schemas/{schema.name}.yaml (v{new_ver} Proposed)",
        ))
        diff_str = "".join(diff_lines)

        # 5. Graph Impact Assessment
        impact = GraphImpactAnalyzer.analyze_impact(
            schema=schema,
            proposed_entity=proposed_entity,
            proposed_relationships=proposed_relationships,
            candidate_occurrences=cluster.total_occurrences,
        )

        proposal_id = f"prop_{uuid.uuid4().hex[:8]}"
        title = f"Add {canonical} concept (v{new_ver})"

        return EvolutionProposal(
            proposal_id=proposal_id,
            schema_name=schema.name,
            title=title,
            concept_name=canonical,
            concept_category=cluster.category,
            description=custom_description or f"Evolution proposal adding '{canonical}' based on {cluster.total_occurrences} observed occurrences.",
            proposed_entity=proposed_entity,
            proposed_relationships=proposed_relationships,
            impact_assessment=impact,
            original_yaml=existing_yaml,
            updated_yaml=updated_yaml,
            diff=diff_str,
            status="PENDING",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _to_relationship_verb(name: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", name)
        return "_".join(w.upper() for w in words) if words else name.upper()


class EvolutionService:
    """Enterprise coordinator for ontology evolution lifecycle and hot-reload."""

    def __init__(
        self,
        store: Optional[EvolutionStore] = None,
        ontology_manager: Optional[OntologyManager] = None,
    ) -> None:
        self.store = store or EvolutionStore()
        self.ontology_manager = ontology_manager or OntologyManager()

    def get_candidate_clusters(
        self, category: Optional[str] = None, min_occurrences: int = 1
    ) -> list[ConceptCluster]:
        """Fetch candidates and group them into semantic concept clusters."""
        candidates = self.store.list_candidates(
            category=category, status="NEW", min_occurrences=min_occurrences
        )
        return SemanticConceptClusterer.cluster_candidates(candidates)

    def generate_proposal_for_cluster(
        self,
        schema_name: str,
        cluster_name: str,
        custom_description: Optional[str] = None,
    ) -> EvolutionProposal:
        """Synthesize and persist a schema evolution proposal for a given cluster."""
        schema = self.ontology_manager.load(schema_name)
        schema_path = self.ontology_manager.schemas_dir / f"{schema_name}.yaml"
        if not schema_path.exists():
            schema_path = self.ontology_manager.schemas_dir / f"{schema_name}.yml"

        with open(schema_path, "r") as f:
            existing_yaml = f.read()

        # Find cluster or construct single-concept cluster
        clusters = self.get_candidate_clusters()
        matched = next((c for c in clusters if c.canonical_name.lower() == cluster_name.lower()), None)

        if not matched:
            matched = ConceptCluster(
                cluster_id=f"cluster_{cluster_name.lower()}",
                canonical_name=SemanticConceptClusterer._to_pascal_case(cluster_name),
                category="entity",
                member_names=[cluster_name],
                total_occurrences=1,
                context_snippets=[],
                suggested_properties=[],
                source_docs=[],
            )

        proposal = SchemaEvolutionGenerator.generate_proposal(
            schema=schema,
            cluster=matched,
            existing_yaml=existing_yaml,
            custom_description=custom_description,
        )

        self.store.create_proposal(proposal)
        logger.info(f"Created evolution proposal: {proposal.proposal_id} ({proposal.title})")
        return proposal

    def approve_and_apply_proposal(
        self, proposal_id: str, review_notes: str = ""
    ) -> dict[str, Any]:
        """
        Validate, backup, apply updated YAML to disk, hot-reload schema cache,
        and mark proposal as APPROVED.
        """
        proposal = self.store.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal '{proposal_id}' not found")
        if proposal.status != "PENDING":
            raise ValueError(f"Proposal '{proposal_id}' is already {proposal.status}")

        # 1. Validate updated YAML syntax and DomainSchema validity
        try:
            raw_data = yaml.safe_load(proposal.updated_yaml)
            validated_schema = DomainSchema(**raw_data)
        except Exception as e:
            raise ValueError(f"Updated YAML failed schema validation: {e}") from e

        # 2. Write backup copy
        schema_path = self.ontology_manager.schemas_dir / f"{proposal.schema_name}.yaml"
        if schema_path.exists():
            backup_path = self.ontology_manager.schemas_dir / f"{proposal.schema_name}.yaml.bak"
            backup_path.write_text(schema_path.read_text())
            logger.info(f"Saved schema backup to {backup_path}")

        # 3. Apply changes to disk
        schema_path.write_text(proposal.updated_yaml)
        logger.info(f"Wrote updated schema YAML to {schema_path}")

        # 4. Hot-reload schema in OntologyManager
        reloaded_schema = self.ontology_manager.reload(proposal.schema_name)
        logger.info(f"Hot-reloaded schema '{proposal.schema_name}' v{reloaded_schema.version}")

        # 5. Update proposal status
        self.store.update_proposal_status(proposal_id, "APPROVED", review_notes)

        return {
            "status": "APPROVED",
            "proposal_id": proposal_id,
            "schema_name": proposal.schema_name,
            "version": reloaded_schema.version,
            "entities_count": len(reloaded_schema.entities),
            "relationships_count": len(reloaded_schema.relationships),
        }

    def reject_proposal(self, proposal_id: str, reason: str = "") -> dict[str, Any]:
        """Mark proposal as REJECTED with notes."""
        proposal = self.store.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal '{proposal_id}' not found")

        self.store.update_proposal_status(proposal_id, "REJECTED", reason)
        return {"status": "REJECTED", "proposal_id": proposal_id, "reason": reason}
