# v5 IRS Phase E Live LLM Acceptance Report

Date: 2026-05-17
Status: **PASS**

## Test Command

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python examples/usage.py
```

## Flags Enabled

```python
enable_worker_boundary_planner=True,
enable_worker_boundary_planner_split=True,
enable_irs_prompt_builder=True,        # Stage 4 + Stage 7 only (see note)
enable_irs_stage4_exception_flow_check=True,
enable_irs_stage7_step_check=True,
enable_irs_diagnostic_consolidation=True,
```

**IRS injection scope note**: `enable_irs_prompt_builder=True` currently injects only Stage 4 (EXCEPTION_FLOW) and Stage 7 (GENERAL_COMMAND, REQUEST_INPUT, CALL_API, INVOKE_WORKER). Stage 3.5 call-sites still invoke `irs_checklist_for_stage()` but receive empty strings because `stage3_5 / stage3_5a / stage3_5b` were removed from the construct map after testing found the checklist text broke LLM JSON output format. Stage 3.5 worker boundary decisions rely on dedicated prompt files (`prompts/stage3_5a_candidate_extractor_system.txt`, `prompts/stage3_5b_boundary_decision_system.txt`) which contain hard anti-pattern and contract rules.

## Results

```text
Workers:       2  (worker_main, retrieve_sources)
Handoffs:      1  (handoff_retrieve_sources -> retrieve_sources)
Rejected:      8  (determine_communication_type, identify_missing_fields,
                   ask_clarifying_questions, maintain_provenance,
                   produce_draft, handle_revisions, finalize_draft,
                   template_matching / delegated_subtasks)
Completeness:  partial
Diagnostics:   4  (missing_output_producer, pseudo-handler TOCA,
                   missing_handler, delegation intent TOCA)
Assumptions:   4
Validation:    0 errors, 4 warnings
SPL length:    5,318 chars
```

## Scenario Checklist

| # | Scenario | Result |
|---|---|---|
| 1 | No failure signal -> no EXCEPTION_FLOW | Pass (not applicable -- failure handling section exists) |
| 2 | Failure condition only -> partial EXCEPTION_FLOW + missing_handler | **Pass** -- exception flow skeleton, missing_handler emitted |
| 3 | Vague failure policy -> type_or_contract_ambiguity | Pass (pseudo-handler "Do not finalize..." caught) |
| 4 | REQUEST_INPUT without ask signal -> no executable REQUEST_INPUT | Pass (no REQUEST_INPUT in final SPL) |
| 5 | CALL_API context-only -> no executable CALL_API | Pass (no CALL_API in final SPL) |
| 6 | Incomplete delegation -> diagnostic only | **Pass** -- template_matching rejected, delegation intent TOCA emitted |
| 7 | Complete source-backed delegation -> child worker + INVOKE_WORKER | **Pass** -- retrieve_sources has worker + handoff + INVOKE |
| 8 | Required output without producer -> missing_output_producer | Pass (assumptions_log diagnostic) |
| 9 | LLMConflictAnalyzer disabled -> v4 behavior | Pass (no semantic_conflict) |
| 10 | Resource hardening -> schema variables filtered | Pass (Phase 7 tests) |

## Key Artifacts

- `output/internal-comms/stage3_5_worker_boundary_planner.json` -- `workers=2`, `handoffs=1`, `rejected_candidates=8`
- `output/internal-comms/stage3_5c_worker_plan_materializer.json` -- `worker_ids=[worker_main, retrieve_sources]`
- `output/internal-comms/final_spl.txt` -- contains `Worker_retrieve_sources` and `[INVOKE Worker_retrieve_sources ...]`
- `output/internal-comms/final_spl.txt` -- exception flow is empty skeleton (no handler command)
- `output/internal-comms/feedback_report.md` -- `Status: partial`, 4 diagnostics, 4 assumptions
- `output/internal-comms/compile_report.txt` -- deterministic report with all diagnostics

## Regressions

```text
1136 passed, 4 skipped, 1 warning
```

v4 baseline, v5 IRS integration scenarios, and all Phase 0-Phase D tests pass.

## Known Limitations

1. `retrieve_sources` is accepted by Stage 3.5b LLM decision (not via materializer hard-fact recovery). Acceptance may vary across LLM runs.
2. `template_matching` remains diagnostic-only; Phase D deterministic guard would reject it if materialized.
3. Stage 3.5 IRS checklist injection is disabled; worker boundary quality relies on prompt file rules.
4. Some unprovenanced variables (`sources_needed`, `sources_available`, etc.) still appear from Stage 6/7 LLM extraction.
