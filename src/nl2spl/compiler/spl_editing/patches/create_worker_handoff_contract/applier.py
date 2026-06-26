"""CreateWorkerHandoffContract applier disabled after R10 migration."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent
from nl2spl.compiler.spl_editing.patches.base import PatchApplier


class CreateWorkerHandoffContractApplier(PatchApplier):
    """Disabled. Use RepairMaterializationService for worker handoff repair."""

    def apply(
        self, patch: RepairPatch, snapshot: ArtifactSnapshot
    ) -> tuple[
        ArtifactSnapshot,
        OverlayEvent,
    ]:
        raise SPLEditingError(
            "CreateWorkerHandoffContractApplier.apply() is disabled. "
            "CreateWorkerHandoffContract must go through RepairMaterializationService."
        )
