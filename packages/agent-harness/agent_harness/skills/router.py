"""
Skill Router — LLM-based skill selection for incoming queries.

Given a user query and the active domain, the router selects the
most appropriate skill from the registry. Uses an LLM call to
analyze query intent and match it to available skills.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from agent_harness.skills.models import Skill
from agent_harness.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillRouter:
    """
    LLM-based skill selector.

    Examines the user's query, lists available skills for the active
    domain, and uses an LLM to pick the best match.

    Falls back to a default skill if the LLM call fails or no
    skill matches.

    Usage:
        router = SkillRouter(registry=skill_registry)
        skill = await router.select_skill(
            query="Summarize patient PAT-001's clinical history",
            domain="healthtech",
        )
    """

    # The prompt used to ask the LLM which skill to use
    ROUTING_PROMPT = """You are a skill routing agent. Given a user query and a list of available skills, select the SINGLE most appropriate skill.

Available Skills:
{skill_list}

User Query: {query}
Domain: {domain}

Respond with ONLY a JSON object in this exact format:
{{
  "selected_skill": "<skill_name>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>"
}}

If no skill is a good match, set selected_skill to "knowledge_qa" (the default general-purpose skill)."""

    def __init__(
        self,
        registry: SkillRegistry,
        default_skill: str = "knowledge_qa",
        confidence_threshold: float = 0.5,
    ) -> None:
        self.registry = registry
        self.default_skill = default_skill
        self.confidence_threshold = confidence_threshold

    async def select_skill(
        self,
        query: str,
        domain: str = "general",
        llm_fn: Optional[callable] = None,
    ) -> Skill:
        """
        Select the best skill for a query.

        Args:
            query: The user's natural language query.
            domain: The active domain (e.g., 'healthtech').
            llm_fn: Optional async function to call the LLM.
                    Signature: async (prompt: str) -> str
                    If not provided, falls back to rule-based matching.

        Returns:
            The selected Skill object.
        """
        # Get candidate skills for this domain
        candidates = self.registry.find_by_domain(domain)

        if not candidates:
            logger.warning(f"No skills found for domain '{domain}', using default")
            return self._get_default_skill()

        # If only one candidate, use it directly
        if len(candidates) == 1:
            logger.info(f"Single skill available: {candidates[0].name}")
            return candidates[0]

        # Try LLM-based routing
        if llm_fn:
            try:
                selected = await self._llm_route(query, domain, candidates, llm_fn)
                if selected:
                    return selected
            except Exception as e:
                logger.warning(f"LLM routing failed, falling back: {e}")

        # Fallback: rule-based keyword matching
        return self._rule_based_route(query, domain, candidates)

    async def _llm_route(
        self,
        query: str,
        domain: str,
        candidates: list[Skill],
        llm_fn: callable,
    ) -> Optional[Skill]:
        """Use an LLM to select the best skill."""
        # Build the skill list for the prompt
        skill_list = "\n".join(
            f"- {s.name}: {s.description} (tools: {', '.join(s.tools)})"
            for s in candidates
        )

        prompt = self.ROUTING_PROMPT.format(
            skill_list=skill_list,
            query=query,
            domain=domain,
        )

        # Call the LLM
        response = await llm_fn(prompt)

        # Parse the response
        try:
            # Strip markdown code fences if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            result = json.loads(cleaned)
            skill_name = result.get("selected_skill", "")
            confidence = result.get("confidence", 0.0)
            reasoning = result.get("reasoning", "")

            logger.info(
                f"LLM skill routing: {skill_name} "
                f"(confidence={confidence:.2f}, reason={reasoning})"
            )

            # Check confidence threshold
            if confidence < self.confidence_threshold:
                logger.info(
                    f"Confidence {confidence:.2f} below threshold "
                    f"{self.confidence_threshold:.2f}, using default"
                )
                return self._get_default_skill()

            # Look up the selected skill
            skill = self.registry.get(skill_name)
            if skill:
                return skill

            logger.warning(f"LLM selected unknown skill: {skill_name}")

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse LLM routing response: {e}")

        return None

    def _rule_based_route(
        self,
        query: str,
        domain: str,
        candidates: list[Skill],
    ) -> Skill:
        """
        Simple keyword-based fallback routing.

        Scores each candidate by counting how many of its tags
        appear in the query.
        """
        query_lower = query.lower()
        best_skill = None
        best_score = -1

        for skill in candidates:
            score = 0
            # Check tags
            for tag in skill.tags:
                if tag.lower() in query_lower:
                    score += 2

            # Check description words
            for word in skill.description.lower().split():
                if len(word) > 3 and word in query_lower:
                    score += 1

            if score > best_score:
                best_score = score
                best_skill = skill

        if best_skill and best_score > 0:
            logger.info(
                f"Rule-based routing: {best_skill.name} (score={best_score})"
            )
            return best_skill

        return self._get_default_skill()

    def _get_default_skill(self) -> Skill:
        """Return the default fallback skill."""
        skill = self.registry.get(self.default_skill)
        if skill:
            return skill

        # If even the default isn't registered, create a minimal one
        logger.warning(f"Default skill '{self.default_skill}' not found, using minimal")
        return Skill(
            name="fallback",
            description="General-purpose knowledge Q&A",
            system_prompt="You are a helpful knowledge assistant. Answer questions using the available tools.",
            tools=["graph_query", "semantic_search", "sql_query"],
        )
