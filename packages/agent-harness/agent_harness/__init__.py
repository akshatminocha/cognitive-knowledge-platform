"""
CKP Agent Harness — Production Agent Runtime.

The 4-pillar cognitive execution layer:
1. Loop & Execution: Google ADK agent runner with step budgets, infinite-loop
   detection, and tool dispatch via MCP Client.
2. Context & Memory: Model-agnostic canonical session store with hot-swap
   format adapters (Gemini, OpenAI, Anthropic, Ollama) — enables mid-session
   model switching with zero context loss.
3. Governance: Integrates the Guardrails package at input/tool/output boundaries
   for PII masking, AST validation, and faithfulness checks.
4. Observability & Evaluation: OpenTelemetry tracing + golden dataset benchmarks.

Routes all LLM calls through the AI Gateway (external infra proxy).
"""

__version__ = "0.1.0"
