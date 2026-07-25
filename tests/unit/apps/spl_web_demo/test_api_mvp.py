from __future__ import annotations

import shutil
import sys
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "apps" / "spl-web-demo" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from spl_web_demo.bootstrap import build_local_demo_api  # noqa: E402
from spl_web_demo.card_api import SplWebDemoCardApi  # noqa: E402

from nl2spl.compiler.spl_editing.presentation import explanation_cache  # noqa: E402

SNAPSHOT = "examples/output/demo/spl_editing_snapshot.json"
ISSUE_ID = "irs_b07e4440a217"


class FakeExplanationScheduler:
    def __init__(self, issue_id: str) -> None:
        self.issue_id = issue_id
        self.calls: list[Path] = []

    def schedule(
        self,
        snapshot_path: Path,
    ) -> Future[explanation_cache.ExplanationPrecomputeResult]:
        path = Path(snapshot_path)
        self.calls.append(path)
        explanation_cache._write_cache(
            path,
            {
                "schema_version": "issue_explanation_cache.v1",
                "status": "pending",
                "language": "zh-CN",
                "started_at": "2026-07-10T00:00:00+00:00",
                "completed_at": None,
                "items": {self.issue_id: {"status": "pending", "explanation": None}},
            },
        )
        return Future()

    def complete(self, snapshot_path: Path, *, status: str) -> None:
        explanation = {"schema_version": "issue_explanation.v1", "issue_id": self.issue_id}
        explanation_cache._write_cache(
            snapshot_path,
            {
                "schema_version": "issue_explanation_cache.v1",
                "status": status,
                "language": "zh-CN",
                "started_at": "2026-07-10T00:00:00+00:00",
                "completed_at": "2026-07-10T00:00:01+00:00",
                "items": {
                    self.issue_id: (
                        {"status": "ready", "explanation": explanation}
                        if status == "ready"
                        else {"status": "error", "explanation": None, "error": "failed"}
                    )
                },
            },
        )


class FailingExplanationScheduler(FakeExplanationScheduler):
    def schedule(
        self,
        snapshot_path: Path,
    ) -> Future[explanation_cache.ExplanationPrecomputeResult]:
        self.calls.append(Path(snapshot_path))
        raise RuntimeError("scheduler startup failed")


def _api() -> SplWebDemoCardApi:
    return build_local_demo_api(repo_root=REPO_ROOT)


def _loaded_api() -> tuple[SplWebDemoCardApi, str, str]:
    api = _api()
    status, body = api.from_snapshot({"snapshot_path": SNAPSHOT})
    assert status == 200
    return api, body["run_id"], body["revision_token"]


def _loaded_api_with_missing_explanation(
    tmp_path: Path,
    scheduler: FakeExplanationScheduler | None,
) -> tuple[SplWebDemoCardApi, str, Path]:
    snapshot_path = tmp_path / "spl_editing_snapshot.json"
    shutil.copyfile(REPO_ROOT / SNAPSHOT, snapshot_path)
    explanation_cache._write_cache(
        snapshot_path,
        {
            "schema_version": "issue_explanation_cache.v1",
            "status": "missing",
            "language": "zh-CN",
            "started_at": None,
            "completed_at": None,
            "items": {},
        },
    )
    api = build_local_demo_api(
        repo_root=REPO_ROOT,
        explanation_scheduler=scheduler,
    )
    status, body = api.from_snapshot({"snapshot_path": str(snapshot_path)})
    assert status == 200
    return api, body["run_id"], snapshot_path


def _repair_interaction(
    api: SplWebDemoCardApi,
    run_id: str,
    revision: str,
) -> dict[str, object]:
    status, interaction = api.get_repair_interaction(
        run_id,
        "irs_b07e4440a217",
        "keep_in_main_flow",
        revision,
    )
    assert status == 200
    return interaction


def _submit_directive(
    api: SplWebDemoCardApi,
    run_id: str,
    interaction: dict[str, object],
    *,
    additional_instruction: str | None = None,
) -> str:
    status, directive = api.submit_repair_directive(
        run_id,
        {
            "issue_id": "irs_b07e4440a217",
            "strategy_id": interaction["strategy_id"],
            "option_id": interaction["option_id"],
            "contract_id": interaction["contract_id"],
            "contract_version": interaction["contract_version"],
            "revision_token": interaction["revision_token"],
            "field_values": {"task_selection": "source gathering"},
            "selected_ref_ids": {},
            "new_fact_declarations": [],
            "additional_instruction": additional_instruction,
        },
    )
    assert status == 200
    assert directive["input_readiness"] == "input_complete"
    directive_id = directive["directive_id"]
    assert isinstance(directive_id, str) and directive_id
    return directive_id


