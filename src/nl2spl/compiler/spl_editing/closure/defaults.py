"""Default closure node templates for MVP strategies."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.closure.model import ConstructClosureNode


def get_default_nodes_for_strategy(strategy_id: str) -> tuple[ConstructClosureNode, ...]:
    """Get the default sequence of ConstructClosureNodes for a given strategy ID."""
    if strategy_id == "exception_flow.complete_handler_action.v1":
        return (
            ConstructClosureNode(
                role="handler_block",
                construct_type="BLOCK",
                action="ensure",
                required=True,
                stage_slice_id="stage5.exception_handler_block_repair.v1",
            ),
            ConstructClosureNode(
                role="handler_action",
                construct_type="COMMAND",
                action="materialize",
                required=True,
                stage_slice_id="stage7.exception_handler_command_repair.v1",
            ),
        )
    elif strategy_id == "required_output.materialize_producer.v1":
        return (
            ConstructClosureNode(
                role="placement_block",
                construct_type="BLOCK",
                action="ensure",
                required=False,
                stage_slice_id="stage7.required_output_producer_command_repair.v1",
            ),
            ConstructClosureNode(
                role="producer_command",
                construct_type="COMMAND",
                action="materialize",
                required=True,
                stage_slice_id="stage7.required_output_producer_command_repair.v1",
            ),
        )
    elif strategy_id == "worker_delegation.complete_closure.v1":
        return (
            ConstructClosureNode(
                role="worker_handoff",
                construct_type="WORKER_HANDOFF",
                action="materialize",
                required=True,
                stage_slice_id="stage3_5.worker_boundary",
            ),
            ConstructClosureNode(
                role="invoke_worker_command",
                construct_type="COMMAND",
                action="materialize",
                required=True,
                stage_slice_id="stage7.worker_step_plan",
            ),
            ConstructClosureNode(
                role="target_worker",
                construct_type="CHILD_WORKER",
                action="bind_existing",
                required=True,
                stage_slice_id="stage3_5.worker_boundary",
            ),
            ConstructClosureNode(
                role="placement_block",
                construct_type="BLOCK",
                action="ensure",
                required=False,
                stage_slice_id="stage7.worker_step_plan",
            ),
        )
    return ()
