"""
Smart Model Cascade Router & Intent Gate — AI Economics Engine.

Provides:
1. Complexity Classifier (Tier 1 Flash -> Tier 2 Pro -> Tier 3 Frontier)
2. Intent Gating (Graph RAG vs. Open-Domain General AI)
3. Multi-Provider Graceful Cascade (BYOK: Gemini, Anthropic, OpenAI, Ollama)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ComplexityTier(str, Enum):
    """Complexity classification tiers for AI economics routing."""

    TIER_1 = "tier_1"  # Free / Flash / Low Latency (e.g. Gemini 2.5 Flash, Ollama)
    TIER_2 = "tier_2"  # Intermediate / Analytical (e.g. Gemini 2.5 Pro, GPT-4o-mini)
    TIER_3 = "tier_3"  # Frontier / Heavy Reasoning (e.g. Claude 3.5 Sonnet, GPT-4o)


class IntentType(str, Enum):
    """User query intent category."""

    GRAPH_RAG = "graph_rag"      # Queries targeting in-domain knowledge graph / vector records
    OPEN_DOMAIN = "open_domain"  # General conversational, coding, drafting, math, planning


@dataclass
class RoutingDecision:
    """Outcome of the Smart Model Cascade evaluation."""

    tier: ComplexityTier
    selected_model: str
    intent: IntentType
    reason: str
    estimated_cost_tier: str
    bypass_graph_tools: bool = False
    original_requested_model: Optional[str] = None
    fallback_applied: bool = False
    fallback_reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# Default model candidates per tier in order of preference
TIER_MODELS: dict[ComplexityTier, list[str]] = {
    ComplexityTier.TIER_1: [
        "gemini-2.5-flash",
        "gemini/gemini-2.5-flash",
        "ollama/llama3.2",
        "gpt-4o-mini",
    ],
    ComplexityTier.TIER_2: [
        "gemini-2.5-pro",
        "gemini/gemini-2.5-pro",
        "gpt-4o-mini",
        "gemini-2.5-flash",
    ],
    ComplexityTier.TIER_3: [
        "claude-3-5-sonnet",
        "anthropic/claude-3-5-sonnet-20241022",
        "gpt-4o",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ],
}

# Pricing indicators for transparency (USD per 1M tokens approx)
TIER_COST_LABELS: dict[ComplexityTier, str] = {
    ComplexityTier.TIER_1: "Free / Micro-tier (~$0.075 / 1M tokens)",
    ComplexityTier.TIER_2: "Analytical (~$1.25 / 1M tokens)",
    ComplexityTier.TIER_3: "Frontier Reasoning (~$3.00 - $15.00 / 1M tokens)",
}


class ModelCascadeRouter:
    """
    Intelligent router that chooses the optimal model tier and intent path.

    - Low complexity & greetings -> Tier 1 (Flash)
    - Analytical & comparative -> Tier 2 (Pro)
    - Deep reasoning / multi-hop synthesis -> Tier 3 (Sonnet / Frontier)
    - Open-domain coding/drafting -> Intent OPEN_DOMAIN (bypass graph tools)
    - Verifies provider API keys to ensure zero-crash graceful cascade.
    """

    def __init__(self) -> None:
        # Regex patterns for complexity classification
        self._tier3_keywords = re.compile(
            r"\b(synthesize|differential diagnosis|clinical trial design|causality analysis|"
            r"multi-hop|deep dive|mathematical proof|implement algorithm|architectural blueprint|"
            r"refactor whole|pathway cross-talk|pharmacokinetics|genomic variant pathogenicity)\b",
            re.IGNORECASE,
        )
        self._tier2_keywords = re.compile(
            r"\b(compare|contrast|difference between|analyze|correlation|evaluate|"
            r"break down|relationship between|why does|explain how|summarize trends|"
            r"pros and cons|aggregate|inspect|deduce|deduction|deductions|report|"
            r"expert|clinical review|clinical assessment|synthesize findings|"
            r"implications|recommendations|recommend)\b",
            re.IGNORECASE,
        )
        self._tier1_keywords = re.compile(
            r"\b(what is|who is|define|definition|list|show me|status of|find|hello|hi|hey|"
            r"help|thanks|thank you|good morning|overview)\b",
            re.IGNORECASE,
        )

        # Regex patterns for domain graph vs. open domain intent
        self._domain_keywords = re.compile(
            r"\b(patient|diagnosis|medication|drug|disease|trial|protocol|treatment|"
            r"symptom|hospital|physician|doctor|mutation|gene|oncology|dosage|adverse event|"
            r"contraindication|biomarker|clinical|graph|knowledge base|database|chunks|"
            r"entity|relationship|records)\b",
            re.IGNORECASE,
        )
        self._open_domain_keywords = re.compile(
            r"\b(write a python|write python|write code|code a|draft an email|draft a letter|"
            r"tell a joke|tell me a joke|joke|tell me a story|poem|creative writing|translate to|solve this math|"
            r"general advice|recipe|workout plan)\b",
            re.IGNORECASE,
        )

    def is_provider_available(self, model_name: str) -> bool:
        """
        Check if the required API key for a given model exists in the environment.
        """
        model_lower = model_name.lower()

        if "gemini" in model_lower:
            return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        elif "claude" in model_lower or "anthropic" in model_lower:
            return bool(os.getenv("ANTHROPIC_API_KEY"))
        elif "gpt" in model_lower or "openai" in model_lower or "o1" in model_lower:
            return bool(os.getenv("OPENAI_API_KEY"))
        elif "ollama" in model_lower:
            # Ollama is local, always consider candidate available if base URL exists
            return bool(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        
        # Default fallback: if unknown provider, assume available if any key exists
        return True

    def classify_complexity(self, query: str) -> tuple[ComplexityTier, str]:
        """
        Classify the complexity tier based on heuristics, length, and reasoning signals.
        """
        clean_query = query.strip()
        words = clean_query.split()
        word_count = len(words)

        # Check for code blocks or multi-line complexity
        has_code_block = "```" in clean_query
        has_multi_step = bool(re.search(r"(\d+\.\s|step \d+:|phase \d+:)", clean_query, re.IGNORECASE))

        # Check Tier 3 signals
        tier3_matches = self._tier3_keywords.findall(clean_query)
        if len(tier3_matches) >= 1 or (has_code_block and word_count > 30) or word_count > 100:
            reasons = []
            if tier3_matches:
                reasons.append(f"deep reasoning triggers ({', '.join(tier3_matches[:2])})")
            if word_count > 100:
                reasons.append("high token context length (>100 words)")
            if has_code_block:
                reasons.append("embedded code block requiring advanced code intelligence")
            return ComplexityTier.TIER_3, f"Classified Tier 3 Frontier: {'; '.join(reasons)}"

        # Check Tier 2 signals
        tier2_matches = self._tier2_keywords.findall(clean_query)
        if len(tier2_matches) >= 1 or (word_count >= 25 and not has_multi_step) or has_multi_step:
            reasons = []
            if tier2_matches:
                reasons.append(f"analytical comparison signals ({', '.join(tier2_matches[:2])})")
            if has_multi_step:
                reasons.append("multi-step structured inquiry")
            if word_count >= 25:
                reasons.append("moderate context size (25+ words)")
            return ComplexityTier.TIER_2, f"Classified Tier 2 Analytical: {'; '.join(reasons)}"

        # Default to Tier 1
        tier1_matches = self._tier1_keywords.findall(clean_query)
        match_info = f" ({', '.join(tier1_matches[:2])})" if tier1_matches else ""
        return ComplexityTier.TIER_1, f"Classified Tier 1 Flash: lightweight single-hop query{match_info}"

    def classify_intent(self, query: str) -> tuple[IntentType, str]:
        """
        Classify whether the query requires In-Domain Graph RAG or Open-Domain General AI.
        """
        domain_matches = self._domain_keywords.findall(query)
        open_matches = self._open_domain_keywords.findall(query)

        # If explicit open-domain command without specific domain data target
        if open_matches and len(domain_matches) == 0:
            return (
                IntentType.OPEN_DOMAIN,
                f"Open-domain task detected ({', '.join(open_matches[:2])}) - bypassing graph tools",
            )

        # If domain keywords present
        if domain_matches:
            return (
                IntentType.GRAPH_RAG,
                f"Knowledge graph domain query ({', '.join(domain_matches[:3])}) - enabling Graph RAG tools",
            )

        # Default: if short conversational query without domain keywords
        if len(query.split()) < 6 and any(w in query.lower() for w in ["hi", "hello", "who are you", "what can you do"]):
            return (
                IntentType.OPEN_DOMAIN,
                "Conversational greeting / orientation - bypassing graph tools",
            )

        # Default assumption: use Graph RAG to ensure full knowledge access
        return IntentType.GRAPH_RAG, "Standard knowledge retrieval query"

    def select_model_for_tier(self, tier: ComplexityTier) -> tuple[str, bool, Optional[str]]:
        """
        Select the best model for a tier that has an active provider key.
        Returns: (selected_model, is_fallback, fallback_reason)
        """
        candidates = TIER_MODELS.get(tier, TIER_MODELS[ComplexityTier.TIER_1])

        for candidate in candidates:
            if self.is_provider_available(candidate):
                return candidate, False, None

        # If none of the models in this tier have available keys, cascade to Tier 1 default
        for fallback_candidate in TIER_MODELS[ComplexityTier.TIER_1]:
            if self.is_provider_available(fallback_candidate):
                reason = (
                    f"No active API keys found for {tier.value} candidates {candidates}; "
                    f"gracefully cascaded to {fallback_candidate}."
                )
                logger.warning(reason)
                return fallback_candidate, True, reason

        # Ultimate fallback
        return "gemini-2.5-flash", True, "Defaulted to gemini-2.5-flash (no provider keys explicitly verified)"

    def route_query(
        self,
        query: str,
        requested_model: Optional[str] = None,
    ) -> RoutingDecision:
        """
        Primary entry point for routing a query.

        - If requested_model is 'auto' or None, evaluates complexity and routes automatically.
        - If requested_model is specific (e.g. 'claude-3-5-sonnet'), checks key availability
          and falls back gracefully if key is missing.
        - Evaluates intent to determine whether graph tools should be bypassed.
        """
        intent, intent_reason = self.classify_intent(query)
        bypass_tools = (intent == IntentType.OPEN_DOMAIN)

        is_auto = not requested_model or requested_model.lower() in ("auto", "auto (ai economics)", "smart")

        if is_auto:
            tier, complexity_reason = self.classify_complexity(query)
            selected_model, is_fallback, fallback_reason = self.select_model_for_tier(tier)

            decision = RoutingDecision(
                tier=tier,
                selected_model=selected_model,
                intent=intent,
                reason=complexity_reason,
                estimated_cost_tier=TIER_COST_LABELS.get(tier, "Standard"),
                bypass_graph_tools=bypass_tools,
                original_requested_model="auto",
                fallback_applied=is_fallback,
                fallback_reason=fallback_reason,
                metadata={
                    "intent_reason": intent_reason,
                    "provider_available": self.is_provider_available(selected_model),
                },
            )
            logger.info(
                f"Smart Route: [{tier.value}] -> {selected_model} "
                f"(intent={intent.value}, bypass_tools={bypass_tools})"
            )
            return decision

        # Explicit model requested
        clean_req = requested_model.strip()
        key_ok = self.is_provider_available(clean_req)

        if key_ok:
            # Map requested model to an estimated tier
            if any(k in clean_req.lower() for k in ["sonnet", "o1", "gpt-4o"]):
                tier = ComplexityTier.TIER_3
            elif any(k in clean_req.lower() for k in ["pro"]):
                tier = ComplexityTier.TIER_2
            else:
                tier = ComplexityTier.TIER_1

            return RoutingDecision(
                tier=tier,
                selected_model=clean_req,
                intent=intent,
                reason=f"Explicit model '{clean_req}' selected by user with verified provider key.",
                estimated_cost_tier=TIER_COST_LABELS.get(tier, "Custom"),
                bypass_graph_tools=bypass_tools,
                original_requested_model=clean_req,
                fallback_applied=False,
                metadata={"intent_reason": intent_reason},
            )

        # Key NOT available for requested model -> Cascade to available model
        tier, complexity_reason = self.classify_complexity(query)
        fallback_model, _, _ = self.select_model_for_tier(tier)
        fallback_msg = (
            f"Requested model '{clean_req}' lacks an active API key in environment. "
            f"Gracefully cascaded to '{fallback_model}'."
        )
        logger.warning(fallback_msg)

        return RoutingDecision(
            tier=tier,
            selected_model=fallback_model,
            intent=intent,
            reason=f"{complexity_reason} | {fallback_msg}",
            estimated_cost_tier=TIER_COST_LABELS.get(tier, "Cascaded"),
            bypass_graph_tools=bypass_tools,
            original_requested_model=clean_req,
            fallback_applied=True,
            fallback_reason=fallback_msg,
            metadata={"intent_reason": intent_reason},
        )
