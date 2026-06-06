"""Route-driven exception flow materializer (D2/D11).

Consumes ``RouteAnnotation`` entries targeting ``EXCEPTION_FLOW.condition``
and ``EXCEPTION_FLOW.handler`` to create ``ExceptionFlow`` skeletons with
optional handler blocks. This is the canonical production path.
"""

from __future__ import annotations

import re
from typing import Any

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.span_ir import SpanIR


def _normalize_condition(text: str) -> str:
    """Normalize condition text for comparison: lowercase, strip punctuation."""
    return re.sub(r"[^\w\s]", "", text.strip().lower())


def _is_empty_condition(text: str) -> bool:
    """Return True when condition text is an empty marker."""
    candidate = text.strip()
    candidate = re.sub(r"^\s*[-*+]\s+", "", candidate)
    candidate = re.sub(r"^\s*\d+\.\s+", "", candidate)
    if ":" in candidate or "\uff1a" in candidate:
        _label, candidate = re.split(r"[:\uff1a]", candidate, maxsplit=1)
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
    normalized condition text. Does NOT create handler blocks or steps.
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
        if ann.semantic_role not in ("failure_mode", "failure_condition"):
            continue
        if ann.executable is not False:
            continue
        span = span_by_id.get(ann.span_id)
        if span is None:
            continue
        if span.is_placeholder:
            continue

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


def materialize_handler_blocks(
    exception_flows: list[ExceptionFlow],
    routes: Any,
    spans: list[SpanIR],
    existing_blocks: BlockStructureIR | None = None,
    packets: list[Any] | None = None,
) -> BlockStructureIR:
    """Create handler blocks for exception flows from handler annotations.

    Pairs handler spans with condition exception flows by matching
    failure_item_index from packet metadata. Falls back to order-based
    pairing when metadata is unavailable.
    """
    blocks = existing_blocks or BlockStructureIR()

    handler_candidates = routes.get_construct_slot_candidates("EXCEPTION_FLOW", "handler")
    handler_anns = [
        a for a in handler_candidates
        if a.semantic_role == "exception_handler" and a.executable is True
    ]
    if not handler_anns:
        return blocks

    span_by_id = {s.span_id: s for s in spans}
    packet_by_id = {p.packet_id: p for p in (packets or [])}

    flow_by_item_idx: dict[tuple[str, int], ExceptionFlow] = {}
    for exc in exception_flows:
        if exc.spans:
            cond_span = span_by_id.get(exc.spans[0])
            if cond_span and cond_span.source_packet_id:
                pkt = packet_by_id.get(cond_span.source_packet_id)
                if pkt and "failure_item_index" in pkt.metadata:
                    key = (
                        cond_span.source_section_id or "",
                        pkt.metadata["failure_item_index"],
                    )
                    flow_by_item_idx[key] = exc

    flows_by_section: dict[str, list[ExceptionFlow]] = {}
    for exc in exception_flows:
        if exc.spans:
            cond_span = span_by_id.get(exc.spans[0])
            if cond_span:
                flows_by_section.setdefault(
                    cond_span.source_section_id or "", []
                ).append(exc)

    block_counter = 0
    for handler_ann in handler_anns:
        handler_span = span_by_id.get(handler_ann.span_id)
        if handler_span is None or handler_span.is_placeholder:
            continue

        section_id = handler_ann.source_section_id or ""
        exc_flow = None

        handler_pkt = packet_by_id.get(handler_ann.source_packet_id or "")
        if handler_pkt and "failure_item_index" in handler_pkt.metadata:
            key = (section_id, handler_pkt.metadata["failure_item_index"])
            exc_flow = flow_by_item_idx.get(key)

        # Last-resort structural pairing when item index metadata is absent.
        if exc_flow is None:
            flows = flows_by_section.get(section_id, [])
            if flows:
                exc_flow = flows[0]

        if exc_flow is None:
            continue

        if handler_ann.span_id not in exc_flow.spans:
            exc_flow.spans.append(handler_ann.span_id)

        flow_id = exc_flow.flow_id
        if flow_id not in blocks.exception_flow_blocks:
            blocks.exception_flow_blocks[flow_id] = []
        block_counter += 1
        blocks.exception_flow_blocks[flow_id].append(
            BlockIR(
                block_id=f"b_exc_handler_{block_counter:02d}",
                block_type="SEQUENTIAL",
                spans=[handler_ann.span_id],
            )
        )

    return blocks
