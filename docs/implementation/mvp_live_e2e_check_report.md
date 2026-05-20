# Partial SPL MVP Live LLM E2E Check Report

**Date**: 2026-05-15
**Expected-output contract**: `docs/implementation/mvp_e2e_expected_outputs.md`
**Mode**: Real CLI run with `NL2SPL_ADAPTER_LLM_ENGINE=all`
**Run directory**: `output/e2e-live/*-v2`

This report checks observable behavior, not exact SPL text equality.  The
criteria are: no silent fabrication, partial SPL when information is missing,
structured diagnostics, assumptions/report separation, and provenance traces.

## Commands

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
$env:NL2SPL_ADAPTER_LLM_ENGINE = "all"

python -m nl2spl.main docs/implementation/e2e_inputs/required_output_without_producer.txt --output-dir output/e2e-live --run-name required-output-v2
python -m nl2spl.main docs/implementation/e2e_inputs/failure_condition_without_handler.txt --output-dir output/e2e-live --run-name failure-handler-v2
python -m nl2spl.main docs/implementation/e2e_inputs/structural_provenance_sections.txt --output-dir output/e2e-live --run-name structural-provenance-v2
python -m nl2spl.main docs/implementation/e2e_inputs/freeform_llm_adapter.txt --output-dir output/e2e-live --run-name freeform-adapter-v2
```

## Summary

| Scenario | Status | Key result |
| --- | --- | --- |
| Required output without producer | Pass | Output contract preserved, no synthetic producer command, `missing_output_producer`, status `partial`, required-output section provenance present. |
| Failure condition without handler | Pass | Failure hard fact is bridged to an exception-flow skeleton, no invented `REQUEST_INPUT`, `missing_handler`, status `partial`, failure-section provenance present. |
| Structural provenance / incomplete delegation | Pass | No executable `[INVOKE]`, `type_or_contract_ambiguity`, status `partial`, `delegation_intent:*` traces with `section=sec_delegation_policy`. |
| Freeform LLM adapter | Pass | Generic NL path accepts evidence-bound LLM facts, report shows `sec_freeform_input` / `p_freeform_*` provenance, uncited or invalid facts remain warnings only. |

Overall: Phase 8 live E2E is complete for the MVP acceptance criteria.  The
pipeline now demonstrates the intended teacher-aligned behavior in real CLI
runs: it materializes partial SPL when possible, refuses to silently invent
missing handlers/producers/delegation contracts, and reports missing or
ambiguous information through diagnostics, assumptions, and provenance.

## Scenario A: Required Output Without Producer

**Input**:
`docs/implementation/e2e_inputs/required_output_without_producer.txt`

**Outputs**:

- SPL: `output/e2e-live/required-output-v2/final_spl.txt`
- Report: `output/e2e-live/required-output-v2/compile_report.txt`

**Observed**:

- Report status: `partial`
- Report contains `missing_output_producer`.
- SPL keeps required output declarations.
- SPL does not contain an executable `Produce required output ...` command.
- Required-output variable traces include `section=sec_required_outputs`.
- Report contains `Provenance Traces`.

**Verdict**: Pass.

The compiler keeps the required output as a contract, does not invent a producer
step, and surfaces the missing producer explicitly.

## Scenario B: Failure Condition Without Handler

**Input**:
`docs/implementation/e2e_inputs/failure_condition_without_handler.txt`

**Outputs**:

- SPL: `output/e2e-live/failure-handler-v2/final_spl.txt`
- Report: `output/e2e-live/failure-handler-v2/compile_report.txt`

**Observed**:

- Report status: `partial`
- SPL contains `[EXCEPTION_FLOW: - Missing timeframe: The user did not provide a timeframe]`.
- SPL does not contain invented `REQUEST_INPUT` / `[INPUT ...]`.
- Report contains `missing_handler`.
- Exception-flow trace includes `section=sec_failure_handling` and packet
  `p_failure_mode_missing_timeframe_the_user_did_not_provide_a_timeframe`.
- Report contains `Provenance Traces`.

**Verdict**: Pass.

The failure-mode bridge now provides the missing partial SPL structure while the
handler remains unfilled and diagnostic-only.

## Scenario C: Structural Provenance / Incomplete Delegation

**Input**:
`docs/implementation/e2e_inputs/structural_provenance_sections.txt`

**Outputs**:

- SPL: `output/e2e-live/structural-provenance-v2/final_spl.txt`
- Report: `output/e2e-live/structural-provenance-v2/compile_report.txt`

**Observed**:

- Report status: `partial`
- Report has `Validation errors: 0`.
- SPL does not contain executable `[INVOKE ...]`.
- Report contains `type_or_contract_ambiguity` for delegation intents without a
  valid handoff contract.
- Report contains `missing_output_producer` and `missing_handler`.
- Delegation traces include:
  - `delegation_intent:source_gathering`
  - `section=sec_delegation_policy`
  - packet `p_delegation_rule_source_gathering_delegate_source_gathering_only_when_a_bounded_child_worker_contract_is_available`

**Verdict**: Pass.

The system preserves delegation provenance while refusing to render an
executable invoke because the handoff contract is incomplete.

## Scenario D: Freeform LLM Adapter

**Input**:
`docs/implementation/e2e_inputs/freeform_llm_adapter.txt`

**Outputs**:

- SPL: `output/e2e-live/freeform-adapter-v2/final_spl.txt`
- Report: `output/e2e-live/freeform-adapter-v2/compile_report.txt`

**Observed**:

- Report status: `partial`
- Generic NL adapter path is selected for freeform input.
- LLM adapter facts are evidence-bound before entering `HardFacts`.
- Report includes `section=sec_freeform_input`.
- Report includes packet provenance such as `packet=p_freeform_004`.
- Report contains `type_or_contract_ambiguity` for non-executable delegation.
- Uncited or invalid LLM facts are rejected by parser/verifier warnings and do
  not become hard facts.

**Verdict**: Pass.

The freeform adapter now creates a synthetic provenance context and lets the LLM
engine add only evidence-bound facts.

## Regression Tests

Targeted tests run after the fixes:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit/test_adapter_fact_verifier.py tests/unit/test_normalizer.py tests/unit/test_generic_nl_llm_adapter.py tests/unit/test_input_adapters.py tests/unit/test_input_adapter_pipeline.py tests/unit/test_structural_nl_llm_enrichment.py -q --basetemp=.pytest_tmp_review
python -m pytest tests/integration/test_llm_adapter_engine_e2e.py tests/integration/test_partial_spl_mvp.py -q --basetemp=.pytest_tmp_review
```

