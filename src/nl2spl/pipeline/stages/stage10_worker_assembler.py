"""Stage 10: WorkerAssembler - Assemble WorkerIR from IRs."""

from __future__ import annotations

import logging

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
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

logger = logging.getLogger(__name__)


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
        worker_by_id = {w.worker_id: w for w in worker_plan.workers}

        # 1. Build inputs/outputs from contract
        inputs = (
            self._inputs_from_contract(main_spec.input_contract)
            if main_spec is not None
            else [WorkerInput(name=v.name, required=v.required) for v in resources.variables if v.source == "input"]
        )
        outputs = (
            self._outputs_from_contract(main_spec.output_contract)
            if main_spec is not None
            else [WorkerOutput(name=v.name, required=v.required) for v in resources.variables if v.source == "output"]
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
        if not main_blocks:
            handoff_steps = [
                s for s in worker_step_plan.main_worker_steps
                if s.command_type in ("INVOKE_WORKER", "CALL_API")
            ]
            if handoff_steps:
                synthetic_block_id = "b_main_handoffs"
                main_blocks = [
                    BlockIR(
                        block_id=synthetic_block_id,
                        block_type="SEQUENTIAL",
                        spans=[sid for s in handoff_steps for sid in s.source_span_ids],
                    )
                ]
                for s in handoff_steps:
                    if not s.block_ref:
                        s.block_ref = synthetic_block_id

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
                    )
                )

        # 4. Build API refs from main worker steps
        main_steps = worker_step_plan.main_worker_steps
        api_refs = list({s.integration_ref for s in main_steps if s.command_type == "CALL_API" and s.integration_ref})

        # 5. Build child workers
        child_worker_refs: list[str] = []
        child_workers: list[ChildWorkerIR] = []
        main_steps = worker_step_plan.main_worker_steps
        for worker_id, spec in worker_by_id.items():
            if worker_id == main_worker_id or spec.kind == "main":
                continue
            # Only include workers that have steps (i.e., actually invoked)
            if worker_id not in worker_step_plan.worker_steps:
                continue
            child_steps = worker_step_plan.worker_steps[worker_id]
            child_flow = worker_flow_plan.worker_flows.get(worker_id) if worker_flow_plan else None
            child_blocks = worker_block_plan.worker_blocks.get(worker_id) if worker_block_plan else None
            # Find invoke step text (matching legacy behavior)
            invoke_step = self._find_invoke_step_by_worker_name(main_steps, spec.worker_name)
            invoke_text = invoke_step.text if invoke_step else None
            child = self._build_child_worker(spec, child_steps, child_flow, child_blocks, invoke_text)
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
            child_worker_refs=child_worker_refs,
            child_workers=child_workers,
        )

    def _build_child_worker(
        self,
        worker: WorkerSpecIR,
        steps: list[StepIR],
        flow: FlowStructureIR | None,
        blocks: BlockStructureIR | None,
        invoke_text: str | None = None,
    ) -> ChildWorkerIR:
        """Build a ChildWorkerIR with full flow and steps support.

        Args:
            worker: Worker specification
            steps: Child worker steps
            flow: Child worker flow structure (if available)
            blocks: Child worker block structure (if available)
            invoke_text: Invoke step text (if available), used as task_text

        Returns:
            ChildWorkerIR with complete flow information
        """
        # Build main flow
        main_flow = FlowRef(blocks=blocks.main_flow_blocks if blocks else [])

        # Build alternative flows — only flow is required; blocks are optional.
        # Condition text is known structured information even when handler blocks
        # are absent (partial SPL principle).
        alternative_flows: list[AlternativeFlowRef] = []
        if flow:
            for alt_flow in flow.alternative_flows:
                alt_blocks = (
                    blocks.alternative_flow_blocks.get(alt_flow.flow_id, [])
                    if blocks
                    else []
                )
                alternative_flows.append(
                    AlternativeFlowRef(
                        flow_id=alt_flow.flow_id,
                        condition_text=alt_flow.condition_text,
                        blocks=alt_blocks,
                    )
                )

        # Build exception flows — same principle: structure known conditions,
        # leave handler empty when missing.
        exception_flows: list[ExceptionFlowRef] = []
        if flow:
            for exc_flow in flow.exception_flows:
                exc_blocks = (
                    blocks.exception_flow_blocks.get(exc_flow.flow_id, [])
                    if blocks
                    else []
                )
                exception_flows.append(
                    ExceptionFlowRef(
                        flow_id=exc_flow.flow_id,
                        condition_text=exc_flow.condition_text,
                        blocks=exc_blocks,
                    )
                )

        # Collect API refs from steps
        api_refs = list({s.integration_ref for s in steps if s.command_type == "CALL_API" and s.integration_ref})

        # Use invoke step text if available (matches legacy behavior),
        # otherwise fall back to worker purpose or reason
        task_text = invoke_text or worker.purpose or worker.reason

        # Validate block-step consistency: each block must have at least one
        # matching step (via source_span_ids or block_ref), otherwise the
        # renderer will produce an empty block.
        step_span_ids: dict[str, list[StepIR]] = {}
        step_block_refs: dict[str, list[StepIR]] = {}
        for s in steps:
            for sid in s.source_span_ids:
                step_span_ids.setdefault(sid, []).append(s)
            if s.block_ref:
                step_block_refs.setdefault(s.block_ref, []).append(s)

        for block in (blocks.main_flow_blocks if blocks else []):
            has_match = any(
                span_id in step_span_ids for span_id in block.spans
            ) or block.block_id in step_block_refs
            if not has_match:
                logger.warning(
                    "Child worker %s block %s has no matching steps "
                    "(spans=%s, block_refs=%s)",
                    worker.worker_name,
                    block.block_id,
                    block.spans,
                    list(step_block_refs.keys()),
                )

        return ChildWorkerIR(
            worker_name=worker.worker_name,
            description=worker.purpose or worker.reason,
            task_text=task_text,
            inputs=self._inputs_from_contract(worker.input_contract),
            outputs=self._outputs_from_contract(worker.output_contract),
            main_flow=main_flow,
            alternative_flows=alternative_flows,
            exception_flows=exception_flows,
            api_refs=api_refs,
            steps=steps,
        )
