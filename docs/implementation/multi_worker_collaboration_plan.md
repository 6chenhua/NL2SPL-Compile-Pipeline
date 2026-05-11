# Multi-Worker Development Collaboration Plan

Date: 2026-05-10

Primary design document: `docs/multi_worker_system_design.md`

This plan splits the multi-worker migration into parallel developer workstreams. Each developer owns a bounded area and should avoid changing files owned by another stream unless coordinated.

## 1. Delivery Goal

Deliver a first-class multi-worker compiler path:

```text
Stage 3.5 WorkerBoundaryPlanner
    -> WorkerPlanIR
    -> Stage 3.6 WorkerPlanValidator
    -> worker-aware flow/block/step/resource/normalizer/worker assembly
    -> SPL with valid DEFINE_WORKER and INVOKE_WORKER contracts
```

The migration should keep current single-worker behavior stable and preserve the existing `FlowStructureIR.delegation_candidates` bridge until downstream stages are migrated.

## 2. Workstream Summary

| Developer | Workstream | Main Output |
|---|---|---|
| Developer A | IR and validation foundation | `WorkerPlanIR` family, `WorkerPlanValidator`, compatibility adapter |
| Developer B | WorkerBoundaryPlanner stage and prompts | Stage 3.5 implementation and prompt contract |
| Developer C | Worker-aware Flow/Block assembly | `WorkerFlowPlanIR`, `WorkerBlockPlanIR`, and control complexity regions |
| Developer D | Step/Normalizer/WorkerAssembler migration | handoff-driven `INVOKE_WORKER` and WorkerIR assembly |
| Developer E | Test harness, fixtures, rollout QA | integration tests, golden SPL, migration safety checks |

Detailed task documents:

- `docs/implementation/multi_worker_dev_a_ir_contracts.md`
- `docs/implementation/multi_worker_dev_b_boundary_planner.md`
- `docs/implementation/multi_worker_dev_c_flow_block.md`
- `docs/implementation/multi_worker_dev_d_step_normalizer_worker_assembler.md`
- `docs/implementation/multi_worker_dev_e_tests_rollout.md`

## 3. Shared Branching And Merge Order

Recommended merge order:

1. Developer A: IR classes, validators, compatibility adapter.
2. Developer B: Stage 3.5 producing WorkerPlanIR.
3. Developer C: worker-aware flow/block with compatibility mode.
4. Developer D: worker-aware step/normalizer/assembler migration.
5. Developer E: integration fixtures and golden regression suite.

Developer E can start fixture design immediately but should merge final tests after A-D expose stable interfaces.

## 4. Shared Contracts

All developers must follow these contracts:

- `WorkerPlanIR` is the source of truth for worker boundaries.
- `FlowStructureIR.delegation_candidates` is compatibility-only.
- FlowAssembler must not invent workers once WorkerPlanIR is present.
- BlockAssembler must not create workers from nested blocks.
- A behavior span must have exactly one owning worker.
- Policy/rule spans may be referenced by multiple workers through constraints.
- Stage 7 must not invent child worker names.
- Unresolved `INVOKE_WORKER` is an error.
- Child worker output variables must bind to parent variables.
- Direct API calls use `mode="api_call"` with `api_ref`; api adapter workers use `mode="invoke"`.
- A rendered child worker must have at least one parent invocation.
- No final `BlockStructureIR` may contain nested blocks.

## 5. Integration Checkpoints

### Checkpoint 1: IR Compiles

Owner: Developer A

Acceptance:

- New IR classes import cleanly from `nl2spl.ir`.
- Unit tests cover serialization-like construction, `WorkerPlanValidator`, and compatibility adapter behavior.
- Existing tests pass without pipeline behavior changes.

### Checkpoint 2: Planner Runs In Compatibility Mode

Owners: Developer A + B

Acceptance:

