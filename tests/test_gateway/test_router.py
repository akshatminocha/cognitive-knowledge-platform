"""
Tests for ModelCascadeRouter — Complexity Classifier, Intent Gating, and Graceful Cascade (BYOK).
"""

from __future__ import annotations

import os
import pytest

from ai_gateway.router import (
    ComplexityTier,
    IntentType,
    ModelCascadeRouter,
    RoutingDecision,
)
from ai_gateway.gateway import GatewayClient


class TestModelCascadeRouter:
    """Test suite for Smart Model Cascade Router and Intent Gating."""

    @pytest.fixture
    def router(self) -> ModelCascadeRouter:
        return ModelCascadeRouter()

    def test_classify_tier_1_flash(self, router: ModelCascadeRouter):
        """Simple greetings and factual single-hop queries should route to Tier 1."""
        queries = [
            "Hello there!",
            "What is diabetes?",
            "List all doctors",
            "Define hypertension",
        ]
        for q in queries:
            tier, reason = router.classify_complexity(q)
            assert tier == ComplexityTier.TIER_1
            assert "Tier 1" in reason

    def test_classify_tier_2_pro(self, router: ModelCascadeRouter):
        """Analytical, comparative, and multi-step queries should route to Tier 2."""
        queries = [
            "Compare the adverse effects of Metformin and Insulin in type 2 diabetes",
            "Analyze the correlation between dosage and patient recovery time",
            "What is the difference between stage 1 and stage 2 hypertension?",
        ]
        for q in queries:
            tier, reason = router.classify_complexity(q)
            assert tier == ComplexityTier.TIER_2
            assert "Tier 2" in reason

    def test_classify_tier_3_frontier(self, router: ModelCascadeRouter):
        """Deep multi-hop synthesis, clinical trial design, or complex code queries should route to Tier 3."""
        queries = [
            "Synthesize a differential diagnosis and multi-hop causality analysis for patient PAT-001 presenting with atypical symptoms",
            "Develop an architectural blueprint for a distributed clinical trial protocol design",
        ]
        for q in queries:
            tier, reason = router.classify_complexity(q)
            assert tier == ComplexityTier.TIER_3
            assert "Tier 3" in reason

    def test_intent_graph_rag(self, router: ModelCascadeRouter):
        """Queries mentioning patient, disease, medication, graph, etc., should trigger GRAPH_RAG."""
        queries = [
            "What medications is patient PAT-001 currently prescribed?",
            "Show me all patients diagnosed with lymphoma in the oncology records",
            "Search the knowledge base for clinical trial contraindications",
        ]
        for q in queries:
            intent, _ = router.classify_intent(q)
            assert intent == IntentType.GRAPH_RAG

    def test_intent_open_domain_bypass(self, router: ModelCascadeRouter):
        """Open-domain coding, drafting, or greeting tasks should bypass graph tools."""
        queries = [
            "Write a python script to sort a list of numbers",
            "Draft an email to our engineering team announcing the v3 launch",
            "Tell me a joke about computer science",
            "Hello, who are you?",
        ]
        for q in queries:
            intent, _ = router.classify_intent(q)
            assert intent == IntentType.OPEN_DOMAIN

    def test_route_query_auto(self, router: ModelCascadeRouter):
        """Routing with model='auto' produces a complete RoutingDecision."""
        decision = router.route_query(
            "Compare the efficacy of Drug A versus Drug B",
            requested_model="auto",
        )
        assert isinstance(decision, RoutingDecision)
        assert decision.tier == ComplexityTier.TIER_2
        assert decision.selected_model in ["gemini-2.5-pro", "gemini-2.5-flash", "gpt-4o-mini"]
        assert decision.original_requested_model == "auto"

    def test_graceful_cascade_missing_key(self, router: ModelCascadeRouter, monkeypatch):
        """When requested model lacks an API key, router gracefully cascades to an available model."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "mock-gemini-key")

        decision = router.route_query(
            "Analyze clinical trial protocols",
            requested_model="claude-3-5-sonnet",
        )
        assert decision.fallback_applied is True
        assert decision.fallback_reason is not None
        assert "claude-3-5-sonnet" in decision.fallback_reason
        assert "gemini" in decision.selected_model.lower()


class TestGatewayClientRouterIntegration:
    """Test GatewayClient integration with the router."""

    def test_gateway_has_router(self):
        """GatewayClient should expose a router instance."""
        gw = GatewayClient()
        assert gw.router is not None
        assert isinstance(gw.router, ModelCascadeRouter)

    def test_resolve_model_preserves_compatibility(self):
        """_resolve_model returns string as expected by existing contracts."""
        gw = GatewayClient()
        assert gw._resolve_model(None) == gw.config.default_model
        assert gw._resolve_model("custom-model") == "custom-model"
