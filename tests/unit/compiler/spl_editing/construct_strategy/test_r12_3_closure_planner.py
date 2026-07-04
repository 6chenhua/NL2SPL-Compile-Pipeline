"""Unit tests for Phase R12.3 ConstructClosurePlan Planner."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.closure import (
    ClosurePlanError,
    ClosurePlanner,
    ConstructClosureNode,
    ConstructClosurePlan,
)
from nl2spl.compiler.spl_editing.closure.validators import validate_closure_plan
from nl2spl.compiler.spl_editing.core.model import RepairTarget
from nl2spl.compiler.spl_editing.preview import compute_closure_plan_hash
from nl2spl.compiler.spl_editing.strategy import RepairDirective, RepairStrategySpec
from nl2spl.compiler.spl_editing.strategy.defaults import build_default_strategy_registry
from nl2spl.ir.diagnostics import DiagnosticIRSRef


@pytest.fixture
def strategy_registry():
    return build_default_strategy_registry()


def _make_target(
    target_ref: str = "worker:w_main.exception_flow:exc_1",
    construct_type: str = "EXCEPTION_FLOW",
    slot_name: str = "handler_action",
    affordance_id: str = "exception_flow.add_handler_step",
) -> RepairTarget:
    return RepairTarget(
        target_ref=target_ref,
        target_kind="element",
        irs_ref=DiagnosticIRSRef(
            construct_type=construct_type,
            construct_id="target_1",
            slot_name=slot_name,
            construct_path=(),
            source_authority="post_normalize_irs",
        ),
        affordance_id=affordance_id,
        construct_path=(),
        editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
    )


def _make_directive(
    directive_id: str = "dir_1",
    source: str = "system_default",
    target_construct_type: str = "EXCEPTION_FLOW",
    target_slot_name: str = "handler_action",
    selected_ref_hints: tuple[str, ...] = (),
) -> RepairDirective:
    return RepairDirective(
        directive_id=directive_id,
        source=source,  # type: ignore[arg-type]
        target_construct_type=target_construct_type,
        target_slot_name=target_slot_name,
        selected_ref_hints=selected_ref_hints,
    )


def _directive_for_target(target: RepairTarget, **kwargs: object) -> RepairDirective:
    return _make_directive(
        target_construct_type=target.irs_ref.construct_type,
        target_slot_name=target.irs_ref.slot_name,
        **kwargs,
    )


def test_missing_handler_closure_plan(strategy_registry) -> None:
    """Verify missing_handler closure plan has ensure block + materialize command."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    target = _make_target()
    directive = _directive_for_target(target)

    plan = ClosurePlanner.generate_closure_plan("plan_1", strategy, target, directive)

    assert plan.closure_plan_id == "plan_1"
    assert plan.strategy_id == strategy.strategy_id
    assert plan.materialization_plan_id == "stage7.exception_handler_step_repair.v1"
    assert plan.target_construct_ref == target.target_ref
    assert plan.default_or_directive_driven == "default"

    assert len(plan.closure_nodes) == 2
    n0, n1 = plan.closure_nodes
    assert n0.role == "handler_block"
    assert n0.construct_type == "BLOCK"
    assert n0.action == "ensure"
    assert n0.required is True
    assert n0.stage_slice_id == "stage5.exception_handler_block_repair.v1"

    assert n1.role == "handler_action"
    assert n1.construct_type == "COMMAND"
    assert n1.action == "materialize"
    assert n1.required is True
    assert n1.stage_slice_id == "stage7.exception_handler_command_repair.v1"


def test_missing_output_producer_closure_plan(strategy_registry) -> None:
    """Missing-output closure ensures placement and materializes a producer."""
    strategy = strategy_registry.get("required_output.materialize_producer.v1")
    target = _make_target(
        construct_type="REQUIRED_OUTPUT",
        slot_name="producer",
        affordance_id="required_output.insert_or_bind_producer",
    )
    directive = _directive_for_target(target)

    plan = ClosurePlanner.generate_closure_plan("plan_2", strategy, target, directive)

    assert plan.materialization_plan_id == "stage7.step_producer_repair.v1"
    assert len(plan.closure_nodes) == 2
    n0, n1 = plan.closure_nodes
    assert n0.role == "placement_block"
    assert n0.construct_type == "BLOCK"
    assert n0.action == "ensure"
    assert n0.required is False
    assert n0.stage_slice_id == "stage7.required_output_producer_command_repair.v1"

    assert n1.role == "producer_command"
    assert n1.construct_type == "COMMAND"
    assert n1.action == "materialize"
    assert n1.required is True
    assert n1.stage_slice_id == "stage7.required_output_producer_command_repair.v1"


