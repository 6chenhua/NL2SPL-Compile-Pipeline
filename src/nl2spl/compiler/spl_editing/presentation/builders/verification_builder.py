"""Verification presentation builder."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import VerificationResult
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation.model.verification import (
    VerificationPresentationView,
)
from nl2spl.compiler.spl_editing.presentation.templates.verification_copy import (
    authority_summary,
)


def build_verification_presentation(
    result: VerificationResult,
    *,
    snapshot: ArtifactSnapshot | None = None,
    updated_spl: str | None = None,
) -> VerificationPresentationView:
    return VerificationPresentationView(
        status="accepted" if result.accepted else "rejected",
        resolved=result.resolved_diagnostic_ids,
        new_blocking_diagnostics=result.new_blocking_diagnostic_ids,
        authority_summary=authority_summary(accepted=result.accepted, lane=result.lane),
        new_snapshot_id=snapshot.snapshot_id if snapshot is not None else None,
        overlay_version=snapshot.overlay_version if snapshot is not None else None,
        updated_spl=updated_spl,
    )


__all__ = ["build_verification_presentation"]
