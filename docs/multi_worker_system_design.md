# NL2SPL Multi-Worker System Design

Date: 2026-05-10

Status: detailed implementation design

Related documents:

- `docs/spl_nl_to_spl_design_document_v4.md`
- `docs/multi-worker_design.md`
- `docs/delegation_plan_todo.md`
- `docs/nl_2_spl_input_adapter_design.md`
- `docs/spl_grammar.txt`

## 1. Purpose

This document defines the target architecture for compiling natural language into SPL with multiple `DEFINE_WORKER` blocks. It is intended as code development guidance, not only conceptual design.

The current implementation can render child workers through `FlowStructureIR.delegation_candidates`, but that field is a compatibility bridge. It mixes worker-boundary planning with flow classification. The target design introduces a first-class `WorkerPlanIR` before flow assembly.

## 2. Core Position

Multi-worker compilation must follow the coarse-to-fine rule:

1. Decide whether the SPL program needs one or more workers.
2. Define every worker's responsibility and data contract.
3. Define parent-child handoffs and failure policy.
4. Build each worker's internal flow.
5. Build each worker's blocks.
6. Extract resources and steps inside worker boundaries.
7. Assemble and render SPL.

Worker boundaries must not be inferred only from words like `subtask`, `delegate`, or from invalid nested block structures. Those are signals, not final decisions.

The canonical boundary rule is:

> A child worker should be generated only when a group of behavior spans forms a callable responsibility unit with clear inputs, outputs, invocation point, failure policy, and independent value.

## 3. Goals And Non-Goals

### 3.1 Goals

- Represent multiple SPL workers before `FlowStructureIR`.
- Prevent undefined child workers, unused child workers, and unresolved `INVOKE_WORKER`.
- Make child worker IO contracts explicit and checkable.
- Support explicit delegation in input text.
- Support passive discovery of unrepresentable control regions without blindly converting them into workers.
- Preserve span provenance from raw input to worker, flow, block, step, and rendered SPL.
- Keep current single-worker behavior stable.
- Provide a staged migration path from `delegation_candidates` to `WorkerPlanIR`.

### 3.2 Non-Goals

- Do not use child workers to hide invalid or uncertain structure.
- Do not turn every API call into a worker.
- Do not treat every exception flow as a worker.
- Do not require all structured inputs to mention workers explicitly.
- Do not remove the current compatibility bridge in the first implementation phase.

### 3.3 Design Decisions

These decisions are part of the target design and should be treated as defaults during implementation:

- Persist WorkerBoundaryPlanner output as `stage3_5_worker_boundary_planner.json`.
- Run `WorkerPlanValidator` immediately after WorkerBoundaryPlanner as Stage 3.6.
- Use wrapper IRs for worker-scoped flows and blocks to make checkpoints, validation, and debugging explicit.
- Render `api_adapter` as a normal SPL `DEFINE_WORKER`; preserve adapter semantics only in IR.
- Treat required child output mismatch as an error.
- Run WorkerBoundaryPlanner before Stage 4.
- Let Stage 5 report concrete control complexity regions as structural feedback to the normalizer.

## 4. Definitions

### 4.1 Main Worker

The main worker is the top-level callable unit of the SPL program. It owns the end-to-end user-facing process and final outputs.

### 4.2 Child Worker

A child worker is a callable task unit invoked by another worker through `INVOKE_WORKER`. It must have:

- `purpose`
- `input_contract`
- `output_contract`
- `owned_span_ids`
- at least one parent handoff

### 4.3 API Adapter Worker

An API adapter worker is a special child worker used only when an external integration needs multi-step handling, such as retry, pagination, filtering, normalization, provenance, or cross-API aggregation.

Single API calls should remain `CALL_API`.

### 4.4 Candidate Task Unit

A candidate task unit is a potential worker boundary discovered from input spans. It is not yet a worker.

### 4.5 Control Complexity Region

A control complexity region is a group of spans whose implied control structure may not be representable by current SPL block grammar in a single worker. It is a repair signal, not automatically a delegation signal.

### 4.6 Worker Ownership Model

