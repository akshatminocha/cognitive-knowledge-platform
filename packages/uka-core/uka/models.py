"""
Universal Knowledge Artifact (UKA) — Core Data Models.

Defines the canonical Pydantic v2 schemas for UKA manifest, subgraphs,
vector chunks, multimodal media indexes, and conversational memory.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class UKAManifest(BaseModel):
    """Manifest descriptor for a Universal Knowledge Artifact bundle."""

    uka_version: str = "0.1.0"
    artifact_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    generator: dict[str, str] = Field(
        default_factory=lambda: {
            "name": "Cognitive Knowledge Platform",
            "version": "3.0.0",
        }
    )
    title: str = ""
    description: str = ""
    modalities: list[str] = Field(default_factory=lambda: ["text"])
    stats: dict[str, Any] = Field(default_factory=dict)
    content_hashes: dict[str, str] = Field(default_factory=dict)


class UKAGraphNode(BaseModel):
    """A node entity in the UKA knowledge subgraph."""

    id: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class UKAGraphEdge(BaseModel):
    """A directed semantic relationship between two nodes in the UKA subgraph."""

    id: str
    type: str
    source: str
    target: str
    properties: dict[str, Any] = Field(default_factory=dict)


class UKASubgraph(BaseModel):
    """Full topological knowledge graph representation."""

    nodes: list[UKAGraphNode] = Field(default_factory=list)
    edges: list[UKAGraphEdge] = Field(default_factory=list)

    def to_cypher(self) -> str:
        """
        Generate parameterized or inline Cypher import statements
        to reconstruct this graph topology in any Neo4j instance.
        """
        statements = []

        # 1. Merge nodes
        for node in self.nodes:
            label_str = ":".join(node.labels) if node.labels else "Entity"
            props_list = [f"n.id = '{node.id}'"]
            for k, v in node.properties.items():
                if k != "id":
                    safe_v = str(v).replace("'", "\\'")
                    props_list.append(f"n.{k} = '{safe_v}'")
            set_clause = ", ".join(props_list)
            statements.append(f"MERGE (n:{label_str} {{id: '{node.id}'}}) SET {set_clause};")

        # 2. Merge edges
        for edge in self.edges:
            rel_type = edge.type.upper()
            rel_props = []
            for k, v in edge.properties.items():
                safe_v = str(v).replace("'", "\\'")
                rel_props.append(f"r.{k} = '{safe_v}'")
            set_clause = f" SET {', '.join(rel_props)}" if rel_props else ""
            statements.append(
                f"MATCH (s {{id: '{edge.source}'}}), (t {{id: '{edge.target}'}}) "
                f"MERGE (s)-[r:{rel_type}]->(t){set_clause};"
            )

        return "\n".join(statements)


class UKAVectorChunk(BaseModel):
    """A semantic text chunk with provenance tracking for vector storage."""

    chunk_id: str
    document_id: str
    modality: str = "text"
    page_or_slide: Optional[int] = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class UKAMediaAsset(BaseModel):
    """
    Multimodal asset metadata with pre-computed semantic content
    (transcripts, OCR, slide summaries) for instant agent comprehension.
    """

    asset_id: str
    filename: str
    mime_type: str = "application/octet-stream"
    sha256: str = ""
    size_bytes: int = 0
    modality: str = "vision"  # vision | audio | video | presentation
    summary: str = ""
    extracted_content: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)

    def __init__(self, **data: Any):
        if "media_type" in data and "mime_type" not in data:
            data["mime_type"] = data.pop("media_type")
        super().__init__(**data)


class UKAMediaIndex(BaseModel):
    """Catalog of all multimodal assets in the bundle with pre-extracted content."""

    version: str = "1.0.0"
    assets: list[UKAMediaAsset] = Field(default_factory=list)


class UKADistilledMemory(BaseModel):
    """Infinite memory summary tracking key facts, decisions, and open questions."""

    distilled_entities: list[Any] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    context_summary: str = ""

    model_config = ConfigDict(populate_by_name=True)

    def __init__(self, **data: Any):
        if "key_entities" in data and "distilled_entities" not in data:
            data["distilled_entities"] = data.pop("key_entities")
        if "confirmed_decisions" in data and "decisions" not in data:
            data["decisions"] = data.pop("confirmed_decisions")
        super().__init__(**data)

    @property
    def key_entities(self) -> list[str]:
        return [
            e.get("name") if isinstance(e, dict) else str(e)
            for e in self.distilled_entities
        ]

    @property
    def confirmed_decisions(self) -> list[str]:
        return self.decisions


class UKAMessage(BaseModel):
    """A conversational turn in the transcript."""

    role: str
    content: str
    timestamp: Optional[str] = None


class UKABundleData(BaseModel):
    """
    In-memory representation of all bundle data before packaging or after extraction.
    """

    manifest: UKAManifest
    context_md: str
    schema_yaml: Optional[str] = None
    messages: list[UKAMessage] = Field(default_factory=list)
    distilled_memory: Optional[UKADistilledMemory] = None
    subgraph: Optional[UKASubgraph] = None
    vector_chunks: list[UKAVectorChunk] = Field(default_factory=list)
    media_index: Optional[UKAMediaIndex] = None
    # Raw media bytes keyed by filename: e.g. {"img_9a8f2c.png": b"..."}
    media_files: dict[str, bytes] = Field(default_factory=dict)
    # Binary vector embeddings (float32 array bytes)
    embeddings_bin: Optional[bytes] = None
