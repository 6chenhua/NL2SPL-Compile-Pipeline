"""R12.1 unit tests for strategy, closure, and preview models/hash helpers."""

from __future__ import annotations

import dataclasses
import sys
import pytest

from nl2spl.compiler.spl_editing.closure import (
    ConstructClosureNode,
    ConstructClosurePlan,
)
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent
from nl2spl.compiler.spl_editing.preview import (
    PreviewMaterializationResult,
    StageSliceTypedPlanRef,
    compute_closure_plan_hash,
    compute_directive_hash,
    compute_intent_hash,
)
from nl2spl.compiler.spl_editing.strategy import (
    RepairDirective,
    RepairStrategySpec,
)


def _make_intent(
    intent_id: str = "int_1",
    selected_ref_ids: tuple[str, ...] = ("ref_a",),
) -> ConstructRepairIntent:
    return ConstructRepairIntent(
        intent_id=intent_id,
        issue_id="issue_1",
        patch_type="AddExceptionHandlerStep",
        affordance_id="exception_flow.add_handler_step",
        target_construct_type="EXCEPTION_FLOW",
        target_construct_id="exc_1",
        target_slot_name="handler_action",
        target_ref_id="ref_target",
        selected_ref_ids=selected_ref_ids,
        intent_summary="Fix exception flow",
        repair_goal="Handle exception",
    )


def _make_directive(
    directive_id: str = "dir_1",
    selected_ref_hints: tuple[str, ...] = ("ref_a",),
) -> RepairDirective:
    return RepairDirective(
        directive_id=directive_id,
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        requested_behavior="Ask the user for input",
        selected_ref_hints=selected_ref_hints,
        constraints=("c1",),
        confidence=0.9,
    )


def _make_closure_plan(strategy_id: str = "strat_1") -> ConstructClosurePlan:
    node = ConstructClosureNode(
        role="handler_block",
        construct_type="BLOCK",
        action="ensure",
        required=True,
    )
    return ConstructClosurePlan(
        closure_plan_id="plan_1",
        strategy_id=strategy_id,
        materialization_plan_id="mat_plan_1",
        target_construct_ref="target_ref",
        closure_nodes=(node,),
        stage_slice_chain=("slice_1",),
        write_layers=("layer_1",),
        dependency_closure=("dep_1",),
        default_or_directive_driven="default",
    )


