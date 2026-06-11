"""Stage 3: AmbiguityResolver - Resolve ambiguous spans."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from nl2spl.compiler.annotation_role_contract.normalize import (
    normalize_annotation_from_role,
)
from nl2spl.compiler.annotation_role_contract.registry import (
    ROLE_CONTRACT_REGISTRY,
)
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
    """Derive a child annotation from a parent, preserving semantic_role.

    ARC: ``semantic_role`` is the primary semantic authority.  Field-driven
    overrides are removed.  The annotation's ``field`` is contract-derived
    from the parent (not overwritten by ``child_field``, which only affects
    legacy route lists).
    """
    return RouteAnnotation(
        span_id=child_span_id,
        field=parent_ann.field,  # contract-derived, not route field
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

        # 4. Only process children whose parent was marked ambiguous in Stage 2.
        # LLM may return extra resolved_spans for non-ambiguous parents; skip them.
        ambiguous_ids = {u.get("span_id") for u in ambiguity_updates if u.get("span_id")}

        new_spans = []
        for span_data in resolved_spans_data:
            parent_id = span_data.get("parent_span_id")
            parent = _find_parent_span(parent_id, spans)
            # Only accept children whose parent was marked ambiguous in Stage 2.
            # LLM may fabricate children for non-ambiguous parents; skip them.
            if parent and parent_id and parent_id not in ambiguous_ids:
                continue  # parent exists but not ambiguous — skip LLM extra child
            try:
                # -- Sub-span ID: suffix strategy (s5 -> s5a, s5b, ...) -------
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

                # System provenance is authoritative; LLM is fallback only.
                child_sid = (parent.source_section_id if parent else None) or span_data.get("source_section_id")
                child_pid = (parent.source_packet_id if parent else None) or span_data.get("source_packet_id")
                span = SpanIR(
                    span_id=child_id,
                    text=span_data["text"],
                    source_section_id=child_sid,
                    source_packet_id=child_pid,
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
        # Derive annotations for split children.
        #
        # Priority order (ARC contract):
        #   1. PRIMARY: split recommendation segment's structured semantic_role
        #      -> normalize_annotation_from_role() -> _derive_child_annotation()
        #      Segment role is the LLM's authoritative judgment about what
        #      each child IS.  Parent annotation is NOT authoritative for
        #      children because the whole point of splitting is that the
        #      parent contained mixed semantics.
        #   2. FALLBACK: parent annotation inheritance --- only when the
        #      corresponding segment has no usable semantic_role.
        #      Diagnostic must be recorded.
        parent_by_span_id = {s.span_id: s for s in spans}

        # Build split recommendation segment index.
        # Maps parent_span_id -> segments[] from ambiguity_updates
        # split_recommendation.
        _split_by_parent: dict[str, list[dict[str, Any]]] = {}
        for au in ambiguity_updates:
            sr = au.get("split_recommendation", {})
            if sr:
                segments = sr.get("segments", [])
                pid = sr.get("parent_span_id") or au.get("span_id")
                if pid and segments:
                    _split_by_parent[pid] = segments

        # Positional segment index per parent (LLM produces children in
        # the same order as split recommendation segments).
        _parent_seg_index: dict[str, int] = {}

        # Collect fallback diagnostics for route-level visibility (P2).
        _fallback_diags: list[str] = []

        for child in new_spans:
            parent_span_id = next(
                (sd.get("parent_span_id") for sd in resolved_spans_data
                 if sd.get("span_id") == child.span_id),
                None,
            )
            if not parent_span_id:
                continue
            parent_anns = routes.get_annotations(parent_span_id)
            child_field = resolved_routes.get_field_for_span(child.span_id) or "behavior"

            # -- Step 1: try split segment semantic_role (PRIMARY) ----------
            segments = _split_by_parent.get(parent_span_id)
            seg_role: str | None = None
            seg_raw: dict[str, Any] = {}
            if segments:
                idx = _parent_seg_index.get(parent_span_id, 0)
                if idx < len(segments):
                    seg_raw = segments[idx]
                    _parent_seg_index[parent_span_id] = idx + 1
                    seg_role = seg_raw.get("semantic_role")

            if seg_role:
                # Validate segment role before calling normalize.
                resolved_role = ROLE_CONTRACT_REGISTRY.resolve_semantic_role(seg_role)
                if resolved_role is None:
                    # Unknown segment role --- diagnostic, try parent fallback.
                    msg = (
                        f"Stage 3: split child '{child.span_id}' "
                        f"(parent '{parent_span_id}') segment has unknown "
                        f"semantic_role '{seg_role}'; falling back to "
                        f"parent annotation if available."
                    )
                    self.logger.warning(msg)
                    _fallback_diags.append(msg)
                    # Fall through to parent fallback below.
                else:
                    # PRIMARY PATH: canonical annotation from segment role.
                    result = normalize_annotation_from_role(
                        span_id=child.span_id,
                        semantic_role=resolved_role,
                        source_section_id=child.source_section_id,
                        source_packet_id=child.source_packet_id,
                        raw_construct_target=seg_raw.get("construct_target"),
                        raw_slot_target=seg_raw.get("slot_target"),
                        raw_executable=seg_raw.get("executable"),
                    )
                    # Use the normalized annotation directly --- the
                    # canonical role contract already derived all fields.
                    # child_field only affects legacy route lists, not
                    # the annotation's canonical contract-derived field.
                    child_ann = result.annotation
                    child_ann = RouteAnnotation(
                        span_id=child.span_id,
                        field=child_ann.field,  # contract-derived
                        semantic_role=child_ann.semantic_role,
                        route_family=child_ann.route_family,
                        source_section_id=child_ann.source_section_id,
                        source_packet_id=child_ann.source_packet_id,
                        source_hint_ids=list(child_ann.source_hint_ids),
                        construct_target=child_ann.construct_target,
                        slot_target=child_ann.slot_target,
                        executable=child_ann.executable,
                        primary=child_ann.primary,
                        diagnostics=list(child_ann.diagnostics),
                        metadata=dict(child_ann.metadata),
                    )
                    resolved_routes.annotations.append(child_ann)
                    continue  # segment role used --- done for this child

            # -- Step 2: parent annotation fallback -------------------------
            # Only reached when:
            #   - No split recommendation segments for this parent, OR
            #   - Segment has no semantic_role, OR
            #   - Segment semantic_role is unknown (not in registry).
            if parent_anns:
                msg = (
                    f"Stage 3: split child '{child.span_id}' "
                    f"(parent '{parent_span_id}') falling back to parent "
                    f"annotation inheritance --- segment semantic_role is "
                    f"missing, unknown, or unavailable."
                )
                self.logger.warning(msg)
                _fallback_diags.append(msg)
                for parent_ann in parent_anns:
                    child_ann = _derive_child_annotation(
                        parent_ann, child.span_id, child_field,
                    )
                    resolved_routes.annotations.append(child_ann)
            else:
                msg = (
                    f"Stage 3: split child '{child.span_id}' "
                    f"(parent '{parent_span_id}') has no segment "
                    f"semantic_role and no parent annotations; skipping."
                )
                self.logger.warning(msg)
                _fallback_diags.append(msg)

        # P2: surface fallback diagnostics in route artifacts, not just logs.
        if _fallback_diags:
            resolved_routes.route_diagnostics.extend(_fallback_diags)

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
