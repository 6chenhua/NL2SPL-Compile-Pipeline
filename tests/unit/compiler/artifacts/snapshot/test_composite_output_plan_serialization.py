"""Snapshot serialization tests for composite output plan related IR.

Covers:
- WorkerStepPlanIR roundtrip preserves composite_output_plans
- WorkerStepPlanIR roundtrip preserves step_variable_relation_plan
- schema_version == composite_output_plan.v1 is verified
- Unknown/missing schema_version fails closed
- ProducerIndex maintains relation_authority mode after snapshot restore
- ExecutableElementGate works after snapshot restore without structured_aggregation
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.artifacts.snapshot.serialization.registry import build_default_registry
from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.ir.composite_output_plan_ir import (
    CompositeFieldMapping,
    CompositeOutputPlan,
    DeclarationRewrite,
    OutputIntent,
)
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.step_variable_relation_ir import StepVariableRelation, StepVariableRelationPlan
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR


def _make_plan(
    step_id: str = "st1",
    composite_var: str = "result_structured",
    original_outputs: list[str] | None = None,
) -> CompositeOutputPlan:
    if original_outputs is None:
        original_outputs = ["field1", "field2"]
    intents = tuple(
        OutputIntent(variable_name=n, data_type="text", source_span_ids=("s1",))
        for n in original_outputs
    )
    return CompositeOutputPlan(
        plan_id=f"cop_{step_id}",
        worker_id="MainWorker",
        step_id=step_id,
        command_type="GENERAL_COMMAND",
        original_output_intents=intents,
        composite_variable_name=composite_var,
        composite_type_name=f"{composite_var}_type",
        field_mappings=tuple(
            CompositeFieldMapping(
                original_field_name=n,
                original_data_type="text",
                composite_field_name=n,
            )
            for n in original_outputs
        ),
        declaration_rewrites=tuple(
            DeclarationRewrite(remove_variable_name=n) for n in original_outputs
        ),
        reference_rewrites=(),
        worker_output_rewrite=None,
        projection_relations=(),
        naming_authority="CompositeNamePolicy",
        source_span_ids=("s1",),
    )


def _make_relation_plan() -> StepVariableRelationPlan:
    return StepVariableRelationPlan(
        relations=(
            StepVariableRelation(
                step_id="st1",
                variable_name="field1",
                relation="produces",
                source_span_ids=("s1",),
                evidence_kind="source_text",
            ),
            StepVariableRelation(
                step_id="st1",
                variable_name="field2",
                relation="produces",
                source_span_ids=("s1",),
                evidence_kind="source_text",
            ),
        )
    )


class TestWorkerStepPlanIRRoundtrip:
    def test_roundtrip_preserves_composite_output_plans(self) -> None:
        """WorkerStepPlanIR roundtrip must preserve composite_output_plans."""
        reg = build_default_registry()
        plan = _make_plan(step_id="st1", composite_var="result_structured")
        sp = WorkerStepPlanIR(
            main_worker_id="MainWorker",
            composite_output_plans=(plan,),
        )

        data = reg.serialize(sp)
        restored: WorkerStepPlanIR = reg.deserialize(data)

        assert len(restored.composite_output_plans) == 1
        restored_plan = restored.composite_output_plans[0]
        assert restored_plan.plan_id == plan.plan_id
        assert restored_plan.step_id == "st1"
        assert restored_plan.composite_variable_name == "result_structured"
        assert len(restored_plan.original_output_intents) == 2
        assert restored_plan.original_output_intents[0].variable_name == "field1"
        assert restored_plan.schema_version == "composite_output_plan.v1"

    def test_roundtrip_preserves_step_variable_relation_plan(self) -> None:
        """WorkerStepPlanIR roundtrip must preserve step_variable_relation_plan."""
        reg = build_default_registry()
        relation_plan = _make_relation_plan()
        sp = WorkerStepPlanIR(
            main_worker_id="MainWorker",
            step_variable_relation_plan=relation_plan,
        )

        data = reg.serialize(sp)
        restored: WorkerStepPlanIR = reg.deserialize(data)

        assert restored.step_variable_relation_plan is not None
        relations = restored.step_variable_relation_plan.relations
        assert len(relations) == 2
        producers = restored.step_variable_relation_plan.producing_relations()
        assert len(producers) == 2
        assert {r.variable_name for r in producers} == {"field1", "field2"}

    def test_roundtrip_both_fields(self) -> None:
        """WorkerStepPlanIR roundtrip preserves both plans simultaneously."""
        reg = build_default_registry()
        plan = _make_plan()
        relation_plan = _make_relation_plan()
        sp = WorkerStepPlanIR(
            main_worker_id="MainWorker",
            composite_output_plans=(plan,),
            step_variable_relation_plan=relation_plan,
        )

        data = reg.serialize(sp)
        restored: WorkerStepPlanIR = reg.deserialize(data)

        assert len(restored.composite_output_plans) == 1
        assert restored.step_variable_relation_plan is not None

    def test_roundtrip_empty_plans(self) -> None:
        """WorkerStepPlanIR with no plans roundtrips cleanly."""
        reg = build_default_registry()
        sp = WorkerStepPlanIR(main_worker_id="MainWorker")

        data = reg.serialize(sp)
        restored: WorkerStepPlanIR = reg.deserialize(data)

        assert restored.composite_output_plans == ()
        assert restored.step_variable_relation_plan is None


class TestCompositeOutputPlanSchemaVersion:
    def test_schema_version_is_correct(self) -> None:
        """CompositeOutputPlan schema_version must equal composite_output_plan.v1."""
        plan = _make_plan()
        assert plan.schema_version == "composite_output_plan.v1"

    def test_to_payload_includes_schema_version(self) -> None:
        """to_payload must include schema_version == composite_output_plan.v1."""
        plan = _make_plan()
        payload = plan.to_payload()
        assert payload["schema_version"] == "composite_output_plan.v1"

    def test_from_payload_with_correct_schema_version(self) -> None:
        """from_payload succeeds with schema_version == composite_output_plan.v1."""
        plan = _make_plan()
        payload = plan.to_payload()
        restored = CompositeOutputPlan.from_payload(payload)
        assert restored.composite_variable_name == plan.composite_variable_name

    def test_from_payload_rejects_unknown_schema_version(self) -> None:
        """from_payload must fail closed when schema_version is unknown."""
        plan = _make_plan()
        payload = plan.to_payload()
        payload["schema_version"] = "composite_output_plan.v999"
        with pytest.raises(ValueError, match="schema_version"):
            CompositeOutputPlan.from_payload(payload)

    def test_from_payload_rejects_missing_schema_version(self) -> None:
        """from_payload must fail closed when schema_version is absent."""
        plan = _make_plan()
        payload = plan.to_payload()
        del payload["schema_version"]
        with pytest.raises(ValueError, match="schema_version"):
            CompositeOutputPlan.from_payload(payload)


class TestRelationPlanProducerIndexMode:
    def test_producing_relations_after_roundtrip(self) -> None:
        """ProducerIndex must use restored relation plan as producer authority."""
        reg = build_default_registry()
        relation_plan = _make_relation_plan()
        sp = WorkerStepPlanIR(
            main_worker_id="MainWorker",
            step_variable_relation_plan=relation_plan,
        )

        data = reg.serialize(sp)
        restored: WorkerStepPlanIR = reg.deserialize(data)

        assert restored.step_variable_relation_plan is not None
        index = ProducerIndex(
            steps=[
                StepIR(
                    "st1",
                    "Do work",
                    ["s1"],
                    "GENERAL_COMMAND",
                    outputs=["result_structured"],
                )
            ],
            step_variable_relation_plan=restored.step_variable_relation_plan,
        )

        assert index.mode == "relation_authority"
        assert index.is_produced("field1")
        assert index.is_produced("field2")
        assert not index.is_produced("result_structured")


class TestGateAfterSnapshotRestore:
    def test_gate_validates_using_plans_after_snapshot_restore(self) -> None:
        """Gate must validate correctness using composite_output_plans after snapshot roundtrip."""
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.pipeline.executable_gate import ExecutableElementGate

        reg = build_default_registry()
        plan = _make_plan(
            step_id="st1", composite_var="result_structured", original_outputs=["out"]
        )
        sp = WorkerStepPlanIR(
            main_worker_id="MainWorker",
            composite_output_plans=(plan,),
        )

        data = reg.serialize(sp)
        restored: WorkerStepPlanIR = reg.deserialize(data)

        gate = ExecutableElementGate()
        gate.composite_output_plans = restored.composite_output_plans

        # Step with composite output matches expected handoff outputs via plan
        step = StepIR(
            "st1",
            "Do work",
            ["s1"],
            "GENERAL_COMMAND",
            outputs=["result_structured"],
            metadata={},  # No structured_aggregation or composite_output_debug
        )
        result = gate._handoff_outputs_match(step, expected_outputs=["out"])
        assert result is True

    def test_gate_fails_closed_without_plans_after_restore(self) -> None:
        """Gate must fail closed when composite_output_plans are absent after restore."""
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.pipeline.executable_gate import ExecutableElementGate

        reg = build_default_registry()
        sp = WorkerStepPlanIR(main_worker_id="MainWorker")  # No plans

        data = reg.serialize(sp)
        restored: WorkerStepPlanIR = reg.deserialize(data)

        gate = ExecutableElementGate()
        gate.composite_output_plans = restored.composite_output_plans  # Will be ()

        step = StepIR(
            "st1",
            "Do work",
            ["s1"],
            "GENERAL_COMMAND",
            outputs=["result_structured"],
            metadata={
                "composite_output_debug": {
                    "result_name": "result_structured",
                    "original_outputs": ["out"],
                    "type_name": "some_type",
                }
            },
        )
        # Even though composite_output_debug is present, gate must fail closed
        result = gate._handoff_outputs_match(step, expected_outputs=["out"])
        assert result is False
