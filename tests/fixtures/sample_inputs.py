"""Sample inputs for NL2SPL pipeline testing."""

from __future__ import annotations

# =============================================================================
# Raw Text Inputs (for Stage 1 - SpanSlicer)
# =============================================================================

# Simple single-paragraph input
SIMPLE_INPUT = """First determine what kind of communication is requested.
Then identify missing required fields.
Do not invent facts or make assumptions."""

# Standard 7-section input (typical use case)
STANDARD_INPUT = """Task family: Internal newsletters and announcements.
Inputs for each run: A user request, optional known topics.
Required outputs: A draft communication, completion status.
Reusable process: First determine communication type. Then identify missing fields.
Policies: Do not invent facts. Require evidence for claims.
Failure handling: Missing timeframe, evidence shortage.
Delegation policy: Optional source gathering if bounded."""

# Complex input with multiple flows
COMPLEX_INPUT = """Task family: Customer support ticket handling.
Inputs for each run: Customer message, ticket history, product knowledge base.
Required outputs: Response draft, ticket status, escalation decision.
Reusable process: First classify the issue type. Then check knowledge base for solutions.
If the issue is known, apply standard resolution. Otherwise, escalate to specialist.
Policies: Always acknowledge the customer within 2 hours. Never share internal system details.
Require evidence for any technical claims. Document all actions in the ticket.
Failure handling: If knowledge base is unavailable, use fallback responses.
When escalation fails, notify supervisor immediately.
Delegation policy: Delegate language translation to the translation service.
Delegate billing inquiries to the finance team."""

# Input with ambiguity (spans that could belong to multiple fields)
AMBIGUOUS_INPUT = """You are a helpful assistant who must follow strict guidelines.
First determine the user's intent. Then provide accurate information.
Never make assumptions about user preferences.
Use the search API to find relevant information.
For each result, verify the source credibility."""

# Input with loops and conditions
LOOP_INPUT = """For each item in the request list, validate the format.
If validation fails, add error to the error list.
While there are unprocessed items, continue processing.
When all items are processed, generate the summary report."""

# Minimal input (edge case)
MINIMAL_INPUT = """Respond to the user's greeting."""

# Input with delegation candidates
DELEGATION_INPUT = """Handle the user's request for data analysis.
First, gather the raw data from the database.
Then delegate the statistical analysis to the analytics service.
Process the results and format them for presentation.
If the analysis fails, use the fallback calculation method."""


# =============================================================================
# Expected Stage 1 Output (SpanSlicer)
# =============================================================================

STAGE1_OUTPUT_SIMPLE = {
    "spans": [
        {"span_id": "s1", "text": "First determine what kind of communication is requested."},
        {"span_id": "s2", "text": "Then identify missing required fields."},
        {"span_id": "s3", "text": "Do not invent facts or make assumptions."},
    ]
}

STAGE1_OUTPUT_STANDARD = {
    "spans": [
        {"span_id": "s1", "text": "Task family: Internal newsletters and announcements."},
        {"span_id": "s2", "text": "Inputs for each run: A user request, optional known topics."},
        {"span_id": "s3", "text": "Required outputs: A draft communication, completion status."},
        {
            "span_id": "s4",
            "text": "Reusable process: First determine communication type. Then identify missing fields.",
        },
        {"span_id": "s5", "text": "Policies: Do not invent facts. Require evidence for claims."},
        {"span_id": "s6", "text": "Failure handling: Missing timeframe, evidence shortage."},
        {
            "span_id": "s7",
            "text": "Delegation policy: Optional source gathering if bounded.",
        },
    ]
}


# =============================================================================
# Expected Stage 2 Output (FieldRouter)
# =============================================================================

STAGE2_OUTPUT_STANDARD = {
    "routes": {
        "identity": [],
        "audience": [],
        "rules": ["s5"],
        "domain": [],
        "integrations": [],
        "behavior": ["s4"],
    },
    "ambiguity_updates": [],
}


# =============================================================================
# Expected Stage 3 Output (AmbiguityResolver)
# =============================================================================

STAGE3_OUTPUT_STANDARD = {
    "resolved_spans": [],
    "resolved_routes": {
        "identity": [],
        "audience": [],
        "rules": ["s5"],
        "domain": [],
        "integrations": [],
        "behavior": ["s1", "s2", "s3", "s4", "s6", "s7"],
    },
}


# =============================================================================
# Expected Stage 4 Output (FlowAssembler)
# =============================================================================

STAGE4_OUTPUT_STANDARD = {
    "main_flow_spans": ["s4"],
    "alternative_flows": [],
    "exception_flows": [
        {
            "flow_id": "exc_1",
            "condition_text": "Missing timeframe or evidence shortage",
            "spans": ["s6"],
        }
    ],
    "delegation_candidates": [
        {
            "candidate_id": "dc_1",
            "spans": ["s7"],
            "reason": "Source gathering is an optional delegated task",
            "suggested_type": "api_call",
            "input_variables": ["user_request"],
            "output_variables": ["gathered_sources"],
        }
    ],
}


