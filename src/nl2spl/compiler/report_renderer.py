"""ReportRenderer — deterministic, human-readable compile report.

Takes all structured compiler output and produces a plain-text report.
Does NOT call the LLM — output is fully deterministic.
"""

from __future__ import annotations

from nl2spl.compiler.compile_result import CompileAssumption, Completeness
from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord


_SEVERITY_ORDER: dict[str, int] = {"error": 0, "warning": 1, "info": 2}

_SECTION_SEP = "\n" + "-" * 60 + "\n"


def render_report(
    spl_text: str,
    completeness: Completeness = "complete",
    diagnostics: list[CompileDiagnostic] | None = None,
    assumptions: list[CompileAssumption] | None = None,
    traces: list[TraceRecord] | None = None,
    adapter_warnings: list[str] | None = None,
    validation_errors: list[str] | None = None,
    validation_warnings: list[str] | None = None,
) -> str:
    """Render the full compile report.

    Args:
        spl_text: Generated SPL text.
        completeness: Overall compile status.
        diagnostics: CompileDiagnostic records from all stages.
        assumptions: CompileAssumption records (not rendered in SPL).
        traces: Provenance TraceRecords.
        adapter_warnings: Input adapter warnings.
        validation_errors: SPL syntax/reference errors.
        validation_warnings: SPL validation warnings.

    Returns:
        Deterministic plain-text report string.
    """
    diags = diagnostics or []
    asms = assumptions or []
    trcs = traces or []
    a_warns = adapter_warnings or []
    v_errs = validation_errors or []
    v_warns = validation_warnings or []

    lines: list[str] = []

    # ── Header ──
    lines.append("NL2SPL Compile Report")
    lines.append("=" * 60)
    lines.append("")

    # ── Summary ──
    lines.extend(_render_summary(
        completeness, bool(spl_text.strip()), diags, asms, trcs, a_warns,
        v_errs, v_warns,
    ))
    lines.append(_SECTION_SEP)

    # ── Adapter ──
    if a_warns:
        lines.extend(_render_adapter(a_warns))
        lines.append(_SECTION_SEP)

    # ── Diagnostics ──
    if diags:
        lines.extend(_render_diagnostics(diags))
        lines.append(_SECTION_SEP)

    # ── Assumptions ──
    if asms:
        lines.extend(_render_assumptions(asms, diags))
        lines.append(_SECTION_SEP)

    # ── Traces ──
    if trcs:
        lines.extend(_render_traces(trcs))
        lines.append(_SECTION_SEP)

    # ── Validation ──
    if v_errs or v_warns:
        lines.extend(_render_validation(v_errs, v_warns))
        lines.append(_SECTION_SEP)

    # ── SPL ──
    lines.append("Generated SPL")
    lines.append("-" * 40)
    lines.append(spl_text if spl_text else "(no SPL generated)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _render_summary(
    completeness: Completeness,
    has_spl: bool,
    diagnostics: list[CompileDiagnostic],
    assumptions: list[CompileAssumption],
    traces: list[TraceRecord],
    adapter_warnings: list[str],
    validation_errors: list[str],
    validation_warnings: list[str],
) -> list[str]:
    lines: list[str] = []
    lines.append("Status: " + completeness)
    lines.append("")
    lines.append("Summary:")
    lines.append(f"  SPL draft generated: {'yes' if has_spl else 'no'}")
    lines.append(f"  Adapter warnings: {len(adapter_warnings)}")
    lines.append(f"  Diagnostics: {_diag_summary(diagnostics)}")
    lines.append(f"  Validation errors: {len(validation_errors)}")
    lines.append(f"  Validation warnings: {len(validation_warnings)}")
    lines.append(f"  Assumptions (not rendered): {len(assumptions)}")
    lines.append(f"  Trace records: {len(traces)}")
    return lines


def _diag_summary(diagnostics: list[CompileDiagnostic]) -> str:
    if not diagnostics:
        return "0"
    errors = sum(1 for d in diagnostics if d.severity == "error")
    warnings = sum(1 for d in diagnostics if d.severity == "warning")
    infos = sum(1 for d in diagnostics if d.severity == "info")
    parts = []
    if errors:
        parts.append(f"{errors} error(s)")
    if warnings:
        parts.append(f"{warnings} warning(s)")
    if infos:
        parts.append(f"{infos} info")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

