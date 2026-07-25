from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "apps" / "spl-web-demo" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from spl_web_demo.app import create_app  # noqa: E402
from spl_web_demo.bootstrap import build_local_demo_api  # noqa: E402

API_PREFIX = "/api/demo/v1"
SNAPSHOT = "examples/output/demo/spl_editing_snapshot.json"
ISSUE_ID = "irs_b07e4440a217"
OPTION_ID = "keep_in_main_flow"
INVALID_REQUEST_BODY = {
    "error": {
        "code": "invalid_request",
        "message": "request validation failed",
        "details": {},
    }
}


def _client() -> TestClient:
    api = build_local_demo_api(repo_root=REPO_ROOT)
    return TestClient(create_app(api))


def _load_run(client: TestClient) -> tuple[str, str]:
    response = client.post(
        f"{API_PREFIX}/runs/from-snapshot",
        json={"snapshot_path": SNAPSHOT},
    )
    assert response.status_code == 200
    body = response.json()
    return body["run_id"], body["revision_token"]


def _interaction(client: TestClient, run_id: str, revision_token: str) -> dict[str, Any]:
    response = client.get(
        f"{API_PREFIX}/runs/{run_id}/issues/{ISSUE_ID}/repair-options/{OPTION_ID}/interaction",
        params={"revision_token": revision_token},
    )
    assert response.status_code == 200
    return response.json()


def _submit_directive(
    client: TestClient,
    run_id: str,
    interaction: dict[str, Any],
) -> str:
    response = client.post(
        f"{API_PREFIX}/runs/{run_id}/repair-directives",
        json={
            "issue_id": ISSUE_ID,
            "strategy_id": interaction["strategy_id"],
            "option_id": interaction["option_id"],
            "contract_id": interaction["contract_id"],
            "contract_version": interaction["contract_version"],
            "revision_token": interaction["revision_token"],
            "field_values": {"task_selection": "source gathering"},
            "selected_ref_ids": {},
            "new_fact_declarations": [],
            "additional_instruction": None,
        },
    )
    assert response.status_code == 200
    directive_id = response.json()["directive_id"]
    assert isinstance(directive_id, str) and directive_id
    return directive_id


def _preview(client: TestClient, run_id: str, directive_id: str) -> str:
    response = client.post(f"{API_PREFIX}/runs/{run_id}/repair-directives/{directive_id}/preview")
    assert response.status_code == 200
    preview_id = response.json()["preview"]["preview_id"]
    assert isinstance(preview_id, str) and preview_id
    return preview_id


