"""Shared fixtures for stage prompt isolation tests.

Contains mock LLM responses and expected IR outputs for each pipeline stage,
loaded from tests/fixtures/sample_inputs.py to avoid hardcoding.
"""

from __future__ import annotations

from nl2spl.ir import (
    AgentProfileIR,
    Aspect,
    BlockIR,
    BlockStructureIR,
    ConstraintIR,
    DelegationCandidate,
    FieldRouteIR,
    FlowStructureIR,
    PersonaIR,
    ResourceRegistryIR,
    SpanIR,
    StepIR,
    SymbolTable,
    VariableSpec,
)
from nl2spl.ir.flow_structure_ir import ExceptionFlow
from tests.fixtures.sample_inputs import (
    STAGE1_OUTPUT_STANDARD,
    STAGE4_OUTPUT_STANDARD,
    STAGE5_OUTPUT_STANDARD,
    STAGE6_OUTPUT_STANDARD,
    STAGE7_OUTPUT_STANDARD,
    STAGE8_OUTPUT_STANDARD,
    STAGE9_OUTPUT_STANDARD,
    STANDARD_INPUT,
)

# =============================================================================
# Raw Text Input
# =============================================================================

EXAMPLE_RAW_TEXT = STANDARD_INPUT


# =============================================================================
# Stage 1: SpanSlicer - Mock LLM Response & Expected Output
# =============================================================================

STAGE1_MOCK_LLM_RESPONSE = STAGE1_OUTPUT_STANDARD

STAGE1_EXPECTED_SPANS = [
    SpanIR(span_id="s1", text="Task family: Internal newsletters and announcements."),
    SpanIR(span_id="s2", text="Inputs for each run: A user request, optional known topics."),
    SpanIR(span_id="s3", text="Required outputs: A draft communication, completion status."),
    SpanIR(
        span_id="s4",
        text="Reusable process: First determine communication type. Then identify missing fields.",
    ),
    SpanIR(span_id="s5", text="Policies: Do not invent facts. Require evidence for claims."),
    SpanIR(span_id="s6", text="Failure handling: Missing timeframe, evidence shortage."),
    SpanIR(span_id="s7", text="Delegation policy: Optional source gathering if bounded."),
]


# =============================================================================
# Stage 2: FieldRouter - Mock LLM Response & Expected Output
# =============================================================================

STAGE2_MOCK_LLM_RESPONSE = {
    "routes": {
        "identity": [],
        "audience": [],
        "rules": ["s5"],
        "domain": [],
        "integrations": [],
        "behavior": ["s1", "s2", "s3", "s4", "s6", "s7"],
    },
    "ambiguity_updates": [],
}

STAGE2_EXPECTED_ROUTES = FieldRouteIR(
    identity=[],
    audience=[],
    rules=["s5"],
    domain=[],
    integrations=[],
    behavior=["s1", "s2", "s3", "s4", "s6", "s7"],
)

STAGE2_EXPECTED_AMBIGUITY_UPDATES: list[dict] = []


# =============================================================================
# Stage 3: AmbiguityResolver - Mock LLM Response & Expected Output
# =============================================================================

STAGE3_MOCK_LLM_RESPONSE = {
    "resolved_spans": [
        {"span_id": "s1a", "text": "Task family: Internal newsletters and announcements."},
    ],
    "resolved_routes": {
        "identity": [],
        "audience": [],
        "rules": ["s5"],
        "domain": [],
        "integrations": [],
        "behavior": ["s1a", "s2", "s3", "s4", "s6", "s7"],
    },
}

STAGE3_EXPECTED_SPANS = STAGE1_EXPECTED_SPANS  # No ambiguity in standard case

STAGE3_EXPECTED_ROUTES = FieldRouteIR(
    identity=[],
    audience=[],
    rules=["s5"],
    domain=[],
    integrations=[],
    behavior=["s1", "s2", "s3", "s4", "s6", "s7"],
)


# =============================================================================
# Stage 4: FlowAssembler - Mock LLM Response & Expected Output
# =============================================================================

STAGE4_MOCK_LLM_RESPONSE = STAGE4_OUTPUT_STANDARD

