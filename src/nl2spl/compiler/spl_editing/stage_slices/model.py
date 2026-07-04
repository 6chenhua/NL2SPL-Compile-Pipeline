"""Input contracts for repair-mode stage slices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from nl2spl.compiler.spl_editing.core.model import RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent, RepairEvidencePacket
from nl2spl.compiler.spl_editing.materialization.id_allocator import IdAllocator
from nl2spl.compiler.spl_editing.materialization.model import MaterializationDependencyClosure
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRefSet
from nl2spl.compiler.spl_editing.stage_slices.typed_plan import TypedPlan
from nl2spl.compiler.spl_editing.strategy.model import RepairDirective

GenerationMode = Literal["none", "stored_typed_plan", "constrained_llm"]


def _assert_non_empty_str(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _to_tuple_of_strings(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a sequence")
    result: list[str] = []
    for item in value:
        _assert_non_empty_str(item, field_name)
        result.append(item)
    return tuple(result)


@dataclass(frozen=True)
class StagePolicy:
    """Stage-local policy metadata for a repair-mode slice."""

    policy_id: str
    stage_authority: str
    allowed_typed_plan_kinds: tuple[str, ...] = ()
    generation_mode: GenerationMode = "none"

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.policy_id, "policy_id")
        _assert_non_empty_str(self.stage_authority, "stage_authority")
        object.__setattr__(
            self,
            "allowed_typed_plan_kinds",
            _to_tuple_of_strings(
                self.allowed_typed_plan_kinds,
                "allowed_typed_plan_kinds",
            ),
        )
        if self.generation_mode not in ("none", "stored_typed_plan", "constrained_llm"):
            raise ValueError(f"Unsupported generation_mode: {self.generation_mode}")


@dataclass(frozen=True)
class StageSliceInput:
    """Input bundle passed to one repair-mode stage slice."""

    slice_id: str
    stage_authority: str
    snapshot: ArtifactSnapshot
    target: RepairTarget
    refset: SelectableRefSet
    directive: RepairDirective
    intent: ConstructRepairIntent
    dependency_closure: MaterializationDependencyClosure
    stage_policy: StagePolicy
    selected_ref_ids: tuple[str, ...]
    evidence_packet: RepairEvidencePacket | None = None
    id_allocator: IdAllocator | None = None
    typed_plan: TypedPlan | None = None
    upstream_stage_results: tuple[Any, ...] = ()
    issue: Any | None = None
    dry_run: bool = True

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.slice_id, "slice_id")
        _assert_non_empty_str(self.stage_authority, "stage_authority")
        if self.stage_authority != self.stage_policy.stage_authority:
            raise ValueError(
                "StageSliceInput stage_authority must match stage_policy.stage_authority"
            )
        object.__setattr__(
            self,
            "selected_ref_ids",
            _to_tuple_of_strings(self.selected_ref_ids, "selected_ref_ids"),
        )
        object.__setattr__(
            self,
            "upstream_stage_results",
            tuple(self.upstream_stage_results),
        )
