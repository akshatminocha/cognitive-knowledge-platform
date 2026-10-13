"""
Prompt Builder Agent — Autonomously creates new prompt templates from natural language.

Takes a plain-English description of what the prompt should do,
examines the existing template library for similar patterns, and generates
a valid PromptTemplate YAML file.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from agent_harness.prompts.models import PromptTemplate, PromptVariable
from agent_harness.prompts.registry import PromptRegistry

logger = logging.getLogger(__name__)


PROMPT_GENERATION_TEMPLATE = """You are a Prompt Builder agent for the Cognitive Knowledge Platform.

Your job is to create a new reusable prompt template based on the user's description.
A prompt template is a Jinja2-based building block used in agent system prompts.

## Existing Templates (for reference)
{existing_templates}

## Jinja2 Syntax Reference
- Variables: {{{{ variable_name }}}}
- Loops: {{% for item in items %}} ... {{% endfor %}}
- Conditionals: {{% if condition %}} ... {{% endif %}}
- Filters: {{{{ value | join(', ') }}}}

## User's Request
{description}

## Output Format
Generate a valid JSON object representing the new prompt template:
{{
  "name": "<snake_case_name>",
  "version": "1.0.0",
  "description": "<clear description>",
  "tags": ["<tag1>", "<tag2>"],
  "template": "<the Jinja2 template string>",
  "variables": [
    {{
      "name": "<var_name>",
      "type": "<string|integer|float|boolean|list[string]|dict>",
      "required": true,
      "description": "<what this variable is>"
    }}
  ]
}}

Respond with ONLY the JSON object, no explanations or markdown fences."""


class PromptBuilderAgent:
    """
    Meta-agent that creates new prompt templates from natural language.

    Usage:
        builder = PromptBuilderAgent(registry=prompt_registry)
        new_template = await builder.create_template(
            description="I need a prompt that makes the agent cite sources in APA format",
            llm_fn=my_llm_function,
        )
    """

    def __init__(self, registry: PromptRegistry) -> None:
        self.registry = registry

    async def create_template(
        self,
        description: str,
        llm_fn: Optional[callable] = None,
    ) -> PromptTemplate:
        """
        Create a new prompt template from a natural language description.

        Args:
            description: Plain-English description of the desired template.
            llm_fn: Async function to call the LLM.
                    Signature: async (prompt: str) -> str

        Returns:
            A validated PromptTemplate object.

        Raises:
            ValueError: If the LLM response cannot be parsed.
        """
        if not llm_fn:
            raise ValueError("llm_fn is required to generate prompt templates")

        # Build context from existing templates
        existing = self.registry.list_all()
        existing_str = "\n".join(
            f"- {t['name']}: {t['description']} (tags: {t['tags']})"
            for t in existing
        ) or "No existing templates."

        prompt = PROMPT_GENERATION_TEMPLATE.format(
            existing_templates=existing_str,
            description=description,
        )

        # Call the LLM
        response = await llm_fn(prompt)

        # Parse the response
        template = self._parse_template_response(response)

        logger.info(f"Generated new template: {template.name}")
        return template

    async def create_and_save(
        self,
        description: str,
        llm_fn: Optional[callable] = None,
    ) -> PromptTemplate:
        """Create a new prompt template and save it to the library."""
        template = await self.create_template(description, llm_fn)
        self.registry.save_template(template)
        return template

    def _parse_template_response(self, response: str) -> PromptTemplate:
        """Parse the LLM's JSON response into a validated PromptTemplate."""
        # Strip markdown fences
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse template JSON: {e}\nResponse: {cleaned}"
            )

        # Build variables
        variables = [
            PromptVariable(
                name=v["name"],
                type=v.get("type", "string"),
                required=v.get("required", True),
                default=v.get("default"),
                description=v.get("description", ""),
            )
            for v in data.get("variables", [])
        ]

        return PromptTemplate(
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            author="prompt_builder_agent",
            template=data["template"],
            variables=variables,
        )
