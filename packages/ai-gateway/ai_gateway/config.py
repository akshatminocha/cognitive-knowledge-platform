"""
AI Gateway Configuration — Pydantic models for gateway settings.

All configuration can be loaded from YAML files or environment variables.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ModelProvider(str, Enum):
    """Supported LLM providers."""

    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class ModelConfig(BaseModel):
    """Configuration for a single LLM model."""

    model_id: str = Field(description="LiteLLM model identifier (e.g., 'gemini/gemini-2.5-flash')")
    provider: ModelProvider = Field(description="Provider for this model")
    api_key_env: Optional[str] = Field(
        default=None,
        description="Environment variable name containing the API key",
    )
    api_base: Optional[str] = Field(
        default=None,
        description="Custom API base URL (e.g., for Ollama)",
    )
    cost_per_input_token: float = Field(
        default=0.0,
        description="Cost per input token in USD (0 for free tier)",
    )
    cost_per_output_token: float = Field(
        default=0.0,
        description="Cost per output token in USD (0 for free tier)",
    )
    max_tokens: int = Field(default=4096, description="Max output tokens per request")


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    tpm: int = Field(default=100_000, description="Tokens per minute limit")
    rpm: int = Field(default=60, description="Requests per minute limit")
    tpd: int = Field(default=1_000_000, description="Tokens per day limit")
    rpd: int = Field(default=5_000, description="Requests per day limit")


class BudgetConfig(BaseModel):
    """Cost budget configuration."""

    max_budget_usd: float = Field(default=10.0, description="Maximum budget in USD")
    budget_period_days: int = Field(default=30, description="Budget reset period in days")
    warn_at_percent: float = Field(
        default=80.0,
        description="Trigger warning callback at this % of budget consumed",
    )


class CacheConfig(BaseModel):
    """Response caching configuration."""

    enabled: bool = Field(default=True, description="Enable response caching")
    ttl_seconds: int = Field(default=3600, description="Cache TTL in seconds")
    max_entries: int = Field(default=1000, description="Maximum cache entries")
    semantic_enabled: bool = Field(
        default=False,
        description="Enable semantic similarity caching (requires embeddings)",
    )
    semantic_threshold: float = Field(
        default=0.95,
        description="Cosine similarity threshold for semantic cache hits",
    )


class GatewayConfig(BaseSettings):
    """
    Top-level AI Gateway configuration.

    Loads from environment variables with the GATEWAY_ prefix,
    or from a YAML config file.
    """

    model_config_dict: dict = Field(default_factory=dict)

    # Default model to use when none is specified
    default_model: str = Field(
        default="gemini/gemini-2.5-flash",
        description="Default LiteLLM model identifier",
    )

    # Fallback chain: ordered list of model IDs to try on failure
    fallback_chain: list[str] = Field(
        default_factory=lambda: ["gemini/gemini-2.5-flash", "ollama/llama3.2"],
        description="Ordered list of model IDs for fallback",
    )

    # Rate limits (applied globally by default)
    rate_limits: RateLimitConfig = Field(default_factory=RateLimitConfig)

    # Budget controls
    budget: BudgetConfig = Field(default_factory=BudgetConfig)

    # Caching
    cache: CacheConfig = Field(default_factory=CacheConfig)

    # API keys from environment
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")

    model_config = {"env_prefix": "GATEWAY_", "env_file": ".env", "extra": "ignore"}


# ---- Pre-built model registry for common free/open models ----

DEFAULT_MODELS: dict[str, ModelConfig] = {
    "gemini/gemini-2.5-flash": ModelConfig(
        model_id="gemini/gemini-2.5-flash",
        provider=ModelProvider.GEMINI,
        api_key_env="GOOGLE_API_KEY",
        cost_per_input_token=0.0,
        cost_per_output_token=0.0,
        max_tokens=8192,
    ),
    "ollama/llama3.2": ModelConfig(
        model_id="ollama/llama3.2",
        provider=ModelProvider.OLLAMA,
        api_base="http://localhost:11434",
        cost_per_input_token=0.0,
        cost_per_output_token=0.0,
        max_tokens=4096,
    ),
}
