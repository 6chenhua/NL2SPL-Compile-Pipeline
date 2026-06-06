"""PromptBuilderMixin for Stage 3.5 WorkerBoundaryPlanner."""

from __future__ import annotations

from typing import Any

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import CandidateTaskUnitIR


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

    def _build_candidate_prompt(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None,
    ) -> str:
        if routes.annotations:
            exec_ids = routes.get_executable_behavior_span_ids()
            non_exec_ids = routes.get_non_executable_behavior_span_ids()
            exec_section = (
                "Executable behavior spans (candidate source_span_ids):\n"
                f"---\n{self._format_route_spans(spans, exec_ids)}\n---"
            )
            ctx_section = ""
            if non_exec_ids:
                ctx_section = (
                    "\nNon-executable context (failure conditions, "
                    "delegation boundaries — NOT task unit candidates):\n"
                    f"---\n{self._format_route_spans(spans, non_exec_ids)}\n---"
                )
            non_beh = self._format_non_behavior_context(spans, routes)
            return (
                f"Discover candidate task units before worker-boundary decisions.\n\n"
                f"{exec_section}\n"
                f"{ctx_section}\n"
                f"Non-behavior context:\n---\n{non_beh}\n---\n\n"
                f"Adapter metadata:\n---\n"
                f"{self._format_adapter_metadata(canonical_input)}\n---\n\n"
                f"Return JSON only with a top-level \"candidates\" array.\n"
                f"Do not output workers, handoffs, decisions, flow, blocks, steps, or SPL."
            )
        return f"""Discover candidate task units before worker-boundary decisions.

Behavior spans available for candidate source_span_ids:
---
{self._format_route_spans(spans, routes.behavior)}
---

Non-behavior context:
---
{self._format_non_behavior_context(spans, routes)}
---

Adapter metadata:
---
{self._format_adapter_metadata(canonical_input)}
---

Return JSON only with a top-level "candidates" array.
Do not output workers, handoffs, decisions, flow, blocks, steps, or SPL."""

    def _build_decision_prompt(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None,
        candidates: list[CandidateTaskUnitIR],
    ) -> str:
        if routes.annotations:
            exec_ids = routes.get_executable_behavior_span_ids()
            non_exec_ids = routes.get_non_executable_behavior_span_ids()
            exec_section = (
                "Executable behavior span context:\n"
                f"---\n{self._format_route_spans(spans, exec_ids)}\n---"
            )
            ctx_section = ""
            if non_exec_ids:
                ctx_section = (
                    "\nNon-executable context (failure conditions, "
                    "delegation boundaries):\n"
                    f"---\n{self._format_route_spans(spans, non_exec_ids)}\n---"
                )
            return (
                f"Decide worker boundaries for candidate task units.\n\n"
                f"Candidates to decide:\n---\n"
                f"{self._format_candidates(candidates)}\n---\n\n"
                f"{exec_section}\n"
                f"{ctx_section}\n"
                f"Adapter metadata:\n---\n"
                f"{self._format_adapter_metadata(canonical_input)}\n---\n\n"
                f"Return JSON only with a top-level \"decisions\" array.\n"
                f"Return exactly one decision for every candidate_id listed above.\n"
                f"Do not output workers, handoffs, flow, blocks, steps, or SPL."
            )
        return f"""Decide worker boundaries for candidate task units.

Candidates to decide:
---
{self._format_candidates(candidates)}
---

Behavior span context:
---
{self._format_route_spans(spans, routes.behavior)}
---

Adapter metadata:
---
{self._format_adapter_metadata(canonical_input)}
---

Return JSON only with a top-level "decisions" array.
Return exactly one decision for every candidate_id listed above.
Do not output workers, handoffs, flow, blocks, steps, or SPL."""

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

    def _format_route_spans(self, spans: list[SpanIR], span_ids: list[str]) -> str:
        span_by_id = {span.span_id: span for span in spans}
        selected = [span_by_id[span_id] for span_id in span_ids if span_id in span_by_id]
        return self._format_spans(selected)

    def _format_non_behavior_context(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
    ) -> str:
        context_ids: list[str] = []
        for route_name in ("rules", "domain", "integrations", "identity", "audience"):
            context_ids.extend(getattr(routes, route_name))
        return self._format_route_spans(spans, context_ids)

    def _format_candidates(self, candidates: list[CandidateTaskUnitIR]) -> str:
        if not candidates:
            return "(none)"
        lines: list[str] = []
        for candidate in candidates:
            lines.append(
                "- "
                f"{candidate.candidate_id}: spans={candidate.source_span_ids}; "
                f"kind={candidate.candidate_kind}; purpose={candidate.purpose}; "
                f"inputs={[field.name for field in candidate.possible_inputs]}; "
                f"outputs={[field.name for field in candidate.possible_outputs]}; "
                f"signals={candidate.signals}; risks={candidate.risks}"
            )
        return "\n".join(lines)

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
