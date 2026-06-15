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

_WORKER_PROMOTION_SLOT_ORDER: tuple[str, ...] = (
    "promotion_input_contract",
    "promotion_output_contract",
    "promotion_invocation_point",
    "promotion_result_handoff",
)

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
    lines.extend(_render_status(
        completeness,
        spl_text,
        diags,
        asms,
        trcs,
        a_warns,
        v_errs,
        v_warns,
    ))
    lines.append("")
    lines.extend(_render_materialized(trcs))
    lines.append("")
    lines.extend(_render_not_materialized(diags))
    lines.append("")
    lines.extend(_render_diagnostics(diags))
    lines.append("")
    lines.extend(_render_assumptions(asms, diags))
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
        for item in _grouped_diag_items(blocking):
            if isinstance(item, list):
                lines.extend(_render_worker_promotion_group(item, "status"))
            elif _is_child_worker_partial_definition_diag(item):
                target = f" on `{item.target_ref}`" if item.target_ref else ""
                lines.append(
                    f"- `type_or_contract_ambiguity`{target}: "
                    "Partial child worker definition can render, but its "
                    "contract/invocation details are incomplete."
                )
            else:
                target = f" on `{item.target_ref}`" if item.target_ref else ""
                lines.append(f"- `{item.kind}`{target}: {item.message}")
    elif completeness == "complete":
        lines.append("No completion-blocking diagnostic was emitted.")
    else:
        lines.append(
            "The result is not complete; inspect diagnostics and validation "
            "sections below."
        )

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

    # R10 Phase 6: "Delegation Intents" replaced by "Source Signals"
    for group in [
        "Workers",
        "Flows",
        "Steps",
        "Variables",
        "Constraints",
        "Handoffs",
        "Source Signals",
        "Other",
    ]:
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

    for item in _grouped_diag_items(partial_diags):
        if isinstance(item, list):
            lines.extend(_render_worker_promotion_group(item, "partial"))
            continue
        target = f"`{item.target_ref}`" if item.target_ref else "affected element"
        if _is_child_worker_partial_definition_diag(item):
            lines.append(
                f"- {target}: `type_or_contract_ambiguity` -- "
                "Partial child worker definition kept renderable; no "
                "executable worker invocation is invented for missing "
                "contract details."
            )
            if item.suggested_resolution:
                lines.append(f"  - Suggested resolution: {item.suggested_resolution}")
            continue
        lines.append(f"- {target}: `{item.kind}` -- {item.message}")
        if item.suggested_resolution:
            lines.append(f"  - Suggested resolution: {item.suggested_resolution}")
    return lines


def _render_diagnostics(diagnostics: list[CompileDiagnostic]) -> list[str]:
    lines = ["## 4. Diagnostics", ""]
    if not diagnostics:
        lines.append("No compile diagnostics.")
        return lines

    for item in _grouped_diag_items(diagnostics):
        if isinstance(item, list):
            lines.extend(_render_worker_promotion_group(item, "diagnostics"))
            lines.append("")
            continue
        d = item
        lines.append(f"### {d.diagnostic_id}: `{d.kind}`")
        lines.append(f"- Severity: `{d.severity}`")
        if d.target_ref:
            lines.append(f"- Target: `{d.target_ref}`")
        if d.source_span_ids:
            lines.append(f"- Source spans: `{', '.join(d.source_span_ids)}`")
        lines.append(f"- Message: {d.message}")
        if _is_child_worker_partial_definition_diag(d):
            lines.append(
                "- Definition status: child worker skeleton is renderable; "
                "worker invocation remains incomplete."
            )
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


