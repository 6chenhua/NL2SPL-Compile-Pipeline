"""R9 Final Audit tests.

Verifies IRS v6 architecture boundaries, configuration hygiene, test hygiene,
and internal-comms-3 Issue 3 explanation capability.
"""

from __future__ import annotations

import inspect

import pytest

from nl2spl.compiler.irs import build_irs_checker_registry, build_irs_runner
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.config import PipelineConfig
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    WorkerPlanIR,
    WorkerSpecIR,
)


# ------------------------------------------------------------------
# R9.2: Configuration Audit
# ------------------------------------------------------------------


class TestR9ConfigSurface:
    """Verify runtime config surface and factory consistency."""

    def test_pipeline_config_has_no_stage_local_irs_flags(self) -> None:
        """Stage-local/v6 IRS runtime flags are no longer PipelineConfig options."""
        config = PipelineConfig()
        assert not hasattr(config, "enable_irs_v6_runner")
        assert not hasattr(config, "enable_irs_worker_delegation_check")
        assert not hasattr(config, "enable_irs_stage4_exception_flow_check")
        assert not hasattr(config, "enable_irs_stage7_step_check")
        assert not hasattr(config, "enable_irs_post_normalize_check")

    def test_factory_registry_matches_flags(self) -> None:
        """Factory registers checkers exactly matching flags."""
        reg_none = build_irs_checker_registry()
        assert reg_none.get_for_stage("stage3_5") == []
        assert reg_none.get_for_stage("stage4") == []
        assert reg_none.get_for_stage("stage7") == []

        reg_all = build_irs_checker_registry(
            enable_worker_delegation=True,
            enable_exception_flow=True,
            enable_step=True,
        )
        assert len(reg_all.get_for_stage("stage3_5")) == 1
        assert len(reg_all.get_for_stage("stage4")) == 1
        assert len(reg_all.get_for_stage("stage7")) == 1

    def test_irs_lazy_exports_no_circular_import(self) -> None:
        """Lazy exports resolve without circular import error."""
        from nl2spl.compiler.irs import (
            IRSCheckContext,
            IRSCheckerRegistry,
            IRSRunner,
            DiagnosticProjector,
        )
        assert IRSCheckContext is not None
        assert IRSCheckerRegistry is not None
        assert IRSRunner is not None
        assert DiagnosticProjector is not None


# ------------------------------------------------------------------
# R9.3: Authority Boundary Audit
# ------------------------------------------------------------------


class TestR9AuthorityBoundary:
    """Verify IRS modules are not imported by renderer/gate/producer_index."""

    def test_renderer_does_not_import_irs_modules(self) -> None:
        """SPL renderer does not depend on IRS runner/projector/checker."""
        import nl2spl.pipeline.stages.stage11_spl_renderer.renderer as renderer_mod
        source = inspect.getsource(renderer_mod)
        for term in ["IRSRunner", "DiagnosticProjector", "ConstructSatisfactionReport"]:
            assert term not in source, f"Renderer imports {term}"

    def test_gate_does_not_import_irs_runner_or_projector(self) -> None:
        """ExecutableElementGate does not depend on IRS runner/projector."""
        import nl2spl.pipeline.executable_gate as gate_mod
        source = inspect.getsource(gate_mod)
        for term in ["IRSRunner", "DiagnosticProjector"]:
            assert term not in source, f"Gate imports {term}"

    def test_producer_index_does_not_depend_on_irs_runner(self) -> None:
        """ProducerIndex does not depend on IRS runner/projector."""
        import nl2spl.compiler.producer_index as pi_mod
        source = inspect.getsource(pi_mod)
        for term in ["IRSRunner", "DiagnosticProjector"]:
            assert term not in source, f"ProducerIndex imports {term}"


# ------------------------------------------------------------------
# R9.4: Test Hygiene Audit
# ------------------------------------------------------------------


