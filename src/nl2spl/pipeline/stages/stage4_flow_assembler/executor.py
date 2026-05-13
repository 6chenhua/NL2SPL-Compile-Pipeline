"""Stage 4: FlowAssembler - ExecutorMixin (execute, _execute_worker_aware, _assemble_flow)."""

from __future__ import annotations

from dataclasses import asdict

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerPlanIR, WorkerSpecIR
from nl2spl.llm.prompts import load_prompt


class ExecutorMixin:
    """Mixin containing execution logic for FlowAssembler."""

    def execute(
        self,
        input_data: tuple[list[SpanIR], FieldRouteIR]
        | tuple[list[SpanIR], FieldRouteIR, WorkerPlanIR],
    ) -> FlowStructureIR | WorkerFlowPlanIR:
        """Execute flow assembly."""
        if len(input_data) == 3:
            spans, routes, worker_plan = input_data
            return self._execute_worker_aware(spans, routes, worker_plan)

        spans, routes = input_data
        behavior_spans = [s for s in spans if s.span_id in routes.behavior]
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
    ) -> WorkerFlowPlanIR:
        """Assemble one FlowStructureIR per worker in a WorkerPlanIR."""
        behavior_span_ids = set(routes.behavior)
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

            flow = self._assemble_flow(
                spans=worker_source_spans or worker_behavior_spans,
                behavior_spans=worker_behavior_spans,
                worker_plan=worker_plan,
                worker=worker,
                include_delegation_candidates=False,
            )
            worker_flows[worker.worker_id] = self._restrict_flow_to_span_ids(
                flow,
                set(owned_behavior_ids),
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
