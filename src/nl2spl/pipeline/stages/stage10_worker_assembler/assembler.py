"""Stage 10: WorkerAssembler - Assemble WorkerIR from IRs."""

from __future__ import annotations

import logging

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
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.stages.stage10_worker_assembler.block_utils import (
    BlockUtilsMixin,
)
from nl2spl.pipeline.stages.stage10_worker_assembler.child_worker_builder import (
    ChildWorkerBuilderMixin,
)
from nl2spl.pipeline.stages.stage10_worker_assembler.step_resolver import (
    StepResolverMixin,
)

logger = logging.getLogger(__name__)


class WorkerAssembler(
    BlockUtilsMixin,
    ChildWorkerBuilderMixin,
    StepResolverMixin,
):
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
                    spans=list(exc_flow.spans) if exc_flow.spans else [],
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
            steps=steps,
            scoped_steps=False,
            child_worker_refs=child_worker_refs,
            child_workers=child_workers,
        )

        return worker

    def _main_worker_spec(self, worker_plan: WorkerPlanIR | None) -> WorkerSpecIR | None:
        if worker_plan is None:
            return None
        return worker_plan.main_worker

    def _inputs_from_contract(self, fields: list[ContractFieldIR]) -> list[WorkerInput]:
        return [
            WorkerInput(
                name=field.name,
                requiredness=field.requiredness,
                required=field.required,
            )
            for field in fields
            if field.name
        ]

    def _outputs_from_contract(self, fields: list[ContractFieldIR]) -> list[WorkerOutput]:
        return [
            WorkerOutput(
                name=field.name,
                requiredness=field.requiredness,
                required=field.required,
            )
            for field in fields
            if field.name
        ]

    def assemble_from_worker_scoped(
        self,
        worker_step_plan: WorkerStepPlanIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        worker_plan: WorkerPlanIR,
        worker_flow_plan: WorkerFlowPlanIR | None = None,
        worker_block_plan: WorkerBlockPlanIR | None = None,
    ) -> WorkerIR:
        """Assemble WorkerIR from worker-scoped data.

        Directly consumes worker_step_plan instead of delegation_candidates.

        Args:
            worker_step_plan: Steps grouped by worker_id
            resources: Resource registry IR
            symbol_table: Symbol table
            worker_plan: Worker boundary plan
            worker_flow_plan: Optional flow structure per worker
            worker_block_plan: Optional block structure per worker

        Returns:
            WorkerIR with full child worker support
        """
        # Worker-aware path must provide flow and block plans for child worker
        # flow/steps to be assembled correctly.
        if worker_flow_plan is None or worker_block_plan is None:
            logger.warning(
                "assemble_from_worker_scoped called without worker_flow_plan or "
                "worker_block_plan; child worker flow/blocks will be incomplete"
            )

        main_spec = self._main_worker_spec(worker_plan)
        # 1. Build inputs/outputs from contract
        inputs = (
            self._inputs_from_contract(main_spec.input_contract)
            if main_spec is not None
            else [
                WorkerInput(name=v.name, required=v.required)
                for v in resources.variables
                if v.source == "input"
            ]
        )
        outputs = (
            self._outputs_from_contract(main_spec.output_contract)
            if main_spec is not None
            else [
                WorkerOutput(name=v.name, required=v.required)
                for v in resources.variables
                if v.source == "output"
            ]
        )

        # 2. Build main flow from worker-scoped blocks
        main_worker_id = worker_plan.main_worker_id
        main_blocks = (
            worker_block_plan.worker_blocks[main_worker_id].main_flow_blocks
            if worker_block_plan and main_worker_id in worker_block_plan.worker_blocks
            else []
        )

        # 2a. 当 main_flow_blocks 为空但存在 INVOKE/CALL_API 步骤时，
        # 注入合成 SEQUENTIAL_BLOCK，避免 INVOKE 步骤无块可渲染。
        main_steps = worker_step_plan.main_worker_steps
        main_blocks = self._ensure_renderable_blocks(
            main_blocks,
            main_steps,
            "b_main_fallback",
        )

        main_flow = FlowRef(blocks=main_blocks)

        # 3. Build alternative/exception flows for main worker
        main_flow_structure = (
            worker_flow_plan.worker_flows[main_worker_id]
            if worker_flow_plan and main_worker_id in worker_flow_plan.worker_flows
            else None
        )
        main_block_structure = (
            worker_block_plan.worker_blocks[main_worker_id]
            if worker_block_plan and main_worker_id in worker_block_plan.worker_blocks
            else None
        )

        alternative_flows: list[AlternativeFlowRef] = []
        if main_flow_structure:
            for alt_flow in main_flow_structure.alternative_flows:
                alt_blocks = (
                    main_block_structure.alternative_flow_blocks.get(alt_flow.flow_id, [])
                    if main_block_structure
                    else []
                )
                alternative_flows.append(
                    AlternativeFlowRef(
                        flow_id=alt_flow.flow_id,
                        condition_text=alt_flow.condition_text,
                        blocks=alt_blocks,
                    )
                )

        exception_flows: list[ExceptionFlowRef] = []
        if main_flow_structure:
            for exc_flow in main_flow_structure.exception_flows:
                exc_blocks = (
                    main_block_structure.exception_flow_blocks.get(exc_flow.flow_id, [])
                    if main_block_structure
                    else []
                )
                exception_flows.append(
                    ExceptionFlowRef(
                        flow_id=exc_flow.flow_id,
                        condition_text=exc_flow.condition_text,
                        blocks=exc_blocks,
                        spans=list(exc_flow.spans) if exc_flow.spans else [],
                    )
                )

        # 4. Build API refs from main worker steps
        api_refs = list({
            s.integration_ref
            for s in main_steps
            if s.command_type == "CALL_API" and s.integration_ref
        })

        # 5. Build child workers
        child_worker_refs: list[str] = []
        child_workers: list[ChildWorkerIR] = []
        for spec in self._child_worker_specs_from_plan(worker_plan):
            worker_id = spec.worker_id
            child_steps = worker_step_plan.worker_steps.get(worker_id, [])
            child_flow = worker_flow_plan.worker_flows.get(worker_id) if worker_flow_plan else None
            child_blocks = (
                worker_block_plan.worker_blocks.get(worker_id)
                if worker_block_plan
                else None
            )
            # Find invoke step text (matching legacy behavior)
            invoke_step = self._find_invoke_step_by_worker_name(main_steps, spec.worker_name)
            invoke_text = invoke_step.text if invoke_step else None
            child = self._build_child_worker(
                spec,
                child_steps,
                child_flow,
                child_blocks,
                invoke_text,
            )
            child_worker_refs.append(child.worker_name)
            child_workers.append(child)

        # 6. Build WorkerIR
        return WorkerIR(
            worker_name=main_spec.worker_name if main_spec is not None else "MainWorker",
            description=main_spec.purpose if main_spec is not None else "Main worker",
            inputs=inputs,
            outputs=outputs,
            main_flow=main_flow,
            alternative_flows=alternative_flows,
            exception_flows=exception_flows,
            api_refs=api_refs,
            steps=main_steps,
            scoped_steps=True,
            child_worker_refs=child_worker_refs,
            child_workers=child_workers,
        )
