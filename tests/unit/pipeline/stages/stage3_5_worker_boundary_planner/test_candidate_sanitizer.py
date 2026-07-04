"""APW2 tests for API exclusion candidate sanitizer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import CandidateTaskUnitIR, ContractFieldIR
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner import (
    WorkerBoundaryPlanner,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.api_exclusion import (
    WorkerBoundaryExclusionView,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.candidate_sanitizer import (
    sanitize_candidates_for_api_exclusion,
)


def _field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(
        name=name,
        data_type="text",
        required=True,
        description=name,
        source=source,
    )


def _candidate(
    candidate_id: str,
    spans: list[str],
    *,
    kind: str = "integration_wrapper",
) -> CandidateTaskUnitIR:
    return CandidateTaskUnitIR(
        candidate_id=candidate_id,
        source_span_ids=spans,
        task_text="Retrieve approved sources and preserve provenance.",
        purpose="Retrieve approved sources.",
        candidate_kind=kind,
        possible_inputs=[_field("approved_source_recipes")],
        possible_outputs=[_field("sourced_facts_with_provenance", "output")],
        signals=["external_integration", "bounded_io"],
        risks=[],
    )


def _view(*consumed: str) -> WorkerBoundaryExclusionView:
    return WorkerBoundaryExclusionView(
        api_consumed_span_ids=frozenset(consumed),
        api_residual_span_ids=frozenset(),
        api_call_demand_ids_by_span={
            span_id: (f"api_call_for_{span_id}",)
            for span_id in consumed
        },
        audit_payload={"authority": "external_capability_intent_plan"},
    )


def test_api_only_candidate_auto_decides_compile_as_call_api() -> None:
    batch = sanitize_candidates_for_api_exclusion(
        [_candidate("candidate_api", ["s16"])],
        _view("s16"),
    )

    assert [c.candidate_id for c in batch.candidates] == ["candidate_api"]
    assert len(batch.auto_decisions) == 1
    assert batch.auto_decisions[0].decision == "compile_as_call_api"
    assert batch.auto_decisions[0].boundary_kind == "call_api"
    assert batch.results[0].result_kind == "api_only_auto_decision"
    assert batch.results[0].removed_api_span_ids == ("s16",)


def test_mixed_candidate_keeps_residual_and_auto_keeps_main() -> None:
    batch = sanitize_candidates_for_api_exclusion(
        [_candidate("candidate_retrieve_approved_sources", ["s16", "s23", "s30"])],
        _view("s16"),
    )

    assert batch.candidates[0].source_span_ids == ["s23", "s30"]
    assert batch.auto_decisions[0].decision == "keep_in_main_worker"
    assert batch.auto_decisions[0].rejection_reason == "insufficient_semantic_boundary"
    result = batch.results[0]
    assert result.result_kind == "mixed_residual_keep_in_main_worker"
    assert result.removed_api_span_ids == ("s16",)
    assert result.residual_source_span_ids == ("s23", "s30")
    assert result.requires_residual_re_evaluation is True
    assert result.residual_policy_reason == "residual_after_api_exclusion_insufficient"


def test_non_overlapping_candidate_is_unchanged() -> None:
    original = _candidate("candidate_main", ["s23"], kind="bounded_subtask")
    batch = sanitize_candidates_for_api_exclusion([original], _view("s16"))

    assert batch.candidates == (original,)
    assert batch.auto_decisions == ()
    assert batch.results[0].result_kind == "unchanged"
    assert batch.results[0].requires_residual_re_evaluation is False


def test_non_confirmed_api_residual_span_is_not_consumed() -> None:
    view = WorkerBoundaryExclusionView(
        api_consumed_span_ids=frozenset({"s16"}),
        api_residual_span_ids=frozenset({"s31"}),
        api_call_demand_ids_by_span={"s16": ("api_call_for_s16",)},
        audit_payload={"authority": "external_capability_intent_plan"},
    )

    batch = sanitize_candidates_for_api_exclusion(
        [_candidate("candidate_policy", ["s31"], kind="bounded_subtask")],
        view,
    )

    assert batch.candidates[0].source_span_ids == ["s31"]
    assert batch.auto_decisions == ()
    assert batch.results[0].result_kind == "unchanged"


def test_sanitized_result_payload_is_stable() -> None:
    batch = sanitize_candidates_for_api_exclusion(
        [_candidate("candidate_api", ["s16", "s23"])],
        _view("s16"),
    )

    payload = batch.results[0].to_payload()

    assert payload["original_candidate_id"] == "candidate_api"
    assert payload["result_kind"] == "mixed_residual_keep_in_main_worker"
    assert payload["removed_api_span_ids"] == ["s16"]
    assert payload["residual_source_span_ids"] == ["s23"]
    assert payload["auto_decision"]["decision"] == "keep_in_main_worker"
    assert payload["audit"]["api_call_demand_ids"] == {
        "s16": ["api_call_for_s16"]
    }


def test_executor_projects_sanitizer_result_into_stage3_5a_checkpoint(
    tmp_path: Path,
) -> None:
    config = PipelineConfig(
        llm=LLMConfig(api_key="test"),
        output_dir=tmp_path / "out",
        run_name="apw2",
        save_intermediate=True,
    )
    client = MagicMock()
    client.call_json.return_value = {
        "candidates": [
            {
                "candidate_id": "candidate_retrieve_approved_sources",
                "source_span_ids": ["s16", "s23", "s30"],
                "task_text": "Retrieve sources using approved recipes.",
                "purpose": "Retrieve approved sources.",
                "candidate_kind": "integration_wrapper",
                "possible_inputs": [
                    {
                        "name": "approved_source_recipes",
                        "data_type": "text",
                        "required": True,
                        "description": "Approved recipes.",
                        "source": "input",
                    }
                ],
                "possible_outputs": [
                    {
                        "name": "sourced_facts_with_provenance",
                        "data_type": "text",
                        "required": True,
                        "description": "Sourced facts.",
                        "source": "output",
                    }
                ],
                "signals": ["external_integration", "bounded_io"],
                "risks": [],
            }
        ]
    }
    planner = WorkerBoundaryPlanner(config, client)
    spans = [
        SpanIR("s16", "retrieve them using approved source recipes"),
        SpanIR("s23", "maintain provenance"),
        SpanIR("s30", "provenance failure"),
    ]
    external_plan = {
        "intents": [
            {
                "intent_id": "cap_intent_8326912547e62e9c",
                "source_span_ids": ["s16"],
                "operation_text": "retrieve them using approved source recipes",
                "capability_surface": "approved source recipes",
                "boundary_status": "confirmed_external",
                "invocation_status": "executable",
                "capability_admission_status": "confirmed_capability",
                "invocation_admission_status": "confirmed_invocation",
            }
        ]
    }

    plan = planner.execute(
        (
            spans,
            FieldRouteIR(behavior=["s16", "s23", "s30"]),
            None,
            None,
            external_plan,
        )
    )

    checkpoint = json.loads(
        (config.run_dir / "stage3_5a_candidate_task_units.json")
        .read_text(encoding="utf-8")
    )
    result = checkpoint["result"]["sanitization_results"][0]
    assert result["removed_api_span_ids"] == ["s16"]
    assert result["residual_source_span_ids"] == ["s23", "s30"]
    assert result["auto_decision"]["decision"] == "keep_in_main_worker"
    assert checkpoint["result"]["candidates"][0]["source_span_ids"] == ["s23", "s30"]
    assert len([w for w in plan.workers if w.kind == "child"]) == 0
    assert client.call_json.call_count == 1
