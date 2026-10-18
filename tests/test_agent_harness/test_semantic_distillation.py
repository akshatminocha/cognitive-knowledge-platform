"""
Tests for Phase 5: Semantic Distillation & Infinite Memory.
Validates rolling memory compression, prompt assembly optimization, and complete archival persistence.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent_harness.context_engine import (
    ContextEngine,
    CanonicalMessage,
    Role,
    DistilledMemoryState,
)
from agent_harness.runner import AgentRunner, RunnerConfig


@pytest.fixture
def ce():
    """Isolated in-memory ContextEngine fixture."""
    return ContextEngine(db_path=":memory:")


class TestDistilledMemoryState:
    """Verify DistilledMemoryState serialization, deserialization, and markdown formatting."""

    def test_state_serialization_roundtrip(self):
        state = DistilledMemoryState(
            user_profile_facts=["Patient PAT-001 is a 52yo male", "Allergic to Penicillin"],
            investigation_goals=["Assess Lisinopril interaction with Potassium supplements"],
            confirmed_findings=["Serum potassium level is 5.8 mEq/L (hyperkalemia)"],
            unresolved_questions=["Has patient discontinued potassium chloride?"],
            turn_range_compressed=(0, 6),
        )

        serialized = state.to_dict()
        assert serialized["user_profile_facts"] == state.user_profile_facts
        assert serialized["turn_range_compressed"] == [0, 6]

        restored = DistilledMemoryState.from_dict(serialized)
        assert restored.user_profile_facts == state.user_profile_facts
        assert restored.investigation_goals == state.investigation_goals
        assert restored.confirmed_findings == state.confirmed_findings
        assert restored.unresolved_questions == state.unresolved_questions
        assert restored.turn_range_compressed == (0, 6)

    def test_to_markdown_formatting(self):
        state = DistilledMemoryState(
            user_profile_facts=["Role: Chief Medical Officer"],
            investigation_goals=["Evaluate Q3 clinical trial efficacy"],
            confirmed_findings=["Primary endpoint achieved with p < 0.01"],
            unresolved_questions=["What is the secondary endpoint safety profile?"],
        )

        md = state.to_markdown()
        assert "[Distilled Historical Context]" in md
        assert "Chief Medical Officer" in md
        assert "Evaluate Q3 clinical trial efficacy" in md
        assert "Primary endpoint achieved" in md
        assert "What is the secondary endpoint safety profile?" in md


class TestSemanticDistillationEngine:
    """Verify ContextEngine distillation, threshold trigger, and context window assembly."""

    def test_deterministic_distillation(self, ce):
        """Test heuristic distillation extracts key facts, goals, findings, and questions."""
        messages = [
            CanonicalMessage(role=Role.USER, content="Hello, my name is Dr. Watson. Patient PAT-999 has hypertension."),
            CanonicalMessage(role=Role.ASSISTANT, content="Confirmed patient PAT-999 records found. Blood pressure is 150/95."),
            CanonicalMessage(role=Role.USER, content="Can we prescribe Lisinopril 10mg?"),
            CanonicalMessage(role=Role.ASSISTANT, content="Lisinopril 10mg is indicated. Should we check kidney function before initiation?"),
        ]

        state = ce._deterministic_distill(messages)
        assert len(state.investigation_goals) >= 1
        assert any("PAT-999" in f or "Dr. Watson" in f or "patient" in f.lower() for f in state.user_profile_facts)
        assert any("150/95" in f or "Lisinopril" in f or "indicated" in f for f in state.confirmed_findings)
        assert any("kidney function" in q for q in state.unresolved_questions)

    def test_rolling_compression_trigger(self, ce):
        """Verify that compression occurs when session reaches message threshold."""
        sid = ce.create_session("long_session")

        # Add 10 messages (5 turns)
        for i in range(5):
            ce.add_message(CanonicalMessage(role=Role.USER, content=f"Query {i}: Patient PAT-10{i} status check", session_id=sid))
            ce.add_message(CanonicalMessage(role=Role.ASSISTANT, content=f"Result {i}: Value confirmed at {i*10} mg.", session_id=sid))

        assert len(ce.get_session_messages(sid)) == 10
        assert ce.get_distilled_state(sid) is None

        # Compress keeping last 2 turns (4 messages)
        distilled = ce.compress_session(sid, threshold_messages=8, keep_recent_turns=2)
        assert distilled is not None
        assert ce.get_distilled_state(sid) is not None

        # Verify cut-off index: 10 non-system messages - 4 kept = 6 compressed
        assert distilled.turn_range_compressed == (0, 6)

    def test_optimized_context_window(self, ce):
        """Optimized window replaces older turns with distilled summary, keeping recent turns intact."""
        sid = ce.create_session("opt_session")

        for i in range(6):
            ce.add_message(CanonicalMessage(role=Role.USER, content=f"Turn {i} question regarding medication", session_id=sid))
            ce.add_message(CanonicalMessage(role=Role.ASSISTANT, content=f"Turn {i} answer: confirmed clinical outcome", session_id=sid))

        # Before compression: all 12 messages returned
        raw_window = ce.get_optimized_context_window(sid, keep_recent_turns=2)
        assert len(raw_window) == 12

        # Compress
        ce.compress_session(sid, threshold_messages=8, keep_recent_turns=2)

        # After compression: 1 synthetic distilled message + 4 recent messages = 5 messages
        opt_window = ce.get_optimized_context_window(sid, keep_recent_turns=2)
        assert len(opt_window) == 5
        assert opt_window[0].role == Role.SYSTEM
        assert opt_window[0].metadata.get("is_distilled_context") is True
        assert "[Distilled Historical Context]" in opt_window[0].content
        assert opt_window[-1].content == "Turn 5 answer: confirmed clinical outcome"

    def test_complete_archival_preservation(self, ce):
        """Full export_session() must return 100% of untruncated messages regardless of context compression."""
        sid = ce.create_session("archive_session")

        for i in range(8):
            ce.add_message(CanonicalMessage(role=Role.USER, content=f"Turn {i} user message", session_id=sid))
            ce.add_message(CanonicalMessage(role=Role.ASSISTANT, content=f"Turn {i} assistant response", session_id=sid))

        assert len(ce.get_session_messages(sid)) == 16

        # Trigger compression
        ce.compress_session(sid, threshold_messages=8, keep_recent_turns=2)

        # Context window is compressed
        opt_window = ce.get_optimized_context_window(sid, keep_recent_turns=2)
        assert len(opt_window) < 16

        # But export_session() preserves ALL 16 original messages for .uka bundling
        exported = ce.export_session(sid)
        assert len(exported) == 16
        assert exported[0]["content"] == "Turn 0 user message"
        assert exported[-1]["content"] == "Turn 7 assistant response"


@pytest.mark.asyncio
class TestAsyncLLMDistillation:
    """Verify async LLM-guided distillation with mock Gateway."""

    async def test_llm_guided_distillation(self, ce):
        sid = ce.create_session("llm_session")
        for i in range(5):
            ce.add_message(CanonicalMessage(role=Role.USER, content=f"User {i}", session_id=sid))
            ce.add_message(CanonicalMessage(role=Role.ASSISTANT, content=f"Assistant {i}", session_id=sid))

        mock_gateway = MagicMock()
        mock_gateway.completion = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": """{
                        "user_profile_facts": ["Patient has Stage 2 CKD"],
                        "investigation_goals": ["Monitor creatinine clearance"],
                        "confirmed_findings": ["Baseline creatinine is 1.4 mg/dL"],
                        "unresolved_questions": ["Schedule repeat renal panel?"]
                    }"""
                }
            }]
        })

        distilled = await ce.acompress_session(
            session_id=sid,
            threshold_messages=8,
            keep_recent_turns=2,
            gateway=mock_gateway,
            model="gemini-2.5-flash",
        )

        assert distilled is not None
        assert distilled.user_profile_facts == ["Patient has Stage 2 CKD"]
        assert distilled.confirmed_findings == ["Baseline creatinine is 1.4 mg/dL"]
        mock_gateway.completion.assert_awaited_once()


@pytest.mark.asyncio
class TestAgentRunnerDistillationIntegration:
    """Verify AgentRunner prompt injection and post-run automatic distillation."""

    async def test_runner_injects_distilled_context(self, ce):
        sid = ce.create_session("runner_session")
        # Pre-seed a distilled state
        ce.set_distilled_state(sid, DistilledMemoryState(
            user_profile_facts=["Patient PAT-777 active"],
            confirmed_findings=["Genetic marker BRAF V600E confirmed positive"],
        ))

        runner = AgentRunner(
            config=RunnerConfig(active_model="gemini-2.5-flash", enable_memory=False, enable_reflection=False),
            context_engine=ce,
        )

        # Mock out InMemoryRunner inside runner.run
        mock_event = MagicMock()
        mock_part = MagicMock()
        mock_part.text = "Understood. BRAF V600E mutation noted for therapy planning."
        mock_event.message.parts = [mock_part]
        mock_event.get_function_calls.return_value = []
        mock_event.get_function_responses.return_value = []

        mock_adk_runner = MagicMock()
        mock_adk_runner.run_debug = AsyncMock(return_value=[mock_event])

        from unittest.mock import patch
        with patch("google.adk.runners.InMemoryRunner", return_value=mock_adk_runner):
            result = await runner.run("What therapy is recommended?", session_id=sid)

        assert result.final_response == "Understood. BRAF V600E mutation noted for therapy planning."
        # Verify the message was added to session
        msgs = ce.get_session_messages(sid)
        assert len(msgs) == 2
        assert msgs[-1].content == result.final_response
