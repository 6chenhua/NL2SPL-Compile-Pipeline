from __future__ import annotations

from nl2spl.ir.control_region_ir import ControlRegion, ControlRegionPlan


def test_control_region_plan_round_trips_relation_and_classification_fields() -> None:
    plan = ControlRegionPlan(
        regions=(
            ControlRegion(
                region_id="cr_s17",
                region_kind="local_if",
                condition_text="required information is missing",
                action_span_ids=("s17",),
                condition_source_span_ids=("s16", "s17"),
                worker_id="worker_main",
                source="route_derived",
                relation="derived",
                classification_source="route_derived",
                confidence="medium",
                notes=("derived_from_adjacent_source_packet",),
            ),
        ),
        diagnostics=("control_region_unresolved:bad",),
    )

    payload = plan.to_payload()
    assert ControlRegionPlan.from_payload(payload).to_payload() == payload
    assert plan.regions_for_worker("worker_main")[0].relation == "derived"
