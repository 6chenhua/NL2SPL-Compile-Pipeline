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


def _is_empty_failure_marker(text: str) -> bool:
    """检查 failure 文本是否为空标记。
    
    Args:
        text: failure condition 文本
    
    Returns:
        True 如果文本是空标记（如 "None", "N/A"）
    """
    candidate = text.strip()
    candidate = re.sub(r"^\s*[-*+]\s+", "", candidate)
    candidate = re.sub(r"^\s*\d+\.\s+", "", candidate)
    if ":" in candidate or "：" in candidate:
        _label, candidate = re.split(r"[:：]", candidate, maxsplit=1)
    candidate = candidate.replace("**", "").replace("__", "")
    normalized = re.sub(r"[^\w\s]", "", candidate.lower()).strip()
    return normalized in {"none", "na", "not applicable", "nil", "empty"}


def _is_aggregate_of_items(
    candidate_text: str,
    existing_texts: list[str]
) -> bool:
    """检查 candidate 是否为多个 existing items 的汇总。
    
    Args:
        candidate_text: 候选文本（可能是 aggregate）
        existing_texts: 已存在的文本列表
    
    Returns:
        True 如果 candidate 包含 2+ 个 existing items
    
    Examples:
        >>> _is_aggregate_of_items(
        ...     "Missing inputs - Tone mismatch - Unverified facts",
        ...     ["Missing inputs", "Tone mismatch"]
        ... )
        True
    """
    candidate_norm = _normalize_condition(candidate_text)
    
    contained_count = 0
    for existing in existing_texts:
        existing_norm = _normalize_condition(existing)
        # 检查 existing 是否为 candidate 的子串
        if existing_norm and existing_norm in candidate_norm:
            contained_count += 1
    
    # 如果包含 2+ 个 items，认为是 aggregate
    return contained_count >= 2


