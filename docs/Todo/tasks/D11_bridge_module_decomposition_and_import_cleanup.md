# Task D11: Bridge Module Decomposition and Production Import Cleanup

Date assigned: 2026-05-22

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 through F4 approved.
- D0 through D10 approved.
- D10 route-driven delegation diagnostics are implemented and passing.
- Failure bridges and delegation bridge are compatibility fallbacks, not primary
  semantic production paths.

Related docs:

- `docs/Todo/tasks/D8_bridge_deprecation_and_deletion.md`
- `docs/Todo/tasks/D10_route_driven_delegation_diagnostics.md`
- `docs/Todo/input_adapter_fieldroute_semantic_routing_refactor_todo.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Separate route-driven production materialization from hard-fact compatibility
bridges.

After D10, the architecture should read:

```text
RouteAnnotation -> route-driven materializers / analyzers -> IR / diagnostics
HardFacts       -> compatibility bridges only when route evidence is absent
```

not:

```text
RouteAnnotation -> fact_bridges.py -> production IR
HardFacts       -> fact_bridges.py -> fallback IR / diagnostics
```

The immediate technical smell is that `materialize_route_exception_flows()` is a
route-driven production helper but currently lives in `fact_bridges.py`. D11
must move it into a route-owned module and update imports so `fact_bridges.py`
contains only compatibility bridge logic.

## Scope

In scope:

- create a route-owned exception materialization module;
- move `materialize_route_exception_flows()` out of `fact_bridges.py`;
- update Stage 4 / orchestrator imports to use the new module;
- keep `bridge_failure_modes()`, `bridge_failure_modes_worker_scoped()`, and
  `bridge_delegation_intents()` as compatibility fallbacks;
- add import-boundary regression tests or audit tests proving production route
  materialization no longer imports from `fact_bridges.py`;
- preserve all D2, D3, D8, and D10 behavior.

Out of scope:

- deleting compatibility bridge wrappers outright;
- changing exception-flow semantics;
- changing delegation diagnostic semantics;
- changing adapter, FieldRouter, Stage 7, renderer, normalizer, or worker
  assembler behavior;
- large refactors of `_is_valid_handoff()` unless strictly needed for imports.

## Required Design

### 1. New Route-Owned Module

Create a small production module, for example:

```text
src/nl2spl/pipeline/route_exception_materializer.py
```

Move:

```python
materialize_route_exception_flows(...)
```

from:

```text
src/nl2spl/pipeline/fact_bridges.py
```

to the new module.

The helper must keep the existing behavior:

- consumes `RouteAnnotation` entries where:
  - `construct_target == "EXCEPTION_FLOW"`;
  - `slot_target == "condition"`;
  - `semantic_role == "failure_mode"`;
  - `executable is False`;
- creates condition-only `ExceptionFlow` skeletons;
- does not fabricate handler blocks, steps, commands, or handler text;
- dedupes by normalized condition text;
- returns the original `FlowStructureIR` object on no-op;
- returns a new `FlowStructureIR` object when adding exception flows.

### 2. Import Cleanup

Update all production imports so route-driven exception materialization imports
from the new route module.

Expected final boundary:

```text
fact_bridges.py
  compatibility fallback only:
    bridge_failure_modes()
    bridge_failure_modes_worker_scoped()
    bridge_delegation_intents()
    _is_valid_handoff()

route_exception_materializer.py
  route-driven production helper:
    materialize_route_exception_flows()
```

There must be no production import like:

```python
from nl2spl.pipeline.fact_bridges import materialize_route_exception_flows
```

### 3. Backward Compatibility

Do not break tests that directly exercise bridge fallbacks. They remain valid
compatibility tests.

Bridge fallback behavior must remain:

- hard-fact-only failure modes still create condition-only exception flows when
  route annotations are absent;
- worker-scoped hard-fact-only failure modes still attach to the correct fallback
  worker path;
- route-derived exception flows plus hard facts do not duplicate;
- delegation hard-fact fallback still emits diagnostics only for uncovered
  intents.

### 4. Tests

Add or update focused tests. Minimum required coverage:

1. Route materializer import boundary:
   - `materialize_route_exception_flows()` is importable from the new route
     module;
   - no production code imports it from `fact_bridges.py`.

2. Route materializer behavior still passes:
   - route failure annotation creates one `ExceptionFlow`;
   - no-op returns the same object;
   - materialization returns a new object when adding flows;
   - no handler is fabricated.

3. Compatibility bridges still pass:
   - existing failure bridge fallback tests pass unchanged or with naming
     cleanup only;
   - D8 condition-coverage fallback tests pass;
   - D10 delegation fallback tests pass.

4. Orchestrator path still passes:
   - structural route-derived failure flow still materializes without relying on
     bridge-first behavior;
   - route + hard fact still dedupes.

## Suggested Files

Likely production files:

- `src/nl2spl/pipeline/route_exception_materializer.py`
- `src/nl2spl/pipeline/fact_bridges.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py`
- `src/nl2spl/pipeline/orchestrator.py`

Likely tests:

- `tests/unit/test_flow_assembler.py`
- `tests/unit/test_failure_mode_bridge.py`
- optionally `tests/unit/test_route_exception_materializer.py`

## Acceptance Criteria

D11 is accepted only when:

- `materialize_route_exception_flows()` no longer lives in
  `fact_bridges.py`;
- route-driven production code imports the helper from the new route-owned
  module;
- `fact_bridges.py` contains compatibility bridge logic only;
- all D2/D3/D8/D10 behavioral tests still pass;
- full unit suite passes;
- a search confirms there is no production import of
  `materialize_route_exception_flows` from `fact_bridges.py`;
- no fallback bridge behavior is deleted prematurely;
- no unrelated pipeline behavior is changed.

## Validation Commands

Run at least:

```bash
pytest tests/unit/test_flow_assembler.py tests/unit/test_failure_mode_bridge.py tests/unit/test_input_adapter_pipeline.py -q
pytest tests/unit/pipeline/stages/test_worker_aware_flow_assembler.py -q
pytest tests/unit/ -q
rg -n "materialize_route_exception_flows|bridge_failure_modes|bridge_delegation_intents" src tests docs/Todo
```

## Submission Requirements

When submitting D11, include:

1. changed file list;
2. exact import boundary before/after;
3. confirmation that `fact_bridges.py` now contains compatibility bridge logic
   only;
4. route materializer behavior summary;
5. bridge fallback behavior summary;
6. test commands and results;
7. any remaining blockers for full bridge deletion.

## Review Checklist

- [ ] Route materializer moved out of `fact_bridges.py`.
- [ ] Stage 4 / orchestrator route path imports from route-owned module.
- [ ] Compatibility bridges still pass.
- [ ] Route + hard fact dedupe still passes.
- [ ] Worker-aware exception materialization still passes.
- [ ] Delegation D10 diagnostics still pass.
- [ ] No broad refactor or unrelated behavior change.
