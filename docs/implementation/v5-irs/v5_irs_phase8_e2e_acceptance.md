# Phase 8 - Regression, E2E Acceptance, and Freeze

## Goal

Validate v5 end-to-end and freeze the implementation with a concise acceptance report.

## Scope

Integration tests, live E2E where available, report checks, and final documentation. No new feature work should enter this phase.

## Target Files

Create:

- `tests/integration/test_v5_irs_pipeline.py`
- `docs/implementation/v5_irs_acceptance_report.md`

Update:

- `docs/implementation/v5_irs_execution_plan.html` progress state if desired
- `examples/output/internal-comms/expected_behavior.md` only if behavior contract changes intentionally

## Required Scenarios

1. No failure signal:
   - no `EXCEPTION_FLOW`
   - no `missing_handler`

2. Failure condition only:
   - partial exception flow skeleton
   - `missing_handler`
   - completeness `partial`

3. Vague failure policy:
   - no concrete exception flow
   - `type_or_contract_ambiguity`

4. REQUEST_INPUT without ask signal:
   - no executable `REQUEST_INPUT`
   - assumption or diagnostic only

5. CALL_API with context-only repository mention:
   - no executable `CALL_API`
   - resource candidate or diagnostic only

6. Incomplete delegation:
   - no executable `INVOKE_WORKER`
   - `type_or_contract_ambiguity`
   - delegation intent or worker candidate trace

7. Complete source-backed delegation:
   - child worker and `INVOKE_WORKER` allowed
   - no completion-blocking diagnostics

8. Required output without producer:
   - output remains declared
   - no synthetic producer command
   - `missing_output_producer`

9. Optional LLMConflictAnalyzer:
   - disabled path matches v4
   - enabled smoke test emits evidence-bound `semantic_conflict`

10. Resource hardening:
   - schema-looking variables are filtered

## Report Checks

Both reports must show v5 diagnostics:

- `compile_report.txt`
- `feedback_report.md`

`feedback_report.md` should explain:

- why result is partial
- which constructs materialized
- which constructs were not materialized
- missing slots
- anti-fabrication decisions
- provenance traces

## Test Commands

Recommended full command:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit tests/integration -q --basetemp=.pytest_tmp_v5_phase8
```

Focused command:

```powershell
python -m pytest tests/integration/test_v5_irs_pipeline.py tests/integration/test_partial_spl_mvp.py tests/unit/test_feedback_report_renderer.py -q --basetemp=.pytest_tmp_v5_phase8
```

Optional live E2E:

```powershell
$env:NL2SPL_ADAPTER_LLM_ENGINE = "all"
python -m nl2spl.main docs/implementation/e2e_inputs/failure_condition_without_handler.txt --output-dir output/v5-e2e --run-name failure-irs
python -m nl2spl.main docs/implementation/e2e_inputs/freeform_llm_adapter.txt --output-dir output/v5-e2e --run-name freeform-irs
```

## Acceptance Report Contents

The report should include:

- commit or working tree reference
- test command and results
- scenario table
- known limitations
- disabled feature flags
- files changed by phase
- screenshots or excerpts of `feedback_report.md` if useful

## Acceptance Criteria

- v4 critical tests pass.
- v5 IRS integration tests pass.
- Stage-local satisfaction reports are present in `intermediate_results`.
- Final SPL contains no invented handler, producer, API call, request input, or invoke worker.
- Reports show IRS-driven diagnostics.
- Acceptance report exists.

## PM Review Checklist

- Does the test suite prove behavior, not only implementation details?
- Are disabled optional features documented?
- Is internal-comms expected behavior still satisfied?
- Are known limitations explicit rather than hidden?

