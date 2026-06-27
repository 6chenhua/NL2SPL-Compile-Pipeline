"""Service for orchestrating SPL Editing preview dry-runs."""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.spl_editing.closure.planner import ClosurePlanner
from nl2spl.compiler.spl_editing.closure.validators import resolve_target_affordance
from nl2spl.compiler.spl_editing.core.model import EditableIssue, EditingSession, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import (
    AddExceptionHandlerStepIntentPayload,
    ConstructRepairIntent,
    ConvertDelegationToMainFlowStepIntentPayload,
    ConvertDelegationToRequestInputIntentPayload,
    CreateWorkerHandoffContractIntentPayload,
    InsertProducerStepIntentPayload,
)
from nl2spl.compiler.spl_editing.materialization.service import RepairMaterializationService
from nl2spl.compiler.spl_editing.preview.errors import PreviewError
from nl2spl.compiler.spl_editing.preview.hashes import (
    compute_closure_plan_hash,
    compute_directive_hash,
    compute_intent_hash,
    compute_llm_generation_config_hash,
    compute_selected_refset_hash,
    compute_sha256,
)
from nl2spl.compiler.spl_editing.preview.model import (
    PreviewMaterializationResult,
    StageSliceTypedPlanRef,
)
from nl2spl.compiler.spl_editing.preview.store import PreviewStore
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRefSet
from nl2spl.compiler.spl_editing.selectable_refs.resolver import resolve_ref_ids_to_result
from nl2spl.compiler.spl_editing.strategy.model import RepairDirective, RepairStrategySpec


