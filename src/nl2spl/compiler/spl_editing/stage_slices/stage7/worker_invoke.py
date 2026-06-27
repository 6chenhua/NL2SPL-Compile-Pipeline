"""Stage 7 repair slice for worker invoke command materialization."""

from __future__ import annotations

import json
from dataclasses import replace

from nl2spl.compiler.spl_editing.intent.model import CreateWorkerHandoffContractIntentPayload
from nl2spl.compiler.spl_editing.stage_slices.errors import (
    StageAuthorityMismatchError,
    StageSliceValidationError,
)
from nl2spl.compiler.spl_editing.stage_slices.model import StageSliceInput
from nl2spl.compiler.spl_editing.stage_slices.result import StageSliceResult
from nl2spl.ir.step_ir import StepIR

_SLICE_ID = "stage7.worker_invoke_command_repair.v1"
_STAGE_AUTHORITY = "stage7.worker_step_plan"
_POLICY_ID = "worker_delegation.invoke_worker_command.v1"
_STAGE35_HANDOFF_SLICE_ID = "stage3_5.worker_handoff_contract_repair.v1"


class Stage7WorkerInvokeCommandRepairSlice:
    """Materialize the parent INVOKE_WORKER step for a worker handoff."""

    @property
    def slice_id(self) -> str:
        return _SLICE_ID

    @property
    def stage_authority(self) -> str:
        return _STAGE_AUTHORITY

    @property
    def policy_id(self) -> str:
        return _POLICY_ID

    @property
    def output_artifacts(self) -> tuple[str, ...]:
        return ("WorkerStepPlanIR",)

    @property
    def write_layers(self) -> tuple[str, ...]:
        return ("worker_step_plan_pre_normalize",)

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        if input_data.stage_authority != self.stage_authority:
            raise StageAuthorityMismatchError(
                f"Stage7 invoke slice requires authority '{self.stage_authority}'."
            )
        if input_data.slice_id != self.slice_id:
            raise StageSliceValidationError(
                f"StageSliceInput slice_id mismatch: '{input_data.slice_id}' != '{self.slice_id}'."
            )
        payload = input_data.intent.payload
        if not isinstance(payload, CreateWorkerHandoffContractIntentPayload):
            raise StageSliceValidationError(
                "Stage7 invoke slice requires CreateWorkerHandoffContractIntentPayload."
            )
        if input_data.snapshot.worker_step_plan is None:
            raise StageSliceValidationError("worker_step_plan is required.")
        if input_data.id_allocator is None:
            raise StageSliceValidationError("Stage7 invoke slice requires id_allocator.")

        handoff_result = self._handoff_result(input_data)
        handoff_id = handoff_result.trace["handoff_id"]
        parent_id = payload.parent_worker_id
        child_id = payload.child_worker_id
        child_name = child_id
        worker_plan = input_data.snapshot.worker_plan
        if worker_plan is not None:
            for worker in worker_plan.workers:
                if worker.worker_id == child_id:
                    child_name = worker.worker_name
                    break
        step_plan = input_data.snapshot.worker_step_plan
        if parent_id not in step_plan.worker_steps:
            raise StageSliceValidationError(f"Parent worker '{parent_id}' has no step list.")

        invoke_inputs = [parent for parent, _child in payload.input_bindings]
        invoke_outputs = [parent for _child, parent in payload.output_bindings]
        consumed_ref_ids = tuple(input_data.selected_ref_ids)
        step_metadata = {
            "origin": "user_confirmed_repair" if input_data.evidence_packet else "preview_repair",
            "materialization_authority": "stage3_5.worker_boundary + stage7.worker_step_plan",
            "materialization_plan_id": input_data.intent.materialization_plan_id or "",
            "consumed_selected_ref_ids": json.dumps(list(consumed_ref_ids)),
            "consumed_directive_id": input_data.directive.directive_id,
            "selected_ref_canonical_names": json.dumps(
                [
                    ref.canonical_name
                    for ref in input_data.refset.refs
                    if ref.ref_id in consumed_ref_ids
                ]
            ),
            "target_worker_promotion_ref_id": payload.target_worker_promotion_ref_id,
            "handoff_id": handoff_id,
        }
        if input_data.evidence_packet is not None:
            step_metadata.update(
                {
                    "repair_patch_id": input_data.evidence_packet.repair_patch_id,
                    "related_diagnostic_id": input_data.evidence_packet.related_diagnostic_id,
                    "evidence_packet_id": input_data.evidence_packet.evidence_packet_id,
                    "user_text": input_data.evidence_packet.user_text,
                }
            )

        worker_steps = {wid: list(steps) for wid, steps in step_plan.worker_steps.items()}
        parent_steps = list(worker_steps[parent_id])
        existing_index = self._matching_invoke_step_index(
            parent_steps,
            child_name=child_name,
            invoke_inputs=invoke_inputs,
            invoke_outputs=invoke_outputs,
        )
        allocated_ids: tuple[str, ...]
        action = "materialize"
        if existing_index is None:
            step_id = input_data.id_allocator.allocate_step_id()
            invoke_step = StepIR(
                step_id=step_id,
                text=f"Invoke worker: {child_name}",
                source_span_ids=[],
                command_type="INVOKE_WORKER",
                inputs=invoke_inputs,
                outputs=invoke_outputs,
                integration_ref=child_name,
                flow_ref=payload.invocation_point,
                block_ref="b_main_fallback",
                handoff_id=handoff_id,
                metadata=step_metadata,
            )
            parent_steps.append(invoke_step)
            allocated_ids = (step_id,)
        else:
            existing = parent_steps[existing_index]
            step_id = existing.step_id
            merged_metadata = {**existing.metadata, **step_metadata}
            parent_steps[existing_index] = replace(
                existing,
                inputs=invoke_inputs,
                outputs=invoke_outputs,
                integration_ref=child_name,
                flow_ref=payload.invocation_point,
                block_ref=existing.block_ref or "b_main_fallback",
                handoff_id=handoff_id,
                metadata=merged_metadata,
            )
            allocated_ids = ()
            action = "bind_existing"
        worker_steps[parent_id] = parent_steps
        new_step_plan = replace(step_plan, worker_steps=worker_steps)

        return StageSliceResult(
            slice_id=self.slice_id,
            stage_authority=self.stage_authority,
            policy_id=input_data.stage_policy.policy_id,
            changed_artifact_refs=("worker_step_plan",),
            generated_construct_refs=(f"step:{parent_id}:{step_id}",),
            consumed_selected_ref_ids=consumed_ref_ids,
            consumed_directive_id=input_data.directive.directive_id,
            allocated_ids=allocated_ids,
            trace={
                "action": action,
                "parent_worker_id": parent_id,
                "child_worker_id": child_id,
                "handoff_id": handoff_id,
                "step_id": step_id,
                "command_family": "INVOKE_WORKER",
            },
            artifact_updates={"worker_step_plan": new_step_plan},
        )

    @staticmethod
    def _matching_invoke_step_index(
        steps: list[StepIR],
        *,
        child_name: str,
        invoke_inputs: list[str],
        invoke_outputs: list[str],
    ) -> int | None:
        for index, step in enumerate(steps):
            if step.command_type != "INVOKE_WORKER":
                continue
            if step.integration_ref and step.integration_ref != child_name:
                continue
            if list(step.inputs) != invoke_inputs:
                continue
            if list(step.outputs) != invoke_outputs:
                continue
            return index
        return None

    def _handoff_result(self, input_data: StageSliceInput):
        for result in input_data.upstream_stage_results:
            if getattr(result, "slice_id", "") == _STAGE35_HANDOFF_SLICE_ID:
                handoff_id = getattr(result, "trace", {}).get("handoff_id", "")
                if isinstance(handoff_id, str) and handoff_id.strip():
                    return result
        raise StageSliceValidationError("Stage7 invoke slice requires Stage3.5 handoff result.")
