"""
CKP AI Gateway — LiteLLM-based Multi-Model Router & Policy Proxy.

Handles model routing, provider fallbacks, rate limiting (TPM/RPM/TPD/RPD),
cost budgeting (token & $ caps), and semantic response caching.

This package operates strictly OUTSIDE the Agent Harness.
It processes raw LLM API requests — no cognitive logic, no memory, no guardrails.
"""

__version__ = "0.1.0"
