"""Pure closure orchestrator for Worker Delegation v2 stage slices."""

from __future__ import annotations

from dataclasses import replace

from nl2spl.compiler.spl_editing.core.model import RepairEvidenceRef
from nl2spl.compiler.spl_editing.core.revision import OverlayEvent, RevisionToken
from nl2spl.compiler.spl_editing.interaction.model import NormalizedWorkerDelegationDirective
from nl2spl.compiler.spl_editing.materialization.errors import DependencyClosureValidationError
from nl2spl.compiler.spl_editing.materialization.model import MaterializationResult
from nl2spl.compiler.spl_editing.resolution.model import PromotionResolutionMarker
from nl2spl.compiler.spl_editing.stage_slices.model import StagePolicy, StageSliceInput
from nl2spl.compiler.spl_editing.stage_slices.worker_delegation_closure import (
    build_worker_delegation_stage_slice_registry,
)
from nl2spl.compiler.spl_editing.stage_slices.worker_delegation_plans import (
    build_worker_delegation_typed_plans,
)
from nl2spl.compiler.spl_editing.strategy.model import RepairDirective

_PLAN_ID = "worker_delegation.complete_closure.v2"
_AUTHORITY = (
    "stage3_5.worker_boundary + stage4.worker_flow_plan + "
    "stage5.worker_block_plan + stage7.worker_step_plan"
)

_DEFINE_CHAIN = (
    ("stage3_5.define_child_worker.v2", "child_boundary"),
    ("stage4.child_worker_flow.v2", "child_flow"),
    ("stage5.worker_delegation_blocks.v2", "child_block"),
    ("stage7.child_worker_command.v2", "child_command"),
    ("stage3_5.worker_handoff_contract.v2", "handoff"),
    ("stage7.worker_invoke.v2", "parent_invoke"),
    ("stage3_5.worker_symbol_bindings.v2", "symbol_bindings"),
)
_KEEP_CHAIN = (
    ("stage3_5.keep_main_boundary.v2", "keep_main"),
    ("stage4.keep_main_flow_cleanup.v2", "keep_main"),
    ("stage5.keep_main_placement.v2", "keep_main"),
    ("stage7.keep_main_command.v2", "keep_main"),
)


