# Partial SPL MVP Execution Plan

This document is the review-friendly Markdown version of
`partial_spl_mvp_execution_plan.html`. The HTML file is the interactive progress
tracker; this Markdown file is intended for code review, team sync, and planning
discussion.

## Goal

Deliver a small but real Partial SPL MVP:

```text
incomplete NL / structural NL
-> current compiler-style pipeline
-> partial or complete SPL draft
-> diagnostics + provenance + assumptions
-> deterministic readable report
```

The MVP must demonstrate requirement fidelity:

- materialize source-backed information as far as possible;
- do not invent executable handler, producer, API, worker, or user-input steps;
- expose missing, ambiguous, inferred, and assumed information explicitly;
- preserve extension points for the full design without widening MVP scope.

## Scope Rules

In scope:

- one main worker;
- at most one level of child worker from source-backed delegation;
- simple normal flow;
- simple failure conditions;
- required outputs;
- optional constraints;
- deterministic diagnostics, provenance, assumptions, completeness, and report.

Out of scope:

- multi-turn UI;
- full semantic conflict detection;
- deep nested-flow repair;
- nested child workers;
- complex worker graph planning;
- complex API contract inference.

Stretch goal:

- structural NL `source_section_id` / `source_packet_id` provenance. This is not
  a hard MVP blocker unless the adapter is already stable enough.

## Dependency-Ordered Phases

### Phase 0: Baseline Freeze

Purpose: freeze TODO 1-8 anti-fabrication behavior as the implementation
baseline.

Deliverables:

- Inventory current diagnostics, traces, gate, provenance, and adapter warnings.
- Record test status and environment limitations.
- Confirm the remaining MVP work does not require pipeline rewrite.

Acceptance:

- Existing anti-fabrication behavior is the baseline for later phases.
- The implementation order in this document is accepted.
- Structural NL section/packet provenance is treated as MVP+ unless stable.

Tests:

- Run current related unit/integration tests.
- Record whether `pytest` is available in the environment.

### Phase 1: Public Result Interface

Purpose: stabilize the public output shape before implementing report-facing
features.

Deliverables:

- Add `src/nl2spl/compiler/compile_result.py`.
- Define `MissingSlot`, `CompileAssumption`, `CompileResult`, and
  `Completeness`.
- Extend `PipelineResult` with:
  - `completeness`
  - `assumptions`
  - `readable_report`

Implementation notes:

- Reuse existing `CompileDiagnostic`, `TraceRecord`, and `StepRenderInfo`.
- Keep existing fields such as `compile_diagnostics` for compatibility.
- Optionally add a compatibility alias from `diagnostics` to
  `compile_diagnostics`.

Acceptance:

- Old callers can still access `spl_text`, `validation_errors`,
  `validation_warnings`, and `compile_diagnostics`.
- New callers can access `completeness`, `assumptions`, and `readable_report`.
- Dataclass defaults do not share mutable lists.

Tests:

- `tests/unit/test_compile_result.py`
- PipelineResult backward compatibility test.

### Phase 2: ProducerIndex

Purpose: make required-output producer detection precise and testable.

Deliverables:

- Add `src/nl2spl/compiler/producer_index.py`.
- Define `ProducerRef`.
- Make `missing_output_producer` diagnostics use `ProducerIndex`.

Producer rules:

- Count renderable `StepIR.outputs`.
- Count valid handoff `OutputBindingIR.parent_variable`.
- Count valid `CALL_API` outputs.
- Count explicitly allowed deterministic compiler scaffold, such as
  `compiler_unpack`.
- Do not count worker `OUTPUTS` declarations as producers.
- Do not use `VariableSpec.source` as producer evidence.

Acceptance:

- Required output without producer emits `missing_output_producer`.
- Blocked assumed step output does not count as producer.
- Valid child-worker handoff output can count as producer.
- Worker output declaration alone does not suppress the diagnostic.

Tests:

- `tests/unit/test_producer_index.py`
- Required-output integration fixture.

### Phase 3: Executable Element Gate

Purpose: make renderability a first-class anti-fabrication decision before
Stage 11.

Deliverables:

- Stabilize `ExecutableElementGate`.
- Stabilize `StepRenderInfo` / renderability side table.
- Ensure gate diagnostics can feed later analyzer, assumptions, and report.

Gate rules:

