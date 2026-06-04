"""IRS v6 runner factory.

This module provides factory functions to build IRSRunner instances
with appropriate checker registrations based on feature flags.

The factory isolates concrete checker imports from the orchestrator,
maintaining clean separation of concerns.
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checker import IRSChecker
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.compiler.irs.registry import IRSCheckerRegistry
from nl2spl.compiler.irs.runner import IRSRunner


def build_irs_checker_registry(
    *,
    enable_worker_delegation: bool = False,
    enable_exception_flow: bool = False,
    enable_step: bool = False,
) -> IRSCheckerRegistry:
    """Build an IRS checker registry with optional checker registrations.

    Args:
        enable_worker_delegation: If True, register WorkerDelegationIRSChecker
        enable_exception_flow: If True, register Stage4ExceptionFlowIRSChecker
        enable_step: If True, register Stage7StepIRSChecker

    Returns:
        IRSCheckerRegistry with requested checkers registered
    """
    registry = IRSCheckerRegistry()

    if enable_worker_delegation:
        # Import concrete checker only when needed
        from nl2spl.compiler.irs.checkers.worker_delegation import (
            WorkerDelegationIRSChecker,
        )

        checker: IRSChecker = WorkerDelegationIRSChecker()
        registry.register(checker)

    if enable_exception_flow:
        from nl2spl.compiler.irs.checkers.exception_flow import (
            Stage4ExceptionFlowIRSChecker,
        )

        registry.register(Stage4ExceptionFlowIRSChecker())

    if enable_step:
        from nl2spl.compiler.irs.checkers.step import Stage7StepIRSChecker

        registry.register(Stage7StepIRSChecker())

    return registry


def build_irs_runner(
    *,
    enable_worker_delegation: bool = False,
    enable_exception_flow: bool = False,
    enable_step: bool = False,
    construct_registry: SPLConstructRegistry | None = None,
) -> IRSRunner:
    """Build an IRS runner with appropriate checker registrations.

    Args:
        enable_worker_delegation: If True, register WorkerDelegationIRSChecker
        enable_exception_flow: If True, register Stage4ExceptionFlowIRSChecker
        enable_step: If True, register Stage7StepIRSChecker
        construct_registry: Optional construct registry to use.  When None,
            uses SPLConstructRegistry.default().

    Returns:
        IRSRunner configured with requested checkers
    """
    checker_registry = build_irs_checker_registry(
        enable_worker_delegation=enable_worker_delegation,
        enable_exception_flow=enable_exception_flow,
        enable_step=enable_step,
    )
    if construct_registry is None:
        construct_registry = SPLConstructRegistry.default()
    projector = DiagnosticProjector()

    return IRSRunner(
        registry=checker_registry,
        construct_registry=construct_registry,
        projector=projector,
    )
