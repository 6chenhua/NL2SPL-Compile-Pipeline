"""Block rendering methods for Stage 11 SPLRenderer."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.step_ir import StepIR


class BlockRendererMixin:
    """Mixin class containing block rendering methods for SPLRenderer."""

    def _render_blocks(
        self,
        blocks: list[BlockIR],
        steps: list[StepIR],
        indent: int,
        outer_condition_text: str | None = None,
    ) -> list[str]:
        """Render flow blocks with SPL grammar block names."""
        lines = []
        indent_str = " " * indent

        for block in blocks:
            block_steps = self._steps_for_block(block, steps)

            if block.block_type == "SEQUENTIAL":
                lines.append(f"{indent_str}[SEQUENTIAL_BLOCK]")
                lines.extend(self._render_step_lines(block_steps, indent + 4))
                lines.append(f"{indent_str}[END_SEQUENTIAL_BLOCK]")
            elif block.block_type == "IF":
                condition = self._render_condition(block.condition_text or "condition")
                if (
                    outer_condition_text
                    and self._condition_key(condition)
                    == self._condition_key(outer_condition_text)
                ):
                    lines.append(f"{indent_str}[SEQUENTIAL_BLOCK]")
                    lines.extend(
                        self._render_step_lines(block_steps, indent + 4, condition)
                    )
                    lines.append(f"{indent_str}[END_SEQUENTIAL_BLOCK]")
                    continue
                lines.append(
                    f"{indent_str}{self._next_decision()} [IF {condition}]"
                )
                lines.extend(
                    self._render_step_lines(block_steps, indent + 4, condition)
                )
                lines.append(f"{indent_str}[END_IF]")
            elif block.block_type == "FOR":
                condition = self._render_condition(block.condition_text or "items")
                lines.append(
                    f"{indent_str}{self._next_decision()} [FOR {condition}]"
                )
                lines.extend(
                    self._render_step_lines(block_steps, indent + 4, condition)
                )
                lines.append(f"{indent_str}[END_FOR]")
            elif block.block_type == "WHILE":
                condition = self._render_condition(block.condition_text or "condition")
                lines.append(
                    f"{indent_str}{self._next_decision()} [WHILE {condition}]"
                )
                lines.extend(
                    self._render_step_lines(block_steps, indent + 4, condition)
                )
                lines.append(f"{indent_str}[END_WHILE]")

        return lines

    def _render_step_lines(
        self,
        steps: list[StepIR],
        indent: int,
        condition_text: str | None = None,
    ) -> list[str]:
        """Render command lines at the requested indentation."""
        indent_str = " " * indent
        return [
            f"{indent_str}{self._render_step(step, condition_text)}"
            for step in steps
        ]

    def _steps_for_block(self, block: BlockIR, steps: list[StepIR]) -> list[StepIR]:
        """Return steps that belong to a block, preserving block span order."""
        span_order = {span_id: i for i, span_id in enumerate(block.spans)}
        selected: list[tuple[int, int, StepIR]] = []

        for step_index, step in enumerate(steps):
            if step.block_ref:
                if step.block_ref != block.block_id:
                    continue
                matching_positions = [
                    span_order[span_id]
                    for span_id in step.source_span_ids
                    if span_id in span_order
                ]
                position = min(matching_positions) if matching_positions else len(span_order)
                selected.append((position, step_index, step))
                continue

            matching_positions = [
                span_order[span_id]
                for span_id in step.source_span_ids
                if span_id in span_order
            ]
            if matching_positions:
                selected.append((min(matching_positions), step_index, step))
            elif step.block_ref == block.block_id:
                selected.append((len(span_order), step_index, step))

        selected.sort(key=lambda item: (item[0], item[1]))
        return [step for _, _, step in selected]

    def _render_step(self, step: StepIR, condition_text: str | None = None) -> str:
        """Render a single step as a grammar-shaped SPL command."""
        command_index = self._next_command()
        command_text = self._canonical_command_text(step.text, condition_text)
        text = self._description_with_refs(command_text, step.inputs)

        if step.command_type == "GENERAL_COMMAND":
            return f"{command_index} [COMMAND {text}{self._result_clause('RESULT', step.outputs)}]"

        if step.command_type == "CALL_API":
            api_name = step.integration_ref or "Api"
            return (
                f"{command_index} [CALL {api_name}"
                f"{self._with_clause(step.inputs)}"
                f"{self._result_clause('RESPONSE', step.outputs)}]"
            )

        if step.command_type == "INVOKE_WORKER":
            worker_name = step.integration_ref or "<UNRESOLVED_WORKER>"
            return (
                f"{command_index} [INVOKE {worker_name}"
                f"{self._with_clause(step.inputs)}"
                f"{self._result_clause('RESPONSE', step.outputs)}]"
            )

        if step.command_type == "REQUEST_INPUT":
            result_clause = self._result_clause("VALUE", step.outputs)
            if not result_clause:
                result_clause = " VALUE user_input:text SET"
            return f"{command_index} [INPUT {text}{result_clause}]"

        if step.command_type == "DISPLAY_MESSAGE":
            return f"{command_index} [DISPLAY {text}]"

        return f"{command_index} [COMMAND {text}{self._result_clause('RESULT', step.outputs)}]"
