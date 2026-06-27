"""Exception types for repair-mode stage slices."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError


class StageSliceError(SPLEditingError):
    """Base exception for repair-mode stage slice failures."""


class DuplicateStageSliceError(StageSliceError):
    """Raised when registering a duplicate stage slice id."""


class StageSliceNotFoundError(StageSliceError):
    """Raised when a requested stage slice is not registered."""


class StageAuthorityMismatchError(StageSliceError):
    """Raised when a slice is registered or executed under the wrong authority."""


class StageSliceValidationError(StageSliceError):
    """Raised when a stage-slice input, result, or typed plan is invalid."""