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

from nl2spl.compiler.spl_editing.core.model import RepairPatch, VerificationResult
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
