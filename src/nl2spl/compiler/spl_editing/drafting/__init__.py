"""Repair drafting substrate for SPL Editing.

The package owns user input normalization and typed draft models only.  It does
not apply repairs, write overlays, or construct materialization payloads.
"""

from nl2spl.compiler.spl_editing.drafting.model import (
    DraftPreview,
    FieldInference,
    InferenceAlternative,
    InferenceTraceRecord,
    InferredRepairDraft,
    RepairClarificationQuestion,
    StoredRepairDraft,
    UserRepairFieldValue,
    UserRepairInput,
)
from nl2spl.compiler.spl_editing.drafting.provider import (
    RepairInferenceProviderIdentity,
)
from nl2spl.compiler.spl_editing.drafting.registry import (
    DuplicateRepairInferenceProviderError,
    ProviderResolution,
    RepairInferenceProviderRegistry,
)
from nl2spl.compiler.spl_editing.drafting.service import (
    RepairDraftingService,
    RepairDraftingServiceResult,
)
from nl2spl.compiler.spl_editing.drafting.staleness import (
    DraftIdentity,
    DraftStalenessResult,
    StaleRepairDraftError,
)
from nl2spl.compiler.spl_editing.drafting.store import (
    DraftCollisionError,
    DraftNotFoundError,
    DraftStoreKey,
    RepairDraftStore,
)
from nl2spl.compiler.spl_editing.drafting.values import (
    ExplicitNoneValue,
    NewOutputDraftValue,
    PlacementIntentValue,
    RepairFieldValue,
    ResponsibilityValue,
    ResultBindingValue,
    SelectedInputRefsValue,
)

__all__ = [
    "DraftPreview",
    "DraftCollisionError",
    "DraftIdentity",
    "DraftNotFoundError",
    "DraftStalenessResult",
    "DraftStoreKey",
    "DuplicateRepairInferenceProviderError",
    "ExplicitNoneValue",
    "FieldInference",
    "InferenceAlternative",
    "InferenceTraceRecord",
    "InferredRepairDraft",
    "NewOutputDraftValue",
    "PlacementIntentValue",
    "ProviderResolution",
    "RepairClarificationQuestion",
    "RepairDraftStore",
    "RepairDraftingService",
    "RepairDraftingServiceResult",
    "RepairFieldValue",
    "RepairInferenceProviderIdentity",
    "RepairInferenceProviderRegistry",
    "ResponsibilityValue",
    "ResultBindingValue",
    "SelectedInputRefsValue",
    "StoredRepairDraft",
    "StaleRepairDraftError",
    "UserRepairFieldValue",
    "UserRepairInput",
]
