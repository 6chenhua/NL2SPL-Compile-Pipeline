"""Admission bridge errors for repair drafting."""

from nl2spl.compiler.spl_editing.drafting.errors import RepairDraftingError


class DraftAdmissionError(RepairDraftingError):
    """Raised when an inferred draft cannot enter directive admission."""

