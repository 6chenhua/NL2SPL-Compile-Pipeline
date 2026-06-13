"""InsertProducerStep applier."""

from dataclasses import replace

from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent, RevisionToken
from nl2spl.compiler.spl_editing.patches.base import PatchApplier
from nl2spl.ir.step_ir import StepIR


class InsertProducerStepApplier(PatchApplier):
    def apply(self, patch: RepairPatch, snapshot: ArtifactSnapshot) -> tuple[
        ArtifactSnapshot, OverlayEvent,
    ]:
        payload = patch.payload
        worker_id = str(payload.get("worker_id", ""))
        output_name = str(payload.get("output_name", ""))
        text = str(payload.get("producer_text", ""))
        command_type = str(payload.get("command_type", "GENERAL_COMMAND"))
        inputs = list(payload.get("inputs", []))
        outputs = list(payload.get("outputs", [output_name]))
        if output_name not in outputs:
            outputs.append(output_name)

        step_id = f"st_repair_{snapshot.overlay_version + 1}_{worker_id}"
        new_step = StepIR(
            step_id=step_id, text=text, source_span_ids=[],
            command_type=command_type, inputs=inputs, outputs=outputs,
            flow_ref="main",
            metadata={
                "origin": "user_confirmed_repair",
                "repair_patch_id": patch.patch_id,
                "related_diagnostic_id": patch.evidence.related_diagnostic_id,
                "user_text": patch.evidence.user_text,
            },
        )

        step_plan = snapshot.require_worker_step_plan()
        worker_steps = {wid: list(steps) for wid, steps in step_plan.worker_steps.items()}
        if worker_id not in worker_steps:
            from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
            raise PatchValidationError(f"Worker '{worker_id}' not found")
        worker_steps[worker_id].append(new_step)
        new_step_plan = replace(step_plan, worker_steps=worker_steps)

        next_token = RevisionToken(
            snapshot.compile_run_id, snapshot.snapshot_id, snapshot.overlay_version + 1,
        )
        patched = snapshot.derive(next_token, worker_step_plan=new_step_plan,
                                   final_spl=None, final_worker=None)

        event = OverlayEvent(
            overlay_id=f"ov_{snapshot.snapshot_id}_{next_token.overlay_version}",
            base_compile_run_id=snapshot.compile_run_id,
            base_artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=next_token.overlay_version,
            patch_type=patch.patch_type, affordance_id=patch.affordance_id,
            patch_id=patch.patch_id, accepted=True,
        )
        return patched, event
