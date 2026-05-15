# Phase 0 Baseline Report — Partial SPL MVP

**Date**: 2026-05-15
**Status**: Baseline frozen

## 0. Reproduction Command

The test baseline was produced in the environment described below.  If you
get `ModuleNotFoundError: No module named 'pytest'`, your shell is using a
different Python interpreter — switch to the one shown here or activate the
matching venv.

### Environment

| Item | Value |
|---|---|
| Python executable | `C:\Python314\python.exe` |
| Python version | 3.14.3 |
| No venv used | System-wide install at `C:\Python314` |
| pytest version | 9.0.3 |
| pytest location | `C:\Users\40795\AppData\Roaming\Python\Python314\site-packages` |
| nl2spl install | Editable (`pip install -e ".[dev]"`) at project root |
| Working dir | `C:\WorkingLocation\UGAiForge\nl2spl_improve\nl2spl` |
| OS | Windows 11 Home China 10.0.26200 |

### Exact command

```powershell
# From the project root, no venv activation needed:
python -m pytest tests/ -v --tb=short
```

### First-time setup (if pytest is missing)

```powershell
# Install the project in editable mode with dev extras:
pip install -e ".[dev]"

# Verify:
python -m pytest --version
```

### Expected result

```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\WorkingLocation\UGAiForge\nl2spl_improve\nl2spl
configfile: pyproject.toml
collected 548 items
...
================== 544 passed, 4 skipped, 1 warning in 6.48s ==================
```

The 4 skipped tests all require LLM access (`test_pipeline_end_to_end`,
`test_stages_6_to_7_integration`, `test_stages_8_to_11_integration`,
`test_pipeline_latency`). All 544 passing tests are pure-code stages
(normalizer, gate, provenance, assembler, renderer, prompt builders).

If you are on a different machine: install the project with
`pip install -e ".[dev]"` using your Python ≥ 3.11, then run the same
`python -m pytest` command.  The exact count of skipped tests may vary
depending on LLM key availability; the 544 passing tests should remain
stable.

## 1. Test Status

```
544 passed, 4 skipped, 0 failures in 6.48s
Python 3.14.3, pytest 9.0.3
```

### Skipped tests (expected — require LLM access or specific config)

| Test | Reason |
|---|---|
| `test_pipeline_end_to_end` | Requires LLM API key |
| `test_stages_6_to_7_integration` | Requires LLM API key |
| `test_stages_8_to_11_integration` | Requires LLM API key |
| `test_pipeline_latency` | Marked `@pytest.mark.performance` |

### Key test files relevant to MVP

| File | Tests | Coverage |
|---|---|---|
| `tests/unit/test_executable_gate.py` | 19 | Gate classification, renderability, filtering, post-gate handler detection |
| `tests/unit/test_provenance.py` | 15 | Worker/flow/step/constraint/variable traces, span resolution, scoped refs |
| `tests/unit/test_normalizer.py` | 33 | Missing handler, missing producer, exception flow preservation, anti-fabrication diagnostics, contract ambiguity, delegation negative path |

## 2. TODO 1-8 Completion Verification

### TODO 1: Stop Stage 9.5 From Inventing Required Output Producers

**Status: DONE**

- `normalization.py:228-268` — `_ensure_required_main_outputs()` no longer synthesizes `GENERAL_COMMAND` steps. Instead, it emits `CompileDiagnostic(kind="missing_output_producer")` via `_build_missing_output_producer_diagnostic()`.
- `normalization.py:270-285` — `_is_valid_producer()` gates on source_span_ids, handoff_id, or `compiler_unpack` origin.
- Worker OUTPUTS declaration alone does not count as a producer.
- Tests: `test_required_output_without_producer_remains_declared`, `test_missing_output_producer_does_not_obscure_validation_errors`, `test_required_outputs_get_normal_path_producers`

### TODO 2: Stage 7 Stop Forcing Every Behavior Span Into Executable Steps

