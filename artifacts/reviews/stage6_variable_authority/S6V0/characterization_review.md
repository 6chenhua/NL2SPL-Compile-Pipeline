# S6V0 Characterization Review

**Date**: 2026-07-09
**Phase**: Characterization (no production code changes)
**Status**: COMPLETE

## Evidence Summary

### 1. Stage 6 Prompt — Condition Variable Declaration Rule (CONFIRMED)

File: `prompts/stage6_system.txt`, lines 39-40:
```
- Every condition variable (used in IF conditions) has been declared
  as a step variable.
```

This rule instructs the LLM to treat condition variables as step variables
that must be declared.  It is the root cause of condition-predicate pollution.

Additionally, the prompt's Type Inference Rules table (line 32) uses
`sources_needed` as a boolean example — a name that matches the exact shape
of demo pollution variables.

### 2. Demo Final SPL — Condition-only Predicates (CONFIRMED)

File: `examples/output/demo/final_spl.txt`, lines 34-37:
```text
"Whether sources are needed for the task." sources_needed: boolean
"Whether needed sources are available." sources_available: boolean
"Whether enough required information is available to produce a draft." enough_required_information: boolean
"Whether the user asks for revision." user_asks_for_revision: boolean
```

These are rendered in `[DEFINE_VARIABLES:]` and consumed via `<REF>` tags:
```text
DECISION-2 [IF <REF>enough_required_information</REF> is available]
DECISION-3 [IF the <REF>user_asks_for_revision</REF>]
```

Note also `required_fields_missing`, `required_slots_remain_missing`,
`draft_marked_as_assumption_bearing`, `user_confirms` — all boolean
guard-condition predicates.

### 3. Stage 6.5 Condition Reference Plan (CONFIRMED)

File: `examples/output/demo/condition_variable_reference_plan.json`

The plan resolves `enough_required_information` and `user_asks_for_revision`
as `selected_symbol` entries with `evidence_kind: "llm_condition_semantic_match"`.
This confirms Stage 6.5 operates on already-polluted SymbolTable entries.

### 4. Stage 3.5 Candidate IO (CONFIRMED)

File: `examples/output/demo/stage3_5a_candidate_task_units.json`

Candidate `candidate_retrieve_supported_sources` has:
```json
"possible_inputs": [{
    "name": "sources_needed",
    "source_span_ids": [],
    "contract_demand_id": null
}]
```

Key observation: `source_span_ids` is empty, `contract_demand_id` is null —
no declaration evidence whatsoever.  The materialized worker contract
(`stage3_5c_worker_plan_materializer.json`) propagates this variable into
the worker plan.

### 5. Feedback Report (CONFIRMED)

File: `examples/output/demo/feedback_report.md`

The report correctly flags these variables as having "no source-backed
producer and no contract section evidence" and labels them `assumed`.
But this diagnostic comes too late — the variables are already in the SPL.

### 6. SymbolTable Write Paths (INVENTORY)

Seven known production write paths identified:
1. Stage 6 legacy: `symbol_table.declare()`
2. Stage 6 worker-scoped: `symbol_table.declare_scoped()`
3. Stage 7 new_variables: `symbol_table.declare()`
4. Stage 7 legacy handoff output: `symbol_table.declare()`
5. Stage 7 worker-scoped new_variables: `symbol_table.declare_scoped()`
6. Stage 9.5 composite output rewrite: `symbol_table.declare()`
7. SPL Editing repair: `symbol_table.declare_scoped()`

None of these currently carry declaration authority metadata.

## Demo Variable Inventory (Condition-Predicate Subset)

| Variable | Type | Source | Declaration Evidence |
|---|---|---|---|
| sources_needed | boolean | step | None (Stage 3.5 candidate IO, empty source_span_ids) |
| sources_available | boolean | step | None (LLM-inferred from guard text) |
| enough_required_information | boolean | step | None (LLM-inferred from guard text) |
| user_asks_for_revision | boolean | step | None (LLM-inferred from guard text) |
| required_fields_missing | boolean | step | None (LLM-inferred) |
| required_slots_remain_missing | boolean | step | None (LLM-inferred) |
| draft_marked_as_assumption_bearing | boolean | step | None (LLM-inferred) |
| user_confirms | boolean | step | None (LLM-inferred) |

## Pollution Chain

```
Natural-language guard clauses in source text
  → Stage 6 prompt instructs: "declare condition variables as step variables"
  → Stage 6 LLM invents boolean predicates (sources_needed, etc.)
  → Stage 3.5 candidate IO carries sources_needed without evidence
  → Worker contract materializes sources_needed
  → Stage 6 _merge_contract_variables() admits it unconditionally
  → SymbolTable is polluted
  → Stage 6.5 resolves conditions against polluted symbols
  → Stage 9.5 treats them as valid references
  → Renderer emits DEFINE_VARIABLES / <REF>
```

## Next: S6V1
