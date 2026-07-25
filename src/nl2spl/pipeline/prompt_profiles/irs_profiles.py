"""Stage-local IRS prompt profile policy."""

# Mapping from stage name to construct types whose IRS should appear in prompts.
STAGE_CONSTRUCT_MAP: dict[str, list[str]] = {
    "stage4": ["EXCEPTION_FLOW"],
    "stage7": [
        "GENERAL_COMMAND",
        "REQUEST_INPUT",
        "CALL_API",
        "INVOKE_WORKER",
    ],
    "stage9_5": [
        "REQUIRED_OUTPUT",
        "CHILD_WORKER",
        "WORKER_CANDIDATE",
    ],
}

# Extra prose that supplements the generated checklist for specific stages.
STAGE_NOTES: dict[str, str] = {
    "stage3_5": (
        "### Critical Rules\n"
        "- Only ACCEPT when ALL of: source-backed responsibility, "
        "input contract, output contract, invocation point, "
        "result handoff, independent callable value.\n"
        "- The following are NEVER workers: 'determine the type', "
        "'identify missing fields', 'generate clarifying questions', "
        "'retrieve sources' (without delegation), 'maintain "
        "provenance', 'produce a draft', 'finalize the result'.\n"
    ),
    "stage3_5a": (
        "### Critical Rules\n"
        "- Identify candidates broadly; mark risks honestly.\n"
        "- Only list contract fields when EXPLICITLY named in source; "
        "leave empty otherwise.\n"
    ),
    "stage3_5b": (
        "### Critical Rules\n"
        "- If a candidate's possible_outputs are empty but the "
        "candidate has explicit_delegation or bounded_io, check "
        "adapter hard facts for the output contract.\n"
    ),
    "stage4": (
        "### Critical Rules\n"
        "- No failure signal → do NOT generate EXCEPTION_FLOW.\n"
        "- Concrete failure condition → output partial EXCEPTION_FLOW with "
        "condition_text and spans only.\n"
        "- Do NOT invent handler actions. missing_handler is diagnosed "
        "later by Stage 9.5.\n"
        "- Keep handler-related spans in the flow; Stage 7 will decide "
        "whether they become handler steps.\n"
        '- Vague "handle failures properly" → type_or_contract_ambiguity, '
        "no concrete flow.\n"
    ),
    "stage7": (
        "### Critical Rules\n"
        "- GENERAL_COMMAND requires source evidence.\n"
        "- REQUEST_INPUT requires explicit ask/request/prompt/confirm source.\n"
        "- CALL_API requires named API/tool/connector plus executable call action.\n"
        "- INVOKE_WORKER requires an accepted handoff.\n"
        "- If an action is only a suggested fix, emit assumption / report data, "
        "NOT an executable StepIR.\n"
    ),
}


