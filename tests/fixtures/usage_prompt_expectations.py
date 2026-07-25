"""Best expected prompt outputs for the examples/usage.py raw_text.

These fixtures are intentionally hand-authored. They describe the target IR a
good prompt should produce for the usage example, without running the whole
pipeline.
"""

from __future__ import annotations

from copy import deepcopy

from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, Concept, PersonaIR
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import (
    AlternativeFlow,
    DelegationCandidate,
    ExceptionFlow,
    FlowStructureIR,
)
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable

USAGE_RAW_TEXT = """
Task family:
Internal newsletters, announcements, update digests, executive briefs, and related
internal-comms artifacts.

Inputs for each run:
A user request, optional known topics, optional timeframe, available connectors or
source repositories, and optional format preferences.

Required outputs:
A draft communication artifact, a source/evidence set, a short assumptions log for any
unresolved items, and a completion status.

Reusable process:
First determine what kind of communication is requested. Then identify which required fields are still missing.
Ask only the highest-value clarifying questions needed to move forward.
If sources are needed and available, retrieve them using approved source recipes.
Maintain provenance for externally sourced facts.
When enough required information is available, produce a draft.
If the user asks for revision, revise while rechecking constraints.
Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms.

Policies:
Do not invent links or unseen facts.
Require evidence for sourced claims.
Limit questions per turn.
Prefer tool evidence over unnecessary user questioning.
Deny finalization if critical slots are missing or provenance fails.

Failure handling:
Missing timeframe, conflicting instructions, insufficient source access, evidence shortage, user refusal to answer, and provenance failure.

Delegation policy:
Optional delegated subtasks such as source gathering or template matching may be used
if bounded and the returned evidence is normalized into approved evidence carriers.
"""


USAGE_STAGE1_RESPONSE = {
    "spans": [
        {
            "span_id": "s1",
            "text": (
                "Task family: Internal newsletters, announcements, update digests, "
                "executive briefs, and related internal-comms artifacts."
            ),
        },
        {
            "span_id": "s2",
            "text": (
                "Inputs for each run: A user request, optional known topics, optional "
                "timeframe, available connectors or source repositories, and optional "
                "format preferences."
            ),
        },
        {
            "span_id": "s3",
            "text": (
                "Required outputs: A draft communication artifact, a source/evidence "
                "set, a short assumptions log for any unresolved items, and a "
                "completion status."
            ),
        },
        {
            "span_id": "s4",
            "text": (
                "Reusable process: First determine what kind of communication is "
                "requested."
            ),
        },
        {
            "span_id": "s5",
            "text": "Then identify which required fields are still missing.",
        },
        {
            "span_id": "s6",
            "text": (
                "Ask only the highest-value clarifying questions needed to move "
                "forward."
            ),
        },
        {
            "span_id": "s7",
            "text": (
                "If sources are needed and available, retrieve them using approved "
                "source recipes."
            ),
        },
        {
            "span_id": "s8",
            "text": "Maintain provenance for externally sourced facts.",
        },
        {
            "span_id": "s9",
            "text": "When enough required information is available, produce a draft.",
        },
        {
            "span_id": "s10",
            "text": (
                "If the user asks for revision, revise while rechecking constraints."
            ),
        },
        {
            "span_id": "s11",
            "text": (
                "Do not finalize if required slots remain missing unless the draft is "
                "explicitly marked as assumption-bearing and the user confirms."
            ),
        },
        {"span_id": "s12", "text": "Policies: Do not invent links or unseen facts."},
        {"span_id": "s13", "text": "Require evidence for sourced claims."},
        {"span_id": "s14", "text": "Limit questions per turn."},
        {
            "span_id": "s15",
            "text": "Prefer tool evidence over unnecessary user questioning.",
        },
        {
            "span_id": "s16",
            "text": (
                "Deny finalization if critical slots are missing or provenance fails."
            ),
        },
        {
            "span_id": "s17",
            "text": (
                "Failure handling: Missing timeframe, conflicting instructions, "
                "insufficient source access, evidence shortage, user refusal to "
                "answer, and provenance failure."
            ),
        },
        {
            "span_id": "s18",
            "text": (
                "Delegation policy: Optional delegated subtasks such as source "
                "gathering or template matching may be used if bounded and the "
                "returned evidence is normalized into approved evidence carriers."
            ),
        },
    ]
}


