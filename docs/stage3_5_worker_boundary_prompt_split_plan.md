# Stage 3.5 Worker Boundary Prompt Split Plan

Date: 2026-05-13

Status: implementation planning

Related documents:

- `docs/multi_worker_system_design.md`
- `docs/migration-worker-aware-pipeline.md`
- `docs/prompt_design_document.md`
- `docs/nl_2_spl_input_adapter_design.md`

## 1. Problem Statement

The current Stage 3.5 WorkerBoundaryPlanner asks one LLM call to perform four coupled tasks:

1. discover possible worker candidate task units;
2. accept or reject each candidate;
3. materialize concrete `WorkerSpecIR` objects;
4. materialize `WorkerHandoffIR` invocation edges.

This makes the output contract brittle. A recent run failed with:

```text
WorkerPlanIR validation failed:
Accepted child decision must match exactly one non-main worker:
candidate_bounded_sourcing, found 0.
```

The failure means the model accepted a candidate as `extract_child_worker`, but did not emit a matching concrete non-main worker. This is a contract consistency failure, not a renderer or Stage 4 issue.

The root cause is that Stage 3.5 currently asks the model to both decide and materialize a graph in one step. The graph-level invariants are too strict to rely on a single free-form structured generation.

## 2. Design Goal

Split Stage 3.5 into three smaller sub-stages with explicit handoff contracts:

```text
Stage 3.5a CandidateTaskUnitExtractor
    spans/routes/adapter hints -> CandidateTaskUnitIR[]

Stage 3.5b WorkerBoundaryDecisionPlanner
    candidates + compact context -> WorkerBoundaryDecisionIR[]

Stage 3.5c WorkerPlanMaterializer
    decisions + candidates + hard facts -> WorkerPlanIR

Stage 3.6 WorkerPlanValidator
    WorkerPlanIR -> validation result
```

The key principle:

```text
candidate discovery != boundary decision != worker graph materialization
```

The model may assist each step, but graph materialization should be as deterministic as possible. If an accepted decision cannot be materialized into a valid worker and handoff, the implementation must reject or repair that decision before Stage 3.6, instead of emitting an invalid `WorkerPlanIR`.

## 3. Non-Goals

- Do not make Stage 3.5 depend on raw input section names such as `Reusable process` or `Failure handling`.
- Do not let Stage 3.5 create `FlowStructureIR`, `BlockStructureIR`, `StepIR`, `ConstraintIR`, or SPL.
- Do not turn every delegation hint into a worker.
- Do not use child workers as fallback for uncertain flow/block classification.
- Do not remove the existing single-call Stage 3.5 path immediately; use it as a compatibility fallback during migration.

## 4. Required Inputs

All three sub-stages should consume compiler-level IR or adapter-normalized hints, not raw section-specific logic.

Common available inputs:

- resolved `SpanIR[]`
- `FieldRouteIR`
- optional `CanonicalCompileInput`
- adapter `semantic_packets`
- adapter `compile_hints`
- hard fact input/output variables
- prior ambiguity resolution output

Important boundary:

```text
InputAdapter may provide section-aware hints.
Stage 3.5 may consume those hints only through generic packet/hint fields.
Stage 3.5 must not encode structural_nl section names as compiler rules.
```

## 5. Stage 3.5a: CandidateTaskUnitExtractor

### 5.1 Responsibility

Discover possible task units that may later become workers.

This stage answers:

```text
What groups of behavior spans might form callable responsibility units?
```

It does not answer:

```text
Should this become a child worker?
```

### 5.2 Inputs

- behavior spans only for ownership candidates;
- relevant rule/integration/domain spans as context;
- adapter hints as generic signals;
- hard fact input/output names for contract seeding context.

### 5.3 Output

`CandidateTaskUnitIR[]`

Each candidate should include:

- `candidate_id`
- `candidate_kind`
- `span_ids`
- `responsibility_text`
- `signals`
- `risks`
- `possible_inputs`
- `possible_outputs`
- `possible_invocation_context`
- `evidence`

### 5.4 Hard Rules

- Candidate span ownership is not final worker ownership.
- A candidate may be weak or later rejected.
- A candidate must not contain flow/block/step structure.
- A candidate must not materialize `WorkerSpecIR`.
- Candidate ids must be stable and deterministic where possible:
  - prefer `candidate_<slug>` from responsibility;
  - de-duplicate with numeric suffix.

