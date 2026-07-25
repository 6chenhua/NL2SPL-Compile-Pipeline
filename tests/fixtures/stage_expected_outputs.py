"""Expected input/output test data for each pipeline stage.

This module provides comprehensive test fixtures for all 12 pipeline stages
using the example raw_text from examples/usage.py (internal newsletters/announcements).

Each stage includes:
- stage_name: Name of the stage
- description: What the stage does
- input_data: What the stage receives
- expected_output: What the stage should produce
- key_points: Things to verify in tests
"""

from __future__ import annotations

# =============================================================================
# RAW TEXT INPUT (from examples/usage.py)
# =============================================================================

USAGE_EXAMPLE_RAW_TEXT = """Task family:
Internal newsletters, announcements, update digests, executive briefs, and related
internal-comms artifacts.

Inputs for each run:
A user request, optional known topics, optional timeframe, available connectors or
source repositories, and optional format preferences.

Required outputs:
A draft communication artifact, a source/evidence set, a short assumptions log for any
unresolved items, and a completion status.

Reusable process:
First determine what kind of communication is requested. Then identify which required
fields are still missing. Ask only the highest-value clarifying questions needed to move
forward. If sources are needed and available, retrieve them using approved source
recipes. Maintain provenance for externally sourced facts. When enough required
information is available, produce a draft. If the user asks for revision, revise while re
checking constraints. Do not finalize if required slots remain missing unless the draft is
explicitly marked as assumption-bearing and the user confirms.

Policies:
Do not invent links or unseen facts. Require evidence for sourced claims. Limit questions
per turn. Prefer tool evidence over unnecessary user questioning. Deny finalization if
critical slots are missing or provenance fails.

Failure handling:
Missing timeframe, conflicting instructions, insufficient source access, evidence
shortage, user refusal to answer, and provenance failure.

Delegation policy:
Optional delegated subtasks such as source gathering or template matching may be
used if bounded and the returned evidence is normalized into approved evidence
carriers.
"""

# =============================================================================
# STAGE 1: SpanSlicer
# =============================================================================

STAGE1_SPAN_SLICER = {
    "stage_name": "SpanSlicer",
    "description": "Split raw text into semantic spans where each span represents a complete semantic unit",
    "input_data": {
        "raw_text": USAGE_EXAMPLE_RAW_TEXT,
    },
    "expected_output": {
        "spans": [
            {
                "span_id": "s1",
                "text": "Task family: Internal newsletters, announcements, update digests, executive briefs, and related internal-comms artifacts.",
            },
            {
                "span_id": "s2",
                "text": "Inputs for each run: A user request, optional known topics, optional timeframe, available connectors or source repositories, and optional format preferences.",
            },
            {
                "span_id": "s3",
                "text": "Required outputs: A draft communication artifact, a source/evidence set, a short assumptions log for any unresolved items, and a completion status.",
            },
            {
                "span_id": "s4",
                "text": "Reusable process: First determine what kind of communication is requested. Then identify which required fields are still missing. Ask only the highest-value clarifying questions needed to move forward. If sources are needed and available, retrieve them using approved source recipes. Maintain provenance for externally sourced facts. When enough required information is available, produce a draft. If the user asks for revision, revise while re checking constraints. Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms.",
            },
            {
                "span_id": "s5",
                "text": "Policies: Do not invent links or unseen facts. Require evidence for sourced claims. Limit questions per turn. Prefer tool evidence over unnecessary user questioning. Deny finalization if critical slots are missing or provenance fails.",
            },
            {
                "span_id": "s6",
                "text": "Failure handling: Missing timeframe, conflicting instructions, insufficient source access, evidence shortage, user refusal to answer, and provenance failure.",
            },
            {
                "span_id": "s7",
                "text": "Delegation policy: Optional delegated subtasks such as source gathering or template matching may be used if bounded and the returned evidence is normalized into approved evidence carriers.",
            },
        ]
    },
    "key_points": [
        "Each span_id follows format 's{N}' (e.g., s1, s2, s3)",
        "Each span text is a complete semantic unit from the original text",
        "All 7 sections from the example are captured as separate spans",
        "Span text preserves original wording and punctuation",
        "No span should be empty or contain only whitespace",
        "Total span count should match the number of semantic sections (7 in this case)",
    ],
}

