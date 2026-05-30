"""Stage 3: AmbiguityResolver - Resolve ambiguous spans."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


def _find_parent_span(parent_id: str | None, spans: list[SpanIR]) -> SpanIR | None:
    if not parent_id:
        return None
    for s in spans:
        if s.span_id == parent_id:
            return s
    return None


def _derive_child_annotation(
    parent_ann: RouteAnnotation,
    child_span_id: str,
    child_field: str,
) -> RouteAnnotation:
    """Derive a child annotation from a parent, adjusting field/semantics."""
    ann = RouteAnnotation(
        span_id=child_span_id,
        field=child_field,
        semantic_role=parent_ann.semantic_role,
        route_family=parent_ann.route_family,
        source_section_id=parent_ann.source_section_id,
        source_packet_id=parent_ann.source_packet_id,
        source_hint_ids=list(parent_ann.source_hint_ids),
        construct_target=parent_ann.construct_target,
        slot_target=parent_ann.slot_target,
        executable=parent_ann.executable,
        primary=parent_ann.primary,
        diagnostics=list(parent_ann.diagnostics),
        metadata=dict(parent_ann.metadata),
    )
    # Apply field-derived overrides per F4 table
    preserve_non_executable = (
        parent_ann.executable is False
        and (
            parent_ann.semantic_role in ("failure_mode", "delegation_intent")
            or parent_ann.route_family == "delegation_boundary"
            or (
                parent_ann.construct_target == "EXCEPTION_FLOW"
                and parent_ann.slot_target == "condition"
            )
        )
    )
    if child_field == "rules":
        ann.semantic_role = "constraint"
        ann.executable = False
    elif child_field == "behavior" and not preserve_non_executable:
        ann.semantic_role = parent_ann.semantic_role or "process_step"
        ann.executable = True
    elif child_field == "domain":
        ann.executable = False
    elif child_field in ("identity", "audience", "integrations"):
        ann.executable = False
    return ann


class AmbiguityResolver(
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR, list[dict[str, Any]]],
        tuple[list[SpanIR], FieldRouteIR],
    ]
):
    """Resolve ambiguous spans by splitting them.

    This stage takes spans that were marked as ambiguous in Stage 2
    and splits them into multiple unambiguous sub-spans.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage3_ambiguity_resolver"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR, list[dict[str, Any]]]
    ) -> tuple[list[SpanIR], FieldRouteIR]:
        """Execute ambiguity resolution.

        Args:
            input_data: Tuple of (spans, routes, ambiguity_updates)

        Returns:
            Tuple of (resolved_spans, resolved_routes)

        Raises:
            StageError: If resolution fails
        """
        spans, routes, ambiguity_updates = input_data

        self.logger.info("Starting ambiguity resolution for %d spans", len(spans))

        # If no ambiguity updates, return as-is
        if not ambiguity_updates:
            self.logger.info("No ambiguity updates, returning original spans")
            return spans, routes

        # 1. Build prompts
        spans_json = json.dumps([s.to_dict() for s in spans], ensure_ascii=False, indent=2)
        routes_json = json.dumps(asdict(routes), ensure_ascii=False, indent=2)
        ambiguity_json = json.dumps(ambiguity_updates, ensure_ascii=False, indent=2)

        system_prompt = load_prompt("stage3")
        user_prompt = f"""The spans below are marked ambiguous. Split each into
unambiguous sub-spans.

Original spans:
---
{spans_json}
---

Current routes:
---
{routes_json}
---

Ambiguous spans:
---
{ambiguity_json}
---

Output valid JSON:"""

        # 2. Call LLM
        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise StageError(
                message=f"LLM call failed in {self.name}: {e}",
                stage=self.name,
            ) from e

        # 3. Parse result
        resolved_spans_data = result.get("resolved_spans", [])
        resolved_routes_data = result.get("resolved_routes", {})

        # 4. Create new spans for resolved ambiguities, inheriting provenance
        new_spans = []
        for span_data in resolved_spans_data:
            try:
                parent_id = span_data.get("parent_span_id")
                parent = _find_parent_span(parent_id, spans)

                # ── Sub-span ID: suffix strategy (s5 → s5a, s5b, ...) ──────
                # Avoids collision with Stage 1's global renumbering.
                if parent:
                    existing_children = sum(
                        1 for s in new_spans
                        if s.span_id.startswith(parent.span_id)
                        and len(s.span_id) == len(parent.span_id) + 1
                    )
                    child_id = (
                        f"{parent.span_id}{chr(ord('a') + existing_children)}"
                    )
                else:
                    child_id = span_data["span_id"]  # fallback: use LLM value

                span = SpanIR(
                    span_id=child_id,
                    text=span_data["text"],
                    source_section_id=(
                        span_data.get("source_section_id")
                        or (parent.source_section_id if parent else None)
                    ),
                    source_packet_id=(
                        span_data.get("source_packet_id")
                        or (parent.source_packet_id if parent else None)
                    ),
                    # Inherit section_context and is_placeholder from parent
                    section_context=(
                        span_data.get("section_context")
                        or (parent.section_context if parent else None)
                    ),
                    is_placeholder=(
                        parent.is_placeholder if parent else False
                    ),
                )
                new_spans.append(span)
            except KeyError as e:
                self.logger.warning("Missing field in resolved span data: %s", e)
                continue
            except ValueError as e:
                self.logger.warning("Invalid resolved span data: %s", e)
                continue

        # 5. Merge spans: remove original ambiguous spans, add new resolved spans
        ambiguous_ids = {u.get("span_id") for u in ambiguity_updates if u.get("span_id")}
        resolved_spans = []
        for span in spans:
            if span.span_id not in ambiguous_ids:
                resolved_spans.append(span)
        resolved_spans.extend(new_spans)

        # 6. Create resolved routes with preserved and derived annotations
        resolved_routes = FieldRouteIR(
            identity=resolved_routes_data.get("identity", []),
            audience=resolved_routes_data.get("audience", []),
            rules=resolved_routes_data.get("rules", []),
            domain=resolved_routes_data.get("domain", []),
            integrations=resolved_routes_data.get("integrations", []),
            behavior=resolved_routes_data.get("behavior", []),
        )
        # Preserve annotations for non-ambiguous spans
        ambiguous_span_ids = {u.get("span_id") for u in ambiguity_updates if u.get("span_id")}
        resolved_routes.annotations = [
            a for a in routes.annotations if a.span_id not in ambiguous_span_ids
        ]
        # Derive annotations for split children from parent annotations
        parent_by_span_id = {s.span_id: s for s in spans}
        for child in new_spans:
            parent_span_id = next(
                (sd.get("parent_span_id") for sd in resolved_spans_data
                 if sd.get("span_id") == child.span_id),
                None,
            )
            if not parent_span_id:
                continue
            parent_anns = routes.get_annotations(parent_span_id)
            if not parent_anns:
                continue
            child_field = resolved_routes.get_field_for_span(child.span_id) or "behavior"
            for parent_ann in parent_anns:
                child_ann = _derive_child_annotation(parent_ann, child.span_id, child_field)
                resolved_routes.annotations.append(child_ann)

        # 7. Validate no overlap in resolved routes
        overlaps = resolved_routes.validate_no_overlap()
        if overlaps:
            self.logger.warning("Overlapping spans in resolved routes: %s", overlaps)

        # 8. Log resolution summary
        self.logger.info(
            "Ambiguity resolution complete: %d original spans -> %d resolved spans",
            len(spans),
            len(resolved_spans),
        )

        # 9. Save checkpoint
        self.save_checkpoint({
            "original_spans_count": len(spans),
            "resolved_spans_count": len(resolved_spans),
            "resolved_spans": [s.to_dict() for s in resolved_spans],
            "resolved_routes": asdict(resolved_routes),
            "overlaps": overlaps,
        })

        return resolved_spans, resolved_routes
