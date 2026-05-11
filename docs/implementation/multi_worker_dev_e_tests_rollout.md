# Developer E Plan: Tests, Fixtures, Documentation, And Rollout

Primary owner: Developer E

Review partners: all developers

Design reference: `docs/multi_worker_system_design.md`

## 1. Responsibility

Developer E owns regression safety, fixture coverage, golden SPL expectations, and rollout documentation.

## 2. Files To Create Or Modify

- `tests/fixtures/multi_worker/`
- `tests/integration/test_multi_worker_pipeline.py`
- `tests/golden/` or existing golden output location
- README documentation links
- migration notes in `docs/delegation_plan_todo.md` if implementation changes the migration plan

## 3. Fixture Set

Create fixtures for:

1. `simple_single_worker`
2. `internal_comms_source_gathering`
3. `explicit_subtask_without_io`
4. `revision_not_worker`
5. `single_api_call_not_worker`
6. `api_adapter_with_provenance`
7. `flattenable_nested_control`
8. `loop_body_child_worker`
9. `same_child_multiple_handoffs`
10. `unresolved_invoke_worker_error`
11. `unused_child_worker_error`
12. `worker_plan_validator_errors`
13. `api_call_vs_api_adapter`
14. `duplicate_behavior_span_ownership`
15. `duplicate_handoff_id`

## 4. Golden Assertions

For SPL outputs, assert:

- no nested blocks
- child workers render before main worker
- child worker names are concrete
- parent invokes child exactly once unless fixture requires multiple calls
- child output variables match parent response variables
- required child output binding mismatches fail
- direct API calls render `CALL_API`, while api adapter workers render `INVOKE_WORKER`
- `[DEFINE_TYPES:]` appears only when structured output is required
- revision remains `ALTERNATIVE_FLOW` unless explicitly delegated
- failure handling remains `EXCEPTION_FLOW` or handoff failure policy

## 5. Regression Strategy

Run these checks for every integration PR:

```bash
pytest tests/unit
pytest tests/integration
ruff check src tests
```

If mypy is currently used in CI, include:

```bash
mypy src
```

## 6. Documentation Responsibilities

Developer E should keep these documents aligned:

- `README.md`
- `docs/multi_worker_system_design.md`
- `docs/delegation_plan_todo.md`
- `docs/prompt_design_document.md`
- implementation task docs under `docs/implementation/`

## 7. Rollout Gates

Gate 1:

- IR exists
- Planner can be mocked
- no behavior changes

Gate 2:

- Planner runs in compatibility mode
- internal-comms source gathering accepted
- weak candidates rejected

Gate 3:

- worker-scoped flow/block path passes single-worker and multi-worker fixtures

Gate 4:

- handoff-driven invocation and WorkerAssembler pass golden SPL tests

Gate 5:

- `delegation_candidates` no longer used in production path

## 8. Acceptance Criteria

- Test fixtures cover both accepted and rejected worker candidates.
- Golden SPL tests catch undefined workers and unused workers.
- Documentation points developers to the correct design and task docs.
- Regression tests demonstrate that single-worker behavior remains stable.

## 9. Current Rollout Coverage

Added deterministic fixtures under `tests/fixtures/multi_worker/` for the
planned acceptance matrix:

- accepted worker cases: simple single worker, internal-comms source gathering,
  API adapter with provenance, loop-body child worker, same child worker invoked
  by multiple handoffs
- rejected worker cases: explicit subtask without IO, revision as alternative
  flow, single API call as `CALL_API`, flattenable nested control
- negative validation cases: unresolved invoke worker, unused child worker,
  duplicate behavior-span ownership, validator graph errors, required child
  output binding mismatch, duplicate `handoff_id`, `api_call` binding
  validation errors

Added `tests/integration/test_multi_worker_pipeline.py` to exercise
WorkerPlanIR validation, Stage 9.5 normalization, Stage 10 assembly, and Stage
11 rendering without LLM calls. The suite asserts concrete child worker names,
child-before-main rendering order, no nested block syntax, direct API versus API
adapter command shape, repeated handoffs to the same child worker, required
output binding validation, and single-worker stability.

This is a deterministic IR-level rollout suite. It does not yet prove the full
`PipelineOrchestrator.run(...)` path, `enable_worker_boundary_planner=True`
orchestrator wiring, or worker-scoped flow/block wrapper consumption.
Until those paths are covered and the remaining P1 implementation fixes land,
the multi-worker feature flag should remain default-off.

Added `tests/integration/test_multi_worker_orchestrator_rollout.py` to cover the
orchestrator feature flag at regression level:

- flag off: the legacy path does not emit worker-plan or worker-scoped
  intermediates and keeps a single worker output
- flag on: `stage3_5_worker_plan`, `stage4_worker_flows`, and
  `stage5_worker_blocks` are present in `PipelineResult.intermediate_results`
- flag on: final SPL renders a concrete child worker and parent `INVOKE`
- flag on: child-owned behavior text is excluded from the Stage 7 behavior-span
  prompt section

The current rollout path is:

```text
Stage 3.5 WorkerPlanIR
-> Stage 3.6 WorkerPlanValidator
-> worker-aware Stage 4/5 wrappers
-> legacy main-worker adapter view
-> Stage 7 / Stage 9.5 / Stage 10 WorkerPlan handoff path
-> Stage 11 SPL rendering
```

Local cleanup note: failed deletion of `.pytest_tmp/` is a Windows file-handle
cleanup issue in the local test environment. It is not a code blocker and should
not be force-deleted by automation.
