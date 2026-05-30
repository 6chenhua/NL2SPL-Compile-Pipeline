# Task D0: Downstream Baseline and Route Helper Adoption

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- `FieldRouteIR` has `RouteAnnotation` and helper methods.
- Stage 2 emits annotations for structural NL.
- Stage 3 preserves annotations across ambiguity resolution.

Related docs:

- `docs/Todo/route_contract_refactor_00_readme.md`
- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/tasks/F4_annotation_aware_ambiguity_resolver.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Prepare downstream stages for annotation-driven migration without changing
runtime behavior.

D0 is a baseline and low-risk helper-adoption phase. It must not materialize
exception flows from annotations yet, must not delete bridges, and must not
change command generation semantics.

## Scope

In scope:

- add downstream baseline tests that document current behavior;
- introduce or use helper calls in Stage 4 and Stage 7 only where behavior is
  identical under current routes;
- verify annotation-bearing `FieldRouteIR` objects do not break downstream
  stages;
- document current bridge-first failure behavior as baseline;
- keep old route-list fallback behavior intact.

Out of scope:

- route-driven exception materialization;
- changing `bridge_failure_modes()` behavior;
- changing orchestrator bridge calls;
- excluding failure/delegation behavior spans from Stage 7 prompts when that
  would change current behavior;
- worker planner migration;
- renderer or normalizer changes.

## Affected Areas

Primary code areas to inspect:

- `src/nl2spl/pipeline/stages/stage4_flow_assembler/`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/`
- `src/nl2spl/pipeline/fact_bridges.py`
- `src/nl2spl/pipeline/orchestrator.py`

Primary tests to extend or reference:

- `tests/unit/test_flow_assembler.py`
- `tests/unit/test_stage4_irs_exception_flow.py`
- `tests/unit/test_step_extractor.py`
- `tests/unit/test_stage7_irs_step_extraction.py`
- `tests/unit/test_failure_mode_bridge.py`
- `tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py`
- `tests/unit/pipeline/stages/test_worker_aware_flow_assembler.py`

## Required Baseline Tests

### Test 1: Stage 4 Ignores Annotations For Now

Create a `FieldRouteIR` with:

- old route lists matching an existing Stage 4 test;
- annotations including a failure-mode
  `EXCEPTION_FLOW.condition` candidate.

Assert current Stage 4 output is unchanged compared with old-list-only input.

This documents that D2, not D0, will make Stage 4 materialize route-derived
exception flows.

### Test 2: Bridge-First Failure Materialization Is Still Baseline

Extend or add a focused test around `bridge_failure_modes()` or the orchestrator
path.

Assert:

- hard-fact failure modes still bridge into partial exception flows;
- annotations are not yet the primary production mechanism;
- no duplicate exception flow appears when both hard facts and annotations are
  present.

If duplicate behavior already exists, document it as a D2 bug target rather than
silently changing D0 behavior.

### Test 3: Stage 7 Old Behavior Is Preserved With Annotations Present

Create a Stage 7 input where:

- `routes.behavior` contains normal process spans;
- `routes.annotations` marks those same spans executable.

Assert Stage 7 output matches the old behavior.

Do not yet add a test that expects failure-mode or delegation annotations to be
filtered out. That belongs to D6 unless the current implementation already does
it without behavior change.

### Test 4: Route Helper Fallback Is Safe

Add focused tests for downstream-compatible helper use:

- `routes.get_executable_behavior_span_ids()` returns old `routes.behavior`
  when annotations are absent;
- when annotations are present and match old behavior, helper output equals the
  old behavior list;
- non-executable annotations are visible through
  `get_non_executable_behavior_span_ids()` but are not consumed by downstream
  stages yet.

If these are already covered in F2 tests, reference those tests in the review
evidence and add only downstream integration coverage.

### Test 5: Worker Planner Baseline

Add or extend a worker boundary planner baseline test showing current behavior
when route annotations are present.

Assert:

- existing worker planner tests still pass;
- annotations do not crash prompt construction or materialization;
- no new worker boundary behavior is introduced in D0.

D1 will change worker candidate extraction.

## Optional Low-Risk Code Changes

You may update stage internals to call route helper methods only when the return
value is behavior-identical today.

Allowed examples:

```python
behavior_span_ids = routes.get_executable_behavior_span_ids()
```

only if the input has no annotations or annotations exactly mirror old behavior.

Do not switch Stage 7 production paths to exclude non-executable failure or
delegation spans in D0. That is D6.

Do not switch Stage 4 production paths to use
`get_construct_slot_candidates("EXCEPTION_FLOW", "condition")` for
materialization in D0. That is D2.

## Acceptance Criteria

D0 is complete when:

- baseline tests document current Stage 4, Stage 7, bridge, and worker planner
  behavior with annotations present;
- Stage 4 and Stage 7 either use helpers only in behavior-identical paths or
  remain unchanged with explicit baseline tests;
- all existing legacy tests pass;
- no route-driven exception materialization has been added;
- no bridge deletion or orchestrator migration has been performed;
- no worker planner behavior has changed;
- full unit test suite passes.

## Required Evidence For Review

When submitting D0 for review, provide:

1. changed files;
2. exact test commands and output summary;
3. baseline sample showing Stage 4 behavior with failure annotations present;
4. baseline sample showing Stage 7 behavior with executable annotations present;
5. confirmation that bridge-first failure behavior is unchanged;
6. confirmation that Stage 4/7 behavior did not semantically change;
7. confirmation that D1/D2/D6 behavior was not implemented early.

## PM Review Checklist

- [ ] D0 is baseline-focused, not migration-by-stealth.
- [ ] Stage 4 does not materialize annotation-derived exception flows yet.
- [ ] Stage 7 does not filter non-executable route material yet unless behavior
      was already identical.
- [ ] Bridge-first behavior remains intact and documented.
- [ ] Worker planner behavior remains unchanged.
- [ ] Annotation-bearing routes do not crash downstream stages.
- [ ] Tests are specific enough to catch accidental D2/D6 behavior changes.
- [ ] Full unit suite passes.
