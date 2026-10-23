"""
Integration tests for UKA REST Endpoints:
- GET /api/v2/sessions/{session_id}/export/uka
- POST /api/v2/uka/import
"""

from __future__ import annotations

import io
import uuid
import zipfile
import httpx
import pytest

from backend.main import app
from agent_harness.context_engine import ContextEngine, CanonicalMessage, Role


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_uka_export_and_import_endpoints(tmp_path):
    """Test full round-trip export and import of a .uka bundle via REST API."""
    # Ensure app state has context engine
    if not hasattr(app.state, "context_engine") or app.state.context_engine is None:
        app.state.context_engine = ContextEngine()

    ctx = app.state.context_engine
    test_session_id = f"test-uka-api-{uuid.uuid4().hex[:8]}"
    new_session_id = f"test-rehydrated-{uuid.uuid4().hex[:8]}"

    try:
        ctx.clear_session(test_session_id)
        ctx.add_message(test_session_id, "user", "What are the contraindications for Lisinopril?")
        ctx.add_message(
            CanonicalMessage(
                role=Role.ASSISTANT,
                content="Lisinopril is contraindicated in patients with a history of angioedema.",
                session_id=test_session_id,
                model_used="gemini-2.5-flash",
                metadata={
                    "model_used": "gemini-2.5-flash",
                    "total_steps": 1,
                    "duration_ms": 320.0,
                    "sources": [{
                        "type": "graph",
                        "label": "Knowledge Base: healthtech",
                        "explanation": "Grounded in active healthtech schema knowledge graph and context.",
                        "data": ["Domain: healthtech", "Model: gemini-2.5-flash"]
                    }]
                }
            )
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # 1. Test GET /api/v2/sessions/{session_id}/export/uka
            res_export = await client.get(f"/api/v2/sessions/{test_session_id}/export/uka")
            assert res_export.status_code == 200
            assert "application/x-uka+zip" in res_export.headers.get("content-type", "")
            
            bundle_bytes = res_export.content
            assert len(bundle_bytes) > 0

            # Verify ZIP structure
            with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as zf:
                namelist = zf.namelist()
                assert "manifest.json" in namelist
                assert "context.md" in namelist
                assert "conversations/transcript.json" in namelist
                assert "ontology/schema.yaml" in namelist

            # 1b. Validate full round-trip through UKA FastMCP Server
            from uka_mcp.server import uka_inspect, uka_search, uka_export_context
            bundle_file = tmp_path / f"{test_session_id}.uka"
            bundle_file.write_bytes(bundle_bytes)

            mcp_inspect = uka_inspect(str(bundle_file))
            assert mcp_inspect["status"] == "valid"
            assert mcp_inspect["manifest"]["artifact_id"].startswith(f"uka_{test_session_id}")

            mcp_search = uka_search(str(bundle_file), query="Lisinopril")
            assert len(mcp_search) > 0

            mcp_ctx = uka_export_context(str(bundle_file))
            assert "Lisinopril" in mcp_ctx

            # 2. Test POST /api/v2/uka/import into a brand new session
            ctx.clear_session(new_session_id)
            files = {
                "file": (f"{test_session_id}.uka", bundle_bytes, "application/x-uka+zip"),
            }
            data = {
                "session_id": new_session_id,
            }
            res_import = await client.post("/api/v2/uka/import", files=files, data=data)
            assert res_import.status_code == 200
            import_json = res_import.json()
            assert import_json["status"] == "success"
            assert import_json["session_id"] == new_session_id
            assert import_json["messages_restored"] == 2

            # 3. Verify the rehydrated session now exists in the context engine
            rehydrated_session = ctx.get_session(new_session_id)
            assert rehydrated_session is not None
            assert len(rehydrated_session.messages) == 2
            assert rehydrated_session.messages[0].content == "What are the contraindications for Lisinopril?"
            assert rehydrated_session.messages[1].content == "Lisinopril is contraindicated in patients with a history of angioedema."

            # 4. Test tamper rejection: modify one byte in context.md
            tampered_buffer = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(bundle_bytes), "r") as zin:
                with zipfile.ZipFile(tampered_buffer, "w", zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        data = zin.read(item.filename)
                        if item.filename == "context.md":
                            data = data + b"\nTAMPERED CONTENT INJECTION"
                        zout.writestr(item, data)

            tampered_bytes = tampered_buffer.getvalue()
            files_tampered = {
                "file": ("tampered.uka", tampered_bytes, "application/x-uka+zip"),
            }
            res_tampered = await client.post("/api/v2/uka/import", files=files_tampered, data={"session_id": "tampered-sess"})
            assert res_tampered.status_code == 400
            assert "integrity verification failed" in res_tampered.json()["detail"].lower()
    finally:
        ctx.clear_session(test_session_id)
        ctx.clear_session(new_session_id)
        ctx.clear_session("tampered-sess")
