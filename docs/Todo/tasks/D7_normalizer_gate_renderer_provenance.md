# Task D7: Normalizer, Gate, Renderer, and Provenance

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0, D1, D2, D3, D4, D5, and D6 approved.

Related docs:

- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/tasks/D2_flow_assembler_route_driven_exception_materialization.md`
- `docs/Todo/tasks/D3_worker_aware_exception_flow_migration.md`
- `docs/Todo/tasks/D4_block_assembler_partial_skeleton_support.md`
- `docs/Todo/tasks/D5_resource_profile_constraint_consumers.md`
- `docs/Todo/tasks/D6_step_extractor_executable_filtering.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Make diagnostics, rendering, and provenance consistent now that failure modes can
enter the pipeline as route-derived condition-only `ExceptionFlow` skeletons.

D2/D3 materialize exception flows from route annotations. D4 preserves
condition-only skeletons without invented handler blocks. D6 prevents failure
conditions from becoming executable steps. D7 must verify and tighten the later
compiler path so partial SPL remains explainable:

```text
failure_mode RouteAnnotation
-> condition-only ExceptionFlow
-> no fake handler
-> missing_handler diagnostic exactly once
-> partial SPL renders consistently
-> report/provenance points back to section/packet/span evidence
```

## Scope

In scope:

- Stage 9.5 normalizer behavior for condition-only exception flows;
- executable gate behavior after assumed/pseudo handlers are filtered;
- Stage 11 renderer behavior for partial exception skeletons;
- provenance aggregation for route-derived exception flows;
- diagnostic analyzer and diagnostic consolidation behavior for missing handlers;
- user-facing report and feedback report naming of route-derived missing-handler
  diagnostics.

Out of scope:

- Stage 2 routing changes;
- Stage 4 exception materialization changes;
- Stage 5 block assembly changes;
- Stage 6/8/9 consumer changes;
- Stage 7 step extraction changes;
- bridge deletion or deprecation;
- new SPL syntax redesign;
- fabricating handler commands, handler blocks, or recovery actions.

## Affected Files

