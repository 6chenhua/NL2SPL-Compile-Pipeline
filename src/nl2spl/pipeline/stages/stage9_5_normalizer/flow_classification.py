"""Flow classification methods for Stage 9.5 IRNormalizer."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR


class FlowClassificationMixin:
    """Mixin class containing flow classification methods for IRNormalizer."""

    def _normalize_flow_classification(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
    ) -> tuple[FlowStructureIR, BlockStructureIR, list[str]]:
        """Move non-exception conditional spans back to the main path."""
        warnings: list[str] = []
        retained_alternative_flows = []
        for alt_flow in flow.alternative_flows:
            if self._should_inline_alternative_flow(alt_flow.condition_text):
                for span_id in alt_flow.spans:
                    if span_id not in flow.main_flow_spans:
                        flow.main_flow_spans.append(span_id)
                moved_blocks = blocks.alternative_flow_blocks.pop(alt_flow.flow_id, [])
                self._append_nonduplicate_main_blocks(blocks, moved_blocks)
                warnings.append(
                    "Moved ordinary alternative flow "
                    f"{alt_flow.flow_id} into main flow: {alt_flow.condition_text}"
                )
            else:
                retained_alternative_flows.append(alt_flow)

        flow.alternative_flows = retained_alternative_flows

        retained_exception_flows = []
        for exc_flow in flow.exception_flows:
            if self._is_loop_condition(exc_flow.condition_text):
                for span_id in exc_flow.spans:
                    if span_id not in flow.main_flow_spans:
                        flow.main_flow_spans.append(span_id)
                moved_blocks = blocks.exception_flow_blocks.pop(exc_flow.flow_id, [])
                for block in moved_blocks:
                    block.block_type = "WHILE"
                    block.condition_text = self._loop_condition_text(exc_flow.condition_text)
                self._append_nonduplicate_main_blocks(blocks, moved_blocks)
                warnings.append(
                    "Moved loop-like exception flow "
                    f"{exc_flow.flow_id} into main flow: {exc_flow.condition_text}"
                )
                continue

            if self._is_exception_condition(exc_flow.condition_text):
                retained_exception_flows.append(exc_flow)
                continue

            for span_id in exc_flow.spans:
                if span_id not in flow.main_flow_spans:
                    flow.main_flow_spans.append(span_id)
            moved_blocks = blocks.exception_flow_blocks.pop(exc_flow.flow_id, [])
            self._append_nonduplicate_main_blocks(blocks, moved_blocks)
            warnings.append(
                "Moved non-exception conditional flow "
                f"{exc_flow.flow_id} into main flow: {exc_flow.condition_text}"
            )

        flow.exception_flows = retained_exception_flows
        flow.main_flow_spans = self._sort_span_ids(flow.main_flow_spans)
        blocks.main_flow_blocks.sort(key=self._block_sort_key)
        blocks.main_flow_blocks = self._deduplicate_blocks(blocks.main_flow_blocks)
        return flow, blocks, warnings

    def _should_inline_alternative_flow(self, condition_text: str) -> bool:
        """Return True when an alternative is ordinary conditional work."""
        text = condition_text.strip().lower()
        return text.startswith(("if ", "when ")) and not self._is_exception_condition(text)
