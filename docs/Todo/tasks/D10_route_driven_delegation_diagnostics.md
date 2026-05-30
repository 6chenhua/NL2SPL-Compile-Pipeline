# Task D10: Route-Driven Delegation Diagnostics

Date assigned: 2026-05-22

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0 through D9 approved.
- `bridge_delegation_intents()` is still active as a compatibility diagnostic
  helper.

Related docs:

- `docs/Todo/input_adapter_fieldroute_semantic_routing_refactor_todo.md`
- `docs/Todo/tasks/D8_bridge_deprecation_and_deletion.md`
- `docs/Todo/tasks/D9_documentation_migration_cleanup.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Move delegation-intent ambiguity diagnostics from hard-fact bridge scanning to
route annotation evidence.

The target path is:

```text
InputAdapter delegation packet / hint
-> FieldRoute RouteAnnotation(semantic_role="delegation_intent")
-> route-driven delegation diagnostic analyzer
-> consolidated type_or_contract_ambiguity diagnostic
```

not:

```text
hard_facts.delegation_intents
-> bridge_delegation_intents()
-> diagnostic
```

This phase should not delete `bridge_delegation_intents()` outright. It should
make route annotations the preferred diagnostic source and keep the bridge only
as a compatibility fallback for inputs that do not yet have delegation
annotations.

## Current State

The approved D8 state is:

- failure bridges are condition-coverage guarded fallback paths;
- `bridge_delegation_intents()` remains active;
- delegation diagnostics are still bridge-driven;
- valid handoff suppression is implemented in the bridge helper;
- pure delegation intent without a valid handoff still produces
  `type_or_contract_ambiguity`.

D10 must close this residual gap.

## Scope

In scope:

- route-driven diagnostics for `RouteAnnotation.semantic_role == "delegation_intent"`;
- preservation of span, section, packet, and hint provenance in diagnostics;
- valid handoff suppression for route-derived delegation diagnostics;
- dedupe between route-derived diagnostics and legacy bridge diagnostics;
- worker-aware and non-worker-aware orchestrator paths;
- tests proving the bridge is skipped or fallback-only when route evidence
  covers delegation diagnostics.

Out of scope:

- deleting `bridge_delegation_intents()`;
- changing worker boundary planning semantics;
- fabricating child workers from delegation intent;
- turning delegation policy/boundary text into executable steps;
- changing failure-mode exception-flow behavior.

## Required Design

### 1. Add Baseline Tests First

Before production changes, add tests that lock current behavior:

- pure structural delegation intent currently produces exactly one
  `type_or_contract_ambiguity`;
- valid handoff suppresses that diagnostic;
- constraint-like delegation boundary rules still survive Stage 9 when they are
  real rules;
- non-delegation annotations do not affect delegation diagnostics;
- diagnostics include source evidence where currently available.

These baseline tests should document which behavior is legacy and which behavior
is the target.

### 2. Introduce Route-Driven Analyzer

Add a small route-driven analyzer rather than embedding delegation logic inside
the orchestrator body.

Suggested location:

```text
src/nl2spl/pipeline/delegation_diagnostics.py
```

Expected function shape:

```python
def diagnose_delegation_intents_from_routes(
    routes: FieldRouteIR,
    spans: list[SpanIR],
    worker_plan: WorkerPlanIR | None = None,
) -> list[CompileDiagnostic]:
    ...
```

The exact signature may vary if existing diagnostic helpers require additional
context, but the analyzer must remain route-first and testable in isolation.

### 3. Evidence Contract

For each route-derived diagnostic:

- `kind` must be `type_or_contract_ambiguity`;
- `source_span_ids` must include the delegation annotation span id;
- `target_ref` should be stable and specific enough for dedupe, for example
  `delegation_intent:<span_id>` or a matching existing convention;
- message text must explain that delegation intent lacks a valid worker/API
  handoff contract;
- diagnostic metadata or evidence must preserve available provenance:
  `source_section_id`, `source_packet_id`, and `source_hint_ids` when present.

Do not invent handoff contracts, workers, APIs, or outputs.

### 4. Valid Handoff Suppression

Route-derived delegation diagnostics must be suppressed when a valid handoff
contract already covers the delegation intent.

Minimum acceptable coverage:

- `WorkerPlanIR.handoffs` contains a valid invoke/API handoff linked to the
  delegation span through `source_span_ids`, owned span ids, or an existing
  project-local association;
- handoff target exists and has required input/output/API contract fields
  according to the existing validation model;
- suppression should not hide unrelated delegation annotations.

If the project does not yet expose a direct span-to-handoff association, choose
the most conservative existing local contract and document it in tests.

### 5. Orchestrator Integration

The orchestrator should prefer route-derived delegation diagnostics:

```text
if routes contain delegation_intent annotations:
    emit route-derived delegation diagnostics
    use bridge_delegation_intents() only for uncovered legacy hard facts, or skip
    it entirely if route coverage is complete
