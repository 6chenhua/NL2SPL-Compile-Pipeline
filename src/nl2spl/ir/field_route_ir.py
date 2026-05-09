"""FieldRouteIR - Field routing result."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FieldRouteIR:
    """Field routing result.

    Attributes:
        identity: Spans routed to identity field
        audience: Spans routed to audience field
        rules: Spans routed to rules field
        domain: Spans routed to domain field
        integrations: Spans routed to integrations field
        behavior: Spans routed to behavior field
    """

    identity: list[str] = field(default_factory=list)
    audience: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    domain: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    behavior: list[str] = field(default_factory=list)

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

    def validate_no_overlap(self) -> list[str]:
        """Validate that no span appears in multiple fields.

        Returns:
            List of overlapping span IDs
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
