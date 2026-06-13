"""BindExistingProducerStep preconditions validator."""

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchValidator


class BindExistingProducerStepValidator(PatchValidator):
    def validate(self, patch: RepairPatch, snapshot: ArtifactSnapshot) -> None:
        payload = patch.payload
        if not isinstance(payload, dict):
            raise PatchValidationError("payload must be a dict")

        worker_id = payload.get("worker_id")
        if not isinstance(worker_id, str) or not worker_id:
            raise PatchValidationError("payload.worker_id is required")

        step_id = payload.get("step_id")
        if not isinstance(step_id, str) or not step_id:
            raise PatchValidationError("payload.step_id is required")

        output_name = payload.get("output_name")
        if not isinstance(output_name, str) or not output_name.strip():
            raise PatchValidationError("payload.output_name is required")

        # Stale revision
        if patch.base_compile_run_id != snapshot.compile_run_id:
            raise PatchValidationError("compile_run_id mismatch")
        if patch.artifact_snapshot_id != snapshot.snapshot_id:
            raise PatchValidationError("snapshot_id mismatch")
        if patch.overlay_version != snapshot.overlay_version:
            raise PatchValidationError("overlay_version mismatch")

        if patch.patch_type != "BindExistingProducerStep":
            raise PatchValidationError(
                f"Patch type '{patch.patch_type}' != 'BindExistingProducerStep'")
        if patch.affordance_id != "required_output.insert_or_bind_producer":
            raise PatchValidationError("Wrong affordance")
        if not patch.evidence.related_diagnostic_id:
            raise PatchValidationError("related_diagnostic_id required")

        # target_ref and irs_ref must match
        expected_ref = f"worker:{worker_id}.output:{output_name}"
        if patch.target_ref != expected_ref:
            raise PatchValidationError(
                f"target_ref '{patch.target_ref}' != '{expected_ref}'")
        if patch.irs_ref.construct_type != "REQUIRED_OUTPUT":
            raise PatchValidationError(
                f"irs_ref.construct_type must be REQUIRED_OUTPUT, "
                f"got '{patch.irs_ref.construct_type}'")
        if patch.irs_ref.slot_name != "producer":
            raise PatchValidationError(
                f"irs_ref.slot_name must be producer, "
                f"got '{patch.irs_ref.slot_name}'")

        # Target step must exist in the specified worker and be renderable
        step_plan = snapshot.worker_step_plan
        if step_plan is None:
            raise PatchValidationError("worker_step_plan required")

        worker_steps = step_plan.worker_steps.get(worker_id, [])
        target_step = next((s for s in worker_steps if s.step_id == step_id), None)
        if target_step is None:
            raise PatchValidationError(
                f"Step '{step_id}' not found in worker '{worker_id}'")
        if not target_step.source_span_ids and target_step.metadata.get("origin") != "user_confirmed_repair":
            raise PatchValidationError(
                f"Step '{step_id}' has no source evidence and is not user-confirmed")
