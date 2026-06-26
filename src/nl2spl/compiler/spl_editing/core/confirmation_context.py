"""Sealed confirmation context bridging suggestion generation to apply.

The ``ConfirmationContextStore`` provides atomic state transitions
with a re-entrant lock.  Only SEALED contexts are retrievable;
terminal states produce structured tombstones with audit trails.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError

# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


class ConfirmationContextState(Enum):
    """Runtime state of a confirmation context."""

    SEALED = "sealed"
    APPLYING = "applying"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairConfirmationContext:
    """Sealed payload bridging suggestion generation to apply.

    Created during suggestion generation AFTER intent validation passes.
    Contains canonical resolved refs — apply only verifies, never re-resolves.

    This DTO carries no ``state`` field.  Runtime state is managed
    externally by ``ConfirmationContextStore._states``.
    """

    context_id: str
    session_id: str
    suggestion_id: str
    patch_id: str
    compile_run_id: str
    intent_id: str
    issue: Any  # EditableIssue
    target: Any  # RepairTarget
    catalog_entry: Any  # RepairCatalogEntry
    refset: Any  # SelectableRefSet
    selected_ref_ids: tuple[str, ...]
    resolved_refs: tuple[Any, ...]  # ResolvedSelectableRef
    snapshot_id: str
    overlay_version: int
    created_at: str


@dataclass(frozen=True)
class ConfirmationContextTombstone:
    """Immutable record of a terminal context state transition."""

    context_id: str
    session_id: str
    suggestion_id: str
    final_state: ConfirmationContextState
    transitioned_at: str
    reason: str


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class ConfirmationContextStore:
    """Thread-safe store with atomic state transitions.

    State diagram::

        seal()          SEALED
        begin_apply()   SEALED ──→ APPLYING
        abort_apply()   APPLYING ──→ SEALED
        commit_consumed() APPLYING ──→ CONSUMED  (tombstone)
        expire()        SEALED|APPLYING ──→ EXPIRED    (tombstone)
        reject()        SEALED|APPLYING ──→ REJECTED   (tombstone)

    All state transitions are protected by a single ``RLock``.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._contexts: dict[str, RepairConfirmationContext] = {}
        self._states: dict[str, ConfirmationContextState] = {}
        self._tombstones: dict[str, ConfirmationContextTombstone] = {}

    # ── seal ──────────────────────────────────────────────────────────

    def seal(self, ctx: RepairConfirmationContext) -> None:
        """Store a newly created context in SEALED state.

        Raises:
            SPLEditingError: If *context_id* is already active or terminal.
        """
        with self._lock:
            if ctx.context_id in self._contexts:
                raise SPLEditingError(f"Duplicate confirmation context_id: {ctx.context_id}")
            if ctx.context_id in self._tombstones:
                raise SPLEditingError(
                    f"Confirmation context '{ctx.context_id}' is already terminal"
                )
            self._contexts[ctx.context_id] = ctx
            self._states[ctx.context_id] = ConfirmationContextState.SEALED

    # ── get ───────────────────────────────────────────────────────────

    def get(self, context_id: str) -> RepairConfirmationContext:
        """Retrieve a SEALED context.

        Returns:
            The sealed context.

        Raises:
            SPLEditingError: If the context is not found or is not SEALED.
        """
        with self._lock:
            ctx = self._contexts.get(context_id)
            if ctx is None:
                self._raise_if_terminal(context_id)
                raise SPLEditingError(f"Unknown confirmation context_id: {context_id}")
            state = self._states.get(context_id)
            if state != ConfirmationContextState.SEALED:
                raise SPLEditingError(
                    f"Confirmation context '{context_id}' is {state.value}, expected sealed"
                )
            return ctx

    # ── begin_apply ───────────────────────────────────────────────────

    def begin_apply(self, context_id: str) -> RepairConfirmationContext:
        """Atomically transition SEALED → APPLYING.

        Returns:
            The sealed context DTO (before transition).

        Raises:
            SPLEditingError: If the context is not SEALED (e.g. already
                APPLYING, or terminal).
        """
        with self._lock:
            ctx = self._contexts.get(context_id)
            if ctx is None:
                self._raise_if_terminal(context_id)
                raise SPLEditingError(f"Unknown confirmation context_id: {context_id}")
            state = self._states.get(context_id)
            if state == ConfirmationContextState.APPLYING:
                raise SPLEditingError(
                    f"Confirmation context '{context_id}' is already being applied"
                )
            if state != ConfirmationContextState.SEALED:
                raise SPLEditingError(
                    f"Cannot apply: confirmation context '{context_id}' is {state.value}"
                )
            self._states[context_id] = ConfirmationContextState.APPLYING
            return ctx

    # ── abort_apply ───────────────────────────────────────────────────

    def abort_apply(self, context_id: str) -> None:
        """Transition APPLYING → SEALED.  No-op if already SEALED or terminal."""
        with self._lock:
            if self._states.get(context_id) == ConfirmationContextState.APPLYING:
                self._states[context_id] = ConfirmationContextState.SEALED

    # ── commit_consumed ───────────────────────────────────────────────

    def commit_consumed(self, context_id: str) -> RepairConfirmationContext:
        """Atomically transition APPLYING → CONSUMED.

        Returns:
            The consumed context DTO.

        Raises:
            SPLEditingError: If the context is not in APPLYING state.
        """
        with self._lock:
            if self._states.get(context_id) != ConfirmationContextState.APPLYING:
                raise SPLEditingError(
                    f"Cannot commit: confirmation context '{context_id}' is not applying"
                )
            ctx = self._contexts.pop(context_id)
            self._states.pop(context_id, None)
            self._tombstones[context_id] = ConfirmationContextTombstone(
                context_id=context_id,
                session_id=ctx.session_id,
                suggestion_id=ctx.suggestion_id,
                final_state=ConfirmationContextState.CONSUMED,
                transitioned_at=datetime.now(UTC).isoformat(),
                reason="Materialization and persistence succeeded",
            )
            return ctx

    # ── expire ────────────────────────────────────────────────────────

    def expire(self, context_id: str, reason: str) -> None:
        """Transition SEALED|APPLYING → EXPIRED (terminal).

        No-op if the context is already terminal.
        """
        with self._lock:
            ctx = self._contexts.pop(context_id, None)
            if ctx is None:
                return  # already terminal or unknown — no-op
            self._states.pop(context_id, None)
            self._tombstones[context_id] = ConfirmationContextTombstone(
                context_id=context_id,
                session_id=ctx.session_id,
                suggestion_id=ctx.suggestion_id,
                final_state=ConfirmationContextState.EXPIRED,
                transitioned_at=datetime.now(UTC).isoformat(),
                reason=reason,
            )

    # ── reject ────────────────────────────────────────────────────────

    def reject(self, context_id: str, reason: str) -> None:
        """Transition SEALED|APPLYING → REJECTED (terminal).

        No-op if the context is already terminal.
        """
        with self._lock:
            ctx = self._contexts.pop(context_id, None)
            if ctx is None:
                return
            self._states.pop(context_id, None)
            self._tombstones[context_id] = ConfirmationContextTombstone(
                context_id=context_id,
                session_id=ctx.session_id,
                suggestion_id=ctx.suggestion_id,
                final_state=ConfirmationContextState.REJECTED,
                transitioned_at=datetime.now(UTC).isoformat(),
                reason=reason,
            )

    # ── query ─────────────────────────────────────────────────────────

    def is_sealed(self, context_id: str) -> bool:
        """Return True if the context exists and is SEALED."""
        with self._lock:
            return self._states.get(context_id) == ConfirmationContextState.SEALED

    def active_count(self) -> int:
        """Return the number of active (non-terminal) contexts."""
        with self._lock:
            return len(self._contexts)

    # ── internal ──────────────────────────────────────────────────────

    def _raise_if_terminal(self, context_id: str) -> None:
        t = self._tombstones.get(context_id)
        if t is not None:
            raise SPLEditingError(
                f"Confirmation context '{context_id}' is {t.final_state.value}: {t.reason}"
            )
