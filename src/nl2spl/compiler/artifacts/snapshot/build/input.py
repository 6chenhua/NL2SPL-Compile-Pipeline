"""SnapshotBuildInput — frozen contract for constructing a SnapshotDocument.

Carries all data the SnapshotBuilder needs, extracted from the pipeline
state by the orchestrator (S4).  The builder must not read the
``intermediate`` dict directly — all access goes through collectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SnapshotBuildInput:
    """Frozen input contract for the SnapshotBuilder.

    Assembled by the orchestrator at the end of a compile run.  Contains
    all structured artifacts needed to produce a canonical
    ``SnapshotDocument``.

    Attributes:
        compile_run_id: The pipeline run identifier.
        output_dir: Output directory for the run.
        source_spans: All ``SpanIR`` instances from the adapter.
        source_routes: ``FieldRouteIR`` from the router.
        construct_plan: ``ConstructPlan`` if one was produced.
        canonical_input: ``CanonicalCompileInput`` contract.
        worker_plan: ``WorkerPlanIR`` with worker boundaries.
        worker_flow_plan: ``WorkerFlowPlanIR`` per-worker flows.
        worker_block_plan: ``WorkerBlockPlanIR`` per-worker blocks.
        worker_step_plan: ``WorkerStepPlanIR`` per-worker steps.
        resources: ``ResourceRegistryIR``.
        worker_scoped_resources: ``WorkerScopedResourceIR``.
        symbol_table: ``SymbolTable``.
        constraints: ``ConstraintIR`` tuple.
        agent_profile: ``AgentProfileIR``.
        final_worker: ``WorkerIR`` assembled worker (post-gate).
        pre_gate_worker: ``WorkerIR`` before executable gate.
        final_spl_text: Rendered SPL text.
        compile_diagnostics: Final consolidated diagnostics tuple.
        traces: ``TraceRecord`` tuple.
        normalizer_input: Stage 9.5 input artifacts.
        normalizer_output: Stage 9.5 output artifacts.
        stage10_input: Stage 10 input artifacts.
        config: Snapshot persistence configuration.
    """

    compile_run_id: str
    output_dir: Path

    # Source / adapter
    source_spans: tuple[Any, ...] = ()
    source_routes: Any = None
    construct_plan: Any = None
    canonical_input: Any = None

    # Stage artifacts
    worker_plan: Any = None
    worker_flow_plan: Any = None
    worker_block_plan: Any = None
    worker_step_plan: Any = None
    resources: Any = None
    worker_scoped_resources: Any = None
    symbol_table: Any = None
    constraints: tuple[Any, ...] = ()
    agent_profile: Any = None

    # Assembly
    final_worker: Any = None
    pre_gate_worker: Any = None
    final_spl_text: str = ""

    # Diagnostics / provenance
    compile_diagnostics: tuple[Any, ...] = ()
    traces: tuple[Any, ...] = ()

    # Replay
    normalizer_input: Any = None
    normalizer_output: Any = None
    stage10_input: Any = None

    # Config
    config: Any = None
