"""Stage 7 repair slice for required-output producer command materialization."""

from __future__ import annotations

import json
from dataclasses import replace

from nl2spl.compiler.spl_editing.intent.model import InsertProducerStepIntentPayload
from nl2spl.compiler.spl_editing.stage_slices.errors import (
    StageAuthorityMismatchError,
    StageSliceValidationError,
)
from nl2spl.compiler.spl_editing.stage_slices.model import StageSliceInput
from nl2spl.compiler.spl_editing.stage_slices.result import StageSliceResult
from nl2spl.compiler.spl_editing.stage_slices.typed_plan import (
    CommandIntentPlan,
    TypedPlanValidator,
)
from nl2spl.ir.step_ir import StepIR

_SLICE_ID = "stage7.required_output_producer_command_repair.v1"
_STAGE_AUTHORITY = "stage7.worker_step_plan"
_POLICY_ID = "required_output.producer_command.v1"
_ALLOWED_COMMAND_FAMILIES = {"GENERAL_COMMAND"}


class Stage7RequiredOutputProducerCommandRepairSlice:
    """Materialize the producer command for a REQUIRED_OUTPUT.producer slot."""

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
                f"Stage7 producer slice requires authority '{self.stage_authority}'."
            )
        if input_data.slice_id != self.slice_id:
            raise StageSliceValidationError(
                f"StageSliceInput slice_id '{input_data.slice_id}' does not match '{self.slice_id}'."
            )
        target_irs = getattr(input_data.target, "irs_ref", None)
        target_construct_type = getattr(
            target_irs,
            "construct_type",
            input_data.intent.target_construct_type,
        )
        target_slot_name = getattr(
            target_irs,
            "slot_name",
            input_data.intent.target_slot_name,
        )
        if target_construct_type != "REQUIRED_OUTPUT":
            raise StageSliceValidationError("Stage7 producer target must be REQUIRED_OUTPUT.")
        if target_slot_name != "producer":
            raise StageSliceValidationError("Stage7 producer target slot must be producer.")
        if not isinstance(input_data.intent.payload, InsertProducerStepIntentPayload):
            raise StageSliceValidationError("Stage7 producer requires InsertProducerStepIntentPayload.")
        if input_data.snapshot.worker_step_plan is None:
            raise StageSliceValidationError("worker_step_plan is required.")
        if input_data.id_allocator is None:
            raise StageSliceValidationError("Stage7 producer slice requires id_allocator.")

        worker_id = input_data.target.worker_id or ""
        output_name = input_data.target.canonical_name or ""
        if not worker_id:
            raise StageSliceValidationError("RepairTarget.worker_id is required.")
        if not output_name:
            raise StageSliceValidationError("RepairTarget.canonical_name is required.")
        if worker_id not in input_data.snapshot.worker_step_plan.worker_steps:
            raise StageSliceValidationError(
                f"Target worker '{worker_id}' not found in worker_step_plan.worker_steps."
            )

        command_plan = self._resolve_command_plan(input_data)
        selected_refs = self._resolve_selected_refs(input_data, command_plan.selected_ref_ids)
        input_names = tuple(ref.canonical_name for ref in selected_refs)
        warnings: list[str] = []
        if not command_plan.selected_ref_ids:
            warnings.append("no_selected_inputs")

        step_id = input_data.id_allocator.allocate_step_id()
        metadata = {
            "origin": "user_confirmed_repair" if input_data.evidence_packet else "preview_repair",
            "materialization_authority": self.stage_authority,
            "materialization_plan_id": input_data.intent.materialization_plan_id or "",
            "consumed_selected_ref_ids": json.dumps(list(command_plan.selected_ref_ids)),
            "consumed_directive_id": input_data.directive.directive_id,
            "selected_ref_canonical_names": json.dumps(list(input_names)),
            "target_output_ref_id": getattr(input_data.intent.payload, "target_output_ref_id", ""),
            "target_output_name": output_name,
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

        step = StepIR(
            step_id=step_id,
            text=command_plan.user_facing_text,
            source_span_ids=[],
            command_type=command_plan.command_family,
            inputs=list(input_names),
            outputs=[output_name],
            flow_ref="main",
            metadata=metadata,
        )

        step_plan = input_data.snapshot.worker_step_plan
        worker_steps = {wid: list(steps) for wid, steps in step_plan.worker_steps.items()}
        worker_steps[worker_id] = worker_steps.get(worker_id, []) + [step]
        updated_step_plan = replace(step_plan, worker_steps=worker_steps)

        return StageSliceResult(
            slice_id=self.slice_id,
            stage_authority=self.stage_authority,
            policy_id=input_data.stage_policy.policy_id,
            changed_artifact_refs=("worker_step_plan",),
            generated_construct_refs=(f"step:{worker_id}:{step_id}",),
            consumed_selected_ref_ids=tuple(command_plan.selected_ref_ids),
            consumed_directive_id=input_data.directive.directive_id,
            allocated_ids=(step_id,),
            trace={
                "action": "materialize",
                "worker_id": worker_id,
                "target_output_name": output_name,
                "step_id": step_id,
                "command_family": command_plan.command_family,
                "warnings": tuple(warnings),
            },
            artifact_updates={"worker_step_plan": updated_step_plan},
        )

    def _resolve_command_plan(self, input_data: StageSliceInput) -> CommandIntentPlan:
        payload = input_data.intent.payload
        if input_data.typed_plan is None:
            producer_goal = getattr(payload, "producer_goal", "") or "Produce required output"
            if not str(producer_goal).strip():
                raise StageSliceValidationError("producer_goal must not be empty.")
            normalized_goal = str(producer_goal).casefold()
            if "<ref" in normalized_goal or "</ref" in normalized_goal:
                raise StageSliceValidationError(
                    "producer_goal must not contain <REF or </REF tokens; use canonical ref names directly."
                )
            return CommandIntentPlan(
                command_family="GENERAL_COMMAND",
                user_facing_text=str(producer_goal).strip(),
                selected_ref_ids=input_data.selected_ref_ids,
                output_intent=input_data.target.canonical_name or "",
            )
        TypedPlanValidator().validate(input_data.typed_plan)
        if not isinstance(input_data.typed_plan, CommandIntentPlan):
            raise StageSliceValidationError("Stage7 producer typed_plan must be CommandIntentPlan.")
        if input_data.typed_plan.command_family not in _ALLOWED_COMMAND_FAMILIES:
            raise StageSliceValidationError(
                f"Unsupported producer command_family '{input_data.typed_plan.command_family}'."
            )
        return input_data.typed_plan

    def _resolve_selected_refs(self, input_data: StageSliceInput, ref_ids: tuple[str, ...]):
        by_id = {ref.ref_id: ref for ref in input_data.refset.refs}
        resolved = []
        for ref_id in ref_ids:
            ref = by_id.get(ref_id)
            if ref is None:
                raise StageSliceValidationError(f"Unknown selected ref id '{ref_id}'.")
            if ref.ref_role != "selectable_input":
                raise StageSliceValidationError(f"Selected ref '{ref_id}' is not selectable_input.")
            resolved.append(ref)
        return tuple(resolved)