Worker ownership is a global invariant used by FlowAssembler, BlockAssembler, StepExtractor, ConstraintExtractor, and coverage validation.

Rules:

1. A behavior span must have exactly one owning worker.
2. A policy or rule span may be referenced by multiple workers through constraints.
3. A domain or concept span is global unless explicitly tied to one worker.
4. Input and output declaration spans seed contracts; they do not imply behavior ownership.
5. A handoff does not transfer span ownership; it transfers data.
6. Child-owned behavior spans must not generate main-worker steps.
7. Shared constraint references must be represented as constraint links, not duplicate behavior ownership.

The main engineering risk this model prevents is duplicate step generation, where the main worker and a child worker both compile the same behavior span into commands.

## 5. Worker Boundary Rules

### 5.1 Hard Requirements

A child worker can be accepted only if all hard requirements are satisfied:

| Requirement | Meaning |
|---|---|
| responsibility | The candidate has one coherent job. |
| input contract | Required input values are identifiable or can be produced by parent steps. |
| output contract | Outputs are identifiable and used by the parent or final SPL. |
| invocation point | The parent has a clear place and condition to invoke the worker. |
| result handoff | The child result can be bound back to parent variables. |

If any hard requirement is missing, the candidate must be rejected or kept in the main worker.

### 5.2 Positive Signals

Positive signals increase the chance of child worker extraction:

- Explicit wording: `delegate`, `subtask`, `child worker`, `invoke worker`, `separate worker`.
- Multi-step process with bounded IO.
- Reusable process that may be called from multiple parent locations.
- Independent failure or recovery policy.
- External source gathering with evidence normalization.
- Provenance/audit maintenance.
- Template matching or format protocol with structured outputs.
- Loop body with complex per-item protocol.
- Control structure that cannot be expressed without loss inside a single worker.

### 5.3 Negative Signals

These cases should remain in the current worker by default:

- Ordinary sequential process.
- Simple `IF`, `FOR`, or `WHILE`.
- Revision flow, unless explicitly delegated or complex enough to be independently contracted.
- Failure handling, unless the recovery protocol itself is multi-step and independently contracted.
- Single API call.
- Simple clarification question.
- Policy, constraint, or gate.
- Candidate without clear parent invocation point.
- Candidate generated only to bypass grammar restrictions.

### 5.4 Conservative Default

The default planner mode is `conservative`.

In conservative mode, keep logic in the main worker unless the candidate satisfies hard requirements and has at least one strong positive signal.

Optional future modes:

- `balanced`: allow moderate candidates with strong IO and testability.
- `aggressive`: split more candidates for modularity, mainly for experimentation.

## 6. Target Pipeline

### 6.1 Current Pipeline

The current pipeline is:

```text
Stage 1: SpanSlicer
Stage 2: FieldRouter
Stage 3: AmbiguityResolver
Stage 4: FlowAssembler
Stage 5: BlockAssembler
Stage 6: ResourceExtractor
Stage 7: StepExtractor
Stage 8: ProfileExtractor
Stage 9: ConstraintExtractor
Stage 9.5: IRNormalizer
Stage 10: WorkerAssembler
Stage 11: SPLRenderer
```

Current delegation is carried by `FlowStructureIR.delegation_candidates`.

### 6.2 Target Pipeline

The target pipeline is:

```text
Stage 1: SpanSlicer
Stage 2: FieldRouter
Stage 3: AmbiguityResolver

Stage 3.5: WorkerBoundaryPlanner
    output: WorkerPlanIR

Stage 3.6: WorkerPlanValidator
    output: validated WorkerPlanIR + diagnostics

Stage 4: WorkerAwareFlowAssembler
    output: WorkerFlowPlanIR

Stage 5: WorkerAwareBlockAssembler
    output: WorkerBlockPlanIR

Stage 6: ResourceExtractor
    input: WorkerPlanIR + worker-scoped flows/blocks

Stage 7: WorkerAwareStepExtractor
    input: WorkerPlanIR + handoffs + worker-scoped flows/blocks + symbols

Stage 8: ProfileExtractor
Stage 9: ConstraintExtractor

Stage 9.5: WorkerAwareIRNormalizer
    validates worker graph, handoffs, symbols, and block legality

Stage 10: WorkerAssembler
    builds WorkerIR from WorkerPlanIR

Stage 11: SPLRenderer
```

