"""IRS v6 Diagnostic Projector — project ConstructSatisfactionReport to CompileDiagnostic.

R2 provides only a skeleton. Full projection semantics (slot -> diagnostic mapping,
severity rules, deduplication) belong to R3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.compiler.construct_registry import ConstructSatisfactionReport
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.ir.diagnostics import CompileDiagnostic


@dataclass
class DiagnosticProjectionResult:
    """Result of projecting IRS reports to compile diagnostics.
    
    Attributes:
        diagnostics: Projected compile diagnostics
        warnings: Non-fatal warnings during projection
    """
    
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DiagnosticProjector:
    """Projects ConstructSatisfactionReport to CompileDiagnostic.
    
    R2 skeleton behavior:
        - Can be instantiated and called
        - Empty reports return empty diagnostics
        - Non-empty reports do NOT generate diagnostics in R2
        - Does not modify input reports
    
    R3 will implement:
        - Slot diagnostic_kind -> CompileDiagnostic.kind mapping
        - Severity rules based on completeness/renderable
        - Source span propagation
        - Deduplication across reports
        - Construct path formatting for messages
    
    Design notes:
        - Projector is stateless, can be reused across runs
        - Context provides additional info for diagnostic formatting
        - Warnings capture projection issues without failing the run
    """
    
    def project(
        self,
        reports: list[ConstructSatisfactionReport],
        context: IRSCheckContext,
    ) -> DiagnosticProjectionResult:
        """Project IRS reports to compile diagnostics.
        
        Args:
            reports: Construct satisfaction reports from checkers
            context: Pipeline context for additional diagnostic info
        
        Returns:
            Projection result with diagnostics and warnings
        
        Notes:
            - R2 skeleton returns empty diagnostics
            - Does not modify reports
            - R3 will implement full projection semantics
        """
        # R2 skeleton: safe empty projection
        # R3 will implement slot -> diagnostic mapping
        return DiagnosticProjectionResult()
