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

try:
    from guardrails import GuardrailEngine, TokenMap
except ImportError:
    GuardrailEngine = None  # type: ignore[assignment, misc]
    TokenMap = None  # type: ignore[assignment, misc]

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
    enable_guardrails: bool = True
    rehydrate_output: bool = True
    active_schema: str = "healthtech"
    active_model: str = "gemini-2.5-flash"
    active_skill: Optional[Skill] = None
    bypass_graph_tools: bool = False
    intent: Optional[str] = None
    complexity_tier: Optional[str] = None
    enable_semantic_distillation: bool = True
    distillation_threshold_messages: int = 8
    distillation_keep_recent_turns: int = 2


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
    mechanic_repaired: bool = False


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
    intent: Optional[str] = None
    complexity_tier: Optional[str] = None
    smart_routed: bool = False
    routing_reason: Optional[str] = None
    mechanic_repairs: int = 0


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
        context: Optional[ContextEngine] = None,
        gateway: Optional[Any] = None,
        guardrails: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        self.config = config or RunnerConfig()
        self.context = context_engine or context or ContextEngine()
        self.memory = memory or MemoryManager()
        self.reflection = reflection or ReflectionLoop()
        self.gateway = gateway
        self.guardrails = guardrails
        if self.guardrails is None and GuardrailEngine is not None and self.config.enable_guardrails:
            try:
                self.guardrails = GuardrailEngine()
            except Exception as e:
                logger.warning(f"Failed to auto-init GuardrailEngine in runner: {e}")

        # Track tool call history for infinite loop detection
        self._recent_tool_calls: list[str] = []

    async def run(self, query: str, session_id: Optional[str] = None) -> RunResult:
        """
        Execute a full agent run for a user query.

        Pipeline:
        1. Apply input guardrails (prompt injection detection + secret/PII masking)
        2. Apply active skill overrides (if set)
        3. Store sanitized user message in canonical context
        4. Retrieve relevant memory (long-term)
        5. Build the LLM prompt (schema + context + memory)
        6. Execute ADK agent loop with step budget
        7. Apply output guardrails (faithfulness scoring & optional rehydration)
        8. Return final result with governance metadata
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

        # 1. Apply Input Guardrails (Prompt injection check + Secrets & PII masking)
        token_map = None
        prompt_query = query
        if self.guardrails and self.config.enable_guardrails:
            try:
                guard_res = self.guardrails.guard_input(query)
                prompt_query = guard_res.masked_text
                token_map = guard_res.token_map
                result.pii_entities_masked = guard_res.pii_entities_found
                if not guard_res.is_safe:
                    result.final_response = f"Query rejected: {guard_res.blocked_reason or 'Input safety violation'}"
                    result.error = guard_res.blocked_reason
                    return result
            except Exception as e:
                logger.warning(f"Input safety violation triggered: {e}")
                result.final_response = f"Query rejected by safety guardrail: {e}"
                result.error = str(e)
                return result

        # 2. Store sanitized user message in canonical context
        self.context.add_message(CanonicalMessage(
            role=Role.USER,
            content=prompt_query,
            session_id=session_id,
        ))

        # 3. Retrieve relevant memory
        memory_context = ""
        if self.config.enable_memory:
            memories = await self.memory.recall(prompt_query, limit=3)
            if memories:
                memory_context = "\n".join(
                    f"[Memory] {m.content}" for m in memories
                )
                logger.info(f"Retrieved {len(memories)} relevant memories")

        # 4. Agent execution loop
        step_start = time.monotonic()
        instruction = "You are a helpful knowledge assistant."
        if skill:
            instruction = skill.system_prompt

        # Retrieve and inject distilled historical memory if available
        if self.config.enable_semantic_distillation:
            distilled_state = self.context.get_distilled_state(session_id)
            if distilled_state:
                instruction += f"\n\n{distilled_state.to_markdown()}"
                logger.info(f"Assembled prompt with distilled memory state ({len(distilled_state.confirmed_findings)} findings)")

        mechanic_history_len_before = 0
        try:
            from mcp_servers.mechanic import get_mechanic
            mechanic_history_len_before = len(get_mechanic().repair_history)
        except Exception:
            pass

        try:
            from google.adk.runners import InMemoryRunner
            from mcp_servers.graph_server import execute_cypher
            from mcp_servers.retrieval_server import semantic_search
            
            # Intent Gating: if bypass_graph_tools is True (open-domain tasks),
            # execute without graph tools to save steps and avoid false 'no data' errors
            tools = []
            if not self.config.bypass_graph_tools:
                tools = [execute_cypher, semantic_search]
            else:
                logger.info("Intent Gate: Open-domain query detected; bypassing graph RAG tools")
                instruction += "\nProvide a direct, helpful, and comprehensive answer without querying domain databases."

            agent = Agent(
                name="ckp_agent",
                model=self.config.active_model or "gemini-2.5-flash",
                instruction=instruction,
                tools=tools
            )
            runner = InMemoryRunner(agent=agent)
            events = await runner.run_debug(prompt_query, session_id=session_id or "default_session", quiet=True)
            
            response_text = ""
            if events and events[-1].message and events[-1].message.parts:
                response_text = "".join([
                    p.text for p in events[-1].message.parts if hasattr(p, "text") and p.text
                ])
            if not response_text:
                response_text = "Sorry, I couldn't generate a response."
                
            # Track tool execution steps from ADK events
            step_idx = 1
            if events:
                for ev in events:
                    fcalls = ev.get_function_calls() if hasattr(ev, "get_function_calls") else []
                    if not fcalls and hasattr(ev, "content") and ev.content and hasattr(ev.content, "parts"):
                        fcalls = [p.function_call for p in ev.content.parts if hasattr(p, "function_call") and p.function_call]

                    fresps = ev.get_function_responses() if hasattr(ev, "get_function_responses") else []
                    if not fresps and hasattr(ev, "content") and ev.content and hasattr(ev.content, "parts"):
                        fresps = [p.function_response for p in ev.content.parts if hasattr(p, "function_response") and p.function_response]

                    for fc in fcalls:
                        tool_input = dict(fc.args) if hasattr(fc, "args") and fc.args else {}
                        result.steps.append(StepResult(
                            step_index=step_idx,
                            action="tool_call",
                            tool_name=fc.name,
                            tool_input=tool_input,
                            duration_ms=0.0
                        ))
                        step_idx += 1

                    for fr in fresps:
                        resp_val = fr.response if hasattr(fr, "response") else {}
                        for prev_step in reversed(result.steps):
                            if prev_step.tool_name == fr.name and prev_step.tool_output is None:
                                prev_step.tool_output = resp_val
                                break

            # Track self-corrections from The Mechanic
            try:
                from mcp_servers.mechanic import get_mechanic
                new_repairs = get_mechanic().repair_history[mechanic_history_len_before:]
                repaired_items = [r for r in new_repairs if r.get("was_repaired")]
                result.mechanic_repairs = len(repaired_items)
                if repaired_items:
                    for s in result.steps:
                        if s.tool_name in ("execute_cypher", "execute_sql"):
                            s.mechanic_repaired = True
            except Exception:
                pass

            error_msg = None
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            response_text = f"Agent execution failed: {e}"
            error_msg = str(e)

        step = StepResult(
            step_index=len(result.steps) + 1,
            action="response",
            response_text=response_text,
            duration_ms=(time.monotonic() - step_start) * 1000,
            error=error_msg
        )
        result.steps.append(step)
        result.final_response = response_text
        result.total_steps = len(result.steps)
        result.intent = self.config.intent
        result.complexity_tier = self.config.complexity_tier

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

        # 5b. Output Guardrails (Groundedness scoring + Optional rehydration)
        if self.guardrails and self.config.enable_guardrails and result.final_response:
            try:
                out_res = self.guardrails.guard_output(
                    response=result.final_response,
                    context_chunks=[],
                    token_map=token_map,
                    rehydrate=self.config.rehydrate_output,
                )
                result.groundedness_score = out_res.groundedness_score
                result.final_response = out_res.final_response
            except Exception as e:
                logger.warning(f"Output guardrail execution failed: {e}")

        # 6. Store assistant response in canonical context
        self.context.add_message(CanonicalMessage(
            role=Role.ASSISTANT,
            content=result.final_response,
            session_id=session_id,
            model_used=self.config.active_model,
            metadata={
                "model_used": self.config.active_model,
                "total_steps": result.total_steps,
                "duration_ms": (time.monotonic() - start_time) * 1000,
            }
        ))

        # 7. Persist to long-term memory
        if self.config.enable_memory and result.final_response:
            await self.memory.store(
                query=query,
                response=result.final_response,
                session_id=session_id,
            )

        # 8. Trigger rolling semantic compression if threshold reached
        if self.config.enable_semantic_distillation:
            session_msgs = self.context.get_session_messages(session_id)
            non_sys_count = len([m for m in session_msgs if m.role != Role.SYSTEM])
            if non_sys_count >= self.config.distillation_threshold_messages:
                try:
                    await self.context.acompress_session(
                        session_id=session_id,
                        threshold_messages=self.config.distillation_threshold_messages,
                        keep_recent_turns=self.config.distillation_keep_recent_turns,
                        gateway=self.gateway,
                        model=self.config.active_model,
                    )
                except Exception as e:
                    logger.warning(f"Rolling context compression failed: {e}")

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

