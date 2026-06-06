"""IRS Result Store — deterministic storage for stage-local and post-normalize results.

IRSResultStore accumulates IRSStageResult entries keyed by stage name
and provides a deterministic ``to_intermediate_payload()`` for writing
into the pipeline's ``intermediate`` dict.

Design constraints:
    - ``IRSStageResult`` is frozen and stores reports/diagnostics/warnings
      as tuples to avoid shared mutable lists.
    - ``put_stage_result`` copies input lists into tuples.
    - ``to_intermediate_payload`` is deterministic (sorted keys).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nl2spl.compiler.construct_registry import ConstructSatisfactionReport
from nl2spl.compiler.irs.graph import ConstructGraph
from nl2spl.ir.diagnostics import CompileDiagnostic


@dataclass(frozen=True)
class IRSStageResult:
    """Immutable result of an IRS stage-local check.

    Attributes:
        stage_name: Pipeline stage identifier (e.g. ``"stage3_5"``).
        reports: Construct satisfaction reports produced by checkers.
        diagnostics: Projected compile diagnostics.
        graph: Optional construct graph snapshot.
        warnings: Non-fatal warnings from checking or projection.
    """

    stage_name: str
    reports: tuple[ConstructSatisfactionReport, ...] = ()
    diagnostics: tuple[CompileDiagnostic, ...] = ()
    graph: ConstructGraph | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Convert any list inputs to tuples for immutability.

        If a graph is provided, deep-copy its nodes and edges so that
        subsequent mutation of the original graph does not affect the
        stored snapshot.
        """
        if not isinstance(self.reports, tuple):
            object.__setattr__(self, "reports", tuple(self.reports))
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if not isinstance(self.warnings, tuple):
            object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.graph is not None:
            object.__setattr__(self, "graph", self._copy_graph(self.graph))

    @staticmethod
    def _copy_graph(graph: ConstructGraph) -> ConstructGraph:
        """Deep-copy a ConstructGraph's mutable fields."""
        from nl2spl.compiler.irs.graph import ConstructEdge

        copied_edges = [
            ConstructEdge(
                from_id=e.from_id,
                to_id=e.to_id,
                edge_type=e.edge_type,
                source_span_ids=list(e.source_span_ids),
                metadata=dict(e.metadata),
            )
            for e in graph.edges
        ]
        return ConstructGraph(
            nodes=list(graph.nodes),
            edges=copied_edges,
        )


@dataclass
class IRSResultStore:
    """Accumulates IRS results across pipeline stages.

    Provides deterministic payload generation for the pipeline's
    ``intermediate`` dict.

    Usage::

        store = IRSResultStore()
        store.put_stage_result(stage_result)
        payload = store.to_intermediate_payload()
        intermediate.update(payload)
    """

    _stage_results: dict[str, IRSStageResult] = field(default_factory=dict)
    _post_normalize_diagnostics: list[CompileDiagnostic] = field(
        default_factory=list,
    )

    # ------------------------------------------------------------------
    # Stage-local
    # ------------------------------------------------------------------

    def put_stage_result(self, result: IRSStageResult) -> None:
        """Store a stage-local result.

        Args:
            result: Immutable stage result to store.
        """
        self._stage_results[result.stage_name] = result

    def get_stage_result(self, stage_name: str) -> IRSStageResult | None:
        """Retrieve a stage-local result by name.

        Args:
            stage_name: Pipeline stage identifier.

        Returns:
            The stored result, or ``None`` if not found.
        """
        return self._stage_results.get(stage_name)

    def get_all_stage_results(self) -> dict[str, IRSStageResult]:
        """Return a shallow copy of all stage results."""
        return dict(self._stage_results)

    # ------------------------------------------------------------------
    # Post-normalize
    # ------------------------------------------------------------------

    def put_post_normalize_diagnostics(
        self,
        diagnostics: list[CompileDiagnostic],
    ) -> None:
        """Store post-normalize diagnostics (final authority).

        Copies the input list to avoid sharing a mutable reference.

        Args:
            diagnostics: Diagnostics from post-normalize IRS.
        """
        self._post_normalize_diagnostics = list(diagnostics)

    def get_post_normalize_diagnostics(self) -> list[CompileDiagnostic]:
        """Retrieve post-normalize diagnostics.

        Returns:
            A copy of the stored diagnostics list.
        """
        return list(self._post_normalize_diagnostics)

    # ------------------------------------------------------------------
    # Payload generation
    # ------------------------------------------------------------------

    def to_intermediate_payload(self) -> dict[str, Any]:
        """Generate a deterministic payload for ``intermediate``.

        Returns a dict with the following keys:

        - ``construct_satisfaction``: ``{stage_name: [report, ...]}``
        - ``stage_local_diagnostics``: ``{stage_name: [diag, ...]}``
        - ``irs_stage_results``: full stage results including graph and
          warnings, keyed by stage name.  Each value is a dict with
          ``reports``, ``diagnostics``, ``graph``, ``warnings``.
        - ``irs_post_normalize_diagnostics``: list of post-normalize
          diagnostics (final authority).

        The first two keys preserve backward compatibility with code
        that reads ``intermediate["construct_satisfaction"]``.
        """
        construct_satisfaction: dict[str, list[ConstructSatisfactionReport]] = {}
        stage_local_diagnostics: dict[str, list[CompileDiagnostic]] = {}
        irs_stage_results: dict[str, dict[str, Any]] = {}

        for stage_name in sorted(self._stage_results):
            result = self._stage_results[stage_name]
            construct_satisfaction[stage_name] = list(result.reports)
            stage_local_diagnostics[stage_name] = list(result.diagnostics)
            # Graph is emitted as a deterministic snapshot dict, not the
            # mutable ConstructGraph object, so payload consumers cannot
            # pollute the store.
            graph_snapshot: dict[str, Any] | None = None
            if result.graph is not None:
                graph_snapshot = {
                    "nodes": sorted(result.graph.nodes),
                    "edges": result.graph.edge_snapshots(),
                }
            irs_stage_results[stage_name] = {
                "reports": list(result.reports),
                "diagnostics": list(result.diagnostics),
                "graph": graph_snapshot,
                "warnings": list(result.warnings),
            }

        return {
            "construct_satisfaction": construct_satisfaction,
            "stage_local_diagnostics": stage_local_diagnostics,
            "irs_stage_results": irs_stage_results,
            "irs_post_normalize_diagnostics": list(
                self._post_normalize_diagnostics
            ),
        }
