"""In-memory suggestion store (MVP).

Suggestions are stored but do NOT mutate artifacts.  Only
``apply_suggestion`` through the service layer can trigger
artifact changes.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import RepairSuggestion


class SuggestionStore:
    """In-memory store of repair suggestions.

    Sessions must be explicitly registered before suggestions
    can be stored or listed.  Unknown session IDs raise ``KeyError``
    — no silent fallback to empty.
    """

    def __init__(self) -> None:
        self._suggestions: dict[str, RepairSuggestion] = {}
        self._by_session: dict[str, list[str]] = {}
        self._known_sessions: set[str] = set()

    def register_session(self, session_id: str) -> None:
        """Register a session as known to this store.

        Must be called before ``put()`` or ``list_for_session()``.
        """
        self._known_sessions.add(session_id)

    def put(self, suggestion: RepairSuggestion) -> None:
        if suggestion.suggestion_id in self._suggestions:
            raise KeyError(
                f"Suggestion '{suggestion.suggestion_id}' already exists"
            )
        if suggestion.session_id not in self._known_sessions:
            raise KeyError(
                f"Session '{suggestion.session_id}' is not registered "
                f"in SuggestionStore"
            )
        self._suggestions[suggestion.suggestion_id] = suggestion
        self._by_session.setdefault(suggestion.session_id, []).append(
            suggestion.suggestion_id
        )

    def get(self, suggestion_id: str) -> RepairSuggestion:
        return self._suggestions[suggestion_id]

    def has(self, suggestion_id: str) -> bool:
        return suggestion_id in self._suggestions

    def list_for_session(self, session_id: str) -> tuple[RepairSuggestion, ...]:
        if session_id not in self._known_sessions:
            raise KeyError(
                f"Session '{session_id}' is not registered in SuggestionStore"
            )
        ids = self._by_session.get(session_id, [])
        return tuple(self._suggestions[sid] for sid in ids)
