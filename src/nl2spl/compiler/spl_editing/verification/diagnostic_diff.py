"""Diagnostic diff — compare before/after diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.ir.diagnostics import CompileDiagnostic


@dataclass(frozen=True)
class DiagnosticDiffResult:
    """Result of comparing two diagnostic sets."""

    resolved_ids: tuple[str, ...] = ()
    """Diagnostics present in *before* but absent in *after*."""

    new_blocking_ids: tuple[str, ...] = ()
    """Blocking diagnostics in *after* that were not in *before*."""

    unchanged_count: int = 0

    @property
    def has_new_blocking(self) -> bool:
        return len(self.new_blocking_ids) > 0

    @property
    def summary(self) -> str:
        parts = [f"{len(self.resolved_ids)} resolved"]
        if self.new_blocking_ids:
            parts.append(f"{len(self.new_blocking_ids)} new blocking")
        parts.append(f"{self.unchanged_count} unchanged")
        return ", ".join(parts)


class DiagnosticDiff:
    """Compare two sets of diagnostics."""

    def compare(
        self,
        before: tuple[CompileDiagnostic, ...],
        after: tuple[CompileDiagnostic, ...],
    ) -> DiagnosticDiffResult:
        before_ids = {d.diagnostic_id for d in before}
        after_ids = {d.diagnostic_id for d in after}

        resolved = tuple(sorted(before_ids - after_ids))

        before_blocking = {
            d.diagnostic_id for d in before if d.blocks_completion
        }
        after_blocking = {
            d.diagnostic_id for d in after if d.blocks_completion
        }
        new_blocking = tuple(sorted(after_blocking - before_blocking))

        unchanged = len(before_ids & after_ids)

        return DiagnosticDiffResult(
            resolved_ids=resolved,
            new_blocking_ids=new_blocking,
            unchanged_count=unchanged,
        )
