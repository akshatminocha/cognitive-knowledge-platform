"""
Declarative Policy Decision Point (PDP) & OPA Bridge.

Implements decoupled Attribute-Based Access Control (ABAC) and compliance policy
evaluation for AI guardrails. Works as the "Brain/Judge" alongside GuardrailEngine (the PEP).
Supports in-process declarative rule evaluation with an optional Open Policy Agent (OPA)
HTTP webhook connector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import logging
from typing import Any, Optional
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class PolicyAction(str, Enum):
    """Verdicts emitted by the Policy Decision Point."""

    ALLOW = "ALLOW"
    MASK = "MASK"
    BLOCK = "BLOCK"
    REHYDRATE = "REHYDRATE"
    AUDIT = "AUDIT"


@dataclass
class PolicyDecision:
    """The evaluated verdict from the Policy Decision Point."""

    allow: bool
    action: PolicyAction
    reason: str
    matched_rule: str
    metadata: dict[str, Any] = field(default_factory=dict)


class PolicyDecisionPoint:
    """
    Decoupled Policy Decision Point (PDP) for enterprise AI guardrails.

    Evaluates context attributes (User Role, Domain, Entity Types, Safety Signals)
    to produce deterministic governance decisions.
    """

    def __init__(
        self,
        opa_webhook_url: Optional[str] = None,
        timeout_seconds: float = 0.3,
    ) -> None:
        self.opa_webhook_url = opa_webhook_url
        self.timeout_seconds = timeout_seconds

    def evaluate_input_policy(
        self,
        user_role: Optional[str],
        domain: str,
        detected_entities: list[str],
        has_prompt_injection: bool = False,
    ) -> PolicyDecision:
        """
        Evaluate policy for user input before routing to the LLM.
        """
        # 1. Try external OPA daemon if configured
        if self.opa_webhook_url:
            opa_res = self._query_opa_webhook({
                "stage": "input",
                "user_role": user_role or "anonymous",
                "domain": domain,
                "detected_entities": detected_entities,
                "has_prompt_injection": has_prompt_injection,
            })
            if opa_res is not None:
                return opa_res

        # 2. In-Process Declarative Policy Matrix
        if has_prompt_injection:
            return PolicyDecision(
                allow=False,
                action=PolicyAction.BLOCK,
                reason="Input blocked due to severe prompt injection or jailbreak heuristics.",
                matched_rule="RULE_CRITICAL_INJECTION_BLOCK",
            )

        if detected_entities:
            # Sensitive medical or financial data requires masking before LLM ingestion
            return PolicyDecision(
                allow=True,
                action=PolicyAction.MASK,
                reason=f"Detected {len(detected_entities)} sensitive entities. Masking required.",
                matched_rule="RULE_PII_PSEUDONYMIZATION_REQUIRED",
                metadata={"entities_to_mask": detected_entities},
            )

        return PolicyDecision(
            allow=True,
            action=PolicyAction.ALLOW,
            reason="Input cleared all safety policies.",
            matched_rule="RULE_DEFAULT_ALLOW",
        )

    def evaluate_unmask_policy(
        self,
        user_role: Optional[str],
        entity_types: list[str],
        dataset_classification: str = "RESTRICTED",
    ) -> PolicyDecision:
        """
        Evaluate whether the current user is authorized to unmask / re-hydrate original PII.
        """
        # 1. Try external OPA daemon if configured
        if self.opa_webhook_url:
            opa_res = self._query_opa_webhook({
                "stage": "unmask",
                "user_role": user_role or "anonymous",
                "entity_types": entity_types,
                "classification": dataset_classification,
            })
            if opa_res is not None:
                return opa_res

        # 2. In-Process Declarative RBAC Matrix
        authorized_roles = {"admin", "compliance_officer", "attending_physician"}
        # If user_role is omitted (None), allow for backwards compatibility with legacy pipelines
        if user_role is None or user_role.lower() in authorized_roles:
            return PolicyDecision(
                allow=True,
                action=PolicyAction.REHYDRATE,
                reason=f"Role '{user_role or 'default_authorized'}' has clearance for de-identification.",
                matched_rule="RULE_RBAC_UNMASK_AUTHORIZED",
            )

        return PolicyDecision(
            allow=False,
            action=PolicyAction.MASK,
            reason=f"Role '{user_role}' lacks compliance clearance to view raw PII.",
            matched_rule="RULE_RBAC_UNMASK_DENIED",
        )

    def evaluate_tool_policy(
        self,
        tool_name: str,
        user_role: Optional[str],
        is_write_operation: bool,
    ) -> PolicyDecision:
        """
        Evaluate tool execution policy at the tool boundary.
        """
        if self.opa_webhook_url:
            opa_res = self._query_opa_webhook({
                "stage": "tool",
                "tool_name": tool_name,
                "user_role": user_role or "anonymous",
                "is_write_operation": is_write_operation,
            })
            if opa_res is not None:
                return opa_res

        if is_write_operation:
            return PolicyDecision(
                allow=False,
                action=PolicyAction.BLOCK,
                reason=f"Mutating database operations blocked by tool safety policy for '{tool_name}'.",
                matched_rule="RULE_TOOL_READ_ONLY_ENFORCEMENT",
            )

        return PolicyDecision(
            allow=True,
            action=PolicyAction.ALLOW,
            reason="Tool call complies with read-only security boundary.",
            matched_rule="RULE_TOOL_READ_ONLY_ALLOW",
        )

    def _query_opa_webhook(self, payload: dict[str, Any]) -> Optional[PolicyDecision]:
        """Query external OPA HTTP daemon with strict timeout."""
        if not self.opa_webhook_url:
            return None

        try:
            req_data = json.dumps({"input": payload}).encode("utf-8")
            req = urllib.request.Request(
                self.opa_webhook_url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    result = body.get("result", {})
                    if isinstance(result, dict) and "allow" in result:
                        action_str = result.get("action", "ALLOW").upper()
                        action = PolicyAction[action_str] if action_str in PolicyAction.__members__ else PolicyAction.ALLOW
                        return PolicyDecision(
                            allow=bool(result.get("allow", False)),
                            action=action,
                            reason=result.get("reason", "Evaluated by OPA Rego policy"),
                            matched_rule=result.get("rule", "OPA_REGO_RULE"),
                            metadata=result.get("metadata", {}),
                        )
        except Exception as e:
            logger.debug(f"OPA webhook query skipped or timed out ({e}). Falling back to embedded PDP.")
        return None