### 6.3 Migration Pipeline

During migration, `WorkerPlanIR` may be adapted into `FlowStructureIR.delegation_candidates` so existing Stage 7, Stage 9.5, and Stage 10 code can keep working.

This adapter is temporary. Production code should eventually stop reading `FlowStructureIR.delegation_candidates`.

### 6.4 Stage 3.6 WorkerPlanValidator

`WorkerPlanValidator` runs immediately after WorkerBoundaryPlanner. Its purpose is to prevent an invalid worker graph from contaminating flow, block, step, and resource stages.

Inputs:

- `WorkerPlanIR`
- resolved spans
- `FieldRouteIR`
- optional canonical input adapter facts

Validation:

- exactly one main worker
- `main_worker_id` exists
- worker ids are unique
- worker names are unique and SPL-safe
- every non-main worker has at least one handoff
- every handoff source and target exists when `mode="invoke"`
- every invoke handoff target is non-main unless self-invocation is explicitly supported later
- every accepted child worker has non-empty input and output contracts
- every behavior span has at most one owning worker
- all `owned_span_ids` exist
- rejected candidates are not included in `workers`
- no handoff references a rejected candidate
- `decisions` and `rejected_candidates` are internally consistent
- `api_call` handoffs do not pretend to target a worker

Stage 9.5 still performs full-program validation after steps and resources exist. Stage 3.6 validates the worker graph before downstream structural assembly.

## 7. New IR Design

All IR classes should live under `src/nl2spl/ir/`.

### 7.0 Shared Enumerations

The IR should use constrained literal values instead of free-form strings where downstream stages need deterministic behavior.

```python
BoundaryKind = Literal[
    "explicit_delegation",
    "bounded_subtask",
    "integration_wrapper",
    "complex_control_extraction",
    "loop_body_worker",
    "failure_recovery_protocol",
    "template_or_format_protocol",
    "main_worker",
    "not_a_worker",
]

Signal = Literal[
    "explicit_delegation",
    "bounded_io",
    "multi_step_process",
    "independent_failure_policy",
    "external_integration",
    "provenance_or_audit",
    "evidence_normalization",
    "reuse_potential",
    "testability",
    "complex_control",
]

Risk = Literal[
    "no_clear_input_contract",
    "no_clear_output_contract",
    "no_parent_invocation_point",
    "single_api_call",
    "ordinary_sequential_step",
    "policy_or_constraint",
    "alternative_flow",
    "exception_flow",
    "over_fragmentation",
    "unclear_result_handoff",
    "insufficient_semantic_boundary",
]
```

### 7.1 CandidateTaskUnitIR

Purpose: expose possible worker boundaries before making final decisions.

```python
@dataclass
class CandidateTaskUnitIR:
    candidate_id: str
    source_span_ids: list[str]
    task_text: str
    purpose: str
    candidate_kind: BoundaryKind
    possible_inputs: list[ContractFieldIR]
    possible_outputs: list[ContractFieldIR]
    signals: list[Signal]
    risks: list[Risk]
```

Notes:

- This IR is allowed to contain weak or rejected candidates.
- It must keep source spans.
- It must not contain flow/block/step structure.

### 7.2 ControlComplexityRegionIR

Purpose: record potentially unrepresentable nested control.

```python
@dataclass
class ControlComplexityRegionIR:
    region_id: str
    source_span_ids: list[str]
    outer_control: Literal["SEQUENTIAL", "IF", "FOR", "WHILE", "unknown"]
    inner_control: Literal["IF", "FOR", "WHILE", "multiple", "unknown"]
    description: str
    discovery_phase: Literal["predicted", "confirmed"]
    severity: Literal["info", "warning", "error"]
    can_flatten: bool
    can_merge_condition: bool
    can_lift_guard: bool
    suggested_repairs: list[Literal[
        "split_blocks",
        "merge_condition",
        "guard_variable",
        "extract_child_worker",
        "compress_to_command",
        "raise_validation_error",
    ]]
```

