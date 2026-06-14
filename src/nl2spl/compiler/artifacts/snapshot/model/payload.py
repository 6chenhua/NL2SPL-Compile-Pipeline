"""Snapshot payload — typed container for all six payload sub-sections.

Each sub-section is a frozen dataclass.  Fields use ``Any`` for IR objects
(serializers arrive in S1), but the structural contract is fully typed:
field names, shapes, and ownership rules are frozen here.

.. important::

    ``stage_artifacts`` is the canonical editable owner for all stage-level
    IRs.  ``replay_artifacts`` entries MUST use ``ArtifactRef`` or
    ``DerivedArtifactRef`` to declare their relationship to stage artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import (
    ArtifactRef,
    DerivedArtifactRef,
)
from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
    SnapshotEditingHistory,
    empty_editing_history,
)

# ===================================================================
# Source layer
# ===================================================================


@dataclass(frozen=True)
class SourceLayer:
    """Source-side context carried into the snapshot.

    Attributes:
        canonical_input: The ``CanonicalCompileInput`` contract.
        spans: All ``SpanIR`` instances from the adapter.
        routes: All ``FieldRouteIR`` instances.
        construct_plan: The ``ConstructPlan`` if one was produced.
    """

    canonical_input: Any | None = None
    spans: tuple[Any, ...] = ()
    routes: Any | None = None
    construct_plan: Any | None = None


# ===================================================================
# Stage artifacts layer — canonical editable owner
# ===================================================================


@dataclass(frozen=True)
class StageArtifactsLayer:
    """Stage-level IRs that patch appliers may modify.

    Every field here is owned by this layer.  ``replay_artifacts`` that
    need these objects MUST use ``ArtifactRef`` or ``DerivedArtifactRef``
    rather than storing independent copies.

    Attributes:
        worker_plan: ``WorkerPlanIR``.
        worker_flow_plan: ``WorkerFlowPlanIR``.
        worker_block_plan: ``WorkerBlockPlanIR``.
        worker_step_plan: ``WorkerStepPlanIR``.
        resources: ``ResourceRegistryIR``.
        worker_scoped_resources: ``WorkerScopedResourceIR``.
        symbol_table: ``SymbolTable``.
        constraints: ``ConstraintIR`` tuple.
        agent_profile: ``AgentProfileIR``.
    """

    worker_plan: Any | None = None
    worker_flow_plan: Any | None = None
    worker_block_plan: Any | None = None
    worker_step_plan: Any | None = None
    resources: Any | None = None
    worker_scoped_resources: Any | None = None
    symbol_table: Any | None = None
    constraints: tuple[Any, ...] = ()
    agent_profile: Any | None = None


# ===================================================================
# Replay artifacts layer
# ===================================================================


@dataclass(frozen=True)
class ReplayArtifactsLayer:
    """Artifacts needed for Lane A / Lane B replay.

    Each field is either:
    - An inline artifact (the actual object stored directly),
    - An ``ArtifactRef`` pointing to a ``stage_artifacts`` entry, or
    - A ``DerivedArtifactRef`` declaring a normalized/copied artifact.

    Attributes:
        normalizer_input: Stage 9.5 input bundle (Lane B).
        normalizer_output: Stage 9.5 output bundle (Lane B equivalence check).
        stage10_input: Stage 10 input bundle (Lane A).
        assembled_worker_pre_gate: WorkerIR before the executable gate.
        gated_worker: WorkerIR after the executable gate (user-facing surface).
        final_spl: Rendered SPL text.
    """

    normalizer_input: Any | ArtifactRef | DerivedArtifactRef | None = None
    normalizer_output: Any | ArtifactRef | DerivedArtifactRef | None = None
    stage10_input: Any | ArtifactRef | DerivedArtifactRef | None = None
    assembled_worker_pre_gate: Any | DerivedArtifactRef | None = None
    gated_worker: Any | DerivedArtifactRef | None = None
    final_spl: str | None = None


# ===================================================================
# Diagnostics layer
# ===================================================================


@dataclass(frozen=True)
class DiagnosticsLayer:
    """Final consolidated diagnostics and stage-level diagnostic bundles.

    Attributes:
        compile_diagnostics: Final consolidated ``CompileDiagnostic`` tuple.
            This is the authority for issue extraction.
        post_normalize_diagnostics: Post-IRS diagnostics.
        gate_diagnostics: Executable gate diagnostics.
        render_diagnostics: Renderer diagnostics.
    """

    compile_diagnostics: tuple[Any, ...] = ()
    post_normalize_diagnostics: tuple[Any, ...] = ()
    gate_diagnostics: tuple[Any, ...] = ()
    render_diagnostics: tuple[Any, ...] = ()


# ===================================================================
# Provenance layer
# ===================================================================


@dataclass(frozen=True)
class ProvenanceLayer:
    """Provenance data for source-span lookup and repair context.

    Attributes:
        traces: ``TraceRecord`` tuple for source-to-SPL mapping.
        assumptions: ``CompileAssumption`` tuple.
    """

    traces: tuple[Any, ...] = ()
    assumptions: tuple[Any, ...] = ()


# ===================================================================
# Editing layer
# ===================================================================


@dataclass(frozen=True)
class EditingLayer:
    """Editing history for the snapshot.

    Base snapshots have an empty history.  Overlays record the full
    event log.
    """

    history: SnapshotEditingHistory = field(default_factory=empty_editing_history)


# ===================================================================
# Full payload
# ===================================================================


@dataclass(frozen=True)
class SnapshotPayload:
    """Complete snapshot payload — all six sub-sections.

    Attributes:
        source: Source-side context.
        stage_artifacts: Editable stage-level IRs.
        replay_artifacts: Replay lane artifacts.
        diagnostics: Compiler diagnostics.
        provenance: Traces and assumptions.
        editing: Editing history.
    """

    source: SourceLayer = field(default_factory=SourceLayer)
    stage_artifacts: StageArtifactsLayer = field(default_factory=StageArtifactsLayer)
    replay_artifacts: ReplayArtifactsLayer = field(default_factory=ReplayArtifactsLayer)
    diagnostics: DiagnosticsLayer = field(default_factory=DiagnosticsLayer)
    provenance: ProvenanceLayer = field(default_factory=ProvenanceLayer)
    editing: EditingLayer = field(default_factory=EditingLayer)
