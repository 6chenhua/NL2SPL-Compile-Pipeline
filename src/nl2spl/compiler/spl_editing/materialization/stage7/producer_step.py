"""Stage7 required-output producer step materializer.

This module implements the Stage 7 authorised materializer that inserts a new
``StepIR`` as the producer for a ``REQUIRED_OUTPUT`` slot.

Design constraints
------------------
* Does NOT import ``Materializer`` from ``registry.py`` --structural subtyping
  ensures Protocol compatibility without creating a circular dependency.
* All validation that can be checked from ``MaterializationInput`` is
  performed before any mutation.
* The input ``ArtifactSnapshot`` is never mutated in place.
"""

from __future__ import annotations

import json
from dataclasses import replace

from nl2spl.compiler.spl_editing.core.model import RepairEvidenceRef
from nl2spl.compiler.spl_editing.core.revision import (
    ArtifactSnapshot,
    OverlayEvent,
    RevisionToken,
)
from nl2spl.compiler.spl_editing.intent.model import InsertProducerStepIntentPayload
from nl2spl.compiler.spl_editing.materialization.errors import (
    DependencyClosureValidationError,
)
from nl2spl.compiler.spl_editing.materialization.model import (
    MaterializationInput,
    MaterializationResult,
)
from nl2spl.ir.step_ir import StepIR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MATERIALIZER_ID = "stage7.step_producer_repair.v1"
_STAGE_AUTHORITY = "stage7.worker_step_plan"


# ---------------------------------------------------------------------------
# Materializer
# ---------------------------------------------------------------------------