Rules:

- WorkerBoundaryPlanner may emit predicted control complexity regions from natural-language signals.
- BlockAssembler may emit confirmed control complexity regions from worker-scoped flow/block structure.
- The normalizer reconciles predicted and confirmed regions.
- This IR does not automatically create a child worker.
- Child worker extraction requires WorkerBoundaryPlanner or normalizer approval.
- `info` means the region can be flattened or condition-merged without semantic loss.
- `warning` means guard-variable or command compression may cause minor semantic loss.
- `error` means the structure cannot be expressed losslessly and no valid child worker boundary exists yet.

### 7.3 WorkerBoundaryDecisionIR

Purpose: document accepted and rejected candidate decisions.

```python
@dataclass
class WorkerBoundaryDecisionIR:
    candidate_id: str
    decision: Literal[
        "extract_child_worker",
        "keep_in_main_worker",
        "compile_as_call_api",
        "compile_as_constraint",
        "compile_as_exception_flow",
        "compile_as_alternative_flow",
        "needs_repair_or_warning",
    ]
    boundary_strength: Literal["strong", "moderate", "weak"]
    boundary_kind: BoundaryKind
    rejection_reason: Risk | None
    reason: str
    evidence: list[Signal]
```

Use `boundary_strength`, not numeric confidence. Numeric confidence is not calibrated enough to drive compilation.

### 7.4 ContractFieldIR

Purpose: represent worker input/output variables before they are merged into the global symbol table.

```python
@dataclass
class ContractFieldIR:
    name: str
    data_type: str
    required: bool
    description: str
    source: Literal["input", "output", "state", "derived"]
```

### 7.5 WorkerSpecIR

Purpose: represent a concrete worker.

```python
@dataclass
class WorkerSpecIR:
    worker_id: str
    worker_name: str
    kind: Literal["main", "child", "api_adapter"]
    purpose: str
    owned_span_ids: list[str]
    input_contract: list[ContractFieldIR]
    output_contract: list[ContractFieldIR]
    depends_on: list[str]
    constraints: list[str]
    boundary_kind: BoundaryKind
    decision_evidence: list[Signal]
    reason: str
```

Rules:

- There is exactly one `kind="main"` worker.
- Every child or api adapter worker must have at least one handoff.
- `worker_name` must be renderable as SPL `WORKER_NAME`.
- `output_contract` represents outputs exposed to the parent through handoffs.
- Internal child variables are not contract outputs and must not leak into parent scope.

### 7.6 InputBindingIR And OutputBindingIR

Purpose: represent handoff data movement with required/optional semantics.

```python
@dataclass
class InputBindingIR:
    parent_variable: str
    child_input: str
    required: bool
    default_value: str | None = None

@dataclass
class OutputBindingIR:
    child_output: str
    parent_variable: str
    required: bool
    merge_strategy: Literal["set", "append", "merge_struct", "ignore_if_empty"]
```

MVP implementations may serialize these as simple dictionaries while the downstream migration is incomplete, but the target IR should use structured binding objects. Required output binding mismatch is an error.

### 7.7 WorkerHandoffIR

Purpose: represent parent-to-child invocation.

```python
@dataclass
class WorkerHandoffIR:
    handoff_id: str
    from_worker: str
    to_worker: str | None
    api_ref: str | None
    mode: Literal["invoke", "api_call"]
    condition_text: str | None
    ordering: Literal["before", "after", "conditional", "loop_body"]
    input_bindings: list[InputBindingIR]
    output_bindings: list[OutputBindingIR]
    invoke_location_hint: InvokeLocationHintIR
    failure_policy: HandoffFailurePolicyIR
```

Mode rules:

- `mode="invoke"` means `to_worker` must reference a `WorkerSpecIR`. It is used for normal child workers and `api_adapter` workers.
- `mode="api_call"` means the parent directly emits `CALL_API`; `api_ref` must be set and `to_worker` must be `None`.
- Invoking an `api_adapter` worker still uses `mode="invoke"`, because the parent is invoking a worker, not directly calling an API.