def _preview_directive(api: SplWebDemoCardApi, run_id: str, directive_id: str) -> str:
    status, preview = api.preview_repair_directive(run_id, directive_id)
    assert status == 200
    preview_id = preview["preview"]["preview_id"]
    assert isinstance(preview_id, str) and preview_id
    return preview_id


def test_from_snapshot_registers_existing_snapshot() -> None:
    api, run_id, revision = _loaded_api()

    status, body = api.get_run(run_id)

    assert status == 200
    assert body["run_id"] == "demo"
    assert body["editing_run_id"] == "demo"
    assert body["snapshot_id"] == "snap_b61a1efdd39c"
    assert body["overlay_version"] == 0
    assert revision == "demo:snap_b61a1efdd39c:0"


def test_editing_available_reflects_snapshot_registration_not_fixable_issues(
    monkeypatch,
) -> None:
    api = _api()
    original_get_run = api.presentation.get_run_presentation

    def get_run_without_fixable_issues(*args, **kwargs):
        return replace(original_get_run(*args, **kwargs), editable=False)

    monkeypatch.setattr(
        api.presentation,
        "get_run_presentation",
        get_run_without_fixable_issues,
    )

    status, created = api.from_snapshot({"snapshot_path": SNAPSHOT})
    assert status == 200
    assert created["editing_available"] is True

    status, refreshed = api.get_run(created["run_id"])
    assert status == 200
    assert refreshed["editing_available"] is True


def test_get_spl_initial_returns_snapshot_final_spl() -> None:
    api, run_id, _revision = _loaded_api()

    status, body = api.get_spl(run_id)

    assert status == 200
    assert body["projection_status"] == "available"
    assert body["overlay_version"] == 0
    assert body["rendered_spl"]
    assert body["rendered_spl"].startswith("[DEFINE_AGENT:")
    assert body["spl_cards"]
    assert {card["construct_type"] for card in body["spl_cards"]} >= {
        "WORKER",
        "FLOW",
        "BLOCK",
        "COMMAND",
    }
    assert all(card["construct_path"] for card in body["spl_cards"])
    assert len({card["construct_ref"] for card in body["spl_cards"]}) == len(body["spl_cards"])
    assert all("trace_target_refs" not in card for card in body["spl_cards"])

    status, constructs = api.list_constructs(run_id)
    assert status == 200
    assert constructs["projection_status"] == "available"
    assert constructs["constructs"] == body["spl_cards"]


def test_construct_provenance_and_span_handlers_use_structured_read_model() -> None:
    api, run_id, _revision = _loaded_api()
    status, constructs = api.list_constructs(run_id)
    assert status == 200

    source_backed = None
    for card in constructs["constructs"]:
        status, body = api.get_construct_provenance(run_id, card["construct_ref"])
        assert status == 200
        if body["provenance"]["spans"]:
            source_backed = body["provenance"]
            break

    assert source_backed is not None
    assert source_backed["trace_status"] == "available"
    assert source_backed["source_span_ids"]
    span_summary = source_backed["spans"][0]

    status, span = api.get_span(run_id, span_summary["span_id"])

    assert status == 200
    assert span["source_status"] == "available"
    assert span["span"] == span_summary
    assert span["span"]["text"]


def test_construct_and_span_not_found_errors_are_stable() -> None:
    api, run_id, _revision = _loaded_api()

    status, construct = api.get_construct_provenance(run_id, "construct-does-not-exist")
    assert status == 404
    assert construct["error"]["code"] == "construct_not_found"

    status, span = api.get_span(run_id, "s-does-not-exist")
    assert status == 404
    assert span["error"]["code"] == "span_not_found"


def test_issue_list_and_detail_use_presentation_dtos() -> None:
    api, run_id, _revision = _loaded_api()

    status, issue_list = api.list_issues(run_id)
    assert status == 200
    worker_issue = next(
        item
        for section in issue_list["sections"]
        for item in section["items"]
        if item["category"] == "worker_delegation"
    )

    status, detail = api.get_issue(run_id, worker_issue["issue_id"])

    assert status == 200
    assert detail["issue"]["issue_id"] == "irs_b07e4440a217"
    assert detail["explanation"]["status"] == "ready"
    assert any(
        option["option_id"] == "keep_in_main_flow"
        for option in detail["issue"]["available_repairs"]
    )


