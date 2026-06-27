"""Stage 7 repair slice for exception handler command materialization."""

from __future__ import annotations

import json
from dataclasses import replace

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

_SLICE_ID = "stage7.exception_handler_command_repair.v1"
_STAGE_AUTHORITY = "stage7.worker_step_plan"
_POLICY_ID = "exception_handler.command_intent.v1"
_STAGE5_BLOCK_SLICE_ID = "stage5.exception_handler_block_repair.v1"
_ALLOWED_COMMAND_FAMILIES = {"GENERAL_COMMAND", "REQUEST_INPUT", "DISPLAY_MESSAGE"}


class Stage7ExceptionHandlerCommandRepairSlice:
    """Materialize a handler command inside a Stage5-provided block."""

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
                f"Stage7 handler command slice requires authority '{self.stage_authority}'."
            )
        if input_data.slice_id != self.slice_id:
            raise StageSliceValidationError(
                f"StageSliceInput slice_id '{input_data.slice_id}' does not match '{self.slice_id}'."
            )
        if input_data.target.irs_ref.construct_type != "EXCEPTION_FLOW":
            raise StageSliceValidationError("Stage7 handler command target must be EXCEPTION_FLOW.")
        if input_data.target.irs_ref.slot_name != "handler_action":
            raise StageSliceValidationError("Stage7 handler command target slot must be handler_action.")
        worker_id = input_data.target.worker_id or ""
        flow_id = input_data.target.canonical_name or ""
        if not worker_id:
            raise StageSliceValidationError("RepairTarget.worker_id is required.")
        if not flow_id:
            raise StageSliceValidationError("RepairTarget.canonical_name is required.")
        if input_data.snapshot.worker_step_plan is None:
            raise StageSliceValidationError("worker_step_plan is required.")
        if input_data.id_allocator is None:
            raise StageSliceValidationError("Stage7 handler command slice requires id_allocator.")

        block_id = self._handler_block_id(input_data)
        command_plan = self._resolve_command_plan(input_data)
        selected_refs = self._resolve_selected_refs(input_data, command_plan.selected_ref_ids)
        input_names = tuple(ref.canonical_name for ref in selected_refs)

        command_family = command_plan.command_family
        if command_family == "REQUEST_INPUT":
            if command_plan.selected_ref_ids:
                raise StageSliceValidationError("REQUEST_INPUT handler command must not consume input refs.")
            if not command_plan.output_intent or not command_plan.output_intent.strip():
                raise StageSliceValidationError("REQUEST_INPUT handler command requires output_intent.")
        elif command_family == "DISPLAY_MESSAGE" and command_plan.selected_ref_ids:
            raise StageSliceValidationError("DISPLAY_MESSAGE handler command must not consume input refs.")

        step_id = input_data.id_allocator.allocate_step_id()
        metadata = {
            "origin": "user_confirmed_repair" if input_data.evidence_packet else "preview_repair",
            "materialization_authority": self.stage_authority,
            "materialization_plan_id": input_data.intent.materialization_plan_id or "",
            "consumed_selected_ref_ids": json.dumps(list(command_plan.selected_ref_ids)),
            "consumed_directive_id": input_data.directive.directive_id,
            "handler_block_id": block_id,
            "selected_ref_canonical_names": json.dumps(list(input_names)),
            "target_exception_flow_ref_id": getattr(input_data.intent.payload, "target_exception_flow_ref_id", ""),
            "target_exception_flow_id": flow_id,
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
            command_type=command_family,
            inputs=list(input_names) if command_family == "GENERAL_COMMAND" else [],
            outputs=[command_plan.output_intent] if command_family == "REQUEST_INPUT" else [],
            flow_ref=flow_id,
            block_ref=block_id,
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
                "flow_id": flow_id,
                "block_id": block_id,
                "step_id": step_id,
                "command_family": command_family,
            },
            artifact_updates={"worker_step_plan": updated_step_plan},
        )

    def _handler_block_id(self, input_data: StageSliceInput) -> str:
        for result in input_data.upstream_stage_results:
            if getattr(result, "slice_id", "") == _STAGE5_BLOCK_SLICE_ID:
                block_id = getattr(result, "trace", {}).get("block_id", "")
                if isinstance(block_id, str) and block_id.strip():
                    return block_id
        raise StageSliceValidationError("Stage7 handler command requires Stage5 handler block result.")

    def _resolve_command_plan(self, input_data: StageSliceInput) -> CommandIntentPlan:
        if self._directive_requests_request_input(input_data.directive.requested_behavior or ""):
            if input_data.typed_plan is None:
                raise StageSliceValidationError(
                    "REQUEST_INPUT directive requires a validated CommandIntentPlan."
                )
        if input_data.typed_plan is None:
            goal = getattr(input_data.intent.payload, "handler_goal", "") or "Handle exception"
            return CommandIntentPlan(
                command_family="GENERAL_COMMAND",
                user_facing_text=str(goal),
                selected_ref_ids=input_data.selected_ref_ids,
            )
        TypedPlanValidator().validate(input_data.typed_plan)
        if not isinstance(input_data.typed_plan, CommandIntentPlan):
            raise StageSliceValidationError("Stage7 handler command typed_plan must be CommandIntentPlan.")
        if input_data.typed_plan.command_family not in _ALLOWED_COMMAND_FAMILIES:
            raise StageSliceValidationError(
                f"Unsupported handler command_family '{input_data.typed_plan.command_family}'."
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

    def _directive_requests_request_input(self, behavior: str) -> bool:
        normalized = behavior.casefold()
        return any(token in normalized for token in ("request input", "ask user", "request_input"))