# =============================================================================
# STAGE 2: FieldRouter
# =============================================================================

STAGE2_FIELD_ROUTER = {
    "stage_name": "FieldRouter",
    "description": "Route each span to one of 6 semantic fields: identity, audience, rules, domain, integrations, behavior",
    "input_data": {
        "spans": STAGE1_SPAN_SLICER["expected_output"]["spans"],
    },
    "expected_output": {
        "routes": {
            "identity": ["s1"],  # Task family defines identity
            "audience": ["s2"],  # Inputs define who/what the audience provides
            "rules": ["s5"],  # Policies are rules
            "domain": ["s3"],  # Required outputs define domain concepts
            "integrations": [],  # No explicit integrations mentioned
            "behavior": ["s4", "s6", "s7"],  # Process, failure handling, delegation are behaviors
        },
        "ambiguity_updates": [],  # No ambiguous spans in this example
    },
    "key_points": [
        "Each span ID appears in exactly one field (no overlap)",
        "Identity field contains span about task family (s1)",
        "Rules field contains policy spans (s5)",
        "Behavior field contains process and handling spans (s4, s6, s7)",
        "Domain field contains output specifications (s3)",
        "Ambiguity updates list is empty when no spans need splitting",
        "All 7 span IDs are accounted for across all fields",
    ],
}

# =============================================================================
# STAGE 3: AmbiguityResolver
# =============================================================================

STAGE3_AMBIGUITY_RESOLVER = {
    "stage_name": "AmbiguityResolver",
    "description": "Resolve ambiguous spans by splitting or reassigning them to appropriate fields",
    "input_data": {
        "spans": STAGE1_SPAN_SLICER["expected_output"]["spans"],
        "routes": STAGE2_FIELD_ROUTER["expected_output"]["routes"],
        "ambiguity_updates": STAGE2_FIELD_ROUTER["expected_output"]["ambiguity_updates"],
    },
    "expected_output": {
        "resolved_spans": [],  # No new spans created (no ambiguity in this example)
        "resolved_routes": {
            "identity": ["s1"],
            "audience": ["s2"],
            "rules": ["s5"],
            "domain": ["s3"],
            "integrations": [],
            "behavior": ["s4", "s6", "s7"],
        },
    },
    "key_points": [
        "Resolved spans list is empty when no splits are needed",
        "Routes remain unchanged if no ambiguity detected",
        "If spans were split, new span IDs would be generated (e.g., s4a, s4b)",
        "Ambiguity resolution preserves original span IDs when no split occurs",
        "All field assignments should be validated for consistency",
    ],
}

# =============================================================================
# STAGE 4: FlowAssembler
# =============================================================================

STAGE4_FLOW_ASSEMBLER = {
    "stage_name": "FlowAssembler",
    "description": "Determine flow structure including main flow, alternative flows, exception flows, and delegation candidates",
    "input_data": {
        "spans": STAGE1_SPAN_SLICER["expected_output"]["spans"],
        "routes": STAGE3_AMBIGUITY_RESOLVER["expected_output"]["resolved_routes"],
    },
    "expected_output": {
        "main_flow_spans": ["s4"],  # Reusable process is the main flow
        "alternative_flows": [],  # No alternative flows in this example
        "exception_flows": [
            {
                "flow_id": "exc_1",
                "condition_text": "Missing timeframe, conflicting instructions, insufficient source access, evidence shortage, user refusal to answer, or provenance failure",
                "spans": ["s6"],  # Failure handling is an exception flow
            }
        ],
        "delegation_candidates": [
            {
                "candidate_id": "dc_1",
                "spans": ["s7"],
                "reason": "Source gathering and template matching are optional delegated subtasks",
                "suggested_type": "child_worker",
                "input_variables": ["user_request", "known_topics"],
                "output_variables": ["gathered_evidence", "matched_template"],
            }
        ],
    },
    "key_points": [
        "Main flow contains the core reusable process (s4)",
        "Exception flows capture failure handling scenarios (s6)",
        "Delegation candidates identify optional subtasks (s7)",
        "Flow IDs follow format 'exc_{N}' for exception flows",
        "Delegation candidate IDs follow format 'dc_{N}'",
        "Each delegation candidate specifies input/output variables",
        "Alternative flows list is empty when no alternatives exist",
    ],
}

