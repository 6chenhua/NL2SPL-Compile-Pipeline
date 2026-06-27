# Add a Repairable IRS Slot

Use this example only after the construct and slot satisfaction contract are
defined. Repair metadata is optional and must not influence whether the IRS
slot itself is valid.

## 1. Define the Slot Contract

Example target:

```text
Construct: EXCEPTION_FLOW
Slot: handler_action
Missing diagnostic: missing_handler
Structured evidence: handler block / handler action in authoritative flow IR
Renderable without slot: partial exception flow only
```

The checker reports satisfaction. It does not generate the missing handler.

## 2. Find an Approved Strategy

Search the `RepairStrategyRegistry` by the exact target tuple:

```text
EXCEPTION_FLOW
handler_action
missing_handler
```

The approved strategy is:

```text
exception_flow.complete_handler_action.v1
```

Its semantic contract is:

```text
ensure handler BLOCK through Stage 5
materialize handler COMMAND through Stage 7
preview before confirmation
apply only with user_confirmed_repair evidence
verify through Lane B
```

`AddExceptionHandlerStep` may remain as a transitional patch adapter. It is not
the strategy and must not define the command family or final construct shape.

## 3. Declare the Affordance

The IRS registry entry may link the slot to the approved strategy:

```python
SlotSpec(
    slot_name="handler_action",
    required_for_complete=True,
    renderable_without=False,
    evidence_kinds=["handler_block", "handler_action"],
    missing_diagnostic="missing_handler",
    repair_affordances=(
        RepairAffordanceSpec(
            affordance_id="exception_flow.complete_handler_action",
            description="Complete the missing exception handler action.",
            repair_strategy_id="exception_flow.complete_handler_action.v1",
            handler_id="missing_handler",
            context_id="exception_flow_context",
            target_resolver_id="exception_flow_target",
            selectable_ref_policy_id=(
                "exception_flow.handler.selectable_refs.v1"
            ),
            required_context_facts=(
                "exception_condition",
                "worker_id",
                "available_variables",
                "nearby_steps",
                "symbol_table",
            ),
            default_verification_lane="B",
            editable_artifacts=("WorkerBlockPlanIR", "WorkerStepPlanIR"),
            supported_patch_types=("AddExceptionHandlerStep",),
            default_patch_type="AddExceptionHandlerStep",
        ),
    ),
)
```

The exact transitional fields must match the current runtime registry. Do not
copy them blindly into a different construct or slot.

## 4. Validate the Full Chain

Before exposing the option, verify:

```text
RepairAffordanceSpec.repair_strategy_id resolves
-> strategy target equals EXCEPTION_FLOW.handler_action
-> strategy diagnostic equals missing_handler
-> closure includes handler BLOCK and COMMAND
-> Stage 5 and Stage 7 slices are registered
-> target resolver resolves the exception flow
-> selectable-ref policy is registered
-> required structured facts are available
-> preview is required and confirmation creates evidence
-> Lane B verifies block, command, provenance, and rendered output
```

If any link is absent, keep the slot non-editable rather than exposing a repair
that fails after selection.

## 5. Required Tests

Add tests for:

- slot requiredness and missing diagnostic projection;
- `DiagnosticIRSRef` target fields;
- catalog derivation with the correct `repair_strategy_id`;
- exact strategy target tuple match;
- closure and stage-slice registration;
- missing required context causing repair unavailability;
- unknown selected refs being rejected;
- preview not persisting an accepted overlay;
- apply requiring user-confirmed evidence;
- replay resolving the diagnostic without new blockers;
- changed handler block and command appearing in rendered SPL;
- existing handler block reuse without duplicate block creation.

## Non-Repairable Variant

When no approved strategy exists, keep the slot contract and omit the
affordance:

```python
SlotSpec(
    slot_name="example_slot",
    required_for_complete=True,
    missing_diagnostic="type_or_contract_ambiguity",
    repair_affordances=(),
)
```

State explicitly that the IRS diagnostic exists but SPL Editing repair is not
yet defined. A diagnostic does not imply an editable issue.

