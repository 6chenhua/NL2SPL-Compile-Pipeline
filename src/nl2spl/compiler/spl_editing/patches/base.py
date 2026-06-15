"""Patch framework interfaces.

Every patch type implements these five roles:
    - ``PatchPayload`` — typed payload schema
    - ``PatchValidator`` — preconditions check
    - ``PatchApplier`` — apply to snapshot
    - ``PatchVerifier`` — patch-specific post-apply checks
    - ``PatchPreviewer`` — generate SPL preview
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from nl2spl.compiler.spl_editing.core.model import (
    RepairPatch,
    VerificationResult,
    PatchApplyResult,
    RepairEvidenceRef,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent


class PatchPayload(ABC):
    """Typed payload for a specific patch type."""


class PatchValidator(ABC):
    """Check preconditions before apply.

    Runs *before* the applier.  Failing preconditions raise
    ``PatchValidationError``.
    """

    @abstractmethod
    def validate(
        self,
        patch: RepairPatch,
        snapshot: ArtifactSnapshot,
    ) -> None: ...


class PatchApplier(ABC):
    """Apply a patch to a frozen snapshot.

    Returns a tuple of ``(patched_snapshot, overlay_event)``.
    Must NOT mutate the base snapshot.
    """

    @abstractmethod
    def apply(
        self,
        patch: RepairPatch,
        snapshot: ArtifactSnapshot,
    ) -> tuple[ArtifactSnapshot, OverlayEvent]: ...

    def build_apply_result(
        self,
        patch: RepairPatch,
        before: ArtifactSnapshot,
        after: ArtifactSnapshot,
        overlay_event: OverlayEvent,
    ) -> PatchApplyResult:
        """Derive changed refs and evidence refs by diffing snapshots.

        The base implementation diffs ``worker_step_plan`` step lists
        (step ids AND step content) and ``worker_plan`` handoff lists
        (handoff ids).  Detects both NEW and MODIFIED steps.
        Appliers may override for more precise results.
        """
        changed_step_ids: list[str] = []
        changed_handoff_ids: list[str] = []
        evidence_refs: list[RepairEvidenceRef] = []

        # --- Diff step plans (new + modified) -------------------------------
        before_wsp = before.worker_step_plan
        after_wsp = after.worker_step_plan
        if before_wsp is not None and after_wsp is not None:
            # Build index of before steps: (worker_id, step_id) → step.
            # step_id alone is NOT unique across workers — using it as the
            # sole key causes cross-worker misattribution when multiple
            # workers share step IDs like st_1, st_2.
            before_index: dict[tuple[str, str], object] = {}
            for wid, steps in before_wsp.worker_steps.items():
                for s in steps:
                    before_index[(wid, s.step_id)] = s
            for worker_id, steps in after_wsp.worker_steps.items():
                for s in steps:
                    before_s = before_index.get((worker_id, s.step_id))
                    is_new = before_s is None
                    is_modified = (
                        before_s is not None
                        and _step_content_changed(before_s, s)
                    )
                    if is_new or is_modified:
                        changed_step_ids.append(s.step_id)
                        if s.metadata.get("origin") == "user_confirmed_repair":
                            # New step: UCR metadata on the step itself
                            evidence_refs.append(RepairEvidenceRef(
                                artifact_ref=f"step:{worker_id}:{s.step_id}",
                                repair_patch_id=s.metadata.get("repair_patch_id", ""),
                                related_diagnostic_id=s.metadata.get(
                                    "related_diagnostic_id", ""
                                ),
                                user_text=s.metadata.get("user_text", ""),
                            ))
                        elif "repair_output_bindings" in s.metadata and is_modified:
                            # Modified step: only include bindings that are NEW
                            # or CHANGED relative to before.  Historical bindings
                            # from prior overlays must not be re-validated against
                            # the current patch.
                            after_bindings = s.metadata["repair_output_bindings"]
                            before_bindings = (
                                getattr(before_s, "metadata", {}).get(
                                    "repair_output_bindings", {}
                                )
                                if before_s is not None else {}
                            )
                            if isinstance(after_bindings, dict):
                                for out_name, binding in after_bindings.items():
                                    if not isinstance(binding, dict):
                                        continue
                                    before_binding = (
                                        before_bindings.get(out_name, {})
                                        if isinstance(before_bindings, dict) else {}
                                    )
                                    is_new_binding = out_name not in (
                                        before_bindings if isinstance(before_bindings, dict) else {}
                                    )
                                    is_changed_binding = (
                                        not is_new_binding
                                        and before_binding != binding
                                    )
                                    if is_new_binding or is_changed_binding:
                                        b_pid = binding.get("repair_patch_id")
                                        if b_pid:
                                            evidence_refs.append(RepairEvidenceRef(
                                                artifact_ref=(
                                                    f"step:{worker_id}:{s.step_id}"
                                                    f":output_binding:{out_name}"
                                                ),
                                                repair_patch_id=b_pid,
                                                related_diagnostic_id=binding.get(
                                                    "related_diagnostic_id", "",
                                                ),
                                                user_text=binding.get("user_text", ""),
                                            ))
        elif after_wsp is not None:
            # No before plan → all steps are new
            for worker_id, steps in after_wsp.worker_steps.items():
                for s in steps:
                    changed_step_ids.append(s.step_id)

        # --- Diff handoffs (new only) + generate evidence refs --------------
        before_plan = before.worker_plan
        after_plan = after.worker_plan
        if before_plan is not None and after_plan is not None:
            before_hids = {h.handoff_id for h in before_plan.handoffs}
            for h in after_plan.handoffs:
                if h.handoff_id not in before_hids:
                    changed_handoff_ids.append(h.handoff_id)
                    # Generate evidence ref for every new handoff
                    evidence_refs.append(RepairEvidenceRef(
                        artifact_ref=f"handoff:{h.handoff_id}",
                        repair_patch_id=patch.patch_id,
                        related_diagnostic_id=patch.evidence.related_diagnostic_id,
                        user_text=patch.evidence.user_text,
                    ))
        elif after_plan is not None:
            for h in after_plan.handoffs:
                changed_handoff_ids.append(h.handoff_id)

        return PatchApplyResult(
            patched_snapshot=after,
            overlay_event=overlay_event,
            changed_refs=tuple(
                f"step:{sid}" for sid in changed_step_ids
            ) + tuple(
                f"handoff:{hid}" for hid in changed_handoff_ids
            ),
            changed_step_ids=tuple(changed_step_ids),
            changed_handoff_ids=tuple(changed_handoff_ids),
            evidence_refs=tuple(evidence_refs),
        )


def _step_content_changed(before_step: object, after_step: object) -> bool:
    """Return True if the step's content differs meaningfully."""
    # Compare mutable fields that modification patches change
    b_outputs = tuple(getattr(before_step, "outputs", []))
    a_outputs = tuple(getattr(after_step, "outputs", []))
    if b_outputs != a_outputs:
        return True
    b_inputs = tuple(getattr(before_step, "inputs", []))
    a_inputs = tuple(getattr(after_step, "inputs", []))
    if b_inputs != a_inputs:
        return True
    b_meta = dict(getattr(before_step, "metadata", {}))
    a_meta = dict(getattr(after_step, "metadata", {}))
    if b_meta != a_meta:
        return True
    b_text = getattr(before_step, "text", "")
    a_text = getattr(after_step, "text", "")
    if b_text != a_text:
        return True
    b_integration = getattr(before_step, "integration_ref", None)
    a_integration = getattr(after_step, "integration_ref", None)
    if b_integration != a_integration:
        return True
    return False


class PatchVerifier(ABC):
    """Patch-specific post-apply verification.

    Runs inside the verification lane after the generic
    ``DiagnosticDiff`` has already been checked.  Returns
    a list of failure reasons (empty = success).
    """

    @abstractmethod
    def verify(
        self,
        patch: RepairPatch,
        base_snapshot: ArtifactSnapshot,
        patched_snapshot: ArtifactSnapshot,
        verification_artifacts: Any,  # VerificationArtifacts
    ) -> tuple[str, ...]: ...


class PatchPreviewer(ABC):
    """Generate a human-readable SPL preview for a suggestion."""

    @abstractmethod
    def preview(self, payload: dict[str, Any]) -> str: ...
