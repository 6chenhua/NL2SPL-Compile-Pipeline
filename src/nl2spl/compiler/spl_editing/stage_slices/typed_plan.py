"""Typed-plan contracts for repair-mode stage slices."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Protocol

from nl2spl.compiler.spl_editing.stage_slices.errors import StageSliceValidationError

_RAW_IR_FIELD_NAMES = frozenset(
    {
        "step_id",
        "block_id",
        "handoff_id",
        "worker_handoff_id",
        "worker_steps",
        "worker_blocks",
        "worker_handoffs",
        "overlay_event",
        "accepted",
        "patched_snapshot",
        "command_type",
        "block_ir",
        "step_ir",
        "worker_handoff_ir",
    }
)
_RAW_IR_TYPE_NAMES = frozenset({"StepIR", "BlockIR", "WorkerHandoffIR"})


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


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


class TypedPlanGenerator(Protocol):
    """Constrained generator boundary for slice-local typed plans."""

    @property
    def generator_id(self) -> str:
        """Stable generator id for audit."""
        ...

    @property
    def generation_config_hash(self) -> str:
        """Stable hash of deterministic generation config."""
        ...

    def generate_typed_plan(self, plan_kind: str, input_payload: dict[str, Any]) -> Any:
        """Return a slice-local typed plan, never raw IR."""
        ...


@dataclass(frozen=True)
class BlockShapePlan:
    """Slice-local plan for handler or placement block shape."""

    block_type: str
    rationale: str = ""
    child_action_slots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.block_type, "block_type")
        object.__setattr__(
            self,
            "child_action_slots",
            _to_tuple_of_strings(self.child_action_slots, "child_action_slots"),
        )


@dataclass(frozen=True)
class CommandIntentPlan:
    """Slice-local command intent plan; not a StepIR."""

    command_family: str
    user_facing_text: str
    selected_ref_ids: tuple[str, ...] = ()
    output_intent: str | None = None
    rationale: str = ""

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.command_family, "command_family")
        _assert_non_empty_str(self.user_facing_text, "user_facing_text")
        object.__setattr__(
            self,
            "selected_ref_ids",
            _to_tuple_of_strings(self.selected_ref_ids, "selected_ref_ids"),
        )


@dataclass(frozen=True)
class HandoffContractPlan:
    """Slice-local worker handoff contract plan; not WorkerHandoffIR."""

    target_worker_ref_id: str
    input_binding_ref_ids: tuple[str, ...] = ()
    output_binding_ref_ids: tuple[str, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.target_worker_ref_id, "target_worker_ref_id")
        object.__setattr__(
            self,
            "input_binding_ref_ids",
            _to_tuple_of_strings(self.input_binding_ref_ids, "input_binding_ref_ids"),
        )
        object.__setattr__(
            self,
            "output_binding_ref_ids",
            _to_tuple_of_strings(self.output_binding_ref_ids, "output_binding_ref_ids"),
        )


@dataclass(frozen=True)
class InvokeWorkerPlan:
    """Slice-local invoke-worker plan; not an INVOKE_WORKER StepIR."""

    handoff_ref_id: str
    selected_ref_ids: tuple[str, ...] = ()
    placement_ref_id: str | None = None
    invocation_text: str = "Invoke worker"
    rationale: str = ""

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.handoff_ref_id, "handoff_ref_id")
        _assert_non_empty_str(self.invocation_text, "invocation_text")
        object.__setattr__(
            self,
            "selected_ref_ids",
            _to_tuple_of_strings(self.selected_ref_ids, "selected_ref_ids"),
        )


TypedPlan = BlockShapePlan | CommandIntentPlan | HandoffContractPlan | InvokeWorkerPlan


class TypedPlanValidator:
    """Validate slice-local typed plans before any IR materialization."""

    def validate(self, plan: TypedPlan | dict[str, Any]) -> TypedPlan | dict[str, Any]:
        self._reject_raw_ir_shape(plan)
        return plan

    def stable_hash(self, plan: TypedPlan | dict[str, Any]) -> str:
        self.validate(plan)
        payload = json.dumps(_json_safe(plan), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _reject_raw_ir_shape(self, value: Any, path: str = "plan") -> None:
        if type(value).__name__ in _RAW_IR_TYPE_NAMES:
            raise StageSliceValidationError(
                f"Typed plan cannot contain raw IR object at {path}."
            )
        if is_dataclass(value):
            self._reject_raw_ir_shape(asdict(value), path)
            return
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                lowered = key_text.lower()
                if key_text in _RAW_IR_TYPE_NAMES or lowered in _RAW_IR_FIELD_NAMES:
                    raise StageSliceValidationError(
                        f"Typed plan cannot contain raw IR field '{key_text}'."
                    )
                self._reject_raw_ir_shape(child, f"{path}.{key_text}")
            return
        if isinstance(value, (list, tuple)):
            for idx, child in enumerate(value):
                self._reject_raw_ir_shape(child, f"{path}[{idx}]")