def _render_adapter(warnings: list[str]) -> list[str]:
    lines: list[str] = []
    lines.append("Adapter Warnings")
    lines.append("-" * 40)
    for w in warnings:
        lines.append(f"  - {w}")
    return lines


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _render_diagnostics(diagnostics: list[CompileDiagnostic]) -> list[str]:
    lines: list[str] = []
    lines.append("Diagnostics")
    lines.append("-" * 40)

    sorted_diags = sorted(
        diagnostics,
        key=lambda d: (_SEVERITY_ORDER.get(d.severity, 99), d.kind, d.diagnostic_id),
    )
    for d in sorted_diags:
        lines.append("")
        lines.append(f"  [{d.severity.upper()}] [{d.kind}] {d.diagnostic_id}")
        if d.target_ref:
            lines.append(f"    Target: {d.target_ref}")
        if d.source_span_ids:
            lines.append(f"    Source spans: {', '.join(d.source_span_ids)}")
        lines.append(f"    {d.message}")
        if d.suggested_resolution:
            lines.append(f"    Suggested: {d.suggested_resolution}")
        if d.blocks_rendering:
            lines.append(f"    (blocks rendering of affected element)")
        if d.missing_slot is not None:
            lines.append(f"    Missing: {d.missing_slot.slot_name} "
                         f"(required for {d.missing_slot.required_for})")
            if d.missing_slot.suggested_question:
                lines.append(f"    Question: {d.missing_slot.suggested_question}")

    return lines


# ---------------------------------------------------------------------------
# Assumptions
# ---------------------------------------------------------------------------

def _render_assumptions(
    assumptions: list[CompileAssumption],
    diagnostics: list[CompileDiagnostic],
) -> list[str]:
    lines: list[str] = []
    lines.append("Assumptions / Suggestions")
    lines.append("-" * 40)

    diag_index = {d.diagnostic_id: d for d in diagnostics}

    for a in assumptions:
        lines.append("")
        lines.append(f"  [{a.assumption_id}] {a.text}")
        if a.target_ref:
            lines.append(f"    Target: {a.target_ref}")
        if a.reason:
            lines.append(f"    Reason: {a.reason}")
        if a.suggested_resolution:
            lines.append(f"    Action: {a.suggested_resolution}")
        if a.related_diagnostic_id and a.related_diagnostic_id in diag_index:
            related = diag_index[a.related_diagnostic_id]
            lines.append(f"    Related diagnostic: [{related.kind}] "
                         f"{related.diagnostic_id} — {related.message[:120]}")
        if a.related_missing_slot:
            lines.append(f"    Related missing slot: {a.related_missing_slot}")

    return lines


# ---------------------------------------------------------------------------
# Traces
# ---------------------------------------------------------------------------

def _render_traces(traces: list[TraceRecord]) -> list[str]:
    lines: list[str] = []
    lines.append("Provenance Traces")
    lines.append("-" * 40)

    sorted_traces = sorted(
        traces,
        key=lambda t: (
            t.target_ref, t.relation,
            tuple(t.source_span_ids),
        ),
    )
    for t in sorted_traces:
        span_info = ""
        if t.source_span_ids:
            span_info = f" spans={', '.join(t.source_span_ids)}"
        section_info = ""
        if t.source_section_id:
            section_info += f" section={t.source_section_id}"
        if t.source_packet_id:
            section_info += f" packet={t.source_packet_id}"
        confirm = " [needs confirmation]" if t.needs_confirmation else ""
        lines.append(
            f"  [{t.relation}] {t.target_ref}{span_info}{section_info}"
            f"{confirm}"
        )
        if t.explanation:
            lines.append(f"    {t.explanation}")

    return lines


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _render_validation(
    errors: list[str],
    warnings: list[str],
) -> list[str]:
    lines: list[str] = []
    lines.append("Validation")
    lines.append("-" * 40)

    if errors:
        lines.append("")
        lines.append(f"  Errors ({len(errors)}):")
        for e in errors:
            lines.append(f"    - {e}")

    if warnings:
        lines.append("")
        lines.append(f"  Warnings ({len(warnings)}):")
        for w in warnings:
            lines.append(f"    - {w}")

    return lines
