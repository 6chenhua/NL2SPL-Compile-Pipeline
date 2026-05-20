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
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import (
    ConstructSatisfactionReport,
    SlotSatisfaction,
    SPLConstructRegistry, ConstructCompleteness,
)
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR

# Guard symbol for no-spans condition ambiguity.
_SLOT_SOURCE_REQUIRED_MESSAGE = (
    "Exception flow has condition text but no source-span evidence. "
    "The condition may be an LLM inference rather than a source-backed fact."
)


def check_exception_flows_irs(
    flow_structure: FlowStructureIR,
    registry: SPLConstructRegistry | None = None,
    worker_id: str | None = None,
) -> tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]:
    """Check exception flows in *flow_structure* against EXCEPTION_FLOW IRS.

    Returns (reports, diagnostics).  *worker_id* is forwarded to
    ``construct_id`` and ``target_ref`` for worker-scoped callers.
    """
    if registry is None:
        registry = SPLConstructRegistry.default()

    irs = registry.get("EXCEPTION_FLOW")
    reports: list[ConstructSatisfactionReport] = []
    diagnostics: list[CompileDiagnostic] = []

    for idx, exc_flow in enumerate(flow_structure.exception_flows):
        construct_id = _make_construct_id(exc_flow.flow_id, worker_id)
        diag_counter = 0

        # -- condition slot ------------------------------------------------
        condition_source_backed = bool(
            exc_flow.condition_text and exc_flow.spans
        )

        if condition_source_backed:
            condition_sat = SlotSatisfaction(
                slot_name="condition",
                status="satisfied",
                source_span_ids=list(exc_flow.spans),
                relation="direct",
            )
        else:
            condition_sat = SlotSatisfaction(
                slot_name="condition",
                status="assumed",
                source_span_ids=list(exc_flow.spans),
                relation="assumed",
                diagnostic_kind="type_or_contract_ambiguity",
                explanation=_SLOT_SOURCE_REQUIRED_MESSAGE,
            )
            diagnostics.append(
                CompileDiagnostic(
                    diagnostic_id=_make_diagnostic_id(idx, worker_id),
                    kind="type_or_contract_ambiguity",
                    severity="warning",
                    message=(
                        f"Exception flow '{exc_flow.flow_id}' has condition "
                        f"text ('{exc_flow.condition_text[:80]}') but no "
                        f"source-span evidence."
                    ),
                    target_ref=_make_target_ref(exc_flow.flow_id, worker_id),
                    source_span_ids=list(exc_flow.spans),
                    suggested_resolution=(
                        "Ensure the exception condition is backed by a "
                        "concrete source span, or remove the exception "
                        "flow if the policy is too vague to materialise."
                    ),
                    blocks_rendering=True,
                    blocks_completion=True,
                )
            )
            diag_counter += 1

        # -- handler_action ------------------------------------------------
        handler_sat = SlotSatisfaction(
            slot_name="handler_action",
            status="not_applicable",
            explanation=(
                "handler_action is a cross-stage slot — Stage 7 / Stage 9.5 "
                "are authoritative for handler presence."
            ),
        )

        # -- trigger_step --------------------------------------------------
        trigger_sat = SlotSatisfaction(
            slot_name="trigger_step",
            status="not_applicable",
            explanation=(
                "trigger_step is post-MVP and not assessed at Stage 4."
            ),
        )

        slots = [condition_sat, handler_sat, trigger_sat]

        completeness = "partial"  # handler_action unknown at Stage 4
        renderable = condition_source_backed  # only renderable if source-backed

        reports.append(
            ConstructSatisfactionReport(
                construct_id=construct_id,
                construct_type="EXCEPTION_FLOW",
                slots=slots,
                completeness=completeness,
                renderable=renderable,
                diagnostics=list(diagnostics[-diag_counter:])
                if diag_counter
                else [],
            )
        )

    return reports, diagnostics


def check_worker_flow_plan_exception_flows_irs(
    worker_flow_plan: WorkerFlowPlanIR,
    registry: SPLConstructRegistry | None = None,
) -> tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]:
    """Check every worker's exception flows in a WorkerFlowPlanIR.

    Returns aggregated (reports, diagnostics) across all workers.
    """
    if registry is None:
        registry = SPLConstructRegistry.default()

    all_reports: list[ConstructSatisfactionReport] = []
    all_diagnostics: list[CompileDiagnostic] = []

    for w_id, flow in worker_flow_plan.worker_flows.items():
        reports, diagnostics = check_exception_flows_irs(
            flow,
            registry=registry,
            worker_id=w_id,
        )
        all_reports.extend(reports)
        all_diagnostics.extend(diagnostics)

    return all_reports, all_diagnostics


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_construct_id(flow_id: str, worker_id: str | None) -> str:
    """Build a scoped construct identifier."""
    if worker_id:
        return f"worker:{worker_id}.exception_flow:{flow_id}"
    return f"exception_flow:{flow_id}"


def _make_target_ref(flow_id: str, worker_id: str | None) -> str:
    """Build a target_ref matching the construct_id convention."""
    if worker_id:
        return f"worker:{worker_id}.exception_flow:{flow_id}"
    return f"exception_flow:{flow_id}"


def _make_diagnostic_id(index: int, worker_id: str | None) -> str:
    """Build a unique diagnostic_id scoped to the worker (or legacy path)."""
    scope = worker_id or "legacy"
    return f"diag_stage4_{scope}_exc_{index:04d}"