USAGE_STAGE2_RESPONSE = {
    "routes": {
        "identity": [],
        "audience": [],
        "rules": ["s12", "s13", "s14", "s15", "s16", "s18"],
        "domain": ["s1"],
        "integrations": [],
        "behavior": [
            "s2",
            "s3",
            "s4",
            "s5",
            "s6",
            "s7",
            "s8",
            "s9",
            "s10",
            "s11",
            "s17",
        ],
    },
    "ambiguity_updates": [
        {
            "span_id": "s18",
            "is_ambiguous": True,
            "reasons": ["mixed_delegation_action_and_policy_boundary"],
            "needs_split": True,
        }
    ],
}


USAGE_STAGE3_RESPONSE = {
    "resolved_spans": [
        {
            "span_id": "s18a",
            "text": (
                "Optional delegated subtasks include source gathering or template "
                "matching."
            ),
        },
        {
            "span_id": "s18b",
            "text": (
                "Delegated subtasks may be used only if bounded and returned "
                "evidence is normalized into approved evidence carriers."
            ),
        },
    ],
    "resolved_routes": {
        "identity": [],
        "audience": [],
        "rules": ["s12", "s13", "s14", "s15", "s16", "s18b"],
        "domain": ["s1"],
        "integrations": [],
        "behavior": [
            "s2",
            "s3",
            "s4",
            "s5",
            "s6",
            "s7",
            "s8",
            "s9",
            "s10",
            "s11",
            "s17",
            "s18a",
        ],
    },
}


USAGE_STAGE4_RESPONSE = {
    "main_flow_spans": ["s4", "s5", "s6", "s7", "s8", "s9"],
    "alternative_flows": [
        {
            "flow_id": "alt_1",
            "condition_text": "the user asks for revision",
            "spans": ["s10"],
        }
    ],
    "exception_flows": [
        {
            "flow_id": "exc_1",
            "condition_text": (
                "required slots remain missing and the draft is not confirmed as "
                "assumption-bearing"
            ),
            "spans": ["s11"],
        },
        {
            "flow_id": "exc_2",
            "condition_text": (
                "missing timeframe, conflicting instructions, insufficient source "
                "access, evidence shortage, user refusal to answer, or provenance "
                "failure"
            ),
            "spans": ["s17"],
        },
    ],
    "delegation_candidates": [
        {
            "candidate_id": "dc_1",
            "spans": ["s18a"],
            "reason": "Source gathering and template matching are bounded subtasks.",
            "suggested_type": "child_worker",
            "input_variables": ["user_request", "known_topics", "available_connectors"],
            "output_variables": ["source_evidence_set"],
        }
    ],
}


USAGE_STAGE5_RESPONSE = {
    "main_flow_blocks": [
        {
            "block_id": "b_1",
            "block_type": "SEQUENTIAL",
            "condition_text": None,
            "spans": ["s4", "s5", "s6"],
        },
        {
            "block_id": "b_2",
            "block_type": "IF",
            "condition_text": "sources are needed and available",
            "spans": ["s7"],
        },
        {
            "block_id": "b_3",
            "block_type": "SEQUENTIAL",
            "condition_text": None,
            "spans": ["s8"],
        },
        {
            "block_id": "b_4",
            "block_type": "IF",
            "condition_text": "enough required information is available",
            "spans": ["s9"],
        },
    ],
    "alternative_flow_blocks": {
        "alt_1": [
            {
                "block_id": "b_5",
                "block_type": "IF",
                "condition_text": "the user asks for revision",
                "spans": ["s10"],
            }
        ]
    },
    "exception_flow_blocks": {
        "exc_1": [
            {
                "block_id": "b_6",
                "block_type": "IF",
                "condition_text": (
                    "required slots remain missing and the draft is not confirmed "
                    "as assumption-bearing"
                ),
                "spans": ["s11"],
            }
        ],
        "exc_2": [
            {
                "block_id": "b_7",
                "block_type": "SEQUENTIAL",
                "condition_text": None,
                "spans": ["s17"],
            }
        ],
    },
}


