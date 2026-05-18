"""Deterministic Markdown feedback report for NL2SPL runs.

The compile report is a compact machine-oriented summary.  This renderer
produces the user-facing feedback artifact: what was materialized, what was
left partial, what evidence was used, and what the compiler deliberately did
not invent.
"""

from __future__ import annotations

from collections import defaultdict

from nl2spl.compiler.compile_result import CompileAssumption, Completeness
from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord


_DIAG_ORDER: dict[str, int] = {
    "missing_handler": 0,
    "missing_output_producer": 1,
    "type_or_contract_ambiguity": 2,
    "assumed_command_not_renderable": 3,
    "unmapped_behavior_span": 4,
    "missing_provenance": 5,
}


def render_feedback_report(
    spl_text: str,
    completeness: Completeness = "complete",
    diagnostics: list[CompileDiagnostic] | None = None,
    assumptions: list[CompileAssumption] | None = None,
    traces: list[TraceRecord] | None = None,
    adapter_warnings: list[str] | None = None,
    validation_errors: list[str] | None = None,
    validation_warnings: list[str] | None = None,
) -> str:
    """Render a Markdown feedback report.

    This output intentionally mirrors the teacher-facing expectation: partial
    SPL is a valid result, gaps are explicit diagnostics, assumptions stay out
    of executable SPL, and provenance is visible.
    """

    diags = diagnostics or []
    asms = assumptions or []
    trcs = traces or []
    a_warns = adapter_warnings or []
    v_errs = validation_errors or []
    v_warns = validation_warnings or []

    lines: list[str] = []
    lines.append("# NL2SPL Feedback Report")
    lines.append("")
    lines.extend(_render_status(completeness, spl_text, diags, asms, trcs, a_warns, v_errs, v_warns))
    lines.append("")
    lines.extend(_render_materialized(trcs))
    lines.append("")
    lines.extend(_render_not_materialized(diags))
    lines.append("")
    lines.extend(_render_diagnostics(diags))
    lines.append("")
    lines.extend(_render_assumptions(asms))
    lines.append("")
    lines.extend(_render_traces(trcs))
    lines.append("")
    lines.extend(_render_anti_fabrication(diags, spl_text))
    lines.append("")
    lines.extend(_render_validation(a_warns, v_errs, v_warns))
    lines.append("")
    lines.extend(_render_spl(spl_text))

    return "\n".join(lines).rstrip() + "\n"


def _render_status(
    completeness: Completeness,
    spl_text: str,
    diagnostics: list[CompileDiagnostic],
    assumptions: list[CompileAssumption],
    traces: list[TraceRecord],
    adapter_warnings: list[str],
    validation_errors: list[str],
    validation_warnings: list[str],
) -> list[str]:
    lines = [
        "## 1. Overall Compile State",
        "",
        f"- Completeness: `{completeness}`",
        f"- SPL draft generated: `{'yes' if spl_text.strip() else 'no'}`",
        f"- Compile diagnostics: `{len(diagnostics)}`",
        f"- Assumptions / suggestions: `{len(assumptions)}`",
        f"- Trace records: `{len(traces)}`",
        f"- Adapter warnings: `{len(adapter_warnings)}`",
        f"- Validation errors: `{len(validation_errors)}`",
        f"- Validation warnings: `{len(validation_warnings)}`",
        "",
    ]

    blocking = [d for d in diagnostics if d.blocks_completion]
    if validation_errors:
        lines.append("Result is blocked because validation errors remain.")
    elif blocking:
        lines.append("Result is partial because the following requirement gaps remain:")
        for d in _sort_diags(blocking):
            target = f" on `{d.target_ref}`" if d.target_ref else ""
            lines.append(f"- `{d.kind}`{target}: {d.message}")
    elif completeness == "complete":
        lines.append("No completion-blocking diagnostic was emitted.")
    else:
        lines.append("The result is not complete; inspect diagnostics and validation sections below.")

    return lines


