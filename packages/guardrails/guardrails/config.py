"""
Guardrail Configuration — Pydantic models for configurable guardrail behavior.

All settings can be driven by YAML config or environment variables,
allowing per-domain customization (healthtech vs fintech vs edtech).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DomainType(str, Enum):
    """Supported industry domains for PII/PHI entity profiles."""

    HEALTHTECH = "healthtech"
    FINTECH = "fintech"
    EDTECH = "edtech"
    ADTECH = "adtech"
    ENTERPRISE_OPS = "enterprise_ops"
    GENERAL = "general"


class CustomEntityPattern(BaseModel):
    """A custom entity recognizer pattern for domain-specific PII."""

    entity_type: str = Field(description="Entity type name (e.g., 'MRN', 'IBAN')")
    patterns: list[str] = Field(description="Regex patterns for detection")
    score: float = Field(default=0.85, description="Confidence score for matches")
    context_words: list[str] = Field(
        default_factory=list,
        description="Context words that boost detection confidence",
    )


class DataProtectionConfig(BaseModel):
    """Configuration for PII/PHI/PCI data protection."""

    enabled: bool = Field(default=True, description="Enable PII/PHI masking")
    active_domain: DomainType = Field(
        default=DomainType.HEALTHTECH,
        description="Active industry domain for entity profile selection",
    )
    score_threshold: float = Field(
        default=0.5,
        description="Minimum confidence score for entity detection",
    )
    custom_entities: list[CustomEntityPattern] = Field(
        default_factory=list,
        description="Additional custom entity patterns for domain-specific data",
    )
    mask_format: str = Field(
        default="[{entity_type}_{index}]",
        description="Format string for pseudonymized tokens",
    )


class InputSafetyConfig(BaseModel):
    """Configuration for input safety checks."""

    enabled: bool = Field(default=True, description="Enable prompt injection detection")
    blocked_topics: list[str] = Field(
        default_factory=list,
        description="Topics that should be rejected (e.g., 'competitor analysis')",
    )
    max_input_length: int = Field(
        default=50_000,
        description="Maximum allowed input length in characters",
    )


class ToolSafetyConfig(BaseModel):
    """Configuration for tool input safety (Cypher/SQL AST validation)."""

    enforce_read_only: bool = Field(
        default=True,
        description="Block all write/mutate operations in Cypher and SQL queries",
    )
    allowed_cypher_clauses: list[str] = Field(
        default_factory=lambda: [
            "MATCH", "RETURN", "WHERE", "WITH", "ORDER", "LIMIT",
            "SKIP", "UNWIND", "OPTIONAL", "CALL", "UNION", "AS",
            "BY", "DESC", "ASC", "AND", "OR", "NOT", "IN", "IS",
            "NULL", "TRUE", "FALSE", "CONTAINS", "STARTS", "ENDS",
            "EXISTS", "COUNT", "SUM", "AVG", "MIN", "MAX", "COLLECT",
            "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END",
        ],
        description="Allowed Cypher keywords (read-only subset)",
    )
    blocked_cypher_clauses: list[str] = Field(
        default_factory=lambda: [
            "CREATE", "DELETE", "DETACH", "DROP", "SET", "REMOVE",
            "MERGE", "FOREACH", "LOAD",
        ],
        description="Blocked Cypher keywords (write/mutate operations)",
    )
    blocked_sql_keywords: list[str] = Field(
        default_factory=lambda: [
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
            "CREATE", "REPLACE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
        ],
        description="Blocked SQL keywords",
    )


class OutputSafetyConfig(BaseModel):
    """Configuration for output safety checks."""

    check_groundedness: bool = Field(
        default=True,
        description="Verify that agent responses are grounded in retrieved context",
    )
    min_groundedness_score: float = Field(
        default=0.3,
        description="Minimum overlap score to consider a response grounded",
    )


class GuardrailConfig(BaseSettings):
    """
    Top-level guardrail configuration.

    Loads from environment variables with the GUARDRAILS_ prefix.
    """

    data_protection: DataProtectionConfig = Field(default_factory=DataProtectionConfig)
    input_safety: InputSafetyConfig = Field(default_factory=InputSafetyConfig)
    tool_safety: ToolSafetyConfig = Field(default_factory=ToolSafetyConfig)
    output_safety: OutputSafetyConfig = Field(default_factory=OutputSafetyConfig)

    model_config = {"env_prefix": "GUARDRAILS_", "env_file": ".env", "extra": "ignore"}
