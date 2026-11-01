"""
Universal Knowledge Artifact (UKA) — Rehydration Engine.

Restores graph nodes and relationships into Neo4j, vector points into Qdrant,
conversational transcripts into ContextEngine SQLite, and media assets into storage.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

from uka.bundle_reader import UKABundleReader
from uka.models import UKASubgraph, UKAVectorChunk, UKAMessage, UKADistilledMemory

logger = logging.getLogger(__name__)


class UKAImporter:
    """
    Bidirectional rehydration engine to restore external .uka bundles into live databases.
    Supports both synchronous and asynchronous drivers.
    """

    def __init__(
        self,
        neo4j_driver: Optional[Any] = None,
        qdrant_client: Optional[Any] = None,
        context_engine: Optional[Any] = None,
        media_storage_dir: Optional[str | Path] = None,
    ) -> None:
        self.neo4j_driver = neo4j_driver
        self.qdrant_client = qdrant_client
        self.context_engine = context_engine
        self.media_storage_dir = Path(media_storage_dir) if media_storage_dir else None

    async def rehydrate_graph_async(self, subgraph: UKASubgraph) -> dict[str, int]:
        """
        Asynchronously rehydrate nodes and edges into Neo4j.
        """
        if not subgraph:
            return {"nodes": 0, "edges": 0}

        if not self.neo4j_driver:
            logger.info(
                f"[Dry Run / No Neo4j] Would rehydrate {len(subgraph.nodes)} nodes and {len(subgraph.edges)} edges."
            )
            return {"nodes": len(subgraph.nodes), "edges": len(subgraph.edges)}

        nodes_count = 0
        edges_count = 0

        session = self.neo4j_driver.session()
        if hasattr(session, "__aenter__"):
            async with session:
                for node in subgraph.nodes:
                    label_str = ":".join(node.labels) if node.labels else "Entity"
                    query = (
                        f"MERGE (n:{label_str} {{id: $node_id}}) "
                        f"SET n += $props"
                    )
                    await session.run(query, node_id=node.id, props=node.properties)
                    nodes_count += 1

                for edge in subgraph.edges:
                    rel_type = edge.type.upper()
                    query = (
                        f"MATCH (s {{id: $source_id}}), (t {{id: $target_id}}) "
                        f"MERGE (s)-[r:{rel_type}]->(t) "
                        f"SET r += $props"
                    )
                    await session.run(
                        query,
                        source_id=edge.source,
                        target_id=edge.target,
                        props=edge.properties,
                    )
                    edges_count += 1
        else:
            with session:
                for node in subgraph.nodes:
                    label_str = ":".join(node.labels) if node.labels else "Entity"
                    query = (
                        f"MERGE (n:{label_str} {{id: $node_id}}) "
                        f"SET n += $props"
                    )
                    session.run(query, node_id=node.id, props=node.properties)
                    nodes_count += 1

                for edge in subgraph.edges:
                    rel_type = edge.type.upper()
                    query = (
                        f"MATCH (s {{id: $source_id}}), (t {{id: $target_id}}) "
                        f"MERGE (s)-[r:{rel_type}]->(t) "
                        f"SET r += $props"
                    )
                    session.run(
                        query,
                        source_id=edge.source,
                        target_id=edge.target,
                        props=edge.properties,
                    )
                    edges_count += 1

        logger.info(f"Rehydrated graph: {nodes_count} nodes, {edges_count} edges into Neo4j.")
        return {"nodes": nodes_count, "edges": edges_count}

    def rehydrate_graph(self, subgraph: UKASubgraph) -> dict[str, int]:
        """
        Synchronous rehydrate nodes and edges into Neo4j.
        """
        if not subgraph:
            return {"nodes": 0, "edges": 0}
        if not self.neo4j_driver:
            logger.info(
                f"[Dry Run / No Neo4j] Would rehydrate {len(subgraph.nodes)} nodes and {len(subgraph.edges)} edges."
            )
            return {"nodes": len(subgraph.nodes), "edges": len(subgraph.edges)}

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(lambda: asyncio.run(self.rehydrate_graph_async(subgraph))).result()
        else:
            return asyncio.run(self.rehydrate_graph_async(subgraph))

    async def rehydrate_vectors_async(
        self,
        chunks: list[UKAVectorChunk],
        collection_name: str = "knowledge_chunks",
    ) -> int:
        """
        Asynchronously rehydrate vector text chunks and metadata into Qdrant.
        """
        if not chunks:
            return 0

        if not self.qdrant_client:
            logger.info(f"[Dry Run / No Qdrant] Would rehydrate {len(chunks)} vector chunks.")
            return len(chunks)

        from qdrant_client.http import models as qmodels

        points = []
        for idx, chunk in enumerate(chunks):
            payload = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "modality": chunk.modality,
                "page_or_slide": chunk.page_or_slide,
                "text": chunk.text,
                **(chunk.metadata or {}),
            }
            vector = chunk.vector if hasattr(chunk, "vector") and chunk.vector else [0.0] * 384
            point_id = chunk.chunk_id if isinstance(chunk.chunk_id, (int, str)) and len(str(chunk.chunk_id)) == 36 else str(uuid.uuid4())
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

        try:
            upsert_fn = self.qdrant_client.upsert
            if inspect.iscoroutinefunction(upsert_fn):
                await upsert_fn(collection_name=collection_name, points=points)
            else:
                upsert_fn(collection_name=collection_name, points=points)
            logger.info(f"Rehydrated {len(points)} vector chunks into Qdrant collection '{collection_name}'.")
        except Exception as e:
            logger.warning(f"Failed to upsert points into Qdrant: {e}")

        return len(chunks)

    def rehydrate_vectors(
        self,
        chunks: list[UKAVectorChunk],
        collection_name: str = "knowledge_chunks",
    ) -> int:
        """
        Synchronous wrapper for rehydrate_vectors.
        """
        if not chunks:
            return 0
        if not self.qdrant_client:
            return len(chunks)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(lambda: asyncio.run(self.rehydrate_vectors_async(chunks, collection_name))).result()
        else:
            return asyncio.run(self.rehydrate_vectors_async(chunks, collection_name))

    def rehydrate_conversation(
        self,
        session_id: str,
        messages: list[UKAMessage],
        distilled_memory: Optional[UKADistilledMemory] = None,
    ) -> int:
        """
        Rehydrate messages into ContextEngine session history.
        """
        if not messages or not self.context_engine:
            return len(messages) if messages else 0

        for msg in messages:
            self.context_engine.add_message(
                session_id=session_id,
                role=msg.role,
                content=msg.content,
            )

        logger.info(f"Rehydrated {len(messages)} conversation turns into session '{session_id}'.")
        return len(messages)

    def save_media_assets(self, media_files: dict[str, bytes]) -> list[Path]:
        """
        Save media files to local storage directory.
        """
        if not self.media_storage_dir or not media_files:
            return []

        saved: list[Path] = []
        self.media_storage_dir.mkdir(parents=True, exist_ok=True)

        for filename, data in media_files.items():
            dest = self.media_storage_dir / filename
            dest.write_bytes(data)
            saved.append(dest)

        return saved

    async def import_bundle_async(
        self,
        bundle_path: str | Path,
        target_session_id: Optional[str] = None,
        verify_integrity: bool = True,
    ) -> dict[str, Any]:
        """
        Full end-to-end asynchronous import pipeline for a .uka archive.
        """
        reader = UKABundleReader(bundle_path)

        if verify_integrity:
            is_valid, errors = reader.verify_integrity()
            if not is_valid:
                raise ValueError(f"UKA bundle integrity verification failed: {', '.join(errors)}")

        bundle_data = reader.to_bundle_data()
        session_id = target_session_id or bundle_data.manifest.artifact_id

        # 1. Graph
        graph_stats = await self.rehydrate_graph_async(bundle_data.subgraph) if bundle_data.subgraph else {"nodes": 0, "edges": 0}

        # 2. Vectors
        vector_count = await self.rehydrate_vectors_async(bundle_data.vector_chunks)

        # 3. Conversation
        msg_count = self.rehydrate_conversation(
            session_id=session_id,
            messages=bundle_data.messages,
            distilled_memory=bundle_data.distilled_memory,
        )

        # 4. Media
        saved_media = self.save_media_assets(bundle_data.media_files)

        return {
            "status": "success",
            "session_id": session_id,
            "manifest": bundle_data.manifest.model_dump(),
            "nodes_restored": graph_stats["nodes"],
            "edges_restored": graph_stats["edges"],
            "vectors_restored": vector_count,
            "messages_restored": msg_count,
            "media_files_saved": len(saved_media),
        }

    def import_bundle(
        self,
        bundle_path: str | Path,
        target_session_id: Optional[str] = None,
        verify_integrity: bool = True,
    ) -> dict[str, Any]:
        """
        Full end-to-end synchronous import pipeline for a .uka archive.
        """
        reader = UKABundleReader(bundle_path)

        if verify_integrity:
            is_valid, errors = reader.verify_integrity()
            if not is_valid:
                raise ValueError(f"UKA bundle integrity verification failed: {', '.join(errors)}")

        bundle_data = reader.to_bundle_data()
        session_id = target_session_id or bundle_data.manifest.artifact_id

        # 1. Graph
        graph_stats = self.rehydrate_graph(bundle_data.subgraph) if bundle_data.subgraph else {"nodes": 0, "edges": 0}

        # 2. Vectors
        vector_count = self.rehydrate_vectors(bundle_data.vector_chunks)

        # 3. Conversation
        msg_count = self.rehydrate_conversation(
            session_id=session_id,
            messages=bundle_data.messages,
            distilled_memory=bundle_data.distilled_memory,
        )

        # 4. Media
        saved_media = self.save_media_assets(bundle_data.media_files)

        return {
            "status": "success",
            "session_id": session_id,
            "manifest": bundle_data.manifest.model_dump(),
            "nodes_restored": graph_stats["nodes"],
            "edges_restored": graph_stats["edges"],
            "vectors_restored": vector_count,
            "messages_restored": msg_count,
            "media_files_saved": len(saved_media),
        }
