"""Frozen typed plans for the Worker Delegation v2 repair closure.

These DTOs are the deterministic boundary between a normalized user directive
and stage-owned IR materialization.  They intentionally contain no IR objects.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields
from typing import Literal

from nl2spl.compiler.spl_editing.materialization.errors import (
    DependencyClosureValidationError,
)
from nl2spl.compiler.spl_editing.stage_slices.typed_plan import TypedPlanValidator


def _required(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class ContractFieldPlan:
    name: str
    data_type: str
    description: str

    def __post_init__(self) -> None:
        _required(self.name, "name")
        _required(self.data_type, "data_type")
        _required(self.description, "description")


@dataclass(frozen=True)
class ResultBindingPlan:
    admitted_output_id: str
    child_output_name: str
    parent_target_name: str
    parent_ref_id: str | None
    creates_parent_local_temporary: bool


@dataclass(frozen=True)
class DefineChildWorkerBoundaryPlan:
    worker_id: str
    worker_name: str
    purpose: str
    input_contract: tuple[ContractFieldPlan, ...]
    output_contract: tuple[ContractFieldPlan, ...]
    reuse_existing: bool


@dataclass(frozen=True)
class ChildWorkerFlowPlan:
    worker_id: str
    flow_id: str
    responsibility: str


@dataclass(frozen=True)
class ChildWorkerBlockPlan:
    worker_id: str
    block_id: str
    block_type: Literal["SEQUENTIAL"]
    flow_ref: Literal["main"]
    parent_worker_id: str
    parent_block_id: str


@dataclass(frozen=True)
class ChildWorkerCommandPlan:
    worker_id: str
    command_id: str
    action_text: str
    input_ref_ids: tuple[str, ...]
    input_names: tuple[str, ...]
    admitted_output_ids: tuple[str, ...]
    output_names: tuple[str, ...]
    block_id: str


@dataclass(frozen=True)
class WorkerHandoffBindingPlan:
    handoff_id: str
    parent_worker_id: str
    child_worker_id: str
    input_bindings: tuple[tuple[str, str], ...]
    output_bindings: tuple[ResultBindingPlan, ...]


@dataclass(frozen=True)
class ParentInvokePlan:
    command_id: str
    parent_worker_id: str
    child_worker_id: str
    child_worker_name: str
    placement_mode: Literal["append", "before", "after"]
    placement_anchor_ref: str | None
    parent_block_id: str
    handoff_id: str
    input_names: tuple[str, ...]
    output_names: tuple[str, ...]


@dataclass(frozen=True)
class WorkerSymbolBindingPlan:
    child_worker_id: str
    child_block_id: str
    parent_worker_id: str
    parent_block_id: str
    parent_invoke_command_id: str
    child_inputs: tuple[ContractFieldPlan, ...]
    child_outputs: tuple[ContractFieldPlan, ...]
    parent_temporaries: tuple[ContractFieldPlan, ...]


@dataclass(frozen=True)
class KeepInMainFlowPlan:
    parent_worker_id: str
    command_id: str
    selected_task_boundary: str
    action_text: str
    placement_mode: Literal["append", "before", "after"]
    placement_anchor_ref: str | None
    parent_block_id: str
    owned_handoff_ids: tuple[str, ...]
    owned_child_worker_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkerDelegationTypedPlanBundle:
    option_id: Literal["define_child_worker", "keep_in_main_flow"]
    child_boundary: DefineChildWorkerBoundaryPlan | None = None
    child_flow: ChildWorkerFlowPlan | None = None
    child_block: ChildWorkerBlockPlan | None = None
    child_command: ChildWorkerCommandPlan | None = None
    handoff: WorkerHandoffBindingPlan | None = None
    parent_invoke: ParentInvokePlan | None = None
    symbol_bindings: WorkerSymbolBindingPlan | None = None
    keep_main: KeepInMainFlowPlan | None = None

    def ordered_plans(self) -> tuple[tuple[str, object], ...]:
        return tuple(
            (field.name, value)
            for field in fields(self)
            if field.name != "option_id" and (value := getattr(self, field.name)) is not None
        )


def build_worker_delegation_typed_plans(snapshot, target, directive):
    """Build and validate a deterministic typed-plan bundle."""

    parent_id = target.worker_id or snapshot.worker_plan.main_worker_id
    parent_block_id = _parent_block_id(snapshot, parent_id, directive)
    if directive.option_id == "keep_in_main_flow":
        owned_handoff_ids, owned_child_worker_ids = _exact_candidate_ownership(
            snapshot, target.target_ref
        )
        plan = KeepInMainFlowPlan(
            parent_worker_id=parent_id,
            command_id=_stable_id(snapshot, directive, "main_command", "st_main"),
            selected_task_boundary=directive.delegated_responsibility,
            action_text=directive.delegated_responsibility,
            placement_mode=directive.invocation_timing.placement_mode,
            placement_anchor_ref=_placement_ref(directive),
            parent_block_id=parent_block_id,
            owned_handoff_ids=owned_handoff_ids,
            owned_child_worker_ids=owned_child_worker_ids,
        )
        bundle = WorkerDelegationTypedPlanBundle(option_id="keep_in_main_flow", keep_main=plan)
        _validate_bundle(bundle)
        return bundle

    if directive.option_id != "define_child_worker" or not directive.admitted_outputs:
        raise DependencyClosureValidationError("Incomplete define-child directive")
    existing = [
        worker
        for worker in snapshot.worker_plan.workers
        if worker.kind == "child"
        and worker.purpose.strip() == directive.delegated_responsibility.strip()
    ]
    if len(existing) > 1:
        raise DependencyClosureValidationError("Ambiguous existing child worker match")
    child_id = (
        existing[0].worker_id
        if existing
        else _stable_id(snapshot, directive, "child_worker", "worker_child")
    )
    child_name = (
        existing[0].worker_name
        if existing
        else _semantic_worker_name(snapshot, directive)
    )
    inputs = tuple(item.ref.canonical_name for item in directive.selected_input_refs)
    input_refs = tuple(item.ref.ref_id for item in directive.selected_input_refs)
    outputs = tuple(item.canonical_name for item in directive.admitted_outputs)
    output_ids = tuple(item.output_id for item in directive.admitted_outputs)
    input_contract = tuple(
        ContractFieldPlan(name, item.ref.type_hint or "text", f"Confirmed child input {name}")
        for name, item in zip(inputs, directive.selected_input_refs, strict=True)
    )
    output_contract = tuple(
        ContractFieldPlan(item.canonical_name, item.data_type, item.semantic_description)
        for item in directive.admitted_outputs
    )
    if existing and (
        {field.name for field in existing[0].input_contract} != set(inputs)
        or {field.name for field in existing[0].output_contract} != set(outputs)
    ):
        raise DependencyClosureValidationError(
            "Existing child worker contract does not match confirmed directive"
        )
    usage_by_output = {item.output_id: item for item in directive.result_usage}
    bindings: list[ResultBindingPlan] = []
    for output in directive.admitted_outputs:
        usage = usage_by_output.get(output.output_id)
        if usage is None:
            raise DependencyClosureValidationError(f"Missing result usage for '{output.output_id}'")
        parent_name = (
            usage.parent_ref.ref.canonical_name
            if usage.parent_ref is not None
            else usage.parent_temporary_name
        )
        if not parent_name:
            raise DependencyClosureValidationError("Invalid result usage target")
        bindings.append(
            ResultBindingPlan(
                output.output_id,
                output.canonical_name,
                parent_name,
                usage.parent_ref.ref.ref_id if usage.parent_ref is not None else None,
                usage.parent_temporary_name is not None,
            )
        )
    existing_blocks = (
        snapshot.worker_block_plan.worker_blocks.get(child_id).main_flow_blocks
        if child_id in snapshot.worker_block_plan.worker_blocks
        else []
    )
    if len(existing_blocks) > 1:
        raise DependencyClosureValidationError(
            "MVP existing child reuse requires exactly one child block"
        )
    block_id = (
        existing_blocks[0].block_id
        if existing_blocks
        else _stable_id(snapshot, directive, "child_block", "b_child")
    )
    existing_commands = snapshot.worker_step_plan.worker_steps.get(child_id, [])
    if len(existing_commands) > 1:
        raise DependencyClosureValidationError(
            "MVP existing child reuse requires exactly one child command"
        )
    if existing_commands and (
        existing_commands[0].text != directive.child_business_logic
        or tuple(existing_commands[0].inputs) != inputs
        or tuple(existing_commands[0].outputs) != outputs
    ):
        raise DependencyClosureValidationError(
            "Existing child command does not match confirmed directive"
        )
    command_id = (
        existing_commands[0].step_id
        if existing_commands
        else _stable_id(snapshot, directive, "child_command", "st_child")
    )
    existing_handoffs = [
        item
        for item in snapshot.worker_plan.handoffs
        if item.from_worker == parent_id and item.to_worker == child_id and item.mode == "invoke"
    ]
    if len(existing_handoffs) > 1:
        raise DependencyClosureValidationError("Ambiguous existing handoff match")
    expected_input_bindings = tuple((name, name) for name in inputs)
    expected_output_bindings = tuple(
        (item.child_output_name, item.parent_target_name) for item in bindings
    )
    if existing_handoffs and (
        tuple(
            (item.parent_variable, item.child_input) for item in existing_handoffs[0].input_bindings
        )
        != expected_input_bindings
        or tuple(
            (item.child_output, item.parent_variable)
            for item in existing_handoffs[0].output_bindings
        )
        != expected_output_bindings
    ):
        raise DependencyClosureValidationError(
            "Existing handoff bindings do not match confirmed directive"
        )
    handoff_id = (
        existing_handoffs[0].handoff_id
        if existing_handoffs
        else _stable_id(snapshot, directive, "handoff", "handoff")
    )
    existing_invokes = [
        step
        for step in snapshot.worker_step_plan.worker_steps.get(parent_id, [])
        if step.command_type == "INVOKE_WORKER" and step.handoff_id == handoff_id
    ]
    if len(existing_invokes) > 1:
        raise DependencyClosureValidationError("Ambiguous existing parent invocation match")
    if existing_invokes and (
        tuple(existing_invokes[0].inputs) != inputs
        or tuple(existing_invokes[0].outputs) != tuple(item.parent_target_name for item in bindings)
        or existing_invokes[0].integration_ref not in {child_id, child_name}
    ):
        raise DependencyClosureValidationError(
            "Existing parent invocation does not match confirmed directive"
        )
    invoke_id = (
        existing_invokes[0].step_id
        if existing_invokes
        else _stable_id(snapshot, directive, "parent_invoke", "st_invoke")
    )
    bundle = WorkerDelegationTypedPlanBundle(
        option_id="define_child_worker",
        child_boundary=DefineChildWorkerBoundaryPlan(
            child_id,
            child_name,
            directive.delegated_responsibility,
            input_contract,
            output_contract,
            bool(existing),
        ),
        child_flow=ChildWorkerFlowPlan(
            child_id,
            _stable_id(snapshot, directive, "child_flow", "flow_child"),
            directive.delegated_responsibility,
        ),
        child_block=ChildWorkerBlockPlan(
            child_id, block_id, "SEQUENTIAL", "main", parent_id, parent_block_id
        ),
        child_command=ChildWorkerCommandPlan(
            child_id,
            command_id,
            directive.child_business_logic,
            input_refs,
            inputs,
            output_ids,
            outputs,
            block_id,
        ),
        handoff=WorkerHandoffBindingPlan(
            handoff_id,
            parent_id,
            child_id,
            expected_input_bindings,
            tuple(bindings),
        ),
        parent_invoke=ParentInvokePlan(
            invoke_id,
            parent_id,
            child_id,
            child_name,
            directive.invocation_timing.placement_mode,
            _placement_ref(directive),
            parent_block_id,
            handoff_id,
            inputs,
            tuple(item.parent_target_name for item in bindings),
        ),
        symbol_bindings=WorkerSymbolBindingPlan(
            child_id,
            block_id,
            parent_id,
            parent_block_id,
            invoke_id,
            input_contract,
            output_contract,
            tuple(
                ContractFieldPlan(
                    usage.parent_temporary_name,
                    next(
                        output.data_type
                        for output in directive.admitted_outputs
                        if output.output_id == usage.output_id
                    ),
                    "Parent-local temporary handoff result",
                )
                for usage in directive.result_usage
                if usage.parent_temporary_name is not None
            ),
        ),
    )
    _validate_bundle(bundle)
    return bundle


def typed_plan_hashes(bundle: WorkerDelegationTypedPlanBundle) -> tuple[tuple[str, str], ...]:
    validator = TypedPlanValidator()
    return tuple((name, validator.stable_hash(plan)) for name, plan in bundle.ordered_plans())


def _stable_id(snapshot, directive, role: str, prefix: str) -> str:
    digest = hashlib.sha256(
        f"{snapshot.snapshot_id}|{directive.directive_id}|{role}|0".encode()
    ).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _stable_digest(snapshot, directive, role: str) -> str:
    return hashlib.sha256(
        f"{snapshot.snapshot_id}|{directive.directive_id}|{role}|0".encode()
    ).hexdigest()[:10]


def _semantic_worker_name(snapshot, directive) -> str:
    """Build a user-facing worker name while keeping worker_id stable separately."""

    base = _pascal_name(directive.delegated_responsibility) or _pascal_name(
        directive.child_business_logic
    )
    if not base:
        base = "DelegatedTask"
    if not base.endswith("Worker"):
        base = f"{base}Worker"
    existing_names = {worker.worker_name for worker in snapshot.worker_plan.workers}
    if base not in existing_names:
        return base
    return f"{base}_{_stable_digest(snapshot, directive, 'child_worker_name')[:4]}"


def _pascal_name(text: str) -> str:
    tokens = _alnum_tokens(text)
    if not tokens:
        return ""
    words = []
    for token in tokens[:8]:
        lowered = token.lower()
        words.append(lowered[:1].upper() + lowered[1:])
    name = "".join(words)
    if name and name[0].isdigit():
        name = f"Task{name}"
    return name


def _alnum_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in text:
        if char.isascii() and char.isalnum():
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _placement_ref(directive) -> str | None:
    return directive.placement_ref.ref.ref_id if directive.placement_ref is not None else None


def _exact_candidate_ownership(
    snapshot, target_ref: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve cleanup ownership only from an exact typed metadata relation.

    Child artifacts are removable only when every handoff targeting that child is
    owned by the same promotion candidate.  Names and identifier substrings are
    deliberately ignored.
    """

    owned_invokes = tuple(
        step
        for steps in snapshot.worker_step_plan.worker_steps.values()
        for step in steps
        if step.command_type == "INVOKE_WORKER"
        and step.handoff_id
        and step.metadata.get("target_worker_promotion_ref_id") == target_ref
    )
    owned_handoffs = {step.handoff_id for step in owned_invokes}
    child_by_handoff = {
        handoff.handoff_id: handoff.to_worker
        for handoff in snapshot.worker_plan.handoffs
        if handoff.handoff_id in owned_handoffs and handoff.to_worker
    }
    owned_child_refs = {step.integration_ref for step in owned_invokes if step.integration_ref}
    candidate_children = set(child_by_handoff.values())
    candidate_children.update(
        worker.worker_id
        for worker in snapshot.worker_plan.workers
        if worker.kind == "child"
        and (worker.worker_id in owned_child_refs or worker.worker_name in owned_child_refs)
    )
    removable_children = {
        child_id
        for child_id in candidate_children
        if all(
            handoff.handoff_id in owned_handoffs
            for handoff in snapshot.worker_plan.handoffs
            if handoff.to_worker == child_id
        )
    }
    return tuple(sorted(owned_handoffs)), tuple(sorted(removable_children))


