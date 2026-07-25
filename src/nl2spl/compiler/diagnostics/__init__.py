"""Compiler-wide diagnostic domain package."""

from nl2spl.compiler.diagnostics.authority import (
    DiagnosticAuthorityBundle,
    StageLocalDiagnosticBundle,
)
from nl2spl.compiler.diagnostics.consolidator import (
    DiagnosticConsolidationInput,
    DiagnosticConsolidationResult,
    DiagnosticConsolidator,
    DiagnosticDedupKey,
    diagnostic_dedup_key,
    missing_slot_name,
)
from nl2spl.compiler.diagnostics.registry import DiagnosticRegistry, DiagnosticSpec, Severity

__all__ = [
    "DiagnosticAuthorityBundle",
    "DiagnosticConsolidationInput",
    "DiagnosticConsolidationResult",
    "DiagnosticConsolidator",
    "DiagnosticDedupKey",
    "DiagnosticRegistry",
    "DiagnosticSpec",
    "Severity",
    "StageLocalDiagnosticBundle",
    "diagnostic_dedup_key",
    "missing_slot_name",
]
