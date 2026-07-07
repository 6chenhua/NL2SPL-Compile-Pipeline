from __future__ import annotations

from nl2spl.ir.action_placement_ir import (
    ExecutableActionCandidate,
    ExecutableActionPlacement,
    ExecutableActionPlacementPlan,
    MaterializationExclusion,
    WorkerExecutableActionSet,
)


def test_action_placement_plan_round_trips_worker_extraction_contract() -> None:
    plan = ExecutableActionPlacementPlan(
        candidates=(
            ExecutableActionCandidate(
                candidate_id="action_s18",
                source_span_ids=("s18",),
                action_text="retrieve them using approved source recipes",
                source="construct_plan_executable_demand",
                status="accepted",
                reason="api_call_demand",
                command_type_hint="CALL_API",
            ),
        ),
        placements=(
            ExecutableActionPlacement(
                candidate_id="action_s18",
                worker_id="worker_main",
                flow_ref=None,
                block_ref=None,
                status="placed",
            ),
        ),
        worker_actions=(
            WorkerExecutableActionSet(
                worker_id="worker_main",
                placement_span_ids=("s18",),
                generic_step_extraction_span_ids=(),
                materialization_exclusions=(
                    MaterializationExclusion(
                        span_id="s18",
                        excluded_from="general_command_extraction",
                        owning_authority="api_call",
                        authority_ref="api_call_approved_sources",
                        reason="api_call_materializer_owns_command_type",
                    ),
                ),
            ),
        ),
    )

    payload = plan.to_payload()
    assert ExecutableActionPlacementPlan.from_payload(payload).to_payload() == payload
    assert plan.accepted_span_ids() == {"s18"}
    assert plan.generic_step_extraction_span_ids("worker_main") == ()
