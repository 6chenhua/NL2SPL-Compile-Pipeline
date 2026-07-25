from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from nl2spl.compiler.spl_editing.presentation import explanation_cache

REPO_ROOT = Path(__file__).resolve().parents[4]
SNAPSHOT = REPO_ROOT / "examples" / "output" / "demo" / "spl_editing_snapshot.json"


class _Detail:
    issue_id = "issue-test"


def _raise_generation_error(
    _self: Any,
    _detail: Any,
    *,
    language: str,
) -> Any:
    del language
    raise RuntimeError("generation infrastructure failed")


def _raise_submit_error(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("batch executor unavailable")


def test_batch_generation_failure_writes_error_cache(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    snapshot_path = tmp_path / "spl_editing_snapshot.json"
    shutil.copyfile(SNAPSHOT, snapshot_path)
    explanation_cache._write_cache(
        snapshot_path,
        {
            "schema_version": "issue_explanation_cache.v1",
            "status": "pending",
            "language": "zh-CN",
            "started_at": "2026-07-10T00:00:00+00:00",
            "completed_at": None,
            "items": {_Detail.issue_id: {"status": "pending", "explanation": None}},
        },
    )
    monkeypatch.setattr(
        explanation_cache.IssueExplanationGenerator,
        "generate",
        _raise_generation_error,
    )

    result = explanation_cache._generate_all(
        snapshot_path,
        (_Detail(),),
        object(),
        "zh-CN",
        1,
    )

    stored = explanation_cache.read_explanation_cache(snapshot_path)
    assert result.status == "error"
    assert result.cached_issue_ids == ()
    assert stored is not None
    assert stored["status"] == "error"
    assert stored["items"][_Detail.issue_id] == {
        "status": "error",
        "explanation": None,
        "error": "generation infrastructure failed",
    }


def test_batch_submit_failure_replaces_pending_cache_with_error(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    snapshot_path = tmp_path / "spl_editing_snapshot.json"
    shutil.copyfile(SNAPSHOT, snapshot_path)
    monkeypatch.setattr(
        explanation_cache,
        "_issue_details",
        lambda _path, _llm: (_Detail(),),
    )
    monkeypatch.setattr(
        explanation_cache._EXECUTOR,
        "submit",
        _raise_submit_error,
    )

    with pytest.raises(RuntimeError, match="batch executor unavailable"):
        explanation_cache.schedule_issue_explanations(
            snapshot_path,
            object(),
            force=True,
        )

    stored = explanation_cache.read_explanation_cache(snapshot_path)
    assert stored is not None
    assert stored["status"] == "error"
    assert stored["items"][_Detail.issue_id] == {
        "status": "error",
        "explanation": None,
        "error": "batch executor unavailable",
    }
