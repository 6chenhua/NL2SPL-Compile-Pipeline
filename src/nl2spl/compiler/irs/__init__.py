"""IRS v6 — Information Requirements Satisfaction framework.

This package provides the v6 IRS type system and checking framework:

R1 types (schema foundation):
    - ConstructEdge, ConstructEdgeType, ConstructGraph
    - FrontierStatus, CutlineReason

R2 types (framework skeleton):
    - IRSCheckContext: Read-only input container
    - ConstructInstance: Construct representation for checking
    - IRSChecker: Pluggable checker protocol
    - IRSCheckerRegistry: Checker registration and lookup
    - IRSRunner, IRSRunResult: Checker orchestration
    - DiagnosticProjector, DiagnosticProjectionResult: Report projection
"""

from __future__ import annotations

# R1 types: no circular dependency, can be eagerly imported
from nl2spl.compiler.irs.frontier import CutlineReason, FrontierStatus
from nl2spl.compiler.irs.graph import ConstructEdge, ConstructEdgeType, ConstructGraph

# R2 types: lazy import to avoid circular dependency with construct_registry
# These will be imported on first access via __getattr__

__all__ = [
    # R1: Graph types
    "ConstructEdge",
    "ConstructEdgeType",
    "ConstructGraph",
    # R1: Frontier types
    "FrontierStatus",
    "CutlineReason",
    # R2: Context and instance
    "IRSCheckContext",
    "ConstructInstance",
    # R2: Checker protocol and registry
    "IRSChecker",
    "IRSCheckerRegistry",
    # R2: Runner
    "IRSRunner",
    "IRSRunResult",
    # R2: Projector
    "DiagnosticProjector",
    "DiagnosticProjectionResult",
]


def __getattr__(name: str):
    """Lazy import for R2 types to avoid circular dependency."""
    # R2 types that depend on construct_registry
    if name == "IRSCheckContext":
        from nl2spl.compiler.irs.context import IRSCheckContext
        return IRSCheckContext
    elif name == "ConstructInstance":
        from nl2spl.compiler.irs.instance import ConstructInstance
        return ConstructInstance
    elif name == "IRSChecker":
        from nl2spl.compiler.irs.checker import IRSChecker
        return IRSChecker
    elif name == "IRSCheckerRegistry":
        from nl2spl.compiler.irs.registry import IRSCheckerRegistry
        return IRSCheckerRegistry
    elif name == "IRSRunner":
        from nl2spl.compiler.irs.runner import IRSRunner
        return IRSRunner
    elif name == "IRSRunResult":
        from nl2spl.compiler.irs.runner import IRSRunResult
        return IRSRunResult
    elif name == "DiagnosticProjector":
        from nl2spl.compiler.irs.projector import DiagnosticProjector
        return DiagnosticProjector
    elif name == "DiagnosticProjectionResult":
        from nl2spl.compiler.irs.projector import DiagnosticProjectionResult
        return DiagnosticProjectionResult
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

