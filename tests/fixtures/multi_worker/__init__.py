"""Multi-worker regression fixtures."""

from tests.fixtures.multi_worker.scenarios import (
    MultiWorkerScenario,
    api_adapter_with_provenance,
    api_call_vs_api_adapter,
    duplicate_behavior_span_ownership,
    duplicate_handoff_id,
    explicit_subtask_without_io,
    flattenable_nested_control,
    internal_comms_source_gathering,
    loop_body_child_worker,
    revision_not_worker,
    same_child_multiple_handoffs,
    simple_single_worker,
    single_api_call_not_worker,
    unresolved_invoke_worker_error,
    unused_child_worker_error,
    worker_plan_validator_errors,
)

__all__ = [
    "MultiWorkerScenario",
    "api_adapter_with_provenance",
    "api_call_vs_api_adapter",
    "duplicate_behavior_span_ownership",
    "duplicate_handoff_id",
    "explicit_subtask_without_io",
    "flattenable_nested_control",
    "internal_comms_source_gathering",
    "loop_body_child_worker",
    "revision_not_worker",
    "same_child_multiple_handoffs",
    "simple_single_worker",
    "single_api_call_not_worker",
    "unused_child_worker_error",
    "unresolved_invoke_worker_error",
    "worker_plan_validator_errors",
]
