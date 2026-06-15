"""Verification runner — orchestrates Lane A/B replay and diagnostics diff.

Does NOT contain patch-specific success rules — those live in
per-patch verifiers inside their patch directories.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import (
    RepairPatch,
    VerificationResult,
    PatchApplyResult,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.verification.diagnostic_diff import DiagnosticDiff
from nl2spl.compiler.spl_editing.verification.generic_evidence_verifier import (
    GenericEvidenceVerifier,
)
from nl2spl.compiler.spl_editing.verification.lanes import (
    LaneAReplayAdapter,
    LaneBReplayAdapter,
    LaneReplayAdapter,
)

_VALID_LANES = frozenset({"A", "B"})


class VerificationRunner:
    """Run verification after a patch is applied.

    1. Select lane (A or B) based on ``patch.verification_lane``.
    2. Replay compiler passes on patched snapshot.
    3. Run ``DiagnosticDiff`` on before/after diagnostics.
    4. Check target diagnostic resolved.
    5. Run patch-specific verifier.
    6. Run ``GenericEvidenceVerifier`` on PatchApplyResult.
    7. Produce ``VerificationResult``.
    """

    def __init__(
        self,
        lane_a: LaneReplayAdapter | None = None,
        lane_b: LaneReplayAdapter | None = None,
        evidence_verifier: GenericEvidenceVerifier | None = None,
    ) -> None:
        self._lane_a = lane_a or LaneAReplayAdapter()
        self._lane_b = lane_b or LaneBReplayAdapter()
        self._diff = DiagnosticDiff()
        self._evidence_verifier = evidence_verifier or GenericEvidenceVerifier()

    def verify(
        self,
        patch: RepairPatch,
        base_snapshot: ArtifactSnapshot,
        patched_snapshot: ArtifactSnapshot,
        patch_verifier: object | None = None,
        *,
        apply_result: PatchApplyResult | None = None,
    ) -> VerificationResult:
        """Run verification for one applied patch.

        Args:
            patch: The applied repair patch.
            base_snapshot: Snapshot BEFORE the patch was applied.
            patched_snapshot: Snapshot AFTER the patch was applied.
            patch_verifier: Optional patch-specific verifier with a
                ``verify(patch, base, patched, artifacts) -> tuple[str,...]`` method.
            apply_result: Optional structured ``PatchApplyResult`` with
                ``changed_refs`` / ``evidence_refs`` for generic evidence audit.

        Returns:
            ``VerificationResult`` with ``accepted=True`` only when all
            checks pass.
        """
        lane = self._select_lane(patch.verification_lane)

        patched_artifacts = lane.replay(patched_snapshot)

        diff_result = self._diff.compare(
            before=base_snapshot.compile_diagnostics,
            after=patched_artifacts.consolidated_diagnostics,
        )

        failure_reasons: list[str] = []

        # Generic: no new blocking diagnostics
        if diff_result.has_new_blocking:
            failure_reasons.append(
                f"New blocking diagnostics: "
                f"{', '.join(diff_result.new_blocking_ids)}"
            )

        # Generic: target diagnostic must be resolved.
        # Require non-empty related_diagnostic_id — a patch without
        # a target diagnostic cannot prove it fixed anything.
        target_id = patch.evidence.related_diagnostic_id
        if not target_id:
            failure_reasons.append(
                "Patch has no related_diagnostic_id in evidence — "
                "cannot verify target resolution."
            )
        elif target_id not in diff_result.resolved_ids:
            failure_reasons.append(
                f"Target diagnostic '{target_id}' was not resolved"
            )

        # Patch-specific verifier
        if patch_verifier is not None:
            verifier_fn = getattr(patch_verifier, "verify", None)
            if verifier_fn is None:
                failure_reasons.append(
                    "Patch verifier does not expose a 'verify' method"
                )
            else:
                patch_failures = verifier_fn(
                    patch, base_snapshot, patched_snapshot, patched_artifacts,
                )
                if not isinstance(patch_failures, tuple):
                    failure_reasons.append(
                        "Patch verifier must return tuple[str, ...]"
                    )
                else:
                    failure_reasons.extend(patch_failures)

        # Generic evidence verifier (U3.5): audit changed refs
        if apply_result is not None:
            evidence_failures = self._evidence_verifier.verify(patch, apply_result)
            failure_reasons.extend(evidence_failures)

        return VerificationResult(
            session_id="",
            patch_id=patch.patch_id,
            accepted=len(failure_reasons) == 0,
            lane=patch.verification_lane,
            resolved_diagnostic_ids=diff_result.resolved_ids,
            new_blocking_diagnostic_ids=diff_result.new_blocking_ids,
            diagnostic_diff_summary=diff_result.summary,
            failure_reasons=tuple(failure_reasons),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _select_lane(self, lane_name: str) -> LaneReplayAdapter:
        if lane_name not in _VALID_LANES:
            raise PatchValidationError(
                f"Unknown verification lane '{lane_name}'. "
                f"Must be one of {sorted(_VALID_LANES)}."
            )
        return self._lane_a if lane_name == "A" else self._lane_b
