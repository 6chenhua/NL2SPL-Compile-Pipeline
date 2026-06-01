"""R2 IRS v6 Framework Skeleton Tests

Tests the R2 framework skeleton including:
- IRSCheckContext
- ConstructInstance
- IRSChecker Protocol
- IRSCheckerRegistry
- IRSRunner
- DiagnosticProjector skeleton

R2 rules:
1. Only test framework skeleton, not checker migration
2. No orchestrator integration
3. No Worker/Delegation checker implementation
4. No LLM or rule-based semantic logic
5. Projector skeleton does not generate diagnostics (R3)
"""

import typing

import pytest

from nl2spl.compiler.construct_registry import (
    ConstructCompleteness,
    ConstructIRS,
    ConstructSatisfactionReport,
    ExistencePolicy,
    SlotSatisfaction,
    SlotSpec,
    SPLConstructRegistry,
)
from nl2spl.compiler.irs import (
    ConstructEdge,
    ConstructInstance,
    DiagnosticProjectionResult,
    DiagnosticProjector,
    IRSCheckContext,
    IRSChecker,
    IRSCheckerRegistry,
    IRSRunResult,
    IRSRunner,
)


# ===========================================================================
# Fake Checker for Protocol Testing
# ===========================================================================


class RecordingProjector:
    """Recording projector for testing runner-projector integration."""
    
    def __init__(self):
        self.call_count = 0
        self.received_reports = []
        self.received_contexts = []
    
    def project(
        self,
        reports: list[ConstructSatisfactionReport],
        context: IRSCheckContext,
    ) -> DiagnosticProjectionResult:
        """Record call and return test warning."""
        self.call_count += 1
        self.received_reports.append(reports)
        self.received_contexts.append(context)
        return DiagnosticProjectionResult(
            diagnostics=[],
            warnings=["projector_was_called"],
        )


class FakeChecker:
    """Fake checker for testing IRSChecker protocol compliance."""
    
    checker_id = "fake_checker"
    supported_construct_types = ("GENERAL_COMMAND",)
    supported_stages = ("stage_fake",)
    
    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        """Extract fake instances from context."""
        # Simple extraction: create one instance per step in context
        instances = []
        for i, step in enumerate(context.steps):
            instances.append(
                ConstructInstance(
                    construct_id=f"step_{i}",
                    construct_type="GENERAL_COMMAND",
                    ir_ref=step,
                    source_span_ids=[f"s{i}"],
                )
            )
        return instances
    
    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Check fake instance."""
        # Simple check: always return complete and renderable
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=[
                SlotSatisfaction(
                    slot_name="command",
                    status="satisfied",
                    source_span_ids=instance.source_span_ids,
                )
            ],
            completeness="complete",
            renderable=True,
            source_span_ids=instance.source_span_ids,
        )


class AnotherFakeChecker:
    """Another fake checker for registry multi-checker tests."""
    
    checker_id = "another_fake_checker"
    supported_construct_types = ("WORKER",)
    supported_stages = ("stage_fake", "stage8")
    
    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        return []
    
    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=[],
            completeness="partial",
            renderable=False,
        )


# ===========================================================================
# 7.1 IRSCheckContext Tests
# ===========================================================================


class TestR2IRSCheckContext:
    """Test IRSCheckContext read-only input container."""
    
    def test_context_allows_stage_only_construction(self):
        """Verify context can be constructed with only stage_name."""
        context = IRSCheckContext(stage_name="stage4")
        
        assert context.stage_name == "stage4"
        assert context.spans == ()
        assert context.routes is None
        assert context.flow is None
        assert context.steps == ()
        assert context.metadata == {}
    
    def test_context_accepts_partial_stage_artifacts(self):
        """Verify context accepts partial IR artifacts for different stages."""
        # Stage 4 context with flow only
        context_stage4 = IRSCheckContext(
            stage_name="stage4",
            spans=("span1", "span2"),
            flow={"flow_id": "main"},
        )
        
        assert context_stage4.stage_name == "stage4"
        assert context_stage4.spans == ("span1", "span2")
        assert context_stage4.flow == {"flow_id": "main"}
        assert context_stage4.steps == ()
        
        # Stage 7 context with steps only
        context_stage7 = IRSCheckContext(
            stage_name="stage7",
            steps=("step1", "step2", "step3"),
        )
        
        assert context_stage7.stage_name == "stage7"
        assert context_stage7.steps == ("step1", "step2", "step3")
        assert context_stage7.flow is None
    
    def test_context_metadata_default_is_isolated(self):
        """Verify metadata defaults don't share mutable state."""
        context1 = IRSCheckContext(stage_name="stage1")
        context2 = IRSCheckContext(stage_name="stage2")
        
        # Modifying context1 metadata should not affect context2
        # Note: frozen=True prevents direct assignment, but we can verify
        # that the default factory creates independent dicts
        assert context1.metadata == {}
        assert context2.metadata == {}
        assert context1.metadata is not context2.metadata
    
    def test_context_does_not_infer_constructs_at_construction(self):
        """Verify context construction doesn't infer or create constructs."""
        # Context with various IR artifacts
        context = IRSCheckContext(
            stage_name="stage7",
            spans=("span1", "span2"),
            steps=("step1", "step2"),
            metadata={"test": "value"},
        )
        
        # Context should just store what was given, no inference
        assert len(context.steps) == 2
        assert context.steps[0] == "step1"
        assert context.metadata == {"test": "value"}
        # No hidden construct extraction or analysis


