"""
Semantic Chunking — Split documents into meaningful, overlapping chunks.

Uses a sentence-aware sliding window approach:
1. Split text into sentences
2. Group sentences into chunks of ~chunk_size tokens
3. Add overlap between chunks for context continuity

Each chunk carries metadata (position, source file, etc.) for
downstream traceability.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A single text chunk with metadata."""

    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    index: int = 0  # Position in the sequence
    token_count: int = 0
    metadata: dict = field(default_factory=dict)


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate (~4 chars per token for English)."""
    return len(text) // 4


def _split_sentences(text: str) -> list[str]:
    """
    Split text into sentences using regex.

    Handles common abbreviations and decimal numbers to avoid
    false sentence breaks.
    """
    # Replace common abbreviations to avoid false splits
    text = re.sub(r"\b(Dr|Mr|Mrs|Ms|Prof|Sr|Jr|etc|vs|i\.e|e\.g)\.", r"\1<DOT>", text)
    # Don't split on decimal numbers
    text = re.sub(r"(\d)\.([\d])", r"\1<DOT>\2", text)

    # Split on sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text)

    # Restore dots
    sentences = [s.replace("<DOT>", ".") for s in sentences]

    # Filter out empty sentences
    return [s.strip() for s in sentences if s.strip()]


class SemanticChunker:
    """
    Sentence-aware sliding window chunker.

    Groups sentences into chunks of approximately `chunk_size` tokens,
    with `chunk_overlap` tokens of overlap between consecutive chunks.

    Usage:
        chunker = SemanticChunker(chunk_size=512, chunk_overlap=64)
        chunks = chunker.chunk("Long document text here...")
        for chunk in chunks:
            print(f"Chunk {chunk.index}: {chunk.token_count} tokens")
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        min_chunk_size: int = 50,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk(
        self,
        text: str,
        metadata: Optional[dict] = None,
    ) -> list[Chunk]:
        """
        Split text into semantic chunks.

        Returns a list of Chunk objects with metadata.
        """
        if not text.strip():
            return []

        sentences = _split_sentences(text)
        if not sentences:
            return []

        chunks: list[Chunk] = []
        current_sentences: list[str] = []
        current_tokens = 0

        for sentence in sentences:
            sent_tokens = _estimate_tokens(sentence)

            # If adding this sentence exceeds chunk_size, flush the current chunk
            if current_tokens + sent_tokens > self.chunk_size and current_sentences:
                chunk = self._create_chunk(
                    current_sentences, len(chunks), metadata
                )
                chunks.append(chunk)

                # Overlap: keep trailing sentences that fit within chunk_overlap
                overlap_sentences: list[str] = []
                overlap_tokens = 0
                for s in reversed(current_sentences):
                    s_tokens = _estimate_tokens(s)
                    if overlap_tokens + s_tokens <= self.chunk_overlap:
                        overlap_sentences.insert(0, s)
                        overlap_tokens += s_tokens
                    else:
                        break

                current_sentences = overlap_sentences
                current_tokens = overlap_tokens

            current_sentences.append(sentence)
            current_tokens += sent_tokens

        # Flush remaining sentences
        if current_sentences:
            chunk = self._create_chunk(current_sentences, len(chunks), metadata)
            if chunk.token_count >= self.min_chunk_size:
                chunks.append(chunk)
            elif chunks:
                # Merge tiny final chunk with the previous one
                prev = chunks[-1]
                prev.text += " " + chunk.text
                prev.token_count = _estimate_tokens(prev.text)

        logger.debug(
            f"Chunked {len(sentences)} sentences into {len(chunks)} chunks "
            f"(target: {self.chunk_size} tokens, overlap: {self.chunk_overlap})"
        )

        return chunks

    def _create_chunk(
        self,
        sentences: list[str],
        index: int,
        metadata: Optional[dict] = None,
    ) -> Chunk:
        """Create a Chunk from a list of sentences."""
        text = " ".join(sentences)
        return Chunk(
            text=text,
            index=index,
            token_count=_estimate_tokens(text),
            metadata={
                "chunk_index": index,
                **(metadata or {}),
            },
        )
