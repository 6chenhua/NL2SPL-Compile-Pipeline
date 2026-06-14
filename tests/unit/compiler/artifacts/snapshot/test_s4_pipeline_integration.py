"""S4 Pipeline Integration tests — snapshot config, PipelineResult fields, modes."""

from __future__ import annotations

from pathlib import Path

import pytest

from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
from nl2spl.compiler.artifacts.snapshot.config import SnapshotPersistenceConfig
from nl2spl.compiler.artifacts.snapshot.constants import SnapshotMode, SnapshotStatus
from nl2spl.config import PipelineConfig
from nl2spl.pipeline.orchestrator import PipelineResult


class TestPipelineConfig:
    def test_snapshot_field_defaults_to_none(self) -> None:
        cfg = PipelineConfig()
        assert cfg.snapshot is None

    def test_snapshot_config_attached(self) -> None:
        snap = SnapshotPersistenceConfig(enabled=False)
        cfg = PipelineConfig(snapshot=snap)
        assert cfg.snapshot is snap
        assert cfg.snapshot.enabled is False


class TestPipelineResult:
    def test_default_snapshot_fields(self) -> None:
        r = PipelineResult(spl_text="test", validation_errors=[], validation_warnings=[])
        assert r.spl_editing_snapshot_path is None
        assert r.spl_editing_snapshot_status == "not_requested"
        assert r.spl_editing_snapshot_error is None

    def test_snapshot_fields_settable(self) -> None:
        r = PipelineResult(
            spl_text="test", validation_errors=[], validation_warnings=[],
            spl_editing_snapshot_path=Path("/tmp/snap.json"),
            spl_editing_snapshot_status="available",
            spl_editing_snapshot_error=None,
        )
        assert r.spl_editing_snapshot_path == Path("/tmp/snap.json")
        assert r.spl_editing_snapshot_status == "available"

    def test_snapshot_status_values_match_s1_enum(self) -> None:
        """All status values must be from the S-1 SnapshotStatus enum."""
        valid = {s.value for s in SnapshotStatus}
        assert "not_requested" in valid
        assert "available" in valid
        assert "failed_best_effort" in valid
        assert "failed_required" in valid


class TestSnapshotConfigModes:
    def test_disabled_config(self) -> None:
        c = SnapshotPersistenceConfig.disabled()
        assert c.enabled is False
        assert c.mode == SnapshotMode.DISABLED

    def test_best_effort_is_default(self) -> None:
        c = SnapshotPersistenceConfig()
        assert c.mode == SnapshotMode.BEST_EFFORT

    def test_required_with_capabilities(self) -> None:
        c = SnapshotPersistenceConfig.required(
            SnapshotCapability.ISSUE_EXTRACTION,
            SnapshotCapability.LANE_A_REPLAY,
        )
        assert c.mode == SnapshotMode.REQUIRED
        assert SnapshotCapability.ISSUE_EXTRACTION in c.required_capabilities
        assert SnapshotCapability.LANE_A_REPLAY in c.required_capabilities


class TestImportBoundary:
    def test_orchestrator_does_not_import_spl_editing_patches(self) -> None:
        import inspect

        from nl2spl.pipeline import orchestrator

        source = inspect.getsource(orchestrator)
        assert "spl_editing.patches" not in source
        assert "spl_editing.handlers" not in source
        assert "spl_editing.storage" not in source


