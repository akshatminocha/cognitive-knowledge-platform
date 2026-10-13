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