# =============================================================================
# STAGE 5: BlockAssembler
# =============================================================================

STAGE5_BLOCK_ASSEMBLER = {
    "stage_name": "BlockAssembler",
    "description": "Organize blocks within flows (SEQUENTIAL, IF, FOR, WHILE)",
    "input_data": {
        "spans": STAGE1_SPAN_SLICER["expected_output"]["spans"],
        "routes": STAGE3_AMBIGUITY_RESOLVER["expected_output"]["resolved_routes"],
        "flow_structure": STAGE4_FLOW_ASSEMBLER["expected_output"],
    },
    "expected_output": {
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
    },
    "key_points": [
        "Block IDs follow format 'b{N}'",
        "Main flow has one SEQUENTIAL block containing process spans",
        "Exception flow has its own SEQUENTIAL block",
        "Block type is SEQUENTIAL for linear execution",
        "Condition text is None for SEQUENTIAL blocks",
        "Each span appears in exactly one block",
        "Block structure mirrors the flow structure",
    ],
}

# =============================================================================
# STAGE 6: ResourceExtractor
# =============================================================================

STAGE6_RESOURCE_EXTRACTOR = {
    "stage_name": "ResourceExtractor",
    "description": "Extract variables, files, APIs, and types from the spans",
    "input_data": {
        "spans": STAGE1_SPAN_SLICER["expected_output"]["spans"],
        "routes": STAGE3_AMBIGUITY_RESOLVER["expected_output"]["resolved_routes"],
    },
    "expected_output": {
        "variables": [
            {
                "name": "user_request",
                "data_type": "text",
                "required": True,
                "description": "User request for the communication",
                "source": "input",
            },
            {
                "name": "known_topics",
                "data_type": "list",
                "required": False,
                "description": "Optional known topics for the communication",
                "source": "input",
            },
            {
                "name": "timeframe",
                "data_type": "text",
                "required": False,
                "description": "Optional timeframe for the communication",
                "source": "input",
            },
            {
                "name": "format_preferences",
                "data_type": "text",
                "required": False,
                "description": "Optional format preferences",
                "source": "input",
            },
            {
                "name": "draft_communication",
                "data_type": "text",
                "required": True,
                "description": "Draft communication artifact",
                "source": "output",
            },
            {
                "name": "source_evidence_set",
                "data_type": "list",
                "required": True,
                "description": "Source/evidence set for claims",
                "source": "output",
            },
            {
                "name": "assumptions_log",
                "data_type": "text",
                "required": True,
                "description": "Log of assumptions for unresolved items",
                "source": "output",
            },
            {
                "name": "completion_status",
                "data_type": "text",
                "required": True,
                "description": "Completion status indicator",
                "source": "output",
            },
            {
                "name": "communication_type",
                "data_type": "text",
                "required": True,
                "description": "Type of communication determined",
                "source": "step",
            },
            {
                "name": "missing_fields",
                "data_type": "list",
                "required": True,
                "description": "List of missing required fields",
                "source": "step",
            },
            {
                "name": "clarifying_questions",
                "data_type": "list",
                "required": True,
                "description": "High-value clarifying questions",
                "source": "step",
            },
            {
                "name": "gathered_sources",
                "data_type": "list",
                "required": True,
                "description": "Sources retrieved using approved recipes",
                "source": "step",
            },
            {
                "name": "provenance_records",
                "data_type": "list",
                "required": True,
                "description": "Provenance for externally sourced facts",
                "source": "step",
            },
        ],
        "files": [],
        "apis": [],
        "types": [],
    },
    "key_points": [
        "Variables are extracted from inputs (s2) and outputs (s3) sections",
        "Each variable has name, data_type, required, description, and source",
        "Source indicates origin: input, output, or step",
        "Required fields match the specification (user_request is required, known_topics is optional)",
        "Files, APIs, and types lists are empty when not explicitly mentioned",
        "Variable names use snake_case convention",
        "Data types are simple types (text, list, boolean)",
    ],
}

# =============================================================================
# STAGE 7: StepExtractor
# =============================================================================

