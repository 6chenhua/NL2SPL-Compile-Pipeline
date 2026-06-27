"""C2: Demo CLI tests --fixture-based + interactive simulation."""

import pytest

from nl2spl.compiler.spl_editing.cli import _build_default_service, _load_snapshot
from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import ExceptionFlowRef
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from tests.spl_editing_stub_llm import StubSuggestionLLM


def _build_mh_snapshot() -> ArtifactSnapshot:
    diag = CompileDiagnostic(
        "diag_mh",
        "missing_handler",
        "warning",
        "Exception flow has condition but no handler step.",
        target_ref="worker:w_main.exception_flow:exc_1",
        blocks_completion=True,
    )
    diag.metadata["irs_ref"] = {
        "construct_type": "EXCEPTION_FLOW",
        "construct_id": "x",
        "slot_name": "handler_action",
        "construct_path": [],
        "source_authority": "post_normalize_irs",
    }
    diag.metadata["authority"] = "post_normalize_irs"
    diag.metadata["repairability"] = "editable"
    diag.metadata["issue_group_id"] = "g_mh"
    diag.metadata["issue_role"] = "primary"
    return ArtifactSnapshot(
        "snap_mh",
        "run_mh",
        0,
        worker_plan=WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    "w_main",
                    "MainWorker",
                    "main",
                    "Main worker",
                    boundary_kind="main_worker",
                )
            ],
        ),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={
                "w_main": FlowStructureIR(
                    exception_flows=[
                        ExceptionFlowRef(
                            flow_id="exc_1",
                            condition_text="Template unavailable.",
                            blocks=[],
                        )
                    ],
                ),
            }
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "w_main": BlockStructureIR(),
            }
        ),
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
        agent_profile=AgentProfileIR(
            persona=PersonaIR(role="Assistant", aspects=[]),
        ),
        compile_diagnostics=(diag,),
    )


def _build_mop_snapshot() -> ArtifactSnapshot:
    diag = CompileDiagnostic(
        "diag_mop",
        "missing_output_producer",
        "warning",
        "Required output 'draft' has no source-backed producer step.",
        target_ref="worker:w_main.output:draft",
        blocks_completion=True,
    )
    diag.metadata["irs_ref"] = {
        "construct_type": "REQUIRED_OUTPUT",
        "construct_id": "x",
        "slot_name": "producer",
        "construct_path": [],
        "source_authority": "post_normalize_irs",
    }
    diag.metadata["authority"] = "post_normalize_irs"
    diag.metadata["repairability"] = "editable"
    diag.metadata["issue_group_id"] = "g_mop"
    diag.metadata["issue_role"] = "primary"
    return ArtifactSnapshot(
        "snap_mop",
        "run_mop",
        0,
        worker_plan=WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    "w_main",
                    "MainWorker",
                    "main",
                    "Main worker",
                    boundary_kind="main_worker",
                )
            ],
        ),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={
                "w_main": FlowStructureIR(),
            }
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "w_main": BlockStructureIR(),
            }
        ),
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
        agent_profile=AgentProfileIR(
            persona=PersonaIR(role="Assistant", aspects=[]),
        ),
        compile_diagnostics=(diag,),
    )


def _mock_input(monkeypatch, responses: list[str]):
    """Replace builtins.input with canned responses."""
    it = iter(responses)

    def _fake(prompt: str = "") -> str:
        val = next(it)
        return val

    monkeypatch.setattr("builtins.input", _fake)


