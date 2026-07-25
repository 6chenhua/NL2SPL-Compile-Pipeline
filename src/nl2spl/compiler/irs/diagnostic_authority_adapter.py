"""Adapters from IRS runtime result storage to diagnostic authority DTOs."""

from __future__ import annotations

from nl2spl.compiler.diagnostics.authority import (
    DiagnosticAuthorityBundle,
    StageLocalDiagnosticBundle,
)
from nl2spl.compiler.irs.result_store import IRSResultStore


def diagnostic_authority_from_irs_store(
    store: IRSResultStore,
) -> DiagnosticAuthorityBundle:
    """Convert an IRSResultStore into an IRS-neutral consolidation input."""
    stage_results: list[StageLocalDiagnosticBundle] = []
    for stage_name in sorted(store.get_all_stage_results()):
        result = store.get_stage_result(stage_name)
        if result is None:
            continue
        stage_results.append(
            StageLocalDiagnosticBundle(
                stage_name=stage_name,
                diagnostics=tuple(result.diagnostics),
                warnings=tuple(result.warnings),
            )
        )
    return DiagnosticAuthorityBundle(stage_local_results=tuple(stage_results))


__all__ = ["diagnostic_authority_from_irs_store"]
