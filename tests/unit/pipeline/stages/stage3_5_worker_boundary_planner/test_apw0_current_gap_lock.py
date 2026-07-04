"""APW target-behavior locks for Stage 3.5 API / worker promotion boundary.

These tests read real generated demo artifacts.  They started as APW0
characterization checks; after APW1+ landed, they now lock the corrected
behavior so the original API/worker ownership regression cannot return.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEMO_DIR = Path("examples/output/demo")


def _artifact(name: str) -> dict[str, Any]:
    return json.loads((DEMO_DIR / name).read_text(encoding="utf-8"))


def _result(name: str) -> dict[str, Any]:
    return _artifact(name)["result"]


def _diagnostics() -> list[dict[str, Any]]:
    snapshot = _artifact("spl_editing_snapshot.json")
    return snapshot["payload"]["diagnostics"]["compile_diagnostics"]


def _issue_explanations() -> dict[str, Any]:
    snapshot = _artifact("spl_editing_snapshot.json")
    return snapshot["presentation"]["issue_explanations"]["items"]


def test_apw0_s16_is_confirmed_api_invocation_in_real_demo_artifact() -> None:
    result = _result("external_capability_intent_resolver.json")

    s16_intents = [
        intent
        for intent in result["intents"]
        if "s16" in intent.get("source_span_ids", ())
    ]

    assert len(s16_intents) == 1
    intent = s16_intents[0]
    assert intent["boundary_status"] == "confirmed_external"
    assert intent["invocation_status"] == "executable"
    assert intent["capability_admission_status"] == "confirmed_capability"
    assert intent["invocation_admission_status"] == "confirmed_invocation"
    assert intent["operation_text"] == "retrieve them using approved source recipes"


def test_apw_target_stage3_5_records_api_exclusion_for_s16() -> None:
    result = _result("stage3_5a_candidate_task_units.json")

    view = result["worker_boundary_exclusion_view"]

    assert view["api_consumed_span_ids"] == ["s16"]
    assert view["api_call_demand_ids_by_span"]["s16"] == [
        "api_call_19e71fc8b204a57a"
    ]
    assert view["audit_payload"]["intents"][0]["consumed_by_api_authority"] is True


def test_apw_target_stage3_5_compiles_api_owned_candidate_as_call_api() -> None:
    result = _result("stage3_5b_worker_boundary_decisions.json")

    decision = next(
        d
        for d in result["decisions"]
        if d["candidate_id"] == "candidate_retrieve_sources"
    )

    assert decision["decision"] == "compile_as_call_api"
    assert decision["boundary_kind"] == "call_api"
    assert decision["rejection_reason"] == "single_api_call"


def test_apw_target_materializer_does_not_give_s16_to_child_worker() -> None:
    result = _result("stage3_5c_worker_plan_materializer.json")

    child_workers = [
        w
        for w in result["workers"]
        if w["kind"] == "child"
    ]

    assert child_workers
    assert all("s16" not in worker["owned_span_ids"] for worker in child_workers)
    assert all(
        worker["worker_name"] != "Worker_retrieve_approved_sources"
        for worker in child_workers
    )


def test_apw_target_worker_promotion_del_s31_uses_source_side_subject() -> None:
    diagnostics = _diagnostics()
    primary = next(
        d
        for d in diagnostics
        if d["target_ref"] == "worker_promotion:del_s31"
        and d["metadata"].get("issue_role") == "primary"
    )

    explanation = _issue_explanations()[primary["diagnostic_id"]]["explanation"]

    assert primary["metadata"]["irs_ref"]["construct_type"] == "WORKER_PROMOTION"
    assert primary["metadata"]["original_source_span_ids"] == ["s31"]
    assert explanation["headline"].startswith(
        "Potential child-worker responsibility is incomplete:"
    )
    assert "Worker_retrieve_approved_sources" not in explanation["headline"]


def test_apw_target_required_output_producer_drift_is_closed_for_source_evidence() -> None:
    diagnostics = _diagnostics()
    missing_outputs = [
        d
        for d in diagnostics
        if d["kind"] == "missing_output_producer"
        and d["target_ref"] == "worker:worker_main.output:source_evidence_set"
    ]
    result = _result("stage3_5c_worker_plan_materializer.json")

    api_decision = next(
        d
        for d in result["rejected_candidates"]
        if d["candidate_id"] == "candidate_retrieve_sources"
    )

    assert missing_outputs == []
    assert api_decision["decision"] == "compile_as_call_api"
    assert not any(
        h
        for h in result.get("handoffs", [])
        if h["handoff_id"] == "handoff_retrieve_approved_sources"
    )