Expected production areas:

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalizer.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/flow_classification.py`
- `src/nl2spl/pipeline/executable_gate.py`
- `src/nl2spl/pipeline/provenance.py`
- `src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py`
- `src/nl2spl/pipeline/stages/stage11_spl_renderer/block_renderer.py`
- `src/nl2spl/compiler/diagnostic_analyzer.py`
- `src/nl2spl/compiler/report_renderer.py`
- `src/nl2spl/compiler/feedback_report_renderer.py`

Expected tests:

- `tests/unit/test_normalizer.py`
- `tests/unit/test_executable_gate.py`
- `tests/unit/test_diagnostic_analyzer.py`
- `tests/unit/test_diagnostic_consolidation.py`
- `tests/unit/test_spl_renderer.py`
- `tests/unit/test_provenance.py`
- `tests/unit/test_feedback_report_renderer.py`
- `tests/unit/pipeline/stages/test_final_irs_checker.py`
- `tests/unit/pipeline/test_worker_aware_orchestrator.py` only if end-to-end
  worker-aware coverage is needed

## Required Implementation

### 1. Baseline Before Production Changes

Start with focused characterization tests. Do not edit production code until the
current behavior is documented for:

- route-derived `ExceptionFlow(flow_id="exc_adapter_00", condition_text=...,
  spans=[...])` with empty Stage 5 blocks;
- worker-scoped main and child exception flows;
- missing handler diagnostics before and after executable gate;
- renderer output for partial exception skeletons;
- provenance/report output for section/packet/span evidence.

If existing behavior is already correct, keep the characterization tests and make
only minimal clarifying changes.

### 2. Normalizer

The normalizer must preserve condition-only exception flows as partial skeletons.

Required behavior:

- do not drop `ExceptionFlow` entries with a condition and no handler blocks;
- do not create pseudo handler steps unless existing code already uses them for
  diagnostic compatibility;
- if pseudo handlers exist, they must be marked as assumptions and must not mask
  final missing-handler diagnostics;
- worker-scoped normalizer must preserve main and child exception flows;
- no output producer or handler step may be fabricated from failure-mode text.

Tests must cover:

- legacy `FlowStructureIR` path with route-derived condition-only exception;
- worker-scoped main worker path;
- worker-scoped child worker path;
- pseudo-handler path if currently present.

### 3. Executable Gate

The executable gate must continue to block non-source-backed or assumed handler
commands while preserving the missing-handler signal.

Required behavior:

- assumed/pseudo handler steps are filtered or marked non-renderable as today;
- after filtering, an exception flow with no handler still produces one
  `missing_handler` diagnostic;
- no duplicate `missing_handler` diagnostic is emitted for the same target;
- child worker exception flows follow the same rule.

Tests must cover:

- handler removed by gate -> `missing_handler`;
- pseudo handler does not create duplicate diagnostics;
- child worker route-derived exception flow with pseudo/assumed handler.

### 4. Renderer

Renderer output must make partial exception skeletons visible without inventing
handler content.

Required behavior:

- legacy main worker / single-worker SPL renders exception condition text or a
  clear partial exception marker;
- worker-aware main worker renders route-derived partial exception flows;
- child worker renders its partial exception flows;
- no fake `COMMAND: Handle missing timeframe` or equivalent is rendered;
- empty exception block lists are accepted.

Tests must assert rendered text, not only object shape.

### 5. Provenance

Route-derived exception flows must be traceable back to source evidence.

Required behavior:

- provenance includes exception flow id, condition text, and source span id;
- if section/packet provenance is available on the source span or annotation, the
  trace includes `source_section_id` and `source_packet_id`;
- worker-scoped provenance includes the worker id for main and child flows;
- missing provenance diagnostics should not be emitted when route-derived source
  span provenance is present.

Implementation notes:

- Prefer using existing `SpanIR.source_section_id` and `SpanIR.source_packet_id`
  before adding new fields.
- If route annotation provenance is needed, pass or preserve annotations through
  the relevant aggregation function rather than global lookup hacks.

### 6. Diagnostics And Report Rendering

Missing-handler diagnostics must be deduplicated and readable.

Required behavior:

- a route-derived condition-only exception emits exactly one missing-handler
  diagnostic for the target exception flow;
- diagnostic consolidation dedupes IRS, normalizer, diagnostic analyzer, and gate
  diagnostics for the same target where applicable;
- reports identify the failure condition and, where available, the source
  section/packet/span evidence;
- feedback report explains that the SPL is partial because the exception
  condition is known but the handler is missing;
- no duplicate missing-handler text appears in reports.

### 7. No Bridge Or Upstream Migration

D7 must not:

- delete `bridge_failure_modes()` or `bridge_failure_modes_worker_scoped()`;
- remove orchestrator bridge fallback calls;
- change FieldRouter behavior;
- change Stage 4 materialization;
- change Stage 5 fabricated handler guard;
- change Stage 7 executable filtering;
- change Stage 6/8/9 consumer behavior.

## Required Tests

### Test 1: Legacy Partial Exception Normalizer Path

Input:

- `FlowStructureIR` containing route-derived `ExceptionFlow` with condition and
  spans;
- `BlockStructureIR.exception_flow_blocks[flow_id] == []`;
- no handler steps.

Assert:

- exception flow remains present after normalization;
- no handler step is created;
- missing-handler diagnostic remains available downstream.

### Test 2: Worker-Scoped Partial Exception Normalizer Path

Input:

- `WorkerFlowPlanIR` with main and child route-derived exception flows;
- matching empty `WorkerBlockPlanIR` exception block entries.

Assert:

- both main and child exception flows survive worker-scoped normalization;
- no handler steps are created.

### Test 3: Gate Missing Handler Is Single

Input:

- route-derived exception flow;
- pseudo/assumed handler step if the current path can produce one.

Assert:

- assumed handler is filtered or marked non-renderable;
- exactly one `missing_handler` diagnostic exists for that exception flow;
- no duplicate diagnostic appears after consolidation.

### Test 4: Renderer Legacy Partial Skeleton

Input:

- final worker or single-worker IR with condition-only exception flow.

Assert:

- rendered SPL includes the exception condition;
- rendered SPL indicates missing/partial handler or leaves handler empty in the
  established project style;
- no synthetic handler command appears.

### Test 5: Renderer Worker-Aware Partial Skeleton

Input:

- main worker and child worker each have condition-only exception flow refs.

Assert:

- rendered SPL includes main and child exception conditions;
- child worker exception flow remains under the child worker;
- no synthetic handler command appears.

### Test 6: Provenance For Route-Derived Exception Flow

Input:

- source span with `source_section_id`, `source_packet_id`, and route-derived
  exception flow.

Assert:

- provenance trace contains exception flow id;
- trace contains source span id;
- trace contains section and packet ids when available;
- no missing provenance diagnostic is emitted for that exception flow.

### Test 7: Report Names Failure Evidence

Input:

- compile result with route-derived missing-handler diagnostic and provenance.

Assert:

- feedback/report output contains failure condition text;
- output contains source section or packet label/id when available;
- output does not contain duplicated missing-handler entries.

### Test 8: No Out-Of-Scope Changes

Review and `git diff --name-only` evidence must show:

- no FieldRouter changes;
- no Stage 4/5/6/7/8/9 changes;
- no bridge deletion/deprecation;
- no broad renderer syntax redesign.

## Acceptance Criteria

D7 is complete when:

- route-derived exception flows survive normalizer paths;
- main and child worker exception flows survive worker-scoped paths;
- missing-handler diagnostics are emitted exactly once per missing handler;
- executable gate does not mask missing handlers;
- partial SPL renders consistently for legacy and worker-aware paths;
- renderer does not invent handler commands;
- provenance traces route-derived flows to span/section/packet evidence;
- reports show readable failure evidence and no duplicate missing-handler noise;
- no bridge deletion or upstream stage migration is mixed in;
- focused D7 tests and the full unit suite pass.

## Required Evidence For Review

When submitting D7 for review, provide:

1. changed files;
2. exact test commands and output summary;
3. sample normalizer output showing condition-only exception flow preserved;
4. sample gate/diagnostic output showing exactly one missing-handler diagnostic;
5. sample rendered SPL for legacy partial exception skeleton;
6. sample rendered SPL for worker-aware main and child partial skeletons;
7. sample provenance trace naming span/section/packet evidence;
8. sample report or feedback report snippet naming the failure condition/evidence;
9. confirmation that FieldRouter, Stage 4/5/6/7/8/9, and bridges were not changed.

## PM Review Checklist

- [ ] Normalizer preserves route-derived condition-only exception flows.
- [ ] Worker-scoped normalizer preserves main and child exception flows.
- [ ] Gate preserves exactly one missing-handler diagnostic after filtering.
- [ ] Diagnostic consolidation dedupes missing-handler noise.
- [ ] Legacy renderer displays partial exception skeleton.
- [ ] Worker-aware renderer displays main and child partial exception skeletons.
- [ ] No synthetic handler command is rendered.
- [ ] Provenance includes span id.
- [ ] Provenance includes section/packet ids when available.
- [ ] Reports name failure condition/evidence.
- [ ] No bridge deletion or upstream migration is mixed in.
- [ ] Full unit suite passes.
