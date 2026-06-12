"""Stage 4: FlowAssembler - ExecutorMixin (execute, _execute_worker_aware, _assemble_flow)."""

from __future__ import annotations

import re as _re
from dataclasses import asdict

from nl2spl.compiler.construct_plan import ConstructPlan
from nl2spl.compiler.construct_plan.exception_materializer import (
    materialize_exception_flows_from_construct_plan,
    materialize_worker_exception_flows_from_construct_plan,
)
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerPlanIR, WorkerSpecIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.route_exception_materializer import (
    materialize_route_exception_flows,
    _is_empty_condition,
)


class ExecutorMixin:
    """Mixin containing execution logic for FlowAssembler."""

    def execute(
        self,
        input_data: tuple[list[SpanIR], FieldRouteIR]
        | tuple[list[SpanIR], FieldRouteIR, WorkerPlanIR]
        | tuple[list[SpanIR], FieldRouteIR, WorkerPlanIR, ConstructPlan],
    ) -> FlowStructureIR | WorkerFlowPlanIR:
        """Execute flow assembly."""
        construct_plan = input_data[3] if len(input_data) == 4 else None
        if len(input_data) in (3, 4):
            spans, routes, worker_plan = input_data[:3]
            return self._execute_worker_aware(
                spans, routes, worker_plan, construct_plan,
            )

        spans, routes = input_data
        behavior_span_ids = (
            set(routes.get_executable_behavior_span_ids())
            if routes.annotations
            else set(routes.behavior)
        )
        # Phase 3 defensive diagnostic: routes.behavior non-empty but zero
        # executable behavior span IDs from annotations.
        if routes.annotations and routes.behavior and not behavior_span_ids:
            self.logger.warning(
                "Defensive: routes.behavior has %d span(s) but zero executable "
                "behavior span IDs from annotations. Behavior spans exist in "
                "the legacy list but none have executable annotations. This "
                "may indicate upstream annotation contract mismatches (e.g., "
                "process_step with invalid construct_target rejected by "
                "Stage 2 validator, or Stage 3 split children missing "
                "annotations).",
                len(routes.behavior),
            )
        if construct_plan is not None:
            behavior_span_ids -= construct_plan.reserved_without_dual_role()
        behavior_spans = [s for s in spans if s.span_id in behavior_span_ids]
        self.logger.info(
            "Starting flow assembly for %d behavior spans (out of %d total)",
            len(behavior_spans),
            len(spans),
        )

        flow_structure = self._assemble_flow(
            spans=spans,
            behavior_spans=behavior_spans,
            include_delegation_candidates=True,
        )

        # ConstructPlan is the construct-level authority.  RouteAnnotation
        # materialization remains as compatibility fallback when no plan is
        # available.
        if construct_plan is not None:
            flow_structure = materialize_exception_flows_from_construct_plan(
                flow_structure, construct_plan, spans,
            )
        else:
            flow_structure = materialize_route_exception_flows(
                flow_structure, routes, spans,
            )

        # D2 guard: remove LLM-generated exception flows whose spans are
        # handler actions (NOT conditions).  Route annotations are the
        # authority on which span is a condition vs handler.
        if routes.annotations:
            flow_structure = _filter_non_condition_exception_flows(
                flow_structure, routes, spans,
            )

        self.logger.info(
            "Flow assembly complete: %d main flow spans, %d alternative flows, "
            "%d exception flows, %d delegation candidates",
            len(flow_structure.main_flow_spans),
            len(flow_structure.alternative_flows),
            len(flow_structure.exception_flows),
            len(flow_structure.delegation_candidates),
        )

        self.save_checkpoint(asdict(flow_structure))
        return flow_structure

    def _execute_worker_aware(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_plan: WorkerPlanIR,
        construct_plan: ConstructPlan | None = None,
    ) -> WorkerFlowPlanIR:
        """Assemble one FlowStructureIR per worker in a WorkerPlanIR."""
        behavior_span_ids = (
            set(routes.get_executable_behavior_span_ids())
            if routes.annotations
            else set(routes.behavior)
        )
        # Phase 3 defensive diagnostic: behavior list non-empty but no
        # executable annotations — worker flows will be empty.
        if routes.annotations and routes.behavior and not behavior_span_ids:
            self.logger.warning(
                "Defensive: routes.behavior has %d span(s) but zero executable "
                "behavior span IDs from annotations. Worker-level flow "
                "assembly may produce empty main flow for all workers.",
                len(routes.behavior),
            )
        if construct_plan is not None:
            behavior_span_ids -= construct_plan.reserved_without_dual_role()
        span_by_id = {span.span_id: span for span in spans}
        worker_flows: dict[str, FlowStructureIR] = {}
        warnings = list(worker_plan.warnings)

        self.logger.info(
            "Starting worker-aware flow assembly for %d workers",
            len(worker_plan.workers),
        )

        for worker in worker_plan.workers:
            owned_behavior_ids = [
                span_id
                for span_id in worker.owned_span_ids
                if span_id in behavior_span_ids and span_id in span_by_id
            ]
            worker_behavior_spans = [
                span_by_id[span_id] for span_id in owned_behavior_ids
            ]
            worker_source_spans = [
                span_by_id[span_id]
                for span_id in worker.owned_span_ids
                if span_id in span_by_id
            ]

            if not worker_behavior_spans:
                warnings.append(
                    f"Worker {worker.worker_id} has no owned behavior spans for Stage 4."
                )
                # Amplify warning when root cause is likely annotation-related
                if routes.annotations and routes.behavior and not behavior_span_ids:
                    warnings.append(
                        f"Worker {worker.worker_id}: routes.behavior is non-empty "
                        f"({len(routes.behavior)} span(s)) but no executable "
                        f"behavior annotations exist. Check Stage 2 annotation "
                        f"contract validation and Stage 3 child annotation "
                        f"derivation."
                    )

            flow = self._assemble_flow(
                spans=worker_source_spans or worker_behavior_spans,
                behavior_spans=worker_behavior_spans,
                worker_plan=worker_plan,
                worker=worker,
                include_delegation_candidates=False,
            )
            flow = self._restrict_flow_to_span_ids(
                flow,
                set(owned_behavior_ids),
            )
            worker_flows[worker.worker_id] = flow

        # D2 guard: filter handler-sourced LLM exception flows per worker
        if routes.annotations:
            for wid in list(worker_flows):
                worker_flows[wid] = _filter_non_condition_exception_flows(
                    worker_flows[wid], routes, spans,
                )

        # ConstructPlan-driven exception flow materialization.  The older
        # route-driven worker materializer remains as compatibility fallback.
        if construct_plan is not None:
            materialize_worker_exception_flows_from_construct_plan(
                worker_flows, construct_plan, spans, worker_plan, warnings,
            )
        else:
            self._materialize_worker_exceptions(
                worker_flows, routes, spans, span_by_id,
                worker_plan, warnings,
            )

        plan = WorkerFlowPlanIR(worker_flows=worker_flows, warnings=warnings)
        self.save_checkpoint(asdict(plan))
        return plan

    def _assemble_flow(
        self,
        spans: list[SpanIR],
        behavior_spans: list[SpanIR],
        worker_plan: WorkerPlanIR | None = None,
        worker: WorkerSpecIR | None = None,
        include_delegation_candidates: bool = True,
    ) -> FlowStructureIR:
        """Call the LLM and parse one FlowStructureIR."""
        behavior_text = self._format_span_text(behavior_spans)
        source_text = self._format_span_text(spans)
        system_prompt = load_prompt("stage4")

        if worker is None:
            user_prompt = f"""Assemble flow structure from behavior spans.

Behavior spans to classify:
---
{behavior_text}
---

Full source text context:
---
{source_text}
---

Use span_id values in output span lists; do not copy span text into span lists.
Return JSON only."""
        else:
            user_prompt = f"""Assemble flow structure for one worker only.

WorkerPlanIR context:
---
{self._format_worker_context(worker_plan, worker)}
---

Worker-local behavior spans to classify:
---
{behavior_text}
---

Worker-local source text context:
---
{source_text}
---

Use only span_id values owned by this worker.
Return flow JSON only: main_flow_spans, alternative_flows, exception_flows.
Do not decide worker boundaries and do not output delegation_candidates.
Return JSON only."""

        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise StageError(
                message=f"LLM call failed in {self.name}: {e}",
                stage=self.name,
            ) from e

        return FlowStructureIR(
            main_flow_spans=result.get("main_flow_spans", []),
            alternative_flows=self._parse_alternative_flows(result),
            exception_flows=self._parse_exception_flows(result),
            delegation_candidates=self._parse_delegation_candidates(result)
            if include_delegation_candidates
            else [],
        )

    @staticmethod
    def _materialize_worker_exceptions(
        worker_flows: dict[str, FlowStructureIR],
        routes: FieldRouteIR,
        spans: list[SpanIR],
        span_by_id: dict[str, SpanIR],
        worker_plan: WorkerPlanIR,
        warnings: list[str],
    ) -> None:
        """D3: ownership-driven exception flow materialization per worker.

        Each failure condition annotation is assigned to exactly one worker
        based on ownership.  Unowned or multi-owned spans fall back to the
        main worker with a warning.
        """
        candidates = routes.get_construct_slot_candidates(
            "EXCEPTION_FLOW", "condition",
        )
        failure_anns = [
            a for a in candidates
            if a.semantic_role in ("failure_mode", "failure_condition") and a.executable is False
        ]
        if not failure_anns:
            return

        # Build span_id → list of owning worker_ids
        owners_by_span: dict[str, list[str]] = {}
        for w in worker_plan.workers:
            for sid in w.owned_span_ids:
                owners_by_span.setdefault(sid, []).append(w.worker_id)

        main_id = worker_plan.main_worker_id
        from nl2spl.ir.flow_structure_ir import ExceptionFlow

        for ann in failure_anns:
            sid = ann.span_id
            span = span_by_id.get(sid)
            if span is None:
                continue
            
            # 跳过 placeholder spans
            if span.is_placeholder:
                continue
            
            owners = owners_by_span.get(sid, [])
            if len(owners) == 1:
                target_worker = owners[0]
            elif len(owners) == 0:
                target_worker = main_id
                warnings.append(
                    f"D3: failure condition span '{sid}' ({span.text[:60]}) "
                    f"is not owned by any worker; attached to main worker "
                    f"'{main_id}'."
                )
            else:
                target_worker = main_id
                warnings.append(
                    f"D3: failure condition span '{sid}' ({span.text[:60]}) "
                    f"is owned by multiple workers {owners}; "
                    f"attached to main worker '{main_id}'."
                )

            flow = worker_flows.get(target_worker)
            if flow is None:
                continue
            # Dedupe by normalized condition text
            norm = _re.sub(r"[^\w\s]", "", span.text.strip().lower())
            existing = {
                _re.sub(r"[^\w\s]", "", exc.condition_text.strip().lower())
                for exc in flow.exception_flows
            }
            if norm in existing:
                continue
            idx = len(flow.exception_flows)
            flow.exception_flows.append(
                ExceptionFlow(
                    flow_id=f"exc_adapter_{idx:02d}",
                    condition_text=span.text,
                    spans=[sid],
                )
            )


