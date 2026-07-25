"""ViewDiagnosticProjector — project DemandView diagnostics into CompileDiagnostic.

Phase A: projector implementation exists and is tested, but is not yet
connected to the orchestrator diagnostic path.
"""

from __future__ import annotations

from nl2spl.compiler.resource_contract_demand_view.model import (
    ResourceContractDemandView,
    ViewDiagnostic,
)
from nl2spl.ir.diagnostics import CompileDiagnostic


class ViewDiagnosticProjector:
    """Convert DemandView ``ViewDiagnostic`` records into ``CompileDiagnostic``."""

    @staticmethod
    def project(
        view: ResourceContractDemandView,
    ) -> list[CompileDiagnostic]:
        """Project all view diagnostics from *view* into ``CompileDiagnostic``.

        Args:
            view: A completed ``ResourceContractDemandView``.

        Returns:
            List of ``CompileDiagnostic`` instances, one per view diagnostic.
        """
        return [
            ViewDiagnosticProjector._project_one(diag)
            for diag in view.view_diagnostics
        ]

    @staticmethod
    def project_list(
        diagnostics: list[ViewDiagnostic],
    ) -> list[CompileDiagnostic]:
        """Project a standalone list of ``ViewDiagnostic`` records.

        Useful when diagnostics are not yet assembled into a full view.
        """
        return [ViewDiagnosticProjector._project_one(diag) for diag in diagnostics]

    # ── private ──────────────────────────────────────────────────────────

    @staticmethod
    def _project_one(diag: ViewDiagnostic) -> CompileDiagnostic:
        """Map a single ``ViewDiagnostic`` to ``CompileDiagnostic``."""
        return CompileDiagnostic(
            diagnostic_id=_make_diagnostic_id(diag),
            kind=diag.kind,
            severity=diag.severity,
            message=diag.message,
            target_ref=diag.demand_id or (
                f"span:{diag.span_ids[0]}" if diag.span_ids else None
            ),
            source_span_ids=list(diag.span_ids),
            suggested_resolution=None,
            blocks_rendering=False,
            blocks_completion=False,
        )


def _make_diagnostic_id(diag: ViewDiagnostic) -> str:
    """Build a stable diagnostic id from kind + span/demand references."""
    parts = ["view", diag.kind.replace("_", "-")]
    if diag.demand_id:
        parts.append(diag.demand_id)
    elif diag.span_ids:
        parts.append("s_" + "_".join(sorted(diag.span_ids)))
    return ":".join(parts)
