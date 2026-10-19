"""
Universal Knowledge Artifact (UKA) Exporter.

Packages session context, infinite memory, knowledge graph subgraphs,
vector chunks, and multimodal assets into a portable, vendor-agnostic
container format (.uka).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from uka.bundle_writer import UKABundleWriter, compute_sha256
from uka.models import (
    UKABundleData,
    UKADistilledMemory,
    UKAGraphEdge,
    UKAGraphNode,
    UKAManifest,
    UKAMediaAsset,
    UKAMediaIndex,
    UKAMessage,
    UKASubgraph,
    UKAVectorChunk,
)
from .context_engine import ContextEngine

logger = logging.getLogger(__name__)


class UKAExporter:
    """
    Exports session context, active graph topologies, vector chunks,
    and multimodal assets into a canonical .uka container archive.
    """

    def __init__(
        self,
        context_engine: ContextEngine,
        neo4j_driver: Optional[Any] = None,
        qdrant_client: Optional[Any] = None,
        ontology_manager: Optional[Any] = None,
        active_domain: str = "healthtech",
    ) -> None:
        self.context_engine = context_engine
        self.neo4j_driver = neo4j_driver
        self.qdrant_client = qdrant_client
        self.ontology_manager = ontology_manager
        self.active_domain = active_domain

    def export_to_bundle(
        self,
        session_id: str,
        output_path: str | Path,
        title: Optional[str] = None,
        description: Optional[str] = None,
        extra_media_files: Optional[dict[str, bytes]] = None,
        extra_vector_chunks: Optional[list[UKAVectorChunk]] = None,
    ) -> Path:
        """
        Export the session as a full-fidelity .uka container bundle.
        """
        session = self.context_engine.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Gather Messages
        messages = [
            UKAMessage(
                role=str(msg.role),
                content=str(msg.content),
                timestamp=msg.timestamp.isoformat() if hasattr(msg, "timestamp") and msg.timestamp else None,
            )
            for msg in session.messages
        ]

        # 2. Gather Distilled Memory
        distilled_memory = None
        if hasattr(self.context_engine, "get_distilled_state"):
            dstate = self.context_engine.get_distilled_state(session_id)
            if dstate:
                distilled_memory = UKADistilledMemory(
                    distilled_entities=dstate.key_entities if hasattr(dstate, "key_entities") else [],
                    decisions=dstate.confirmed_decisions if hasattr(dstate, "confirmed_decisions") else [],
                    constraints=dstate.active_constraints if hasattr(dstate, "active_constraints") else [],
                    open_questions=dstate.unresolved_questions if hasattr(dstate, "unresolved_questions") else [],
                )

        # 3. Gather Active Domain Ontology Schema
        schema_yaml = self._load_ontology_yaml()

        # 4. Extract Knowledge Subgraph (Neo4j or Distilled State fallback)
        subgraph = self._extract_subgraph(session_id, distilled_memory)

        # 5. Extract Vector Chunks
        vector_chunks = extra_vector_chunks or []

        # 6. Extract Multimodal Media Assets
        media_index, media_files = self._extract_media_assets(session_id, extra_media_files)

        # 7. Generate Unified Context Markdown
        context_md = self._generate_markdown_context(
            session_id=session_id,
            messages=messages,
            distilled_memory=distilled_memory,
            subgraph=subgraph,
            media_index=media_index,
            title=title,
        )

        # 8. Build Manifest
        modalities = ["text"]
        if subgraph and (subgraph.nodes or subgraph.edges):
            modalities.append("graph")
        if vector_chunks:
            modalities.append("vector")
        if media_files:
            modalities.extend(["vision", "audio"])
        modalities = sorted(list(set(modalities)))

        manifest = UKAManifest(
            artifact_id=f"uka_{session_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            title=title or f"UKA Session Context: {session_id}",
            description=description or f"Portable universal knowledge artifact for session {session_id}",
            modalities=modalities,
        )

        # 9. Pack and Stream Bundle
        bundle_data = UKABundleData(
            manifest=manifest,
            context_md=context_md,
            schema_yaml=schema_yaml,
            messages=messages,
            distilled_memory=distilled_memory,
            subgraph=subgraph,
            vector_chunks=vector_chunks,
            media_index=media_index,
            media_files=media_files,
        )

        writer = UKABundleWriter()
        return writer.write(bundle_data, out_path)

    def export_to_json(self, session_id: str, output_path: str | Path) -> Path:
        """Backwards-compatible JSON context export."""
        session = self.context_engine.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found.")

        messages = [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat() if hasattr(msg, "timestamp") and msg.timestamp else None,
            }
            for msg in session.messages
        ]

        payload = {
            "metadata": {
                "version": "0.1.0",
                "export_date": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "format": "Universal Knowledge Artifact (UKA) JSON",
            },
            "messages": messages,
        }

        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        return p

    def _load_ontology_yaml(self) -> Optional[str]:
        """Load YAML string of active domain ontology."""
        if self.ontology_manager:
            try:
                schema = self.ontology_manager.load(self.active_domain)
                if hasattr(schema, "model_dump"):
                    import yaml
                    return yaml.dump(schema.model_dump(), sort_keys=False)
            except Exception as e:
                logger.debug(f"Could not load ontology from manager: {e}")

        # Fallback to direct file read from ontology-engine package
        pkg_root = Path(__file__).parent.parent.parent / "ontology-engine" / "schemas"
        candidates = [
            pkg_root / f"{self.active_domain}.yaml",
            pkg_root / f"{self.active_domain}.yml",
        ]
        for c in candidates:
            if c.exists():
                return c.read_text(encoding="utf-8")

        return None

    def _extract_subgraph(
        self,
        session_id: str,
        distilled_memory: Optional[UKADistilledMemory],
    ) -> UKASubgraph:
        """Extract graph entities and relations from Neo4j or memory fallback."""
        nodes: list[UKAGraphNode] = []
        edges: list[UKAGraphEdge] = []

        if self.neo4j_driver:
            try:
                with self.neo4j_driver.session() as session:
                    # Query recent nodes associated with this session or domain
                    cypher = (
                        "MATCH (n) "
                        "OPTIONAL MATCH (n)-[r]->(m) "
                        "RETURN n, r, m LIMIT 100"
                    )
                    records = session.run(cypher)
                    seen_nodes = set()
                    for record in records:
                        n = record.get("n")
                        if n and n.element_id not in seen_nodes:
                            seen_nodes.add(n.element_id)
                            nodes.append(
                                UKAGraphNode(
                                    id=str(n.get("id", n.element_id)),
                                    labels=list(n.labels),
                                    properties=dict(n),
                                )
                            )
                        r = record.get("r")
                        m = record.get("m")
                        if r and m:
                            edges.append(
                                UKAGraphEdge(
                                    id=str(r.element_id),
                                    type=r.type,
                                    source=str(n.get("id", n.element_id)),
                                    target=str(m.get("id", m.element_id)),
                                    properties=dict(r),
                                )
                            )
                    return UKASubgraph(nodes=nodes, edges=edges)
            except Exception as e:
                logger.warning(f"Failed to query Neo4j for session subgraph: {e}")

        # Fallback: Synthesize nodes from distilled entities
        if distilled_memory and distilled_memory.distilled_entities:
            for idx, ent in enumerate(distilled_memory.distilled_entities):
                name = ent.get("name") or ent.get("entity") or f"entity_{idx}"
                etype = ent.get("type") or "Entity"
                nodes.append(
                    UKAGraphNode(
                        id=f"node_{idx}",
                        labels=[etype],
                        properties={"name": name, **ent},
                    )
                )

        return UKASubgraph(nodes=nodes, edges=edges)

    def _extract_media_assets(
        self,
        session_id: str,
        extra_media_files: Optional[dict[str, bytes]],
    ) -> tuple[Optional[UKAMediaIndex], dict[str, bytes]]:
        """Gather multimodal assets and companion index."""
        media_files = extra_media_files or {}
        if not media_files:
            return None, {}

        assets = []
        for idx, (filename, data) in enumerate(media_files.items()):
            ext = Path(filename).suffix.lower()
            modality = "vision"
            if ext in (".wav", ".mp3"):
                modality = "audio"
            elif ext in (".mp4", ".mov"):
                modality = "video"
            elif ext in (".pptx", ".ppt"):
                modality = "presentation"

            assets.append(
                UKAMediaAsset(
                    asset_id=f"media_{idx}_{Path(filename).stem}",
                    filename=filename,
                    mime_type=f"application/octet-stream",
                    sha256=compute_sha256(data),
                    size_bytes=len(data),
                    modality=modality,
                    summary=f"Attached {modality} asset: {filename}",
                    extracted_content={"filename": filename},
                )
            )

        return UKAMediaIndex(assets=assets), media_files

    def _generate_markdown_context(
        self,
        session_id: str,
        messages: list[UKAMessage],
        distilled_memory: Optional[UKADistilledMemory],
        subgraph: Optional[UKASubgraph],
        media_index: Optional[UKAMediaIndex],
        title: Optional[str],
    ) -> str:
        """Build human- and LLM-readable Markdown context."""
        md = [
            f"# {title or f'Universal Knowledge Artifact: {session_id}'}",
            f"**Session ID:** `{session_id}`  ",
            f"**Exported:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            "",
            "---",
            "",
        ]

        # 1. Distilled Memory
        if distilled_memory:
            md.extend([
                "## 🧠 Distilled Memory State",
                "",
            ])
            if distilled_memory.distilled_entities:
                md.append("### Key Entities")
                for e in distilled_memory.distilled_entities:
                    md.append(f"- **{e.get('name', 'Entity')}** ({e.get('type', 'General')})")
                md.append("")

            if distilled_memory.decisions:
                md.append("### Confirmed Decisions")
                for d in distilled_memory.decisions:
                    md.append(f"- {d}")
                md.append("")

            if distilled_memory.constraints:
                md.append("### Active Constraints")
                for c in distilled_memory.constraints:
                    md.append(f"- {c}")
                md.append("")

            if distilled_memory.open_questions:
                md.append("### Open Questions & Next Steps")
                for q in distilled_memory.open_questions:
                    md.append(f"- {q}")
                md.append("")

        # 2. Knowledge Graph Subgraph
        if subgraph and subgraph.nodes:
            md.extend([
                "## 🕸️ Knowledge Graph Subgraph",
                f"**Entities ({len(subgraph.nodes)}) | Relationships ({len(subgraph.edges)})**",
                "",
            ])
            for n in subgraph.nodes[:10]:
                labels_str = ":".join(n.labels)
                name = n.properties.get("name", n.id)
                md.append(f"- `(:{labels_str} {{name: '{name}'}})`")
            if len(subgraph.nodes) > 10:
                md.append(f"- *...and {len(subgraph.nodes) - 10} more nodes*")
            md.append("")

        # 3. Attached Media Assets
        if media_index and media_index.assets:
            md.extend([
                "## 🎙️ Attached Multimodal Media",
                "",
            ])
            for a in media_index.assets:
                md.append(f"### {a.modality.title()}: `{a.filename}`")
                if a.summary:
                    md.append(f"> **Summary**: {a.summary}")
                transcript = a.extracted_content.get("transcript")
                if transcript:
                    md.append(f"> **Transcript**: *{transcript}*")
                ocr = a.extracted_content.get("ocr_text")
                if ocr:
                    md.append(f"> **Extracted Text**: `{ocr}`")
                md.append("")

        # 4. Conversation History
        md.extend([
            "## 💬 Conversational Transcript",
            "",
        ])
        for msg in messages:
            role_header = f"### {msg.role.upper()}"
            if msg.timestamp:
                role_header += f" *({msg.timestamp})*"
            md.append(role_header)
            md.append(msg.content)
            md.append("")

        return "\n".join(md)
