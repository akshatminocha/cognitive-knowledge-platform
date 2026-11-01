"""
CKP AI Gateway — LiteLLM-based Multi-Model Router & Policy Proxy.

Handles model routing, provider fallbacks, rate limiting (TPM/RPM/TPD/RPD),
cost budgeting (token & $ caps), and semantic response caching.

This package operates strictly OUTSIDE the Agent Harness.
It processes raw LLM API requests — no cognitive logic, no memory, no guardrails.
"""

__version__ = "0.1.0"

from ai_gateway.config import GatewayConfig, ModelConfig, ModelProvider
from ai_gateway.gateway import GatewayClient, GatewayError, AllModelsFailed
from ai_gateway.router import (
    ComplexityTier,
    IntentType,
    ModelCascadeRouter,
    RoutingDecision,
)
from ai_gateway.telemetry import AuditLogEntry, TelemetryStore

__all__ = [
    "GatewayClient",
    "GatewayConfig",
    "ModelConfig",
    "ModelProvider",
    "GatewayError",
    "AllModelsFailed",
    "ComplexityTier",
    "IntentType",
    "ModelCascadeRouter",
    "RoutingDecision",
    "TelemetryStore",
    "AuditLogEntry",
]
