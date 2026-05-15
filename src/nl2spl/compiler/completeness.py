"""Completeness calculator — determine compile status from diagnostics.

Computes a three-tier Completeness value (complete / partial / blocked)
based on validation errors and compile diagnostics.  Adapter warnings are
excluded — they describe input shape issues, not compilation problems.
"""

from __future__ import annotations

from nl2spl.compiler.compile_result import Completeness
from nl2spl.ir.diagnostics import CompileDiagnostic


def compute_completeness(
    validation_errors: list[str] | None = None,
    diagnostics: list[CompileDiagnostic] | None = None,
) -> Completeness:
    """Compute the overall compile completeness status.

    Rules:
    - **blocked**: one or more ``validation_errors`` exist (SPL syntax,
      reference, or structure failures that prevent producing a valid
      output).
    - **partial**: no blocking errors, but at least one compile diagnostic
      describes missing, ambiguous, assumed, or anti-fabrication
      information.
    - **complete**: no blocking errors and no diagnostics — the SPL draft
      is fully source-backed with no gaps detected.

    Adapter warnings do NOT affect completeness (they describe input-shape
    issues, not compilation problems).

    Args:
        validation_errors: SPL syntax/reference/structure errors.
        diagnostics: CompileDiagnostic records from all stages.

    Returns:
        ``"complete"``, ``"partial"``, or ``"blocked"``.
    """
    errors = validation_errors or []
    diags = diagnostics or []

    if errors:
        return "blocked"

    if any(d.blocks_completion for d in diags):
        return "partial"

    return "complete"
