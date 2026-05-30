"""D10: Route-driven delegation diagnostic analyzer.

Emits ``type_or_contract_ambiguity`` diagnostics from route annotations
with ``semantic_role="delegation_intent"`` when no valid handoff contract
covers the delegation span.  Bridge ``delegation_intents()`` remains as a
compatibility fallback for hard-fact-only inputs.
"""

from __future__ import annotations

from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerHandoffIR, WorkerPlanIR
from nl2spl.pipeline.fact_bridges import _is_valid_handoff


def diagnose_delegation_intents_from_routes(
    routes: FieldRouteIR,
    spans: list[SpanIR],
    worker_plan: WorkerPlanIR | None = None,
    declared_apis: set[str] | None = None,
) -> list[CompileDiagnostic]:
    """Emit route-driven delegation diagnostics from annotations.

    For each ``delegation_intent`` annotation, checks whether a valid
    handoff contract exists in *worker_plan*.  When no valid handoff
    covers the delegation span, a ``type_or_contract_ambiguity``
    diagnostic is emitted with span provenance.
    """
    diags: list[CompileDiagnostic] = []
    anns = routes.get_annotations_by_role("delegation_intent")
    if not anns:
        return diags

    apis = declared_apis or set()
    span_by_id = {s.span_id: s for s in spans}
    handoffs = worker_plan.handoffs if worker_plan else []

    for ann in anns:
        span = span_by_id.get(ann.span_id)
        if span is None:
            continue

        source_span_ids = [ann.span_id]
        section_id = ann.source_section_id or span.source_section_id
        packet_id = ann.source_packet_id or span.source_packet_id
        hint_evidence = (
            f" hints={','.join(ann.source_hint_ids)}"
            if ann.source_hint_ids else ""
        )

        # Check if any valid handoff covers this delegation span
        covered = _handoff_covers_span(
            ann.span_id, handoffs, worker_plan, apis,
        )
        if covered:
            continue

        diags.append(
            CompileDiagnostic(
                diagnostic_id=f"diag_d10_{len(diags):04d}",
                kind="type_or_contract_ambiguity",
                severity="warning",
                message=(
                    f"Delegation intent '{span.text[:80]}' lacks a valid "
                    f"worker/API handoff contract.  No INVOKE_WORKER or "
                    f"CALL_API will be generated from this span."
                    f"  [{section_id or 'no-section'}"
                    f"/{packet_id or 'no-packet'}]"
                ),
                suggested_resolution=(
                    f"Provide a valid worker/API handoff contract with "
                    f"input/output/API bindings covering span "
                    f"'{ann.span_id}'.{hint_evidence}"
                ) if hint_evidence else None,
                target_ref=f"delegation_intent:{ann.span_id}",
                source_span_ids=source_span_ids,
                blocks_completion=True,
            )
        )

    return diags


def _handoff_covers_span(
    span_id: str,
    handoffs: list[WorkerHandoffIR],
    worker_plan: WorkerPlanIR | None,
    declared_apis: set[str],
) -> bool:
    """Check whether any valid handoff covers *span_id*."""
    if not handoffs:
        return False
    known_child_ids: set[str] = set()
    if worker_plan:
        known_child_ids = {
            w.worker_id for w in worker_plan.workers
            if w.worker_id != worker_plan.main_worker_id
        }
    for h in handoffs:
        if not _is_valid_handoff(h, known_child_ids, declared_apis):
            continue
        hint_ids: list[str] = []
        if h.invoke_location_hint.after_span_id:
            hint_ids.append(h.invoke_location_hint.after_span_id)
        if h.invoke_location_hint.before_span_id:
            hint_ids.append(h.invoke_location_hint.before_span_id)
        hint_ids.extend(h.failure_policy.source_span_ids)
        if span_id in hint_ids:
            return True
    return False
