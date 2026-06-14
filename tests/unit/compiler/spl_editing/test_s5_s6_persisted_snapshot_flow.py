"""S5/S6 persisted snapshot loader and overlay flow tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
    JsonFileSnapshotRepository,
)
from nl2spl.compiler.artifacts.snapshot.persistence.loader import SnapshotLoader
from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.compiler.spl_editing.core.snapshot_adapter import (
    artifact_snapshot_from_document,
    document_from_artifact_snapshot,
)
from nl2spl.compiler.spl_editing.verification.lanes import LaneAReplayAdapter
from tests.spl_editing_stub_llm import StubSuggestionLLM
from tests.unit.compiler.spl_editing.test_c2_demo_cli import _build_mh_snapshot


def _write_snapshot(run_dir: Path) -> Path:
    path = run_dir / "spl_editing_snapshot.json"
    document = document_from_artifact_snapshot(_build_mh_snapshot())
    JsonFileSnapshotRepository().save(document, path)
    return path


class TestS5SnapshotLoaderCompatibility:
    def test_register_snapshot_file_lists_editable_issues(self, tmp_path: Path) -> None:
        path = _write_snapshot(tmp_path)
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())

        run_id = svc.register_snapshot_file(path)
        issues = svc.list_editable_issues(run_id)

        assert issues
        assert issues[0].kind == "missing_handler"

    def test_loader_rejects_feedback_report(self, tmp_path: Path) -> None:
        report = tmp_path / "feedback_report.md"
        report.write_text("# human report", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid JSON"):
            SnapshotLoader().load(report)

    def test_loader_rejects_stage_debug_json(self, tmp_path: Path) -> None:
        stage_json = tmp_path / "stage1.json"
        stage_json.write_text("{}", encoding="utf-8")

        with pytest.raises(ValueError, match="Stage JSON"):
            SnapshotLoader().load(stage_json)


class TestS6OverlayPersistence:
    def test_apply_and_verify_persist_full_overlay_snapshot(
        self, tmp_path: Path,
    ) -> None:
        base_path = _write_snapshot(tmp_path)
        repo = JsonFileSnapshotRepository()
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        run_id = svc.register_snapshot_file(base_path)

        issue = svc.list_editable_issues(run_id)[0]
        session = svc.create_session(run_id, issue)
        suggestion = svc.generate_suggestions(session.session_id)[0]

        updated = svc.apply_suggestion(session.session_id, suggestion.suggestion_id)

        overlay_files = sorted((tmp_path / "spl_editing_overlays").glob("*.json"))
        assert updated.overlay_version == 1
        assert len(overlay_files) == 1

        overlay_doc = repo.document_from_dict(repo.load(overlay_files[0]))
        assert overlay_doc.identity.overlay_version == 1
        assert overlay_doc.identity.base_snapshot_id == "snap_mh"
        assert overlay_doc.identity.parent_snapshot_id == "snap_mh"
        assert len(overlay_doc.editing_history.overlay_events) == 1
        assert len(overlay_doc.editing_history.accepted_patches) == 1

        result = svc.verify_session(session.session_id)
        assert result.accepted is True

        verified_doc = repo.document_from_dict(repo.load(overlay_files[0]))
        assert len(verified_doc.editing_history.verification_history) == 1
        assert verified_doc.editing_history.verification_history[0].passed is True

        reloaded_snapshot = artifact_snapshot_from_document(verified_doc)
        artifacts = LaneAReplayAdapter().replay(reloaded_snapshot)
        assert "MainWorker" in artifacts.rendered_spl