STAGE7_STEP_EXTRACTOR = {
    "stage_name": "StepExtractor",
    "description": "Extract atomic actions (steps) with inputs/outputs from the spans",
    "input_data": {
        "spans": STAGE1_SPAN_SLICER["expected_output"]["spans"],
        "routes": STAGE3_AMBIGUITY_RESOLVER["expected_output"]["resolved_routes"],
        "flow_structure": STAGE4_FLOW_ASSEMBLER["expected_output"],
        "block_structure": STAGE5_BLOCK_ASSEMBLER["expected_output"],
        "symbol_table": {
            "variables": STAGE6_RESOURCE_EXTRACTOR["expected_output"]["variables"]
        },
    },
    "expected_output": {
        "steps": [
            {
                "step_id": "st1",
                "text": "Determine what kind of communication is requested",
                "source_span_ids": ["s4"],
                "command_type": "GENERAL_COMMAND",
                "inputs": ["user_request", "known_topics"],
                "outputs": ["communication_type"],
                "integration_ref": None,
                "flow_ref": "main",
                "block_ref": "b1",
                "kind": "normal",
            },
            {
                "step_id": "st2",
                "text": "Identify which required fields are still missing",
                "source_span_ids": ["s4"],
                "command_type": "GENERAL_COMMAND",
                "inputs": ["communication_type"],
                "outputs": ["missing_fields"],
                "integration_ref": None,
                "flow_ref": "main",
                "block_ref": "b1",
                "kind": "normal",
            },
            {
                "step_id": "st3",
                "text": "Ask highest-value clarifying questions needed to move forward",
                "source_span_ids": ["s4"],
                "command_type": "REQUEST_INPUT",
                "inputs": ["missing_fields"],
                "outputs": ["clarifying_questions"],
                "integration_ref": None,
                "flow_ref": "main",
                "block_ref": "b1",
                "kind": "user_input",
            },
            {
                "step_id": "st4",
                "text": "Retrieve sources using approved source recipes if needed",
                "source_span_ids": ["s4"],
                "command_type": "CALL_API",
                "inputs": ["user_request", "known_topics"],
                "outputs": ["gathered_sources"],
                "integration_ref": "source_recipes",
                "flow_ref": "main",
                "block_ref": "b1",
                "kind": "tool",
            },
            {
                "step_id": "st5",
                "text": "Maintain provenance for externally sourced facts",
                "source_span_ids": ["s4"],
                "command_type": "GENERAL_COMMAND",
                "inputs": ["gathered_sources"],
                "outputs": ["provenance_records"],
                "integration_ref": None,
                "flow_ref": "main",
                "block_ref": "b1",
                "kind": "normal",
            },
            {
                "step_id": "st6",
                "text": "Produce draft when enough required information is available",
                "source_span_ids": ["s4"],
                "command_type": "GENERAL_COMMAND",
                "inputs": ["communication_type", "gathered_sources", "provenance_records"],
                "outputs": ["draft_communication"],
                "integration_ref": None,
                "flow_ref": "main",
                "block_ref": "b1",
                "kind": "normal",
            },
            {
                "step_id": "st7",
                "text": "Revise while re-checking constraints if user asks for revision",
                "source_span_ids": ["s4"],
                "command_type": "GENERAL_COMMAND",
                "inputs": ["draft_communication"],
                "outputs": ["draft_communication"],
                "integration_ref": None,
                "flow_ref": "main",
                "block_ref": "b1",
                "kind": "normal",
            },
            {
                "step_id": "st8",
                "text": "Generate source/evidence set and assumptions log",
                "source_span_ids": ["s3", "s4"],
                "command_type": "GENERAL_COMMAND",
                "inputs": ["draft_communication", "provenance_records"],
                "outputs": ["source_evidence_set", "assumptions_log"],
                "integration_ref": None,
                "flow_ref": "main",
                "block_ref": "b1",
                "kind": "normal",
            },
            {
                "step_id": "st9",
                "text": "Set completion status",
                "source_span_ids": ["s3", "s4"],
                "command_type": "DISPLAY_MESSAGE",
                "inputs": ["draft_communication", "source_evidence_set", "assumptions_log"],
                "outputs": ["completion_status"],
                "integration_ref": None,
                "flow_ref": "main",
                "block_ref": "b1",
                "kind": "display",
            },
        ],
        "new_variables": [],
    },
    "key_points": [
        "Step IDs follow format 'st{N}'",
        "Each step has command_type: GENERAL_COMMAND, CALL_API, REQUEST_INPUT, or DISPLAY_MESSAGE",
        "Steps reference source spans from the original text (s4 for process steps)",
        "Input/output variables must exist in the symbol table",
        "Flow reference is 'main' for main flow steps",
        "Block reference matches the block structure (b1)",
        "Kind indicates semantic type: normal, tool, user_input, display",
        "Steps cover all actions mentioned in the reusable process (s4)",
    ],
}