def test_health_and_snapshot_read_routes() -> None:
    client = _client()

    health = client.get(f"{API_PREFIX}/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "service": "spl-web-demo",
        "editing_service": "ready",
    }

    run_id, revision_token = _load_run(client)

    run = client.get(f"{API_PREFIX}/runs/{run_id}")
    assert run.status_code == 200
    assert run.json()["revision_token"] == revision_token

    spl = client.get(f"{API_PREFIX}/runs/{run_id}/spl")
    assert spl.status_code == 200
    assert spl.json()["projection_status"] == "available"
    assert spl.json()["rendered_spl"].startswith("[DEFINE_AGENT:")
    assert spl.json()["spl_cards"]

    document = client.get(f"{API_PREFIX}/runs/{run_id}/spl-document")
    assert document.status_code == 200
    document_body = document.json()
    assert document_body["projection_status"] == "available"
    assert document_body["projection_fidelity"] == "render_aligned"
    assert document_body["nodes"]
    node_refs = [node["node_ref"] for node in document_body["nodes"]]
    assert len(node_refs) == len(set(node_refs))
    assert any(node["node_type"] == "PERSONA" for node in document_body["nodes"])
    assert all(isinstance(node["title"], str) for node in document_body["nodes"])
    assert all(
        node["summary"] is None or isinstance(node["summary"], str)
        for node in document_body["nodes"]
    )
    assert all(
        node["construct_ref"] is None
        for node in document_body["nodes"]
        if node["node_kind"] == "section"
    )

    constructs = client.get(f"{API_PREFIX}/runs/{run_id}/constructs")
    assert constructs.status_code == 200
    assert constructs.json()["projection_status"] == "available"
    assert constructs.json()["constructs"] == spl.json()["spl_cards"]

    source_provenance = None
    for card in constructs.json()["constructs"]:
        response = client.get(
            f"{API_PREFIX}/runs/{run_id}/constructs/{card['construct_ref']}/provenance"
        )
        assert response.status_code == 200
        if response.json()["provenance"]["spans"]:
            source_provenance = response.json()["provenance"]
            break

    assert source_provenance is not None
    span_summary = source_provenance["spans"][0]
    span = client.get(f"{API_PREFIX}/runs/{run_id}/spans/{span_summary['span_id']}")
    assert span.status_code == 200
    assert span.json()["span"] == span_summary
    assert span.json()["span"]["text"]

    issues = client.get(f"{API_PREFIX}/runs/{run_id}/issues")
    assert issues.status_code == 200
    assert any(
        item["issue_id"] == ISSUE_ID
        for section in issues.json()["sections"]
        for item in section["items"]
    )

    issue = client.get(f"{API_PREFIX}/runs/{run_id}/issues/{ISSUE_ID}")
    assert issue.status_code == 200
    assert issue.json()["issue"]["issue_id"] == ISSUE_ID
    assert issue.json()["explanation"]["status"] == "ready"

    explanation = client.post(f"{API_PREFIX}/runs/{run_id}/issues/{ISSUE_ID}/explanation")
    assert explanation.status_code == 200
    assert explanation.json()["explanation"]["status"] == "ready"
    assert explanation.json()["scheduling"] == {
        "requested": False,
        "accepted": False,
    }


def test_http_repair_preview_apply_flow() -> None:
    client = _client()
    run_id, revision_token = _load_run(client)
    initial_constructs = client.get(f"{API_PREFIX}/runs/{run_id}/constructs")
    assert initial_constructs.status_code == 200
    construct_ref = initial_constructs.json()["constructs"][0]["construct_ref"]
    interaction = _interaction(client, run_id, revision_token)
    directive_id = _submit_directive(client, run_id, interaction)
    preview_id = _preview(client, run_id, directive_id)

    applied = client.post(
        f"{API_PREFIX}/runs/{run_id}/repair-directives/{directive_id}/previews/{preview_id}/apply",
        json={"user_confirmation": True},
    )

    assert applied.status_code == 200
    body = applied.json()
    assert body["status"] == "applied"
    assert body["overlay_version"] == 1
    assert body["verification"]["accepted"] is True
    assert body["verification"]["lane"] == "B"
    assert body["projection_status"] == "projection_unavailable"
    assert body["spl"]["rendered_spl"] is None

    refreshed_run = client.get(f"{API_PREFIX}/runs/{run_id}")
    assert refreshed_run.status_code == 200
    assert refreshed_run.json()["overlay_version"] == 1
    assert refreshed_run.json()["revision_token"].endswith(":1")

    refreshed_spl = client.get(f"{API_PREFIX}/runs/{run_id}/spl")
    assert refreshed_spl.status_code == 200
    assert refreshed_spl.json()["projection_status"] == "projection_unavailable"
    assert refreshed_spl.json()["rendered_spl"] is None
    assert refreshed_spl.json()["spl_cards"] == []

    refreshed_constructs = client.get(f"{API_PREFIX}/runs/{run_id}/constructs")
    assert refreshed_constructs.status_code == 200
    assert refreshed_constructs.json()["projection_status"] == "projection_unavailable"
    assert refreshed_constructs.json()["constructs"] == []

    refreshed_document = client.get(f"{API_PREFIX}/runs/{run_id}/spl-document")
    assert refreshed_document.status_code == 200
    assert refreshed_document.json() == {
        "run_id": run_id,
        "snapshot_id": body["snapshot_id"],
        "overlay_version": 1,
        "revision_token": body["revision_token"],
        "projection_status": "projection_unavailable",
        "projection_fidelity": "partial",
        "nodes": [],
    }

    refreshed_provenance = client.get(
        f"{API_PREFIX}/runs/{run_id}/constructs/{construct_ref}/provenance"
    )
    assert refreshed_provenance.status_code == 200
    assert refreshed_provenance.json()["projection_status"] == "projection_unavailable"
    assert refreshed_provenance.json()["provenance"] is None