class TestR12_1Models:
    def test_dto_immutability_own_fields(self) -> None:
        """Verify all DTO instances are strictly frozen on their own declared fields.

        Each DTO is tested against one of *its own real fields* to confirm that
        ``frozen=True`` correctly raises ``FrozenInstanceError`` on assignment.
        Testing a non-existent field would also raise FrozenInstanceError but
        would not prove the specific field is protected.

        Threat-model note: Python's ``object.__setattr__`` can bypass the
        ``frozen=True`` guard at the C level — this is a known CPython
        implementation limitation (there is no way to close this without a
        metaclass or C extension). The production contract is:
          1. All tuple fields are immutable tuples after construction.
          2. Normal Python assignment (``obj.field = val``) raises FrozenInstanceError.
          3. ``object.__setattr__`` is a deliberate bypass that no production
             caller may use; it is out of the immutability threat model.
        See ``test_tuple_fields_normalized_to_tuples`` for the runtime guard.
        """
        spec = RepairStrategySpec(
            strategy_id="strat_1",
            target_construct_type="EXCEPTION_FLOW",
            target_slot_name="handler_action",
            diagnostic_kind="missing_handler",
            missing_construct_closure=("BLOCK",),
            default_policy_id="default_policy",
            directive_policy_id="dir_policy",
            stage_slice_chain=("slice_1",),
        )
        directive = _make_directive()
        node = ConstructClosureNode(role="r1", construct_type="BLOCK", action="ensure")
        plan = _make_closure_plan()
        ref = StageSliceTypedPlanRef(slice_id="s1", typed_plan_hash="h1")
        result = PreviewMaterializationResult(
            preview_id="prev_1",
            base_snapshot_id="base_1",
            intent_hash="ih1",
            directive_hash="dh1",
            closure_plan_hash="cph1",
            selected_refset_id="refset_1",
            slice_typed_plan_hashes=(ref,),
            preview_construct_hashes=("pch1",),
            llm_generation_config_hash="gh1",
            rendered_preview="preview text",
        )

        # Each entry: (object, one of its own real field names)
        own_field_cases = [
            (spec, "strategy_id"),
            (directive, "directive_id"),
            (node, "role"),
            (plan, "closure_plan_id"),
            (ref, "slice_id"),
            (result, "preview_id"),
        ]
        for obj, field_name in own_field_cases:
            assert dataclasses.is_dataclass(obj), f"{type(obj).__name__} must be a dataclass"
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(obj, field_name, "mutated")  # type: ignore[call-overload]

    def test_tuple_fields_normalized_to_tuples(self) -> None:
        """Verify that passing mutable lists to tuple fields normalizes them to tuples.

        After ``__post_init__`` normalization:
        - The field value is always a ``tuple`` (never a ``list``).
        - Mutating the original list does not affect the DTO.
        - Calling ``.append()`` on the field raises ``AttributeError``
          (tuples have no ``append``).
        - Normal ``obj.field = val`` assignment raises ``FrozenInstanceError``.
        """
        mutable_hints = ["hint_a", "hint_b"]
        directive = RepairDirective(
            directive_id="dir_1",
            source="user",
            target_construct_type="EXCEPTION_FLOW",
            target_slot_name="handler_action",
            selected_ref_hints=mutable_hints,  # passed as list
        )

        # Normalized to tuple
        assert isinstance(directive.selected_ref_hints, tuple)
        assert directive.selected_ref_hints == ("hint_a", "hint_b")

        # Mutating the original list does not affect the DTO
        mutable_hints.append("hint_c")
        assert directive.selected_ref_hints == ("hint_a", "hint_b"), (
            "Original list mutation must not affect the frozen DTO"
        )

        # .append() is blocked (tuples have no append)
        with pytest.raises(AttributeError):
            directive.selected_ref_hints.append("hack")  # type: ignore[attr-defined]

        # Normal Python assignment is blocked by FrozenInstanceError
        with pytest.raises(dataclasses.FrozenInstanceError):
            directive.selected_ref_hints = ("hacked",)  # type: ignore[misc]

        # RepairStrategySpec tuple fields also normalize correctly
        mutable_chain = ["s1", "s2"]
        spec = RepairStrategySpec(
            strategy_id="s",
            target_construct_type="EXCEPTION_FLOW",
            target_slot_name="handler_action",
            diagnostic_kind="missing_handler",
            missing_construct_closure=["BLOCK"],  # list input
            default_policy_id="dp",
            directive_policy_id="dirp",
            stage_slice_chain=mutable_chain,  # list input
        )
        assert isinstance(spec.stage_slice_chain, tuple)
        mutable_chain.append("s3")
        assert spec.stage_slice_chain == ("s1", "s2"), (
            "Original list mutation must not affect frozen RepairStrategySpec"
        )

        # ConstructClosurePlan tuple fields
        node = ConstructClosureNode(role="r", construct_type="C", action="ensure")
        plan = ConstructClosurePlan(
            closure_plan_id="p1",
            strategy_id="s1",
            materialization_plan_id="m1",
            target_construct_ref="t",
            closure_nodes=[node],  # list input
            stage_slice_chain=["sl1"],  # list input
            write_layers=["w1"],
            dependency_closure=[],
            default_or_directive_driven="default",
        )
        assert isinstance(plan.closure_nodes, tuple)
        assert isinstance(plan.stage_slice_chain, tuple)
        with pytest.raises(AttributeError):
            plan.closure_nodes.append(node)  # type: ignore[attr-defined]

    def test_constructor_empty_fields_validation(self) -> None:
        """Verify that empty or blank IDs/strings are rejected with ValueError."""
        # Empty strategy_id
        with pytest.raises(ValueError, match="cannot be empty or blank"):
            RepairStrategySpec(
                strategy_id=" ",
                target_construct_type="EXCEPTION_FLOW",
                target_slot_name="handler_action",
                diagnostic_kind="missing_handler",
                missing_construct_closure=(),
                default_policy_id="d1",
                directive_policy_id="d2",
                stage_slice_chain=(),
            )

        # Empty directive_id
        with pytest.raises(ValueError, match="cannot be empty or blank"):
            RepairDirective(
                directive_id="",
                source="user",
                target_construct_type="EXCEPTION_FLOW",
                target_slot_name="handler_action",
            )

    def test_construct_closure_node_action_validation(self) -> None:
        """Verify ConstructClosureNode.action only accepts ensure, bind_existing, or materialize."""
        # Legal values must succeed
        for action in ("ensure", "bind_existing", "materialize"):
            node = ConstructClosureNode(
                role="role",
                construct_type="BLOCK",
                action=action,  # type: ignore[arg-type]
            )
            assert node.action == action

        # Illegal values must fail with ValueError
        with pytest.raises(ValueError, match="Invalid ConstructClosureNode action"):
            ConstructClosureNode(
                role="role",
                construct_type="BLOCK",
                action="invalid_action",  # type: ignore[arg-type]
            )

    def test_repair_directive_source_validation(self) -> None:
        """Verify RepairDirective.source only accepts user or system_default."""
        # Illegal source value must fail
        with pytest.raises(ValueError, match="Invalid source"):
            RepairDirective(
                directive_id="dir_1",
                source="bad_source",  # type: ignore[arg-type]
                target_construct_type="EXCEPTION_FLOW",
                target_slot_name="handler_action",
            )

    def test_repair_directive_confidence_range_validation(self) -> None:
        """Verify RepairDirective.confidence is checked for range [0.0, 1.0]."""
        # Confidence too low
        with pytest.raises(ValueError, match="confidence must be in range"):
            RepairDirective(
                directive_id="dir_1",
                source="user",
                target_construct_type="EXCEPTION_FLOW",
                target_slot_name="handler_action",
                confidence=-0.1,
            )

        # Confidence too high
        with pytest.raises(ValueError, match="confidence must be in range"):
            RepairDirective(
                directive_id="dir_1",
                source="user",
                target_construct_type="EXCEPTION_FLOW",
                target_slot_name="handler_action",
                confidence=1.1,
            )

    def test_construct_closure_plan_mode_validation(self) -> None:
        """Verify ConstructClosurePlan.default_or_directive_driven only accepts default or directive_driven."""
        with pytest.raises(ValueError, match="Invalid default_or_directive_driven"):
            ConstructClosurePlan(
                closure_plan_id="plan_1",
                strategy_id="strat_1",
                materialization_plan_id="mat_1",
                target_construct_ref="target",
                closure_nodes=(),
                stage_slice_chain=(),
                write_layers=(),
                dependency_closure=(),
                default_or_directive_driven="invalid_mode",  # type: ignore[arg-type]
            )

    def test_repair_directive_forbidden_evidence_fields(self) -> None:
        """Verify that RepairDirective cannot carry any evidence authority fields."""
        # Check class level attributes do not declare evidence fields
        forbidden_attributes = {
            "evidence_packet_id",
            "evidence_status",
            "origin",
            "user_confirmed_repair",
            "materialization_authority",
        }
        for attr in forbidden_attributes:
            assert not hasattr(RepairDirective, attr)

        # Check constructor does not allow extra fields
        with pytest.raises(TypeError):
            RepairDirective(
                directive_id="dir_1",
                source="user",
                target_construct_type="EXCEPTION_FLOW",
                target_slot_name="handler_action",
                evidence_packet_id="ev_123",  # type: ignore[call-arg]
            )

    def test_selected_ref_hints_separation(self) -> None:
        """Verify that selected_ref_hints is just a passive field model and does not act as materialization authority."""
        directive = _make_directive(selected_ref_hints=("hint_var",))
        assert directive.selected_ref_hints == ("hint_var",)
        # Ensure there is no logic in DTOs translating this field to authorization packets
        assert not hasattr(directive, "to_evidence_packet")

    def test_preview_materialization_result_stale_fields(self) -> None:
        """Verify PreviewMaterializationResult has all required hashes for stale detection."""
        ref = StageSliceTypedPlanRef(slice_id="s1", typed_plan_hash="h1")
        result = PreviewMaterializationResult(
            preview_id="prev_1",
            base_snapshot_id="base_1",
            intent_hash="ih1",
            directive_hash="dh1",
            closure_plan_hash="cph1",
            selected_refset_id="refset_1",
            slice_typed_plan_hashes=(ref,),
            preview_construct_hashes=("pch1",),
            llm_generation_config_hash="gh1",
            rendered_preview="preview text",
        )
        assert result.preview_id == "prev_1"
        assert result.base_snapshot_id == "base_1"
        assert result.intent_hash == "ih1"
        assert result.directive_hash == "dh1"
        assert result.closure_plan_hash == "cph1"
        assert result.selected_refset_id == "refset_1"
        assert result.slice_typed_plan_hashes == (ref,)
        assert result.preview_construct_hashes == ("pch1",)
        assert result.llm_generation_config_hash == "gh1"
        assert result.rendered_preview == "preview text"


