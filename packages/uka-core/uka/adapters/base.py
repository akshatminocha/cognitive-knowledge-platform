"""
Universal Knowledge Artifact (UKA) — Base Adapter Interface.

Provides foundational ingestion patterns for extracting conversations,
subgraphs, and multimodal media from external AI platforms and agent harnesses
(Claude, Cursor, ChatGPT, Antigravity).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from uka.bundle_writer import UKABundleWriter
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

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """
    Abstract adapter that parses foreign conversational / context formats
    from external agent harnesses and produces a standardized, content-addressed .uka bundle.
    """

    def __init__(self, platform_name: str) -> None:
        self.platform_name = platform_name
        self.writer = UKABundleWriter()

    @abstractmethod
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
        Extract external platform data and package into a .uka container.
        """
        pass

    def harvest(
        self,
        source: str | Path | dict,
        output_path: str | Path,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs: Any,
    ) -> Path:
        """Alias for adapt() for backwards compatibility."""
        return self.adapt(source, output_path, session_id, title, description, **kwargs)

    def build_markdown_context(
        self,
        title: str,
        messages: list[UKAMessage],
        subgraph: Optional[UKASubgraph] = None,
        distilled: Optional[UKADistilledMemory] = None,
    ) -> str:
        """Helper to generate Layer 1 human/LLM-readable markdown context."""
        lines = [f"# {title}", "", f"*Adapted from {self.platform_name}*", ""]

        if distilled and (distilled.key_entities or distilled.confirmed_decisions):
            lines.append("## Executive Context & Distilled Memory")
            if distilled.key_entities:
                lines.append(f"**Key Entities**: {', '.join(distilled.key_entities)}")
            if distilled.confirmed_decisions:
                lines.append("**Confirmed Decisions**:")
                for d in distilled.confirmed_decisions:
                    lines.append(f"- {d}")
            if distilled.open_questions:
                lines.append("**Open Questions**:")
                for q in distilled.open_questions:
                    lines.append(f"- {q}")
            lines.append("")

        if subgraph and subgraph.nodes:
            lines.append("## Active Knowledge Graph Subgraph")
            for node in subgraph.nodes[:20]:
                lbl = node.labels[0] if node.labels else "Entity"
                name = node.properties.get("name") or node.properties.get("title") or node.id
                lines.append(f"- `({lbl}:{name})`")
            if len(subgraph.nodes) > 20:
                lines.append(f"*... and {len(subgraph.nodes) - 20} more entities*")
            lines.append("")

        if messages:
            lines.append("## Conversation Transcript")
            for msg in messages:
                role_header = msg.role.upper()
                lines.append(f"### {role_header}")
                lines.append(msg.content.strip())
                lines.append("")

        return "\n".join(lines).strip()


# Backwards compatibility alias
BaseHarvester = BaseAdapter