# ===========================================================================
# 7.2 ConstructInstance Tests
# ===========================================================================


class TestR2ConstructInstance:
    """Test ConstructInstance representation."""
    
    def test_instance_defaults_represent_materialized_source_demanded_construct(self):
        """Verify default instance represents normal materialized construct."""
        instance = ConstructInstance(
            construct_id="step_1",
            construct_type="GENERAL_COMMAND",
        )
        
        assert instance.construct_id == "step_1"
        assert instance.construct_type == "GENERAL_COMMAND"
        assert instance.materialized is True
        assert instance.source_demanded is True
        assert instance.candidate_only is False
        assert instance.ir_ref is None
    
    def test_instance_can_represent_candidate_only_source_demand(self):
        """Verify instance can represent promotion candidates."""
        # Worker promotion candidate
        candidate = ConstructInstance(
            construct_id="worker_candidate_1",
            construct_type="WORKER_CANDIDATE",
            materialized=False,
            source_demanded=True,
            candidate_only=True,
            source_span_ids=["s10", "s11"],
        )
        
        assert candidate.materialized is False
        assert candidate.source_demanded is True
        assert candidate.candidate_only is True
        assert candidate.source_span_ids == ["s10", "s11"]
    
    def test_instance_mutable_defaults_are_isolated(self):
        """Verify mutable field defaults don't share state."""
        instance1 = ConstructInstance(
            construct_id="inst1",
            construct_type="TEST",
        )
        instance2 = ConstructInstance(
            construct_id="inst2",
            construct_type="TEST",
        )
        
        # Modify instance1 lists
        instance1.child_construct_ids.append("child1")
        instance1.related_edges.append(
            ConstructEdge(from_id="a", to_id="b", edge_type="contains")
        )
        instance1.source_span_ids.append("s1")
        instance1.metadata["key"] = "value"
        
        # instance2 should be unaffected
        assert instance2.child_construct_ids == []
        assert instance2.related_edges == []
        assert instance2.source_span_ids == []
        assert instance2.metadata == {}
    
    def test_instance_preserves_parent_path_source_and_edges(self):
        """Verify instance can store parent, path, source, and edges."""
        edge = ConstructEdge(
            from_id="worker_main",
            to_id="step_1",
            edge_type="contains",
        )
        
        instance = ConstructInstance(
            construct_id="step_1",
            construct_type="GENERAL_COMMAND",
            ir_ref={"step_id": "st_1"},
            primary_parent_id="worker_main",
            child_construct_ids=["substep_1"],
            related_edges=[edge],
            construct_path=("worker_main", "step_1"),
            source_span_ids=["s1", "s2"],
            source_section_id="section_1",
            source_packet_id="packet_1",
            metadata={"confidence": 0.9},
        )
        
        assert instance.primary_parent_id == "worker_main"
        assert instance.child_construct_ids == ["substep_1"]
        assert len(instance.related_edges) == 1
        assert instance.related_edges[0].edge_type == "contains"
        assert instance.construct_path == ("worker_main", "step_1")
        assert instance.source_span_ids == ["s1", "s2"]
        assert instance.source_section_id == "section_1"
        assert instance.source_packet_id == "packet_1"
        assert instance.metadata == {"confidence": 0.9}


# ===========================================================================
# 7.3 IRSChecker Protocol Tests
# ===========================================================================


