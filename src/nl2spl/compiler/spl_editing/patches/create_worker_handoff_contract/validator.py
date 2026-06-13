"""CreateWorkerHandoffContract validator."""

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchValidator


class CreateWorkerHandoffContractValidator(PatchValidator):
    def validate(self, patch: RepairPatch, snapshot: ArtifactSnapshot) -> None:
        p = patch.payload
        if not isinstance(p, dict):
            raise PatchValidationError("payload must be a dict")

        for field in ("worker_promotion_id", "parent_worker_id", "child_worker_id"):
            v = p.get(field)
            if not isinstance(v, str) or not v:
                raise PatchValidationError(f"payload.{field} required")

        if patch.patch_type != "CreateWorkerHandoffContract":
            raise PatchValidationError(f"Wrong patch_type '{patch.patch_type}'")
        if patch.affordance_id != "worker_promotion.resolve_contract":
            raise PatchValidationError(f"Wrong affordance")
        if patch.irs_ref.construct_type != "WORKER_PROMOTION":
            raise PatchValidationError(
                f"construct_type must be WORKER_PROMOTION, "
                f"got '{patch.irs_ref.construct_type}'")
        if not patch.evidence.related_diagnostic_id:
            raise PatchValidationError("related_diagnostic_id required")

        # Stale revision
        if patch.base_compile_run_id != snapshot.compile_run_id:
            raise PatchValidationError("compile_run_id mismatch")
        if patch.artifact_snapshot_id != snapshot.snapshot_id:
            raise PatchValidationError("snapshot_id mismatch")
        if patch.overlay_version != snapshot.overlay_version:
            raise PatchValidationError("overlay_version mismatch")

        if snapshot.worker_plan is None:
            raise PatchValidationError("worker_plan required")
        if snapshot.worker_step_plan is None:
            raise PatchValidationError("worker_step_plan required")

        # IRS boundary
        if patch.irs_ref.construct_type != "WORKER_PROMOTION":
            raise PatchValidationError(
                f"construct_type must be WORKER_PROMOTION, "
                f"got '{patch.irs_ref.construct_type}'")
        expected_ref = f"worker_promotion:{p['worker_promotion_id']}"
        if patch.target_ref != expected_ref:
            raise PatchValidationError(
                f"target_ref '{patch.target_ref}' != '{expected_ref}'")

        # Worker existence check
        plan = snapshot.worker_plan
        worker_ids = {w.worker_id for w in plan.workers}
        parent_id = p.get("parent_worker_id", "")
        child_id = p.get("child_worker_id", "")
        if parent_id not in worker_ids:
            raise PatchValidationError(
                f"parent_worker_id '{parent_id}' not in worker plan")
        if child_id not in worker_ids:
            raise PatchValidationError(
                f"child_worker_id '{child_id}' not in worker plan")
