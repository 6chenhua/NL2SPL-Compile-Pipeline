# Task F1: Adapter Hint and Evidence Strengthening

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisite:

- F0 Baseline Frontend Tests approved.

Related docs:

- `docs/Todo/route_contract_refactor_00_readme.md`
- `docs/Todo/route_contract_refactor_01_frontend_semantic_contract.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`
- `docs/Todo/tasks/F0_baseline_frontend_tests.md`

## Objective

Strengthen `InputAdapter` output so later `FieldRouter` work can consume clear,
traceable semantic evidence.

This task should improve adapter facts and hints only. It must not introduce
`RouteAnnotation`, change downstream routing behavior, or remove bridge logic.

## Scope

In scope:

- `CanonicalCompileInput` hint/evidence usage;
- `StructuralNLAdapter` failure-mode hints;
- `StructuralNLAdapter` delegation-intent hints;
- packet-level evidence where deterministic packets exist;
- tests proving the strengthened adapter contract.

Out of scope:

- adding `RouteAnnotation`;
- changing `FieldRouteIR`;
- changing `FieldRouter` route decisions;
- changing `failure_mode -> rules` current baseline;
- changing Stage 4 materialization;
- changing Stage 7 executable filtering;
- deleting or rewriting `bridge_failure_modes()`;
- deleting or rewriting `bridge_delegation_intents()`.

## Current Baseline

F0 established the current behavior:

```text
failure_mode packet
-> Stage 2 routes to rules
-> bridge_failure_modes() later creates partial ExceptionFlow
```

F1 must not change that runtime behavior. F1 only makes adapter output richer
and more precise for future phases.

## Required Implementation

## 1. Strengthen Failure Handling Hints

For every deterministic failure mode extracted from `Failure handling`, emit a
`CompileHint` that clearly identifies the target construct and slot.

Expected hint shape:

```python
CompileHint(
    source_section_id="sec_failure_handling",
    text=mode.text,
    target="EXCEPTION_FLOW",
    suggested_flow="exception",
    suggested_condition=mode.text,
    metadata={
        "route_family": "flow_relevant",
        "slot_target": "condition",
        "semantic_role": "failure_mode",
        "executable": False,
    },
    evidence=[...],
)
```

The exact metadata values can be strings if the current project conventions
prefer JSON-serializable primitives:

```python
"executable": "false"
```

Use one convention consistently and test it.

## 2. Strengthen Failure Semantic Packets

Failure mode packets should point to the condition slot rather than only a broad
flow target.

Current likely target:

```text
["flow.exception"]
```

Target:

```text
["flow.exception.condition"]
```

This is adapter evidence only. Do not change Stage 2 routing in this task.

## 3. Add Packet-Level Evidence Where Possible

When a hard fact is produced from a semantic packet, its evidence should include:

```python
EvidenceRef(
    source_section_id=...,
    source_packet_id=...,
    quoted_text=...
)
```

At minimum, implement this for:

- `FailureModeFact`;
- `DelegationIntentFact`;
- input `VariableFact`;
- output `VariableFact`.

If the current adapter creates facts before packets, restructure locally within
the adapter so packet id can be referenced deterministically. Keep the change
small and local.

Do not require `source_span_ids` yet. Stage 1 owns span creation.

## 4. Strengthen Delegation Hints

For `Delegation policy`, hints should explicitly state that delegation intent is
not executable without a contract.

Expected delegation hint metadata:

```python
metadata={
    "route_family": "delegation_boundary",
    "semantic_role": "delegation_intent",
    "requires_contract": True,
    "executable": False,
}
```

The adapter may still emit:

```python
suggested_type="child_worker_candidate"
```

but metadata must make clear that this is not a materialized worker or invoke.

## 5. Strengthen Input / Output Contract Hints or Packet Metadata

Inputs and outputs should remain hard facts and non-executable resource
contracts.

For `runtime_input` and `required_output` semantic packets, add metadata such as:

```python
metadata={
    "route_family": "resource_contract",
    "semantic_role": "input_contract",  # or output_contract
    "executable": False,
}
```

If adding metadata to packets is too invasive, document why and add tests for
the hard facts' evidence instead. Prefer adding metadata because F2/F3 will use
it.

## Required Tests

Add or update tests in:

- `tests/unit/test_input_adapters.py`
- optionally `tests/unit/test_adapter_fact_verifier.py`
- optionally `tests/unit/test_input_adapter_pipeline.py`

### Test 1: Failure Hint Contract

Assert that structural failure handling produces a flow hint with:

- `target == "EXCEPTION_FLOW"`;
- `suggested_flow == "exception"`;
- `suggested_condition` equal to failure text;
- metadata route family is `flow_relevant`;
- metadata slot target is `condition`;
- metadata semantic role is `failure_mode`;
- metadata executable is false;
- evidence points to `sec_failure_handling`;
- evidence includes `source_packet_id` when packet exists.

### Test 2: Failure Packet Compile Target

Assert every `failure_mode` packet uses:

```text
flow.exception.condition
```

and not only:

```text
flow.exception
```

### Test 3: Hard Fact Packet Evidence

Assert at least these hard facts have packet-level evidence:

- one input fact;
- one output fact;
- one failure mode fact;
- one delegation intent fact.

Each evidence ref should have:

- `source_section_id`;
- `source_packet_id`;
- optional but preferred `quoted_text`.

### Test 4: Delegation Non-Executable Contract

Assert delegation hints or packet metadata state:

- `semantic_role = delegation_intent`;
- `route_family = delegation_boundary`;
- `requires_contract = true`;
- `executable = false`.

### Regression Test: No Routing Behavior Change

Re-run the F0 Stage 2 routing baseline and ensure:

- `failure_mode` still routes to `rules` in this phase;
- `delegation_rule` still routes to `behavior` in this phase;
- runtime inputs and required outputs are still consumed by adapter and not
  routed.

This regression protects the phase boundary. The route behavior changes later,
not in F1.

## Acceptance Criteria

F1 is complete when:

- failure mode hints identify `EXCEPTION_FLOW.condition`;
- failure mode packets identify `flow.exception.condition`;
- hard facts have packet-level evidence where deterministic packets exist;
- delegation hints explicitly remain non-executable without contract;
- input/output packets or facts identify non-executable resource contract
  semantics;
- F0 routing behavior remains unchanged;
- all added and adjacent tests pass;
- no downstream stages are modified;
- bridge functions are not modified except possibly comments, and preferably not
  touched at all;
- `docs/Todo/route_contract_refactor_progress_tracker.html` F1 section is
  updated or a JSON progress export is provided.

## Required Evidence For Review

When submitting for review, provide:

1. changed files;
2. exact test commands run;
3. test output summary;
4. diff summary proving no downstream stage changed;
5. example adapter output for one failure mode showing:

```text
packet_id
source_section_id
source_packet_id in evidence
target=EXCEPTION_FLOW
slot_target=condition
executable=false
```

6. confirmation that F0 routing baseline still passes.

## PM Review Checklist

- [ ] No `RouteAnnotation` introduced yet.
- [ ] No `FieldRouter` route behavior changed.
- [ ] No Stage 4 / Stage 7 / orchestrator bridge behavior changed.
- [ ] Failure hints are precise enough for F3.
- [ ] Hard facts have packet-level evidence where possible.
- [ ] Delegation remains non-executable without contract.
- [ ] F0 baseline tests still pass.

