"""Compiler package — public result types, analysis, and report generation.

All public types are reachable from ``nl2spl.compiler`` so callers
do not need to import from ``nl2spl.ir.diagnostics`` directly.
"""

from nl2spl.compiler.analyzers import (
    ConflictAnalysisContext,
    LLMConflictDiagnosticVerifier,
    LLMSemanticConflictAnalyzer,
    NoOpSemanticConflictAnalyzer,
    SemanticConflictAnalyzer,
)
from nl2spl.compiler.assumptions import AssumptionBuilder
from nl2spl.compiler.compile_result import (
    CompileAssumption,
    CompileResult,
    Completeness,
    DiagnosticKind,
    MissingSlot,
    Severity,
    TraceRelation,
)
from nl2spl.compiler.completeness import compute_completeness
from nl2spl.compiler.constructs import (
    ConstructIRS,
    ConstructSatisfactionReport,
    SlotSatisfaction,
    SlotSpec,
    SPLConstructRegistry,
)
from nl2spl.compiler.diagnostics import DiagnosticRegistry, DiagnosticSpec
from nl2spl.compiler.feedback_report_renderer import render_feedback_report
from nl2spl.compiler.irs_prompt_builder import IRSDrivenPromptBuilder
from nl2spl.compiler.producer_index import ProducerIndex, ProducerRef
from nl2spl.compiler.reporting import render_report
from nl2spl.ir.diagnostics import CompileDiagnostic, StepRenderInfo, TraceRecord
from nl2spl.pipeline.provenance import ProvenanceAggregator

__all__ = [
    "AssumptionBuilder",
    "ConflictAnalysisContext",
    "CompileAssumption",
    "CompileDiagnostic",
    "CompileResult",
    "Completeness",
    "compute_completeness",
    "ConstructIRS",
    "ConstructSatisfactionReport",
    "DiagnosticKind",
    "DiagnosticRegistry",
    "DiagnosticSpec",
    "IRSDrivenPromptBuilder",
    "LLMConflictDiagnosticVerifier",
    "LLMSemanticConflictAnalyzer",
    "MissingSlot",
    "NoOpSemanticConflictAnalyzer",
    "ProducerIndex",
    "ProducerRef",
    "ProvenanceAggregator",
    "render_feedback_report",
    "render_report",
    "SemanticConflictAnalyzer",
    "Severity",
    "SlotSatisfaction",
    "SlotSpec",
    "SPLConstructRegistry",
    "StepRenderInfo",
    "TraceRecord",
    "TraceRelation",
]
