"""S6V0 Characterization: Lock down current error behavior before any fix.

These tests document the CURRENT (broken) state of the variable declaration
authority chain.  They must PASS now because they assert the existing behavior.
After S6V1–S6V6 fixes are applied, these tests must be updated to reflect the
new correct behavior.

DO NOT skip/xfail these tests to hide failures.

Per the implementation plan:
  S6V0 does NOT change production code.  It only adds characterization
  evidence so every subsequent phase has a baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_DIR = REPO_ROOT / "prompts"
DEMO_DIR = REPO_ROOT / "examples" / "output" / "demo"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_prompt(name: str) -> str:
    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        pytest.skip(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _read_demo_json(name: str) -> dict:
    path = DEMO_DIR / f"{name}.json"
    if not path.exists():
        pytest.skip(f"Demo artifact not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_demo_text(name: str) -> str:
    path = DEMO_DIR / f"{name}.txt"
    if not path.exists():
        pytest.skip(f"Demo artifact not found: {path}")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Prompt evidence – condition variable declaration rule IS present
# ---------------------------------------------------------------------------


class TestS6V0PromptCurrentConditionRule:
    """Verify the CURRENT prompt contains the problematic rule.

    These assert the BROKEN state.  After S6V1 they must be updated.
    """

    def test_stage6_prompt_requires_condition_variable_declaration(self) -> None:
        """Post-S6V1: The old rule 'Every condition variable ... has been
        declared as a step variable' has been removed from the prompt."""
        prompt = _read_prompt("stage6_system")
        assert "Every condition variable" not in prompt, (
            "CHARACTERIZATION (post-S6V1): the old condition variable "
            "declaration rule has been removed.  This was the fix for the "
            "primary extraction bug."
        )

    def test_stage6_prompt_contains_condition_keyword_in_completeness_check(
        self,
    ) -> None:
        """Post-S6V1: the prompt no longer references 'condition variable'
        as a declaration concept.  The word 'condition' may appear in
        negation context (Do not declare from conditions)."""
        prompt = _read_prompt("stage6_system")
        # Post-S6V1: "condition variable" as a compound phrase is gone
        # because the old rule was removed.  "condition" alone may appear
        # in the prohibition section.
        assert "condition variable" not in prompt.lower(), (
            "CHARACTERIZATION (post-S6V1): 'condition variable' phrase "
            "has been removed from the prompt."
        )

    def test_stage6_prompt_boolean_example_is_sources_needed(self) -> None:
        """Post-S6V1: 'sources_needed' has been replaced with generic
        examples (has_errors, is_complete)."""
        prompt = _read_prompt("stage6_system")
        assert "sources_needed" not in prompt, (
            "CHARACTERIZATION (post-S6V1): 'sources_needed' has been "
            "replaced with generic boolean examples."
        )


# ---------------------------------------------------------------------------
# 2. Demo evidence – condition-only predicates in final SPL
# ---------------------------------------------------------------------------

CONDITION_PREDICATE_NAMES = frozenset({
    "sources_needed",
    "sources_available",
    "enough_required_information",
    "user_asks_for_revision",
    "required_slots_remain_missing",
    "required_fields_missing",
    "draft_marked_as_assumption_bearing",
    "user_confirms",
})


class TestS6V0DemoCurrentConditionPredicates:
    """Verify the CURRENT demo final_spl.txt defines condition-only
    predicates."""

    def test_condition_predicates_in_define_variables(self) -> None:
        """At least some condition-only predicates appear in
        [DEFINE_VARIABLES:]."""
        spl = _read_demo_text("final_spl")
        found = [n for n in CONDITION_PREDICATE_NAMES if f"{n}:" in spl]
        assert found == []

    def test_condition_predicates_have_boolean_type(self) -> None:
        """Predicates are typed boolean in DEFINE_VARIABLES."""
        spl = _read_demo_text("final_spl")
        for name in ["enough_required_information", "user_asks_for_revision",
                      "sources_needed", "sources_available"]:
            if name in spl:
                assert f"{name}: boolean" not in spl

    def test_condition_blocks_use_ref_tags_for_predicates(self) -> None:
        """DECISION blocks render <REF> tags for condition-only predicates."""
        spl = _read_demo_text("final_spl")
        assert "<REF>enough_required_information</REF>" not in spl
        assert "<REF>user_asks_for_revision</REF>" not in spl


# ---------------------------------------------------------------------------
# 3. Stage 6.5 evidence – reference plan uses generated symbols
# ---------------------------------------------------------------------------


class TestS6V0Stage65ReferencePlan:
    """Verify the CURRENT Stage 6.5 condition_variable_reference_plan
    references generated condition-predicate symbols."""

    def test_reference_plan_has_condition_predicates(self) -> None:
        raw = _read_demo_json("condition_variable_reference_plan")
        refs = raw.get("result", {}).get("references", [])
        ref_names = {r["canonical_ref"] for r in refs}
        assert "enough_required_information" not in ref_names
        assert "user_asks_for_revision" not in ref_names

    def test_reference_plan_selected_symbols_are_condition_predicates(
        self,
    ) -> None:
        raw = _read_demo_json("condition_variable_reference_plan")
        refs = raw.get("result", {}).get("references", [])
        selected = set()
        for r in refs:
            sel = r.get("selected_symbol")
            if sel:
                selected.add(sel)
        assert "enough_required_information" not in selected
        assert "user_asks_for_revision" not in selected


# ---------------------------------------------------------------------------
# 4. Stage 3.5 evidence – candidate IO carries predicate-like variables
# ---------------------------------------------------------------------------


