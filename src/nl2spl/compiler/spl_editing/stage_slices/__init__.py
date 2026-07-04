"""Repair-mode stage slice substrate."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.stage_slices.errors import (
    DuplicateStageSliceError,
    StageAuthorityMismatchError,
    StageSliceError,
    StageSliceNotFoundError,
    StageSliceValidationError,
)
from nl2spl.compiler.spl_editing.stage_slices.model import (
    StagePolicy,
    StageSliceInput,
)
from nl2spl.compiler.spl_editing.stage_slices.registry import (
    RepairModeStageSlice,
    StageSliceRegistry,
)
from nl2spl.compiler.spl_editing.stage_slices.result import StageSliceResult
from nl2spl.compiler.spl_editing.stage_slices.stage3_5 import (
    Stage35WorkerHandoffContractRepairSlice,
)
from nl2spl.compiler.spl_editing.stage_slices.stage5 import Stage5ExceptionHandlerBlockRepairSlice
from nl2spl.compiler.spl_editing.stage_slices.stage7 import (
    Stage7ExceptionHandlerCommandRepairSlice,
    Stage7RequiredOutputProducerCommandRepairSlice,
    Stage7WorkerDelegationResolutionCommandRepairSlice,
    Stage7WorkerInvokeCommandRepairSlice,
)
from nl2spl.compiler.spl_editing.stage_slices.typed_plan import (
    BlockShapePlan,
    CommandIntentPlan,
    HandoffContractPlan,
    InvokeWorkerPlan,
    TypedPlan,
    TypedPlanGenerator,
    TypedPlanValidator,
)
from nl2spl.compiler.spl_editing.stage_slices.worker_delegation_closure import (
    build_worker_delegation_stage_slice_registry,
)

__all__ = [
    "BlockShapePlan",
    "CommandIntentPlan",
    "DuplicateStageSliceError",
    "HandoffContractPlan",
    "InvokeWorkerPlan",
    "RepairModeStageSlice",
    "StageAuthorityMismatchError",
    "StagePolicy",
    "StageSliceError",
    "StageSliceInput",
    "StageSliceNotFoundError",
    "StageSliceRegistry",
    "StageSliceResult",
    "StageSliceValidationError",
    "build_worker_delegation_stage_slice_registry",
    "Stage35WorkerHandoffContractRepairSlice",
    "Stage5ExceptionHandlerBlockRepairSlice",
    "Stage7ExceptionHandlerCommandRepairSlice",
    "Stage7RequiredOutputProducerCommandRepairSlice",
    "Stage7WorkerDelegationResolutionCommandRepairSlice",
    "Stage7WorkerInvokeCommandRepairSlice",
    "TypedPlan",
    "TypedPlanGenerator",
    "TypedPlanValidator",
]
