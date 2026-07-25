from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    get_default_registry,
)
from nl2spl.ir.condition_variable_reference_ir import (
    ConditionVariableReferenceIR,
    ConditionVariableReferencePlan,
)


def test_condition_variable_reference_plan_serializer_round_trips() -> None:
    plan = ConditionVariableReferencePlan(
        references=(
            ConditionVariableReferenceIR(
                reference_id="cond_ref_owner_0",
                owner_kind="alternative_flow_condition",
                owner_ref="condition:flow:worker_main:alternative:alt_1",
                condition_text="<REF>x</REF> is missing",
                ref_text="<REF>x</REF>",
                canonical_ref="x",
                top_level_name="x",
                qualified_path=("x",),
                status="resolved",
                source_span_ids=("s1",),
                worker_id="worker_main",
                flow_ref="alt_1",
                block_ref=None,
            ),
        ),
    )

    registry = get_default_registry()
    serialized = registry.serialize(plan)

    assert serialized["$type"] == "ConditionVariableReferencePlan"
    assert registry.deserialize(serialized) == plan