class TestR2IRSCheckerProtocol:
    """Test IRSChecker protocol compliance."""
    
    def test_fake_checker_satisfies_protocol_shape(self):
        """Verify FakeChecker satisfies IRSChecker protocol."""
        checker = FakeChecker()
        
        # Protocol attributes
        assert checker.checker_id == "fake_checker"
        assert checker.supported_construct_types == ("GENERAL_COMMAND",)
        assert checker.supported_stages == ("stage_fake",)
        
        # Protocol methods
        assert callable(checker.extract_instances)
        assert callable(checker.check_instance)
        
        # Can be used as IRSChecker
        context = IRSCheckContext(stage_name="stage_fake", steps=("step1",))
        instances = checker.extract_instances(context)
        assert isinstance(instances, list)
    
    def test_checker_contract_docstring_mentions_no_llm_no_ir_mutation_no_construct_generation(self):
        """Verify IRSChecker protocol documents contract constraints."""
        # Check that IRSChecker.__doc__ contains key contract terms
        from nl2spl.compiler.irs.checker import IRSChecker
        
        doc = IRSChecker.__doc__ or ""
        
        # Key contract terms that should be documented
        assert "MUST NOT call LLM" in doc or "LLM" in doc
        assert "MUST NOT modify" in doc or "modify" in doc
        assert "MUST NOT generate" in doc or "generate" in doc


# ===========================================================================
# 7.4 IRSCheckerRegistry Tests
# ===========================================================================


class TestR2IRSCheckerRegistry:
    """Test IRSCheckerRegistry registration and lookup."""
    
    def test_registry_empty_queries_return_empty_lists(self):
        """Verify empty registry returns empty lists for all queries."""
        registry = IRSCheckerRegistry()
        
        assert registry.get_for_stage("stage4") == []
        assert registry.get_for_construct_type("GENERAL_COMMAND") == []
        assert registry.get_for_stage_and_construct_type("stage4", "GENERAL_COMMAND") == []
    
    def test_registry_register_and_query_by_stage(self):
        """Verify registry can register and query by stage."""
        registry = IRSCheckerRegistry()
        checker = FakeChecker()
        
        registry.register(checker)
        
        # Query by supported stage
        result = registry.get_for_stage("stage_fake")
        assert len(result) == 1
        assert result[0].checker_id == "fake_checker"
        
        # Query by unsupported stage
        assert registry.get_for_stage("stage4") == []
    
    def test_registry_register_and_query_by_construct_type(self):
        """Verify registry can query by construct type."""
        registry = IRSCheckerRegistry()
        checker = FakeChecker()
        
        registry.register(checker)
        
        # Query by supported construct type
        result = registry.get_for_construct_type("GENERAL_COMMAND")
        assert len(result) == 1
        assert result[0].checker_id == "fake_checker"
        
        # Query by unsupported construct type
        assert registry.get_for_construct_type("WORKER") == []
    
    def test_registry_query_by_stage_and_construct_type(self):
        """Verify registry can filter by both stage and construct type."""
        registry = IRSCheckerRegistry()
        checker1 = FakeChecker()
        checker2 = AnotherFakeChecker()
        
        registry.register(checker1)
        registry.register(checker2)
        
        # Both checkers support stage_fake
        result_stage = registry.get_for_stage("stage_fake")
        assert len(result_stage) == 2
        
        # Only checker1 supports GENERAL_COMMAND
        result_construct = registry.get_for_construct_type("GENERAL_COMMAND")
        assert len(result_construct) == 1
        assert result_construct[0].checker_id == "fake_checker"
        
        # Combined filter: stage_fake + GENERAL_COMMAND
        result_both = registry.get_for_stage_and_construct_type("stage_fake", "GENERAL_COMMAND")
        assert len(result_both) == 1
        assert result_both[0].checker_id == "fake_checker"
        
        # Combined filter: stage8 + WORKER
        result_both2 = registry.get_for_stage_and_construct_type("stage8", "WORKER")
        assert len(result_both2) == 1
        assert result_both2[0].checker_id == "another_fake_checker"
        
        # Combined filter: no match
        result_none = registry.get_for_stage_and_construct_type("stage4", "WORKER")
        assert result_none == []
    
    def test_registry_rejects_duplicate_checker_id(self):
        """Verify registry rejects duplicate checker_id."""
        registry = IRSCheckerRegistry()
        checker1 = FakeChecker()
        checker2 = FakeChecker()  # Same checker_id
        
        registry.register(checker1)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(checker2)
    
    def test_registry_preserves_registration_order(self):
        """Verify registry returns checkers in registration order."""
        registry = IRSCheckerRegistry()
        checker1 = FakeChecker()
        checker2 = AnotherFakeChecker()
        
        # Register in specific order
        registry.register(checker1)
        registry.register(checker2)
        
        # Query should preserve order
        result = registry.get_for_stage("stage_fake")
        assert len(result) == 2
        assert result[0].checker_id == "fake_checker"
        assert result[1].checker_id == "another_fake_checker"