# =============================================================================
# STAGE 8: ProfileExtractor
# =============================================================================

STAGE8_PROFILE_EXTRACTOR = {
    "stage_name": "ProfileExtractor",
    "description": "Extract persona, audience, and domain concepts from the spans",
    "input_data": {
        "spans": STAGE1_SPAN_SLICER["expected_output"]["spans"],
        "routes": STAGE3_AMBIGUITY_RESOLVER["expected_output"]["resolved_routes"],
        "symbol_table": {
            "variables": STAGE6_RESOURCE_EXTRACTOR["expected_output"]["variables"]
        },
    },
    "expected_output": {
        "persona": {
            "role": "Internal Communications Specialist",
            "aspects": [
                {
                    "name": "ProfessionalCommunication",
                    "text": "Specializes in internal newsletters, announcements, and executive briefs",
                },
                {
                    "name": "EvidenceBased",
                    "text": "Requires evidence for all sourced claims and maintains provenance",
                },
                {
                    "name": "ClarificationSeeker",
                    "text": "Asks high-value clarifying questions when information is missing",
                },
            ],
        },
        "audience_aspects": [
            {
                "name": "InternalTeams",
                "text": "Company employees receiving internal communications",
            },
            {
                "name": "Executives",
                "text": "Executive leadership receiving briefs and digests",
            },
        ],
        "concepts": [
            {
                "term": "Internal Newsletter",
                "definition": "Regular communication artifact for internal company updates",
            },
            {
                "term": "Evidence Set",
                "definition": "Collection of sources and provenance records supporting claims",
            },
            {
                "term": "Assumptions Log",
                "definition": "Documentation of unresolved items and working assumptions",
            },
            {
                "term": "Source Recipes",
                "definition": "Approved methods for retrieving external information",
            },
            {
                "term": "Provenance",
                "definition": "Tracking of origin and chain of custody for sourced facts",
            },
        ],
    },
    "key_points": [
        "Persona role reflects the task family (Internal Communications Specialist)",
        "Persona aspects capture key behavioral traits from the text",
        "Audience aspects identify who receives the communications",
        "Domain concepts are extracted from terminology in the text",
        "Each concept has a term and definition",
        "Profile is derived from identity (s1) and domain (s3) spans",
    ],
}

# =============================================================================
# STAGE 9: ConstraintExtractor
# =============================================================================

