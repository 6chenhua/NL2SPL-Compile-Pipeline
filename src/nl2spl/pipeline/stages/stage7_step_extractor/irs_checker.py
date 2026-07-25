"""Stage 7 IRS checker -- post-hoc step-level slot satisfaction.

Runs after Stage 7 produces StepIR list / WorkerStepPlanIR and checks
each executable step against its command-type ConstructIRS.

Rules (Phase 4):
- GENERAL_COMMAND: source_span_ids non-empty ->satisfied; empty ->assumed_command_not_renderable
- REQUEST_INPUT: source_span_ids non-empty ->satisfied; empty ->type_or_contract_ambiguity
- CALL_API: integration_ref non-empty + source_span_ids non-empty ->satisfied;
  either empty ->type_or_contract_ambiguity
- INVOKE_WORKER: handoff_id non-empty ->satisfied; empty ->type_or_contract_ambiguity
- DISPLAY_MESSAGE / unknown types: skipped (no IRS check).

R6.4: Internally uses Stage7StepIRSChecker via IRSRunner +
DiagnosticProjector.  Diagnostics are now projected (deterministic
irs_{hash} IDs, populated missing_slot).
"""

from __future__ import annotations

from nl2spl.compiler.constructs import (
    ConstructSatisfactionReport,
    SPLConstructRegistry,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.factory import build_irs_runner
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

# Command types that have IRS construct specs.
_IRS_COMMAND_TYPES = {"GENERAL_COMMAND", "REQUEST_INPUT", "CALL_API", "INVOKE_WORKER"}


def _validate_step_construct_specs(
    registry: SPLConstructRegistry,
    steps: list[StepIR],
) -> None:
    """Validate that required construct specs exist in registry.

    Raises KeyError if a step's command type has an IRS spec but the
    registry does not contain it.  DISPLAY_MESSAGE is silently skipped.
    """
    for step in steps:
        if step.command_type in _IRS_COMMAND_TYPES:
            registry.get(step.command_type)


def check_steps_irs(
    steps: list[StepIR],
    registry: SPLConstructRegistry | None = None,
    worker_id: str | None = None,
) -> tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]:
    """Check *steps* against per-command-type IRS.

    Returns (reports, diagnostics).  *worker_id* is forwarded to
    ``construct_id`` and ``target_ref`` for worker-scoped callers.

    R6.4: Internally delegates to Stage7StepIRSChecker via
    IRSRunner + DiagnosticProjector.
    """
    reg = registry or SPLConstructRegistry.default()
    _validate_step_construct_specs(reg, steps)

    runner = build_irs_runner(
        enable_step=True,
        construct_registry=reg,
    )

    if worker_id is not None:
        # Worker-scoped path: wrap in a single-entry WorkerStepPlanIR
        worker_step_plan = WorkerStepPlanIR(
            main_worker_id=worker_id,
            worker_steps={worker_id: steps},
        )
        context = IRSCheckContext(
            stage_name="stage7",
            worker_steps=worker_step_plan,
        )
    else:
        # Legacy path: pass steps directly
        context = IRSCheckContext(
            stage_name="stage7",
            steps=tuple(steps),
        )

    result = runner.run_stage("stage7", context)
    return result.reports, result.diagnostics


def check_worker_step_plan_irs(
    worker_step_plan: WorkerStepPlanIR,
    registry: SPLConstructRegistry | None = None,
) -> tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]:
    """Check every worker's steps in a WorkerStepPlanIR.

    Returns aggregated (reports, diagnostics) across all workers.

    R6.4: Internally delegates to Stage7StepIRSChecker via
    IRSRunner + DiagnosticProjector.
    """
    reg = registry or SPLConstructRegistry.default()
    for steps in worker_step_plan.worker_steps.values():
        _validate_step_construct_specs(reg, steps)

    runner = build_irs_runner(
        enable_step=True,
        construct_registry=reg,
    )

    context = IRSCheckContext(
        stage_name="stage7",
        worker_steps=worker_step_plan,
    )

    result = runner.run_stage("stage7", context)
    return result.reports, result.diagnostics