# ===========================================================================
# 7.5 DiagnosticProjector Skeleton Tests
# ===========================================================================


class TestR2DiagnosticProjectorSkeleton:
    """Test DiagnosticProjector skeleton (R2 does not implement R3 semantics)."""
    
    def test_projector_type_contract_is_enforced(self):
        """Verify DiagnosticProjectionResult uses real type annotations."""
        type_hints = typing.get_type_hints(DiagnosticProjectionResult)
        
        # Verify diagnostics binds to list[CompileDiagnostic]
        diagnostics_type = type_hints["diagnostics"]
        assert hasattr(diagnostics_type, "__origin__")
        assert diagnostics_type.__origin__ is list
        from nl2spl.ir.diagnostics import CompileDiagnostic
        assert diagnostics_type.__args__[0] is CompileDiagnostic
        
        # Verify warnings binds to list[str]
        warnings_type = type_hints["warnings"]
        assert hasattr(warnings_type, "__origin__")
        assert warnings_type.__origin__ is list
        assert warnings_type.__args__[0] is str
    
    def test_projector_empty_reports_returns_empty_result(self):
        """Verify projector returns empty result for empty reports."""
        projector = DiagnosticProjector()
        context = IRSCheckContext(stage_name="stage4")
        
        result = projector.project([], context)
        
        assert isinstance(result, DiagnosticProjectionResult)
        assert result.diagnostics == []
        assert result.warnings == []
    
    def test_projector_non_empty_reports_still_does_not_emit_diagnostics_in_r2(self):
        """Verify R2 projector skeleton does not generate diagnostics."""
        projector = DiagnosticProjector()
        context = IRSCheckContext(stage_name="stage4")
        
        # Create reports with diagnostic slots
        reports = [
            ConstructSatisfactionReport(
                construct_id="step_1",
                construct_type="GENERAL_COMMAND",
                slots=[
                    SlotSatisfaction(
                        slot_name="command",
                        status="missing",
                        diagnostic_kind="missing_required_slot",
                    )
                ],
                completeness="partial",
                renderable=False,
            )
        ]
        
        result = projector.project(reports, context)
        
        # R2 skeleton does not implement projection
        assert result.diagnostics == []
        assert result.warnings == []
    
    def test_projector_does_not_mutate_reports(self):
        """Verify projector does not modify input reports."""
        projector = DiagnosticProjector()
        context = IRSCheckContext(stage_name="stage4")
        
        original_report = ConstructSatisfactionReport(
            construct_id="step_1",
            construct_type="GENERAL_COMMAND",
            slots=[],
            completeness="complete",
            renderable=True,
        )
        
        reports = [original_report]
        
        projector.project(reports, context)
        
        # Report should be unchanged
        assert original_report.construct_id == "step_1"
        assert original_report.completeness == "complete"
        assert len(reports) == 1


# ===========================================================================
# 7.6 IRSRunner Tests
# ===========================================================================


