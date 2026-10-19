"""
Tests for UKA Core Standard Engine (v0.1).

Verifies bundle creation, DEFLATE ZIP container packaging, SHA-256 integrity,
dual-layer schema reader, selective streaming, and rehydration importer.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
import pytest

from uka.models import (
    UKABundleData,
    UKADistilledMemory,
    UKAGraphEdge,
    UKAGraphNode,
    UKAManifest,
    UKAMediaAsset,
    UKAMediaIndex,
    UKAMessage,
    UKASubgraph,
    UKAVectorChunk,
)
from uka.bundle_writer import UKABundleWriter, compute_sha256
from uka.bundle_reader import UKABundleReader
from uka.importer import UKAImporter


class TestUKAModels:
    """Verify core Pydantic data models and Cypher generation."""

    def test_manifest_creation(self):
        manifest = UKAManifest(
            artifact_id="uka_test_001",
            title="Cardiology Consultation",
            description="Clinical intake test",
            modalities=["text", "graph", "vision"],
        )
        assert manifest.uka_version == "0.1.0"
        assert manifest.artifact_id == "uka_test_001"
        assert "vision" in manifest.modalities
        assert manifest.created_at is not None

    def test_subgraph_to_cypher(self):
        node1 = UKAGraphNode(id="p1", labels=["Patient"], properties={"name": "Alice", "age": 45})
        node2 = UKAGraphNode(id="d1", labels=["Disease"], properties={"name": "Hypertension"})
        edge = UKAGraphEdge(id="e1", type="HAS_DIAGNOSIS", source="p1", target="d1", properties={"confidence": 0.95})
        subgraph = UKASubgraph(nodes=[node1, node2], edges=[edge])

        cypher = subgraph.to_cypher()
        assert "MERGE (n:Patient {id: 'p1'})" in cypher
        assert "MERGE (n:Disease {id: 'd1'})" in cypher
        assert "MERGE (s)-[r:HAS_DIAGNOSIS]->(t)" in cypher

    def test_media_index_structure(self):
        asset = UKAMediaAsset(
            asset_id="img_001",
            filename="ecg_strip.png",
            mime_type="image/png",
            sha256="sha256:abcdef1234567890",
            size_bytes=45000,
            modality="vision",
            summary="Normal sinus rhythm ECG",
            extracted_content={
                "ocr_text": "Heart Rate: 72 bpm",
                "visual_description": "Green rhythm waveform",
            },
        )
        index = UKAMediaIndex(assets=[asset])
        assert len(index.assets) == 1
        assert index.assets[0].extracted_content["ocr_text"] == "Heart Rate: 72 bpm"


class TestUKABundleWriterAndReader:
    """Verify bundling, ZIP packaging, streaming read, and SHA-256 verification."""

    @pytest.fixture
    def sample_bundle_data(self) -> UKABundleData:
        manifest = UKAManifest(
            artifact_id="uka_session_alpha",
            title="Trial Intake Session",
            description="Multi-modal clinical session",
            modalities=["text", "graph", "vector", "vision", "audio"],
        )
        context_md = "# Clinical Summary\nPatient presented with mild symptoms."
        schema_yaml = "version: '1.0'\ndomain: 'healthtech'\nentity_types:\n  Patient: {}\n"
        messages = [
            UKAMessage(role="user", content="Hello doctor", timestamp="2026-10-20T01:00:00Z"),
            UKAMessage(role="assistant", content="Hello, what symptoms do you have?", timestamp="2026-10-20T01:00:05Z"),
        ]
        distilled = UKADistilledMemory(
            distilled_entities=[{"name": "Alice", "type": "Patient"}],
            decisions=["Order blood pressure monitor"],
            constraints=["No beta blockers"],
            open_questions=["Check kidney lab results"],
        )
        subgraph = UKASubgraph(
            nodes=[
                UKAGraphNode(id="p1", labels=["Patient"], properties={"name": "Alice"}),
                UKAGraphNode(id="d1", labels=["Disease"], properties={"name": "Hypertension"}),
            ],
            edges=[
                UKAGraphEdge(id="e1", type="HAS_DIAGNOSIS", source="p1", target="d1", properties={}),
            ],
        )
        chunks = [
            UKAVectorChunk(
                chunk_id="chk_01",
                document_id="doc_intake",
                text="Patient has mild hypertension since 2024.",
                metadata={"confidence": 0.9},
            )
        ]
        media_asset = UKAMediaAsset(
            asset_id="audio_01",
            filename="consultation.wav",
            mime_type="audio/wav",
            sha256=compute_sha256(b"RIFF_FAKE_AUDIO_DATA_BYTES"),
            size_bytes=26,
            modality="audio",
            summary="Patient symptoms consultation",
            extracted_content={"transcript": "Patient: I feel dizzy in the mornings."},
        )
        media_index = UKAMediaIndex(assets=[media_asset])
        media_files = {
            "consultation.wav": b"RIFF_FAKE_AUDIO_DATA_BYTES",
        }

        return UKABundleData(
            manifest=manifest,
            context_md=context_md,
            schema_yaml=schema_yaml,
            messages=messages,
            distilled_memory=distilled,
            subgraph=subgraph,
            vector_chunks=chunks,
            media_index=media_index,
            media_files=media_files,
            embeddings_bin=b"\x00\x00\x80?\x00\x00\x00@",  # Dummy float32 [1.0, 2.0]
        )

    def test_bundle_write_and_read(self, tmp_path: Path, sample_bundle_data: UKABundleData):
        writer = UKABundleWriter()
        out_file = tmp_path / "test_session.uka"

        # 1. Write bundle
        written_path = writer.write(sample_bundle_data, out_file)
        assert written_path.exists()
        assert written_path.stat().st_size > 0

        # Verify it is a valid zip archive
        assert zipfile.is_zipfile(written_path)

        # 2. Read with UKABundleReader
        reader = UKABundleReader(written_path)
        files = reader.list_files()

        # Check required files exist
        assert "manifest.json" in files
        assert "context.md" in files
        assert "ontology/schema.yaml" in files
        assert "conversations/transcript.json" in files
        assert "conversations/distilled_memory.json" in files
        assert "graph/subgraph.json" in files
        assert "graph/cypher_import.cql" in files
        assert "vectors/chunks.json" in files
        assert "vectors/embeddings.bin" in files
        assert "media/index.json" in files
        assert "media/consultation.wav" in files

        # 3. Verify content
        manifest = reader.read_manifest()
        assert manifest.artifact_id == "uka_session_alpha"
        assert manifest.stats["total_turns"] == 2
        assert manifest.stats["graph_nodes"] == 2
        assert manifest.stats["vector_chunks"] == 1
        assert manifest.stats["media_assets"] == 1

        context_md = reader.read_context_markdown()
        assert "Clinical Summary" in context_md

        schema_yaml = reader.read_ontology()
        assert "healthtech" in schema_yaml

        subgraph = reader.read_subgraph()
        assert len(subgraph.nodes) == 2
        assert subgraph.nodes[0].properties["name"] == "Alice"

        chunks = reader.read_vector_chunks()
        assert len(chunks) == 1
        assert chunks[0].chunk_id == "chk_01"

        media_index = reader.read_media_index()
        assert len(media_index.assets) == 1
        assert "dizzy" in media_index.assets[0].extracted_content["transcript"]

        raw_media = reader.get_media_bytes("consultation.wav")
        assert raw_media == b"RIFF_FAKE_AUDIO_DATA_BYTES"

        # 4. Cryptographic integrity check
        is_valid, errors = reader.verify_integrity()
        assert is_valid is True
        assert len(errors) == 0

    def test_tamper_detection(self, tmp_path: Path, sample_bundle_data: UKABundleData):
        writer = UKABundleWriter()
        out_file = tmp_path / "tamper_test.uka"
        writer.write(sample_bundle_data, out_file)

        # Tamper with the archive by modifying a file inside without updating manifest
        tampered_file = tmp_path / "tampered.uka"
        with zipfile.ZipFile(out_file, "r") as zin:
            with zipfile.ZipFile(tampered_file, "w") as zout:
                for item in zin.infolist():
                    content = zin.read(item.filename)
                    if item.filename == "context.md":
                        content = b"# TAMPERED CONTEXT!"
                    zout.writestr(item, content)

        reader = UKABundleReader(tampered_file)
        is_valid, errors = reader.verify_integrity()
        assert is_valid is False
        assert any("context.md" in err for err in errors)


class TestUKAImporter:
    """Verify bidirectional rehydration engine."""

    def test_dry_run_rehydration(self, tmp_path: Path):
        # Create minimal valid bundle
        manifest = UKAManifest(artifact_id="uka_dry_run")
        bundle = UKABundleData(
            manifest=manifest,
            context_md="Minimal context",
            messages=[UKAMessage(role="user", content="Test")],
            subgraph=UKASubgraph(
                nodes=[UKAGraphNode(id="n1", labels=["Test"], properties={})],
                edges=[],
            ),
            vector_chunks=[UKAVectorChunk(chunk_id="c1", document_id="d1", text="Chunk 1")],
            media_files={"sample.png": b"PNG_BYTES"},
        )
        bundle_path = tmp_path / "dry_run.uka"
        UKABundleWriter().write(bundle, bundle_path)

        media_dest = tmp_path / "imported_media"
        importer = UKAImporter(
            neo4j_driver=None,  # Dry run
            qdrant_client=None,  # Dry run
            context_engine=None,  # Dry run
            media_storage_dir=media_dest,
        )

        res = importer.import_bundle(bundle_path)
        assert res["status"] == "success"
        assert res["nodes_restored"] == 1
        assert res["vectors_restored"] == 1
        assert res["messages_restored"] == 1
        assert res["media_files_saved"] == 1
        assert (media_dest / "sample.png").exists()