class TestR12_1HashHelpers:
    def test_intent_hash_stability_and_sensitivity(self) -> None:
        """Verify compute_intent_hash is stable for identical inputs and sensitive to changes."""
        intent_a = _make_intent(intent_id="int_1", selected_ref_ids=("ref_x",))
        intent_b = _make_intent(intent_id="int_1", selected_ref_ids=("ref_x",))
        intent_c = _make_intent(intent_id="int_2", selected_ref_ids=("ref_x",))
        intent_d = _make_intent(intent_id="int_1", selected_ref_ids=("ref_y",))

        hash_a = compute_intent_hash(intent_a)
        hash_b = compute_intent_hash(intent_b)
        hash_c = compute_intent_hash(intent_c)
        hash_d = compute_intent_hash(intent_d)

        # Stability
        assert hash_a == hash_b
        # Sensitivity
        assert hash_a != hash_c
        assert hash_a != hash_d

    def test_directive_hash_stability_and_sensitivity(self) -> None:
        """Verify compute_directive_hash is stable for identical inputs and sensitive to changes."""
        dir_a = _make_directive(directive_id="dir_1", selected_ref_hints=("ref_x",))
        dir_b = _make_directive(directive_id="dir_1", selected_ref_hints=("ref_x",))
        dir_c = _make_directive(directive_id="dir_2", selected_ref_hints=("ref_x",))
        dir_d = _make_directive(directive_id="dir_1", selected_ref_hints=("ref_y",))

        hash_a = compute_directive_hash(dir_a)
        hash_b = compute_directive_hash(dir_b)
        hash_c = compute_directive_hash(dir_c)
        hash_d = compute_directive_hash(dir_d)

        # Stability
        assert hash_a == hash_b
        # Sensitivity
        assert hash_a != hash_c
        assert hash_a != hash_d

    def test_closure_plan_hash_stability_and_sensitivity(self) -> None:
        """Verify compute_closure_plan_hash is stable for identical inputs and sensitive to changes."""
        plan_a = _make_closure_plan(strategy_id="s_1")
        plan_b = _make_closure_plan(strategy_id="s_1")
        plan_c = _make_closure_plan(strategy_id="s_2")

        hash_a = compute_closure_plan_hash(plan_a)
        hash_b = compute_closure_plan_hash(plan_b)
        hash_c = compute_closure_plan_hash(plan_c)

        # Stability
        assert hash_a == hash_b
        # Sensitivity
        assert hash_a != hash_c


class TestR12_1ImportIsolation:
    def test_no_forbidden_runtime_imports_in_models(self) -> None:
        """Verify strategy, closure, and preview model files do not import runtime handlers, appliers, or CLI."""
        forbidden_modules = {
            "nl2spl.compiler.spl_editing.patches",
            "nl2spl.compiler.spl_editing.handlers",
            "nl2spl.compiler.spl_editing.cli",
            "nl2spl.compiler.spl_editing.core.service",
        }
        # Verify strategy, closure, and preview are not loaded via those packages
        for mod in list(sys.modules.keys()):
            if mod.startswith("nl2spl.compiler.spl_editing.strategy") or \
               mod.startswith("nl2spl.compiler.spl_editing.closure") or \
               mod.startswith("nl2spl.compiler.spl_editing.preview"):
                # Inspect imports of the loaded modules to ensure no dependencies exist
                module_obj = sys.modules[mod]
                module_vars = vars(module_obj)
                for var_name, var_val in module_vars.items():
                    if hasattr(var_val, "__name__"):
                        mod_name = var_val.__name__
                        assert not any(mod_name.startswith(f) for f in forbidden_modules), (
                            f"Model module '{mod}' imports forbidden runtime entity '{mod_name}'"
                        )
