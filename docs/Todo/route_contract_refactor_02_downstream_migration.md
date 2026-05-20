# Route Contract Refactor 02: Downstream Migration

Date: 2026-05-18

## Purpose

This document defines how downstream compiler stages migrate after the frontend
route contract is introduced.

Prerequisite:

- complete the frontend contract work in
  `route_contract_refactor_01_frontend_semantic_contract.md` through at least
  phases F2 and F3.

The downstream goal is:

```text
RouteAnnotation
-> construct-aware flow/resource/step/constraint/profile generation
-> diagnostics and provenance
```

The final state should remove bridge-first semantics from production paths.

## Current Downstream Problem

Several downstream stages currently infer semantics from old route fields:

```text
routes.behavior
routes.rules
routes.domain
routes.integrations
```

Other parts bypass routes by reading hard facts directly:

```text
canonical_input.hard_facts.failure_modes
canonical_input.hard_facts.delegation_intents
```

This creates multiple semantic paths:

```text
Path A: routes.behavior -> stages
Path B: hard_facts -> bridge_failure_modes
Path C: hard_facts -> bridge_delegation_intents
Path D: compile_hints -> prompts only
```

The refactor should converge these into:

```text
adapter evidence / hints
-> FieldRoute annotations
-> stage-specific construct materialization
```

## Migration Rule

No downstream stage should be switched blindly from old lists to annotations.

Each stage should first use helper methods with fallback:

```python
routes.get_executable_behavior_span_ids()
routes.get_construct_slot_candidates("EXCEPTION_FLOW", "condition")
routes.get_annotations_by_role("constraint")
```

If annotations are absent, fall back to the old lists.

## Downstream Phase Plan

## D0: Downstream Baseline and Route Helper Adoption

### Goal

Prepare downstream stages to read route helpers without changing behavior.

### Tasks

1. Add helper methods to `FieldRouteIR` in frontend phase F2.
2. Add baseline tests around:
   - flow assembly;
   - step extraction;
   - worker boundary planning;
   - resource extraction;
   - constraint extraction;
   - partial exception flow rendering.
3. Update stage internals to call helper methods where behavior is identical.

### Acceptance Criteria

- No behavior changes.
- Legacy tests still pass.
- Helper methods are used in at least Stage 4 and Stage 7 behind fallback
  behavior.

## D1: WorkerBoundaryPlanner Migration

### Affected Files

- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py`
- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/prompt_builder.py`
- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/materializer.py`

### Goal

Prevent non-executable semantic material from becoming worker task candidates.

### Tasks

1. Candidate extraction should use executable behavior candidates.
2. Failure condition annotations should appear as flow context, not worker task
   candidates.
3. Delegation intent annotations should inform boundary planning but not create
   executable workers without contracts.
4. Ownership logic should support condition spans for exception-flow placement.

### Acceptance Criteria

- Failure mode spans are not proposed as worker task units.
- Delegation policy without contract does not create executable child worker.
- Worker ownership can still preserve exception condition provenance.

## D2: FlowAssembler Route-Driven Exception Materialization

### Affected Files

- `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/flow_parser.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/span_filter.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py`
- `src/nl2spl/pipeline/fact_bridges.py`
- `src/nl2spl/pipeline/orchestrator.py`

### Goal

Move failure materialization from bridge-first behavior to route-driven flow
construction.

### Tasks

1. Add a materializer that consumes:
   - `construct_target = EXCEPTION_FLOW`;
   - `slot_target = condition`;
   - `semantic_role = failure_mode`.
2. Append partial `ExceptionFlow` skeletons after LLM flow parsing and before
   Stage 4 output is finalized.
3. Dedupe with LLM-generated exception flows by normalized condition text.
4. Preserve condition span ids.
5. Keep `bridge_failure_modes()` as a compatibility wrapper during this phase.
6. Update orchestrator so bridge-first materialization is guarded by
   "annotations missing" fallback logic.

### Acceptance Criteria

- Failure modes materialize from route annotations.
- Missing handler diagnostics still appear.
- No duplicate exception flow for the same condition.
- Legacy route-driven failure tests pass.
- Existing bridge tests are migrated or wrapped around the new materializer.

## D3: Worker-Aware Exception Flow Migration

### Affected Files

- `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/span_filter.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage10_worker_assembler/assembler.py`
- `src/nl2spl/pipeline/stages/stage10_worker_assembler/child_worker_builder.py`

### Goal

Make route-derived exception flows work when worker boundary planning is
enabled.

### Tasks

1. Assign exception condition spans to the correct worker flow.
2. If ownership is ambiguous, attach to main worker or emit a diagnostic based
   on worker plan rules.
3. Preserve route-derived exception flows through worker-scoped block assembly.
4. Render main and child worker partial exception flows.

### Acceptance Criteria

- `enable_worker_boundary_planner=True` still produces partial exception flows.
- Child worker exception flows render when condition spans belong to child
  workers.
- No route-derived failure mode is silently dropped.

## D4: BlockAssembler Partial Skeleton Support

### Affected Files

- `src/nl2spl/pipeline/stages/stage5_block_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/prompt_enricher.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/block_postprocess.py`

### Goal

Ensure condition-only exception flows remain renderable as partial SPL.

### Tasks

1. Detect exception flows that have condition spans but no handler blocks.
2. Keep them as legal partial structures.
3. Avoid inventing handler blocks.
4. Add deterministic fallback only if renderer requires a block container.

### Acceptance Criteria

- Condition-only `EXCEPTION_FLOW` renders as partial skeleton.
- No synthetic handler step is created.
- Stage 9.5 emits or preserves `missing_handler`.

## D5: Resource, Profile, and Constraint Consumers

### Affected Files

- `src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/context_builder.py`
- `src/nl2spl/pipeline/stages/stage8_profile_extractor.py`
- `src/nl2spl/pipeline/stages/stage9_constraint_extractor.py`

### Goal

Teach context-building stages to consume route annotations without confusing
semantic material.

### Tasks

1. Resource extractor:
   - use input/output hard facts as authoritative resources;
   - do not extract route metadata as variables;
   - do not treat failure conditions as resources unless resources are
     explicitly mentioned.
2. Profile extractor:
   - prefer profile/domain annotations where present;
   - keep old route lists as fallback.
3. Constraint extractor:
   - consume constraint annotations;
   - treat delegation boundaries as constraints only when they express boundary
     rules;
   - do not treat failure mode conditions as policies unless text says so.

### Acceptance Criteria

- Inputs and outputs remain resource contracts.
- Failure modes do not become variables or constraints by default.
- Policy extraction still works.
- Delegation boundary constraints remain available.

## D6: StepExtractor Executable Filtering

### Affected Files

- `src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py`

### Goal

Prevent non-executable route material from becoming commands.

### Tasks

1. Use `routes.get_executable_behavior_span_ids()` for step prompts.
2. Exclude annotations with `executable=false`.
3. Do not emit unmapped behavior diagnostics for excluded non-executable
   annotations.
4. Keep handoff-generated `INVOKE_WORKER` and `CALL_API` contract-driven.
5. Ensure `REQUEST_INPUT` is generated only from explicit ask/request source
   evidence.

### Acceptance Criteria

- `Missing timeframe` never becomes `GENERAL_COMMAND`.
- Delegation intent without contract never becomes `INVOKE_WORKER`.
- Normal process steps still become step candidates.
- Worker-scoped Stage 7 follows the same rule.

## D7: Normalizer, Gate, Renderer, and Provenance

### Affected Files

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalizer.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py`
- `src/nl2spl/pipeline/executable_gate.py`
- `src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py`
- `src/nl2spl/pipeline/provenance.py`
- `src/nl2spl/compiler/report_renderer.py`
- `src/nl2spl/compiler/feedback_report_renderer.py`
- `src/nl2spl/compiler/diagnostic_analyzer.py`

