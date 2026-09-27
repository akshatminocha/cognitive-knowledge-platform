"""
Ingestion Pipeline — Orchestrates file parsing, chunking, and storage.

End-to-end pipeline:
1. Load file content (via Loaders)
2. Chunk into semantic segments (via Chunker)
3. Extract entities/relationships (via Ontology Engine)
4. Embed chunks (via embedding model)
5. Store in Qdrant (vectors), Neo4j (graph), PostgreSQL (tabular)
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import litellm

from backend.ingestion.chunking import SemanticChunker, Chunk
from backend.ingestion.loaders import FileLoader, LoadedDocument
from ontology_engine.extractor import EntityExtractor, ExtractionResult
from ontology_engine.manager import OntologyManager

logger = logging.getLogger(__name__)

# Embedding model — configurable via environment
EMBEDDING_MODEL = os.getenv("CKP_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("CKP_EMBEDDING_DIMENSIONS", "1536"))


@dataclass
class IngestionResult:
    """Result of ingesting a single file."""

    filename: str
    file_type: str
    status: str = "success"
    chunks_created: int = 0
    entities_extracted: int = 0
    relationships_extracted: int = 0
    vectors_stored: int = 0
    graph_nodes_created: int = 0
    duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


class IngestionPipeline:
    """
    Orchestrates the full ingestion workflow.

    Usage:
        pipeline = IngestionPipeline(
            schema_name="healthtech",
            gateway=gateway_client,
            ontology_manager=ontology_manager,
        )
        result = await pipeline.ingest_file(Path("patient_records.pdf"))
        print(f"Created {result.chunks_created} chunks, {result.entities_extracted} entities")
    """

    def __init__(
        self,
        schema_name: str = "healthtech",
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        gateway: Any = None,
        ontology_manager: Optional[OntologyManager] = None,
        qdrant_client: Any = None,
        neo4j_driver: Any = None,
    ) -> None:
        self.schema_name = schema_name
        self.loader = FileLoader()
        self.chunker = SemanticChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.gateway = gateway
        self.ontology_manager = ontology_manager or OntologyManager()
        self.qdrant_client = qdrant_client
        self.neo4j_driver = neo4j_driver

    async def ingest_file(
        self,
        file_path: Path,
        metadata: Optional[dict] = None,
    ) -> IngestionResult:
        """
        Ingest a single file through the full pipeline.

        Pipeline stages:
        1. Load → Parse file into text
        2. Chunk → Split into semantic segments
        3. Extract → Schema-guided entity extraction (via Ontology Engine)
        4. Embed → Generate vector embeddings
        5. Store → Persist to Qdrant + Neo4j + PostgreSQL
        """
        start = time.monotonic()
        result = IngestionResult(
            filename=file_path.name,
            file_type=file_path.suffix.lstrip("."),
        )

        try:
            # 1. Load
            logger.info(f"Loading: {file_path.name}")
            document = self.loader.load(file_path)
            if not document.content:
                result.errors.append("File produced no content")
                result.status = "error"
                return result

            # 2. Chunk
            logger.info(f"Chunking: {len(document.content)} chars")
            chunks = self.chunker.chunk(document.content, metadata={
                "filename": file_path.name,
                "file_type": result.file_type,
                "schema": self.schema_name,
                **(metadata or {}),
            })
            result.chunks_created = len(chunks)
            logger.info(f"Created {len(chunks)} chunks")

            # 3. Extract entities (via Ontology Engine + LLM)
            extractions: list[ExtractionResult] = []
            try:
                schema = self.ontology_manager.load(self.schema_name)
                extractor = EntityExtractor(schema)

                for chunk in chunks:
                    prompt = extractor.build_extraction_prompt(chunk.text)

                    if self.gateway:
                        llm_response = await self.gateway.completion(
                            messages=[
                                {"role": "system", "content": "You are an entity extraction engine. Respond ONLY with valid JSON."},
                                {"role": "user", "content": prompt},
                            ],
                        )
                        response_text = llm_response["choices"][0]["message"]["content"]
                    else:
                        # No gateway available — skip extraction
                        response_text = '{"entities": [], "relationships": []}'

                    extraction = extractor.parse_extraction_response(response_text, chunk.text)
                    extractions.append(extraction)
                    result.entities_extracted += len(extraction.entities)
                    result.relationships_extracted += len(extraction.relationships)

                logger.info(
                    f"Extracted {result.entities_extracted} entities, "
                    f"{result.relationships_extracted} relationships"
                )
            except Exception as e:
                logger.warning(f"Entity extraction failed (non-fatal): {e}")
                result.errors.append(f"Extraction warning: {e}")

            # 4. Embed chunks
            embeddings: list[list[float]] = []
            try:
                chunk_texts = [chunk.text for chunk in chunks]
                if chunk_texts:
                    embed_response = await litellm.aembedding(
                        model=EMBEDDING_MODEL,
                        input=chunk_texts,
                    )
                    embeddings = [item["embedding"] for item in embed_response.data]
                    logger.info(f"Generated {len(embeddings)} embeddings (dim={len(embeddings[0])})")
            except Exception as e:
                logger.warning(f"Embedding failed (non-fatal): {e}")
                result.errors.append(f"Embedding warning: {e}")

            # 5a. Store vectors in Qdrant
            if embeddings and self.qdrant_client:
                try:
                    from qdrant_client.models import PointStruct, VectorParams, Distance

                    collection_name = "knowledge_chunks"
                    # Ensure collection exists
                    collections = await self.qdrant_client.get_collections()
                    existing = [c.name for c in collections.collections]
                    if collection_name not in existing:
                        await self.qdrant_client.create_collection(
                            collection_name=collection_name,
                            vectors_config=VectorParams(
                                size=len(embeddings[0]),
                                distance=Distance.COSINE,
                            ),
                        )

                    points = []
                    for chunk, embedding in zip(chunks, embeddings):
                        points.append(PointStruct(
                            id=chunk.chunk_id,
                            vector=embedding,
                            payload={
                                "text": chunk.text,
                                "filename": file_path.name,
                                "schema": self.schema_name,
                                **chunk.metadata,
                            },
                        ))

                    await self.qdrant_client.upsert(
                        collection_name=collection_name,
                        points=points,
                    )
                    result.vectors_stored = len(points)
                    logger.info(f"Stored {len(points)} vectors in Qdrant")
                except Exception as e:
                    logger.warning(f"Qdrant storage failed (non-fatal): {e}")
                    result.errors.append(f"Vector storage warning: {e}")

            # 5b. Store entities/relationships in Neo4j
            if extractions and self.neo4j_driver:
                try:
                    async with self.neo4j_driver.session() as session:
                        nodes_created = 0
                        for extraction in extractions:
                            for entity in extraction.entities:
                                props = {k: str(v) for k, v in entity.properties.items()}
                                props["_source_schema"] = self.schema_name
                                props["_source_file"] = file_path.name

                                # MERGE on entity type + first property as identifier
                                label = entity.entity_type.replace(" ", "_")
                                prop_str = ", ".join(f"n.{k} = ${k}" for k in props)
                                cypher = f"MERGE (n:{label} {{name: $name}}) SET {prop_str}" if "name" in props else f"CREATE (n:{label}) SET {prop_str}"

                                if "name" not in props and props:
                                    first_key = next(iter(props))
                                    props["name"] = props[first_key]
                                    prop_str = ", ".join(f"n.{k} = ${k}" for k in props)
                                    cypher = f"MERGE (n:{label} {{name: $name}}) SET {prop_str}"

                                await session.run(cypher, parameters=props)
                                nodes_created += 1

                        result.graph_nodes_created = nodes_created
                        logger.info(f"Created {nodes_created} graph nodes in Neo4j")
                except Exception as e:
                    logger.warning(f"Neo4j storage failed (non-fatal): {e}")
                    result.errors.append(f"Graph storage warning: {e}")

        except Exception as e:
            logger.error(f"Ingestion error: {e}")
            result.errors.append(str(e))
            result.status = "error"

        result.duration_ms = (time.monotonic() - start) * 1000
        if not result.errors:
            result.status = "success"
        elif result.chunks_created > 0:
            result.status = "partial"

        logger.info(
            f"Ingestion complete: {result.filename} — "
            f"{result.chunks_created} chunks, {result.entities_extracted} entities, "
            f"{result.vectors_stored} vectors, {result.duration_ms:.0f}ms"
        )

        return result

    async def ingest_bytes(
        self,
        content: bytes,
        filename: str,
        metadata: Optional[dict] = None,
    ) -> IngestionResult:
        """Ingest from raw bytes (for API file uploads)."""
        import tempfile
        start = time.monotonic()

        # Write to temp file and delegate to ingest_file
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            result = await self.ingest_file(tmp_path, metadata=metadata)
            result.filename = filename  # Use the original filename
        finally:
            tmp_path.unlink(missing_ok=True)

        return result

    async def ingest_directory(
        self,
        dir_path: Path,
        extensions: Optional[list[str]] = None,
    ) -> list[IngestionResult]:
        """Ingest all supported files in a directory."""
        supported = extensions or [".pdf", ".txt", ".md", ".csv", ".json", ".docx"]
        results = []

        for file_path in sorted(dir_path.iterdir()):
            if file_path.is_file() and file_path.suffix.lower() in supported:
                result = await self.ingest_file(file_path)
                results.append(result)

        logger.info(f"Directory ingestion: {len(results)} files processed")
        return results


