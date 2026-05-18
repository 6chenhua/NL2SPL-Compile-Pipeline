"""Compiler analyzers -- pluggable analysis passes beyond core IRS checks."""

from nl2spl.compiler.analyzers.dataflow import (
    DataFlowAnalysisContext,
    DataFlowAnalyzer,
    NoOpDataFlowAnalyzer,
)
from nl2spl.compiler.analyzers.redundancy import (
    NoOpRequirementRedundancyAnalyzer,
    RedundancyAnalysisContext,
    RequirementRedundancyAnalyzer,
)
from nl2spl.compiler.analyzers.semantic_conflict import (
    ConflictAnalysisContext,
    LLMConflictDiagnosticVerifier,
    LLMSemanticConflictAnalyzer,
    NoOpSemanticConflictAnalyzer,
    SemanticConflictAnalyzer,
)
from nl2spl.compiler.analyzers.worker_graph_validator import (
    MinimalWorkerGraphValidator,
    WorkerGraphValidationContext,
    WorkerGraphValidator,
)

__all__ = [
    "ConflictAnalysisContext",
    "DataFlowAnalysisContext",
    "DataFlowAnalyzer",
    "LLMConflictDiagnosticVerifier",
    "LLMSemanticConflictAnalyzer",
    "MinimalWorkerGraphValidator",
    "NoOpDataFlowAnalyzer",
    "NoOpRequirementRedundancyAnalyzer",
    "NoOpSemanticConflictAnalyzer",
    "RedundancyAnalysisContext",
    "RequirementRedundancyAnalyzer",
    "SemanticConflictAnalyzer",
    "WorkerGraphValidationContext",
    "WorkerGraphValidator",
]