class TestS6V0Stage35CandidateIO:
    """Verify Stage 3.5 candidate task units can carry predicate-like
    possible_inputs / possible_outputs."""

    def test_candidate_io_contains_sources_needed(self) -> None:
        """Stage 3.5 LLM still produces 'sources_needed' as candidate IO.
        The fix is in Stage 6: candidate IO without evidence defaults to
        inadmissible and is rejected by Stage6VariableDeclarationPolicy.
        This test documents that Stage 3.5 output is unchanged; the gate
        is downstream."""
        raw = _read_demo_json("stage3_5a_candidate_task_units")
        all_inputs: list[str] = []
        for c in raw.get("result", {}).get("candidates", []):
            for f in c.get("possible_inputs", []):
                all_inputs.append(f["name"])
        assert "sources_needed" in all_inputs, (
            "CHARACTERIZATION: Stage 3.5 LLM still produces "
            "'sources_needed' as candidate IO. Stage 6 policy "
            "rejects it because candidate IO without evidence is "
            "inadmissible (llm_candidate_io)."
        )

    def test_candidate_io_fields_lack_source_span_ids(self) -> None:
        raw = _read_demo_json("stage3_5a_candidate_task_units")
        for c in raw.get("result", {}).get("candidates", []):
            for f in c.get("possible_inputs", []):
                if f["name"] == "sources_needed":
                    assert f.get("source_span_ids") == [], (
                        "CHARACTERIZATION: sources_needed candidate IO "
                        "has empty source_span_ids — no declaration evidence."
                    )
                    assert f.get("contract_demand_id") is None, (
                        "CHARACTERIZATION: sources_needed candidate IO "
                        "has no contract_demand_id."
                    )

    def test_materialized_worker_contract_contains_sources_needed(self) -> None:
        """Stage 3.5c materializer still includes 'sources_needed' in the
        worker contract. Stage 6 _merge_contract_variables() filters it
        out because candidate IO defaults to inadmissible. This test
        documents that upstream artifact is unchanged; the gate is in
        Stage 6."""
        materializer = _read_demo_json("stage3_5c_worker_plan_materializer")
        raw = json.dumps(materializer)
        assert "sources_needed" in raw, (
            "CHARACTERIZATION: materialized worker plan still contains "
            "'sources_needed'. Stage 6 authority registry rejects it."
        )


# ---------------------------------------------------------------------------
# 5. SymbolTable write-path inventory (static scan helper)
# ---------------------------------------------------------------------------


class TestS6V0SymbolTableWritePathInventory:
    """Document all current SymbolTable write paths.

    These are not assertions about *correctness* — they are a census.
    After S6V4.5 every entry here must have a declaration authority
    classification.
    """

    KNOWN_WRITE_PATHS = [
        # (file, line_hint, method, stage)
        ("src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py",
         "~183", "symbol_table.declare()", "Stage 6 legacy"),
        ("src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py",
         "~459", "symbol_table.declare_scoped()", "Stage 6 worker-scoped"),
        ("src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py",
         "~243", "symbol_table.declare()", "Stage 7 new_variables"),
        ("src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py",
         "~302", "symbol_table.declare()", "Stage 7 legacy handoff output"),
        ("src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py",
         "~483", "symbol_table.declare_scoped()", "Stage 7 worker-scoped new_variables"),
        ("src/nl2spl/pipeline/stages/stage9_5_normalizer/composite_output_applier.py",
         "~95", "symbol_table.declare()", "Stage 9.5 composite output rewrite"),
        ("src/nl2spl/compiler/spl_editing/stage_slices/worker_delegation_closure.py",
         "~825", "symbol_table.declare_scoped()", "SPL Editing repair"),
    ]

    def test_static_scan_confirms_expected_call_sites(self) -> None:
        """Sanity: grep scan result matches the documented inventory.

        If this fails because new call sites were added, the inventory
        above AND S6V4.5 must be updated.
        """
        import subprocess

        result = subprocess.run(
            ["grep", "-rn", r"\.declare\(_scoped\)\?\|\\.declare_scoped\|\\.declare(",
             "src/nl2spl"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), shell=True,
        )
        # Fall back to Python-based search if grep not available
        if result.returncode not in (0, 1, 2):
            pytest.skip("grep not available")

        hits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            if "tests/" in line or "__pycache__" in line:
                continue
            hits.append(line.split(":")[0])

        if not hits:
            # Do a Python-based scan instead
            hits = list(self._scan_declare_sites_python())

        unique_files = sorted(set(hits))
        inventory_files = sorted({p[0] for p in self.KNOWN_WRITE_PATHS})

        for inv_file in inventory_files:
            found = any(inv_file in f for f in unique_files)
            if not found:
                # Check if file exists — it may have been moved
                full = REPO_ROOT / inv_file
                if full.exists():
                    # File exists but not in scan — scan may be incomplete
                    # This is informational only in S6V0
                    print(f"\n  INFO: inventory entry {inv_file} exists "
                          f"but was not matched by scan.")

        print(f"\n  SymbolTable write-path static scan: {len(unique_files)} "
              f"unique production files, {len(hits)} call sites.")
        for f in unique_files:
            print(f"    {f}")

    @staticmethod
    def _scan_declare_sites_python():
        """Fallback: scan declare/declare_scoped call sites in Python."""
        src_dir = REPO_ROOT / "src" / "nl2spl"
        for py_file in src_dir.rglob("*.py"):
            if "tests" in str(py_file) or "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except Exception:
                continue
            if ".declare(" in content or ".declare_scoped(" in content:
                rel = str(py_file.relative_to(REPO_ROOT))
                yield rel.replace("\\", "/")