class PreviewDryRunService:
    """Orchestrates preview generation without modifying live state."""

    def __init__(self, materialization_service: RepairMaterializationService) -> None:
        self.materialization_service = materialization_service

    def preview(
        self,
        session: EditingSession,
        issue: EditableIssue,
        strategy: RepairStrategySpec,
        directive: RepairDirective,
        target: RepairTarget,
        refset: SelectableRefSet,
        snapshot: ArtifactSnapshot,
        store: PreviewStore,
        candidate_intent: ConstructRepairIntent | None = None,
        ttl_seconds: float | None = None,
    ) -> PreviewMaterializationResult:
        """Run dry-run materialization, compute stale hashes, and store the preview."""
        # 1. Enforce strict scope identity check across input parameters
        if session.issue.issue_id != issue.issue_id:
            raise PreviewError(
                f"Session issue ID mismatch: '{session.issue.issue_id}' != '{issue.issue_id}'."
            )
        if session.artifact_snapshot_id != snapshot.snapshot_id:
            raise PreviewError("Session snapshot ID mismatch.")
        if refset.issue_id != issue.issue_id:
            raise PreviewError(
                f"Refset issue ID mismatch: '{refset.issue_id}' != '{issue.issue_id}'."
            )
        if refset.snapshot_id != snapshot.snapshot_id:
            raise PreviewError(
                f"Refset snapshot ID mismatch: '{refset.snapshot_id}' != '{snapshot.snapshot_id}'."
            )

        # 1b. Enforce policy and availability validation on SelectableRefSet
        if not refset.is_available:
            raise PreviewError("SelectableRefSet is marked as unavailable.")

        if strategy.selectable_ref_policy_id:
            if refset.policy_id != strategy.selectable_ref_policy_id:
                raise PreviewError("Policy mismatch: strategy selectable ref policy.")

        # 2. Resolve and validate affordance
        affordance = resolve_target_affordance(target)
        if affordance.repair_strategy_id != strategy.strategy_id:
            raise PreviewError(
                f"Affordance repair_strategy_id '{affordance.repair_strategy_id}' "
                f"does not match strategy '{strategy.strategy_id}'."
            )

        if affordance.selectable_ref_policy_id:
            if refset.policy_id != affordance.selectable_ref_policy_id:
                raise PreviewError("Policy mismatch: affordance selectable ref policy.")

        # 3. Resolve target reference structurally in the refset
        construct_type = target.irs_ref.construct_type
        if construct_type == "REQUIRED_OUTPUT":
            expected_role = "target_output"
        elif construct_type == "EXCEPTION_FLOW":
            expected_role = "target_exception_flow"
        elif construct_type == "WORKER_PROMOTION":
            expected_role = "target_worker"
        else:
            expected_role = "target_output"

        target_ref_id = None
        for ref in refset.refs:
            if (
                ref.ref_role == expected_role
                and ref.worker_id == target.worker_id
                and ref.canonical_name == target.canonical_name
            ):
                target_ref_id = ref.ref_id
                break

        if not target_ref_id:
            raise PreviewError(
                f"Could not structurally resolve target reference for kind='{construct_type}', "
                f"worker='{target.worker_id}', name='{target.canonical_name}'."
            )

        # 4. Validate selected ref hints in the refset
        if directive.selected_ref_hints:
            res = resolve_ref_ids_to_result(
                refset, directive.selected_ref_hints, "selectable_input"
            )
            if not res.is_success:
                raise PreviewError(
                    f"Selected reference hints validation failed: {', '.join(res.errors)}"
                )

        # 5. Generate ConstructClosurePlan
        closure_plan = ClosurePlanner.generate_closure_plan(
            closure_plan_id=f"closure_{directive.directive_id}",
            strategy=strategy,
            target=target,
            directive=directive,
            selectable_refs=refset,
        )

        # 6. Determine patch type and build corresponding payload DTO with explicit routing
        patch_type = candidate_intent.patch_type if candidate_intent is not None else None
        if patch_type is None and len(strategy.supported_patch_types) == 1:
            patch_type = strategy.supported_patch_types[0]
        elif patch_type is None and len(strategy.supported_patch_types) > 1:
            # A. Check constraints first
            for const in directive.constraints:
                for pt in strategy.supported_patch_types:
                    if const.casefold() == pt.casefold():
                        patch_type = pt
                        break
                if patch_type:
                    break

            # B. Check requested_behavior for worker delegation routing
            if not patch_type and directive.requested_behavior:
                behavior = directive.requested_behavior.casefold()
                if any(x in behavior for x in ["main-flow", "main flow", "inline", "main_flow"]):
                    patch_type = "ConvertDelegationIntentToMainFlowStep"
                elif any(
                    x in behavior
                    for x in ["request input", "ask user", "request_input", "ask_user"]
                ):
                    patch_type = "ConvertDelegationIntentToRequestInput"
                elif any(x in behavior for x in ["handoff", "contract", "delegate"]):
                    patch_type = "CreateWorkerHandoffContract"
                else:
                    raise PreviewError("Cannot determine target patch type for worker delegation.")

            # C. Default fallback if neither is specified
            if not patch_type:
                patch_type = strategy.supported_patch_types[0]

        if not patch_type:
            raise PreviewError("No matching patch type could be resolved for preview.")

        payload: Any = candidate_intent.payload if candidate_intent is not None else None
        if payload is not None:
            pass
        elif patch_type == "InsertProducerStep":
            payload = InsertProducerStepIntentPayload(
                target_output_ref_id=target_ref_id,
                selected_input_ref_ids=directive.selected_ref_hints,
                producer_goal=directive.requested_behavior or "Dry-run producer goal",
            )
        elif patch_type == "AddExceptionHandlerStep":
            payload = AddExceptionHandlerStepIntentPayload(
                target_exception_flow_ref_id=target_ref_id,
                selected_input_ref_ids=directive.selected_ref_hints,
                handler_goal=directive.requested_behavior or "Dry-run handler goal",
            )
        elif patch_type == "CreateWorkerHandoffContract":
            parent_worker_id = target.worker_id or ""
            child_worker_id = target.canonical_name or ""
            input_bindings: tuple[tuple[str, str], ...] = ()
            output_bindings: tuple[tuple[str, str], ...] = ()
            if snapshot.worker_plan is not None:
                for worker in snapshot.worker_plan.workers:
                    if worker.worker_id == child_worker_id:
                        input_bindings = tuple(
                            (field.name, field.name) for field in worker.input_contract
                        )
                        output_bindings = tuple(
                            (field.name, field.name) for field in worker.output_contract
                        )
                        break
            payload = CreateWorkerHandoffContractIntentPayload(
                target_worker_promotion_ref_id=target_ref_id,
                parent_worker_id=parent_worker_id,
                child_worker_id=child_worker_id,
                input_bindings=input_bindings,
                output_bindings=output_bindings,
                input_binding_status="known_present" if input_bindings else "known_empty",
                output_binding_status="known_present" if output_bindings else "known_empty",
            )
        elif patch_type == "ConvertDelegationIntentToMainFlowStep":
            payload = ConvertDelegationToMainFlowStepIntentPayload(
                target_worker_promotion_ref_id=target_ref_id,
                worker_id=target.worker_id or "",
                action_text=directive.requested_behavior or "Keep inline",
            )
        elif patch_type == "ConvertDelegationIntentToRequestInput":
            payload = ConvertDelegationToRequestInputIntentPayload(
                target_worker_promotion_ref_id=target_ref_id,
                worker_id=target.worker_id or "",
                prompt_text=directive.requested_behavior or "Request input",
                value_target=directive.requested_behavior or "",
            )

        # 7. Construct provisional ConstructRepairIntent candidate
        intent = ConstructRepairIntent(
            intent_id=f"prov_int_{directive.directive_id}",
            issue_id=issue.issue_id,
            patch_type=patch_type,
            affordance_id=affordance.affordance_id,
            target_construct_type=target.irs_ref.construct_type,
            target_construct_id=target.irs_ref.construct_id,
            target_slot_name=target.irs_ref.slot_name,
            target_ref_id=target_ref_id,
            selected_ref_ids=directive.selected_ref_hints,
            intent_summary=strategy.display_label,
            repair_goal=strategy.closure_summary,
            materialization_plan_id=affordance.materialization_plan_id,
            payload=payload,
        )

        if candidate_intent is not None:
            self._validate_candidate_intent(
                candidate_intent,
                issue=issue,
                affordance_id=affordance.affordance_id,
                materialization_plan_id=affordance.materialization_plan_id,
                target=target,
                target_ref_id=target_ref_id,
                selected_ref_ids=directive.selected_ref_hints,
            )
            intent = candidate_intent
        # 8. Invoke dry-run materialization
        rendered = self.materialization_service.dry_run_materialize(
            intent=intent,
            target=target,
            refset=refset,
            snapshot=snapshot,
            closure_plan=closure_plan,
            directive=directive,
        )

        # 9. Compute deterministic hashes
        intent_hash = compute_intent_hash(intent)
        directive_hash = compute_directive_hash(directive)
        closure_plan_hash = compute_closure_plan_hash(closure_plan)
        refset_hash = compute_selected_refset_hash(refset)
        llm_config_hash = compute_llm_generation_config_hash(
            {"generation": "disabled", "model": "dry-run"}
        )

        # 9b. Compute StageSliceTypedPlanRefs at preview service level
        slice_refs = []
        for slice_id in closure_plan.stage_slice_chain:
            combined_str = ":".join(
                (
                    slice_id,
                    intent_hash,
                    closure_plan_hash,
                    refset_hash,
                    affordance.materialization_plan_id,
                )
            )
            typed_plan_hash = compute_sha256(combined_str)
            slice_refs.append(
                StageSliceTypedPlanRef(slice_id=slice_id, typed_plan_hash=typed_plan_hash)
            )

        # 9c. Compute preview construct hashes based on closure nodes
        construct_hashes = tuple(
            compute_sha256(f"construct:{node.construct_type}:{node.role}:{node.action}")
            for node in closure_plan.closure_nodes
        )

        # 10. Compute collision-free scoped preview_id
        scope_str = (
            f"{session.session_id}:{issue.issue_id}:{snapshot.snapshot_id}:"
            f"{intent_hash}:{directive_hash}:{closure_plan_hash}:{refset_hash}"
        )
        preview_id = f"prev_{compute_sha256(scope_str)}"

        # 11. Construct PreviewMaterializationResult
        preview_res = PreviewMaterializationResult(
            preview_id=preview_id,
            base_snapshot_id=snapshot.snapshot_id,
            intent_hash=intent_hash,
            directive_hash=directive_hash,
            closure_plan_hash=closure_plan_hash,
            selected_refset_id=refset.set_id,
            slice_typed_plan_hashes=tuple(slice_refs),
            preview_construct_hashes=construct_hashes,
            llm_generation_config_hash=llm_config_hash,
            rendered_preview=rendered,
        )

        # 12. Register with PreviewStore
        store.put(
            session_id=session.session_id,
            issue_id=issue.issue_id,
            base_snapshot_id=snapshot.snapshot_id,
            preview=preview_res,
            ttl_seconds=ttl_seconds,
        )

        return preview_res

    @staticmethod
    def _validate_candidate_intent(
        intent: ConstructRepairIntent,
        *,
        issue: EditableIssue,
        affordance_id: str,
        materialization_plan_id: str,
        target: RepairTarget,
        target_ref_id: str,
        selected_ref_ids: tuple[str, ...],
    ) -> None:
        if intent.issue_id != issue.issue_id:
            raise PreviewError(
                f"Candidate issue mismatch: '{intent.issue_id}' != '{issue.issue_id}'."
            )
        if intent.affordance_id != affordance_id:
            raise PreviewError(
                f"Candidate affordance mismatch: '{intent.affordance_id}' != '{affordance_id}'."
            )
        if intent.materialization_plan_id != materialization_plan_id:
            raise PreviewError("Candidate plan mismatch.")
        if intent.target_construct_type != target.irs_ref.construct_type:
            raise PreviewError("Candidate construct type mismatch.")
        if intent.target_construct_id != target.irs_ref.construct_id:
            raise PreviewError("Candidate construct_id mismatch.")
        if intent.target_slot_name != target.irs_ref.slot_name:
            raise PreviewError("Candidate slot mismatch.")
        if intent.target_ref_id != target_ref_id:
            raise PreviewError(
                f"Candidate target_ref_id mismatch: '{intent.target_ref_id}' != '{target_ref_id}'."
            )
        if tuple(intent.selected_ref_ids) != tuple(selected_ref_ids):
            raise PreviewError(
                "Candidate intent selected_ref_ids do not match directive selected_ref_hints."
            )