USAGE_STAGE6_RESPONSE = {
    "variables": [
        {
            "name": "user_request",
            "data_type": "text",
            "required": True,
            "description": "User-provided request for the run.",
            "source": "input",
        },
        {
            "name": "known_topics",
            "data_type": "List[text]",
            "required": False,
            "description": "Optional known topics provided by the user.",
            "source": "input",
        },
        {
            "name": "timeframe",
            "data_type": "text",
            "required": False,
            "description": "Optional timeframe provided by the user.",
            "source": "input",
        },
        {
            "name": "available_connectors",
            "data_type": "List[text]",
            "required": True,
            "description": "Available connectors or source repositories.",
            "source": "input",
        },
        {
            "name": "format_preferences",
            "data_type": "text",
            "required": False,
            "description": "Optional format preferences provided by the user.",
            "source": "input",
        },
        {
            "name": "revision_request",
            "data_type": "boolean",
            "required": False,
            "description": "Whether the user asks for a revision.",
            "source": "input",
        },
        {
            "name": "user_confirmation",
            "data_type": "boolean",
            "required": False,
            "description": "Whether the user confirms an assumption-bearing draft.",
            "source": "input",
        },
        {
            "name": "draft_communication_artifact",
            "data_type": "text",
            "required": True,
            "description": "Draft communication artifact generated as output.",
            "source": "output",
        },
        {
            "name": "source_evidence_set",
            "data_type": "List[text]",
            "required": True,
            "description": "Sources and evidence used to support sourced claims.",
            "source": "output",
        },
        {
            "name": "assumptions_log",
            "data_type": "text",
            "required": True,
            "description": "Short log of assumptions for unresolved items.",
            "source": "output",
        },
        {
            "name": "completion_status",
            "data_type": "boolean",
            "required": True,
            "description": "Whether the run completed successfully.",
            "source": "output",
        },
        {
            "name": "communication_type",
            "data_type": "text",
            "required": True,
            "description": "Kind of communication requested.",
            "source": "step",
        },
        {
            "name": "missing_required_fields",
            "data_type": "List[text]",
            "required": True,
            "description": "Required fields still missing.",
            "source": "step",
        },
        {
            "name": "clarifying_questions",
            "data_type": "List[text]",
            "required": False,
            "description": "Highest-value clarifying questions.",
            "source": "step",
        },
        {
            "name": "sources_needed",
            "data_type": "boolean",
            "required": True,
            "description": "Whether external sources are needed.",
            "source": "step",
        },
        {
            "name": "sources_available",
            "data_type": "boolean",
            "required": True,
            "description": "Whether approved sources are available.",
            "source": "step",
        },
        {
            "name": "approved_source_recipes",
            "data_type": "List[text]",
            "required": False,
            "description": "Approved source retrieval recipes.",
            "source": "step",
        },
        {
            "name": "provenance_status",
            "data_type": "boolean",
            "required": True,
            "description": "Whether provenance is maintained for sourced facts.",
            "source": "step",
        },
        {
            "name": "required_slots_missing",
            "data_type": "boolean",
            "required": True,
            "description": "Whether required slots remain missing.",
            "source": "step",
        },
        {
            "name": "assumption_bearing_draft",
            "data_type": "boolean",
            "required": False,
            "description": "Whether the draft is marked assumption-bearing.",
            "source": "step",
        },
        {
            "name": "failure_conditions",
            "data_type": "List[text]",
            "required": True,
            "description": "Failure conditions encountered during the run.",
            "source": "step",
        },
    ],
    "files": [],
    "apis": [],
    "types": [],
}


