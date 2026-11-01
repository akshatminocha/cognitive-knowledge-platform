"""
Claude.ai Web Adapter.

Parses official Claude.ai export archives (`conversations.json` and attachments)
and packages them into canonical Universal Knowledge Artifacts (.uka).
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
    UKAGraphNode,
    UKAManifest,
    UKAMessage,
    UKASubgraph,
    UKAVectorChunk,
)

logger = logging.getLogger(__name__)


class ClaudeWebAdapter(BaseAdapter):
    """
    Adapter for official Claude.ai export archives and conversations.json files.
    """

    def __init__(self) -> None:
        super().__init__(platform_name="Claude.ai Web")

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
        Adapt a Claude.ai conversation into a .uka container.

        `source` can be:
        - Path to `conversations.json`
        - A single conversation dict
        """
        conversation: dict = {}

        if isinstance(source, (str, Path)):
            src_path = Path(source)
            if not src_path.exists():
                raise FileNotFoundError(f"Claude source file not found: {source}")

            with open(src_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                # Search by session_id or pick first
                if session_id:
                    matched = next((c for c in data if c.get("uuid") == session_id or c.get("id") == session_id), None)
                    if not matched:
                        raise ValueError(f"Conversation with UUID '{session_id}' not found in {src_path}")
                    conversation = matched
                else:
                    conversation = data[0] if data else {}
            elif isinstance(data, dict):
                conversation = data
        elif isinstance(source, dict):
            conversation = source
        else:
            raise TypeError(f"Unsupported source type: {type(source)}")

        # Extract metadata
        cid = conversation.get("uuid") or conversation.get("id") or session_id or "claude_session"
        ctitle = title or conversation.get("name") or f"Claude.ai Session ({cid[:8]})"
        created_at_raw = conversation.get("created_at")
        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else datetime.now(timezone.utc)

        # Extract turns
        messages: list[UKAMessage] = []
        raw_msgs = conversation.get("chat_messages", []) or conversation.get("messages", [])

        for idx, m in enumerate(raw_msgs):
            sender = m.get("sender") or m.get("role") or "unknown"
            role = "user" if sender.lower() in ("human", "user") else "assistant"
            content = m.get("text") or m.get("content") or ""
            if isinstance(content, list):
                # Claude block format (text + media blocks)
                text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                content = "\n".join(text_parts)

            msg_time = m.get("created_at") or created_at.isoformat()
            messages.append(
                UKAMessage(
                    role=role,
                    content=str(content),
                    timestamp=msg_time,
                    metadata={"index": idx, "sender": sender},
                )
            )

        # Heuristic entity extraction for graph nodes
        entities_found: set[str] = set()
        for msg in messages:
            # Capitalized noun phrases as basic entities
            matches = re.findall(r"\b[A-Z][a-zA-Z0-9_-]{2,}\b", msg.content)
            for match in matches:
                if len(match) > 3 and match not in {"What", "When", "Where", "Which", "This", "That", "Here", "There"}:
                    entities_found.add(match)

        nodes = [
            UKAGraphNode(
                id=f"ent_{i}",
                labels=["Entity"],
                properties={"name": name, "source": "ClaudeWebAdapter"},
            )
            for i, name in enumerate(sorted(entities_found)[:30])
        ]
        subgraph = UKASubgraph(nodes=nodes, edges=[])

        # Generate vector chunks from assistant turns
        chunks = [
            UKAVectorChunk(
                chunk_id=f"chunk_{idx}",
                document_id=cid,
                text=msg.content[:800],
                metadata={"role": msg.role, "turn": idx},
            )
            for idx, msg in enumerate(messages)
            if msg.role == "assistant" and len(msg.content.strip()) > 20
        ]

        # Distilled memory summary
        distilled = UKADistilledMemory(
            key_entities=sorted(entities_found)[:10],
            confirmed_decisions=[],
            open_questions=[],
            context_summary=f"Adapted from Claude.ai web export with {len(messages)} conversational turns.",
        )

        manifest = UKAManifest(
            artifact_id=f"uka_{cid.replace('-', '_')}",
            title=ctitle,
            description=description or f"Claude.ai conversation export adapted into UKA bundle.",
            created_at=created_at.isoformat(),
            modalities=["text", "graph", "vector"],
            source_platform="Claude.ai Web",
            stats={
                "message_count": len(messages),
                "node_count": len(nodes),
                "chunk_count": len(chunks),
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
ClaudeWebHarvester = ClaudeWebAdapter
