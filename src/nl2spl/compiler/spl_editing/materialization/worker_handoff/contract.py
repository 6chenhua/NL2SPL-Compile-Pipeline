"""Worker handoff materialization facade backed by repair-mode stage slices."""

from __future__ import annotations

from importlib import import_module

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

_MATERIALIZER_ID = "worker_handoff.contract_repair.v1"
_STAGE_AUTHORITY = "stage3_5.worker_boundary + stage7.worker_step_plan"


def _load_runtime():
    stage_slices = import_module("nl2spl.compiler.spl_editing.stage_slices")
    strategy = import_module("nl2spl.compiler.spl_editing.strategy")
    return stage_slices, strategy.RepairDirective


class WorkerHandoffContractMaterializer:
    """Compatibility facade that delegates worker closure shape to stage slices."""

    @property
    def materializer_id(self) -> str:
        return _MATERIALIZER_ID

    @property
    def stage_authority(self) -> str:
        return _STAGE_AUTHORITY

    def materialize(self, input_data: MaterializationInput) -> MaterializationResult:
        payload = input_data.intent.payload
        if isinstance(payload, CreateWorkerHandoffContractIntentPayload):
            return self._materialize_handoff_contract(input_data, payload)
        if isinstance(payload, (ConvertDelegationToMainFlowStepIntentPayload, ConvertDelegationToRequestInputIntentPayload)):
            return self._materialize_resolution_step(input_data, payload)
        raise DependencyClosureValidationError(
            "WorkerHandoffContractMaterializer requires a worker-promotion "
            f"intent payload but received {type(payload).__name__!r}."
        )

    def _directive(self, input_data: MaterializationInput, requested_behavior: str):
        stage_slices, RepairDirective = _load_runtime()
        return RepairDirective(
            directive_id=f"dir_{input_data.intent.intent_id}",
            source="system_default",
            target_construct_type=input_data.intent.target_construct_type,
            target_slot_name=input_data.intent.target_slot_name,
            requested_behavior=requested_behavior,
            selected_ref_hints=tuple(ref.ref.ref_id for ref in input_data.resolved_refs),
        )

    def _materialize_handoff_contract(
        self,
        input_data: MaterializationInput,
        payload: CreateWorkerHandoffContractIntentPayload,
    ) -> MaterializationResult:
        stage_slices, _RepairDirective = _load_runtime()
        snapshot = input_data.snapshot
        if snapshot.worker_plan is None:
            raise DependencyClosureValidationError("worker_plan is missing from snapshot.")
        if snapshot.worker_step_plan is None:
            raise DependencyClosureValidationError("worker_step_plan is missing from snapshot.")
        directive = self._directive(input_data, "create worker handoff contract")
        selected_ref_ids = tuple(ref.ref.ref_id for ref in input_data.resolved_refs)

        stage35 = stage_slices.Stage35WorkerHandoffContractRepairSlice()
        stage35_result = stage35.execute(
            stage_slices.StageSliceInput(
                slice_id=stage35.slice_id,
                stage_authority="stage3_5.worker_boundary",
                snapshot=snapshot,
                target=input_data.target,
                refset=input_data.refset,
                directive=directive,
                intent=input_data.intent,
                dependency_closure=input_data.plan.dependency_closure,
                stage_policy=stage_slices.StagePolicy(
                    policy_id="worker_delegation.handoff_contract.v1",
                    stage_authority="stage3_5.worker_boundary",
                    allowed_typed_plan_kinds=("HandoffContractPlan",),
                    generation_mode="none",
                ),
                selected_ref_ids=selected_ref_ids,
                evidence_packet=input_data.evidence_packet,
                id_allocator=input_data.id_allocator,
                dry_run=False,
            )
        )
        stage7 = stage_slices.Stage7WorkerInvokeCommandRepairSlice()
        stage7_result = stage7.execute(
            stage_slices.StageSliceInput(
                slice_id=stage7.slice_id,
                stage_authority="stage7.worker_step_plan",
                snapshot=snapshot,
                target=input_data.target,
                refset=input_data.refset,
                directive=directive,
                intent=input_data.intent,
                dependency_closure=input_data.plan.dependency_closure,
                stage_policy=stage_slices.StagePolicy(
                    policy_id="worker_delegation.invoke_worker_command.v1",
                    stage_authority="stage7.worker_step_plan",
                    allowed_typed_plan_kinds=("InvokeWorkerPlan",),
                    generation_mode="none",
                ),
                selected_ref_ids=selected_ref_ids,
                evidence_packet=input_data.evidence_packet,
                id_allocator=input_data.id_allocator,
                upstream_stage_results=(stage35_result,),
                dry_run=False,
            )
        )
        return self._finish(
            input_data,
            worker_plan=stage35_result.artifact_updates["worker_plan"],
            step_plan=stage7_result.artifact_updates["worker_step_plan"],
            changed_refs=(stage7_result.generated_construct_refs[0], stage35_result.generated_construct_refs[0]),
            changed_step_ids=(stage7_result.generated_construct_refs[0].rsplit(":", 1)[-1],),
            changed_handoff_ids=(stage35_result.generated_construct_refs[0].rsplit(":", 1)[-1],),
            consumed_selected_ref_ids=selected_ref_ids,
            stage_slice_results=(stage35_result, stage7_result),
        )

    def _materialize_resolution_step(
        self,
        input_data: MaterializationInput,
        payload: ConvertDelegationToMainFlowStepIntentPayload | ConvertDelegationToRequestInputIntentPayload,
    ) -> MaterializationResult:
        stage_slices, _RepairDirective = _load_runtime()
        snapshot = input_data.snapshot
        if snapshot.worker_step_plan is None:
            raise DependencyClosureValidationError("worker_step_plan is missing from snapshot.")
        if isinstance(payload, ConvertDelegationToMainFlowStepIntentPayload):
            requested_behavior = payload.action_text
        else:
            requested_behavior = payload.prompt_text
        directive = self._directive(input_data, requested_behavior)
        selected_ref_ids = tuple(ref.ref.ref_id for ref in input_data.resolved_refs)
        stage7 = stage_slices.Stage7WorkerDelegationResolutionCommandRepairSlice()
        stage7_result = stage7.execute(
            stage_slices.StageSliceInput(
                slice_id=stage7.slice_id,
                stage_authority="stage7.worker_step_plan",
                snapshot=snapshot,
                target=input_data.target,
                refset=input_data.refset,
                directive=directive,
                intent=input_data.intent,
                dependency_closure=input_data.plan.dependency_closure,
                stage_policy=stage_slices.StagePolicy(
                    policy_id="worker_delegation.resolution_command.v1",
                    stage_authority="stage7.worker_step_plan",
                    allowed_typed_plan_kinds=("CommandIntentPlan",),
                    generation_mode="none",
                ),
                selected_ref_ids=selected_ref_ids,
                evidence_packet=input_data.evidence_packet,
                id_allocator=input_data.id_allocator,
                dry_run=False,
            )
        )
        return self._finish(
            input_data,
            worker_plan=None,
            step_plan=stage7_result.artifact_updates["worker_step_plan"],
            changed_refs=(stage7_result.generated_construct_refs[0],),
            changed_step_ids=(stage7_result.generated_construct_refs[0].rsplit(":", 1)[-1],),
            changed_handoff_ids=(),
            consumed_selected_ref_ids=selected_ref_ids,
            stage_slice_results=(stage7_result,),
        )

    def _finish(
        self,
        input_data: MaterializationInput,
        *,
        worker_plan,
        step_plan,
        changed_refs: tuple[str, ...],
        changed_step_ids: tuple[str, ...],
        changed_handoff_ids: tuple[str, ...],
        consumed_selected_ref_ids: tuple[str, ...],
        stage_slice_results: tuple[object, ...],
    ) -> MaterializationResult:
        snapshot = input_data.snapshot
        next_token = RevisionToken(
            snapshot.compile_run_id, snapshot.snapshot_id, snapshot.overlay_version + 1
        )
        derive_kwargs = {
            "worker_step_plan": step_plan,
            "final_spl": None,
            "final_worker": None,
        }
        if worker_plan is not None:
            derive_kwargs["worker_plan"] = worker_plan
        patched_snapshot: ArtifactSnapshot = snapshot.derive(next_token, **derive_kwargs)
        overlay_event = OverlayEvent(
            overlay_id=f"ov_{snapshot.snapshot_id}_{next_token.overlay_version}",
            base_compile_run_id=snapshot.compile_run_id,
            base_artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=next_token.overlay_version,
            patch_type=input_data.intent.patch_type,
            affordance_id=input_data.intent.affordance_id,
            patch_id=input_data.evidence_packet.repair_patch_id,
            accepted=True,
        )
        stage7_step_metadata = {
            "user_text": input_data.evidence_packet.user_text,
            "resolution_kind": "stage_slice_delegation_resolution",
        }
        evidence_refs = tuple(
            RepairEvidenceRef(
                artifact_ref=ref,
                repair_patch_id=input_data.evidence_packet.repair_patch_id,
                related_diagnostic_id=input_data.evidence_packet.related_diagnostic_id,
                user_text=input_data.evidence_packet.user_text,
            )
            for ref in changed_refs
        )
        return MaterializationResult(
            patched_snapshot=patched_snapshot,
            overlay_event=overlay_event,
            changed_refs=changed_refs,
            changed_step_ids=changed_step_ids,
            changed_handoff_ids=changed_handoff_ids,
            evidence_refs=evidence_refs,
            materialization_plan_id=_MATERIALIZER_ID,
            materializer_id=_MATERIALIZER_ID,
            materialization_authority=_STAGE_AUTHORITY,
            consumed_selected_ref_ids=consumed_selected_ref_ids,
            evidence_packet_id=input_data.evidence_packet.evidence_packet_id,
            dependency_validation_metadata={"stage7_step_metadata": stage7_step_metadata},
            stage_slice_results=stage_slice_results,
        )
