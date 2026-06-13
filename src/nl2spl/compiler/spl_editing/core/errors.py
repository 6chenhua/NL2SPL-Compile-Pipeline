"""SPL Editing typed errors.

Every error raised by SPL Editing code inherits from ``SPLEditingError``.
Catchers should never fall back to bare ``except Exception`` — typed errors
let the service/CLI surface actionable messages to the user.
"""

from __future__ import annotations


class SPLEditingError(Exception):
    """Base for all SPL Editing errors."""


class UnsupportedIssueError(SPLEditingError):
    """The diagnostic does not map to a supported editable issue.

    Raised when the extractor cannot find a repair affordance, when the
    authority is not accepted, or when the issue is non-repairable.
    """


class UnsupportedPatchTypeError(SPLEditingError):
    """The patch type is not in the allowed set for this affordance.

    Raised by the parser / suggestion handler when the LLM outputs a
    patch type outside the allowed list declared in the catalog entry.
    """


class PatchValidationError(SPLEditingError):
    """Preconditions for applying a patch are not met.

    Raised by the patch validator when the payload is malformed, the
    target does not match the irs_ref, required artifacts are missing,
    or the patch would violate a structural invariant.
    """


class StaleRevisionError(SPLEditingError):
    """The patch targets a base snapshot that is no longer current.

    Detected via (compile_run_id, artifact_snapshot_id, overlay_version).
    """


class VerificationFailedError(SPLEditingError):
    """The patch did not pass verification.

    Carried by the verification result when one or more verification
    predicates fail.  The diagnostic diff and per-patch verifier output
    explain which conditions were not met.
    """