class Stage7ProducerRepairMaterializer:
    """Stage 7 materializer for inserting a required-output producer step.

    Implements the ``Materializer`` Protocol via structural subtyping --the
    registry matches on ``materializer_id``, ``stage_authority``, and
    ``materialize()`` at call time.
    """

    @property
    def materializer_id(self) -> str:
        return _MATERIALIZER_ID

    @property
    def stage_authority(self) -> str:
        return _STAGE_AUTHORITY

    def materialize(self, input_data: MaterializationInput) -> MaterializationResult:
        """Validate intent and snapshot, allocate a step ID, build StepIR, derive snapshot."""
        intent = input_data.intent
        snapshot = input_data.snapshot
        target = input_data.target
        evidence_packet = input_data.evidence_packet
        id_allocator = input_data.id_allocator
        resolved_refs = input_data.resolved_refs

        # ------------------------------------------------------------------
        # 1. Payload type validation
        # ------------------------------------------------------------------
        payload = intent.payload
        if not isinstance(payload, InsertProducerStepIntentPayload):
            raise DependencyClosureValidationError(
                f"Stage7ProducerRepairMaterializer requires InsertProducerStepIntentPayload "
                f"but received {type(payload).__name__!r}."
            )

        producer_goal: str = payload.producer_goal

        # ------------------------------------------------------------------
        # 2. Goal content validation
        # ------------------------------------------------------------------
        if not producer_goal or not producer_goal.strip():
            raise DependencyClosureValidationError("producer_goal must not be empty or whitespace.")

        # Reject every REF-token prefix, including malformed and self-closing
        # variants, before free text can reach a renderer.
        normalized_goal = producer_goal.casefold()
        if "<ref" in normalized_goal or "</ref" in normalized_goal:
            raise DependencyClosureValidationError(
                "producer_goal must not contain <REF or </REF tokens; "
                "use canonical ref names directly."
            )

        # ------------------------------------------------------------------
        # 3. Target worker existence check
        # ------------------------------------------------------------------
        worker_id: str = target.worker_id or ""
        step_plan = snapshot.worker_step_plan
        if step_plan is None:
            raise DependencyClosureValidationError("worker_step_plan is missing from snapshot.")
        if worker_id not in step_plan.worker_steps:
            raise DependencyClosureValidationError(
                f"Target worker '{worker_id}' not found in worker_step_plan.worker_steps."
            )

        # ------------------------------------------------------------------
        # 4. Resolve inputs and output
        # ------------------------------------------------------------------
        output_name: str = target.canonical_name or ""
        if not output_name:
            raise DependencyClosureValidationError(
                "RepairTarget.canonical_name is required but empty."
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

        input_names: list[str] = [r.ref.canonical_name for r in resolved_refs]
        outputs: list[str] = [output_name]

        # ------------------------------------------------------------------
        # 5. Allocate step ID
        # ------------------------------------------------------------------
        step_id = id_allocator.allocate_step_id()

        # ------------------------------------------------------------------
        # 6. Build StepIR with complete audit metadata
        # ------------------------------------------------------------------
        consumed_ref_ids: tuple[str, ...] = tuple(r.ref.ref_id for r in resolved_refs)
        metadata: dict = {
            "origin": "user_confirmed_repair",
            "repair_patch_id": evidence_packet.repair_patch_id,
            "related_diagnostic_id": evidence_packet.related_diagnostic_id,
            "evidence_packet_id": evidence_packet.evidence_packet_id,
            "materialization_authority": _STAGE_AUTHORITY,
            "materialization_plan_id": _MATERIALIZER_ID,
            "consumed_selected_ref_ids": json.dumps(list(consumed_ref_ids)),
            "selected_ref_canonical_names": json.dumps(input_names),
            "target_output_ref_id": payload.target_output_ref_id,
            "target_output_name": output_name,
            "user_text": evidence_packet.user_text,
        }

        new_step = StepIR(
            step_id=step_id,
            text=producer_goal.strip(),
            source_span_ids=[],
            command_type="GENERAL_COMMAND",
            inputs=input_names,
            outputs=outputs,
            flow_ref="main",
            metadata=metadata,
        )

        # ------------------------------------------------------------------
        # 7. Build new WorkerStepPlanIR without mutating the input snapshot
        # ------------------------------------------------------------------
        # Deep-copy the per-worker step lists (list-of-StepIR values are
        # themselves frozen, so shallow copy of each list is sufficient).
        new_worker_steps: dict[str, list] = {
            wid: list(steps) for wid, steps in step_plan.worker_steps.items()
        }
        new_worker_steps[worker_id] = new_worker_steps[worker_id] + [new_step]

        new_step_plan = replace(step_plan, worker_steps=new_worker_steps)

        # ------------------------------------------------------------------
        # 8. Derive new snapshot
        # ------------------------------------------------------------------
        next_token = RevisionToken(
            compile_run_id=snapshot.compile_run_id,
            artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=snapshot.overlay_version + 1,
        )
        patched_snapshot: ArtifactSnapshot = snapshot.derive(
            next_token,
            worker_step_plan=new_step_plan,
            final_spl=None,
            final_worker=None,
        )

        # ------------------------------------------------------------------
        # 9. Construct OverlayEvent and evidence refs
        # ------------------------------------------------------------------
        overlay_id = f"ov_{snapshot.snapshot_id}_{next_token.overlay_version}"
        overlay_event = OverlayEvent(
            overlay_id=overlay_id,
            base_compile_run_id=snapshot.compile_run_id,
            base_artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=next_token.overlay_version,
            patch_type=intent.patch_type,
            affordance_id=intent.affordance_id,
            patch_id=evidence_packet.repair_patch_id,
            accepted=True,
        )

        changed_ref = f"step:{worker_id}:{step_id}"
        evidence_ref = RepairEvidenceRef(
            artifact_ref=changed_ref,
            repair_patch_id=evidence_packet.repair_patch_id,
            related_diagnostic_id=evidence_packet.related_diagnostic_id,
            user_text=evidence_packet.user_text,
        )

        # ------------------------------------------------------------------
        # 10. Return result
        # ------------------------------------------------------------------
        return MaterializationResult(
            patched_snapshot=patched_snapshot,
            overlay_event=overlay_event,
            changed_refs=(changed_ref,),
            changed_step_ids=(step_id,),
            changed_handoff_ids=(),
            evidence_refs=(evidence_ref,),
            materialization_plan_id=_MATERIALIZER_ID,
            materializer_id=_MATERIALIZER_ID,
            materialization_authority=_STAGE_AUTHORITY,
            consumed_selected_ref_ids=consumed_ref_ids,
            evidence_packet_id=evidence_packet.evidence_packet_id,
            dependency_validation_metadata={},  # populated by service post-call
        )
