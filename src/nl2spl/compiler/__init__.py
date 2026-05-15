"""Compiler package — public result types, analysis, and report generation.

All public types are reachable from ``nl2spl.compiler`` so callers
do not need to import from ``nl2spl.ir.diagnostics`` directly.
"""

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
from nl2spl.compiler.diagnostic_analyzer import AnalyzeInput, DiagnosticAnalyzer
from nl2spl.compiler.producer_index import ProducerIndex, ProducerRef
from nl2spl.compiler.report_renderer import render_report
from nl2spl.ir.diagnostics import CompileDiagnostic, StepRenderInfo, TraceRecord
from nl2spl.pipeline.provenance import ProvenanceAggregator

__all__ = [
    "AnalyzeInput",
    "AssumptionBuilder",
    "CompileAssumption",
    "CompileDiagnostic",
    "CompileResult",
    "Completeness",
    "compute_completeness",
    "DiagnosticAnalyzer",
    "DiagnosticKind",
    "MissingSlot",
    "ProducerIndex",
    "ProducerRef",
    "ProvenanceAggregator",
    "render_report",
    "Severity",
    "StepRenderInfo",
    "TraceRecord",
    "TraceRelation",
]
