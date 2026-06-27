"""Stage 7 repair slice for worker delegation resolution commands."""

from __future__ import annotations

import json
from dataclasses import replace

from nl2spl.compiler.spl_editing.intent.model import (
    ConvertDelegationToMainFlowStepIntentPayload,
    ConvertDelegationToRequestInputIntentPayload,
)
from nl2spl.compiler.spl_editing.stage_slices.errors import (
    StageAuthorityMismatchError,
    StageSliceValidationError,
)
from nl2spl.compiler.spl_editing.stage_slices.model import StageSliceInput
from nl2spl.compiler.spl_editing.stage_slices.result import StageSliceResult
from nl2spl.ir.step_ir import StepIR

_SLICE_ID = "stage7.worker_delegation_resolution_command_repair.v1"
_STAGE_AUTHORITY = "stage7.worker_step_plan"
_POLICY_ID = "worker_delegation.resolution_command.v1"


class Stage7WorkerDelegationResolutionCommandRepairSlice:
    """Materialize non-handoff delegation resolution commands."""

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
                f"Stage7 delegation resolution slice requires authority '{self.stage_authority}'."
            )
        if input_data.slice_id != self.slice_id:
            raise StageSliceValidationError(
                f"StageSliceInput slice_id '{input_data.slice_id}' does not match '{self.slice_id}'."
            )
        if input_data.snapshot.worker_step_plan is None:
            raise StageSliceValidationError("worker_step_plan is required.")
        if input_data.id_allocator is None:
            raise StageSliceValidationError("Stage7 delegation resolution slice requires id_allocator.")

        payload = input_data.intent.payload
        if isinstance(payload, ConvertDelegationToMainFlowStepIntentPayload):
            worker_id = payload.worker_id
            text = payload.action_text.strip()
            command_type = "GENERAL_COMMAND"
            outputs = tuple(payload.outputs)
            metadata_extra = {
                "resolution_kind": "converted_to_main_flow_step",
                "target_worker_promotion_ref_id": payload.target_worker_promotion_ref_id,
            }
        elif isinstance(payload, ConvertDelegationToRequestInputIntentPayload):
            worker_id = payload.worker_id
            text = payload.prompt_text.strip()
            if not payload.value_target.strip():
                raise StageSliceValidationError("value_target must not be empty.")
            command_type = "REQUEST_INPUT"
            outputs = tuple(payload.outputs) or (payload.value_target,)
            if payload.value_target not in outputs:
                outputs = outputs + (payload.value_target,)
            metadata_extra = {
                "resolution_kind": "converted_to_request_input",
                "target_worker_promotion_ref_id": payload.target_worker_promotion_ref_id,
                "value_target": payload.value_target,
            }
        else:
            raise StageSliceValidationError("Unsupported delegation resolution payload.")

        if not text:
            raise StageSliceValidationError("delegation resolution text must not be empty.")
        step_plan = input_data.snapshot.worker_step_plan
        if worker_id not in step_plan.worker_steps:
            raise StageSliceValidationError(f"Worker '{worker_id}' not found in worker_step_plan.")

        step_id = input_data.id_allocator.allocate_step_id()
        consumed_ref_ids = tuple(input_data.selected_ref_ids)
        metadata = {
            "origin": "user_confirmed_repair" if input_data.evidence_packet else "preview_repair",
            "materialization_authority": "stage3_5.worker_boundary + stage7.worker_step_plan",
            "materialization_plan_id": input_data.intent.materialization_plan_id or "",
            "consumed_selected_ref_ids": json.dumps(list(consumed_ref_ids)),
            "consumed_directive_id": input_data.directive.directive_id,
            "selected_ref_canonical_names": json.dumps(
                [ref.canonical_name for ref in input_data.refset.refs if ref.ref_id in consumed_ref_ids]
            ),
            **metadata_extra,
        }
        if input_data.evidence_packet is not None:
            metadata.update(
                {
                    "repair_patch_id": input_data.evidence_packet.repair_patch_id,
                    "related_diagnostic_id": input_data.evidence_packet.related_diagnostic_id,
                    "evidence_packet_id": input_data.evidence_packet.evidence_packet_id,
                    "user_text": input_data.evidence_packet.user_text,
                }
            )
        new_step = StepIR(
            step_id=step_id,
            text=text,
            source_span_ids=[],
            command_type=command_type,
            outputs=list(outputs),
            flow_ref="main",
            metadata=metadata,
        )
        worker_steps = {wid: list(steps) for wid, steps in step_plan.worker_steps.items()}
        worker_steps[worker_id] = worker_steps[worker_id] + [new_step]
        new_step_plan = replace(step_plan, worker_steps=worker_steps)

        return StageSliceResult(
            slice_id=self.slice_id,
            stage_authority=self.stage_authority,
            policy_id=input_data.stage_policy.policy_id,
            changed_artifact_refs=("worker_step_plan",),
            generated_construct_refs=(f"step:{worker_id}:{step_id}",),
            consumed_selected_ref_ids=consumed_ref_ids,
            consumed_directive_id=input_data.directive.directive_id,
            allocated_ids=(step_id,),
            trace={
                "action": "materialize",
                "worker_id": worker_id,
                "step_id": step_id,
                "command_family": command_type,
            },
            artifact_updates={"worker_step_plan": new_step_plan},
        )