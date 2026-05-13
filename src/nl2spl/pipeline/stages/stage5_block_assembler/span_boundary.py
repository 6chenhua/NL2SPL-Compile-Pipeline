"""Stage 5: BlockAssembler - SpanBoundaryMixin (worker span boundary enforcement)."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.worker_plan_ir import ControlComplexityRegionIR


class SpanBoundaryMixin:
    """Mixin containing worker span boundary enforcement methods."""

    def _enforce_worker_span_boundary(
        self,
        block_structure: BlockStructureIR,
        control_regions: list[ControlComplexityRegionIR],
        allowed_span_ids: set[str],
        worker_id: str | None,
    ) -> tuple[BlockStructureIR, list[ControlComplexityRegionIR], list[str]]:
        """Drop spans outside the worker-local flow and report each repair."""
        filtered_main, warnings = self._filter_blocks_to_allowed_spans(
            block_structure.main_flow_blocks,
            flow_ref="main",
            allowed_span_ids=allowed_span_ids,
            worker_id=worker_id,
        )

        filtered_alternative: dict[str, list[BlockIR]] = {}
        for flow_id, blocks in block_structure.alternative_flow_blocks.items():
            filtered_blocks, flow_warnings = self._filter_blocks_to_allowed_spans(
                blocks,
                flow_ref=flow_id,
                allowed_span_ids=allowed_span_ids,
                worker_id=worker_id,
            )
            filtered_alternative[flow_id] = filtered_blocks
            warnings.extend(flow_warnings)

        filtered_exception: dict[str, list[BlockIR]] = {}
        for flow_id, blocks in block_structure.exception_flow_blocks.items():
            filtered_blocks, flow_warnings = self._filter_blocks_to_allowed_spans(
                blocks,
                flow_ref=flow_id,
                allowed_span_ids=allowed_span_ids,
                worker_id=worker_id,
            )
            filtered_exception[flow_id] = filtered_blocks
            warnings.extend(flow_warnings)

        filtered_regions: list[ControlComplexityRegionIR] = []
        for region in control_regions:
            invalid_span_ids = [
                span_id
                for span_id in region.source_span_ids
                if span_id not in allowed_span_ids
            ]
            if invalid_span_ids:
                warnings.append(
                    self._boundary_warning(
                        worker_id,
                        f"control region {region.region_id}",
                        invalid_span_ids,
                    )
                )
            region.source_span_ids = [
                span_id
                for span_id in region.source_span_ids
                if span_id in allowed_span_ids
            ]
            if region.source_span_ids:
                filtered_regions.append(region)

        return (
            BlockStructureIR(
                main_flow_blocks=filtered_main,
                alternative_flow_blocks=filtered_alternative,
                exception_flow_blocks=filtered_exception,
            ),
            filtered_regions,
            warnings,
        )

    def _filter_blocks_to_allowed_spans(
        self,
        blocks: list[BlockIR],
        flow_ref: str,
        allowed_span_ids: set[str],
        worker_id: str | None,
    ) -> tuple[list[BlockIR], list[str]]:
        """Return blocks with only worker-local spans, dropping empty blocks."""
        filtered_blocks: list[BlockIR] = []
        warnings: list[str] = []

        for block in blocks:
            invalid_span_ids = [
                span_id for span_id in block.spans if span_id not in allowed_span_ids
            ]
            kept_span_ids = [
                span_id for span_id in block.spans if span_id in allowed_span_ids
            ]
            if invalid_span_ids:
                warnings.append(
                    self._boundary_warning(
                        worker_id,
                        f"{flow_ref} block {block.block_id}",
                        invalid_span_ids,
                    )
                )
            if not kept_span_ids:
                if block.spans:
                    warnings.append(
                        self._drop_block_warning(worker_id, flow_ref, block.block_id)
                    )
                continue
            filtered_blocks.append(
                BlockIR(
                    block_id=block.block_id,
                    block_type=block.block_type,
                    condition_text=block.condition_text,
                    spans=kept_span_ids,
                )
            )

        return filtered_blocks, warnings

    def _boundary_warning(
        self,
        worker_id: str | None,
        target: str,
        invalid_span_ids: list[str],
    ) -> str:
        """Format a worker-boundary span warning."""
        worker_label = worker_id or "legacy"
        invalid_spans = ", ".join(invalid_span_ids)
        return (
            f"Worker {worker_label} {target} referenced span(s) outside "
            f"its worker-local flow and they were discarded: {invalid_spans}."
        )

    def _drop_block_warning(
        self,
        worker_id: str | None,
        flow_ref: str,
        block_id: str,
    ) -> str:
        """Format a warning for blocks emptied by worker-boundary filtering."""
        worker_label = worker_id or "legacy"
        return (
            f"Worker {worker_label} {flow_ref} block {block_id} was dropped "
            "because no spans remained inside the worker-local flow."
        )
