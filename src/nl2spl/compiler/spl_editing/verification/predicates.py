"""Common verification predicates.

Predicates are pure functions: ``(VerificationResult or artifacts) -> bool``.
They are composed by the verification runner, but patch-specific
verifiers remain inside their patch directories.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import VerificationResult
from nl2spl.compiler.spl_editing.verification.diagnostic_diff import (
    DiagnosticDiffResult,
)


def no_new_blocking_diagnostics(diff: DiagnosticDiffResult) -> bool:
    """True when the diff has zero new blocking diagnostics."""
    return not diff.has_new_blocking


def target_diagnostic_resolved(
    diff: DiagnosticDiffResult,
    target_diagnostic_id: str,
) -> bool:
    """True when *target_diagnostic_id* is in the resolved set."""
    return target_diagnostic_id in diff.resolved_ids


def verification_accepted(result: VerificationResult) -> bool:
    """True when the verification result is accepted."""
    return result.accepted