### 5.5 Prompt Contract

The prompt should focus on discovery only:

```text
List possible callable task units.
Do not decide whether they become workers.
Do not generate workers.
Do not generate handoffs.
Include risks when the boundary is weak.
```

### 5.6 Deterministic Post-Processing

After the LLM returns candidates:

- remove candidates with no behavior spans;
- normalize ids;
- normalize enum values;
- remove duplicate candidates with identical span sets and responsibility;
- keep rejected/weak candidates for diagnostics, but mark them as `risk-heavy`.

## 6. Stage 3.5b: WorkerBoundaryDecisionPlanner

### 6.1 Responsibility

Accept or reject each candidate using hard requirements.

This stage answers:

```text
Should this candidate become a child worker?
```

It does not directly create:

- `WorkerSpecIR`
- `WorkerHandoffIR`
- child flow/block/step structure

### 6.2 Inputs

- normalized `CandidateTaskUnitIR[]`
- behavior span summary
- hard facts
- compile hints
- main worker responsibility seed
- existing risks/signals

### 6.3 Output

`WorkerBoundaryDecisionIR[]`

Each decision should include:

- `candidate_id`
- `decision`
- `boundary_kind`
- `accepted`
- `rejection_reason`
- `hard_requirement_status`
- `required_inputs`
- `required_outputs`
- `parent_invocation_point`
- `result_handoff`
- `failure_policy_hint`
- `reason`

### 6.4 Hard Requirements For Acceptance

A candidate may be accepted only if all are present:

1. responsibility is callable and bounded;
2. input contract can be named;
3. output contract can be named;
4. parent invocation point can be located or described;
5. result handoff to parent is clear;
6. candidate provides independent value;
7. candidate is not merely a policy, alternative flow, exception flow, or ordinary sequential step.

### 6.5 Required Rejection Cases

Reject if any applies:

- no clear input contract;
- no clear output contract;
- no parent invocation point;
- unclear result handoff;
- ordinary sequential step;
- policy or constraint only;
- single API call with no adapter responsibility;
- over-fragmentation;
- simple local control branch;
- candidate duplicates another accepted candidate.

### 6.6 Prompt Contract

The prompt should explicitly say:

```text
You are deciding boundaries, not building workers.
For each candidate, output exactly one decision.
Accepted decisions must include enough structured data for deterministic materialization.
If any hard requirement is missing, reject the candidate.
```

### 6.7 Decision Validator

Before materialization:

- every decision references an existing candidate;
- every candidate has at most one decision;
- accepted decisions have all required fields;
- rejected decisions have a valid rejection reason;
- accepted span sets do not overlap unless explicitly allowed by ownership rules;
- accepted decisions do not cover only rule/domain/input/output hard fact spans.

Invalid accepted decisions should be converted to rejected decisions with warning:

```text
Rejected accepted candidate <id>: missing materialization requirement <field>.
```

This prevents the exact failure where an accepted decision cannot produce a child worker.

## 7. Stage 3.5c: WorkerPlanMaterializer

### 7.1 Responsibility

Build a valid `WorkerPlanIR` from accepted decisions.

This stage answers:

```text
What concrete workers and handoffs exist?
```

### 7.2 Implementation Preference

Use deterministic code first.

The LLM may only fill optional descriptions when the deterministic data is insufficient for readable text. It should not be responsible for id consistency, handoff binding consistency, or worker ownership invariants.

### 7.3 Inputs

- accepted/rejected `WorkerBoundaryDecisionIR[]`
- normalized `CandidateTaskUnitIR[]`
- hard fact inputs/outputs
- behavior spans
- route information
- compile hints

### 7.4 Output

`WorkerPlanIR`

The materializer must produce:

- exactly one main worker;
- zero or more non-main workers;
- one or more handoffs for every accepted child worker;
- rejected candidates preserved for diagnostics;
- decisions preserved for auditability.

### 7.5 Deterministic Main Worker Construction

Main worker:

- `worker_id = "worker_main"` unless already configured;
- `worker_name = "MainWorker"` unless a safe name exists;
- owns all behavior spans not owned by accepted child workers;
- input contract seeded from hard fact inputs;
- output contract seeded from hard fact required outputs;
- constraints are references/hints, not owned behavior spans.

### 7.6 Deterministic Child Worker Construction

For each accepted decision:

