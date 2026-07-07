from __future__ import annotations

import importlib.util
import json
import shutil
import threading
from pathlib import Path

from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
    JsonFileSnapshotRepository,
)
from nl2spl.compiler.spl_editing.presentation.explanation_cache import (
    read_cached_issue_explanation,
    read_explanation_cache,
    schedule_issue_explanations,
)


class _LLM:
    def __init__(self) -> None:
        self.release = threading.Event()
        self.calls = 0

    def generate_json(self, _system: str, prompt: str) -> str:
        self.calls += 1
        self.release.wait(timeout=5)
        facts = json.loads(prompt)["compiler_facts"]
        return json.dumps(
            {
                "headline": "Specific issue",
                "problem": "One field is undefined.",
                "impact": "The construct cannot be materialized safely.",
                "source_interpretation": "Intent is present but the contract is not.",
                "option_guidance": [
                    {
                        "option": option["option"],
                        "when_to_choose": "When it matches the intended behavior.",
                        "tradeoff": "Review the patch.",
                    }
                    for option in facts["repair_options"]
                ],
                "recommended_option": None,
                "recommendation_reason": "There is insufficient evidence.",
                "questions": ["What behavior was intended?"],
            }
        )


def _copy_snapshot(tmp_path: Path) -> Path:
    target = tmp_path / "spl_editing_snapshot.json"
    shutil.copyfile("examples/output/demo/spl_editing_snapshot.json", target)
    return target


def test_async_cache_moves_from_pending_to_ready(tmp_path: Path) -> None:
    path = _copy_snapshot(tmp_path)
    llm = _LLM()
    future = schedule_issue_explanations(path, llm, force=True)
    assert read_explanation_cache(path)["status"] == "pending"
    llm.release.set()
    result = future.result(timeout=10)
    cache = read_explanation_cache(path)
    assert result.status == "ready"
    assert cache["status"] == "ready"
    issue_id = next(iter(cache["items"]))
    assert read_cached_issue_explanation(path, issue_id) is not None
    JsonFileSnapshotRepository().load(path)


def test_ready_cache_avoids_new_calls(tmp_path: Path) -> None:
    path = _copy_snapshot(tmp_path)
    llm = _LLM()
    llm.release.set()
    schedule_issue_explanations(path, llm, force=True).result(timeout=10)
    calls = llm.calls
    schedule_issue_explanations(path, llm).result(timeout=1)
    assert llm.calls == calls


def test_run_demo_consumes_snapshot_cache() -> None:
    source = Path("examples/output/spl_editing_demo/run_demo.py").read_text()
    assert "schedule_issue_explanations" in source
    assert "read_cached_issue_explanation" in source


def test_run_demo_reads_precomputed_explanation_end_to_end(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    path = _copy_snapshot(tmp_path)
    llm = _LLM()
    llm.release.set()
    import nl2spl.compiler.spl_editing.cli as editing_cli

    monkeypatch.setattr(editing_cli, "build_suggestion_llm_from_env", lambda: llm)
    monkeypatch.setenv("SPL_EDITING_DEMO_BOOTSTRAPPED", "1")
    script_path = Path("examples/output/spl_editing_demo/run_demo.py")
    spec = importlib.util.spec_from_file_location("spl_editing_run_demo_e2e", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_choose_snapshot_path", lambda *args, **kwargs: path)
    monkeypatch.setattr(module, "_choose_fix_option", lambda _options: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")

    module.main([])

    output = capsys.readouterr().out
    assert "AI issue explanation (cached in snapshot)" in output
    cache = read_explanation_cache(path)
    assert cache is not None
    assert cache["status"] == "ready"
    assert cache["items"]
    assert all(item["status"] == "ready" for item in cache["items"].values())


def test_expected_correct_deferred_validation_issue_detail_presentation(
    tmp_path: Path,
) -> None:
    import pytest

    from nl2spl.compiler.spl_editing.cli import _build_default_service
    from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
    from nl2spl.compiler.spl_editing.presentation.service import (
        SPLEditingPresentationService,
    )

    path = _copy_snapshot(tmp_path)
    service = _build_default_service(suggestion_llm=_LLM())
    run_id = service.register_snapshot_file(path)
    presentation = SPLEditingPresentationService(service)

    issue = next(
        item
        for item in service.list_issue_inventory(run_id).deferred
        if item.irs_ref.construct_type == "API_DECLARATION"
    )
    detail = presentation.get_issue_detail_presentation(run_id, issue.issue_id)
    assert detail is not None
    assert detail.issue_id == issue.issue_id
    assert detail.presentation_quality is not None

    # Verify that available repairs has only review-only / no patch types
    assert len(detail.available_repairs) == 1
    opt = detail.available_repairs[0]
    assert not opt.patch_types  # empty tuple

    # Verify that we cannot generate suggestions for non-editable issues
    msg = "Cannot generate suggestions for non-editable issue"
    with pytest.raises(SPLEditingError, match=msg):
        presentation.generate_suggestions_for_option(run_id, issue.issue_id, 0)


def test_expected_correct_explanation_cache_handles_deferred_validation_issues(
    tmp_path: Path,
) -> None:
    from nl2spl.compiler.spl_editing.cli import _build_default_service

    path = _copy_snapshot(tmp_path)
    llm = _LLM()
    llm.release.set()
    # This will call schedule_issue_explanations which internally calls _issue_details.
    # It must not raise IssuePresentationNotFoundError.
    future = schedule_issue_explanations(path, llm, force=True)
    result = future.result(timeout=10)
    assert result.status == "ready"
    cache = read_explanation_cache(path)
    service = _build_default_service(suggestion_llm=_LLM())
    run_id = service.register_snapshot_file(path)
    deferred_api_issue_ids = {
        issue.issue_id
        for issue in service.list_issue_inventory(run_id).deferred
        if issue.irs_ref.construct_type == "API_DECLARATION"
    }
    assert deferred_api_issue_ids
    assert deferred_api_issue_ids.issubset(cache["items"].keys())
