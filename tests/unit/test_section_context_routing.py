"""Unit tests for section_context routing in Stage 2 FieldRouter.

Covers:
- L3-F6: Delegation Policy routes to behavior (not rules)
- L3-F8: is_placeholder=True + section_context routes correctly
- Priority 1: canonical source_section_id takes precedence
- Priority 2: section_context exact match
- Priority 2b: keyword fallback
- Priority 3: default "behavior"
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.canonical.compile_input import CanonicalCompileInput, RawSection
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage2_field_router import FieldRouter


class TestSectionContextRouting:
    """Tests for _section_field() routing logic."""

    @pytest.fixture
    def canonical_input(self) -> CanonicalCompileInput:
        """Create a CanonicalCompileInput with test sections."""
        return CanonicalCompileInput(
            raw_text="test",
            raw_sections=[
                RawSection(
                    section_id="sec_task_family",
                    canonical_title="task_family",
                    original_title="Task Family",
                    text="Internal Communications",
                    order=1,
                ),
                RawSection(
                    section_id="sec_policies",
                    canonical_title="policies",
                    original_title="Policies",
                    text="Hard policies",
                    order=2,
                ),
                RawSection(
                    section_id="sec_inputs",
                    canonical_title="inputs",
                    original_title="Inputs",
                    text="Topic, Audience",
                    order=3,
                ),
            ],
            source_schema="structural_nl",
            schema_version="1.0",
        )

    # =========================================================================
    # L3-F6: Delegation Policy routes to behavior
    # =========================================================================

    def test_delegation_policy_routes_to_behavior(self, canonical_input: CanonicalCompileInput) -> None:
        """L3-F6: 'Delegation Policy' routes to 'behavior' (not 'rules')."""
        span = SpanIR(span_id="s1", text="Drafting", section_context="Delegation Policy")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "behavior"

    def test_policies_routes_to_rules(self, canonical_input: CanonicalCompileInput) -> None:
        """'Policies' section_context routes to 'rules'."""
        span = SpanIR(span_id="s1", text="No external data", section_context="Policies")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "rules"

    def test_task_family_routes_to_domain(self, canonical_input: CanonicalCompileInput) -> None:
        """'Task Family' routes to 'domain'."""
        span = SpanIR(span_id="s1", text="Internal Communications", section_context="Task Family")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "domain"

    def test_inputs_for_each_run_routes_to_resources(self, canonical_input: CanonicalCompileInput) -> None:
        """'Inputs for Each Run' routes to 'resources'."""
        span = SpanIR(span_id="s1", text="Topic", section_context="Inputs for Each Run")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "resources"

    def test_reusable_process_routes_to_behavior(self, canonical_input: CanonicalCompileInput) -> None:
        """'Reusable Process' routes to 'behavior'."""
        span = SpanIR(span_id="s1", text="Draft", section_context="Reusable Process")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "behavior"

    def test_failure_handling_routes_to_behavior(self, canonical_input: CanonicalCompileInput) -> None:
        """'Failure Handling' routes to 'behavior'."""
        span = SpanIR(span_id="s1", text="Missing inputs", section_context="Failure Handling")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "behavior"

    def test_required_outputs_routes_to_resources(self, canonical_input: CanonicalCompileInput) -> None:
        """'Required Outputs' routes to 'resources'."""
        span = SpanIR(span_id="s1", text="Draft message", section_context="Required Outputs")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "resources"

    # =========================================================================
    # L3-F8: is_placeholder=True routes by section_context
    # =========================================================================

    def test_placeholder_none_in_inputs_routes_to_resources(self, canonical_input: CanonicalCompileInput) -> None:
        """L3-F8-a: 'None' in Inputs context routes to resources."""
        span = SpanIR(
            span_id="s1",
            text="None",
            section_context="Inputs for Each Run",
            is_placeholder=True,
        )
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "resources"

    def test_placeholder_none_in_policies_routes_to_rules(self, canonical_input: CanonicalCompileInput) -> None:
        """L3-F8-b: 'None' in Policies context routes to rules."""
        span = SpanIR(
            span_id="s1",
            text="None",
            section_context="Policies",
            is_placeholder=True,
        )
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "rules"

    def test_placeholder_without_section_context_defaults_to_behavior(self, canonical_input: CanonicalCompileInput) -> None:
        """Placeholder without section_context falls back to behavior."""
        span = SpanIR(
            span_id="s1",
            text="None",
            is_placeholder=True,
        )
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "behavior"

    # =========================================================================
    # Priority levels
    # =========================================================================

    def test_priority_1_canonical_section_id_takes_precedence(self, canonical_input: CanonicalCompileInput) -> None:
        """Priority 1: source_section_id wins over section_context."""
        span = SpanIR(
            span_id="s1",
            text="Some text",
            source_section_id="sec_policies",  # canonical -> "rules"
            section_context="Task Family",  # would be "domain" if used
        )
        from nl2spl.adapters.section_semantic_mapper import RoutePrior
        canonical_input.route_priors = [
            RoutePrior(
                section_id="sec_policies",
                suggested_semantic_role="policies",
                suggested_field="rules",
                strength="strong",
                evidence="mock",
                source="llm"
            )
        ]
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "rules"  # canonical wins, not section_context

    def test_priority_2b_keyword_fallback_input(self, canonical_input: CanonicalCompileInput) -> None:
        """Priority 2b: keyword 'input' → resources."""
        span = SpanIR(span_id="s1", text="Topic", section_context="User Input Specification")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "resources"

    def test_priority_2b_keyword_fallback_rule(self, canonical_input: CanonicalCompileInput) -> None:
        """Priority 2b: keyword 'rule' → rules."""
        span = SpanIR(span_id="s1", text="Always cite", section_context="Citation Rules")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "rules"

    def test_priority_2b_keyword_fallback_process(self, canonical_input: CanonicalCompileInput) -> None:
        """Priority 2b: keyword 'process' → behavior."""
        span = SpanIR(span_id="s1", text="Step 1", section_context="Review Process Guidelines")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "behavior"

    def test_priority_3_default_behavior(self, canonical_input: CanonicalCompileInput) -> None:
        """Priority 3: no section info → behavior."""
        span = SpanIR(span_id="s1", text="Some text")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "behavior"

    def test_priority_3_unknown_section_context(self, canonical_input: CanonicalCompileInput) -> None:
        """Priority 3: unrecognized section_context → behavior."""
        span = SpanIR(span_id="s1", text="Some text", section_context="Random Context With No Matches")
        field = FieldRouter._section_field(span, canonical_input)
        assert field == "behavior"
