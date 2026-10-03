"""Tests for ContextEngine — Model-agnostic session storage."""

from __future__ import annotations

import pytest

from agent_harness.context_engine import ContextEngine, CanonicalMessage, Role


class TestContextEngine:
    """Verify session management and message storage."""

    def test_add_message(self):
        """Messages should be stored in the active session."""
        ce = ContextEngine()
        ce.add_message(CanonicalMessage(role=Role.USER, content="Hello world"))
        
        history = ce.get_session_messages()
        assert len(history) == 1
        assert history[0].role == Role.USER
        assert history[0].content == "Hello world"

    def test_session_isolation(self):
        """Messages should be isolated between different sessions."""
        ce = ContextEngine()
        ce.set_active_session("session-A")
        ce.add_message(CanonicalMessage(role=Role.USER, content="Message A"))

        ce.set_active_session("session-B")
        ce.add_message(CanonicalMessage(role=Role.USER, content="Message B"))

        ce.set_active_session("session-A")
        history_a = ce.get_session_messages()
        assert len(history_a) == 1
        assert history_a[0].content == "Message A"

        ce.set_active_session("session-B")
        history_b = ce.get_session_messages()
        assert len(history_b) == 1
        assert history_b[0].content == "Message B"

    def test_clear_session(self):
        """Clearing a session should remove its messages."""
        ce = ContextEngine()
        ce.add_message(CanonicalMessage(role=Role.USER, content="Hello"))
        assert len(ce.get_session_messages()) == 1
        
        ce.clear_session()
        assert len(ce.get_session_messages()) == 0

    def test_list_sessions(self):
        """list_sessions should return metadata for all tracked sessions."""
        ce = ContextEngine()
        ce.set_active_session("session-1")
        ce.add_message(CanonicalMessage(role=Role.USER, content="A"))
        
        ce.set_active_session("session-2")
        ce.add_message(CanonicalMessage(role=Role.USER, content="B"))
        ce.add_message(CanonicalMessage(role=Role.ASSISTANT, content="C"))

        sessions = ce.list_sessions()
        assert len(sessions) == 2
        
        s1 = next(s for s in sessions if s["session_id"] == "session-1")
        assert s1["message_count"] == 1
        
        s2 = next(s for s in sessions if s["session_id"] == "session-2")
        assert s2["message_count"] == 2

    def test_export_session(self):
        """Export session should return a list of JSON-serializable dicts."""
        ce = ContextEngine()
        ce.add_message(CanonicalMessage(role=Role.USER, content="Test"))
        
        export = ce.export_session()
        assert len(export) == 1
        assert isinstance(export[0], dict)
        assert export[0]["role"] == "user"
        assert export[0]["content"] == "Test"
