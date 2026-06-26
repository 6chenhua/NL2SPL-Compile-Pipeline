"""InsertProducerStep preconditions validator."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchValidator


class InsertProducerStepValidator(PatchValidator):
    def validate(self, patch: RepairPatch, snapshot: ArtifactSnapshot) -> None:
        payload = patch.payload

        # R6: Reject dict payload — InsertProducerStep MUST use ConstructRepairIntent
        if isinstance(payload, dict):
            raise PatchValidationError(
                "InsertProducerStep payload must be ConstructRepairIntent, "
                "not dict. Dict payload is no longer supported for InsertProducerStep."
            )

        from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent

        if not isinstance(payload, ConstructRepairIntent):
            raise PatchValidationError(
                f"InsertProducerStep payload must be ConstructRepairIntent, "
                f"got {type(payload).__name__}"
            )

        # Stale revision
        if patch.base_compile_run_id != snapshot.compile_run_id:
            raise PatchValidationError("compile_run_id mismatch")
        if patch.artifact_snapshot_id != snapshot.snapshot_id:
            raise PatchValidationError("snapshot_id mismatch")
        if patch.overlay_version != snapshot.overlay_version:
            raise PatchValidationError("overlay_version mismatch")

        if patch.patch_type != "InsertProducerStep":
            raise PatchValidationError(f"Patch type '{patch.patch_type}' != 'InsertProducerStep'")
        if patch.affordance_id != "required_output.insert_or_bind_producer":
            raise PatchValidationError(f"Wrong affordance '{patch.affordance_id}'")
        if not patch.evidence.related_diagnostic_id:
            raise PatchValidationError("related_diagnostic_id required")

        # Intent-specific validations
        if not payload.target_ref_id:
            raise PatchValidationError("ConstructRepairIntent.target_ref_id is required")
        if not payload.materialization_plan_id:
            raise PatchValidationError("ConstructRepairIntent.materialization_plan_id is required")

        if patch.irs_ref.construct_type != "REQUIRED_OUTPUT":
            raise PatchValidationError(
                f"irs_ref.construct_type must be REQUIRED_OUTPUT, "
                f"got '{patch.irs_ref.construct_type}'"
            )
        if patch.irs_ref.slot_name != "producer":
            raise PatchValidationError(
                f"irs_ref.slot_name must be producer, got '{patch.irs_ref.slot_name}'"
            )
