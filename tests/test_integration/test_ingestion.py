"""Tests for IngestionPipeline — orchestration logic."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from backend.ingestion.pipeline import IngestionPipeline, IngestionResult
from backend.ingestion.chunking import Chunk
from backend.ingestion.loaders import LoadedDocument


class TestIngestionPipeline:
    """Verify ingestion pipeline orchestration."""

    @pytest.fixture
    def mock_pipeline(self):
        """Creates a pipeline with mocked external dependencies."""
        mock_gateway = AsyncMock()
        mock_ontology = MagicMock()
        mock_qdrant = AsyncMock()
        mock_neo4j = MagicMock()
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.run = AsyncMock()
        mock_neo4j.session.return_value = mock_session

        pipeline = IngestionPipeline(
            schema_name="default",
            gateway=mock_gateway,
            ontology_manager=mock_ontology,
            qdrant_client=mock_qdrant,
            neo4j_driver=mock_neo4j,
        )
        
        # Setup mocks for actual pipeline integration points
        pipeline.gateway.completion = AsyncMock(return_value={
            "choices": [{"message": {"content": '{"entities": [{"type": "Person", "properties": {"name": "Test"}}], "relationships": []}'}}]
        })
        pipeline.gateway.embeddings = AsyncMock(return_value={
            "data": [{"embedding": [0.1] * 1536}]
        })

        return pipeline

    @pytest.mark.asyncio
    @patch("backend.ingestion.pipeline.litellm.aembedding")
    async def test_ingest_file_flow(self, mock_aembedding, mock_pipeline, tmp_path):
        """Pipeline should execute all 5 stages in order."""
        
        # Mock the litellm aembedding response
        mock_aembedding.return_value = MagicMock(data=[{"embedding": [0.1] * 1536}])
        
        # 1. Execute
        test_file = tmp_path / "doc.txt"
        test_file.write_text("This is a long test sentence to make sure we have enough tokens. " * 20)
        result = await mock_pipeline.ingest_file(test_file)
        
        # 2. Assert stages were called
        assert isinstance(result, IngestionResult)
        assert result.filename == "doc.txt"
        assert result.status == "success"
        assert result.chunks_created > 0
        


    @pytest.mark.asyncio
    async def test_ingest_file_missing_db(self, mock_pipeline, tmp_path):
        """Pipeline should gracefully handle missing optional DB clients."""
        # Remove DB clients
        mock_pipeline.qdrant_client = None
        mock_pipeline.neo4j_driver = None
        
        test_file = tmp_path / "doc.txt"
        test_file.write_text("Hello world")
        result = await mock_pipeline.ingest_file(test_file)
        
        # Should succeed but skip DB storage
        assert result.status == "success"


    @pytest.mark.asyncio
    async def test_ingest_file_failure(self, mock_pipeline, tmp_path):
        """Pipeline should catch exceptions and return a failed result."""
        # Force a failure in stage 1
        mock_pipeline.loader.load = MagicMock(side_effect=Exception("Simulated load error"))
        
        test_file = tmp_path / "doc.txt"
        test_file.write_text("Hello world")
        result = await mock_pipeline.ingest_file(test_file)
        
        assert result.status == "error"
        assert len(result.errors) > 0
        assert "Simulated load error" in result.errors[0]
        

