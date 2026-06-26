"""Materializer for worker handoff contract repair."""

from __future__ import annotations

import json
from dataclasses import replace

from nl2spl.compiler.spl_editing.core.model import RepairEvidenceRef
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent, RevisionToken
from nl2spl.compiler.spl_editing.intent.model import (
    ConvertDelegationToMainFlowStepIntentPayload,
    ConvertDelegationToRequestInputIntentPayload,
    CreateWorkerHandoffContractIntentPayload,
)
from nl2spl.compiler.spl_editing.materialization.errors import DependencyClosureValidationError
from nl2spl.compiler.spl_editing.materialization.model import (
    MaterializationInput,
    MaterializationResult,
)
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_contract_status import derive_handoff_materialization_status
from nl2spl.ir.worker_plan_ir import (
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerHandoffIR,
)

_MATERIALIZER_ID = "worker_handoff.contract_repair.v1"
_STAGE_AUTHORITY = "stage3_5.worker_boundary + stage7.worker_step_plan"


class WorkerHandoffContractMaterializer:
    """Materialize a worker handoff and its parent INVOKE_WORKER step."""

    @property
    def materializer_id(self) -> str:
        return _MATERIALIZER_ID

    @property
    def stage_authority(self) -> str:
        return _STAGE_AUTHORITY

    def materialize(self, input_data: MaterializationInput) -> MaterializationResult:
        intent = input_data.intent
        payload = intent.payload
        if isinstance(payload, ConvertDelegationToMainFlowStepIntentPayload):
            return self._materialize_main_flow_step(input_data, payload)
        if isinstance(payload, ConvertDelegationToRequestInputIntentPayload):
            return self._materialize_request_input_step(input_data, payload)
        if not isinstance(payload, CreateWorkerHandoffContractIntentPayload):
            raise DependencyClosureValidationError(
                "WorkerHandoffContractMaterializer requires a worker-promotion "
                f"intent payload but received {type(payload).__name__!r}."
            )

        snapshot = input_data.snapshot
        evidence_packet = input_data.evidence_packet
        worker_plan = snapshot.worker_plan
        step_plan = snapshot.worker_step_plan
        if worker_plan is None:
            raise DependencyClosureValidationError("worker_plan is missing from snapshot.")
        if step_plan is None:
            raise DependencyClosureValidationError("worker_step_plan is missing from snapshot.")

        parent_id = payload.parent_worker_id
        child_id = payload.child_worker_id
        worker_ids = {w.worker_id for w in worker_plan.workers}
        if parent_id not in worker_ids:
            raise DependencyClosureValidationError(f"Parent worker '{parent_id}' not found.")
        if child_id not in worker_ids:
            raise DependencyClosureValidationError(f"Child worker '{child_id}' not found.")
        if parent_id not in step_plan.worker_steps:
            raise DependencyClosureValidationError(f"Parent worker '{parent_id}' has no step list.")

        if payload.invocation_point not in ("main", "alternative", "exception"):
            raise DependencyClosureValidationError(
                f"Invalid invocation_point '{payload.invocation_point}'."
            )
        valid_status = {"known_present", "known_empty"}
        if payload.input_binding_status not in valid_status:
            raise DependencyClosureValidationError(
                f"Invalid input_binding_status '{payload.input_binding_status}'."
            )
        if payload.output_binding_status not in valid_status:
            raise DependencyClosureValidationError(
                f"Invalid output_binding_status '{payload.output_binding_status}'."
            )
        if payload.input_binding_status == "known_present" and not payload.input_bindings:
            raise DependencyClosureValidationError(
                "known_present input bindings require at least one binding."
            )
        if payload.output_binding_status == "known_present" and not payload.output_bindings:
            raise DependencyClosureValidationError(
                "known_present output bindings require at least one binding."
            )
        if payload.input_binding_status == "known_empty" and payload.input_bindings:
            raise DependencyClosureValidationError("known_empty input bindings must be empty.")
        if payload.output_binding_status == "known_empty" and payload.output_bindings:
            raise DependencyClosureValidationError("known_empty output bindings must be empty.")

        child_name = child_id
        for worker in worker_plan.workers:
            if worker.worker_id == child_id:
                child_name = worker.worker_name
                break

        existing_invoke_index = None
        parent_steps = list(step_plan.worker_steps[parent_id])
        for idx, step in enumerate(parent_steps):
            if getattr(step, "command_type", "") != "INVOKE_WORKER":
                continue
            integration_ref = getattr(step, "integration_ref", "") or ""
            step_handoff_id = getattr(step, "handoff_id", "") or ""
            if (
                integration_ref in {child_id, child_name}
                or step_handoff_id
                == f"handoff_repair_{payload.target_worker_promotion_ref_id.rsplit('::', 1)[-1]}"
                or step_handoff_id.startswith("handoff_repair_")
            ):
                existing_invoke_index = idx
                break



        existing_invoke = (
            parent_steps[existing_invoke_index] if existing_invoke_index is not None else None
        )
        handoff_id = (
            getattr(existing_invoke, "handoff_id", "") if existing_invoke is not None else ""
        )
        if not handoff_id:
            handoff_id = input_data.id_allocator.allocate_handoff_id()
        step_id = (
            existing_invoke.step_id
            if existing_invoke is not None
            else input_data.id_allocator.allocate_step_id()
        )

        input_irs = [
            InputBindingIR(parent, child, True) for parent, child in payload.input_bindings
        ]
        output_irs = [
            OutputBindingIR(child, parent, True, "set") for child, parent in payload.output_bindings
        ]
        mat_status = derive_handoff_materialization_status(
            input_bindings=input_irs,
            output_bindings=output_irs,
            input_status=payload.input_binding_status,
            output_status=payload.output_binding_status,
        )
        flow = InvokeLocationHintIR(
            flow_kind=payload.invocation_point,
            flow_id=None,
            after_span_id=None,
            before_span_id=None,
            block_hint="sequential",
        )
        handoff = WorkerHandoffIR(
            handoff_id=handoff_id,
            from_worker=parent_id,
            to_worker=child_id,
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=input_irs,
            output_bindings=output_irs,
            input_binding_status=payload.input_binding_status,
            output_binding_status=payload.output_binding_status,
            input_binding_status_source="user_confirmed_repair",
            output_binding_status_source="user_confirmed_repair",
            materialization_status=mat_status,
            invoke_location_hint=flow,
        )

        consumed_ref_ids = tuple(ref.ref.ref_id for ref in input_data.resolved_refs)
        invoke_inputs = [binding.parent_variable for binding in input_irs]
        invoke_outputs = [binding.parent_variable for binding in output_irs]
        step_metadata = {
            "origin": "user_confirmed_repair",
            "repair_patch_id": evidence_packet.repair_patch_id,
            "related_diagnostic_id": evidence_packet.related_diagnostic_id,
            "evidence_packet_id": evidence_packet.evidence_packet_id,
            "materialization_authority": _STAGE_AUTHORITY,
            "materialization_plan_id": _MATERIALIZER_ID,
            "consumed_selected_ref_ids": json.dumps(list(consumed_ref_ids)),
            "selected_ref_canonical_names": json.dumps(
                [r.ref.canonical_name for r in input_data.resolved_refs]
            ),
            "target_worker_promotion_ref_id": payload.target_worker_promotion_ref_id,
            "handoff_id": handoff_id,
            "user_text": evidence_packet.user_text,
        }
        if existing_invoke is not None:
            merged_metadata = dict(getattr(existing_invoke, "metadata", {}) or {})
            merged_metadata.update(step_metadata)
            invoke_step = replace(
                existing_invoke,
                inputs=invoke_inputs,
                outputs=invoke_outputs,
                integration_ref=child_name,
                flow_ref=payload.invocation_point,
                block_ref=getattr(existing_invoke, "block_ref", None) or "b_main_fallback",
                handoff_id=handoff_id,
                metadata=merged_metadata,
            )
        else:
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

        existing_handoffs = [h for h in worker_plan.handoffs if h.handoff_id != handoff_id]
        new_worker_plan = replace(worker_plan, handoffs=existing_handoffs + [handoff])
        worker_steps = {wid: list(steps) for wid, steps in step_plan.worker_steps.items()}
        if existing_invoke_index is not None:
            updated_parent_steps = list(worker_steps[parent_id])
            updated_parent_steps[existing_invoke_index] = invoke_step
            worker_steps[parent_id] = updated_parent_steps
        else:
            worker_steps[parent_id] = worker_steps[parent_id] + [invoke_step]
        new_step_plan = replace(step_plan, worker_steps=worker_steps)

        next_token = RevisionToken(
            snapshot.compile_run_id, snapshot.snapshot_id, snapshot.overlay_version + 1
        )
        patched_snapshot: ArtifactSnapshot = snapshot.derive(
            next_token,
            worker_plan=new_worker_plan,
            worker_step_plan=new_step_plan,
            final_spl=None,
            final_worker=None,
        )
        overlay_event = OverlayEvent(
            overlay_id=f"ov_{snapshot.snapshot_id}_{next_token.overlay_version}",
            base_compile_run_id=snapshot.compile_run_id,
            base_artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=next_token.overlay_version,
            patch_type=intent.patch_type,
            affordance_id=intent.affordance_id,
            patch_id=evidence_packet.repair_patch_id,
            accepted=True,
        )
        changed_step_ref = f"step:{parent_id}:{step_id}"
        changed_handoff_ref = f"handoff:{handoff_id}"
        evidence_refs = (
            RepairEvidenceRef(
                artifact_ref=changed_step_ref,
                repair_patch_id=evidence_packet.repair_patch_id,
                related_diagnostic_id=evidence_packet.related_diagnostic_id,
                user_text=evidence_packet.user_text,
            ),
            RepairEvidenceRef(
                artifact_ref=changed_handoff_ref,
                repair_patch_id=evidence_packet.repair_patch_id,
                related_diagnostic_id=evidence_packet.related_diagnostic_id,
                user_text=evidence_packet.user_text,
            ),
        )
        return MaterializationResult(
            patched_snapshot=patched_snapshot,
            overlay_event=overlay_event,
            changed_refs=(changed_step_ref, changed_handoff_ref),
            changed_step_ids=(step_id,),
            changed_handoff_ids=(handoff_id,),
            evidence_refs=evidence_refs,
            materialization_plan_id=_MATERIALIZER_ID,
            materializer_id=_MATERIALIZER_ID,
            materialization_authority=_STAGE_AUTHORITY,
            consumed_selected_ref_ids=consumed_ref_ids,
            evidence_packet_id=evidence_packet.evidence_packet_id,
            dependency_validation_metadata={},
        )

    def _materialize_main_flow_step(
        self,
        input_data: MaterializationInput,
        payload: ConvertDelegationToMainFlowStepIntentPayload,
    ) -> MaterializationResult:
        action_text = payload.action_text.strip()
        if not action_text:
            raise DependencyClosureValidationError("action_text must not be empty.")
        return self._materialize_resolution_step(
            input_data,
            worker_id=payload.worker_id,
            text=action_text,
            command_type="GENERAL_COMMAND",
            outputs=tuple(payload.outputs),
            metadata_extra={
                "resolution_kind": "converted_to_main_flow_step",
                "target_worker_promotion_ref_id": payload.target_worker_promotion_ref_id,
            },
        )

    def _materialize_request_input_step(
        self,
        input_data: MaterializationInput,
        payload: ConvertDelegationToRequestInputIntentPayload,
    ) -> MaterializationResult:
        prompt_text = payload.prompt_text.strip()
        if not prompt_text:
            raise DependencyClosureValidationError("prompt_text must not be empty.")
        if not payload.value_target.strip():
            raise DependencyClosureValidationError("value_target must not be empty.")
        outputs = tuple(payload.outputs) or (payload.value_target,)
        if payload.value_target not in outputs:
            outputs = outputs + (payload.value_target,)
        return self._materialize_resolution_step(
            input_data,
            worker_id=payload.worker_id,
            text=prompt_text,
            command_type="REQUEST_INPUT",
            outputs=outputs,
            metadata_extra={
                "resolution_kind": "converted_to_request_input",
                "target_worker_promotion_ref_id": payload.target_worker_promotion_ref_id,
                "value_target": payload.value_target,
            },
        )

    def _materialize_resolution_step(
        self,
        input_data: MaterializationInput,
        *,
        worker_id: str,
        text: str,
        command_type: str,
        outputs: tuple[str, ...],
        metadata_extra: dict[str, str],
    ) -> MaterializationResult:
        snapshot = input_data.snapshot
        evidence_packet = input_data.evidence_packet
        step_plan = snapshot.worker_step_plan
        if step_plan is None:
            raise DependencyClosureValidationError("worker_step_plan is missing from snapshot.")
        if worker_id not in step_plan.worker_steps:
            raise DependencyClosureValidationError(
                f"Worker '{worker_id}' not found in worker_step_plan."
            )
        step_id = input_data.id_allocator.allocate_step_id()
        consumed_ref_ids = tuple(ref.ref.ref_id for ref in input_data.resolved_refs)
        metadata = {
            "origin": "user_confirmed_repair",
            "repair_patch_id": evidence_packet.repair_patch_id,
            "related_diagnostic_id": evidence_packet.related_diagnostic_id,
            "evidence_packet_id": evidence_packet.evidence_packet_id,
            "materialization_authority": _STAGE_AUTHORITY,
            "materialization_plan_id": _MATERIALIZER_ID,
            "consumed_selected_ref_ids": json.dumps(list(consumed_ref_ids)),
            "selected_ref_canonical_names": json.dumps(
                [r.ref.canonical_name for r in input_data.resolved_refs]
            ),
            "user_text": evidence_packet.user_text,
            **metadata_extra,
        }
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
        next_token = RevisionToken(
            snapshot.compile_run_id, snapshot.snapshot_id, snapshot.overlay_version + 1
        )
        patched_snapshot: ArtifactSnapshot = snapshot.derive(
            next_token,
            worker_step_plan=new_step_plan,
            final_spl=None,
            final_worker=None,
        )
        overlay_event = OverlayEvent(
            overlay_id=f"ov_{snapshot.snapshot_id}_{next_token.overlay_version}",
            base_compile_run_id=snapshot.compile_run_id,
            base_artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=next_token.overlay_version,
            patch_type=input_data.intent.patch_type,
            affordance_id=input_data.intent.affordance_id,
            patch_id=evidence_packet.repair_patch_id,
            accepted=True,
        )
        changed_ref = f"step:{worker_id}:{step_id}"
        evidence_ref = RepairEvidenceRef(
            artifact_ref=changed_ref,
            repair_patch_id=evidence_packet.repair_patch_id,
            related_diagnostic_id=evidence_packet.related_diagnostic_id,
            user_text=evidence_packet.user_text,
        )
        return MaterializationResult(
            patched_snapshot=patched_snapshot,
            overlay_event=overlay_event,
            changed_refs=(changed_ref,),
            changed_step_ids=(step_id,),
            changed_handoff_ids=(),
            evidence_refs=(evidence_ref,),
            materialization_plan_id=_MATERIALIZER_ID,
            materializer_id=_MATERIALIZER_ID,
            materialization_authority=_STAGE_AUTHORITY,
            consumed_selected_ref_ids=consumed_ref_ids,
            evidence_packet_id=evidence_packet.evidence_packet_id,
            dependency_validation_metadata={},
        )
