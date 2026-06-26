"""In-memory verification result store (MVP).

Results are persisted per session.  Multiple verification runs
for the same session are preserved as history.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import VerificationResult


class VerificationResultStore:
    """In-memory store of verification results, keyed by session_id."""

    def __init__(self) -> None:
        self._results: dict[str, list[VerificationResult]] = {}

    def append(self, session_id: str, result: VerificationResult) -> None:
        if result.session_id and result.session_id != session_id:
            raise ValueError(
                f"Result session_id '{result.session_id}' does not match store key '{session_id}'"
            )
        self._results.setdefault(session_id, []).append(result)

    def get_latest(self, session_id: str) -> VerificationResult:
        results = self._results.get(session_id)
        if not results:
            raise KeyError(f"No verification results for session '{session_id}'")
        return results[-1]

    def list_all(self, session_id: str) -> tuple[VerificationResult, ...]:
        results = self._results.get(session_id, [])
        if not results:
            raise KeyError(f"No verification results for session '{session_id}'")
        return tuple(results)

    def has(self, session_id: str) -> bool:
        return bool(self._results.get(session_id))
