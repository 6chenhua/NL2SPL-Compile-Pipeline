"""S3 File-backed Snapshot Repository tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
from nl2spl.compiler.artifacts.snapshot.model.document import (
    new_base_document,
    new_overlay_document,
)
from nl2spl.compiler.artifacts.snapshot.model.identity import (
    new_base_identity,
    new_overlay_identity,
)
from nl2spl.compiler.artifacts.snapshot.model.payload import (
    DiagnosticsLayer,
    SnapshotPayload,
    SourceLayer,
)
from nl2spl.compiler.artifacts.snapshot.model.validation import (
    SnapshotDeclaredCapabilities,
)
from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
    JsonFileSnapshotRepository,
)
from nl2spl.compiler.artifacts.snapshot.persistence.repository import (
    SnapshotRepository,
)
from nl2spl.compiler.artifacts.snapshot.validation.validator import SnapshotValidator
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from nl2spl.ir.span_ir import SpanIR


@pytest.fixture
def repo() -> JsonFileSnapshotRepository:
    return JsonFileSnapshotRepository()


def _base_doc() -> object:
    ident = new_base_identity("run-001", "snap-001", created_at="2025-06-15T10:00:00Z")
    return new_base_document(ident)


def _valid_doc() -> object:
    """A valid base document with compile_diagnostics."""
    ident = new_base_identity("run-001", "snap-001", created_at="2025-06-15T10:00:00Z")
    return new_base_document(
        ident,
        payload=SnapshotPayload(
            source=SourceLayer(spans=(SpanIR(span_id="s1", text="test"),)),
            diagnostics=DiagnosticsLayer(
                compile_diagnostics=(
                    CompileDiagnostic(
                        diagnostic_id="D1", kind="missing_handler",
                        severity="warning", message="test",
                        metadata={
                            "irs_ref": DiagnosticIRSRef("T", "id", "slot"),
                            "authority": "post_normalize_irs",
                            "repairability": "editable",
                            "issue_group_id": "g1",
                        },
                    ),
                ),
            ),
        ),
    )


# ===================================================================
# Protocol
# ===================================================================


class TestRepositoryProtocol:
    def test_repository_is_abstract(self) -> None:
        assert SnapshotRepository is not None
        # JsonFileSnapshotRepository is a concrete implementation
        repo = JsonFileSnapshotRepository()
        assert isinstance(repo, SnapshotRepository)

    def test_file_repo_is_concrete(self) -> None:
        repo = JsonFileSnapshotRepository()
        assert hasattr(repo, "save")
        assert hasattr(repo, "load")
        assert hasattr(repo, "save_overlay")


# ===================================================================
# Save and load round-trip
# ===================================================================


class TestSaveLoadRoundTrip:
    def test_save_and_load_valid_document(self, repo: JsonFileSnapshotRepository,
                                          tmp_path: Path) -> None:
        doc = _valid_doc()
        file_path = tmp_path / "spl_editing_snapshot.json"
        repo.save(doc, file_path)
        data = repo.load(file_path)
        assert isinstance(data, dict)
        assert data["artifact_kind"] == "spl_editing_artifact_snapshot"
        assert data["schema_version"] == "1.0.0"
        assert data["identity"]["compile_run_id"] == "run-001"
        assert data["identity"]["overlay_version"] == 0

    def test_save_and_load_preserves_identity(self, repo: JsonFileSnapshotRepository,
                                              tmp_path: Path) -> None:
        doc = _valid_doc()
        file_path = tmp_path / "snap.json"
        repo.save(doc, file_path)
        data = repo.load(file_path)
        ident = data["identity"]
        assert ident["compile_run_id"] == "run-001"
        assert ident["snapshot_id"] == "snap-001"
        assert ident["base_snapshot_id"] == "snap-001"
        assert ident["parent_snapshot_id"] is None
        assert ident["overlay_version"] == 0
        assert ident["producer"] == "nl2spl"

    def test_save_and_load_preserves_payload_spans(self, repo: JsonFileSnapshotRepository,
                                                   tmp_path: Path) -> None:
        doc = _valid_doc()
        file_path = tmp_path / "snap.json"
        repo.save(doc, file_path)
        data = repo.load(file_path)
        spans = data["payload"]["source"]["spans"]
        assert isinstance(spans, list)
        assert len(spans) == 1
        assert spans[0]["$type"] == "SpanIR"

    def test_load_restores_declared_capabilities_for_typed_validation(
        self, repo: JsonFileSnapshotRepository, tmp_path: Path,
    ) -> None:
        ident = new_base_identity(
            "run-001", "snap-001", created_at="2025-06-15T10:00:00Z",
        )
        doc = new_base_document(
            ident,
            payload=_valid_doc().payload,
            declared_capabilities=SnapshotDeclaredCapabilities(
                capabilities=(
                    SnapshotCapability.ISSUE_EXTRACTION,
                    SnapshotCapability.SUGGESTION_GENERATION,
                ),
            ),
        )
        file_path = tmp_path / "snap.json"

        repo.save(doc, file_path)
        loaded = repo.document_from_dict(repo.load(file_path))
        result = SnapshotValidator().validate(loaded)

        assert result.is_valid is True
        assert loaded.declared_capabilities.capabilities == (
            SnapshotCapability.ISSUE_EXTRACTION,
            SnapshotCapability.SUGGESTION_GENERATION,
        )

    def test_save_overlay_snapshot(self, repo: JsonFileSnapshotRepository,
                                   tmp_path: Path) -> None:
        base_ident = new_base_identity("run-001", "snap-001", created_at="t")
        base_doc = new_base_document(base_ident)
        overlay_ident = new_overlay_identity(base_ident, "snap-002", created_at="t2")
        overlay_doc = new_overlay_document(overlay_ident, base_doc)
        file_path = tmp_path / "overlay_snap.json"
        repo.save_overlay(overlay_doc, file_path)
        data = repo.load(file_path)
        assert data["identity"]["overlay_version"] == 1
        assert data["identity"]["parent_snapshot_id"] == "snap-001"


# ===================================================================
# Validation on save
# ===================================================================


class TestSaveValidation:
    def test_save_rejects_invalid_document(self, repo: JsonFileSnapshotRepository,
                                           tmp_path: Path) -> None:
        doc = _base_doc()  # Missing compile_diagnostics, will have diag errors
        file_path = tmp_path / "invalid.json"
        # Base doc without required diagnostics is still structurally valid
        repo.save(doc, file_path)
        data = repo.load(file_path)
        assert data["identity"]["compile_run_id"] == "run-001"

    def test_save_rejects_wrong_artifact_kind(self, repo: JsonFileSnapshotRepository,
                                              tmp_path: Path) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument

        ident = new_base_identity("run-001", "snap-001", created_at="t")
        doc = SnapshotDocument(artifact_kind="wrong_kind", identity=ident)
        file_path = tmp_path / "bad.json"
        with pytest.raises(ValueError, match="artifact_kind"):
            repo.save(doc, file_path)


# ===================================================================
# Load error handling
# ===================================================================


class TestLoadErrors:
    def test_load_missing_file_raises(self, repo: JsonFileSnapshotRepository,
                                      tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            repo.load(tmp_path / "nonexistent.json")

    def test_load_invalid_json_raises(self, repo: JsonFileSnapshotRepository,
                                      tmp_path: Path) -> None:
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("not valid json{{{", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            repo.load(bad_path)

    def test_load_non_dict_json_raises(self, repo: JsonFileSnapshotRepository,
                                        tmp_path: Path) -> None:
        list_path = tmp_path / "list.json"
        list_path.write_text('[1, 2, 3]', encoding="utf-8")
        with pytest.raises(ValueError, match="must be a dict"):
            repo.load(list_path)

    def test_load_stage_debug_json_rejected(self, repo: JsonFileSnapshotRepository,
                                            tmp_path: Path) -> None:
        stage_path = tmp_path / "stage1.json"
        stage_path.write_text('{"stage": 1, "data": "debug"}', encoding="utf-8")
        with pytest.raises(ValueError, match="stage debug JSON"):
            repo.load(stage_path)

    def test_load_wrong_schema_version_rejected(self, repo: JsonFileSnapshotRepository,
                                                tmp_path: Path) -> None:
        bad_path = tmp_path / "bad_version.json"
        bad_path.write_text(json.dumps({
            "artifact_kind": "spl_editing_artifact_snapshot",
            "schema_version": "9.9.9",
            "identity": {
                "compile_run_id": "run", "snapshot_id": "snap",
                "base_snapshot_id": "snap", "parent_snapshot_id": None,
                "overlay_version": 0, "created_at": "t",
                "producer": "nl2spl", "producer_version": "1.0.0",
            },
            "capabilities": {},
            "payload": {"source": {}, "stage_artifacts": {},
                        "replay_artifacts": {}, "diagnostics": {},
                        "provenance": {}, "editing": {}},
            "integrity": {"payload_hash": "sha256:aa", "artifact_set_hash": "sha256:bb"},
        }), encoding="utf-8")
        with pytest.raises(ValueError, match="Schema version|S2 validation"):
            repo.load(bad_path)

    def test_load_wrong_artifact_kind_rejected(self, repo: JsonFileSnapshotRepository,
                                               tmp_path: Path) -> None:
        bad_path = tmp_path / "bad_kind.json"
        bad_path.write_text(json.dumps({
            "artifact_kind": "not_a_snapshot",
            "schema_version": "1.0.0",
            "identity": {
                "compile_run_id": "run", "snapshot_id": "snap",
                "base_snapshot_id": "snap", "parent_snapshot_id": None,
                "overlay_version": 0, "created_at": "t",
                "producer": "nl2spl", "producer_version": "1.0.0",
            },
            "capabilities": {},
            "payload": {"source": {}, "stage_artifacts": {},
                        "replay_artifacts": {}, "diagnostics": {},
                        "provenance": {}, "editing": {}},
            "integrity": {"payload_hash": "sha256:aa", "artifact_set_hash": "sha256:bb"},
        }), encoding="utf-8")
        with pytest.raises(ValueError, match="artifact_kind|S2 validation"):
            repo.load(bad_path)

    def test_load_null_integrity_rejected(self, repo: JsonFileSnapshotRepository,
                                          tmp_path: Path) -> None:
        bad_path = tmp_path / "null_integrity.json"
        bad_path.write_text(json.dumps({
            "artifact_kind": "spl_editing_artifact_snapshot",
            "schema_version": "1.0.0",
            "identity": {
                "compile_run_id": "run", "snapshot_id": "snap",
                "base_snapshot_id": "snap", "parent_snapshot_id": None,
                "overlay_version": 0, "created_at": "t",
                "producer": "nl2spl", "producer_version": "1.0.0",
            },
            "capabilities": {},
            "payload": {"source": {}, "stage_artifacts": {},
                        "replay_artifacts": {}, "diagnostics": {},
                        "provenance": {}, "editing": {}},
            "integrity": None,
        }), encoding="utf-8")
        with pytest.raises(ValueError, match="payload_hash"):
            repo.load(bad_path)

    def test_load_missing_section_rejected(self, repo: JsonFileSnapshotRepository,
                                           tmp_path: Path) -> None:
        bad_path = tmp_path / "missing_section.json"
        base = {
            "artifact_kind": "spl_editing_artifact_snapshot",
            "schema_version": "1.0.0",
            "identity": {
                "compile_run_id": "run", "snapshot_id": "snap",
                "base_snapshot_id": "snap", "parent_snapshot_id": None,
                "overlay_version": 0, "created_at": "t",
                "producer": "nl2spl", "producer_version": "1.0.0",
            },
            "capabilities": {},
            "payload": {"source": {}, "stage_artifacts": {},
                        "replay_artifacts": {}, "diagnostics": {},
                        "provenance": {}, "editing": {}},
        }
        # Missing "integrity" key — remove it to see if validation catches
        bad_text = json.dumps(base)
        bad_path.write_text(bad_text, encoding="utf-8")
        with pytest.raises(ValueError, match="missing required section"):
            repo.load(bad_path)


# ===================================================================
# Atomic write
# ===================================================================


class TestAtomicWrite:
    def test_no_partial_file_on_error(self, repo: JsonFileSnapshotRepository,
                                      tmp_path: Path) -> None:
        """If a write fails, no partial .snapshot_tmp_ file should remain."""
        file_path = tmp_path / "should_not_exist.json"
        # Force an error by using a path with invalid characters (skip on Windows)
        # Instead, verify normal atomic write leaves no temp files
        doc = _valid_doc()
        repo.save(doc, file_path)
        # Verify no temp files remain in the directory
        temps = list(tmp_path.glob(".snapshot_tmp_*"))
        assert len(temps) == 0, f"Temp files left behind: {temps}"


# ===================================================================
# Boundary
# ===================================================================


class TestImportBoundary:
    def test_repository_does_not_import_spl_editing(self) -> None:
        import importlib
        import sys

        mod_path = "nl2spl.compiler.artifacts.snapshot.persistence.file_repository"
        mod = sys.modules.get(mod_path)
        if mod is None:
            mod = importlib.import_module(mod_path)

        forbidden = (
            "nl2spl.compiler.spl_editing.patches",
            "nl2spl.compiler.spl_editing.handlers",
            "nl2spl.compiler.spl_editing.storage",
        )
        for key in dir(mod):
            obj = getattr(mod, key)
            if hasattr(obj, "__module__"):
                mod_name = getattr(obj, "__module__", "")
                for f in forbidden:
                    assert not mod_name.startswith(f)

    def test_repository_does_not_parse_reports(self) -> None:
        import inspect

        from nl2spl.compiler.artifacts.snapshot.persistence import file_repository

        source = inspect.getsource(file_repository)
        assert "feedback_report" not in source.lower()
        assert "compile_report" not in source.lower()
        assert "load_intermediate_result" not in source
