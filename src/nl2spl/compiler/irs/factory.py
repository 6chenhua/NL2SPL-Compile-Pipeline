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
) -> IRSCheckerRegistry:
    """Build an IRS checker registry with optional checker registrations.

    Args:
        enable_worker_delegation: If True, register WorkerDelegationIRSChecker

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

    return registry


def build_irs_runner(
    *,
    enable_worker_delegation: bool = False,
) -> IRSRunner:
    """Build an IRS runner with appropriate checker registrations.

    Args:
        enable_worker_delegation: If True, register WorkerDelegationIRSChecker

    Returns:
        IRSRunner configured with requested checkers
    """
    checker_registry = build_irs_checker_registry(
        enable_worker_delegation=enable_worker_delegation,
    )
    construct_registry = SPLConstructRegistry.default()
    projector = DiagnosticProjector()

    return IRSRunner(
        registry=checker_registry,
        construct_registry=construct_registry,
        projector=projector,
    )
