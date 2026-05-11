"""Stage 10: WorkerAssembler - Assemble WorkerIR from IRs."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import (
    AlternativeFlowRef,
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerInput,
    WorkerIR,
    WorkerOutput,
)
from nl2spl.ir.worker_plan_ir import ContractFieldIR, WorkerPlanIR, WorkerSpecIR


class WorkerAssembler:
    """Worker assembly (code logic).

    This stage assembles all IRs into a WorkerIR that represents
    the complete SPL worker structure.
    """

    def assemble(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        steps: list[StepIR],
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        worker_plan: WorkerPlanIR | None = None,
    ) -> WorkerIR:
        """Assemble WorkerIR from IRs.

        Args:
            flow: Flow structure IR
            blocks: Block structure IR
            steps: List of step IRs
            resources: Resource registry IR
            symbol_table: Symbol table

        Returns:
            WorkerIR object
        """
        main_spec = self._main_worker_spec(worker_plan)

        # 1. Build inputs
        inputs = (
            self._inputs_from_contract(main_spec.input_contract)
            if main_spec is not None
            else [
                WorkerInput(name=var.name, required=var.required)
                for var in resources.variables
                if var.source == "input"
            ]
        )

        # 2. Build outputs
        outputs = (
            self._outputs_from_contract(main_spec.output_contract)
            if main_spec is not None
            else [
                WorkerOutput(name=var.name, required=var.required)
                for var in resources.variables
                if var.source == "output"
            ]
        )

        # 3. Build main flow
        main_flow = FlowRef(blocks=blocks.main_flow_blocks)

        # 4. Build alternative flows
        alternative_flows = []
        for alt_flow in flow.alternative_flows:
            alt_blocks = blocks.alternative_flow_blocks.get(alt_flow.flow_id, [])
            alternative_flows.append(
                AlternativeFlowRef(
                    flow_id=alt_flow.flow_id,
                    condition_text=alt_flow.condition_text,
                    blocks=alt_blocks,
                )
            )

        # 5. Build exception flows
        exception_flows = []
        for exc_flow in flow.exception_flows:
            exc_blocks = blocks.exception_flow_blocks.get(exc_flow.flow_id, [])
            exception_flows.append(
                ExceptionFlowRef(
                    flow_id=exc_flow.flow_id,
                    condition_text=exc_flow.condition_text,
                    blocks=exc_blocks,
                )
            )

        # 6. Build API refs
        api_refs = [a.api_name for a in resources.apis]

        # 7. Build child worker refs. WorkerPlanIR has priority; legacy
        # delegation_candidates remain only as a compatibility bridge.
        if worker_plan is not None:
            child_worker_refs, child_workers = self._child_workers_from_plan(
                worker_plan,
                steps,
            )
        else:
            child_worker_refs, child_workers = self._child_workers_from_delegation(
                flow,
                steps,
                resources,
            )

        # 8. Build WorkerIR
        worker = WorkerIR(
            worker_name=main_spec.worker_name if main_spec is not None else "MainWorker",
            description=main_spec.purpose if main_spec is not None else "Main worker",
            inputs=inputs,
            outputs=outputs,
            main_flow=main_flow,
            alternative_flows=alternative_flows,
            exception_flows=exception_flows,
            api_refs=api_refs,
            child_worker_refs=child_worker_refs,
            child_workers=child_workers,
        )

        return worker

    def _main_worker_spec(self, worker_plan: WorkerPlanIR | None) -> WorkerSpecIR | None:
        if worker_plan is None:
            return None
        return next(
            (
                worker
                for worker in worker_plan.workers
                if worker.worker_id == worker_plan.main_worker_id and worker.kind == "main"
            ),
            None,
        )

    def _inputs_from_contract(self, fields: list[ContractFieldIR]) -> list[WorkerInput]:
        return [WorkerInput(field.name, field.required) for field in fields]

    def _outputs_from_contract(self, fields: list[ContractFieldIR]) -> list[WorkerOutput]:
        return [WorkerOutput(field.name, field.required) for field in fields]

    def _child_workers_from_plan(
        self,
        worker_plan: WorkerPlanIR,
        steps: list[StepIR],
    ) -> tuple[list[str], list[ChildWorkerIR]]:
        worker_by_id = {worker.worker_id: worker for worker in worker_plan.workers}
        invoked_worker_ids = [
            handoff.to_worker
            for handoff in worker_plan.handoffs
            if handoff.mode == "invoke"
            and handoff.to_worker in worker_by_id
            and worker_by_id[handoff.to_worker].kind != "main"
        ]

        child_worker_refs: list[str] = []
        child_workers: list[ChildWorkerIR] = []
        for worker_id in dict.fromkeys(invoked_worker_ids):
            if worker_id is None:
                continue
            spec = worker_by_id[worker_id]
            invoke_step = self._find_invoke_step_by_worker_name(steps, spec.worker_name)
            child_worker_refs.append(spec.worker_name)
            child_workers.append(
                ChildWorkerIR(
                    worker_name=spec.worker_name,
                    description=spec.purpose or spec.reason,
                    task_text=invoke_step.text if invoke_step else spec.purpose or spec.reason,
                    inputs=self._inputs_from_contract(spec.input_contract),
                    outputs=self._outputs_from_contract(spec.output_contract),
                )
            )

        return child_worker_refs, child_workers

    def _child_workers_from_delegation(
        self,
        flow: FlowStructureIR,
        steps: list[StepIR],
        resources: ResourceRegistryIR,
    ) -> tuple[list[str], list[ChildWorkerIR]]:
        child_worker_refs = []
        child_workers = []
        for candidate in flow.delegation_candidates:
            if candidate.suggested_type == "child_worker":
                worker_name = self._child_worker_name(candidate.candidate_id)
                child_worker_refs.append(worker_name)
                invoke_step = self._find_invoke_step_for_candidate(steps, candidate.spans)
                input_names = invoke_step.inputs if invoke_step else candidate.input_variables
                output_names = invoke_step.outputs if invoke_step else candidate.output_variables
                task_text = invoke_step.text if invoke_step else candidate.reason
                child_workers.append(
                    ChildWorkerIR(
                        worker_name=worker_name,
                        description=candidate.reason,
                        task_text=task_text,
                        inputs=[
                            WorkerInput(name=name, required=self._is_required(resources, name))
                            for name in input_names
                        ],
                        outputs=[
                            WorkerOutput(name=name, required=self._is_required(resources, name))
                            for name in output_names
                        ],
                    )
                )
        return child_worker_refs, child_workers

    def _child_worker_name(self, candidate_id: str) -> str:
        """Return the concrete child worker name for a delegation candidate."""
        return f"child_{candidate_id}"

    def _find_invoke_step_for_candidate(
        self,
        steps: list[StepIR],
        candidate_spans: list[str],
    ) -> StepIR | None:
        """Find the INVOKE_WORKER step backed by the delegation candidate."""
        candidate_span_set = set(candidate_spans)
        for step in steps:
            if step.command_type != "INVOKE_WORKER":
                continue
            if candidate_span_set.intersection(step.source_span_ids):
                return step
        return None

    def _find_invoke_step_by_worker_name(
        self,
        steps: list[StepIR],
        worker_name: str,
    ) -> StepIR | None:
        for step in steps:
            if step.command_type == "INVOKE_WORKER" and step.integration_ref == worker_name:
                return step
        return None

    def _is_required(self, resources: ResourceRegistryIR, variable_name: str) -> bool:
        """Look up a variable's required flag."""
        for variable in resources.variables:
            if variable.name == variable_name:
                return variable.required
        return True
