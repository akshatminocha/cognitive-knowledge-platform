"""
Universal Knowledge Artifact (UKA) — Ecosystem Adapters.

Ingestion adapters for external agent harnesses and platforms (Claude, Cursor, Markdown).
"""

from uka.adapters.base import BaseAdapter, BaseHarvester
from uka.adapters.claude_web import ClaudeWebAdapter, ClaudeWebHarvester
from uka.adapters.cursor_ide import CursorAdapter, CursorHarvester
from uka.adapters.generic_markdown import GenericMarkdownAdapter, GenericMarkdownHarvester

__all__ = [
    "BaseAdapter",
    "BaseHarvester",
    "ClaudeWebAdapter",
    "ClaudeWebHarvester",
    "CursorAdapter",
    "CursorHarvester",
    "GenericMarkdownAdapter",
    "GenericMarkdownHarvester",
]
