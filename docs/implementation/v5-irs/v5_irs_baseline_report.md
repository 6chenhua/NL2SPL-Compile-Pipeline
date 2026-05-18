# v5 IRS Phase 0 — Baseline Report

Date: 2026-05-16
Branch: main
Commit: 55c8c7c (demo: add env-based LLM config and split planner flag to usage.py)

## 1. Test Baseline

### Critical tests (anti-fabrication + producer + diagnostics + feedback + partial SPL)

```
Command:
  $env:PYTHONPATH = ".pytest_deps;src"
  python -m pytest tests/unit/test_executable_gate.py tests/unit/test_producer_index.py
    tests/unit/test_diagnostic_analyzer.py tests/unit/test_feedback_report_renderer.py
    tests/integration/test_partial_spl_mvp.py -q --basetemp=.pytest_tmp_v5_phase0

Result: 135 passed, 0 skipped, 0 warnings
```

### Full suite

```
Command:
  python -m pytest tests/unit tests/integration -q --basetemp=.pytest_tmp_v5_phase0_full

Result: 789 passed, 4 skipped, 1 warning (unknown pytest.mark.performance)
Time:   6.71s
```

### Skipped tests (4)

| Test | Reason |
|---|---|
| `tests/integration/test_pipeline.py::test_full_pipeline` (line 210) | Requires all stages to be implemented |
| `tests/integration/test_pipeline.py::test_stage_6_7_integration` (line 307) | Requires Stage 6-7 to be implemented |
| `tests/integration/test_pipeline.py::test_stage_8_11_integration` (line 312) | Requires Stage 8-11 to be implemented |
| `tests/integration/test_pipeline.py::test_pipeline_performance` (line 442) | Performance test — run manually |

All 4 skips are expected: traditional flat pipeline integration tests that are not yet wired in the current multi-worker path. No regression.

### Known warning

`tests/integration/test_pipeline.py:438`: `@pytest.mark.performance` is not registered in `pytest.ini`. Harmless — the mark is used for manual performance runs only.

---

## 2. v4 Public Result Fields (must remain compatible)

Defined in `PipelineResult` (`src/nl2spl/pipeline/orchestrator.py:58`) and `CompileResult` (`src/nl2spl/compiler/compile_result.py:65`):

| Field | Type | Description |
|---|---|---|
| `spl_text` | `str` | Generated SPL text |
| `validation_errors` | `list[str]` | Hard validation errors that block rendering |
| `validation_warnings` | `list[str]` | Non-blocking validation warnings |
| `compile_diagnostics` / `diagnostics` | `list[CompileDiagnostic]` | Structured compiler diagnostics (missing_handler, missing_output_producer, etc.) |
| `traces` | `list[TraceRecord]` | Provenance traces linking SPL elements to source spans |
| `adapter_warnings` | `list[str]` | Adapter-level warnings from input normalization |
| `completeness` | `Literal["complete", "partial", "blocked"]` | Overall compile status |
| `assumptions` | `list[CompileAssumption]` | Compiler assumptions NOT rendered into SPL |
| `readable_report` | `str` | Human-readable deterministic compile report |
| `intermediate_results` | `dict[str, Any]` | Intermediate stage results (PipelineResult only) |
| `final_spl_path` | `Path \| None` | Path to saved final SPL file (PipelineResult only) |

Diagnostic kinds currently registered (`DiagnosticKind`):
- `missing_handler`
- `missing_output_producer`
- `type_or_contract_ambiguity`
- `assumed_command_not_renderable`
- `unmapped_behavior_span`
- `missing_provenance`

---

## 3. Current Output Artifacts

For `internal-comms` example, the pipeline produces:

```
examples/output/internal-comms/
├── final_spl.txt                          # Rendered SPL text (partial)
├── stage1_span_slicer.json                # 37 spans from structural NL
├── stage2_field_router.json               # Field classification (behavior/resources/inputs/outputs)
├── stage3_5_worker_boundary_planner.json  # WorkerPlanIR with 2 workers + handoffs
├── stage4_flow_assembler.json             # Worker-scoped flow IRs
├── stage5_block_assembler.json            # Worker-scoped block IRs
├── stage6_resource_extractor.json         # Variable registry + symbol table
├── stage7_step_extractor.json             # Step IRs with worker-scoped steps
├── stage8_profile_extractor.json          # Policy profiles
├── stage9_constraint_extractor.json       # Constraint IRs
├── expected_behavior.md                   # Behavioral acceptance criteria (not golden SPL)
└── expected_result.md                     # Expected partial SPL behavior description
```

CLI writes `feedback_report.md` to the run directory (`config.run_dir / "feedback_report.md"`), alongside `compile_report.txt` (deterministic, no LLM involved).

---

## 4. Anti-Fabrication Baseline