class TestR9TestHygiene:
    """Verify no skip/xfail in IRS tests."""

    # R9 plan specified file scope
    IRS_TEST_FILES = [
        "tests/unit/compiler/irs",
        "tests/unit/test_irs_v6_r1_report_schema.py",
        "tests/unit/test_executable_gate.py",
    ]

    def _collect_py_files(self) -> list:
        """Collect all .py files from the R9-specified scope."""
        import pathlib
        files = []
        for entry in self.IRS_TEST_FILES:
            p = pathlib.Path(entry)
            if p.is_dir():
                files.extend(p.glob("*.py"))
            elif p.is_file():
                files.append(p)
        # Exclude this audit file
        return [f for f in files if f.name != "test_r9_final_audit.py"]

    def test_no_pytest_skip_in_irs_tests(self) -> None:
        """No pytest.skip or pytest.mark.skip in IRS test files."""
        for py_file in self._collect_py_files():
            content = py_file.read_text(encoding="utf-8")
            in_docstring = False
            for line in content.splitlines():
                stripped = line.strip()
                if '"""' in stripped:
                    count = stripped.count('"""')
                    if count == 1:
                        in_docstring = not in_docstring
                    continue
                if in_docstring:
                    continue
                if stripped.startswith("#"):
                    continue
                assert "pytest.skip(" not in stripped, (
                    f"{py_file}: pytest.skip found: {stripped}"
                )
                assert "pytest.mark.skip" not in stripped, (
                    f"{py_file}: pytest.mark.skip found: {stripped}"
                )

    def test_no_xfail_in_irs_tests(self) -> None:
        """No pytest.mark.xfail in IRS test files."""
        for py_file in self._collect_py_files():
            content = py_file.read_text(encoding="utf-8")
            in_docstring = False
            for line in content.splitlines():
                stripped = line.strip()
                if '"""' in stripped:
                    count = stripped.count('"""')
                    if count == 1:
                        in_docstring = not in_docstring
                    continue
                if in_docstring:
                    continue
                if stripped.startswith("#"):
                    continue
                assert "xfail" not in stripped, (
                    f"{py_file}: xfail found: {stripped}"
                )


# ------------------------------------------------------------------
# R9.6: internal-comms-3 Issue 3 Explanation
# ------------------------------------------------------------------


