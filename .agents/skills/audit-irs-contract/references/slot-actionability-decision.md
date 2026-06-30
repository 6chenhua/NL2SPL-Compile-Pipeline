# Slot Actionability Decision

SlotActionabilityDecision is a first-class SlotSpec contract.

## Typed Contract

~~~python
@dataclass(frozen=True)
class SlotActionabilityDecision:
    actionability: Literal[
        "editable",
        "non_editable",
        "optional_enrichment",
    ]
    non_editable_disposition: Literal[
        "review_only",
        "deferred_validation",
        "developer_only",
        "non_repairable",
    ] | None
    rationale_code: str
    decision_source_ref: str
    decision_status: Literal["confirmed", "unresolved"]
~~~

The implementation must validate these Literal values at runtime. Static typing
alone is not the registry gate.

## Mandatory Decision Scope

    required_for_partial
    OR required_for_complete
    OR missing_diagnostic is not null
    OR repair_affordances is not empty

## Coherence Rules

Editable:

- requires one or more repair affordances;
- requires complete runtime repair closure;
- forbids non_editable_disposition.

Non-editable:

- requires a non-editable disposition;
- forbids repair affordances.

Optional enrichment:

- must not be required for partial rendering;
- must not be required for complete output;
- must be explicitly renderable without the slot;
- must not use a completion-blocking diagnostic;
- must not be projected as a mandatory editable issue;
- may appear only through an explicit optional enhancement surface;
- has no mandatory RepairCatalog entry.

All decisions require non-empty rationale_code and decision_source_ref.
Unresolved decisions are P1 until resolved or explicitly waived.

Do not infer actionability from diagnostic kind. Do not add an affordance merely
because a required slot can be missing.