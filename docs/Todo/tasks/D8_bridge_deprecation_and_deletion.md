# Task D8: Bridge Deprecation and Production Path Cleanup

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0 through D7 approved.

Related docs:

- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/input_adapter_fieldroute_semantic_routing_refactor_todo.md`
- `docs/Todo/tasks/D2_flow_assembler_route_driven_exception_materialization.md`
- `docs/Todo/tasks/D3_worker_aware_exception_flow_migration.md`
- `docs/Todo/tasks/D5_resource_profile_constraint_consumers.md`
- `docs/Todo/tasks/D7_normalizer_gate_renderer_provenance.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Remove bridge-first semantics from production paths now that route annotations
drive downstream behavior.

The target architecture is:

```text
adapter evidence / hard facts
-> FieldRoute annotations
-> route-driven stage materialization
-> diagnostics / provenance / reports
```

not:

```text
adapter hard facts
-> post-Stage-4 bridge mutation
-> downstream partial IR
```

D8 should make bridge functions compatibility-only. They may remain temporarily
as wrappers for no-annotation or legacy tests, but production behavior must no
longer depend on bridge-first materialization.

## Scope

In scope:

- `bridge_failure_modes()`;
- `bridge_failure_modes_worker_scoped()`;
- `bridge_delegation_intents()`;
- `PipelineOrchestrator` call sites for failure-mode and delegation bridges;
- bridge-focused tests and orchestrator-focused regression tests;
- deprecation comments or compatibility wrapper documentation.

Out of scope:

- changing InputAdapter packet extraction;
- changing FieldRouter annotation generation;
- changing Stage 4 route materialization semantics;
- changing Stage 7 executable filtering;
- changing renderer syntax;
- deleting hard facts from `CanonicalCompileInput`;
- fabricating exception handlers or delegation workers.

## Affected Files

Expected production areas:

- `src/nl2spl/pipeline/fact_bridges.py`
- `src/nl2spl/pipeline/orchestrator.py`

Expected tests:

- `tests/unit/test_failure_mode_bridge.py`
- `tests/unit/test_flow_assembler.py`
- `tests/unit/test_input_adapter_pipeline.py`
- `tests/unit/test_diagnostic_consolidation.py`
- `tests/unit/test_feedback_report_renderer.py`
- worker-aware tests under `tests/unit/pipeline/stages/`
- integration tests only if existing bridge-first assertions require updates

## Required Implementation

### 1. Characterize Current Bridge Call Sites

Before production edits, add or update characterization tests that prove:

- Stage 4 route annotations already create failure-mode `ExceptionFlow`
  skeletons in legacy mode;
- worker-aware Stage 4 route annotations already create worker-local
  `ExceptionFlow` skeletons;
- route + hard facts do not duplicate failure conditions;
- hard-fact-only fallback still works when annotations are absent;
- delegation intent diagnostics still appear for non-executable delegation
  intent without a valid handoff contract.

Do not start by deleting bridge functions.

### 2. Failure Mode Bridge Compatibility Wrapper

Convert failure-mode bridges from primary materializers into compatibility
fallbacks.

Required behavior:

- when route-derived exception flows already exist, bridge fallback must be a
  no-op;
- when route annotations are absent but hard-fact failure modes exist, fallback
  may still create condition-only `ExceptionFlow` skeletons;
- fallback must reuse the same condition normalization and span provenance rules
  as route-driven materialization;
- fallback must not create handler blocks or handler steps;
- fallback must not mutate input IR objects.

Preferred direction:

- keep `materialize_route_exception_flows()` as the canonical materializer for
  route annotations;
- mark `bridge_failure_modes()` and `bridge_failure_modes_worker_scoped()` as
  compatibility fallback wrappers;
- if useful, factor common dedupe/span-resolution helpers, but do not broaden
  the refactor beyond bridge cleanup.

### 3. Orchestrator Failure Bridge Call Site

The orchestrator must stop behaving as bridge-first.

Required behavior:

- in the normal structural-NL route-annotated path, Stage 4 route materialization
  is the only primary source of failure-mode exception flows;
- hard-fact bridge fallback runs only when annotations did not produce failure
  exception flows;
- fallback skip/fallback decision is deterministic and test-covered;
- legacy and worker-aware orchestrator paths both avoid duplicate exception
  flows when annotations and hard facts coexist;
- `intermediate_results` should make the decision auditable if a simple marker
  already fits the project style.

Do not remove `canonical_input.hard_facts.failure_modes`; they remain evidence,
diagnostic, and fallback material.

### 4. Delegation Intent Bridge Cleanup

`bridge_delegation_intents()` currently emits diagnostics from hard facts. D8
should reduce it to a compatibility diagnostic helper or replace production use
with route-driven delegation diagnostics.

Required behavior:

- pure delegation intent without executable contract still produces a
  `type_or_contract_ambiguity` diagnostic;
- valid handoff contracts suppress the diagnostic;
- delegation boundary rules that are actual constraints remain handled by Stage
  9, not by bridge diagnostics;
- route annotations and provenance should be preferred where available;
- no invalid `INVOKE_WORKER` or `CALL_API` is rendered.

