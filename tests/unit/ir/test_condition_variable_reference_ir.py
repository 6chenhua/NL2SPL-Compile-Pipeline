from __future__ import annotations

import dataclasses

import pytest

from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    get_default_registry,
)
from nl2spl.ir.condition_variable_reference_ir import (
    ConditionTextRewrite,
    ConditionVariableReferenceIR,
    ConditionVariableReferencePlan,
    build_condition_reference_id,
)
from nl2spl.ir.diagnostics import CompileDiagnostic


def _reference() -> ConditionVariableReferenceIR:
    return ConditionVariableReferenceIR(
        reference_id=build_condition_reference_id("condition:block:worker:main:b1", 0),
        owner_kind="block_condition",
        owner_ref="condition:block:worker:main:b1",
        condition_text="When <REF>a</REF> is ready",
        ref_text="<REF>a</REF>",
        canonical_ref="a",
        top_level_name="a",
        qualified_path=("a",),
        status="resolved",
        source_span_ids=("s1",),
        worker_id="worker",
        flow_ref="main",
        block_ref="b1",
    )


def test_condition_reference_id_is_stable() -> None:
    assert build_condition_reference_id("owner", 0) == build_condition_reference_id(
        "owner",
        0,
    )
    assert build_condition_reference_id("owner", 0, "llm").startswith("cond_ref_")
    assert "_llm_" in build_condition_reference_id("owner", 0, "llm")


def test_condition_reference_is_frozen_and_supports_llm_evidence() -> None:
    reference = _reference()

    with pytest.raises(dataclasses.FrozenInstanceError):
        reference.status = "unresolved"  # type: ignore[misc]

    semantic = ConditionVariableReferenceIR(
        reference_id=build_condition_reference_id("condition:block:worker:main:b1", 0, "llm"),
        owner_kind="block_condition",
        owner_ref="condition:block:worker:main:b1",
        condition_text="when enough evidence has been collected",
        ref_text=None,
        canonical_ref="evidence",
        top_level_name="evidence",
        qualified_path=("evidence",),
        status="resolved",
        source_span_ids=("s1",),
        worker_id="worker",
        flow_ref="main",
        block_ref="b1",
        evidence_kind="llm_condition_semantic_match",
        evidence_text="enough evidence has been collected",
        selected_symbol="evidence",
        confidence="medium",
    )
    assert semantic.evidence_kind == "llm_condition_semantic_match"
    assert semantic.ref_text is None


def test_condition_plan_payload_and_registry_round_trip() -> None:
    reference = _reference()
    plan = ConditionVariableReferencePlan(
        references=(reference,),
        text_rewrites=(
            ConditionTextRewrite(
                owner_ref=reference.owner_ref,
                original_condition_text=reference.condition_text,
                rewritten_condition_text="When <REF>a_b.a</REF> is ready",
                rewrite_reason="composite_output_rewrite",
                source_reference_ids=(reference.reference_id,),
            ),
        ),
        diagnostics=(
            CompileDiagnostic(
                diagnostic_id="diag1",
                kind="condition_variable_ref_unresolved",
                severity="warning",
                message="Condition ref unresolved.",
                target_ref=reference.owner_ref,
                source_span_ids=["s1"],
            ),
        ),
    )

    restored = ConditionVariableReferencePlan.from_payload(plan.to_payload())
    assert restored == plan

    registry = get_default_registry()
    canonical = registry.serialize(plan)
    assert registry.deserialize(canonical) == plan
    assert restored.final_condition_text(
        reference.owner_ref,
        reference.condition_text,
    ) == "When <REF>a_b.a</REF> is ready"
