"""
CKP Guardrails — Configurable Governance & Data Protection Engine.

Provides:
- Dynamic PII/PHI/PCI entity masking with reversible pseudonymization (Presidio)
- Cypher & SQL AST read-only validation (blocks destructive queries)
- Prompt injection & jailbreak detection
- Output faithfulness & groundedness verification

This package lives INSIDE the Agent Harness as the governance layer.
It is also independently pip-installable for standalone use.
"""

__version__ = "0.1.0"

from .engine import GuardrailEngine, InputGuardResult, OutputGuardResult
from .data_protection import DataProtector
from .secret_scanner import SecretScanner, calculate_shannon_entropy, is_high_entropy_candidate
from .input_safety import InputSafetyGuard, InputSafetyViolation
from .tool_safety import ToolSafetyGuard, ToolSafetyViolation
from .output_safety import OutputSafetyGuard, OutputSafetyViolation
from .token_map import TokenMap
from .config import (
    GuardrailConfig,
    DataProtectionConfig,
    InputSafetyConfig,
    ToolSafetyConfig,
    OutputSafetyConfig,
)

__all__ = [
    "GuardrailEngine",
    "InputGuardResult",
    "OutputGuardResult",
    "DataProtector",
    "SecretScanner",
    "calculate_shannon_entropy",
    "is_high_entropy_candidate",
    "InputSafetyGuard",
    "InputSafetyViolation",
    "ToolSafetyGuard",
    "ToolSafetyViolation",
    "OutputSafetyGuard",
    "OutputSafetyViolation",
    "TokenMap",
    "GuardrailConfig",
    "DataProtectionConfig",
    "InputSafetyConfig",
    "ToolSafetyConfig",
    "OutputSafetyConfig",
]
