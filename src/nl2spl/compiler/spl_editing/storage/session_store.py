"""In-memory editing session store (MVP)."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import EditingSession


class SessionStore:
    """In-memory store of editing sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, EditingSession] = {}

    def put(self, session: EditingSession) -> None:
        if session.session_id in self._sessions:
            raise KeyError(
                f"Session '{session.session_id}' already exists"
            )
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> EditingSession:
        return self._sessions[session_id]

    def has(self, session_id: str) -> bool:
        return session_id in self._sessions

    def replace(self, session: EditingSession) -> None:
        """Store or replace a session (allows overwrite)."""
        self._sessions[session.session_id] = session