class TestR2IRSRunner:
    """Test IRSRunner orchestration."""
    
    def test_runner_result_type_contract_is_enforced(self):
        """Verify IRSRunResult uses real type annotations."""
        type_hints = typing.get_type_hints(IRSRunResult)
        
        # Verify reports binds to list[ConstructSatisfactionReport]
        reports_type = type_hints["reports"]
        assert hasattr(reports_type, "__origin__")
        assert reports_type.__origin__ is list
        assert reports_type.__args__[0] is ConstructSatisfactionReport
        
        # Verify diagnostics binds to list[CompileDiagnostic]
        diagnostics_type = type_hints["diagnostics"]
        assert hasattr(diagnostics_type, "__origin__")
        assert diagnostics_type.__origin__ is list
        from nl2spl.ir.diagnostics import CompileDiagnostic
        assert diagnostics_type.__args__[0] is CompileDiagnostic
        
        # Verify warnings binds to list[str]
        warnings_type = type_hints["warnings"]
        assert hasattr(warnings_type, "__origin__")
        assert warnings_type.__origin__ is list
        assert warnings_type.__args__[0] is str
    
    def test_runner_empty_registry_returns_empty_result(self):
        """Verify runner with empty registry returns empty result."""
        runner = IRSRunner(registry=None)
        context = IRSCheckContext(stage_name="stage4")
        
        result = runner.run_stage("stage4", context)
        
        assert isinstance(result, IRSRunResult)
        assert result.reports == []
        assert result.diagnostics == []
        assert result.warnings == []
    
    def test_runner_invokes_registered_checker_for_stage(self):
        """Verify runner invokes checker when stage matches."""
        registry = IRSCheckerRegistry()
        checker = FakeChecker()
        registry.register(checker)
        
        construct_registry = SPLConstructRegistry()
        construct_registry.register(
            ConstructIRS(
                construct_type="GENERAL_COMMAND",
                existence_policy="source_signal_required",
                source_signals=["command_text"],
                slots=[
                    SlotSpec(slot_name="command", syntax_required=True)
                ],
            )
        )
        
        runner = IRSRunner(
            registry=registry,
            construct_registry=construct_registry,
        )
        
        context = IRSCheckContext(
            stage_name="stage_fake",
            steps=("step1", "step2"),
        )
        
        result = runner.run_stage("stage_fake", context)
        
        # Should have 2 reports (one per step)
        assert len(result.reports) == 2
        assert result.reports[0].construct_id == "step_0"
        assert result.reports[1].construct_id == "step_1"
        assert all(r.completeness == "complete" for r in result.reports)
    
    def test_runner_filters_checker_by_stage(self):
        """Verify runner only invokes checkers for matching stage."""
        registry = IRSCheckerRegistry()
        checker = FakeChecker()  # Only supports stage_fake
        registry.register(checker)
        
        construct_registry = SPLConstructRegistry()
        
        runner = IRSRunner(
            registry=registry,
            construct_registry=construct_registry,
        )
        
        # Query with non-matching stage
        context = IRSCheckContext(stage_name="stage4", steps=("step1",))
        result = runner.run_stage("stage4", context)
        
        # No checkers should run
        assert result.reports == []
    
    def test_runner_uses_construct_registry_to_fetch_irs(self):
        """Verify runner fetches ConstructIRS from construct registry."""
        registry = IRSCheckerRegistry()
        checker = FakeChecker()
        registry.register(checker)
        
        construct_registry = SPLConstructRegistry()
        test_irs = ConstructIRS(
            construct_type="GENERAL_COMMAND",
            existence_policy="source_signal_required",
            source_signals=["command_text"],
            slots=[SlotSpec(slot_name="command")],
        )
        construct_registry.register(test_irs)
        
        runner = IRSRunner(
            registry=registry,
            construct_registry=construct_registry,
        )
        
        context = IRSCheckContext(stage_name="stage_fake", steps=("step1",))
        result = runner.run_stage("stage_fake", context)
        
        # Checker should have been called with the IRS
        assert len(result.reports) == 1
        assert result.reports[0].construct_type == "GENERAL_COMMAND"
    
    def test_runner_warns_and_skips_unknown_construct_type(self):
        """Verify runner skips instances with unknown construct types."""
        registry = IRSCheckerRegistry()
        checker = FakeChecker()
        registry.register(checker)
        
        # Empty construct registry - GENERAL_COMMAND not registered
        construct_registry = SPLConstructRegistry()
        
        runner = IRSRunner(
            registry=registry,
            construct_registry=construct_registry,
        )
        
        context = IRSCheckContext(stage_name="stage_fake", steps=("step1",))
        result = runner.run_stage("stage_fake", context)
        
        # No reports generated
        assert result.reports == []
        # Warning about unknown construct type
        assert len(result.warnings) == 1
        assert "Unknown construct type" in result.warnings[0]
        assert "GENERAL_COMMAND" in result.warnings[0]
    
    def test_runner_calls_projector_after_collecting_reports(self):
        """Verify runner calls projector with collected reports and context."""
        registry = IRSCheckerRegistry()
        checker = FakeChecker()
        registry.register(checker)
        
        construct_registry = SPLConstructRegistry()
        construct_registry.register(
            ConstructIRS(
                construct_type="GENERAL_COMMAND",
                existence_policy="source_signal_required",
                source_signals=["command_text"],
                slots=[SlotSpec(slot_name="command")],
            )
        )
        
        recording_projector = RecordingProjector()
        
        runner = IRSRunner(
            registry=registry,
            construct_registry=construct_registry,
            projector=recording_projector,
        )
        
        context = IRSCheckContext(stage_name="stage_fake", steps=("step1",))
        result = runner.run_stage("stage_fake", context)
        
        # Reports collected
        assert len(result.reports) == 1
        
        # Projector was called exactly once
        assert recording_projector.call_count == 1
        
        # Projector received the correct reports
        assert len(recording_projector.received_reports) == 1
        assert len(recording_projector.received_reports[0]) == 1
        assert recording_projector.received_reports[0][0].construct_id == "step_0"
        
        # Projector received the same context
        assert len(recording_projector.received_contexts) == 1
        assert recording_projector.received_contexts[0] is context
        
        # Projector's warning was merged into result
        assert "projector_was_called" in result.warnings
        
        # R2 skeleton returns empty diagnostics
        assert result.diagnostics == []