USAGE_STAGE7_RESPONSE = {
    "steps": [
        {
            "step_id": "st_1",
            "text": "Determine the requested communication type.",
            "source_span_ids": ["s4"],
            "command_type": "GENERAL_COMMAND",
            "inputs": ["user_request", "known_topics", "format_preferences"],
            "outputs": ["communication_type"],
            "integration_ref": None,
            "flow_ref": "main",
            "block_ref": "b_1",
            "kind": "normal",
        },
        {
            "step_id": "st_2",
            "text": "Identify missing required fields and source availability.",
            "source_span_ids": ["s5"],
            "command_type": "GENERAL_COMMAND",
            "inputs": [
                "user_request",
                "known_topics",
                "timeframe",
                "available_connectors",
                "format_preferences",
            ],
            "outputs": [
                "missing_required_fields",
                "sources_needed",
                "sources_available",
            ],
            "integration_ref": None,
            "flow_ref": "main",
            "block_ref": "b_1",
            "kind": "normal",
        },
        {
            "step_id": "st_3",
            "text": "Ask the highest-value clarifying questions.",
            "source_span_ids": ["s6"],
            "command_type": "REQUEST_INPUT",
            "inputs": ["missing_required_fields"],
            "outputs": ["clarifying_questions"],
            "integration_ref": None,
            "flow_ref": "main",
            "block_ref": "b_1",
            "kind": "user_input",
        },
        {
            "step_id": "st_4",
            "text": "Retrieve source evidence using approved source recipes.",
            "source_span_ids": ["s7"],
            "command_type": "GENERAL_COMMAND",
            "inputs": [
                "user_request",
                "known_topics",
                "timeframe",
                "available_connectors",
                "approved_source_recipes",
            ],
            "outputs": ["source_evidence_set"],
            "integration_ref": None,
            "flow_ref": "main",
            "block_ref": "b_2",
            "kind": "normal",
        },
        {
            "step_id": "st_5",
            "text": "Maintain provenance for externally sourced facts.",
            "source_span_ids": ["s8"],
            "command_type": "GENERAL_COMMAND",
            "inputs": ["source_evidence_set"],
            "outputs": ["provenance_status"],
            "integration_ref": None,
            "flow_ref": "main",
            "block_ref": "b_3",
            "kind": "normal",
        },
        {
            "step_id": "st_6",
            "text": "Produce the draft communication artifact.",
            "source_span_ids": ["s9"],
            "command_type": "GENERAL_COMMAND",
            "inputs": [
                "user_request",
                "known_topics",
                "timeframe",
                "format_preferences",
                "source_evidence_set",
            ],
            "outputs": [
                "draft_communication_artifact",
                "assumptions_log",
                "completion_status",
            ],
            "integration_ref": None,
            "flow_ref": "main",
            "block_ref": "b_4",
            "kind": "normal",
        },
        {
            "step_id": "st_7",
            "text": "Revise the draft while rechecking constraints.",
            "source_span_ids": ["s10"],
            "command_type": "GENERAL_COMMAND",
            "inputs": ["revision_request", "draft_communication_artifact"],
            "outputs": ["draft_communication_artifact"],
            "integration_ref": None,
            "flow_ref": "alt_1",
            "block_ref": "b_5",
            "kind": "normal",
        },
        {
            "step_id": "st_8",
            "text": "Block finalization when required slots remain unresolved.",
            "source_span_ids": ["s11"],
            "command_type": "GENERAL_COMMAND",
            "inputs": [
                "required_slots_missing",
                "assumption_bearing_draft",
                "user_confirmation",
                "provenance_status",
            ],
            "outputs": ["completion_status"],
            "integration_ref": None,
            "flow_ref": "exc_1",
            "block_ref": "b_6",
            "kind": "normal",
        },
        {
            "step_id": "st_9",
            "text": "Handle failure conditions.",
            "source_span_ids": ["s17"],
            "command_type": "GENERAL_COMMAND",
            "inputs": ["failure_conditions"],
            "outputs": ["assumptions_log", "completion_status"],
            "integration_ref": None,
            "flow_ref": "exc_2",
            "block_ref": "b_7",
            "kind": "normal",
        },
    ],
    "new_variables": [],
}


