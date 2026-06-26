"""BindExistingProducerStep applier disabled after R11 materialization cleanup."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent
from nl2spl.compiler.spl_editing.patches.base import PatchApplier


class BindExistingProducerStepApplier(PatchApplier):
    """Disabled. Missing-output repair must use materialization."""

    def apply(
        self,
        patch: RepairPatch,
        snapshot: ArtifactSnapshot,
    ) -> tuple[ArtifactSnapshot, OverlayEvent]:
        raise SPLEditingError(
            "BindExistingProducerStepApplier.apply() is disabled. "
            "Missing-output producer repair must go through RepairMaterializationService."
        )