### 7.8 InvokeLocationHintIR

```python
@dataclass
class InvokeLocationHintIR:
    flow_kind: Literal["main", "alternative", "exception"]
    flow_id: str | None
    after_span_id: str | None
    before_span_id: str | None
    block_hint: Literal["sequential", "if", "for", "while", "unknown"]
```

Purpose: prevent StepExtractor from guessing where to place `INVOKE_WORKER`.

### 7.9 HandoffFailurePolicyIR

```python
@dataclass
class HandoffFailurePolicyIR:
    policy_kind: Literal[
        "propagate_exception",
        "ask_user",
        "continue_with_assumption",
        "block_finalization",
        "return_empty_result",
        "custom",
    ]
    description: str
    source_span_ids: list[str]
```

### 7.10 WorkerPlanIR

```python
@dataclass
class WorkerPlanIR:
    main_worker_id: str
    workers: list[WorkerSpecIR]
    handoffs: list[WorkerHandoffIR]
    candidates: list[CandidateTaskUnitIR]
    decisions: list[WorkerBoundaryDecisionIR]
    rejected_candidates: list[WorkerBoundaryDecisionIR]
    control_complexity_regions: list[ControlComplexityRegionIR]
    unassigned_span_ids: list[str]
    warnings: list[str]
```

Rules:

- `main_worker_id` must refer to a worker in `workers`.
- Every non-main worker must be referenced by at least one handoff.
- Every invoke handoff target must exist.
- A child worker cannot own spans that are also owned by another child worker unless explicitly marked as shared constraint spans.
- Policy spans may be referenced by multiple workers through `constraints`, but behavior spans should have a single owner.
- `decisions` contains all boundary decisions.
- `rejected_candidates` is a derived convenience list where `decision != "extract_child_worker"`.
- Every item in `rejected_candidates` must also appear in `decisions`.
- No item with `decision="extract_child_worker"` may appear in `rejected_candidates`.

### 7.11 WorkerFlowPlanIR

Purpose: checkpoint and validate worker-scoped flow structures.

```python
@dataclass
class WorkerScopedFlowIR:
    worker_id: str
    flow: FlowStructureIR

@dataclass
class WorkerFlowPlanIR:
    worker_flows: dict[str, FlowStructureIR]
    warnings: list[str]
```

The wrapper is preferred over a raw dictionary because it gives persistence, schema validation, and diagnostics a stable envelope.

### 7.12 WorkerBlockPlanIR

Purpose: checkpoint and validate worker-scoped block structures plus structural control findings.

```python
@dataclass
class WorkerBlockPlanIR:
    worker_blocks: dict[str, BlockStructureIR]
    control_complexity_regions: list[ControlComplexityRegionIR]
    warnings: list[str]
```

## 8. WorkerBoundaryPlanner

### 8.1 Stage Location

`WorkerBoundaryPlanner` runs after Stage 3 and before Stage 4.

It consumes:

- resolved spans
- field routes
- compact original text or input adapter section metadata
- optional previous run diagnostics

It outputs:

- `WorkerPlanIR`

### 8.2 Prompt Responsibilities

The planner prompt should ask the model to:

1. Identify candidate task units.
2. Identify control complexity regions.
3. Decide which candidates become workers.
4. Reject weak candidates explicitly.
5. Produce worker contracts and handoffs only for accepted workers.

The prompt must not ask for flow blocks, SPL commands, or final SPL.

Highest-priority prompt rule:

> Explicit delegation words and nested-control signals are evidence only. They are not decisions. A candidate becomes a worker only after hard requirements pass.

### 8.3 Code Responsibilities

Code must validate and normalize the model output:

- Ensure exactly one main worker.
- Ensure unique worker ids and names.
- Ensure all accepted child workers have handoffs.
- Ensure every handoff target exists.
- Ensure required contracts are non-empty.
- Ensure rejected candidates are not rendered.
- Ensure behavior-span ownership is unique.
- Ensure `decisions` and `rejected_candidates` are consistent.
- Ensure `invoke` and `api_call` handoffs obey their mode-specific constraints.
- Convert valid child worker plans into compatibility `delegation_candidates` only during migration.