def _filter_non_condition_exception_flows(
    flow: FlowStructureIR,
    routes: Any,
    spans: list[SpanIR],
) -> FlowStructureIR:
    """Keep only exception flows that are backed by a condition annotation.

    Route annotations are authoritative on which span is an
    ``EXCEPTION_FLOW.condition``.  An LLM-generated exception flow is
    retained only if it references at least one span annotated as
    ``failure_mode / EXCEPTION_FLOW / condition / executable=False``.

    When annotations exist but no condition span is declared, ALL
    LLM exception flows are removed (legacy path preserved when
    annotations are absent).

    Retained flows are sanitised so their ``spans`` list contains only
    condition-backed span ids — handler, process, or un-annotated spans
    are stripped to avoid contaminating provenance downstream.
    """
    condition_span_ids: set[str] = {
        a.span_id
        for a in routes.get_construct_slot_candidates(
            "EXCEPTION_FLOW", "condition",
        )
        if a.semantic_role in ("failure_mode", "failure_condition") and a.executable is False
    }

    span_by_id = {s.span_id: s for s in spans}
    existing_norms: set[str] = set()

    changed = False

    # First pass: keep route-derived flows and seed dedup set
    sanitised: list[Any] = []
    for exc in flow.exception_flows:
        if exc.flow_id.startswith("exc_adapter_"):
            sanitised.append(exc)
            existing_norms.add(
                _re.sub(r"[^\w\s]", "", exc.condition_text.strip().lower())
            )

    # Second pass: sanitize LLM flows, skip if already covered
    idx = len(flow.exception_flows)
    for exc in flow.exception_flows:
        if exc.flow_id.startswith("exc_adapter_"):
            continue
        condition_spans = [s for s in exc.spans if s in condition_span_ids]
        if not condition_spans:
            changed = True
            continue
        cond_span = span_by_id.get(condition_spans[0])
        condition_text = cond_span.text if cond_span else exc.condition_text
        
        # 检查是否为空标记（文本级别检查）
        if _is_empty_condition(condition_text):
            changed = True
            continue
        
        # 检查是否为 placeholder span
        if cond_span and cond_span.is_placeholder:
            changed = True
            continue
        
        norm = _re.sub(r"[^\w\s]", "", condition_text.strip().lower())
        if norm in existing_norms:
            changed = True
            continue
        existing_norms.add(norm)
        sanitised.append(
            ExceptionFlow(
                flow_id=f"exc_adapter_{idx:02d}",
                condition_text=condition_text,
                spans=condition_spans,
            )
        )
        changed = True
        idx += 1

    if not changed:
        return flow

    return FlowStructureIR(
        main_flow_spans=list(flow.main_flow_spans),
        alternative_flows=list(flow.alternative_flows),
        exception_flows=sanitised,
        delegation_candidates=list(flow.delegation_candidates),
    )
