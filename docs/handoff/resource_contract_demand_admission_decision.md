# RESOURCE_CONTRACT_DEMAND Admission Decision

**Status**: Approved for this refactor
**Decision**: keep as IRS construct
**Owner**: `resource_contract_demand_view` + post-normalize IRS
**Decision date**: 2026-07-08

---

## 1. Decision

`RESOURCE_CONTRACT_DEMAND` remains in the default construct registry as an approved compiler analysis / materialization construct.

It is not an SPL grammar construct and must not be treated as one. It represents a source-demanded resource contract after the compiler has normalized resource-contract evidence into a stable demand view or legacy `ResourceContractPlanIR` fallback.

This decision allows Phase 9 of `irs_constructs_refactor_implementation_plan.md` to create:

```text
constructs/definitions/resource_contract_demand.py
```

provided the split preserves current registry shape and RepairCatalog identity.

---

## 2. Construct Identity

Stable identity:

```text
resource_contract_demand:{demand_id}
```

The post-normalize checker currently extracts this from:

```text
context.metadata["demand_view"].valid_demands()
```

with fallback to:

```text
context.metadata["resource_contract_plan"].demands
```

The construct identity is therefore the compiler-normalized resource contract demand, not the original route annotation and not a diagnostic kind.

---

## 3. Lifecycle

Current lifecycle:

```text
source route / annotation evidence
-> resource_contract_demand_view or ResourceContractPlanIR fallback
-> ResourceContractDemandIR / demand object with demand_id
-> Stage 6 resource contract binding / resource registry materialization
-> post-normalize IRS RESOURCE_CONTRACT_DEMAND instance
-> ConstructSatisfactionReport
-> DiagnosticProjector
-> CompileDiagnostic
```

`resource_contract_demand_view` owns evidence projection and demand normalization. IRS owns only slot satisfaction for the extracted demand instance.

---

## 4. Slots

Current slots remain valid:

| Slot | Required | Evidence | Diagnostic | Decision |
|---|---:|---|---|---|
| `materialization` | partial + complete | `ResourceContractBindingIR.contract_demand_id == demand_id` | `missing_resource_contract` | keep |
| `resource_registry` | complete | binding points to materialized registry item | `resource_kind_mismatch` | keep |
| `producer` | complete | `ProducerIndex` has a renderable producer for output demands | `missing_output_producer` or `unspecified_output_missing_producer` | keep as alias/context where `REQUIRED_OUTPUT.producer` is primary |

These slots are independent enough to justify an IRS construct during this refactor:

1. a demand can exist with no binding;
2. a binding can exist but point to a missing registry resource;
3. a binding can exist but lack a renderable producer.

---

## 5. Diagnostic Ownership

Primary ownership rules:

```text
missing_resource_contract       -> RESOURCE_CONTRACT_DEMAND.materialization
resource_kind_mismatch          -> RESOURCE_CONTRACT_DEMAND.resource_registry
missing_output_producer         -> REQUIRED_OUTPUT.producer primary, RESOURCE_CONTRACT_DEMAND.producer alias/context
unspecified_output_missing_producer -> RESOURCE_CONTRACT_DEMAND.producer review/info
```

`RESOURCE_CONTRACT_DEMAND.producer` must not override `REQUIRED_OUTPUT.producer` as the primary user-facing issue for missing output producers. Existing issue grouping that prefers `REQUIRED_OUTPUT` over `RESOURCE_CONTRACT_DEMAND` should remain intact.

---

## 6. Repairability

`RESOURCE_CONTRACT_DEMAND` remains non-editable in this refactor.

It must not create a `RepairCatalog` entry unless a later architecture document approves a construct-level repair strategy. Current actionability decisions are review-only / non-repairable and should stay that way.

Allowed:

```text
diagnostic projection
issue alias/context grouping
developer review details
```

Forbidden:

```text
RepairAffordanceSpec for RESOURCE_CONTRACT_DEMAND
repair_strategy_id for RESOURCE_CONTRACT_DEMAND
patch handlers targeting RESOURCE_CONTRACT_DEMAND directly
LLM repair drafting based on this construct
```

If a missing producer should be repairable, the repair target remains the owning output construct or producer/materialization flow, not this demand-view construct.

---

## 7. Why Not Demote Now

Demotion would be valid only if all current diagnostics could be owned cleanly by existing constructs without losing lifecycle evidence.

Current blockers to demotion:

1. `missing_resource_contract` is specifically about a normalized demand with no binding, before a file/variable/API declaration can own the failure.
2. `resource_kind_mismatch` compares demand bindings against the materialized registry and is not naturally owned by `REQUIRED_OUTPUT` alone.
3. existing post-normalize tests assert a resource-demand instance and slot-level satisfaction behavior.
4. current issue grouping already handles the producer slot as alias/context, reducing the main risk of duplicate primary diagnostics.

Therefore the least risky refactor path is to keep the construct, preserve its non-editable status, and document alias semantics.

---

## 8. Implementation Consequences

Phase 9 may split the definition into:

```text
constructs/definitions/resource_contract_demand.py
```

but must preserve:

1. construct type `RESOURCE_CONTRACT_DEMAND`;
2. source signals `input_contract`, `output_contract`, `resource_contract`;
3. slots `materialization`, `resource_registry`, `producer`;
4. missing diagnostics;
5. actionability decisions as non-editable;
6. no repair affordances;
7. issue grouping that keeps `REQUIRED_OUTPUT.producer` primary for producer gaps.

The post-normalize checker may later move extraction helpers during checker splitting, but it must continue to consume `resource_contract_demand_view` / `ResourceContractPlanIR` as structured evidence only.

---

## 9. Required Tests

Existing tests to preserve:

```text
tests/unit/test_post_normalize_resource_contract_irs.py
tests/unit/compiler/test_producer_index_v2_relations.py
```

Additional checks required during Phase 9:

1. default registry shape snapshot still includes `RESOURCE_CONTRACT_DEMAND`;
2. `RESOURCE_CONTRACT_DEMAND` has no `RepairCatalog` entries;
3. producer grouping still prefers `REQUIRED_OUTPUT` over `RESOURCE_CONTRACT_DEMAND`;
4. post-normalize IRS still extracts demand instances from `demand_view` before legacy plan fallback;
5. `missing_resource_contract` and `resource_kind_mismatch` still project from the correct slots.

---

## 10. Review Gate

This decision is approved only for the package-boundary refactor. It does not approve new repair behavior, new diagnostics, or new source-demand extraction semantics.

Any future change that makes `RESOURCE_CONTRACT_DEMAND` editable must go through a separate architecture review and define:

```text
RepairStrategySpec
ConstructClosurePlan
stage-slice chain
preview/apply behavior
compiler-authority verification
```
