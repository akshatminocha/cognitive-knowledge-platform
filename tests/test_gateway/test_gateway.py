"""Tests for GatewayClient — init, config, rate limiter integration."""

from __future__ import annotations

import pytest

from ai_gateway.gateway import GatewayClient
from ai_gateway.config import GatewayConfig, RateLimitConfig, BudgetConfig, CacheConfig


class TestGatewayClientInit:
    """Verify GatewayClient initialization and config binding."""

    def test_default_config(self):
        """GatewayClient should initialise with sensible defaults."""
        gw = GatewayClient()
        assert gw.config.default_model is not None
        assert gw.config.rate_limits is not None
        assert gw.config.budget is not None

    def test_custom_config(self):
        """GatewayClient should accept a custom GatewayConfig."""
        cfg = GatewayConfig(default_model="gpt-4o")
        gw = GatewayClient(config=cfg)
        assert gw.config.default_model == "gpt-4o"

    def test_config_model_dump(self):
        """Config should be serializable via Pydantic model_dump (used by /diagnostics)."""
        gw = GatewayClient()
        dump = gw.config.model_dump()
        assert isinstance(dump, dict)
        assert "default_model" in dump
        assert "rate_limits" in dump

    def test_model_registry_populated(self):
        """Default model registry should contain at least one model."""
        gw = GatewayClient()
        assert len(gw._model_registry) > 0

    def test_resolve_model_default(self):
        """_resolve_model with None should return the config default."""
        gw = GatewayClient()
        assert gw._resolve_model(None) == gw.config.default_model

    def test_resolve_model_override(self):
        """_resolve_model with an explicit model should return that model."""
        gw = GatewayClient()
        assert gw._resolve_model("claude-3-opus") == "claude-3-opus"


class TestRateLimiter:
    """Verify rate limiter initialises from config."""

    def test_rate_limiter_created(self):
        """Rate limiter should be created during GatewayClient init."""
        gw = GatewayClient()
        assert gw._rate_limiter is not None

    def test_budget_manager_created(self):
        """Budget manager should be created during GatewayClient init."""
        gw = GatewayClient()
        assert gw._budget is not None

    def test_cache_created(self):
        """Response cache should be created during GatewayClient init."""
        gw = GatewayClient()
        assert gw._cache is not None
