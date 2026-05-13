"""Stage 4: FlowAssembler - Main class."""

from __future__ import annotations

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerPlanIR
from nl2spl.pipeline.stages.base import PipelineStage
from nl2spl.pipeline.stages.stage4_flow_assembler.executor import ExecutorMixin
from nl2spl.pipeline.stages.stage4_flow_assembler.flow_parser import FlowParserMixin
from nl2spl.pipeline.stages.stage4_flow_assembler.prompt_builder import PromptBuilderMixin
from nl2spl.pipeline.stages.stage4_flow_assembler.span_filter import SpanFilterMixin


class FlowAssembler(
    ExecutorMixin,
    FlowParserMixin,
    PromptBuilderMixin,
    SpanFilterMixin,
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR]
        | tuple[list[SpanIR], FieldRouteIR, WorkerPlanIR],
        FlowStructureIR | WorkerFlowPlanIR,
    ],
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
