"""
Context Engine — Model-agnostic canonical session store.

The single source of truth for conversation state. All messages are stored
in a canonical format (CanonicalMessage) and converted to provider-specific
formats on-the-fly via format adapters.

This enables mid-session model switching with zero context loss:
Switch from Gemini → OpenAI → Ollama without losing conversation history.

Design principle: "Never store state in the LLM's context window as
the source of truth."
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical Message Types
# ---------------------------------------------------------------------------
class Role(str, Enum):
    """Universal message roles across all LLM providers."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


@dataclass
class CanonicalMessage:
    """
    Provider-agnostic message format.

    This is the single source of truth for a conversation turn.
    It stores enough information to serialize into any provider's
    format via a ModelAdapter.
    """

    role: Role
    content: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Tool-specific fields
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_output: Optional[Any] = None
    tool_call_id: Optional[str] = None

    # Metadata
    model_used: Optional[str] = None
    token_count: Optional[int] = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Session Store
# ---------------------------------------------------------------------------
class ContextEngine:
    """
    Canonical session store — the source of truth for all conversations.

    Stores messages in a provider-agnostic format and provides:
    - Session management (create, retrieve, list)
    - Message history with windowing
    - Context formatting for LLM consumption
    - Session export/import for persistence

    Usage:
        ctx = ContextEngine()
        ctx.add_message(CanonicalMessage(role=Role.USER, content="Hello"))
        ctx.add_message(CanonicalMessage(role=Role.ASSISTANT, content="Hi!"))

        # Get messages for LLM context:
        messages = ctx.get_context_window(max_messages=20)

        # Switch models mid-session — just change the adapter:
        gemini_msgs = adapter.format(messages, provider="gemini")
        openai_msgs = adapter.format(messages, provider="openai")
    """

    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max_history
        self._sessions: dict[str, list[CanonicalMessage]] = defaultdict(list)
        self._active_session: str = str(uuid.uuid4())

    @property
    def active_session_id(self) -> str:
        """Get the active session ID."""
        return self._active_session

    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new session and set it as active."""
        sid = session_id or str(uuid.uuid4())
        self._sessions[sid] = []
        self._active_session = sid
        logger.info(f"Created session: {sid}")
        return sid

    def set_active_session(self, session_id: str) -> None:
        """Switch the active session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._active_session = session_id

    def add_message(self, message: CanonicalMessage) -> None:
        """
        Add a message to the session store.

        Uses the message's session_id if set, otherwise the active session.
        Enforces max_history by trimming oldest messages (keeping system messages).
        """
        sid = message.session_id or self._active_session
        session = self._sessions[sid]
        session.append(message)

        # Enforce history limit (preserve system messages)
        if len(session) > self.max_history:
            system_msgs = [m for m in session if m.role == Role.SYSTEM]
            non_system = [m for m in session if m.role != Role.SYSTEM]
            trimmed = non_system[-(self.max_history - len(system_msgs)):]
            self._sessions[sid] = system_msgs + trimmed
            logger.debug(f"Trimmed session {sid} to {self.max_history} messages")

    def get_context_window(
        self,
        session_id: Optional[str] = None,
        max_messages: Optional[int] = None,
    ) -> list[CanonicalMessage]:
        """
        Retrieve the context window for LLM consumption.

        Always includes system messages, then the most recent conversation
        turns up to max_messages.
        """
        sid = session_id or self._active_session
        session = self._sessions.get(sid, [])

        if not max_messages or len(session) <= max_messages:
            return list(session)

        # Always include system messages
        system_msgs = [m for m in session if m.role == Role.SYSTEM]
        non_system = [m for m in session if m.role != Role.SYSTEM]
        recent = non_system[-(max_messages - len(system_msgs)):]
        return system_msgs + recent

    def get_session_messages(
        self, session_id: Optional[str] = None
    ) -> list[CanonicalMessage]:
        """Get all messages in a session."""
        sid = session_id or self._active_session
        return list(self._sessions.get(sid, []))

    def list_sessions(self) -> list[dict]:
        """List all sessions with message counts."""
        return [
            {
                "session_id": sid,
                "message_count": len(msgs),
                "is_active": sid == self._active_session,
            }
            for sid, msgs in self._sessions.items()
        ]

    def clear_session(self, session_id: Optional[str] = None) -> None:
        """Clear all messages in a session."""
        sid = session_id or self._active_session
        self._sessions[sid] = []
        logger.info(f"Cleared session: {sid}")

    def export_session(self, session_id: Optional[str] = None) -> list[dict]:
        """Export a session as a list of serializable dicts."""
        sid = session_id or self._active_session
        return [
            {
                "role": m.role.value,
                "content": m.content,
                "message_id": m.message_id,
                "timestamp": m.timestamp.isoformat(),
                "tool_name": m.tool_name,
                "tool_input": m.tool_input,
                "tool_output": m.tool_output,
                "model_used": m.model_used,
                "metadata": m.metadata,
            }
            for m in self._sessions.get(sid, [])
        ]

    def import_session(self, messages: list[dict], session_id: Optional[str] = None) -> str:
        """Import a session from a list of dicts."""
        sid = session_id or str(uuid.uuid4())
        self._sessions[sid] = [
            CanonicalMessage(
                role=Role(m["role"]),
                content=m["content"],
                message_id=m.get("message_id", str(uuid.uuid4())),
                session_id=sid,
                tool_name=m.get("tool_name"),
                tool_input=m.get("tool_input"),
                tool_output=m.get("tool_output"),
                model_used=m.get("model_used"),
                metadata=m.get("metadata", {}),
            )
            for m in messages
        ]
        logger.info(f"Imported {len(messages)} messages into session {sid}")
        return sid
