"""SymbolTable write-path authority audit (S6V4.5).

Static inventory of every ``symbol_table.declare()`` /
``symbol_table.declare_scoped()`` call site in production code.

Each entry must have:
- call_site: file path + approximate line
- stage: pipeline stage
- owner: responsible stage / module
- authority_category: declaration authority classification
- guard: what deterministic check prevents unauthorized writes
- tests: test coverage reference
- waiver: if present, owner + reason + removal condition
"""

from __future__ import annotations

from dataclasses import dataclass

AuthorityCategory = str

CATEGORY_LABELS: dict[str, str] = {
    "stage6_llm_variable": "Stage 6 LLM-extracted variable; must pass policy",
    "stage6_worker_contract_merge": (
        "Stage 6 contract merge; must pass authority sidecar"
    ),
    "stage7_handoff_output_binding": "Stage 7 handoff output binding",
    "stage9_5_composite_output_rewrite": (
        "Stage 9.5 composite output rewrite; derived from admitted output"
    ),
    "spl_editing_repair": "SPL Editing repair; user_confirmed_repair",
    "legacy_compat_waiver": (
        "Legacy path; waived with owner/reason/removal condition"
    ),
}


@dataclass
class WritePathEntry:
    """A single SymbolTable write path entry."""

    call_site: str
    stage: str
    owner: str
    authority_category: str
    accepted_inputs: str
    guard_function_or_metadata: str
    tests: str
    waiver_if_any: str = ""


WRITE_PATH_INVENTORY: list[WritePathEntry] = [
    WritePathEntry(
        call_site="src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py ~254",
        stage="Stage 6",
        owner="ResourceExtractor (legacy)",
        authority_category="stage6_llm_variable",
        accepted_inputs="Variables passing Stage6VariableDeclarationPolicy",
        guard_function_or_metadata="Stage6VariableDeclarationPolicy.evaluate()",
        tests=(
            "tests/unit/test_stage6_prompt.py, "
            "tests/unit/pipeline/stage6/test_variable_declaration_policy.py"
        ),
    ),
    WritePathEntry(
        call_site=(
            "src/nl2spl/pipeline/stages/stage6_resource_extractor/"
            "worker_scoped.py ~492"
        ),
        stage="Stage 6",
        owner="ResourceExtractor (worker-scoped)",
        authority_category="stage6_llm_variable",
        accepted_inputs="Variables passing Stage6VariableDeclarationPolicy",
        guard_function_or_metadata="Stage6VariableDeclarationPolicy.evaluate()",
        tests=(
            "tests/unit/pipeline/stages/test_stage6_worker_scoped.py, "
            "tests/unit/pipeline/stage6/test_variable_declaration_policy.py"
        ),
    ),
    WritePathEntry(
        call_site="src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py ~302",
        stage="Stage 7",
        owner="StepExtractor (legacy handoff)",
        authority_category="stage7_handoff_output_binding",
        accepted_inputs="Handoff output binding parent_variable",
        guard_function_or_metadata=(
            "worker_handoff_binding authority; only created when handoff binding exists"
        ),
        tests="tests/unit/pipeline/stage7/",
    ),
    WritePathEntry(
        call_site=(
            "src/nl2spl/pipeline/stages/stage9_5_normalizer/"
            "composite_output_applier.py ~95"
        ),
        stage="Stage 9.5",
        owner="IRNormalizer (composite output)",
        authority_category="stage9_5_composite_output_rewrite",
        accepted_inputs="Composite output variable replacing original outputs",
        guard_function_or_metadata=(
            "Derived from admitted output via CompositeOutputPlan. Replaces "
            "existing admitted outputs with structured type."
        ),
        tests="tests/unit/pipeline/stage9_5/",
    ),
    WritePathEntry(
        call_site=(
            "src/nl2spl/compiler/spl_editing/stage_slices/"
            "worker_delegation_closure.py ~825"
        ),
        stage="SPL Editing",
        owner="SPL Editing (worker delegation closure)",
        authority_category="spl_editing_repair",
        accepted_inputs="Repair directive with user_confirmed_repair authority",
        guard_function_or_metadata=(
            "User-confirmed repair: source='user_confirmed_repair', validated "
            "by StageSlice validation."
        ),
        tests="tests/unit/compiler/spl_editing/",
    ),
]


def get_inventory() -> list[WritePathEntry]:
    """Return the current write-path inventory."""
    return list(WRITE_PATH_INVENTORY)


def get_unclassified_paths() -> list[WritePathEntry]:
    """Return entries that still need classification."""
    return [entry for entry in WRITE_PATH_INVENTORY if not entry.authority_category]


def get_waivered_paths() -> list[WritePathEntry]:
    """Return entries with active waivers."""
    return [entry for entry in WRITE_PATH_INVENTORY if entry.waiver_if_any]
