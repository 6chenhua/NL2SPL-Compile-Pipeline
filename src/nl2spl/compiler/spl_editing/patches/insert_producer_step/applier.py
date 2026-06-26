"""InsertProducerStep applier.

R6: This applier is DISABLED.  InsertProducerStep is materialized via
``SPLEditingService._apply_via_materialization()`` using the
``Stage7ProducerRepairMaterializer``.  Calling ``apply()`` directly
always raises.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent
from nl2spl.compiler.spl_editing.patches.base import PatchApplier


class InsertProducerStepApplier(PatchApplier):
    """Disabled.  Use ``SPLEditingService._apply_via_materialization()``."""

    def apply(
        self, patch: RepairPatch, snapshot: ArtifactSnapshot
    ) -> tuple[
        ArtifactSnapshot,
        OverlayEvent,
    ]:
        raise SPLEditingError(
            "InsertProducerStepApplier.apply() is disabled. "
            "InsertProducerStep must go through RepairMaterializationService. "
            "Use SPLEditingService._apply_via_materialization() instead."
        )