def test_http_routes_preserve_handler_error_statuses() -> None:
    client = _client()
    run_id, revision_token = _load_run(client)

    missing_run = client.get(f"{API_PREFIX}/runs/does-not-exist")
    assert missing_run.status_code == 404
    assert missing_run.json()["error"]["code"] == "run_not_found"

    missing_constructs = client.get(f"{API_PREFIX}/runs/does-not-exist/constructs")
    assert missing_constructs.status_code == 404
    assert missing_constructs.json()["error"]["code"] == "run_not_found"

    missing_explanation = client.post(
        f"{API_PREFIX}/runs/{run_id}/issues/issue-does-not-exist/explanation"
    )
    assert missing_explanation.status_code == 404
    assert missing_explanation.json()["error"]["code"] == "issue_not_found"

    missing_construct = client.get(
        f"{API_PREFIX}/runs/{run_id}/constructs/construct-does-not-exist/provenance"
    )
    assert missing_construct.status_code == 404
    assert missing_construct.json()["error"]["code"] == "construct_not_found"

    missing_span = client.get(f"{API_PREFIX}/runs/{run_id}/spans/s-does-not-exist")
    assert missing_span.status_code == 404
    assert missing_span.json()["error"]["code"] == "span_not_found"

    missing_revision = client.get(
        f"{API_PREFIX}/runs/{run_id}/issues/{ISSUE_ID}/repair-options/{OPTION_ID}/interaction"
    )
    assert missing_revision.status_code == 400
    assert missing_revision.json() == INVALID_REQUEST_BODY

    stale = client.get(
        f"{API_PREFIX}/runs/{run_id}/issues/{ISSUE_ID}/repair-options/{OPTION_ID}/interaction",
        params={"revision_token": f"{revision_token}:stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_revision"

    interaction = _interaction(client, run_id, revision_token)
    malformed = client.post(
        f"{API_PREFIX}/runs/{run_id}/repair-directives",
        json={
            "issue_id": ISSUE_ID,
            "strategy_id": interaction["strategy_id"],
            "option_id": interaction["option_id"],
            "contract_id": interaction["contract_id"],
            "contract_version": interaction["contract_version"],
            "revision_token": interaction["revision_token"],
            "field_values": "bad",
        },
    )
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "invalid_request"

    directive_id = _submit_directive(client, run_id, interaction)
    preview_id = _preview(client, run_id, directive_id)
    not_confirmed = client.post(
        f"{API_PREFIX}/runs/{run_id}/repair-directives/{directive_id}/previews/{preview_id}/apply",
        json={"user_confirmation": False},
    )
    assert not_confirmed.status_code == 422
    assert not_confirmed.json()["error"]["code"] == "input_required"


def test_non_object_json_bodies_return_uniform_invalid_request() -> None:
    client = _client()
    endpoints = (
        f"{API_PREFIX}/runs/from-snapshot",
        f"{API_PREFIX}/runs/demo/repair-directives",
        f"{API_PREFIX}/runs/demo/repair-directives/directive-x/previews/preview-x/apply",
    )

    for endpoint in endpoints:
        for body in ([], "not-an-object", None):
            response = client.post(endpoint, json=body)

            assert response.status_code == 400
            assert response.json() == INVALID_REQUEST_BODY
