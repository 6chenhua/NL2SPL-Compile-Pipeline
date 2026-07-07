"""Validation helpers for draft Admission bridge."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.drafting.admission.errors import DraftAdmissionError
from nl2spl.compiler.spl_editing.drafting.model import StoredRepairDraft, UserRepairInput


def require_draft_acceptance(user_input: UserRepairInput) -> None:
    if not user_input.draft_accepted:
        raise DraftAdmissionError("draft_accepted is required before materialized preview")


def require_strategy_option_identity(stored: StoredRepairDraft, *, option) -> None:
    if stored.option_id != option.option_id:
        raise DraftAdmissionError("option_id mismatch")
    if stored.draft.strategy_id != option.strategy_id:
        raise DraftAdmissionError("strategy_id mismatch")

