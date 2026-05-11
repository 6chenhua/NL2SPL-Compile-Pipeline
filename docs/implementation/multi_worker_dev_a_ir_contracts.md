# Developer A Plan: WorkerPlanIR And Contracts

Primary owner: Developer A

Review partners: Developer D, Developer B

Design reference: `docs/multi_worker_system_design.md`

## 1. Responsibility

Developer A owns the IR foundation for multi-worker compilation. This work must be merged before planner, flow, step, and assembler migration can stabilize.

## 2. Files To Create

- `src/nl2spl/ir/worker_plan_ir.py`
- `tests/unit/ir/test_worker_plan_ir.py`
- `tests/unit/pipeline/test_worker_plan_validation.py`
- optional: `src/nl2spl/pipeline/worker_plan_validator.py`
- optional: `src/nl2spl/pipeline/worker_plan_adapter.py`

## 3. Files To Modify

- `src/nl2spl/ir/__init__.py`
- `src/nl2spl/pipeline/orchestrator.py` only if a neutral placeholder import is required
- documentation only if IR fields change from the system design

## 4. IR Classes

Implement:

- `BoundaryKind`
- `Signal`
- `Risk`
- `ContractFieldIR`
- `CandidateTaskUnitIR`
- `ControlComplexityRegionIR`
- `WorkerBoundaryDecisionIR`
- `WorkerSpecIR`
- `InputBindingIR`
- `OutputBindingIR`
- `InvokeLocationHintIR`
- `HandoffFailurePolicyIR`
- `WorkerHandoffIR`
- `WorkerPlanIR`
- `WorkerScopedFlowIR`
- `WorkerFlowPlanIR`
- `WorkerBlockPlanIR`

Use dataclasses and `typing.Literal`, matching existing IR style.

## 5. Validation Functions

Add `WorkerPlanValidator` helpers that return errors and warnings without throwing by default:

- exactly one main worker
- `main_worker_id` exists
- worker ids are unique
- worker names are unique and SPL-safe
- every non-main worker has at least one handoff
- every invoke handoff source and target exists
- every `api_call` handoff has `api_ref` and no `to_worker`
- every accepted child worker has non-empty input and output contracts
- every handoff binding references contract fields
- no duplicate behavior-span ownership across workers
- all `owned_span_ids` exist
- rejected candidates are not present as concrete workers
- no handoff references rejected candidates
- `decisions` contains all `rejected_candidates`
- no accepted decision appears in `rejected_candidates`

## 6. Compatibility Adapter

Implement an adapter from `WorkerPlanIR` to legacy `DelegationCandidate` only for migration.

Rules:

- accepted `extract_child_worker` decisions become `DelegationCandidate`
- rejected candidates are never adapted
- adapter preserves span ids, reason, input variable names, output variable names
- adapter marks `suggested_type="child_worker"` unless decision says API adapter

## 7. Tests

Required unit tests:

- construct minimal one-worker plan
- construct main + child plan with handoff
- reject child without handoff
- reject handoff with missing target
- reject duplicate worker names
- reject unsafe worker names
- validate binding mismatch
- validate `invoke` vs `api_call` handoff mode constraints
- validate duplicate behavior-span ownership
- preserve rejected candidate
- adapter converts accepted worker only
- adapter ignores rejected candidate

## 8. Acceptance Criteria

- Existing test suite passes.
- New IR imports from `nl2spl.ir`.
- No pipeline behavior changes are required to pass tests.
- Developer B can consume `WorkerPlanIR` without adding new schema fields.