def _render_materialized(traces: list[TraceRecord]) -> list[str]:
    lines = ["## 2. Materialized Source-Backed Structure", ""]
    if not traces:
        lines.append("No provenance traces were produced.")
        return lines

    grouped: dict[str, list[TraceRecord]] = defaultdict(list)
    for trace in traces:
        group = _trace_group(trace.target_ref)
        if trace.relation != "assumed":
            grouped[group].append(trace)

    if not grouped:
        lines.append("No source-backed structure was materialized.")
        return lines

    for group in ["Workers", "Flows", "Steps", "Variables", "Constraints", "Handoffs", "Delegation Intents", "Other"]:
        items = sorted(grouped.get(group, []), key=_trace_sort_key)
        if not items:
            continue
        lines.append(f"### {group}")
        for trace in items:
            lines.append(f"- `{trace.target_ref}` ({trace.relation}){_trace_source_suffix(trace)}")
        lines.append("")

    if lines[-1] == "":
        lines.pop()
    return lines


def _render_not_materialized(diagnostics: list[CompileDiagnostic]) -> list[str]:
    lines = ["## 3. Not Materialized / Kept Partial", ""]
    partial_diags = [
        d for d in diagnostics
        if d.kind in {
            "missing_handler",
            "missing_output_producer",
            "type_or_contract_ambiguity",
            "assumed_command_not_renderable",
            "unmapped_behavior_span",
        }
    ]
    if not partial_diags:
        lines.append("No source-expressed structure was blocked or kept partial.")
        return lines

    for d in _sort_diags(partial_diags):
        target = f"`{d.target_ref}`" if d.target_ref else "affected element"
        lines.append(f"- {target}: `{d.kind}` -- {d.message}")
        if d.suggested_resolution:
            lines.append(f"  - Suggested resolution: {d.suggested_resolution}")
    return lines


def _render_diagnostics(diagnostics: list[CompileDiagnostic]) -> list[str]:
    lines = ["## 4. Diagnostics", ""]
    if not diagnostics:
        lines.append("No compile diagnostics.")
        return lines

    for d in _sort_diags(diagnostics):
        lines.append(f"### {d.diagnostic_id}: `{d.kind}`")
        lines.append(f"- Severity: `{d.severity}`")
        if d.target_ref:
            lines.append(f"- Target: `{d.target_ref}`")
        if d.source_span_ids:
            lines.append(f"- Source spans: `{', '.join(d.source_span_ids)}`")
        lines.append(f"- Message: {d.message}")
        lines.append(f"- Blocks rendering: `{str(d.blocks_rendering).lower()}`")
        lines.append(f"- Blocks completion: `{str(d.blocks_completion).lower()}`")
        if d.suggested_resolution:
            lines.append(f"- Suggested resolution: {d.suggested_resolution}")
        if d.missing_slot is not None:
            lines.append(f"- Missing slot: `{d.missing_slot.slot_name}`")
            lines.append(f"- Missing reason: {d.missing_slot.reason}")
            if d.missing_slot.suggested_question:
                lines.append(f"- Question to ask: {d.missing_slot.suggested_question}")
        lines.append("")

    if lines[-1] == "":
        lines.pop()
    return lines


def _render_assumptions(assumptions: list[CompileAssumption]) -> list[str]:
    lines = ["## 5. Assumptions / Suggestions", ""]
    if not assumptions:
        lines.append("No report-only assumptions were generated.")
        return lines

    for a in sorted(assumptions, key=lambda x: x.assumption_id):
        lines.append(f"- `{a.assumption_id}` for `{a.target_ref}`: {a.text}")
        if a.reason:
            lines.append(f"  - Reason: {a.reason}")
        if a.suggested_resolution:
            lines.append(f"  - Suggested resolution: {a.suggested_resolution}")
        if a.related_diagnostic_id:
            lines.append(f"  - Related diagnostic: `{a.related_diagnostic_id}`")
    return lines


def _render_traces(traces: list[TraceRecord]) -> list[str]:
    lines = ["## 6. Provenance / TraceRecords", ""]
    if not traces:
        lines.append("No trace records.")
        return lines

    for t in sorted(traces, key=_trace_sort_key):
        flags = []
        if t.needs_confirmation:
            flags.append("needs confirmation")
        flag_text = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"- `{t.target_ref}` -> `{t.relation}`{flag_text}")
        source_parts = []
        if t.source_span_ids:
            source_parts.append(f"spans=`{', '.join(t.source_span_ids)}`")
        if t.source_section_id:
            source_parts.append(f"section=`{t.source_section_id}`")
        if t.source_packet_id:
            source_parts.append(f"packet=`{t.source_packet_id}`")
        if source_parts:
            lines.append(f"  - Source: {', '.join(source_parts)}")
        if t.explanation:
            lines.append(f"  - Explanation: {t.explanation}")
    return lines


