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
# Semantic Distillation & Infinite Memory Types
# ---------------------------------------------------------------------------
@dataclass
class DistilledMemoryState:
    """
    Structured semantic compression of historical conversation turns.
    Preserves core entities, user profile facts, active goals, confirmed findings,
    and unresolved questions without unbounded prompt token bloat.
    """

    user_profile_facts: list[str] = field(default_factory=list)
    investigation_goals: list[str] = field(default_factory=list)
    confirmed_findings: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    turn_range_compressed: tuple[int, int] = (0, 0)
    last_updated: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "user_profile_facts": self.user_profile_facts,
            "investigation_goals": self.investigation_goals,
            "confirmed_findings": self.confirmed_findings,
            "unresolved_questions": self.unresolved_questions,
            "turn_range_compressed": list(self.turn_range_compressed),
            "last_updated": self.last_updated or datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> DistilledMemoryState:
        tr = data.get("turn_range_compressed", [0, 0])
        return cls(
            user_profile_facts=list(data.get("user_profile_facts", [])),
            investigation_goals=list(data.get("investigation_goals", [])),
            confirmed_findings=list(data.get("confirmed_findings", [])),
            unresolved_questions=list(data.get("unresolved_questions", [])),
            turn_range_compressed=(tr[0], tr[1]) if isinstance(tr, (list, tuple)) and len(tr) == 2 else (0, 0),
            last_updated=data.get("last_updated"),
        )

    def to_markdown(self) -> str:
        """Render distilled memory state into a high-density Markdown context block."""
        parts = ["[Distilled Historical Context]"]
        if self.user_profile_facts:
            parts.append("**User / Subject Profile:**\n" + "\n".join(f"- {f}" for f in self.user_profile_facts))
        if self.investigation_goals:
            parts.append("**Investigation Goals:**\n" + "\n".join(f"- {g}" for g in self.investigation_goals))
        if self.confirmed_findings:
            parts.append("**Confirmed Findings:**\n" + "\n".join(f"- {cf}" for cf in self.confirmed_findings))
        if self.unresolved_questions:
            parts.append("**Unresolved / Next Steps:**\n" + "\n".join(f"- {q}" for q in self.unresolved_questions))
        return "\n\n".join(parts)


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
        self._distillations: dict[str, DistilledMemoryState] = {}
        
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
            conn.execute('''CREATE TABLE IF NOT EXISTS session_distillations
                            (session_id TEXT PRIMARY KEY,
                             state_json TEXT,
                             last_compressed_msg_id INTEGER,
                             updated_at DATETIME)''')
                            
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

                cur_dist = conn.execute('SELECT session_id, state_json FROM session_distillations')
                for session_id, state_str in cur_dist.fetchall():
                    try:
                        self._distillations[session_id] = DistilledMemoryState.from_dict(json.loads(state_str))
                    except Exception as e:
                        logger.warning(f"Failed to load distillation from DB: {e}")

            logger.info(f"Loaded {sum(len(s) for s in self._sessions.values())} messages and {len(self._distillations)} distillations from DB")
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
                conn.execute('DELETE FROM session_distillations WHERE session_id = ?', (session_id,))
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

    def get_distilled_state(self, session_id: Optional[str] = None) -> Optional[DistilledMemoryState]:
        """Get the current distilled memory state for a session, if any exists."""
        sid = session_id or self._active_session
        return self._distillations.get(sid)

    def set_distilled_state(
        self,
        session_id: str,
        state: DistilledMemoryState,
        last_compressed_msg_id: int = 0,
    ) -> None:
        """Persist distilled memory state to memory and SQLite."""
        self._distillations[session_id] = state
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute(
                    '''INSERT OR REPLACE INTO session_distillations 
                       (session_id, state_json, last_compressed_msg_id, updated_at) 
                       VALUES (?, ?, ?, ?)''',
                    (
                        session_id,
                        json.dumps(state.to_dict()),
                        last_compressed_msg_id,
                        datetime.now(timezone.utc).isoformat(),
                    )
                )
        except Exception as e:
            logger.error(f"Failed to save distilled state in DB: {e}")

    def clear_distilled_state(self, session_id: str) -> None:
        """Clear distilled memory state for a session."""
        self._distillations.pop(session_id, None)
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                conn.execute('DELETE FROM session_distillations WHERE session_id = ?', (session_id,))
        except Exception as e:
            logger.error(f"Failed to clear distilled state in DB: {e}")

    def _deterministic_distill(
        self,
        messages: list[CanonicalMessage],
        existing_state: Optional[DistilledMemoryState] = None,
    ) -> DistilledMemoryState:
        """
        Fast heuristic distillation without external LLM dependencies.
        Extracts user profile facts, active goals, confirmed findings, and open questions.
        """
        state = existing_state or DistilledMemoryState()
        facts = list(state.user_profile_facts)
        goals = list(state.investigation_goals)
        findings = list(state.confirmed_findings)
        questions = list(state.unresolved_questions)

        for msg in messages:
            content = (msg.content or "").strip()
            if not content:
                continue

            lines = [line.strip() for line in content.split("\n") if line.strip()]

            if msg.role == Role.USER:
                # First non-empty user line represents a goal
                first_line = lines[0][:140]
                if first_line and first_line not in goals:
                    goals.append(first_line)

                # Check for profile / patient / domain disclosures
                for line in lines:
                    low = line.lower()
                    if any(cue in low for cue in ["patient", "diagnosed", "mrn", "prescribed", "allergic", "preference", "user id", "i am", "my name", "role:"]):
                        clean_fact = line[:140]
                        if clean_fact not in facts:
                            facts.append(clean_fact)

            elif msg.role == Role.ASSISTANT:
                for line in lines:
                    clean = line.lstrip("-*#0123456789. ")
                    if not clean:
                        continue
                    if clean.endswith("?") and clean not in questions:
                        questions.append(clean[:140])
                    elif any(indicator in line.lower() for indicator in [
                        "result:", "found", "confirmed", "identified", "diagnosis", "recommend",
                        "status:", "value:", "mg", "table", "graph"
                    ]) or line.startswith(("- ", "* ", "1.", "2.")):
                        clean_finding = clean[:140]
                        if clean_finding not in findings and len(clean_finding) > 10:
                            findings.append(clean_finding)

        # Cap items to prevent runaway unbounded arrays
        state.user_profile_facts = facts[-10:]
        state.investigation_goals = goals[-8:]
        state.confirmed_findings = findings[-15:]
        state.unresolved_questions = questions[-6:]
        state.last_updated = datetime.now(timezone.utc).isoformat()
        return state

    async def acompress_session(
        self,
        session_id: Optional[str] = None,
        threshold_messages: int = 8,
        keep_recent_turns: int = 2,
        gateway: Optional[Any] = None,
        model: Optional[str] = None,
    ) -> Optional[DistilledMemoryState]:
        """
        Compress historical turns into a structured DistilledMemoryState.
        
        Preserves raw messages in SQLite permanently, while updating the structured distilled state
        used for lean, infinite-turn prompt assembly.
        """
        sid = session_id or self._active_session
        session = self._sessions.get(sid, [])
        non_system = [m for m in session if m.role != Role.SYSTEM]

        if len(non_system) < threshold_messages:
            return self.get_distilled_state(sid)

        # Older messages before the kept recent turns get distilled
        keep_count = keep_recent_turns * 2
        cutoff_idx = len(non_system) - keep_count
        if cutoff_idx <= 0:
            return self.get_distilled_state(sid)

        older_messages = non_system[:cutoff_idx]
        existing_state = self.get_distilled_state(sid)
        new_state = None

        if gateway is not None:
            try:
                transcript_text = "\n".join(
                    f"{m.role.value.upper()}: {m.content}" for m in older_messages
                )
                existing_json = json.dumps(existing_state.to_dict()) if existing_state else "{}"
                prompt = (
                    "You are an expert context distillation agent.\n"
                    "Your mission is to compress historical conversation turns into a high-density structured JSON summary.\n"
                    "Preserve all patient/user profile facts, active goals, confirmed clinical/domain findings, and open questions.\n\n"
                    f"Existing State:\n{existing_json}\n\n"
                    f"Conversation Turns to Distill:\n{transcript_text}\n\n"
                    "Respond with ONLY a JSON object matching this schema:\n"
                    "{\n"
                    '  "user_profile_facts": ["string"],\n'
                    '  "investigation_goals": ["string"],\n'
                    '  "confirmed_findings": ["string"],\n'
                    '  "unresolved_questions": ["string"]\n'
                    "}"
                )
                resp = await gateway.completion(
                    messages=[
                        {"role": "system", "content": "You are a precise data distillation engine. Output valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    model=model,
                    temperature=0.2,
                )
                content = resp["choices"][0]["message"]["content"].strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                parsed = json.loads(content.strip())
                new_state = DistilledMemoryState.from_dict(parsed)
            except Exception as e:
                logger.warning(f"LLM distillation failed, falling back to deterministic heuristic: {e}")

        if new_state is None:
            new_state = self._deterministic_distill(older_messages, existing_state=existing_state)

        new_state.turn_range_compressed = (0, cutoff_idx)
        self.set_distilled_state(sid, new_state, last_compressed_msg_id=cutoff_idx)
        logger.info(f"Compressed session {sid}: {cutoff_idx} messages distilled into structured state")
        return new_state

    def compress_session(
        self,
        session_id: Optional[str] = None,
        threshold_messages: int = 8,
        keep_recent_turns: int = 2,
    ) -> Optional[DistilledMemoryState]:
        """Synchronous deterministic compression helper."""
        sid = session_id or self._active_session
        session = self._sessions.get(sid, [])
        non_system = [m for m in session if m.role != Role.SYSTEM]
        if len(non_system) < threshold_messages:
            return self.get_distilled_state(sid)

        cutoff_idx = len(non_system) - (keep_recent_turns * 2)
        if cutoff_idx <= 0:
            return self.get_distilled_state(sid)

        older = non_system[:cutoff_idx]
        existing = self.get_distilled_state(sid)
        state = self._deterministic_distill(older, existing_state=existing)
        state.turn_range_compressed = (0, cutoff_idx)
        self.set_distilled_state(sid, state, last_compressed_msg_id=cutoff_idx)
        return state

    def get_optimized_context_window(
        self,
        session_id: Optional[str] = None,
        keep_recent_turns: int = 2,
    ) -> list[CanonicalMessage]:
        """
        Retrieve an optimized context window.
        
        If a distilled memory state exists, returns:
        - System messages
        - Synthetic system message containing [Distilled Historical Context]
        - The most recent non-system messages (keep_recent_turns * 2 messages)
        """
        sid = session_id or self._active_session
        session = self._sessions.get(sid, [])
        distilled = self.get_distilled_state(sid)
        non_system = [m for m in session if m.role != Role.SYSTEM]
        keep_count = keep_recent_turns * 2

        if not distilled or len(non_system) <= keep_count:
            return list(session)

        system_msgs = [m for m in session if m.role == Role.SYSTEM]
        recent_msgs = non_system[-keep_count:]

        distilled_msg = CanonicalMessage(
            role=Role.SYSTEM,
            content=distilled.to_markdown(),
            session_id=sid,
            metadata={"is_distilled_context": True}
        )
        return system_msgs + [distilled_msg] + recent_msgs

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
        """
        Export complete untruncated session messages from database.
        Ensures 100% transcript preservation regardless of live context compression.
        """
        sid = session_id or self._active_session
        try:
            with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
                cur = conn.execute(
                    'SELECT data FROM messages WHERE session_id = ? ORDER BY id ASC',
                    (sid,)
                )
                rows = cur.fetchall()
                if rows:
                    return [json.loads(r[0]) for r in rows]
        except Exception as e:
            logger.warning(f"Error reading complete session from DB: {e}")

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