def test_ready_explanation_trigger_is_idempotent_without_scheduler() -> None:
    api, run_id, _revision = _loaded_api()

    status, body = api.trigger_issue_explanation(run_id, ISSUE_ID)

    assert status == 200
    assert body["explanation"]["status"] == "ready"
    assert body["scheduling"] == {"requested": False, "accepted": False}


def test_missing_explanation_transitions_pending_then_ready(tmp_path: Path) -> None:
    scheduler = FakeExplanationScheduler(ISSUE_ID)
    api, run_id, snapshot_path = _loaded_api_with_missing_explanation(tmp_path, scheduler)

    status, pending = api.trigger_issue_explanation(run_id, ISSUE_ID)

    assert status == 202
    assert pending["explanation"]["status"] == "pending"
    assert pending["scheduling"] == {"requested": True, "accepted": True}
    assert scheduler.calls == [snapshot_path]

    status, duplicate = api.trigger_issue_explanation(run_id, ISSUE_ID)
    assert status == 202
    assert duplicate["scheduling"] == {"requested": True, "accepted": False}
    assert scheduler.calls == [snapshot_path]

    scheduler.complete(snapshot_path, status="ready")
    status, ready = api.trigger_issue_explanation(run_id, ISSUE_ID)
    assert status == 200
    assert ready["explanation"]["status"] == "ready"
    assert ready["scheduling"] == {"requested": False, "accepted": False}


def test_missing_explanation_can_transition_to_error(tmp_path: Path) -> None:
    scheduler = FakeExplanationScheduler(ISSUE_ID)
    api, run_id, snapshot_path = _loaded_api_with_missing_explanation(tmp_path, scheduler)

    status, _pending = api.trigger_issue_explanation(run_id, ISSUE_ID)
    assert status == 202
    scheduler.complete(snapshot_path, status="error")

    status, error = api.get_issue(run_id, ISSUE_ID)

    assert status == 200
    assert error["explanation"] == {
        "status": "error",
        "value": None,
        "error": "failed",
    }


def test_missing_explanation_without_scheduler_fails_explicitly(tmp_path: Path) -> None:
    api, run_id, _snapshot_path = _loaded_api_with_missing_explanation(tmp_path, None)

    status, body = api.trigger_issue_explanation(run_id, ISSUE_ID)

    assert status == 503
    assert body["error"]["code"] == "explanation_scheduler_unavailable"


def test_explanation_scheduler_start_failure_returns_503(tmp_path: Path) -> None:
    scheduler = FailingExplanationScheduler(ISSUE_ID)
    api, run_id, snapshot_path = _loaded_api_with_missing_explanation(
        tmp_path,
        scheduler,
    )

    status, body = api.trigger_issue_explanation(run_id, ISSUE_ID)

    assert status == 503
    assert body["error"]["code"] == "explanation_schedule_failed"
    assert scheduler.calls == [snapshot_path]


def test_repair_interaction_matches_probe_contract() -> None:
    api, run_id, revision = _loaded_api()

    status, body = api.get_repair_interaction(
        run_id,
        "irs_b07e4440a217",
        "keep_in_main_flow",
        revision,
    )

    assert status == 200
    assert body["contract_id"] == "worker_delegation.keep_in_main_flow.v1"
    assert body["availability"] == "available"
    fields = {field["field_id"]: field for field in body["fields"]}
    assert fields["task_selection"]["input_type"] == "single_choice"
    assert fields["task_selection"]["required"] is True
    assert fields["additional_instruction"]["input_type"] == "long_text"
    assert fields["additional_instruction"]["required"] is False
    assert "demo_availability" not in body


def test_preview_cancel_is_client_discard_without_state_change() -> None:
    api, run_id, revision = _loaded_api()
    status, issues_before = api.list_issues(run_id)
    assert status == 200
    interaction = _repair_interaction(api, run_id, revision)
    directive_id = _submit_directive(api, run_id, interaction)
    _preview_id = _preview_directive(api, run_id, directive_id)

    status, run_after = api.get_run(run_id)
    assert status == 200
    assert run_after["overlay_version"] == 0
    assert run_after["revision_token"] == revision

    status, issues_after = api.list_issues(run_id)
    assert status == 200
    assert issues_after == issues_before
    assert api.store.require(run_id).last_verification is None


