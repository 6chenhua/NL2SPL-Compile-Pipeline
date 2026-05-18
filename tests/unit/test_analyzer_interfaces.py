"""Phase 1: verify analyzer Protocol + no-op/minimal imports and behaviour."""

from __future__ import annotations

from nl2spl.compiler.analyzers import (
    DataFlowAnalysisContext,
    DataFlowAnalyzer,
    MinimalWorkerGraphValidator,
    NoOpDataFlowAnalyzer,
    NoOpRequirementRedundancyAnalyzer,
    NoOpSemanticConflictAnalyzer,
    RedundancyAnalysisContext,
    RequirementRedundancyAnalyzer,
    SemanticConflictAnalyzer,
    WorkerGraphValidationContext,
    WorkerGraphValidator,
)
from nl2spl.compiler.analyzers.dataflow import DataFlowAnalyzer as DFAlias

# =========================================================================
# Imports
# =========================================================================


class TestImports:
    """Every Phase 1 interface must be importable."""

    def test_dataflow_imports(self) -> None:
        assert DFAlias is DataFlowAnalyzer
        assert DataFlowAnalysisContext is not None
        assert NoOpDataFlowAnalyzer is not None

    def test_redundancy_imports(self) -> None:
        assert RequirementRedundancyAnalyzer is not None
        assert RedundancyAnalysisContext is not None
        assert NoOpRequirementRedundancyAnalyzer is not None

    def test_worker_graph_imports(self) -> None:
        assert WorkerGraphValidator is not None
        assert WorkerGraphValidationContext is not None
        assert MinimalWorkerGraphValidator is not None

    def test_existing_exports_preserved(self) -> None:
        assert SemanticConflictAnalyzer is not None
        assert NoOpSemanticConflictAnalyzer is not None


# =========================================================================
# DataFlow
# =========================================================================


class TestNoOpDataFlowAnalyzer:
    def test_returns_empty_list(self) -> None:
        analyzer = NoOpDataFlowAnalyzer()
        ctx = DataFlowAnalysisContext()
        result = analyzer.analyze([], None, None, ctx)
        assert result == []


# =========================================================================
# Redundancy
# =========================================================================


class TestNoOpRequirementRedundancyAnalyzer:
    def test_returns_empty_list(self) -> None:
        analyzer = NoOpRequirementRedundancyAnalyzer()
        ctx = RedundancyAnalysisContext()
        result = analyzer.analyze([], [], [], ctx)
        assert result == []


# =========================================================================
# Worker graph
# =========================================================================


class TestMinimalWorkerGraphValidator:
    def test_returns_empty_list(self) -> None:
        validator = MinimalWorkerGraphValidator()
        ctx = WorkerGraphValidationContext()
        result = validator.validate(None, None, ctx)
        assert result == []


# =========================================================================
# Protocol conformance
# =========================================================================


class TestProtocolConformance:
    """NoOp / Minimal classes structurally conform to their Protocols."""

    def test_noop_dataflow_conforms(self) -> None:
        analyzer: DataFlowAnalyzer = NoOpDataFlowAnalyzer()
        result = analyzer.analyze([], None, None, DataFlowAnalysisContext())
        assert result == []

    def test_noop_redundancy_conforms(self) -> None:
        analyzer: RequirementRedundancyAnalyzer = NoOpRequirementRedundancyAnalyzer()
        result = analyzer.analyze([], [], [], RedundancyAnalysisContext())
        assert result == []

    def test_minimal_worker_graph_conforms(self) -> None:
        validator: WorkerGraphValidator = MinimalWorkerGraphValidator()
        result = validator.validate(None, None, WorkerGraphValidationContext())
        assert result == []
