"""Deterministic bridges from adapter hard facts to partial IR elements.

These bridges convert evidence-bound canonical facts into compiler IR
skeletons without inventing executable behavior.  The compiler's existing
diagnostic, gate, and provenance stages then produce missing_handler,
partial status, and section/packet provenance automatically.
"""

from __future__ import annotations

import re

from nl2spl.canonical import DelegationIntentFact, FailureModeFact
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerHandoffIR, WorkerPlanIR


def _normalize_condition(text: str) -> str:
    """Normalize condition text for comparison: lowercase, strip punctuation."""
    return re.sub(r"[^\w\s]", "", text.strip().lower())


def _resolve_fact_span_ids(
    fact: FailureModeFact,
    span_ids_by_section: dict[str, list[str]],
) -> list[str]:
    """Resolve span IDs for a failure fact from its evidence."""
    ids: list[str] = []
    for ev in fact.evidence:
        if ev.source_span_ids:
            ids.extend(ev.source_span_ids)
        elif ev.source_section_id:
            ids.extend(span_ids_by_section.get(ev.source_section_id, []))
    if not ids:
        ids = span_ids_by_section.get(fact.source_section_id, [])
    return ids


def bridge_failure_modes(
    failure_modes: list[FailureModeFact],
    spans: list[SpanIR],
    existing_flow: FlowStructureIR,
) -> FlowStructureIR:
    """Create partial ExceptionFlow skeletons from FailureModeFact objects.

    For each failure fact, if no existing ExceptionFlow already has a
    matching normalized condition text, create a new skeleton.  No handler
    blocks or steps are created -- the compiler's missing_handler
    diagnostic surfaces the gap.

    Deduplication is by normalized condition text only.  Two facts whose
    condition text normalizes to the same string are treated as duplicates
    and only the first is kept.  Multiple failure modes from the same
    section naturally share span IDs and are NOT deduplicated by span
    overlap.

    Args:
        failure_modes: FailureModeFact objects from the adapter.
        spans: All SpanIR objects from Stage 1.
        existing_flow: FlowStructureIR from Stage 4 (may already have
            exception flows from LLM output).

    Returns:
        A new FlowStructureIR (input is NOT mutated).
    """
    if not failure_modes:
        return existing_flow

    # Build section -> span_ids index
    span_ids_by_section: dict[str, list[str]] = {}
    for s in spans:
        if s.source_section_id:
            span_ids_by_section.setdefault(s.source_section_id, []).append(s.span_id)

    # Collect existing condition text for dedup
    existing_conditions: set[str] = set()
    for exc in existing_flow.exception_flows:
        existing_conditions.add(_normalize_condition(exc.condition_text))

    # Build new exception flows
    new_exc_flows: list[ExceptionFlow] = []
    flow_counter = len(existing_flow.exception_flows)

    for fact in failure_modes:
        normalized_condition = _normalize_condition(fact.text)

        # Dedup by normalized condition text only
        if normalized_condition in existing_conditions:
            continue

        existing_conditions.add(normalized_condition)
        ev_span_ids = _resolve_fact_span_ids(fact, span_ids_by_section)

        flow_counter += 1
        new_exc_flows.append(
            ExceptionFlow(
                flow_id=f"exc_adapter_{flow_counter - 1:02d}",
                condition_text=fact.text,
                spans=ev_span_ids,
            )
        )

    if not new_exc_flows:
        return existing_flow

    return FlowStructureIR(
        main_flow_spans=list(existing_flow.main_flow_spans),
        alternative_flows=list(existing_flow.alternative_flows),
        exception_flows=existing_flow.exception_flows + new_exc_flows,
        delegation_candidates=list(existing_flow.delegation_candidates),
    )


def bridge_failure_modes_worker_scoped(
    failure_modes: list[FailureModeFact],
    spans: list[SpanIR],
    worker_flow_plan: WorkerFlowPlanIR,
    worker_plan: WorkerPlanIR,
) -> WorkerFlowPlanIR:
    """Worker-aware variant of :func:`bridge_failure_modes`.

    Appends source-backed ``ExceptionFlow`` skeletons to the **main
    worker's** ``FlowStructureIR`` inside the ``WorkerFlowPlanIR``.
    Deduplication and span resolution follow the same rules as the
    legacy bridge -- no handler blocks or steps are created.

    Args:
        failure_modes: ``FailureModeFact`` objects from the adapter.
        spans: All ``SpanIR`` objects from Stage 1.
        worker_flow_plan: ``WorkerFlowPlanIR`` from worker-aware Stage 4.
        worker_plan: ``WorkerPlanIR`` from Stage 3.5 (identifies main worker).

    Returns:
        A new ``WorkerFlowPlanIR`` (input is NOT mutated).
    """
    if not failure_modes:
        return worker_flow_plan

    main_wid = worker_plan.main_worker_id
    main_flow = worker_flow_plan.worker_flows.get(main_wid)
    if main_flow is None:
        return worker_flow_plan

    # Build section -> span_ids index
    span_ids_by_section: dict[str, list[str]] = {}
    for s in spans:
        if s.source_section_id:
            span_ids_by_section.setdefault(s.source_section_id, []).append(s.span_id)

    # Collect existing condition text for dedup
    existing_conditions: set[str] = set()
    for exc in main_flow.exception_flows:
        existing_conditions.add(_normalize_condition(exc.condition_text))

    # Build new exception flows
    new_exc_flows: list[ExceptionFlow] = []
    flow_counter = len(main_flow.exception_flows)

    for fact in failure_modes:
        normalized_condition = _normalize_condition(fact.text)

        # Dedup by normalized condition text only
        if normalized_condition in existing_conditions:
            continue

        existing_conditions.add(normalized_condition)
        ev_span_ids = _resolve_fact_span_ids(fact, span_ids_by_section)

        flow_counter += 1
        new_exc_flows.append(
            ExceptionFlow(
                flow_id=f"exc_adapter_{flow_counter - 1:02d}",
                condition_text=fact.text,
                spans=ev_span_ids,
            )
        )

    if not new_exc_flows:
        return worker_flow_plan

    updated_flow = FlowStructureIR(
        main_flow_spans=list(main_flow.main_flow_spans),
        alternative_flows=list(main_flow.alternative_flows),
        exception_flows=main_flow.exception_flows + new_exc_flows,
        delegation_candidates=list(main_flow.delegation_candidates),
    )

    updated_worker_flows = dict(worker_flow_plan.worker_flows)
    updated_worker_flows[main_wid] = updated_flow

    return WorkerFlowPlanIR(
        worker_flows=updated_worker_flows,
        warnings=list(worker_flow_plan.warnings),
    )