- create exactly one child `WorkerSpecIR`;
- derive `worker_id` from accepted decision or candidate id;
- derive SPL-safe `worker_name`;
- set `kind = "child"` unless explicitly `api_adapter`;
- set `owned_span_ids = candidate.span_ids`;
- set input/output contracts from decision first, then candidate possible IO;
- attach constraints as references/hints, not owned spans.

### 7.7 Deterministic Handoff Construction

For each accepted child worker:

- create at least one `WorkerHandoffIR`;
- `from_worker` defaults to `worker_main` unless decision specifies a different caller;
- `to_worker` must be the child worker id;
- `mode = "invoke"` for child worker;
- input bindings map parent variables to child inputs;
- output bindings map child outputs to parent variables;
- invoke location hint uses accepted decision invocation point if valid;
- failure policy uses decision failure policy hint or default propagate policy.

### 7.8 Materialization Repair Rules

If accepted decision cannot be materialized:

1. Missing child input/output contract:
   - attempt deterministic fill from candidate possible IO;
   - if still missing, reject decision.

2. Missing invocation point:
   - allow empty `source_span_ids` with warning only if handoff is otherwise valid;
   - if caller cannot be determined, reject decision.

3. Missing output binding:
   - if child output name equals parent output or known intermediate variable, bind directly;
   - otherwise reject decision.

4. Duplicate child worker for same accepted decision:
   - merge only if span set and responsibility match exactly;
   - otherwise reject lower-confidence or riskier decision.

5. Accepted decision without concrete worker:
   - never pass through to Stage 3.6;
   - either materialize exactly one worker or convert to rejected.

### 7.9 Validator Gate

After materialization, run `WorkerPlanValidator`.

Stage 3.5c must not return invalid `WorkerPlanIR`.

If validation fails:

- try one deterministic repair pass;
- if still invalid, raise `StageError` with candidate/decision ids and failed invariant.

## 8. Transitional Architecture

### 8.1 Compatibility Mode

Add feature flags:

```python
enable_worker_boundary_planner_split: bool = False
enable_worker_boundary_single_call_fallback: bool = True
```

Migration behavior:

```text
if enable_worker_boundary_planner_split:
    run 3.5a -> 3.5b -> 3.5c -> 3.6
else:
    run current single-call 3.5 -> 3.6
```

During rollout, if split mode fails before materialization, the orchestrator may fall back to current single-call Stage 3.5 only when explicitly enabled.

Do not silently fallback after an invalid materialized `WorkerPlanIR`, because that hides contract bugs.

### 8.2 Checkpoints

Persist separate files:

```text
stage3_5a_candidate_task_units.json
stage3_5b_worker_boundary_decisions.json
stage3_5c_worker_plan_materializer.json
stage3_6_worker_plan_validation.json
```

The existing `stage3_5_worker_boundary_planner.json` may continue to store the final `WorkerPlanIR` for backward compatibility, but the detailed debug source should be the new sub-stage files.

### 8.3 Intermediate Results

Add to `PipelineResult.intermediate_results`:

```python
intermediate["stage3_5a_candidates"]
intermediate["stage3_5b_decisions"]
intermediate["stage3_5c_worker_plan"]
intermediate["stage3_6_worker_plan_validation"]
```

Keep:

```python
intermediate["stage3_5_worker_plan"]
```

as alias to the final materialized `WorkerPlanIR` during migration.

## 9. IR Additions And Adjustments

### 9.1 CandidateTaskUnitIR

If current `CandidateTaskUnitIR` already exists, extend only as needed.

Recommended fields:

```python
candidate_id: str
candidate_kind: BoundaryKind | str
span_ids: list[str]
responsibility_text: str
signals: list[Signal]
risks: list[Risk]
possible_inputs: list[ContractFieldIR]
possible_outputs: list[ContractFieldIR]
possible_invocation_context: InvokeLocationHintIR | None
evidence: list[str]
source_hint_ids: list[str]
```

### 9.2 WorkerBoundaryDecisionIR

Recommended additional structured field:

```python
hard_requirement_status: dict[str, bool]
```

Required keys:

```text
responsibility
input_contract
output_contract
invocation_point
result_handoff
independent_value
```

### 9.3 WorkerPlanIR

No major change required. Ensure it stores:

- candidates;
- decisions;
- rejected candidates;
- materialization warnings.

If `rejected_candidates` remains separate from `decisions`, add invariant:

```text
rejected_candidates must be a subset of decisions where decision != extract_child_worker.
```

