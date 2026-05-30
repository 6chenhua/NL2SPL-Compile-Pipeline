# Task D9: Documentation, Migration Cleanup, and Final Audit

Date assigned: 2026-05-22

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0 through D8 approved.

Related docs:

- `docs/Todo/input_adapter_fieldroute_semantic_routing_refactor_todo.md`
- `docs/Todo/input_adapter_fieldroute_semantic_routing_refactor_todo_zh.md`
- `docs/Todo/route_contract_refactor_00_readme.md`
- `docs/Todo/route_contract_refactor_01_frontend_semantic_contract.md`
- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`
- `docs/Todo/tasks/F0_baseline_frontend_tests.md`
- `docs/Todo/tasks/F1_adapter_hint_evidence_strengthening.md`
- `docs/Todo/tasks/F2_route_annotation_ir.md`
- `docs/Todo/tasks/F3_hint_aware_field_router.md`
- `docs/Todo/tasks/F4_annotation_aware_ambiguity_resolver.md`
- `docs/Todo/tasks/D0_downstream_baseline_and_route_helper_adoption.md`
- `docs/Todo/tasks/D1_worker_boundary_planner_annotation_migration.md`
- `docs/Todo/tasks/D2_flow_assembler_route_driven_exception_materialization.md`
- `docs/Todo/tasks/D3_worker_aware_exception_flow_migration.md`
- `docs/Todo/tasks/D4_block_assembler_partial_skeleton_support.md`
- `docs/Todo/tasks/D5_resource_profile_constraint_consumers.md`
- `docs/Todo/tasks/D6_step_extractor_executable_filtering.md`
- `docs/Todo/tasks/D7_normalizer_gate_renderer_provenance.md`
- `docs/Todo/tasks/D8_bridge_deprecation_and_deletion.md`

## Objective

Make the completed refactor understandable, auditable, and consistent across
docs, task trackers, comments, examples, and migration notes.

The implementation is now route-driven for failure-mode exception materialization
and executable filtering. Documentation must no longer describe the old
bridge-first path as the current architecture.

The final documented architecture should be:

```text
Raw text
-> InputAdapter evidence / hints
-> SpanSlicer section-aware spans
-> FieldRouteIR annotations
-> stage-specific construct materialization
-> partial SPL + diagnostics + provenance
```

## Scope

In scope:

- update design docs to match F0-F4 and D0-D8 behavior;
- update task docs or progress tracker entries that still show stale review
  status or obsolete evidence;
- clean old wording that says bridge-first is the current primary production
  path;
- document the remaining delegation bridge compatibility boundary;
- add migration notes for future semantic roles and downstream stage authors;
- add final architecture examples and expected diagnostics;
- run documentation-oriented `rg` audits plus focused/full test suite.

Out of scope:

- changing production compiler behavior;
- deleting bridge wrappers;
- implementing route-driven delegation diagnostics;
- changing FieldRouter semantics;
- changing Stage 4/7/normalizer/renderer behavior;
- broad formatting churn unrelated to this refactor.

## Required Cleanup Areas

### 1. Progress Tracker

Update `docs/Todo/route_contract_refactor_progress_tracker.html` so it reflects
the actual final state:

- F0-F4 status = done / approved;
- D0-D8 status = done / approved;
- D7 evidence must describe the final approved implementation, not the earlier
  inferred-provenance draft;
- D8 evidence must describe condition-coverage bridge fallback and delegation
  compatibility helper;
- final test count should reflect the latest full suite result reported by the
  implementer.

Do not leave stale `review` statuses in default tracker data for approved tasks.

### 2. Main Design Docs

Update:

- `input_adapter_fieldroute_semantic_routing_refactor_todo.md`;
- `input_adapter_fieldroute_semantic_routing_refactor_todo_zh.md`;
- `route_contract_refactor_00_readme.md`;
- `route_contract_refactor_01_frontend_semantic_contract.md`;
- `route_contract_refactor_02_downstream_migration.md`.

Required content:

- `InputAdapter` is a schema-aware evidence/hint layer, not SPL IR generator;
- `FieldRoute` is the unified semantic routing and annotation contract;
- `failure_mode` routes to `EXCEPTION_FLOW.condition` as non-executable flow
  material;
- `Stage 7` uses executable-only behavior candidates;
- condition-only exception flows are legal partial skeletons;
- missing handlers produce exactly-one diagnostics and partial SPL;
- bridge failure functions are compatibility fallbacks, not primary path;
- `bridge_delegation_intents()` remains a compatibility diagnostic helper until
  route-driven delegation diagnostics are implemented.

### 3. Task Docs

Update task docs only where stale wording is now misleading.

Examples to audit:

- D0 baseline wording should remain historically accurate, but should not imply
  bridge-first is still the current architecture;
- D2 and D3 should describe route-driven materialization as completed;
- D7 should describe final direct span/section/packet provenance, not inferred
  provenance;
- D8 should record the approved compromise: failure bridge guarded fallback,
  delegation bridge retained as compatibility diagnostic helper.

Do not rewrite every task doc for style. Limit edits to stale or misleading
technical statements.

### 4. Code Comments And Test Names

Audit code and tests for comments that are now wrong.

Allowed:

- historical baseline tests that explicitly say "D0 baseline";
- compatibility comments that identify old behavior as fallback;
- tests that call bridge helpers directly as compatibility tests.

Not allowed:

- comments claiming `bridge_failure_modes()` is current primary production path;
- tests whose name says bridge is skipped while only testing bridge dedupe;
- comments saying route-derived provenance is inferred when it is now direct;
- comments suggesting failure modes become `rules` as the target design.

### 5. Final Architecture Examples

Add or update examples in docs for:

- structural input with `Failure handling: Missing timeframe`;
- structural input with delegation policy and no valid handoff;
- input/output contracts that remain resource contracts;
- mixed sentence containing process action plus policy constraint;
- worker-aware child-owned failure condition.

Each example should state the expected route/stage outcome and diagnostics.

### 6. Residual Work Register

Create or update a small section in the relevant docs that lists known residual
items after D8:

- route-driven delegation diagnostics are not implemented yet;
- `bridge_delegation_intents()` remains active as a compatibility diagnostic
  helper;
- full deletion of bridge wrappers requires equivalent route-driven tests.

This residual register must be explicit so future work does not confuse the D8
compromise with the final ideal state.

## Required Audits

Run and report:

```text
rg -n "bridge-first|primary production path|inferred provenance|route-derived provenance|delegation bridge|compatibility fallback" docs src tests
rg -n "D7|D8|reviewDecision|status" docs/Todo/route_contract_refactor_progress_tracker.html
rg -n "bridge_failure_modes|bridge_delegation_intents" src tests docs/Todo
```

Use the results to identify stale statements. Do not mechanically delete all
matches; some historical or compatibility references are expected.

## Acceptance Criteria

D9 is complete when:

- docs and progress tracker reflect all approved F/D stages;
- the final documented architecture matches the implemented pipeline;
- stale D7/D8 evidence is corrected;
- bridge-first wording is either historical, compatibility-only, or removed;
- residual delegation bridge work is explicitly documented;
- examples describe expected route annotations, partial SPL, diagnostics, and
  provenance behavior;
- no production behavior changes are mixed in unless they are trivial comment
  updates;
- focused documentation audits and the full unit suite pass.

## Required Evidence For Review

When submitting D9, provide:

1. changed files;
2. exact docs audit commands and relevant findings;
3. exact test commands and output summary;
4. before/after summary for progress tracker statuses;
5. before/after summary for D7/D8 stale evidence cleanup;
6. list of remaining bridge references and why each is allowed;
7. residual work register location;
8. confirmation that no production behavior changed.

## PM Review Checklist

- [ ] Progress tracker statuses and evidence are current.
- [ ] D7 direct provenance is documented correctly.
- [ ] D8 failure bridge fallback is documented correctly.
- [ ] Delegation bridge residual is explicit.
- [ ] Bridge-first wording is not presented as current architecture.
- [ ] Examples cover failure, delegation, resource contracts, mixed spans, and
      worker-aware failure ownership.
- [ ] No unrelated doc churn.
- [ ] Full unit suite passes.
