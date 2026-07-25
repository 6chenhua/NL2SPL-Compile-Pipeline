"""IRS-neutral diagnostic authority inputs for consolidation."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.ir.diagnostics import CompileDiagnostic


@dataclass(frozen=True)
class StageLocalDiagnosticBundle:
    """Diagnostics and warnings produced by one stage-local authority."""

    stage_name: str
    diagnostics: tuple[CompileDiagnostic, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticAuthorityBundle:
    """IRS-neutral bundle of stage-local diagnostic authority outputs."""

    stage_local_results: tuple[StageLocalDiagnosticBundle, ...] = ()


__all__ = ["DiagnosticAuthorityBundle", "StageLocalDiagnosticBundle"]
