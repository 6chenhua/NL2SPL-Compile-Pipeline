"""Structural normalization methods for Stage 9.5 IRNormalizer."""

from __future__ import annotations

from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, TypeSpec, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import ContractFieldIR, WorkerPlanIR


class NormalizationMixin:
    """Deterministic structural normalization helpers for IRNormalizer."""

    def _normalize_multi_output_steps(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
        worker_id: str | None = None,
        worker_plan: WorkerPlanIR | None = None,
    ) -> list[str]:
        """Aggregate multi-output commands into one structured result variable."""
        warnings: list[str] = []
        normalized_steps: list[StepIR] = []
        output_to_structured: dict[str, str] = {}
        prior_producers: set[str] = set()
        worker_inputs = self._worker_input_names(worker_id, worker_plan)

        for step in steps:
            if output_to_structured:
                step.inputs = self._rewrite_structured_inputs(
                    step.inputs,
                    output_to_structured,
                )
            normalized_steps.append(step)
            if len(step.outputs) <= 1:
                for output_name in step.outputs:
                    output_to_structured.pop(output_name, None)
                prior_producers.update(step.outputs)
                continue

            original_outputs = list(step.outputs)
            step.inputs = [
                input_name
                for input_name in step.inputs
                if (
                    input_name not in original_outputs
                    or input_name in prior_producers
                    or input_name in worker_inputs
                )
            ]
            result_name = self._aggregate_result_name(step, worker_id)
            type_name = self._aggregate_type_name(result_name)
            definition = self._structured_type_definition(original_outputs, symbol_table)

            step.metadata["origin"] = step.metadata.get("origin") or "source_backed"
            step.metadata["structured_aggregation"] = {
                "result_name": result_name,
                "original_outputs": original_outputs,
                "type_name": type_name,
            }
            if step.handoff_id and worker_plan:
                handoff = next(
                    (h for h in worker_plan.handoffs if h.handoff_id == step.handoff_id),
                    None,
                )
                if handoff:
                    step.metadata["handoff_output_bindings"] = [
                        {
                            "child_output": binding.child_output,
                            "parent_variable": binding.parent_variable,
                            "required": binding.required,
                        }
                        for binding in handoff.output_bindings
                    ]

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
            self._replace_worker_output_contract(
                resources,
                symbol_table,
                worker_plan,
                worker_id,
                original_outputs,
                result_name,
                type_name,
                step.step_id,
            )
            for output_name in original_outputs:
                output_to_structured[output_name] = result_name
            prior_producers.add(result_name)

            warnings.append(
                f"Aggregated multi-output step {step.step_id} into "
                f"{result_name} without unpack steps."
            )

        steps[:] = normalized_steps
        return warnings

    @staticmethod
    def _rewrite_structured_inputs(
        inputs: list[str],
        output_to_structured: dict[str, str],
    ) -> list[str]:
        """Rewrite consumed aggregate fields to their structured result variable."""
        rewritten: list[str] = []
        for input_name in inputs:
            replacement = output_to_structured.get(input_name, input_name)
            if replacement not in rewritten:
                rewritten.append(replacement)
        return rewritten

    @staticmethod
    def _worker_input_names(
        worker_id: str | None,
        worker_plan: WorkerPlanIR | None,
    ) -> set[str]:
        if worker_id is None or worker_plan is None:
            return set()
        worker = next(
            (spec for spec in worker_plan.workers if spec.worker_id == worker_id),
            None,
        )
        if worker is None:
            return set()
        return {field.name for field in worker.input_contract}

    def _replace_worker_output_contract(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        worker_plan: WorkerPlanIR | None,
        worker_id: str | None,
        original_outputs: list[str],
        result_name: str,
        type_name: str,
        step_id: str,
    ) -> None:
        """Replace covered worker output fields with the structured result."""
        if worker_id is None or worker_plan is None:
            return

        worker = next(
            (spec for spec in worker_plan.workers if spec.worker_id == worker_id),
            None,
        )
        if worker is None:
            return

        covered = set(original_outputs)
        removed = [field for field in worker.output_contract if field.name in covered]
        if not removed:
            return

        insert_at = min(
            index
            for index, field in enumerate(worker.output_contract)
            if field.name in covered
        )
        worker.output_contract = [
            field
            for field in worker.output_contract
            if field.name not in covered and field.name != result_name
        ]
        worker.output_contract.insert(
            min(insert_at, len(worker.output_contract)),
            ContractFieldIR(
                name=result_name,
                data_type=type_name,
                required=any(field.required for field in removed),
                description=f"Structured result for {step_id}.",
                source="output",
            ),
        )

        resource_var = next(
            (variable for variable in resources.variables if variable.name == result_name),
            None,
        )
        if resource_var is not None:
            resource_var.source = "output"
            resource_var.required = any(field.required for field in removed)

        symbol = symbol_table.variables.get(result_name)
        if symbol is not None:
            symbol.source = "output"

    def _aggregate_result_name(self, step: StepIR, worker_id: str | None = None) -> str:
        """Derive a structured result variable name from a step."""
        if step.handoff_id:
            base = f"{step.handoff_id}_response"
        elif worker_id:
            base = f"{worker_id}_{step.step_id}_result"
        else:
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

    def _ensure_type(
        self,
        resources: ResourceRegistryIR,
        type_name: str,
        definition: dict[str, str],
    ) -> None:
        """Ensure a type exists in the resource registry."""
        existing = next((t for t in resources.types if t.type_name == type_name), None)
        if existing is not None:
            return
        resources.types.append(
            TypeSpec(
                type_name=type_name,
                type_kind="structured",
                definition=self._structured_type_literal(definition),
            )
        )

    def _structured_type_literal(self, definition: dict[str, str]) -> str:
        """Render a SPL structured type declaration body."""
        fields = [
            f"{name}: {self._format_structured_field_type(data_type)}"
            for name, data_type in definition.items()
        ]
        return "{ " + ", ".join(fields) + " }"

    def _format_structured_field_type(self, data_type: str) -> str:
        """Normalize simple field data type spelling for SPL."""
        text = data_type.strip()
        if text.startswith("List[") and text.endswith("]"):
            return f"List [{text[5:-1].strip()}]"
        return text

    def _ensure_variable(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        name: str,
        data_type: str,
        description: str,
    ) -> None:
        """Ensure a variable exists in both resource registry and symbol table."""
        existing_resource = next((v for v in resources.variables if v.name == name), None)
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
