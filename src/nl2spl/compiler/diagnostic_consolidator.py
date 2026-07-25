"""Compatibility shim for diagnostic consolidation.

New code should import from ``nl2spl.compiler.diagnostics``.
"""

from nl2spl.compiler.diagnostics.consolidator import (
    DiagnosticConsolidationInput,
    DiagnosticConsolidationResult,
    DiagnosticConsolidator,
    DiagnosticDedupKey,
    diagnostic_dedup_key,
    missing_slot_name,
)

__all__ = [
    "DiagnosticConsolidationInput",
    "DiagnosticConsolidationResult",
    "DiagnosticConsolidator",
    "DiagnosticDedupKey",
    "diagnostic_dedup_key",
    "missing_slot_name",
]
