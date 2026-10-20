"""
Universal Knowledge Artifact (UKA) — FastMCP Server.

Exposes portable .uka knowledge containers over the Model Context Protocol (MCP)
to Claude Desktop, Cursor IDE, Antigravity IDE, and external AI agent harnesses.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP
from uka.bundle_reader import UKABundleReader

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "uka-server",
    instructions="Universal Knowledge Artifact (UKA) Server — Inspect, search, and extract knowledge graph subgraphs, vector chunks, and multimodal media from portable .uka archives.",
)


@mcp.tool()
def uka_inspect(bundle_path: str) -> dict[str, Any]:
    """
    Inspect a .uka archive, verify its cryptographic integrity, and return metadata & statistics.

    Args:
        bundle_path: Path to the .uka or .zip container archive.

    Returns:
        Dictionary containing manifest metadata, statistics, and integrity verification status.
    """
    reader = UKABundleReader(bundle_path)
    manifest = reader.read_manifest()
    is_valid, errors = reader.verify_integrity()

    return {
        "status": "valid" if is_valid else "corrupted",
        "integrity_errors": errors,
        "manifest": manifest.model_dump(),
        "contained_files": reader.list_files(),
    }


@mcp.tool()
def uka_export_context(bundle_path: str) -> str:
    """
    Extract the unified Layer 1 Markdown context distillation from a .uka container.
    Ideal for direct prompt injection into Claude, Cursor, or local LLMs.

    Args:
        bundle_path: Path to the .uka archive.

    Returns:
        Complete synthesized Markdown context string.
    """
    reader = UKABundleReader(bundle_path)
    context_md = reader.read_context_markdown()
    if not context_md:
        raise ValueError(f"No context.md found in {bundle_path}")
    return context_md


@mcp.tool()
def uka_get_schema(bundle_path: str) -> str:
    """
    Extract the self-describing domain ontology YAML schema (Palantir-style grounding)
    defining all entity types, relationship rules, and constraints.

    Args:
        bundle_path: Path to the .uka archive.

    Returns:
        YAML schema string of the domain ontology.
    """
    reader = UKABundleReader(bundle_path)
    schema_yaml = reader.read_schema_yaml()
    if not schema_yaml:
        return "No domain ontology schema defined in this artifact."
    return schema_yaml


@mcp.tool()
def uka_search(bundle_path: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Search within a .uka bundle across vector text chunks, conversational turns,
    and multimodal precomputed transcripts.

    Args:
        bundle_path: Path to the .uka archive.
        query: Search term or keyword phrase.
        limit: Maximum number of search results to return.

    Returns:
        List of matching text segments with provenance and confidence ranking.
    """
    reader = UKABundleReader(bundle_path)
    query_lower = query.lower()
    results: list[dict[str, Any]] = []

    # 1. Search Vector Chunks
    chunks = reader.read_vector_chunks()
    for c in chunks:
        if query_lower in c.text.lower():
            results.append({
                "source": "vector_chunk",
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "modality": c.modality,
                "text": c.text,
                "metadata": c.metadata,
            })
            if len(results) >= limit:
                return results

    # 2. Search Transcripts
    messages = reader.read_transcript()
    for idx, msg in enumerate(messages):
        if query_lower in msg.content.lower():
            results.append({
                "source": "transcript",
                "role": msg.role,
                "turn": idx,
                "timestamp": msg.timestamp,
                "text": msg.content[:400],
            })
            if len(results) >= limit:
                return results

    # 3. Search Media Index
    media_idx = reader.read_media_index()
    if media_idx:
        for asset in media_idx.assets:
            content_str = json.dumps(asset.extracted_content).lower()
            if query_lower in content_str or query_lower in asset.summary.lower():
                results.append({
                    "source": "media_index",
                    "filename": asset.filename,
                    "modality": asset.modality,
                    "summary": asset.summary,
                    "extracted_content": asset.extracted_content,
                })
                if len(results) >= limit:
                    return results

    return results


@mcp.tool()
def uka_query_graph(
    bundle_path: str,
    node_label: Optional[str] = None,
    name_filter: Optional[str] = None,
) -> dict[str, Any]:
    """
    Query the knowledge graph topology from `graph/subgraph.json` in a .uka container
    without requiring a live Neo4j instance.

    Args:
        bundle_path: Path to the .uka archive.
        node_label: Filter nodes by label (e.g. 'Patient', 'Disease', 'Medication').
        name_filter: Optional case-insensitive substring match on node name.

    Returns:
        Subgraph topology containing matching nodes, their incident edges, and properties.
    """
    reader = UKABundleReader(bundle_path)
    subgraph = reader.read_subgraph()
    if not subgraph:
        return {"nodes": [], "edges": [], "stats": {"total_nodes": 0, "total_edges": 0}}

    filtered_nodes = []
    matched_ids = set()

    for node in subgraph.nodes:
        if node_label and node_label not in node.labels:
            continue
        if name_filter:
            name = str(node.properties.get("name", node.id)).lower()
            if name_filter.lower() not in name:
                continue
        filtered_nodes.append(node.model_dump())
        matched_ids.add(node.id)

    # Include edges connecting matched nodes
    filtered_edges = []
    for edge in subgraph.edges:
        if edge.source in matched_ids or edge.target in matched_ids:
            filtered_edges.append(edge.model_dump())

    return {
        "nodes": filtered_nodes,
        "edges": filtered_edges,
        "stats": {
            "total_nodes_in_graph": len(subgraph.nodes),
            "total_edges_in_graph": len(subgraph.edges),
            "matched_nodes": len(filtered_nodes),
            "matched_edges": len(filtered_edges),
        },
    }


@mcp.tool()
def uka_list_entities(bundle_path: str) -> list[dict[str, Any]]:
    """
    List all knowledge entities and labels present in the .uka archive.

    Args:
        bundle_path: Path to the .uka archive.

    Returns:
        List of entity nodes with labels, IDs, and key properties.
    """
    reader = UKABundleReader(bundle_path)
    subgraph = reader.read_subgraph()
    if not subgraph or not subgraph.nodes:
        return []

    return [
        {
            "id": n.id,
            "labels": n.labels,
            "name": n.properties.get("name", n.id),
            "properties": n.properties,
        }
        for n in subgraph.nodes
    ]


@mcp.tool()
def uka_get_media(bundle_path: str, asset_id: Optional[str] = None) -> list[dict[str, Any]]:
    """
    Retrieve multimodal companion index data (transcripts, OCR text, slide notes)
    from `media/index.json`.

    Args:
        bundle_path: Path to the .uka archive.
        asset_id: Optional specific asset ID to filter.

    Returns:
        List of media asset descriptors and extracted text.
    """
    reader = UKABundleReader(bundle_path)
    index = reader.read_media_index()
    if not index or not index.assets:
        return []

    if asset_id:
        return [a.model_dump() for a in index.assets if a.asset_id == asset_id]

    return [a.model_dump() for a in index.assets]


def main() -> None:
    """CLI entrypoint for the UKA FastMCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="Universal Knowledge Artifact (UKA) FastMCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (stdio or sse)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host for SSE transport")
    parser.add_argument("--port", type=int, default=8008, help="Port for SSE transport")
    args = parser.parse_args()

    logger.info(f"Starting UKA FastMCP Server ({args.transport} transport)...")
    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
