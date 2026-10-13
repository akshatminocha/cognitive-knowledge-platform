"""
AI Gateway — LiteLLM-based Multi-Model Router with full lifecycle management.

Orchestrates:
1. Pre-flight: Rate limit check → Budget check → Cache lookup
2. Routing: Model selection → Provider fallback chain
3. Post-flight: Token recording → Cost tracking → Cache storage
4. Hot-swap: Accepts per-request model override for mid-session model switching

Usage:
    from ai_gateway import GatewayClient

    gateway = GatewayClient()
    response = await gateway.completion(
        messages=[{"role": "user", "content": "Hello"}],
        model="gemini/gemini-2.5-flash",  # Optional override
    )
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator, Optional

import litellm

from ai_gateway.budget import BudgetExhausted, BudgetManager
from ai_gateway.cache import ResponseCache
from ai_gateway.config import DEFAULT_MODELS, GatewayConfig, ModelConfig
from ai_gateway.rate_limiter import RateLimitExceeded, RateLimiter

logger = logging.getLogger(__name__)

# Suppress LiteLLM's verbose logging
litellm.suppress_debug_info = True


class GatewayError(Exception):
    """Base exception for gateway errors."""

    pass


class AllModelsFailed(GatewayError):
    """Raised when all models in the fallback chain fail."""

    def __init__(self, errors: list[tuple[str, Exception]]):
        self.errors = errors
        models = ", ".join(m for m, _ in errors)
        super().__init__(f"All models failed: {models}")


class GatewayClient:
    """
    Production AI Gateway client.

    Wraps LiteLLM's async completion with:
    - Multi-model routing with configurable fallback chains
    - Rate limiting (TPM/RPM/TPD/RPD)
    - Cost budget enforcement
    - Response caching (exact-match with TTL)
    - Hot-swap model switching per request

    This client is STATELESS per request — it does not manage conversation
    history or context. That's the Agent Harness's job.
    """

    def __init__(self, config: Optional[GatewayConfig] = None) -> None:
        self.config = config or GatewayConfig()
        self._model_registry: dict[str, ModelConfig] = dict(DEFAULT_MODELS)

        # Initialize subsystems
        self._rate_limiter = RateLimiter(
            tpm=self.config.rate_limits.tpm,
            rpm=self.config.rate_limits.rpm,
            tpd=self.config.rate_limits.tpd,
            rpd=self.config.rate_limits.rpd,
        )
        self._budget = BudgetManager(
            max_budget_usd=self.config.budget.max_budget_usd,
            budget_period_days=self.config.budget.budget_period_days,
            warn_at_percent=self.config.budget.warn_at_percent,
        )
        self._cache = ResponseCache(
            ttl_seconds=self.config.cache.ttl_seconds,
            max_entries=self.config.cache.max_entries,
        )

        # Set API keys from config into environment (LiteLLM reads from env)
        self._configure_api_keys()

    def _configure_api_keys(self) -> None:
        """Set provider API keys into environment variables for LiteLLM."""
        if self.config.google_api_key:
            os.environ.setdefault("GEMINI_API_KEY", self.config.google_api_key)
        if self.config.openai_api_key:
            os.environ.setdefault("OPENAI_API_KEY", self.config.openai_api_key)
        if self.config.anthropic_api_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", self.config.anthropic_api_key)

    def register_model(self, model_config: ModelConfig) -> None:
        """Register a new model in the gateway's model registry."""
        self._model_registry[model_config.model_id] = model_config
        logger.info(f"Registered model: {model_config.model_id}")

    def _resolve_model(self, model: Optional[str] = None) -> str:
        """Resolve the model to use: explicit override > config default."""
        return model or self.config.default_model

    def _get_model_config(self, model_id: str) -> Optional[ModelConfig]:
        """Look up model config from registry. Returns None if not registered."""
        return self._model_registry.get(model_id)

    async def completion(
        self,
        messages: list[dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        use_cache: bool = True,
        use_fallback: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Send a completion request through the gateway.

        Args:
            messages: Chat messages in OpenAI format.
            model: Model override (enables hot-swap). If None, uses default.
            temperature: Sampling temperature.
            max_tokens: Max output tokens. If None, uses model config default.
            use_cache: Whether to check/populate the cache.
            use_fallback: Whether to try fallback models on failure.
            **kwargs: Additional params passed to LiteLLM.

        Returns:
            LiteLLM response dict with usage metadata.

        Raises:
            RateLimitExceeded: If rate limits are breached.
            BudgetExhausted: If cost budget is exhausted.
            AllModelsFailed: If all models in fallback chain fail.
        """
        target_model = self._resolve_model(model)

        # 1. Pre-flight: Rate limit check
        self._rate_limiter.check_request()

        # 2. Pre-flight: Budget check
        self._budget.check_budget()

        # 3. Pre-flight: Cache lookup
        if use_cache and self.config.cache.enabled:
            cached = self._cache.get(model=target_model, messages=messages)
            if cached is not None:
                logger.debug(f"Cache hit for model={target_model}")
                return cached

        # 4. Build fallback chain
        if use_fallback:
            models_to_try = [target_model]
            for fallback in self.config.fallback_chain:
                if fallback != target_model and fallback not in models_to_try:
                    models_to_try.append(fallback)
        else:
            models_to_try = [target_model]

        # 5. Try each model in the chain
        errors: list[tuple[str, Exception]] = []
        for model_id in models_to_try:
            try:
                response = await self._call_litellm(
                    model=model_id,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )

                # 6. Post-flight: Record tokens and cost
                usage = response.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                self._rate_limiter.record_tokens(prompt_tokens, completion_tokens)

                model_cfg = self._get_model_config(model_id)
                cost_in = model_cfg.cost_per_input_token if model_cfg else 0.0
                cost_out = model_cfg.cost_per_output_token if model_cfg else 0.0
                self._budget.record_usage(
                    model_id=model_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_per_input_token=cost_in,
                    cost_per_output_token=cost_out,
                )

                # 7. Post-flight: Cache the response
                if use_cache and self.config.cache.enabled:
                    self._cache.put(
                        model=target_model,
                        messages=messages,
                        response=response,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )

                # Inject gateway metadata
                response["_gateway"] = {
                    "model_used": model_id,
                    "cache_hit": False,
                    "fallback_used": model_id != target_model,
                }

                return response

            except Exception as e:
                logger.warning(f"Model {model_id} failed: {e}")
                errors.append((model_id, e))
                continue

        raise AllModelsFailed(errors)

    async def _call_litellm(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make the actual LiteLLM async completion call."""
        model_cfg = self._get_model_config(model)

        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        elif model_cfg and model_cfg.max_tokens:
            call_kwargs["max_tokens"] = model_cfg.max_tokens

        if model_cfg and model_cfg.api_base:
            call_kwargs["api_base"] = model_cfg.api_base

        call_kwargs.update(kwargs)

        response = await litellm.acompletion(**call_kwargs)
        return response.model_dump()

    # --- Observability & Diagnostics ---

    def get_usage_summary(self) -> dict[str, Any]:
        """Get comprehensive usage summary across all subsystems."""
        return {
            "rate_limits": self._rate_limiter.get_usage(),
            "budget": self._budget.get_summary(),
            "cache": self._cache.get_stats(),
        }

    def switch_default_model(self, model_id: str) -> None:
        """
        Hot-swap the default model.
        This enables the model-switching feature discussed in architecture.
        """
        logger.info(f"Switching default model: {self.config.default_model} → {model_id}")
        self.config.default_model = model_id
