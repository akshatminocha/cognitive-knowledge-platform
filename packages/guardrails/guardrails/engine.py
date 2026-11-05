"""
Guardrail Engine — Unified orchestrator for all guardrail checks.

Provides a single entry point for the Agent Harness to invoke guardrails
at three boundaries:
1. Input:  PII masking + prompt injection detection
2. Tool:   Cypher/SQL AST read-only validation
3. Output: Faithfulness/groundedness scoring + PII re-hydration

Usage:
    from guardrails import GuardrailEngine

    engine = GuardrailEngine()

    # At input boundary:
    result = engine.guard_input("Patient John Doe has MRN: 123456789")
    # result.masked_text = "Patient [PERSON_1] has MRN: [MEDICAL_RECORD_NUMBER_1]"

    # At tool boundary:
    engine.guard_tool("graph_mcp", {"query": "MATCH (n) RETURN n LIMIT 10"})

    # At output boundary:
    result = engine.guard_output(
        response="John has diabetes.",
        context_chunks=["Patient John diagnosed with Type 2 Diabetes."],
        token_map=result.token_map,  # From input stage
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from guardrails.config import GuardrailConfig
from guardrails.data_protection import DataProtector
from guardrails.input_safety import InputSafetyGuard
from guardrails.output_safety import OutputSafetyGuard
from guardrails.policy_engine import PolicyAction, PolicyDecisionPoint
from guardrails.token_map import TokenMap
from guardrails.tool_safety import ToolSafetyGuard

logger = logging.getLogger(__name__)


@dataclass
class InputGuardResult:
    """Result of input-stage guardrail processing."""

    original_text: str
    masked_text: str
    token_map: TokenMap
    pii_entities_found: int
    injection_issues: list[dict] = field(default_factory=list)
    is_safe: bool = True
    blocked_reason: Optional[str] = None


@dataclass
class OutputGuardResult:
    """Result of output-stage guardrail processing."""

    original_response: str
    final_response: str
    groundedness_score: float
    is_grounded: bool
    was_rehydrated: bool


class GuardrailEngine:
    """
    Unified guardrail orchestrator.

    Composes all four guardrail subsystems into a clean API:
    - DataProtector:    PII/PHI masking and re-hydration
    - InputSafetyGuard: Prompt injection and topic blocking
    - ToolSafetyGuard:  Cypher/SQL read-only validation
    - OutputSafetyGuard: Response groundedness scoring

    The engine is stateless per-call — token maps are passed between
    stages explicitly.
    """

    def __init__(self, config: Optional[GuardrailConfig] = None) -> None:
        self.config = config or GuardrailConfig()

        self._data_protector = DataProtector(self.config.data_protection)
        self._input_guard = InputSafetyGuard(self.config.input_safety)
        self._tool_guard = ToolSafetyGuard(self.config.tool_safety)
        self._output_guard = OutputSafetyGuard(self.config.output_safety)
        self._policy_pdp = PolicyDecisionPoint(
            opa_webhook_url=self.config.data_protection.opa_webhook_url
        )

    def guard_input(
        self,
        text: str,
        token_map: Optional[TokenMap] = None,
        user_role: Optional[str] = None,
    ) -> InputGuardResult:
        """
        Process user input through all input-stage guardrails (PEP).

        Pipeline:
        1. Prompt injection detection (non-blocking scan)
        2. Policy evaluation via PolicyDecisionPoint (PDP / OPA)
        3. PII/PHI masking via DataProtector

        Returns InputGuardResult with masked text and token map.
        Raises InputSafetyViolation if injection or policy violation is detected.
        """
        # 1. Input safety check (throws on violation)
        self._input_guard.validate(text)

        # 2. Non-blocking injection scan for logging/UI
        injection_issues = self._input_guard.scan(text)
        has_injection = len(injection_issues) > 0

        # 3. Detect PII entities for policy evaluation
        detected_entities = [d["entity_type"] for d in self._data_protector.detect_entities(text)]

        # 4. Evaluate input policy via PDP / OPA
        policy_verdict = self._policy_pdp.evaluate_input_policy(
            user_role=user_role,
            domain=self.config.data_protection.active_domain.value,
            detected_entities=detected_entities,
            has_prompt_injection=has_injection,
        )

        if not policy_verdict.allow and policy_verdict.action == PolicyAction.BLOCK:
            from guardrails.input_safety import InputSafetyViolation
            raise InputSafetyViolation(policy_verdict.reason, injection_issues[0] if injection_issues else None)

        # 5. PII/PHI masking
        if policy_verdict.action == PolicyAction.MASK or len(detected_entities) > 0:
            masked_text, tmap = self._data_protector.mask_text(text, token_map, user_role=user_role)
            pii_count = tmap.size - (token_map.size if token_map else 0)
        else:
            masked_text = text
            tmap = token_map or TokenMap()
            pii_count = 0

        if pii_count > 0:
            logger.info(f"Masked {pii_count} PII entities in input (Policy: {policy_verdict.matched_rule})")

        return InputGuardResult(
            original_text=text,
            masked_text=masked_text,
            token_map=tmap,
            pii_entities_found=pii_count,
            injection_issues=injection_issues,
            is_safe=len(injection_issues) == 0,
        )

    def guard_tool(
        self,
        tool_name: str,
        tool_input: dict,
        user_role: Optional[str] = None,
    ) -> None:
        """
        Validate a tool call at the tool-execution boundary (PEP).

        Dispatches to the appropriate validator (Cypher or SQL) and checks
        authorization policy via the PolicyDecisionPoint (PDP).
        """
        # Determine if query is write-mutating
        query = tool_input.get("query") or tool_input.get("cypher") or tool_input.get("sql") or ""
        write_keywords = {"CREATE", "MERGE", "DELETE", "SET", "DROP", "ALTER", "INSERT", "UPDATE"}
        is_write = any(re.search(rf"\b{kw}\b", query, re.IGNORECASE) for kw in write_keywords)

        policy_verdict = self._policy_pdp.evaluate_tool_policy(
            tool_name=tool_name,
            user_role=user_role,
            is_write_operation=is_write,
        )

        if not policy_verdict.allow:
            from guardrails.tool_safety import ToolSafetyViolation
            raise ToolSafetyViolation(policy_verdict.reason, tool_name=tool_name)

        self._tool_guard.validate_tool_call(tool_name, tool_input)

    def guard_output(
        self,
        response: str,
        context_chunks: list[str],
        token_map: Optional[TokenMap] = None,
        rehydrate: bool = False,
        user_role: Optional[str] = None,
    ) -> OutputGuardResult:
        """
        Process agent output through all output-stage guardrails (PEP).

        Pipeline:
        1. Groundedness check against context chunks
        2. Policy evaluation via PolicyDecisionPoint for PII re-hydration clearance
        3. Optional PII re-hydration for authorized users
        """
        # 1. Groundedness scoring (non-throwing)
        score = self._output_guard.compute_groundedness_score(response, context_chunks)
        is_grounded = score >= self.config.output_safety.min_groundedness_score

        if not is_grounded:
            logger.warning(
                f"Low groundedness score: {score:.3f} "
                f"(threshold: {self.config.output_safety.min_groundedness_score})"
            )

        # 2. PII re-hydration policy evaluation via PDP
        final_response = response
        was_rehydrated = False

        if rehydrate and token_map and token_map.size > 0:
            policy_verdict = self._policy_pdp.evaluate_unmask_policy(
                user_role=user_role,
                entity_types=list(token_map.get_all_mappings().values()),
            )

            if policy_verdict.allow and policy_verdict.action == PolicyAction.REHYDRATE:
                final_response = token_map.restore_text(response, user_role=user_role)
                was_rehydrated = True
                logger.info(f"Re-hydrated {token_map.size} PII tokens in output for role '{user_role}'")
            else:
                logger.warning(
                    f"PII re-hydration denied by policy: {policy_verdict.reason}. Preserving masked tokens."
                )

        return OutputGuardResult(
            original_response=response,
            final_response=final_response,
            groundedness_score=score,
            is_grounded=is_grounded,
            was_rehydrated=was_rehydrated,
        )

    def get_diagnostics(self) -> dict:
        """Return diagnostic information about the guardrail engine configuration."""
        return {
            "data_protection": {
                "enabled": self.config.data_protection.enabled,
                "domain": self.config.data_protection.active_domain.value,
            },
            "input_safety": {
                "enabled": self.config.input_safety.enabled,
                "max_input_length": self.config.input_safety.max_input_length,
                "blocked_topics_count": len(self.config.input_safety.blocked_topics),
            },
            "tool_safety": {
                "enforce_read_only": self.config.tool_safety.enforce_read_only,
            },
            "output_safety": {
                "check_groundedness": self.config.output_safety.check_groundedness,
                "min_score": self.config.output_safety.min_groundedness_score,
            },
        }