**Status: DONE**

- `prompts/stage7_system.txt:116-118` — Now allows `unmapped_spans` for "non-executable conditions, policies, or partial descriptions."
- `source_span_ids` must not be empty for source-backed steps, but handoff-generated steps (INVOKE_WORKER, CALL_API) may have empty spans.
- Tests in `test_stage7_prompt.py` and `test_usage_stage7_prompt.py`.

### TODO 3: Keep Partial Exception Flows Instead of Repairing Them

**Status: DONE**

- `normalizer.py:126` — `_diagnose_exception_flow_handlers()` emits `missing_handler` when exception flows have no handler steps.
- `executable_gate.py:213-270` — `_post_gate_missing_handler()` re-checks after gate filtering; emits `missing_handler` when assumed handler is removed.
- Exception flows are preserved even without handlers.
- No synthetic handler commands (REQUEST_INPUT, GENERAL_COMMAND) are invented.
- Tests: `test_exception_flow_preserved_even_without_handler`, `test_exception_flow_without_handler_emits_missing_handler`, `test_vague_handler_gate_chain`

### TODO 4: Structured Diagnostic Collector in Stage 9.5

**Status: DONE**

- `ir/diagnostics.py` defines `CompileDiagnostic` with `diagnostic_id`, `kind`, `severity`, `message`, `target_ref`, `source_span_ids`, `suggested_resolution`, `blocks_rendering`, `blocks_completion`.
- `ir/diagnostics.py` defines `StepRenderInfo` with `step_id`, `origin`, `renderable`, `render_block_reason`.
- Stage 9.5 generates four diagnostic kinds via:
  - `_diagnose_exception_flow_handlers()` → `missing_handler`
  - `_ensure_required_main_outputs()` → `missing_output_producer`
  - `_diagnose_type_contract_ambiguities()` → `type_or_contract_ambiguity`
  - `_diagnose_assumed_commands()` → `assumed_command_not_renderable`
- The executable gate also generates `assumed_command_not_renderable` and `missing_handler`.

### TODO 5: Provenance Aggregation Without Full TraceRef

**Status: DONE**

- `pipeline/provenance.py` — `ProvenanceAggregator` builds `TraceRecord` entries from existing `source_span_ids`.
- Resolves `source_section_id` / `source_packet_id` through `SpanIR`.
- Variable provenance recovered from producer steps, handoffs, contracts — NOT from `VariableSpec.source`.
- Relation defaults: `direct` (source span), `normalized` (compiler_unpack), `inferred` (structural), `assumed` (no evidence).
- `TraceRecord` has `target_ref`, `source_span_ids`, `source_section_id`, `source_packet_id`, `relation`, `explanation`, `needs_confirmation`.
- Tests: 15 covering worker, flow, step, constraint, variable, profile traces, scoped refs.

### TODO 6: Executable Element Gate Before Rendering

**Status: DONE**

- `pipeline/executable_gate.py` — `ExecutableElementGate` classifies steps by origin and filters non-renderable commands.
- `StepRenderInfo` side table with `origin` (source_backed / handoff_generated / compiler_synthetic / assumed) and `renderable`.
- Applied in orchestrator at `orchestrator.py:381-386`, between Stage 10 (assembly) and Stage 11 (rendering).
- Gate rules: source_backed → renderable; handoff_generated → renderable only with valid target + IO bindings; compiler_synthetic → renderable only for unpack scaffolding; assumed → not renderable.
- Post-gate `missing_handler` check re-evaluates exception flows after assumed handler steps are removed.
- Tests: 19 covering origin classification, renderability rules, handoff validation, gate filtering, child-worker filtering, post-gate handler detection.

### TODO 7: Keep Adapter Warnings Separate From Compile Diagnostics

**Status: DONE**

