"""Neutral editing history DTOs.

These are compiler-owned data transfer objects.  SPL Editing runtime
objects (``OverlayEvent``, ``AcceptedRepairPatch``, verification
results) must be converted to these neutral DTOs before entering
the snapshot document.  The serializer (S1) serializes these DTOs,
NOT the SPL Editing runtime models.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Overlay event DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotOverlayEventDTO:
    """Neutral DTO for one overlay event.

    Mirrors ``spl_editing.core.revision.OverlayEvent`` but lives in the
    compiler-owned snapshot contract so serialization does not depend on
    SPL Editing internals.

    Attributes:
        overlay_id: Unique identifier for this overlay event.
        base_compile_run_id: The compile run that produced the base.
        base_artifact_snapshot_id: The base snapshot id.
        overlay_version: Overlay version after this event.
        patch_type: The patch type that was applied.
        affordance_id: The repair affordance exercised.
        patch_id: Unique identifier of the applied patch.
        accepted: Whether the patch was accepted.
    """

    overlay_id: str
    base_compile_run_id: str
    base_artifact_snapshot_id: str
    overlay_version: int
    patch_type: str
    affordance_id: str
    patch_id: str
    accepted: bool


# ---------------------------------------------------------------------------
# Accepted patch DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotAcceptedPatchDTO:
    """Neutral DTO for one accepted repair patch.

    Mirrors ``spl_editing.core.revision.AcceptedRepairPatch``.

    Attributes:
        patch_id: Unique patch identifier.
        patch_type: The patch type that was applied.
        affordance_id: The repair affordance exercised.
        overlay_id: The overlay event this patch belongs to.
    """

    patch_id: str
    patch_type: str
    affordance_id: str
    overlay_id: str


# ---------------------------------------------------------------------------
# Verification record DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotVerificationRecordDTO:
    """Neutral DTO for one verification run.

    Records the outcome of verifying a patched snapshot through Lane A
    or Lane B replay.

    Attributes:
        verification_id: Unique identifier for this verification.
        overlay_id: The overlay event this verification checked.
        lane: Which replay lane was used (``"A"`` or ``"B"``).
        passed: Whether verification succeeded.
        diagnostic_count_before: Number of diagnostics before the patch.
        diagnostic_count_after: Number of diagnostics after the patch.
        error_messages: Validation error messages, if any.
    """

    verification_id: str
    overlay_id: str
    lane: str
    passed: bool
    diagnostic_count_before: int
    diagnostic_count_after: int
    error_messages: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()


# ---------------------------------------------------------------------------
# Editing history container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotEditingHistory:
    """Container for the full editing history of a snapshot.

    Base snapshots have empty sequences.  Overlay snapshots append to
    the base history.

    Attributes:
        overlay_events: Ordered list of overlay events.
        accepted_patches: Ordered list of accepted patches.
        verification_history: Ordered list of verification records.
    """

    overlay_events: tuple[SnapshotOverlayEventDTO, ...] = ()
    accepted_patches: tuple[SnapshotAcceptedPatchDTO, ...] = ()
    verification_history: tuple[SnapshotVerificationRecordDTO, ...] = ()

    @property
    def is_empty(self) -> bool:
        """``True`` when no editing has occurred (base snapshot)."""
        return (
            len(self.overlay_events) == 0
            and len(self.accepted_patches) == 0
            and len(self.verification_history) == 0
        )


def empty_editing_history() -> SnapshotEditingHistory:
    """Return an empty editing history (for base snapshots)."""
    return SnapshotEditingHistory()
