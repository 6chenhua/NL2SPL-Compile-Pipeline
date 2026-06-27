"""Exception-handler materialization facade backed by repair-mode stage slices."""

from __future__ import annotations

from importlib import import_module

from nl2spl.compiler.spl_editing.core.model import RepairEvidenceRef
from nl2spl.compiler.spl_editing.core.revision import (
    ArtifactSnapshot,
    OverlayEvent,
    RevisionToken,
)
from nl2spl.compiler.spl_editing.intent.model import AddExceptionHandlerStepIntentPayload
from nl2spl.compiler.spl_editing.materialization.errors import (
    DependencyClosureValidationError,
)
from nl2spl.compiler.spl_editing.materialization.model import (
    MaterializationInput,
    MaterializationResult,
)

_MATERIALIZER_ID = "stage7.exception_handler_step_repair.v1"
_STAGE_AUTHORITY = "stage7.worker_step_plan"
_STAGE5_AUTHORITY = "stage5.worker_block_plan"


def _load_stage_slice_runtime():
    stage_slices = import_module("nl2spl.compiler.spl_editing.stage_slices")
    strategy = import_module("nl2spl.compiler.spl_editing.strategy")
    return (
        stage_slices.StagePolicy,
        stage_slices.StageSliceInput,
        stage_slices.Stage5ExceptionHandlerBlockRepairSlice,
        stage_slices.Stage7ExceptionHandlerCommandRepairSlice,
        strategy.RepairDirective,
    )