The following anti-fabrication behaviors are enforced by v4 code (not LLM prompts):

### 4.1 Stage 9.5 IRNormalizer

File: `src/nl2spl/pipeline/stages/stage9_5_normalizer/`

| Check | Mechanism | Severity |
|---|---|---|
| Exception flow has no handler step | `_diagnose_exception_flow_handlers()` | diagnostic (blocks_completion) |
| CALL_API has no integration_ref or undeclared API | `_diagnose_type_contract_ambiguities()` | diagnostic (blocks_rendering) |
| INVOKE_WORKER has no concrete target worker | `_diagnose_type_contract_ambiguities()` | diagnostic (blocks_rendering) |
| REQUEST_INPUT has no source-span evidence | `_diagnose_type_contract_ambiguities()` | diagnostic |
| Step has no source_span_ids and is not compiler scaffolding | `_diagnose_assumed_commands()` | diagnostic (blocks_rendering) |
| Required output has no source-backed producer | `_ensure_required_main_outputs()` | diagnostic (blocks_completion) |
| Unused step variables pruned | `_prune_unused_step_variables()` | silent cleanup |
| Multi-output steps aggregated + unpacked | `_normalize_multi_output_steps()` | silent normalization |
| Incomplete delegation candidates resolved | `_resolve_worker_invocations()` | error if unresolved |

### 4.2 ProducerIndex

File: `src/nl2spl/compiler/producer_index.py`

Determines whether a variable has a valid producer by checking:
1. Direct step outputs in the worker
2. Handoff output bindings (child worker returns)
3. Declared API responses
4. Known child worker IDs (their invoke steps are treated as producers)

Used by Stage 9.5's `_ensure_required_main_outputs()` and `_ensure_required_worker_outputs()`. Does NOT synthesize producers — missing producers are reported as diagnostics only.

### 4.3 ExecutableElementGate

File: `src/nl2spl/pipeline/executable_gate.py`

Blocks rendering of steps that:
- Have no source span evidence (`assumed_command_not_renderable`)
- Reference undeclared APIs
- Are INVOKE_WORKER without accepted handoff
- Are CALL_API without named API evidence

### 4.4 What v4 does NOT invent

- Does NOT synthesize handler actions for exception flows with condition only
- Does NOT synthesize producer steps for required outputs without producers
- Does NOT convert missing slots into REQUEST_INPUT
- Does NOT upgrade optional delegation mentions to full child workers
- Does NOT downgrade unresolved API/worker contracts to generic commands
- Adapter hard-fact path rejects or avoids schema/internal fields as canonical hard facts. Stage 6 LLM resource extraction may still produce schema-looking variable noise; this is tracked as v5 Phase 7.

---

## 5. v5 Non-Goals (confirmed)

From `docs/nl_2_spl_compiler_architecture_irs_v_5.md` Section 8.2:

1. No full pipeline rewrite
2. No all-IR TraceRef migration
3. No rule-based semantic conflict detector (LLM prompt only in MVP)
4. No full DataFlowAnalyzer (ProducerIndex retained)
5. No full WorkerGraphValidator
6. No semantic duplicate detection
7. No interactive UI
8. No CompileResult / PipelineResult public schema change

---

## 6. Files That Should Not Be Touched During v5 (unless explicitly required by a phase)

- `src/nl2spl/pipeline/orchestrator.py` — core orchestration, pipeline execution
- `src/nl2spl/pipeline/executable_gate.py` — anti-fabrication gate
- `src/nl2spl/compiler/producer_index.py` — required-output producer check
- `src/nl2spl/compiler/compile_result.py` — public result types
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/` — IR normalization and validation
- `src/nl2spl/pipeline/stages/stage{10,11}*/` — WorkerAssembler, SPLRenderer
- `src/nl2spl/ir/*.py` — IR data models (unless adding new optional fields)
- `tests/unit/`, `tests/integration/` — test suite (additive only)
- `examples/output/internal-comms/expected_behavior.md` — behavioral acceptance criteria

---

## 7. Phase 1 Entry Conditions

Per `v5_irs_phase0_baseline.md` acceptance criteria:

- [x] Baseline report exists (this document)
- [x] Current MVP behavior is documented
- [x] No production behavior changed
- [x] All critical anti-fabrication tests pass (135/135)
- [x] Known limitations listed (4 skipped tests, 1 unregistered mark warning)
- [x] v5 non-goals explicit
- [x] No new production code/test files were modified by Phase 0. Existing dirty files predate Phase 0 and are intentionally excluded from this phase. Phase 0 only adds/updates docs/implementation/v5-irs/v5_irs_baseline_report.md.
- [x] Later phase regressions can be judged against this baseline

**Phase 1 ready:** `SPLConstructRegistry` implementation can begin when approved.
