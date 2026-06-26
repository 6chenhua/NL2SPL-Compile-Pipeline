"""AddExceptionHandlerStep applier disabled after R9 materialization migration."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent
from nl2spl.compiler.spl_editing.patches.base import PatchApplier


class AddExceptionHandlerStepApplier(PatchApplier):
    """Disabled. Use RepairMaterializationService for AddExceptionHandlerStep."""

    def apply(
        self,
        patch: RepairPatch,
        snapshot: ArtifactSnapshot,
    ) -> tuple[ArtifactSnapshot, OverlayEvent]:
        raise SPLEditingError(
            "AddExceptionHandlerStepApplier.apply() is disabled. "
            "AddExceptionHandlerStep must go through RepairMaterializationService."
        )
