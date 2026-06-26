"""Stage7 exception-handler step materializer."""

from __future__ import annotations

import json
from dataclasses import replace

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
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.step_ir import StepIR

_MATERIALIZER_ID = "stage7.exception_handler_step_repair.v1"
_STAGE_AUTHORITY = "stage7.worker_step_plan"


class Stage7ExceptionHandlerStepMaterializer:
    """Stage 7 materializer for adding an exception-flow handler step."""

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
        id_allocator = input_data.id_allocator
        resolved_refs = input_data.resolved_refs

        payload = intent.payload
        if not isinstance(payload, AddExceptionHandlerStepIntentPayload):
            raise DependencyClosureValidationError(
                "Stage7ExceptionHandlerStepMaterializer requires "
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

        step_plan = snapshot.worker_step_plan
        block_plan = snapshot.worker_block_plan
        flow_plan = snapshot.worker_flow_plan
        if step_plan is None:
            raise DependencyClosureValidationError("worker_step_plan is missing from snapshot.")
        if block_plan is None:
            raise DependencyClosureValidationError("worker_block_plan is missing from snapshot.")
        if flow_plan is None:
            raise DependencyClosureValidationError("worker_flow_plan is missing from snapshot.")
        if worker_id not in step_plan.worker_steps:
            raise DependencyClosureValidationError(
                f"Target worker '{worker_id}' not found in worker_step_plan.worker_steps."
            )
        worker_flows = getattr(flow_plan, "worker_flows", {})
        fs = worker_flows.get(worker_id)
        if fs is None or not any(
            getattr(ef, "flow_id", None) == flow_id for ef in getattr(fs, "exception_flows", [])
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

        input_names = [r.ref.canonical_name for r in resolved_refs]
        consumed_ref_ids = tuple(r.ref.ref_id for r in resolved_refs)
        step_id = id_allocator.allocate_step_id()
        block_id = id_allocator.allocate_block_id(worker_id)

        metadata = {
            "origin": "user_confirmed_repair",
            "repair_patch_id": evidence_packet.repair_patch_id,
            "related_diagnostic_id": evidence_packet.related_diagnostic_id,
            "evidence_packet_id": evidence_packet.evidence_packet_id,
            "materialization_authority": _STAGE_AUTHORITY,
            "materialization_plan_id": _MATERIALIZER_ID,
            "consumed_selected_ref_ids": json.dumps(list(consumed_ref_ids)),
            "selected_ref_canonical_names": json.dumps(input_names),
            "target_exception_flow_ref_id": payload.target_exception_flow_ref_id,
            "target_exception_flow_id": flow_id,
            "user_text": evidence_packet.user_text,
        }

        new_block = BlockIR(block_id=block_id, block_type="SEQUENTIAL", spans=[])
        new_step = StepIR(
            step_id=step_id,
            text=handler_goal,
            source_span_ids=[],
            command_type="GENERAL_COMMAND",
            inputs=input_names,
            outputs=[],
            flow_ref=flow_id,
            block_ref=block_id,
            metadata=metadata,
        )

        new_worker_steps = {wid: list(steps) for wid, steps in step_plan.worker_steps.items()}
        new_worker_steps[worker_id] = new_worker_steps[worker_id] + [new_step]
        new_step_plan = replace(step_plan, worker_steps=new_worker_steps)

        worker_blocks: dict[str, BlockStructureIR] = {}
        for wid, bs in block_plan.worker_blocks.items():
            eb = {fid: list(blocks) for fid, blocks in bs.exception_flow_blocks.items()}
            worker_blocks[wid] = replace(bs, exception_flow_blocks=eb)
        if worker_id not in worker_blocks:
            worker_blocks[worker_id] = BlockStructureIR()
        current_bs = worker_blocks[worker_id]
        new_exception_blocks = {
            fid: list(blocks) for fid, blocks in current_bs.exception_flow_blocks.items()
        }
        new_exception_blocks[flow_id] = new_exception_blocks.get(flow_id, []) + [new_block]
        worker_blocks[worker_id] = replace(
            current_bs,
            exception_flow_blocks=new_exception_blocks,
        )
        new_block_plan = replace(block_plan, worker_blocks=worker_blocks)

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
        changed_ref = f"step:{worker_id}:{step_id}"
        block_ref = f"block:{worker_id}:{block_id}"
        evidence_ref = RepairEvidenceRef(
            artifact_ref=changed_ref,
            repair_patch_id=evidence_packet.repair_patch_id,
            related_diagnostic_id=evidence_packet.related_diagnostic_id,
            user_text=evidence_packet.user_text,
        )

        return MaterializationResult(
            patched_snapshot=patched_snapshot,
            overlay_event=overlay_event,
            changed_refs=(changed_ref, block_ref),
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
