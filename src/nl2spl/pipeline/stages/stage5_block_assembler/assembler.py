"""Stage 5: BlockAssembler - Main class."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR
from nl2spl.pipeline.stages.base import PipelineStage
from nl2spl.pipeline.stages.stage5_block_assembler.block_parser import BlockParserMixin
from nl2spl.pipeline.stages.stage5_block_assembler.executor import ExecutorMixin
from nl2spl.pipeline.stages.stage5_block_assembler.prompt_enricher import PromptEnricherMixin
from nl2spl.pipeline.stages.stage5_block_assembler.region_parser import RegionParserMixin
from nl2spl.pipeline.stages.stage5_block_assembler.span_boundary import SpanBoundaryMixin


class BlockAssembler(
    ExecutorMixin,
    BlockParserMixin,
    RegionParserMixin,
    SpanBoundaryMixin,
    PromptEnricherMixin,
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR, FlowStructureIR]
        | tuple[list[SpanIR], FieldRouteIR, WorkerFlowPlanIR],
        BlockStructureIR | WorkerBlockPlanIR,
    ],
):
    """Organize behavior spans into legal top-level blocks.

    Legacy calls return one global BlockStructureIR. Worker-aware calls consume
    WorkerFlowPlanIR and return WorkerBlockPlanIR.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage5_block_assembler"
