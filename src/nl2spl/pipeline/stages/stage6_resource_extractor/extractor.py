"""Stage 6: ResourceExtractor - Extract variables, files, APIs, types."""

from __future__ import annotations

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.base import PipelineStage
from nl2spl.pipeline.stages.stage6_resource_extractor.legacy import (
    LegacyMethodsMixin,
)
from nl2spl.pipeline.stages.stage6_resource_extractor.worker_scoped import (
    WorkerScopedMixin,
)


class ResourceExtractor(
    LegacyMethodsMixin,
    WorkerScopedMixin,
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR]
        | tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR]
        | tuple[
            list[SpanIR],
            FieldRouteIR,
            FlowStructureIR,
            BlockStructureIR,
            CanonicalCompileInput,
        ],
        tuple[ResourceRegistryIR, SymbolTable],
    ],
):
    """Extract resources (variables, files, APIs, types) from spans.

    This stage takes behavior and integrations spans, extracts resources,
    and builds a SymbolTable for variable management.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage6_resource_extractor"
