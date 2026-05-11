# Developer D Plan: Step, Normalizer, And WorkerAssembler Migration

Primary owner: Developer D

Review partners: Developer A, Developer C

Design reference: `docs/multi_worker_system_design.md`

## 1. Responsibility

Developer D owns the compilation path from WorkerPlanIR handoffs into concrete `INVOKE_WORKER` steps and rendered `DEFINE_WORKER` blocks.

## 2. Files To Modify

- `src/nl2spl/pipeline/stages/stage7_step_extractor.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer.py`
- `src/nl2spl/pipeline/stages/stage10_worker_assembler.py`
- `src/nl2spl/pipeline/stages/stage11_spl_renderer.py` only if renderer support is missing
- `src/nl2spl/ir/worker_ir.py` only if required by WorkerPlanIR mapping

## 3. Files To Create

- `tests/unit/pipeline/stages/test_worker_handoff_step_extraction.py`
- `tests/unit/pipeline/stages/test_worker_plan_normalizer.py`
- `tests/unit/pipeline/stages/test_worker_plan_assembler.py`

## 4. StepExtractor Changes

Target behavior:

- Use `WorkerPlanIR.handoffs` to emit `INVOKE_WORKER`.
- Use concrete `to_worker.worker_name` as invocation target.
- Use `input_bindings` to populate step inputs.
- Use `output_bindings` to populate step outputs.
- Respect structured binding fields: `required`, `default_value`, and `merge_strategy`.
- Do not emit placeholder worker targets.
- Do not duplicate child-owned behavior spans as main-worker commands.
- Use `mode="api_call"` only for direct `CALL_API`; use `mode="invoke"` for child and api adapter workers.

## 5. Normalizer Changes

The normalizer must enforce:

- every `INVOKE_WORKER` has a WorkerPlanIR handoff
- every handoff has existing source and target workers
- every invocation target is concrete
- required child inputs are provided by parent variables
- required child outputs are bound to parent variables
- required output bindings are consumed or declared as final outputs
- optional output bindings may be ignored only when the merge strategy allows it
- child worker definitions are used
- required child outputs are consumed or declared as final outputs
- no fallback from `INVOKE_WORKER` to `COMMAND`

Invalid unresolved invocation should produce an error, not a warning.

## 6. WorkerAssembler Changes

Target behavior:

- Build child workers from `WorkerPlanIR.workers`.
- Use worker contracts for `[INPUTS]` and `[OUTPUTS]`.
- Use worker-scoped flow/block/step slices.
- Stop inferring child workers from `FlowStructureIR.delegation_candidates` once WorkerPlanIR is available.

During migration:

- legacy path may still use `delegation_candidates`
- WorkerPlanIR path has priority

## 7. Structured Output Handling

If one child task semantically returns multiple fields but SPL grammar requires one response variable, normalize to a structured result type:

```spl
[DEFINE_TYPES:]
    SourceGatheringResult = { evidence_set: List [text], provenance_log: text }
[END_TYPES]
```

Rules:

- Type generation should be based on child `output_contract`.
- Parent invocation response should bind to the structured result variable.
- Downstream references should use the structured result variable unless field-level references become supported.

## 8. Tests

Required tests:

- handoff produces concrete `INVOKE_WORKER`
- missing handoff target errors
- placeholder target errors
- child worker without invocation errors
- child output mismatch errors
- structured multi-output result type is generated
- legacy delegation path still passes until bridge removal

## 9. Acceptance Criteria

- Internal-comms source gathering renders one child worker and one concrete invocation.
- No child worker is rendered unless referenced by a handoff.
- No unresolved `INVOKE_WORKER` can reach renderer.
- Existing single-worker fixtures remain stable.