def test_worker_delegation_closure_plan(strategy_registry) -> None:
    """Verify worker_delegation closure plan has handoff + invoke + binding nodes."""
    strategy = strategy_registry.get("worker_delegation.complete_closure.v2")
    target = _make_target(
        construct_type="WORKER_PROMOTION",
        slot_name="promotion_input_contract",
        affordance_id="worker_promotion.resolve_contract",
    )
    directive = RepairDirective(
        directive_id="dir_worker_v2",
        source="user",
        target_construct_type="WORKER_PROMOTION",
        target_slot_name="promotion_input_contract",
        requested_behavior="Define the child worker closure",
        option_id="define_child_worker",
    )

    plan = ClosurePlanner.generate_closure_plan("plan_3", strategy, target, directive)

    assert plan.materialization_plan_id == "worker_delegation.complete_closure.v2"
    assert plan.option_id == "define_child_worker"
    assert [node.construct_type for node in plan.closure_nodes] == [
        "CHILD_WORKER",
        "FLOW",
        "BLOCK",
        "COMMAND",
        "WORKER_HANDOFF",
        "BLOCK",
        "INVOKE_WORKER",
    ]
    assert plan.closure_nodes[0].action == "ensure"
    assert plan.closure_nodes[-1].action == "materialize"


def test_missing_target_ref_rejected(strategy_registry) -> None:
    """Verify that a target with missing or empty target_ref raises ClosurePlanError."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    target = _make_target(target_ref="")
    directive = _directive_for_target(target)

    with pytest.raises(ClosurePlanError, match="Target construct reference must not be empty"):
        ClosurePlanner.generate_closure_plan("plan_err", strategy, target, directive)


def test_strategy_target_mismatch_rejected(strategy_registry) -> None:
    strategy = strategy_registry.get("required_output.materialize_producer.v1")
    target = _make_target()
    directive = _directive_for_target(target)

    with pytest.raises(ClosurePlanError, match="does not match strategy target_construct_type"):
        ClosurePlanner.generate_closure_plan("plan_mismatch", strategy, target, directive)


def test_affordance_strategy_mismatch_rejected(strategy_registry) -> None:
    base_strategy = strategy_registry.get("required_output.materialize_producer.v1")
    strategy = RepairStrategySpec(
        strategy_id=base_strategy.strategy_id,
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        diagnostic_kind="missing_handler",
        missing_construct_closure=base_strategy.missing_construct_closure,
        default_policy_id=base_strategy.default_policy_id,
        directive_policy_id=base_strategy.directive_policy_id,
        stage_slice_chain=base_strategy.stage_slice_chain,
        verification_lane=base_strategy.verification_lane,
        supported_patch_types=base_strategy.supported_patch_types,
        selectable_ref_policy_id=base_strategy.selectable_ref_policy_id,
        required_context_facts=base_strategy.required_context_facts,
    )
    target = _make_target()
    directive = _directive_for_target(target)

    with pytest.raises(ClosurePlanError, match="repair_strategy_id.*does not match strategy"):
        ClosurePlanner.generate_closure_plan("plan_aff_mismatch", strategy, target, directive)


def test_directive_target_mismatch_rejected(strategy_registry) -> None:
    strategy = strategy_registry.get("required_output.materialize_producer.v1")
    target = _make_target(
        construct_type="REQUIRED_OUTPUT",
        slot_name="producer",
        affordance_id="required_output.insert_or_bind_producer",
    )
    directive = _make_directive(
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="output_name",
    )

    with pytest.raises(ClosurePlanError, match="Directive target_slot_name"):
        ClosurePlanner.generate_closure_plan("plan_bad_directive", strategy, target, directive)


def test_selected_refs_required_when_directive_hints_present(strategy_registry) -> None:
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    target = _make_target()
    directive = _directive_for_target(
        target,
        source="user",
        selected_ref_hints=("ref_missing",),
    )

    with pytest.raises(ClosurePlanError, match="selectable_refs are required"):
        ClosurePlanner.generate_closure_plan(
            "plan_missing_refset",
            strategy,
            target,
            directive,
            selectable_refs=None,
        )


def test_selected_ref_hint_must_exist(strategy_registry) -> None:
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    target = _make_target()
    directive = _directive_for_target(
        target,
        source="user",
        selected_ref_hints=("ref_missing",),
    )

    with pytest.raises(ClosurePlanError, match="not found in selectable refs"):
        ClosurePlanner.generate_closure_plan(
            "plan_missing_ref",
            strategy,
            target,
            directive,
            selectable_refs={"other_ref": object()},
        )


def test_selected_ref_hint_present_allows_directive_plan(strategy_registry) -> None:
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    target = _make_target()
    directive = _directive_for_target(
        target,
        source="user",
        selected_ref_hints=("ref_1",),
    )

    plan = ClosurePlanner.generate_closure_plan(
        "plan_ref_ok",
        strategy,
        target,
        directive,
        selectable_refs={"ref_1": object()},
    )

    assert plan.default_or_directive_driven == "directive_driven"


def test_strategy_template_action_mismatch_rejected(strategy_registry) -> None:
    """Verify that a legal action string is rejected when it is illegal for the strategy role."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    target = _make_target()

    plan = ConstructClosurePlan(
        closure_plan_id="plan_bad_action",
        strategy_id=strategy.strategy_id,
        materialization_plan_id="stage7.exception_handler_step_repair.v1",
        target_construct_ref="some_ref",
        closure_nodes=(
            ConstructClosureNode(
                role="handler_block",
                construct_type="BLOCK",
                action="ensure",
                stage_slice_id="stage5.exception_handler_block_repair.v1",
            ),
            ConstructClosureNode(
                role="handler_action",
                construct_type="COMMAND",
                action="bind_existing",
                stage_slice_id="stage7.exception_handler_command_repair.v1",
            ),
        ),
        stage_slice_chain=strategy.stage_slice_chain,
        write_layers=(),
        dependency_closure=(),
        default_or_directive_driven="default",
    )
    with pytest.raises(ClosurePlanError, match="does not match the strategy closure template"):
        validate_closure_plan(plan, strategy, target)


