"""Logic for building user confirmation RepairEvidencePacket from ConstructRepairIntent."""

from __future__ import annotations

import time

from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent, RepairEvidencePacket


def create_evidence_packet(
    intent: ConstructRepairIntent,
    repair_patch_id: str,
    related_diagnostic_id: str,
    user_text: str,
) -> RepairEvidencePacket:
    """Create a user confirmed RepairEvidencePacket from a ConstructRepairIntent."""
    return RepairEvidencePacket(
        evidence_packet_id=f"ev_packet_{intent.intent_id}",
        confirmed_intent_id=intent.intent_id,
        repair_patch_id=repair_patch_id,
        related_diagnostic_id=related_diagnostic_id,
        user_text=user_text,
        confirmed_selected_ref_ids=intent.selected_ref_ids,
        confirmed_at=str(int(time.time())),
    )