def _render_assumptions(
    assumptions: list[CompileAssumption],
    diagnostics: list[CompileDiagnostic] | None = None,
) -> list[str]:
    lines = ["## 5. Assumptions / Suggestions", ""]
    if not assumptions:
        lines.append("No report-only assumptions were generated.")
        return lines

    diag_group_by_id: dict[str, tuple[str, tuple[str, ...]]] = {}
    promotion_groups = _group_worker_promotion_diags(diagnostics or [])
    for key, group in promotion_groups.items():
        if len(group) <= 1:
            continue
        for diag in group:
            diag_group_by_id[diag.diagnostic_id] = key

    assumptions_by_diag_id = {
        a.related_diagnostic_id: a
        for a in assumptions
        if a.related_diagnostic_id
    }
    rendered_groups: set[tuple[str, tuple[str, ...]]] = set()

    for a in sorted(assumptions, key=lambda x: x.assumption_id):
        group_key = (
            diag_group_by_id.get(a.related_diagnostic_id)
            if a.related_diagnostic_id
            else None
        )
        if group_key is not None:
            if group_key in rendered_groups:
                continue
            rendered_groups.add(group_key)
            group = promotion_groups[group_key]
            grouped_asms = [
                assumptions_by_diag_id[d.diagnostic_id]
                for d in _sort_worker_promotion_group(group)
                if d.diagnostic_id in assumptions_by_diag_id
            ]
            if grouped_asms:
                assumption_ids = ", ".join(a.assumption_id for a in grouped_asms)
                diagnostic_ids = ", ".join(a.related_diagnostic_id or "" for a in grouped_asms)
                target = group[0].target_ref or "worker promotion"
                lines.append(
                    f"- `{assumption_ids}` for `{target}`: "
                    "Worker promotion has an incomplete contract."
                )
                lines.append(
                    "  - Reason: The candidate is blocked by multiple "
                    "missing promotion slots."
                )
                lines.append(
                    "  - Suggested resolution: Provide the missing input/output "
                    "contracts, invocation point, and result handoff details "
                    "listed in the related diagnostics."
                )
                lines.append(f"  - Related diagnostics: `{diagnostic_ids}`")
                continue

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
            "Exception conditions without handler action stay as partial "
            "exception flows; no handler command is invented.",
        ),
        (
            "missing_output_producer",
            "Required outputs without a source-backed producer stay in the "
            "contract; no synthetic producer command is invented.",
        ),
        (
            "type_or_contract_ambiguity",
            "Unresolved worker/API contracts are reported as ambiguity; they "
            "are not downgraded to generic commands.",
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


def _is_worker_promotion_slot_diag(diagnostic: CompileDiagnostic) -> bool:
    missing_slot = diagnostic.missing_slot
    return (
        diagnostic.kind == "type_or_contract_ambiguity"
        and bool(diagnostic.target_ref)
        and diagnostic.target_ref.startswith("worker_promotion:")
        and missing_slot is not None
        and missing_slot.slot_name in _WORKER_PROMOTION_SLOT_ORDER
    )


def _is_child_worker_partial_definition_diag(diagnostic: CompileDiagnostic) -> bool:
    irs_ref = diagnostic.metadata.get("irs_ref")
    if not isinstance(irs_ref, dict):
        return False
    return (
        diagnostic.kind == "type_or_contract_ambiguity"
        and irs_ref.get("construct_type") == "CHILD_WORKER"
        and not diagnostic.blocks_rendering
        and diagnostic.blocks_completion
    )


def _worker_promotion_group_key(
    diagnostic: CompileDiagnostic,
) -> tuple[str, tuple[str, ...]]:
    return (
        diagnostic.target_ref or "",
        tuple(sorted(diagnostic.source_span_ids)),
    )


def _group_worker_promotion_diags(
    diagnostics: list[CompileDiagnostic],
) -> dict[tuple[str, tuple[str, ...]], list[CompileDiagnostic]]:
    groups: dict[tuple[str, tuple[str, ...]], list[CompileDiagnostic]] = defaultdict(list)
    for diagnostic in diagnostics:
        if _is_worker_promotion_slot_diag(diagnostic):
            groups[_worker_promotion_group_key(diagnostic)].append(diagnostic)
    return groups


def _grouped_diag_items(
    diagnostics: list[CompileDiagnostic],
) -> list[CompileDiagnostic | list[CompileDiagnostic]]:
    groups = _group_worker_promotion_diags(diagnostics)
    grouped_ids = {
        diagnostic.diagnostic_id
        for group in groups.values()
        if len(group) > 1
        for diagnostic in group
    }
    items: list[CompileDiagnostic | list[CompileDiagnostic]] = []
    emitted_groups: set[tuple[str, tuple[str, ...]]] = set()

    for diagnostic in _sort_diags(diagnostics):
        if diagnostic.diagnostic_id not in grouped_ids:
            items.append(diagnostic)
            continue
        key = _worker_promotion_group_key(diagnostic)
        if key in emitted_groups:
            continue
        emitted_groups.add(key)
        items.append(_sort_worker_promotion_group(groups[key]))
    return items


def _sort_worker_promotion_group(
    diagnostics: list[CompileDiagnostic],
) -> list[CompileDiagnostic]:
    slot_order = {
        slot_name: index
        for index, slot_name in enumerate(_WORKER_PROMOTION_SLOT_ORDER)
    }
    return sorted(
        diagnostics,
        key=lambda d: (
            slot_order.get(d.missing_slot.slot_name if d.missing_slot else "", 99),
            d.diagnostic_id,
        ),
    )


def _render_worker_promotion_group(
    diagnostics: list[CompileDiagnostic],
    section: str,
) -> list[str]:
    group = _sort_worker_promotion_group(diagnostics)
    first = group[0]
    target = first.target_ref or "worker promotion"
    source_spans = sorted(first.source_span_ids)
    lines: list[str] = []

    if section == "status":
        lines.append(
            f"- `type_or_contract_ambiguity` on `{target}`: "
            "WORKER_PROMOTION blocked by missing promotion slots."
        )
        for diagnostic in group:
            lines.append(_promotion_slot_line(diagnostic, indent="  "))
        return lines

    if section == "partial":
        lines.append(
            f"- `{target}`: `type_or_contract_ambiguity` -- "
            "WORKER_PROMOTION blocked by missing promotion slots."
        )
        if source_spans:
            lines.append(f"  - Source spans: `{', '.join(source_spans)}`")
        for diagnostic in group:
            lines.append(_promotion_slot_line(diagnostic, indent="  "))
        return lines

    lines.append(f"### grouped:{target}: `type_or_contract_ambiguity`")
    lines.append("- Severity: `warning`")
    lines.append(f"- Target: `{target}`")
    if source_spans:
        lines.append(f"- Source spans: `{', '.join(source_spans)}`")
    lines.append("- Message: WORKER_PROMOTION blocked by missing promotion slots.")
    lines.append("- Blocks rendering: `false`")
    lines.append(
        f"- Blocks completion: `{str(any(d.blocks_completion for d in group)).lower()}`"
    )
    lines.append("- Missing slots:")
    for diagnostic in group:
        lines.append(_promotion_slot_line(diagnostic, indent="  "))
        lines.append(f"    - Diagnostic: `{diagnostic.diagnostic_id}`")
    return lines


def _promotion_slot_line(diagnostic: CompileDiagnostic, indent: str) -> str:
    missing_slot = diagnostic.missing_slot
    slot_name = missing_slot.slot_name if missing_slot else "unknown"
    reason = missing_slot.reason if missing_slot else diagnostic.message
    return f"{indent}- `{slot_name}`: {reason}"


def _trace_group(target_ref: str) -> str:
    if target_ref.startswith("worker:"):
        return "Workers"
    if (
        target_ref.startswith("flow:")
        or ".exception_flow:" in target_ref
        or target_ref.startswith("exception_flow:")
    ):
        return "Flows"
    if target_ref.startswith("step:"):
        return "Steps"
    if ".variable:" in target_ref or target_ref.startswith("variable:"):
        return "Variables"
    if target_ref.startswith("constraint:"):
        return "Constraints"
    if target_ref.startswith("handoff:"):
        return "Handoffs"
    # R10 Phase 6: delegation_intent:* is no longer a construct/diagnostic
    # target.  Source-signal traces use source_signal:delegation_intent: prefix.
    if target_ref.startswith("source_signal:delegation_intent:"):
        return "Source Signals"
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
