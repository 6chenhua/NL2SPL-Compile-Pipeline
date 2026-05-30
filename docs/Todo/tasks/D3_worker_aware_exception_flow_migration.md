# Task D3: Worker-Aware Exception Flow Migration

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0, D1, D2, D6, and D4 approved.

Related docs:

- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/tasks/D2_flow_assembler_route_driven_exception_materialization.md`
- `docs/Todo/tasks/D4_block_assembler_partial_skeleton_support.md`
- `docs/Todo/tasks/D6_step_extractor_executable_filtering.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Make route-derived exception flows work when worker boundary planning is
enabled.

D2 implemented route-driven exception materialization for the legacy
`FlowStructureIR` path. D4 made condition-only exception flows survive Stage 5.
D3 extends those semantics to worker-aware flow/block/worker assembly so
failure-mode exception conditions are not silently dropped when the pipeline
uses `WorkerPlanIR`, `WorkerFlowPlanIR`, and `WorkerBlockPlanIR`.

The target behavior is:

```text
RouteAnnotation(failure_mode, EXCEPTION_FLOW.condition, executable=false)
-> worker-aware Stage 4 assigns condition-only ExceptionFlow to the right worker
-> worker-aware Stage 5 preserves the partial skeleton without invented handler
-> Stage 10 WorkerIR / ChildWorkerIR keeps the exception flow reference
```

## Scope

In scope:

- route-driven exception materialization in worker-aware Stage 4;
- deterministic ownership of exception condition spans;
- main-worker fallback or diagnostic when ownership is ambiguous;
- worker-aware Stage 5 preservation of partial exception skeletons;
- WorkerAssembler / child worker assembly preserving worker-local exception
  flow refs;
- tests for main worker and child worker exception flows.

Out of scope:

- changing D2 legacy Stage 4 behavior;
- changing D6 Stage 7 executable filtering;
- deleting or deprecating failure-mode bridge code;
- renderer syntax changes;
- normalizer/final diagnostic migration beyond preserving current structure;
- inventing exception handlers or recovery steps.

## Affected Files

Expected production areas:

- `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/span_filter.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage10_worker_assembler/assembler.py`
- `src/nl2spl/pipeline/stages/stage10_worker_assembler/child_worker_builder.py`
- `src/nl2spl/pipeline/orchestrator.py` only if needed to pass route context
  or preserve warnings, not for broad orchestration refactors

Expected tests:

- `tests/unit/pipeline/stages/test_worker_aware_flow_assembler.py`
- `tests/unit/pipeline/stages/test_worker_aware_block_assembler.py`
- `tests/unit/test_worker_assembler.py`
- `tests/unit/pipeline/test_worker_aware_orchestrator.py` if end-to-end worker
  path coverage is needed
- bridge tests only if verifying fallback compatibility

## Required Implementation

### 1. Baseline Before Production Changes

Start by adding focused failing or characterization tests for current
worker-aware behavior:

- worker-aware Stage 4 currently assembles worker flows independently;
- route-derived `failure_mode` annotations must not disappear in this path;
- hard-fact bridge fallback still exists after Stage 4.

Do not skip this baseline. D3 is risky because legacy Stage 4 and worker-aware
Stage 4 have separate execution paths.

### 2. Worker-Aware Stage 4 Materialization

Worker-aware Stage 4 must consume:

```python
routes.get_construct_slot_candidates("EXCEPTION_FLOW", "condition")
```

Filter exactly as D2 does:

- `semantic_role == "failure_mode"`;
- `construct_target == "EXCEPTION_FLOW"`;
- `slot_target == "condition"`;
- `executable is False`;
- source span exists.

For each candidate, assign the resulting condition-only `ExceptionFlow` to a
worker-local `FlowStructureIR`.

Preferred assignment rule:

```text
If condition span is owned by one worker:
    attach exception flow to that worker.
If condition span is not owned by any worker:
    attach to main worker and record a warning.
If condition span is owned by multiple workers:
    attach to main worker and record a warning.
```

Do not create handler blocks, handler steps, or recovery actions.

### 3. Dedupe And Bridge Compatibility

Worker-aware route-derived exception flows must dedupe with:

- LLM-generated worker-local exception flows;
- `bridge_failure_modes_worker_scoped()` fallback output.

Use normalized condition text, consistent with D2.

During D3:

- keep `bridge_failure_modes_worker_scoped()` as fallback;
- do not delete bridge code;
- ensure route + bridge does not duplicate the same condition in a worker flow.

### 4. Worker-Aware Stage 5 Preservation

Stage 5 worker-aware block assembly must preserve worker-local condition-only
exception flows.

Expected shape:

```python
worker_block_plan.worker_blocks["worker_main"].exception_flow_blocks[
    "exc_adapter_00"
] == []
```

or equivalent existing partial skeleton representation.

It must reuse D4 semantics:

- no invented handler blocks;
- route annotation condition spans identify fabricated blocks;
- source-backed handler spans remain preserved.

### 5. Stage 10 Worker Assembly Preservation

`WorkerAssembler.assemble_from_worker_scoped()` and child worker builder must
preserve worker-local exception flow references:

- main worker exception flows become `WorkerIR.exception_flows`;
- child worker exception flows become `ChildWorkerIR.exception_flows`;
- empty block refs are allowed for partial skeletons;
- condition text and flow id are preserved.

