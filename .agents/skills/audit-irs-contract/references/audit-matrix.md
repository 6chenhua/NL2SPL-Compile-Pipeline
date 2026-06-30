# IRS Contract Audit Matrix

Use this matrix for a full audit.

| Layer | Required checks |
| --- | --- |
| Admission | Construct is a grammar construct or approved compiler construct; source signals are evidence, not constructs. |
| Construct contract | Identity, existence policy, source signals, no-demand behavior, and partial rendering are explicit. |
| Slot contract | Requiredness, renderability, evidence kinds, missing diagnostic, and actionability decision are coherent. |
| Diagnostic | Diagnostic kind is registered and projected with IRS authority metadata. |
| Runtime | Checker extraction, runner registration, projector, result storage, and feedback projection are present. |
| Repair | Editable slots have affordance, strategy, target resolver, context builder, patch adapter, materialization plan, preview/apply, verifier, and registration. |
| Tests | Registry, checker, projector, catalog, issue extraction, negative non-editable, and E2E paths are covered. |

A missing affordance is acceptable only when the actionability decision is
explicitly non-editable or optional enrichment. A declared affordance without
runtime closure is not acceptable as production-ready behavior.