### 8.4 Candidate Discovery Algorithm

The planner should use these signal groups:

1. Explicit delegation signal.
2. Bounded IO signal.
3. Multi-step process signal.
4. Independent failure policy signal.
5. External integration/provenance signal.
6. Complex control signal.
7. Reuse/testability signal.

Candidates are accepted only after hard requirements pass.

### 8.5 Rejection Reasons

The planner must provide one of the `Risk` values as `rejection_reason` when it rejects a candidate. Recommended values:

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

## 9. Nested Control Handling

### 9.1 Grammar Constraint

SPL block grammar does not support nested blocks. `IF`, `FOR`, and `WHILE` bodies contain commands, not blocks.

Therefore:

```text
IF A:
    COMMAND B
    COMMAND C
```

is legal, but:

```text
IF A:
    SEQUENTIAL_BLOCK:
        COMMAND B
```

is not legal under the current grammar.

### 9.2 Repair Order

When nested control is detected, apply repair options in this order:

1. Split surrounding sequential blocks.
2. Merge conditions.
3. Lift condition into a guard variable.
4. Compress inner control into a command if semantic loss is acceptable.
5. Extract child worker if the region has clear IO and invocation semantics.
6. Raise validation error.

Discovery responsibility:

- Stage 3.5 may predict control complexity from natural-language descriptions. This is an early signal.
- Stage 5 may confirm control complexity while assembling worker-scoped blocks. This is a structural finding.
- Stage 9.5 reconciles both sources, applies repairs, or raises validation errors.

Severity handling:

- `info`: repair is lossless through splitting or condition merge.
- `warning`: repair may require guard variable or command compression.
- `error`: no lossless single-worker representation exists and no valid child worker boundary was accepted.

### 9.3 Examples

Flattenable:

```text
Do A. If condition, do B. Then do C.
```

Compile as:

```text
SEQUENTIAL: A
IF condition: B
SEQUENTIAL: C
```

Condition merge:

```text
If sources are needed:
    If sources are available:
        retrieve sources
```

Compile as:

```text
IF sources are needed and available:
    retrieve sources
```

Possible child worker:

```text
For each requested topic:
    validate topic
    if evidence is missing, recover sources
    normalize evidence
```

Compile as:

```text
FOR each topic:
    INVOKE TopicEvidenceWorker
```

## 10. Flow And Block Integration

### 10.1 FlowAssembler

Target input:

- `WorkerPlanIR`
- spans
- routes

Target output:

```python
WorkerFlowPlanIR
```

Each `FlowStructureIR` is scoped to one worker.

Rules:

- FlowAssembler must not decide worker boundaries.
- FlowAssembler may use `WorkerSpecIR.owned_span_ids` to select worker-local behavior spans.
- FlowAssembler must not output `delegation_candidates` in the final architecture.
- During migration, a compatibility adapter may populate `delegation_candidates` from WorkerPlanIR handoffs.

### 10.2 BlockAssembler

Target input:

- `worker_id`
- worker-scoped `FlowStructureIR`
- spans

Target output:

```python
WorkerBlockPlanIR
```

Rules:

- Blocks are top-level inside each flow.
- Blocks do not contain blocks.
- If Stage 5 sees nested control intent, it records `ControlComplexityRegionIR`.
- Stage 5 should not create workers.

## 11. Resource, Step, Constraint Integration

### 11.1 ResourceExtractor

Resource extraction should become worker-aware but still maintain a global symbol table.

Requirements:

- Variables from worker contracts must be pre-registered.
- Child output variables must be visible to parent only through handoff bindings.
- Multi-output handoffs should create structured result types when SPL grammar requires one output variable.
- Internal child variables should not leak into the main worker.
- Contract outputs are the only outputs visible to the parent.
- Internal outputs are worker-local intermediate variables and remain in the child worker scope.

### 11.2 StepExtractor

StepExtractor must use `WorkerPlanIR.handoffs` when generating `INVOKE_WORKER`.