STAGE9_CONSTRAINT_EXTRACTOR = {
    "stage_name": "ConstraintExtractor",
    "description": "Extract constraints including prohibitions, requirements, gates, evidence rules, and safety constraints",
    "input_data": {
        "spans": STAGE1_SPAN_SLICER["expected_output"]["spans"],
        "routes": STAGE3_AMBIGUITY_RESOLVER["expected_output"]["resolved_routes"],
        "flow_structure": STAGE4_FLOW_ASSEMBLER["expected_output"],
        "block_structure": STAGE5_BLOCK_ASSEMBLER["expected_output"],
        "symbol_table": {
            "variables": STAGE6_RESOURCE_EXTRACTOR["expected_output"]["variables"]
        },
        "steps": STAGE7_STEP_EXTRACTOR["expected_output"]["steps"],
    },
    "expected_output": {
        "constraints": [
            {
                "constraint_id": "c1",
                "text": "Do not invent links or unseen facts",
                "kind": "prohibition",
                "targets": ["global"],
                "source_span_ids": ["s5"],
            },
            {
                "constraint_id": "c2",
                "text": "Require evidence for sourced claims",
                "kind": "evidence",
                "targets": ["global"],
                "source_span_ids": ["s5"],
            },
            {
                "constraint_id": "c3",
                "text": "Limit questions per turn",
                "kind": "requirement",
                "targets": ["step:st3"],
                "source_span_ids": ["s5"],
            },
            {
                "constraint_id": "c4",
                "text": "Prefer tool evidence over unnecessary user questioning",
                "kind": "requirement",
                "targets": ["global"],
                "source_span_ids": ["s5"],
            },
            {
                "constraint_id": "c5",
                "text": "Deny finalization if critical slots are missing or provenance fails",
                "kind": "gate",
                "targets": ["step:st9"],
                "source_span_ids": ["s5"],
            },
            {
                "constraint_id": "c6",
                "text": "Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms",
                "kind": "gate",
                "targets": ["step:st9"],
                "source_span_ids": ["s4"],
            },
            {
                "constraint_id": "c7",
                "text": "Delegated subtasks must be bounded and evidence normalized into approved carriers",
                "kind": "delegation_boundary",
                "targets": ["global"],
                "source_span_ids": ["s7"],
            },
        ]
    },
    "key_points": [
        "Constraint IDs follow format 'c{N}'",
        "Constraint kinds include: prohibition, evidence, requirement, gate, delegation_boundary",
        "Targets reference steps (step:st3) or are global",
        "Prohibitions prevent specific actions (c1: no inventing facts)",
        "Evidence constraints require sourcing (c2)",
        "Gates block finalization until conditions met (c5, c6)",
        "Constraints are extracted from policies (s5) and process (s4) spans",
    ],
}

# =============================================================================
# STAGE 9.5: IRNormalizer
# =============================================================================

STAGE9_5_IR_NORMALIZER = {
    "stage_name": "IRNormalizer",
    "description": "Normalize and validate all IRs for consistency across steps, constraints, and resources",
    "input_data": {
        "flow_structure": STAGE4_FLOW_ASSEMBLER["expected_output"],
        "block_structure": STAGE5_BLOCK_ASSEMBLER["expected_output"],
        "resources": STAGE6_RESOURCE_EXTRACTOR["expected_output"],
        "symbol_table": {
            "variables": STAGE6_RESOURCE_EXTRACTOR["expected_output"]["variables"]
        },
        "steps": STAGE7_STEP_EXTRACTOR["expected_output"]["steps"],
        "constraints": STAGE9_CONSTRAINT_EXTRACTOR["expected_output"]["constraints"],
    },
    "expected_output": {
        "normalized_flow": STAGE4_FLOW_ASSEMBLER["expected_output"],
        "normalized_blocks": STAGE5_BLOCK_ASSEMBLER["expected_output"],
        "normalized_steps": STAGE7_STEP_EXTRACTOR["expected_output"]["steps"],
        "normalized_constraints": STAGE9_CONSTRAINT_EXTRACTOR["expected_output"]["constraints"],
        "symbol_table": {
            "variables": STAGE6_RESOURCE_EXTRACTOR["expected_output"]["variables"]
        },
        "errors": [],
        "warnings": [],
    },
    "key_points": [
        "Validates all step variable references exist in symbol table",
        "Validates constraint targets reference valid steps/variables",
        "Checks all flow spans are covered by steps",
        "Reconciles step flow_ref and block_ref fields",
        "Reconciles constraint targets to use 'global' if empty",
        "Returns empty errors list when all references are valid",
        "Returns warnings for uncovered spans or missing references",
    ],
}

# =============================================================================
# STAGE 10: WorkerAssembler
# =============================================================================

