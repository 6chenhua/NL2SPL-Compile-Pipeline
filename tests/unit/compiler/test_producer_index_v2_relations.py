"""
Unit tests for ProducerIndex v2 / Gate A relations authority and legacy fallback.
"""

from __future__ import annotations

from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.step_variable_relation_ir import (
    StepVariableRelation,
    StepVariableRelationPlan,
)


def test_producer_index_relation_authority_mode() -> None:
    step = StepIR(
        step_id="st7",
        text="Record assumptions and status",
        command_type="GENERAL_COMMAND",
        source_span_ids=["s20"],
        outputs=["assumptions_log", "completion_status"],
    )

    relation_plan = StepVariableRelationPlan(
        relations=(
            StepVariableRelation(
                step_id="st7",
                variable_name="run_completion_record",
                relation="produces",
                source_span_ids=("s20",),
                evidence_kind="source_text",
            ),
        )
    )

    index = ProducerIndex(
        steps=[step],
        step_variable_relation_plan=relation_plan,
    )

    # 1. relation_authority mode is active
    assert index.mode == "relation_authority"
    assert len(index.compat_warnings) == 0

    # 2. Registers composite variable from relation plan
    assert index.is_produced("run_completion_record")

    # 3. Does not register original fields from StepIR.outputs
    assert not index.is_produced("assumptions_log")
    assert not index.is_produced("completion_status")


def test_producer_index_legacy_fallback_none_plan() -> None:
    step = StepIR(
        step_id="st7",
        text="Record assumptions and status",
        command_type="GENERAL_COMMAND",
        source_span_ids=["s20"],
        outputs=["assumptions_log", "completion_status"],
    )

    # relation plan is None
    index = ProducerIndex(
        steps=[step],
        step_variable_relation_plan=None,
    )

    # 1. legacy_fallback mode is active
    assert index.mode == "legacy_fallback"
    assert len(index.compat_warnings) > 0
    assert "no StepVariableRelationPlan supplied" in index.compat_warnings[0]

    # 2. Legacy fallback works using StepIR.outputs
    assert index.is_produced("assumptions_log")
    assert index.is_produced("completion_status")


def test_empty_relation_plan_disables_legacy_step_outputs() -> None:
    step = StepIR(
        step_id="st7",
        text="Record assumptions and status",
        command_type="GENERAL_COMMAND",
        source_span_ids=["s20"],
        outputs=["assumptions_log", "completion_status"],
    )

    # relation plan is empty
    index = ProducerIndex(
        steps=[step],
        step_variable_relation_plan=StepVariableRelationPlan(relations=()),
    )

    assert index.mode == "relation_authority"
    assert len(index.compat_warnings) == 0
    assert not index.is_produced("assumptions_log")
    assert not index.is_produced("completion_status")


def test_relation_plan_without_produces_disables_legacy_step_outputs() -> None:
    step = StepIR(
        step_id="st_1",
        text="Maintain provenance.",
        command_type="GENERAL_COMMAND",
        source_span_ids=["s1"],
        outputs=["source_evidence_set"],
    )
    relation_plan = StepVariableRelationPlan(
        relations=(
            StepVariableRelation(
                step_id="st_1",
                variable_name="source_evidence_set",
                relation="ambiguous",
                source_span_ids=("s1",),
                evidence_kind="stage7_provenance_maintenance_no_output",
            ),
        )
    )

    index = ProducerIndex(
        steps=[step],
        step_variable_relation_plan=relation_plan,
    )

    assert index.mode == "relation_authority"
    assert len(index.compat_warnings) == 0
    assert not index.is_produced("source_evidence_set")


def test_call_api_legacy_fallback_does_not_claim_outputs() -> None:
    step = StepIR(
        step_id="st_api",
        text="CALL SearchAPI",
        command_type="CALL_API",
        integration_ref="SearchAPI",
        source_span_ids=["s18"],
        outputs=["source_evidence_set"],
    )

    # No relation plan -> legacy fallback records API deferral metadata only.
    index = ProducerIndex(
        steps=[step],
        declared_apis={"SearchAPI"},
        step_variable_relation_plan=None,
    )

    assert index.mode == "legacy_fallback"
    assert not index.is_produced("source_evidence_set")
    assert any("CALL_API StepIR.outputs ignored" in w for w in index.compat_warnings)


def test_call_api_relation_authority() -> None:
    step = StepIR(
        step_id="st_api",
        text="CALL SearchAPI",
        command_type="CALL_API",
        integration_ref="SearchAPI",
        source_span_ids=["s18"],
        outputs=["source_evidence_set"],
    )

    relation_plan = StepVariableRelationPlan(
        relations=(
            StepVariableRelation(
                step_id="st_api",
                variable_name="custom_api_output",
                relation="produces",
                source_span_ids=("s18",),
                evidence_kind="api_contract",
            ),
        )
    )

    # Relation plan exists -> CALL_API output comes from relation plan, ignores StepIR.outputs
    index = ProducerIndex(
        steps=[step],
        declared_apis={"SearchAPI"},
        step_variable_relation_plan=relation_plan,
    )

    assert index.mode == "relation_authority"
    assert index.is_produced("custom_api_output")
    assert not index.is_produced("source_evidence_set")
