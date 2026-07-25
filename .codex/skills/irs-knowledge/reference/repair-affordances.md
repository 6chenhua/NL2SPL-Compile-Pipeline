# IRS Repair Affordance Specification

Use this reference when creating or modifying `SlotSpec.repair_affordances` in
an IRS `ConstructIRS`. The types live in `nl2spl.compiler.repair_contracts`;
`compiler.irs.patch_type_meta` is only a legacy compatibility shim.

`RepairAffordanceSpec` is pure registry metadata. It links a missing IRS slot to
an approved SPL Editing capability. It does not execute repair behavior and it
must not become a second repair strategy registry.

Read `construct-repair-strategies.md` before adding an R12+ affordance.

## Contents

- [Semantic Source of Truth](#semantic-source-of-truth)
- [Confirmation and Admission Rule](#confirmation-and-admission-rule)
- [Runtime Flow](#runtime-flow)
- [Field Guide](#field-guide)
- [Creation Checklist](#creation-checklist)
- [Anti-Patterns](#anti-patterns)

## Semantic Source of Truth

For R12+ repairs, the semantic source is:

```text
RepairAffordanceSpec.repair_strategy_id
-> RepairStrategyRegistry
-> RepairStrategySpec
```

The following affordance fields remain useful as routing, capability, or
transition metadata, but they are not the repair strategy:

```text
supported_patch_types
default_patch_type
handler_id
context_id
target_resolver_id
materialization_plan_id
stage_authority
patch_type_metadata
```

When `repair_strategy_id` is present, UI copy, prompts, construct closure,
default generation policy, stage-slice ownership, and verification semantics
must come from the strategy and its registered runtime components.

## Confirmation and Admission Rule

Do not invent repair behavior while creating an IRS.

Add a repair affordance only when the user or architecture documentation has
confirmed:

- the construct-level repair direction;
- the stable `repair_strategy_id`;
- the missing construct closure;
- the owning stage-slice chain;
- required structured facts and selectable-reference policy;
- preview and user-confirmation behavior;
- editable artifact layers and verification lane;
- any transitional patch adapters still required by runtime.

If slot semantics are clear but repair ownership is not confirmed, leave
`repair_affordances=()` and state that SPL Editing repair is not yet defined.

Do not add an affordance merely because the slot has a `missing_diagnostic`.

## Runtime Flow

```text
SlotSpec.repair_affordances
-> RepairCatalogBuilder
-> RepairCatalogEntry with repair_strategy_id
-> RepairStrategyRegistry lookup
-> target and selectable-ref resolution
-> optional RepairDirective
-> validated ConstructRepairIntent
-> ConstructClosurePlan
-> preview dry-run stage slices
-> user confirmation
-> RepairEvidencePacket
-> confirmed materialization and overlay
-> compiler-authority verification
```

The IRS registry owns only the first declaration. It does not own the remaining
runtime flow.

## Field Guide

### `affordance_id`

A stable identifier for the repair capability attached to the slot. Prefer a
construct-level name, such as:

```text
exception_flow.complete_handler_action
required_output.materialize_producer
worker_delegation.complete_closure
```

Avoid names that permanently encode a concrete default result, such as
`add_display_message_step`.

The catalog entry identity remains:

```text
{construct_type}.{slot_name}.{diagnostic_kind}.{affordance_id}
```

Related slots may share an affordance only when they resolve to the same
strategy set and issue grouping semantics.

### `description`

A short summary of the missing construct capability. Describe the completion
goal, not the hard-coded implementation.

Good:

```text
Complete the missing exception handler action.
```

Bad:

```text
Always add a GENERAL_COMMAND that displays an error.
```

### `repair_strategy_id`

Required semantic link for an R12+ user-facing repair.

The referenced `RepairStrategySpec` must match:

- `target_construct_type` to the owning `ConstructIRS.construct_type`;
- `target_slot_name` to the owning `SlotSpec.slot_name`;
- `diagnostic_kind` to `SlotSpec.missing_diagnostic`.

It must also provide a coherent construct closure, stage-slice chain, context
requirements, selectable-ref policy, default/directive policies, preview rule,
and verification lane.

If the strategy does not resolve, the issue must not be shown as fixable.

### `supported_patch_types`

Transitional execution adapters that may carry the selected strategy through
legacy validator/applier/verifier interfaces.

Rules:

1. Every value must be registered.
2. Every value must be permitted by the referenced strategy.
3. A patch type must not become the source for strategy selection or construct
   shape when `repair_strategy_id` is present.
4. New R12+ behavior should not introduce patch names that encode a permanent
   concrete answer.

### `default_patch_type`

Transitional adapter selected when one is required by legacy execution. It
must belong to `supported_patch_types`.

It is not the default repair policy. The default construct behavior comes from
`RepairStrategySpec.default_policy_id`.

### `handler_id`

Identifier of the issue repair handler or suggestion orchestration component.
The handler may propose a validated construct repair intent. It must not choose
the semantic strategy by inspecting only `diagnostic.kind`, and it must not
emit IR.

### `context_id`

Identifier of the structured repair context builder. It must supply the facts
required by the strategy without parsing reports or diagnostic messages.

### `target_resolver_id`

Identifier of the resolver that maps `DiagnosticIRSRef` and snapshot state to
the real editable construct. Source annotations and diagnostic labels are not
repair targets.

### `selectable_ref_policy_id`

Identifier of the policy that builds the bounded reference set available to
the strategy. It must distinguish reference kind from repair role, such as:

```text
target_output
selectable_input
placement_anchor
binding_source
binding_target
target_worker
target_exception_flow
```

The LLM and directive may suggest references, but materialization may consume
only validated `ConstructRepairIntent.selected_ref_ids`.

### `required_context_facts`

Structured facts required before the repair is offered. Each fact needs an
authoritative backend source in the snapshot, target resolver, trace, source
span, or repair context.

Do not satisfy this list by parsing `CompileDiagnostic.message` or presentation
copy.

### `materialization_plan_id`

Transitional link to executable materialization orchestration. Under R12+, the
materialization plan must be consistent with the strategy-derived
`ConstructClosurePlan`; it must not define a conflicting closure or stage
chain.

### `stage_authority`

Transition/audit metadata describing the stage ownership expected by the
execution adapter. It must agree with `RepairStrategySpec.stage_slice_chain`.
Do not collapse a multi-stage closure into a misleading single stage.

### `default_verification_lane`

Fallback verification lane. It must agree with the strategy and every written
artifact layer.

- Lane A is limited to changes that assembler replay can authoritatively
  verify.
- Lane B is required for block plans, normalized structures, worker plans,
  handoff contracts, cross-worker bindings, or other normalizer-owned state.

### `editable_artifacts`

The minimal artifact classes that confirmed materialization may modify. Include
every layer in the closure, but do not broaden the list to hide unclear stage
ownership.

### `intent_schema_id`

Identifier of the typed construct repair intent schema used by the transitional
handler/adapter. The schema must not expose IR-like free-form fields or permit
raw variable names outside `SelectableRefSet`.

### `required_evidence_kind`

The evidence required for accepted apply. The current user-facing default is
`user_confirmed_repair`.

This field does not make a provisional directive confirmed. Evidence authority
is created only after the user confirms the preview and a
`RepairEvidencePacket` is issued.

Confirmation does not satisfy structural slots, validate handoffs, authorize
undefined refs, or prove rendered placement.

### `user_facing`

Whether the affordance may appear in the default issue repair flow. Set this to
`True` only when the full strategy, preview, apply, and verification chain is
available.

### `patch_type_metadata`

Transitional labels and adapter-specific lanes. When a strategy is present,
these labels must not replace strategy-level presentation. They may explain
legacy execution choices that remain genuinely distinct.

### `notes`

Maintainer-only context. Runtime behavior must not depend on it.

## Creation Checklist

Before adding a `RepairAffordanceSpec`, verify all of the following:

1. The slot has a real `missing_diagnostic`.
2. The slot is user-actionable.
3. The strategy was confirmed by architecture or the user.
4. `repair_strategy_id` resolves in the strategy registry.
5. Strategy construct, slot, and diagnostic exactly match the IRS owner.
6. The strategy closure contains every required parent and child construct.
7. Every closure node has an owning registered stage slice.
8. Default and directive-driven policies are defined.
9. Required structured facts have authoritative providers.
10. The selectable-ref policy exists and constrains all consumable refs.
11. The target resolver resolves the actual construct, not a source signal.
12. Preview is generated before confirmation and cannot persist an accepted
    overlay.
13. Confirmed apply creates the required evidence packet.
14. Editable artifacts and verification lane cover the complete write set.
15. Verification checks authority, refs, closure, provenance, graph/producer/
    handoff constraints as applicable, and rendered visibility.
16. Transitional patch adapters are registered and agree with the strategy.
17. Tests fail when any registry link is missing or mismatched.

## Anti-Patterns

- Treating `supported_patch_types` as the user-facing strategy set.
- Naming an affordance after a fixed command family or final answer.
- Adding a repair affordance solely because a diagnostic exists.
- Linking a strategy whose construct, slot, or diagnostic does not match.
- Declaring only Stage 7 when the closure also requires Stage 5 block
  materialization.
- Making a patch applier or generic materializer decide the full construct
  shape.
- Letting a handler parse diagnostic text to obtain primary materialization
  facts.
- Letting a user directive or LLM supply raw refs that are absent from the
  selectable set.
- Treating preview generation as accepted apply.
- Treating `user_confirmed_repair` as authority to bypass structural checks.
- Exposing a repair before stage slices, preview, apply, or verification are
  registered.
- Creating a repair target for `delegation_intent` instead of the owning
  `WORKER_PROMOTION`, `WORKER_HANDOFF`, `CHILD_WORKER`, or `INVOKE_WORKER` slot.