STAGE10_WORKER_ASSEMBLER = {
    "stage_name": "WorkerAssembler",
    "description": "Assemble worker structure from flow, blocks, steps, and resources",
    "input_data": {
        "flow_structure": STAGE4_FLOW_ASSEMBLER["expected_output"],
        "block_structure": STAGE5_BLOCK_ASSEMBLER["expected_output"],
        "steps": STAGE7_STEP_EXTRACTOR["expected_output"]["steps"],
        "resources": STAGE6_RESOURCE_EXTRACTOR["expected_output"],
        "symbol_table": {
            "variables": STAGE6_RESOURCE_EXTRACTOR["expected_output"]["variables"]
        },
    },
    "expected_output": {
        "worker": {
            "worker_name": "Draft internal communication",
            "description": "Generate internal newsletters, announcements, and related communications with proper sourcing",
            "inputs": [
                {"name": "user_request", "required": True},
                {"name": "known_topics", "required": False},
                {"name": "timeframe", "required": False},
                {"name": "format_preferences", "required": False},
            ],
            "outputs": [
                {"name": "draft_communication", "required": True},
                {"name": "source_evidence_set", "required": True},
                {"name": "assumptions_log", "required": True},
                {"name": "completion_status", "required": True},
            ],
            "main_flow": {
                "blocks": [
                    {
                        "block_id": "b1",
                        "block_type": "SEQUENTIAL",
                        "condition_text": None,
                        "spans": ["s4"],
                    }
                ]
            },
            "alternative_flows": [],
            "exception_flows": [
                {
                    "flow_id": "exc_1",
                    "condition_text": "Missing timeframe, conflicting instructions, insufficient source access, evidence shortage, user refusal to answer, or provenance failure",
                    "blocks": [
                        {
                            "block_id": "b2",
                            "block_type": "SEQUENTIAL",
                            "condition_text": None,
                            "spans": ["s6"],
                        }
                    ],
                }
            ],
            "api_refs": [],
            "child_worker_refs": [],
        }
    },
    "key_points": [
        "Worker name reflects the task (Draft internal communication)",
        "Inputs match required/optional variables from symbol table",
        "Outputs match required outputs from specification",
        "Main flow contains sequential blocks from flow structure",
        "Exception flows capture failure handling",
        "API refs list APIs used (empty if none)",
        "Child worker refs list delegated workers (empty if none)",
    ],
}

# =============================================================================
# STAGE 11: SPLRenderer
# =============================================================================

