"""Snapshot persistence configuration.

Controls whether and how snapshot persistence occurs during a compile run.
"""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
from nl2spl.compiler.artifacts.snapshot.constants import SnapshotMode


@dataclass
class SnapshotPersistenceConfig:
    """Configuration for snapshot persistence during a compile run.

    Attributes:
        enabled: Master switch.  When ``False``, no snapshot is written
            and ``PipelineResult`` status is ``NOT_REQUESTED``.
        mode: Persistence mode — ``disabled``, ``best_effort``, or
            ``required``.  Controls failure semantics.
        filename: Snapshot JSON filename (default:
            ``"spl_editing_snapshot.json"``).
        include_traces: Include provenance traces in the snapshot.
        include_pre_gate_worker: Include the pre-gate WorkerIR.
        include_stage_debug_payloads: Include stage-level debug payloads
            (not used by SPL Editing, only for diagnostics).
        serialization_format: Always ``"json"`` in MVP.
        required_capabilities: Capabilities that must be effective for
            the snapshot to be considered valid in ``required`` mode.
    """

    enabled: bool = True
    mode: SnapshotMode = SnapshotMode.BEST_EFFORT
    filename: str = "spl_editing_snapshot.json"
    include_traces: bool = True
    include_pre_gate_worker: bool = False
    include_stage_debug_payloads: bool = False
    serialization_format: str = "json"
    required_capabilities: tuple[SnapshotCapability, ...] = ()

    @classmethod
    def disabled(cls) -> SnapshotPersistenceConfig:
        """Return a config with snapshot persistence disabled."""
        return cls(enabled=False, mode=SnapshotMode.DISABLED)

    @classmethod
    def required(cls, *capabilities: SnapshotCapability) -> SnapshotPersistenceConfig:
        """Return a config that requires specific capabilities."""
        return cls(
            enabled=True,
            mode=SnapshotMode.REQUIRED,
            required_capabilities=capabilities or (),
        )
