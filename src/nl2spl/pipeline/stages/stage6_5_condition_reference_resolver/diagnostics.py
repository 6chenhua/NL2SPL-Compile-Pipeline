"""Diagnostics for Stage 6.5 condition reference resolution.

S6V5: Diagnostic blocking policy is differentiated by source:
- Explicit missing <REF> → blocks_completion=True (semantic integrity risk)
- LLM unresolved/rejected → blocks_completion=False (report/audit only)
- Parser diagnostics → blocks_completion=False (report/audit only)
"""

from __future__ import annotations

from nl2spl.ir.diagnostics import CompileDiagnostic


def resolver_diagnostic(
    *,
    diagnostic_id: str,
    kind: str,
    message: str,
    owner_ref: str,
    source_span_ids: tuple[str, ...],
    metadata: dict[str, object] | None = None,
    blocks_completion: bool = False,
) -> CompileDiagnostic:
    """Create a Stage 6.5 resolver diagnostic.

    Args:
        diagnostic_id: Unique diagnostic identifier.
        kind: Diagnostic kind string.
        message: Human-readable diagnostic message.
        owner_ref: Reference to the owning condition/block.
        source_span_ids: Source span IDs for provenance.
        metadata: Additional metadata.
        blocks_completion: Whether this diagnostic blocks compile completion.
            Default False (report/audit only). Set True for explicit missing
            <REF> tokens (semantic integrity risk).
    """
    return CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind=kind,
        severity="warning",
        message=message,
        target_ref=owner_ref,
        source_span_ids=list(source_span_ids),
        metadata=metadata or {},
        blocks_rendering=False,
        blocks_completion=blocks_completion,
    )
