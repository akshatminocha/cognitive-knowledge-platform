"""
Reflection Loop — Self-correction and response quality evaluation.

Evaluates the agent's response against the original query and retrieved
context to determine if a revision is needed. Provides structured
feedback for the agent to improve its answer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ReflectionResult:
    """Result of a reflection evaluation."""

    needs_revision: bool = False
    reason: Optional[str] = None
    quality_score: float = 1.0  # 0.0 - 1.0
    suggestions: list[str] = field(default_factory=list)
    checks_passed: dict[str, bool] = field(default_factory=dict)


class ReflectionLoop:
    """
    Self-correction evaluator for agent responses.

    Runs a series of heuristic checks on the agent's response:
    1. Completeness: Does the response address the query?
    2. Coherence: Is the response logically consistent?
    3. Specificity: Does the response contain concrete information?
    4. Safety: Does the response avoid harmful content?

    If any check fails, the evaluator recommends a revision with
    specific feedback for the agent.

    Usage:
        reflection = ReflectionLoop()

        result = reflection.evaluate(
            query="What medications does PAT-001 take?",
            response="The patient takes medication.",
            context_chunks=["PAT-001 takes Metformin 500mg twice daily."],
        )

        if result.needs_revision:
            print(f"Revision needed: {result.reason}")
            print(f"Suggestions: {result.suggestions}")
    """

    def __init__(
        self,
        min_response_length: int = 20,
        min_quality_score: float = 0.5,
    ) -> None:
        self.min_response_length = min_response_length
        self.min_quality_score = min_quality_score

    def evaluate(
        self,
        query: str,
        response: str,
        context_chunks: list[str],
    ) -> ReflectionResult:
        """
        Evaluate a response and determine if revision is needed.

        Returns a ReflectionResult with quality score and suggestions.
        """
        result = ReflectionResult()

        # Run all checks
        result.checks_passed["completeness"] = self._check_completeness(
            query, response, result
        )
        result.checks_passed["coherence"] = self._check_coherence(response, result)
        result.checks_passed["specificity"] = self._check_specificity(
            response, context_chunks, result
        )
        result.checks_passed["safety"] = self._check_safety(response, result)

        # Calculate overall quality score
        passed = sum(1 for v in result.checks_passed.values() if v)
        total = len(result.checks_passed)
        result.quality_score = passed / total if total > 0 else 1.0

        # Determine if revision is needed
        if result.quality_score < self.min_quality_score:
            result.needs_revision = True
            result.reason = (
                f"Quality score ({result.quality_score:.2f}) is below threshold "
                f"({self.min_quality_score:.2f}). "
                f"Failed checks: {[k for k, v in result.checks_passed.items() if not v]}"
            )

        logger.debug(
            f"Reflection: quality={result.quality_score:.2f}, "
            f"revision_needed={result.needs_revision}"
        )

        return result

    def _check_completeness(
        self, query: str, response: str, result: ReflectionResult
    ) -> bool:
        """Check if the response adequately addresses the query."""
        # Check minimum length
        if len(response.strip()) < self.min_response_length:
            result.suggestions.append(
                "Response is too short. Provide a more detailed answer."
            )
            return False

        # Check if response is just a refusal without explanation
        refusal_phrases = [
            "i cannot", "i can't", "i'm not able", "i don't know",
            "i'm unable", "i am not able",
        ]
        response_lower = response.lower()
        is_refusal = any(phrase in response_lower for phrase in refusal_phrases)

        if is_refusal and len(response.split()) < 15:
            result.suggestions.append(
                "If you cannot answer, explain why and suggest alternatives."
            )
            return False

        return True

    def _check_coherence(self, response: str, result: ReflectionResult) -> bool:
        """Check if the response is logically coherent."""
        # Check for contradictions (simple heuristic)
        sentences = [s.strip() for s in response.split(".") if s.strip()]

        if len(sentences) == 0:
            result.suggestions.append("Response contains no complete sentences.")
            return False

        # Check for excessive repetition
        if len(sentences) >= 3:
            unique_sentences = set(s.lower() for s in sentences)
            if len(unique_sentences) < len(sentences) * 0.5:
                result.suggestions.append(
                    "Response contains excessive repetition. Consolidate repeated points."
                )
                return False

        return True

    def _check_specificity(
        self, response: str, context_chunks: list[str], result: ReflectionResult
    ) -> bool:
        """Check if the response contains specific, concrete information."""
        if not context_chunks:
            return True  # Can't check without context

        # Check if the response uses any specific terms from the context
        context_text = " ".join(context_chunks).lower()
        response_lower = response.lower()

        # Extract content words from context (simple approach)
        context_words = set(context_text.split()) - {
            "the", "a", "an", "is", "are", "was", "of", "in", "to", "and", "for",
        }

        response_words = set(response_lower.split())
        overlap = context_words & response_words

        # If context is available but response shares very few terms
        if len(context_words) > 10 and len(overlap) < 3:
            result.suggestions.append(
                "Response lacks specificity. Use concrete details from the retrieved context."
            )
            return False

        return True

    def _check_safety(self, response: str, result: ReflectionResult) -> bool:
        """Check for potentially harmful or inappropriate content."""
        # Check for leaked system prompts or instructions
        leak_indicators = [
            "my instructions are", "my system prompt", "i was told to",
            "my programming", "as an ai model",
        ]

        response_lower = response.lower()
        for indicator in leak_indicators:
            if indicator in response_lower:
                result.suggestions.append(
                    "Response may contain leaked system instructions. Revise to remove."
                )
                return False

        return True

    def build_revision_prompt(self, result: ReflectionResult) -> str:
        """
        Build a revision prompt from the reflection result.

        This prompt is appended to the conversation to guide the agent
        toward a better response.
        """
        if not result.needs_revision:
            return ""

        lines = [
            "[REFLECTION] Your previous response needs improvement:",
            f"Quality Score: {result.quality_score:.2f}",
            "",
            "Issues found:",
        ]

        for suggestion in result.suggestions:
            lines.append(f"- {suggestion}")

        lines.append("")
        lines.append("Please provide an improved response addressing these issues.")

        return "\n".join(lines)
