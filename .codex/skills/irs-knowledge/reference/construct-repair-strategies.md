# Construct-Level Repair Strategy Guidance

Use this reference when an IRS slot is intended to be repairable through SPL
Editing. It defines how IRS repair metadata connects to construct-level repair
strategies without turning IRS into a repair engine.

## Contents

- [Core Boundary](#core-boundary)
- [Strategy Is Not Patch Type](#strategy-is-not-patch-type)
- [Repair Strategy Admission](#repair-strategy-admission)
- [RepairStrategySpec Review](#repairstrategyspec-review)
- [Construct Closure Rules](#construct-closure-rules)
- [Stage-Slice Authority](#stage-slice-authority)
- [Facts and Selectable References](#facts-and-selectable-references)
- [Preview, Confirmation, and Evidence](#preview-confirmation-and-evidence)
- [Verification Contract](#verification-contract)
- [Current Approved MVP Strategies](#current-approved-mvp-strategies)
- [New IRS Slot Decision Procedure](#new-irs-slot-decision-procedure)

## Core Boundary

IRS owns the missing-slot declaration. SPL Editing owns repair execution.

```text
ConstructIRS + SlotSpec
-> missing slot report
-> CompileDiagnostic with DiagnosticIRSRef
-> RepairAffordanceSpec.repair_strategy_id
-> RepairStrategySpec
-> ConstructClosurePlan
-> repair-mode stage slices
-> preview and user confirmation
-> confirmed materialization
-> compiler-authority verification
```

IRS may declare that an approved strategy exists. IRS must not:

- create a `RepairDirective`;
- call an LLM;
- choose a command family or block shape;
- create a `ConstructRepairIntent` or `ConstructClosurePlan`;
- execute a repair-mode stage slice;
- generate or mutate `BlockIR`, `StepIR`, `WorkerHandoffIR`, or `WorkerIR`;
- produce a preview or apply an overlay.

## Strategy Is Not Patch Type

An R12+ repair strategy describes how to complete a missing SPL construct
closure. A patch type is only a transitional execution adapter.

Correct:

```text
EXCEPTION_FLOW.handler_action missing
-> exception_flow.complete_handler_action.v1
-> ensure handler BLOCK
-> materialize handler COMMAND
-> Stage 5 block slice
-> Stage 7 command slice
```

Incorrect:

```text
EXCEPTION_FLOW.handler_action missing
-> AddExceptionHandlerStep is the complete repair strategy
-> always emit one hard-coded GENERAL_COMMAND
```

The default policy may still produce one sequential block and one minimal
command. That result is a conservative default, not the strategy definition.

## Repair Strategy Admission

Do not invent a new strategy while adding an IRS slot. A strategy may be linked
only when all of the following are true:

1. The missing slot is user-actionable.
2. The construct owner and target slot are unambiguous.
3. Architecture documentation or the user has confirmed the repair direction.
4. A stable `RepairStrategySpec.strategy_id` exists or is part of the approved
   change scope.
5. The strategy describes a construct closure, not a fixed answer.
6. Each closure node has an owning repair-mode stage slice.
7. Required structured facts have authoritative sources.
8. Every selectable reference role has a policy and resolver.
9. Preview and user confirmation occur before accepted apply.
10. The verification lane covers every written artifact layer.

If any required runtime component is missing, leave
`SlotSpec.repair_affordances=()` or keep the capability non-user-facing. Do not
expose an option that only has presentation metadata.

## RepairStrategySpec Review

The current strategy model is defined under
`src/nl2spl/compiler/spl_editing/strategy/`.

Review these fields as one coherent contract:

### Identity and target

- `strategy_id`: stable semantic identifier, versioned when behavior changes.
- `target_construct_type`: must equal the owning `ConstructIRS.construct_type`.
- `target_slot_name`: must equal the owning `SlotSpec.slot_name`.
- `diagnostic_kind`: must equal `SlotSpec.missing_diagnostic`.

### Construct closure

- `missing_construct_closure`: construct categories required to satisfy the
  slot, such as `BLOCK`, `COMMAND`, `WORKER_HANDOFF`, or `INVOKE_WORKER`.
- `default_policy_id`: conservative policy when no user directive is supplied.
- `directive_policy_id`: policy that may interpret a user-provided business
  directive without bypassing stage authority.

### Stage ownership

- `stage_slice_chain`: ordered repair-mode slices that own each construct in
  the closure.
- `verification_lane`: replay lane required by the write layers and dependency
  closure. Use Lane B when normalized structures, block plans, worker plans, or
  handoffs are changed.

### Context and references

- `selectable_ref_policy_id`: policy that builds the bounded set of references
  the repair may consume.
- `required_context_facts`: structured facts that must be available before the
  repair is offered.

### Transitional execution adapters

- `supported_patch_types`: adapters that carry a confirmed strategy through
  legacy patch infrastructure.

Patch types must not become the semantic source for UI labels, prompts,
construct closure, command family, or stage ownership when
`repair_strategy_id` is present.

## Construct Closure Rules

Each repair instance derives a `ConstructClosurePlan`. Closure nodes use these
actions:

- `ensure`: reuse a suitable existing construct, or materialize one if absent;
- `bind_existing`: bind an existing construct to the missing role;
- `materialize`: create a new construct through its owning stage slice.

Use the smallest closure that actually satisfies the slot, but include every
structural dependency. Do not skip a required parent construct merely because
a lower-level materializer can synthesize it.

Examples:

```text
missing_handler:
  ensure handler BLOCK through Stage 5
  materialize handler COMMAND through Stage 7

missing_output_producer:
  ensure or bind placement BLOCK when needed through Stage 5
  materialize producer COMMAND through Stage 7

worker delegation contract gap:
  ensure target CHILD_WORKER
  materialize or complete WORKER_HANDOFF through Stage 3.5
  ensure invocation placement BLOCK through Stage 5 when needed
  materialize or bind INVOKE_WORKER through Stage 7
```

The closure plan and executable materialization plan must reference one
another. They must not become parallel truth sources.

## Stage-Slice Authority

Repair-mode stage slices reuse the construct policy owned by a pipeline stage
without fabricating full-pipeline inputs.

Do not create fake `SpanIR`, `FieldRouteIR`, or `compile_hint` values merely to
invoke a full stage executor. A stage slice consumes a repair-mode input
contract built from:

- the frozen `ArtifactSnapshot`;
- `TargetResolverResult`;
- a bounded `SelectableRefSet`;
- an optional provisional `RepairDirective`;
- a validated `ConstructRepairIntent`;
- `MaterializationDependencyClosure`;
- stage policy and ID allocators;
- `RepairEvidencePacket` only after user confirmation.

The owning stage for common constructs is:

| Construct responsibility | Repair-mode authority |
|---|---|
| Worker boundary / handoff contract | Stage 3.5 slice |
| Block shape and placement | Stage 5 slice |
| Resource or API context | Stage 6 slice when applicable |
| Command / step contract | Stage 7 slice |
| Normalization | Stage 9.5 validates and normalizes; it must not invent repair semantics |
| Assembly and rendering | Stages 10 and 11 consume repaired artifacts; they are not strategy generators |

A stage slice may call an LLM only as a constrained stage-owned generator. The
LLM may return a slice-local typed plan. It must not return IR or unbounded raw
references.

## Facts and Selectable References

Primary materialization facts must come from structured backend state:

- target construct and slot from `DiagnosticIRSRef` and `TargetResolverResult`;
- construct content from authoritative snapshot artifacts;
- source-backed context from source spans or traces;
- user preference from `RepairDirective`;
- usable symbols, workers, blocks, handoffs, connectors, and outputs from
  `SelectableRefSet`.

Do not parse `CompileDiagnostic.message`, feedback reports, rendered SPL, or UI
copy to obtain a condition, output name, worker target, variable, placement, or
repair strategy.

`RepairDirective.selected_ref_hints` are hints only. Materialization may consume
only `ConstructRepairIntent.selected_ref_ids` after validation against the
current `SelectableRefSet`.

## Preview, Confirmation, and Evidence

The directive is provisional. It is not confirmed evidence.

```text
provisional directive + validated intent + closure plan
-> dry-run stage-slice preview
-> user confirms the rendered result
-> RepairEvidencePacket(user_confirmed_repair)
-> confirmed materialization
-> overlay and replay
```

The user confirms the result preview, not internal strategy IDs or stage names.
Internal target, strategy, closure, selected refs, stage slices, and lane remain
available for audit or advanced details.

Preview identity must bind the base snapshot, directive, intent, closure plan,
selected ref set, typed plans, and preview constructs. Apply must reject stale
or mismatched previews.

`user_confirmed_repair` satisfies evidence requirements only. It does not
satisfy missing structural slots, authorize undefined refs, validate a handoff,
or prove that a changed construct appears in rendered SPL.

## Verification Contract

An exposed repair strategy requires end-to-end verification that checks:

1. The target diagnostic is resolved.
2. No new blocking diagnostics are introduced.
3. Every changed construct came from a declared stage slice.
4. Materialization authority matches the strategy's stage-slice chain.
5. Consumed selected refs belong to the confirmed intent and current ref set.
6. Closure plan and materialization plan agree.
7. Preview identity is current and apply matches the previewed result.
8. Changed constructs satisfy IRS, Gate, ProducerIndex, graph, handoff, and
   provenance authorities as applicable.
9. Changed steps are attached to renderable blocks and appear in final rendered
   output when the strategy requires visible SPL.
10. No undefined reference is rendered.

Verification is acceptance, not generation. Do not compensate for an
under-specified strategy or stage slice with a verifier that guesses intent.

## Current Approved MVP Strategies

The current default strategy registry defines these semantic strategies:

| IRS target | Strategy | Construct closure | Stage slices |
|---|---|---|---|
| `EXCEPTION_FLOW.handler_action` | `exception_flow.complete_handler_action.v1` | handler `BLOCK + COMMAND` | Stage 5 + Stage 7 |
| `REQUIRED_OUTPUT.producer` | `required_output.materialize_producer.v1` | producer `COMMAND`, optional placement `BLOCK` | Stage 7, Stage 5 when needed |
| `WORKER_PROMOTION` contract slots | `worker_delegation.complete_closure.v1` | child worker, handoff, bindings, invocation placement, `INVOKE_WORKER` | Stage 3.5 + Stage 5 when needed + Stage 7 |

Treat this table as a pointer to the runtime registry, not a substitute for it.
Inspect the registered `RepairStrategySpec` before modifying an IRS affordance.

## New IRS Slot Decision Procedure

When creating a new IRS slot:

1. Define requiredness, evidence, renderability, and missing diagnostic first.
2. Decide whether the missing slot is user-actionable.
3. Search the strategy registry for an exact construct/slot/diagnostic match.
4. If a strategy exists, inspect its closure, stage slices, facts, refs, and
   verification lane.
5. Confirm that runtime registries contain every required component.
6. Add `RepairAffordanceSpec` only after the chain is coherent.
7. If no strategy exists, leave the affordance empty and document the gap.
8. Add contract tests that fail on a missing or mismatched strategy.

Never start by inventing a patch type or handler ID.