def bridge_delegation_intents(
    delegation_intents: list[DelegationIntentFact],
    handoffs: list[WorkerHandoffIR] | None,
    spans: list[SpanIR],
    known_child_worker_ids: set[str] | None = None,
    declared_apis: set[str] | None = None,
) -> list[CompileDiagnostic]:
    """Emit diagnostics for delegation intents without valid handoffs.

    For each DelegationIntentFact, if no *valid* handoff exists that
    covers the same evidence, emit a ``type_or_contract_ambiguity``
    diagnostic.  A handoff is valid only when it has a concrete contract
    (target worker + IO bindings for invoke, or api_ref for api_call).

    The diagnostic does NOT block rendering of the element itself
    (there is nothing to render), but it does block completion,
    causing ``partial`` status.

    Args:
        delegation_intents: DelegationIntentFact objects from the adapter.
        handoffs: WorkerHandoffIR list from the worker plan (may be None
            or empty in legacy path).
        spans: All SpanIR objects from Stage 1.
        known_child_worker_ids: Valid child worker IDs (invoke target).
        declared_apis: Known API names (api_call target).

    Returns:
        List of CompileDiagnostic records.
    """
    diags: list[CompileDiagnostic] = []
    if not delegation_intents:
        return diags

    handoffs = handoffs or []

    # Collect evidence sections covered by *valid* handoffs
    valid_handoff_sections: set[str] = set()
    for h in handoffs:
        if not _is_valid_handoff(h, known_child_worker_ids, declared_apis):
            continue
        hint_span_ids: list[str] = []
        if h.invoke_location_hint.after_span_id:
            hint_span_ids.append(h.invoke_location_hint.after_span_id)
        if h.invoke_location_hint.before_span_id:
            hint_span_ids.append(h.invoke_location_hint.before_span_id)
        hint_span_ids.extend(h.failure_policy.source_span_ids)
        for sid in hint_span_ids:
            span = next((s for s in spans if s.span_id == sid), None)
            if span and span.source_section_id:
                valid_handoff_sections.add(span.source_section_id)

    for idx, intent in enumerate(delegation_intents):
        # Resolve evidence sections from the intent
        intent_sections: set[str] = set()
        intent_span_ids: list[str] = []
        for ev in getattr(intent, "evidence", []):
            sid = getattr(ev, "source_section_id", None)
            if sid:
                intent_sections.add(sid)
            if getattr(ev, "source_span_ids", None):
                intent_span_ids.extend(ev.source_span_ids)

        # Resolve spans by section if no direct span_ids
        if not intent_span_ids:
            for sid in intent_sections:
                intent_span_ids.extend(
                    s.span_id for s in spans
                    if s.source_section_id == sid
                )

        # Only a valid handoff suppresses the diagnostic
        if intent_sections & valid_handoff_sections:
            continue

        diags.append(
            CompileDiagnostic(
                diagnostic_id=f"diag_del_{idx:04d}",
                kind="type_or_contract_ambiguity",
                severity="warning",
                message=(
                    f"Delegation intent '{intent.name}' exists but no "
                    f"valid handoff contract was materialized. "
                    f"The delegation is not executable."
                ),
                target_ref=f"delegation_intent:{intent.name}",
                source_span_ids=intent_span_ids,
                suggested_resolution=(
                    "Specify target worker, input bindings, output "
                    "bindings, and invocation condition for this "
                    "delegation."
                ),
                blocks_rendering=False,
                blocks_completion=True,
            )
        )

    return diags


def _is_valid_handoff(
    handoff: WorkerHandoffIR,
    known_child_worker_ids: set[str] | None,
    declared_apis: set[str] | None,
) -> bool:
    """Check whether a handoff has sufficient contract evidence to be
    considered valid.  Mirrors ProducerIndex / Gate rules."""
    if handoff.mode == "invoke":
        if not handoff.to_worker:
            return False
        if known_child_worker_ids is not None:
            if handoff.to_worker not in known_child_worker_ids:
                return False
        if not handoff.input_bindings:
            return False
        if not handoff.output_bindings:
            return False
        return True
    if handoff.mode == "api_call":
        if not handoff.api_ref:
            return False
        if declared_apis is not None:
            if handoff.api_ref not in declared_apis:
                return False
        return True
    return False