def test_stage_slice_missing_from_strategy_chain_rejected(strategy_registry) -> None:
    """Verify that template stage slices must be present in the strategy chain."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    target = _make_target()
    broken_strategy = RepairStrategySpec(
        strategy_id=strategy.strategy_id,
        target_construct_type=strategy.target_construct_type,
        target_slot_name=strategy.target_slot_name,
        diagnostic_kind=strategy.diagnostic_kind,
        missing_construct_closure=strategy.missing_construct_closure,
        default_policy_id=strategy.default_policy_id,
        directive_policy_id=strategy.directive_policy_id,
        stage_slice_chain=("stage5.exception_handler_block_repair.v1",),
        verification_lane=strategy.verification_lane,
        supported_patch_types=strategy.supported_patch_types,
        selectable_ref_policy_id=strategy.selectable_ref_policy_id,
        required_context_facts=strategy.required_context_facts,
        display_label=strategy.display_label,
        closure_summary=strategy.closure_summary,
        preview_required=strategy.preview_required,
    )
    plan = ConstructClosurePlan(
        closure_plan_id="plan_bad_slice",
        strategy_id=broken_strategy.strategy_id,
        materialization_plan_id="stage7.exception_handler_step_repair.v1",
        target_construct_ref="some_ref",
        closure_nodes=(
            ConstructClosureNode(
                role="handler_block",
                construct_type="BLOCK",
                action="ensure",
                stage_slice_id="stage5.exception_handler_block_repair.v1",
            ),
            ConstructClosureNode(
                role="handler_action",
                construct_type="COMMAND",
                action="materialize",
                stage_slice_id="stage7.exception_handler_command_repair.v1",
            ),
        ),
        stage_slice_chain=broken_strategy.stage_slice_chain,
        write_layers=(),
        dependency_closure=(),
        default_or_directive_driven="default",
    )
    with pytest.raises(ClosurePlanError, match="does not exist in strategy stage chain"):
        validate_closure_plan(plan, broken_strategy, target)


def test_materialization_plan_id_mismatch_rejected(strategy_registry) -> None:
    """Verify that a plan with mismatched materialization_plan_id raises ClosurePlanError."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    target = _make_target()

    plan = ConstructClosurePlan(
        closure_plan_id="plan_bad_mat",
        strategy_id=strategy.strategy_id,
        materialization_plan_id="mismatched_mat_plan_id",
        target_construct_ref="some_ref",
        closure_nodes=(
            ConstructClosureNode(
                role="handler_block",
                construct_type="BLOCK",
                action="ensure",
                stage_slice_id="stage5.exception_handler_block_repair.v1",
            ),
            ConstructClosureNode(
                role="handler_action",
                construct_type="COMMAND",
                action="materialize",
                stage_slice_id="stage7.exception_handler_command_repair.v1",
            ),
        ),
        stage_slice_chain=strategy.stage_slice_chain,
        write_layers=(),
        dependency_closure=(),
        default_or_directive_driven="default",
    )
    with pytest.raises(ClosurePlanError, match="does not match affordance materialization_plan_id"):
        validate_closure_plan(plan, strategy, target)


def test_closure_plan_hash_determinism(strategy_registry) -> None:
    """Verify closure plan hash is deterministic and sensitive to changes."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    target = _make_target()
    directive = _directive_for_target(target)

    plan1 = ClosurePlanner.generate_closure_plan("plan_1", strategy, target, directive)
    plan2 = ClosurePlanner.generate_closure_plan("plan_1", strategy, target, directive)
    plan3 = ClosurePlanner.generate_closure_plan("plan_different", strategy, target, directive)

    hash1 = compute_closure_plan_hash(plan1)
    hash2 = compute_closure_plan_hash(plan2)
    hash3 = compute_closure_plan_hash(plan3)

    assert hash1 == hash2
    assert hash1 != hash3