USAGE_STAGE8_RESPONSE = {
    "persona": {
        "role": "Internal communications specialist",
        "aspects": [
            {
                "name": "EvidenceGrounded",
                "text": "Maintains evidence and provenance for sourced claims.",
            },
            {
                "name": "ClarificationFocused",
                "text": "Asks only high-value clarifying questions.",
            },
        ],
    },
    "audience": {
        "aspects": [
            {
                "name": "InternalCommsRequesters",
                "text": "Users requesting internal newsletters, announcements, or briefs.",
            }
        ]
    },
    "concepts": [
        {
            "term": "InternalCommsArtifact",
            "definition": "Newsletter, announcement, update digest, or executive brief.",
        },
        {
            "term": "SourceEvidenceSet",
            "definition": "Evidence package supporting externally sourced claims.",
        },
        {
            "term": "AssumptionsLog",
            "definition": "Short record of unresolved items and working assumptions.",
        },
        {
            "term": "Provenance",
            "definition": "Origin tracking for externally sourced facts.",
        },
    ],
}


USAGE_STAGE9_RESPONSE = {
    "constraints": [
        {
            "constraint_id": "c_1",
            "text": "Do not invent links or unseen facts.",
            "kind": "prohibition",
            "targets": ["global"],
            "source_span_ids": ["s12"],
        },
        {
            "constraint_id": "c_2",
            "text": "Require evidence for sourced claims.",
            "kind": "evidence",
            "targets": ["global"],
            "source_span_ids": ["s13"],
        },
        {
            "constraint_id": "c_3",
            "text": "Limit questions per turn.",
            "kind": "safety",
            "targets": ["step:st_3"],
            "source_span_ids": ["s14"],
        },
        {
            "constraint_id": "c_4",
            "text": "Prefer tool evidence over unnecessary user questioning.",
            "kind": "evidence",
            "targets": ["global"],
            "source_span_ids": ["s15"],
        },
        {
            "constraint_id": "c_5",
            "text": "Deny finalization if critical slots are missing or provenance fails.",
            "kind": "gate",
            "targets": ["step:st_8"],
            "source_span_ids": ["s16"],
        },
        {
            "constraint_id": "c_6",
            "text": (
                "Do not finalize if required slots remain missing unless the draft "
                "is explicitly marked as assumption-bearing and the user confirms."
            ),
            "kind": "gate",
            "targets": ["step:st_8"],
            "source_span_ids": ["s11"],
        },
        {
            "constraint_id": "c_7",
            "text": (
                "Delegated subtasks must be bounded and returned evidence must be "
                "normalized into approved evidence carriers."
            ),
            "kind": "delegation_boundary",
            "targets": ["global"],
            "source_span_ids": ["s18b"],
        },
    ]
}


def usage_stage_response(stage_num: int) -> dict:
    """Return a deep-copied mock LLM response for a usage prompt stage."""
    responses = {
        1: USAGE_STAGE1_RESPONSE,
        2: USAGE_STAGE2_RESPONSE,
        3: USAGE_STAGE3_RESPONSE,
        4: USAGE_STAGE4_RESPONSE,
        5: USAGE_STAGE5_RESPONSE,
        6: USAGE_STAGE6_RESPONSE,
        7: USAGE_STAGE7_RESPONSE,
        8: USAGE_STAGE8_RESPONSE,
        9: USAGE_STAGE9_RESPONSE,
    }
    return deepcopy(responses[stage_num])


def usage_stage1_spans() -> list[SpanIR]:
    """Return expected Stage 1 spans."""
    return [
        SpanIR(span_id=item["span_id"], text=item["text"])
        for item in USAGE_STAGE1_RESPONSE["spans"]
    ]


def usage_stage2_routes() -> FieldRouteIR:
    """Return expected Stage 2 field routes."""
    routes = USAGE_STAGE2_RESPONSE["routes"]
    return FieldRouteIR(**deepcopy(routes))


def usage_stage2_ambiguity_updates() -> list[dict]:
    """Return expected Stage 2 ambiguity updates."""
    return deepcopy(USAGE_STAGE2_RESPONSE["ambiguity_updates"])


