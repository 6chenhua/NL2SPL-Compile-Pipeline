"""Stage 4: FlowAssembler - Determine worker-local flow structure."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import (
    AlternativeFlow,
    DelegationCandidate,
    ExceptionFlow,
    FlowStructureIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerPlanIR, WorkerSpecIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


class FlowAssembler(
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR]
        | tuple[list[SpanIR], FieldRouteIR, WorkerPlanIR],
        FlowStructureIR | WorkerFlowPlanIR,
    ]
):
    """Determine execution-path flow structure.

    Legacy calls return one global FlowStructureIR. Worker-aware calls return
    one worker-scoped FlowStructureIR per WorkerSpecIR and do not emit
    delegation candidates.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage4_flow_assembler"

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

    def _parse_alternative_flows(self, result: dict[str, Any]) -> list[AlternativeFlow]:
        """Parse alternative flow objects from LLM JSON."""
        alternative_flows: list[AlternativeFlow] = []
        for flow_data in result.get("alternative_flows", []):
            try:
                alternative_flows.append(
                    AlternativeFlow(
                        flow_id=flow_data["flow_id"],
                        condition_text=flow_data["condition_text"],
                        spans=flow_data["spans"],
                    )
                )
            except KeyError as e:
                self.logger.warning("Missing field in alternative flow data: %s", e)
        return alternative_flows

    def _parse_exception_flows(self, result: dict[str, Any]) -> list[ExceptionFlow]:
        """Parse exception flow objects from LLM JSON."""
        exception_flows: list[ExceptionFlow] = []
        for flow_data in result.get("exception_flows", []):
            try:
                exception_flows.append(
                    ExceptionFlow(
                        flow_id=flow_data["flow_id"],
                        condition_text=flow_data["condition_text"],
                        spans=flow_data["spans"],
                    )
                )
            except KeyError as e:
                self.logger.warning("Missing field in exception flow data: %s", e)
        return exception_flows

    def _parse_delegation_candidates(
        self,
        result: dict[str, Any],
    ) -> list[DelegationCandidate]:
        """Parse legacy delegation candidates."""
        delegation_candidates: list[DelegationCandidate] = []
        for cand_data in result.get("delegation_candidates", []):
            try:
                delegation_candidates.append(
                    DelegationCandidate(
                        candidate_id=cand_data["candidate_id"],
                        spans=cand_data["spans"],
                        reason=cand_data["reason"],
                        suggested_type=cand_data["suggested_type"],
                        input_variables=cand_data.get("input_variables", []),
                        output_variables=cand_data.get("output_variables", []),
                    )
                )
            except KeyError as e:
                self.logger.warning(
                    "Missing field in delegation candidate data: %s",
                    e,
                )
        return delegation_candidates

    def _format_span_text(self, spans: list[SpanIR]) -> str:
        """Format spans as compact plain text for prompts."""
        if not spans:
            return "(none)"
        return "\n".join(f"{span.span_id}: {span.text}" for span in spans)

    def _format_worker_context(
        self,
        worker_plan: WorkerPlanIR | None,
        worker: WorkerSpecIR | None,
    ) -> str:
        """Return compact WorkerPlanIR context for the current worker."""
        if worker_plan is None or worker is None:
            return "(none)"

        relevant_handoffs = [
            handoff
            for handoff in worker_plan.handoffs
            if handoff.from_worker == worker.worker_id
            or handoff.to_worker == worker.worker_id
        ]
        context: dict[str, Any] = {
            "main_worker_id": worker_plan.main_worker_id,
            "current_worker": asdict(worker),
            "handoffs": [asdict(handoff) for handoff in relevant_handoffs],
            "unassigned_span_ids": worker_plan.unassigned_span_ids,
        }
        return json.dumps(context, ensure_ascii=False, indent=2)

    def _restrict_flow_to_span_ids(
        self,
        flow: FlowStructureIR,
        allowed_span_ids: set[str],
    ) -> FlowStructureIR:
        """Keep worker-scoped flows inside the WorkerSpecIR ownership boundary."""
        return FlowStructureIR(
            main_flow_spans=[
                span_id
                for span_id in flow.main_flow_spans
                if span_id in allowed_span_ids
            ],
            alternative_flows=[
                AlternativeFlow(
                    flow_id=alt_flow.flow_id,
                    condition_text=alt_flow.condition_text,
                    spans=[
                        span_id
                        for span_id in alt_flow.spans
                        if span_id in allowed_span_ids
                    ],
                )
                for alt_flow in flow.alternative_flows
            ],
            exception_flows=[
                ExceptionFlow(
                    flow_id=exc_flow.flow_id,
                    condition_text=exc_flow.condition_text,
                    spans=[
                        span_id
                        for span_id in exc_flow.spans
                        if span_id in allowed_span_ids
                    ],
                )
                for exc_flow in flow.exception_flows
            ],
            delegation_candidates=[],
        )