def test_directive_preview_apply_then_spl_projection_unavailable() -> None:
    api, run_id, revision = _loaded_api()
    status, initial_constructs = api.list_constructs(run_id)
    assert status == 200
    construct_ref = initial_constructs["constructs"][0]["construct_ref"]
    interaction = _repair_interaction(api, run_id, revision)
    directive_id = _submit_directive(api, run_id, interaction)
    preview_id = _preview_directive(api, run_id, directive_id)

    status, applied = api.apply_repair_preview(
        run_id,
        directive_id,
        preview_id,
        {"user_confirmation": True},
    )
    assert status == 200
    assert applied["status"] == "applied"
    assert applied["overlay_version"] == 1
    assert applied["verification"]["accepted"] is True
    assert applied["verification"]["lane"] == "B"
    assert applied["projection_status"] == "projection_unavailable"

    status, spl = api.get_spl(run_id)
    assert status == 200
    assert spl["overlay_version"] == 1
    assert spl["projection_status"] == "projection_unavailable"
    assert spl["rendered_spl"] is None
    assert spl["spl_cards"] == []
    assert "unavailable" in spl["message"]

    status, constructs = api.list_constructs(run_id)
    assert status == 200
    assert constructs["projection_status"] == "projection_unavailable"
    assert constructs["constructs"] == []

    status, provenance = api.get_construct_provenance(run_id, construct_ref)
    assert status == 200
    assert provenance["projection_status"] == "projection_unavailable"
    assert provenance["provenance"] is None


def test_get_run_after_apply_reflects_overlay_and_projection_status() -> None:
    api, run_id, revision = _loaded_api()
    interaction = _repair_interaction(api, run_id, revision)
    directive_id = _submit_directive(api, run_id, interaction)
    preview_id = _preview_directive(api, run_id, directive_id)
    status, _applied = api.apply_repair_preview(
        run_id,
        directive_id,
        preview_id,
        {"user_confirmation": True},
    )
    assert status == 200

    status, run = api.get_run(run_id)

    assert status == 200
    assert run["overlay_version"] == 1
    assert run["revision_token"] == "demo:snap_b61a1efdd39c:1"
    assert run["projection_status"] == "projection_unavailable"


def test_stale_revision_returns_409() -> None:
    api, run_id, revision = _loaded_api()

    status, body = api.get_repair_interaction(
        run_id,
        "irs_b07e4440a217",
        "keep_in_main_flow",
        f"{revision}:stale",
    )

    assert status == 409
    assert body["error"]["code"] == "stale_revision"


def test_malformed_directive_payload_returns_invalid_request() -> None:
    api, run_id, revision = _loaded_api()
    interaction = _repair_interaction(api, run_id, revision)

    status, body = api.submit_repair_directive(
        run_id,
        {
            "issue_id": "irs_b07e4440a217",
            "strategy_id": interaction["strategy_id"],
            "option_id": interaction["option_id"],
            "contract_id": interaction["contract_id"],
            "contract_version": interaction["contract_version"],
            "revision_token": interaction["revision_token"],
            "field_values": "bad",
        },
    )

    assert status == 400
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["message"] == "field_values must be an object"


def test_apply_requires_user_confirmation() -> None:
    api, run_id, revision = _loaded_api()
    interaction = _repair_interaction(api, run_id, revision)
    directive_id = _submit_directive(api, run_id, interaction)
    preview_id = _preview_directive(api, run_id, directive_id)

    status, body = api.apply_repair_preview(
        run_id,
        directive_id,
        preview_id,
        {"user_confirmation": False},
    )

    assert status == 422
    assert body["error"]["code"] == "input_required"


def test_directive_cannot_be_previewed_from_other_run() -> None:
    api, run_id, revision = _loaded_api()
    interaction = _repair_interaction(api, run_id, revision)
    directive_id = _submit_directive(api, run_id, interaction)
    api.store.put(replace(api.store.require(run_id), api_run_id="other-run"))

    status, body = api.preview_repair_directive("other-run", directive_id)

    assert status == 404
    assert body["error"]["code"] == "directive_not_found"


def test_preview_cannot_be_applied_to_other_directive() -> None:
    api, run_id, revision = _loaded_api()
    interaction = _repair_interaction(api, run_id, revision)
    first_directive_id = _submit_directive(api, run_id, interaction)
    preview_id = _preview_directive(api, run_id, first_directive_id)
    second_directive_id = _submit_directive(
        api,
        run_id,
        interaction,
        additional_instruction="Keep the parent task wording unchanged.",
    )
    assert second_directive_id != first_directive_id

    status, body = api.apply_repair_preview(
        run_id,
        second_directive_id,
        preview_id,
        {"user_confirmation": True},
    )

    assert status == 404
    assert body["error"]["code"] == "preview_not_found"