Results:

- Unit target set: `91 passed`
- Integration target set: `11 passed`

## Fixes Confirmed

- `InputAdapterRegistry` receives `llm_client` and `adapter_llm_engine`.
- `PipelineOrchestrator.run()` passes config into the registry.
- `load_config()` reads `NL2SPL_ADAPTER_LLM_ENGINE` and rejects invalid values.
- `GenericNLAdapter` returns `raw_sections` / `semantic_packets` for LLM-backed
  freeform input.
- `GenericNLAdapter` avoids duplicate LLM warnings after verifier merge.
- `StructuralNLAdapter._enrich_with_llm()` is an instance method and can merge
  non-duplicate evidence-bound LLM facts.
- LLM adapter facts with reserved compiler/schema variable names are rejected.
- Constraints targeting step variables pruned as orphan LLM noise no longer
  upgrade the result to `blocked`.

## Residual Limitations

- Downstream LLM stages can still extract schema-looking variables from stage
  context.  Some of these are pruned as orphan step variables, but required
  output scenarios may still show noisy variable declarations from Stage 6.
  This is outside the adapter-engine boundary and should be addressed in a
  later resource-extractor prompt/schema hardening pass.
- The live output is LLM-dependent.  The acceptance checks should remain
  behavior-based rather than exact-text snapshots.