## 10. Prompt Files

Create:

```text
prompts/stage3_5a_candidate_extractor_system.txt
prompts/stage3_5b_boundary_decision_system.txt
prompts/stage3_5c_materializer_system.txt
```

Existing:

```text
prompts/stage3_5_system.txt
```

remains for compatibility mode.

### 10.1 Stage 3.5a Prompt Focus

- find possible callable units;
- keep weak candidates;
- mark risks;
- no final worker decisions;
- no workers;
- no handoffs.

### 10.2 Stage 3.5b Prompt Focus

- accept/reject candidates;
- apply hard requirements;
- fill structured decision fields;
- reject on missing hard requirements;
- no workers;
- no handoffs.

### 10.3 Stage 3.5c Prompt Focus

Preferred implementation is deterministic. If an LLM prompt is still used:

- only fill descriptions and readable purpose text;
- do not invent candidate ids;
- do not invent span ownership;
- do not invent bindings not grounded in decisions/candidates/hard facts.

## 11. Orchestrator Changes

Add new runner methods:

```python
_run_stage3_5a(...)
_run_stage3_5b(...)
_run_stage3_5c(...)
```

Orchestrator flow:

```python
if config.enable_worker_boundary_planner_split:
    candidates = _run_stage3_5a(...)
    decisions = _run_stage3_5b(..., candidates)
    worker_plan = _run_stage3_5c(..., candidates, decisions)
else:
    worker_plan = _run_stage3_5(...)

worker_validation = WorkerPlanValidator().validate(worker_plan)
```

Ownership repair after Stage 3.6 must remain behavior-only:

```text
unassigned_behavior_spans = routes.behavior - owned_behavior_spans
```

Do not assign rule/domain/input/output hard fact spans to worker ownership.

## 12. Error Handling

### 12.1 Recoverable Warnings

- weak candidate rejected;
- accepted candidate repaired into valid worker;
- missing invoke source span but caller can be determined;
- duplicate candidate merged;
- non-behavior span ignored for ownership.

### 12.2 Blocking Errors

- accepted decision cannot be materialized;
- child worker has no handoff;
- handoff references missing worker;
- duplicate behavior span ownership;
- accepted child output has no binding;
- graph has no main worker;
- graph has more than one main worker.

### 12.3 Required Behavior For The Known Failure

For:

```text
Accepted child decision must match exactly one non-main worker:
candidate_bounded_sourcing, found 0.
```

Split mode should produce one of two outcomes before Stage 3.6:

```text
Outcome A:
    materialize worker_bounded_sourcing + handoff

Outcome B:
    reject candidate_bounded_sourcing with reason:
    unclear_result_handoff / no_clear_output_contract / no_parent_invocation_point
```

It must not emit:

```text
accepted decision + no matching concrete worker
```

## 13. Test Plan

### 13.1 Unit Tests

Candidate extractor:

- finds bounded sourcing candidate from behavior spans;
- keeps weak candidate with risks;
- does not emit workers or handoffs;
- ignores rules-only candidate as worker candidate or marks high risk.

Decision planner:

- accepts candidate with full hard requirements;
- rejects candidate missing output contract;
- rejects ordinary sequential step;
- rejects policy-only candidate;
- returns exactly one decision per candidate.

Materializer:

- accepted decision produces exactly one child worker;
- accepted decision produces handoff to child worker;
- accepted decision missing IO is rejected or repaired deterministically;
- main worker owns remaining behavior spans;
- hard fact inputs/outputs seed main contract;
- no non-behavior span is forced into ownership.

Validator integration:

- accepted decision without concrete worker cannot pass;
- child worker without handoff cannot pass;
- duplicate behavior span ownership fails;
- output binding mismatch fails.

### 13.2 Regression Tests

Use the enterprise procurement sample:

- bounded sourcing candidate can be discovered;
- accepted bounded sourcing decision materializes a child worker;
- no `candidate_bounded_sourcing found 0` error;
- non-behavior spans do not trigger unassigned ownership warning;
- child worker steps do not render in MainWorker;
- multi-output invoke is aggregated or otherwise rendered without output loss.

Use internal-comms sample:

- source gathering candidate can be discovered;
- revision remains normal flow/alternative flow depending Stage 4, not forced worker;
- delegation hints do not directly become workers without hard requirements.

### 13.3 Golden Tests

Add fixtures under:

