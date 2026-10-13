"""
Prompt Template Models — Pydantic schemas for versioned prompt templates.

Defines the data model for prompt templates that can be loaded from YAML,
composed via Jinja2, and stored in a library for reuse across skills.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class VariableType(str, Enum):
    """Supported variable types for prompt template inputs."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST_STRING = "list[string]"
    DICT = "dict"


class PromptVariable(BaseModel):
    """Definition of a single variable expected by a prompt template."""

    name: str = Field(description="Variable name used in the Jinja2 template")
    type: VariableType = Field(
        default=VariableType.STRING, description="Expected type"
    )
    required: bool = Field(
        default=True, description="Whether this variable must be provided"
    )
    default: Optional[Any] = Field(
        default=None,
        description="Default value if not provided (only valid when required=False)",
    )
    description: str = Field(default="", description="Human-readable description")


class PromptTemplate(BaseModel):
    """
    A versioned, composable prompt template.

    Templates are loaded from YAML files and rendered with Jinja2.
    They serve as reusable building blocks for system prompts,
    extraction prompts, reflection prompts, etc.

    Example YAML:
        name: grounded_qa
        version: "1.2.0"
        description: "Answer questions strictly grounded in retrieved context"
        tags: [retrieval, grounding, qa]
        template: |
          You are a knowledge assistant for the {{ domain }} domain.
          ...
        variables:
          - name: domain
            type: string
            required: true
    """

    name: str = Field(description="Unique template name (e.g., 'grounded_qa')")
    version: str = Field(default="1.0.0", description="Semantic version")
    description: str = Field(default="", description="What this template does")
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for discovery (e.g., ['retrieval', 'qa'])",
    )
    template: str = Field(description="Jinja2 template string")
    variables: list[PromptVariable] = Field(
        default_factory=list,
        description="Variables the template expects",
    )
    author: str = Field(default="system", description="Who created this template")

    def get_variable(self, name: str) -> Optional[PromptVariable]:
        """Look up a variable definition by name."""
        for var in self.variables:
            if var.name == name:
                return var
        return None

    def get_required_variables(self) -> list[str]:
        """Return names of all required variables."""
        return [v.name for v in self.variables if v.required]

    def get_default_values(self) -> dict[str, Any]:
        """Return a dict of variable names to their default values."""
        return {
            v.name: v.default
            for v in self.variables
            if not v.required and v.default is not None
        }
