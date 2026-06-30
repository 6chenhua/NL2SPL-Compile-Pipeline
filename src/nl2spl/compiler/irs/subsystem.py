"""IRS Subsystem — unified entry point for IRS runtime operations.

IRSSubsystem composes IRSRunner, IRSCheckerRegistry, and DiagnosticProjector
into a single productized interface.  It exposes:

- ``run_stage_local()`` — stage-local construct satisfaction (Stage 3.5/4/7)
- ``run_post_normalize()`` — final construct-level diagnostics

Design constraints:
    - Subsystem does **only** orchestration — no semantic judgment.
    - ``run_post_normalize()`` uses the same IRSRunner / registry /
      DiagnosticProjector path as stage-local checks.
    - When ``config.enabled=False``, all methods return empty results.
    - No LLM imports, no raw NL rules, no fallback.
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import ConstructSatisfactionReport
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.graph import ConstructGraph
from nl2spl.compiler.irs.policy import IRSRuntimeConfig
from nl2spl.compiler.irs.result_store import IRSStageResult
from nl2spl.compiler.irs.runner import IRSRunner
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, WorkerScopedResourceIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR


class IRSSubsystem:
    """Unified entry point for IRS runtime operations.

    Args:
        config: Product-level IRS configuration.
        runner: Pre-configured IRS runner (from factory).
    """

    def __init__(
        self,
        config: IRSRuntimeConfig,
        runner: IRSRunner,
    ) -> None:
        self._config = config
        self._runner = runner

    @property
    def config(self) -> IRSRuntimeConfig:
        """Return the runtime configuration (read-only)."""
        return self._config

    # ------------------------------------------------------------------
    # Stage-local
    # ------------------------------------------------------------------

    def run_stage_local(
        self,
        stage_name: str,
        context: IRSCheckContext,
    ) -> IRSStageResult:
        """Run stage-local IRS checks.

        Args:
            stage_name: Pipeline stage identifier (e.g. ``"stage3_5"``).
            context: Read-only pipeline artifacts for this stage.

        Returns:
            Stage result with reports, diagnostics, graph, and warnings.
            Returns an empty result when IRS or stage-local is disabled.
        """
        if not self._config.enabled or not self._config.stage_local_enabled:
            return IRSStageResult(stage_name=stage_name)

        run_result = self._runner.run_stage(stage_name, context)

        # Build graph snapshot from report edges when enabled.
        # This is a flat extraction — no recursive traversal.
        graph: ConstructGraph | None = None
        if self._config.collect_graph_snapshot:
            graph = self._build_graph_snapshot(run_result.reports)

        return IRSStageResult(
            stage_name=stage_name,
            reports=tuple(run_result.reports),
            diagnostics=tuple(run_result.diagnostics),
            graph=graph,
            warnings=tuple(run_result.warnings),
        )

    # ------------------------------------------------------------------
    # Graph snapshot
    # ------------------------------------------------------------------

    @staticmethod
    def _build_graph_snapshot(
        reports: list[ConstructSatisfactionReport],
    ) -> ConstructGraph:
        """Build a deterministic graph snapshot from report edges.

        Extracts nodes and edges from all reports without recursive
        traversal.  Deduplicates edges by key.

        Args:
            reports: Construct satisfaction reports from a stage run.

        Returns:
            Deduplicated ConstructGraph.
        """
        graph = ConstructGraph()
        for report in reports:
            graph.add_node(report.construct_id)
            for edge in report.related_edges:
                graph.add_edge(edge)
        return graph.deduped()

    # ------------------------------------------------------------------
    # Post-normalize
    # ------------------------------------------------------------------

    def run_post_normalize(
        self,
        worker: WorkerIR,
        worker_plan: WorkerPlanIR | None = None,
        symbol_table: SymbolTable | None = None,
        resources: ResourceRegistryIR | None = None,
        *,
        worker_scoped_resources: WorkerScopedResourceIR | None = None,
        resource_contract_plan: Any = None,
        demand_view: Any = None,
        renderable_resource_registry_view: Any = None,
    ) -> list[CompileDiagnostic]:
        """Run post-normalize IRS — final construct-level authority.

        Runs the ``post_normalize`` checker set through ``IRSRunner`` so
        final diagnostics are projected from ``ConstructSatisfactionReport``
        and ``ConstructIRS`` slot metadata.

        Args:
            worker: Assembled WorkerIR from Stage 10.
            worker_plan: WorkerPlanIR from Stage 3.5.
            symbol_table: Symbol table with producer/consumer links.
            resources: Global resource registry.
            worker_scoped_resources: Worker-scoped resources for merged view.
            demand_view: B5 DemandView (preferred over resource_contract_plan).

        Returns:
            List of authoritative compile diagnostics.
            Returns empty list when IRS or post-normalize is disabled.
        """
        if not self._config.enabled or not self._config.post_normalize_enabled:
            return []

        result = self.run_post_normalize_result(
            worker=worker,
            worker_plan=worker_plan,
            symbol_table=symbol_table,
            resources=resources,
            worker_scoped_resources=worker_scoped_resources,
            resource_contract_plan=resource_contract_plan,
            demand_view=demand_view,
            renderable_resource_registry_view=renderable_resource_registry_view,
        )
        return list(result.diagnostics)

    def run_post_normalize_result(
        self,
        worker: WorkerIR | None,
        worker_plan: WorkerPlanIR | None = None,
        symbol_table: SymbolTable | None = None,
        resources: ResourceRegistryIR | None = None,
        *,
        worker_scoped_resources: WorkerScopedResourceIR | None = None,
        resource_contract_plan: Any = None,
        demand_view: Any = None,
        renderable_resource_registry_view: Any = None,
    ) -> IRSStageResult:
        """Run post-normalize IRS and return reports plus diagnostics."""
        if not self._config.enabled or not self._config.post_normalize_enabled:
            return IRSStageResult(stage_name="post_normalize")

        context = IRSCheckContext(
            stage_name="post_normalize",
            normalized_ir=worker,
            worker_plan=worker_plan,
            symbol_table=symbol_table,
            resources=resources,
            metadata={
                "worker_scoped_resources": worker_scoped_resources,
                "resource_contract_plan": resource_contract_plan,
                "demand_view": demand_view,
                "renderable_resource_registry_view": renderable_resource_registry_view,
            },
        )

        run_result = self._runner.run_stage("post_normalize", context)
        graph = None
        if self._config.collect_graph_snapshot:
            graph = self._build_graph_snapshot(run_result.reports)
        return IRSStageResult(
            stage_name="post_normalize",
            reports=tuple(run_result.reports),
            diagnostics=tuple(run_result.diagnostics),
            graph=graph,
            warnings=tuple(run_result.warnings),
        )