class TestC2DemoCLI:
    """C2: Demo CLI paths via fixture snapshots."""

    def test_default_service_requires_configured_llm(self, monkeypatch) -> None:
        """Production default does not silently fall back to stub LLM."""

        class EmptyLLMConfig:
            api_key = None

        monkeypatch.setattr("nl2spl.config.LLMConfig", EmptyLLMConfig)
        with pytest.raises(SPLEditingError, match="requires a configured LLM"):
            _build_default_service()

    def test_missing_handler_demo_path(self) -> None:
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        snap = _build_mh_snapshot()
        run_id = svc.register_compile_result(snap)

        issues = svc.list_editable_issues(run_id)
        assert len(issues) >= 1
        assert issues[0].kind == "missing_handler"

        session = svc.create_session(run_id, issues[0])
        suggestions = svc.generate_suggestions(session.session_id)
        assert len(suggestions) >= 1

        updated = svc.apply_suggestion(session.session_id, suggestions[0].suggestion_id)
        assert updated.overlay_version > 0

        result = svc.verify_session(session.session_id)
        assert result.accepted is True

    def test_missing_handler_default_service_uses_materialization_intent(self) -> None:
        from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent

        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        snap = _build_mh_snapshot()
        run_id = svc.register_compile_result(snap)
        issue = svc.list_editable_issues(run_id)[0]
        session = svc.create_session(run_id, issue)
        suggestions = svc.generate_suggestions(session.session_id)

        assert isinstance(suggestions[0].patch.payload, ConstructRepairIntent)
        updated = svc.apply_suggestion(session.session_id, suggestions[0].suggestion_id)
        patched = svc._get_snapshot(run_id)
        step = patched.worker_step_plan.worker_steps["w_main"][0]
        assert updated.overlay_version == 1
        assert step.metadata["materialization_plan_id"] == "stage7.exception_handler_step_repair.v1"
        assert step.metadata["materialization_authority"] == "stage7.worker_step_plan"
        assert step.flow_ref == "exc_1"
        assert step.block_ref

    def test_missing_output_producer_demo_path(self) -> None:
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        snap = _build_mop_snapshot()
        run_id = svc.register_compile_result(snap)

        issues = svc.list_editable_issues(run_id)
        assert len(issues) >= 1
        assert issues[0].kind == "missing_output_producer"

        session = svc.create_session(run_id, issues[0])
        suggestions = svc.generate_suggestions(session.session_id)
        assert len(suggestions) >= 1

        updated = svc.apply_suggestion(session.session_id, suggestions[0].suggestion_id)
        assert updated.overlay_version > 0

        result = svc.verify_session(session.session_id)
        assert result.accepted is True

    def test_missing_artifacts_fails_fast(self) -> None:
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        snap = ArtifactSnapshot("snap_x", "run_x", 0)
        run_id = svc.register_compile_result(snap)
        issues = svc.list_editable_issues(run_id)
        assert issues == ()

    def test_cli_does_not_import_feedback_report(self) -> None:
        """C2: CLI never imports feedback report renderer."""
        import inspect

        from nl2spl.compiler.spl_editing import cli as cli_mod

        source = inspect.getsource(cli_mod)
        assert "feedback_report_renderer" not in source
        assert "render_feedback_report" not in source

    def test_interactive_demo_flow(self, monkeypatch, capsys) -> None:
        """C2: simulate interactive demo: select issue 1,
        confirm apply, print patched SPL."""
        _mock_input(monkeypatch, ["1", "1", "", "y"])
        monkeypatch.setattr(
            "nl2spl.compiler.spl_editing.cli.build_suggestion_llm_from_env",
            lambda: StubSuggestionLLM(),
        )
        from nl2spl.compiler.spl_editing.cli import _run_demo

        _run_demo(_build_mh_snapshot())

        captured = capsys.readouterr()
        output = captured.out
        assert "Editable issues" in output
        assert "What was detected" in output
        assert "Repair suggestion" in output
        assert "Verification result" in output
        assert "accepted" in output
        assert "Updated SPL" in output

    def test_interactive_demo_cancel_does_not_apply(self, monkeypatch) -> None:
        """C2: cancelling confirmation does not apply."""
        _mock_input(monkeypatch, ["1", "n"])
        monkeypatch.setattr(
            "nl2spl.compiler.spl_editing.cli.build_suggestion_llm_from_env",
            lambda: StubSuggestionLLM(),
        )
        from nl2spl.compiler.spl_editing.cli import _run_demo

        _run_demo(_build_mh_snapshot())
        # No crash --just cancelled

    def test_bind_suggestion_not_generated_after_r11(self) -> None:
        """R11: missing-output default flow exposes only materialized InsertProducerStep."""
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        snap = _build_mop_snapshot()
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            "snap_mop",
            "run_mop",
            0,
            worker_plan=snap.worker_plan,
            worker_step_plan=WorkerStepPlanIR(
                "w_main",
                {
                    "w_main": [
                        StepIR("st_existing_1", "Draft work 1", ["s1"], "GENERAL_COMMAND"),
                    ],
                },
            ),
            worker_flow_plan=snap.worker_flow_plan,
            worker_block_plan=snap.worker_block_plan,
            resources=snap.resources,
            symbol_table=snap.symbol_table,
            agent_profile=snap.agent_profile,
            compile_diagnostics=snap.compile_diagnostics,
        )
        run_id = svc.register_compile_result(snap)
        issues = svc.list_editable_issues(run_id)
        session = svc.create_session(run_id, issues[0])
        suggestions = svc.generate_suggestions(
            session.session_id,
            selected_patch_types=("BindExistingProducerStep",),
        )
        assert tuple(suggestions) == ()

    def test_no_bind_suggestion_when_no_bindable_step(self) -> None:
        """C4: handler does NOT generate Bind when no renderable step."""
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        snap = _build_mop_snapshot()
        run_id = svc.register_compile_result(snap)
        issues = svc.list_editable_issues(run_id)
        session = svc.create_session(run_id, issues[0])
        suggestions = svc.generate_suggestions(session.session_id)
        patch_types = {s.patch.patch_type for s in suggestions}
        assert "BindExistingProducerStep" not in patch_types

    def test_load_snapshot_rejects_missing_file(self, tmp_path) -> None:
        """C2: _load_snapshot raises when spl_editing_snapshot.json is missing."""
        import pytest

        with pytest.raises(FileNotFoundError, match="spl_editing_snapshot.json"):
            _load_snapshot(str(tmp_path))

    def test_main_entry_with_json_snapshot(self, monkeypatch, tmp_path) -> None:
        """C2: main() with --run loads canonical JSON and runs demo."""
        import sys

        from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
            JsonFileSnapshotRepository,
        )
        from nl2spl.compiler.spl_editing.cli import main
        from nl2spl.compiler.spl_editing.core.snapshot_adapter import (
            document_from_artifact_snapshot,
        )

        snap = _build_mh_snapshot()
        document = document_from_artifact_snapshot(snap)
        JsonFileSnapshotRepository().save(
            document,
            tmp_path / "spl_editing_snapshot.json",
        )

        # Mock input and argv
        _mock_input(monkeypatch, ["1", "1", "", "y"])
        monkeypatch.setattr(
            "nl2spl.compiler.spl_editing.cli.build_suggestion_llm_from_env",
            lambda: StubSuggestionLLM(),
        )
        monkeypatch.setattr(
            sys,
            "argv",
            ["spl-edit", "demo", "--run", str(tmp_path)],
        )
        main()  # Should not raise

        overlay_dir = tmp_path / "spl_editing_overlays"
        assert list(overlay_dir.glob("*.json"))
