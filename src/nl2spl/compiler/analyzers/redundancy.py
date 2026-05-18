"""Requirement redundancy analyzer — protocol, NoOp, and future
implementations.

§7.4: MVP does not implement complex duplicate detection.  The Protocol
and NoOp placeholder satisfy the §9.1 interface-reservation requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from nl2spl.ir.diagnostics import CompileDiagnostic

if TYPE_CHECKING:
    from nl2spl.ir.constraint_ir import ConstraintIR
    from nl2spl.ir.span_ir import SpanIR
    from nl2spl.ir.step_ir import StepIR


@dataclass
class RedundancyAnalysisContext:
    """Immutable input context for a redundancy analyzer."""

    pass


class RequirementRedundancyAnalyzer(Protocol):
    """Detects duplicate or near-duplicate requirements across spans.

    Implementations MUST NOT mutate IR inputs.
    """

    def analyze(
        self,
        spans: list[SpanIR],
        constraints: list[ConstraintIR],
        steps: list[StepIR],
        context: RedundancyAnalysisContext,
    ) -> list[CompileDiagnostic]:
        ...


class NoOpRequirementRedundancyAnalyzer:
    """Default no-op — returns empty list, no side effects."""

    def analyze(
        self,
        spans: list[SpanIR],
        constraints: list[ConstraintIR],
        steps: list[StepIR],
        context: RedundancyAnalysisContext,
    ) -> list[CompileDiagnostic]:
        return []