```text
tests/fixtures/multi_worker/stage3_5_split/
```

Recommended cases:

```text
01_no_worker_simple_sequence
02_explicit_bounded_sourcing
03_weak_subtask_no_output
04_policy_only_delegation
05_candidate_accepted_materialized
06_candidate_accepted_missing_worker_repaired
07_candidate_accepted_unrepairable_rejected
08_duplicate_candidate_spans
```

## 14. Rollout Plan

### Phase 0: Contract Preparation

- add any missing fields to candidate/decision IR;
- add serialization tests;
- add validators for candidates and decisions;
- no orchestrator behavior change.

### Phase 1: Stage 3.5a Candidate Extraction

- implement extractor;
- persist checkpoint;
- add tests;
- do not use output downstream yet.

### Phase 2: Stage 3.5b Decision Planning

- implement decision planner;
- validate decisions;
- add tests;
- still do not replace current Stage 3.5.

### Phase 3: Stage 3.5c Materializer

- implement deterministic materializer;
- generate `WorkerPlanIR`;
- run `WorkerPlanValidator`;
- add repair/reject behavior for accepted-but-unmaterializable decisions.

### Phase 4: Orchestrator Feature Flag

- add `enable_worker_boundary_planner_split`;
- store new intermediate results;
- keep single-call fallback available but disabled for strict validation tests.

### Phase 5: A/B Regression

Run both planners on existing examples:

- internal-comms;
- enterprise-procedure;
- simple single-worker samples;
- weak subtask samples;
- API call samples.

Compare:

- validation errors;
- number of workers;
- handoff completeness;
- span ownership;
- final SPL structure.

### Phase 6: Default Switch

After split planner is stable:

- make split planner default;
- keep current single-call Stage 3.5 for one release as fallback;
- document deprecation of single-call planner.

## 15. Developer Task Breakdown

### Developer A: IR And Validators

Deliverables:

- candidate validator;
- decision validator;
- optional IR field additions;
- serialization tests;
- invariant docs.

Dependencies:

- none.

### Developer B: Stage 3.5a Candidate Extractor

Deliverables:

- `stage3_5a_candidate_extractor`;
- prompt file;
- checkpoint persistence;
- unit tests.

Dependencies:

- Developer A IR contract.

### Developer C: Stage 3.5b Decision Planner

Deliverables:

- `stage3_5b_boundary_decision_planner`;
- prompt file;
- decision validation;
- rejection tests.

Dependencies:

- Developer A;
- Developer B candidate output.

### Developer D: Stage 3.5c Materializer

Deliverables:

- deterministic materializer;
- repair/reject rules;
- WorkerPlanIR output;
- WorkerPlanValidator integration tests.

Dependencies:

- Developer A;
- Developer C decision output.

### Developer E: Orchestrator Rollout And Regression

Deliverables:

- feature flags;
- orchestrator wiring;
- checkpoint storage;
- A/B tests;
- enterprise-procedure regression.

Dependencies:

- Developer B/C/D complete enough for integrated path.

## 16. Acceptance Criteria

The split Stage 3.5 implementation is acceptable when:

1. Current single-worker examples still produce a valid single-worker plan.
2. Enterprise procurement no longer fails with accepted decision missing concrete worker.
3. Accepted child decisions always materialize exactly one non-main worker or are rejected before Stage 3.6.
4. Every non-main worker has at least one valid handoff.
5. Every accepted child worker has non-empty input and output contracts.
6. Behavior span ownership is complete and non-overlapping.
7. Non-behavior spans are not forced into worker ownership.
8. Stage 4/5/6/7/9.5/10/11 remain worker-aware and do not consume legacy `delegation_candidates` in the production worker-aware path.
9. Split planner checkpoints make candidate, decision, and materialization failures debuggable.
10. Tests cover accepted, rejected, repaired, and unrepairable candidates.

## 17. Key Design Decision

The split is justified because the current failure is a graph materialization consistency failure. Better prompt wording can reduce frequency, but it cannot reliably enforce:

- exactly one child worker per accepted decision;
- valid handoff per child worker;
- complete IO bindings;
- non-overlapping behavior ownership;
- accepted/rejected decision consistency.

Therefore Stage 3.5 should become a small compiler pipeline of its own:

```text
discover candidates -> decide boundaries -> materialize graph -> validate graph
```

This keeps LLM reasoning where it is useful and moves graph invariants into deterministic code where they are enforceable.