- Source-backed executable steps are renderable unless blocked by
  contract/type ambiguity.
- `REQUEST_INPUT` must be explicitly supported by source wording.
- `CALL_API` must have explicit API/integration evidence.
- `INVOKE_WORKER` must have accepted handoff, concrete target, and IO bindings.
- Assumed or synthetic executable behavior is not renderable.

Acceptance:

- Assumed behavior does not enter SPL.
- Executable commands with empty `source_span_ids` are blocked by default.
- Unresolved worker/API behavior does not degrade to generic command.
- Blocked commands become diagnostics and can later become assumptions/report
  entries.

Tests:

- `tests/unit/test_executable_gate.py`
- Gate-level anti-fabrication chain tests.

### Phase 4: DiagnosticAnalyzer + MissingSlot

Purpose: centralize requirement-fidelity diagnostics and connect them to missing
slots.

Deliverables:

- Add or organize `src/nl2spl/compiler/diagnostic_analyzer.py`.
- Use `ProducerIndex` and gate renderability decisions.
- Allow `CompileDiagnostic` to carry `MissingSlot` where useful.

Diagnostic responsibilities:

- `missing_handler`
- `missing_output_producer`
- `type_or_contract_ambiguity`
- `assumed_command_not_renderable`
- existing Stage 7 unmapped behavior diagnostics
- no-demand-no-structure negative behavior

Important rule:

```text
No demand, no structure.
```

If the user did not express a structure, do not generate that structure and do
not report that the structure is missing.

Acceptance:

- Four MVP diagnostic kinds are covered by focused tests.
- Missing diagnostics are only emitted for source-backed partial structures.
- Diagnostic `target_ref`, `source_span_ids`, and `suggested_resolution` are
  stable enough for report rendering.

Tests:

- `tests/unit/test_diagnostic_analyzer.py`
- No-demand-no-structure negative tests.

### Phase 5: AssumptionBuilder

Purpose: turn diagnostics and blocked render decisions into explicit
non-rendered suggestions.

Deliverables:

- Add `src/nl2spl/compiler/assumptions.py`.
- Implement `build_assumptions()`.
- Link assumptions to diagnostics through `related_diagnostic_id` and, when
  useful, `related_missing_slot`.

Mapping:

- `missing_handler` -> handler action suggestion.
- `missing_output_producer` -> producer step suggestion.
- `type_or_contract_ambiguity` -> API ref, worker target, or IO contract
  suggestion.
- `assumed_command_not_renderable` -> blocked command explanation.

Acceptance:

- Assumptions never enter SPL text.
- Assumptions are available through `PipelineResult.assumptions`.
- Report can merge related diagnostic and assumption instead of showing
  duplicate unrelated entries.

Tests:

- `tests/unit/test_assumptions.py`

### Phase 6: Trace Aggregation

Purpose: produce report-facing provenance without requiring full `TraceRef` on
every IR object.

Deliverables:

- Stabilize `ProvenanceAggregator` as the MVP trace aggregator.
- Produce `TraceRecord` for major worker, flow, step, constraint, and variable
  elements.
- Emit `missing_provenance` diagnostics or conservative trace warnings when
  evidence is absent.

Rules:

- Do not treat `VariableSpec.source` as provenance evidence.
- Preserve worker scope in worker-local variable trace target refs.
- Use producer steps, handoffs, and contracts as variable evidence when valid.
- Use `direct`, `normalized`, `inferred`, and `assumed` consistently.

Acceptance:

- Major elements have traces or missing provenance diagnostics.
- Assumed traces set `needs_confirmation=True`.
- Future full `TraceRef` can be added without changing report-facing schema.

Tests:

- `tests/unit/test_provenance.py`
- Worker-scoped variable trace collision test.

### Phase 7: Completeness Calculator

Purpose: compute `complete | partial | blocked` after diagnostics, renderability,
producer, and validation inputs are available.

Deliverables:

- Add `src/nl2spl/compiler/completeness.py`.
- Implement `compute_completeness()`.
- Define diagnostic-to-completeness mapping.

Rules:

- `blocked` if validation errors exist, no renderable main task exists, or a
  blocking error diagnostic exists.
- `partial` if missing/ambiguity/assumption diagnostics remain.
- `complete` if there are no blocking errors and no completion-affecting
  diagnostics.
- Adapter warnings do not affect completeness by default.

Acceptance:

