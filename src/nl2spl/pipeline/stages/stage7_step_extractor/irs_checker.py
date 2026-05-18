"""Stage 7 IRS checker -- post-hoc step-level slot satisfaction.

Runs after Stage 7 produces StepIR list / WorkerStepPlanIR and checks
each executable step against its command-type ConstructIRS.

Rules (Phase 4):
- GENERAL_COMMAND: source_span_ids non-empty ->satisfied; empty ->assumed_command_not_renderable
- REQUEST_INPUT: source_span_ids non-empty ->satisfied; empty ->type_or_contract_ambiguity
- CALL_API: integration_ref non-empty + source_span_ids non-empty ->satisfied; either empty ->type_or_contract_ambiguity
- INVOKE_WORKER: handoff_id non-empty ->satisfied; empty ->type_or_contract_ambiguity
- DISPLAY_MESSAGE / unknown types: skipped (no IRS check).
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import (
    ConstructSatisfactionReport,
    SlotSatisfaction,
    SPLConstructRegistry,
)
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

# Command types that map to IRS constructs.
_COMMAND_TYPE_TO_CONSTRUCT: dict[str, str] = {
    "GENERAL_COMMAND": "GENERAL_COMMAND",
    "REQUEST_INPUT": "REQUEST_INPUT",
    "CALL_API": "CALL_API",
    "INVOKE_WORKER": "INVOKE_WORKER",
}


def check_steps_irs(
    steps: list[StepIR],
    registry: SPLConstructRegistry | None = None,
    worker_id: str | None = None,
) -> tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]:
    """Check *steps* against per-command-type IRS.

    Returns (reports, diagnostics).  *worker_id* is forwarded to
    ``construct_id`` and ``target_ref`` for worker-scoped callers.
    """
    if registry is None:
        registry = SPLConstructRegistry.default()

    reports: list[ConstructSatisfactionReport] = []
    diagnostics: list[CompileDiagnostic] = []

    for step in steps:
        construct_type = _COMMAND_TYPE_TO_CONSTRUCT.get(step.command_type)
        if construct_type is None:
            continue  # DISPLAY_MESSAGE etc. --no IRS check

        irs = registry.get(construct_type)
        construct_id = _make_step_construct_id(step.step_id, worker_id)

        if step.command_type == "GENERAL_COMMAND":
            report, diags = _check_general_command(
                step, irs, construct_id, worker_id
            )
        elif step.command_type == "REQUEST_INPUT":
            report, diags = _check_request_input(
                step, irs, construct_id, worker_id
            )
        elif step.command_type == "CALL_API":
            report, diags = _check_call_api(
                step, irs, construct_id, worker_id
            )
        elif step.command_type == "INVOKE_WORKER":
            report, diags = _check_invoke_worker(
                step, irs, construct_id, worker_id
            )
        else:
            continue

        reports.append(report)
        diagnostics.extend(diags)

    return reports, diagnostics


def check_worker_step_plan_irs(
    worker_step_plan: WorkerStepPlanIR,
    registry: SPLConstructRegistry | None = None,
) -> tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]:
    """Check every worker's steps in a WorkerStepPlanIR.

    Returns aggregated (reports, diagnostics) across all workers.
    """
    if registry is None:
        registry = SPLConstructRegistry.default()

    all_reports: list[ConstructSatisfactionReport] = []
    all_diagnostics: list[CompileDiagnostic] = []

    for w_id, steps in worker_step_plan.worker_steps.items():
        reports, diagnostics = check_steps_irs(
            steps, registry=registry, worker_id=w_id
        )
        all_reports.extend(reports)
        all_diagnostics.extend(diagnostics)

    return all_reports, all_diagnostics


# ------------------------------------------------------------------
# Per-command-type checkers
# ------------------------------------------------------------------


def _check_general_command(
    step: StepIR,
    irs: ConstructIRS,
    construct_id: str,
    worker_id: str | None,
) -> tuple[ConstructSatisfactionReport, list[CompileDiagnostic]]:
    source_backed = bool(step.source_span_ids)
    slots: list[SlotSatisfaction] = []

    # action_text --always satisfied from step.text
    slots.append(SlotSatisfaction(
        slot_name="action_text", status="satisfied",
        source_span_ids=list(step.source_span_ids),
        relation="direct" if source_backed else None,
    ))

    diags: list[CompileDiagnostic] = []
    if source_backed:
        slots.append(SlotSatisfaction(
            slot_name="source_evidence", status="satisfied",
            source_span_ids=list(step.source_span_ids), relation="direct",
        ))
    else:
        slots.append(SlotSatisfaction(
            slot_name="source_evidence", status="missing",
            diagnostic_kind="assumed_command_not_renderable",
            explanation="Step has no source-span evidence.",
        ))
        diags.append(_make_diag(
            step, "assumed_command_not_renderable", worker_id,
            suffix="source_evidence",
            message=(
                f"GENERAL_COMMAND step '{step.step_id}' "
                f"('{step.text[:80]}') has no source-span evidence "
                f"and is not compiler scaffolding."
            ),
            blocks_rendering=True,
        ))

    # result_variable --optional
    result_status = "satisfied" if step.outputs else "not_applicable"
    slots.append(SlotSatisfaction(slot_name="result_variable", status=result_status))

    completeness = "complete" if source_backed else "partial"
    return (
        ConstructSatisfactionReport(
            construct_id=construct_id,
            construct_type="GENERAL_COMMAND",
            slots=slots,
            completeness=completeness,
            renderable=source_backed,
            diagnostics=list(diags),
        ),
        diags,
    )


def _check_request_input(
    step: StepIR,
    irs: ConstructIRS,
    construct_id: str,
    worker_id: str | None,
) -> tuple[ConstructSatisfactionReport, list[CompileDiagnostic]]:
    source_backed = bool(step.source_span_ids)
    slots: list[SlotSatisfaction] = []

    # prompt_text --always satisfied from step.text
    slots.append(SlotSatisfaction(
        slot_name="prompt_text", status="satisfied",
        source_span_ids=list(step.source_span_ids),
        relation="direct" if source_backed else None,
    ))

    diags: list[CompileDiagnostic] = []
    if source_backed:
        slots.append(SlotSatisfaction(
            slot_name="value_target", status="satisfied",
            source_span_ids=list(step.source_span_ids), relation="direct",
        ))
    else:
        slots.append(SlotSatisfaction(
            slot_name="value_target", status="missing",
            diagnostic_kind="type_or_contract_ambiguity",
            explanation=(
                "REQUEST_INPUT step has no source-span evidence --"
                "missing explicit ask/request/prompt signal."
            ),
        ))
        diags.append(_make_diag(
            step, "type_or_contract_ambiguity", worker_id,
            suffix="value_target",
            message=(
                f"REQUEST_INPUT step '{step.step_id}' "
                f"('{step.text[:80]}') has no source-span evidence. "
                f"REQUEST_INPUT requires an explicit ask/request/prompt "
                f"signal in the source."
            ),
            blocks_rendering=True,
        ))

    completeness = "complete" if source_backed else "partial"
    return (
        ConstructSatisfactionReport(
            construct_id=construct_id,
            construct_type="REQUEST_INPUT",
            slots=slots,
            completeness=completeness,
            renderable=source_backed,
            diagnostics=list(diags),
        ),
        diags,
    )


def _check_call_api(
    step: StepIR,
    irs: ConstructIRS,
    construct_id: str,
    worker_id: str | None,
) -> tuple[ConstructSatisfactionReport, list[CompileDiagnostic]]:
    has_api = bool(step.integration_ref)
    has_call_action = bool(step.source_span_ids)
    slots: list[SlotSatisfaction] = []
    diags: list[CompileDiagnostic] = []

    # api_name
    if has_api:
        slots.append(SlotSatisfaction(
            slot_name="api_name", status="satisfied",
            source_span_ids=list(step.source_span_ids),
            relation="direct" if has_call_action else None,
        ))
    else:
        slots.append(SlotSatisfaction(
            slot_name="api_name", status="missing",
            diagnostic_kind="type_or_contract_ambiguity",
            explanation="CALL_API has no integration_ref (API name).",
        ))
        diags.append(_make_diag(
            step, "type_or_contract_ambiguity", worker_id,
            suffix="api_name",
            message=(
                f"CALL_API step '{step.step_id}' "
                f"('{step.text[:80]}') has no integration_ref."
            ),
            blocks_rendering=True,
        ))

    # call_action
    if has_call_action:
        slots.append(SlotSatisfaction(
            slot_name="call_action", status="satisfied",
            source_span_ids=list(step.source_span_ids), relation="direct",
        ))
    else:
        slots.append(SlotSatisfaction(
            slot_name="call_action", status="missing",
            diagnostic_kind="type_or_contract_ambiguity",
            explanation=(
                "CALL_API has no source-span evidence for "
                "executable call action."
            ),
        ))
        diags.append(_make_diag(
            step, "type_or_contract_ambiguity", worker_id,
            suffix="call_action",
            message=(
                f"CALL_API step '{step.step_id}' "
                f"('{step.text[:80]}') has no source-span evidence "
                f"for the executable call action."
            ),
            blocks_rendering=True,
        ))

    # integration_evidence --satisfied if api_name present
    slots.append(SlotSatisfaction(
        slot_name="integration_evidence",
        status="satisfied" if has_api else "missing",
    ))

    # response_binding --optional
    slots.append(SlotSatisfaction(
        slot_name="response_binding",
        status="satisfied" if step.outputs else "not_applicable",
    ))

    all_ok = has_api and has_call_action
    completeness = "complete" if all_ok else "partial"
    return (
        ConstructSatisfactionReport(
            construct_id=construct_id,
            construct_type="CALL_API",
            slots=slots,
            completeness=completeness,
            renderable=all_ok,
            diagnostics=list(diags),
        ),
        diags,
    )


def _check_invoke_worker(
    step: StepIR,
    irs: ConstructIRS,
    construct_id: str,
    worker_id: str | None,
) -> tuple[ConstructSatisfactionReport, list[CompileDiagnostic]]:
    has_handoff = bool(step.handoff_id)
    has_target = bool(step.integration_ref)
    slots: list[SlotSatisfaction] = []
    diags: list[CompileDiagnostic] = []

    # target_worker
    if has_target:
        slots.append(SlotSatisfaction(
            slot_name="target_worker", status="satisfied",
            source_span_ids=list(step.source_span_ids),
        ))
    else:
        slots.append(SlotSatisfaction(
            slot_name="target_worker", status="missing",
            diagnostic_kind="type_or_contract_ambiguity",
            explanation="INVOKE_WORKER has no integration_ref (target worker).",
        ))
        diags.append(_make_diag(
            step, "type_or_contract_ambiguity", worker_id,
            suffix="target_worker",
            message=(
                f"INVOKE_WORKER step '{step.step_id}' "
                f"('{step.text[:80]}') has no target worker "
                f"(integration_ref)."
            ),
            blocks_rendering=True,
        ))

    # handoff_id
    if has_handoff:
        slots.append(SlotSatisfaction(
            slot_name="handoff_id", status="satisfied",
        ))
    else:
        slots.append(SlotSatisfaction(
            slot_name="handoff_id", status="missing",
            diagnostic_kind="type_or_contract_ambiguity",
            explanation="INVOKE_WORKER has no handoff_id.",
        ))
        diags.append(_make_diag(
            step, "type_or_contract_ambiguity", worker_id,
            suffix="handoff_id",
            message=(
                f"INVOKE_WORKER step '{step.step_id}' "
                f"('{step.text[:80]}') has no handoff_id -- "
                f"not linked to an accepted handoff."
            ),
            blocks_rendering=True,
        ))

    # input_bindings / output_bindings --basic check
    slots.append(SlotSatisfaction(
        slot_name="input_bindings",
        status="satisfied" if step.inputs else "not_applicable",
    ))
    slots.append(SlotSatisfaction(
        slot_name="output_bindings",
        status="satisfied" if step.outputs else "not_applicable",
    ))

    all_ok = has_handoff and has_target
    completeness = "complete" if all_ok else "partial"
    return (
        ConstructSatisfactionReport(
            construct_id=construct_id,
            construct_type="INVOKE_WORKER",
            slots=slots,
            completeness=completeness,
            renderable=all_ok,
            diagnostics=list(diags),
        ),
        diags,
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

from nl2spl.compiler.construct_registry import ConstructIRS  # noqa: E402


def _make_step_construct_id(step_id: str, worker_id: str | None) -> str:
    if worker_id:
        return f"worker:{worker_id}.step:{step_id}"
    return f"step:{step_id}"


def _make_step_target_ref(step_id: str, worker_id: str | None) -> str:
    if worker_id:
        return f"worker:{worker_id}.step:{step_id}"
    return f"step:{step_id}"


def _make_diag(
    step: StepIR,
    kind: str,
    worker_id: str | None,
    *,
    suffix: str = "",
    message: str,
    blocks_rendering: bool = True,
) -> CompileDiagnostic:
    scope = worker_id or "legacy"
    sid = f"diag_stage7_{scope}_{step.step_id}"
    if suffix:
        sid = f"{sid}_{suffix}"
    return CompileDiagnostic(
        diagnostic_id=sid,
        kind=kind,
        severity="warning",
        message=message,
        target_ref=_make_step_target_ref(step.step_id, worker_id),
        source_span_ids=list(step.source_span_ids),
        blocks_rendering=blocks_rendering,
        blocks_completion=True,
    )
