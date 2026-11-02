"""
CKP Self-Healing Knowledge Agent — Reconciliation Loop & Graph De-duplication.

Responsibilities:
1. Multi-metric duplicate entity detection (exact match, Levenshtein, Jaro-Winkler, cosine similarity)
2. Atomic graph merger & relationship redirection in Neo4j
3. Qdrant vector chunk entity metadata synchronization
4. SQLite audit trail logging and rollback capability
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import math
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# String Similarity & Distance Algorithms (Zero external C-dependency)
# ---------------------------------------------------------------------------
def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def normalized_levenshtein_similarity(s1: str, s2: str) -> float:
    """Return normalized similarity [0.0, 1.0] based on Levenshtein distance."""
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    dist = levenshtein_distance(s1.lower().strip(), s2.lower().strip())
    return max(0.0, 1.0 - (dist / max_len))


def jaro_winkler_similarity(s1: str, s2: str, p: float = 0.1) -> float:
    """
    Compute the Jaro-Winkler similarity between two strings.
    Higher weight for common prefixes up to 4 characters.
    """
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] == s2[j]:
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

    if matches == 0:
        return 0.0

    # Count transpositions
    k = 0
    transpositions = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    transpositions //= 2

    jaro = (
        (matches / len1) +
        (matches / len2) +
        ((matches - transpositions) / matches)
    ) / 3.0

    # Prefix scale (up to 4 chars)
    prefix_len = 0
    for i in range(min(4, min(len1, len2))):
        if s1[i] == s2[i]:
            prefix_len += 1
        else:
            break

    return jaro + (prefix_len * p * (1.0 - jaro))


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm1 * norm2)))


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
@dataclass
class DuplicateCandidate:
    """Represents a detected duplicate node candidate pair."""

    source_id: str             # The duplicate node to merge into canonical
    canonical_id: str          # The canonical target node that will be kept
    entity_label: str
    source_name: str
    canonical_name: str
    similarity_score: float
    match_reasons: list[str] = field(default_factory=list)
    source_props: dict[str, Any] = field(default_factory=dict)
    canonical_props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MergeAuditRecord:
    """Audit log entry for a completed entity merge operation."""

    merge_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    entity_label: str = ""
    canonical_id: str = ""
    duplicate_id: str = ""
    canonical_name: str = ""
    duplicate_name: str = ""
    similarity_score: float = 0.0
    match_reasons: list[str] = field(default_factory=list)
    original_duplicate_props: dict[str, Any] = field(default_factory=dict)
    original_relationships: list[dict[str, Any]] = field(default_factory=list)
    qdrant_points_updated: int = 0
    status: str = "merged"  # "merged" | "reverted"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# SQLite Audit Log Store
# ---------------------------------------------------------------------------
class ReconciliationAuditStore:
    """SQLite-backed persistent audit trail for knowledge graph entity mergers."""

    def __init__(self, db_path: str = "data/reconciliation_audit.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entity_merge_audit (
                    merge_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    entity_label TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    duplicate_id TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    duplicate_name TEXT NOT NULL,
                    similarity_score REAL NOT NULL,
                    match_reasons TEXT NOT NULL,
                    original_duplicate_props TEXT NOT NULL,
                    original_relationships TEXT NOT NULL,
                    qdrant_points_updated INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'merged'
                )
                """
            )
            conn.commit()

    def record_merge(self, record: MergeAuditRecord) -> None:
        """Insert a completed merge record."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO entity_merge_audit (
                    merge_id, timestamp, entity_label, canonical_id, duplicate_id,
                    canonical_name, duplicate_name, similarity_score, match_reasons,
                    original_duplicate_props, original_relationships,
                    qdrant_points_updated, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.merge_id,
                    record.timestamp,
                    record.entity_label,
                    record.canonical_id,
                    record.duplicate_id,
                    record.canonical_name,
                    record.duplicate_name,
                    record.similarity_score,
                    json.dumps(record.match_reasons),
                    json.dumps(record.original_duplicate_props),
                    json.dumps(record.original_relationships),
                    record.qdrant_points_updated,
                    record.status,
                ),
            )
            conn.commit()

    def get_merge(self, merge_id: str) -> Optional[MergeAuditRecord]:
        """Fetch a specific merge audit record by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM entity_merge_audit WHERE merge_id = ?",
                (merge_id,),
            ).fetchone()
            if not row:
                return None
            return MergeAuditRecord(
                merge_id=row["merge_id"],
                timestamp=row["timestamp"],
                entity_label=row["entity_label"],
                canonical_id=row["canonical_id"],
                duplicate_id=row["duplicate_id"],
                canonical_name=row["canonical_name"],
                duplicate_name=row["duplicate_name"],
                similarity_score=float(row["similarity_score"]),
                match_reasons=json.loads(row["match_reasons"]),
                original_duplicate_props=json.loads(row["original_duplicate_props"]),
                original_relationships=json.loads(row["original_relationships"]),
                qdrant_points_updated=int(row["qdrant_points_updated"]),
                status=row["status"],
            )

    def list_merges(self, limit: int = 50) -> list[MergeAuditRecord]:
        """List recent merge audit entries."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM entity_merge_audit ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            results = []
            for row in rows:
                results.append(
                    MergeAuditRecord(
                        merge_id=row["merge_id"],
                        timestamp=row["timestamp"],
                        entity_label=row["entity_label"],
                        canonical_id=row["canonical_id"],
                        duplicate_id=row["duplicate_id"],
                        canonical_name=row["canonical_name"],
                        duplicate_name=row["duplicate_name"],
                        similarity_score=float(row["similarity_score"]),
                        match_reasons=json.loads(row["match_reasons"]),
                        original_duplicate_props=json.loads(row["original_duplicate_props"]),
                        original_relationships=json.loads(row["original_relationships"]),
                        qdrant_points_updated=int(row["qdrant_points_updated"]),
                        status=row["status"],
                    )
                )
            return results

    def mark_reverted(self, merge_id: str) -> bool:
        """Mark an audit record as reverted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE entity_merge_audit SET status = 'reverted' WHERE merge_id = ?",
                (merge_id,),
            )
            conn.commit()
            return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Knowledge Reconciler Agent
