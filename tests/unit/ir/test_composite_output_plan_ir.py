"""
Unit tests for CompositeOutputPlan IR model.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from nl2spl.ir.composite_output_plan_ir import (
    CompositeFieldMapping,
    CompositeOutputPlan,
    DeclarationRewrite,
    FieldProjectionRelation,
    OutputIntent,
    ReferenceRewrite,
    WorkerOutputRewrite,
)


def test_composite_output_plan_construction_and_payload_roundtrip() -> None:
    intent = OutputIntent(
        variable_name="a",
        data_type="text",
        source_span_ids=("s1",),
    )
    field_mapping = CompositeFieldMapping(
        original_field_name="a",
        original_data_type="text",
        composite_field_name="a",
    )
    decl_rewrite = DeclarationRewrite(
        remove_variable_name="a",
    )
    ref_rewrite = ReferenceRewrite(
        original_ref="a",
        rewritten_ref="composite.a",
        top_name="composite",
        field_path=("a",),
    )
    worker_rewrite = WorkerOutputRewrite(
        remove_output_names=("a", "b"),
        add_output_name="composite",
        add_output_type="CompositeType",
        required=True,
    )

    plan = CompositeOutputPlan(
        plan_id="cop_worker_step",
        worker_id="worker",
        step_id="step",
        command_type="GENERAL_COMMAND",
        original_output_intents=(intent,),
        composite_variable_name="composite",
        composite_type_name="CompositeType",
        field_mappings=(field_mapping,),
        declaration_rewrites=(decl_rewrite,),
        reference_rewrites=(ref_rewrite,),
        worker_output_rewrite=worker_rewrite,
        projection_relations=(),
        naming_authority="CompositeNamePolicy",
        source_span_ids=("s1",),
    )

    # Verify frozen
    with pytest.raises(FrozenInstanceError):
        plan.composite_variable_name = "new_name"  # type: ignore

    # Verify schema version
    assert plan.schema_version == "composite_output_plan.v1"
    assert plan.projection_relations == ()

    # Roundtrip check
    payload = plan.to_payload()
    restored = CompositeOutputPlan.from_payload(payload)
    assert restored == plan


def test_composite_output_plan_validation_failures() -> None:
    # 1. Missing schema_version
    payload = {
        "plan_id": "cop_1",
        "worker_id": "w1",
        "step_id": "s1",
        "command_type": "GENERAL_COMMAND",
        "original_output_intents": [],
        "composite_variable_name": "composite",
        "composite_type_name": "CompositeType",
        "field_mappings": [],
        "declaration_rewrites": [],
        "reference_rewrites": [],
        "worker_output_rewrite": None,
        "projection_relations": [],
        "naming_authority": "CompositeNamePolicy",
        "source_span_ids": [],
    }
    with pytest.raises(ValueError, match="Missing schema_version"):
        CompositeOutputPlan.from_payload(payload)

    # 2. Invalid schema_version
    payload["schema_version"] = "composite_output.v1"
    with pytest.raises(ValueError, match="Invalid schema_version: composite_output.v1"):
        CompositeOutputPlan.from_payload(payload)

    # 3. Missing other required field
    payload["schema_version"] = "composite_output_plan.v1"
    del payload["plan_id"]
    with pytest.raises(ValueError, match="Missing field in CompositeOutputPlan: plan_id"):
        CompositeOutputPlan.from_payload(payload)


def test_composite_output_plan_field_projection_relation() -> None:
    # Projection relation can be constructed
    relation = FieldProjectionRelation(
        source_variable="composite",
        field_path=("a",),
        target_variable="a",
    )
    assert relation.source_variable == "composite"
    assert relation.field_path == ("a",)
    assert relation.target_variable == "a"

    payload = relation.to_payload()
    restored = FieldProjectionRelation.from_payload(payload)
    assert restored == relation
