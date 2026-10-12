"""
Context Engine — Model-agnostic canonical session store with SQLite persistence.

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
import sqlite3
import json
import os
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
    """

    def __init__(self, max_history: int = 100, db_path: str = "data/sessions.db") -> None:
        self.max_history = max_history
        self._sessions: dict[str, list[CanonicalMessage]] = defaultdict(list)
        self._active_session: str = str(uuid.uuid4())
        
        self.db_path = db_path
        self._init_db()
        self._load_from_db()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        # Use check_same_thread=False since FastAPI might access from multiple threads
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS sessions
                            (session_id TEXT PRIMARY KEY, last_active DATETIME)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS messages
                            (id INTEGER PRIMARY KEY AUTOINCREMENT,
                             session_id TEXT,
                             data TEXT)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS active_session
                            (id INTEGER PRIMARY KEY CHECK (id = 1), session_id TEXT)''')
                            
    def _load_from_db(self) -> None:
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cur = conn.execute('SELECT session_id FROM active_session WHERE id = 1')
                row = cur.fetchone()
                if row:
                    self._active_session = row[0]
                
                cur = conn.execute('SELECT session_id, data FROM messages ORDER BY id ASC')
                for session_id, data_str in cur.fetchall():
                    try:
                        data = json.loads(data_str)
                        msg = CanonicalMessage(
                            role=Role(data.get('role', 'user')),
                            content=data.get('content', ''),
                            message_id=data.get('message_id', str(uuid.uuid4())),
                            session_id=data.get('session_id', session_id),
                            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now(timezone.utc).isoformat())),
                            tool_name=data.get('tool_name'),
                            tool_input=data.get('tool_input'),
                            tool_output=data.get('tool_output'),
                            model_used=data.get('model_used'),
                            metadata=data.get('metadata', {}),
                        )
                        self._sessions[session_id].append(msg)
                    except Exception as e:
                        logger.warning(f"Failed to load message from DB: {e}")
            logger.info(f"Loaded {sum(len(s) for s in self._sessions.values())} messages from DB")
        except Exception as e:
            logger.error(f"Failed to initialize ContextEngine from DB: {e}")

    def _save_message_to_db(self, msg: CanonicalMessage) -> None:
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                data = {
                    'role': msg.role.value,
                    'content': msg.content,
                    'message_id': msg.message_id,
                    'session_id': msg.session_id,
                    'timestamp': msg.timestamp.isoformat(),
                    'tool_name': msg.tool_name,
                    'tool_input': msg.tool_input,
                    'tool_output': msg.tool_output,
                    'model_used': msg.model_used,
                    'metadata': msg.metadata,
                }
                conn.execute('INSERT INTO messages (session_id, data) VALUES (?, ?)', 
                             (msg.session_id, json.dumps(data)))
                conn.execute('INSERT OR REPLACE INTO sessions (session_id, last_active) VALUES (?, ?)',
                             (msg.session_id, datetime.now(timezone.utc).isoformat()))
        except Exception as e:
            logger.error(f"Failed to save message to DB: {e}")

    def _set_active_session_db(self, session_id: str) -> None:
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute('INSERT OR REPLACE INTO active_session (id, session_id) VALUES (1, ?)', (session_id,))
        except Exception as e:
            logger.error(f"Failed to set active session in DB: {e}")

    def _clear_session_db(self, session_id: str) -> None:
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
                conn.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        except Exception as e:
            logger.error(f"Failed to clear session from DB: {e}")

    @property
    def active_session_id(self) -> str:
        """Get the active session ID."""
        return self._active_session

    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new session and set it as active."""
        sid = session_id or str(uuid.uuid4())
        self._sessions[sid] = []
        self._active_session = sid
        self._set_active_session_db(sid)
        logger.info(f"Created session: {sid}")
        return sid

    def set_active_session(self, session_id: str) -> None:
        """Switch the active session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._active_session = session_id
        self._set_active_session_db(session_id)

    def add_message(self, message: CanonicalMessage) -> None:
        """
        Add a message to the session store.

        Uses the message's session_id if set, otherwise the active session.
        Enforces max_history by trimming oldest messages (keeping system messages).
        """
        sid = message.session_id or self._active_session
        message.session_id = sid
        session = self._sessions[sid]
        session.append(message)
        
        self._save_message_to_db(message)

        # Enforce history limit in memory (preserve system messages)
        if len(session) > self.max_history:
            system_msgs = [m for m in session if m.role == Role.SYSTEM]
            non_system = [m for m in session if m.role != Role.SYSTEM]
            trimmed = non_system[-(self.max_history - len(system_msgs)):]
            self._sessions[sid] = system_msgs + trimmed
            logger.debug(f"Trimmed session {sid} to {self.max_history} messages")

    def update_last_message_metadata(self, session_id: Optional[str] = None, metadata_updates: dict = None) -> None:
        """
        Update the metadata of the last message in a session (both in-memory and in SQLite).
        Used to persist rich data sources, tools, and execution stats after an agent run completes.
        """
        if not metadata_updates:
            return
        sid = session_id or self._active_session
        session = self._sessions.get(sid, [])
        if not session:
            return

        last_msg = session[-1]
        if not isinstance(last_msg.metadata, dict):
            last_msg.metadata = {}
        last_msg.metadata.update(metadata_updates)

        # Update in SQLite DB
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cur = conn.execute('SELECT id, data FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 1', (sid,))
                row = cur.fetchone()
                if row:
                    msg_id, data_str = row
                    data = json.loads(data_str)
                    if 'metadata' not in data or not isinstance(data['metadata'], dict):
                        data['metadata'] = {}
                    data['metadata'].update(metadata_updates)
                    conn.execute('UPDATE messages SET data = ? WHERE id = ?', (json.dumps(data), msg_id))
        except Exception as e:
            logger.error(f"Failed to update last message metadata in DB: {e}")

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
        """List all sessions with message counts, sorted by latest activity descending."""
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT session_id, count(id) as msg_count, max(id) as last_id
                    FROM messages
                    GROUP BY session_id
                    ORDER BY last_id DESC
                """)
                rows = cur.fetchall()
                if rows:
                    return [
                        {
                            "session_id": r[0],
                            "message_count": r[1],
                            "is_active": r[0] == self._active_session,
                        }
                        for r in rows
                    ]
        except Exception as e:
            logger.warning(f"Error querying sessions from DB: {e}")

        return [
            {
                "session_id": sid,
                "message_count": len(msgs),
                "is_active": sid == self._active_session,
            }
            for sid, msgs in reversed(list(self._sessions.items()))
        ]

    def clear_session(self, session_id: Optional[str] = None) -> None:
        """Clear all messages in a session and remove it."""
        sid = session_id or self._active_session
        if sid in self._sessions:
            del self._sessions[sid]
        self._clear_session_db(sid)
        logger.info(f"Cleared and removed session: {sid}")

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
        imported = []
        for m in messages:
            msg = CanonicalMessage(
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
            imported.append(msg)
            
        self._sessions[sid] = imported
        
        # Persist to DB
        self._set_active_session_db(sid)
        for msg in imported:
            self._save_message_to_db(msg)
            
        logger.info(f"Imported {len(messages)} messages into session {sid}")
        return sid

