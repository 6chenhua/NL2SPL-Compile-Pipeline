# Task D6: StepExtractor Executable Filtering

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0, D1, and D2 approved.

Related docs:

- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/tasks/D2_flow_assembler_route_driven_exception_materialization.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Prevent non-executable route material from becoming Stage 7 steps.

D2 materializes `failure_mode` annotations into condition-only
`ExceptionFlow` skeletons. D6 must ensure those same spans do not also become
commands such as:

```text
GENERAL_COMMAND: Handle missing timeframe
```

Stage 7 must treat route annotations with `executable=False` as contextual
flow material, not executable step candidates.

## Scope

In scope:

- use route annotation helpers in Stage 7 prompt/input preparation;
- exclude non-executable behavior spans from step extraction candidates;
- preserve non-executable spans as context where useful;
- keep existing behavior when annotations are absent;
- apply the same rule to worker-scoped Stage 7;
- update unmapped-behavior diagnostics so excluded non-executable spans do not
  create false missing-step warnings;
- keep handoff-generated `INVOKE_WORKER` / `CALL_API` contract-driven.

Out of scope:

- changing Stage 4 exception materialization;
- deleting failure-mode bridge code;
- changing block assembly or renderer behavior;
- worker-aware exception ownership migration;
- adding synthetic handlers for exception flows.

## Affected Files

Expected production areas:

- `src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py`
- prompt/context helpers used by Stage 7, if split into separate modules

Expected tests:

- `tests/unit/test_step_extractor.py`
- `tests/unit/pipeline/stages/test_stage7_worker_scoped.py`
- Stage 7 IRS tests if diagnostics are affected
- integration-style pipeline test if needed to prove D2+D6 interaction

## Required Implementation

### 1. Candidate Span Selection

When `FieldRouteIR.annotations` exist, Stage 7 must derive executable behavior
candidate span ids from:

```python
routes.get_executable_behavior_span_ids()
```

Only those spans should be eligible to become extracted steps.

When no annotations exist, preserve legacy behavior:

```python
routes.behavior
```

Do not hand-roll filtering logic in multiple places if a local helper can keep
legacy and worker-scoped paths consistent.

### 2. Non-Executable Context

Non-executable behavior-like spans may be included in prompt context, but they
must be clearly separated from executable candidates.

The prompt/context contract should communicate:

```text
Non-executable context only; do not create COMMAND / REQUEST_INPUT /
INVOKE_WORKER / CALL_API steps from these spans.
```

This matters for:

- `failure_mode`;
- `delegation_intent` without an accepted worker/API contract;
- route annotations explicitly marked `executable=False`.

### 3. Step Post-Processing Guard

Add a deterministic guard after LLM step extraction:

- if a returned step is sourced only from non-executable span ids, reject it or
  drop it with a diagnostic/warning;
- if a returned step mixes executable and non-executable span ids, keep the
  step only if at least one executable source span justifies it, and remove or
  ignore non-executable-only provenance according to existing IR conventions;
- never generate a command whose only source is a `failure_mode` condition.

The guard is required because prompt separation alone is not sufficient.

### 4. Diagnostics

Do not emit ordinary "unmapped behavior span" diagnostics for spans excluded
because they are non-executable route material.

If a diagnostic is needed, use a specific reason such as:

```text
non_executable_route_material_excluded
```

The diagnostic should be informational or warning-level only if existing
diagnostic structures support that distinction. Do not treat excluded failure
conditions as missing commands.

### 5. Worker-Scoped Stage 7

Worker-scoped Stage 7 must apply the same filtering rule inside each worker:

- executable candidate ids are the intersection of worker-owned span ids and
  `routes.get_executable_behavior_span_ids()`;
- non-executable owned spans are context only;
- child workers must not receive commands sourced only from failure conditions
  or delegation boundaries.

If worker ownership does not include a non-executable exception condition, D6
should not try to fix ownership. That belongs to D3.

### 6. Handoff And API Contracts

Do not break contract-driven handoff behavior:

- accepted worker handoffs may still produce `INVOKE_WORKER` when the worker
  plan contract exists;