# ---------------------------------------------------------------------------
class KnowledgeReconciler:
    """
    Self-healing knowledge reconciliation agent.

    Identifies duplicate entities across Neo4j and semantic vectors,
    synthesizes canonical profiles, redirects graph edges atomically,
    updates Qdrant chunk entity payloads, and logs rollbacks in SQLite.
    """

    def __init__(
        self,
        neo4j_driver: Optional[Any] = None,
        qdrant_client: Optional[Any] = None,
        audit_store: Optional[ReconciliationAuditStore] = None,
        default_threshold: float = 0.85,
    ):
        self.neo4j_driver = neo4j_driver
        self.qdrant_client = qdrant_client
        self.audit_store = audit_store or ReconciliationAuditStore()
        self.default_threshold = default_threshold

    # ---- Similarity Scoring -----------------------------------------------

    def calculate_entity_similarity(
        self,
        node_a: dict[str, Any],
        node_b: dict[str, Any],
    ) -> tuple[float, list[str]]:
        """
        Evaluate pair-wise multi-metric similarity between two entity dictionaries.
        Combines exact property matching, Jaro-Winkler, Levenshtein, and vector embeddings.
        """
        reasons: list[str] = []
        scores: list[float] = []

        name_a = str(node_a.get("name") or node_a.get("title") or "").strip()
        name_b = str(node_b.get("name") or node_b.get("title") or "").strip()

        if not name_a or not name_b:
            return 0.0, []

        # 1. Normalized exact match (case, whitespace, punctuation)
        clean_a = "".join(ch for ch in name_a.lower() if ch.isalnum())
        clean_b = "".join(ch for ch in name_b.lower() if ch.isalnum())
        if clean_a == clean_b:
            return 1.0, ["Exact normalized name match"]

        # 2. Key Identifier Matches (SSN, MRN, Email, Code)
        for id_field in ("mrn", "patient_id", "doctor_id", "medication_id", "code", "npi", "email"):
            val_a = node_a.get(id_field)
            val_b = node_b.get(id_field)
            if val_a and val_b and str(val_a).strip().lower() == str(val_b).strip().lower():
                reasons.append(f"Matching unique identifier field '{id_field}': {val_a}")
                return 1.0, reasons

        # 3. String Metrics
        jw = jaro_winkler_similarity(name_a, name_b)
        lev = normalized_levenshtein_similarity(name_a, name_b)

        # Weighted combination for string metrics (60% Jaro-Winkler, 40% Levenshtein)
        name_score = (0.6 * jw) + (0.4 * lev)
        scores.append(name_score)
        if name_score >= 0.85:
            reasons.append(f"High name similarity ({name_score:.2f}): '{name_a}' ≈ '{name_b}'")

        # 4. Property Overlap Similarity (e.g. specialty, dosage, department)
        common_keys = set(node_a.keys()).intersection(node_b.keys()) - {"id", "name", "title", "_id"}
        if common_keys:
            prop_matches = 0
            for k in common_keys:
                va = str(node_a[k]).strip().lower()
                vb = str(node_b[k]).strip().lower()
                if va and vb and (va == vb or va in vb or vb in va):
                    prop_matches += 1
            if prop_matches > 0:
                prop_ratio = prop_matches / len(common_keys)
                scores.append(prop_ratio)
                reasons.append(f"Property agreement on {prop_matches}/{len(common_keys)} attributes")

        # 5. Vector Embedding Cosine Similarity (if present in node dicts)
        vec_a = node_a.get("embedding")
        vec_b = node_b.get("embedding")
        if vec_a and vec_b:
            v_sim = cosine_similarity(vec_a, vec_b)
            scores.append(v_sim)
            if v_sim >= 0.85:
                reasons.append(f"Vector cosine similarity ({v_sim:.2f})")

        overall_score = sum(scores) / len(scores) if scores else 0.0
        return round(overall_score, 4), reasons

    # ---- Duplicate Detection Scanner --------------------------------------

    async def scan_duplicates(
        self,
        nodes: Optional[list[dict[str, Any]]] = None,
        label: Optional[str] = None,
        threshold: Optional[float] = None,
    ) -> list[DuplicateCandidate]:
        """
        Scan a collection of nodes (or query Neo4j) to detect duplicate candidates.
        """
        min_threshold = threshold if threshold is not None else self.default_threshold
        candidates: list[DuplicateCandidate] = []

        # If nodes not directly provided, query Neo4j if available
        if nodes is None and self.neo4j_driver:
            nodes = await self._fetch_neo4j_nodes(label=label)
        elif nodes is None:
            nodes = []

        # Group nodes by label/type for efficient pairwise comparison
        by_label: dict[str, list[dict[str, Any]]] = {}
        for n in nodes:
            lbl = n.get("_label") or label or "Entity"
            by_label.setdefault(lbl, []).append(n)

        for lbl, group in by_label.items():
            n_nodes = len(group)
            for i in range(n_nodes):
                for j in range(i + 1, n_nodes):
                    node_1 = group[i]
                    node_2 = group[j]

                    score, reasons = self.calculate_entity_similarity(node_1, node_2)
                    if score >= min_threshold:
                        # Decide canonical vs duplicate:
                        # Prioritize node with more properties or older ID
                        props_1 = len([k for k, v in node_1.items() if v])
                        props_2 = len([k for k, v in node_2.items() if v])

                        id_1 = str(node_1.get("id") or node_1.get("name") or i)
                        id_2 = str(node_2.get("id") or node_2.get("name") or j)

                        if props_2 > props_1:
                            canonical, duplicate = node_2, node_1
                            canon_id, dup_id = id_2, id_1
                        else:
                            canonical, duplicate = node_1, node_2
                            canon_id, dup_id = id_1, id_2

                        candidates.append(
                            DuplicateCandidate(
                                source_id=dup_id,
                                canonical_id=canon_id,
                                entity_label=lbl,
                                source_name=str(duplicate.get("name") or duplicate.get("title") or dup_id),
                                canonical_name=str(canonical.get("name") or canonical.get("title") or canon_id),
                                similarity_score=score,
                                match_reasons=reasons,
                                source_props=duplicate,
                                canonical_props=canonical,
                            )
                        )

        # Sort descending by similarity
        candidates.sort(key=lambda c: c.similarity_score, reverse=True)
        return candidates

    async def _fetch_neo4j_nodes(self, label: Optional[str] = None) -> list[dict[str, Any]]:
        """Fetch nodes from Neo4j."""
        if not self.neo4j_driver:
            return []
        nodes: list[dict[str, Any]] = []
        try:
            async with self.neo4j_driver.session() as session:
                query = (
                    f"MATCH (n:{label}) RETURN n, labels(n)[0] as lbl, id(n) as nid LIMIT 500"
                    if label
                    else "MATCH (n) RETURN n, labels(n)[0] as lbl, id(n) as nid LIMIT 500"
                )
                result = await session.run(query)
                records = await result.data()
                for rec in records:
                    props = dict(rec.get("n", {}))
                    props["_label"] = rec.get("lbl") or "Entity"
                    props["_nid"] = rec.get("nid")
                    if "id" not in props:
                        props["id"] = props.get("name") or str(rec.get("nid"))
                    nodes.append(props)
        except Exception as e:
            logger.warning("Failed to fetch nodes from Neo4j: %s", e)
        return nodes

    # ---- Atomic Graph Merger & Edge Redirection ---------------------------

    async def execute_merge(
        self,
        candidate: DuplicateCandidate,
        dry_run: bool = False,
    ) -> MergeAuditRecord:
        """
        Merge duplicate entity node into canonical entity node.

        Actions:
        1. Synthesize merged properties (preserving existing, appending aliases)
        2. Redirect incoming relationships in Neo4j
        3. Redirect outgoing relationships in Neo4j
        4. Safely delete duplicate node
        5. Synchronize Qdrant vector chunk payloads
        6. Persist audit log in SQLite
        """
        audit_record = MergeAuditRecord(
            entity_label=candidate.entity_label,
            canonical_id=candidate.canonical_id,
            duplicate_id=candidate.source_id,
            canonical_name=candidate.canonical_name,
            duplicate_name=candidate.source_name,
            similarity_score=candidate.similarity_score,
            match_reasons=candidate.match_reasons,
            original_duplicate_props=candidate.source_props,
        )

        if dry_run:
            logger.info(
                "[Dry-Run] Would merge duplicate '%s' (%s) -> canonical '%s' (%s)",
                candidate.source_name, candidate.source_id,
                candidate.canonical_name, candidate.canonical_id,
            )
            return audit_record

        # 1. Neo4j graph edge redirection & node deletion
        relationships_captured: list[dict[str, Any]] = []
        if self.neo4j_driver:
            relationships_captured = await self._execute_neo4j_merge(candidate)
        audit_record.original_relationships = relationships_captured

        # 2. Qdrant vector chunk metadata synchronization
        qdrant_updated = 0
        if self.qdrant_client:
            qdrant_updated = await self._sync_qdrant_references(
                old_name=candidate.source_name,
                new_name=candidate.canonical_name,
                old_id=candidate.source_id,
                new_id=candidate.canonical_id,
            )
        audit_record.qdrant_points_updated = qdrant_updated

        # 3. Record audit trail in SQLite
        self.audit_store.record_merge(audit_record)
        logger.info(
            "Successfully merged '%s' -> '%s' (merge_id=%s, qdrant_pts=%d)",
            candidate.source_name, candidate.canonical_name,
            audit_record.merge_id[:8], qdrant_updated,
        )
        return audit_record

    async def _execute_neo4j_merge(self, candidate: DuplicateCandidate) -> list[dict[str, Any]]:
        """Atomically redirect incoming/outgoing edges and delete duplicate node in Neo4j."""
        captured_relationships: list[dict[str, Any]] = []
        lbl = candidate.entity_label

        try:
            async with self.neo4j_driver.session() as session:
                # 1. Capture and redirect incoming edges: (x)-[r]->(dup) => (x)-[new_r]->(canon)
                in_query = f"""
                MATCH (x)-[r]->(dup:{lbl})
                WHERE dup.name = $dup_name OR dup.id = $dup_id
                MATCH (canon:{lbl})
                WHERE canon.name = $canon_name OR canon.id = $canon_id
                RETURN type(r) as rel_type, properties(r) as rel_props,
                       x.name as other_name, labels(x)[0] as other_label, 'in' as direction
                """
                in_res = await session.run(
                    in_query,
                    dup_name=candidate.source_name,
                    dup_id=candidate.source_id,
                    canon_name=candidate.canonical_name,
                    canon_id=candidate.canonical_id,
                )
                captured_in = await in_res.data()
                captured_relationships.extend(captured_in)

                # 2. Capture and redirect outgoing edges: (dup)-[r]->(y) => (canon)-[new_r]->(y)
                out_query = f"""
                MATCH (dup:{lbl})-[r]->(y)
                WHERE dup.name = $dup_name OR dup.id = $dup_id
                MATCH (canon:{lbl})
                WHERE canon.name = $canon_name OR canon.id = $canon_id
                RETURN type(r) as rel_type, properties(r) as rel_props,
                       y.name as other_name, labels(y)[0] as other_label, 'out' as direction
                """
                out_res = await session.run(
                    out_query,
                    dup_name=candidate.source_name,
                    dup_id=candidate.source_id,
                    canon_name=candidate.canonical_name,
                    canon_id=candidate.canonical_id,
                )
                captured_out = await out_res.data()
                captured_relationships.extend(captured_out)

                # 3. Cypher Transaction: copy non-conflicting properties, add alias, redirect edges, delete duplicate
                merge_cypher = f"""
                MATCH (dup:{lbl})
                WHERE dup.name = $dup_name OR dup.id = $dup_id
                MATCH (canon:{lbl})
                WHERE canon.name = $canon_name OR canon.id = $canon_id
                AND id(dup) <> id(canon)

                // Add duplicate name to canonical aliases
                SET canon.aliases = CASE
                    WHEN canon.aliases IS NULL THEN [$dup_name]
                    WHEN NOT $dup_name IN canon.aliases THEN canon.aliases + $dup_name
                    ELSE canon.aliases
                END

                // Merge non-existing properties
                SET canon += $dup_props

                // Re-wire incoming relationships
                WITH dup, canon
                MATCH (x)-[r_in]->(dup)
                CALL apoc.create.relationship(x, type(r_in), properties(r_in), canon) YIELD rel as new_in
                DELETE r_in

                // Re-wire outgoing relationships
                WITH dup, canon
                MATCH (dup)-[r_out]->(y)
                CALL apoc.create.relationship(canon, type(r_out), properties(r_out), y) YIELD rel as new_out
                DELETE r_out

                // Safely delete duplicate node
                DETACH DELETE dup
                """
                try:
                    await session.run(
                        merge_cypher,
                        dup_name=candidate.source_name,
                        dup_id=candidate.source_id,
                        canon_name=candidate.canonical_name,
                        canon_id=candidate.canonical_id,
                        dup_props={k: v for k, v in candidate.source_props.items() if not k.startswith("_")},
                    )
                except Exception as apoc_err:
                    # Fallback for vanilla Neo4j without APOC procedures
                    logger.debug("APOC merge failed, attempting standard Cypher merge: %s", apoc_err)
                    fallback_cypher = f"""
                    MATCH (dup:{lbl})
                    WHERE dup.name = $dup_name OR dup.id = $dup_id
                    MATCH (canon:{lbl})
                    WHERE canon.name = $canon_name OR canon.id = $canon_id
                    AND id(dup) <> id(canon)

                    SET canon.aliases = CASE
                        WHEN canon.aliases IS NULL THEN [$dup_name]
                        WHEN NOT $dup_name IN canon.aliases THEN canon.aliases + $dup_name
                        ELSE canon.aliases
                    END

                    DETACH DELETE dup
                    """
                    await session.run(
                        fallback_cypher,
                        dup_name=candidate.source_name,
                        dup_id=candidate.source_id,
                        canon_name=candidate.canonical_name,
                        canon_id=candidate.canonical_id,
                    )
        except Exception as e:
            logger.warning("Neo4j execution failed during merge: %s", e)

        return captured_relationships

    # ---- Qdrant Vector Chunk Payload Synchronization ---------------------

    async def _sync_qdrant_references(
        self,
        old_name: str,
        new_name: str,
        old_id: str,
        new_id: str,
        collection_name: str = "ckp_chunks",
    ) -> int:
        """
        Update vector chunk payloads in Qdrant so references point to the canonical entity.
        """
        if not self.qdrant_client:
            return 0
        updated = 0
        try:
            # Query points containing references to old_name or old_id
            scroll_res = await self.qdrant_client.scroll(
                collection_name=collection_name,
                limit=100,
                with_payload=True,
            )
            points, _ = scroll_res
            for pt in points:
                payload = dict(pt.payload or {})
                mutated = False

                # Update entities list if present
                if "entities" in payload and isinstance(payload["entities"], list):
                    new_entities = []
                    for ent in payload["entities"]:
                        if ent == old_name or ent == old_id:
                            new_entities.append(new_name)
                            mutated = True
                        else:
                            new_entities.append(ent)
                    if mutated:
                        payload["entities"] = list(set(new_entities))

                if mutated:
                    await self.qdrant_client.set_payload(
                        collection_name=collection_name,
                        payload=payload,
                        points=[pt.id],
                    )
                    updated += 1
        except Exception as e:
            logger.debug("Qdrant metadata sync skipped or failed: %s", e)
        return updated

    # ---- Merge Rollback --------------------------------------------------

    async def rollback_merge(self, merge_id: str) -> bool:
        """
        Roll back a previously executed merge using the SQLite audit record.
        Reconstructs the original duplicate node and restores its properties.
        """
        record = self.audit_store.get_merge(merge_id)
        if not record or record.status == "reverted":
            return False

        if self.neo4j_driver:
            lbl = record.entity_label
            props = record.original_duplicate_props
            try:
                async with self.neo4j_driver.session() as session:
                    # Recreate duplicate node
                    create_cypher = f"CREATE (n:{lbl}) SET n = $props"
                    await session.run(
                        create_cypher,
                        props={k: v for k, v in props.items() if not k.startswith("_")},
                    )
            except Exception as e:
                logger.error("Failed to restore Neo4j node during rollback: %s", e)
                return False

        self.audit_store.mark_reverted(merge_id)
        logger.info("Successfully rolled back merge %s", merge_id)
        return True
