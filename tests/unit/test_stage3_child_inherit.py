"""Unit tests for Stage 3 AmbiguityResolver child span inheritance.

Covers:
- L3-F7: Child span inherits parent's section_context
- L3-F9: Child span uses suffix ID strategy (s5 → s5a, s5b)
- LLM overriding section_context takes precedence
- is_placeholder propagated from parent to child
- Fallback when parent is not found
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage3_ambiguity_resolver import AmbiguityResolver


class TestStage3ChildInherit:
    """Tests for Stage 3 child span creation with inheritance."""

    @pytest.fixture
    def parent_spans(self) -> list[SpanIR]:
        """Parent spans representing ambiguous span to be resolved."""
        return [
            SpanIR(
                span_id="s5",
                text="If sources are unavailable, flag the issue and ask for clarification.",
                section_context="Reusable Process",
                is_placeholder=False,
            ),
            SpanIR(
                span_id="s3",
                text="No external data allowed.",
                section_context="Policies",
                is_placeholder=False,
            ),
        ]

    @pytest.fixture
    def routes(self) -> FieldRouteIR:
        """Simple routes structure."""
        return FieldRouteIR()

    @pytest.fixture
    def resolver(self, pipeline_config: MagicMock, mock_client: MagicMock) -> AmbiguityResolver:
        """AmbiguityResolver instance."""
        return AmbiguityResolver(pipeline_config, mock_client)

    # =========================================================================
    # L3-F9: Suffix ID strategy
    # =========================================================================

    def test_single_child_gets_suffix_a(
        self,
        resolver: AmbiguityResolver,
        parent_spans: list[SpanIR],
        routes: FieldRouteIR,
        mock_client: MagicMock,
    ) -> None:
        """L3-F9-a: Single child gets suffix 'a' (s5 → s5a)."""
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {
                    "parent_span_id": "s5",
                    "span_id": "x1",  # ignored — override with suffix
                    "text": "If sources are unavailable",
                },
            ],
            "resolved_routes": {},
        }
        ambiguity_updates = [{"span_id": "s5", "reasons": ["compound sentence"]}]

        resolved_spans, _ = resolver.execute(
            (parent_spans, routes, ambiguity_updates)
        )

        children = [s for s in resolved_spans if s.span_id.startswith("s5")]
        assert len(children) == 1
        assert children[0].span_id == "s5a"

    def test_multiple_children_get_suffixes_abc(
        self,
        resolver: AmbiguityResolver,
        parent_spans: list[SpanIR],
        routes: FieldRouteIR,
        mock_client: MagicMock,
    ) -> None:
        """L3-F9-b: Multiple children get suffixes 'a', 'b', 'c'."""
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {
                    "parent_span_id": "s5",
                    "span_id": "x1",
                    "text": "If sources are unavailable",
                },
                {
                    "parent_span_id": "s5",
                    "span_id": "x2",
                    "text": "Flag the issue",
                },
                {
                    "parent_span_id": "s5",
                    "span_id": "x3",
                    "text": "Ask for clarification",
                },
            ],
            "resolved_routes": {},
        }
        ambiguity_updates = [{"span_id": "s5", "reasons": ["compound sentence"]}]

        resolved_spans, _ = resolver.execute(
            (parent_spans, routes, ambiguity_updates)
        )

        children = sorted(
            [s for s in resolved_spans if s.span_id.startswith("s5")],
            key=lambda s: s.span_id,
        )
        assert len(children) == 3
        assert children[0].span_id == "s5a"
        assert children[1].span_id == "s5b"
        assert children[2].span_id == "s5c"

    def test_child_without_parent_uses_llm_id(
        self,
        resolver: AmbiguityResolver,
        parent_spans: list[SpanIR],
        routes: FieldRouteIR,
        mock_client: MagicMock,
    ) -> None:
        """Child without a parent uses the LLM's span_id (fallback)."""
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {
                    "parent_span_id": "s999",  # non-existent parent
                    "span_id": "s_fallback",  # must start with 's' for SpanIR validation
                    "text": "Fallback span",
                },
            ],
            "resolved_routes": {},
        }
        ambiguity_updates = [{"span_id": "s5", "reasons": ["ambiguous"]}]

        resolved_spans, _ = resolver.execute(
            (parent_spans, routes, ambiguity_updates)
        )

        children = [s for s in resolved_spans if s.span_id == "s_fallback"]
        assert len(children) == 1

    # =========================================================================
    # L3-F7: Child inherits section_context from parent
    # =========================================================================

    def test_child_inherits_section_context_from_parent(
        self,
        resolver: AmbiguityResolver,
        parent_spans: list[SpanIR],
        routes: FieldRouteIR,
        mock_client: MagicMock,
    ) -> None:
        """L3-F7-a: Child inherits parent's section_context when LLM doesn't override."""
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {
                    "parent_span_id": "s5",
                    "span_id": "x1",
                    "text": "If sources are unavailable",
                    # No section_context → inherit from parent
                },
            ],
            "resolved_routes": {},
        }
        ambiguity_updates = [{"span_id": "s5", "reasons": ["compound sentence"]}]

        resolved_spans, _ = resolver.execute(
            (parent_spans, routes, ambiguity_updates)
        )

        children = [s for s in resolved_spans if s.span_id == "s5a"]
        assert len(children) == 1
        assert children[0].section_context == "Reusable Process"

    def test_child_overrides_section_context_when_llm_provides(
        self,
        resolver: AmbiguityResolver,
        parent_spans: list[SpanIR],
        routes: FieldRouteIR,
        mock_client: MagicMock,
    ) -> None:
        """LLM-provided section_context overrides parent's value."""
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {
                    "parent_span_id": "s5",
                    "span_id": "x1",
                    "text": "If sources are unavailable",
                    "section_context": "Failure Handling",  # override
                },
            ],
            "resolved_routes": {},
        }
        ambiguity_updates = [{"span_id": "s5", "reasons": ["compound sentence"]}]

        resolved_spans, _ = resolver.execute(
            (parent_spans, routes, ambiguity_updates)
        )

        children = [s for s in resolved_spans if s.span_id == "s5a"]
        assert len(children) == 1
        assert children[0].section_context == "Failure Handling"

    def test_child_no_parent_has_none_section_context(
        self,
        resolver: AmbiguityResolver,
        parent_spans: list[SpanIR],
        routes: FieldRouteIR,
        mock_client: MagicMock,
    ) -> None:
        """Child without parent has section_context=None."""
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {
                    "parent_span_id": "s999",
                    "span_id": "s_orphan",  # must start with 's'
                    "text": "Orphan span",
                },
            ],
            "resolved_routes": {},
        }
        ambiguity_updates = [{"span_id": "s5", "reasons": ["ambiguous"]}]

        resolved_spans, _ = resolver.execute(
            (parent_spans, routes, ambiguity_updates)
        )

        children = [s for s in resolved_spans if s.span_id == "s_orphan"]
        assert len(children) == 1
        assert children[0].section_context is None

    # =========================================================================
    # is_placeholder propagation
    # =========================================================================

    def test_child_inherits_placeholder_true_from_parent(
        self,
        resolver: AmbiguityResolver,
        routes: FieldRouteIR,
        mock_client: MagicMock,
    ) -> None:
        """Child inherits is_placeholder=True from parent."""
        placeholder_parent = SpanIR(
            span_id="s3",
            text="None",
            section_context="Policies",
            is_placeholder=True,
        )
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {
                    "parent_span_id": "s3",
                    "span_id": "x1",
                    "text": "No policy data needed",
                },
            ],
            "resolved_routes": {},
        }
        ambiguity_updates = [{"span_id": "s3", "reasons": ["placeholder"]}]

        resolved_spans, _ = resolver.execute(
            ([placeholder_parent], routes, ambiguity_updates)
        )

        children = [s for s in resolved_spans if s.span_id == "s3a"]
        assert len(children) == 1
        assert children[0].is_placeholder is True

    def test_child_inherits_placeholder_false_from_non_placeholder_parent(
        self,
        resolver: AmbiguityResolver,
        parent_spans: list[SpanIR],
        routes: FieldRouteIR,
        mock_client: MagicMock,
    ) -> None:
        """Child of non-placeholder parent has is_placeholder=False."""
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {
                    "parent_span_id": "s5",
                    "span_id": "x1",
                    "text": "Child content",
                },
            ],
            "resolved_routes": {},
        }
        ambiguity_updates = [{"span_id": "s5", "reasons": ["ambiguous"]}]

        resolved_spans, _ = resolver.execute(
            (parent_spans, routes, ambiguity_updates)
        )

        children = [s for s in resolved_spans if s.span_id == "s5a"]
        assert len(children) == 1
        assert children[0].is_placeholder is False

    # =========================================================================
    # Other inheritance (source_section_id, source_packet_id)
    # =========================================================================

    def test_child_inherits_section_id_and_packet_id(
        self,
        resolver: AmbiguityResolver,
        routes: FieldRouteIR,
        mock_client: MagicMock,
    ) -> None:
        """Child inherits source_section_id and source_packet_id from parent."""
        parent = SpanIR(
            span_id="s7",
            text="Parent content",
            source_section_id="sec_inputs",
            source_packet_id="pkt_002",
        )
        mock_client.call_json.return_value = {
            "resolved_spans": [
                {
                    "parent_span_id": "s7",
                    "span_id": "x1",
                    "text": "Child content",
                },
            ],
            "resolved_routes": {},
        }
        ambiguity_updates = [{"span_id": "s7", "reasons": ["ambiguous"]}]

        resolved_spans, _ = resolver.execute(
            ([parent], routes, ambiguity_updates)
        )

        children = [s for s in resolved_spans if s.span_id == "s7a"]
        assert len(children) == 1
        assert children[0].source_section_id == "sec_inputs"
        assert children[0].source_packet_id == "pkt_002"