def _parent_block_id(snapshot, parent_id: str, directive) -> str:
    if directive.placement_ref is not None:
        target_step_id = directive.placement_ref.ref.canonical_name
        matches = [
            step
            for step in snapshot.worker_step_plan.worker_steps.get(parent_id, ())
            if step.step_id == target_step_id and step.block_ref
        ]
        if len(matches) != 1:
            raise DependencyClosureValidationError("Placement anchor step is missing")
        return matches[0].block_ref
    structure = snapshot.worker_block_plan.worker_blocks.get(parent_id)
    if structure is not None and structure.main_flow_blocks:
        return structure.main_flow_blocks[-1].block_id
    return _stable_id(snapshot, directive, "parent_block", "b_main_repair")


def _validate_bundle(bundle: WorkerDelegationTypedPlanBundle) -> None:
    if bundle.option_id == "define_child_worker":
        if len(bundle.ordered_plans()) != 7 or bundle.keep_main is not None:
            raise DependencyClosureValidationError("Invalid define-child typed plan bundle")
        if len(bundle.child_command.output_names) != len(bundle.handoff.output_bindings):
            raise DependencyClosureValidationError("Typed plan output closure is incomplete")
    elif bundle.keep_main is None or len(bundle.ordered_plans()) != 1:
        raise DependencyClosureValidationError("Invalid keep-main typed plan bundle")
    validator = TypedPlanValidator()
    for _name, plan in bundle.ordered_plans():
        validator.validate(plan)


__all__ = [name for name in globals() if name.endswith("Plan") or name.endswith("Bundle")]