class TestRealPersistencePath:
    def test_persist_snapshot_with_real_keys(self, tmp_path: Path) -> None:
        """Verify _persist_snapshot maps real pipeline intermediate keys correctly."""
        from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
        from nl2spl.ir.span_ir import SpanIR

        orchestrator = _make_orchestrator(tmp_path)
        intermediate: dict = {
            "stage1_spans": [SpanIR(span_id="s1", text="test")],
            "stage2_routes": None,
            "stage3_5_worker_plan": None,
            "stage4_worker_flows": None,
            "stage5_worker_blocks": None,
            "stage7_worker_step_plan": None,
            "stage6_resources": None,
            "stage6_worker_scoped_resources": None,
            "symbol_table": None,
            "stage9_constraints": [],
            "stage8_profile": None,
            "stage10_worker": None,
            # Real pipeline stores normalization result as a tuple
            "stage9_5_normalization": (None, None, None, None, [], []),
            "canonical_input": None,
            "construct_plan": None,
        }
        diags = [
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
        ]
        path = orchestrator._persist_snapshot(
            compile_run_id="test-run",
            output_dir=tmp_path,
            spl_text="[DEFINE_WORKER: W]",
            final_spl_path=None,
            intermediate=intermediate,
            all_diagnostics=diags,
            traces=[],
        )
        assert path is not None
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "SpanIR" in content
        assert "compile_diagnostics" in content
        assert '"integrity"' in content

    def test_real_tuple_normalization_does_not_crash(self, tmp_path: Path) -> None:
        """Tuple-shaped stage9_5_normalization must not raise AttributeError."""
        from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef

        orchestrator = _make_orchestrator(tmp_path)
        # Real pipeline tuple: (flow, block, step, symbols, errors, warnings)
        intermediate: dict = {
            "stage1_spans": [],
            "stage9_5_normalization": ("flow", "block", "step", "symbols", [], []),
        }
        path = orchestrator._persist_snapshot(
            compile_run_id="test-run",
            output_dir=tmp_path,
            spl_text="test",
            final_spl_path=None,
            intermediate=intermediate,
            all_diagnostics=[
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
            ],
            traces=[],
        )
        assert path is not None
        assert path.exists()

    def test_lane_a_save_load_roundtrip(self, tmp_path: Path) -> None:
        """Full Lane A snapshot must survive save→load S2 validation."""
        from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
            JsonFileSnapshotRepository,
        )
        from nl2spl.compiler.artifacts.snapshot.validation.validator import (
            SnapshotValidator,
        )
        from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef

        orchestrator = _make_orchestrator(tmp_path)
        intermediate: dict = {
            "stage1_spans": [],
            "stage3_5_worker_plan": "wp",
            "stage4_worker_flows": "wfp",
            "stage5_worker_blocks": "wbp",
            "stage7_worker_step_plan": "wsp",
            "stage6_resources": "res",
            "symbol_table": "st",
            "stage9_5_normalization": ("wfp", "wbp", "wsp", "st", [], []),
        }
        diags = [
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
        ]
        path = orchestrator._persist_snapshot(
            compile_run_id="test-run",
            output_dir=tmp_path,
            spl_text="[DEFINE_WORKER: W]",
            final_spl_path=None,
            intermediate=intermediate,
            all_diagnostics=diags,
            traces=[],
        )
        # Reload must succeed (no S2 hash mismatch)
        repo = JsonFileSnapshotRepository()
        data = repo.load(path)
        assert data is not None
        # Verify Lane A is effective via S2 on reconstructed doc
        from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument

        doc = repo._dict_to_document(data)
        doc = SnapshotDocument(
            artifact_kind=doc.artifact_kind,
            schema_version=doc.schema_version,
            identity=doc.identity,
            declared_capabilities=doc.declared_capabilities,
            payload=doc.payload,
            integrity=None,
        )
        validator = SnapshotValidator()
        result = validator.validate(doc)
        assert result.effective_capabilities.has(
            SnapshotCapability.LANE_A_REPLAY
        ) is True, f"Failures: {result.capability_failures}"

    def test_tampered_json_rejected_by_load(self, tmp_path: Path) -> None:
        """Tampered snapshot JSON with old hash must fail load."""
        import json

        from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
            JsonFileSnapshotRepository,
        )
        from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef

        orchestrator = _make_orchestrator(tmp_path)
        diags = [
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
        ]
        path = orchestrator._persist_snapshot(
            compile_run_id="test-run",
            output_dir=tmp_path,
            spl_text="[DEFINE_WORKER: W]",
            final_spl_path=None,
            intermediate={"stage1_spans": [], "stage9_5_normalization": ()},
            all_diagnostics=diags,
            traces=[],
        )
        # Tamper: modify the SPL text but keep old hashes
        data = json.loads(path.read_text(encoding="utf-8"))
        data["payload"]["replay_artifacts"]["final_spl"] = "TAMPERED"
        path.write_text(json.dumps(data), encoding="utf-8")

        repo = JsonFileSnapshotRepository()
        with pytest.raises(ValueError, match="payload_hash mismatch"):
            repo.load(path)

    def test_required_capability_failure_raises(self, tmp_path: Path) -> None:
        """When required_capabilities are not effective, _persist_snapshot raises."""
        from nl2spl.compiler.artifacts.snapshot.config import SnapshotPersistenceConfig

        orchestrator = _make_orchestrator(
            tmp_path,
            snapshot=SnapshotPersistenceConfig.required(
                SnapshotCapability.LANE_A_REPLAY,
            ),
        )
        with pytest.raises(ValueError, match="Required capabilities"):
            orchestrator._persist_snapshot(
                compile_run_id="test-run",
                output_dir=tmp_path,
                spl_text="[DEFINE_WORKER: W]",
                final_spl_path=None,
                intermediate={},
                all_diagnostics=[],
                traces=[],
            )


def _make_orchestrator(
    tmp_path: Path,
    snapshot: object = None,
) -> object:
    import os

    from nl2spl.config import PipelineConfig

    os.environ.setdefault("OPENAI_API_KEY", "test-key-for-s4")

    cfg = PipelineConfig(
        output_dir=Path(str(tmp_path)),
        run_name="test-run",
        snapshot=snapshot,
    )
    from nl2spl.pipeline.orchestrator import PipelineOrchestrator

    return PipelineOrchestrator(cfg)


class TestSnapshotPersistenceDisabled:
    def test_disabled_mode_not_requested_status(self) -> None:
        """When no snapshot config or disabled, status stays not_requested."""
        r = PipelineResult(spl_text="test", validation_errors=[], validation_warnings=[])
        assert r.spl_editing_snapshot_status == "not_requested"
        assert r.spl_editing_snapshot_path is None
