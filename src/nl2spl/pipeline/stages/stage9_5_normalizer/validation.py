"""Validation methods for Stage 9.5 IRNormalizer."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerHandoffIR, WorkerPlanIR, WorkerSpecIR


class ValidationMixin:
    """Mixin class containing validation methods for IRNormalizer."""

    def _validate_worker_plan_handoffs(
        self,
        worker_plan: WorkerPlanIR,
        steps: list[StepIR],
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
    ) -> list[str]:
        """Validate final handoff steps against WorkerPlanIR contracts."""
        errors: list[str] = []
        worker_by_id = {worker.worker_id: worker for worker in worker_plan.workers}
        final_outputs = {
            variable.name
            for variable in resources.variables
            if variable.source == "output"
        }
        invoked_worker_names = {
            worker_by_id[handoff.to_worker].worker_name
            for handoff in worker_plan.handoffs
            if handoff.mode == "invoke"
            and handoff.to_worker in worker_by_id
            and self._steps_for_worker_plan_handoff(
                handoff,
                "INVOKE_WORKER",
                worker_by_id[handoff.to_worker].worker_name,
                steps,
            )
        }
        for worker in worker_plan.workers:
            if worker.kind == "main":
                continue
            if worker.worker_name not in invoked_worker_names:
                errors.append(
                    f"Non-main worker has no parent invocation step: {worker.worker_name}"
                )

        for handoff in worker_plan.handoffs:
            if handoff.mode == "invoke":
                if handoff.to_worker is None:
                    continue
                target = worker_by_id.get(handoff.to_worker)
                if target is None:
                    continue

                target_steps = self._steps_for_worker_plan_handoff(
                    handoff,
                    "INVOKE_WORKER",
                    target.worker_name,
                    steps,
                )
                if not target_steps:
                    errors.append(
                        f"Handoff {handoff.handoff_id} has no INVOKE_WORKER step for "
                        f"{target.worker_name}."
                    )
                    continue

                for step in target_steps:
                    errors.extend(
                        self._validate_handoff_step_bindings(
                            handoff,
                            target,
                            step,
                            final_outputs,
                            symbol_table,
                        )
                    )
                continue

            if handoff.mode != "api_call":
                continue

            api_steps = self._steps_for_worker_plan_handoff(
                handoff,
                "CALL_API",
                handoff.api_ref,
                steps,
            )
            if not api_steps:
                errors.append(
                    f"Handoff {handoff.handoff_id} has no CALL_API step for "
                    f"{handoff.api_ref or '<missing api_ref>'}."
                )
                continue

            for step in api_steps:
                errors.extend(
                    self._validate_api_handoff_step_bindings(
                        handoff,
                        step,
                        final_outputs,
                        symbol_table,
                    )
                )

        return errors

    def _steps_for_worker_plan_handoff(
        self,
        handoff: WorkerHandoffIR,
        command_type: str,
        integration_ref: str | None,
        steps: list[StepIR],
    ) -> list[StepIR]:
        """Find final steps corresponding to one WorkerPlanIR handoff."""
        by_handoff_id = [
            step
            for step in steps
            if step.handoff_id == handoff.handoff_id
            and step.command_type == command_type
            and step.integration_ref == integration_ref
        ]
        if by_handoff_id:
            return by_handoff_id

        planned_inputs = [
            binding.parent_variable
            for binding in handoff.input_bindings
            if binding.parent_variable
        ]
        planned_outputs = [
            binding.parent_variable
            for binding in handoff.output_bindings
            if binding.parent_variable
        ]
        planned_spans = set(self._handoff_source_spans(handoff, None))

        return [
            step
            for step in steps
            if step.command_type == command_type
            and step.integration_ref == integration_ref
            and not step.handoff_id
            and list(step.inputs) == planned_inputs
            and list(step.outputs) == planned_outputs
            and (
                not planned_spans
                or set(step.source_span_ids) == planned_spans
            )
        ]

    def _validate_handoff_step_bindings(
        self,
        handoff: WorkerHandoffIR,
        target: WorkerSpecIR,
        step: StepIR,
        final_outputs: set[str],
        symbol_table: SymbolTable,
    ) -> list[str]:
        errors: list[str] = []
        target_input_names = {field.name for field in target.input_contract}
        target_output_names = {field.name for field in target.output_contract}

        for binding in handoff.input_bindings:
            if binding.child_input not in target_input_names:
                errors.append(
                    f"Handoff {handoff.handoff_id} input binding targets unknown "
                    f"child input: {binding.child_input}"
                )
            if binding.required and binding.parent_variable not in step.inputs:
                errors.append(
                    f"Handoff {handoff.handoff_id} required input "
                    f"{binding.parent_variable} is missing from step {step.step_id}."
                )
            if binding.required and binding.parent_variable not in symbol_table.variables:
                errors.append(
                    f"Handoff {handoff.handoff_id} required input "
                    f"{binding.parent_variable} is not declared."
                )

        for binding in handoff.output_bindings:
            if binding.child_output not in target_output_names:
                errors.append(
                    f"Handoff {handoff.handoff_id} output binding targets unknown "
                    f"child output: {binding.child_output}"
                )
            if (
                not binding.required
                and binding.parent_variable not in step.outputs
                and binding.merge_strategy != "ignore_if_empty"
            ):
                errors.append(
                    f"Handoff {handoff.handoff_id} optional output "
                    f"{binding.parent_variable} is ignored without ignore_if_empty."
                )
            if binding.required and binding.parent_variable not in symbol_table.variables:
                errors.append(
                    f"Handoff {handoff.handoff_id} required output "
                    f"{binding.parent_variable} is not declared."
                )
            if binding.required and not self._is_parent_output_used(
                binding.parent_variable,
                step.step_id,
                final_outputs,
                symbol_table,
            ):
                errors.append(
                    f"Handoff {handoff.handoff_id} required output "
                    f"{binding.parent_variable} is not consumed or declared as a final output."
                )
        return errors

    def _validate_api_handoff_step_bindings(
        self,
        handoff: WorkerHandoffIR,
        step: StepIR,
        final_outputs: set[str],
        symbol_table: SymbolTable,
    ) -> list[str]:
        """Validate direct API handoff bindings against the materialized CALL_API step."""
        errors: list[str] = []
        if step.command_type != "CALL_API":
            errors.append(
                f"Handoff {handoff.handoff_id} expected CALL_API step, got {step.command_type}."
            )
        if step.integration_ref != handoff.api_ref:
            errors.append(
                f"Handoff {handoff.handoff_id} CALL_API target mismatch: "
                f"{step.integration_ref} != {handoff.api_ref}."
            )

        errors.extend(
            self._validate_parent_input_bindings(handoff, step, symbol_table)
        )
        errors.extend(
            self._validate_parent_output_bindings(
                handoff,
                step,
                final_outputs,
                symbol_table,
            )
        )
        return errors

    def _validate_parent_input_bindings(
        self,
        handoff: WorkerHandoffIR,
        step: StepIR,
        symbol_table: SymbolTable,
    ) -> list[str]:
        errors: list[str] = []
        for binding in handoff.input_bindings:
            if binding.required and binding.parent_variable not in step.inputs:
                errors.append(
                    f"Handoff {handoff.handoff_id} required input "
                    f"{binding.parent_variable} is missing from step {step.step_id}."
                )
            if (
                binding.required
                and binding.parent_variable not in symbol_table.variables
            ):
                errors.append(
                    f"Handoff {handoff.handoff_id} required input "
                    f"{binding.parent_variable} is not declared."
                )
        return errors

    def _validate_parent_output_bindings(
        self,
        handoff: WorkerHandoffIR,
        step: StepIR,
        final_outputs: set[str],
        symbol_table: SymbolTable,
    ) -> list[str]:
        errors: list[str] = []
        for binding in handoff.output_bindings:
            parent_symbol = symbol_table.variables.get(binding.parent_variable)
            if (
                binding.required
                and binding.parent_variable not in step.outputs
                and not (parent_symbol and parent_symbol.producer_step)
            ):
                errors.append(
                    f"Handoff {handoff.handoff_id} required output "
                    f"{binding.parent_variable} is missing from step {step.step_id}."
                )
            if (
                not binding.required
                and binding.parent_variable not in step.outputs
                and binding.merge_strategy != "ignore_if_empty"
            ):
                errors.append(
                    f"Handoff {handoff.handoff_id} optional output "
                    f"{binding.parent_variable} is ignored without ignore_if_empty."
                )
            if binding.required and binding.parent_variable not in symbol_table.variables:
                errors.append(
                    f"Handoff {handoff.handoff_id} required output "
                    f"{binding.parent_variable} is not declared."
                )
            if binding.required and not self._is_parent_output_used(
                binding.parent_variable,
                step.step_id,
                final_outputs,
                symbol_table,
            ):
                errors.append(
                    f"Handoff {handoff.handoff_id} required output "
                    f"{binding.parent_variable} is not consumed or declared as a final output."
                )
        return errors

    def _is_parent_output_used(
        self,
        parent_variable: str,
        producer_step_id: str,
        final_outputs: set[str],
        symbol_table: SymbolTable,
    ) -> bool:
        if parent_variable in final_outputs:
            return True
        variable = symbol_table.variables.get(parent_variable)
        if variable is None:
            return False
        return any(
            consumer_step_id != producer_step_id
            for consumer_step_id in variable.consumer_steps
        )

    def _validate_references(
        self,
        steps: list[StepIR],
        constraints: list[ConstraintIR],
        symbol_table: SymbolTable,
        resources: ResourceRegistryIR,
    ) -> list[str]:
        """Validate all references.

        Args:
            steps: List of step IRs
            constraints: List of constraint IRs
            symbol_table: Symbol table
            resources: Resource registry IR

        Returns:
            List of validation errors
        """
        errors: list[str] = []
        step_ids = {s.step_id for s in steps}
        api_names = {a.api_name for a in resources.apis}

        # Validate step variable references
        for step in steps:
            for var_name in step.inputs + step.outputs:
                if var_name not in symbol_table.variables:
                    errors.append(f"Step {step.step_id} references unknown variable: {var_name}")

            if (
                step.command_type == "CALL_API"
                and step.integration_ref
                and step.integration_ref not in api_names
            ):
                errors.append(f"Step {step.step_id} references unknown API: {step.integration_ref}")

        # Validate constraint references
        for constraint in constraints:
            for target in constraint.targets:
                if ":" in target:
                    target_type, target_id = target.split(":", 1)
                    if target_type == "step" and target_id not in step_ids:
                        errors.append(
                            "Constraint "
                            f"{constraint.constraint_id} references unknown step: {target_id}"
                        )
                    elif target_type == "variable" and target_id not in symbol_table.variables:
                        if target_id in getattr(self, "_pruned_variable_names", set()):
                            continue
                        errors.append(
                            "Constraint "
                            f"{constraint.constraint_id} references unknown variable: {target_id}"
                        )

        return errors

    def _validate_coverage(self, flow: FlowStructureIR, steps: list[StepIR]) -> list[str]:
        """Validate all spans are covered by steps.

        Args:
            flow: Flow structure IR
            steps: List of step IRs

        Returns:
            List of validation warnings
        """
        warnings: list[str] = []
        flow_spans = flow.get_all_flow_spans()
        covered_spans: set[str] = set()
        for step in steps:
            covered_spans.update(step.source_span_ids)

        uncovered = flow_spans - covered_spans
        if uncovered:
            warnings.append(f"Spans not covered by any step: {uncovered}")

        return warnings

    def _reconcile_steps(
        self, steps: list[StepIR], flow: FlowStructureIR, blocks: BlockStructureIR
    ) -> list[StepIR]:
        """Reconcile step flow_ref and block_ref.

        Args:
            steps: List of step IRs
            flow: Flow structure IR
            blocks: Block structure IR

        Returns:
            List of reconciled step IRs
        """
        for step in steps:
            if not step.flow_ref:
                if step.source_span_ids:
                    step.flow_ref = flow.get_flow_for_span(step.source_span_ids[0]) or "main"
                else:
                    step.flow_ref = "main"
            elif step.source_span_ids:
                step.flow_ref = flow.get_flow_for_span(step.source_span_ids[0]) or step.flow_ref
            if not step.block_ref:
                block = None
                if step.source_span_ids:
                    block = blocks.get_block_for_span(step.source_span_ids[0])
                step.block_ref = block.block_id if block else ""
            elif step.source_span_ids:
                block = blocks.get_block_for_span(step.source_span_ids[0])
                if block:
                    step.block_ref = block.block_id
        return steps

    def _validate_path_dataflow(
        self,
        steps: list[StepIR],
        resources: ResourceRegistryIR,
    ) -> list[str]:
        """Validate dataflow consistency across paths.

        Args:
            steps: List of step IRs
            resources: Resource registry IR

        Returns:
            List of validation warnings
        """
        warnings: list[str] = []

        # Check for steps that produce outputs but have no inputs
        for step in steps:
            if step.outputs and not step.inputs and step.command_type == "GENERAL_COMMAND":
                if step.source_span_ids:  # Only warn for steps with source spans
                    warnings.append(
                        f"Step {step.step_id} produces outputs but has no inputs"
                    )

        return warnings

    def _reconcile_constraints(
        self, constraints: list[ConstraintIR], steps: list[StepIR], blocks: BlockStructureIR
    ) -> list[ConstraintIR]:
        """Reconcile constraint targets.

        Args:
            constraints: List of constraint IRs
            steps: List of step IRs
            blocks: Block structure IR

        Returns:
            List of reconciled constraint IRs
        """
        step_ids = {step.step_id for step in steps}
        compact_to_step_id = {
            self._compact_step_id(step_id): step_id for step_id in step_ids
        }

        for constraint in constraints:
            if not constraint.targets:
                constraint.targets = ["global"]
                continue

            reconciled_targets: list[str] = []
            for target in constraint.targets:
                if not target.startswith("step:"):
                    reconciled_targets.append(target)
                    continue

                target_id = target.split(":", 1)[1]
                replacement = (
                    self._step_replacements.get(target_id)
                    or compact_to_step_id.get(target_id)
                    or target_id
                )
                reconciled_targets.append(f"step:{replacement}")
            constraint.targets = reconciled_targets
        return constraints
