"""APW target-behavior locks for Stage 3.5 API / worker promotion boundary.

These tests read real generated demo artifacts. They lock the corrected behavior
without assuming stable Stage 1 span ids.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEMO_DIR = Path("examples/output/demo")
API_OPERATION = "retrieve them using approved source recipes"


def _artifact(name: str) -> dict[str, Any]:
    return json.loads((DEMO_DIR / name).read_text(encoding="utf-8"))


def _result(name: str) -> dict[str, Any]:
    return _artifact(name)["result"]


def _diagnostics() -> list[dict[str, Any]]:
    snapshot = _artifact("spl_editing_snapshot.json")
    return snapshot["payload"]["diagnostics"]["compile_diagnostics"]


def _api_intent() -> dict[str, Any]:
    result = _result("external_capability_intent_resolver.json")
    intents = [
        intent
        for intent in result["intents"]
        if intent["operation_text"].startswith("retrieve")
        and _normalize_text(intent.get("capability_surface"))
        == "approved source recipes"
    ]
    assert len(intents) == 1
    return intents[0]


def _api_span_id() -> str:
    source_span_ids = _api_intent()["source_span_ids"]
    assert len(source_span_ids) == 1
    return source_span_ids[0]


def test_apw0_retrieve_sources_span_is_confirmed_api_invocation() -> None:
    intent = _api_intent()

    assert intent["boundary_status"] == "confirmed_external"
    assert intent["invocation_status"] == "executable"
    assert intent["capability_admission_status"] == "confirmed_capability"
    assert intent["invocation_admission_status"] == "confirmed_invocation"
    assert intent["operation_text"].startswith("retrieve")
    assert _normalize_text(intent["capability_surface"]) == "approved source recipes"


def test_apw_target_stage3_5_records_api_exclusion_for_api_span() -> None:
    result = _result("stage3_5a_candidate_task_units.json")
    view = result["worker_boundary_exclusion_view"]
    api_span_id = _api_span_id()
    api_call_demand_id = view["api_call_demand_ids_by_span"][api_span_id][0]

    assert view["api_consumed_span_ids"] == [api_span_id]
    assert view["api_call_demand_ids_by_span"][api_span_id] == [api_call_demand_id]
    consumed_intents = [
        intent
        for intent in view["audit_payload"]["intents"]
        if intent["consumed_by_api_authority"] is True
    ]
    assert len(consumed_intents) == 1
    assert consumed_intents[0]["source_span_ids"] == [api_span_id]
    assert consumed_intents[0]["api_call_demand_id"] == api_call_demand_id


def test_apw_target_stage3_5_compiles_api_owned_candidate_as_call_api() -> None:
    """The API-owned retrieve span is stripped from worker candidates."""
    result = _result("stage3_5a_candidate_task_units.json")
    api_span_id = _api_span_id()

    sanitization_results = result["sanitization_results"]
    api_removed = [
        item
        for item in sanitization_results
        if api_span_id in item["removed_api_span_ids"]
    ]

    assert len(api_removed) == 1, (
        f"Expected exactly 1 candidate to have {api_span_id} removed; got {api_removed}"
    )
    removed = api_removed[0]
    assert removed["auto_decision"]["decision"] == "keep_in_main_worker"
    assert api_span_id not in removed["residual_source_span_ids"]


def test_apw_target_materializer_does_not_give_api_span_to_child_worker() -> None:
    """No materialized worker should own the API-owned retrieve span."""
    result = _result("stage3_5c_worker_plan_materializer.json")
    api_span_id = _api_span_id()

    all_workers = result["workers"]
    assert all(
        api_span_id not in worker["owned_span_ids"] for worker in all_workers
    ), f"{api_span_id} must not be owned by any worker in the materialized plan"


def test_apw_target_worker_promotion_uses_source_side_subject() -> None:
    from nl2spl.compiler.spl_editing.demo import _build_default_service
    from nl2spl.compiler.spl_editing.presentation.service import (
        SPLEditingPresentationService,
    )

    diagnostics = _diagnostics()
    primary = next(
        d
        for d in diagnostics
        if d["metadata"].get("issue_role") == "primary"
        and d["metadata"].get("irs_ref", {}).get("construct_type")
        == "WORKER_PROMOTION"
    )

    assert primary["metadata"]["irs_ref"]["construct_type"] == "WORKER_PROMOTION"
    assert primary["metadata"]["original_source_span_ids"]

    service = _build_default_service(suggestion_llm=object())
    run_id = service.register_snapshot_file(DEMO_DIR / "spl_editing_snapshot.json")
    presentation = SPLEditingPresentationService(service)
    issue_list = presentation.list_issue_presentations(run_id)
    card = next(
        item
        for section in issue_list.sections
        for item in section.items
        if item.issue_id == primary["diagnostic_id"]
    )
    assert card.title.startswith(
        "Potential child-worker responsibility is incomplete:"
    )
    assert "Worker_retrieve_approved_sources" not in card.title


def test_apw_target_required_output_producer_stays_deferred_for_source_evidence() -> None:
    """The API call must not fabricate source_evidence_set as an API response."""
    fulfillment = _result("required_output_fulfillment.json")
    state = next(
        item
        for item in fulfillment["states"]
        if item["output_name"] == "source_evidence_set"
    )
    assert state["status"] == "deferred"
    assert state["reason"] == "api_return_contract_unknown"
    assert state["deferred_refs"]

    result = _result("stage3_5c_worker_plan_materializer.json")
    assert not any(
        handoff
        for handoff in result.get("handoffs", [])
        if handoff["handoff_id"] == "handoff_retrieve_approved_sources"
    )


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").split())