def _render_anti_fabrication(
    diagnostics: list[CompileDiagnostic],
    spl_text: str,
) -> list[str]:
    lines = ["## 7. Anti-Fabrication Checks", ""]
    kinds = {d.kind for d in diagnostics}

    checks = [
        (
            "missing_handler",
            "Exception conditions without handler action stay as partial exception flows; no handler command is invented.",
        ),
        (
            "missing_output_producer",
            "Required outputs without a source-backed producer stay in the contract; no synthetic producer command is invented.",
        ),
        (
            "type_or_contract_ambiguity",
            "Unresolved worker/API contracts are reported as ambiguity; they are not downgraded to generic commands.",
        ),
        (
            "assumed_command_not_renderable",
            "Commands without acceptable evidence are blocked before rendering.",
        ),
    ]

    any_specific = False
    for kind, text in checks:
        if kind in kinds:
            any_specific = True
            lines.append(f"- `{kind}`: {text}")

    if not any_specific:
        lines.append("- No anti-fabrication diagnostic was emitted for this run.")

    if "[INVOKE" not in spl_text:
        lines.append("- Rendered SPL contains no executable `[INVOKE ...]` command.")

    return lines


def _render_validation(
    adapter_warnings: list[str],
    validation_errors: list[str],
    validation_warnings: list[str],
) -> list[str]:
    lines = ["## 8. Adapter / Validation Notes", ""]
    if not adapter_warnings and not validation_errors and not validation_warnings:
        lines.append("No adapter or validation notes.")
        return lines

    if adapter_warnings:
        lines.append("Adapter warnings:")
        for warning in adapter_warnings:
            lines.append(f"- {warning}")
        lines.append("")
    if validation_errors:
        lines.append("Validation errors:")
        for error in validation_errors:
            lines.append(f"- {error}")
        lines.append("")
    if validation_warnings:
        lines.append("Validation warnings:")
        for warning in validation_warnings:
            lines.append(f"- {warning}")

    if lines[-1] == "":
        lines.pop()
    return lines


def _render_spl(spl_text: str) -> list[str]:
    return [
        "## 9. SPL Draft",
        "",
        "```spl",
        spl_text.strip() if spl_text.strip() else "(no SPL generated)",
        "```",
    ]


def _sort_diags(diagnostics: list[CompileDiagnostic]) -> list[CompileDiagnostic]:
    return sorted(
        diagnostics,
        key=lambda d: (_DIAG_ORDER.get(d.kind, 99), d.severity, d.diagnostic_id),
    )


def _trace_group(target_ref: str) -> str:
    if target_ref.startswith("worker:"):
        return "Workers"
    if target_ref.startswith("flow:") or ".exception_flow:" in target_ref or target_ref.startswith("exception_flow:"):
        return "Flows"
    if target_ref.startswith("step:"):
        return "Steps"
    if ".variable:" in target_ref or target_ref.startswith("variable:"):
        return "Variables"
    if target_ref.startswith("constraint:"):
        return "Constraints"
    if target_ref.startswith("handoff:"):
        return "Handoffs"
    if target_ref.startswith("delegation_intent:"):
        return "Delegation Intents"
    return "Other"


def _trace_source_suffix(trace: TraceRecord) -> str:
    parts = []
    if trace.source_span_ids:
        parts.append(f"spans={', '.join(trace.source_span_ids)}")
    if trace.source_section_id:
        parts.append(f"section={trace.source_section_id}")
    if trace.source_packet_id:
        parts.append(f"packet={trace.source_packet_id}")
    if not parts:
        return ""
    return " -- " + "; ".join(parts)


def _trace_sort_key(trace: TraceRecord) -> tuple[str, str, tuple[str, ...]]:
    return (trace.target_ref, trace.relation, tuple(trace.source_span_ids))
