"""S3.5 SnapshotBuilder tests."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from nl2spl.compiler.artifacts.snapshot.build.builder import SnapshotBuilder
from nl2spl.compiler.artifacts.snapshot.build.input import SnapshotBuildInput
from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
from nl2spl.compiler.artifacts.snapshot.config import SnapshotPersistenceConfig
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef, TraceRecord
from nl2spl.ir.span_ir import SpanIR


@pytest.fixture
def builder() -> SnapshotBuilder:
    return SnapshotBuilder()


def _input(**kwargs: object) -> SnapshotBuildInput:
    defaults: dict = {
        "compile_run_id": "run-001",
        "output_dir": Path("/tmp/output/run-001"),
    }
    defaults.update(kwargs)
    return SnapshotBuildInput(**defaults)  # type: ignore[arg-type]


class TestBuildInput:
    def test_minimal_input_is_frozen(self) -> None:
        inp = _input()
        assert inp.compile_run_id == "run-001"
        with pytest.raises(dataclasses.FrozenInstanceError):
            inp.compile_run_id = "changed"  # type: ignore[misc]

    def test_defaults_are_zeros(self) -> None:
        inp = _input()
        assert inp.source_spans == ()
        assert inp.constraints == ()
        assert inp.compile_diagnostics == ()
        assert inp.traces == ()
        assert inp.final_spl_text == ""
        assert inp.worker_plan is None


class TestBuilder:
    def test_builds_base_document(self, builder: SnapshotBuilder) -> None:
        inp = _input()
        doc = builder.build(inp)
        assert doc.is_base is True
        assert doc.artifact_kind == "spl_editing_artifact_snapshot"
        assert doc.identity.compile_run_id == "run-001"
        assert doc.identity.overlay_version == 0
        assert doc.identity.parent_snapshot_id is None
        assert doc.has_base_editing_history is True

    def test_build_identity_includes_producer(self, builder: SnapshotBuilder) -> None:
        inp = _input()
        doc = builder.build(inp)
        assert doc.identity.producer == "nl2spl"
        assert doc.identity.created_at != ""

    def test_generates_unique_snapshot_ids(self, builder: SnapshotBuilder) -> None:
        inp = _input()
        doc1 = builder.build(inp)
        doc2 = builder.build(inp)
        assert doc1.identity.snapshot_id != doc2.identity.snapshot_id

    def test_populates_source_spans(self, builder: SnapshotBuilder) -> None:
        spans = (SpanIR(span_id="s1", text="test"),)
        inp = _input(source_spans=spans)
        doc = builder.build(inp)
        assert doc.payload.source.spans == spans

    def test_populates_stage_artifacts(self, builder: SnapshotBuilder) -> None:
        inp = _input(
            worker_plan="wp", worker_flow_plan="wfp",
            worker_block_plan="wbp", worker_step_plan="wsp",
            resources="res", symbol_table="st",
        )
        doc = builder.build(inp)
        sa = doc.payload.stage_artifacts
        assert sa.worker_plan == "wp"
        assert sa.symbol_table == "st"

    def test_populates_replay_artifacts(self, builder: SnapshotBuilder) -> None:
        inp = _input(
            normalizer_input="ni", normalizer_output="no",
            stage10_input="s10", final_worker="fw",
            final_spl_text="[DEFINE_WORKER: W]",
        )
        doc = builder.build(inp)
        ra = doc.payload.replay_artifacts
        assert ra.normalizer_input == "ni"
        assert ra.gated_worker == "fw"
        assert ra.final_spl == "[DEFINE_WORKER: W]"

    def test_pre_gate_worker_included_when_config_enabled(self, builder: SnapshotBuilder) -> None:
        config = SnapshotPersistenceConfig(include_pre_gate_worker=True)
        inp = _input(pre_gate_worker="pre_gate_w", config=config)
        doc = builder.build(inp)
        assert doc.payload.replay_artifacts.assembled_worker_pre_gate == "pre_gate_w"

    def test_pre_gate_worker_excluded_by_default(self, builder: SnapshotBuilder) -> None:
        inp = _input(pre_gate_worker="pre_gate_w")
        doc = builder.build(inp)
        assert doc.payload.replay_artifacts.assembled_worker_pre_gate is None

    def test_populates_diagnostics(self, builder: SnapshotBuilder) -> None:
        diags = (
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
        )
        inp = _input(compile_diagnostics=diags)
        doc = builder.build(inp)
        assert len(doc.payload.diagnostics.compile_diagnostics) == 1

    def test_populates_traces(self, builder: SnapshotBuilder) -> None:
        traces = (TraceRecord(target_ref="step:st1"),)
        inp = _input(traces=traces)
        doc = builder.build(inp)
        assert len(doc.payload.provenance.traces) == 1

    def test_declared_capabilities_from_artifacts(self, builder: SnapshotBuilder) -> None:
        diags = (
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
        )
        inp = _input(
            compile_diagnostics=diags,
            source_spans=(SpanIR(span_id="s1", text="t"),),
            traces=(TraceRecord(target_ref="step:st1"),),
            worker_plan="wp", worker_flow_plan="wfp",
            worker_block_plan="wbp", worker_step_plan="wsp",
            resources="res", symbol_table="st",
            stage10_input="s10",
            normalizer_input="ni", normalizer_output="no",
            final_spl_text="[DEFINE_WORKER: W]",
        )
        doc = builder.build(inp)
        caps = doc.declared_capabilities
        assert caps.has(SnapshotCapability.ISSUE_EXTRACTION) is True
        assert caps.has(SnapshotCapability.LANE_A_REPLAY) is True
        assert caps.has(SnapshotCapability.LANE_B_REPLAY) is True
        assert caps.has(SnapshotCapability.FINAL_SPL_DISPLAY) is True

    def test_lane_a_not_declared_without_flow_block_plans(self, builder: SnapshotBuilder) -> None:
        """Missing worker_flow_plan/worker_block_plan must block Lane A declaration."""
        diags = (
            CompileDiagnostic(
                diagnostic_id="D1", kind="missing_handler",
                severity="warning", message="test",
            ),
        )
        inp = _input(
            compile_diagnostics=diags,
            worker_plan="wp", worker_step_plan="wsp",
            resources="res", symbol_table="st",
            stage10_input="s10",
            # worker_flow_plan and worker_block_plan MISSING
        )
        doc = builder.build(inp)
        assert doc.declared_capabilities.has(SnapshotCapability.LANE_A_REPLAY) is False
        assert doc.declared_capabilities.has(SnapshotCapability.LANE_B_REPLAY) is False

    def test_no_capabilities_declared_for_empty_input(self, builder: SnapshotBuilder) -> None:
        inp = _input()
        doc = builder.build(inp)
        assert doc.declared_capabilities.count == 0

    def test_non_editable_diagnostics_do_not_declare_issue_capability(
        self, builder: SnapshotBuilder,
    ) -> None:
        diags = (
            CompileDiagnostic(
                diagnostic_id="stage2_route_refinement_rejected_s4",
                kind="route_refinement_rejected",
                severity="warning",
                message="Rejected route refinement",
                target_ref="span:s4",
            ),
        )
        inp = _input(
            compile_diagnostics=diags,
            source_spans=(SpanIR(span_id="s1", text="t"),),
            traces=(TraceRecord(target_ref="span:s1"),),
        )
        doc = builder.build(inp)
        assert doc.declared_capabilities.has(
            SnapshotCapability.ISSUE_EXTRACTION
        ) is False
        assert doc.declared_capabilities.has(
            SnapshotCapability.SUGGESTION_GENERATION
        ) is False

    def test_builder_does_not_import_spl_editing(self) -> None:
        import importlib
        import sys

        mod_path = "nl2spl.compiler.artifacts.snapshot.build.builder"
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


class TestConfig:
    def test_default_config(self) -> None:
        c = SnapshotPersistenceConfig()
        assert c.enabled is True
        assert c.mode.value == "best_effort"
        assert c.filename == "spl_editing_snapshot.json"
        assert c.include_traces is True
        assert c.include_pre_gate_worker is False

    def test_disabled_factory(self) -> None:
        c = SnapshotPersistenceConfig.disabled()
        assert c.enabled is False
        assert c.mode.value == "disabled"

    def test_required_factory(self) -> None:
        c = SnapshotPersistenceConfig.required(
            SnapshotCapability.ISSUE_EXTRACTION,
        )
        assert c.mode.value == "required"
        assert SnapshotCapability.ISSUE_EXTRACTION in c.required_capabilities
