"""Orchestrator-level multi-worker feature flag regressions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


RAW_TEXT = """
Task family: Evidence-backed answers.
Inputs for each run: request.
Required outputs: evidence.
Reusable process: Prepare the request context. If sources are needed, invoke source gathering.
Delegation policy: Gather approved source evidence in a child worker.
"""


def pipeline_config(tmp_path: Path, enable_worker_boundary_planner: bool) -> PipelineConfig:
    return PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=tmp_path / "output",
        run_name="orchestrator-rollout",
        save_intermediate=False,
        enable_worker_boundary_planner=enable_worker_boundary_planner,
    )


def worker_plan_response() -> dict[str, object]:
    field_request = {
        "name": "request",
        "data_type": "text",
        "required": True,
        "description": "request field",
        "source": "input",
    }
    field_evidence = {
        "name": "evidence",
        "data_type": "text",
        "required": True,
        "description": "evidence field",
        "source": "output",
    }
    return {
        "main_worker_id": "worker_main",
        "workers": [
            {
                "worker_id": "worker_main",
                "worker_name": "MainWorker",
                "kind": "main",
                "purpose": "Coordinate request.",
                "owned_span_ids": ["s1", "s2"],
                "input_contract": [field_request],
                "output_contract": [field_evidence],
                "depends_on": [],
                "constraints": [],
                "boundary_kind": "main_worker",
                "decision_evidence": [],
                "reason": "Main worker.",
            },
            {
                "worker_id": "worker_source",
                "worker_name": "SourceWorker",
                "kind": "child",
                "purpose": "Gather approved source evidence.",
                "owned_span_ids": ["s3"],
                "input_contract": [field_request],
                "output_contract": [field_evidence],
                "depends_on": [],
                "constraints": [],
                "boundary_kind": "bounded_subtask",
                "decision_evidence": ["explicit_delegation", "bounded_io"],
                "reason": "Accepted source worker.",
            },
        ],
        "handoffs": [
            {
                "handoff_id": "handoff_source",
                "from_worker": "worker_main",
                "to_worker": "worker_source",
                "api_ref": None,
                "mode": "invoke",
                "condition_text": "sources are needed",
                "ordering": "conditional",
                "input_bindings": [
                    {
                        "parent_variable": "request",
                        "child_input": "request",
                        "required": True,
                    }
                ],
                "output_bindings": [
                    {
                        "child_output": "evidence",
                        "parent_variable": "evidence",
                        "required": True,
                        "merge_strategy": "set",
                    }
                ],
                "invoke_location_hint": {
                    "flow_kind": "main",
                    "flow_id": None,
                    "after_span_id": "s2",
                    "before_span_id": None,
                    "block_hint": "if",
                },
                "failure_policy": {
                    "policy_kind": "block_finalization",
                    "description": "Block finalization if source gathering fails.",
                    "source_span_ids": ["s3"],
                },
            }
        ],
        "candidates": [
            {
                "candidate_id": "candidate_source",
                "source_span_ids": ["s3"],
                "task_text": "Gather approved source evidence.",
                "purpose": "Gather approved source evidence.",
                "candidate_kind": "bounded_subtask",
                "possible_inputs": [field_request],
                "possible_outputs": [field_evidence],
                "signals": ["explicit_delegation", "bounded_io"],
                "risks": [],
            }
        ],
        "decisions": [
            {
                "candidate_id": "candidate_source",
                "decision": "extract_child_worker",
                "boundary_strength": "strong",
                "boundary_kind": "bounded_subtask",
                "rejection_reason": None,
                "reason": "Clear child worker handoff.",
                "evidence": ["explicit_delegation", "bounded_io"],
            }
        ],
        "rejected_candidates": [],
        "control_complexity_regions": [],
        "unassigned_span_ids": [],
        "warnings": [],
    }


def stage_response(stage_name: str, user_prompt: str) -> dict[str, object]:
    if stage_name == "stage1_span_slicer":
        return {
            "spans": [
                {"span_id": "s1", "text": "Prepare the request context."},
                {"span_id": "s2", "text": "If sources are needed, invoke source gathering."},
                {"span_id": "s3", "text": "Gather approved source evidence."},
            ]
        }
    if stage_name == "stage2_field_router":
        return {
            "routes": {
                "identity": [],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": ["s1", "s2", "s3"],
            },
            "ambiguity_updates": [],
        }
    if stage_name == "stage3_ambiguity_resolver":
        return {
            "resolved_spans": [],
            "resolved_routes": {
                "identity": [],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": ["s1", "s2", "s3"],
            },
        }
    if stage_name == "stage3_5_worker_boundary_planner":
        return worker_plan_response()
    if stage_name == "stage4_flow_assembler":
        if '"worker_id": "worker_source"' in user_prompt:
            return {
                "main_flow_spans": ["s3"],
                "alternative_flows": [],
                "exception_flows": [],
            }
        if "WorkerPlanIR context" in user_prompt:
            return {
                "main_flow_spans": ["s1", "s2"],
                "alternative_flows": [],
                "exception_flows": [],
            }
        return {
            "main_flow_spans": ["s1", "s2", "s3"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
    if stage_name == "stage5_block_assembler":
        if '"span_id": "s3"' in user_prompt and '"span_id": "s1"' not in user_prompt:
            return {
                "main_flow_blocks": [
                    {"block_id": "b_child", "block_type": "SEQUENTIAL", "spans": ["s3"]}
                ],
                "alternative_flow_blocks": {},
                "exception_flow_blocks": {},
            }
        if "s1" in user_prompt and "s3" not in user_prompt:
            return {
                "main_flow_blocks": [
                    {"block_id": "b1", "block_type": "SEQUENTIAL", "spans": ["s1"]},
                    {
                        "block_id": "b2",
                        "block_type": "IF",
                        "condition_text": "sources are needed",
                        "spans": ["s2"],
                    },
                ],
                "alternative_flow_blocks": {},
                "exception_flow_blocks": {},
            }
        return {
            "main_flow_blocks": [
                {"block_id": "b1", "block_type": "SEQUENTIAL", "spans": ["s1", "s2", "s3"]}
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }
    if stage_name == "stage6_resource_extractor":
        return {
            "variables": [
                {
                    "name": "request",
                    "data_type": "text",
                    "source": "input",
                    "required": True,
                    "description": "Request.",
                },
                {
                    "name": "evidence",
                    "data_type": "text",
                    "source": "output",
                    "required": True,
                    "description": "Evidence.",
                },
            ],
            "files": [],
            "apis": [],
            "types": [],
        }
    if stage_name == "stage7_step_extractor":
        if "Gather approved source evidence." in user_prompt:
            return {
                "steps": [
                    {
                        "step_id": "st1",
                        "text": "Produce evidence directly",
                        "source_span_ids": ["s3"],
                        "command_type": "GENERAL_COMMAND",
                        "inputs": ["request"],
                        "outputs": ["evidence"],
                        "flow_ref": "main",
                        "block_ref": "b1",
                    }
                ],
                "new_variables": [],
            }
        return {
            "steps": [
                {
                    "step_id": "st1",
                    "text": "Prepare request context",
                    "source_span_ids": ["s1"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": ["request"],
                    "outputs": [],
                    "flow_ref": "main",
                    "block_ref": "b1",
                }
            ],
            "new_variables": [],
        }
    if stage_name == "stage8_profile_extractor":
        return {
            "persona": {"role": "Evidence assistant", "aspects": []},
            "audience": {"aspects": []},
            "concepts": [],
        }
    if stage_name == "stage9_constraint_extractor":
        return {"constraints": []}
    raise AssertionError(f"Unexpected stage call: {stage_name}")


def run_with_mocked_llm(tmp_path: Path, enable_worker_boundary_planner: bool):
    captured_calls: list[tuple[str, str]] = []
    client = MagicMock()

    def call_json(stage_name: str, system_prompt: str, user_prompt: str):
        captured_calls.append((stage_name, user_prompt))
        return stage_response(stage_name, user_prompt)

    client.call_json.side_effect = call_json
    with patch("nl2spl.pipeline.orchestrator.LLMClient", return_value=client):
        orchestrator = PipelineOrchestrator(
            pipeline_config(tmp_path, enable_worker_boundary_planner)
        )
        result = orchestrator.run(RAW_TEXT)

    return result, captured_calls


def behavior_prompt_section(stage7_prompt: str) -> str:
    marker = "behavior spans"
    start = stage7_prompt.index(marker)
    end = stage7_prompt.index("Flow", start)
    return stage7_prompt[start:end]


def test_orchestrator_feature_flag_off_uses_legacy_path(tmp_path: Path) -> None:
    result, calls = run_with_mocked_llm(tmp_path, enable_worker_boundary_planner=False)

    assert "stage3_5_worker_plan" not in result.intermediate_results
    assert "stage4_worker_flows" not in result.intermediate_results
    assert "stage5_worker_blocks" not in result.intermediate_results
    assert "[DEFINE_WORKER:" in result.spl_text
    assert result.spl_text.count("[DEFINE_WORKER:") == 1
    assert "[INVOKE" not in result.spl_text
    assert not any(stage_name == "stage3_5_worker_boundary_planner" for stage_name, _ in calls)


def test_orchestrator_feature_flag_on_runs_worker_aware_path(tmp_path: Path) -> None:
    result, calls = run_with_mocked_llm(tmp_path, enable_worker_boundary_planner=True)

    assert "stage3_5_worker_plan" in result.intermediate_results
    assert "stage4_worker_flows" in result.intermediate_results
    assert "stage5_worker_blocks" in result.intermediate_results
    assert "stage4_legacy_flow_adapter" in result.intermediate_results
    assert "stage5_legacy_block_adapter" in result.intermediate_results
    # Stage 6 worker-scoped resources verification
    assert "stage6_worker_scoped_resources" in result.intermediate_results
    worker_scoped_resources = result.intermediate_results["stage6_worker_scoped_resources"]
    assert hasattr(worker_scoped_resources, "global_resources")
    assert hasattr(worker_scoped_resources, "worker_resources")
    assert "worker_source" in worker_scoped_resources.worker_resources
    assert "handoff_source" in worker_scoped_resources.handoff_contracts
    assert result.spl_text.count("[DEFINE_WORKER:") == 2
    assert "[DEFINE_WORKER: \"Gather approved source evidence.\" SourceWorker]" in result.spl_text
    assert "[INVOKE SourceWorker" in result.spl_text

    # Verify Stage 6 child worker prompt includes worker context and scoped spans
    stage6_calls = [
        (name, prompt) for name, prompt in calls if name == "stage6_resource_extractor"
    ]
    # Child worker prompt: has "SourceWorker" in worker context and only s3 in behavior
    child_prompts = [
        p for _, p in stage6_calls
        if "SourceWorker" in p and '"span_id": "s3"' in p
        and '"span_id": "s1"' not in p
    ]
    assert len(child_prompts) == 1, f"Expected one child stage6 prompt, got {len(child_prompts)}"
    child_prompt = child_prompts[0]
    assert "worker context" in child_prompt
    assert "known variables" in child_prompt

    stage7_prompt = next(
        user_prompt for stage_name, user_prompt in calls if stage_name == "stage7_step_extractor"
    )
    behavior_section = behavior_prompt_section(stage7_prompt)
    assert "Prepare the request context." in behavior_section
    assert "If sources are needed, invoke source gathering." in behavior_section
    assert "Gather approved source evidence." not in behavior_section
