"""Build validated control-region plans from source-backed action evidence."""

from __future__ import annotations

import re

from nl2spl.compiler.construct_plan import ConstructPlan
from nl2spl.ir.action_placement_ir import ExecutableActionPlacementPlan
from nl2spl.ir.control_region_ir import ControlRegion, ControlRegionPlan
from nl2spl.ir.flow_structure_ir import AlternativeFlow
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerPlanIR


def build_control_region_plan(
    spans: list[SpanIR],
    worker_plan: WorkerPlanIR,
    worker_flow_plan: WorkerFlowPlanIR,
    action_plan: ExecutableActionPlacementPlan,
    construct_plan: ConstructPlan | None = None,
) -> ControlRegionPlan:
    """Build validated local/top-level control regions.

    LLM flow classification is treated as input evidence only; validated
    source-backed guarded spans and accepted action spans define the plan.
    """
    builder = ControlRegionPlanBuilder(
        spans,
        worker_plan,
        worker_flow_plan,
        action_plan,
        construct_plan,
    )
    return ControlRegionPlanValidator(action_plan, worker_plan).validate(
        builder.build()
    )


class ControlRegionPlanBuilder:
    """Collect control-region evidence without making Stage 5 authority final."""

    def __init__(
        self,
        spans: list[SpanIR],
        worker_plan: WorkerPlanIR,
        worker_flow_plan: WorkerFlowPlanIR,
        action_plan: ExecutableActionPlacementPlan,
        construct_plan: ConstructPlan | None = None,
    ) -> None:
        self.spans = _dedupe_spans_by_id(spans)
        self.worker_plan = worker_plan
        self.worker_flow_plan = worker_flow_plan
        self.action_plan = action_plan
        self.accepted_span_ids = action_plan.accepted_span_ids()
        self.span_by_id = {span.span_id: span for span in self.spans}
        self.worker_by_span = _worker_by_span(worker_plan)
        self.api_action_span_ids = _api_action_span_ids(action_plan)
        self.alternative_span_ids = _alternative_span_ids(worker_flow_plan)
        self.exception_handler_span_ids = {
            span_id
            for demand in (
                construct_plan.exception_flow_demands()
                if construct_plan is not None
                else ()
            )
            for span_id in demand.handler_span_ids
        }

    def build(self) -> ControlRegionPlan:
        regions: list[ControlRegion] = []
        diagnostics: list[str] = []

        for span_index, span in enumerate(self.spans):
            if span.segmentation_kind != "guarded_action":
                continue
            if span.span_id in self.exception_handler_span_ids:
                continue
            worker_id = self.worker_by_span.get(
                span.span_id,
                self.worker_plan.main_worker_id,
            )
            if span.span_id not in self.accepted_span_ids:
                diagnostics.append(f"guarded_action_not_executable:{span.span_id}")
                continue
            guard = span.guard_text_exact or _strip_guard_intro(span.text)
            if not guard:
                diagnostics.append(f"guarded_action_missing_guard:{span.span_id}")
                continue
            condition_source_span_ids = (span.span_id,)
            relation = "direct"
            source = "stage1_guarded_action"
            confidence = "high"
            reason = None
            if _is_incomplete_guard(guard):
                resolved = _resolve_negative_anaphoric_guard(self.spans, span_index)
                if resolved is None:
                    diagnostics.append(
                        f"guarded_action_incomplete_guard:{span.span_id}:{guard}"
                    )
                    continue
                guard, condition_source_span_ids = resolved
                relation = "derived"
                source = "stage1_cross_packet_guard_repair"
                confidence = "medium"
                reason = "negative_anaphora_resolved_from_prior_verification"
            if is_terminal_placement_guard(guard):
                diagnostics.append(f"guarded_action_terminal_placement:{span.span_id}")
                continue
            if not _has_guard_led_control_shape(span):
                diagnostics.append(
                    f"guarded_action_not_guard_led:{span.span_id}"
                )
                continue
            if (
                span.span_id in self.alternative_span_ids
                and span.span_id not in self.api_action_span_ids
            ):
                regions.append(
                    ControlRegion(
                        region_id=f"cr_top_alt_{span.span_id}",
                        region_kind="top_level_alternative",
                        condition_text=guard,
                        action_span_ids=(span.span_id,),
                        condition_source_span_ids=condition_source_span_ids,
                        worker_id=worker_id,
                        source=source,
                        relation=relation,
                        classification_source="stage4_llm_classified",
                        confidence=confidence,
                        reason=reason,
                        notes=("stage4_alternative_flow_preserved",),
                    )
                )
                continue
            regions.append(
                ControlRegion(
                    region_id=f"cr_local_if_{span.span_id}",
                    region_kind="local_if",
                    condition_text=guard,
                    action_span_ids=(span.span_id,),
                    condition_source_span_ids=condition_source_span_ids,
                    worker_id=worker_id,
                    source=source,
                    relation=relation,
                    classification_source=source,
                    confidence=confidence,
                    reason=reason,
                )
            )

        regions.extend(
            _derive_adjacent_clarification_regions(
                self.spans,
                self.accepted_span_ids,
                self.worker_by_span,
                self.worker_plan.main_worker_id,
            )
        )
        regions.extend(
            _derive_cross_packet_guard_regions(
                self.spans,
                self.accepted_span_ids,
                self.worker_by_span,
                self.worker_plan.main_worker_id,
                existing_action_span_ids={
                    span_id
                    for region in regions
                    if region.region_kind == "local_if"
                    for span_id in region.action_span_ids
                },
                excluded_action_span_ids=self.exception_handler_span_ids,
            )
        )

        local_region_span_ids = {
            span_id
            for region in regions
            if region.region_kind == "local_if"
            for span_id in region.action_span_ids
        }
        planned_top_alt_span_ids = {
            span_id
            for region in regions
            if region.region_kind == "top_level_alternative"
            for span_id in region.action_span_ids
        }

        for worker_id, flow in self.worker_flow_plan.worker_flows.items():
            for alt in flow.alternative_flows:
                if set(alt.spans).issubset(
                    local_region_span_ids | planned_top_alt_span_ids
                ):
                    continue
                if alt.spans:
                    regions.append(
                        ControlRegion(
                            region_id=f"cr_top_alt_{alt.flow_id}",
                            region_kind="top_level_alternative",
                            condition_text=alt.condition_text,
                            action_span_ids=tuple(alt.spans),
                            condition_source_span_ids=tuple(
                                _condition_source_spans(alt, self.span_by_id)
                            ),
                            worker_id=worker_id,
                            source="stage4_llm_classified",
                            relation="direct",
                            classification_source="stage4_llm_classified",
                            confidence="medium",
                        )
                    )

        return ControlRegionPlan(regions=tuple(regions), diagnostics=tuple(diagnostics))


