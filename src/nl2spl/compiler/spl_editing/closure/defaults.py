"""Default closure node templates for MVP strategies."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.closure.model import ConstructClosureNode


def get_default_nodes_for_strategy(
    strategy_id: str,
    option_id: str | None = None,
) -> tuple[ConstructClosureNode, ...]:
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
    elif strategy_id == "worker_delegation.complete_closure.v2":
        if option_id == "keep_in_main_flow":
            return (
                ConstructClosureNode(
                    role="main_flow_placement",
                    construct_type="BLOCK",
                    action="ensure",
                    required=False,
                    stage_slice_id="stage5.parent_invocation_placement.v1",
                ),
                ConstructClosureNode(
                    role="main_flow_command",
                    construct_type="COMMAND",
                    action="materialize",
                    stage_slice_id="stage7.worker_delegation_resolution_command_repair.v1",
                ),
            )
        return (
            ConstructClosureNode(
                "child_worker",
                "CHILD_WORKER",
                "ensure",
                True,
                "stage3_5.define_child_worker.v1",
            ),
            ConstructClosureNode(
                "child_flow",
                "FLOW",
                "ensure",
                True,
                "stage4.child_worker_flow.v1",
            ),
            ConstructClosureNode(
                "child_block",
                "BLOCK",
                "ensure",
                True,
                "stage5.child_worker_block.v1",
            ),
            ConstructClosureNode(
                "child_command",
                "COMMAND",
                "materialize",
                True,
                "stage7.child_worker_command.v1",
            ),
            ConstructClosureNode(
                "worker_handoff",
                "WORKER_HANDOFF",
                "materialize",
                True,
                "stage3_5.worker_handoff_contract.v2",
            ),
            ConstructClosureNode(
                "parent_placement",
                "BLOCK",
                "ensure",
                False,
                "stage5.parent_invocation_placement.v1",
            ),
            ConstructClosureNode(
                "parent_invoke",
                "INVOKE_WORKER",
                "materialize",
                True,
                "stage7.worker_invoke.v2",
            ),
        )
    return ()