- Orchestrator can optionally run Stage 3.5.
- Orchestrator can run Stage 3.6 validation immediately after Stage 3.5.
- Planner checkpoint is saved as `stage3_5_worker_boundary_planner.json`.
- WorkerPlanIR can be adapted into current `delegation_candidates`.
- Internal-comms source gathering appears as a candidate with accepted handoff.

### Checkpoint 3: Worker-Scoped Flow/Block

Owners: Developer B + C

Acceptance:

- Stage 4 can assemble flows per worker when WorkerPlanIR is available.
- Stage 5 can assemble blocks per worker.
- Worker-scoped wrappers are checkpointed.
- Control complexity regions are checkpointed.
- Existing single-worker path still works.

### Checkpoint 4: Handoff-Driven Invocation

Owners: Developer A + D

Acceptance:

- StepExtractor uses handoff target names.
- Normalizer rejects placeholder worker targets.
- WorkerAssembler builds child workers from WorkerPlanIR, not inferred delegation candidates.
- Required child outputs match parent invocation response variables.

### Checkpoint 5: Regression Suite

Owner: Developer E

Acceptance:

- Internal-comms golden SPL passes.
- Simple single-worker fixture passes.
- Explicit weak subtask is rejected.
- Nested flattenable control stays single-worker.
- Nested per-item protocol can become child worker.
- Unresolved `INVOKE_WORKER` fails fast.

## 6. File Ownership

| Area | Primary Owner | Secondary Review |
|---|---|---|
| `src/nl2spl/ir/worker_plan_ir.py` | A | D |
| `src/nl2spl/ir/__init__.py` | A | B |
| WorkerPlanValidator | A | D |
| compatibility adapter | A | D |
| `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner.py` | B | A |
| planner prompt docs/templates | B | E |
| orchestrator Stage 3.5 wiring | B | C |
| Stage 4 worker-aware flow | C | B |
| Stage 5 worker-aware block | C | E |
| control complexity IR use | C | A |
| Stage 7 handoff-aware extraction | D | B |
| Stage 9.5 worker validation | D | A |
| Stage 10 WorkerAssembler migration | D | C |
| integration tests and fixtures | E | all |
| README and developer docs | E | all |

## 7. Coordination Rules

- A developer should not edit another developer's owned files without a short handoff note.
- Interface-changing PRs must update the relevant task document.
- Prompt changes must include at least one fixture demonstrating the expected behavior.
- Validator changes must include negative tests.
- Any fallback that converts an invalid worker invocation to ordinary `COMMAND` is prohibited.
- If a candidate lacks IO or invocation point, reject it explicitly instead of silently dropping it.

## 8. Recommended Sprint Plan

### Sprint 1: Foundation

- A completes IR and validation.
- A exposes Stage 3.6 validator API.
- B drafts planner prompt and mock planner output tests.
- E prepares fixtures and expected decisions.

### Sprint 2: Planner Compatibility

- B wires Stage 3.5.
- A adds compatibility adapter into current flow path.
- E adds planner contract tests.

### Sprint 3: Worker-Scoped Structures

- C migrates Stage 4 and Stage 5 to worker-scoped mode.
- E adds block/control complexity tests.

### Sprint 4: Handoff Compilation

- D migrates StepExtractor, Normalizer, and WorkerAssembler.
- A supports any contract validation gaps.
- E adds end-to-end golden SPL tests.

### Sprint 5: Bridge Removal Prep

- D removes production dependence on `delegation_candidates`.
- C updates old fixtures.
- E runs regression suite and documents remaining migration risk.

## 9. Definition Of Done

The multi-worker migration is complete when:

- `WorkerPlanIR` is produced before flow assembly.
- Worker boundaries are no longer decided inside `FlowStructureIR`.
- Every rendered child worker is referenced by a concrete parent `INVOKE_WORKER`.
- Every `INVOKE_WORKER` target comes from a WorkerPlanIR handoff.
- No invalid nested blocks render into final SPL.
- Internal-comms example generates source-gathering child worker only when the planner validates its IO/handoff.
- All single-worker fixtures remain unchanged except for harmless formatting differences.
