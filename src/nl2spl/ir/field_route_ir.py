"""FieldRouteIR - Field routing result with route annotations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StructuralPrior:
    """Deterministic structural evidence for semantic routing.

    A ``StructuralPrior`` is **not** a final semantic routing decision.
    It can guide the LLM semantic mapper and the validator, but
    Stage 4/5/7 must not consume it as semantic truth.

    Attributes:
        span_id: The span this prior describes.
        suggested_field: Weak field hint (not a final routing decision).
        source_section_id: Adapter section provenance.
        source_packet_id: Adapter packet provenance.
        source_hint_ids: CompileHint ids that informed this prior.
        prior_kind: Structural evidence type, e.g. ``neutral_context``,
            ``weak_section_context``, ``exact_route_prior``,
            ``runtime_input_contract``, ``required_output_contract``.
        confidence: ``exact`` / ``structural`` / ``context`` / ``weak``.
        reason: Human-readable explanation.
        packet_type: Adapter packet type.
        section_title: Original or canonical section title.
        structural_tags: E.g. ``list_item``, ``colon_pair``,
            ``section_context``.
        metadata: Non-semantic附加信息 (must be JSON-primitives only).
    """

    span_id: str
    suggested_field: str | None = None
    source_section_id: str | None = None
    source_packet_id: str | None = None
    source_hint_ids: list[str] = field(default_factory=list)
    prior_kind: str = "neutral_context"
    confidence: str = "context"
    reason: str | None = None
    packet_type: str | None = None
    section_title: str | None = None
    structural_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteAnnotation:
    """Semantic route annotation for a span.

    Annotations express richer routing semantics than the six legacy field
    lists.  A single span may carry multiple annotations with different
    semantic roles, construct targets, or slot targets.

    Attributes:
        span_id: The span this annotation describes.
        field: Primary legacy field for backward compatibility.
        semantic_role: E.g. ``failure_mode``, ``delegation_intent``, ``action``.
        route_family: E.g. ``flow_relevant``, ``resource_contract``,
            ``delegation_boundary``.
        source_section_id: Adapter section provenance.
        source_packet_id: Adapter packet provenance.
        source_hint_ids: CompileHint ids that informed this annotation.
        construct_target: Target SPL construct, e.g. ``EXCEPTION_FLOW``.
        slot_target: Target slot within the construct, e.g. ``condition``.
        executable: Whether this annotation may produce executable SPL.
        primary: Whether this is the primary annotation for the span.
        diagnostics: Route-level diagnostic messages.
        metadata: Additional metadata for downstream consumers.
    """

    span_id: str
    field: str
    semantic_role: str | None = None
    route_family: str | None = None
    source_section_id: str | None = None
    source_packet_id: str | None = None
    source_hint_ids: list[str] = field(default_factory=list)
    construct_target: str | None = None
    slot_target: str | None = None
    executable: bool = True
    primary: bool = True
    diagnostics: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FieldRouteIR:
    """Field routing result.

    Attributes:
        identity: Spans routed to identity field
        audience: Spans routed to audience field
        rules: Spans routed to rules field
        domain: Spans routed to domain field
        integrations: Spans routed to integration field
        behavior: Spans routed to behavior field
        annotations: Final semantic routing decisions consumed by Stage 4/5/7.
        structural_priors: Deterministic structural evidence for LLM/validator.
            Stage 4/5/7 must NOT consume these as semantic truth.
    """

    identity: list[str] = field(default_factory=list)
    audience: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    domain: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    behavior: list[str] = field(default_factory=list)
    annotations: list[RouteAnnotation] = field(default_factory=list)
    structural_priors: list[StructuralPrior] = field(default_factory=list)
    route_diagnostics: list[str] = field(default_factory=list)
    # Structured route diagnostics for compile-diagnostic conversion.
    # Each dict has: span_id, kind, message.
    structured_route_diagnostics: list[dict[str, str]] = field(default_factory=list)

    def get_all_span_ids(self) -> set[str]:
        """Get all span IDs across all fields."""
        return (
            set(self.identity)
            | set(self.audience)
            | set(self.rules)
            | set(self.domain)
            | set(self.integrations)
            | set(self.behavior)
        )

    def get_field_for_span(self, span_id: str) -> str | None:
        """Get the field a span is routed to.

        Args:
            span_id: Span ID to look up

        Returns:
            Field name or None if not found
        """
        for field_name in [
            "identity",
            "audience",
            "rules",
            "domain",
            "integrations",
            "behavior",
        ]:
            if span_id in getattr(self, field_name):
                return field_name
        return None

    # -- annotation helpers -------------------------------------------------

    def get_annotations(self, span_id: str) -> list[RouteAnnotation]:
        """Return all annotations for *span_id*."""
        return [a for a in self.annotations if a.span_id == span_id]

    def get_primary_field(self, span_id: str) -> str | None:
        """Return the primary field for *span_id*.

        Prefers the primary annotation's field when annotations exist,
        otherwise falls back to the old six-field ``get_field_for_span``.
        """
        primary = [a for a in self.annotations if a.span_id == span_id and a.primary]
        if primary:
            return primary[0].field
        return self.get_field_for_span(span_id)

    def get_executable_behavior_span_ids(self) -> list[str]:
        """Return span ids that represent executable behavior.

        When annotations exist this returns only executable behavior spans
        in the same order as ``self.behavior``, with any additional
        annotation-only spans appended in annotation-list order.
        When no annotations exist this falls back to ``self.behavior``.
        """
        if self.annotations:
            exec_set = {
                a.span_id
                for a in self.annotations
                if a.executable and a.field == "behavior"
            }
            result: list[str] = []
            seen: set[str] = set()
            for sid in self.behavior:
                if sid in exec_set:
                    result.append(sid)
                    seen.add(sid)
            for a in self.annotations:
                if a.span_id in exec_set and a.span_id not in seen:
                    result.append(a.span_id)
                    seen.add(a.span_id)
            return result
        return list(self.behavior)

    def get_non_executable_behavior_span_ids(self) -> list[str]:
        """Return span ids that are behavior-like but NOT executable.

        E.g. failure_mode conditions or delegation intents without contracts.
        Returns empty list when no annotations exist.
        Preserves ``self.behavior`` ordering where applicable.

        Defensive guard: a span with an executable behavior annotation is
        excluded from the non-executable set even if a stale non-executable
        annotation also exists (executable wins).
        """
        exec_set = {
            a.span_id
            for a in self.annotations
            if a.executable and a.field == "behavior"
        }
        non_exec_set = {
            a.span_id
            for a in self.annotations
            if not a.executable and a.field == "behavior"
        } - exec_set
        result: list[str] = []
        seen: set[str] = set()
        for sid in self.behavior:
            if sid in non_exec_set:
                result.append(sid)
                seen.add(sid)
        for a in self.annotations:
            if a.span_id in non_exec_set and a.span_id not in seen:
                result.append(a.span_id)
                seen.add(a.span_id)
        return result

    def get_construct_slot_candidates(
        self, construct: str, slot: str
    ) -> list[RouteAnnotation]:
        """Return annotations targeting the given construct + slot."""
        return [
            a
            for a in self.annotations
            if a.construct_target == construct and a.slot_target == slot
        ]

    def get_annotations_by_role(self, role: str) -> list[RouteAnnotation]:
        """Return annotations with the given semantic role."""
        return [a for a in self.annotations if a.semantic_role == role]

    # -- validation ---------------------------------------------------------

    def validate_no_overlap(self) -> list[str]:
        """Validate that no span appears in multiple old six-field lists.

        Annotation-level multi-label semantics (multiple RouteAnnotations
        on the same span with different roles) are explicitly allowed and
        are NOT reported as overlap by this method.

        Returns:
            List of overlapping span IDs from the six legacy fields.
        """
        all_spans: list[str] = (
            self.identity
            + self.audience
            + self.rules
            + self.domain
            + self.integrations
            + self.behavior
        )
        seen: set[str] = set()
        overlaps: list[str] = []
        for span_id in all_spans:
            if span_id in seen:
                overlaps.append(span_id)
            seen.add(span_id)
        return overlaps