Rules:

- Do not invent child worker names.
- Do not emit placeholder targets like `Worker` or `child_worker`.
- Every `INVOKE_WORKER` must map to a concrete `mode="invoke"` handoff.
- Direct `CALL_API` steps must map to `mode="api_call"` handoffs only when the worker planner chose to model direct API calls in WorkerPlanIR.
- Existing behavior spans owned by a child worker should not also produce main-worker command steps.

### 11.3 ConstraintExtractor

Constraint extraction remains global, but constraints can reference workers through:

- shared source spans
- variable references
- step references after normalization

Do not add a mandatory `scope` field unless later compilation requires it. The current design keeps scope implicit.

### 11.4 IRNormalizer

The normalizer is the main structural enforcement point.

It must validate:

- worker graph consistency
- handoff target existence
- input/output binding validity
- no unresolved `INVOKE_WORKER`
- no child worker without parent invocation
- no child worker output ignored by parent unless explicitly optional
- no nested block in final `BlockStructureIR`
- no duplicate behavior-span ownership across child workers
- no reference to undeclared variables

Unresolved `INVOKE_WORKER` is an error. It must never be downgraded to ordinary `COMMAND`.

## 12. WorkerAssembler And Renderer

### 12.1 WorkerAssembler

Target behavior:

- Build `WorkerIR.child_workers` from `WorkerPlanIR.workers`, not from `FlowStructureIR.delegation_candidates`.
- Use worker contracts for `[INPUTS]` and `[OUTPUTS]`.
- Use worker-scoped flows, blocks, and steps.
- Use handoff bindings to connect parent invocation steps to child outputs.

### 12.2 SPLRenderer

Rendering order:

1. Agent metadata.
2. Persona, audience, concepts, constraints.
3. Variables.
4. Types.
5. Child workers.
6. Main worker.

Renderer must preserve concrete child worker names and must not render unused child workers.

## 13. API Adapter Boundary

Default mapping:

- Single external call: `CALL_API`
- Multi-step integration protocol: `api_adapter` worker

Handoff semantics:

- Direct API call: `WorkerHandoffIR.mode="api_call"`, `api_ref` is set, `to_worker=None`, renderer emits `CALL_API`.
- API adapter worker: `WorkerSpecIR.kind="api_adapter"`, parent handoff uses `mode="invoke"`, `to_worker` references the adapter worker, renderer emits `INVOKE_WORKER`.

Use `api_adapter` only when at least one applies:

- retry/pagination/filtering/sorting
- multi-source aggregation
- provenance maintenance
- evidence normalization
- integration-specific failure recovery
- repeated reuse by multiple workers

## 14. Input Adapter Interaction

The planned input adapter should provide section-aware hints, not final worker decisions.

Recommended adapter outputs relevant to worker planning:

- section id
- section type
- canonical role such as `inputs`, `outputs`, `process`, `policy`, `failure_handling`, `delegation_policy`
- fixed routing hints
- policy/process mixture flags

WorkerBoundaryPlanner should use these hints as evidence.

Examples:

- `Delegation policy` is a strong source for candidate discovery, but may include policy, integrations, and subtasks.
- `Failure handling` should normally inform exception flows or failure policies, not automatically create child workers.
- `Reusable process` may contain both behavior and constraints.

Example adapter packet:

```json
{
  "source_section_id": "sec_delegation_policy",
  "packet_type": "delegation_rule",
  "text": "Source gathering may be delegated if bounded.",
  "compile_targets": [
    "worker.candidate",
    "constraint.delegation_boundary"
  ]
}
```

WorkerBoundaryPlanner may use this packet as `evidence`, but it must still satisfy hard requirements before accepting a child worker.

## 15. Internal-Comms Example

Recommended decisions:

| Text Meaning | Decision |
|---|---|
| determine communication type | keep in main worker |
| identify missing fields | keep in main worker |
| ask clarifying questions | keep in main worker |
| retrieve sources using approved recipes | child worker candidate |
| maintain provenance | child worker candidate or child worker internal step |
| produce draft | keep in main worker |
| user asks for revision | alternative flow, not child worker by default |
| do not finalize if required slots missing | constraint/gate plus loop or decision |
| evidence shortage | exception flow or handoff failure policy |
| optional delegated source gathering | strong delegation signal if IO is bounded |