### Goal

Keep partial SPL and diagnostics correct after route-driven materialization.

### Tasks

1. Normalizer:
   - diagnose missing handlers for route-derived exception flows;
   - keep pseudo-handler detection;
   - avoid inventing handler steps.
2. Gate:
   - continue blocking non-source-backed steps;
   - preserve missing-handler diagnostics after assumed handlers are filtered.
3. Renderer:
   - render partial exception skeletons for main and child workers.
4. Provenance:
   - trace route-derived flows to section, packet, and span evidence.
5. Reports:
   - show route-derived diagnostics and provenance.

### Acceptance Criteria

- Route-derived exception flows have provenance.
- Missing-handler diagnostics are not duplicated.
- Partial SPL renders consistently.
- Readable report names the failure section/packet when available.

## D8: Bridge Deprecation and Deletion

### Affected Files

- `src/nl2spl/pipeline/fact_bridges.py`
- `src/nl2spl/pipeline/orchestrator.py`
- bridge-focused tests

### Goal

Remove bridge-first semantics from production paths.

### Tasks

1. Convert `bridge_failure_modes()` into a compatibility wrapper:

```text
hard facts
-> synthesize route annotations if missing
-> call route-driven exception materializer
```

2. Convert `bridge_delegation_intents()` into a compatibility diagnostic wrapper
   or replace it with route-driven delegation diagnostics.
3. Remove orchestrator bridge-first calls.
4. Delete wrappers only after all route-driven tests pass.

### Acceptance Criteria

- No production path depends on bridge-first failure materialization.
- Bridge wrappers are deleted or marked deprecated with no primary call sites.
- Tests use route-driven materialization as the canonical path.

## Recommended Execution Sequence

Execute frontend first:

```text
F0 -> F1 -> F2 -> F3 -> F4
```

Then downstream:

```text
D0 -> D1 -> D2 -> D6 -> D4 -> D3 -> D5 -> D7 -> D8
```

Reason for this order:

- D1 protects worker planning before failure modes become flow-relevant.
- D2 creates route-driven exception flows.
- D6 prevents command fabrication before broader downstream consumption.
- D4 ensures partial exception flows remain renderable.
- D3 then extends the same behavior to worker-aware flows.
- D5 migrates resource/profile/constraint consumers.
- D7 consolidates diagnostics, rendering, and provenance.
- D8 removes bridges only after the new path is stable.

## Downstream Completion Gate

Downstream migration is complete when:

- Stage 4 materializes exception flows from route annotations.
- Stage 7 consumes only executable behavior annotations.
- Worker-aware and legacy paths both preserve route-derived failure modes.
- Inputs/outputs remain resource contracts.
- Delegation intents do not render executable invocations without valid
  handoff contracts.
- Provenance traces section, packet, and span evidence.
- `bridge_failure_modes()` and `bridge_delegation_intents()` are no longer
  primary production mechanisms.

