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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.ingestion.chunking import SemanticChunker, Chunk
from backend.ingestion.loaders import FileLoader, LoadedDocument

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result of ingesting a single file."""

    filename: str
    file_type: str
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
        pipeline = IngestionPipeline(schema_name="healthtech")
        result = await pipeline.ingest_file(Path("patient_records.pdf"))
        print(f"Created {result.chunks_created} chunks, {result.entities_extracted} entities")
    """

    def __init__(
        self,
        schema_name: str = "healthtech",
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> None:
        self.schema_name = schema_name
        self.loader = FileLoader()
        self.chunker = SemanticChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

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

            # 3. Extract entities (via Ontology Engine)
            # TODO: Wire to EntityExtractor
            # extractor = EntityExtractor(schema)
            # for chunk in chunks:
            #     prompt = extractor.build_extraction_prompt(chunk.text)
            #     llm_response = await gateway.generate(prompt)
            #     extraction = extractor.parse_extraction_response(llm_response)
            #     result.entities_extracted += len(extraction.entities)
            #     result.relationships_extracted += len(extraction.relationships)

            # 4. Embed chunks
            # TODO: Wire to embedding model
            # embeddings = embedding_model.embed([chunk.text for chunk in chunks])

            # 5. Store
            # TODO: Wire to MCP servers
            # await retrieval_mcp.upsert_chunks(...)  → Qdrant
            # await graph_mcp.execute_cypher(...)      → Neo4j
            # await tabular_mcp.execute_sql(...)       → PostgreSQL

        except Exception as e:
            logger.error(f"Ingestion error: {e}")
            result.errors.append(str(e))

        result.duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            f"Ingestion complete: {result.filename} — "
            f"{result.chunks_created} chunks, {result.duration_ms:.0f}ms"
        )

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