Source gathering should become a child worker only when the planner can define:

- inputs: request context, connectors/source repositories, source requirements
- outputs: evidence set, provenance log, missing evidence report
- invocation condition: sources are needed and available
- failure policy: propagate evidence shortage or block finalization

## 16. Validation Matrix

| Case | Expected Result |
|---|---|
| no delegation text, simple process | one main worker |
| explicit delegated source gathering with IO | main worker + SourceGatheringWorker |
| explicit subtask without IO | rejected candidate |
| revision request | alternative flow |
| missing timeframe | exception flow or clarification step |
| single API call | CALL_API |
| API call with normalization/provenance | api_adapter or child worker |
| FOR with simple command body | FOR block |
| FOR with inner IF and per-item protocol | child worker if IO exists |
| unresolved INVOKE_WORKER | validation error |
| child worker not invoked | validation error |
| required child output not bound or consumed | validation error |
| optional child output ignored | warning or allowed by `ignore_if_empty` binding |
| multi-output child result | structured type if grammar requires one result variable |

## 17. Rollout Plan

### Phase 1: IR Only

- Add new IR classes.
- Add serialization tests.
- Add `WorkerPlanValidator`.
- No pipeline behavior changes.

### Phase 2: WorkerBoundaryPlanner

- Add Stage 3.5.
- Emit `WorkerPlanIR`.
- Run Stage 3.6 validation immediately after Stage 3.5.
- Keep current pipeline using compatibility adapter.

### Phase 3: Worker-Aware Flow And Block

- Update Stage 4 to optionally consume WorkerPlanIR.
- Update Stage 5 to emit worker-scoped blocks.
- Add `ControlComplexityRegionIR`.

### Phase 4: Worker-Aware Steps And Normalization

- Update StepExtractor to use handoffs.
- Update normalizer to enforce worker graph and handoff validity.
- Keep compatibility bridge only for fixtures that have not migrated.

### Phase 5: WorkerAssembler Migration

- Build child workers from WorkerPlanIR.
- Remove child-worker inference from `delegation_candidates`.
- Ensure structured output typing is based on contracts.

### Phase 6: Remove Compatibility Bridge

- Remove production reads of `FlowStructureIR.delegation_candidates`.
- Update prompts, fixtures, README, and design documents.

## 18. Test Strategy

### 18.1 Unit Tests

- IR dataclass construction and serialization.
- Worker graph validation.
- Handoff validation.
- Rejected candidate preservation.
- Control complexity repair classification.
- Compatibility adapter conversion.

### 18.2 Prompt Contract Tests

- Planner outputs valid schema.
- Planner rejects weak candidates.
- Planner does not emit flow/block/step data.
- Stage 4 does not invent workers.
- Stage 5 does not create workers from nested blocks.

### 18.3 Integration Tests

- Internal-comms source gathering child worker.
- Single-worker simple process.
- Explicit subtask without IO stays rejected.
- Nested control that can be flattened stays single-worker.
- Nested control requiring per-item child worker.
- Unresolved `INVOKE_WORKER` fails.
- Unused child worker fails.

### 18.4 Golden SPL Tests

Golden outputs should verify:

- child worker definitions appear before main worker
- main worker invokes child with concrete name
- child outputs match parent response variables
- no nested block syntax
- `[DEFINE_TYPES:]` appears only when needed

## 19. Open Decisions

These should be resolved during implementation:

1. Whether direct API calls should be represented in WorkerPlanIR at all, or left entirely to StepExtractor unless an `api_adapter` worker is needed.
2. Whether field-level access for structured child results should be added to SPL, or whether parent flows should consume only the structured result variable.
3. Whether self-invocation or recursive worker invocation should be permanently forbidden or introduced later with explicit safeguards.
4. Whether `balanced` and `aggressive` worker planning modes should be implemented, or kept as future design options.
