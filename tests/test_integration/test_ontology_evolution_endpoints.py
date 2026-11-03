"""
Integration tests for Dynamic Ontology Evolution REST endpoints.
Verifies candidate listing, proposal generation, proposal approval/rejection,
and admin authorization enforcement.
"""

from __future__ import annotations

import httpx
import pytest

from backend.main import app
from backend.auth.service import AuthService, ADMIN_KEY, DEMO_CODE
from ontology_engine.manager import OntologyManager
from ontology_engine.evolution import EvolutionService, EvolutionStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def setup_app_state(tmp_path):
    """Ensure app.state has auth_service and evolution_service initialized."""
    app.state.auth_service = AuthService()
    app.state.ontology_manager = OntologyManager()
    evolution_db = tmp_path / "test_api_evolution.db"
    store = EvolutionStore(db_path=evolution_db)
    app.state.evolution_service = EvolutionService(store=store, ontology_manager=app.state.ontology_manager)
    yield


@pytest.mark.asyncio
async def test_evolution_candidates_endpoints():
    """Test candidate listing, recording, and dismissal."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Get admin and demo tokens
        admin_resp = await client.post("/api/v2/auth/verify", json={"passcode": ADMIN_KEY})
        assert admin_resp.status_code == 200
        admin_token = admin_resp.json()["token"]

        demo_resp = await client.post("/api/v2/auth/verify", json={"passcode": DEMO_CODE})
        assert demo_resp.status_code == 200
        demo_token = demo_resp.json()["token"]

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        demo_headers = {"Authorization": f"Bearer {demo_token}"}

        # 1. List candidates as demo user (allowed to view)
        res = await client.get("/api/v2/ontology/evolution/candidates", headers=demo_headers)
        assert res.status_code == 200
        data = res.json()
        assert "candidates" in data
        assert "clusters" in data
        assert data["total_candidates"] >= 1

        # 2. Record new candidate concept as demo user (forbidden)
        forbidden_resp = await client.post(
            "/api/v2/ontology/evolution/candidates",
            json={"name": "GenomicMarker", "category": "entity", "context": "Sample context"},
            headers=demo_headers,
        )
        assert forbidden_resp.status_code == 403

        # 3. Record new candidate concept as admin (allowed)
        rec_resp = await client.post(
            "/api/v2/ontology/evolution/candidates",
            json={
                "name": "CardiovascularBiomarker",
                "category": "entity",
                "context": "Elevated troponin T as CardiovascularBiomarker",
                "properties": ["troponin_level", "assay_method"],
            },
            headers=admin_headers,
        )
        assert rec_resp.status_code == 200
        assert rec_resp.json()["status"] == "recorded"
        assert rec_resp.json()["candidate"]["name"] == "CardiovascularBiomarker"

        # 4. Dismiss candidate as admin
        dismiss_resp = await client.post(
            "/api/v2/ontology/evolution/candidates/CardiovascularBiomarker/dismiss",
            headers=admin_headers,
        )
        assert dismiss_resp.status_code == 200
        assert dismiss_resp.json()["status"] == "dismissed"


@pytest.mark.asyncio
async def test_evolution_proposals_lifecycle():
    """Test proposal generation, listing, inspection, and rejection."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Get tokens
        admin_resp = await client.post("/api/v2/auth/verify", json={"passcode": ADMIN_KEY})
        admin_token = admin_resp.json()["token"]
        demo_resp = await client.post("/api/v2/auth/verify", json={"passcode": DEMO_CODE})
        demo_token = demo_resp.json()["token"]

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        demo_headers = {"Authorization": f"Bearer {demo_token}"}

        # 1. Generate proposal as demo user (forbidden)
        demo_gen = await client.post(
            "/api/v2/ontology/evolution/proposals/generate",
            json={"schema_name": "healthtech", "cluster_name": "AdverseEvent"},
            headers=demo_headers,
        )
        assert demo_gen.status_code == 403

        # 2. Generate proposal as admin (allowed)
        gen_resp = await client.post(
            "/api/v2/ontology/evolution/proposals/generate",
            json={"schema_name": "healthtech", "cluster_name": "AdverseEvent"},
            headers=admin_headers,
        )
        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert gen_data["status"] == "generated"
        proposal = gen_data["proposal"]
        proposal_id = proposal["proposal_id"]
        assert proposal["concept_name"] == "AdverseEvent"
        assert proposal["status"] == "PENDING"
        assert "diff" in proposal

        # 3. List proposals
        list_resp = await client.get("/api/v2/ontology/evolution/proposals", headers=demo_headers)
        assert list_resp.status_code == 200
        proposals = list_resp.json()["proposals"]
        assert any(p["proposal_id"] == proposal_id for p in proposals)

        # 4. Get proposal details
        get_resp = await client.get(f"/api/v2/ontology/evolution/proposals/{proposal_id}", headers=demo_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["proposal"]["proposal_id"] == proposal_id

        # 5. Reject proposal as admin
        reject_resp = await client.post(
            f"/api/v2/ontology/evolution/proposals/{proposal_id}/reject",
            json={"notes": "Integration test rejection"},
            headers=admin_headers,
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "REJECTED"

        # Verify status changed
        updated_resp = await client.get(f"/api/v2/ontology/evolution/proposals/{proposal_id}", headers=demo_headers)
        assert updated_resp.json()["proposal"]["status"] == "REJECTED"