STAGE4_EXPECTED_FLOW = FlowStructureIR(
    main_flow_spans=["s4"],
    alternative_flows=[],
    exception_flows=[
        ExceptionFlow(
            flow_id="exc_1",
            condition_text="Missing timeframe or evidence shortage",
            spans=["s6"],
        ),
    ],
    delegation_candidates=[
        DelegationCandidate(
            candidate_id="dc_1",
            spans=["s7"],
            reason="Source gathering is an optional delegated task",
            suggested_type="api_call",
            input_variables=["user_request"],
            output_variables=["gathered_sources"],
        ),
    ],
)


# =============================================================================
# Stage 5: BlockAssembler - Mock LLM Response & Expected Output
# =============================================================================

STAGE5_MOCK_LLM_RESPONSE = STAGE5_OUTPUT_STANDARD

STAGE5_EXPECTED_BLOCKS = BlockStructureIR(
    main_flow_blocks=[
        BlockIR(block_id="b1", block_type="SEQUENTIAL", condition_text=None, spans=["s4"]),
    ],
    alternative_flow_blocks={},
    exception_flow_blocks={
        "exc_1": [
            BlockIR(block_id="b2", block_type="SEQUENTIAL", condition_text=None, spans=["s6"]),
        ],
    },
)


# =============================================================================
# Stage 6: ResourceExtractor - Mock LLM Response & Expected Output
# =============================================================================

STAGE6_MOCK_LLM_RESPONSE = STAGE6_OUTPUT_STANDARD

STAGE6_EXPECTED_RESOURCES = ResourceRegistryIR(
    variables=[
        VariableSpec(
            name="user_request",
            data_type="text",
            required=False,
            description="User's request text",
            source="input",
        ),
        VariableSpec(
            name="draft_communication",
            data_type="text",
            required=False,
            description="Draft communication text",
            source="output",
        ),
        VariableSpec(
            name="completion_status",
            data_type="text",
            required=False,
            description="Completion status indicator",
            source="output",
        ),
    ],
    files=[],
    apis=[],
    types=[],
)


def _build_stage6_expected_symbol_table() -> SymbolTable:
    """Build expected symbol table for Stage 6."""
    table = SymbolTable()
    table.declare(name="user_request", data_type="text", source="input", description="User's request text")
    table.declare(name="draft_communication", data_type="text", source="output", description="Draft communication text")
    table.declare(name="completion_status", data_type="text", source="output", description="Completion status indicator")
    return table


STAGE6_EXPECTED_SYMBOL_TABLE = _build_stage6_expected_symbol_table()


# =============================================================================
# Stage 7: StepExtractor - Mock LLM Response & Expected Output
# =============================================================================

STAGE7_MOCK_LLM_RESPONSE = STAGE7_OUTPUT_STANDARD

