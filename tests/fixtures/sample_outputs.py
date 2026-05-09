"""Sample outputs for NL2SPL pipeline testing.

These are expected IR outputs for use in unit tests and integration tests.
"""

from __future__ import annotations

from nl2spl.ir import (
    AmbiguityInfo,
    BlockIR,
    BlockStructureIR,
    ConstraintIR,
    DelegationCandidate,
    FieldRouteIR,
    FlowStructureIR,
    ResourceRegistryIR,
    SpanIR,
    StepIR,
    SymbolTable,
    VariableSymbol,
)


# =============================================================================
# Stage 1 Outputs (SpanSlicer)
# =============================================================================

def make_standard_spans() -> list[SpanIR]:
    """Create standard spans for testing."""
    return [
        SpanIR(
            span_id="s1",
            text="Task family: Internal newsletters and announcements.",
            ambiguity=AmbiguityInfo(),
        ),
        SpanIR(
            span_id="s2",
            text="Inputs for each run: A user request, optional known topics.",
            ambiguity=AmbiguityInfo(),
        ),
        SpanIR(
            span_id="s3",
            text="Required outputs: A draft communication, completion status.",
            ambiguity=AmbiguityInfo(),
        ),
        SpanIR(
            span_id="s4",
            text="Reusable process: First determine communication type. Then identify missing fields.",
            ambiguity=AmbiguityInfo(),
        ),
        SpanIR(
            span_id="s5",
            text="Policies: Do not invent facts. Require evidence for claims.",
            ambiguity=AmbiguityInfo(),
        ),
        SpanIR(
            span_id="s6",
            text="Failure handling: Missing timeframe, evidence shortage.",
            ambiguity=AmbiguityInfo(),
        ),
        SpanIR(
            span_id="s7",
            text="Delegation policy: Optional source gathering if bounded.",
            ambiguity=AmbiguityInfo(),
        ),
    ]


# =============================================================================
# Stage 2 Outputs (FieldRouter)
# =============================================================================

def make_standard_field_route() -> FieldRouteIR:
    """Create standard field route for testing."""
    return FieldRouteIR(
        identity=[],
        audience=[],
        rules=["s5"],
        domain=[],
        integrations=[],
        behavior=["s1", "s2", "s3", "s4", "s6", "s7"],
    )


# =============================================================================
# Stage 3 Outputs (AmbiguityResolver)
# =============================================================================

def make_resolved_spans() -> list[SpanIR]:
    """Create resolved spans (after ambiguity resolution)."""
    return make_standard_spans()  # No ambiguity in standard case


def make_resolved_field_route() -> FieldRouteIR:
    """Create resolved field route."""
    return make_standard_field_route()


# =============================================================================
# Stage 4 Outputs (FlowAssembler)
# =============================================================================

def make_standard_flow_structure() -> FlowStructureIR:
    """Create standard flow structure for testing."""
    return FlowStructureIR(
        main_flow_spans=["s4"],
        alternative_flows=[],
        exception_flows=[],  # s6 is handled as exception but kept simple for now
        delegation_candidates=[
            DelegationCandidate(
                candidate_id="dc_1",
                spans=["s7"],
                reason="Source gathering is optional and bounded",
                suggested_type="api_call",
                input_variables=["user_request"],
                output_variables=["gathered_sources"],
            ),
        ],
    )


# =============================================================================
# Stage 5 Outputs (BlockAssembler)
# =============================================================================

def make_standard_block_structure() -> BlockStructureIR:
    """Create standard block structure for testing."""
    return BlockStructureIR(
        main_flow_blocks=[
            BlockIR(
                block_id="b1",
                block_type="SEQUENTIAL",
                condition_text=None,
                spans=["s4"],
            ),
        ],
        alternative_flow_blocks={},
        exception_flow_blocks={},
    )


# =============================================================================
# Stage 6 Outputs (ResourceExtractor)
# =============================================================================

def make_standard_resource_registry() -> ResourceRegistryIR:
    """Create standard resource registry for testing."""
    return ResourceRegistryIR(
        variables=[],
        files=[],
        apis=[],
        types=[],
    )


