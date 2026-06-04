"""Stage 4 IRS checker — post-hoc EXCEPTION_FLOW slot satisfaction.

Runs after Stage 4 produces FlowStructureIR / WorkerFlowPlanIR and checks
every exception flow against the EXCEPTION_FLOW ConstructIRS from the
default SPLConstructRegistry.

Rules (Phase 3):
- condition_text non-empty + spans non-empty → condition satisfied,
  construct partial (handler_action not yet known at Stage 4).
- condition_text non-empty + spans empty → condition assumed,
  type_or_contract_ambiguity.
- Does NOT check handler_action (cross-stage slot — Stage 9.5 authority).
- Does NOT emit missing_handler.

R6.4: Internally uses Stage4ExceptionFlowIRSChecker via IRSRunner +
DiagnosticProjector.  Diagnostics are now projected (deterministic
irs_{hash} IDs, populated missing_slot).
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import (
    ConstructSatisfactionReport,
    SPLConstructRegistry,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.factory import build_irs_runner
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR


def check_exception_flows_irs(
    flow_structure: FlowStructureIR,
    registry: SPLConstructRegistry | None = None,
    worker_id: str | None = None,
) -> tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]:
    """Check exception flows in *flow_structure* against EXCEPTION_FLOW IRS.

    Returns (reports, diagnostics).  *worker_id* is forwarded to
    ``construct_id`` and ``target_ref`` for worker-scoped callers.

    R6.4: Internally delegates to Stage4ExceptionFlowIRSChecker via
    IRSRunner + DiagnosticProjector.
    """
    reg = registry or SPLConstructRegistry.default()
    # Validate required construct spec exists (matches old registry.get() behavior)
    reg.get("EXCEPTION_FLOW")

    runner = build_irs_runner(
        enable_exception_flow=True,
        construct_registry=reg,
    )

    if worker_id is not None:
        # Worker-scoped path: wrap in a single-entry WorkerFlowPlanIR
        worker_flow_plan = WorkerFlowPlanIR(
            worker_flows={worker_id: flow_structure},
        )
        context = IRSCheckContext(
            stage_name="stage4",
            worker_flows=worker_flow_plan,
        )
    else:
        # Legacy path: pass flow directly
        context = IRSCheckContext(
            stage_name="stage4",
            flow=flow_structure,
        )

    result = runner.run_stage("stage4", context)
    return result.reports, result.diagnostics


def check_worker_flow_plan_exception_flows_irs(
    worker_flow_plan: WorkerFlowPlanIR,
    registry: SPLConstructRegistry | None = None,
) -> tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]:
    """Check every worker's exception flows in a WorkerFlowPlanIR.

    Returns aggregated (reports, diagnostics) across all workers.

    R6.4: Internally delegates to Stage4ExceptionFlowIRSChecker via
    IRSRunner + DiagnosticProjector.
    """
    reg = registry or SPLConstructRegistry.default()
    reg.get("EXCEPTION_FLOW")

    runner = build_irs_runner(
        enable_exception_flow=True,
        construct_registry=reg,
    )

    context = IRSCheckContext(
        stage_name="stage4",
        worker_flows=worker_flow_plan,
    )

    result = runner.run_stage("stage4", context)
    return result.reports, result.diagnostics
