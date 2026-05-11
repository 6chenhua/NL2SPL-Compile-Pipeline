# Developer C Plan: Worker-Aware Flow And Block Assembly

Primary owner: Developer C

Review partners: Developer B, Developer E

Design reference: `docs/multi_worker_system_design.md`

## 1. Responsibility

Developer C owns the transition from global flow/block assembly to worker-scoped flow/block assembly using explicit wrapper IRs.

## 2. Files To Modify

- `src/nl2spl/pipeline/stages/stage4_flow_assembler.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler.py`
- `src/nl2spl/ir/flow_structure_ir.py` if wrapper types are needed
- `src/nl2spl/ir/block_structure_ir.py` if worker-scoped wrapper types are needed
- `docs/prompt_design_document.md`

## 3. Files To Create

- `tests/unit/pipeline/stages/test_worker_aware_flow_assembler.py`
- `tests/unit/pipeline/stages/test_worker_aware_block_assembler.py`

## 4. FlowAssembler Target Behavior

When `WorkerPlanIR` is available:

- assemble one `FlowStructureIR` per worker
- use `WorkerSpecIR.owned_span_ids` as the behavior span boundary
- do not invent `delegation_candidates`
- preserve current single-worker output shape through compatibility wrapper if needed

Required wrapper:

```python
@dataclass
class WorkerFlowPlanIR:
    worker_flows: dict[str, FlowStructureIR]
    warnings: list[str]
```

## 5. BlockAssembler Target Behavior

When worker-scoped flows are available:

- assemble one `BlockStructureIR` per worker
- keep blocks top-level only
- emit `ControlComplexityRegionIR` for nested control intent
- mark findings as `confirmed` when Stage 5 discovers them structurally
- set severity to `info`, `warning`, or `error`
- do not create workers

Required wrapper:

```python
@dataclass
class WorkerBlockPlanIR:
    worker_blocks: dict[str, BlockStructureIR]
    control_complexity_regions: list[ControlComplexityRegionIR]
    warnings: list[str]
```

## 6. Nested Control Policy

Stage 5 must use this order:

1. split blocks
2. merge conditions
3. lift guard variable
4. compress to command if acceptable
5. emit control complexity region

Stage 5 must not directly output a child worker candidate.

## 7. Prompt Changes

Stage 4 prompt:

- input: worker-local spans and WorkerPlanIR context
- output: flow only
- explicit rule: do not decide worker boundaries

Stage 5 prompt:

- input: worker-local flow JSON with span text
- output: block structure plus optional control complexity regions
- explicit rule: no nested blocks

## 8. Compatibility Requirements

Existing pipeline calls should continue to work:

- If no WorkerPlanIR is passed, return current `FlowStructureIR` and `BlockStructureIR`.
- If WorkerPlanIR has only main worker, output should be equivalent to current behavior.

## 9. Tests

Required tests:

- one-worker plan produces one flow and one block structure
- main + child plan produces separate flow structures
- child-owned spans do not appear in main worker flow
- flattenable nested sequence is split into top-level blocks
- nested IF inside FOR emits control complexity region
- Stage 5 does not emit delegation candidate

## 10. Acceptance Criteria

- Developer D can locate a handoff insertion point from worker-scoped flow/block structures.
- Existing Stage 5 prompt contract remains valid in legacy mode.
- No nested block can appear in final `BlockStructureIR`.