STAGE11_SPL_RENDERER = {
    "stage_name": "SPLRenderer",
    "description": "Render final SPL (Structured Prompt Language) text from worker, profile, resources, steps, and constraints",
    "input_data": {
        "worker": STAGE10_WORKER_ASSEMBLER["expected_output"]["worker"],
        "profile": STAGE8_PROFILE_EXTRACTOR["expected_output"],
        "resources": STAGE6_RESOURCE_EXTRACTOR["expected_output"],
        "symbol_table": {
            "variables": STAGE6_RESOURCE_EXTRACTOR["expected_output"]["variables"]
        },
        "steps": STAGE7_STEP_EXTRACTOR["expected_output"]["steps"],
        "constraints": STAGE9_CONSTRAINT_EXTRACTOR["expected_output"]["constraints"],
    },
    "expected_output": {
        "spl_text": """[DEFINE_AGENT: InternalCommsAgent "Internal communications specialist for newsletters and announcements"]

[DEFINE_PERSONA:]
ROLE: Internal Communications Specialist
ASPECT: ProfessionalCommunication - Specializes in internal newsletters, announcements, and executive briefs
ASPECT: EvidenceBased - Requires evidence for all sourced claims and maintains provenance
ASPECT: ClarificationSeeker - Asks high-value clarifying questions when information is missing
[END_PERSONA]

[DEFINE_AUDIENCE:]
TARGET: InternalTeams - Company employees receiving internal communications
TARGET: Executives - Executive leadership receiving briefs and digests
[END_AUDIENCE]

[DEFINE_VARIABLES:]
"User request" user_request: text REQUIRED
"Known topics" known_topics: list OPTIONAL
"Timeframe" timeframe: text OPTIONAL
"Format preferences" format_preferences: text OPTIONAL
"Draft communication" draft_communication: text REQUIRED
"Source evidence set" source_evidence_set: list REQUIRED
"Assumptions log" assumptions_log: text REQUIRED
"Completion status" completion_status: text REQUIRED
"Communication type" communication_type: text
"Missing fields" missing_fields: list
"Clarifying questions" clarifying_questions: list
"Gathered sources" gathered_sources: list
"Provenance records" provenance_records: list
[END_VARIABLES]

[DEFINE_CONSTRAINTS:]
[PROHIBITION]
Do not invent links or unseen facts
TARGETS: global
[END_PROHIBITION]

[EVIDENCE]
Require evidence for sourced claims
TARGETS: global
[END_EVIDENCE]

[REQUIREMENT]
Limit questions per turn
TARGETS: step:st3
[END_REQUIREMENT]

[REQUIREMENT]
Prefer tool evidence over unnecessary user questioning
TARGETS: global
[END_REQUIREMENT]

[GATE]
Deny finalization if critical slots are missing or provenance fails
TARGETS: step:st9
[END_GATE]

[GATE]
Do not finalize if required slots remain missing unless the draft is explicitly marked as assumption-bearing and the user confirms
TARGETS: step:st9
[END_GATE]

[DELEGATION_BOUNDARY]
Delegated subtasks must be bounded and evidence normalized into approved carriers
TARGETS: global
[END_DELEGATION_BOUNDARY]
[END_CONSTRAINTS]

[DEFINE_WORKER: "Draft internal communication" InternalCommsAgent]
[INPUTS]
REQUIRED <REF>user_request</REF>
OPTIONAL <REF>known_topics</REF>
OPTIONAL <REF>timeframe</REF>
OPTIONAL <REF>format_preferences</REF>
[END_INPUTS]

[OUTPUTS]
REQUIRED <REF>draft_communication</REF>
REQUIRED <REF>source_evidence_set</REF>
REQUIRED <REF>assumptions_log</REF>
REQUIRED <REF>completion_status</REF>
[END_OUTPUTS]

[MAIN_FLOW]
[SEQUENTIAL]
COMMAND: Determine what kind of communication is requested
COMMAND: Identify which required fields are still missing
COMMAND: Ask highest-value clarifying questions needed to move forward
COMMAND: Retrieve sources using approved source recipes if needed
COMMAND: Maintain provenance for externally sourced facts
COMMAND: Produce draft when enough required information is available
COMMAND: Revise while re-checking constraints if user asks for revision
COMMAND: Generate source/evidence set and assumptions log
COMMAND: Set completion status
[END_SEQUENTIAL]
[END_MAIN_FLOW]

[EXCEPTION_FLOW: Missing timeframe or evidence shortage]
[SEQUENTIAL]
COMMAND: Handle failure: report missing information or evidence shortage
[END_SEQUENTIAL]
[END_EXCEPTION_FLOW]

[END_WORKER]
[END_AGENT]
""",
        "validation_errors": [],
        "validation_warnings": [],
    },
    "key_points": [
        "SPL text follows proper SPL syntax with [TAG] and [END_TAG] markers",
        "Agent definition includes name and description",
        "Persona section includes ROLE and ASPECT entries",
        "Audience section lists TARGET entries",
        "Variables section uses proper format with quotes, name, type, and REQUIRED/OPTIONAL",
        "Constraints include PROHIBITION, EVIDENCE, REQUIREMENT, GATE, and DELEGATION_BOUNDARY",
        "Worker section includes INPUTS, OUTPUTS, MAIN_FLOW, and EXCEPTION_FLOW",
        "Variable references use <REF>name</REF> format",
        "Validation errors list is empty when SPL is valid",
        "Validation warnings list is empty when no issues detected",
    ],
}

# =============================================================================
# COMPLETE TEST CASE SUMMARY
# =============================================================================

ALL_STAGES = {
    "stage1_span_slicer": STAGE1_SPAN_SLICER,
    "stage2_field_router": STAGE2_FIELD_ROUTER,
    "stage3_ambiguity_resolver": STAGE3_AMBIGUITY_RESOLVER,
    "stage4_flow_assembler": STAGE4_FLOW_ASSEMBLER,
    "stage5_block_assembler": STAGE5_BLOCK_ASSEMBLER,
    "stage6_resource_extractor": STAGE6_RESOURCE_EXTRACTOR,
    "stage7_step_extractor": STAGE7_STEP_EXTRACTOR,
    "stage8_profile_extractor": STAGE8_PROFILE_EXTRACTOR,
    "stage9_constraint_extractor": STAGE9_CONSTRAINT_EXTRACTOR,
    "stage9_5_ir_normalizer": STAGE9_5_IR_NORMALIZER,
    "stage10_worker_assembler": STAGE10_WORKER_ASSEMBLER,
    "stage11_spl_renderer": STAGE11_SPL_RENDERER,
}

STAGE_COUNT = len(ALL_STAGES)