def usage_stage3_spans() -> list[SpanIR]:
    """Return expected Stage 3 resolved spans."""
    original = [span for span in usage_stage1_spans() if span.span_id != "s18"]
    resolved = [
        SpanIR(span_id=item["span_id"], text=item["text"])
        for item in USAGE_STAGE3_RESPONSE["resolved_spans"]
    ]
    return original + resolved


def usage_stage3_routes() -> FieldRouteIR:
    """Return expected Stage 3 resolved routes."""
    routes = USAGE_STAGE3_RESPONSE["resolved_routes"]
    return FieldRouteIR(**deepcopy(routes))


def usage_stage4_flow() -> FlowStructureIR:
    """Return expected Stage 4 flow structure."""
    data = USAGE_STAGE4_RESPONSE
    return FlowStructureIR(
        main_flow_spans=deepcopy(data["main_flow_spans"]),
        alternative_flows=[AlternativeFlow(**item) for item in data["alternative_flows"]],
        exception_flows=[ExceptionFlow(**item) for item in data["exception_flows"]],
        delegation_candidates=[
            DelegationCandidate(**item) for item in data["delegation_candidates"]
        ],
    )


def usage_stage5_blocks() -> BlockStructureIR:
    """Return expected Stage 5 block structure."""
    data = USAGE_STAGE5_RESPONSE
    return BlockStructureIR(
        main_flow_blocks=[BlockIR(**item) for item in data["main_flow_blocks"]],
        alternative_flow_blocks={
            flow_id: [BlockIR(**item) for item in blocks]
            for flow_id, blocks in data["alternative_flow_blocks"].items()
        },
        exception_flow_blocks={
            flow_id: [BlockIR(**item) for item in blocks]
            for flow_id, blocks in data["exception_flow_blocks"].items()
        },
    )


def usage_stage6_resources() -> ResourceRegistryIR:
    """Return expected Stage 6 resource registry."""
    data = USAGE_STAGE6_RESPONSE
    return ResourceRegistryIR(
        variables=[
            VariableSpec(**item)
            for item in data["variables"]
            if item.get("source") != "step"
        ],
        files=[],
        apis=[],
        types=[],
    )


def usage_stage6_symbol_table() -> SymbolTable:
    """Return expected Stage 6 symbol table."""
    table = SymbolTable()
    for variable in usage_stage6_resources().variables:
        table.declare(
            name=variable.name,
            data_type=variable.data_type,
            source=variable.source,
            description=variable.description,
        )
    return table


def usage_stage7_steps() -> list[StepIR]:
    """Return expected Stage 7 steps."""
    return [StepIR(**item) for item in USAGE_STAGE7_RESPONSE["steps"]]


def usage_stage8_profile() -> AgentProfileIR:
    """Return expected Stage 8 profile."""
    data = USAGE_STAGE8_RESPONSE
    return AgentProfileIR(
        persona=PersonaIR(
            role=data["persona"]["role"],
            aspects=[Aspect(**item) for item in data["persona"]["aspects"]],
        ),
        audience_aspects=[Aspect(**item) for item in data["audience"]["aspects"]],
        concepts=[Concept(**item) for item in data["concepts"]],
    )


def usage_stage9_constraints() -> list[ConstraintIR]:
    """Return expected Stage 9 constraints."""
    return [ConstraintIR(**item) for item in USAGE_STAGE9_RESPONSE["constraints"]]


def assert_field_routes_equal(actual: FieldRouteIR, expected: FieldRouteIR) -> None:
    """Assert field routes are equal with a helpful message."""
    assert actual == expected, f"routes mismatch: {actual!r} != {expected!r}"


def assert_symbol_table_matches_resources(
    symbol_table: SymbolTable,
    resources: ResourceRegistryIR,
) -> None:
    """Assert a symbol table contains the same variables as a registry."""
    expected = {variable.name: variable for variable in resources.variables}
    assert set(symbol_table.variables) == set(expected)
    for name, variable in expected.items():
        symbol = symbol_table.variables[name]
        assert symbol.data_type == variable.data_type
        assert symbol.source == variable.source
        assert symbol.description == variable.description