- `PipelineResult.adapter_warnings: list[str]` — separate from `compile_diagnostics`.
- Adapter warnings collected at `orchestrator.py:115-117`.
- `compile_diagnostics` aggregates: stage7 diagnostics + normalization diagnostics + gate diagnostics + provenance diagnostics.
- `main.py:76-119` reports adapter warnings, validation errors, validation warnings, compile diagnostics, and traces as separate stderr sections.

### TODO 8: Tests Around Anti-Fabrication

**Status: DONE**

All required test cases have corresponding tests:

| Test case | Test |
|---|---|
| No failure source → no exception flow, no missing_handler | `test_no_failure_source_no_exception_flow_no_missing_handler` |
| Failure condition only → partial exception flow + missing_handler | `test_exception_flow_without_handler_emits_missing_handler` |
| Failure condition + handler → complete exception + handler | `test_exception_flow_with_handler_step_does_not_emit_missing_handler` |
| Required output without producer → missing_output_producer | `test_required_output_without_producer_remains_declared` |
| Vague exception policy → type_or_contract_ambiguity | `test_vague_exception_policy_handler_is_assumed` |
| API retrieval without named API → no CALL_API | `test_call_api_without_integration_ref_is_ambiguity` |
| Incomplete delegation → no executable child worker | `test_incomplete_delegation_no_executable_child` + gate tests |
| Assumed command → report only, not rendered | `test_assumed_steps_are_blocked` + `test_synthetic_step_without_source_is_assumed_not_renderable` |

## 3. Current Architecture Snapshot

### Module inventory

```
src/nl2spl/
├── compiler/
│   └── spl_formatter.py          # SPL text formatting (pre-existing)
├── ir/
│   ├── diagnostics.py            # CompileDiagnostic, TraceRecord, StepRenderInfo
│   ├── step_ir.py                # StepIR
│   ├── worker_ir.py              # WorkerIR, FlowRef, ExceptionFlowRef, etc.
│   ├── worker_plan_ir.py         # WorkerPlanIR, WorkerHandoffIR, etc.
│   ├── ... (other IRs)
│   └── __init__.py               # Re-exports CompileDiagnostic, TraceRecord
├── pipeline/
│   ├── orchestrator.py           # PipelineOrchestrator, PipelineResult
│   ├── executable_gate.py        # ExecutableElementGate
│   ├── provenance.py             # ProvenanceAggregator
│   ├── worker_plan_validator.py  # WorkerPlanValidator
│   └── stages/...
└── main.py                       # CLI entry point
```

### PipelineResult current fields

```python
@dataclass
class PipelineResult:
    spl_text: str
    validation_errors: list[str]
    validation_warnings: list[str]
    compile_diagnostics: list[Any] = field(default_factory=list)  # CompileDiagnostic
    traces: list[Any] = field(default_factory=list)               # TraceRecord
    adapter_warnings: list[str] = field(default_factory=list)
    intermediate_results: dict[str, Any] = field(default_factory=dict)
    final_spl_path: Path | None = None
```

### Pipeline flow (current orchestration)

```
Adapter → Stage 1 (spans) → Stage 2 (routes) → Stage 3 (ambiguity)
  → [Stage 3.5 (worker plan, if flag on)]
  → Stage 4 (flows) → Stage 5 (blocks)
  → Stage 6 (resources) → Stage 7 (steps + diagnostics)
  → Stage 8 (profile) → Stage 9 (constraints)
  → Stage 9.5 (normalization + diagnostics)
  → Stage 10 (worker assembly)
  → ExecutableElementGate (filter + gate diagnostics)
  → Stage 11 (SPL render)
  → ProvenanceAggregator (traces + provenance diagnostics)
  → PipelineResult
```

### Diagnostic flow

```
Stage 7:     stage7_diagnostics (unmapped behavior spans)
Stage 9.5:   normalizer.diagnostics (missing_handler, missing_output_producer,
                type_or_contract_ambiguity, assumed_command_not_renderable)
Gate:        gate_diags (assumed_command_not_renderable, missing_handler)
Provenance:  provenance_diags (missing_provenance)
                ↓
PipelineResult.compile_diagnostics = stage7 + normalization + gate + provenance
```

