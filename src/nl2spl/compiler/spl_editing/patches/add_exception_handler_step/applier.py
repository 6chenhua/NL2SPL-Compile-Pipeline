"""AddExceptionHandlerStep applier — writes StepIR into worker plans."""

from __future__ import annotations

from dataclasses import replace

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import (
    ArtifactSnapshot,
    OverlayEvent,
    RevisionToken,
)
from nl2spl.compiler.spl_editing.patches.base import PatchApplier
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerStepPlanIR


class AddExceptionHandlerStepApplier(PatchApplier):
    """Apply an AddExceptionHandlerStep patch.

    Creates a new ``StepIR`` with ``metadata.origin = "user_confirmed_repair"``,
    adds it under ``WorkerStepPlanIR.worker_steps[worker_id]``, creates an
    exception-flow block in ``WorkerBlockPlanIR``, and derives a new snapshot.
    """

    def apply(
        self,
        patch: RepairPatch,
        snapshot: ArtifactSnapshot,
    ) -> tuple[ArtifactSnapshot, OverlayEvent]:
        payload = patch.payload
        worker_id = str(payload.get("worker_id", ""))
        flow_id = str(payload.get("exception_flow_id", ""))
        handler_text = str(payload.get("handler_text", ""))
        command_type = str(payload.get("command_type", "GENERAL_COMMAND"))
        inputs = list(payload.get("inputs", []))
        outputs = list(payload.get("outputs", []))

        # 1. Create the block for this exception flow
        block_id = f"b_repair_{flow_id}"
        new_block = BlockIR(
            block_id=block_id,
            block_type="SEQUENTIAL",
            spans=[],
        )

        # 2. Create the handler StepIR
        step_id = f"st_repair_{snapshot.overlay_version + 1}_{worker_id}"
        new_step = StepIR(
            step_id=step_id,
            text=handler_text,
            source_span_ids=[],
            command_type=command_type,
            inputs=inputs,
            outputs=outputs,
            flow_ref=flow_id,
            block_ref=block_id,
            metadata={
                "origin": "user_confirmed_repair",
                "repair_patch_id": patch.patch_id,
                "related_diagnostic_id": patch.evidence.related_diagnostic_id,
                "user_text": patch.evidence.user_text,
            },
        )

        # 3. Update WorkerStepPlanIR — deep-copy lists to avoid mutating base
        step_plan = snapshot.require_worker_step_plan()
        worker_steps: dict[str, list] = {
            wid: list(steps)
            for wid, steps in step_plan.worker_steps.items()
        }
        worker_steps.setdefault(worker_id, []).append(new_step)
        new_step_plan = replace(step_plan, worker_steps=worker_steps)

        # 4. Update WorkerBlockPlanIR — deep-copy nested dicts/lists
        block_plan = snapshot.require_worker_block_plan()
        worker_blocks: dict[str, BlockStructureIR] = {}
        for wid, bs in block_plan.worker_blocks.items():
            eb = {
                fid: list(blocks)
                for fid, blocks in bs.exception_flow_blocks.items()
            }
            worker_blocks[wid] = replace(bs, exception_flow_blocks=eb)
        if worker_id not in worker_blocks:
            worker_blocks[worker_id] = BlockStructureIR()
        eb2 = worker_blocks[worker_id].exception_flow_blocks
        if flow_id not in eb2:
            new_eb = dict(eb2)
            new_eb.setdefault(flow_id, []).append(new_block)
            worker_blocks[worker_id] = replace(
                worker_blocks[worker_id],
                exception_flow_blocks=new_eb,
            )
        else:
            eb2[flow_id].append(new_block)
        new_block_plan = replace(block_plan, worker_blocks=worker_blocks)

        # 5. Clear stale final outputs (Lane A replay will re-produce them)
        next_token = RevisionToken(
            compile_run_id=snapshot.compile_run_id,
            artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=snapshot.overlay_version + 1,
        )
        patched = snapshot.derive(
            next_token,
            worker_step_plan=new_step_plan,
            worker_block_plan=new_block_plan,
            final_spl=None,
            final_worker=None,
        )

        event = OverlayEvent(
            overlay_id=f"ov_{snapshot.snapshot_id}_{next_token.overlay_version}",
            base_compile_run_id=snapshot.compile_run_id,
            base_artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=next_token.overlay_version,
            patch_type=patch.patch_type,
            affordance_id=patch.affordance_id,
            patch_id=patch.patch_id,
            accepted=True,
        )

        return patched, event
