"""ConstructPlan builder from resolved spans and route annotations."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from nl2spl.compiler.capability_intent.model import (
    ExternalCapabilityIntentPlanIR,
)
from nl2spl.compiler.construct_plan.model import (
    APICallArgumentBindingIR,
    APICallDemand,
    APIDeclarationDemand,
    ConstructPlan,
    ConstructSlotDemand,
    ExceptionFlowDemand,
    OperationCoverageIR,
)
from nl2spl.compiler.constructs.graph import ConstructEdge
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR


class ConstructPlanner:
    """Build source-demanded construct plan from structured route evidence."""

    def plan(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        *,
        source_schema: str | None = None,
        capability_intent_plan: ExternalCapabilityIntentPlanIR | None = None,
    ) -> ConstructPlan:
        """Build a ConstructPlan without LLM calls or raw-NL semantic rules."""
        span_by_id = {span.span_id: span for span in spans}
        conditions = _condition_annotations(routes)
        handlers = _handler_annotations(routes)
        dual_role_span_ids = _dual_role_handler_spans(routes, handlers)

        demands: list[ExceptionFlowDemand | APIDeclarationDemand | APICallDemand] = []
        diagnostics: list[CompileDiagnostic] = []

        grouped_conditions = _group_annotations(conditions)
        grouped_handlers = _group_annotations(handlers)
        group_keys = sorted(set(grouped_conditions) | set(grouped_handlers))

        demand_index = 0
        used_handlers: set[str] = set()

        for group_key in group_keys:
            group_conditions = grouped_conditions.get(group_key, [])
            group_handlers = grouped_handlers.get(group_key, [])
            if not group_conditions and group_handlers:
                demand, demand_index = self._orphan_handler_demand(
                    group_key,
                    group_handlers,
                    demand_index,
                )
                used_handlers.update(ann.span_id for ann in group_handlers)
                demands.append(demand)
                continue

            if len(group_conditions) == 1 and len(group_handlers) <= 1:
                demand, demand_index = self._condition_demand(
                    group_key,
                    group_conditions[0],
                    group_handlers,
                    span_by_id,
                    dual_role_span_ids,
                    demand_index,
                )
                used_handlers.update(ann.span_id for ann in group_handlers)
                demands.append(demand)
                continue

            if group_conditions and not group_handlers:
                for condition in group_conditions:
                    demand, demand_index = self._condition_demand(
                        group_key,
                        condition,
                        [],
                        span_by_id,
                        dual_role_span_ids,
                        demand_index,
                    )
                    demands.append(demand)
                continue

            # Multiple condition/handler candidates without explicit pairing
            # evidence are not paired.  Conditions remain partial skeleton
            # demands; handler spans are reserved and a planner diagnostic
            # records the ambiguity.
            if group_conditions and group_handlers:
                diagnostics.append(
                    _diagnostic(
                        kind="construct_plan_ambiguous_exception_pairing",
                        message=(
                            "Multiple EXCEPTION_FLOW condition/handler "
                            f"annotations share group {group_key!r}; "
                            "no source-backed pairing was available."
                        ),
                        span_ids=[
                            ann.span_id for ann in list(group_conditions) + list(group_handlers)
                        ],
                        target_ref=f"construct_plan:group:{group_key}",
                    )
                )
                for condition in group_conditions:
                    demand, demand_index = self._condition_demand(
                        group_key,
                        condition,
                        [],
                        span_by_id,
                        dual_role_span_ids,
                        demand_index,
                        pairing_status="ambiguous_pairing",
                    )
                    demands.append(demand)
                used_handlers.update(ann.span_id for ann in group_handlers)

        demands = _attach_adjacent_orphan_handlers(
            demands,
            spans,
        )

        (
            api_declaration_demands,
            api_call_demands,
            api_call_argument_bindings,
        ) = _api_demands_from_intent_plan(
            capability_intent_plan,
            span_by_id,
        )
        demands.extend(api_declaration_demands)
        demands.extend(api_call_demands)

        reserved_span_ids = (
            ({ann.span_id for ann in handlers} - dual_role_span_ids)
            | _api_reserved_span_ids(api_call_demands)
        )
        plan = ConstructPlan(
            plan_id="construct_plan_00",
            source_schema=source_schema,
            demands=demands,
            api_call_argument_bindings=api_call_argument_bindings,
            reserved_span_ids=reserved_span_ids,
            dual_role_span_ids=set(dual_role_span_ids),
            diagnostics=diagnostics,
            metadata={
                "exception_condition_count": len(conditions),
                "exception_handler_count": len(handlers),
                "used_handler_count": len(used_handlers),
                "api_declaration_demand_count": len(api_declaration_demands),
                "api_call_demand_count": len(api_call_demands),
                "api_demand_authority": "external_capability_intent_plan",
            },
        )
        return plan

    def _condition_demand(
        self,
        group_key: str,
        condition: RouteAnnotation,
        handlers: list[RouteAnnotation],
        span_by_id: dict[str, SpanIR],
        dual_role_span_ids: set[str],
        demand_index: int,
        *,
        pairing_status: str | None = None,
    ) -> tuple[ExceptionFlowDemand, int]:
        demand_id = f"exc_demand_{demand_index:02d}"
        demand_index += 1
        condition_span = span_by_id.get(condition.span_id)
        handler_span_ids = [ann.span_id for ann in handlers]
        source_span_ids = [condition.span_id] + handler_span_ids
        status = pairing_status or (
            "condition_with_handler" if handler_span_ids else "condition_only"
        )
        demand = ExceptionFlowDemand(
            demand_id=demand_id,
            condition_span_ids=[condition.span_id],
            handler_span_ids=handler_span_ids,
            condition_text=(
                condition_span.guard_text_exact
                if condition_span
                and condition_span.segmentation_kind == "guarded_action"
                and condition_span.guard_text_exact
                else condition_span.text if condition_span else None
            ),
            slots={
                "condition": _slot_from_annotations("condition", [condition]),
                "handler": _slot_from_annotations(
                    "handler",
                    handlers,
                    status="present" if handlers else "missing",
                ),
            },
            pairing_status=status,
            materialization_policy="partial_skeleton_allowed",
            reserved_span_ids=set(handler_span_ids) - dual_role_span_ids,
            dual_role_span_ids=set(handler_span_ids) & dual_role_span_ids,
            source_span_ids=source_span_ids,
            source_section_id=condition.source_section_id,
            source_packet_id=condition.source_packet_id,
            construct_path=("construct_plan", "exception_flows", demand_id),
            related_edges=_slot_edges(
                demand_id,
                condition_span_ids=[condition.span_id],
                handler_span_ids=handler_span_ids,
            ),
            metadata={
                "group_key": group_key,
                "slot_pairing_source": _pairing_source(condition, handlers),
            },
        )
        return demand, demand_index

    def _orphan_handler_demand(
        self,
        group_key: str,
        handlers: list[RouteAnnotation],
        demand_index: int,
    ) -> tuple[ExceptionFlowDemand, int]:
        demand_id = f"exc_demand_{demand_index:02d}"
        demand_index += 1
        handler_span_ids = [ann.span_id for ann in handlers]
        demand = ExceptionFlowDemand(
            demand_id=demand_id,
            condition_span_ids=[],
            handler_span_ids=handler_span_ids,
            slots={
                "condition": ConstructSlotDemand(
                    slot_name="condition",
                    status="missing",
                    evidence_relation="ambiguous",
                ),
                "handler": _slot_from_annotations("handler", handlers),
            },
            pairing_status="orphan_handler",
            materialization_policy="no_condition_no_materialization",
            reserved_span_ids=set(handler_span_ids),
            source_span_ids=handler_span_ids,
            source_section_id=handlers[0].source_section_id if handlers else None,
            source_packet_id=handlers[0].source_packet_id if handlers else None,
            construct_path=("construct_plan", "exception_flows", demand_id),
            related_edges=_slot_edges(
                demand_id,
                condition_span_ids=[],
                handler_span_ids=handler_span_ids,
            ),
            metadata={"group_key": group_key},
        )
        return demand, demand_index


def _condition_annotations(routes: FieldRouteIR) -> list[RouteAnnotation]:
    return [
        ann
        for ann in routes.get_construct_slot_candidates("EXCEPTION_FLOW", "condition")
        if ann.semantic_role in ("failure_mode", "failure_condition") and ann.executable is False
    ]


def _handler_annotations(routes: FieldRouteIR) -> list[RouteAnnotation]:
    return [
        ann
        for ann in routes.get_construct_slot_candidates("EXCEPTION_FLOW", "handler")
        if ann.semantic_role in ("exception_handler", "exception_handler_action")
        and ann.executable is True
    ]


def _dual_role_handler_spans(
    routes: FieldRouteIR,
    handlers: list[RouteAnnotation],
) -> set[str]:
    handler_ids = {ann.span_id for ann in handlers}
    condition_ids = {
        ann.span_id
        for ann in routes.annotations
        if ann.construct_target == "EXCEPTION_FLOW"
        and ann.slot_target == "condition"
        and ann.executable is False
    }
    return {
        ann.span_id
        for ann in routes.annotations
        if ann.span_id in handler_ids
        and (
            ann.span_id in condition_ids
            or (
                ann.semantic_role == "process_step"
                and ann.executable is True
                and ann.field == "behavior"
            )
        )
    }


def _api_demands_from_intent_plan(
    intent_plan: ExternalCapabilityIntentPlanIR | None,
    span_by_id: dict[str, SpanIR],
) -> tuple[
    list[APIDeclarationDemand],
    list[APICallDemand],
    list[APICallArgumentBindingIR],
]:
    """Lower only resolver-authorized final intents into construct demands."""
    declarations: list[APIDeclarationDemand] = []
    calls: list[APICallDemand] = []
    argument_bindings: list[APICallArgumentBindingIR] = []
    if intent_plan is None:
        return declarations, calls, argument_bindings
    for intent in sorted(intent_plan.intents, key=lambda item: item.intent_id):
        if intent.capability_admission_status != "confirmed_capability":
            continue
        declaration_id = _stable_capability_demand_id("api_decl", intent.intent_id)
        explicit_names = [intent.capability_ref] if intent.capability_ref else []
        mechanism_status = (
            "explicit"
            if intent.capability_ref
            else "concrete_unnamed"
            if intent.identity_status == "described_unnamed"
            else "unknown"
        )
        source_span_ids = list(intent.source_span_ids)
        evidence_ids = [item.evidence_id for item in intent.evidence]
        declaration_metadata = {
            "capability_intent_id": intent.intent_id,
            "operation_text": intent.operation_text,
        }
        declaration = APIDeclarationDemand(
            demand_id=declaration_id,
            slots={
                "source_evidence": ConstructSlotDemand(
                    slot_name="source_evidence",
                    source_span_ids=source_span_ids,
                    semantic_roles=["external_capability"],
                    executable_values=[False],
                    source_section_id=intent.source_section_id,
                    source_packet_id=intent.source_packet_id,
                    evidence_relation="direct",
                    status="present",
                    metadata={"semantic_evidence_ids": evidence_ids},
                ),
                "api_name": ConstructSlotDemand(
                    slot_name="api_name",
                    source_span_ids=source_span_ids if explicit_names else [],
                    semantic_roles=["capability_identity"],
                    executable_values=[False],
                    source_section_id=intent.source_section_id,
                    source_packet_id=intent.source_packet_id,
                    evidence_relation="direct" if explicit_names else "derived",
                    status="present" if explicit_names else "missing",
                    metadata={"explicit_name_candidates": explicit_names},
                ),
            },
            pairing_status=(
                "paired"
                if intent.invocation_admission_status == "confirmed_invocation"
                else "declaration_only"
            ),
            materialization_policy="partial_skeleton_allowed",
            owner_policy="agent_global",
            source_span_ids=source_span_ids,
            source_section_id=intent.source_section_id,
            source_packet_id=intent.source_packet_id,
            construct_path=("construct_plan", "api_declarations", declaration_id),
            related_edges=_api_edges(declaration_id, source_span_ids, "source_evidence"),
            metadata=declaration_metadata,
            declaration_annotation_ids=evidence_ids,
            explicit_name_candidates=explicit_names,
            integration_admission="confirmed",
            mechanism_status=mechanism_status,
            inferred_name_allowed=intent.identity_status == "described_unnamed",
            api_group_id=intent.intent_id,
            owner_scope="agent_global",
            capability_intent_id=intent.intent_id,
            capability_surface=intent.capability_surface,
        )
        declarations.append(declaration)
        if intent.invocation_admission_status != "confirmed_invocation":
            continue
        call_id = _stable_capability_demand_id("api_call", intent.intent_id)
        coverage, consumed, residual, policy = _operation_coverage(intent, span_by_id)
        call = APICallDemand(
            demand_id=call_id,
            slots={
                "call_action": ConstructSlotDemand(
                    slot_name="call_action",
                    source_span_ids=[item.source_span_id for item in coverage],
                    semantic_roles=["external_capability_invocation"],
                    executable_values=[True],
                    source_section_id=intent.source_section_id,
                    source_packet_id=intent.source_packet_id,
                    status="present" if coverage else "ambiguous",
                    metadata={"coverage_ids": [item.coverage_id for item in coverage]},
                )
            },
            pairing_status="paired",
            materialization_policy="call_demand_only",
            owner_policy="stage4_stage5_placement_required",
            owner_worker_id=None,
            source_span_ids=source_span_ids,
            source_section_id=intent.source_section_id,
            source_packet_id=intent.source_packet_id,
            construct_path=("construct_plan", "api_calls", call_id),
            related_edges=_api_edges(call_id, source_span_ids, "call_action"),
            metadata={
                "capability_intent_id": intent.intent_id,
                "capability_surface": intent.capability_surface,
            },
            call_annotation_ids=evidence_ids,
            declaration_demand_id=declaration_id,
            api_group_id=intent.intent_id,
            action_text=intent.operation_text,
            worker_candidate_id=None,
            capability_intent_id=intent.intent_id,
            operation_coverage=coverage,
            consumes_behavior_span_ids=consumed,
            residual_behavior_span_ids=residual,
            behavior_lowering_policy=policy,
        )
        calls.append(call)
        argument_bindings.append(
            APICallArgumentBindingIR(
                call_demand_id=call_id,
                input_bindings={
                    f"input_{index:02d}": resource_ref
                    for index, resource_ref in enumerate(intent.input_refs)
                },
                output_bindings={
                    f"output_{index:02d}": resource_ref
                    for index, resource_ref in enumerate(intent.output_refs)
                },
                binding_status=intent.binding_status,
                unresolved_binding_claims=intent.unresolved_binding_claims,
                source_span_ids=intent.source_span_ids,
            )
        )
    return declarations, calls, argument_bindings


def _operation_coverage(
    intent: object,
    span_by_id: dict[str, SpanIR],
) -> tuple[list[OperationCoverageIR], list[str], list[str], str]:
    operation_evidence = [item for item in intent.evidence if item.claim == "operation"]
    coverage: list[OperationCoverageIR] = []
    residual: list[str] = []
    consumed: list[str] = []
    for item in operation_evidence:
        span = span_by_id.get(item.source_span_id)
        if span is None:
            continue
        surface_text, start, end, relation = _select_operation_coverage_surface(
            item,
            intent.evidence,
            span.text,
        )
        if start >= 0 and end is not None:
            for match in re.finditer(r"[^.!?]+[.!?]?", span.text):
                s_start, s_end = match.start(), match.end()
                if s_start <= start < s_end:
                    leading_part = span.text[s_start:start]
                    cleaned_leading = leading_part.strip(" ,;.")
                    is_conditional = re.match(
                        r"^(if|when|unless|in\s+case|provided\s+that|on\s+condition\s+that|once|as\s+long\s+as)\b",
                        cleaned_leading,
                        re.IGNORECASE,
                    )
                    if is_conditional:
                        start = s_start
                        end = s_end
                        surface_text = match.group(0)
                        break

        coverage_id = _stable_capability_demand_id(
            "operation_coverage",
            f"{intent.intent_id}|{item.source_span_id}|{item.surface_text}",
        )
        coverage.append(
            OperationCoverageIR(
                coverage_id=coverage_id,
                source_span_id=item.source_span_id,
                operation_surface=surface_text,
                char_start=start if start >= 0 else None,
                char_end=end,
                relation=relation,
            )
        )
        consumed.append(item.source_span_id)
        if start < 0 or _has_residual_text(span.text, start, end or start):
            residual.append(item.source_span_id)
    consumed = list(dict.fromkeys(consumed))
    residual = list(dict.fromkeys(residual))
    if not coverage:
        policy = "ambiguous"
    elif residual and all(
        item.char_start is not None and item.char_end is not None for item in coverage
    ):
        policy = "api_call_augments_behavior"
    elif residual:
        policy = "ambiguous"
    else:
        policy = "api_call_replaces_behavior"
    return coverage, consumed, residual, policy


def _api_reserved_span_ids(api_call_demands: list[APICallDemand]) -> set[str]:
    """Return API-owned spans that should not enter generic step extraction."""
    reserved: set[str] = set()
    for demand in api_call_demands:
        residual = set(demand.residual_behavior_span_ids)
        for span_id in demand.consumes_behavior_span_ids:
            if span_id not in residual:
                reserved.add(span_id)
    return reserved


def _select_operation_coverage_surface(
    operation_item: object,
    evidence_items: tuple[object, ...],
    span_text: str,
) -> tuple[str, int, int | None, str]:
    """Choose the source surface that best covers the API operation action.

    Semantic extraction can split a single API invocation into a narrow operation
    claim (for example, "retrieve them") and a wider invocation claim (for
    example, "retrieve them using approved source recipes"). Stage 7 action
    partitioning needs the wider action surface when it is source-backed and
    contains the operation range; otherwise the capability phrase becomes a fake
    trailing residual clause and CALL_API materialization is blocked.
    """
    surface_text = operation_item.surface_text
    start, end, relation = _locate_operation_surface(span_text, surface_text)
    if start < 0 or end is None:
        return surface_text, start, end, relation

    best = (surface_text, start, end, relation)
    for candidate in evidence_items:
        if candidate is operation_item:
            continue
        if candidate.claim != "invocation":
            continue
        if candidate.source_span_id != operation_item.source_span_id:
            continue
        cand_start, cand_end, cand_relation = _locate_operation_surface(
            span_text,
            candidate.surface_text,
        )
        if cand_start < 0 or cand_end is None:
            continue
        if cand_start <= start and cand_end >= end and cand_end - cand_start > end - start:
            best = (
                candidate.surface_text,
                cand_start,
                cand_end,
                cand_relation,
            )
    return best


def _locate_operation_surface(text: str, surface_text: str) -> tuple[int, int | None, str]:
    start = text.find(surface_text)
    if start >= 0:
        return start, start + len(surface_text), "direct"

    parts = re.split(r"\s+", surface_text.strip())
    if not parts:
        return -1, None, "normalized"
    pattern = r"\s+".join(re.escape(part) for part in parts)
    match = re.search(pattern, text)
    if match:
        return match.start(), match.end(), "normalized_whitespace"
    return -1, None, "normalized"


def _has_residual_text(text: str, start: int, end: int) -> bool:
    residual = text[:start] + text[end:]
    residual = re.sub(r"[\s\W_]+", "", residual, flags=re.UNICODE)
    return bool(residual)


def _stable_capability_demand_id(prefix: str, stable_source: str) -> str:
    digest = hashlib.sha256(stable_source.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _api_edges(
    demand_id: str,
    span_ids: list[str],
    slot_name: str,
) -> list[ConstructEdge]:
    return [
        ConstructEdge(
            from_id=f"span:{span_id}",
            to_id=demand_id,
            edge_type="derived_from",
            source_span_ids=[span_id],
            metadata={"slot": slot_name},
        )
        for span_id in span_ids
    ]


def _group_annotations(
    annotations: list[RouteAnnotation],
) -> dict[str, list[RouteAnnotation]]:
    grouped: dict[str, list[RouteAnnotation]] = defaultdict(list)
    for ann in annotations:
        grouped[_group_key(ann)].append(ann)
    return grouped


def _attach_adjacent_orphan_handlers(
    demands: list[
        ExceptionFlowDemand | APIDeclarationDemand | APICallDemand
    ],
    spans: list[SpanIR],
) -> list[
    ExceptionFlowDemand | APIDeclarationDemand | APICallDemand
]:
    """Attach a source-adjacent handler continuation to its condition demand."""

    source_order = {
        span.span_id: index
        for index, span in enumerate(spans)
    }
    exception_demands = [
        demand
        for demand in demands
        if isinstance(demand, ExceptionFlowDemand)
    ]
    removed_ids: set[str] = set()

    for orphan in exception_demands:
        if (
            orphan.pairing_status != "orphan_handler"
            or len(orphan.handler_span_ids) != 1
        ):
            continue
        handler_span_id = orphan.handler_span_ids[0]
        handler_position = source_order.get(handler_span_id)
        if handler_position is None:
            continue
        candidates = [
            demand
            for demand in exception_demands
            if demand.condition_span_ids
            and demand.source_section_id == orphan.source_section_id
            and max(
                (
                    source_order.get(span_id, -1)
                    for span_id in demand.source_span_ids
                ),
                default=-1,
            )
            == handler_position - 1
        ]
        if len(candidates) != 1:
            continue
        target = candidates[0]
        target.handler_span_ids.append(handler_span_id)
        target.source_span_ids.append(handler_span_id)
        target.reserved_span_ids.add(handler_span_id)
        target.slots["handler"].source_span_ids.append(handler_span_id)
        target.slots["handler"].semantic_roles.extend(
            orphan.slots["handler"].semantic_roles
        )
        target.slots["handler"].executable_values.extend(
            orphan.slots["handler"].executable_values
        )
        target.slots["handler"].status = "present"
        target.related_edges.extend(
            _slot_edges(
                target.demand_id,
                condition_span_ids=[],
                handler_span_ids=[handler_span_id],
            )
        )
        target.pairing_status = "condition_with_handler"
        target.metadata["adjacent_handler_continuation"] = handler_span_id
        removed_ids.add(orphan.demand_id)

    return [
        demand
        for demand in demands
        if not (
            isinstance(demand, ExceptionFlowDemand)
            and demand.demand_id in removed_ids
        )
    ]


def _group_key(ann: RouteAnnotation) -> str:
    metadata = ann.metadata or {}
    for key in (
        "construct_group_id",
        "construct_instance_id",
        "pair_key",
        "failure_item_index",
    ):
        if key in metadata and metadata[key] not in (None, ""):
            return f"{key}:{metadata[key]}"
    if ann.source_packet_id:
        return f"packet:{ann.source_packet_id}"
    if ann.source_section_id:
        return f"section:{ann.source_section_id}"
    return f"span:{ann.span_id}"


def _slot_from_annotations(
    slot_name: str,
    annotations: list[RouteAnnotation],
    *,
    status: str = "present",
) -> ConstructSlotDemand:
    if not annotations:
        return ConstructSlotDemand(slot_name=slot_name, status=status)  # type: ignore[arg-type]
    return ConstructSlotDemand(
        slot_name=slot_name,
        source_span_ids=[ann.span_id for ann in annotations],
        semantic_roles=[ann.semantic_role for ann in annotations if ann.semantic_role is not None],
        executable_values=[ann.executable for ann in annotations],
        source_section_id=annotations[0].source_section_id,
        source_packet_id=annotations[0].source_packet_id,
        status=status,  # type: ignore[arg-type]
    )


def _slot_edges(
    demand_id: str,
    *,
    condition_span_ids: list[str],
    handler_span_ids: list[str],
) -> list[ConstructEdge]:
    edges: list[ConstructEdge] = []
    for span_id in condition_span_ids:
        edges.append(
            ConstructEdge(
                from_id=f"span:{span_id}",
                to_id=demand_id,
                edge_type="derived_from",
                source_span_ids=[span_id],
                metadata={"slot": "condition"},
            )
        )
    for span_id in handler_span_ids:
        edges.append(
            ConstructEdge(
                from_id=f"span:{span_id}",
                to_id=demand_id,
                edge_type="derived_from",
                source_span_ids=[span_id],
                metadata={"slot": "handler"},
            )
        )
    return edges


def _pairing_source(
    condition: RouteAnnotation,
    handlers: list[RouteAnnotation],
) -> str:
    if not handlers:
        return "condition_only"
    cond_meta = condition.metadata or {}
    handler_meta = handlers[0].metadata or {}
    for key in (
        "construct_group_id",
        "construct_instance_id",
        "pair_key",
        "failure_item_index",
    ):
        if cond_meta.get(key) == handler_meta.get(key) and cond_meta.get(key) is not None:
            return f"metadata:{key}"
    if condition.source_packet_id == handlers[0].source_packet_id:
        return "source_packet_id"
    if condition.source_section_id == handlers[0].source_section_id:
        return "source_section_id"
    return "unpaired"


def _diagnostic(
    *,
    kind: str,
    message: str,
    span_ids: list[str],
    target_ref: str,
) -> CompileDiagnostic:
    digest = hashlib.sha1(
        "|".join([kind, target_ref, *sorted(span_ids)]).encode("utf-8")
    ).hexdigest()[:10]
    return CompileDiagnostic(
        diagnostic_id=f"diag_cp_{digest}",
        kind=kind,
        severity="warning",
        message=message,
        target_ref=target_ref,
        source_span_ids=list(span_ids),
        blocks_completion=True,
        blocks_rendering=False,
    )
