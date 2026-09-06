"""
Skill Models — Pydantic schemas for declarative agent skills.

A Skill is a self-contained, reusable package of agent behavior.
It defines the system prompt, tool whitelist, input/output schemas,
guardrail overrides, and few-shot examples for a specific task.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class GuardrailLevel(str, Enum):
    """PII masking strictness levels."""

    OFF = "off"
    STANDARD = "standard"
    STRICT = "strict"


class SkillGuardrails(BaseModel):
    """Guardrail overrides specific to a skill."""

    pii_masking: GuardrailLevel = Field(
        default=GuardrailLevel.STANDARD,
        description="PII masking strictness level",
    )
    max_steps: int = Field(
        default=10, description="Maximum agent steps for this skill"
    )
    max_tokens: int = Field(
        default=4096, description="Maximum tokens per step"
    )
    require_grounding: bool = Field(
        default=True, description="Whether to enforce groundedness checks"
    )


class SkillExample(BaseModel):
    """A few-shot example for a skill."""

    input: dict[str, Any] = Field(description="Example input variables")
    output: dict[str, Any] = Field(description="Expected output")


class SkillInputField(BaseModel):
    """Definition of a single input field for a skill."""

    name: str = Field(description="Field name")
    type: str = Field(default="string", description="Expected type")
    required: bool = Field(default=True)
    default: Optional[Any] = Field(default=None)
    description: str = Field(default="")


class SkillOutputField(BaseModel):
    """Definition of a single output field for a skill."""

    name: str = Field(description="Field name")
    type: str = Field(default="string", description="Expected type")
    description: str = Field(default="")


class Skill(BaseModel):
    """
    A complete, reusable agent skill definition.

    Skills are loaded from YAML files and plug into the AgentRunner
    to customize behavior for specific tasks without code changes.

    Example YAML:
        name: clinical_summary
        version: "1.0.0"
        description: "Summarize a patient's clinical history"
        domain: healthtech
        system_prompt: |
          You are a clinical data analyst...
        tools:
          - graph_query
          - semantic_search
        input_schema:
          - name: patient_id
            type: string
            required: true
        output_schema:
          - name: summary
            type: string
        guardrails:
          pii_masking: strict
          max_steps: 5
    """

    name: str = Field(description="Unique skill name (e.g., 'clinical_summary')")
    version: str = Field(default="1.0.0", description="Semantic version")
    description: str = Field(default="", description="What this skill does")
    domain: str = Field(
        default="general",
        description="Target domain (e.g., 'healthtech', 'fintech', 'general')",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for discovery and routing",
    )
    author: str = Field(default="system", description="Who created this skill")

    # Core behavior
    system_prompt: str = Field(
        description="System prompt that defines the agent's behavior for this skill"
    )
    prompt_template: Optional[str] = Field(
        default=None,
        description="Name of a PromptTemplate to use instead of system_prompt",
    )

    # Tool configuration
    tools: list[str] = Field(
        default_factory=list,
        description="Whitelist of MCP tool names this skill can use",
    )

    # Input/output contracts
    input_schema: list[SkillInputField] = Field(
        default_factory=list,
        description="Expected input fields",
    )
    output_schema: list[SkillOutputField] = Field(
        default_factory=list,
        description="Expected output fields",
    )

    # Guardrail overrides
    guardrails: SkillGuardrails = Field(
        default_factory=SkillGuardrails,
        description="Skill-specific guardrail configuration",
    )

    # Few-shot examples
    examples: list[SkillExample] = Field(
        default_factory=list,
        description="Few-shot examples for the LLM",
    )

    def get_required_inputs(self) -> list[str]:
        """Return names of all required input fields."""
        return [f.name for f in self.input_schema if f.required]

    def get_input_defaults(self) -> dict[str, Any]:
        """Return default values for optional input fields."""
        return {
            f.name: f.default
            for f in self.input_schema
            if not f.required and f.default is not None
        }

    def get_tool_names(self) -> list[str]:
        """Return the list of allowed tool names."""
        return list(self.tools)
