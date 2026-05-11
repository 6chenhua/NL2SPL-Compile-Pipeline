# Developer B Plan: WorkerBoundaryPlanner

Primary owner: Developer B

Review partners: Developer A, Developer E

Design reference: `docs/multi_worker_system_design.md`

## 1. Responsibility

Developer B owns Stage 3.5: `WorkerBoundaryPlanner`. This stage proposes worker boundaries before flow assembly. Developer A's Stage 3.6 `WorkerPlanValidator` validates the emitted graph immediately after this stage.

## 2. Files To Create

- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner.py`
- prompt template for Stage 3.5 in the existing prompt system
- `tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py`

## 3. Files To Modify

- `src/nl2spl/pipeline/orchestrator.py`
- `src/nl2spl/llm/prompts.py` or prompt registry equivalent
- persistence/checkpoint naming if needed
- `docs/prompt_design_document.md`

## 4. Stage Input

The stage consumes:

- `list[SpanIR]`
- `FieldRouteIR`
- optional input adapter metadata when available

The prompt should use compact text, not full raw IR JSON.

## 5. Stage Output

The stage outputs `WorkerPlanIR`.

Checkpoint name:

```text
stage3_5_worker_boundary_planner.json
```

## 6. Prompt Requirements

The prompt must instruct the model to:

- identify candidate task units
- identify control complexity regions if visible
- decide accepted and rejected worker boundaries
- create contracts and handoffs only for accepted workers
- not emit flow, block, command, or final SPL
- reject weak candidates explicitly
- treat explicit delegation words and nested control as evidence, not final decisions

The prompt must include the hard requirements:

- responsibility
- input contract
- output contract
- invocation point
- result handoff

## 7. Planner Decision Rules

Accepted child worker requires:

- all hard requirements present
- at least one strong positive signal
- no blocking negative signal

Rejected candidates must include a rejection category:

- `no_clear_input_contract`
- `no_clear_output_contract`
- `no_parent_invocation_point`
- `simple_control_flow`
- `ordinary_sequential_step`
- `policy_or_constraint`
- `alternative_flow`
- `exception_flow`
- `single_api_call`
- `insufficient_semantic_boundary`

## 8. Orchestrator Integration

Initial integration should be feature-flag friendly:

- If Stage 3.5 is disabled, current pipeline behavior remains unchanged.
- If enabled, save WorkerPlanIR checkpoint.
- Run `WorkerPlanValidator` immediately after Stage 3.5.
- During migration, pass WorkerPlanIR through the compatibility adapter to current Stage 4/9.5/10 path.

## 9. Tests

Required tests:

- simple process produces only main worker
- explicit source gathering with IO produces child worker and handoff
- explicit subtask without output is rejected
- revision is rejected as `alternative_flow`
- missing timeframe is rejected as `exception_flow`
- single API call is rejected as `single_api_call`
- planner output with missing main worker fails validation

## 10. Acceptance Criteria

- Stage 3.5 can run independently in unit tests with mocked LLM output.
- Invalid planner output is rejected by Developer A validators.
- Internal-comms fixture produces an accepted source gathering candidate.
- No final SPL rendering changes are required at this stage.
