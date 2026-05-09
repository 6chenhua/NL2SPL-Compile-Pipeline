"""Stage 4: FlowAssembler - Determine flow structure and delegation candidates."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import (
    AlternativeFlow,
    DelegationCandidate,
    ExceptionFlow,
    FlowStructureIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


class FlowAssembler(
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR],
        FlowStructureIR,
    ]
):
    """Determine flow structure and identify delegation candidates.

    This stage takes behavior spans and field routes, then determines
    which spans belong to the main flow, alternative flows, or exception
    flows, and identifies delegation candidates.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage4_flow_assembler"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR]
    ) -> FlowStructureIR:
        """Execute flow assembly.

        Args:
            input_data: Tuple of (spans, routes)

        Returns:
            FlowStructureIR with flow structure and delegation candidates

        Raises:
            StageError: If flow assembly fails
        """
        spans, routes = input_data

        # 1. Filter behavior spans
        behavior_spans = [s for s in spans if s.span_id in routes.behavior]
        self.logger.info(
            "Starting flow assembly for %d behavior spans (out of %d total)",
            len(behavior_spans),
            len(spans),
        )

        # 2. Build prompts
        behavior_json = json.dumps(
            [asdict(s) for s in behavior_spans], ensure_ascii=False, indent=2
        )
        all_json = json.dumps(
            [asdict(s) for s in spans], ensure_ascii=False, indent=2
        )

        system_prompt = load_prompt("stage4")
        user_prompt = f"""请分析以下 span 的流程结构：

behavior spans（只有 behavior 字段的 span 需要判断 Flow）：
---
{behavior_json}
---

所有 spans（用于上下文理解）：
---
{all_json}
---

输出 JSON："""

        # 3. Call LLM
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

        # 4. Parse result
        main_flow_spans = result.get("main_flow_spans", [])

        alternative_flows: list[AlternativeFlow] = []
        for flow_data in result.get("alternative_flows", []):
            try:
                flow = AlternativeFlow(
                    flow_id=flow_data["flow_id"],
                    condition_text=flow_data["condition_text"],
                    spans=flow_data["spans"],
                )
                alternative_flows.append(flow)
            except KeyError as e:
                self.logger.warning("Missing field in alternative flow data: %s", e)
                continue

        exception_flows: list[ExceptionFlow] = []
        for exc_flow_data in result.get("exception_flows", []):
            try:
                exc_flow = ExceptionFlow(
                    flow_id=exc_flow_data["flow_id"],
                    condition_text=exc_flow_data["condition_text"],
                    spans=exc_flow_data["spans"],
                )
                exception_flows.append(exc_flow)
            except KeyError as e:
                self.logger.warning("Missing field in exception flow data: %s", e)
                continue

        delegation_candidates: list[DelegationCandidate] = []
        for cand_data in result.get("delegation_candidates", []):
            try:
                candidate = DelegationCandidate(
                    candidate_id=cand_data["candidate_id"],
                    spans=cand_data["spans"],
                    reason=cand_data["reason"],
                    suggested_type=cand_data["suggested_type"],
                    input_variables=cand_data.get("input_variables", []),
                    output_variables=cand_data.get("output_variables", []),
                )
                delegation_candidates.append(candidate)
            except KeyError as e:
                self.logger.warning(
                    "Missing field in delegation candidate data: %s", e
                )
                continue

        flow_structure = FlowStructureIR(
            main_flow_spans=main_flow_spans,
            alternative_flows=alternative_flows,
            exception_flows=exception_flows,
            delegation_candidates=delegation_candidates,
        )

        self.logger.info(
            "Flow assembly complete: %d main flow spans, %d alternative flows, "
            "%d exception flows, %d delegation candidates",
            len(main_flow_spans),
            len(alternative_flows),
            len(exception_flows),
            len(delegation_candidates),
        )

        # 5. Save checkpoint
        self.save_checkpoint(asdict(flow_structure))

        return flow_structure
