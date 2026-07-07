"""Admission bridge from inferred repair drafts to existing directives."""

from nl2spl.compiler.spl_editing.drafting.admission.bridge import (
    DraftAdmissionBridge,
    DraftAdmissionResult,
    require_materialized_preview_acceptance,
)

__all__ = [
    "DraftAdmissionBridge",
    "DraftAdmissionResult",
    "require_materialized_preview_acceptance",
]
