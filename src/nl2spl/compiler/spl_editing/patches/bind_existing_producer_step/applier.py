"""BindExistingProducerStep applier — updates output binding, no new StepIR."""

from dataclasses import replace

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent, RevisionToken
from nl2spl.compiler.spl_editing.patches.base import PatchApplier


class BindExistingProducerStepApplier(PatchApplier):
    def apply(self, patch: RepairPatch, snapshot: ArtifactSnapshot) -> tuple[
        ArtifactSnapshot, OverlayEvent,
    ]:
        payload = patch.payload
        worker_id = str(payload.get("worker_id", ""))
        step_id = str(payload.get("step_id", ""))
        output_name = str(payload.get("output_name", ""))

        step_plan = snapshot.require_worker_step_plan()
        if worker_id not in step_plan.worker_steps:
            raise PatchValidationError(f"Worker '{worker_id}' not found")
        steps = step_plan.worker_steps[worker_id]

        target_step = next((s for s in steps if s.step_id == step_id), None)
        if target_step is None:
            raise PatchValidationError(
                f"Step '{step_id}' not found in worker '{worker_id}'")

        new_outputs = list(target_step.outputs)
        if output_name not in new_outputs:
            new_outputs.append(output_name)
        new_meta = dict(target_step.metadata)
        bindings = dict(new_meta.get("repair_output_bindings", {}))
        bindings[output_name] = {
            "repair_patch_id": patch.patch_id,
            "related_diagnostic_id": patch.evidence.related_diagnostic_id,
            "user_text": patch.evidence.user_text,
        }
        new_meta["repair_output_bindings"] = bindings
        new_step = replace(target_step, outputs=new_outputs, metadata=new_meta)

        worker_steps = {wid: list(steps) for wid, steps in step_plan.worker_steps.items()}
        worker_steps[worker_id] = [
            new_step if s.step_id == step_id else s
            for s in worker_steps[worker_id]
        ]
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