- accepted API handoffs may still produce `CALL_API` when the API contract
  exists;
- delegation intent text alone must not become an executable invocation.

### 7. REQUEST_INPUT Guard

`REQUEST_INPUT` should only be generated from explicit request/ask evidence,
not from a failure condition label alone.

Example:

```text
Missing timeframe
```

is an exception condition candidate, not a user-input request step by itself.

## Required Tests

### Test 1: Failure Mode Does Not Become Command

Input:

- `routes.behavior` includes `s_failure`;
- `routes.annotations` marks `s_failure` as:
  - `semantic_role="failure_mode"`;
  - `construct_target="EXCEPTION_FLOW"`;
  - `slot_target="condition"`;
  - `executable=False`;
- LLM returns a `GENERAL_COMMAND` sourced only from `s_failure`.

Assert:

- returned steps do not include the command;
- no ordinary unmapped-behavior error is emitted for `s_failure`;
- a clear warning/diagnostic is recorded if the implementation records drops.

### Test 2: Process Step Still Becomes Command

Input:

- one executable `process_step` annotation;
- one non-executable `failure_mode` annotation.

Assert:

- executable process step remains eligible and can become a step;
- failure condition does not become a step.

### Test 3: No Annotation Fallback Preserves Legacy Behavior

Input:

- `FieldRouteIR(behavior=[...])`;
- no annotations.

Assert:

- Stage 7 behavior matches pre-D6 candidate selection.

### Test 4: Delegation Intent Without Contract Is Not Invocation

Input:

- delegation-like span with `semantic_role="delegation_intent"`;
- `route_family="delegation_boundary"` or equivalent;
- `executable=False`;
- no worker handoff/API contract.

Assert:

- no `INVOKE_WORKER`;
- no `CALL_API`;
- no general command from the delegation policy text alone.

### Test 5: Contract-Backed Handoff Still Works

Input:

- accepted worker/API handoff contract exists through current IR path;
- source spans include executable contract-backed material.

Assert:

- existing handoff-generated step behavior is preserved.

### Test 6: Worker-Scoped Filtering

Input:

- worker-scoped Stage 7;
- worker owns both an executable process span and a non-executable failure span.

Assert:

- worker step plan contains steps only for executable spans;
- failure condition is not emitted as a worker command.

### Test 7: REQUEST_INPUT Is Not Fabricated From Failure Label

Input:

- failure text such as `Missing timeframe`;
- no explicit ask/request action.

Assert:

- no `REQUEST_INPUT` step is generated from that span alone.

## Acceptance Criteria

D6 is complete when:

- Stage 7 uses route helper semantics for executable candidate selection;
- no non-executable `failure_mode` span becomes `GENERAL_COMMAND`;
- no delegation boundary without contract becomes `INVOKE_WORKER` or `CALL_API`;
- normal executable process steps still extract as before;
- no-annotation fallback preserves old behavior;
- worker-scoped Stage 7 applies the same filter;
- false unmapped-behavior diagnostics for excluded non-executable material are
  removed or replaced with specific non-executable exclusion diagnostics;
- no Stage 4, bridge deletion, renderer, or normalizer migration is mixed into
  this phase;
- focused Stage 7 tests and the full unit suite pass.

## Required Evidence For Review

When submitting D6 for review, provide:

1. changed files;
2. exact test commands and output summary;
3. sample route annotations for executable and non-executable behavior spans;
4. before/after Stage 7 candidate span ids;
5. example proving `Missing timeframe` is not emitted as a command;
6. example proving normal process steps still emit;
7. confirmation that Stage 4, bridge deletion, renderer, and normalizer were
   not changed.

## PM Review Checklist

- [ ] Stage 7 candidate source uses `get_executable_behavior_span_ids()`.
- [ ] Non-executable spans are not source-only commands.
- [ ] Prompt/context separation is tested, not only implementation helpers.
- [ ] Post-processing guard is tested against bad LLM output.
- [ ] Worker-scoped Stage 7 follows the same rule.
- [ ] No-annotation fallback remains compatible.
- [ ] Contract-backed handoffs still work.
- [ ] Full unit suite passes.
