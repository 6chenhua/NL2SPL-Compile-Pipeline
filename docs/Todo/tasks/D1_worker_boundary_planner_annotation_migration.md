# Task D1: WorkerBoundaryPlanner Annotation Migration

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0 Downstream Baseline approved.

Related docs:

- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/tasks/D0_downstream_baseline_and_route_helper_adoption.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Prevent non-executable route material from becoming worker task candidates.

D1 migrates Stage 3.5 WorkerBoundaryPlanner to respect `RouteAnnotation`
semantics while preserving old-list fallback behavior when annotations are
absent.

## Scope

In scope:

- candidate extraction should prefer executable behavior annotations;
- failure-mode annotations should be available as flow context, not worker task
  units;
- delegation intent annotations should inform boundary/context, but must not
  create executable child workers unless a valid handoff contract exists;
- prompt context may include non-executable route material as contextual
  evidence;
- old behavior list fallback must remain when annotations are absent;
- add focused tests for annotated structural routes.

Out of scope:

- Stage 4 route-driven exception materialization;
- Stage 7 executable filtering;
- bridge deletion;
- renderer or normalizer changes;
- changing final worker assembly outside Stage 3.5.

## Affected Files

Expected production files:

- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py`
- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/prompt_builder.py`
- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/materializer.py`

Expected test file:

- `tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py`

## Required Implementation

## 1. Candidate Extraction Uses Executable Behavior

Where candidate extraction currently reads `routes.behavior`, introduce a helper
path:

```python
behavior_candidate_ids = routes.get_executable_behavior_span_ids()
```

Fallback requirement:

- when `routes.annotations == []`, helper output must equal old
  `routes.behavior`;
- existing worker planner tests must still pass.

Do not include annotation-only non-executable behavior spans as candidate task
units.

## 2. Non-Executable Context Is Still Visible

Failure modes and delegation boundaries should not disappear. They should be
available to prompt/context builders as non-executable context.

Use helpers such as:

```python
routes.get_non_executable_behavior_span_ids()
routes.get_annotations_by_role("failure_mode")
routes.get_annotations_by_role("delegation_intent")
```

Context rules:

- `failure_mode` should be described as exception condition / flow context;
- `delegation_intent` should be described as delegation boundary material;
- neither should be described as a task unit to extract.

## 3. Materializer Guards Accepted Candidates

If the LLM or legacy path returns an accepted worker candidate whose span ids are
only non-executable route material, the materializer or validation layer must
reject or downgrade it.

Expected behavior:

- no child worker for pure `failure_mode`;
- no child worker for pure `delegation_intent` unless a valid handoff contract
  and executable task span exist;
- mixed candidates may proceed only if they contain at least one executable
  behavior span.

## 4. Preserve Legacy Behavior Without Annotations

When `FieldRouteIR.annotations` is empty:

- behavior should match D0 baseline;
- existing tests using only `routes.behavior` should not need semantic rewrites.

## Required Tests

Add or update tests in:

- `tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py`

### Test 1: Failure Mode Not Candidate

Input:

- `routes.behavior` includes a failure-mode span and a process-step span;
- annotations mark failure mode `executable=False` and process step
  `executable=True`.

Assert:

- candidate extraction/prompt candidate list excludes failure-mode span;
- process step remains candidate material.

### Test 2: Delegation Intent Without Contract Not Candidate

Input:

- `routes.behavior` includes a delegation policy span;
- annotation marks it `semantic_role="delegation_intent"`,
  `route_family="delegation_boundary"`, `executable=False`.

Assert:

- no accepted child worker is produced from that span alone;
- if rejected candidate/diagnostic exists, it identifies missing contract or
  non-executable boundary material.

### Test 3: Mixed Candidate Requires Executable Span

Input:

- candidate spans include one executable process step and one non-executable
  delegation/failure span.

Assert:

- candidate can still be considered only because executable span exists;
- non-executable span is context, not the task anchor.

### Test 4: Fallback Without Annotations

Input:

- old `FieldRouteIR(behavior=[...])`, no annotations.

Assert:

- worker planner behavior matches existing baseline.

### Test 5: Prompt Mentions Non-Executable Context Separately

If prompt builder is touched, assert the prompt separates:

- executable candidate task units;
- failure condition context;
- delegation boundary context.

Do not assert exact full prompt text; assert stable labels or key phrases.

## Acceptance Criteria

D1 is complete when:

- WorkerBoundaryPlanner does not propose pure failure-mode spans as worker task
  candidates;
- delegation intent without executable task/contract does not produce a child
  worker;
- executable process steps remain candidate material;
- mixed candidates are handled conservatively;
- prompt/context builder preserves non-executable route context;
- old no-annotation behavior remains compatible;
- D0 tests still pass;
- full unit suite passes.

## Required Evidence For Review

When submitting D1 for review, provide:

1. changed files;
2. exact test commands and output summary;
3. before/after summary for candidate extraction input ids;
4. sample failure-mode annotation excluded from worker candidate list;
5. sample delegation annotation treated as boundary context;
6. confirmation that no Stage 4/7/bridge/orchestrator code changed.

## PM Review Checklist

- [ ] Pure failure-mode spans are not worker task candidates.
- [ ] Pure delegation-boundary spans do not create child workers.
- [ ] Executable process spans still work.
- [ ] Annotation absence preserves old behavior.
- [ ] Prompt/context does not drop non-executable material.
- [ ] No D2/D6 bridge or step-extractor migration is mixed in.