class ControlRegionPlanValidator:
    """Validate that region authority is typed and placement-backed."""

    def __init__(
        self,
        action_plan: ExecutableActionPlacementPlan,
        worker_plan: WorkerPlanIR,
    ) -> None:
        self.accepted_span_ids = action_plan.accepted_span_ids()
        self.worker_by_span = _worker_by_span(worker_plan)

    def validate(self, plan: ControlRegionPlan) -> ControlRegionPlan:
        validated: list[ControlRegion] = []
        diagnostics = list(plan.diagnostics)
        for region in plan.regions:
            reason = self._rejection_reason(region)
            if reason is None:
                validated.append(region)
                continue
            diagnostics.append(f"control_region_unresolved:{region.region_id}:{reason}")
            validated.append(
                ControlRegion(
                    region_id=region.region_id,
                    region_kind="unresolved",
                    condition_text=region.condition_text,
                    action_span_ids=region.action_span_ids,
                    condition_source_span_ids=region.condition_source_span_ids,
                    worker_id=region.worker_id,
                    source=region.source,
                    status="rejected",
                    reason=reason,
                    relation="ambiguous",
                    classification_source=region.classification_source,
                    confidence="low",
                    notes=region.notes,
                )
            )
        return ControlRegionPlan(regions=tuple(validated), diagnostics=tuple(diagnostics))

    def _rejection_reason(self, region: ControlRegion) -> str | None:
        if region.relation == "direct" and not region.condition_source_span_ids:
            return "direct_relation_without_guard_evidence"
        if region.relation == "derived" and not region.condition_source_span_ids:
            return "derived_relation_without_condition_source"
        if any(span_id not in self.accepted_span_ids for span_id in region.action_span_ids):
            return "action_span_outside_accepted_executable_set"
        for span_id in region.action_span_ids:
            owner = self.worker_by_span.get(span_id)
            if owner is not None and owner != region.worker_id:
                return "cross_worker_condition_action_region"
        return None


