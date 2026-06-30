"""Data models for SPL Editing Repair Strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


def _to_tuple_of_strings(val: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(val, (list, tuple)):
        raise TypeError(
            f"Field '{field_name}' must be a sequence, got {type(val).__name__}"
        )
    res = []
    for item in val:
        if not isinstance(item, str):
            raise TypeError(
                f"Element in '{field_name}' must be str, got {type(item).__name__}"
            )
        res.append(item)
    return tuple(res)


def _assert_non_empty_str(val: Any, field_name: str) -> None:
    if not isinstance(val, str):
        raise TypeError(
            f"Field '{field_name}' must be str, got {type(val).__name__}"
        )
    if not val.strip():
        raise ValueError(f"Field '{field_name}' cannot be empty or blank")


@dataclass(frozen=True)
class RepairStrategyOptionSpec:
    """Stable user-visible outcome owned by a construct repair strategy."""

    option_id: str
    strategy_id: str
    label_key: str
    description_key: str
    interaction_contract_id: str
    execution_patch_types: tuple[str, ...]
    closure_policy_id: str
    user_facing: bool = True

    def __post_init__(self) -> None:
        for name in (
            "option_id",
            "strategy_id",
            "label_key",
            "description_key",
            "interaction_contract_id",
            "closure_policy_id",
        ):
            _assert_non_empty_str(getattr(self, name), name)
        object.__setattr__(
            self,
            "execution_patch_types",
            _to_tuple_of_strings(self.execution_patch_types, "execution_patch_types"),
        )
        if not self.execution_patch_types:
            raise ValueError("execution_patch_types cannot be empty")


@dataclass(frozen=True)
class RepairStrategySpec:
    """Read-only spec defining construct-level repair direction and missing closure requirements."""

    strategy_id: str
    target_construct_type: str
    target_slot_name: str
    diagnostic_kind: str
    missing_construct_closure: tuple[str, ...]
    default_policy_id: str
    directive_policy_id: str
    stage_slice_chain: tuple[str, ...]
    verification_lane: str = "B"
    supported_patch_types: tuple[str, ...] = ()
    options: tuple[RepairStrategyOptionSpec, ...] = ()
    selectable_ref_policy_id: str | None = None
    required_context_facts: tuple[str, ...] = ()
    display_label: str = ""
    closure_summary: str = ""
    preview_required: bool = False

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.strategy_id, "strategy_id")
        _assert_non_empty_str(self.target_construct_type, "target_construct_type")
        _assert_non_empty_str(self.target_slot_name, "target_slot_name")
        _assert_non_empty_str(self.diagnostic_kind, "diagnostic_kind")
        _assert_non_empty_str(self.default_policy_id, "default_policy_id")
        _assert_non_empty_str(self.directive_policy_id, "directive_policy_id")
        _assert_non_empty_str(self.verification_lane, "verification_lane")
        if self.verification_lane not in {"A", "B"}:
            raise ValueError(
                f"Invalid verification_lane: {self.verification_lane}"
            )

        if self.selectable_ref_policy_id is not None:
            _assert_non_empty_str(
                self.selectable_ref_policy_id, "selectable_ref_policy_id"
            )

        if self.display_label:
            _assert_non_empty_str(self.display_label, "display_label")

        if self.closure_summary:
            _assert_non_empty_str(self.closure_summary, "closure_summary")

        # Normalize to immutable tuples
        object.__setattr__(
            self,
            "missing_construct_closure",
            _to_tuple_of_strings(
                self.missing_construct_closure, "missing_construct_closure"
            ),
        )
        object.__setattr__(
            self,
            "stage_slice_chain",
            _to_tuple_of_strings(self.stage_slice_chain, "stage_slice_chain"),
        )
        object.__setattr__(
            self,
            "supported_patch_types",
            _to_tuple_of_strings(
                self.supported_patch_types, "supported_patch_types"
            ),
        )
        object.__setattr__(
            self,
            "required_context_facts",
            _to_tuple_of_strings(
                self.required_context_facts, "required_context_facts"
            ),
        )
        options = tuple(self.options)
        seen: set[str] = set()
        for option in options:
            if not isinstance(option, RepairStrategyOptionSpec):
                raise TypeError("options must contain RepairStrategyOptionSpec values")
            if option.strategy_id != self.strategy_id:
                raise ValueError(
                    f"Option '{option.option_id}' belongs to '{option.strategy_id}', "
                    f"expected '{self.strategy_id}'"
                )
            if option.option_id in seen:
                raise ValueError(f"Duplicate option_id '{option.option_id}'")
            seen.add(option.option_id)
            unsupported = set(option.execution_patch_types) - set(self.supported_patch_types)
            if unsupported:
                raise ValueError(
                    f"Option '{option.option_id}' uses unsupported patch types: "
                    f"{sorted(unsupported)}"
                )
        object.__setattr__(self, "options", options)


@dataclass(frozen=True)
class RepairDirective:
    """Provisional business intent representing user guidelines or default system choices.

    Strictly provisional prior to confirmation; does not hold evidence authority.
    """

    directive_id: str
    source: Literal["user", "system_default"]
    target_construct_type: str
    target_slot_name: str
    requested_behavior: str | None = None
    selected_ref_hints: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    confidence: float = 1.0
    option_id: str | None = None

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.directive_id, "directive_id")
        _assert_non_empty_str(self.target_construct_type, "target_construct_type")
        _assert_non_empty_str(self.target_slot_name, "target_slot_name")

        if self.source not in {"user", "system_default"}:
            raise ValueError(f"Invalid source: {self.source}")

        if self.requested_behavior is not None:
            _assert_non_empty_str(self.requested_behavior, "requested_behavior")
        if self.option_id is not None:
            _assert_non_empty_str(self.option_id, "option_id")

        if not isinstance(self.confidence, (int, float)):
            raise TypeError(
                f"confidence must be float or int, got {type(self.confidence).__name__}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be in range [0.0, 1.0], got {self.confidence}"
            )

        # Normalize to immutable tuples
        object.__setattr__(
            self,
            "selected_ref_hints",
            _to_tuple_of_strings(self.selected_ref_hints, "selected_ref_hints"),
        )
        object.__setattr__(
            self,
            "constraints",
            _to_tuple_of_strings(self.constraints, "constraints"),
        )

        # Check that no forbidden evidence authority fields are present
        forbidden_attributes = {
            "evidence_packet_id",
            "evidence_status",
            "origin",
            "user_confirmed_repair",
            "materialization_authority",
        }
        for name in forbidden_attributes:
            if hasattr(self, name):
                raise ValueError(
                    f"RepairDirective cannot carry evidence authority field: {name}"
                )
