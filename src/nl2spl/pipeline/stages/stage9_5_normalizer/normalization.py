"""Normalization methods for Stage 9.5 IRNormalizer."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, TypeSpec, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable


class NormalizationMixin:
    """Mixin class containing normalization methods for IRNormalizer."""

    def _normalize_source_retrieval_inputs(
        self,
        steps: list[StepIR],
        symbol_table: SymbolTable,
    ) -> list[str]:
        """Prefer declared runtime inputs over unproduced planning variables."""
        warnings: list[str] = []
        if "available_connectors" not in symbol_table.variables:
            return warnings

        for step in steps:
            if step.command_type != "GENERAL_COMMAND":
                continue
            text = step.text.lower()
            if "source" not in text and "retriev" not in text and "provenance" not in text:
                continue
            if "available_connectors" in step.inputs:
                continue
            step.inputs = ["available_connectors"]
            warnings.append(
                f"Remapped inputs for step {step.step_id} to available_connectors."
            )

        return warnings

    def _prune_unused_step_variables(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
    ) -> list[str]:
        """Remove orphan step variables left behind by earlier LLM stages."""
        used_names = {
            name
            for step in steps
            for name in [*step.inputs, *step.outputs]
        }
        pruned = [
            variable.name
            for variable in resources.variables
            if variable.source == "step" and variable.name not in used_names
        ]
        if not pruned:
            return []

        resources.variables = [
            variable
            for variable in resources.variables
            if variable.name not in pruned
        ]
        for name in pruned:
            symbol_table.variables.pop(name, None)

        return [f"Pruned unused step variable: {name}" for name in pruned]

    def _normalize_multi_output_steps(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
    ) -> list[str]:
        """Aggregate multi-output commands into one structured result variable."""
        warnings: list[str] = []
        used_ids = {step.step_id for step in steps}
        normalized_steps: list[StepIR] = []

        for step in steps:
            normalized_steps.append(step)
            if len(step.outputs) <= 1:
                continue

            original_outputs = list(step.outputs)
            result_name = self._aggregate_result_name(step)
            type_name = self._aggregate_type_name(result_name)
            definition = self._structured_type_definition(original_outputs, symbol_table)

            self._ensure_type(resources, type_name, definition)
            self._ensure_variable(
                resources,
                symbol_table,
                result_name,
                type_name,
                f"Structured result for {step.step_id}.",
            )
            step.outputs = [result_name]
            symbol_table.add_producer(result_name, step.step_id)

            for output_name in original_outputs:
                unpack_step_id = self._next_synthetic_step_id(used_ids)
                unpack_step = StepIR(
                    step_id=unpack_step_id,
                    text=f"Extract {output_name} from {result_name}",
                    source_span_ids=[],
                    command_type="GENERAL_COMMAND",
                    inputs=[result_name],
                    outputs=[output_name],
                    flow_ref=step.flow_ref,
                    block_ref=step.block_ref,
                )
                normalized_steps.append(unpack_step)
                symbol_table.add_producer(output_name, unpack_step_id)

            warnings.append(
                f"Aggregated multi-output step {step.step_id} into "
                f"{result_name} with {len(original_outputs)} unpack steps."
            )

        steps[:] = normalized_steps
        return warnings

    def _aggregate_result_name(self, step: StepIR) -> str:
        """Derive a structured result variable name from a step."""
        base = step.outputs[0] if step.outputs else "result"
        return f"{self._safe_name(base)}_structured"

    def _aggregate_type_name(self, result_name: str) -> str:
        """Derive a type name for an aggregated result."""
        return f"{self._safe_name(result_name)}_type"

    def _structured_type_definition(
        self,
        original_outputs: list[str],
        symbol_table: SymbolTable,
    ) -> dict[str, str]:
        """Build a structured type definition from original outputs."""
        definition: dict[str, str] = {}
        for output_name in original_outputs:
            variable = symbol_table.variables.get(output_name)
            definition[output_name] = variable.data_type if variable else "text"
        return definition

    def _format_struct_data_type(self, data_type: str) -> str:
        """Format a structured data type for display."""
        return data_type

    def _ensure_type(
        self,
        resources: ResourceRegistryIR,
        type_name: str,
        definition: dict[str, str],
    ) -> None:
        """Ensure a type exists in the resource registry."""
        existing = next(
            (t for t in resources.types if t.name == type_name),
            None,
        )
        if existing is not None:
            return

        resources.types.append(
            TypeSpec(
                name=type_name,
                fields=[
                    {"name": name, "data_type": dtype}
                    for name, dtype in definition.items()
                ],
            )
        )

    def _ensure_variable(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        name: str,
        data_type: str,
        description: str,
    ) -> None:
        """Ensure a variable exists in both resource registry and symbol table."""
        existing_resource = next(
            (v for v in resources.variables if v.name == name),
            None,
        )
        if existing_resource is None:
            resources.variables.append(
                VariableSpec(
                    name=name,
                    data_type=data_type,
                    required=True,
                    description=description,
                    source="step",
                )
            )

        if name not in symbol_table.variables:
            symbol_table.declare(
                name=name,
                data_type=data_type,
                source="step",
                description=description,
            )

    def _is_unproduced_step_variable(self, name: str, symbol_table: SymbolTable) -> bool:
        """Return True when a step variable has no producer."""
        variable = symbol_table.variables.get(name)
        if variable is None:
            return True
        return variable.source == "step" and variable.producer_step is None

    def _ensure_required_main_outputs(
        self,
        blocks: BlockStructureIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
    ) -> list[str]:
        """Ensure required outputs have producers in the main flow."""
        warnings: list[str] = []
        required_outputs = [
            variable.name
            for variable in resources.variables
            if variable.required and variable.source == "output"
        ]
        if not required_outputs:
            return warnings

        produced_outputs = {
            output
            for step in steps
            for output in step.outputs
        }
        existing_main_outputs = [
            output for output in required_outputs if output in produced_outputs
        ]

        for output in required_outputs:
            if output in produced_outputs:
                continue

            inputs = self._completion_inputs_for_output(
                output, existing_main_outputs, symbol_table
            )
            block_id = self._normal_completion_block_id(blocks)
            step_id = self._next_synthetic_step_id({step.step_id for step in steps})
            completion_step = StepIR(
                step_id=step_id,
                text=self._completion_step_text(output),
                source_span_ids=[],
                command_type="GENERAL_COMMAND",
                inputs=inputs,
                outputs=[output],
                flow_ref="main",
                block_ref=block_id,
            )
            steps.append(completion_step)
            symbol_table.add_producer(output, step_id)
            existing_main_outputs.append(output)
            warnings.append(f"Added normal-path producer for required output {output}.")

        return warnings

    def _completion_inputs_for_output(
        self,
        output: str,
        existing_main_outputs: list[str],
        symbol_table: SymbolTable,
    ) -> list[str]:
        """Choose semantically useful inputs for synthetic completion outputs."""
        if output == "source_evidence_set":
            evidence_inputs = [
                name
                for name in ("retrieved_sources", "provenance_log")
                if name in symbol_table.variables
            ]
            if evidence_inputs:
                return evidence_inputs

        return [name for name in existing_main_outputs if name != output]

    def _normal_completion_block_id(self, blocks: BlockStructureIR) -> str:
        """Return a main-flow block id suitable for synthetic completion steps."""
        if not blocks.main_flow_blocks:
            blocks.main_flow_blocks.append(BlockIR("b_normal_completion", "SEQUENTIAL", None, []))
            return "b_normal_completion"

        last_block = blocks.main_flow_blocks[-1]
        if last_block.block_type == "SEQUENTIAL":
            return last_block.block_id

        block_id = self._next_block_id(blocks)
        blocks.main_flow_blocks.append(BlockIR(block_id, "SEQUENTIAL", None, []))
        return block_id

    def _completion_step_text(self, output: str) -> str:
        text_by_output = {
            "assumptions_log": "Record assumptions for unresolved items",
            "completion_status": "Set completion status for the normal completion path",
            "source_evidence_set": "Produce the source evidence set for normal completion",
            "draft": "Produce the draft for normal completion",
        }
        return text_by_output.get(output, f"Produce required output {output}")