# ===========================================================================
# 7.7 Compatibility Tests
# ===========================================================================


class TestR2Compatibility:
    """Test R2 compatibility with R0/R1 and existing checkers."""
    
    def test_no_circular_import_from_top_level_exports(self):
        """Verify top-level imports don't trigger circular dependency."""
        # This test verifies that lazy import in irs/__init__.py works
        # Import order that would previously cause circular dependency:
        # 1. construct_registry imports irs.frontier
        # 2. irs.__init__ would eagerly import checker/projector/runner
        # 3. Those modules import construct_registry -> circular
        
        # With lazy __getattr__, this should work:
        from nl2spl.compiler.construct_registry import ConstructSatisfactionReport
        from nl2spl.compiler.irs import (
            DiagnosticProjector,
            IRSChecker,
            IRSRunner,
        )
        
        # Verify types are accessible
        assert ConstructSatisfactionReport is not None
        assert IRSRunner is not None
        assert DiagnosticProjector is not None
        assert IRSChecker is not None
    
    def test_r0_r1_public_imports_still_work(self):
        """Verify R1 graph/frontier imports remain accessible."""
        from nl2spl.compiler.irs import (
            ConstructEdge,
            ConstructEdgeType,
            ConstructGraph,
            CutlineReason,
            FrontierStatus,
        )
        
        # Can create R1 types
        edge = ConstructEdge(from_id="a", to_id="b", edge_type="contains")
        assert edge.edge_type == "contains"
        
        graph = ConstructGraph(nodes=["a", "b"], edges=[edge])
        assert len(graph.nodes) == 2
        
        # Frontier types are accessible
        status: FrontierStatus = "leaf"
        reason: CutlineReason = "promotion_blocked"
        assert status == "leaf"
        assert reason == "promotion_blocked"
    
    def test_existing_stage4_stage7_checkers_not_required_to_use_runner(self):
        """Verify old checkers can still work without v6 runner."""
        # Import old checker functions
        from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
        from nl2spl.pipeline.stages.stage4_flow_assembler.irs_checker import (
            check_exception_flows_irs,
        )
        
        # Old checker still works
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Error",
                    spans=["s2"],
                )
            ],
        )
        
        reports, diagnostics = check_exception_flows_irs(flow)
        
        # Old checker returns results without using v6 runner
        assert len(reports) == 1
        assert reports[0].construct_type == "EXCEPTION_FLOW"


# ===========================================================================
# R2 Metadata - Implementation notes
# ===========================================================================

# R2 Framework Skeleton completion criteria:
# 1. IRSCheckContext defined and importable
# 2. ConstructInstance defined with materialized/source_demanded/candidate_only
# 3. IRSChecker Protocol defined with extract_instances/check_instance
# 4. IRSCheckerRegistry supports register/query/duplicate rejection/order preservation
# 5. IRSRunner supports empty registry, fake checker dispatch, unknown construct warning
# 6. DiagnosticProjector skeleton importable, callable, R2 does not generate diagnostics
# 7. nl2spl.compiler.irs exports all R2 types
# 8. No orchestrator integration
# 9. No old checker migration
# 10. No Worker/Delegation checker
# 11. No LLM or rule-based semantic logic
# 12. R0/R1 baseline tests pass
# 13. R2 framework tests pass
# 14. Full unit tests pass
