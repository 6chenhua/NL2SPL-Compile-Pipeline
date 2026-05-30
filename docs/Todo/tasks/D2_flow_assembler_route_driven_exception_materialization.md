# Task D2: FlowAssembler Route-Driven Exception Materialization

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0 Downstream Baseline approved.
- D1 WorkerBoundaryPlanner Annotation Migration approved.

Related docs:

- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/tasks/D1_worker_boundary_planner_annotation_migration.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Move failure-mode exception-flow materialization from bridge-first behavior
toward route-driven Stage 4 materialization.

D2 teaches Stage 4 to consume `RouteAnnotation` entries with:

```text
semantic_role = failure_mode
construct_target = EXCEPTION_FLOW
slot_target = condition
executable = false
```

and create partial `ExceptionFlow` condition skeletons without inventing handler
steps.

## Scope

In scope:

- add a route-driven exception materializer for Stage 4;
- materialize condition-only `ExceptionFlow` skeletons from route annotations;
- dedupe route-derived exceptions against LLM-generated exceptions;
- preserve condition span ids and annotation provenance;
- keep `bridge_failure_modes()` as compatibility fallback;
- update orchestrator only enough to avoid bridge-first duplication when route
  annotations have already materialized failures;
- add focused Stage 4, bridge, and orchestrator tests.

Out of scope:

- Stage 7 executable filtering;
- worker-aware exception ownership migration;
- bridge deletion;
- block/render/normalizer changes beyond preserving current partial flow shape;
- inventing exception handler blocks or steps.

## Affected Files

Expected production areas:

- `src/nl2spl/pipeline/stages/stage4_flow_assembler/`
- `src/nl2spl/pipeline/fact_bridges.py`
- `src/nl2spl/pipeline/orchestrator.py`

Expected tests:

- `tests/unit/test_flow_assembler.py`
- `tests/unit/test_stage4_irs_exception_flow.py`
- `tests/unit/test_failure_mode_bridge.py`
- orchestrator-focused tests if bridge fallback logic is changed there

## Required Implementation

## 1. Add Route-Driven Exception Materializer

Create a small function/helper near Stage 4 flow assembly, or in a narrowly
named helper module, that consumes:

```python
routes.get_construct_slot_candidates("EXCEPTION_FLOW", "condition")
```

Filter candidates to:

- `semantic_role == "failure_mode"`;
- `executable is False`;
- span exists in the current span list when possible.

For each candidate, create an `ExceptionFlow` with:

- deterministic id;
- `condition_text` from the source span text;
- `spans=[annotation.span_id]`.

Do not create handler blocks or steps.

## 2. Dedupe Against Existing Exceptions

If Stage 4 LLM output already includes an exception flow with equivalent
condition text, do not add another.

Use the same normalization principle as the bridge:

```text
lowercase + strip punctuation / whitespace
```

Do not dedupe purely by span overlap.

## 3. Preserve Bridge Compatibility

`bridge_failure_modes()` must remain available.

During D2:

- route annotations are the preferred Stage 4 source when present;
- bridge hard facts remain fallback when annotations are missing;
- if both route-derived exceptions and hard-fact bridge input exist for the same
  failure condition, the final flow must contain only one exception flow.

Do not delete bridge tests. Update them only where they assert primary path
semantics that D2 intentionally changes.

## 4. Orchestrator Fallback Guard

If the orchestrator currently always calls `bridge_failure_modes()` after Stage
4, guard that call so it does not duplicate route-derived exceptions.

Allowed approaches:

- skip bridge call when route annotations for failure modes are present and
  Stage 4 already materialized them;
- or call bridge with existing route-derived flow and rely on condition-text
  dedupe.

The chosen behavior must be explicit in tests.

## 5. Diagnostics And Partial IR

Route-derived exception flows are condition-only partial IR. Do not synthesize
handlers.

Existing downstream missing-handler diagnostics should continue to surface in
later phases. D2 only needs to ensure no handler is fabricated.

## Required Tests

### Test 1: Stage 4 Materializes Failure Annotation

Input:

- spans include `s_failure`;
- routes include a `RouteAnnotation` for `s_failure` targeting
  `EXCEPTION_FLOW.condition`;
- LLM Stage 4 output has no exception flows.

Assert:

- resulting `FlowStructureIR.exception_flows` contains one flow;
- condition text equals source span text;
- spans include `s_failure`;
- no handler/block/step is created.

### Test 2: Existing LLM Exception Dedupe

Input:

- LLM Stage 4 output already includes an exception flow with same condition text;
- route annotation targets the same condition.

Assert:

- only one exception flow remains.

### Test 3: Bridge Fallback Still Works Without Annotations

Input:

- no route annotations;
- hard-fact failure modes exist as before.

Assert:

- bridge fallback still creates condition-only partial exception flow.

### Test 4: Route + Bridge Does Not Duplicate

Input:

- both route annotation and hard fact represent the same failure condition.

Assert:

- final flow has one exception flow for that condition.

### Test 5: Non-Failure Annotation Ignored

Input:

- annotation has `construct_target=EXCEPTION_FLOW` but wrong
  `semantic_role`, or `executable=True`.

Assert:

- no route-derived exception flow is created.

### Test 6: Stage 4 Baseline Process Flow Still Works

Existing flow assembler tests for normal main flow must still pass.

## Acceptance Criteria

D2 is complete when:

- Stage 4 materializes condition-only exception flows from route annotations;
- materialization uses annotation semantics, not raw `routes.rules`;
- route-derived exception flows preserve source span ids;
- no handler blocks or handler steps are fabricated;
- LLM-generated and route-derived exception flows are deduped by condition text;
- bridge fallback still works when annotations are absent;
- route + bridge path does not duplicate failure modes;
- no Stage 7 executable filtering is mixed into this phase;
- no bridge deletion occurs;
- relevant Stage 4 / bridge / orchestrator tests and full unit suite pass.

## Required Evidence For Review

When submitting D2 for review, provide:

1. changed files;
2. exact test commands and output summary;
3. sample route annotation that materializes an `ExceptionFlow`;
4. sample resulting `ExceptionFlow`;
5. confirmation that no handler step/block is created;
6. confirmation that bridge fallback still works;
7. confirmation that Stage 7 and bridge deletion were not touched.

## PM Review Checklist

- [ ] Route annotations drive Stage 4 exception materialization.
- [ ] Failure condition span ids are preserved.
- [ ] Existing LLM exception flows dedupe with route-derived ones.
- [ ] Bridge fallback remains intact.
- [ ] Route + bridge path does not duplicate exceptions.
- [ ] No handler fabrication.
- [ ] No Stage 7 filtering or bridge deletion is mixed in.