# =============================================================================
# Expected Stage 5 Output (BlockAssembler)
# =============================================================================

STAGE5_OUTPUT_STANDARD = {
    "main_flow_blocks": [
        {
            "block_id": "b1",
            "block_type": "SEQUENTIAL",
            "condition_text": None,
            "spans": ["s4"],
        }
    ],
    "alternative_flow_blocks": {},
    "exception_flow_blocks": {
        "exc_1": [
            {
                "block_id": "b2",
                "block_type": "SEQUENTIAL",
                "condition_text": None,
                "spans": ["s6"],
            }
        ]
    },
}


# =============================================================================
# Expected Stage 6 Output (ResourceExtractor)
# =============================================================================

STAGE6_OUTPUT_STANDARD = {
    "variables": [
        {
            "name": "user_request",
            "data_type": "text",
            "source": "input",
            "description": "User's request text",
        },
        {
            "name": "draft_communication",
            "data_type": "text",
            "source": "output",
            "description": "Draft communication text",
        },
        {
            "name": "completion_status",
            "data_type": "text",
            "source": "output",
            "description": "Completion status indicator",
        },
        {
            "name": "communication_type",
            "data_type": "text",
            "source": "step",
            "description": "Type of communication determined",
        },
        {
            "name": "missing_fields",
            "data_type": "List[text]",
            "source": "step",
            "description": "List of missing required fields",
        },
    ],
    "files": [],
    "apis": [],
    "types": [],
}


# =============================================================================
# Expected Stage 7 Output (StepExtractor)
# =============================================================================

STAGE7_OUTPUT_STANDARD = {
    "steps": [
        {
            "step_id": "st1",
            "text": "Determine communication type",
            "source_span_ids": ["s4"],
            "command_type": "GENERAL_COMMAND",
            "inputs": ["user_request"],
            "outputs": ["communication_type"],
            "integration_ref": None,
            "flow_ref": "main",
            "block_ref": "b1",
            "kind": "normal",
        },
        {
            "step_id": "st2",
            "text": "Identify missing required fields",
            "source_span_ids": ["s4"],
            "command_type": "GENERAL_COMMAND",
            "inputs": ["communication_type"],
            "outputs": ["missing_fields"],
            "integration_ref": None,
            "flow_ref": "main",
            "block_ref": "b1",
            "kind": "normal",
        },
    ],
    "new_variables": [],
}


# =============================================================================
# Expected Stage 8 Output (ProfileExtractor)
# =============================================================================

STAGE8_OUTPUT_STANDARD = {
    "persona": {
        "role": "Internal Communications Assistant",
        "aspects": [
            {"name": "ProfessionalTone", "text": "Maintains professional communication style"},
        ],
    },
    "audience": {
        "aspects": [
            {"name": "InternalStaff", "text": "Company employees and internal teams"},
        ],
    },
    "concepts": [],
}


# =============================================================================
# Expected Stage 9 Output (ConstraintExtractor)
# =============================================================================

STAGE9_OUTPUT_STANDARD = {
    "constraints": [
        {
            "constraint_id": "c1",
            "text": "Do not invent facts or make assumptions.",
            "kind": "prohibition",
            "targets": ["global"],
            "source_span_ids": ["s5"],
        },
        {
            "constraint_id": "c2",
            "text": "Require evidence for claims.",
            "kind": "evidence",
            "targets": ["global"],
            "source_span_ids": ["s5"],
        },
    ],
}


# =============================================================================
# Test Case Collections
# =============================================================================

# All simple test cases
SIMPLE_CASES = {
    "minimal": MINIMAL_INPUT,
    "simple": SIMPLE_INPUT,
}

# All standard test cases
STANDARD_CASES = {
    "standard": STANDARD_INPUT,
    "ambiguous": AMBIGUOUS_INPUT,
}

# All complex test cases
COMPLEX_CASES = {
    "complex": COMPLEX_INPUT,
    "loop": LOOP_INPUT,
    "delegation": DELEGATION_INPUT,
}

# All test cases
ALL_CASES = {**SIMPLE_CASES, **STANDARD_CASES, **COMPLEX_CASES}


# =============================================================================
# Edge Cases
# =============================================================================

EDGE_CASES = {
    "empty": "",
    "whitespace": "   \n\t  ",
    "single_word": "Hello",
    "single_sentence": "This is a single sentence.",
    "very_long": "This is a test. " * 1000,  # Repeated text
    "special_chars": "Use <angle> brackets & 'quotes' carefully.",
    "unicode": "支持中文输入和处理。",
    "mixed_language": "Handle both English and 中文 text.",
}
