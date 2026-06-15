"""Child worker building methods for Stage 10 WorkerAssembler."""

from __future__ import annotations

import logging

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import (
    AlternativeFlowRef,
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerInput,
    WorkerOutput,
)
from nl2spl.ir.worker_plan_ir import (
    WorkerPlanIR,
    WorkerSpecIR,
)

logger = logging.getLogger(__name__)


class ChildWorkerBuilderMixin:
    """Mixin class containing child worker building methods for WorkerAssembler."""

    def _child_workers_from_plan(
        self,
        worker_plan: WorkerPlanIR,
        steps: list[StepIR],
    ) -> tuple[list[str], list[ChildWorkerIR]]:
        child_worker_refs: list[str] = []
        child_workers: list[ChildWorkerIR] = []
        for spec in self._child_worker_specs_from_plan(worker_plan):
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

    def _child_worker_specs_from_plan(
        self,
        worker_plan: WorkerPlanIR,
    ) -> list[WorkerSpecIR]:
        """Return renderable non-main worker specs from WorkerPlanIR.

        Worker definitions are a separate lifecycle from invocation readiness:
        a source-backed partial child worker must render even when no executable
        handoff step exists yet. Empty shells with no responsibility stay out.
        """
        main_worker_id = worker_plan.main_worker_id
        specs: list[WorkerSpecIR] = []
        seen_names: set[str] = set()
        for spec in worker_plan.workers:
            if spec.worker_id == main_worker_id or spec.kind == "main":
                continue
            if not self._has_worker_responsibility(spec):
                continue
            if spec.worker_name in seen_names:
                continue
            seen_names.add(spec.worker_name)
            specs.append(spec)
        return specs

    @staticmethod
    def _has_worker_responsibility(worker: WorkerSpecIR) -> bool:
        return bool(worker.purpose or worker.reason or worker.owned_span_ids)

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
        main_blocks = blocks.main_flow_blocks if blocks else []
        coverage_blocks = self._all_blocks(blocks)
        main_blocks = self._ensure_renderable_blocks(
            main_blocks,
            steps,
            f"b_{worker.worker_id}_fallback",
            coverage_blocks=coverage_blocks,
        )
        main_flow = FlowRef(blocks=main_blocks)

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
                        spans=list(exc_flow.spans) if exc_flow.spans else [],
                    )
                )

        # Collect API refs from steps
        api_refs = list({
            s.integration_ref
            for s in steps
            if s.command_type == "CALL_API" and s.integration_ref
        })

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