- `missing_handler` -> partial.
- `missing_output_producer` -> partial.
- `assumed_command_not_renderable` -> partial.
- Validation error -> blocked.
- Clean happy path -> complete.

Tests:

- `tests/unit/test_completeness.py`
- `tests/integration/test_partial_spl_completeness.py`

### Phase 8: Deterministic ReportRenderer

Purpose: generate the human-readable compiler report from stable result fields.

Deliverables:

- Add `src/nl2spl/compiler/report_renderer.py`.
- Generate `readable_report`.
- Do not call an LLM.

Report sections:

- Summary
- Diagnostics
- Assumptions / Suggestions
- Provenance
- Validation
- Adapter

Implementation notes:

- ReportRenderer can start as a skeleton with unit tests.
- Full real-pipeline integration is validated in Phase 9 and Phase 10.
- Show source span excerpts when available.
- Section/packet provenance can be part of MVP+.

Acceptance:

- Adapter warnings, validation warnings, and compile diagnostics are separate.
- Assumed commands appear in Assumptions, not SPL.
- Output is stable enough for snapshot or exact-section tests.

Tests:

- `tests/unit/test_report_renderer.py`
- Report skeleton snapshot tests.

### Phase 9: Orchestrator + CLI Integration

Purpose: wire MVP result fields into the actual pipeline and CLI output.

Deliverables:

- Orchestrator assembles all MVP fields at the end of `run()`.
- `compile_report.txt` is written to `run_dir`.
- `main.py` prints a concise compile status summary.

Implementation order:

1. Merge Stage 7, diagnostic analyzer, gate, and provenance diagnostics.
2. Build assumptions.
3. Compute completeness.
4. Render report.
5. Return extended `PipelineResult`.
6. Save report file.

Acceptance:

- `result.completeness` is available.
- `result.assumptions` is available.
- `result.readable_report` is available.
- CLI run generates final SPL and compile report.
- Existing public fields remain compatible.

Tests:

- Orchestrator result shape integration test.
- Report file persistence test.

### Phase 10: Integration Fixtures + DoD

Purpose: prove the MVP with a small, realistic acceptance suite.

Deliverables:

- Add `tests/integration/test_partial_spl_mvp.py`.
- Add `docs/implementation/partial_spl_mvp_acceptance_report.md`.
- Cover the six core MVP scenarios.

Core fixtures:

1. Failure condition only.
2. Required output without producer.
3. Complete failure handling.
4. Vague policy.
5. Complete single-level delegation.
6. Incomplete delegation.

Acceptance:

- Each fixture asserts SPL, diagnostics, completeness, and report.
- Partial cases do not invent handlers or producers.
- Complete cases avoid unnecessary MVP diagnostics.
- Delegation happy path renders child worker and `INVOKE_WORKER`.
- Delegation negative path renders no executable child worker or
  `INVOKE_WORKER`.
- Global DoD is fully checked or each exception has a clear deferral reason.

Tests:

- `tests/integration/test_partial_spl_mvp.py`
- Full MVP integration subset.

## MVP+ / Stretch: Structural NL Provenance

This is valuable but should not block the first MVP unless the InputAdapter path
is already stable enough.

Deliverables:

- Report displays `source_section_id` / `source_packet_id`.
- Variable trace prefers adapter hard facts or source spans.
- Missing provenance is explicit.

Acceptance:

- Required output can trace to structural output section.
- Failure policy can trace to failure section.
- Delegation contract can trace to delegation section.

## Global Definition of Done

- Syntactically valid partial SPL draft can be generated.
- No demand, no structure: if the user did not express a structure, the compiler
  does not generate it and does not report it as missing.
- No invented exception handler command.
- No invented required-output producer command.
- Unresolved worker/API behavior does not degrade to generic command.
- Missing, ambiguous, inferred, and assumed information enters structured
  diagnostics.
- Major Worker / Flow / Step / Constraint / Variable elements have
  `TraceRecord` or missing-provenance diagnostics.
- Assumptions are separated from SPL text and included in the report.
- Completeness correctly distinguishes `complete`, `partial`, and `blocked`.
- `readable_report` is deterministic and does not depend on an LLM.
- One complete single-level delegation happy path exists.
- One incomplete delegation negative path exists and does not render executable
  child worker / `INVOKE_WORKER`.
- MVP integration tests cover SPL + diagnostics + completeness + report.

