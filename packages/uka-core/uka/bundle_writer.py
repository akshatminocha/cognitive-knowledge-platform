"""
Universal Knowledge Artifact (UKA) — Bundle Writer.

Packages heterogeneous multimodal data, graph topologies, vector chunks,
and conversational memory into a compressed, content-addressed .uka (ZIP) archive.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from uka.models import (
    UKABundleData,
    UKAManifest,
    UKASubgraph,
    UKAVectorChunk,
    UKAMediaIndex,
    UKADistilledMemory,
    UKAMessage,
)

logger = logging.getLogger(__name__)


def compute_sha256(data: bytes | str) -> str:
    """Compute sha256 checksum string for bytes or text."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


class UKABundleWriter:
    """
    Constructs and streams a canonical .uka container archive with full
    cryptographic integrity verification and dual-layer layout.
    """

    def __init__(self, compression: int = zipfile.ZIP_DEFLATED) -> None:
        self.compression = compression

    def write(self, bundle: UKABundleData, output_path: str | Path) -> Path:
        """
        Write the bundle data into a .uka archive at output_path.
        Uses atomic file writing (writes to .tmp before atomic rename).
        """
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        # 1. Prepare files and calculate checksums
        file_buffers: dict[str, bytes] = {}
        total_uncompressed_bytes = 0

        # Layer 1: context.md
        context_bytes = bundle.context_md.encode("utf-8")
        file_buffers["context.md"] = context_bytes
        total_uncompressed_bytes += len(context_bytes)

        # Layer 1: ontology/schema.yaml
        if bundle.schema_yaml:
            schema_bytes = bundle.schema_yaml.encode("utf-8")
            file_buffers["ontology/schema.yaml"] = schema_bytes
            total_uncompressed_bytes += len(schema_bytes)

        # Conversations
        messages_json = json.dumps([m.model_dump() for m in bundle.messages], indent=2)
        messages_bytes = messages_json.encode("utf-8")
        file_buffers["conversations/transcript.json"] = messages_bytes
        total_uncompressed_bytes += len(messages_bytes)

        if bundle.distilled_memory:
            distilled_json = json.dumps(bundle.distilled_memory.model_dump(), indent=2)
            distilled_bytes = distilled_json.encode("utf-8")
            file_buffers["conversations/distilled_memory.json"] = distilled_bytes
            total_uncompressed_bytes += len(distilled_bytes)

        # Layer 2: Graph
        if bundle.subgraph:
            subgraph_json = json.dumps(bundle.subgraph.model_dump(), indent=2)
            subgraph_bytes = subgraph_json.encode("utf-8")
            file_buffers["graph/subgraph.json"] = subgraph_bytes
            total_uncompressed_bytes += len(subgraph_bytes)

            cypher_cql = bundle.subgraph.to_cypher()
            cypher_bytes = cypher_cql.encode("utf-8")
            file_buffers["graph/cypher_import.cql"] = cypher_bytes
            total_uncompressed_bytes += len(cypher_bytes)

        # Layer 2: Vectors
        if bundle.vector_chunks:
            chunks_json = json.dumps([c.model_dump() for c in bundle.vector_chunks], indent=2)
            chunks_bytes = chunks_json.encode("utf-8")
            file_buffers["vectors/chunks.json"] = chunks_bytes
            total_uncompressed_bytes += len(chunks_bytes)

        if bundle.embeddings_bin:
            file_buffers["vectors/embeddings.bin"] = bundle.embeddings_bin
            total_uncompressed_bytes += len(bundle.embeddings_bin)

        # Multimodal Media: media/index.json + raw binary files
        if bundle.media_index:
            media_index_json = json.dumps(bundle.media_index.model_dump(), indent=2)
            media_index_bytes = media_index_json.encode("utf-8")
            file_buffers["media/index.json"] = media_index_bytes
            total_uncompressed_bytes += len(media_index_bytes)

        for fname, raw_bytes in bundle.media_files.items():
            rel_path = f"media/{fname}"
            file_buffers[rel_path] = raw_bytes
            total_uncompressed_bytes += len(raw_bytes)

        # 2. Build Content Hashes & Statistics for Manifest
        hashes: dict[str, str] = {}
        for rel_path, data in file_buffers.items():
            hashes[rel_path] = compute_sha256(data)

        stats = {
            "total_turns": len(bundle.messages),
            "graph_nodes": len(bundle.subgraph.nodes) if bundle.subgraph else 0,
            "graph_edges": len(bundle.subgraph.edges) if bundle.subgraph else 0,
            "vector_chunks": len(bundle.vector_chunks),
            "media_assets": len(bundle.media_files),
            "uncompressed_bytes": total_uncompressed_bytes,
        }

        # Update Manifest
        manifest = bundle.manifest.model_copy(
            update={
                "content_hashes": hashes,
                "stats": stats,
            }
        )
        manifest_bytes = json.dumps(manifest.model_dump(), indent=2).encode("utf-8")
        file_buffers["manifest.json"] = manifest_bytes

        # 3. Write ZIP atomically
        tmp_fd, tmp_path_str = tempfile.mkstemp(
            prefix="uka_",
            suffix=".tmp",
            dir=str(out_p.parent),
        )
        os.close(tmp_fd)
        tmp_path = Path(tmp_path_str)

        try:
            with zipfile.ZipFile(tmp_path, "w", self.compression) as zf:
                # Always write manifest.json as first entry for fast streaming reads
                zf.writestr("manifest.json", file_buffers["manifest.json"])

                for rel_path, content in file_buffers.items():
                    if rel_path != "manifest.json":
                        zf.writestr(rel_path, content)

            # Atomic replace
            tmp_path.replace(out_p)
            logger.info(f"Successfully packaged UKA bundle: {out_p} ({stats['uncompressed_bytes']} bytes)")
            return out_p
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