## 4. What's Missing for MVP (Phases 1-10)

### Phase 1: CompileResult dataclasses

**Missing**:
- `src/nl2spl/compiler/compile_result.py` with `MissingSlot`, `CompileAssumption`, `CompileResult`, `Completeness` type
- `PipelineResult` lacks: `completeness`, `assumptions`, `readable_report`

### Phase 2: ProducerIndex

**Missing**:
- `src/nl2spl/compiler/producer_index.py` with `ProducerRef` dataclass
- Producer index currently implicit in normalization logic (`_is_valid_producer`, producer detection in `_ensure_required_main_outputs`)

### Phase 3: ExecutableElementGate (already exists)

**Already exists** at `pipeline/executable_gate.py`. May need minor relocation or wrapping. Gate is wired into orchestrator and working.

### Phase 4: DiagnosticAnalyzer

**Missing**:
- `src/nl2spl/compiler/diagnostic_analyzer.py`
- Current diagnostic logic is spread across normalizer mixin methods and gate — needs to be extracted into a dedicated, fixture-testable module
- `MissingSlot` dataclass not yet implemented
- `CompileDiagnostic` needs `missing_slot: MissingSlot | None` field (per MVP design §Data Structures)

### Phase 5: AssumptionBuilder

**Missing**:
- `src/nl2spl/compiler/assumptions.py` with `build_assumptions()`
- `CompileAssumption` dataclass not yet defined
- No assumption-building from diagnostics + render_info

### Phase 6: Trace Aggregation (already exists)

**Already exists** at `pipeline/provenance.py`. May need relocation or wrapping. Working and tested.

### Phase 7: Completeness Calculator

**Missing**:
- `src/nl2spl/compiler/completeness.py` with `compute_completeness()`
- No completeness computation wired into orchestrator

### Phase 8: ReportRenderer

**Missing**:
- `src/nl2spl/compiler/report_renderer.py`
- No deterministic report generation
- `readable_report` not produced

### Phase 9: Orchestrator + CLI integration

**Missing**:
- `PipelineResult` lacks `completeness`, `assumptions`, `readable_report`
- `main.py` does not output `readable_report` or write `compile_report.txt`
- No stderr summary with status, diagnostic count, report path

### Phase 10: Integration Fixtures + DoD

**Missing**:
- `tests/integration/test_partial_spl_mvp.py`
- 6 MVP scenario integration tests
- Final acceptance report

## 5. Environment Limitations

- **No LLM access**: Integration tests requiring LLM calls are skipped. We test against deterministic stages (normalizer, gate, provenance, assembler, renderer) which are all pure-code.
- **Windows PowerShell 5.1**: Shell commands use PowerShell syntax. Bash also available via Git Bash.
- **Python 3.14.3**: All packages install and import correctly.

## 6. MVP Scope Boundaries (Confirmed)

The following are explicitly **out of scope** for MVP and will not block completion:

- Structural NL section/packet provenance display (MVP+ stretch)
- Multi-turn user clarification UI
- Full semantic duplicate detection
- Full policy conflict detection
- Deep nested-flow repair
- Nested child-worker extraction
- Complex worker graph planning
- Full `TraceRef` on every IR type

## 7. Key Artifacts

| Artifact | Path | Status |
|---|---|---|
| Refactor TODO list | `docs/implementation/pipeline_requirement_fidelity_refactor_todo.md` | All 8 TODOs complete |
| MVP Design | `docs/implementation/partial_spl_mvp_design.md` | Reference for Phases 1-10 |
| Execution Plan (HTML) | `docs/implementation/partial_spl_mvp_execution_plan.html` | Progress tracking |
| This Report | `docs/implementation/phase0_baseline_report.md` | Baseline frozen |
