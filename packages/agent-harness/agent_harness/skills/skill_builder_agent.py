"""
Skill Builder Agent — Autonomously creates new agent skills from natural language.

Takes a plain-English description of what the user wants the agent to do,
examines the existing skill library for similar templates, and generates
a valid Skill YAML file.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from agent_harness.skills.models import (
    Skill,
    SkillExample,
    SkillGuardrails,
    SkillInputField,
    SkillOutputField,
)
from agent_harness.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


SKILL_GENERATION_PROMPT = """You are a Skill Builder agent for the Cognitive Knowledge Platform.

Your job is to create a new agent skill definition based on the user's description.
A skill is a reusable, declarative package of agent behavior defined in YAML.

## Existing Skills (for reference)
{existing_skills}

## Available MCP Tools
- graph_query: Query the Neo4j knowledge graph using Cypher
- semantic_search: Semantic similarity search over the Qdrant vector store
- sql_query: Execute read-only SQL queries on PostgreSQL tabular data

## User's Request
{description}

{domain_context}

## Output Format
Generate a valid JSON object representing the new skill with these fields:
{{
  "name": "<snake_case_name>",
  "version": "1.0.0",
  "description": "<clear description of what the skill does>",
  "domain": "<general|healthtech|fintech|edtech|enterprise_ops>",
  "tags": ["<tag1>", "<tag2>"],
  "system_prompt": "<detailed system prompt with numbered rules>",
  "tools": ["<tool1>", "<tool2>"],
  "input_schema": [
    {{"name": "<field_name>", "type": "<string|integer|boolean|list[string]>", "required": true, "description": "<what this input is>"}}
  ],
  "output_schema": [
    {{"name": "<field_name>", "type": "<string|integer|list[string]>", "description": "<what this output contains>"}}
  ],
  "guardrails": {{
    "pii_masking": "<off|standard|strict>",
    "max_steps": <integer>,
    "max_tokens": <integer>,
    "require_grounding": <true|false>
  }},
  "examples": [
    {{"input": {{"<field>": "<value>"}}, "output": {{"<field>": "<value>"}}}}
  ]
}}

Respond with ONLY the JSON object, no explanations or markdown fences."""


class SkillBuilderAgent:
    """
    Meta-agent that creates new skills from natural language descriptions.

    Usage:
        builder = SkillBuilderAgent(registry=skill_registry)
        new_skill = await builder.create_skill(
            description="I need a skill that analyzes drug interactions between medications",
            domain="healthtech",
            llm_fn=my_llm_function,
        )
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    async def create_skill(
        self,
        description: str,
        domain: str = "general",
        llm_fn: Optional[callable] = None,
    ) -> Skill:
        """
        Create a new skill from a natural language description.

        Args:
            description: Plain-English description of the desired skill.
            domain: Target domain for the skill.
            llm_fn: Async function to call the LLM.
                    Signature: async (prompt: str) -> str

        Returns:
            A validated Skill object.

        Raises:
            ValueError: If the LLM response cannot be parsed into a valid Skill.
        """
        if not llm_fn:
            raise ValueError("llm_fn is required to generate skills")

        # Build context from existing skills
        existing = self.registry.list_all()
        existing_str = "\n".join(
            f"- {s['name']}: {s['description']} (domain: {s['domain']}, tools: {s['tools']})"
            for s in existing
        ) or "No existing skills."

        domain_context = ""
        if domain != "general":
            domain_context = f"Target Domain: {domain}\nEnsure the skill is tailored to the {domain} domain."

        prompt = SKILL_GENERATION_PROMPT.format(
            existing_skills=existing_str,
            description=description,
            domain_context=domain_context,
        )

        # Call the LLM
        response = await llm_fn(prompt)

        # Parse the response
        skill = self._parse_skill_response(response)

        logger.info(f"Generated new skill: {skill.name} (domain: {skill.domain})")
        return skill

    async def create_and_save(
        self,
        description: str,
        domain: str = "general",
        llm_fn: Optional[callable] = None,
    ) -> Skill:
        """Create a new skill and save it to the library."""
        skill = await self.create_skill(description, domain, llm_fn)
        self.registry.save_skill(skill)
        return skill

    def _parse_skill_response(self, response: str) -> Skill:
        """Parse the LLM's JSON response into a validated Skill object."""
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
            raise ValueError(f"Failed to parse skill JSON: {e}\nResponse: {cleaned}")

        # Build the Skill object
        input_schema = [
            SkillInputField(
                name=f["name"],
                type=f.get("type", "string"),
                required=f.get("required", True),
                default=f.get("default"),
                description=f.get("description", ""),
            )
            for f in data.get("input_schema", [])
        ]

        output_schema = [
            SkillOutputField(
                name=f["name"],
                type=f.get("type", "string"),
                description=f.get("description", ""),
            )
            for f in data.get("output_schema", [])
        ]

        gr_data = data.get("guardrails", {})
        guardrails = SkillGuardrails(
            pii_masking=gr_data.get("pii_masking", "standard"),
            max_steps=gr_data.get("max_steps", 10),
            max_tokens=gr_data.get("max_tokens", 4096),
            require_grounding=gr_data.get("require_grounding", True),
        )

        examples = [
            SkillExample(input=ex["input"], output=ex["output"])
            for ex in data.get("examples", [])
        ]

        return Skill(
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            domain=data.get("domain", "general"),
            tags=data.get("tags", []),
            author="skill_builder_agent",
            system_prompt=data.get("system_prompt", ""),
            prompt_template=data.get("prompt_template"),
            tools=data.get("tools", []),
            input_schema=input_schema,
            output_schema=output_schema,
            guardrails=guardrails,
            examples=examples,
        )
