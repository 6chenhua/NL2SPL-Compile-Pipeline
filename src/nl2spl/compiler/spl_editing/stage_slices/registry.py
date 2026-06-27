"""Registry for repair-mode stage slices."""

from __future__ import annotations

from typing import Protocol

from nl2spl.compiler.spl_editing.stage_slices.errors import (
    DuplicateStageSliceError,
    StageAuthorityMismatchError,
    StageSliceNotFoundError,
)
from nl2spl.compiler.spl_editing.stage_slices.model import StageSliceInput
from nl2spl.compiler.spl_editing.stage_slices.result import StageSliceResult


class RepairModeStageSlice(Protocol):
    """Protocol for stage-authorized repair-mode slice implementations."""

    @property
    def slice_id(self) -> str:
        """Globally unique slice id."""
        ...

    @property
    def stage_authority(self) -> str:
        """Compiler stage authority that owns this slice."""
        ...

    @property
    def policy_id(self) -> str:
        """Default stage policy id for this slice."""
        ...

    @property
    def output_artifacts(self) -> tuple[str, ...]:
        """Artifact names this slice may emit or update."""
        ...

    @property
    def write_layers(self) -> tuple[str, ...]:
        """Materialization write layers this slice may target."""
        ...

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        """Execute the slice using typed-plan constrained inputs."""
        ...


class StageSliceRegistry:
    """Registry of repair-mode stage slices, separate from materialization plans."""

    def __init__(self) -> None:
        self._slices: dict[str, RepairModeStageSlice] = {}

    def register(
        self,
        stage_slice: RepairModeStageSlice,
        *,
        expected_stage_authority: str | None = None,
    ) -> None:
        """Register a stage slice and validate authority metadata."""
        if not stage_slice.slice_id or not stage_slice.slice_id.strip():
            raise ValueError("slice_id must not be empty")
        if stage_slice.slice_id in self._slices:
            raise DuplicateStageSliceError(
                f"Stage slice '{stage_slice.slice_id}' is already registered."
            )
        if not stage_slice.stage_authority or not stage_slice.stage_authority.strip():
            raise ValueError("stage_authority must not be empty")
        if (
            expected_stage_authority is not None
            and stage_slice.stage_authority != expected_stage_authority
        ):
            raise StageAuthorityMismatchError(
                f"Stage slice '{stage_slice.slice_id}' has authority "
                f"'{stage_slice.stage_authority}', expected '{expected_stage_authority}'."
            )
        self._slices[stage_slice.slice_id] = stage_slice

    def get(self, slice_id: str) -> RepairModeStageSlice:
        """Return a registered stage slice by id."""
        if slice_id not in self._slices:
            raise StageSliceNotFoundError(f"Stage slice '{slice_id}' is not registered.")
        return self._slices[slice_id]

    def has(self, slice_id: str) -> bool:
        """Return whether a stage slice id is registered."""
        return slice_id in self._slices

    def list_slice_ids(self) -> tuple[str, ...]:
        """Return registered slice ids in deterministic order."""
        return tuple(sorted(self._slices))