class TestR9InternalCommsIssue3:
    """Verify IRS v6 can explain incomplete delegation."""

    def test_worker_promotion_blocked_explained(self) -> None:
        """Incomplete delegation produces WORKER_PROMOTION blocked report."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.worker_delegation import (
            WorkerDelegationIRSChecker,
        )

        checker = WorkerDelegationIRSChecker()
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_draft",
            candidate_kind="explicit_delegation",
            source_span_ids=["s1"],
            task_text="Draft using templates",
            purpose="Drafting",
            possible_inputs=[],
            possible_outputs=[],
            signals=["explicit_delegation"],
            risks=["no_clear_input_contract", "no_clear_output_contract"],
        )
        plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[WorkerSpecIR(
                worker_id="main", worker_name="main", kind="main",
                purpose="Main", owned_span_ids=["s1"],
                input_contract=[], output_contract=[],
                depends_on=[], constraints=[],
                boundary_kind="main_worker",
                decision_evidence=[], reason="",
            )],
            candidates=[candidate],
            handoffs=[],
            decisions=[],
        )
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        instances = checker.extract_instances(context)

        # WORKER_CANDIDATE report exists
        candidates = [
            i for i in instances if i.construct_type == "WORKER_CANDIDATE"
        ]
        assert len(candidates) == 1

        # WORKER_PROMOTION report exists and is blocked
        promotions = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ]
        assert len(promotions) == 1

        irs = SPLConstructRegistry.default().get("WORKER_PROMOTION")
        report = checker.check_instance(promotions[0], irs, context)

        assert report.metadata["promotion_status"] == "blocked"
        missing = report.metadata["promotion_missing_slots"]
        assert "promotion_input_contract" in missing
        assert "promotion_output_contract" in missing
        assert "promotion_invocation_point" in missing
        assert "promotion_result_handoff" in missing

        # blocked_by edges for each missing slot
        blocked_by = [
            e for e in report.related_edges if e.edge_type == "blocked_by"
        ]
        assert len(blocked_by) == len(missing)

    def test_diagnostic_projector_projects_promotion_diagnostics(self) -> None:
        """DiagnosticProjector projects type_or_contract_ambiguity for blocked promotion."""
        from nl2spl.compiler.irs import build_irs_runner

        runner = build_irs_runner(enable_worker_delegation=True)
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_draft",
            candidate_kind="explicit_delegation",
            source_span_ids=["s1"],
            task_text="Draft",
            purpose="Drafting",
            possible_inputs=[],
            possible_outputs=[],
            signals=["explicit_delegation"],
            risks=["no_clear_input_contract"],
        )
        plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[WorkerSpecIR(
                worker_id="main", worker_name="main", kind="main",
                purpose="Main", owned_span_ids=["s1"],
                input_contract=[], output_contract=[],
                depends_on=[], constraints=[],
                boundary_kind="main_worker",
                decision_evidence=[], reason="",
            )],
            candidates=[candidate],
            handoffs=[],
            decisions=[],
        )
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        result = runner.run_stage("stage3_5", context)

        # Diagnostics projected by DiagnosticProjector
        assert len(result.diagnostics) > 0
        kinds = {d.kind for d in result.diagnostics}
        assert "type_or_contract_ambiguity" in kinds

        # All 4 promotion slots must be projected as diagnostics
        projected_slots = {
            d.missing_slot.slot_name
            for d in result.diagnostics
            if d.kind == "type_or_contract_ambiguity" and d.missing_slot
        }
        assert projected_slots == {
            "promotion_input_contract",
            "promotion_output_contract",
            "promotion_invocation_point",
            "promotion_result_handoff",
        }

    def test_no_child_worker_generated_for_incomplete_delegation(self) -> None:
        """Incomplete delegation does not produce child worker instances."""
        from nl2spl.compiler.irs.checkers.worker_delegation import (
            WorkerDelegationIRSChecker,
        )

        checker = WorkerDelegationIRSChecker()
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_draft",
            candidate_kind="explicit_delegation",
            source_span_ids=["s1"],
            task_text="Draft",
            purpose="Drafting",
            possible_inputs=[],
            possible_outputs=[],
            signals=["explicit_delegation"],
            risks=["no_clear_input_contract"],
        )
        plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[WorkerSpecIR(
                worker_id="main", worker_name="main", kind="main",
                purpose="Main", owned_span_ids=["s1"],
                input_contract=[], output_contract=[],
                depends_on=[], constraints=[],
                boundary_kind="main_worker",
                decision_evidence=[], reason="",
            )],
            candidates=[candidate],
            handoffs=[],
            decisions=[],
        )
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        instances = checker.extract_instances(context)

        child_workers = [
            i for i in instances if i.construct_type == "CHILD_WORKER"
        ]
        assert len(child_workers) == 0


# ------------------------------------------------------------------
# R9.5: Test Matrix Coverage
# ------------------------------------------------------------------


class TestR9TestMatrixCoverage:
    """Verify all 11 test matrix scenarios have covering tests."""

    # Each entry: (scenario_name, test_file_pattern, test_name_fragment)
    # Mappings verified against 07_irs_v6_refactor_tasks.md test matrix.
    SCENARIOS = [
        # failure condition only: source-backed condition, no handler → missing_handler
        ("failure condition only", "test_r10_irs_subsystem_foundation", "missing_handler"),
        # failure condition + handler evidence: handler not misinterpreted as condition
        ("failure condition + handler evidence", "test_flow_assembler", "handler_action_not_materialized_as_condition"),
        ("required output no producer", "test_post_normalize_resource_contract_irs", "missing_output_producer"),
        # incomplete delegation: R4/R9 blocked promotion (not stale R0 baseline)
        ("incomplete delegation", "test_r9_final_audit", "test_worker_promotion_blocked_explained"),
        ("worker candidate only", "test_r4_worker_delegation", "promotion"),
        ("complete source-backed delegation", "test_r4_worker_delegation", "complete"),
        ("REQUEST_INPUT without ask signal", "test_r6_step_checker", "REQUEST_INPUT"),
        ("CALL_API with repository mention only", "test_r6_step_checker", "CALL_API"),
        ("assumed command", "test_r6_step_checker", "source_evidence"),
        ("compiler unpack without renderable producer", "test_executable_gate", "compiler_unpack_blocked"),
        ("gate-filtered handler", "test_executable_gate", "vague_handler_gate_chain"),
    ]

    def test_all_matrix_scenarios_have_covering_tests(self) -> None:
        """All 11 test matrix scenarios have covering tests in the codebase."""
        import pathlib

        test_dirs = [
            pathlib.Path("tests/unit"),
            pathlib.Path("tests/unit/compiler/irs"),
        ]

        for scenario, file_pattern, fragment in self.SCENARIOS:
            found = False
            for d in test_dirs:
                for py_file in d.rglob(f"*{file_pattern}*.py"):
                    content = py_file.read_text(encoding="utf-8")
                    if fragment in content:
                        found = True
                        break
                if found:
                    break
            assert found, (
                f"Scenario '{scenario}' has no covering test "
                f"(looking for '{fragment}' in {file_pattern})"
            )
