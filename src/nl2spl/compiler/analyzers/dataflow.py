"""DataFlow analyzer — protocol, NoOp, and future implementations.

§7.3: MVP defers full UseDef analysis.  The Protocol and NoOp placeholder
satisfy the §9.1 interface-reservation requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from nl2spl.ir.diagnostics import CompileDiagnostic

if TYPE_CHECKING:
    from nl2spl.ir.step_ir import StepIR
    from nl2spl.ir.symbol_table import SymbolTable
    from nl2spl.ir.worker_plan_ir import WorkerPlanIR


@dataclass
class DataFlowAnalysisContext:
    """Immutable input context for a data-flow analyzer."""

    pass


class DataFlowAnalyzer(Protocol):
    """Detects use-before-def, dead variables, and data-flow inconsistencies.

    Implementations MUST NOT mutate IR inputs.
    """

    def analyze(
        self,
        steps: list[StepIR],
        symbols: SymbolTable,
        worker_plan: WorkerPlanIR | None,
        context: DataFlowAnalysisContext,
    ) -> list[CompileDiagnostic]:
        ...


class NoOpDataFlowAnalyzer:
    """Default no-op — returns empty list, no side effects."""

    def analyze(
        self,
        steps: list[StepIR],
        symbols: SymbolTable,
        worker_plan: WorkerPlanIR | None,
        context: DataFlowAnalysisContext,
    ) -> list[CompileDiagnostic]:
        return []
