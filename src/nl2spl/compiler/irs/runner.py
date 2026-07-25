"""IRS v6 Runner — orchestrates checker execution and diagnostic projection.

IRSRunner coordinates the IRS checking workflow:
1. Find checkers for stage
2. Extract construct instances
3. Check each instance against its IRS
4. Project reports to diagnostics
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.compiler.constructs import (
    ConstructSatisfactionReport,
    SPLConstructRegistry,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.compiler.irs.registry import IRSCheckerRegistry
from nl2spl.ir.diagnostics import CompileDiagnostic


@dataclass
class IRSRunResult:
    """Result of running IRS checks for a stage.

    Attributes:
        reports: Construct satisfaction reports from checkers
        diagnostics: Projected compile diagnostics
        warnings: Non-fatal warnings during checking or projection
    """

    reports: list[ConstructSatisfactionReport] = field(default_factory=list)
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class IRSRunner:
    """Runs IRS checks for a pipeline stage.

    Workflow:
        1. Query registry for checkers supporting the stage
        2. For each checker, extract construct instances from context
        3. For each instance, get ConstructIRS from construct registry
        4. If construct type not registered, skip with warning
        5. Call checker.check_instance(instance, irs, context)
        6. Collect all reports
        7. Project reports to diagnostics via projector
        8. Return IRSRunResult

    Design notes:
        - Empty registry returns empty result, no error
        - Unknown construct types are skipped with warning, not error
        - Runner itself does not write orchestrator state; orchestrator
          calls it through stage-local integration helpers (e.g.
          _run_stage3_5_irs_v6 in PipelineOrchestrator)
        - Projector is optional; if None, diagnostics will be empty
    """

    def __init__(
        self,
        registry: IRSCheckerRegistry | None = None,
        construct_registry: SPLConstructRegistry | None = None,
        projector: DiagnosticProjector | None = None,
    ) -> None:
        """Initialize runner with registries and projector.

        Args:
            registry: Checker registry (if None, no checkers will run)
            construct_registry: Construct IRS registry (if None, all instances skipped)
            projector: Diagnostic projector (if None, no diagnostics projected)
        """
        self._registry = registry
        self._construct_registry = construct_registry
        self._projector = projector

    def run_stage(
        self,
        stage_name: str,
        context: IRSCheckContext,
    ) -> IRSRunResult:
        """Run IRS checks for a pipeline stage.

        Args:
            stage_name: Pipeline stage identifier
            context: Read-only pipeline artifacts

        Returns:
            Run result with reports, diagnostics, and warnings

        Notes:
            - Empty registry returns empty result
            - Unknown construct types generate warnings
            - Does not modify context
        """
        reports: list[ConstructSatisfactionReport] = []
        warnings: list[str] = []

        # Empty registry case
        if self._registry is None:
            return IRSRunResult(reports=reports, diagnostics=[], warnings=warnings)

        # Get checkers for this stage
        checkers = self._registry.get_for_stage(stage_name)

        # Extract and check instances from each checker
        for checker in checkers:
            instances = checker.extract_instances(context)

            for instance in instances:
                # Get ConstructIRS for this construct type
                if self._construct_registry is None:
                    warnings.append(
                        f"No construct registry provided, skipping instance "
                        f"{instance.construct_id} ({instance.construct_type})"
                    )
                    continue

                if not self._construct_registry.has(instance.construct_type):
                    warnings.append(
                        f"Unknown construct type '{instance.construct_type}' "
                        f"for instance {instance.construct_id}, skipping"
                    )
                    continue

                irs = self._construct_registry.get(instance.construct_type)

                # Check instance
                report = checker.check_instance(instance, irs, context)
                reports.append(report)

        # Project reports to diagnostics
        diagnostics: list[CompileDiagnostic] = []
        if self._projector is not None:
            projection_result = self._projector.project(reports, context)
            diagnostics = projection_result.diagnostics
            warnings.extend(projection_result.warnings)

        return IRSRunResult(
            reports=reports,
            diagnostics=diagnostics,
            warnings=warnings,
        )
