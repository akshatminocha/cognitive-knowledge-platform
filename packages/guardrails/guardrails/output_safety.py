"""
Output Safety — Faithfulness and groundedness scoring.

Validates that the agent's response is grounded in the retrieved context
(i.e., the response doesn't hallucinate facts not present in the source data).

Uses lightweight token-overlap scoring — no LLM call required.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from guardrails.config import OutputSafetyConfig

logger = logging.getLogger(__name__)


@dataclass
class OutputSafetyViolation(Exception):
    """Raised when an output fails groundedness checks."""

    violation_type: str
    detail: str
    score: float
    threshold: float

    def __str__(self) -> str:
        return (
            f"Output safety violation [{self.violation_type}]: {self.detail} "
            f"(score={self.score:.3f}, threshold={self.threshold:.3f})"
        )


def _tokenize(text: str) -> set[str]:
    """
    Extract a set of lowercased content tokens from text.

    Strips common stopwords to focus on meaningful content overlap.
    """
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
        "into", "through", "during", "before", "after", "above", "below",
        "between", "out", "off", "over", "under", "again", "further",
        "then", "once", "here", "there", "when", "where", "why", "how",
        "all", "both", "each", "few", "more", "most", "other", "some",
        "such", "no", "nor", "not", "only", "own", "same", "so", "than",
        "too", "very", "just", "because", "but", "and", "or", "if", "it",
        "its", "this", "that", "these", "those", "i", "me", "my", "we",
        "our", "you", "your", "he", "him", "his", "she", "her", "they",
        "them", "their", "what", "which", "who", "whom",
    }

    # Extract word tokens
    tokens = set(re.findall(r"\b[a-z0-9]+\b", text.lower()))
    # Remove stopwords
    return tokens - stopwords


class OutputSafetyGuard:
    """
    Validates that agent responses are grounded in retrieved context.

    Uses token-overlap scoring: measures the proportion of content tokens
    in the response that also appear in the provided context chunks.

    Usage:
        guard = OutputSafetyGuard(config)

        context_chunks = [
            "Patient John has been diagnosed with Type 2 Diabetes.",
            "Recommended treatment: Metformin 500mg twice daily.",
        ]
        response = "John has Type 2 Diabetes and should take Metformin."

        guard.validate(response=response, context_chunks=context_chunks)  # OK

        hallucinated = "John has a heart condition and needs surgery."
        guard.validate(response=hallucinated, context_chunks=context_chunks)
        # Raises OutputSafetyViolation (low groundedness score)
    """

    def __init__(self, config: Optional[OutputSafetyConfig] = None) -> None:
        self.config = config or OutputSafetyConfig()

    def compute_groundedness_score(
        self,
        response: str,
        context_chunks: list[str],
    ) -> float:
        """
        Compute a groundedness score between 0 and 1.

        Score = |response_tokens ∩ context_tokens| / |response_tokens|

        A score of 1.0 means every content word in the response also appears
        in the context. A score of 0.0 means no overlap.
        """
        if not response.strip():
            return 1.0  # Empty response is trivially grounded

        response_tokens = _tokenize(response)
        if not response_tokens:
            return 1.0  # No content tokens after stopword removal

        # Combine all context chunks into a single token set
        context_tokens: set[str] = set()
        for chunk in context_chunks:
            context_tokens.update(_tokenize(chunk))

        if not context_tokens:
            return 0.0  # No context provided → cannot be grounded

        overlap = response_tokens & context_tokens
        score = len(overlap) / len(response_tokens)

        return round(score, 4)

    def validate(
        self,
        response: str,
        context_chunks: list[str],
    ) -> float:
        """
        Validate that the response is grounded in the context.

        Returns the groundedness score.
        Raises OutputSafetyViolation if below the minimum threshold.
        """
        if not self.config.check_groundedness:
            return 1.0

        score = self.compute_groundedness_score(response, context_chunks)

        if score < self.config.min_groundedness_score:
            raise OutputSafetyViolation(
                violation_type="LOW_GROUNDEDNESS",
                detail=(
                    f"Response groundedness ({score:.3f}) is below the minimum "
                    f"threshold ({self.config.min_groundedness_score:.3f}). "
                    f"The response may contain hallucinated content."
                ),
                score=score,
                threshold=self.config.min_groundedness_score,
            )

        logger.debug(f"Groundedness score: {score:.3f} (threshold: {self.config.min_groundedness_score})")
        return score

    def score_report(
        self,
        response: str,
        context_chunks: list[str],
    ) -> dict:
        """
        Non-throwing analysis — returns a detailed grounding report.
        Useful for UI display, debugging, or audit logging.
        """
        response_tokens = _tokenize(response)
        context_tokens: set[str] = set()
        for chunk in context_chunks:
            context_tokens.update(_tokenize(chunk))

        overlap = response_tokens & context_tokens
        ungrounded = response_tokens - context_tokens
        score = len(overlap) / len(response_tokens) if response_tokens else 1.0

        return {
            "groundedness_score": round(score, 4),
            "threshold": self.config.min_groundedness_score,
            "is_grounded": score >= self.config.min_groundedness_score,
            "response_token_count": len(response_tokens),
            "context_token_count": len(context_tokens),
            "overlap_count": len(overlap),
            "ungrounded_tokens": sorted(ungrounded)[:20],  # Top 20 for brevity
        }
