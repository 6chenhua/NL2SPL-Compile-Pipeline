"""ConvertDelegationToMainFlowStep applier disabled after R10 migration."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent
from nl2spl.compiler.spl_editing.patches.base import PatchApplier


class ConvertDelegationToMainFlowStepApplier(PatchApplier):
    """Disabled. Use RepairMaterializationService for worker promotion repair."""

    def apply(
        self, patch: RepairPatch, snapshot: ArtifactSnapshot
    ) -> tuple[
        ArtifactSnapshot,
        OverlayEvent,
    ]:
        raise SPLEditingError(
            "ConvertDelegationToMainFlowStepApplier.apply() is disabled. "
            "ConvertDelegationIntentToMainFlowStep must go through RepairMaterializationService."
        )