def _is_item_of_aggregate(
    item_text: str,
    aggregate_text: str
) -> bool:
    """检查 item 是否为 aggregate 的一部分。
    
    Args:
        item_text: 单个 item 文本
        aggregate_text: 可能的 aggregate 文本
    
    Returns:
        True 如果 item 是 aggregate 的一部分
    
    Examples:
        >>> _is_item_of_aggregate(
        ...     "Missing inputs",
        ...     "Missing inputs - Tone mismatch - Unverified facts"
        ... )
        True
    """
    item_norm = _normalize_condition(item_text)
    aggregate_norm = _normalize_condition(aggregate_text)
    
    # item 是 aggregate 的子串，且长度差异显著
    if item_norm in aggregate_norm and len(item_norm) < len(aggregate_norm) * 0.6:
        return True
    
    return False


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
    intermediate_results: dict | None = None,
) -> FlowStructureIR:
    """D8: COMPATIBILITY FALLBACK — not the primary production path.

    Use ``materialize_route_exception_flows()`` for route-annotated input.
    This bridge only runs as a hard-fact fallback for failure conditions
    not already covered by route-derived exception flows (see orchestrator
    guard).

    For each failure fact, if no existing ExceptionFlow already has a
    matching normalized condition text, create a new skeleton.  No handler
    blocks or steps are created -- the compiler's missing_handler
    diagnostic surfaces the gap.

    Deduplication is by normalized condition text only.  Two facts whose
    condition text normalizes to the same string are treated as duplicates
    and only the first is kept.  Multiple failure modes from the same
    section naturally share span IDs and are NOT deduplicated by span
    overlap.
    
    Aggregate deduplication: If a new item is part of an existing aggregate,
    the aggregate is marked for removal and the item is kept. If a new
    candidate is an aggregate of existing items, it is skipped.

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

    # Collect existing condition text for dedup and aggregate detection
    existing_condition_texts: list[str] = [
        exc.condition_text for exc in existing_flow.exception_flows
    ]
    existing_conditions: set[str] = {
        _normalize_condition(text) for text in existing_condition_texts
    }
    
    # Track aggregates to remove
    aggregates_to_remove: set[str] = set()

    # Build new exception flows
    new_exc_flows: list[ExceptionFlow] = []
    flow_counter = len(existing_flow.exception_flows)

    for fact in failure_modes:
        # 跳过空标记
        if _is_empty_failure_marker(fact.text):
            continue
        
        normalized_condition = _normalize_condition(fact.text)

        # Dedup by normalized condition text only
        if normalized_condition in existing_conditions:
            continue
        
        # 检查是否为 aggregate（包含多个已存在的 items）
        if _is_aggregate_of_items(fact.text, existing_condition_texts):
            # 这是一个 aggregate，跳过
            continue
        
        # 检查是否为某个 existing aggregate 的 item
        for existing_text in existing_condition_texts:
            if _is_item_of_aggregate(fact.text, existing_text):
                # 这是一个具体 item，标记 aggregate 待移除
                aggregates_to_remove.add(existing_text)

        existing_conditions.add(normalized_condition)
        existing_condition_texts.append(fact.text)
        ev_span_ids = _resolve_fact_span_ids(fact, span_ids_by_section)

        flow_counter += 1
        new_flow = ExceptionFlow(
            flow_id=f"exc_adapter_{flow_counter - 1:02d}",
            condition_text=fact.text,
            spans=ev_span_ids,
        )
        new_exc_flows.append(new_flow)

        if intermediate_results is not None:
            origins = intermediate_results.setdefault("flow_origins", {})
            origins[new_flow.flow_id] = "bridge_fallback"

    if not new_exc_flows and not aggregates_to_remove:
        return existing_flow
    
    # 过滤掉 aggregates
    filtered_existing_flows = [
        exc for exc in existing_flow.exception_flows
        if exc.condition_text not in aggregates_to_remove
    ]

    return FlowStructureIR(
        main_flow_spans=list(existing_flow.main_flow_spans),
        alternative_flows=list(existing_flow.alternative_flows),
        exception_flows=filtered_existing_flows + new_exc_flows,
        delegation_candidates=list(existing_flow.delegation_candidates),
    )


def bridge_failure_modes_worker_scoped(
    failure_modes: list[FailureModeFact],
    spans: list[SpanIR],
    worker_flow_plan: WorkerFlowPlanIR,
    worker_plan: WorkerPlanIR,
    intermediate_results: dict | None = None,
) -> WorkerFlowPlanIR:
    """D8: COMPATIBILITY FALLBACK — not the primary production path.

    Appends source-backed ``ExceptionFlow`` skeletons to the **main
    worker's** ``FlowStructureIR`` inside the ``WorkerFlowPlanIR``.
    Deduplication and span resolution follow the same rules as the
    legacy bridge -- no handler blocks or steps are created.
    
    Aggregate deduplication: If a new item is part of an existing aggregate,
    the aggregate is marked for removal and the item is kept. If a new
    candidate is an aggregate of existing items, it is skipped.

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

    # D3: collect existing condition text from ALL worker flows for dedup
    existing_condition_texts: list[str] = []
    existing_conditions: set[str] = set()
    for flow in worker_flow_plan.worker_flows.values():
        for exc in flow.exception_flows:
            existing_condition_texts.append(exc.condition_text)
            existing_conditions.add(_normalize_condition(exc.condition_text))
    
    # Track aggregates to remove from main_flow
    aggregates_to_remove: set[str] = set()

    # Build new exception flows
    new_exc_flows: list[ExceptionFlow] = []
    flow_counter = len(main_flow.exception_flows)

    for fact in failure_modes:
        # 跳过空标记
        if _is_empty_failure_marker(fact.text):
            continue
        
        normalized_condition = _normalize_condition(fact.text)

        # Dedup by normalized condition text only
        if normalized_condition in existing_conditions:
            continue
        
        # 检查是否为 aggregate（包含多个已存在的 items）
        if _is_aggregate_of_items(fact.text, existing_condition_texts):
            # 这是一个 aggregate，跳过
            continue
        
        # 检查是否为某个 existing aggregate 的 item
        for existing_text in existing_condition_texts:
            if _is_item_of_aggregate(fact.text, existing_text):
                # 这是一个具体 item，标记 aggregate 待移除
                aggregates_to_remove.add(existing_text)

        existing_conditions.add(normalized_condition)
        existing_condition_texts.append(fact.text)
        ev_span_ids = _resolve_fact_span_ids(fact, span_ids_by_section)

        flow_counter += 1
        new_flow = ExceptionFlow(
            flow_id=f"exc_adapter_{flow_counter - 1:02d}",
            condition_text=fact.text,
            spans=ev_span_ids,
        )
        new_exc_flows.append(new_flow)

        if intermediate_results is not None:
            origins = intermediate_results.setdefault("flow_origins", {})
            origins[new_flow.flow_id] = "bridge_fallback"

    if not new_exc_flows and not aggregates_to_remove:
        return worker_flow_plan
    
    # 过滤掉 aggregates
    filtered_main_flows = [
        exc for exc in main_flow.exception_flows
        if exc.condition_text not in aggregates_to_remove
    ]

    updated_flow = FlowStructureIR(
        main_flow_spans=list(main_flow.main_flow_spans),
        alternative_flows=list(main_flow.alternative_flows),
        exception_flows=filtered_main_flows + new_exc_flows,
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
    """D8: COMPATIBILITY FALLBACK — prefer route-driven delegation diagnostics.

    Emit diagnostics for delegation intents without valid handoffs.

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

    # Collect span ids covered by *valid* handoffs
    valid_handoff_span_ids: set[str] = set()
    for h in handoffs:
        if not _is_valid_handoff(h, known_child_worker_ids, declared_apis):
            continue
        hint_span_ids: list[str] = []
        if h.invoke_location_hint.after_span_id:
            hint_span_ids.append(h.invoke_location_hint.after_span_id)
        if h.invoke_location_hint.before_span_id:
            hint_span_ids.append(h.invoke_location_hint.before_span_id)
        hint_span_ids.extend(h.failure_policy.source_span_ids)
        valid_handoff_span_ids.update(hint_span_ids)

    def _add_unique(target: list[str], source: list[str]) -> None:
        for span_id in source:
            if span_id not in target:
                target.append(span_id)

    for idx, intent in enumerate(delegation_intents):
        # Resolve suppression_span_ids separately from diagnostic_span_ids.
        # Suppression must be precise; diagnostics can retain broader evidence.
        suppression_span_ids: list[str] = []
        diagnostic_span_ids: list[str] = []
        for ev in getattr(intent, "evidence", []):
            if getattr(ev, "source_span_ids", None):
                _add_unique(suppression_span_ids, ev.source_span_ids)
                _add_unique(diagnostic_span_ids, ev.source_span_ids)
        if not suppression_span_ids:
            import re as _re
            intent_norm = _re.sub(r"[^\w\s]", "", intent.text.strip().lower())
            for sid in (getattr(ev, "source_section_id", None)
                        for ev in getattr(intent, "evidence", [])
                        if getattr(ev, "source_section_id", None)):
                section_spans = [s for s in spans if s.source_section_id == sid]
                section_span_ids = [s.span_id for s in section_spans]
                narrowed = []
                for s in section_spans:
                    span_norm = _re.sub(r"[^\w\s]", "", s.text.strip().lower())
                    if intent_norm in span_norm or span_norm in intent_norm:
                        narrowed.append(s.span_id)
                if narrowed:
                    _add_unique(suppression_span_ids, narrowed)
                    _add_unique(diagnostic_span_ids, narrowed)
                elif len(section_spans) == 1:
                    # Single-span section: the only span is the intent span.
                    _add_unique(suppression_span_ids, section_span_ids)
                    _add_unique(diagnostic_span_ids, section_span_ids)
                else:
                    # Multi-span section with no text match: keep evidence for
                    # diagnostics, but do not allow section-wide suppression.
                    _add_unique(diagnostic_span_ids, section_span_ids)
                # else: multi-span section, no text match → do NOT suppress

        # D10: suppress only when suppression_span_ids precisely overlap
        # valid handoff span ids.  No section-wide fallback.
        if suppression_span_ids and valid_handoff_span_ids:
            if set(suppression_span_ids) & valid_handoff_span_ids:
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
                source_span_ids=diagnostic_span_ids,
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


# route-driven exception materializer moved to route_exception_materializer.py (D11)
