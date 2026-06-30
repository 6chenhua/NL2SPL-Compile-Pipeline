"""Stage 2: FieldRouter - Route spans to semantic fields."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation, StructuralPrior
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage
from nl2spl.pipeline.stages.stage2_field_router_prompt import (
    ALLOWED_CONSTRUCT_TARGETS,
    ALLOWED_FIELDS,
    ALLOWED_SEMANTIC_ROLES,
    ALLOWED_SLOT_TARGETS,
    NON_EXECUTABLE_ROLES,
    RouteRefinementResult,
    build_adapter_guided_user_prompt,
    parse_refinement_result,
)
from nl2spl.pipeline.stages.stage2_field_router_validator import (
    RouteRefinementValidator,
)

# =========================================================================
# ARC3: Canonical role contract integration
# =========================================================================

from nl2spl.compiler.annotation_role_contract.normalize import (
    NormalizedAnnotation,
    normalize_annotation_from_role,
)
from nl2spl.compiler.annotation_role_contract.registry import (
    ROLE_CONTRACT_REGISTRY,
)

# Compatibility wrapper: packet_type → canonical semantic_role.
# Compiler-facing fields are now derived from ROLE_CONTRACT_REGISTRY
# via normalize_annotation_from_role().  This table only resolves
# the adapter packet_type to the semantic_role.
_ANNOTATION_SEMANTICS: dict[str, dict[str, Any]] = {
    "task_family":       {"semantic_role": "profile_domain"},
    "runtime_input":     {"semantic_role": "input_contract"},
    "required_output":   {"semantic_role": "output_contract"},
    "process_step":      {"semantic_role": "process_step"},
    "policy":            {"semantic_role": "constraint"},
    "failure_mode":      {"semantic_role": "failure_mode"},
    "delegation_rule":   {"semantic_role": "delegation_intent"},
}

# Compatibility wrapper: RoutePrior.suggested_semantic_role → canonical
# semantic_role (after alias resolution).  Compiler-facing fields are
# now derived from ROLE_CONTRACT_REGISTRY via normalize_annotation_from_role().
# This table only provides the role-to-role resolution where aliases are
# involved; canonical roles pass through unchanged.
ROUTE_PRIOR_ROLE_CONTRACTS: dict[str, dict[str, Any]] = {}

# _OPTIONAL_CONSTRUCT_SLOT_ROLES removed — the canonical registry encodes
# expected None explicitly via AnnotationRoleContract.construct_target=None
# and slot_target=None.

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

_SECTION_CONTEXT_TO_STRUCTURAL_ROLE: dict[str, str] = {
    "task family": "task_family",
    "inputs for each run": "input_contract",
    "required outputs": "output_contract",
    "reusable process": "process_step",
    "policies": "policy",
    "failure handling": "failure_mode",
    "delegation policy": "delegation_intent",
}


def _contract_field_for_role(role_or_alias: str, default_field: str) -> str:
    """Resolve *role_or_alias* via the canonical registry and return the contract ``field``.

    This is a compatibility helper for ``_build_structural_route_context()``
    which needs a ``suggested_field`` for ``StructuralPrior`` generation.
    """
    resolved = ROLE_CONTRACT_REGISTRY.resolve_semantic_role(role_or_alias)
    if resolved is None:
        return default_field
    contract = ROLE_CONTRACT_REGISTRY.get_role_contract(resolved)
    if contract is None:
        return default_field
    return contract.field


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
        self.save_checkpoint(
            {
                "routes": asdict(routes),
                "ambiguity_updates": ambiguity_updates,
                "overlaps": overlaps,
            }
        )

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
                adapter_consumed_spans.append(
                    {
                        "span_id": span.span_id,
                        "reason": f"seeded_as_hard_fact_{pkt.packet_type}",
                    }
                )
            else:
                self._route_packet_span(span, pkt.packet_type, routes)

        # 2. Build structural route context (Phase D)
        structural_priors, deterministic_annotations = (
            self._build_structural_route_context(spans, canonical_input)
        )

        # 3. LLM refinement (gated)
        route_diagnostics: list[str] = []
        llm_refinement_used = False
        split_recommendations: list[dict[str, Any]] = []
        merge_struct_diags: list[dict] = []
        priors = deterministic_annotations

        if self._llm_refinement_enabled():
            try:
                llm_result = self._call_adapter_guided_llm(
                    spans,
                    canonical_input,
                    structural_priors,
                    priors,
                )
                (
                    priors, route_diagnostics, split_recommendations,
                    merge_struct_diags,
                ) = self._merge_llm_refinement(
                    priors, llm_result, spans, canonical_input,
                    structural_priors=structural_priors,
                )
                llm_refinement_used = True
            except StageError as exc:
                self._save_adapter_guided_failure_checkpoint(exc)
                raise

        # ARC4: collect structured diagnostics from validator merge
        struct_diags: list[dict] = list(merge_struct_diags)

        # 3b. Enrich resource contract annotations with requiredness.
        # Must run AFTER LLM refinement because in the default structural
        # path, resource contract annotations come from the LLM, not from
        # deterministic priors.  Enrichment uses adapter-confirmed
        # SemanticPacket.required via provenance-aligned packet_id match.
        self._enrich_contract_requiredness(
            priors, spans, canonical_input,
        )

        # 3c. Post-enrichment requiredness finalization (ARC4).
        # Runs AFTER _enrich_contract_requiredness() so that missing/
        # invalid requiredness on resource contract annotations is
        # visible as structured diagnostics.
        req_strings, req_struct = RouteRefinementValidator.finalize_requiredness(
            priors,
        )
        route_diagnostics.extend(req_strings)
        # Merge requiredness structured diagnostics
        struct_diags.extend(d.to_dict() for d in req_struct)

        # 4. Attach annotations, structural priors, and route diagnostics
        routes.annotations = priors
        routes.structural_priors = structural_priors
        self._sync_legacy_routes_from_annotations(routes)
        routes.route_diagnostics = route_diagnostics
        routes.structured_route_diagnostics = _build_structured_diagnostics(
            route_diagnostics,
            llm_refinement_used,
            split_recommendations,
        )
        # ARC4: append typed structured diagnostics alongside legacy string diags
        routes.structured_route_diagnostics.extend(struct_diags)

        # 5. Convert split recommendations to ambiguity_updates for Stage 3
        ambiguity_updates: list[dict[str, Any]] = []
        for sr in split_recommendations:
            ambiguity_updates.append(
                {
                    "span_id": sr["parent_span_id"],
                    "is_ambiguous": True,
                    "reasons": [sr.get("reason", "LLM split recommendation")],
                    "needs_split": True,
                    "split_recommendation": sr,
                }
            )

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
    # Structural route context (Phase D)
    # =========================================================================

    def _build_structural_route_context(
        self,
        spans: list[SpanIR],
        canonical_input: CanonicalCompileInput,
    ) -> tuple[list[StructuralPrior], list[RouteAnnotation]]:
        """Build structural priors and deterministic annotations.

        Returns ``(structural_priors, deterministic_annotations)``.

        - ``structural_priors``: deterministic structural evidence for the LLM
          semantic mapper and validator.  Stage 4/5/7 must NOT consume these.
        - ``deterministic_annotations``: final semantic routing decisions from
          hard contracts only (runtime_input, required_output).

        Priority chain per span:
          1. packet_id prior: precise match → structural prior (route_prior)
          2. span_hint_id prior: precise match → structural prior (route_prior)
          3. section-level prior:
             - Single-packet section → structural prior (route_prior)
             - Multi-packet section → structural prior (weak_section_context)
          4. Legacy packet_type semantics → structural prior (packet_type_context)
          5. Fallback → structural prior (neutral_context)

        Only runtime_input and required_output packets generate deterministic
        RouteAnnotation (hard facts).  All other semantic decisions are
        delegated to LLM refinement via structural evidence.
        """
        packets = {pkt.packet_id: pkt for pkt in canonical_input.semantic_packets}
        hint_indexes = self._build_hint_indexes(canonical_input.compile_hints)
        route_priors = getattr(canonical_input, "route_priors", []) or []

        # Build prior indexes for fast lookup
        priors_by_packet_id: dict[str, list[Any]] = {}
        priors_by_span_hint_id: dict[str, list[Any]] = {}
        priors_by_section_id: dict[str, list[Any]] = {}
        for prior in route_priors:
            if getattr(prior, "packet_id", None):
                priors_by_packet_id.setdefault(prior.packet_id, []).append(prior)
            elif getattr(prior, "span_hint_id", None):
                priors_by_span_hint_id.setdefault(prior.span_hint_id, []).append(prior)
            else:
                priors_by_section_id.setdefault(prior.section_id, []).append(prior)

        # Count packets per section for single-packet section detection
        packets_per_section: dict[str, list[str]] = {}
        for pkt in canonical_input.semantic_packets:
            packets_per_section.setdefault(pkt.source_section_id, []).append(pkt.packet_id)

        structural_priors: list[StructuralPrior] = []
        annotations: list[RouteAnnotation] = []

        for span in spans:
            # Skip placeholder spans
            if span.is_placeholder:
                continue

            packet = packets.get(span.source_packet_id or "")

            # --- Case 1: no backing packet (section-only placeholder span) ---
            if packet is None:
                field = self._section_field(span, canonical_input)
                structural_priors.append(
                    StructuralPrior(
                        span_id=span.span_id,
                        suggested_field=field,
                        source_section_id=span.source_section_id,
                        prior_kind="no_backing_packet",
                        confidence="weak",
                        reason="No backing packet for span",
                    )
                )
                continue

            # --- Case 2: legacy hard-fact packets (runtime_input, required_output) ---
            if packet.packet_type in {"runtime_input", "required_output"}:
                ann = self._build_packet_annotation(span, packet, hint_indexes)
                annotations.append(ann)
                structural_priors.append(
                    StructuralPrior(
                        span_id=span.span_id,
                        suggested_field=ann.field,
                        source_section_id=span.source_section_id,
                        source_packet_id=span.source_packet_id,
                        prior_kind=f"{packet.packet_type}_contract",
                        confidence="exact",
                        packet_type=packet.packet_type,
                        reason=f"Deterministic {packet.packet_type} contract",
                    )
                )
                continue

            # --- Case 3: look for applicable RoutePriors ---
            matched_priors: list[Any] = []

            # Priority 1: exact packet_id prior
            if span.source_packet_id and span.source_packet_id in priors_by_packet_id:
                matched_priors = priors_by_packet_id[span.source_packet_id]

            # Priority 2: span_hint_id prior
            elif span.span_id in priors_by_span_hint_id:
                matched_priors = priors_by_span_hint_id[span.span_id]

            # Priority 3: section-level prior. Apply broadly only for
            # exact-title compatibility priors; LLM section-only priors remain
            # weak context in multi-packet sections.
            elif span.source_section_id and span.source_section_id in priors_by_section_id:
                section_packets = packets_per_section.get(span.source_section_id, [])
                section_priors = priors_by_section_id[span.source_section_id]
                if len(section_packets) == 1 or any(
                    getattr(prior, "source", None) == "heuristic" for prior in section_priors
                ):
                    matched_priors = section_priors
                else:
                    # Multi-packet section: structural prior only
                    field = self._section_field(span, canonical_input)
                    structural_priors.append(
                        StructuralPrior(
                            span_id=span.span_id,
                            suggested_field=field,
                            source_section_id=span.source_section_id,
                            source_packet_id=span.source_packet_id,
                            prior_kind="weak_section_context",
                            confidence="weak",
                            packet_type=packet.packet_type,
                            reason="Multi-packet section, weak context only",
                        )
                    )
                    continue

            if matched_priors:
                # RoutePriors are structural evidence, not final semantic
                # decisions.  Generate StructuralPrior for each.
                for prior in matched_priors:
                    role = prior.suggested_semantic_role
                    suggested_field = _contract_field_for_role(
                        role, prior.suggested_field or "behavior"
                    )
                    structural_priors.append(
                        StructuralPrior(
                            span_id=span.span_id,
                            suggested_field=suggested_field,
                            source_section_id=span.source_section_id,
                            source_packet_id=span.source_packet_id,
                            prior_kind="route_prior",
                            confidence="structural",
                            packet_type=packet.packet_type,
                            reason=f"RoutePrior suggests {role}",
                            metadata={"suggested_semantic_role": role or ""},
                        )
                    )
                continue

            # --- Case 4: legacy packet_type semantics → structural evidence ---
            section_role = self._section_structural_role(span, canonical_input)
            if section_role:
                suggested_field = _contract_field_for_role(
                    section_role, self._section_field(span, canonical_input)
                )
                structural_priors.append(
                    StructuralPrior(
                        span_id=span.span_id,
                        suggested_field=suggested_field,
                        source_section_id=span.source_section_id,
                        source_packet_id=span.source_packet_id,
                        prior_kind="route_prior",
                        confidence="structural",
                        packet_type=packet.packet_type,
                        reason=f"Section title suggests {section_role}",
                        metadata={"suggested_semantic_role": section_role},
                    )
                )
                continue

            if packet.packet_type in _ANNOTATION_SEMANTICS:
                sem = _ANNOTATION_SEMANTICS[packet.packet_type]
                # ARC3: field derived from canonical registry, not old wrapper
                sem_role = sem.get("semantic_role", "")
                suggested_field = _contract_field_for_role(sem_role, "behavior")
                structural_priors.append(
                    StructuralPrior(
                        span_id=span.span_id,
                        suggested_field=suggested_field,
                        source_section_id=span.source_section_id,
                        source_packet_id=span.source_packet_id,
                        prior_kind="packet_type_context",
                        confidence="structural",
                        packet_type=packet.packet_type,
                        reason=(
                            f"Packet type '{packet.packet_type}' suggests "
                            f"{sem_role}"
                        ),
                        metadata={
                            "suggested_semantic_role": sem_role,
                        },
                    )
                )
                continue

            # --- Case 5: neutral packet with no matching prior ---
            # Structural evidence only — LLM refinement is the authoritative
            # path for assigning semantic roles to these.
            field = self._section_field(span, canonical_input)
            structural_priors.append(
                StructuralPrior(
                    span_id=span.span_id,
                    suggested_field=field,
                    source_section_id=span.source_section_id,
                    source_packet_id=span.source_packet_id,
                    prior_kind="neutral_context",
                    confidence="context",
                    packet_type=packet.packet_type,
                    reason="No matching route prior for neutral packet",
                )
            )

        return structural_priors, annotations

    @staticmethod
    def _section_structural_role(
        span: SpanIR,
        canonical_input: CanonicalCompileInput,
    ) -> str | None:
        """Return a structural role hint from fixed section titles."""
        section_title = None
        if span.source_section_id:
            for section in canonical_input.raw_sections:
                if section.section_id == span.source_section_id:
                    section_title = section.canonical_title
                    break
        if section_title is None and span.section_context:
            section_title = span.section_context
        if not section_title:
            return None
        normalized = section_title.replace("_", " ").strip().lower()
        return _SECTION_CONTEXT_TO_STRUCTURAL_ROLE.get(normalized)

    @staticmethod
    def _section_field(
        span: SpanIR,
        canonical_input: CanonicalCompileInput,
    ) -> str:
        """Derive a structural field hint for a span.

        This is a **structural routing hint** for ``StructuralPrior.suggested_field``,
        NOT a semantic routing decision.  The final field assignment is made by
        the LLM semantic mapper.

        Priority 1: canonical source_section_id (structured, highest confidence)
        Priority 2: section_context exact match (LLM path, medium confidence)
        Priority 2b: section_context keyword fallback (low confidence, structural only)
        Priority 3: default "behavior"
        """
        # Priority 1: canonical route_priors
        if span.source_section_id and hasattr(canonical_input, "route_priors"):
            for prior in canonical_input.route_priors:
                if prior.section_id == span.source_section_id:
                    return prior.suggested_field

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
            # Priority 2b: keyword fallback (structural field hint only,
            # not a semantic decision — LLM refinement is authoritative)
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
        return True

    def _call_adapter_guided_llm(
        self,
        spans: list[SpanIR],
        canonical_input: CanonicalCompileInput,
        structural_priors: list[StructuralPrior],
        deterministic_annotations: list[RouteAnnotation],
    ) -> RouteRefinementResult:
        """Call the adapter-guided LLM and return parsed result.

        Call or parse failures are hard errors.
        """
        try:
            system_prompt = load_prompt("stage2_adapter_guided")
            user_prompt = build_adapter_guided_user_prompt(
                spans,
                canonical_input,
                structural_priors,
                deterministic_annotations,
            )
            result_dict = self.client.call_json(
                stage_name="stage2_adapter_guided",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            return parse_refinement_result(result_dict)
        except Exception as exc:
            message = (
                "stage2_adapter_guided LLM refinement failed with "
                f"{type(exc).__name__}: {exc}; fallback disabled."
            )
            self.logger.warning(message)
            raise StageError(
                message=message,
                stage=self.name,
                details={
                    "llm_stage_name": "stage2_adapter_guided",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "fallback_allowed": False,
                    "source_schema": canonical_input.source_schema,
                    "spans_count": len(spans),
                },
            ) from exc

    def _save_adapter_guided_failure_checkpoint(self, exc: StageError) -> None:
        """Persist a failure-only checkpoint before fail-fast propagation."""
        details = dict(exc.details)
        self.save_checkpoint(
            {
                "failure": {
                    "stage": self.name,
                    "message": str(exc),
                    "details": details,
                },
                "llm_refinement": {
                    "used": False,
                    "llm_stage_name": details.get("llm_stage_name", "stage2_adapter_guided"),
                    "error_type": details.get("exception_type"),
                    "error_message": details.get("exception_message"),
                    "fallback_allowed": details.get("fallback_allowed", False),
                },
            }
        )

    @staticmethod
    def _normalize_annotation_contract(
        *,
        span_id: str,
        field: str,
        semantic_role: str | None,
        route_family: str | None,
        construct_target: str | None,
        slot_target: str | None,
        executable: bool,
        diagnostics: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, str | None, str | None, str | None, str | None, bool]:
        """Normalize an LLM annotation to the canonical role contract.

        All compiler-facing fields are derived from ROLE_CONTRACT_REGISTRY.
        Raw LLM values are preserved in diagnostics but are NOT authoritative.
        """
        if semantic_role is None:
            return (
                field,
                semantic_role,
                route_family,
                construct_target,
                slot_target,
                executable,
            )

        # Resolve alias if needed, then look up contract
        resolved = ROLE_CONTRACT_REGISTRY.resolve_semantic_role(semantic_role)
        if resolved is None:
            # Unknown role — pass through unchanged (validator will handle)
            return (
                field,
                semantic_role,
                route_family,
                construct_target,
                slot_target,
                executable,
            )

        contract = ROLE_CONTRACT_REGISTRY.require_role_contract(resolved)

        result = normalize_annotation_from_role(
            span_id=span_id,
            semantic_role=resolved,
            raw_field=field,
            raw_route_family=route_family,
            raw_construct_target=construct_target,
            raw_slot_target=slot_target,
            raw_executable=executable,
            metadata=metadata,
        )

        # Merge diagnostics
        diagnostics.extend(result.diagnostics)

        return (
            result.annotation.field,
            result.annotation.semantic_role,
            result.annotation.route_family,
            result.annotation.construct_target,
            result.annotation.slot_target,
            result.annotation.executable,
        )

    def _merge_llm_refinement(
        self,
        priors: list[RouteAnnotation],
        llm_result: RouteRefinementResult,
        spans: list[SpanIR],
        canonical_input: CanonicalCompileInput | None = None,
        structural_priors: list[StructuralPrior] | None = None,
    ) -> tuple[list[RouteAnnotation], list[str], list[dict[str, Any]], list[dict]]:
        """Merge validated LLM annotations with deterministic priors.

        Runs the standalone RouteRefinementValidator first, then merges
        only accepted annotations.  When all LLM annotations are rejected,
        the deterministic priors are returned unchanged (the merge loop
        iterates over an empty accepted list).

        Returns:
            (merged_annotations, route_diagnostics, split_recommendations,
             structured_diagnostics_as_dicts)
        """
        route_diagnostics: list[str] = []
        valid_span_ids = {s.span_id for s in spans}

        # --- Step 0: standalone validator --------------------------------
        validator = RouteRefinementValidator()
        validated = validator.validate(
            llm_result,
            spans,
            canonical_input=canonical_input,
            structural_priors=structural_priors or [],
            deterministic_annotations=priors,
        )

        # Collect validator diagnostics
        route_diagnostics.extend(validated.diagnostics)

        # --- Step 1: merge accepted annotations --------------------------

        # Build structural prior index for provenance lookup
        structural_prior_by_sid: dict[str, StructuralPrior] = {}
        for sp in structural_priors or []:
            if sp.span_id not in structural_prior_by_sid:
                structural_prior_by_sid[sp.span_id] = sp

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
                route_diagnostics.append(f"LLM refinement rejected: unknown span_id '{span_id}'")
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
                    f"LLM refinement rejected: invalid slot_target '{slot}' for span '{span_id}'"
                )
                continue

            (
                field,
                sem_role,
                route_family,
                construct,
                slot,
                executable,
            ) = self._normalize_annotation_contract(
                span_id=span_id,
                field=field,
                semantic_role=sem_role,
                route_family=llm_ann.route_family,
                construct_target=construct,
                slot_target=slot,
                executable=executable,
                metadata=llm_ann.metadata,
                diagnostics=route_diagnostics,
            )
            ann_metadata = dict(llm_ann.metadata)

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
                        route_family=route_family or existing.route_family,
                        construct_target=construct,
                        slot_target=slot,
                        executable=executable,
                        source_section_id=existing.source_section_id or llm_ann.source_section_id,
                        source_packet_id=existing.source_packet_id or llm_ann.source_packet_id,
                        primary=llm_ann.primary,
                        metadata={**existing.metadata, **ann_metadata},
                    )
                    replaced = True
                    break

            if not replaced:
                # Prefer structural prior provenance over LLM provenance
                # for new multi-label annotations.
                provenance_sid = llm_ann.source_section_id
                provenance_pid = llm_ann.source_packet_id
                sp = structural_prior_by_sid.get(span_id)
                if sp:
                    provenance_sid = sp.source_section_id or provenance_sid
                    provenance_pid = sp.source_packet_id or provenance_pid
                elif span_id in prior_by_sid:
                    existing_list = prior_by_sid[span_id]
                    if existing_list:
                        provenance_sid = existing_list[0].source_section_id or provenance_sid
                        provenance_pid = existing_list[0].source_packet_id or provenance_pid

                merged.append(
                    RouteAnnotation(
                        span_id=span_id,
                        field=field,
                        semantic_role=sem_role,
                        route_family=route_family,
                        construct_target=construct,
                        slot_target=slot,
                        executable=executable,
                        source_section_id=provenance_sid,
                        source_packet_id=provenance_pid,
                        primary=llm_ann.primary,
                        metadata=ann_metadata,
                    )
                )

        # --- Detect contradictory executable state ---------------------------
        # Only flag genuine semantic conflicts (both sides have populated
        # roles).  Neutral prior leaks are handled by Phase A/B and do not
        # constitute a conflict.
        span_anns_by_id: dict[str, list[RouteAnnotation]] = {}
        for ann in merged:
            span_anns_by_id.setdefault(ann.span_id, []).append(ann)

        for sid, anns in span_anns_by_id.items():
            has_exec = any(a.executable for a in anns)
            has_non_exec = any(not a.executable for a in anns)
            if has_exec and has_non_exec:
                has_real_non_exec = any(
                    not a.executable and a.semantic_role is not None for a in anns
                )
                if has_real_non_exec:
                    route_diagnostics.append(
                        f"route_refinement_conflict: span '{sid}' has both "
                        f"executable and non-executable annotations with "
                        f"populated semantic roles"
                    )

        # --- Collect LLM diagnostics ------------------------------------
        for diag in llm_result.diagnostics:
            route_diagnostics.append(
                f"LLM route diagnostic [{diag.kind}] span='{diag.span_id}': {diag.message}"
            )

        # --- Collect parse diagnostics ----------------------------------
        for pd in llm_result.parse_diagnostics:
            route_diagnostics.append(f"LLM parse issue: {pd.field} — {pd.issue}")

        # --- Use validator-filtered split recommendations ----------------
        split_recs = validated.split_recommendations

        return merged, route_diagnostics, split_recs, [
            d.to_dict() for d in validated.structured_diagnostics
        ]


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
            routes.behavior.append(span.span_id)
        elif packet_type == "delegation_rule":
            routes.behavior.append(span.span_id)
        elif packet_type in {"list_item", "sentence", "section_block"}:
            return
        else:
            routes.behavior.append(span.span_id)

    @staticmethod
    def _sync_legacy_routes_from_annotations(routes: FieldRouteIR) -> None:
        """Align legacy route lists with authoritative annotations.

        Resource contracts are intentionally excluded from legacy route lists;
        they are consumed by resource extraction through annotations/hard facts.
        Neutral context annotations without a semantic role are also excluded
        so they cannot become executable behavior candidates.
        """
        routes.identity = []
        routes.audience = []
        routes.rules = []
        routes.domain = []
        routes.integrations = []
        routes.behavior = []

        for ann in routes.annotations:
            if not ann.semantic_role:
                continue
            role = ann.semantic_role
            if role in {"input_contract", "output_contract"}:
                continue
            if role == "profile_domain":
                target = routes.domain
            elif role in {
                "constraint",
                "delegation_boundary_constraint",
                "delegation_prohibition",
                "handoff_condition",
            }:
                target = routes.rules
            elif role in {"api_candidate", "integration_hint"}:
                target = routes.integrations
            elif role in {"process_step", "exception_handler_action"} and ann.executable:
                target = routes.behavior
            else:
                continue
            if ann.span_id not in target:
                target.append(ann.span_id)

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
        section_title = section.canonical_title.replace("_", " ")
        if section_title == "task family":
            routes.domain.append(span.span_id)
        elif section_title == "policies":
            routes.rules.append(span.span_id)
        elif section_title == "failure handling":
            routes.behavior.append(span.span_id)
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
        """Build a RouteAnnotation from packet type semantics.

        Uses _ANNOTATION_SEMANTICS (compatibility wrapper) only to resolve
        packet_type → semantic_role.  All compiler-facing fields are derived
        from the canonical role contract via normalize_annotation_from_role().
        """
        sem = _ANNOTATION_SEMANTICS.get(packet.packet_type, {})
        semantic_role = sem.get("semantic_role")
        if semantic_role is None:
            # Unknown packet type — build a minimal neutral annotation
            annotation = RouteAnnotation(
                span_id=span.span_id,
                field="behavior",
                source_section_id=span.source_section_id,
                source_packet_id=span.source_packet_id,
            )
        else:
            result = normalize_annotation_from_role(
                span_id=span.span_id,
                semantic_role=semantic_role,
                source_section_id=span.source_section_id,
                source_packet_id=span.source_packet_id,
            )
            annotation = result.annotation

        self._enrich_from_hints(
            annotation,
            span.source_packet_id or "",
            span.source_section_id or "",
            hint_indexes,
        )
        return annotation

    @staticmethod
    def _enrich_contract_requiredness(
        annotations: list[RouteAnnotation],
        spans: list[SpanIR],
        canonical_input: CanonicalCompileInput,
    ) -> None:
        """Set ``metadata["requiredness"]`` on resource contract annotations.

        Primary source: ``SemanticPacket.required`` on the packet backing
        each span.  The Structural Adapter writes ``required`` on list-item
        packets under known input/output sections — this is the adapter's
        own deterministic logic, not a downstream fallback.

        Fallback: ``VariableFact.required`` from hard_facts (when enabled).
        Enrichment only applies when provenance aligns (packet or hard_fact
        matches by identity, not by text normalisation).

        B2: no LLM prompt change, no downstream section-title inference,
        no evidence-text parsing.  Requiredness is adapter-confirmed
        structural metadata carried via ``SemanticPacket``.
        """
        # Primary source: packet-level required (always available)
        packets = {
            pkt.packet_id: pkt
            for pkt in canonical_input.semantic_packets
        }

        # Fallback source: hard_facts (when enable_adapter_hard_facts=True)
        hard_fact_lookup: dict[str, dict[str, bool]] | None = None

        span_by_id = {s.span_id: s for s in spans}

        for ann in annotations:
            if ann.semantic_role not in ("input_contract", "output_contract"):
                continue
            span = span_by_id.get(ann.span_id)
            if span is None:
                continue

            # 1. Provenance-aligned packet match (primary)
            if span.source_packet_id:
                pkt = packets.get(span.source_packet_id)
                if pkt is not None and pkt.required is not None:
                    ann.metadata["requiredness"] = (
                        "required" if pkt.required else "optional"
                    )
                    continue

            # 2. Hard-fact fallback (provenance-aligned via evidence packet_id)
            if hard_fact_lookup is None:
                hard_fact_lookup = {}
                for direction, facts in (
                    ("input_contract", canonical_input.hard_facts.inputs),
                    ("output_contract", canonical_input.hard_facts.outputs),
                ):
                    hf_map: dict[str, bool] = {}
                    for fact in facts:
                        for ev in fact.evidence:
                            pid = getattr(ev, "source_packet_id", None)
                            if pid:
                                hf_map[pid] = fact.required
                    hard_fact_lookup[direction] = hf_map
            if span.source_packet_id:
                hf_map = hard_fact_lookup[ann.semantic_role]
                required = hf_map.get(span.source_packet_id)
                if required is not None:
                    ann.metadata["requiredness"] = (
                        "required" if required else "optional"
                    )
            # else: leave unset → DemandView interprets as unspecified

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
            annotation.source_hint_ids.append(f"hint_{category}_{idx}_{hint.source_section_id}")
            meta = hint.metadata
            if not meta:
                continue

            # --- conflict diagnostics only (no role-contract mutation) ---
            #
            # ARC3: Hints MUST NOT write or override role-contract fields.
            # All compiler-facing fields are derived from the canonical
            # role contract during normalization.  Hints can only:
            #   - add source_hint_ids (done above)
            #   - emit typed conflict diagnostics (below)
            #   - add raw candidate values into annotation metadata

            # slot_target — diagnostic only
            hint_slot = meta.get("slot_target")
            if hint_slot is not None and hint_slot != annotation.slot_target:
                annotation.diagnostics.append(
                    f"Hint slot_target '{hint_slot}' conflicts with "
                    f"contract slot_target '{annotation.slot_target}'"
                )
                annotation.metadata.setdefault("_hint_", {})["slot_target"] = hint_slot

            # route_family — diagnostic only
            hint_rf = meta.get("route_family")
            if hint_rf is not None and hint_rf != annotation.route_family:
                annotation.diagnostics.append(
                    f"Hint route_family '{hint_rf}' conflicts with "
                    f"contract route_family '{annotation.route_family}'"
                )
                annotation.metadata.setdefault("_hint_", {})["route_family"] = hint_rf

            # semantic_role — diagnostic only
            hint_role = meta.get("semantic_role")
            if hint_role is not None and hint_role != annotation.semantic_role:
                annotation.diagnostics.append(
                    f"Hint semantic_role '{hint_role}' conflicts with "
                    f"contract role '{annotation.semantic_role}'"
                )
                annotation.metadata.setdefault("_hint_", {})["semantic_role"] = hint_role

            # executable — diagnostic only
            hint_exec = meta.get("executable")
            if hint_exec is not None and hint_exec != annotation.executable:
                annotation.diagnostics.append(
                    f"Hint executable={hint_exec} conflicts with "
                    f"contract executable={annotation.executable}"
                )
                annotation.metadata.setdefault("_hint_", {})["executable"] = hint_exec

            # construct_target — diagnostic only
            hint_target = getattr(hint, "target", None) or meta.get("target")
            if hint_target is not None and hint_target != annotation.construct_target:
                annotation.diagnostics.append(
                    f"Hint target '{hint_target}' conflicts with "
                    f"contract construct_target '{annotation.construct_target}'"
                )
                annotation.metadata.setdefault("_hint_", {})["construct_target"] = hint_target

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

        result.append(
            {
                "span_id": span_id,
                "kind": kind,
                "message": diag,
            }
        )

    if llm_refinement_used and split_recommendations:
        for sr in split_recommendations:
            result.append(
                {
                    "span_id": sr.get("parent_span_id", ""),
                    "kind": "route_refinement_split",
                    "message": f"Split recommended for {sr['parent_span_id']}: {sr.get('reason', '')}",
                }
            )

    return result


# =============================================================================
# B2: requiredness enrichment helpers
# =============================================================================


def _normalize_to_variable_name(text: str) -> str:
    """Normalise span text to a snake_case variable name.

    Uses the same algorithm as ``StructuralAdapter._variable_name()`` so that
    span texts can be matched against hard-fact ``VariableFact.name`` entries.

    Does NOT parse evidence text for semantics — this is a pure text normaliser.
    """
    normalized = text.strip().lower().rstrip(".")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"^(a|an|the)\s+", "", normalized)
    normalized = re.sub(r"^optional\s+", "", normalized)
    normalized = normalized.replace("/", " ")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_")


def _build_hard_fact_required_lookup(
    facts: list[object],  # list[VariableFact]  — lazy import to avoid circularity
) -> dict[str, bool]:
    """Build a lookup from evidence packet_id → required: bool.

    Provenance-aligned: matches by ``EvidenceRef.source_packet_id``,
    not by name normalisation.
    """
    result: dict[str, bool] = {}
    for fact in facts:
        required = getattr(fact, "required", True)
        evidence_list = getattr(fact, "evidence", []) or []
        for ev in evidence_list:
            pid = getattr(ev, "source_packet_id", None)
            if pid:
                result[pid] = required
    return result