Do not require renderer changes in D3.

### 6. Ambiguous Ownership Warnings

If an exception condition cannot be assigned cleanly, D3 should not silently
drop it.

At minimum:

- attach to main worker;
- add a warning to `WorkerFlowPlanIR.warnings`.

The warning should name:

- condition span id;
- exception condition text;
- reason for main-worker fallback.

### 7. No Synthetic Handler Behavior

D3 must remain aligned with D4 and D6:

- failure condition does not become a step;
- exception flow can remain condition-only;
- no fake handler block masks downstream `missing_handler`.

## Required Tests

### Test 1: Worker-Aware Stage 4 Materializes Main Worker Failure

Input:

- worker plan with main worker owning `s_failure`;
- route annotation marks `s_failure` as failure mode
  `EXCEPTION_FLOW.condition`;
- worker-local LLM Stage 4 output has no exception flows.

Assert:

- `WorkerFlowPlanIR.worker_flows[main_worker_id].exception_flows` contains one
  condition-only exception flow;
- condition text equals source span text;
- spans include `s_failure`;
- no handler structure exists.

### Test 2: Worker-Aware Stage 4 Materializes Child Worker Failure

Input:

- child worker owns `s_failure`;
- route annotation marks `s_failure` as failure mode.

Assert:

- child worker flow contains the exception flow;
- main worker does not duplicate it;
- no route-derived failure is silently dropped.

### Test 3: Unowned Or Ambiguous Failure Falls Back To Main Worker

Input:

- failure condition span is not owned by any worker, or appears in multiple
  worker ownership sets.

Assert:

- main worker receives the exception flow;
- `WorkerFlowPlanIR.warnings` records the fallback reason.

### Test 4: Route + Bridge Worker Path Does Not Duplicate

Input:

- route annotation and adapter hard fact represent the same failure condition;
- worker-aware orchestrator path calls Stage 4 then bridge fallback.

Assert:

- final worker flow has one exception for that condition;
- dedupe is by normalized condition text.

### Test 5: Worker-Aware Stage 5 Preserves Partial Skeleton

Input:

- `WorkerFlowPlanIR` contains worker-local condition-only exception flow;
- Stage 5 LLM returns no exception blocks.

Assert:

- `WorkerBlockPlanIR` preserves empty exception block entry for that flow;
- no handler block is invented.

### Test 6: Worker-Aware Stage 5 Strips Fabricated Condition Handler

Input:

- worker-local condition-only exception flow;
- Stage 5 LLM returns an exception block sourced only from the condition span.

Assert:

- fabricated block is stripped;
- warning is recorded;
- source-backed handler span, if present separately, is preserved.

### Test 7: Stage 10 Preserves Main Worker Exception Flow

Input:

- worker-scoped flow/block/step/resource plans contain main worker partial
  exception flow.

Assert:

- assembled `WorkerIR.exception_flows` includes the flow id and condition text;
- empty block refs are allowed.

### Test 8: Stage 10 Preserves Child Worker Exception Flow

Input:

- child worker flow contains a partial exception flow.

Assert:

- assembled `ChildWorkerIR.exception_flows` includes the flow id and condition
  text.

### Test 9: No Stage 7 / Renderer / Bridge Deletion Changes

Review and `git diff --name-only` evidence must show:

- D6 Stage 7 filtering is not modified;
- renderer syntax is not changed;
- bridge wrappers are not deleted.

## Acceptance Criteria

D3 is complete when:

- worker-aware Stage 4 materializes route-derived exception flows;
- condition spans are assigned to the correct worker when ownership is clear;
- unowned or ambiguous condition spans fall back to main worker with warning;
- worker-aware route + bridge path does not duplicate failure conditions;
- worker-aware Stage 5 preserves condition-only exception skeletons;
- D4 fabricated-handler guard works in worker-aware block assembly;
- Stage 10 preserves main and child worker exception flow refs;
- no handler block, handler step, or recovery action is invented;
- no Stage 7, renderer, normalizer, or bridge-deletion scope is mixed in;
- focused worker-aware tests and the full unit suite pass.

## Required Evidence For Review

When submitting D3 for review, provide:

1. changed files;
2. exact test commands and output summary;
3. sample main-worker route annotation -> `ExceptionFlow`;
4. sample child-worker route annotation -> `ExceptionFlow`;
5. sample ownership fallback warning;
6. sample worker-aware Stage 5 partial skeleton output;
7. sample Stage 10 main/child worker exception flow refs;
8. confirmation that no Stage 7, renderer, normalizer, or bridge deletion was
   changed.

## PM Review Checklist

- [ ] Worker-aware Stage 4 uses route annotations for exception conditions.
- [ ] Main worker exception condition materializes.
- [ ] Child worker exception condition materializes.
- [ ] Ambiguous/unowned condition has deterministic fallback and warning.
- [ ] Route + bridge worker path dedupes.
- [ ] Worker-aware Stage 5 preserves partial skeletons.
- [ ] Stage 10 preserves main and child worker exception refs.
- [ ] No fake handler masks `missing_handler`.
- [ ] No out-of-scope Stage 7 / renderer / normalizer / bridge deletion.
- [ ] Full unit suite passes.
