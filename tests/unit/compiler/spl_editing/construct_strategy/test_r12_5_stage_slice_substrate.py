"""Unit tests for Phase R12.5 repair-mode stage-slice substrate."""

from __future__ import annotations

import ast
import pathlib

import pytest

from nl2spl.compiler.spl_editing.stage_slices import (
    BlockShapePlan,
    CommandIntentPlan,
    DuplicateStageSliceError,
    RepairModeStageSlice,
    StageAuthorityMismatchError,
    StageSliceRegistry,
    StageSliceResult,
    StageSliceValidationError,
    TypedPlanGenerator,
    TypedPlanValidator,
)


class _DummySlice:
    @property
    def slice_id(self) -> str:
        return "stageX.fixture_slice.v1"

    @property
    def stage_authority(self) -> str:
        return "stageX.fixture"

    @property
    def policy_id(self) -> str:
        return "fixture.policy.v1"

    @property
    def output_artifacts(self) -> tuple[str, ...]:
        return ("FixtureArtifact",)

    @property
    def write_layers(self) -> tuple[str, ...]:
        return ("worker_step_plan_pre_normalize",)

    def execute(self, input_data) -> StageSliceResult:
        return StageSliceResult(
            slice_id=self.slice_id,
            stage_authority=self.stage_authority,
            policy_id=self.policy_id,
            changed_artifact_refs=("FixtureArtifact",),
            generated_construct_refs=("construct_1",),
            consumed_selected_ref_ids=("ref_1",),
            consumed_directive_id="dir_1",
            allocated_ids=("alloc_1",),
            trace={"typed_plan_hash": "h1"},
        )


class _GeneratorFixture:
    @property
    def generator_id(self) -> str:
        return "fixture.constrained_generator"

    @property
    def generation_config_hash(self) -> str:
        return "config_hash"

    def generate_typed_plan(self, plan_kind: str, input_payload: dict):
        assert plan_kind == "CommandIntentPlan"
        return CommandIntentPlan(
            command_family="GENERAL_COMMAND",
            user_facing_text=input_payload["text"],
            selected_ref_ids=("ref_1",),
        )


def test_stage_slice_registry_rejects_duplicate_slice_id() -> None:
    registry = StageSliceRegistry()
    stage_slice = _DummySlice()

    registry.register(stage_slice)

    with pytest.raises(DuplicateStageSliceError):
        registry.register(stage_slice)


def test_stage_slice_registry_rejects_authority_mismatch() -> None:
    registry = StageSliceRegistry()

    with pytest.raises(StageAuthorityMismatchError):
        registry.register(_DummySlice(), expected_stage_authority="stage7.worker_step_plan")


def test_stage_slice_result_contains_required_audit_fields() -> None:
    result = _DummySlice().execute(None)

    assert result.generated_construct_refs == ("construct_1",)
    assert result.consumed_directive_id == "dir_1"
    assert result.consumed_selected_ref_ids == ("ref_1",)
    assert result.allocated_ids == ("alloc_1",)


def test_stage_slice_result_rejects_accepted_overlay_authority() -> None:
    with pytest.raises(StageSliceValidationError, match="accepted overlay"):
        StageSliceResult(
            slice_id="slice_1",
            stage_authority="stage7.worker_step_plan",
            policy_id="policy_1",
            changed_artifact_refs=("WorkerStepPlanIR",),
            generated_construct_refs=("step_1",),
            consumed_selected_ref_ids=(),
            consumed_directive_id="dir_1",
            trace={"overlay_event": "ov_1"},
        )


@pytest.mark.parametrize(
    "bad_plan",
    [
        {"StepIR": {"id": "st_1"}},
        {"step_id": "st_1", "command_family": "GENERAL_COMMAND"},
        {"nested": {"worker_handoff_ir": {"id": "handoff_1"}}},
    ],
)
def test_typed_plan_validator_rejects_raw_ir_shaped_payloads(bad_plan) -> None:
    with pytest.raises(StageSliceValidationError):
        TypedPlanValidator().validate(bad_plan)


def test_typed_plan_hash_is_stable_for_fixture() -> None:
    validator = TypedPlanValidator()
    plan_a = BlockShapePlan(
        block_type="SEQUENTIAL",
        rationale="default block",
        child_action_slots=("handler_action",),
    )
    plan_b = BlockShapePlan(
        block_type="SEQUENTIAL",
        rationale="default block",
        child_action_slots=["handler_action"],
    )

    assert validator.stable_hash(plan_a) == validator.stable_hash(plan_b)


def test_llm_boundary_is_constrained_to_typed_plan_generator_protocol() -> None:
    generator: TypedPlanGenerator = _GeneratorFixture()

    plan = generator.generate_typed_plan("CommandIntentPlan", {"text": "Handle issue"})

    assert isinstance(plan, CommandIntentPlan)
    assert plan.command_family == "GENERAL_COMMAND"
    assert plan.selected_ref_ids == ("ref_1",)


def test_stage_slice_substrate_does_not_import_handlers_cli_or_llm_clients() -> None:
    root = pathlib.Path("src/nl2spl/compiler/spl_editing/stage_slices")
    forbidden_parts = {"handlers", "cli", "llm_context"}
    for py_file in root.glob("**/*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = set(node.module.split("."))
                assert not (parts & forbidden_parts), (
                    f"stage_slices substrate imports forbidden module {node.module}"
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    parts = set(alias.name.split("."))
                    assert not (parts & forbidden_parts), (
                        f"stage_slices substrate imports forbidden module {alias.name}"
                    )


def test_repair_mode_stage_slice_protocol_accepts_fixture_slice() -> None:
    stage_slice: RepairModeStageSlice = _DummySlice()

    assert stage_slice.slice_id == "stageX.fixture_slice.v1"
    assert stage_slice.output_artifacts == ("FixtureArtifact",)