STAGE7_EXPECTED_STEPS = [
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
# Stage 8: ProfileExtractor - Mock LLM Response & Expected Output
# =============================================================================

STAGE8_MOCK_LLM_RESPONSE = STAGE8_OUTPUT_STANDARD

STAGE8_EXPECTED_PROFILE = AgentProfileIR(
    persona=PersonaIR(
        role="Internal Communications Assistant",
        aspects=[Aspect(name="ProfessionalTone", text="Maintains professional communication style")],
    ),
    audience_aspects=[Aspect(name="InternalStaff", text="Company employees and internal teams")],
    concepts=[],
)


# =============================================================================
# Stage 9: ConstraintExtractor - Mock LLM Response & Expected Output
# =============================================================================

STAGE9_MOCK_LLM_RESPONSE = STAGE9_OUTPUT_STANDARD

STAGE9_EXPECTED_CONSTRAINTS = [
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
# Helper Functions
# =============================================================================


def load_mock_response(stage_num: int) -> dict:
    """Load mock LLM response for a given stage number.

    Args:
        stage_num: Stage number (1-9)

    Returns:
        Mock LLM JSON response dict
    """
    mapping = {
        1: STAGE1_MOCK_LLM_RESPONSE,
        2: STAGE2_MOCK_LLM_RESPONSE,
        3: STAGE3_MOCK_LLM_RESPONSE,
        4: STAGE4_MOCK_LLM_RESPONSE,
        5: STAGE5_MOCK_LLM_RESPONSE,
        6: STAGE6_MOCK_LLM_RESPONSE,
        7: STAGE7_MOCK_LLM_RESPONSE,
        8: STAGE8_MOCK_LLM_RESPONSE,
        9: STAGE9_MOCK_LLM_RESPONSE,
    }
    return mapping[stage_num]


def compare_spans(actual: list[SpanIR], expected: list[SpanIR]) -> list[str]:
    """Compare actual vs expected spans, returning mismatches.

    Args:
        actual: Actual span list from stage execution
        expected: Expected span list

    Returns:
        List of mismatch descriptions (empty if all match)
    """
    mismatches = []
    if len(actual) != len(expected):
        mismatches.append(f"Span count: {len(actual)} != {len(expected)}")
        return mismatches
    for a, e in zip(actual, expected, strict=False):
        if a.span_id != e.span_id:
            mismatches.append(f"span_id mismatch: {a.span_id} != {e.span_id}")
        if a.text != e.text:
            mismatches.append(f"text mismatch for {a.span_id}: {a.text!r} != {e.text!r}")
    return mismatches


def compare_field_routes(actual: FieldRouteIR, expected: FieldRouteIR) -> list[str]:
    """Compare actual vs expected field routes, returning mismatches.

    Args:
        actual: Actual field route from stage execution
        expected: Expected field route

    Returns:
        List of mismatch descriptions (empty if all match)
    """
    mismatches = []
    for field_name in ["identity", "audience", "rules", "domain", "integrations", "behavior"]:
        actual_set = set(getattr(actual, field_name))
        expected_set = set(getattr(expected, field_name))
        if actual_set != expected_set:
            mismatches.append(
                f"{field_name}: {sorted(actual_set)} != {sorted(expected_set)}"
            )
    return mismatches


def compare_flow_structures(actual: FlowStructureIR, expected: FlowStructureIR) -> list[str]:
    """Compare actual vs expected flow structures, returning mismatches.

    Args:
        actual: Actual flow structure from stage execution
        expected: Expected flow structure

    Returns:
        List of mismatch descriptions (empty if all match)
    """
    mismatches = []
    if set(actual.main_flow_spans) != set(expected.main_flow_spans):
        mismatches.append(
            f"main_flow_spans: {actual.main_flow_spans} != {expected.main_flow_spans}"
        )
    if len(actual.alternative_flows) != len(expected.alternative_flows):
        mismatches.append(
            f"alternative_flows count: {len(actual.alternative_flows)} != {len(expected.alternative_flows)}"
        )
    if len(actual.exception_flows) != len(expected.exception_flows):
        mismatches.append(
            f"exception_flows count: {len(actual.exception_flows)} != {len(expected.exception_flows)}"
        )
    if len(actual.delegation_candidates) != len(expected.delegation_candidates):
        mismatches.append(
            f"delegation_candidates count: {len(actual.delegation_candidates)} != {len(expected.delegation_candidates)}"
        )
    return mismatches


def compare_block_structures(actual: BlockStructureIR, expected: BlockStructureIR) -> list[str]:
    """Compare actual vs expected block structures, returning mismatches.

    Args:
        actual: Actual block structure from stage execution
        expected: Expected block structure

    Returns:
        List of mismatch descriptions (empty if all match)
    """
    mismatches = []
    if len(actual.main_flow_blocks) != len(expected.main_flow_blocks):
        mismatches.append(
            f"main_flow_blocks count: {len(actual.main_flow_blocks)} != {len(expected.main_flow_blocks)}"
        )
    else:
        for a, e in zip(actual.main_flow_blocks, expected.main_flow_blocks, strict=False):
            if a.block_id != e.block_id or a.block_type != e.block_type:
                mismatches.append(f"main block mismatch: {a.block_id}({a.block_type}) != {e.block_id}({e.block_type})")
    if set(actual.alternative_flow_blocks.keys()) != set(expected.alternative_flow_blocks.keys()):
        mismatches.append(
            f"alternative_flow_blocks keys: {list(actual.alternative_flow_blocks.keys())} != {list(expected.alternative_flow_blocks.keys())}"
        )
    if set(actual.exception_flow_blocks.keys()) != set(expected.exception_flow_blocks.keys()):
        mismatches.append(
            f"exception_flow_blocks keys: {list(actual.exception_flow_blocks.keys())} != {list(expected.exception_flow_blocks.keys())}"
        )
    return mismatches


def compare_steps(actual: list[StepIR], expected: list[StepIR]) -> list[str]:
    """Compare actual vs expected steps, returning mismatches.

    Args:
        actual: Actual step list from stage execution
        expected: Expected step list

    Returns:
        List of mismatch descriptions (empty if all match)
    """
    mismatches = []
    if len(actual) != len(expected):
        mismatches.append(f"Step count: {len(actual)} != {len(expected)}")
        return mismatches
    for a, e in zip(actual, expected, strict=False):
        if a.step_id != e.step_id:
            mismatches.append(f"step_id mismatch: {a.step_id} != {e.step_id}")
        if a.text != e.text:
            mismatches.append(f"text mismatch for {a.step_id}: {a.text!r} != {e.text!r}")
        if a.command_type != e.command_type:
            mismatches.append(f"command_type mismatch for {a.step_id}: {a.command_type} != {e.command_type}")
        if a.flow_ref != e.flow_ref:
            mismatches.append(f"flow_ref mismatch for {a.step_id}: {a.flow_ref} != {e.flow_ref}")
    return mismatches


def compare_constraints(actual: list[ConstraintIR], expected: list[ConstraintIR]) -> list[str]:
    """Compare actual vs expected constraints, returning mismatches.

    Args:
        actual: Actual constraint list from stage execution
        expected: Expected constraint list

    Returns:
        List of mismatch descriptions (empty if all match)
    """
    mismatches = []
    if len(actual) != len(expected):
        mismatches.append(f"Constraint count: {len(actual)} != {len(expected)}")
        return mismatches
    for a, e in zip(actual, expected, strict=False):
        if a.constraint_id != e.constraint_id:
            mismatches.append(f"constraint_id mismatch: {a.constraint_id} != {e.constraint_id}")
        if a.kind != e.kind:
            mismatches.append(f"kind mismatch for {a.constraint_id}: {a.kind} != {e.kind}")
        if set(a.targets) != set(e.targets):
            mismatches.append(f"targets mismatch for {a.constraint_id}: {a.targets} != {e.targets}")
    return mismatches


def compare_profiles(actual: AgentProfileIR, expected: AgentProfileIR) -> list[str]:
    """Compare actual vs expected agent profiles, returning mismatches.

    Args:
        actual: Actual agent profile from stage execution
        expected: Expected agent profile

    Returns:
        List of mismatch descriptions (empty if all match)
    """
    mismatches = []
    if actual.persona.role != expected.persona.role:
        mismatches.append(f"persona.role: {actual.persona.role!r} != {expected.persona.role!r}")
    if len(actual.persona.aspects) != len(expected.persona.aspects):
        mismatches.append(
            f"persona.aspects count: {len(actual.persona.aspects)} != {len(expected.persona.aspects)}"
        )
    if len(actual.audience_aspects) != len(expected.audience_aspects):
        mismatches.append(
            f"audience_aspects count: {len(actual.audience_aspects)} != {len(expected.audience_aspects)}"
        )
    if len(actual.concepts) != len(expected.concepts):
        mismatches.append(
            f"concepts count: {len(actual.concepts)} != {len(expected.concepts)}"
        )
    return mismatches


def compare_resource_registries(actual: ResourceRegistryIR, expected: ResourceRegistryIR) -> list[str]:
    """Compare actual vs expected resource registries, returning mismatches.

    Args:
        actual: Actual resource registry from stage execution
        expected: Expected resource registry

    Returns:
        List of mismatch descriptions (empty if all match)
    """
    mismatches = []
    actual_var_names = {v.name for v in actual.variables}
    expected_var_names = {v.name for v in expected.variables}
    if actual_var_names != expected_var_names:
        mismatches.append(f"variable names: {sorted(actual_var_names)} != {sorted(expected_var_names)}")
    if len(actual.files) != len(expected.files):
        mismatches.append(f"files count: {len(actual.files)} != {len(expected.files)}")
    if len(actual.apis) != len(expected.apis):
        mismatches.append(f"apis count: {len(actual.apis)} != {len(expected.apis)}")
    if len(actual.types) != len(expected.types):
        mismatches.append(f"types count: {len(actual.types)} != {len(expected.types)}")
    return mismatches


def generate_test_report(
    stage_num: int,
    stage_name: str,
    mismatches: list[str],
) -> str:
    """Generate a human-readable test report for a stage prompt test.

    Args:
        stage_num: Stage number (1-9)
        stage_name: Stage class name
        mismatches: List of mismatch descriptions

    Returns:
        Formatted test report string
    """
    status = "PASS" if not mismatches else "FAIL"
    lines = [
        f"Stage {stage_num} Prompt Test Report: {stage_name}",
        f"Status: {status}",
    ]
    if mismatches:
        lines.append("Mismatches:")
        for m in mismatches:
            lines.append(f"  - {m}")
    else:
        lines.append("All assertions passed.")
    return "\n".join(lines)
