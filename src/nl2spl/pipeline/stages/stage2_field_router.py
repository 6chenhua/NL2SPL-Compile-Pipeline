"""Stage 2: FieldRouter - Route spans to semantic fields."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage
from nl2spl.pipeline.stages.stage2_field_router_prompt import (
    ALLOWED_CONSTRUCT_TARGETS,
    ALLOWED_FIELDS,
    ALLOWED_SEMANTIC_ROLES,
    ALLOWED_SLOT_TARGETS,
    NON_EXECUTABLE_ROLES,
    RefinedAnnotation,
    RouteRefinementResult,
    build_adapter_guided_user_prompt,
    parse_refinement_result,
)
from nl2spl.pipeline.stages.stage2_field_router_validator import (
    RouteRefinementValidator,
)


_ANNOTATION_SEMANTICS: dict[str, dict[str, Any]] = {
    "task_family": {
        "field": "domain", "semantic_role": "profile_domain", "executable": False,
    },
    "runtime_input": {
        "field": "resources", "semantic_role": "input_contract",
        "route_family": "resource_contract", "executable": False,
    },
    "required_output": {
        "field": "resources", "semantic_role": "output_contract",
        "route_family": "resource_contract", "executable": False,
    },
    "process_step": {
        "field": "behavior", "semantic_role": "process_step",
        "route_family": "flow_relevant", "executable": True,
    },
    "policy": {
        "field": "rules", "semantic_role": "constraint", "executable": False,
    },
    "failure_mode": {
        "field": "behavior", "semantic_role": "failure_mode",
        "route_family": "flow_relevant", "construct_target": "EXCEPTION_FLOW",
        "slot_target": "condition", "executable": False,
    },
    "delegation_rule": {
        "field": "behavior", "semantic_role": "delegation_intent",
        "route_family": "delegation_boundary", "executable": False,
    },
}

# Exact mapping from section_context (lowercase) to semantic field.
# Aligned with _ORGANIZATIONAL_TITLES in stage1_span_slicer.py.
# ⚠️ SYNC CONSTRAINT: Any change here must also update
# src/nl2spl/pipeline/stages/stage1_span_slicer.py (_ORGANIZATIONAL_TITLES)
# and prompts/stage1_system.txt (Rule 3 "Strip All Structural Markers").
_SECTION_CONTEXT_TO_FIELD: dict[str, str] = {
    "task family": "domain",
    "inputs for each run": "resources",
    "required outputs": "resources",
    "reusable process": "behavior",
    "policies": "rules",
    "failure handling": "behavior",
    "delegation policy": "behavior",
}


class FieldRouter(
    PipelineStage[
        list[SpanIR] | tuple[list[SpanIR], CanonicalCompileInput],
        tuple[FieldRouteIR, list[dict[str, Any]]],
    ]
):
    """Route spans to 6 semantic fields.

    This stage takes a list of spans and routes each span to one of 6 semantic fields:
    identity, audience, rules, domain, integrations, behavior.

    It also identifies ambiguous spans that need to be split in Stage 3.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage2_field_router"

    def execute(
        self, input_data: list[SpanIR] | tuple[list[SpanIR], CanonicalCompileInput]
    ) -> tuple[FieldRouteIR, list[dict[str, Any]]]:
        """Execute field routing.

        Args:
            input_data: List of spans to route

        Returns:
            Tuple of (FieldRouteIR, ambiguity_updates)

        Raises:
            StageError: If routing fails
        """
        canonical_input: CanonicalCompileInput | None = None
        if isinstance(input_data, tuple):
            spans, canonical_input = input_data
        else:
            spans = input_data
        self.logger.info("Starting field routing for %d spans", len(spans))

        if canonical_input is not None and canonical_input.source_schema != "generic_nl":
            return self._execute_canonical(spans, canonical_input)

        # 1. Build prompts
        spans_json = json.dumps([s.to_dict() for s in spans], ensure_ascii=False, indent=2)
        system_prompt = load_prompt("stage2")
        user_prompt = f"""Route each span below to one of 6 semantic fields.

---
{spans_json}
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
        routes_data = result.get("routes", {})
        ambiguity_updates = result.get("ambiguity_updates", [])

        # Create FieldRouteIR
        routes = FieldRouteIR(
            identity=routes_data.get("identity", []),
            audience=routes_data.get("audience", []),
            rules=routes_data.get("rules", []),
            domain=routes_data.get("domain", []),
            integrations=routes_data.get("integrations", []),
            behavior=routes_data.get("behavior", []),
        )

        # 4. Write back ambiguity info to spans
        for update in ambiguity_updates:
            span_id = update.get("span_id")
            if not span_id:
                self.logger.warning("Ambiguity update missing span_id: %s", update)
                continue

            # Find the span and update its ambiguity info
            for span in spans:
                if span.span_id == span_id:
                    span.ambiguity.is_ambiguous = update.get("is_ambiguous", False)
                    span.ambiguity.reasons = update.get("reasons", [])
                    span.ambiguity.needs_split = update.get("needs_split", False)
                    self.logger.debug("Updated ambiguity for span %s: %s", span_id, update)
                    break
            else:
                self.logger.warning("Span %s not found for ambiguity update", span_id)

        # 5. Validate no overlap
        overlaps = routes.validate_no_overlap()
        if overlaps:
            self.logger.warning("Overlapping spans detected: %s", overlaps)

        # 6. Log routing summary
        self.logger.info(
            "Routing complete: identity=%d, audience=%d, rules=%d, domain=%d, "
            "integrations=%d, behavior=%d",
            len(routes.identity),
            len(routes.audience),
            len(routes.rules),
            len(routes.domain),
            len(routes.integrations),
            len(routes.behavior),
        )

        # 7. Save checkpoint
        self.save_checkpoint({
            "routes": asdict(routes),
            "ambiguity_updates": ambiguity_updates,
            "overlaps": overlaps,
        })

        return routes, ambiguity_updates

    # =========================================================================
    # Canonical (structural NL) path
    # =========================================================================

    def _execute_canonical(
        self,
        spans: list[SpanIR],
        canonical_input: CanonicalCompileInput,
    ) -> tuple[FieldRouteIR, list[dict[str, Any]]]:
        """Route adapter-aware spans deterministically, optionally refined by LLM."""
        packets = {pkt.packet_id: pkt for pkt in canonical_input.semantic_packets}

        # 1. Build old-list routes and adapter-consumed markers (unchanged)
        routes = FieldRouteIR()
        adapter_consumed_spans: list[dict[str, str]] = []

        for span in spans:
            pkt = packets.get(span.source_packet_id or "")
            if pkt is None:
                self._route_section_span(span, routes, canonical_input)
            elif pkt.packet_type in {"runtime_input", "required_output"}:
                adapter_consumed_spans.append({
                    "span_id": span.span_id,
                    "reason": f"seeded_as_hard_fact_{pkt.packet_type}",
                })
            else:
                self._route_packet_span(span, pkt.packet_type, routes)

        # 2. Build annotations from deterministic priors
        priors = self._build_deterministic_priors(spans, canonical_input)

        # 3. LLM refinement (gated)
        route_diagnostics: list[str] = []
        llm_refinement_used = False
        split_recommendations: list[dict[str, Any]] = []

        if self._llm_refinement_enabled():
            llm_result = self._call_adapter_guided_llm(spans, canonical_input, priors)
            if llm_result is not None:
                priors, route_diagnostics, split_recommendations = (
                    self._merge_llm_refinement(priors, llm_result, spans, canonical_input)
                )
                llm_refinement_used = True
            else:
                route_diagnostics.append(
                    "adapter_guided_refinement_failed: LLM call failed; "
                    "fell back to deterministic priors."
                )

        # 4. Attach annotations and route diagnostics
        routes.annotations = priors
        routes.route_diagnostics = route_diagnostics
        routes.structured_route_diagnostics = _build_structured_diagnostics(
            route_diagnostics, llm_refinement_used, split_recommendations,
        )

        # 5. Convert split recommendations to ambiguity_updates for Stage 3
        ambiguity_updates: list[dict[str, Any]] = []
        for sr in split_recommendations:
            ambiguity_updates.append({
                "span_id": sr["parent_span_id"],
                "is_ambiguous": True,
                "reasons": [sr.get("reason", "LLM split recommendation")],
                "needs_split": True,
                "split_recommendation": sr,
            })

        # 6. Validate
        overlaps = routes.validate_no_overlap()
        if overlaps:
            self.logger.warning("Overlapping spans detected: %s", overlaps)

        # 6. Log
        self.logger.info(
            "Adapter routing complete: identity=%d, audience=%d, rules=%d, "
            "domain=%d, integrations=%d, behavior=%d, consumed=%d, "
            "annotations=%d, llm_refinement=%s",
            len(routes.identity),
            len(routes.audience),
            len(routes.rules),
            len(routes.domain),
            len(routes.integrations),
            len(routes.behavior),
            len(adapter_consumed_spans),
            len(priors),
            llm_refinement_used,
        )

        # 7. Checkpoint
        checkpoint: dict[str, Any] = {
            "routes": asdict(routes),
            "ambiguity_updates": ambiguity_updates,
            "overlaps": overlaps,
            "adapter_consumed_spans": adapter_consumed_spans,
            "llm_refinement": {
                "used": llm_refinement_used,
                "route_diagnostics": route_diagnostics,
                "split_recommendations": split_recommendations,
            },
        }
        self.save_checkpoint(checkpoint)

        return routes, ambiguity_updates

    # =========================================================================
    # Deterministic priors
    # =========================================================================

    def _build_deterministic_priors(
        self,
        spans: list[SpanIR],
        canonical_input: CanonicalCompileInput,
    ) -> list[RouteAnnotation]:
        """Build deterministic RouteAnnotations from packet_type + section mapping."""
        packets = {pkt.packet_id: pkt for pkt in canonical_input.semantic_packets}
        hint_indexes = self._build_hint_indexes(canonical_input.compile_hints)
        annotations: list[RouteAnnotation] = []

        for span in spans:
            packet = packets.get(span.source_packet_id or "")
            if packet is None:
                # Section-only span — derive field from section title
                field = self._section_field(span, canonical_input)
                annotations.append(RouteAnnotation(
                    span_id=span.span_id,
                    field=field,
                    source_section_id=span.source_section_id,
                ))
                continue

            if packet.packet_type in {"runtime_input", "required_output"}:
                annotations.append(
                    self._build_packet_annotation(span, packet, hint_indexes)
                )
                continue

            annotations.append(
                self._build_packet_annotation(span, packet, hint_indexes)
            )

        return annotations

    @staticmethod
    def _section_field(
        span: SpanIR,
        canonical_input: CanonicalCompileInput,
    ) -> str:
        """Derive semantic field for a span, with three priority levels.

        Priority 1: canonical source_section_id (structured, highest confidence)
        Priority 2: section_context exact match (LLM path, medium confidence)
        Priority 2b: section_context keyword fallback (low confidence)
        Priority 3: default "behavior"
        """
        # Priority 1: canonical structured ID
        if span.source_section_id:
            sections = {s.section_id: s for s in canonical_input.raw_sections}
            section = sections.get(span.source_section_id)
            if section is not None:
                if section.canonical_title == "task_family":
                    return "domain"
                if section.canonical_title in {"policies", "failure_handling"}:
                    return "rules"
                return "behavior"

        # Shortcut: placeholder spans → route by section_context directly
        if span.is_placeholder and span.section_context:
            ctx_lower = span.section_context.strip().lower()
            if ctx_lower in _SECTION_CONTEXT_TO_FIELD:
                return _SECTION_CONTEXT_TO_FIELD[ctx_lower]

        # Priority 2: section_context exact match
        if span.section_context:
            ctx_lower = span.section_context.strip().lower()
            if ctx_lower in _SECTION_CONTEXT_TO_FIELD:
                return _SECTION_CONTEXT_TO_FIELD[ctx_lower]
            # Priority 2b: keyword fallback
            if "input" in ctx_lower or "output" in ctx_lower:
                return "resources"
            if "policy" in ctx_lower or "rule" in ctx_lower or "constraint" in ctx_lower:
                return "rules"
            if "process" in ctx_lower or "step" in ctx_lower or "delegation" in ctx_lower:
                return "behavior"
            if "task" in ctx_lower or "family" in ctx_lower:
                return "domain"

        # Priority 3: default
        return "behavior"

    # =========================================================================
    # LLM refinement
    # =========================================================================

    def _llm_refinement_enabled(self) -> bool:
        """Check whether adapter-guided LLM refinement is enabled."""
        return bool(getattr(self.config, "enable_adapter_guided_fieldroute_llm", False))

    def _call_adapter_guided_llm(
        self,
        spans: list[SpanIR],
        canonical_input: CanonicalCompileInput,
        priors: list[RouteAnnotation],
    ) -> RouteRefinementResult | None:
        """Call the adapter-guided LLM and return parsed result, or None on failure."""
        try:
            system_prompt = load_prompt("stage2_adapter_guided")
            user_prompt = build_adapter_guided_user_prompt(
                spans, canonical_input, priors,
            )
            result_dict = self.client.call_json(
                stage_name="stage2_adapter_guided",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=4096,
            )
            return parse_refinement_result(result_dict)
        except Exception as exc:
            self.logger.warning(
                "Adapter-guided LLM refinement failed: %s. Falling back to "
                "deterministic priors.", exc,
            )
            return None

    def _merge_llm_refinement(
        self,
        priors: list[RouteAnnotation],
        llm_result: RouteRefinementResult,
        spans: list[SpanIR],
        canonical_input: CanonicalCompileInput | None = None,
    ) -> tuple[list[RouteAnnotation], list[str], list[dict[str, Any]]]:
        """Merge validated LLM annotations with deterministic priors.

        Runs the standalone RouteRefinementValidator first, then merges
        only accepted annotations.  If the validator triggers fallback,
        the deterministic priors are returned unchanged.

        Returns:
            (merged_annotations, route_diagnostics, split_recommendations)
        """
        route_diagnostics: list[str] = []
        valid_span_ids = {s.span_id for s in spans}

        # --- Step 0: standalone validator --------------------------------
        validator = RouteRefinementValidator()
        validated = validator.validate(llm_result, spans, canonical_input=canonical_input, priors=priors)

        # Collect validator diagnostics
        route_diagnostics.extend(validated.diagnostics)

        # If fallback triggered, return priors unchanged; discard LLM
        # split recommendations — they are from the same untrusted LLM output.
        if validated.fallback_triggered:
            route_diagnostics.append(
                "LLM split recommendations suppressed due to fallback."
            )
            return list(priors), route_diagnostics, []

        # --- Step 1: merge accepted annotations --------------------------

        # Build index: prior_by_sid[sid] = [list of RouteAnnotation]
        prior_by_sid: dict[str, list[RouteAnnotation]] = {}
        for a in priors:
            prior_by_sid.setdefault(a.span_id, []).append(a)

        # Work on a mutable list copy
        merged: list[RouteAnnotation] = list(priors)

        for llm_ann in validated.accepted:
            span_id = llm_ann.span_id

            # --- Validation: span must exist -----------------------------
            if span_id not in valid_span_ids:
                route_diagnostics.append(
                    f"LLM refinement rejected: unknown span_id '{span_id}'"
                )
                continue

            # --- Validation: field must be present and in allowed set ----
            field = llm_ann.field
            if field is None or field not in ALLOWED_FIELDS:
                route_diagnostics.append(
                    f"LLM refinement rejected: missing or invalid field "
                    f"'{field}' for span '{span_id}'"
                )
                continue

            # --- Validation: executable must be a bool -------------------
            executable = llm_ann.executable
            if not isinstance(executable, bool):
                route_diagnostics.append(
                    f"LLM refinement rejected: missing or malformed "
                    f"executable ({executable}) for span '{span_id}'"
                )
                continue

            # --- Enforce non-executable constraint -----------------------
            if llm_ann.semantic_role and llm_ann.semantic_role in NON_EXECUTABLE_ROLES:
                if executable:
                    route_diagnostics.append(
                        f"LLM refinement corrected: {llm_ann.semantic_role} "
                        f"must be non-executable, got executable=True "
                        f"for span '{span_id}'"
                    )
                    executable = False

            # --- Validation: allowed schema ------------------------------
            sem_role = llm_ann.semantic_role
            construct = llm_ann.construct_target
            slot = llm_ann.slot_target

            if sem_role is not None and sem_role not in ALLOWED_SEMANTIC_ROLES:
                route_diagnostics.append(
                    f"LLM refinement rejected: invalid semantic_role "
                    f"'{sem_role}' for span '{span_id}'"
                )
                continue

            if construct is not None and construct not in ALLOWED_CONSTRUCT_TARGETS:
                route_diagnostics.append(
                    f"LLM refinement rejected: invalid construct_target "
                    f"'{construct}' for span '{span_id}'"
                )
                continue

            if slot is not None and slot not in ALLOWED_SLOT_TARGETS:
                route_diagnostics.append(
                    f"LLM refinement rejected: invalid slot_target "
                    f"'{slot}' for span '{span_id}'"
                )
                continue

            # --- Merge: replace matching prior, or append new -------------
            # Matching key: (span_id, field, semantic_role, construct_target,
            # slot_target).  Same span with different construct/slot also
            # produces multi-label.
            replaced = False
            for i, existing in enumerate(merged):
                if (
                    existing.span_id == span_id
                    and existing.field == field
                    and existing.semantic_role == sem_role
                    and existing.construct_target == construct
                    and existing.slot_target == slot
                ):
                    merged[i] = RouteAnnotation(
                        span_id=span_id,
                        field=field,
                        semantic_role=sem_role,
                        route_family=llm_ann.route_family or existing.route_family,
                        construct_target=construct or existing.construct_target,
                        slot_target=slot or existing.slot_target,
                        executable=executable,
                        source_section_id=existing.source_section_id or llm_ann.source_section_id,
                        source_packet_id=existing.source_packet_id or llm_ann.source_packet_id,
                        primary=llm_ann.primary,
                    )
                    replaced = True
                    break

            if not replaced:
                # Prefer prior provenance over LLM provenance for new
                # multi-label annotations.  LLM provenance is only used
                # when the prior on that span provides nothing.
                provenance_sid = llm_ann.source_section_id
                provenance_pid = llm_ann.source_packet_id
                if span_id in prior_by_sid:
                    existing_list = prior_by_sid[span_id]
                    if existing_list:
                        provenance_sid = existing_list[0].source_section_id or provenance_sid
                        provenance_pid = existing_list[0].source_packet_id or provenance_pid

                merged.append(RouteAnnotation(
                    span_id=span_id,
                    field=field,
                    semantic_role=sem_role,
                    route_family=llm_ann.route_family,
                    construct_target=construct,
                    slot_target=slot,
                    executable=executable,
                    source_section_id=provenance_sid,
                    source_packet_id=provenance_pid,
                    primary=llm_ann.primary,
                ))

        # --- Collect LLM diagnostics ------------------------------------
        for diag in llm_result.diagnostics:
            route_diagnostics.append(
                f"LLM route diagnostic [{diag.kind}] "
                f"span='{diag.span_id}': {diag.message}"
            )

        # --- Collect parse diagnostics ----------------------------------
        for pd in llm_result.parse_diagnostics:
            route_diagnostics.append(
                f"LLM parse issue: {pd.field} — {pd.issue}"
            )

        # --- Use validator-filtered split recommendations ----------------
        split_recs = validated.split_recommendations

        return merged, route_diagnostics, split_recs

    # =========================================================================
    # old-list routing (unchanged)
    # =========================================================================

    def _route_packet_span(self, span: SpanIR, packet_type: str, routes: FieldRouteIR) -> None:
        if packet_type == "task_family":
            routes.domain.append(span.span_id)
        elif packet_type == "process_step":
            routes.behavior.append(span.span_id)
        elif packet_type == "policy":
            routes.rules.append(span.span_id)
        elif packet_type == "failure_mode":
            routes.rules.append(span.span_id)
        elif packet_type == "delegation_rule":
            routes.behavior.append(span.span_id)
        else:
            routes.behavior.append(span.span_id)

    def _route_section_span(
        self,
        span: SpanIR,
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput,
    ) -> None:
        sections = {section.section_id: section for section in canonical_input.raw_sections}
        section = sections.get(span.source_section_id or "")
        if section is None:
            routes.behavior.append(span.span_id)
            return
        if section.canonical_title == "task_family":
            routes.domain.append(span.span_id)
        elif section.canonical_title in {"policies", "failure_handling"}:
            routes.rules.append(span.span_id)
        else:
            routes.behavior.append(span.span_id)

    # -- annotation generation ------------------------------------------------

    @staticmethod
    def _build_hint_indexes(
        hints: Any,  # CompileHints
    ) -> dict[str, dict[str, Any]]:
        """Build hint indexes keyed by packet_id and section_id.

        Returns:
            {category: {"by_packet": {pid: [hint,...]}, "by_section": {sid: [hint,...]}}}
        """
        categories = {
            "flow": hints.flow_hints,
            "delegation": hints.delegation_hints,
            "constraint": hints.constraint_hints,
            "process": hints.process_hints,
            "profile": hints.profile_hints,
        }
        indexes: dict[str, dict[str, Any]] = {}
        for category, hint_list in categories.items():
            by_packet: dict[str, list[Any]] = {}
            by_section: dict[str, list[Any]] = {}
            for hint in hint_list:
                has_packet_ev = False
                for ev in hint.evidence:
                    if ev.source_packet_id:
                        by_packet.setdefault(ev.source_packet_id, []).append(hint)
                        has_packet_ev = True
                    if ev.source_section_id:
                        by_section.setdefault(ev.source_section_id, []).append(hint)
                if not has_packet_ev:
                    sid = hint.source_section_id
                    if sid:
                        by_section.setdefault(sid, []).append(hint)
            indexes[category] = {"by_packet": by_packet, "by_section": by_section}
        return indexes

    def _build_packet_annotation(
        self,
        span: SpanIR,
        packet: Any,  # SemanticPacket
        hint_indexes: dict[str, dict[str, list[Any]]],
    ) -> RouteAnnotation:
        """Build a RouteAnnotation from packet type semantics and adapter hints."""
        sem = _ANNOTATION_SEMANTICS.get(packet.packet_type, {})
        annotation = RouteAnnotation(
            span_id=span.span_id,
            field=sem.get("field", "behavior"),
            semantic_role=sem.get("semantic_role"),
            route_family=sem.get("route_family"),
            source_section_id=span.source_section_id,
            source_packet_id=span.source_packet_id,
            construct_target=sem.get("construct_target"),
            slot_target=sem.get("slot_target"),
            executable=sem.get("executable", True),
        )
        self._enrich_from_hints(
            annotation,
            span.source_packet_id or "",
            span.source_section_id or "",
            hint_indexes,
        )
        return annotation

    def _build_section_annotation(
        self,
        span: SpanIR,
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput,
    ) -> RouteAnnotation:
        """Build a minimal annotation for a non-packet span from its old-list field."""
        field = routes.get_field_for_span(span.span_id) or "behavior"
        return RouteAnnotation(
            span_id=span.span_id,
            field=field,
            source_section_id=span.source_section_id,
        )

    def _enrich_from_hints(
        self,
        annotation: RouteAnnotation,
        source_packet_id: str,
        source_section_id: str,
        hint_indexes: dict[str, dict[str, Any]],
    ) -> None:
        """Enrich annotation metadata from adapter compile hints.

        Packet-level hints are tried first, then section-level fallback.
        Hint values supplement annotation fields but do not override
        packet-type semantics.  Conflicts are recorded as diagnostics.
        """
        category = self._hint_category_for(annotation.semantic_role)
        if not category:
            return
        cat_index = hint_indexes.get(category, {})
        if not cat_index:
            return

        # Packet-level first, then section-level fallback
        hints: list[Any] = []
        if source_packet_id:
            hints = list(cat_index.get("by_packet", {}).get(source_packet_id, []))
        if not hints and source_section_id:
            hints = list(cat_index.get("by_section", {}).get(source_section_id, []))

        for idx, hint in enumerate(hints):
            annotation.source_hint_ids.append(
                f"hint_{category}_{idx}_{hint.source_section_id}"
            )
            meta = hint.metadata
            if not meta:
                continue

            # --- conflict-aware field enrichment ---

            # slot_target
            hint_slot = meta.get("slot_target")
            if hint_slot:
                if annotation.slot_target is None:
                    annotation.slot_target = hint_slot
                elif hint_slot != annotation.slot_target:
                    annotation.diagnostics.append(
                        f"Hint slot_target '{hint_slot}' conflicts with "
                        f"packet-derived '{annotation.slot_target}'"
                    )

            # route_family
            hint_rf = meta.get("route_family")
            if hint_rf:
                if annotation.route_family is None:
                    annotation.route_family = hint_rf
                elif hint_rf != annotation.route_family:
                    annotation.diagnostics.append(
                        f"Hint route_family '{hint_rf}' conflicts with "
                        f"packet-derived '{annotation.route_family}'"
                    )

            # semantic_role
            hint_role = meta.get("semantic_role")
            if hint_role:
                if annotation.semantic_role is None:
                    annotation.semantic_role = hint_role
                elif hint_role != annotation.semantic_role:
                    annotation.diagnostics.append(
                        f"Hint semantic_role '{hint_role}' conflicts with "
                        f"packet-derived role '{annotation.semantic_role}'"
                    )

            # executable
            hint_exec = meta.get("executable")
            if hint_exec is not None:
                if hint_exec != annotation.executable:
                    annotation.diagnostics.append(
                        f"Hint executable={hint_exec} conflicts with "
                        f"packet-derived executable={annotation.executable}"
                    )

            # construct_target (hint uses "target" field on CompileHint object)
            hint_target = getattr(hint, "target", None) or meta.get("target")
            if hint_target:
                if annotation.construct_target is None:
                    annotation.construct_target = hint_target
                elif hint_target != annotation.construct_target:
                    annotation.diagnostics.append(
                        f"Hint target '{hint_target}' conflicts with "
                        f"packet-derived construct_target '{annotation.construct_target}'"
                    )

    @staticmethod
    def _hint_category_for(semantic_role: str | None) -> str:
        if semantic_role in (None, ""):
            return ""
        if semantic_role in ("failure_mode",):
            return "flow"
        if semantic_role in ("delegation_intent",):
            return "delegation"
        if semantic_role in ("constraint",):
            return "constraint"
        if semantic_role in ("process_step",):
            return "process"
        if semantic_role in ("profile_domain",):
            return "profile"
        return ""


def _build_structured_diagnostics(
    route_diagnostics: list[str],
    llm_refinement_used: bool,
    split_recommendations: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Convert route diagnostic strings into structured dicts for CompileDiagnostic."""
    import re as _re
    result: list[dict[str, str]] = []

    for diag in route_diagnostics:
        # Extract span_id if present
        m = _re.search(r"span\s*'([^']+)'", diag)
        span_id = m.group(1) if m else ""

        kind = "route_refinement_diagnostic"
        if "rejected" in diag.lower():
            kind = "route_refinement_rejected"
        elif "corrected" in diag.lower():
            kind = "route_refinement_corrected"
        elif "conflict" in diag.lower():
            kind = "route_refinement_conflict"
        elif "fell back" in diag.lower() or "fallback" in diag.lower():
            kind = "route_refinement_fallback"
        elif "suppressed" in diag.lower():
            kind = "route_refinement_suppressed"
        elif "mismatch" in diag.lower():
            kind = "route_refinement_provenance_mismatch"

        result.append({
            "span_id": span_id,
            "kind": kind,
            "message": diag,
        })

    if llm_refinement_used and split_recommendations:
        for sr in split_recommendations:
            result.append({
                "span_id": sr.get("parent_span_id", ""),
                "kind": "route_refinement_split",
                "message": f"Split recommended for {sr['parent_span_id']}: {sr.get('reason', '')}",
            })

    return result
