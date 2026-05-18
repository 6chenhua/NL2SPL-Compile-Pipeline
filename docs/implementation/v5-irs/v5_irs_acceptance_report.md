# v5 IRS Acceptance Report

Date: 2026-05-17
Branch: main
Commit: 55c8c7c (base) + v5 IRS Phase 0–8 changes

## 1. Test Results

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit tests/integration -q
```

```
1113 passed, 4 skipped, 1 warning
```

### Per-phase cumulative totals

| Phase | Tests | Description |
|---|---|---|
| 0 | 789 | v4 baseline frozen |
| 1 | 884 (+95) | SPLConstructRegistry + DiagnosticRegistry |
| 2 | 930 (+46) | IRSDrivenPromptBuilder |
| 3 | 951 (+21) | Stage 4 IRS exception flow check |
| 4 | 990 (+39) | Stage 7 IRS step check |
| 5 | 1009 (+19) | Diagnostic consolidation |
| 6 | 1029 (+20) | LLMConflictAnalyzer MVP |
| 7 | 1100 (+71) | Resource Extractor Hardening |
| 8 | 1113 (+13) | v5 IRS integration tests |

4 skipped tests are pre-existing: 3 legacy pipeline tests awaiting stage implementation, 1 manual performance test.

## 2. Scenario Coverage

| # | Scenario | Status | Key Assertion |
|---|---|---|---|
| 1 | No failure signal | Pass | No EXCEPTION_FLOW, no missing_handler |
| 2 | Failure condition only | Pass | Stage4 partial satisfaction + Stage9.5 missing_handler |
| 3 | Vague failure policy | Pass | type_or_contract_ambiguity, not renderable |
| 4 | REQUEST_INPUT without ask signal | Pass | Not renderable, type_or_contract_ambiguity |
| 5 | CALL_API context-only mention | Pass | Not renderable, type_or_contract_ambiguity |
| 6 | Incomplete delegation | Pass | INVOKE_WORKER not renderable |
| 7 | Complete source-backed delegation | Pass | INVOKE_WORKER renderable, complete |
| 8 | Required output without producer | Pass | missing_output_producer diagnostic |
| 9 | LLMConflictAnalyzer disabled | Pass | No semantic_conflict (v4 behavior) |
| 10 | Resource hardening | Pass | Stage 6 filter + warnings propagate to adapter_warnings |

## 3. Side-Channel Verification

- `intermediate_results["construct_satisfaction"]["stage4"]` — Stage 4 EXCEPTION_FLOW reports
- `intermediate_results["construct_satisfaction"]["stage7"]` — Stage 7 step reports
- `intermediate_results["stage_local_diagnostics"]["stage4"]` — Stage 4 diagnostics
- `intermediate_results["stage_local_diagnostics"]["stage7"]` — Stage 7 diagnostics
- Consolidation merges stage-local diagnostics into `compile_diagnostics`
- `PipelineResult.readable_report` shows IRS diagnostics
- `render_feedback_report()` shows IRS diagnostics

## 4. Anti-Fabrication Compliance

All v4 anti-fabrication boundaries preserved:

- No invented handler actions for exception flows with condition only
- No synthesized producer steps for required outputs
- Missing slots not converted to REQUEST_INPUT
- Optional delegation not promoted to child worker without contract
- Unresolved API/worker contracts not downgraded to generic command
- Schema/IR field names filtered at Stage 6 boundary
- ExecutableElementGate remains final renderability authority
- Stage 9.5 missing_handler authority preserved

## 5. Feature Flags (all default False)

| Flag | Phase | Purpose |
|---|---|---|
| `enable_irs_prompt_builder` | 2 | Inject IRS checklist into Stage 7 prompts |
| `enable_irs_stage4_exception_flow_check` | 3 | Stage 4 post-hoc exception flow check |
| `enable_irs_stage7_step_check` | 4 | Stage 7 post-hoc step check |
| `enable_irs_diagnostic_consolidation` | 5 | Merge stage-local diagnostics |
| `enable_llm_conflict_analyzer` | 6 | LLM semantic conflict analysis |
| `enable_resource_name_filter` | 7 | Filter schema-looking variable names |

## 6. Files Changed by v5 IRS

```
New modules:
  src/nl2spl/compiler/analyzers/__init__.py
  src/nl2spl/compiler/analyzers/semantic_conflict.py
  src/nl2spl/compiler/construct_registry.py
  src/nl2spl/compiler/diagnostic_registry.py
  src/nl2spl/compiler/irs_prompt_builder.py
  src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py
  src/nl2spl/pipeline/stages/stage6_resource_extractor/resource_name_filter.py
  src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py

Modified modules:
  src/nl2spl/compiler/__init__.py
  src/nl2spl/compiler/compile_result.py
  src/nl2spl/config.py
  src/nl2spl/pipeline/orchestrator.py
  src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py
  src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py
  src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
  src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py

Modified prompt:
  prompts/stage6_system.txt

New tests:
  tests/unit/test_construct_registry.py
  tests/unit/test_diagnostic_registry.py
  tests/unit/test_irs_prompt_builder.py
  tests/unit/test_stage4_irs_exception_flow.py
  tests/unit/test_stage7_irs_step_extraction.py
  tests/unit/test_diagnostic_consolidation.py
  tests/unit/test_semantic_conflict_analyzer.py
  tests/unit/test_resource_extractor_hardening.py
  tests/integration/test_v5_irs_pipeline.py
```

## 7. Known Limitations

1. LLMConflictAnalyzer is a stub — no actual LLM call yet.
2. Vague failure policy detection is span-based only (no text heuristic).
3. Stage 4 does not assess handler_action (Stage 9.5 authority).
4. CALL_API / INVOKE_WORKER post-hoc checks are structural only.
5. Verifier does not validate target_ref existence (format check only).
6. Worker-scoped normalizer only checks worker output contracts, not global output variables.
7. All IRS flags default to False — full v5 behavior requires explicit opt-in.
