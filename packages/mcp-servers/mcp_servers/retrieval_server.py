"""
Retrieval MCP Server — Qdrant FastMCP tool server.

Exposes vector similarity search against Qdrant as MCP tools.
Supports dense search, filtered search, and collection management.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Qdrant connection settings (from environment)
# ---------------------------------------------------------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_COLLECTION = os.getenv("QDRANT_DEFAULT_COLLECTION", "knowledge_chunks")
DEFAULT_VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", "384"))  # all-MiniLM-L6-v2


# ---------------------------------------------------------------------------
# Lifespan: manage the Qdrant async client
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(server: FastMCP):
    """Create and tear down the Qdrant async client."""
    client = AsyncQdrantClient(url=QDRANT_URL)
    try:
        # Verify connectivity
        collections = await client.get_collections()
        logger.info(
            f"Connected to Qdrant at {QDRANT_URL} "
            f"({len(collections.collections)} collections)"
        )
        server.state["qdrant"] = client
        yield
    finally:
        await client.close()
        logger.info("Qdrant connection closed")


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="retrieval-mcp",
    description="Qdrant Vector Store — Semantic similarity search for RAG retrieval",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@mcp.tool()
async def semantic_search(
    query_vector: list[float],
    collection: str | None = None,
    limit: int = 5,
    score_threshold: float | None = None,
    metadata_filter: dict[str, Any] | None = None,
) -> list[dict]:
    """
    Search for semantically similar chunks using a query vector.

    Args:
        query_vector: The embedding vector to search with.
        collection: Collection name (defaults to 'knowledge_chunks').
        limit: Maximum number of results (default 5).
        score_threshold: Minimum similarity score (0-1). None = no threshold.
        metadata_filter: Optional metadata filter dict, e.g. {"domain": "healthtech"}.

    Returns:
        A list of matching chunks with scores and metadata.

    Example:
        semantic_search(
            query_vector=[0.1, 0.2, ...],
            limit=5,
            metadata_filter={"entity_type": "Patient"}
        )
    """
    client: AsyncQdrantClient = mcp.state["qdrant"]
    target_collection = collection or DEFAULT_COLLECTION

    # Build filter if metadata_filter provided
    qdrant_filter = None
    if metadata_filter:
        conditions = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in metadata_filter.items()
        ]
        qdrant_filter = Filter(must=conditions)

    results = await client.search(
        collection_name=target_collection,
        query_vector=query_vector,
        limit=limit,
        score_threshold=score_threshold,
        query_filter=qdrant_filter,
    )

    return [
        {
            "id": str(hit.id),
            "score": hit.score,
            "text": hit.payload.get("text", "") if hit.payload else "",
            "metadata": {
                k: v for k, v in (hit.payload or {}).items() if k != "text"
            },
        }
        for hit in results
    ]


@mcp.tool()
async def list_collections() -> list[dict]:
    """
    List all available Qdrant collections with their details.

    Returns:
        A list of collection info dicts with name, vector size, and point count.
    """
    client: AsyncQdrantClient = mcp.state["qdrant"]
    collections = await client.get_collections()

    result = []
    for col in collections.collections:
        info = await client.get_collection(col.name)
        result.append({
            "name": col.name,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "vector_size": (
                info.config.params.vectors.size
                if hasattr(info.config.params.vectors, "size")
                else None
            ),
        })

    return result


@mcp.tool()
async def get_chunk_by_id(
    point_id: str,
    collection: str | None = None,
) -> dict | None:
    """
    Retrieve a specific chunk by its point ID.

    Args:
        point_id: The ID of the point to retrieve.
        collection: Collection name (defaults to 'knowledge_chunks').

    Returns:
        The chunk's text and metadata, or None if not found.
    """
    client: AsyncQdrantClient = mcp.state["qdrant"]
    target_collection = collection or DEFAULT_COLLECTION

    results = await client.retrieve(
        collection_name=target_collection,
        ids=[point_id],
        with_payload=True,
    )

    if not results:
        return None

    point = results[0]
    return {
        "id": str(point.id),
        "text": point.payload.get("text", "") if point.payload else "",
        "metadata": {
            k: v for k, v in (point.payload or {}).items() if k != "text"
        },
    }


@mcp.tool()
async def upsert_chunks(
    chunks: list[dict],
    collection: str | None = None,
) -> dict:
    """
    Upsert text chunks with their embeddings into Qdrant.

    Each chunk dict must have: 'id', 'vector', 'text'.
    Optional: any additional metadata fields.

    Args:
        chunks: List of chunk dicts with id, vector, text, and optional metadata.
        collection: Collection name (defaults to 'knowledge_chunks').

    Returns:
        A summary dict with the number of upserted points.
    """
    client: AsyncQdrantClient = mcp.state["qdrant"]
    target_collection = collection or DEFAULT_COLLECTION

    # Ensure collection exists
    collections = await client.get_collections()
    existing_names = [c.name for c in collections.collections]

    if target_collection not in existing_names:
        vector_size = len(chunks[0]["vector"]) if chunks else DEFAULT_VECTOR_SIZE
        await client.create_collection(
            collection_name=target_collection,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created collection '{target_collection}' (size={vector_size})")

    # Build points
    points = []
    for chunk in chunks:
        payload = {"text": chunk["text"]}
        # Add any extra metadata fields
        for k, v in chunk.items():
            if k not in ("id", "vector", "text"):
                payload[k] = v

        points.append(
            PointStruct(
                id=chunk["id"],
                vector=chunk["vector"],
                payload=payload,
            )
        )

    await client.upsert(
        collection_name=target_collection,
        points=points,
    )

    logger.info(f"Upserted {len(points)} chunks into '{target_collection}'")
    return {"collection": target_collection, "upserted_count": len(points)}
