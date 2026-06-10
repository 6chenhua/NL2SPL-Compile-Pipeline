"""Productized diagnostic consolidation for compiler outputs.

The consolidator is the single place that merges diagnostics from
post-normalize IRS, executable gate, provenance, promoted IRS demand
diagnostics, conflict analysis, and stage-local IRS.  It does not create new
diagnostics and does not inspect raw NL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from nl2spl.compiler.irs.result_store import IRSResultStore
from nl2spl.ir.diagnostics import CompileDiagnostic


DiagnosticDedupKey = tuple[str, str | None, str | None, tuple[str, ...]]


def missing_slot_name(diagnostic: CompileDiagnostic) -> str | None:
    """Return the missing slot name for deduplication, if present."""
    missing_slot = getattr(diagnostic, "missing_slot", None)
    if missing_slot is not None:
        return getattr(missing_slot, "slot_name", None)
    return None


def diagnostic_dedup_key(diagnostic: CompileDiagnostic) -> DiagnosticDedupKey:
    """Return the authority-safe dedup key for one diagnostic."""
    return (
        diagnostic.kind,
        diagnostic.target_ref,
        missing_slot_name(diagnostic),
        tuple(sorted(diagnostic.source_span_ids or [])),
    )


@dataclass(frozen=True)
class DiagnosticConsolidationInput:
    """Inputs from all diagnostic-producing compiler authorities."""

    stage2_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    construct_plan_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    stage7_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    irs_store: IRSResultStore | None = None
    post_normalize_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    gate_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    provenance_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    irs_promoted_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    conflict_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    include_stage_local_diagnostics: bool = False


@dataclass(frozen=True)
class DiagnosticConsolidationResult:
    """Result of productized diagnostic consolidation."""

    final_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    suppressed_stage_local_diagnostics: list[CompileDiagnostic] = field(
        default_factory=list
    )
    warnings: list[str] = field(default_factory=list)


class DiagnosticConsolidator:
    """Merge diagnostics according to compiler authority boundaries."""

    def consolidate(
        self,
        data: DiagnosticConsolidationInput,
    ) -> DiagnosticConsolidationResult:
        """Consolidate diagnostics without mutating input objects."""
        final: list[CompileDiagnostic] = []
        seen: set[DiagnosticDedupKey] = set()
        warnings: list[str] = []

        def add_group(group: Iterable[CompileDiagnostic]) -> None:
            for diagnostic in group:
                key = diagnostic_dedup_key(diagnostic)
                if key in seen:
                    continue
                seen.add(key)
                final.append(diagnostic)

        # Authority order: final construct-level and executable authorities
        # seed the dedup set before route/stage-local diagnostics.
        add_group(data.post_normalize_diagnostics)
        add_group(data.gate_diagnostics)
        add_group(data.provenance_diagnostics)
        add_group(data.stage2_diagnostics)
        add_group(data.construct_plan_diagnostics)
        add_group(data.irs_promoted_diagnostics)
        add_group(data.conflict_diagnostics)
        add_group(data.stage7_diagnostics)

        suppressed_stage_local: list[CompileDiagnostic] = []
        if data.irs_store is not None:
            for stage_name in sorted(data.irs_store.get_all_stage_results()):
                stage_result = data.irs_store.get_stage_result(stage_name)
                if stage_result is None:
                    continue
                for diagnostic in stage_result.diagnostics:
                    key = diagnostic_dedup_key(diagnostic)
                    if key in seen:
                        suppressed_stage_local.append(diagnostic)
                        continue
                    if data.include_stage_local_diagnostics:
                        seen.add(key)
                        final.append(diagnostic)
                    else:
                        suppressed_stage_local.append(diagnostic)
                warnings.extend(stage_result.warnings)

        return DiagnosticConsolidationResult(
            final_diagnostics=list(final),
            suppressed_stage_local_diagnostics=list(suppressed_stage_local),
            warnings=warnings,
        )
