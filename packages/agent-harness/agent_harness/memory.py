"""
Memory Manager — Short-term and long-term semantic memory.

Provides two memory tiers:
1. Short-term: In-memory buffer for recent conversation context (session-scoped)
2. Long-term: Vector-backed persistent memory for cross-session recall

Long-term memory enables the agent to recall relevant past interactions
even across different sessions, providing continuity and learning.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """A single memory entry — either short-term or long-term."""

    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    query: str = ""  # The original query that produced this memory
    session_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    relevance_score: float = 0.0
    memory_type: str = "short_term"  # "short_term" | "long_term"
    metadata: dict = field(default_factory=dict)


class MemoryManager:
    """
    Two-tier memory system for the agent.

    Short-term memory:
        - In-memory buffer scoped to the current session
        - Automatically evicts oldest entries when the buffer is full
        - Fast lookup, no persistence

    Long-term memory:
        - Backed by Qdrant vector store (via Retrieval MCP server)
        - Persists across sessions and restarts
        - Semantic recall: finds relevant past interactions by meaning

    Usage:
        memory = MemoryManager(max_short_term=50)

        # Store after each interaction:
        await memory.store(
            query="What meds does PAT-001 take?",
            response="Patient PAT-001 takes Metformin 500mg.",
            session_id="session-123",
        )

        # Recall relevant memories for a new query:
        memories = await memory.recall("medication for patient PAT-001")
    """

    def __init__(
        self,
        max_short_term: int = 50,
        long_term_collection: str = "agent_memory",
    ) -> None:
        self.max_short_term = max_short_term
        self.long_term_collection = long_term_collection

        # Short-term: in-memory buffer
        self._short_term: list[MemoryEntry] = []

    async def store(
        self,
        query: str,
        response: str,
        session_id: Optional[str] = None,
    ) -> MemoryEntry:
        """
        Store a query-response pair in memory.

        Always stores in short-term. If short-term buffer is full,
        the oldest entry is promoted to long-term before eviction.
        """
        entry = MemoryEntry(
            content=f"Q: {query}\nA: {response}",
            query=query,
            session_id=session_id,
            memory_type="short_term",
        )

        # Add to short-term buffer
        self._short_term.append(entry)

        # Evict oldest if over capacity
        if len(self._short_term) > self.max_short_term:
            evicted = self._short_term.pop(0)
            await self._promote_to_long_term(evicted)

        logger.debug(
            f"Stored memory (short-term buffer: {len(self._short_term)}/{self.max_short_term})"
        )
        return entry

    async def recall(
        self,
        query: str,
        limit: int = 5,
        include_short_term: bool = True,
        include_long_term: bool = True,
    ) -> list[MemoryEntry]:
        """
        Recall relevant memories for a query.

        Searches both short-term (keyword match) and long-term
        (semantic search via Qdrant) memories, then merges and
        ranks by relevance.
        """
        results: list[MemoryEntry] = []

        # Short-term recall: simple keyword overlap
        if include_short_term:
            st_results = self._recall_short_term(query, limit)
            results.extend(st_results)

        # Long-term recall: semantic search via Qdrant
        # NOTE: Integration point — calls Retrieval MCP server
        if include_long_term:
            lt_results = await self._recall_long_term(query, limit)
            results.extend(lt_results)

        # Deduplicate and sort by relevance
        seen = set()
        unique = []
        for entry in sorted(results, key=lambda e: e.relevance_score, reverse=True):
            if entry.memory_id not in seen:
                seen.add(entry.memory_id)
                unique.append(entry)

        return unique[:limit]

    def _recall_short_term(self, query: str, limit: int) -> list[MemoryEntry]:
        """Keyword-based recall from short-term buffer."""
        query_words = set(query.lower().split())
        scored: list[MemoryEntry] = []

        for entry in self._short_term:
            content_words = set(entry.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                entry_copy = MemoryEntry(
                    memory_id=entry.memory_id,
                    content=entry.content,
                    query=entry.query,
                    session_id=entry.session_id,
                    timestamp=entry.timestamp,
                    relevance_score=overlap / max(len(query_words), 1),
                    memory_type="short_term",
                    metadata=entry.metadata,
                )
                scored.append(entry_copy)

        scored.sort(key=lambda e: e.relevance_score, reverse=True)
        return scored[:limit]

    async def _recall_long_term(self, query: str, limit: int) -> list[MemoryEntry]:
        """
        Semantic recall from long-term vector store.

        NOTE: This is the integration point where we call the Retrieval MCP
        server's semantic_search tool with an embedding of the query.
        For now, returns an empty list — wired during platform integration.
        """
        # TODO: Embed query → call retrieval_server.semantic_search()
        # → convert results to MemoryEntry objects
        return []

    async def _promote_to_long_term(self, entry: MemoryEntry) -> None:
        """
        Promote a short-term memory to long-term storage.

        Embeds the content and upserts into the Qdrant collection.
        """
        entry.memory_type = "long_term"
        # TODO: Embed content → call retrieval_server.upsert_chunks()
        logger.debug(f"Promoted memory {entry.memory_id} to long-term storage")

    def get_short_term_buffer(self) -> list[MemoryEntry]:
        """Return the current short-term memory buffer."""
        return list(self._short_term)

    def clear_short_term(self) -> None:
        """Clear the short-term memory buffer."""
        self._short_term.clear()
        logger.info("Short-term memory cleared")

    def stats(self) -> dict:
        """Return memory statistics."""
        return {
            "short_term_count": len(self._short_term),
            "short_term_capacity": self.max_short_term,
            "long_term_collection": self.long_term_collection,
        }
