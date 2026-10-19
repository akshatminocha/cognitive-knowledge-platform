"""
Cursor IDE Adapter.

Adapts code context, workspace discussions, and edited file references
from Cursor IDE sessions into portable Universal Knowledge Artifacts (.uka).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from uka.adapters.base import BaseAdapter
from uka.models import (
    UKABundleData,
    UKADistilledMemory,
    UKAGraphEdge,
    UKAGraphNode,
    UKAManifest,
    UKAMessage,
    UKASubgraph,
    UKAVectorChunk,
)

logger = logging.getLogger(__name__)


class CursorAdapter(BaseAdapter):
    """
    Adapter for Cursor IDE conversations, workspace sessions, and code context.
    """

    def __init__(self) -> None:
        super().__init__(platform_name="Cursor IDE")

    def adapt(
        self,
        source: str | Path | dict,
        output_path: str | Path,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs: Any,
    ) -> Path:
        """
        Adapt Cursor session into a .uka container.

        `source` can be:
        - A JSON file containing Cursor conversation export
        - A Markdown transcript of a Cursor chat
        - A dictionary with messages and file context
        """
        messages: list[UKAMessage] = []
        files_referenced: set[str] = set()
        cid = session_id or f"cursor_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        ctitle = title or f"Cursor IDE Session: {cid[:8]}"

        if isinstance(source, (str, Path)):
            src_path = Path(source)
            if not src_path.exists():
                raise FileNotFoundError(f"Cursor source file not found: {source}")

            raw = src_path.read_text(encoding="utf-8")
            if src_path.suffix.lower() == ".json":
                data = json.loads(raw)
                if isinstance(data, list):
                    raw_msgs = data
                else:
                    raw_msgs = data.get("messages", [])
                    ctitle = title or data.get("title", ctitle)

                for idx, m in enumerate(raw_msgs):
                    role = m.get("role", "user")
                    text = m.get("content", "")
                    messages.append(UKAMessage(role=role, content=text, metadata={"index": idx}))
            else:
                # Parse markdown formatted chat
                blocks = re.split(r"(?m)^(?:###|##|\*\*)\s*(User|Assistant|Human|AI|Claude|Cursor)\b[:*]*\s*", raw)
                if len(blocks) > 1:
                    for i in range(1, len(blocks), 2):
                        role_str = blocks[i].lower()
                        role = "user" if role_str in ("user", "human") else "assistant"
                        text = blocks[i + 1].strip() if (i + 1) < len(blocks) else ""
                        messages.append(UKAMessage(role=role, content=text))
                else:
                    messages.append(UKAMessage(role="user", content=raw))
        elif isinstance(source, dict):
            raw_msgs = source.get("messages", [])
            ctitle = title or source.get("title", ctitle)
            for idx, m in enumerate(raw_msgs):
                messages.append(UKAMessage(role=m.get("role", "user"), content=m.get("content", "")))

        # Detect referenced files and functions
        for msg in messages:
            # File references like `path/to/file.py` or `src/component.tsx`
            file_matches = re.findall(r"`([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]{1,6})`", msg.content)
            for fm in file_matches:
                if "/" in fm or "\\" in fm or fm.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".md")):
                    files_referenced.add(fm)

        # Build graph nodes for referenced files
        nodes: list[UKAGraphNode] = []
        edges: list[UKAGraphEdge] = []

        session_node = UKAGraphNode(
            id=cid,
            labels=["CursorSession"],
            properties={"title": ctitle, "platform": "Cursor IDE"},
        )
        nodes.append(session_node)

        for idx, filepath in enumerate(sorted(files_referenced)[:50]):
            f_id = f"file_{idx}"
            file_node = UKAGraphNode(
                id=f_id,
                labels=["SourceFile"],
                properties={"path": filepath, "extension": Path(filepath).suffix},
            )
            nodes.append(file_node)
            edges.append(
                UKAGraphEdge(
                    id=f"edge_ref_{idx}",
                    type="REFERENCES_FILE",
                    source=cid,
                    target=f_id,
                )
            )

        subgraph = UKASubgraph(nodes=nodes, edges=edges)

        # Vector chunks
        chunks = [
            UKAVectorChunk(
                chunk_id=f"cursor_chunk_{i}",
                document_id=cid,
                text=m.content[:1000],
                metadata={"role": m.role},
            )
            for i, m in enumerate(messages)
            if len(m.content.strip()) > 30
        ]

        distilled = UKADistilledMemory(
            key_entities=list(files_referenced)[:15],
            confirmed_decisions=[],
            open_questions=[],
            context_summary=f"Cursor IDE workspace session involving {len(files_referenced)} code files.",
        )

        manifest = UKAManifest(
            artifact_id=f"uka_{cid.replace('-', '_')}",
            title=ctitle,
            description=description or f"Cursor IDE chat and code context adapted into UKA.",
            modalities=["text", "graph", "vector"],
            source_platform="Cursor IDE",
            stats={
                "message_count": len(messages),
                "referenced_files": len(files_referenced),
                "node_count": len(nodes),
            },
        )

        context_md = self.build_markdown_context(
            title=ctitle,
            messages=messages,
            subgraph=subgraph,
            distilled=distilled,
        )

        bundle_data = UKABundleData(
            manifest=manifest,
            context_md=context_md,
            messages=messages,
            subgraph=subgraph,
            vector_chunks=chunks,
            distilled_memory=distilled,
        )

        return self.writer.write(bundle_data, output_path)


# Backwards compatibility alias
CursorHarvester = CursorAdapter
