"""Complete Worker Delegation v2 closure materialization."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace

from nl2spl.compiler.spl_editing.core.model import RepairEvidenceRef
from nl2spl.compiler.spl_editing.core.revision import OverlayEvent, RevisionToken
from nl2spl.compiler.spl_editing.interaction.model import NormalizedWorkerDelegationDirective
from nl2spl.compiler.spl_editing.materialization.errors import DependencyClosureValidationError
from nl2spl.compiler.spl_editing.materialization.model import MaterializationResult
from nl2spl.compiler.spl_editing.resolution.model import PromotionResolutionMarker
from nl2spl.compiler.spl_editing.stage_slices.result import StageSliceResult
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerHandoffIR,
    WorkerSpecIR,
)

_PLAN_ID = "worker_delegation.complete_closure.v2"
_AUTHORITY = (
    "stage3_5.worker_boundary + stage4.worker_flow_plan + "
    "stage5.worker_block_plan + stage7.worker_step_plan"
)


class DefineChildWorkerClosureMaterializer:
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
                "DefineChildWorkerClosure requires NormalizedWorkerDelegationDirective"
            )
        if directive.option_id == "keep_in_main_flow":
            return self._materialize_keep_main(input_data, directive)
        if directive.option_id != "define_child_worker" or not directive.admitted_outputs:
            raise DependencyClosureValidationError("Incomplete define-child directive")

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
            raise DependencyClosureValidationError("Worker closure artifacts are incomplete")

        parent_id = input_data.target.worker_id or snapshot.worker_plan.main_worker_id
        suffix = hashlib.sha256(
            f"{snapshot.snapshot_id}|{directive.directive_id}|child_worker".encode()
        ).hexdigest()[:10]
        source_spans = list(input_data.issue.source_span_ids)
        input_names = [item.ref.canonical_name for item in directive.selected_input_refs]
        output_names = [item.canonical_name for item in directive.admitted_outputs]

        worker_plan = copy.deepcopy(snapshot.worker_plan)
        existing = [
            worker
            for worker in worker_plan.workers
            if worker.kind == "child"
            and worker.purpose.strip() == directive.delegated_responsibility.strip()
        ]
        if len(existing) > 1:
            raise DependencyClosureValidationError("Ambiguous existing child worker match")
        child_id = existing[0].worker_id if existing else f"worker_child_{suffix}"
        child_name = existing[0].worker_name if existing else f"ChildWorker_{suffix}"
        input_contract = [
            ContractFieldIR(
                name=name,
                data_type="text",
                required=True,
                description=f"Input {name} confirmed for delegated responsibility.",
                source="derived",
                source_span_ids=source_spans,
            )
            for name in input_names
        ]
        output_contract = [
            ContractFieldIR(
                name=item.canonical_name,
                data_type=item.data_type,
                required=True,
                description=item.semantic_description,
                source="derived",
                source_span_ids=source_spans,
            )
            for item in directive.admitted_outputs
        ]
        if not existing:
            worker_plan.workers.append(
                WorkerSpecIR(
                    worker_id=child_id,
                    worker_name=child_name,
                    kind="child",
                    purpose=directive.delegated_responsibility,
                    owned_span_ids=source_spans,
                    input_contract=input_contract,
                    output_contract=output_contract,
                    boundary_kind="child_worker",
                    reason="User-confirmed worker delegation repair",
                    input_contract_status="known_present" if input_contract else "known_empty",
                    output_contract_status="known_present",
                    input_contract_status_source="user_confirmed_repair",
                    output_contract_status_source="user_confirmed_repair",
                )
            )
        else:
            matched = existing[0]
            if ({field.name for field in matched.input_contract} != set(input_names)
                or {field.name for field in matched.output_contract} != set(output_names)):
                raise DependencyClosureValidationError(
                    "Existing child worker contract does not match confirmed directive"
                )

        flow_id = f"flow_child_{suffix}"
        block_id = f"b_child_{suffix}"
        child_step_id = f"st_child_{suffix}"
        handoff_id = f"handoff_{suffix}"
        invoke_step_id = f"st_invoke_{suffix}"

        flow_plan = copy.deepcopy(snapshot.worker_flow_plan)
        if child_id not in flow_plan.worker_flows:
            flow_plan.worker_flows[child_id] = FlowStructureIR(main_flow_spans=source_spans)

        block_plan = copy.deepcopy(snapshot.worker_block_plan)
        if child_id not in block_plan.worker_blocks:
            block_plan.worker_blocks[child_id] = BlockStructureIR(
                main_flow_blocks=[BlockIR(block_id, "SEQUENTIAL", spans=source_spans)]
            )

        metadata = self._metadata(input_data, directive)
        step_plan = copy.deepcopy(snapshot.worker_step_plan)
        child_steps = step_plan.worker_steps.setdefault(child_id, [])
        if not child_steps:
            child_steps.append(
                StepIR(
                    step_id=child_step_id,
                    text=directive.delegated_responsibility,
                    source_span_ids=source_spans,
                    command_type="GENERAL_COMMAND",
                    inputs=input_names,
                    outputs=output_names,
                    flow_ref="main",
                    block_ref=block_id,
                    metadata={**metadata, "closure_role": "child_command"},
                )
            )
        elif len(child_steps) != 1:
            raise DependencyClosureValidationError(
                "MVP existing child reuse requires exactly one child command"
            )

        usage_by_output = {item.output_id: item for item in directive.result_usage}
        output_bindings = []
        parent_outputs = []
        for admitted in directive.admitted_outputs:
            usage = usage_by_output.get(admitted.output_id)
            if usage is None:
                raise DependencyClosureValidationError(
                    f"Missing result usage for '{admitted.output_id}'"
                )
            parent_name = (
                usage.parent_ref.ref.canonical_name
                if usage.parent_ref is not None
                else usage.parent_temporary_name
            )
            if not parent_name:
                raise DependencyClosureValidationError("Invalid result usage target")
            parent_outputs.append(parent_name)
            output_bindings.append(OutputBindingIR(admitted.canonical_name, parent_name, True, "set"))

        placement_span = source_spans[0] if source_spans else None
        ordering = "after"
        if directive.invocation_timing.placement_mode == "before":
            ordering = "before"
        handoff = next((item for item in worker_plan.handoffs if item.handoff_id == handoff_id), None)
        if handoff is None:
            handoff = WorkerHandoffIR(
                handoff_id=handoff_id,
                from_worker=parent_id,
                to_worker=child_id,
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering=ordering,
                input_bindings=[InputBindingIR(name, name, True) for name in input_names],
                output_bindings=output_bindings,
                invoke_location_hint=InvokeLocationHintIR(
                    flow_kind="main",
                    flow_id="main",
                    after_span_id=placement_span if ordering == "after" else None,
                    before_span_id=placement_span if ordering == "before" else None,
                    block_hint="sequential",
                ),
                input_binding_status="known_present" if input_names else "known_empty",
                output_binding_status="known_present",
                input_binding_status_source="user_confirmed_repair",
                output_binding_status_source="user_confirmed_repair",
                materialization_status="materialized",
            )
            worker_plan.handoffs.append(handoff)

        parent_block = self._parent_block(snapshot, directive, parent_id)
        parent_steps = step_plan.worker_steps.setdefault(parent_id, [])
        if not any(step.handoff_id == handoff_id for step in parent_steps):
            parent_steps.append(
                StepIR(
                    step_id=invoke_step_id,
                    text=f"Invoke {child_name}",
                    source_span_ids=source_spans,
                    command_type="INVOKE_WORKER",
                    inputs=input_names,
                    outputs=parent_outputs,
                    integration_ref=child_name,
                    flow_ref="main",
                    block_ref=parent_block,
                    kind="invoke",
                    handoff_id=handoff_id,
                    metadata={**metadata, "closure_role": "parent_invoke"},
                )
            )

        symbol_table = copy.deepcopy(snapshot.symbol_table)
        for name in input_names:
            if symbol_table.lookup(name) is None:
                raise DependencyClosureValidationError(f"Selected input '{name}' is undefined")
            symbol_table.declare_scoped(
                name, "text", "user_confirmed_repair", f"Child input {name}",
                scope_kind="worker", scope_id=child_id, block_ref=block_id,
            )
        for admitted in directive.admitted_outputs:
            symbol_table.declare_scoped(
                admitted.canonical_name,
                admitted.data_type,
                "user_confirmed_repair",
                admitted.semantic_description,
                scope_kind="worker",
                scope_id=child_id,
                block_ref=block_id,
            )
        for usage in directive.result_usage:
            if usage.parent_temporary_name:
                admitted = next(item for item in directive.admitted_outputs if item.output_id == usage.output_id)
                symbol_table.declare_scoped(
                    usage.parent_temporary_name,
                    admitted.data_type,
                    "user_confirmed_repair",
                    "Parent-local temporary handoff result",
                    scope_kind="worker",
                    scope_id=parent_id,
                    block_ref=parent_block,
                )

        changed_refs = (
            f"worker:{child_id}",
            f"flow:{child_id}:main",
            f"block:{child_id}:{block_id}",
            f"step:{child_id}:{child_step_id}",
            f"handoff:{handoff_id}",
            f"step:{parent_id}:{invoke_step_id}",
        )
        marker = PromotionResolutionMarker(
            marker_id=f"promotion_resolution:{directive.directive_id}",
            target_worker_promotion_id=input_data.target.target_ref,
            resolved_diagnostic_group_id=f"worker_promotion_group:{input_data.target.target_ref}",
            resolution_kind="defined_child_worker",
            normalized_directive_id=directive.directive_id,
            materialized_construct_refs=changed_refs,
            evidence_ref=input_data.evidence_packet.evidence_packet_id,
        )
        next_token = RevisionToken(
            snapshot.compile_run_id, snapshot.snapshot_id, snapshot.overlay_version + 1
        )
        patched = snapshot.derive(
            next_token,
            worker_plan=worker_plan,
            worker_flow_plan=flow_plan,
            worker_block_plan=block_plan,
            worker_step_plan=step_plan,
            symbol_table=symbol_table,
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
        stage_results = self._stage_results(directive, changed_refs)
        return MaterializationResult(
            patched_snapshot=patched,
            overlay_event=overlay,
            changed_refs=changed_refs,
            changed_step_ids=(child_step_id, invoke_step_id),
            changed_handoff_ids=(handoff_id,),
            evidence_refs=evidence_refs,
            materialization_plan_id=_PLAN_ID,
            materializer_id=_PLAN_ID,
            materialization_authority=_AUTHORITY,
            consumed_selected_ref_ids=tuple(
                item.ref.ref_id for item in directive.selected_input_refs
            ),
            evidence_packet_id=input_data.evidence_packet.evidence_packet_id,
            dependency_validation_metadata={"normalized_directive_id": directive.directive_id},
            stage_slice_results=stage_results,
            resolution_markers=(marker,),
        )

    def _materialize_keep_main(self, input_data, directive):
        snapshot = input_data.snapshot
        parent_id = input_data.target.worker_id or snapshot.worker_plan.main_worker_id
        suffix = hashlib.sha256(
            f"{snapshot.snapshot_id}|{directive.directive_id}|main_command".encode()
        ).hexdigest()[:10]
        step_id = f"st_main_{suffix}"
        block_id = self._parent_block(snapshot, directive, parent_id)
        input_names = [item.ref.canonical_name for item in directive.selected_input_refs]
        metadata = {
            **self._metadata(input_data, directive),
            "closure_role": "main_flow_command",
            "target_worker_promotion_ref_id": input_data.target.target_ref,
            "resolution_kind": "kept_in_main_flow",
        }
        step_plan = copy.deepcopy(snapshot.worker_step_plan)
        parent_steps = step_plan.worker_steps.setdefault(parent_id, [])
        if any(
            step.metadata.get("normalized_directive_id") == directive.directive_id
            for step in parent_steps
        ):
            raise DependencyClosureValidationError("Directive already materialized")
        parent_steps.append(
            StepIR(
                step_id=step_id,
                text=directive.delegated_responsibility,
                source_span_ids=list(input_data.issue.source_span_ids),
                command_type="GENERAL_COMMAND",
                inputs=input_names,
                outputs=[],
                flow_ref="main",
                block_ref=block_id,
                metadata=metadata,
            )
        )
        changed_refs = (f"step:{parent_id}:{step_id}",)
        marker = PromotionResolutionMarker(
            marker_id=f"promotion_resolution:{directive.directive_id}",
            target_worker_promotion_id=input_data.target.target_ref,
            resolved_diagnostic_group_id=f"worker_promotion_group:{input_data.target.target_ref}",
            resolution_kind="kept_in_main_flow",
            normalized_directive_id=directive.directive_id,
            materialized_construct_refs=changed_refs,
            evidence_ref=input_data.evidence_packet.evidence_packet_id,
        )
        next_token = RevisionToken(
            snapshot.compile_run_id, snapshot.snapshot_id, snapshot.overlay_version + 1
        )
        patched = snapshot.derive(
            next_token,
            worker_step_plan=step_plan,
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
        evidence = RepairEvidenceRef(
            artifact_ref=changed_refs[0],
            repair_patch_id=input_data.evidence_packet.repair_patch_id,
            related_diagnostic_id=input_data.evidence_packet.related_diagnostic_id,
            user_text=input_data.evidence_packet.user_text,
        )
        stage_result = StageSliceResult(
            slice_id="stage7.worker_delegation_resolution_command_repair.v1",
            stage_authority="stage7.worker_step_plan",
            policy_id="worker_delegation.main_flow_closure.v1",
            changed_artifact_refs=changed_refs,
            generated_construct_refs=changed_refs,
            consumed_selected_ref_ids=tuple(
                item.ref.ref_id for item in directive.selected_input_refs
            ),
            consumed_directive_id=directive.directive_id,
            allocated_ids=(step_id,),
            trace={"action": "materialize", "resolution_kind": "kept_in_main_flow"},
        )
        return MaterializationResult(
            patched_snapshot=patched,
            overlay_event=overlay,
            changed_refs=changed_refs,
            changed_step_ids=(step_id,),
            changed_handoff_ids=(),
            evidence_refs=(evidence,),
            materialization_plan_id=_PLAN_ID,
            materializer_id=_PLAN_ID,
            materialization_authority=_AUTHORITY,
            consumed_selected_ref_ids=tuple(
                item.ref.ref_id for item in directive.selected_input_refs
            ),
            evidence_packet_id=input_data.evidence_packet.evidence_packet_id,
            dependency_validation_metadata={"normalized_directive_id": directive.directive_id},
            stage_slice_results=(stage_result,),
            resolution_markers=(marker,),
        )

    @staticmethod
    def _metadata(input_data, directive):
        return {
            "origin": "user_confirmed_repair",
            "repair_patch_id": input_data.evidence_packet.repair_patch_id,
            "related_diagnostic_id": input_data.evidence_packet.related_diagnostic_id,
            "evidence_packet_id": input_data.evidence_packet.evidence_packet_id,
            "normalized_directive_id": directive.directive_id,
            "materialization_plan_id": _PLAN_ID,
            "materialization_authority": _AUTHORITY,
            "consumed_selected_ref_ids": json.dumps(
                [item.ref.ref_id for item in directive.selected_input_refs]
            ),
        }

    @staticmethod
    def _parent_block(snapshot, directive, parent_id: str) -> str:
        blocks = snapshot.worker_block_plan.worker_blocks[parent_id].main_flow_blocks
        if directive.placement_ref is not None:
            target_step_id = directive.placement_ref.ref.canonical_name
            for step in snapshot.worker_step_plan.worker_steps[parent_id]:
                if step.step_id == target_step_id:
                    return step.block_ref
            raise DependencyClosureValidationError("Placement anchor step is missing")
        if not blocks:
            raise DependencyClosureValidationError("Main worker has no placement block")
        return blocks[-1].block_id

    @staticmethod
    def _stage_results(directive, changed_refs):
        specs = (
            ("stage3_5.define_child_worker.v1", "stage3_5.worker_boundary", changed_refs[:1]),
            ("stage4.child_worker_flow.v1", "stage4.worker_flow_plan", changed_refs[1:2]),
            ("stage5.child_worker_block.v1", "stage5.worker_block_plan", changed_refs[2:3]),
            ("stage7.child_worker_command.v1", "stage7.worker_step_plan", changed_refs[3:4]),
            ("stage3_5.worker_handoff_contract.v2", "stage3_5.worker_boundary", changed_refs[4:5]),
            ("stage7.worker_invoke.v2", "stage7.worker_step_plan", changed_refs[5:]),
        )
        return tuple(
            StageSliceResult(
                slice_id=slice_id,
                stage_authority=authority,
                policy_id=slice_id,
                changed_artifact_refs=tuple(refs),
                generated_construct_refs=tuple(refs),
                consumed_selected_ref_ids=tuple(
                    item.ref.ref_id for item in directive.selected_input_refs
                ),
                consumed_directive_id=directive.directive_id,
                trace={"action": "materialize", "typed_plan": slice_id},
            )
            for slice_id, authority, refs in specs
        )
