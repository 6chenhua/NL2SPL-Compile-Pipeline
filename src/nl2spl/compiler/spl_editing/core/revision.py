"""Revision token and artifact snapshot for SPL Editing.

Revision identity is the triple:
    ``(compile_run_id, artifact_snapshot_id, overlay_version)``

A patch targets a specific ``(snapshot_id, overlay_version)``.  The
applier produces a new snapshot with ``overlay_version + 1``.
Staleness is detected when the base overlay version no longer matches
the latest stored version for the same snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    StaleRevisionError,
)
from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord

# ---------------------------------------------------------------------------
# Sentinel for derive() — distinguishes "not provided" from "set to None"
# ---------------------------------------------------------------------------

_UNSET: Any = object()
"""Sentinel used by ``ArtifactSnapshot.derive()``.

When a keyword argument equals ``_UNSET`` (the default), the base
snapshot's value is carried over.  Passing ``None`` explicitly means
"clear this field to None".
"""


# ---------------------------------------------------------------------------
# Revision identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RevisionToken:
    """Identifies a specific artifact revision.

    Attributes:
        compile_run_id: The NL2SPL pipeline run that produced the base.
        artifact_snapshot_id: Identifies the frozen artifact set.
        overlay_version: Monotonically increasing edit counter.
    """

    compile_run_id: str
    artifact_snapshot_id: str
    overlay_version: int

    def next_overlay(self) -> RevisionToken:
        """Return a new token with overlay_version + 1."""
        return RevisionToken(
            compile_run_id=self.compile_run_id,
            artifact_snapshot_id=self.artifact_snapshot_id,
            overlay_version=self.overlay_version + 1,
        )

    def is_stale_relative_to(self, current: RevisionToken) -> bool:
        """True when this token is behind *current* for the same run + snapshot.

        Different ``compile_run_id`` or ``artifact_snapshot_id`` always
        counts as stale — a patch from one run/snapshot must never
        silently apply to another.
        """
        if self.compile_run_id != current.compile_run_id:
            return True
        if self.artifact_snapshot_id != current.artifact_snapshot_id:
            return True
        return self.overlay_version < current.overlay_version


# ---------------------------------------------------------------------------
# ArtifactSnapshot — immutable, deterministic serializable
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactSnapshot:
    """Frozen snapshot of all stage-level artifacts for one compile run.

    Patch appliers always work on a deep copy / derived snapshot.
    The base snapshot is immutable.

    All fields use tuples (not lists) for determinism.  Optional
    artifacts are ``None`` when not available.

    Access required artifacts through ``require_*()`` methods —
    they raise ``PatchValidationError`` early if the artifact is
    missing, rather than letting patch code encounter ``None``
    mid-apply.
    """

    snapshot_id: str
    compile_run_id: str
    overlay_version: int

    # -- Source / adapter layer --
    canonical_input: Any | None = None
    spans: tuple[Any, ...] = ()
    routes: Any | None = None

    # -- Worker-scoped plans --
    worker_plan: Any | None = None
    worker_flow_plan: Any | None = None
    worker_block_plan: Any | None = None
    worker_step_plan: Any | None = None

    # -- Resources and symbols --
    resources: Any | None = None
    worker_scoped_resources: Any | None = None
    symbol_table: Any | None = None

    # -- Constraints and profile --
    constraints: tuple[Any, ...] = ()
    agent_profile: Any | None = None

    # -- Final assembly --
    final_worker: Any | None = None
    final_spl: str | None = None
    compile_diagnostics: tuple[CompileDiagnostic, ...] = ()
    traces: tuple[TraceRecord, ...] = ()
    promotion_resolution_markers: tuple[Any, ...] = ()

    # ------------------------------------------------------------------
    # require_* accessors — fail early on missing artifact
    # ------------------------------------------------------------------

    def require_worker_plan(self) -> Any:
        if self.worker_plan is None:
            raise PatchValidationError("ArtifactSnapshot requires worker_plan but it is None")
        return self.worker_plan

    def require_worker_flow_plan(self) -> Any:
        if self.worker_flow_plan is None:
            raise PatchValidationError("ArtifactSnapshot requires worker_flow_plan but it is None")
        return self.worker_flow_plan

    def require_worker_block_plan(self) -> Any:
        if self.worker_block_plan is None:
            raise PatchValidationError("ArtifactSnapshot requires worker_block_plan but it is None")
        return self.worker_block_plan

    def require_worker_step_plan(self) -> Any:
        if self.worker_step_plan is None:
            raise PatchValidationError("ArtifactSnapshot requires worker_step_plan but it is None")
        return self.worker_step_plan

    def require_resources(self) -> Any:
        if self.resources is None:
            raise PatchValidationError("ArtifactSnapshot requires resources but it is None")
        return self.resources

    def require_compile_diagnostics(self) -> tuple[CompileDiagnostic, ...]:
        return self.compile_diagnostics

    def require_final_worker(self) -> Any:
        if self.final_worker is None:
            raise PatchValidationError("ArtifactSnapshot requires final_worker but it is None")
        return self.final_worker

    # ------------------------------------------------------------------
    # Derived snapshot factory
    # ------------------------------------------------------------------

    def derive(
        self,
        token: RevisionToken,
        *,
        worker_plan: Any = _UNSET,
        worker_flow_plan: Any = _UNSET,
        worker_block_plan: Any = _UNSET,
        worker_step_plan: Any = _UNSET,
        resources: Any = _UNSET,
        worker_scoped_resources: Any = _UNSET,
        symbol_table: Any = _UNSET,
        final_worker: Any = _UNSET,
        final_spl: Any = _UNSET,
        compile_diagnostics: Any = _UNSET,
        promotion_resolution_markers: Any = _UNSET,
    ) -> ArtifactSnapshot:
        """Return a derived snapshot with updated revision identity.

        Patch appliers must construct replacement artifacts and pass
        them explicitly.  Fields left as ``_UNSET`` carry over from the
        base snapshot.  Passing ``None`` explicitly clears the field
        (useful for ``final_spl`` / ``final_worker`` which become stale
        after a stage-level artifact change).

        To mutate a field, the applier deep-copies / constructs a new
        artifact *before* calling ``derive()`` and passes the
        replacement.

        Raises ``StaleRevisionError`` if *token* does not match the
        same run + snapshot or is not a strictly higher overlay version.
        """
        if (
            token.compile_run_id != self.compile_run_id
            or token.artifact_snapshot_id != self.snapshot_id
        ):
            raise StaleRevisionError(
                f"Cannot derive snapshot from mismatched run/snapshot: "
                f"base=({self.compile_run_id}, {self.snapshot_id}), "
                f"token=({token.compile_run_id}, {token.artifact_snapshot_id})"
            )
        if token.overlay_version <= self.overlay_version:
            raise StaleRevisionError(
                f"Overlay version must increase: {self.overlay_version} -> {token.overlay_version}"
            )

        def _val(arg: Any, base: Any) -> Any:
            return base if arg is _UNSET else arg

        return ArtifactSnapshot(
            snapshot_id=token.artifact_snapshot_id,
            compile_run_id=token.compile_run_id,
            overlay_version=token.overlay_version,
            canonical_input=self.canonical_input,
            spans=self.spans,
            routes=self.routes,
            worker_plan=_val(worker_plan, self.worker_plan),
            worker_flow_plan=_val(worker_flow_plan, self.worker_flow_plan),
            worker_block_plan=_val(worker_block_plan, self.worker_block_plan),
            worker_step_plan=_val(worker_step_plan, self.worker_step_plan),
            resources=_val(resources, self.resources),
            worker_scoped_resources=_val(worker_scoped_resources, self.worker_scoped_resources),
            symbol_table=_val(symbol_table, self.symbol_table),
            constraints=self.constraints,
            agent_profile=self.agent_profile,
            final_worker=_val(final_worker, self.final_worker),
            final_spl=_val(final_spl, self.final_spl),
            compile_diagnostics=_val(compile_diagnostics, self.compile_diagnostics),
            traces=self.traces,
            promotion_resolution_markers=_val(
                promotion_resolution_markers, self.promotion_resolution_markers
            ),
        )

    @property
    def revision_token(self) -> RevisionToken:
        return RevisionToken(
            compile_run_id=self.compile_run_id,
            artifact_snapshot_id=self.snapshot_id,
            overlay_version=self.overlay_version,
        )


# ---------------------------------------------------------------------------
# Overlay event — persisted record of a single apply
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OverlayEvent:
    """Persisted record of one accepted repair patch application.

    Immutable — stored alongside the patched snapshot.
    """

    overlay_id: str
    base_compile_run_id: str
    base_artifact_snapshot_id: str
    overlay_version: int
    patch_type: str
    affordance_id: str
    patch_id: str
    accepted: bool


@dataclass(frozen=True)
class AcceptedRepairPatch:
    """A repair patch that was accepted and applied."""

    patch_id: str
    patch_type: str
    affordance_id: str
    overlay_id: str
