"""
Prompt Builder — Jinja2-based prompt rendering engine.

Loads PromptTemplate objects and renders them with provided variables.
Handles variable validation, defaults, and composition of multiple templates.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from jinja2 import BaseLoader, Environment, TemplateSyntaxError, UndefinedError

from agent_harness.prompts.models import PromptTemplate

logger = logging.getLogger(__name__)


class PromptBuildError(Exception):
    """Raised when a prompt template cannot be rendered."""


class PromptBuilder:
    """
    Jinja2-based prompt rendering engine.

    Takes a PromptTemplate and a dict of variables, validates inputs,
    fills defaults, and renders the final prompt string.

    Usage:
        builder = PromptBuilder()

        prompt = builder.render(
            template=grounded_qa_template,
            variables={
                "domain": "healthtech",
                "schema_prompt": schema.to_schema_prompt(),
                "context_chunks": ["chunk1", "chunk2"],
            },
        )
    """

    def __init__(self) -> None:
        self._env = Environment(
            loader=BaseLoader(),
            # Keep whitespace control clean
            trim_blocks=True,
            lstrip_blocks=True,
            # Fail loudly on undefined variables
            undefined=_StrictUndefined,
        )

    def render(
        self,
        template: PromptTemplate,
        variables: dict[str, Any],
    ) -> str:
        """
        Render a prompt template with the given variables.

        Validates that all required variables are provided,
        fills defaults for optional variables, and renders
        the Jinja2 template.

        Args:
            template: The PromptTemplate to render.
            variables: Dict of variable name → value.

        Returns:
            The rendered prompt string.

        Raises:
            PromptBuildError: If required variables are missing or
                             the template contains syntax errors.
        """
        # 1. Validate required variables
        missing = []
        for var_name in template.get_required_variables():
            if var_name not in variables:
                missing.append(var_name)

        if missing:
            raise PromptBuildError(
                f"Template '{template.name}' is missing required variables: {missing}"
            )

        # 2. Fill defaults for optional variables
        render_vars = dict(template.get_default_values())
        render_vars.update(variables)

        # 3. Render the Jinja2 template
        try:
            jinja_template = self._env.from_string(template.template)
            rendered = jinja_template.render(**render_vars)
        except TemplateSyntaxError as e:
            raise PromptBuildError(
                f"Syntax error in template '{template.name}': {e}"
            ) from e
        except UndefinedError as e:
            raise PromptBuildError(
                f"Undefined variable in template '{template.name}': {e}"
            ) from e

        logger.debug(
            f"Rendered template '{template.name}' v{template.version} "
            f"({len(rendered)} chars)"
        )
        return rendered

    def compose(
        self,
        templates: list[PromptTemplate],
        variables: dict[str, Any],
        separator: str = "\n\n",
    ) -> str:
        """
        Compose multiple templates into a single prompt.

        Renders each template with the shared variables dict and
        joins them with the separator.

        Args:
            templates: List of PromptTemplates to compose (in order).
            variables: Shared variables dict.
            separator: String to join rendered templates.

        Returns:
            The composed prompt string.
        """
        parts = []
        for tmpl in templates:
            rendered = self.render(tmpl, variables)
            parts.append(rendered)

        composed = separator.join(parts)
        logger.debug(
            f"Composed {len(templates)} templates ({len(composed)} chars)"
        )
        return composed


class _StrictUndefined:
    """
    Custom Jinja2 undefined that raises on access.

    This ensures we catch any template variables that were not
    provided in the render call.
    """

    def __init__(self, name: Optional[str] = None, **_kwargs: Any) -> None:
        self._name = name

    def __str__(self) -> str:
        raise UndefinedError(f"Variable '{self._name}' is undefined")

    def __iter__(self) -> Any:
        raise UndefinedError(f"Variable '{self._name}' is undefined")

    def __bool__(self) -> bool:
        raise UndefinedError(f"Variable '{self._name}' is undefined")
