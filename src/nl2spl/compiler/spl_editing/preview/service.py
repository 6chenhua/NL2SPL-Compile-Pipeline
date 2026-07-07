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
from nl2spl.compiler.spl_editing.preview.artifact import (
    PreviewArtifactChange,
    PreviewConstructNode,
    PreviewStageSliceResult,
    TypedRepairPreviewArtifact,
    compute_preview_hash,
)
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
from nl2spl.compiler.spl_editing.stage_slices.worker_delegation_plans import (
    typed_plan_hashes,
)
from nl2spl.compiler.spl_editing.strategy.model import RepairDirective, RepairStrategySpec
from nl2spl.rendering.spl.construct_renderer import RenderableSPLConstructType


def extract_preview_construct_ir(node: Any, updated_snapshot: Any, main_worker_ir: Any) -> Any:
    # 1. StepIR
    if node.construct_type == "STEP":
        if updated_snapshot.worker_step_plan:
            for step in updated_snapshot.worker_step_plan.get_all_steps():
                if step.step_id == node.role:
                    return step

    # 2. BlockIR
    elif node.construct_type == "BLOCK":
        if updated_snapshot.worker_block_plan:
            for w_blocks in updated_snapshot.worker_block_plan.worker_blocks.values():
                for b in w_blocks.main_flow_blocks:
                    if b.block_id == node.role:
                        return b
                for blocks_list in w_blocks.alternative_flow_blocks.values():
                    for b in blocks_list:
                        if b.block_id == node.role:
                            return b
                for blocks_list in w_blocks.exception_flow_blocks.values():
                    for b in blocks_list:
                        if b.block_id == node.role:
                            return b

    # 3. WorkerIR
    elif node.construct_type == "WORKER":
        if main_worker_ir:
            if main_worker_ir.worker_name == node.role:
                return main_worker_ir
            for child in main_worker_ir.child_workers:
                if child.worker_name == node.role:
                    from nl2spl.ir.worker_ir import WorkerIR

                    return WorkerIR(
                        worker_name=child.worker_name,
                        description=child.description,
                        inputs=child.inputs,
                        outputs=child.outputs,
                        main_flow=child.main_flow,
                        alternative_flows=child.alternative_flows,
                        exception_flows=child.exception_flows,
                        api_refs=child.api_refs,
                        steps=child.steps,
                        scoped_steps=True,
                    )

    # 4. ExceptionFlowRef
    elif node.construct_type == "EXCEPTION_FLOW":
        if main_worker_ir:
            for exc in main_worker_ir.exception_flows:
                if exc.flow_id == node.role:
                    return exc
            for child in main_worker_ir.child_workers:
                for exc in child.exception_flows:
                    if exc.flow_id == node.role:
                        return exc
    return None


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
        # 8. Dry-run materialization slices are executed during construct node building.

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
        v2_plan_hash_pairs: tuple[tuple[str, str], ...] = ()
        normalized_payload = intent.payload
        if strategy.strategy_id == "worker_delegation.complete_closure.v2" and hasattr(
            normalized_payload, "directive_id"
        ):
            from nl2spl.compiler.spl_editing.stage_slices.worker_delegation_plans import (
                build_worker_delegation_typed_plans,
            )

            plan_bundle = build_worker_delegation_typed_plans(snapshot, target, normalized_payload)
            v2_plan_hash_pairs = typed_plan_hashes(plan_bundle)
            actual_hashes = dict(v2_plan_hash_pairs)
            plan_for_slice = {
                "stage3_5.define_child_worker.v1": "child_boundary",
                "stage4.child_worker_flow.v1": "child_flow",
                "stage5.child_worker_block.v1": "child_block",
                "stage7.child_worker_command.v1": "child_command",
                "stage3_5.worker_handoff_contract.v2": "handoff",
                "stage5.parent_invocation_placement.v1": (
                    "keep_main" if plan_bundle.keep_main is not None else "parent_invoke"
                ),
                "stage7.worker_invoke.v2": "parent_invoke",
                "stage7.worker_delegation_resolution_command_repair.v1": "keep_main",
            }
            for slice_id in closure_plan.stage_slice_chain:
                plan_name = plan_for_slice[slice_id]
                slice_refs.append(StageSliceTypedPlanRef(slice_id, actual_hashes[plan_name]))
        else:
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
        construct_hashes = (
            tuple(
                compute_sha256(("construct", plan_name, plan_hash))
                for plan_name, plan_hash in v2_plan_hash_pairs
            )
            if v2_plan_hash_pairs
            else tuple(
                compute_sha256(f"construct:{node.construct_type}:{node.role}:{node.action}")
                for node in closure_plan.closure_nodes
            )
        )

        # 10. Compute collision-free scoped preview_id
        scope_str = (
            f"{session.session_id}:{issue.issue_id}:{snapshot.snapshot_id}:"
            f"{intent_hash}:{directive_hash}:{closure_plan_hash}:{refset_hash}"
        )
        preview_id = f"prev_{compute_sha256(scope_str)}"

        option_id = getattr(normalized_payload, "option_id", "")

        # Generate the list of actual IR objects
        from dataclasses import asdict, replace

        from nl2spl.ir.block_structure_ir import BlockIR
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_ir import (
            ExceptionFlowRef,
            FlowRef,
            WorkerInput,
            WorkerIR,
            WorkerOutput,
        )

        preview_ir_by_role: dict[str, tuple[RenderableSPLConstructType, Any]] = {}

        # Case 1: DefineChildWorkerClosure
        if intent.patch_type == "DefineChildWorkerClosure":
            from nl2spl.compiler.spl_editing.stage_slices.worker_delegation_plans import (
                build_worker_delegation_typed_plans,
            )

            directive_payload = intent.payload
            if hasattr(directive_payload, "admitted_outputs"):
                bundle = build_worker_delegation_typed_plans(snapshot, target, directive_payload)
                # 1. Child worker IR
                inputs = [
                    WorkerInput(name=var.name, required=True)
                    for var in bundle.child_boundary.input_contract
                ]
                outputs = [
                    WorkerOutput(name=var.name, required=True)
                    for var in bundle.child_boundary.output_contract
                ]
                admitted_output_names = [
                    item.canonical_name for item in directive_payload.admitted_outputs
                ]
                renderable_output_names = admitted_output_names
                if len(admitted_output_names) > 1:
                    renderable_output_names = ["_".join(admitted_output_names)]
                child_command = StepIR(
                    step_id=bundle.child_command.command_id,
                    text=directive_payload.child_business_logic,
                    source_span_ids=[],
                    command_type="GENERAL_COMMAND",
                    inputs=[
                        item.ref.canonical_name for item in directive_payload.selected_input_refs
                    ],
                    outputs=renderable_output_names,
                    flow_ref="main",
                    block_ref=bundle.child_block.block_id,
                )
                preview_ir_by_role["child_command"] = (
                    RenderableSPLConstructType.STEP,
                    child_command,
                )
                child_worker = WorkerIR(
                    worker_name=bundle.child_boundary.worker_name,
                    description=bundle.child_boundary.purpose,
                    inputs=inputs,
                    outputs=outputs,
                    main_flow=FlowRef(
                        blocks=[
                            BlockIR(block_id=bundle.child_block.block_id, block_type="SEQUENTIAL")
                        ]
                    ),
                    steps=[child_command],
                    scoped_steps=True,
                )
                preview_ir_by_role["child_worker"] = (
                    RenderableSPLConstructType.WORKER,
                    child_worker,
                )

                # 2. Invoke step in parent worker
                invoke_step = StepIR(
                    step_id=bundle.parent_invoke.command_id,
                    text=f"Invoke {bundle.child_boundary.worker_name}",
                    source_span_ids=[],
                    command_type="INVOKE_WORKER",
                    inputs=[
                        item.ref.canonical_name for item in directive_payload.selected_input_refs
                    ],
                    outputs=renderable_output_names,
                    integration_ref=bundle.child_boundary.worker_name,
                    flow_ref="main",
                    block_ref=bundle.parent_invoke.parent_block_id,
                    kind="invoke",
                    handoff_id=bundle.parent_invoke.handoff_id,
                )
                preview_ir_by_role["parent_invoke"] = (
                    RenderableSPLConstructType.STEP,
                    invoke_step,
                )

        # Case 2: ConvertDelegationIntentToMainFlowStep (keep_in_main_flow)
        elif (
            intent.patch_type
            in {
                "ConvertDelegationIntentToMainFlowStep",
                "ConvertDelegationIntentToRequestInput",
            }
            and hasattr(intent.payload, "option_id")
            and intent.payload.option_id == "keep_in_main_flow"
        ):
            step = StepIR(
                step_id="st_main",
                text=intent.payload.delegated_responsibility,
                source_span_ids=[],
                command_type="GENERAL_COMMAND",
            )
            preview_ir_by_role["main_flow_command"] = (
                RenderableSPLConstructType.STEP,
                step,
            )

        # Case 3: Slices-based execution
        else:
            results = self.materialization_service.execute_dry_run_slices(
                intent=intent,
                target=target,
                refset=refset,
                snapshot=snapshot,
                closure_plan=closure_plan,
                directive=directive,
            )
            if results:
                # Apply updates to snapshot copy
                updated_snapshot = snapshot
                for res in results:
                    for field_name, update in res.artifact_updates.items():
                        updated_snapshot = replace(updated_snapshot, **{field_name: update})

                from nl2spl.pipeline.stages.stage10_worker_assembler.assembler import (
                    WorkerAssembler,
                )

                assembler = WorkerAssembler()
                try:
                    main_worker_ir = assembler.assemble_from_worker_scoped(
                        worker_step_plan=updated_snapshot.worker_step_plan,
                        resources=updated_snapshot.resources,
                        symbol_table=updated_snapshot.symbol_table,
                        worker_plan=updated_snapshot.worker_plan,
                        worker_flow_plan=updated_snapshot.worker_flow_plan,
                        worker_block_plan=updated_snapshot.worker_block_plan,
                    )
                except Exception:
                    main_worker_ir = None

                # Extract preview objects for each closure node
                for node in closure_plan.closure_nodes:
                    ir_obj = extract_preview_construct_ir(node, updated_snapshot, main_worker_ir)
                    if ir_obj is not None:
                        if isinstance(ir_obj, StepIR):
                            render_type = RenderableSPLConstructType.STEP
                        elif isinstance(ir_obj, BlockIR):
                            render_type = RenderableSPLConstructType.BLOCK
                        elif isinstance(ir_obj, ExceptionFlowRef):
                            render_type = RenderableSPLConstructType.EXCEPTION_FLOW
                        elif isinstance(ir_obj, WorkerIR):
                            render_type = RenderableSPLConstructType.WORKER
                        else:
                            continue
                        preview_ir_by_role[node.role] = (render_type, ir_obj)

        # Construct nodes
        preview_nodes = []

        for node in closure_plan.closure_nodes:
            renderable = preview_ir_by_role.get(node.role)
            if renderable is not None:
                ctype, ir_obj = renderable
                payload = asdict(ir_obj)
                status = "dry_run_materialized"
            else:
                if strategy.strategy_id == "worker_delegation.complete_closure.v2":
                    if node.role not in {"main_flow_placement", "worker_handoff"}:
                        continue
                    display = False
                else:
                    display = True
                ctype = None
                payload = {
                    "action": node.action,
                    "construct_type": node.construct_type,
                    "stage_slice_id": node.stage_slice_id or "",
                    "output_ref_role": node.output_ref_role or "",
                    "display": display,
                }
                status = "planned"

            preview_nodes.append(
                PreviewConstructNode(
                    node_id=f"node_{node.role}",
                    node_kind="spl_construct" if renderable is not None else "structured_fallback",
                    spl_construct_type=ctype,
                    role=node.role,
                    ir_payload=payload,
                    materialization_status=status,
                )
            )

        artifact_changes = []
        for node in closure_plan.closure_nodes:
            if node.action in {"materialize", "ensure"}:
                artifact_changes.append(
                    PreviewArtifactChange(
                        change_id=f"change_{node.role}",
                        artifact_type=node.construct_type,
                        change_type="add" if node.action == "materialize" else "modify",
                        target_path=f"worker:{node.role}",
                        description=(
                            f"Materialize or ensure {node.construct_type} for role {node.role}"
                        ),
                    )
                )

        slice_results = []
        for slice_id in closure_plan.stage_slice_chain:
            slice_results.append(
                PreviewStageSliceResult(
                    slice_id=slice_id,
                    stage_name=slice_id.split(".")[0],
                    status="success",
                    diagnostic_count=0,
                )
            )

        preview_hash = compute_preview_hash(
            base_snapshot_id=snapshot.snapshot_id,
            issue_id=issue.issue_id,
            strategy_id=strategy.strategy_id,
            option_id=option_id,
            directive_hash=directive_hash,
            closure_plan_hash=closure_plan_hash,
            selected_refset_id=refset.set_id,
            construct_nodes=tuple(preview_nodes),
            artifact_changes=tuple(artifact_changes),
            stage_slice_results=tuple(slice_results),
        )

        typed_artifact = TypedRepairPreviewArtifact(
            preview_id=preview_id,
            base_snapshot_id=snapshot.snapshot_id,
            issue_id=issue.issue_id,
            strategy_id=strategy.strategy_id,
            option_id=option_id,
            directive_hash=directive_hash,
            closure_plan_hash=closure_plan_hash,
            selected_refset_id=refset.set_id,
            construct_nodes=tuple(preview_nodes),
            artifact_changes=tuple(artifact_changes),
            stage_slice_results=tuple(slice_results),
            preview_hash=preview_hash,
        )

        # Render compatibility preview text via the rendering subsystem
        from nl2spl.rendering import SPLRenderContext, render_repair_preview_spl

        context = SPLRenderContext(
            symbol_table=snapshot.symbol_table,
            resources=snapshot.resources,
            profile=snapshot.agent_profile,
        )
        rendered_res = render_repair_preview_spl(typed_artifact, context)
        rendered = rendered_res.text

        # 11. Construct PreviewMaterializationResult
        normalized_hash = (
            compute_sha256(normalized_payload)
            if hasattr(normalized_payload, "directive_id")
            else ""
        )
        admitted_hashes = tuple(
            compute_sha256(item) for item in getattr(normalized_payload, "admitted_outputs", ())
        )
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
            strategy_id=strategy.strategy_id,
            option_id=option_id,
            interaction_contract_hash=(
                compute_sha256(
                    (
                        getattr(normalized_payload, "interaction_contract_id", ""),
                        getattr(normalized_payload, "interaction_contract_version", ""),
                    )
                )
                if option_id
                else ""
            ),
            normalized_directive_hash=normalized_hash,
            admitted_fact_hashes=admitted_hashes,
            typed_artifact=typed_artifact,
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
