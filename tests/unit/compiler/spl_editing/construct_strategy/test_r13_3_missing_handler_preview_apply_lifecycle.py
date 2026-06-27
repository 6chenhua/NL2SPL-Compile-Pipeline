"""R13.3 missing_handler preview/apply lifecycle tests."""

from __future__ import annotations

import inspect

import pytest

from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.compiler.spl_editing.core.service import SPLEditingService
from nl2spl.compiler.spl_editing.preview.errors import PreviewStaleError
from nl2spl.compiler.spl_editing.preview.store import PreviewStoreError
from tests.spl_editing_stub_llm import StubSuggestionLLM
from tests.unit.compiler.spl_editing.construct_strategy.test_r12_contract_baseline import (
    _snapshot,
)


def _build_flow():
    llm = StubSuggestionLLM(
        {
            "patch_type": "AddExceptionHandlerStep",
            "title": "Complete handler",
            "explanation": "Complete the missing exception handler action.",
            "payload": {"handler_goal": "Handle the exception."},
        }
    )
    svc = _build_default_service(suggestion_llm=llm)
    run_id = svc.register_compile_result(_snapshot())
    issue = svc.list_editable_issues(run_id)[0]
    session = svc.create_session(run_id, issue)
    suggestions = svc.generate_suggestions(session.session_id).suggestions
    assert len(suggestions) == 1
    return svc, run_id, session, suggestions[0]


def test_preview_suggestion_does_not_mutate_snapshot_or_overlay() -> None:
    svc, _run_id, session, suggestion = _build_flow()

    preview = svc.preview_suggestion(session.session_id, suggestion.suggestion_id)
    unchanged_session = svc._sessions.get(session.session_id)

    assert preview.preview_id.startswith("prev_")
    assert preview.base_snapshot_id == session.artifact_snapshot_id
    assert "[EXCEPTION_FLOW]" in preview.rendered_preview
    assert "[SEQUENTIAL_BLOCK]" in preview.rendered_preview
    assert "Patch adapter" not in preview.rendered_preview
    assert "Target:" not in preview.rendered_preview
    assert "stage5." not in preview.rendered_preview
    assert "stage7." not in preview.rendered_preview
    assert unchanged_session.overlay_version == 0
    assert unchanged_session.artifact_snapshot_id == session.artifact_snapshot_id
    with pytest.raises(PreviewStoreError):
        svc.get_preview_store().validate_applicable(
            "missing_preview",
            session.session_id,
            session.issue.issue_id,
            session.artifact_snapshot_id,
        )


def test_apply_preview_result_increments_overlay_and_lane_b_accepts() -> None:
    svc, _run_id, session, suggestion = _build_flow()
    preview = svc.preview_suggestion(session.session_id, suggestion.suggestion_id)

    updated = svc.apply_preview_result(
        session.session_id,
        suggestion.suggestion_id,
        preview.preview_id,
    )
    result = svc.verify_session(session.session_id)

    assert updated.overlay_version == 1
    assert result.accepted is True
    assert result.lane == "B"
    assert result.failure_reasons == ()
    with pytest.raises(PreviewStoreError):
        svc.get_preview_store().get(preview.preview_id)


def test_apply_preview_result_rejects_stale_user_advice_before_overlay() -> None:
    svc, _run_id, session, suggestion = _build_flow()
    preview = svc.preview_suggestion(
        session.session_id,
        suggestion.suggestion_id,
        user_text="Handle the exception.",
    )

    with pytest.raises(PreviewStaleError):
        svc.apply_preview_result(
            session.session_id,
            suggestion.suggestion_id,
            preview.preview_id,
            user_text="Ask the user for a replacement template.",
        )

    unchanged_session = svc._sessions.get(session.session_id)
    assert unchanged_session.overlay_version == 0
    verify = svc.verify_session(session.session_id)
    assert verify.accepted is False
    assert verify.failure_reasons == ("No overlay events for this session",)


def test_apply_preview_result_requires_stored_preview_id() -> None:
    svc, _run_id, session, suggestion = _build_flow()

    with pytest.raises(PreviewStoreError):
        svc.apply_preview_result(
            session.session_id,
            suggestion.suggestion_id,
            "prev_missing",
        )


def test_default_service_catalog_enables_missing_handler_preview_gate() -> None:
    svc, _run_id, session, suggestion = _build_flow()
    ctx = svc._confirmation_contexts.get(f"ctx_{suggestion.suggestion_id}")

    assert ctx.catalog_entry.repair_strategy_id == "exception_flow.complete_handler_action.v1"
    assert ctx.catalog_entry.preview_required is True
    assert isinstance(svc, SPLEditingService)


def test_cli_default_flow_uses_preview_apply_api() -> None:
    import nl2spl.compiler.spl_editing.cli as cli_module

    source = inspect.getsource(cli_module._run_demo_for_run)

    assert ".preview_suggestion(" in source
    assert ".apply_preview_result(" in source
    assert ".apply_suggestion(" not in source
