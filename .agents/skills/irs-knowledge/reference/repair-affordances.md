# IRS Repair Affordance Specification

Use this reference when creating or modifying `SlotSpec.repair_affordances`
inside an IRS `ConstructIRS`.

`repair_affordances` are pure registry metadata. They describe which repair
strategies SPL Editing may expose for a missing IRS slot. They do not execute a
repair, call an LLM, mutate IR, or invent missing slot content.

## Confirmation Rule

When using this skill to create or modify an IRS construct, do not invent repair
strategies. A `repair_affordances` entry may be added only when the user or an
architecture document has confirmed the allowed repair strategy set.

If the construct and slot requirements are clear but repair strategy ownership
is not confirmed, leave `repair_affordances=()` and state that the slot is not
repairable through SPL Editing yet. If an editable diagnostic is required, ask
the user to confirm:

- which repair strategies should be exposed;
- which patch types implement those strategies;
- which artifacts may be edited;
- which verification lane each strategy requires.

Do not treat a missing diagnostic kind as enough evidence to create a repair
affordance. Repair affordances are user-facing product behavior and must be
confirmed separately from slot satisfaction rules.

## Runtime Flow

```text
SlotSpec.repair_affordances
-> RepairCatalogBuilder.from_construct_registry(...)
-> RepairCatalogEntry
-> Diagnostics Console repair option
-> IssueRepairHandler / patch validator / applier / verifier
```

The IRS registry owns only the first step. The remaining components must exist
or be planned before exposing a repair option.

## Field Guide

### `affordance_id`

Stable identifier for a repair capability, usually
`{construct_type_lower}.{descriptive_suffix}`.

Use the same `affordance_id` across related slots only when they expose the same
repair capability and strategy set. The unique catalog key is:

```text
{construct_type}.{slot_name}.{diagnostic_kind}.{affordance_id}
```

So related slots may share an `affordance_id`, but do not reuse one for
unrelated behavior.

### `description`

Short human-readable summary of the overall repair capability. It should explain
the problem the affordance resolves, not prescribe hidden implementation logic.

### `supported_patch_types`

Tuple of allowed patch type strings the repair handler may produce for this
slot. Every value must correspond to a registered or explicitly planned patch
bundle with validator, applier, and verifier behavior.

Do not include speculative patch types. If multiple strategies are exposed, each
must be user-confirmed.

### `default_patch_type`

Patch type selected when the user does not choose a more specific strategy. It
must be one of `supported_patch_types`.

Use a default only when product behavior is confirmed. Otherwise prefer a single
explicit patch type or leave the affordance absent.

### `handler_id`

Identifier of the `IssueRepairHandler` that generates the patch proposal for
this diagnostic and slot.

Usually this matches the diagnostic kind, for example
`type_or_contract_ambiguity`, but do not assume that automatically. Use the
registered handler that owns this repair flow.

### `context_id`

Identifier of the `RepairContextBuilder` that gathers structured context for
the handler.

The context builder must provide enough evidence for every supported patch type.
If a patch type needs child-worker context, handoff context, source spans, or
artifact snapshots, the selected context builder must supply them.

### `target_resolver_id`

Identifier of the `IssueTargetResolver` that maps a diagnostic target or
`DiagnosticIRSRef` to the editable object.

Choose the resolver that matches the real target identity, such as a step,
handoff, worker promotion, or required output. Do not point a route annotation
or diagnostic label directly at a repair target unless a resolver explicitly
supports that boundary.

### `default_verification_lane`

Default verification lane used when per-patch metadata does not override it.

- `A`: Assembler replay. Use for localized changes that do not require
  normalizer-level worker/handoff reconstruction.
- `B`: Normalizer replay. Use when the patch can change worker plans, handoff
  contracts, cross-worker bindings, or other normalized structures.

Prefer per-patch `PatchTypeMeta.verification_lane` when an affordance exposes
multiple strategies with different replay needs.

### `editable_artifacts`

Tuple of IR artifact class names the patch applier is allowed to modify, such
as `WorkerStepPlanIR`, `WorkerPlanIR`, or `WorkerHandoffIR`.

Keep this list minimal. It is a capability boundary, not documentation. Do not
include artifacts merely because they are nearby.

### `required_evidence_kind`

Evidence kind required before applying a repair. The MVP default is
`user_confirmed_repair`.

Do not weaken this requirement for AI-generated suggestions. Unconfirmed
suggestions must remain non-renderable unless another confirmed authority is
explicitly designed.

### `user_facing`

Whether the affordance should be exposed in the Diagnostics Console UI.

Use `False` only for internal or staged capabilities that should be hidden from
users while still remaining catalog-visible for tests or internal tooling.

### `notes`

Internal design notes for maintainers. Runtime code must not depend on this
field.

### `patch_type_metadata`

Tuple of `PatchTypeMeta` entries used to present individual strategy options.
Use this whenever `supported_patch_types` contains more than one user-visible
strategy.

Each `PatchTypeMeta` should define:

- `patch_type`: one value from `supported_patch_types`;
- `label`: concise user-facing strategy label;
- `description`: when the user should choose this strategy;
- `verification_lane`: lane for this specific strategy.

The set of `patch_type_metadata.patch_type` values should match
`supported_patch_types` for user-facing multi-strategy affordances.

## Creation Checklist

Before adding a `RepairAffordanceSpec`, verify:

1. The slot has a real `missing_diagnostic`.
2. The missing slot is user-actionable.
3. The user or architecture has confirmed each exposed repair strategy.
4. Every `supported_patch_types` value is registered or explicitly planned.
5. `default_patch_type` is confirmed and belongs to `supported_patch_types`.
6. `handler_id`, `context_id`, and `target_resolver_id` map to real SPL Editing
   components.
7. `editable_artifacts` is the minimal set required by the patch applier.
8. `default_verification_lane` and per-patch lanes match the artifact blast
   radius.
9. Multi-strategy affordances include `patch_type_metadata`.
10. Tests cover registry shape and `RepairCatalog` derivation.

## Anti-Patterns

- Adding repair affordances just because a slot has a diagnostic.
- Inventing patch types without user or architecture confirmation.
- Reusing an `affordance_id` for unrelated behavior.
- Exposing a patch type whose handler, context builder, resolver, validator,
  applier, or verifier does not exist or is not planned.
- Listing broad `editable_artifacts` to avoid choosing a real ownership
  boundary.
- Marking unconfirmed AI output as renderable repair evidence.
- Creating a repair target for a source signal such as `delegation_intent`
  instead of targeting the owning IRS construct slot.
