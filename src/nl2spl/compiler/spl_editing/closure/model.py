"""Data models for SPL Editing Construct Closure."""

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
class ConstructClosureNode:
    """A single node inside a ConstructClosurePlan."""

    role: str
    construct_type: str
    action: Literal["ensure", "bind_existing", "materialize"]
    required: bool = True
    stage_slice_id: str | None = None
    output_ref_role: str | None = None

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.role, "role")
        _assert_non_empty_str(self.construct_type, "construct_type")
        if self.action not in {"ensure", "bind_existing", "materialize"}:
            raise ValueError(
                f"Invalid ConstructClosureNode action: {self.action}"
            )
        if self.stage_slice_id is not None:
            _assert_non_empty_str(self.stage_slice_id, "stage_slice_id")
        if self.output_ref_role is not None:
            _assert_non_empty_str(self.output_ref_role, "output_ref_role")


@dataclass(frozen=True)
class ConstructClosurePlan:
    """Instance-level construct closure requirements resolved for a repair strategy."""

    closure_plan_id: str
    strategy_id: str
    materialization_plan_id: str
    target_construct_ref: str
    closure_nodes: tuple[ConstructClosureNode, ...]
    stage_slice_chain: tuple[str, ...]
    write_layers: tuple[str, ...]
    dependency_closure: tuple[str, ...]
    default_or_directive_driven: Literal["default", "directive_driven"]
    option_id: str | None = None

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.closure_plan_id, "closure_plan_id")
        _assert_non_empty_str(self.strategy_id, "strategy_id")
        _assert_non_empty_str(
            self.materialization_plan_id, "materialization_plan_id"
        )
        _assert_non_empty_str(self.target_construct_ref, "target_construct_ref")

        if self.default_or_directive_driven not in {
            "default",
            "directive_driven",
        }:
            raise ValueError(
                "Invalid default_or_directive_driven: "
                f"{self.default_or_directive_driven}"
            )

        # Normalize to immutable tuples
        object.__setattr__(
            self,
            "stage_slice_chain",
            _to_tuple_of_strings(self.stage_slice_chain, "stage_slice_chain"),
        )
        object.__setattr__(
            self,
            "write_layers",
            _to_tuple_of_strings(self.write_layers, "write_layers"),
        )
        object.__setattr__(
            self,
            "dependency_closure",
            _to_tuple_of_strings(self.dependency_closure, "dependency_closure"),
        )

        # Validate and normalize closure_nodes as tuple of ConstructClosureNode
        if not isinstance(self.closure_nodes, (list, tuple)):
            raise TypeError(
                "closure_nodes must be a sequence of ConstructClosureNode"
            )
        nodes = []
        for node in self.closure_nodes:
            if not isinstance(node, ConstructClosureNode):
                raise TypeError(
                    "Element in closure_nodes must be ConstructClosureNode, "
                    f"got {type(node).__name__}"
                )
            nodes.append(node)
        object.__setattr__(self, "closure_nodes", tuple(nodes))
