"""SPL Editing Preview module."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.preview.errors import PreviewError, PreviewStaleError
from nl2spl.compiler.spl_editing.preview.hashes import (
    compute_closure_plan_hash,
    compute_directive_hash,
    compute_intent_hash,
)
from nl2spl.compiler.spl_editing.preview.model import (
    PreviewMaterializationResult,
    StageSliceTypedPlanRef,
)
from nl2spl.compiler.spl_editing.preview.service import PreviewDryRunService
from nl2spl.compiler.spl_editing.preview.store import (
    PreviewStore,
    PreviewStoreError,
)
from nl2spl.compiler.spl_editing.preview.validators import (
    PreviewApplyExpectedState,
    validate_preview_not_stale,
)

__all__ = [
    "StageSliceTypedPlanRef",
    "PreviewMaterializationResult",
    "PreviewError",
    "PreviewStaleError",
    "compute_intent_hash",
    "compute_directive_hash",
    "compute_closure_plan_hash",
    "PreviewStore",
    "PreviewStoreError",
    "PreviewDryRunService",
    "PreviewApplyExpectedState",
    "validate_preview_not_stale",
]