class DefineChildWorkerClosureMaterializer:
    """Coordinate registered slices without mutating stage-owned artifacts."""

    required_stage_slice_ids = tuple(
        slice_id for slice_id, _plan_name in (*_DEFINE_CHAIN, *_KEEP_CHAIN)
    )

    def __init__(self, stage_slice_registry=None) -> None:
        self.stage_slice_registry = (
            stage_slice_registry or build_worker_delegation_stage_slice_registry()
        )

    @property
    def materializer_id(self) -> str:
        return _PLAN_ID

    @property
    def stage_authority(self) -> str:
        return _AUTHORITY

    def materialize(self, input_data) -> MaterializationResult:
        directive = input_data.intent.payload
        if not isinstance(directive, NormalizedWorkerDelegationDirective):
            raise DependencyClosureValidationError(
                "Worker Delegation v2 requires NormalizedWorkerDelegationDirective."
            )
        snapshot = input_data.snapshot
        if any(
            value is None
            for value in (
                snapshot.worker_plan,
                snapshot.worker_flow_plan,
                snapshot.worker_block_plan,
                snapshot.worker_step_plan,
                snapshot.symbol_table,
            )
        ):
            raise DependencyClosureValidationError("Worker closure artifacts are incomplete.")
        bundle = build_worker_delegation_typed_plans(snapshot, input_data.target, directive)
        if directive.option_id == "define_child_worker":
            if not directive.admitted_outputs:
                raise DependencyClosureValidationError("Child output contract cannot be empty.")
            chain = _DEFINE_CHAIN
            resolution_kind = "defined_child_worker"
        elif directive.option_id == "keep_in_main_flow":
            chain = _KEEP_CHAIN
            resolution_kind = "kept_in_main_flow"
        else:
            raise DependencyClosureValidationError(
                f"Unsupported Worker Delegation option '{directive.option_id}'."
            )

        registry = self.stage_slice_registry
        working = snapshot
        stage_results = []
        provisional = RepairDirective(
            directive_id=directive.directive_id,
            source="user",
            target_construct_type=input_data.intent.target_construct_type,
            target_slot_name=input_data.intent.target_slot_name,
            requested_behavior=directive.delegated_responsibility,
            selected_ref_hints=tuple(item.ref.ref_id for item in directive.selected_input_refs),
            option_id=directive.option_id,
        )
        for slice_id, plan_name in chain:
            stage_slice = registry.get(slice_id)
            typed_plan = getattr(bundle, plan_name)
            result = stage_slice.execute(
                StageSliceInput(
                    slice_id=stage_slice.slice_id,
                    stage_authority=stage_slice.stage_authority,
                    snapshot=working,
                    target=input_data.target,
                    refset=input_data.refset,
                    directive=provisional,
                    intent=input_data.intent,
                    dependency_closure=input_data.plan.dependency_closure,
                    stage_policy=StagePolicy(
                        policy_id=stage_slice.policy_id,
                        stage_authority=stage_slice.stage_authority,
                        allowed_typed_plan_kinds=(type(typed_plan).__name__,),
                        generation_mode="stored_typed_plan",
                    ),
                    selected_ref_ids=tuple(input_data.intent.selected_ref_ids),
                    evidence_packet=input_data.evidence_packet,
                    id_allocator=input_data.id_allocator,
                    typed_plan=typed_plan,
                    upstream_stage_results=tuple(stage_results),
                    issue=input_data.issue,
                    dry_run=False,
                )
            )
            expected_fields = {
                "WorkerPlanIR": "worker_plan",
                "WorkerFlowPlanIR": "worker_flow_plan",
                "WorkerBlockPlanIR": "worker_block_plan",
                "WorkerStepPlanIR": "worker_step_plan",
                "SymbolTable": "symbol_table",
            }
            expected_field = expected_fields[stage_slice.output_artifacts[0]]
            if set(result.artifact_updates) != {expected_field}:
                raise DependencyClosureValidationError(
                    f"Stage slice '{slice_id}' crossed its artifact authority."
                )
            working = replace(working, **result.artifact_updates)
            stage_results.append(result)

        changed_refs = tuple(
            ref for result in stage_results for ref in result.changed_artifact_refs
        )
        generated_refs = tuple(
            ref for result in stage_results for ref in result.generated_construct_refs
        )
        if resolution_kind == "defined_child_worker":
            closure_refs = (
                f"worker:{bundle.child_boundary.worker_id}",
                f"flow:{bundle.child_flow.worker_id}:main",
                f"block:{bundle.child_block.worker_id}:{bundle.child_block.block_id}",
                f"step:{bundle.child_command.worker_id}:{bundle.child_command.command_id}",
                f"handoff:{bundle.handoff.handoff_id}",
                f"step:{bundle.parent_invoke.parent_worker_id}:{bundle.parent_invoke.command_id}",
            )
        else:
            closure_refs = (
                f"step:{bundle.keep_main.parent_worker_id}:{bundle.keep_main.command_id}",
            )
        marker = PromotionResolutionMarker(
            marker_id=f"promotion_resolution:{directive.directive_id}",
            target_worker_promotion_id=input_data.target.target_ref,
            resolved_diagnostic_group_id=(f"worker_promotion_group:{input_data.target.target_ref}"),
            resolution_kind=resolution_kind,
            normalized_directive_id=directive.directive_id,
            materialized_construct_refs=closure_refs,
            evidence_ref=input_data.evidence_packet.evidence_packet_id,
            repair_patch_id=input_data.evidence_packet.repair_patch_id,
            user_confirmed=True,
        )
        next_token = RevisionToken(
            snapshot.compile_run_id,
            snapshot.snapshot_id,
            snapshot.overlay_version + 1,
        )
        patched = snapshot.derive(
            next_token,
            worker_plan=working.worker_plan,
            worker_flow_plan=working.worker_flow_plan,
            worker_block_plan=working.worker_block_plan,
            worker_step_plan=working.worker_step_plan,
            symbol_table=working.symbol_table,
            final_worker=None,
            final_spl=None,
            promotion_resolution_markers=(*snapshot.promotion_resolution_markers, marker),
        )
        overlay = OverlayEvent(
            overlay_id=f"ov_{snapshot.snapshot_id}_{next_token.overlay_version}",
            base_compile_run_id=snapshot.compile_run_id,
            base_artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=next_token.overlay_version,
            patch_type=input_data.intent.patch_type,
            affordance_id=input_data.intent.affordance_id,
            patch_id=input_data.evidence_packet.repair_patch_id,
            accepted=True,
        )
        evidence_refs = tuple(
            RepairEvidenceRef(
                artifact_ref=ref,
                repair_patch_id=input_data.evidence_packet.repair_patch_id,
                related_diagnostic_id=input_data.evidence_packet.related_diagnostic_id,
                user_text=input_data.evidence_packet.user_text,
            )
            for ref in changed_refs
        )
        changed_step_ids = tuple(
            ref.rsplit(":", 1)[-1] for ref in generated_refs if ref.startswith("step:")
        )
        changed_handoff_ids = tuple(
            ref.removeprefix("handoff:") for ref in generated_refs if ref.startswith("handoff:")
        )
        return MaterializationResult(
            patched_snapshot=patched,
            overlay_event=overlay,
            changed_refs=changed_refs,
            changed_step_ids=changed_step_ids,
            changed_handoff_ids=changed_handoff_ids,
            evidence_refs=evidence_refs,
            materialization_plan_id=_PLAN_ID,
            materializer_id=_PLAN_ID,
            materialization_authority=_AUTHORITY,
            consumed_selected_ref_ids=tuple(
                item.ref.ref_id for item in directive.selected_input_refs
            ),
            evidence_packet_id=input_data.evidence_packet.evidence_packet_id,
            dependency_validation_metadata={
                "normalized_directive_id": directive.directive_id,
                "executed_stage_slice_ids": [result.slice_id for result in stage_results],
                "generated_construct_refs": list(generated_refs),
            },
            stage_slice_results=tuple(stage_results),
            resolution_markers=(marker,),
        )


__all__ = ["DefineChildWorkerClosureMaterializer"]
