"""Helper methods for Stage 9.5 IRNormalizer."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable


class HelpersMixin:
    """Mixin class containing helper methods for IRNormalizer."""

    def _append_nonduplicate_main_blocks(
        self,
        blocks: BlockStructureIR,
        moved_blocks: list[BlockIR],
    ) -> None:
        """Append moved blocks unless their span set is already represented."""
        existing_span_sets = {tuple(block.spans) for block in blocks.main_flow_blocks}
        for block in moved_blocks:
            signature = tuple(block.spans)
            if signature and signature in existing_span_sets:
                continue
            blocks.main_flow_blocks.append(block)
            existing_span_sets.add(signature)

    def _deduplicate_blocks(self, blocks: list[BlockIR]) -> list[BlockIR]:
        """Remove duplicate block span sets while preserving the first block."""
        seen: set[tuple[str, ...]] = set()
        deduped: list[BlockIR] = []
        for block in blocks:
            signature = tuple(block.spans)
            if signature and signature in seen:
                continue
            seen.add(signature)
            deduped.append(block)
        return deduped

    def _sync_symbol_table_from_steps(
        self,
        steps: list[StepIR],
        symbol_table: SymbolTable,
    ) -> None:
        """Refresh producer and consumer links from StepIR."""
        for variable in symbol_table.variables.values():
            variable.consumer_steps = []
            if variable.source in {"step", "output"}:
                variable.producer_step = None

        for step in steps:
            for input_name in step.inputs:
                symbol_table.add_consumer(input_name, step.step_id)
            for output_name in step.outputs:
                symbol_table.add_producer(output_name, step.step_id)

    def _is_loop_condition(self, condition_text: str) -> bool:
        """Return True for gate conditions that require repeated resolution."""
        text = condition_text.lower()
        return "do not finalize" in text and "missing" in text

    def _loop_condition_text(self, condition_text: str) -> str:
        """Rewrite a gate sentence into a WHILE condition."""
        text = condition_text.strip().rstrip(".")
        if self._is_loop_condition(text):
            return (
                "required slots remain missing and the draft is not explicitly "
                "marked as assumption-bearing with user confirmation"
            )
        return text

    def _is_exception_condition(self, condition_text: str) -> bool:
        """Return True when a condition describes failure, blocking, or refusal."""
        text = condition_text.lower()
        exception_markers = (
            "fail",
            "failure",
            "error",
            "exception",
            "missing",
            "invalid",
            "conflict",
            "insufficient",
            "shortage",
            "refusal",
            "refuse",
            "unavailable",
            "blocked",
            "deny",
            "do not finalize",
            "cannot",
            "provenance failure",
        )
        return any(marker in text for marker in exception_markers)

    def _sort_span_ids(self, span_ids: list[str]) -> list[str]:
        """Sort span ids by numeric suffix while preserving unknown ids."""
        return sorted(dict.fromkeys(span_ids), key=self._span_sort_key)

    def _block_sort_key(self, block: object) -> tuple[int, str]:
        """Sort blocks by their earliest source span."""
        spans = getattr(block, "spans", [])
        if not spans:
            return (10**9, getattr(block, "block_id", ""))
        return (
            min(self._span_sort_key(span_id) for span_id in spans),
            getattr(block, "block_id", ""),
        )

    def _span_sort_key(self, span_id: str) -> int:
        digits = "".join(ch for ch in span_id if ch.isdigit())
        return int(digits) if digits else 10**9

    def _compact_step_id(self, step_id: str) -> str:
        """Return st_12 as st12 for reconciling LLM target variants."""
        import re

        return re.sub(r"^st_", "st", step_id)

    def _next_synthetic_step_id(self, used_ids: set[str]) -> str:
        index = 1
        while f"st_norm_{index}" in used_ids:
            index += 1
        step_id = f"st_norm_{index}"
        used_ids.add(step_id)
        return step_id

    def _next_block_id(self, blocks: BlockStructureIR) -> str:
        used = {block.block_id for block in blocks.get_all_blocks()}
        index = 1
        while f"b_norm_{index}" in used:
            index += 1
        return f"b_norm_{index}"

    def _safe_name(self, name: str) -> str:
        """Convert a variable name into a safe identifier fragment."""
        import re

        return re.sub(r"[^a-zA-Z0-9_]", "_", name)
