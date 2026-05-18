# Phase 0 - Baseline Freeze and Scope Guardrails

## Goal

Freeze the current v4 behavior before v5 IRS work begins. This phase prevents v5 implementation from accidentally regressing the Partial SPL MVP, Structural Provenance, LLM Adapter Engine, feedback report, and anti-fabrication behavior.

## Scope

This phase should make no production behavior changes unless a baseline test or report is missing. It is a measurement and guardrail phase.

## Inputs

- `docs/nl_2_spl_compiler_architecture_irs_v_5 (1).md`
- `docs/spl_nl_to_spl_design_document_v4.md`
- `examples/output/internal-comms/expected_behavior.md`
- Existing unit and integration tests

## Tasks

1. Record current test baseline.
2. Identify all v4 public result fields that must remain compatible:
   - `spl_text`
   - `validation_errors`
   - `validation_warnings`
   - `compile_diagnostics`
   - `traces`
   - `adapter_warnings`
   - `completeness`
   - `assumptions`
   - `readable_report`
   - `feedback_report.md` written by CLI
3. Create a short baseline report:
   - proposed path: `docs/implementation/v5_irs_baseline_report.md`
4. Capture expected v5 non-goals:
   - no full pipeline rewrite
   - no full rule-based semantic conflict detector
   - no full DataFlowAnalyzer
   - no full WorkerGraphValidator
   - no interactive UI
   - no public result field removal
5. Confirm current internal-comms expected behavior file is present.

## Development Guidance

Use the current v4 behavior as the invariant. v5 should add construct-level IRS metadata and earlier diagnostics, not change the meaning of existing compile results.

Do not begin implementing `SPLConstructRegistry` until the baseline report lists:

- current pass/fail count
- known failing/skipped tests
- current output artifacts
- current anti-fabrication behavior
- files that should not be touched during v5 unless explicitly required

## Tests

Recommended command:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit tests/integration -q --basetemp=.pytest_tmp_v5_phase0
```

If full tests are too slow, run at least:

```powershell
python -m pytest tests/unit/test_executable_gate.py tests/unit/test_producer_index.py tests/unit/test_diagnostic_analyzer.py tests/unit/test_feedback_report_renderer.py tests/integration/test_partial_spl_mvp.py -q --basetemp=.pytest_tmp_v5_phase0
```

## Acceptance Criteria

- Baseline report exists.
- Current MVP behavior is documented.
- No production behavior is changed.
- All critical anti-fabrication tests pass.
- Known limitations are listed rather than fixed opportunistically.

## PM Review Checklist

- Does the report clearly define the stable v4 baseline?
- Are v5 non-goals explicit?
- Are any unrelated dirty files mixed into the phase?
- Can later phase regressions be judged against this baseline?

