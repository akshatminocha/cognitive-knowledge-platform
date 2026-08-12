"""
Input Safety — Prompt injection detection and input validation.

Detects common prompt injection patterns, excessive length, and
blocked topics before the user's input reaches the LLM.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from guardrails.config import InputSafetyConfig

logger = logging.getLogger(__name__)


@dataclass
class InputSafetyViolation(Exception):
    """Raised when an input fails safety checks."""

    violation_type: str
    detail: str
    matched_pattern: Optional[str] = None

    def __str__(self) -> str:
        return f"Input safety violation [{self.violation_type}]: {self.detail}"


# ---- Prompt Injection Patterns ----
# These detect common attempts to override system instructions or
# extract system prompts. Patterns are intentionally broad to catch
# creative variations.

INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Direct instruction overrides
    (
        "INSTRUCTION_OVERRIDE",
        re.compile(
            r"(?:ignore|disregard|forget|override|bypass)\s+"
            r"(?:all\s+)?(?:previous|above|prior|earlier|system|your)\s+"
            r"(?:instructions?|prompts?|rules?|guidelines?|constraints?|directives?)",
            re.IGNORECASE,
        ),
    ),
    # Role-playing exploits
    (
        "ROLE_HIJACK",
        re.compile(
            r"(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you(?:'re|\s+are))|"
            r"switch\s+to|enter\s+(?:developer|admin|god|root|sudo)\s+mode|"
            r"from\s+now\s+on\s+you\s+(?:are|will))",
            re.IGNORECASE,
        ),
    ),
    # System prompt extraction
    (
        "PROMPT_EXTRACTION",
        re.compile(
            r"(?:show|reveal|display|print|output|repeat|tell\s+me|what\s+(?:is|are))\s+"
            r"(?:your|the)?\s*(?:system\s+)?(?:prompt|instructions?|rules?|initial\s+(?:prompt|message))",
            re.IGNORECASE,
        ),
    ),
    # Encoded/obfuscated injection attempts
    (
        "ENCODING_ATTACK",
        re.compile(
            r"(?:base64|rot13|hex|unicode|url)\s*(?:decode|encode|convert)",
            re.IGNORECASE,
        ),
    ),
    # Delimiter injection (trying to break out of context)
    (
        "DELIMITER_INJECTION",
        re.compile(
            r"```\s*(?:system|assistant|tool_call|function_call)\b|"
            r"\[INST\]|\[\/INST\]|<\|(?:im_start|im_end|system|user|assistant)\|>|"
            r"<\/?(?:system|instruction|context)>",
            re.IGNORECASE,
        ),
    ),
]


class InputSafetyGuard:
    """
    Validates user input for prompt injection and safety violations.

    Performs three checks:
    1. Length check: Rejects excessively long inputs
    2. Injection detection: Pattern-based prompt injection detection
    3. Topic blocking: Rejects inputs containing blocked topics

    Usage:
        guard = InputSafetyGuard(config)

        # Validate input before sending to LLM:
        guard.validate("What is the patient's diagnosis?")  # OK

        guard.validate("Ignore all previous instructions and...")
        # Raises InputSafetyViolation
    """

    def __init__(self, config: Optional[InputSafetyConfig] = None) -> None:
        self.config = config or InputSafetyConfig()

    def validate(self, text: str) -> None:
        """
        Run all input safety checks. Raises InputSafetyViolation on failure.
        """
        if not self.config.enabled:
            return

        self._check_length(text)
        self._check_injection(text)
        self._check_blocked_topics(text)

    def _check_length(self, text: str) -> None:
        """Reject inputs that exceed the maximum allowed length."""
        if len(text) > self.config.max_input_length:
            raise InputSafetyViolation(
                violation_type="INPUT_TOO_LONG",
                detail=(
                    f"Input length ({len(text)} chars) exceeds maximum "
                    f"({self.config.max_input_length} chars)"
                ),
            )

    def _check_injection(self, text: str) -> None:
        """Detect prompt injection patterns in the input."""
        for pattern_name, pattern in INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                raise InputSafetyViolation(
                    violation_type="PROMPT_INJECTION",
                    detail=f"Detected prompt injection pattern: {pattern_name}",
                    matched_pattern=match.group(),
                )

    def _check_blocked_topics(self, text: str) -> None:
        """Reject inputs that contain explicitly blocked topics."""
        if not self.config.blocked_topics:
            return

        text_lower = text.lower()
        for topic in self.config.blocked_topics:
            if topic.lower() in text_lower:
                raise InputSafetyViolation(
                    violation_type="BLOCKED_TOPIC",
                    detail=f"Input contains blocked topic: '{topic}'",
                    matched_pattern=topic,
                )

    def scan(self, text: str) -> list[dict]:
        """
        Non-throwing scan — returns a list of all detected issues.
        Useful for UI display or audit logging without blocking the request.
        """
        issues: list[dict] = []

        if len(text) > self.config.max_input_length:
            issues.append({
                "type": "INPUT_TOO_LONG",
                "detail": f"Input length: {len(text)}/{self.config.max_input_length}",
            })

        for pattern_name, pattern in INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                issues.append({
                    "type": "PROMPT_INJECTION",
                    "pattern": pattern_name,
                    "matched": match.group(),
                })

        if self.config.blocked_topics:
            text_lower = text.lower()
            for topic in self.config.blocked_topics:
                if topic.lower() in text_lower:
                    issues.append({
                        "type": "BLOCKED_TOPIC",
                        "topic": topic,
                    })

        return issues
