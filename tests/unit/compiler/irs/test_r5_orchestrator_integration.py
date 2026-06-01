"""R5 Orchestrator Integration tests.

Tests for IRS v6 runner integration with PipelineOrchestrator.
Verifies that Stage 3.5 IRS runner is correctly invoked and
diagnostics flow to compile_diagnostics and readable_report.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nl2spl.canonical import CanonicalCompileInput, HardFacts
from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import AmbiguityInfo, SpanIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerFlowPlanIR,
    WorkerBlockPlanIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


def _make_minimal_worker_spec(worker_id: str = "main") -> WorkerSpecIR:
    """Helper to create minimal WorkerSpecIR."""
    return WorkerSpecIR(
        worker_id=worker_id,
        worker_name=worker_id,
        kind="main" if worker_id == "main" else "child",
        purpose="Main workflow" if worker_id == "main" else "Child worker",
        owned_span_ids=["s1"],
        input_contract=[],
        output_contract=[],
        depends_on=[],
        constraints=[],
        boundary_kind="main_worker" if worker_id == "main" else "explicit_delegation",
        decision_evidence=[],
        reason="",
    )


def _make_incomplete_delegation_candidate() -> CandidateTaskUnitIR:
    """Helper to create incomplete delegation candidate."""
    return CandidateTaskUnitIR(
        candidate_id="cand_draft",
        candidate_kind="explicit_delegation",
        source_span_ids=["s1"],
        task_text="Process payment",
        purpose="Payment processing",
        possible_inputs=[],
        possible_outputs=[],
        signals=["explicit_delegation"],
        risks=["no_clear_input_contract", "no_clear_output_contract"],
    )


def _make_minimal_worker_plan() -> WorkerPlanIR:
    """Helper to create minimal WorkerPlanIR with incomplete candidate."""
    return WorkerPlanIR(
        main_worker_id="main",
        workers=[_make_minimal_worker_spec()],
        candidates=[_make_incomplete_delegation_candidate()],
        handoffs=[],
        decisions=[],
    )


def _mock_canonical_input(text: str) -> CanonicalCompileInput:
    """Helper to create CanonicalCompileInput."""
    return CanonicalCompileInput(
        raw_text=text,
        source_schema="text",
        schema_version="1.0",
        hard_facts=HardFacts(),
    )


class TestOrchestratorDefaultBehavior:
    """Tests for orchestrator with R5 flags disabled (default)."""

    def test_flags_default_to_false(self) -> None:
        """R5 flags default to False in PipelineConfig."""
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=Path("output"),
        )
        assert config.enable_irs_v6_runner is False
        assert config.enable_irs_worker_delegation_check is False

    def test_default_config_does_not_run_irs_v6(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Default config does not invoke IRS v6 runner."""
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=True,
        )

        # Mock LLMClient to avoid httpx initialization issues
        mock_client = MagicMock()
        monkeypatch.setattr(
            "nl2spl.pipeline.orchestrator.LLMClient",
            lambda config: mock_client,
        )

        # Mock all stages to avoid actual LLM calls
        span = SpanIR(span_id="s1", text="Do work", ambiguity=AmbiguityInfo())
        routes = FieldRouteIR(behavior=["s1"])
        worker_plan = _make_minimal_worker_plan()

        monkeypatch.setattr(
            "nl2spl.adapters.InputAdapterRegistry.adapt",
            lambda self, text: _mock_canonical_input(text),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage1",
            lambda self, *args, **kwargs: [span],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage2",
            lambda self, *args, **kwargs: (routes, []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3",
            lambda self, *args, **kwargs: ([span], routes),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3_5",
            lambda self, *args, **kwargs: worker_plan,
        )

        # Spy on _run_stage3_5_irs_v6 to verify it's not called
        irs_v6_called = {"called": False}

        original_method = PipelineOrchestrator._run_stage3_5_irs_v6

        def spy_irs_v6(self, **kwargs):
            irs_v6_called["called"] = True
            return original_method(self, **kwargs)

        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3_5_irs_v6",
            spy_irs_v6,
        )

        # Mock remaining stages to complete pipeline
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.ir.worker_ir import WorkerIR
        from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerBlockPlanIR, WorkerStepPlanIR

        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage4",
            lambda self, *args, **kwargs: WorkerFlowPlanIR(worker_flows={}),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage5",
            lambda self, *args, **kwargs: WorkerBlockPlanIR(worker_blocks={}),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage6",
            lambda self, *args, **kwargs: (ResourceRegistryIR(), SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage7",
            lambda self, *args, **kwargs: ([], SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage8",
            lambda self, *args, **kwargs: AgentProfileIR(persona=PersonaIR(role="T")),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage9",
            lambda self, *args, **kwargs: [],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_normalization",
            lambda self, *args, **kwargs: (
                FlowStructureIR(),
                BlockStructureIR(),
                [],
                [],
                SymbolTable(),
                [],
                [],
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage10",
            lambda self, *args, **kwargs: WorkerIR(
                worker_name="Main",
                description="Test",
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage11",
            lambda self, *args, **kwargs: ("SPL", [], []),
        )

        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run("Do work")

        # Verify IRS v6 runner was NOT called
        assert irs_v6_called["called"] is False

        # Verify no stage3_5 IRS intermediate results
        assert "construct_satisfaction" not in result.intermediate_results or \
               "stage3_5" not in result.intermediate_results.get("construct_satisfaction", {})
        assert "stage_local_diagnostics" not in result.intermediate_results or \
               "stage3_5" not in result.intermediate_results.get("stage_local_diagnostics", {})


class TestOrchestratorIRSV6Integration:
    """Tests for orchestrator with R5 flags enabled."""

    def test_flags_enabled_invokes_irs_v6_runner(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Flags enabled invokes IRS v6 runner after Stage 3.6."""
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=True,
            enable_irs_v6_runner=True,
            enable_irs_worker_delegation_check=True,
        )

        # Mock LLMClient to avoid httpx initialization issues
        mock_client = MagicMock()
        monkeypatch.setattr(
            "nl2spl.pipeline.orchestrator.LLMClient",
            lambda config: mock_client,
        )

        span = SpanIR(span_id="s1", text="Do work", ambiguity=AmbiguityInfo())
        routes = FieldRouteIR(behavior=["s1"])
        worker_plan = _make_minimal_worker_plan()

        monkeypatch.setattr(
            "nl2spl.adapters.InputAdapterRegistry.adapt",
            lambda self, text: _mock_canonical_input(text),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage1",
            lambda self, *args, **kwargs: [span],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage2",
            lambda self, *args, **kwargs: (routes, []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3",
            lambda self, *args, **kwargs: ([span], routes),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3_5",
            lambda self, *args, **kwargs: worker_plan,
        )

        # Spy on _run_stage3_5_irs_v6
        irs_v6_called = {"called": False, "context": None}

        original_method = PipelineOrchestrator._run_stage3_5_irs_v6

        def spy_irs_v6(self, **kwargs):
            irs_v6_called["called"] = True
            irs_v6_called["context"] = kwargs
            return original_method(self, **kwargs)

        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3_5_irs_v6",
            spy_irs_v6,
        )

        # Mock remaining stages
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.ir.worker_ir import WorkerIR

        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage4",
            lambda self, *args, **kwargs: WorkerFlowPlanIR(worker_flows={}),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage5",
            lambda self, *args, **kwargs: WorkerBlockPlanIR(worker_blocks={}),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage6",
            lambda self, *args, **kwargs: (ResourceRegistryIR(), SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage7",
            lambda self, *args, **kwargs: ([], SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage8",
            lambda self, *args, **kwargs: AgentProfileIR(persona=PersonaIR(role="T")),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage9",
            lambda self, *args, **kwargs: [],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_normalization",
            lambda self, *args, **kwargs: (
                FlowStructureIR(),
                BlockStructureIR(),
                [],
                [],
                SymbolTable(),
                [],
                [],
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage10",
            lambda self, *args, **kwargs: WorkerIR(
                worker_name="Main",
                description="Test",
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage11",
            lambda self, *args, **kwargs: ("SPL", [], []),
        )

        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run("Do work")

        # Verify IRS v6 runner WAS called
        assert irs_v6_called["called"] is True
        assert irs_v6_called["context"]["worker_plan"] == worker_plan

        # Verify stage3_5 IRS intermediate results exist
        assert "construct_satisfaction" in result.intermediate_results
        assert "stage3_5" in result.intermediate_results["construct_satisfaction"]
        assert "stage_local_diagnostics" in result.intermediate_results
        assert "stage3_5" in result.intermediate_results["stage_local_diagnostics"]

    def test_stage3_5_diagnostics_enter_compile_diagnostics(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Stage 3.5 IRS diagnostics appear in compile_diagnostics."""
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=True,
            enable_irs_v6_runner=True,
            enable_irs_worker_delegation_check=True,
        )

        # Mock LLMClient to avoid httpx initialization issues
        mock_client = MagicMock()
        monkeypatch.setattr(
            "nl2spl.pipeline.orchestrator.LLMClient",
            lambda config: mock_client,
        )

        span = SpanIR(span_id="s1", text="Do work", ambiguity=AmbiguityInfo())
        routes = FieldRouteIR(behavior=["s1"])
        worker_plan = _make_minimal_worker_plan()

        monkeypatch.setattr(
            "nl2spl.adapters.InputAdapterRegistry.adapt",
            lambda self, text: _mock_canonical_input(text),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage1",
            lambda self, *args, **kwargs: [span],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage2",
            lambda self, *args, **kwargs: (routes, []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3",
            lambda self, *args, **kwargs: ([span], routes),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3_5",
            lambda self, *args, **kwargs: worker_plan,
        )

        # Mock remaining stages
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.ir.worker_ir import WorkerIR

        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage4",
            lambda self, *args, **kwargs: WorkerFlowPlanIR(worker_flows={}),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage5",
            lambda self, *args, **kwargs: WorkerBlockPlanIR(worker_blocks={}),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage6",
            lambda self, *args, **kwargs: (ResourceRegistryIR(), SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage7",
            lambda self, *args, **kwargs: ([], SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage8",
            lambda self, *args, **kwargs: AgentProfileIR(persona=PersonaIR(role="T")),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage9",
            lambda self, *args, **kwargs: [],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_normalization",
            lambda self, *args, **kwargs: (
                FlowStructureIR(),
                BlockStructureIR(),
                [],
                [],
                SymbolTable(),
                [],
                [],
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage10",
            lambda self, *args, **kwargs: WorkerIR(
                worker_name="Main",
                description="Test",
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage11",
            lambda self, *args, **kwargs: ("SPL", [], []),
        )

        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run("Do work")

        # Verify diagnostics exist
        stage3_5_diags = result.intermediate_results["stage_local_diagnostics"]["stage3_5"]
        assert len(stage3_5_diags) > 0

        # Verify at least one diagnostic is type_or_contract_ambiguity
        diagnostic_kinds = [d.kind for d in stage3_5_diags]
        assert "type_or_contract_ambiguity" in diagnostic_kinds

        # Verify stage3_5 diagnostics are in compile_diagnostics
        compile_diag_ids = {d.diagnostic_id for d in result.compile_diagnostics}
        stage3_5_diag_ids = {d.diagnostic_id for d in stage3_5_diags}
        assert stage3_5_diag_ids.issubset(compile_diag_ids)

    def test_stage3_5_diagnostics_appear_in_readable_report(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Stage 3.5 IRS diagnostics appear in readable_report."""
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=True,
            enable_irs_v6_runner=True,
            enable_irs_worker_delegation_check=True,
        )

        # Mock LLMClient to avoid httpx initialization issues
        mock_client = MagicMock()
        monkeypatch.setattr(
            "nl2spl.pipeline.orchestrator.LLMClient",
            lambda config: mock_client,
        )

        span = SpanIR(span_id="s1", text="Do work", ambiguity=AmbiguityInfo())
        routes = FieldRouteIR(behavior=["s1"])
        worker_plan = _make_minimal_worker_plan()

        monkeypatch.setattr(
            "nl2spl.adapters.InputAdapterRegistry.adapt",
            lambda self, text: _mock_canonical_input(text),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage1",
            lambda self, *args, **kwargs: [span],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage2",
            lambda self, *args, **kwargs: (routes, []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3",
            lambda self, *args, **kwargs: ([span], routes),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3_5",
            lambda self, *args, **kwargs: worker_plan,
        )

        # Mock remaining stages
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.ir.worker_ir import WorkerIR

        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage4",
            lambda self, *args, **kwargs: WorkerFlowPlanIR(worker_flows={}),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage5",
            lambda self, *args, **kwargs: WorkerBlockPlanIR(worker_blocks={}),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage6",
            lambda self, *args, **kwargs: (ResourceRegistryIR(), SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage7",
            lambda self, *args, **kwargs: ([], SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage8",
            lambda self, *args, **kwargs: AgentProfileIR(persona=PersonaIR(role="T")),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage9",
            lambda self, *args, **kwargs: [],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_normalization",
            lambda self, *args, **kwargs: (
                FlowStructureIR(),
                BlockStructureIR(),
                [],
                [],
                SymbolTable(),
                [],
                [],
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage10",
            lambda self, *args, **kwargs: WorkerIR(
                worker_name="Main",
                description="Test",
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage11",
            lambda self, *args, **kwargs: ("SPL", [], []),
        )

        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run("Do work")

        # Verify readable_report contains specific Stage 3.5 diagnostic info
        assert result.readable_report is not None
        assert len(result.readable_report) > 0

        # Get stage3_5 diagnostics and verify their details appear in report
        stage3_5_diags = result.intermediate_results["stage_local_diagnostics"]["stage3_5"]
        assert len(stage3_5_diags) > 0

        report_lower = result.readable_report.lower()

        # Assert each stage3_5 diagnostic's kind and id appear in readable_report
        for diag in stage3_5_diags:
            assert diag.kind in report_lower, (
                f"Diagnostic kind '{diag.kind}' not found in readable_report"
            )
            assert diag.diagnostic_id in report_lower, (
                f"Diagnostic id '{diag.diagnostic_id}' not found in readable_report"
            )
            # If the diagnostic has a missing_slot, its slot_name should appear
            if diag.missing_slot is not None:
                assert diag.missing_slot.slot_name in report_lower, (
                    f"Missing slot '{diag.missing_slot.slot_name}' not found "
                    f"in readable_report"
                )

        # Also verify stage3_5 diagnostic ids are in compile_diagnostics
        compile_diag_ids = {d.diagnostic_id for d in result.compile_diagnostics}
        stage3_5_diag_ids = {d.diagnostic_id for d in stage3_5_diags}
        assert stage3_5_diag_ids.issubset(compile_diag_ids)

    def test_worker_plan_not_modified_by_irs_v6(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """IRS v6 runner does not modify WorkerPlanIR."""
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=True,
            enable_irs_v6_runner=True,
            enable_irs_worker_delegation_check=True,
        )

        # Mock LLMClient to avoid httpx initialization issues
        mock_client = MagicMock()
        monkeypatch.setattr(
            "nl2spl.pipeline.orchestrator.LLMClient",
            lambda config: mock_client,
        )

        span = SpanIR(span_id="s1", text="Do work", ambiguity=AmbiguityInfo())
        routes = FieldRouteIR(behavior=["s1"])
        worker_plan = _make_minimal_worker_plan()

        # Capture original state
        original_workers_count = len(worker_plan.workers)
        original_candidates_count = len(worker_plan.candidates)
        original_handoffs_count = len(worker_plan.handoffs)
        original_decisions_count = len(worker_plan.decisions)

        monkeypatch.setattr(
            "nl2spl.adapters.InputAdapterRegistry.adapt",
            lambda self, text: _mock_canonical_input(text),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage1",
            lambda self, *args, **kwargs: [span],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage2",
            lambda self, *args, **kwargs: (routes, []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3",
            lambda self, *args, **kwargs: ([span], routes),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3_5",
            lambda self, *args, **kwargs: worker_plan,
        )

        # Mock remaining stages
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.ir.worker_ir import WorkerIR

        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage4",
            lambda self, *args, **kwargs: WorkerFlowPlanIR(worker_flows={}),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage5",
            lambda self, *args, **kwargs: WorkerBlockPlanIR(worker_blocks={}),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage6",
            lambda self, *args, **kwargs: (ResourceRegistryIR(), SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage7",
            lambda self, *args, **kwargs: ([], SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage8",
            lambda self, *args, **kwargs: AgentProfileIR(persona=PersonaIR(role="T")),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage9",
            lambda self, *args, **kwargs: [],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_normalization",
            lambda self, *args, **kwargs: (
                FlowStructureIR(),
                BlockStructureIR(),
                [],
                [],
                SymbolTable(),
                [],
                [],
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage10",
            lambda self, *args, **kwargs: WorkerIR(
                worker_name="Main",
                description="Test",
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage11",
            lambda self, *args, **kwargs: ("SPL", [], []),
        )

        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run("Do work")

        # Verify WorkerPlanIR unchanged
        assert len(worker_plan.workers) == original_workers_count
        assert len(worker_plan.candidates) == original_candidates_count
        assert len(worker_plan.handoffs) == original_handoffs_count
        assert len(worker_plan.decisions) == original_decisions_count

    def test_validator_failure_skips_irs_v6(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """WorkerPlanValidator failure prevents IRS v6 runner from running."""
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=True,
            enable_irs_v6_runner=True,
            enable_irs_worker_delegation_check=True,
        )

        # Mock LLMClient to avoid httpx initialization issues
        mock_client = MagicMock()
        monkeypatch.setattr(
            "nl2spl.pipeline.orchestrator.LLMClient",
            lambda config: mock_client,
        )

        span = SpanIR(span_id="s1", text="Do work", ambiguity=AmbiguityInfo())
        routes = FieldRouteIR(behavior=["s1"])

        # Create an invalid WorkerPlanIR: main worker has invalid name
        invalid_worker = WorkerSpecIR(
            worker_id="main",
            worker_name="invalid name!",  # spaces and ! are not SPL-safe
            kind="main",
            purpose="Main workflow",
            owned_span_ids=["s1"],
            input_contract=[],
            output_contract=[],
            depends_on=[],
            constraints=[],
            boundary_kind="main_worker",
            decision_evidence=[],
            reason="",
        )
        invalid_plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[invalid_worker],
            candidates=[],
            handoffs=[],
            decisions=[],
        )

        monkeypatch.setattr(
            "nl2spl.adapters.InputAdapterRegistry.adapt",
            lambda self, text: _mock_canonical_input(text),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage1",
            lambda self, *args, **kwargs: [span],
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage2",
            lambda self, *args, **kwargs: (routes, []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3",
            lambda self, *args, **kwargs: ([span], routes),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3_5",
            lambda self, *args, **kwargs: invalid_plan,
        )

        # Spy on _run_stage3_5_irs_v6 to verify it's not called
        irs_v6_called = {"called": False}
        original_method = PipelineOrchestrator._run_stage3_5_irs_v6

        def spy_irs_v6(self, **kwargs):
            irs_v6_called["called"] = True
            return original_method(self, **kwargs)

        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage3_5_irs_v6",
            spy_irs_v6,
        )

        orchestrator = PipelineOrchestrator(config)

        # Validation error should propagate; IRS v6 should not run
        with pytest.raises(ValueError, match="WorkerPlanIR validation failed"):
            orchestrator.run("Do work")

        assert irs_v6_called["called"] is False

