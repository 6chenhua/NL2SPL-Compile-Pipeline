# DelegationPlanIR / WorkerPlanIR Migration TODO

Date: 2026-05-09

Expanded design and implementation planning:

- `docs/multi_worker_system_design.md`
- `docs/implementation/multi_worker_collaboration_plan.md`
- `docs/implementation/multi_worker_dev_a_ir_contracts.md`
- `docs/implementation/multi_worker_dev_b_boundary_planner.md`
- `docs/implementation/multi_worker_dev_c_flow_block.md`
- `docs/implementation/multi_worker_dev_d_step_normalizer_worker_assembler.md`
- `docs/implementation/multi_worker_dev_e_tests_rollout.md`

## Background

Current implementation keeps `FlowStructureIR.delegation_candidates` as a compatibility bridge. This lets Stage 9.5 materialize `INVOKE_WORKER` steps and lets Stage 10 render concrete child workers, but it puts worker-boundary planning inside a flow-planning IR.

This is a design debt. Worker boundaries should be decided before `FlowStructureIR`, following the coarse-to-fine rule:

1. Decide whether the SPL needs multiple workers.
2. Define each worker's responsibility and data contract.
3. Define worker handoffs and failure policy.
4. Build each worker's internal flow/block/step structure.

## Problems With The Current Bridge

- `FlowStructureIR` mixes two responsibilities: execution-path classification and worker-boundary planning.
- Stage 7 can emit `INVOKE_WORKER` before a concrete worker plan exists.
- Stage 9.5 must infer missing worker targets after the fact.
- Child worker inputs/outputs are inferred from local delegation candidates instead of a first-class contract.
- A child worker can be defined without a reliable handoff model unless normalization patches it.
- Multi-worker collaboration is implicit in step variables rather than explicit handoff edges.

## Target IR

### WorkerPlanIR

```json
{
  "main_worker_id": "worker_main",
  "workers": [],
  "handoffs": [],
  "unassigned_span_ids": [],
  "warnings": []
}
```

### WorkerSpecIR

Required fields:

- `worker_id`: stable internal id, for example `worker_main` or `worker_source_retrieval`
- `worker_name`: SPL worker name, for example `MainWorker` or `child_dc_1`
- `kind`: `main`, `child`, or `api_adapter`
- `purpose`: concise worker responsibility
- `owned_span_ids`: source spans owned by this worker
- `input_contract`: variable names, data types, required flags, descriptions
- `output_contract`: variable names, data types, required flags, descriptions
- `depends_on`: worker ids that must run before this worker
- `constraints`: applicable constraint ids or source span ids
- `boundary_kind`: constrained boundary category
- `decision_evidence`: constrained signal values explaining the worker boundary
- `reason`: why this worker boundary exists

### WorkerHandoffIR

Required fields:

- `from_worker`
- `to_worker`
- `mode`: `invoke` or `api_call`
- `condition_text`
- `input_bindings`: structured parent-to-child input bindings
- `output_bindings`: structured child-to-parent output bindings with required/optional semantics
- `ordering`: before/after/conditional relationship
- `failure_policy`: what to do when the child worker cannot complete

## Migration Plan

### Phase 1: Add IR Without Rewiring The Pipeline

- Add `src/nl2spl/ir/worker_plan_ir.py`.
- Add unit tests for `WorkerPlanIR`, `WorkerSpecIR`, and `WorkerHandoffIR`.
- Add `WorkerPlanValidator` with worker graph, ownership, handoff, and binding invariants.
- Keep `FlowStructureIR.delegation_candidates` unchanged for compatibility.
- Add documentation showing `delegation_candidates` is deprecated once WorkerPlanIR is adopted.

Acceptance criteria:

- New IR can represent the current internal-comms source gathering/template matching delegation.
- No pipeline behavior changes yet.

### Phase 2: Add Worker Boundary Planner Stage

- Add Stage 3.5 after Stage 3 and before FlowAssembler.
- Input: resolved spans, routes, and compact source text.
- Output: `WorkerPlanIR`.
- Prompt must decide whether multiple SPL workers are warranted before flow structure is assembled.
- Worker planner must not output execution blocks or steps.
- Run Stage 3.6 `WorkerPlanValidator` immediately after Stage 3.5.

Acceptance criteria:

- Internal-comms produces one main worker and one optional child worker for bounded source gathering/template matching.
- A non-delegated input produces only the main worker.

### Phase 3: Make FlowAssembler Worker-Aware

- FlowAssembler should consume `WorkerPlanIR`.
- It should build flow structure per worker, or at least only for the main worker during the first migration step.
- Remove delegation decision-making from Stage 4 prompt.
- Keep compatibility adapter that copies WorkerPlanIR child workers into `FlowStructureIR.delegation_candidates` only while downstream stages migrate.

Acceptance criteria:

- Stage 4 no longer invents `delegation_candidates`.
- Flow classification and worker-boundary planning become separately testable.

### Phase 4: Make StepExtractor And Normalizer Worker-Aware

- StepExtractor should use `WorkerPlanIR.handoffs` when emitting `INVOKE_WORKER`.
- Stage 9.5 should validate worker handoffs instead of guessing concrete child targets.
- Remove fallback logic that infers child worker names only from overlapping source spans.
- Preserve the rule: unresolved `INVOKE_WORKER` is an error, never a downgrade to ordinary COMMAND.

Acceptance criteria:

- Every `INVOKE_WORKER` has a target from `WorkerPlanIR`.
- Every target has a child worker contract.
- Every handoff binding references declared variables.

### Phase 5: Make WorkerAssembler Build From WorkerPlanIR

- WorkerAssembler should build `WorkerIR.child_workers` from `WorkerPlanIR.workers`.
- Child worker inputs/outputs should come from worker contracts, not directly from StepIR guesses.
- Flow/block/step slices should be assigned according to each worker's `owned_span_ids`.

Acceptance criteria:

- Child workers cannot be defined but unused.
- Child worker output variables match parent invocation responses.
- Multi-output child results produce structured TypeSpec when required.

### Phase 6: Remove Compatibility Field

- Remove or deprecate `FlowStructureIR.delegation_candidates`.
- Update fixtures and prompt docs.
- Add migration notes for any tests that still construct delegation through FlowStructureIR.

Acceptance criteria:

- No production stage reads `FlowStructureIR.delegation_candidates`.
- Worker planning is represented only by `WorkerPlanIR`.

## Tests To Add

- Worker planner emits no child worker when delegation text is absent.
- Worker planner emits child worker with contract when delegation text has bounded IO.
- Revision is not treated as a child worker unless explicitly delegated.
- Source retrieval can be a main-flow IF and a child worker invocation only when the handoff plan says so.
- Unresolved `INVOKE_WORKER` raises validation error.
- A child worker cannot be rendered if it is not referenced by a handoff.
- Handoff output with multiple fields becomes a structured TypeSpec.

## Open Design Questions

- Should api-only subtasks become `api_adapter` workers or remain plain `CALL_API` steps?
- Should failure policy compile into `EXCEPTION_FLOW`, local IF/WHILE blocks, or constraints depending on text?
- Should input/output contracts use `VariableSpec` directly or a smaller contract-specific type?