def _api_action_span_ids(action_plan: ExecutableActionPlacementPlan) -> set[str]:
    return {
        span_id
        for candidate in action_plan.candidates
        if candidate.status == "accepted" and candidate.command_type_hint == "CALL_API"
        for span_id in candidate.source_span_ids
    }


def _alternative_span_ids(worker_flow_plan: WorkerFlowPlanIR) -> set[str]:
    return {
        span_id
        for flow in worker_flow_plan.worker_flows.values()
        for alt in flow.alternative_flows
        for span_id in alt.spans
    }


def _derive_adjacent_clarification_regions(
    spans: list[SpanIR],
    accepted_span_ids: set[str],
    worker_by_span: dict[str, str],
    main_worker_id: str,
) -> list[ControlRegion]:
    regions: list[ControlRegion] = []
    for index, span in enumerate(spans):
        if span.span_id not in accepted_span_ids:
            continue
        action_text = span.text.lower()
        if "clarifying question" not in action_text and "clarifying questions" not in action_text:
            continue
        previous = spans[index - 1] if index > 0 else None
        if previous is None:
            continue
        if previous.source_packet_id != span.source_packet_id:
            continue
        previous_text = previous.text.lower()
        if "required fields" not in previous_text or "missing" not in previous_text:
            continue
        regions.append(
            ControlRegion(
                region_id=f"cr_local_if_{span.span_id}",
                region_kind="local_if",
                condition_text="required fields are still missing",
                action_span_ids=(span.span_id,),
                condition_source_span_ids=(previous.span_id, span.span_id),
                worker_id=worker_by_span.get(span.span_id, main_worker_id),
                source="route_derived",
                relation="derived",
                classification_source="route_derived",
                confidence="medium",
                reason="source_adjacent_clarification_guard",
                notes=("derived_from_adjacent_source_packet",),
            )
        )
    return regions


def _derive_cross_packet_guard_regions(
    spans: list[SpanIR],
    accepted_span_ids: set[str],
    worker_by_span: dict[str, str],
    main_worker_id: str,
    *,
    existing_action_span_ids: set[str],
    excluded_action_span_ids: set[str] | None = None,
) -> list[ControlRegion]:
    """Repair source-adjacent guard tails split from executable actions.

    The guard phrase is only condition evidence. The action span must already
    be admitted by ExecutableActionPlacementPlan, so raw keywords never create
    an executable action by themselves.
    """

    regions: list[ControlRegion] = []
    for index, condition_span in enumerate(spans[:-1]):
        action_span = spans[index + 1]
        if action_span.span_id in (excluded_action_span_ids or set()):
            continue
        if condition_span.segmentation_kind == "guarded_action":
            continue
        if action_span.span_id in existing_action_span_ids:
            continue
        if action_span.span_id not in accepted_span_ids:
            continue
        if condition_span.source_section_id != action_span.source_section_id:
            continue
        guard = _trailing_guard_text(condition_span.text)
        if not guard:
            continue
        condition_source_span_ids = (condition_span.span_id,)
        reason = "guard_tail_precedes_accepted_action"
        if _is_incomplete_guard(guard):
            resolved = _resolve_negative_anaphoric_guard(spans, index)
            if resolved is None:
                continue
            guard, condition_source_span_ids = resolved
            reason = "negative_anaphora_resolved_from_prior_verification"
        regions.append(
            ControlRegion(
                region_id=f"cr_local_if_{condition_span.span_id}_{action_span.span_id}",
                region_kind="local_if",
                condition_text=guard,
                action_span_ids=(action_span.span_id,),
                condition_source_span_ids=condition_source_span_ids,
                worker_id=worker_by_span.get(action_span.span_id, main_worker_id),
                source="stage1_cross_packet_guard_repair",
                relation="derived",
                classification_source="deterministic_evidence",
                confidence="medium",
                reason=reason,
            )
        )
        existing_action_span_ids.add(action_span.span_id)
    return regions