class ExceptionHandlerStageSliceChainMaterializer:
    """Compatibility facade that orchestrates Stage5 and Stage7 repair slices."""

    @property
    def materializer_id(self) -> str:
        return _MATERIALIZER_ID

    @property
    def stage_authority(self) -> str:
        return _STAGE_AUTHORITY

    def materialize(self, input_data: MaterializationInput) -> MaterializationResult:
        intent = input_data.intent
        snapshot = input_data.snapshot
        target = input_data.target
        evidence_packet = input_data.evidence_packet
        resolved_refs = input_data.resolved_refs

        payload = intent.payload
        if not isinstance(payload, AddExceptionHandlerStepIntentPayload):
            raise DependencyClosureValidationError(
                "ExceptionHandlerStageSliceChainMaterializer requires "
                f"AddExceptionHandlerStepIntentPayload but received {type(payload).__name__!r}."
            )

        handler_goal = payload.handler_goal.strip()
        if not handler_goal:
            raise DependencyClosureValidationError("handler_goal must not be empty.")
        normalized_goal = handler_goal.casefold()
        if "<ref" in normalized_goal or "</ref" in normalized_goal:
            raise DependencyClosureValidationError(
                "handler_goal must not contain <REF or </REF tokens; "
                "use canonical ref names directly."
            )

        worker_id = target.worker_id or ""
        flow_id = target.canonical_name or ""
        if not worker_id:
            raise DependencyClosureValidationError("RepairTarget.worker_id is required.")
        if not flow_id:
            raise DependencyClosureValidationError("RepairTarget.canonical_name is required.")
        if snapshot.worker_step_plan is None:
            raise DependencyClosureValidationError("worker_step_plan is missing from snapshot.")
        if snapshot.worker_block_plan is None:
            raise DependencyClosureValidationError("worker_block_plan is missing from snapshot.")
        if snapshot.worker_flow_plan is None:
            raise DependencyClosureValidationError("worker_flow_plan is missing from snapshot.")
        if worker_id not in snapshot.worker_step_plan.worker_steps:
            raise DependencyClosureValidationError(
                f"Target worker '{worker_id}' not found in worker_step_plan.worker_steps."
            )
        worker_flows = getattr(snapshot.worker_flow_plan, "worker_flows", {})
        flow_scope = worker_flows.get(worker_id)
        if flow_scope is None or not any(
            getattr(exc, "flow_id", None) == flow_id
            for exc in getattr(flow_scope, "exception_flows", [])
        ):
            raise DependencyClosureValidationError(
                f"Exception flow '{flow_id}' not found in worker '{worker_id}'."
            )

        for resolved in resolved_refs:
            if (
                resolved.ref.ref_role != "selectable_input"
                or resolved.resolved_role != "selectable_input"
                or not resolved.scope_matched
            ):
                raise DependencyClosureValidationError(
                    f"Resolved ref '{resolved.ref.ref_id}' is not an authorized "
                    "selectable_input in the target scope."
                )

        (
            StagePolicy,
            StageSliceInput,
            Stage5ExceptionHandlerBlockRepairSlice,
            Stage7ExceptionHandlerCommandRepairSlice,
            RepairDirective,
        ) = _load_stage_slice_runtime()

        selected_ref_ids = tuple(ref.ref.ref_id for ref in resolved_refs)
        directive = RepairDirective(
            directive_id=f"dir_{intent.intent_id}",
            source="system_default",
            target_construct_type=intent.target_construct_type,
            target_slot_name=intent.target_slot_name,
            requested_behavior=handler_goal,
            selected_ref_hints=selected_ref_ids,
        )

        stage5 = Stage5ExceptionHandlerBlockRepairSlice()
        stage5_result = stage5.execute(
            StageSliceInput(
                slice_id=stage5.slice_id,
                stage_authority=_STAGE5_AUTHORITY,
                snapshot=snapshot,
                target=target,
                refset=input_data.refset,
                directive=directive,
                intent=intent,
                dependency_closure=input_data.plan.dependency_closure,
                stage_policy=StagePolicy(
                    policy_id="exception_handler.block_shape.v1",
                    stage_authority=_STAGE5_AUTHORITY,
                    allowed_typed_plan_kinds=("BlockShapePlan",),
                    generation_mode="none",
                ),
                selected_ref_ids=(),
                evidence_packet=evidence_packet,
                id_allocator=input_data.id_allocator,
                dry_run=False,
            )
        )

        stage7 = Stage7ExceptionHandlerCommandRepairSlice()
        stage7_result = stage7.execute(
            StageSliceInput(
                slice_id=stage7.slice_id,
                stage_authority=_STAGE_AUTHORITY,
                snapshot=snapshot,
                target=target,
                refset=input_data.refset,
                directive=directive,
                intent=intent,
                dependency_closure=input_data.plan.dependency_closure,
                stage_policy=StagePolicy(
                    policy_id="exception_handler.command_intent.v1",
                    stage_authority=_STAGE_AUTHORITY,
                    allowed_typed_plan_kinds=("CommandIntentPlan",),
                    generation_mode="none",
                ),
                selected_ref_ids=selected_ref_ids,
                evidence_packet=evidence_packet,
                id_allocator=input_data.id_allocator,
                upstream_stage_results=(stage5_result,),
                dry_run=False,
            )
        )

        new_block_plan = stage5_result.artifact_updates.get(
            "worker_block_plan",
            snapshot.worker_block_plan,
        )
        new_step_plan = stage7_result.artifact_updates["worker_step_plan"]
        next_token = RevisionToken(
            compile_run_id=snapshot.compile_run_id,
            artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=snapshot.overlay_version + 1,
        )
        patched_snapshot: ArtifactSnapshot = snapshot.derive(
            next_token,
            worker_step_plan=new_step_plan,
            worker_block_plan=new_block_plan,
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
        changed_refs = tuple(
            stage7_result.generated_construct_refs + stage5_result.generated_construct_refs
        )
        changed_step_ids = tuple(
            ref.rsplit(":", 1)[-1] for ref in stage7_result.generated_construct_refs
        )
        evidence_ref = RepairEvidenceRef(
            artifact_ref=stage7_result.generated_construct_refs[0],
            repair_patch_id=evidence_packet.repair_patch_id,
            related_diagnostic_id=evidence_packet.related_diagnostic_id,
            user_text=evidence_packet.user_text,
        )
        stage7_step_metadata = {
            "origin": "user_confirmed_repair",
            "repair_patch_id": evidence_packet.repair_patch_id,
            "related_diagnostic_id": evidence_packet.related_diagnostic_id,
            "user_text": evidence_packet.user_text,
        }

        return MaterializationResult(
            patched_snapshot=patched_snapshot,
            overlay_event=overlay_event,
            changed_refs=changed_refs,
            changed_step_ids=changed_step_ids,
            changed_handoff_ids=(),
            evidence_refs=(evidence_ref,),
            materialization_plan_id=_MATERIALIZER_ID,
            materializer_id=_MATERIALIZER_ID,
            materialization_authority=_STAGE_AUTHORITY,
            consumed_selected_ref_ids=selected_ref_ids,
            evidence_packet_id=evidence_packet.evidence_packet_id,
            dependency_validation_metadata={"stage7_step_metadata": stage7_step_metadata},
            stage_slice_results=(stage5_result, stage7_result),
        )
