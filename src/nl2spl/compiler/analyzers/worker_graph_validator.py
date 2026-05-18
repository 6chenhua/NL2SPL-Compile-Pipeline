"""Worker graph validator — protocol, minimal MVP implementation, and
future implementations.

§7.5: MVP only validates single-level accepted handoffs.  Complex
multi-worker cycle/orphan/unused detection is deferred.  The Protocol
satisfies the §9.1 interface-reservation requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from nl2spl.ir.diagnostics import CompileDiagnostic

if TYPE_CHECKING:
    from nl2spl.ir.worker_ir import WorkerIR
    from nl2spl.ir.worker_plan_ir import WorkerPlanIR


@dataclass
class WorkerGraphValidationContext:
    """Immutable input context for a worker graph validator."""

    pass


class WorkerGraphValidator(Protocol):
    """Validates multi-worker call graph consistency.

    Implementations MUST NOT mutate IR inputs.
    """

    def validate(
        self,
        worker_plan: WorkerPlanIR,
        worker_ir: WorkerIR,
        context: WorkerGraphValidationContext,
    ) -> list[CompileDiagnostic]:
        ...


class MinimalWorkerGraphValidator:
    """MVP implementation — returns empty list.

    Future phases may add single-level handoff existence checks.
    """

    def validate(
        self,
        worker_plan: WorkerPlanIR,
        worker_ir: WorkerIR,
        context: WorkerGraphValidationContext,
    ) -> list[CompileDiagnostic]:
        return []
