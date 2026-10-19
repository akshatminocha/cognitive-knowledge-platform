"""
Generic Markdown & Document Adapter.

Converts standard markdown documents, meeting transcripts, and research notes
into fully qualified Universal Knowledge Artifacts (.uka).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from uka.adapters.base import BaseAdapter
from uka.models import (
    UKABundleData,
    UKADistilledMemory,
    UKAGraphNode,
    UKAManifest,
    UKAMessage,
    UKASubgraph,
    UKAVectorChunk,
)

logger = logging.getLogger(__name__)


class GenericMarkdownAdapter(BaseAdapter):
    """
    Adapter for general Markdown notes, meeting transcripts, and documentation.
    """

    def __init__(self) -> None:
        super().__init__(platform_name="Generic Markdown")

    def adapt(
        self,
        source: str | Path,
        output_path: str | Path,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs: Any,
    ) -> Path:
        """
        Convert Markdown content into a .uka container.
        """
        src_path = Path(source)
        if not src_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {source}")

        raw_text = src_path.read_text(encoding="utf-8")
        cid = session_id or f"doc_{src_path.stem}_{int(datetime.now().timestamp())}"
        h1_match = re.search(r"(?m)^#\s+(.+)$", raw_text)
        ctitle = title or (h1_match.group(1).strip() if h1_match else src_path.stem.replace("_", " ").title())

        # Split markdown into sections
        sections = re.split(r"(?m)^#{1,3}\s+", raw_text)
        chunks: list[UKAVectorChunk] = []
        messages: list[UKAMessage] = []

        # If transcript style (e.g., Speaker: text or User: text)
        dialogue_matches = re.findall(r"(?m)^(?:\*\*)?([A-Za-z0-9_\-\s]+?)(?:\*\*)?:\s*(.+)$", raw_text)
        if len(dialogue_matches) >= 3:
            for speaker, text in dialogue_matches:
                role = "user" if any(k in speaker.lower() for k in ("user", "human", "interviewer", "patient")) else "assistant"
                messages.append(UKAMessage(role=role, content=text.strip(), metadata={"speaker": speaker}))
        else:
            # Fallback to single document turn
            messages.append(UKAMessage(role="system", content=raw_text[:2000]))

        # Chunks for vector indexing
        for idx, sec in enumerate(sections):
            sec_clean = sec.strip()
            if len(sec_clean) > 20:
                chunks.append(
                    UKAVectorChunk(
                        chunk_id=f"sec_{idx}",
                        document_id=cid,
                        text=sec_clean[:1200],
                        metadata={"section_index": idx},
                    )
                )

        # Graph node extraction from headings
        headings = re.findall(r"(?m)^#{1,4}\s+(.+)$", raw_text)
        nodes = [
            UKAGraphNode(
                id=f"sec_node_{i}",
                labels=["DocumentSection"],
                properties={"title": h.strip()},
            )
            for i, h in enumerate(headings[:25])
        ]
        subgraph = UKASubgraph(nodes=nodes, edges=[])

        distilled = UKADistilledMemory(
            key_entities=[h.strip() for h in headings[:10]],
            confirmed_decisions=[],
            open_questions=[],
            context_summary=f"Markdown document '{ctitle}' with {len(chunks)} parsed sections.",
        )

        manifest = UKAManifest(
            artifact_id=f"uka_{cid.replace('-', '_')}",
            title=ctitle,
            description=description or f"Converted markdown document: {src_path.name}",
            modalities=["text", "graph", "vector"],
            source_platform="Generic Markdown",
            stats={
                "sections": len(chunks),
                "headings": len(headings),
                "bytes": len(raw_text.encode("utf-8")),
            },
        )

        bundle_data = UKABundleData(
            manifest=manifest,
            context_md=raw_text,
            messages=messages,
            subgraph=subgraph,
            vector_chunks=chunks,
            distilled_memory=distilled,
        )

        return self.writer.write(bundle_data, output_path)


# Backwards compatibility alias
GenericMarkdownHarvester = GenericMarkdownAdapter