def _worker_by_span(worker_plan: WorkerPlanIR) -> dict[str, str]:
    return {
        span_id: worker.worker_id
        for worker in worker_plan.workers
        for span_id in worker.owned_span_ids
    }


def _dedupe_spans_by_id(spans: list[SpanIR]) -> list[SpanIR]:
    selected: dict[str, SpanIR] = {}
    order: list[str] = []
    for span in spans:
        if span.span_id not in selected:
            selected[span.span_id] = span
            order.append(span.span_id)
            continue
        current = selected[span.span_id]
        if _span_metadata_score(span) > _span_metadata_score(current):
            selected[span.span_id] = span
    return [selected[span_id] for span_id in order]


def _span_metadata_score(span: SpanIR) -> int:
    return sum(
        1
        for value in (
            span.segmentation_kind,
            span.guard_text_exact,
            span.action_text_exact,
        )
        if value
    )


def is_terminal_placement_guard(text: str) -> bool:
    normalized = " ".join(text.lower().strip(" ,.;:").split())
    return normalized in {
        "at the end",
        "the end",
        "end",
        "at end",
        "finally",
    }


def _condition_source_spans(
    alt: AlternativeFlow,
    span_by_id: dict[str, SpanIR],
) -> list[str]:
    spans: list[str] = []
    for span_id in alt.spans:
        if span_id in span_by_id:
            spans.append(span_id)
    return spans or list(alt.spans)


def _strip_guard_intro(text: str) -> str:
    stripped = " ".join(text.split())
    lowered = stripped.lower()
    for prefix in ("if ", "when ", "unless "):
        if lowered.startswith(prefix):
            stripped = stripped[len(prefix):]
            break
    if "," in stripped:
        return stripped.split(",", 1)[0].strip()
    return stripped


def _trailing_guard_text(text: str) -> str | None:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return None
    fragments = [
        fragment.strip()
        for fragment in re_split_sentences(normalized)
        if fragment.strip()
    ]
    if not fragments:
        fragments = [normalized]
    candidate = fragments[-1].strip(" .;")
    lowered = candidate.lower()
    for prefix in ("if ", "when ", "unless "):
        if lowered.startswith(prefix):
            guard = candidate[len(prefix):].strip(" ,;.")
            return guard or None
    return None


def _is_incomplete_guard(text: str) -> bool:
    normalized = " ".join(text.lower().strip(" ,.;:").split())
    return normalized in {
        "not",
        "otherwise",
        "if not",
        "when not",
        "unless so",
    }


def _resolve_negative_anaphoric_guard(
    spans: list[SpanIR],
    condition_index: int,
) -> tuple[str, tuple[str, ...]] | None:
    """Resolve a narrow ``if not`` reference from prior verification evidence."""

    condition_span = spans[condition_index]
    for prior in reversed(spans[max(0, condition_index - 8) : condition_index]):
        if prior.source_section_id != condition_span.source_section_id:
            break
        prior_text = " ".join(prior.text.split())
        match = re.search(
            r"(?:generate|create|produce)\s+(?:a\s+|the\s+)?"
            r"(?P<subject>.+?)\s+and\s+verify\s+(?:whether|if)\s+it\s+meets\s+"
            r"(?P<criteria>.+?)(?:[.;]|$)",
            prior_text,
            flags=re.IGNORECASE,
        )
        if match is None:
            continue
        subject = match.group("subject").strip(" ,.;")
        criteria = match.group("criteria").strip(" ,.;")
        if not subject or not criteria:
            continue
        return (
            f"{subject} does not meet {criteria}",
            (prior.span_id, condition_span.span_id),
        )
    return None


def _has_guard_led_control_shape(span: SpanIR) -> bool:
    """Reject embedded ``check whether/if`` clauses as control regions."""

    text = " ".join(span.text.lower().split()).lstrip()
    if text.startswith(("if ", "when ", "unless ", "where ")):
        return True
    if ":" not in text:
        return False
    _label, suffix = text.split(":", 1)
    return suffix.lstrip().startswith(("if ", "when ", "unless ", "where "))


def re_split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char not in ".!?":
            continue
        if index + 1 < len(text) and not text[index + 1].isspace():
            continue
        parts.append(text[start : index + 1])
        start = index + 1
        while start < len(text) and text[start].isspace():
            start += 1
    if start < len(text):
        parts.append(text[start:])
    return parts