def make_standard_symbol_table() -> SymbolTable:
    """Create standard symbol table for testing."""
    table = SymbolTable()
    table.declare(
        name="user_request",
        data_type="text",
        source="input",
        description="User's request text",
    )
    table.declare(
        name="draft_communication",
        data_type="text",
        source="output",
        description="Draft communication text",
    )
    table.declare(
        name="completion_status",
        data_type="text",
        source="output",
        description="Completion status indicator",
    )
    table.declare(
        name="communication_type",
        data_type="text",
        source="step",
        description="Type of communication determined",
    )
    table.declare(
        name="missing_fields",
        data_type="List[text]",
        source="step",
        description="List of missing required fields",
    )
    return table


# =============================================================================
# Stage 7 Outputs (StepExtractor)
# =============================================================================

def make_standard_steps() -> list[StepIR]:
    """Create standard steps for testing."""
    return [
        StepIR(
            step_id="st1",
            text="Determine communication type",
            source_span_ids=["s4"],
            command_type="GENERAL_COMMAND",
            inputs=["user_request"],
            outputs=["communication_type"],
            integration_ref=None,
            flow_ref="main",
            block_ref="b1",
            kind="normal",
        ),
        StepIR(
            step_id="st2",
            text="Identify missing required fields",
            source_span_ids=["s4"],
            command_type="GENERAL_COMMAND",
            inputs=["communication_type"],
            outputs=["missing_fields"],
            integration_ref=None,
            flow_ref="main",
            block_ref="b1",
            kind="normal",
        ),
    ]


# =============================================================================
# Stage 8 Outputs (ProfileExtractor)
# =============================================================================

def make_standard_agent_profile() -> dict:
    """Create standard agent profile for testing."""
    return {
        "persona": {
            "role": "Internal Communications Assistant",
            "aspects": [
                {
                    "name": "ProfessionalTone",
                    "text": "Maintains professional communication style",
                },
            ],
        },
        "audience": {
            "aspects": [
                {
                    "name": "InternalStaff",
                    "text": "Company employees and internal teams",
                },
            ],
        },
        "concepts": [],
    }


# =============================================================================
# Stage 9 Outputs (ConstraintExtractor)
# =============================================================================

def make_standard_constraints() -> list[ConstraintIR]:
    """Create standard constraints for testing."""
    return [
        ConstraintIR(
            constraint_id="c1",
            text="Do not invent facts or make assumptions.",
            kind="prohibition",
            targets=["global"],
            source_span_ids=["s5"],
        ),
        ConstraintIR(
            constraint_id="c2",
            text="Require evidence for claims.",
            kind="evidence",
            targets=["global"],
            source_span_ids=["s5"],
        ),
    ]


# =============================================================================
# Complete Pipeline Output
# =============================================================================

def make_standard_pipeline_result() -> dict:
    """Create complete standard pipeline result for integration testing."""
    return {
        "spans": [s.__dict__ for s in make_standard_spans()],
        "field_route": make_standard_field_route().__dict__,
        "flow_structure": make_standard_flow_structure().__dict__,
        "block_structure": make_standard_block_structure().__dict__,
        "resource_registry": make_standard_resource_registry().__dict__,
        "symbol_table": {
            name: var.__dict__
            for name, var in make_standard_symbol_table().variables.items()
        },
        "steps": [s.__dict__ for s in make_standard_steps()],
        "agent_profile": make_standard_agent_profile(),
        "constraints": [c.__dict__ for c in make_standard_constraints()],
    }


# =============================================================================
# Test Helpers
# =============================================================================

def assert_spans_equal(actual: list[SpanIR], expected: list[SpanIR]) -> None:
    """Assert that two span lists are equal."""
    assert len(actual) == len(expected), f"Length mismatch: {len(actual)} != {len(expected)}"
    for a, e in zip(actual, expected):
        assert a.span_id == e.span_id, f"span_id mismatch: {a.span_id} != {e.span_id}"
        assert a.text == e.text, f"text mismatch for {a.span_id}"


def assert_field_route_equal(actual: FieldRouteIR, expected: FieldRouteIR) -> None:
    """Assert that two field routes are equal."""
    assert set(actual.identity) == set(expected.identity)
    assert set(actual.audience) == set(expected.audience)
    assert set(actual.rules) == set(expected.rules)
    assert set(actual.domain) == set(expected.domain)
    assert set(actual.integrations) == set(expected.integrations)
    assert set(actual.behavior) == set(expected.behavior)
