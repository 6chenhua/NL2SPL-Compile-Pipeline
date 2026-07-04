"""APW1 tests for WorkerBoundaryExclusionView."""

from __future__ import annotations

import json
from pathlib import Path

from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.api_exclusion import (
    WorkerBoundaryExclusionView,
    build_worker_boundary_exclusion_view,
)


def test_builds_view_from_demo_artifact_with_s16_consumed() -> None:
    artifact = json.loads(
        Path("examples/output/demo/external_capability_intent_resolver.json")
        .read_text(encoding="utf-8")
    )

    view = build_worker_boundary_exclusion_view(artifact)

    assert isinstance(view, WorkerBoundaryExclusionView)
    assert view.api_consumed_span_ids == frozenset({"s16"})
    assert view.api_call_demand_ids_by_span == {
        "s16": ("api_call_19e71fc8b204a57a",)
    }
    assert view.exclusion_authority == "external_capability_intent_plan"
    assert view.audit_payload["authority"] == "external_capability_intent_plan"


def test_only_confirmed_executable_admitted_invocation_is_consumed() -> None:
    view = build_worker_boundary_exclusion_view(
        {
            "plan_id": "plan_test",
            "intents": [
                {
                    "intent_id": "confirmed",
                    "source_span_ids": ["s1"],
                    "operation_text": "call service",
                    "capability_surface": "service",
                    "boundary_status": "confirmed_external",
                    "invocation_status": "executable",
                    "capability_admission_status": "confirmed_capability",
                    "invocation_admission_status": "confirmed_invocation",
                },
                {
                    "intent_id": "mention",
                    "source_span_ids": ["s2"],
                    "operation_text": "approved service policy",
                    "capability_surface": "service",
                    "boundary_status": "confirmed_external",
                    "invocation_status": "mention_only",
                    "capability_admission_status": "confirmed_capability",
                    "invocation_admission_status": "no_invocation",
                },
                {
                    "intent_id": "candidate",
                    "source_span_ids": ["s3"],
                    "operation_text": "maybe call service",
                    "capability_surface": "service",
                    "boundary_status": "candidate_external",
                    "invocation_status": "executable",
                    "capability_admission_status": "candidate_capability",
                    "invocation_admission_status": "candidate_invocation",
                },
            ],
        }
    )

    assert view.api_consumed_span_ids == frozenset({"s1"})
    assert view.api_residual_span_ids == frozenset({"s2"})
    assert "s2" not in view.api_call_demand_ids_by_span
    assert "s3" not in view.api_call_demand_ids_by_span


def test_view_payload_is_stable_and_auditable() -> None:
    view = build_worker_boundary_exclusion_view(
        {
            "intents": [
                {
                    "intent_id": "cap_intent_demo",
                    "source_span_ids": ["s10"],
                    "operation_text": "retrieve records",
                    "capability_surface": "records API",
                    "boundary_status": "confirmed_external",
                    "invocation_status": "executable",
                    "capability_admission_status": "confirmed_capability",
                    "invocation_admission_status": "confirmed_invocation",
                }
            ]
        }
    )

    payload = view.to_payload()

    assert payload["api_consumed_span_ids"] == ["s10"]
    assert payload["api_call_demand_ids_by_span"]["s10"] == [
        "api_call_9194f8a5492aab86"
    ]
    assert payload["audit_payload"]["intent_count"] == 1
    assert payload["audit_payload"]["intents"][0]["operation_text"] == (
        "retrieve records"
    )
    assert payload["audit_payload"]["intents"][0]["consumed_by_api_authority"] is True


def test_view_builder_handles_missing_plan_without_side_effects() -> None:
    view = build_worker_boundary_exclusion_view(None)

    assert view.api_consumed_span_ids == frozenset()
    assert view.api_residual_span_ids == frozenset()
    assert view.api_call_demand_ids_by_span == {}
    assert view.audit_payload["intent_count"] == 0


def test_api_exclusion_module_does_not_define_diagnostics_or_irs() -> None:
    source = Path(
        "src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/api_exclusion.py"
    ).read_text(encoding="utf-8")

    assert "CompileDiagnostic" not in source
    assert "ConstructIRS" not in source
    assert "diagnostic_id" not in source
    assert "missing_slot" not in source
