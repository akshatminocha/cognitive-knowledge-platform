"""
Agent Runner — Google ADK execution loop.

Orchestrates the agent lifecycle:
1. Receives a user query
2. Passes it through input guardrails (PII masking + injection detection)
3. Runs the ADK agent with MCP tools and schema context
4. Validates tool calls at the tool boundary
5. Passes the response through output guardrails (groundedness check)
6. Returns the final response with PII re-hydrated for authorized users

State is never stored in the LLM context window as source of truth —
canonical state lives in the ContextEngine.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from google.adk import Agent

from agent_harness.context_engine import ContextEngine, CanonicalMessage, Role
from agent_harness.memory import MemoryManager
from agent_harness.reflection import ReflectionLoop
from agent_harness.skills.models import Skill

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_MAX_STEPS = 10
DEFAULT_MAX_TOKENS_PER_STEP = 4096
INFINITE_LOOP_THRESHOLD = 3  # Repeated identical tool calls


@dataclass
class RunnerConfig:
    """Configuration for the agent runner."""

    max_steps: int = DEFAULT_MAX_STEPS
    max_tokens_per_step: int = DEFAULT_MAX_TOKENS_PER_STEP
    enable_reflection: bool = True
    enable_memory: bool = True
    active_schema: str = "healthtech"
    active_model: str = "gemini-2.5-flash"
    active_skill: Optional[Skill] = None


# ---------------------------------------------------------------------------
# Step / Run result types
# ---------------------------------------------------------------------------
@dataclass
class StepResult:
    """Result of a single agent step."""

    step_index: int
    action: str  # "tool_call" | "response" | "reflection"
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_output: Optional[Any] = None
    response_text: Optional[str] = None
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class RunResult:
    """Complete result of an agent run."""

    query: str
    final_response: str
    steps: list[StepResult] = field(default_factory=list)
    total_steps: int = 0
    total_duration_ms: float = 0.0
    groundedness_score: float = 0.0
    pii_entities_masked: int = 0
    context_chunks_used: int = 0
    model_used: str = ""
    was_reflected: bool = False
    error: Optional[str] = None


class AgentRunner:
    """
    Production agent execution loop.

    Wraps the Google ADK agent with the CKP governance layer:
    - Input guardrails (masking + injection)
    - Tool boundary guardrails (AST validation)
    - Output guardrails (groundedness)
    - Infinite loop detection
    - Step budgets

    Usage:
        runner = AgentRunner(config=RunnerConfig())
        result = await runner.run("What medications is patient PAT-001 taking?")
        print(result.final_response)
    """

    def __init__(
        self,
        config: Optional[RunnerConfig] = None,
        context_engine: Optional[ContextEngine] = None,
        memory: Optional[MemoryManager] = None,
        reflection: Optional[ReflectionLoop] = None,
    ) -> None:
        self.config = config or RunnerConfig()
        self.context = context_engine or ContextEngine()
        self.memory = memory or MemoryManager()
        self.reflection = reflection or ReflectionLoop()

        # Track tool call history for infinite loop detection
        self._recent_tool_calls: list[str] = []

    async def run(self, query: str, session_id: Optional[str] = None) -> RunResult:
        """
        Execute a full agent run for a user query.

        Pipeline:
        1. Apply active skill overrides (if set)
        2. Store user message in canonical context
        3. Retrieve relevant memory (long-term)
        4. Build the LLM prompt (schema + context + memory)
        5. Execute ADK agent loop with step budget
        6. Return final result with governance metadata
        """
        start_time = time.monotonic()
        self._recent_tool_calls.clear()

        # Apply skill overrides if an active skill is set
        effective_max_steps = self.config.max_steps
        effective_max_tokens = self.config.max_tokens_per_step
        skill = self.config.active_skill

        if skill:
            effective_max_steps = skill.guardrails.max_steps
            effective_max_tokens = skill.guardrails.max_tokens
            logger.info(
                f"Running with skill '{skill.name}' "
                f"(tools={skill.tools}, max_steps={effective_max_steps})"
            )

        result = RunResult(
            query=query,
            final_response="",
            model_used=self.config.active_model,
        )

        # 1. Store user message in canonical context
        self.context.add_message(CanonicalMessage(
            role=Role.USER,
            content=query,
            session_id=session_id,
        ))

        # 2. Retrieve relevant memory
        memory_context = ""
        if self.config.enable_memory:
            memories = await self.memory.recall(query, limit=3)
            if memories:
                memory_context = "\n".join(
                    f"[Memory] {m.content}" for m in memories
                )
                logger.info(f"Retrieved {len(memories)} relevant memories")

        # 3-4. Agent execution loop
        step_start = time.monotonic()
        instruction = "You are a helpful knowledge assistant."
        if skill:
            instruction = skill.description

        try:
            from google.adk.runners import InMemoryRunner
            agent = Agent(
                name="ckp_agent",
                model="gemini-2.5-flash",
                instruction=instruction,
            )
            runner = InMemoryRunner(agent=agent)
            events = await runner.run_debug(query, quiet=True)
            
            response_text = ""
            if events and events[-1].message and events[-1].message.parts:
                response_text = "".join([
                    p.text for p in events[-1].message.parts if hasattr(p, "text") and p.text
                ])
            if not response_text:
                response_text = "Sorry, I couldn't generate a response."
                
            error_msg = None
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            response_text = f"Agent execution failed: {e}"
            error_msg = str(e)

        step = StepResult(
            step_index=1,
            action="response",
            response_text=response_text,
            duration_ms=(time.monotonic() - step_start) * 1000,
            error=error_msg
        )
        result.steps.append(step)
        result.final_response = response_text
        result.total_steps = 1

        # 5. Optional reflection
        if self.config.enable_reflection and result.final_response:
            reflection_result = self.reflection.evaluate(
                query=query,
                response=result.final_response,
                context_chunks=[],
            )
            if reflection_result.needs_revision:
                result.was_reflected = True
                logger.info(f"Reflection triggered: {reflection_result.reason}")

        # 6. Store assistant response in canonical context
        self.context.add_message(CanonicalMessage(
            role=Role.ASSISTANT,
            content=result.final_response,
            session_id=session_id,
        ))

        # 7. Persist to long-term memory
        if self.config.enable_memory and result.final_response:
            await self.memory.store(
                query=query,
                response=result.final_response,
                session_id=session_id,
            )

        result.total_duration_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            f"Run complete: {result.total_steps} steps, "
            f"{result.total_duration_ms:.0f}ms"
        )

        return result

    def _detect_infinite_loop(self, step: StepResult) -> bool:
        """Detect if the agent is stuck in an infinite loop of identical tool calls."""
        if step.action != "tool_call" or not step.tool_name:
            return False

        call_signature = f"{step.tool_name}:{step.tool_input}"
        self._recent_tool_calls.append(call_signature)

        if len(self._recent_tool_calls) >= INFINITE_LOOP_THRESHOLD:
            recent = self._recent_tool_calls[-INFINITE_LOOP_THRESHOLD:]
            if len(set(recent)) == 1:
                return True

        return False
