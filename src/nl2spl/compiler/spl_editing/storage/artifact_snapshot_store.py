"""In-memory artifact snapshot store (MVP).

Stores frozen ``ArtifactSnapshot`` objects keyed by the full revision
identity: ``(compile_run_id, snapshot_id, overlay_version)``.
Different runs are fully isolated — same ``snapshot_id`` in two runs
never collides.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot


class ArtifactSnapshotStore:
    """In-memory store of frozen artifact snapshots.

    All operations are scoped by ``(compile_run_id, snapshot_id)``.
    Omit *overlay_version* to get the latest; pass it to get a
    specific revision.
    """

    def __init__(self) -> None:
        # (compile_run_id, snapshot_id, overlay_version) → ArtifactSnapshot
        self._snapshots: dict[tuple[str, str, int], ArtifactSnapshot] = {}
        # (compile_run_id, snapshot_id) → max overlay_version
        self._latest: dict[tuple[str, str], int] = {}

    def put(self, snapshot: ArtifactSnapshot) -> None:
        run_id = snapshot.compile_run_id
        sid = snapshot.snapshot_id
        key = (run_id, sid, snapshot.overlay_version)
        if key in self._snapshots:
            raise KeyError(
                f"Snapshot ('{run_id}', '{sid}', "
                f"v{snapshot.overlay_version}) already exists"
            )
        self._snapshots[key] = snapshot
        run_key = (run_id, sid)
        current = self._latest.get(run_key, -1)
        if snapshot.overlay_version > current:
            self._latest[run_key] = snapshot.overlay_version

    def get(
        self,
        compile_run_id: str,
        snapshot_id: str,
        overlay_version: int | None = None,
    ) -> ArtifactSnapshot:
        """Return the snapshot.

        When *overlay_version* is None, returns the latest version.
        Raises KeyError if no version exists for this run + snapshot.
        """
        if overlay_version is not None:
            return self._snapshots[(compile_run_id, snapshot_id, overlay_version)]

        run_key = (compile_run_id, snapshot_id)
        latest = self._latest.get(run_key)
        if latest is None:
            raise KeyError(
                f"Snapshot '{compile_run_id}/{snapshot_id}' not found"
            )
        return self._snapshots[(compile_run_id, snapshot_id, latest)]

    def has(
        self,
        compile_run_id: str,
        snapshot_id: str,
        overlay_version: int | None = None,
    ) -> bool:
        if overlay_version is not None:
            return (compile_run_id, snapshot_id, overlay_version) in self._snapshots
        return (compile_run_id, snapshot_id) in self._latest

    def get_latest_overlay_version(
        self, compile_run_id: str, snapshot_id: str,
    ) -> int:
        run_key = (compile_run_id, snapshot_id)
        if run_key not in self._latest:
            raise KeyError(
                f"Snapshot '{compile_run_id}/{snapshot_id}' not found"
            )
        return self._latest[run_key]