else:
    keep bridge_delegation_intents() fallback behavior
```

This must be implemented with an explicit guard/helper, not a broad
`if routes.annotations` check.

The guard must be role-specific:

```text
delegation_intent annotations affect delegation bridge fallback;
failure/profile/resource/process annotations must not suppress delegation
fallback.
```

### 6. Deduplication

Route-derived diagnostics and bridge-derived diagnostics must not duplicate each
other.

Required behavior:

- route-derived diagnostic only -> exactly one diagnostic;
- bridge fallback only -> exactly one diagnostic;
- route + hard fact for same delegation span/text -> exactly one diagnostic;
- unrelated route delegation annotation + hard fact -> both may produce separate
  diagnostics if they refer to distinct unresolved delegation intents;
- valid handoff suppresses the matching diagnostic only.

### 7. Stage 9 Boundary Safety

D10 must not regress D5:

- pure `delegation_intent` remains excluded from constraint extraction;
- delegation boundary rules that are genuine constraints still survive;
- route-driven delegation diagnostics must not cause Stage 9 to reclassify pure
  delegation intent as a policy rule.

### 8. Reporting And Provenance

Readable reports should show route-derived delegation ambiguity with the same or
better evidence than the bridge path:

- delegation condition/text;
- span id;
- section id when available;
- packet id when available;
- concise diagnostic reason.

Do not add duplicate report entries after diagnostic consolidation.

## Acceptance Criteria

D10 is accepted only when all criteria are met:

- baseline tests prove current bridge-driven delegation diagnostics before the
  production migration;
- route-derived analyzer emits `type_or_contract_ambiguity` from
  `delegation_intent` annotations;
- route-derived diagnostics include span/section/packet provenance;
- valid handoff suppresses the matching route-derived diagnostic;
- bridge fallback still works when no delegation annotations exist;
- bridge fallback is not invoked, or is deduped to no-op, when route evidence
  fully covers delegation diagnostics;
- non-delegation annotations do not suppress delegation fallback;
- route + hard fact for the same unresolved delegation intent yields exactly one
  final diagnostic;
- Stage 9 delegation boundary behavior remains unchanged;
- worker-aware path is covered by at least one route-derived test;
- full unit suite passes.

## Required Tests

Add or update focused tests in the most local files possible.

Required test groups:

1. Analyzer unit tests:
   - pure delegation annotation -> diagnostic;
   - valid handoff -> suppressed;
   - unrelated handoff -> diagnostic remains;
   - provenance copied from annotation.

2. Orchestrator integration tests:
   - structural NL delegation packet -> route-derived diagnostic;
   - route + hard fact duplicate -> exactly one final diagnostic;
   - no route annotations -> bridge fallback still emits;
   - non-delegation annotation does not suppress bridge fallback.

3. Worker-aware tests:
   - worker plan with valid handoff suppresses route-derived diagnostic;
   - missing/invalid handoff produces route-derived diagnostic.

4. Regression tests:
   - D5 Stage 9 pure delegation exclusion still holds;
   - delegation boundary constraint still survives;
   - D6 delegation intent still does not become `INVOKE_WORKER`.

## Required Evidence In Submission

When submitting D10, include:

1. changed files;
2. new analyzer API and where it is called;
3. before/after diagnostic flow for:
   - pure delegation intent;
   - valid handoff suppression;
   - route + hard fact duplicate;
4. bridge fallback guard behavior;
5. exact pytest commands and results;
6. confirmation that `bridge_delegation_intents()` remains fallback-only and is
   not deleted in D10;
7. remaining D11 deletion prerequisites, if any.

## Review Notes

Likely rejection issues:

- broad guard such as `if routes.annotations` suppressing delegation bridge;
- diagnostic without span/section/packet provenance;
- route-derived and bridge-derived duplicate diagnostics;
- treating delegation intent as executable behavior;
- deleting `bridge_delegation_intents()` before route-driven behavior has full
  parity;
- only testing analyzer units without orchestrator integration;
- skipping worker-aware coverage.

## Completion Checklist

- [ ] Baseline tests added.
- [ ] Route-driven analyzer added.
- [ ] Orchestrator integration added with role-specific guard.
- [ ] Bridge fallback still works without route annotations.
- [ ] Valid handoff suppression works.
- [ ] Route/bridge duplicate diagnostics dedupe to one.
- [ ] Worker-aware route-derived diagnostics covered.
- [ ] Stage 9 and Stage 7 delegation regressions covered.
- [ ] Full unit suite passes.