If full delegation bridge deletion is too large, keep the helper but mark it as
compatibility-only and make orchestrator use it only for annotation-missing or
legacy evidence paths. Do not leave an unguarded hard-fact primary diagnostic
path.

### 5. Tests To Migrate

Bridge tests should no longer describe bridge-first behavior as the expected
production path.

Update tests so the new contract is clear:

- route-driven materializer tests are canonical;
- bridge tests are fallback compatibility tests;
- old comments like "bridge remains the primary production path" must be
  deleted or rewritten;
- integration tests that explicitly call bridge helpers may remain, but their
  wording must identify them as compatibility helper tests.

## Required Tests

### Test 1: Route Path Does Not Need Failure Bridge

Input:

- structural NL or direct route fixture with `failure_mode` annotation and hard
  fact failure mode both present.

Assert:

- Stage 4 / orchestrator output contains one route-derived `ExceptionFlow`;
- no second bridge-derived exception is added;
- condition span id is preserved;
- missing-handler diagnostic still appears downstream.

### Test 2: Failure Bridge Fallback Without Annotations

Input:

- hard-fact failure modes exist;
- routes have no `EXCEPTION_FLOW.condition` failure annotations.

Assert:

- fallback creates one condition-only exception flow;
- no handler block or step is created;
- provenance and missing-handler diagnostics remain available;
- bridge function is documented as compatibility fallback.

### Test 3: Worker-Aware Route Path Does Not Need Failure Bridge

Input:

- worker-aware pipeline with failure condition annotation owned by a child
  worker, plus matching hard fact.

Assert:

- child worker receives one exception flow;
- main worker does not receive a duplicate fallback exception;
- bridge fallback is skipped or deduped deterministically;
- renderer/provenance remain correct.

### Test 4: Worker-Aware Failure Fallback Without Annotations

Input:

- worker-aware pipeline with hard-fact failure mode but no route annotation.

Assert:

- compatibility fallback still attaches condition-only exception flow to the
  deterministic fallback worker, currently main worker unless ownership evidence
  says otherwise;
- warning behavior remains deterministic when ownership is unavailable;
- no duplicate condition appears across workers.

### Test 5: Delegation Diagnostic Route Preference

Input:

- `delegation_intent` annotation / hard fact without valid handoff contract.

Assert:

- exactly one `type_or_contract_ambiguity` diagnostic appears;
- diagnostic source spans and section/packet evidence are preserved where
  available;
- no executable worker/API invocation is fabricated.

### Test 6: Valid Handoff Suppresses Delegation Diagnostic

Input:

- delegation intent evidence plus a valid `WorkerHandoffIR`.

Assert:

- no bridge-style ambiguity diagnostic is emitted;
- handoff remains renderable only if it has valid target and IO/API contract.

### Test 7: No Bridge-First Wording Or Primary Call Sites

Assert by code search or focused tests:

- no test or doc newly claims bridge is the primary production path;
- `PipelineOrchestrator` does not unconditionally call failure bridge after
  Stage 4 route materialization;
- any remaining bridge call is guarded compatibility fallback;
- bridge wrappers contain deprecation or compatibility comments.

## Acceptance Criteria

D8 is complete when:

- route-derived exception materialization is the canonical production path;
- bridge failure functions are compatibility fallback wrappers, not primary
  materializers;
- orchestrator failure bridge calls are guarded or removed;
- no annotation-bearing route path depends on hard-fact bridge-first behavior;
- hard-fact-only fallback still works when annotations are absent;
- worker-aware route + hard facts do not duplicate failure conditions;
- delegation-intent diagnostics are route-preferred or compatibility-guarded;
- valid handoffs suppress delegation ambiguity diagnostics;
- reports, diagnostics, provenance, and renderer behavior from D7 remain green;
- focused D8 tests and full unit suite pass;
- bridge deletion is only performed if all compatibility tests have equivalent
  route-driven coverage.

## Required Evidence For Review

When submitting D8, provide:

1. changed files;
2. exact test commands and output summary;
3. before/after summary of orchestrator bridge call sites;
4. sample route-derived failure path showing no bridge duplicate;
5. sample hard-fact-only fallback path showing compatibility still works;
6. worker-aware route + bridge coexistence result;
7. delegation diagnostic result for no valid handoff;
8. valid handoff suppression result;
9. `rg` evidence for remaining bridge call sites and comments;
10. confirmation that FieldRouter, Stage 4 materialization semantics, Stage 7
    filtering, D7 renderer/provenance behavior were not mixed into this phase.

## PM Review Checklist

- [ ] Failure bridge is not the primary production path.
- [ ] Route-derived exception flows are not duplicated by hard-fact fallback.
- [ ] Hard-fact-only fallback remains available when annotations are absent.
- [ ] Worker-aware route path does not duplicate exceptions across workers.
- [ ] Delegation diagnostics are not emitted twice.
- [ ] Valid handoff suppresses delegation ambiguity.
- [ ] Bridge-focused tests now describe compatibility behavior.
- [ ] No handler block or command is fabricated.
- [ ] D7 diagnostics/provenance/report behavior remains intact.
- [ ] Full unit suite passes.
