"""PromptBuilderMixin for Stage 3.5 WorkerBoundaryPlanner."""

from __future__ import annotations

from typing import Any

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR


class PromptBuilderMixin:
    """Mixin providing prompt construction methods."""

    def _build_user_prompt(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None,
    ) -> str:
        return f"""Plan worker boundaries before flow assembly.

Resolved spans:
---
{self._format_spans(spans)}
---

Field routes:
---
{self._format_routes(routes)}
---

Adapter metadata:
---
{self._format_adapter_metadata(canonical_input)}
---

Return JSON only. Use span_id values in source_span_ids and owned_span_ids."""

    def _format_spans(self, spans: list[SpanIR]) -> str:
        if not spans:
            return "(none)"
        lines = []
        for span in spans:
            provenance = []
            if span.source_section_id:
                provenance.append(f"section={span.source_section_id}")
            if span.source_packet_id:
                provenance.append(f"packet={span.source_packet_id}")
            suffix = f" ({', '.join(provenance)})" if provenance else ""
            lines.append(f"{span.span_id}: {span.text}{suffix}")
        return "\n".join(lines)

    def _format_routes(self, routes: FieldRouteIR) -> str:
        route_names = ["identity", "audience", "rules", "domain", "integrations", "behavior"]
        return "\n".join(
            f"{name}: {', '.join(getattr(routes, name)) or '(none)'}" for name in route_names
        )

    def _format_adapter_metadata(self, canonical_input: CanonicalCompileInput | None) -> str:
        if canonical_input is None:
            return "(none)"

        lines: list[str] = [
            f"schema: {canonical_input.source_schema} {canonical_input.schema_version}",
        ]
        if canonical_input.raw_sections:
            lines.append("section index:")
            lines.extend(
                f"- {section.section_id}: {section.canonical_title}"
                for section in canonical_input.raw_sections
            )
        if canonical_input.hard_facts.inputs:
            lines.append("hard inputs:")
            lines.extend(
                f"- {fact.name}: {fact.data_type}, required={fact.required}, "
                f"section={fact.source_section_id}, {fact.description}"
                for fact in canonical_input.hard_facts.inputs
            )
        if canonical_input.hard_facts.outputs:
            lines.append("hard outputs:")
            lines.extend(
                f"- {fact.name}: {fact.data_type}, required={fact.required}, "
                f"section={fact.source_section_id}, {fact.description}"
                for fact in canonical_input.hard_facts.outputs
            )
        if canonical_input.hard_facts.failure_modes:
            lines.append("failure modes:")
            lines.extend(
                f"- {fact.name}: section={fact.source_section_id}, "
                f"text={self._compact_text(fact.text)}"
                for fact in canonical_input.hard_facts.failure_modes
            )
        self._append_hints(
            lines,
            "process hints",
            canonical_input.compile_hints.process_hints,
        )
        self._append_hints(
            lines,
            "constraint hints",
            canonical_input.compile_hints.constraint_hints,
        )
        self._append_hints(
            lines,
            "flow hints",
            canonical_input.compile_hints.flow_hints,
        )
        self._append_hints(
            lines,
            "delegation hints",
            canonical_input.compile_hints.delegation_hints,
        )
        return "\n".join(lines) if lines else "(none)"

    def _append_hints(self, lines: list[str], label: str, hints: list[Any]) -> None:
        if not hints:
            return
        lines.append(f"{label}:")
        for hint in hints:
            parts = [
                f"section={hint.source_section_id}",
                f"target={hint.target}",
                f"kind={hint.suggested_kind}",
                f"flow={hint.suggested_flow}",
            ]
            if hint.suggested_block_type:
                parts.append(f"block={hint.suggested_block_type}")
            if hint.suggested_step_type:
                parts.append(f"step={hint.suggested_step_type}")
            if hint.suggested_condition:
                parts.append(f"condition={self._compact_text(hint.suggested_condition)}")
            if hint.suggested_worker_name:
                parts.append(f"worker={hint.suggested_worker_name}")
            if hint.metadata:
                metadata = ", ".join(
                    f"{key}={self._compact_text(str(value), max_chars=80)}"
                    for key, value in sorted(hint.metadata.items())
                )
                parts.append(f"metadata=[{metadata}]")
            if hint.text:
                parts.append(f"text={self._compact_text(hint.text)}")
            lines.append("- " + ", ".join(parts))

    def _compact_text(self, text: str, max_chars: int = 160) -> str:
        compact = " ".join(text.split())
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 3].rstrip() + "..."
