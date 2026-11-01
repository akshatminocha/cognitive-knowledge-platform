"""
Tests for UKA FastMCP Server & Ecosystem Adapters.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from uka.bundle_writer import UKABundleWriter
from uka.models import (
    UKABundleData,
    UKAGraphEdge,
    UKAGraphNode,
    UKAManifest,
    UKAMediaAsset,
    UKAMediaIndex,
    UKAMessage,
    UKASubgraph,
    UKAVectorChunk,
)
from uka.adapters import (
    ClaudeWebAdapter,
    CursorAdapter,
    GenericMarkdownAdapter,
    ClaudeWebHarvester,
)
from uka_mcp.server import (
    uka_export_context,
    uka_get_media,
    uka_get_schema,
    uka_inspect,
    uka_list_entities,
    uka_query_graph,
    uka_search,
)


@pytest.fixture
def sample_uka_bundle(tmp_path: Path) -> Path:
    """Create a canonical test .uka bundle with graph, vectors, and media index."""
    bundle_path = tmp_path / "cardiology_session.uka"

    manifest = UKAManifest(
        artifact_id="uka_cardio_101",
        title="Cardiology & Hypertension Clinical Session",
        description="Comprehensive review of Lisinopril contraindications and clinical trials.",
        modalities=["text", "graph", "vector", "vision"],
    )

    context_md = (
        "# Cardiology & Hypertension Clinical Session\n\n"
        "**Key Findings**: Lisinopril is contraindicated in patients with angioedema.\n\n"
        "## Conversation Transcript\n"
        "### USER\nWhat are the contraindications for Lisinopril?\n\n"
        "### ASSISTANT\nLisinopril is contraindicated in patients with a history of angioedema."
    )

    schema_yaml = (
        "version: '1.0.0'\n"
        "domain: healthtech\n"
        "entities:\n"
        "  Medication:\n"
        "    properties:\n"
        "      name: string\n"
        "  Condition:\n"
        "    properties:\n"
        "      name: string\n"
    )

    messages = [
        UKAMessage(role="user", content="What are the contraindications for Lisinopril?", timestamp="2026-10-18T10:00:00Z"),
        UKAMessage(role="assistant", content="Lisinopril is contraindicated in patients with a history of angioedema.", timestamp="2026-10-18T10:00:05Z"),
    ]

    nodes = [
        UKAGraphNode(id="med_lisinopril", labels=["Medication"], properties={"name": "Lisinopril", "category": "ACE Inhibitor"}),
        UKAGraphNode(id="cond_angioedema", labels=["Condition"], properties={"name": "Angioedema", "icd10": "T78.3"}),
        UKAGraphNode(id="pat_001", labels=["Patient"], properties={"name": "Jane Doe", "mrn": "MRN-99882"}),
    ]

    edges = [
        UKAGraphEdge(id="rel_contra", type="CONTRAINDICATED_IN", source="med_lisinopril", target="cond_angioedema"),
        UKAGraphEdge(id="rel_diagnosed", type="DIAGNOSED_WITH", source="pat_001", target="cond_angioedema"),
    ]

    subgraph = UKASubgraph(nodes=nodes, edges=edges)

    chunks = [
        UKAVectorChunk(
            chunk_id="chunk_cardio_01",
            document_id="doc_trial_88",
            text="Clinical trial NCT002938 evaluated ACE inhibitors including Lisinopril in 450 hypertensive patients.",
            metadata={"source": "clinical_trials", "page": 4},
        ),
        UKAVectorChunk(
            chunk_id="chunk_cardio_02",
            document_id="doc_trial_88",
            text="Secondary outcomes demonstrated significant blood pressure reduction without renal impairment.",
            metadata={"source": "clinical_trials", "page": 12},
        ),
    ]

    media_asset = UKAMediaAsset(
        asset_id="ecg_img_01",
        filename="patient_ecg.png",
        media_type="image/png",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        extracted_content={"ocr_text": "HR: 48 bpm | PR: 160ms | QRS: 88ms"},
    )

    media_index = UKAMediaIndex(assets=[media_asset])

    bundle_data = UKABundleData(
        manifest=manifest,
        context_md=context_md,
        schema_yaml=schema_yaml,
        messages=messages,
        subgraph=subgraph,
        vector_chunks=chunks,
        media_index=media_index,
        media_binaries={"media/patient_ecg.png": b"\x89PNG\r\n\x1a\nfake_image_bytes"},
    )

    writer = UKABundleWriter()
    return writer.write(bundle_data, bundle_path)


# ---------------------------------------------------------------------------
# FastMCP Tool Tests
# ---------------------------------------------------------------------------
def test_mcp_uka_inspect(sample_uka_bundle: Path):
    """uka_inspect should return status valid and parsed manifest metadata."""
    res = uka_inspect(str(sample_uka_bundle))
    assert res["status"] == "valid"
    assert res["manifest"]["artifact_id"] == "uka_cardio_101"
    assert "text" in res["manifest"]["modalities"]
    assert "graph" in res["manifest"]["modalities"]
    assert "contained_files" in res
    assert "context.md" in res["contained_files"]
    assert "graph/subgraph.json" in res["contained_files"]


def test_mcp_uka_export_context(sample_uka_bundle: Path):
    """uka_export_context should return Layer 1 Markdown context string."""
    res = uka_export_context(str(sample_uka_bundle))
    assert isinstance(res, str)
    assert "Cardiology & Hypertension Clinical Session" in res
    assert "Lisinopril is contraindicated" in res


def test_mcp_uka_get_schema(sample_uka_bundle: Path):
    """uka_get_schema should return the Palantir YAML schema string."""
    res = uka_get_schema(str(sample_uka_bundle))
    assert isinstance(res, str)
    assert "domain: healthtech" in res
    assert "Medication:" in res


def test_mcp_uka_search(sample_uka_bundle: Path):
    """uka_search should find matches in vector chunks and transcripts."""
    # Search for term in vector chunk
    res = uka_search(str(sample_uka_bundle), query="ACE inhibitors")
    assert isinstance(res, list)
    assert len(res) > 0
    assert any(m["source"] == "vector_chunk" for m in res)

    # Search for term in transcript
    res_transcript = uka_search(str(sample_uka_bundle), query="angioedema")
    assert isinstance(res_transcript, list)
    assert len(res_transcript) > 0


def test_mcp_uka_query_graph(sample_uka_bundle: Path):
    """uka_query_graph should filter nodes and edges without requiring Neo4j."""
    # Filter by label
    res_meds = uka_query_graph(str(sample_uka_bundle), node_label="Medication")
    assert len(res_meds["nodes"]) == 1
    assert res_meds["nodes"][0]["properties"]["name"] == "Lisinopril"

    # Filter by name
    res_name = uka_query_graph(str(sample_uka_bundle), name_filter="angioedema")
    assert len(res_name["nodes"]) == 1
    assert res_name["nodes"][0]["id"] == "cond_angioedema"


def test_mcp_uka_list_entities(sample_uka_bundle: Path):
    """uka_list_entities should summarize all node entities."""
    entities = uka_list_entities(str(sample_uka_bundle))
    assert len(entities) == 3
    names = [e["properties"].get("name") for e in entities]
    assert "Lisinopril" in names
    assert "Angioedema" in names
    assert "Jane Doe" in names


def test_mcp_uka_get_media(sample_uka_bundle: Path):
    """uka_get_media should retrieve media assets from companion index."""
    assets = uka_get_media(str(sample_uka_bundle))
    assert len(assets) == 1
    assert assets[0]["asset_id"] == "ecg_img_01"
    assert assets[0]["extracted_content"]["ocr_text"] == "HR: 48 bpm | PR: 160ms | QRS: 88ms"


# ---------------------------------------------------------------------------
# Ecosystem Adapter Tests
# ---------------------------------------------------------------------------
def test_claude_web_adapter(tmp_path: Path):
    """ClaudeWebAdapter should turn official Claude conversations JSON into .uka."""
    claude_export = [
        {
            "uuid": "claude_conv_99",
            "name": "Distributed Consensus Algorithm Design",
            "created_at": "2026-04-10T14:20:00Z",
            "chat_messages": [
                {
                    "sender": "human",
                    "text": "How does Raft handle leader election during network partitions?",
                    "created_at": "2026-04-10T14:20:05Z",
                },
                {
                    "sender": "assistant",
                    "text": "In Raft, a leader must receive votes from a strict quorum (majority) of nodes.",
                    "created_at": "2026-04-10T14:20:15Z",
                },
            ],
        }
    ]

    json_path = tmp_path / "conversations.json"
    json_path.write_text(json.dumps(claude_export), encoding="utf-8")

    out_uka = tmp_path / "adapted_claude.uka"
    adapter = ClaudeWebAdapter()
    res_path = adapter.adapt(json_path, out_uka, session_id="claude_conv_99")
    assert res_path.exists()

    # Backwards compatibility check
    assert ClaudeWebHarvester == ClaudeWebAdapter

    # Verify through MCP inspector
    inspect_res = uka_inspect(str(res_path))
    assert inspect_res["status"] == "valid"
    assert inspect_res["manifest"]["title"] == "Distributed Consensus Algorithm Design"


def test_cursor_adapter(tmp_path: Path):
    """CursorAdapter should extract code citations and workspace turns into .uka."""
    chat_log = (
        "### User\n"
        "Can you refactor `packages/agent-harness/agent_harness/runner.py` to support retry logic?\n\n"
        "### Assistant\n"
        "I will update `runner.py` and inspect `packages/ai-gateway/gateway.py` to handle timeouts.\n"
    )

    log_path = tmp_path / "cursor_chat.md"
    log_path.write_text(chat_log, encoding="utf-8")

    out_uka = tmp_path / "adapted_cursor.uka"
    adapter = CursorAdapter()
    res_path = adapter.adapt(log_path, out_uka, title="Cursor Refactoring Session")
    assert res_path.exists()

    inspect_res = uka_inspect(str(res_path))
    assert inspect_res["status"] == "valid"

    # Entities should cite the code files
    entities = uka_list_entities(str(res_path))
    file_names = [e["properties"].get("path") for e in entities if "path" in e["properties"]]
    assert any("runner.py" in str(fn) for fn in file_names)


def test_generic_markdown_adapter(tmp_path: Path):
    """GenericMarkdownAdapter should package markdown documents into .uka."""
    doc_content = (
        "# System Architecture Specification\n\n"
        "## Ingestion Layer\n"
        "Extracts multimodal data from PDF, PPTX, WAV, and PNG files.\n\n"
        "## Ontology Layer\n"
        "Grounds entities in Palantir-style YAML schemas.\n"
    )

    doc_path = tmp_path / "architecture.md"
    doc_path.write_text(doc_content, encoding="utf-8")

    out_uka = tmp_path / "architecture.uka"
    adapter = GenericMarkdownAdapter()
    res_path = adapter.adapt(doc_path, out_uka)
    assert res_path.exists()

    inspect_res = uka_inspect(str(res_path))
    assert inspect_res["status"] == "valid"
    assert "System Architecture Specification" in inspect_res["manifest"]["title"]
