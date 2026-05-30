# Task F0: Baseline Frontend Tests

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Related docs:

- `docs/Todo/route_contract_refactor_00_readme.md`
- `docs/Todo/route_contract_refactor_01_frontend_semantic_contract.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Establish a reliable baseline before changing `InputAdapter`, `FieldRouteIR`,
or `FieldRouter`.

This task must document current behavior and add/adjust tests only where needed.
Do not refactor production routing logic in this task.

## Scope

In scope:

- structural adapter output baseline;
- canonical Stage 1 span provenance baseline;
- current Stage 2 adapter-aware routing baseline;
- current failure-mode behavior baseline;
- current delegation-intent behavior baseline;
- current input/output hard-fact contract baseline.

Out of scope:

- adding `RouteAnnotation`;
- changing `failure_mode` routing;
- changing Stage 4 bridge behavior;
- changing Stage 7 executable filtering;
- deleting bridge code.

## Required Baseline Cases

Use a structural NL input containing all seven known sections:

```text
Task family:
Internal newsletters and announcements.

Inputs for each run:
A user request, optional known topics, optional timeframe.

Required outputs:
A draft communication artifact, a source/evidence set, a short assumptions log, and a completion status.

Reusable process:
First determine what kind of communication is requested.
If sources are needed and available, retrieve them using approved source recipes.

Policies:
Do not invent links or unseen facts. Require evidence for sourced claims.

Failure handling:
Missing timeframe, conflicting instructions, evidence shortage, and provenance failure.

Delegation policy:
Optional delegated subtasks such as source gathering or template matching may be used if bounded.
```

## Implementation Requirements

### 1. Adapter Baseline

Add or update tests proving:

- `StructuralNLAdapter` detects structural NL.
- `raw_sections` include all expected canonical titles.
- `semantic_packets` include:
  - `task_family`
  - `runtime_input`
  - `required_output`
  - `process_step`
  - `policy`
  - `failure_mode`
  - `delegation_rule`
- `hard_facts.inputs` includes runtime inputs.
- `hard_facts.outputs` includes required outputs.
- `hard_facts.failure_modes` includes `missing_timeframe`.
- `hard_facts.delegation_intents` is populated for delegation policy.
- no adapter output includes a confidence field.

Suggested test area:

- `tests/unit/test_input_adapters.py`

### 2. SpanSlicer Baseline

Add or update tests proving:

- canonical structural input does not call the LLM for Stage 1;
- packet-backed spans carry `source_section_id`;
- packet-backed spans carry `source_packet_id`;
- uncovered section spans, if any, carry `source_section_id`;
- no section provenance is dropped.

Suggested test area:

- `tests/unit/test_input_adapter_pipeline.py`

### 3. FieldRouter Current Behavior Baseline

Add or update tests documenting current behavior, even where it is imperfect:

- `runtime_input` and `required_output` spans are not routed to `behavior`;
- `process_step` spans are routed to `behavior`;
- `policy` spans are routed to `rules`;
- current `failure_mode` spans are routed to `rules`;
- `delegation_rule` spans are routed to `behavior`;
- `ambiguity_updates` are empty for canonical adapter path.

Important: mark the `failure_mode -> rules` assertion as current baseline, not
target design.

Suggested test area:

- `tests/unit/test_input_adapter_pipeline.py`
- `tests/unit/test_field_router.py`

### 4. Failure Bridge Baseline

Add or confirm tests proving:

- `FailureModeFact` can create partial `ExceptionFlow` through
  `bridge_failure_modes()`;
- the bridge does not create handler steps;
- duplicate failure conditions are deduped;
- source section provenance can be resolved from failure spans.

Suggested test area:

- `tests/unit/test_failure_mode_bridge.py`
- `tests/integration/test_llm_adapter_engine_e2e.py`

### 5. Delegation Baseline

Add or confirm tests proving:

- delegation intent without a valid handoff does not render executable
  `INVOKE_WORKER`;
- a diagnostic is emitted for incomplete delegation contract;
- delegation provenance points to `sec_delegation_policy`.

Suggested test area:

- `tests/unit/test_failure_mode_bridge.py`
- `tests/integration/test_llm_adapter_engine_e2e.py`

## Acceptance Criteria

This task is complete when:

- baseline tests exist for adapter, Stage 1, Stage 2, failure bridge, and
  delegation bridge behavior;
- all new tests pass in the local environment;
- no production code routing behavior is changed;
- any failing pre-existing tests are recorded separately with explanation;
- `docs/Todo/route_contract_refactor_progress_tracker.html` is updated for F0:
  - status;
  - code changes;
  - test commands;
  - evidence;
  - risks.

## Required Evidence For Review

When submitting for review, provide:

1. list of changed test files;
2. exact test commands run;
3. test output summary;
4. any known failures and whether they are pre-existing;
5. confirmation that production routing logic was not changed;
6. short note explaining the current baseline mismatch:

```text
Current baseline: failure_mode routes to rules and reaches ExceptionFlow via bridge.
Target design: failure_mode should become a non-executable EXCEPTION_FLOW.condition route annotation.
```

## PM Review Checklist

- [ ] No production routing logic changed.
- [ ] Baseline documents current behavior, including known wrong behavior.
- [ ] Tests are narrow and deterministic.
- [ ] Failure handling baseline covers no invented handler.
- [ ] Delegation baseline covers no executable worker without contract.
- [ ] Progress tracker F0 section is filled.

