"""Productized diagnostic consolidation for compiler outputs.

The consolidator is the single place that merges diagnostics from
post-normalize IRS, executable gate, provenance, promoted IRS demand
diagnostics, conflict analysis, and stage-local authorities. It does not
create new diagnostics and does not inspect raw NL.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from nl2spl.compiler.diagnostics.authority import DiagnosticAuthorityBundle
from nl2spl.ir.diagnostics import CompileDiagnostic

DiagnosticDedupKey = tuple[
    str, str | None, str | None, tuple[str, ...],
    str | None, str | None,  # semantic_role, field_name (ARC7)
]


def missing_slot_name(diagnostic: CompileDiagnostic) -> str | None:
    """Return the missing slot name for deduplication, if present."""
    missing_slot = getattr(diagnostic, "missing_slot", None)
    if missing_slot is not None:
        return getattr(missing_slot, "slot_name", None)
    return None


def diagnostic_dedup_key(diagnostic: CompileDiagnostic) -> DiagnosticDedupKey:
    """Return the authority-safe dedup key for one diagnostic.

    ARC7: includes ``metadata["semantic_role"]`` and ``metadata["field_name"]``
    so that different role-contract conflicts for the same span are not collapsed.
    """
    meta = getattr(diagnostic, "metadata", None) or {}
    return (
        diagnostic.kind,
        diagnostic.target_ref,
        missing_slot_name(diagnostic),
        tuple(sorted(diagnostic.source_span_ids or [])),
        meta.get("semantic_role"),
        meta.get("field_name"),
    )


@dataclass(frozen=True)
class DiagnosticConsolidationInput:
    """Inputs from all diagnostic-producing compiler authorities."""

    stage2_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    construct_plan_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    stage7_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    stage_local_authority: DiagnosticAuthorityBundle | None = None
    post_normalize_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    gate_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    provenance_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    irs_promoted_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    conflict_diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    include_stage_local_diagnostics: bool = False

    @property
    def irs_store(self) -> DiagnosticAuthorityBundle | None:
        """Backward-compatible alias for legacy tests and monkeypatch hooks.

        The value is an IRS-neutral authority bundle, not an ``IRSResultStore``.
        """
        return self.stage_local_authority


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
        if data.stage_local_authority is not None:
            for stage_result in sorted(
                data.stage_local_authority.stage_local_results,
                key=lambda result: result.stage_name,
            ):
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


__all__ = [
    "DiagnosticConsolidationInput",
    "DiagnosticConsolidationResult",
    "DiagnosticConsolidator",
    "DiagnosticDedupKey",
    "diagnostic_dedup_key",
    "missing_slot_name",
]
