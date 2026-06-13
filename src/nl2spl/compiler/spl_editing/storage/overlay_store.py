"""In-memory overlay event store (MVP).

Overlay events form an append-only log of accepted patches, scoped by
``(compile_run_id, snapshot_id)``.  Different runs are fully isolated.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import StaleRevisionError
from nl2spl.compiler.spl_editing.core.revision import OverlayEvent


class OverlayStore:
    """Append-only in-memory store of overlay events.

    Snapshots must be explicitly registered before overlay events
    can be appended or queried.  Registration and queries are scoped
    by ``(compile_run_id, snapshot_id)``.
    """

    def __init__(self) -> None:
        self._events: dict[str, OverlayEvent] = {}           # overlay_id → event
        self._by_run_snap: dict[tuple[str, str], list[str]] = {}  # (run, snap) → [overlay_id]
        self._known: set[tuple[str, str]] = set()            # registered (run, snap)

    def register_snapshot(
        self, compile_run_id: str, snapshot_id: str,
    ) -> None:
        self._known.add((compile_run_id, snapshot_id))

    def append(self, event: OverlayEvent) -> None:
        if event.overlay_id in self._events:
            raise KeyError(
                f"Overlay event '{event.overlay_id}' already exists"
            )
        run_key = (event.base_compile_run_id, event.base_artifact_snapshot_id)
        if run_key not in self._known:
            raise KeyError(
                f"Snapshot '{event.base_compile_run_id}/"
                f"{event.base_artifact_snapshot_id}' "
                f"is not registered in OverlayStore"
            )
        current = self._latest_version(run_key)
        expected = current + 1
        if event.overlay_version != expected:
            raise StaleRevisionError(
                f"Overlay version must be {expected} for snapshot "
                f"'{event.base_compile_run_id}/"
                f"{event.base_artifact_snapshot_id}', "
                f"got {event.overlay_version}"
            )
        self._events[event.overlay_id] = event
        self._by_run_snap.setdefault(run_key, []).append(event.overlay_id)

    def get(self, overlay_id: str) -> OverlayEvent:
        return self._events[overlay_id]

    def has(self, overlay_id: str) -> bool:
        return overlay_id in self._events

    def list_for_snapshot(
        self, compile_run_id: str, snapshot_id: str,
    ) -> tuple[OverlayEvent, ...]:
        run_key = (compile_run_id, snapshot_id)
        if run_key not in self._known:
            raise KeyError(
                f"Snapshot '{compile_run_id}/{snapshot_id}' "
                f"is not registered in OverlayStore"
            )
        ids = self._by_run_snap.get(run_key, [])
        return tuple(self._events[sid] for sid in ids)

    def latest_overlay_version(
        self, compile_run_id: str, snapshot_id: str,
    ) -> int:
        run_key = (compile_run_id, snapshot_id)
        if run_key not in self._known:
            raise KeyError(
                f"Snapshot '{compile_run_id}/{snapshot_id}' "
                f"is not registered in OverlayStore"
            )
        return self._latest_version(run_key)

    def _latest_version(self, run_key: tuple[str, str]) -> int:
        ids = self._by_run_snap.get(run_key, [])
        if not ids:
            return 0
        return max(self._events[sid].overlay_version for sid in ids)
