"""Route-driven exception flow materializer (D2/D11).

Consumes ``RouteAnnotation`` entries targeting ``EXCEPTION_FLOW.condition``
and creates partial ``ExceptionFlow`` skeletons without inventing handler
blocks or steps.  This is the canonical production path; hard-fact bridges
in ``fact_bridges.py`` are compatibility fallbacks.
"""

from __future__ import annotations

import re
from typing import Any

from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.span_ir import SpanIR


def _normalize_condition(text: str) -> str:
    """Normalize condition text for comparison: lowercase, strip punctuation."""
    return re.sub(r"[^\w\s]", "", text.strip().lower())


def _is_empty_condition(text: str) -> bool:
    """检查 condition 文本是否为空标记。
    
    Args:
        text: condition 文本
    
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


def materialize_route_exception_flows(
    flow: FlowStructureIR,
    routes: Any,  # FieldRouteIR (lazy import to avoid cycle)
    spans: list[SpanIR],
) -> FlowStructureIR:
    """Create partial ExceptionFlow skeletons from route annotations.

    Consumes ``RouteAnnotation`` entries with
    ``semantic_role="failure_mode"``, ``construct_target="EXCEPTION_FLOW"``,
    ``slot_target="condition"``, and ``executable=False``.

    Deduplicates against existing LLM-generated exception flows by
    normalized condition text.  Does NOT create handler blocks or steps.
    Returns a new ``FlowStructureIR`` when materialization occurs;
    returns the original *flow* unchanged otherwise.
    """
    span_by_id = {s.span_id: s for s in spans}
    existing_conditions = {
        _normalize_condition(exc.condition_text)
        for exc in flow.exception_flows
    }

    candidates = routes.get_construct_slot_candidates("EXCEPTION_FLOW", "condition")
    new_exc_flows: list[ExceptionFlow] = []
    idx = len(flow.exception_flows)

    for ann in candidates:
        if ann.semantic_role != "failure_mode":
            continue
        if ann.executable is not False:
            continue
        span = span_by_id.get(ann.span_id)
        if span is None:
            continue
        
        # 跳过 placeholder spans
        if span.is_placeholder:
            continue
        
        # 额外防御：检查文本内容
        cond_text = span.text
        if _is_empty_condition(cond_text):
            continue
        
        if _normalize_condition(cond_text) in existing_conditions:
            continue
        existing_conditions.add(_normalize_condition(cond_text))

        new_exc_flows.append(
            ExceptionFlow(
                flow_id=f"exc_adapter_{idx:02d}",
                condition_text=cond_text,
                spans=[ann.span_id],
            )
        )
        idx += 1

    if not new_exc_flows:
        return flow

    return FlowStructureIR(
        main_flow_spans=list(flow.main_flow_spans),
        alternative_flows=list(flow.alternative_flows),
        exception_flows=list(flow.exception_flows) + new_exc_flows,
        delegation_candidates=list(flow.delegation_candidates),
    )
