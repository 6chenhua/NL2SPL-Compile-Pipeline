# Construct Demand Plan Architecture Gap

Date: 2026-06-06

Status: Open

## Summary

The current pipeline has an architecture gap between `RouteAnnotation` and IRS:

```text
RouteAnnotation
  -> Stage 3.5 / Stage 4 / Stage 5 consume annotations directly or indirectly
  -> IRS checks materialized/source-demanded constructs
```

What is missing is an explicit compiler pass that turns route-level slot evidence into source-demanded construct instances before worker planning and flow assembly.

Proposed placeholder name:

```text
ConstructDemandPlan
```

Alternative names:

```text
RouteConstructPlan
SourceDemandPlan
ConstructMaterializationPlan
```

This document uses `ConstructDemandPlan` because the core responsibility is to record which constructs are demanded by source evidence, before deciding whether they can be materialized.

## Discovery Origin

This gap was found while reviewing:

```text
docs/Todo/exception_flow_routing_issues.md
```

The review asked whether the exception-flow routing problems in that document were real. The code audit showed:

1. Stage 2 route annotations can mark:

   ```text
   EXCEPTION_FLOW.condition
   EXCEPTION_FLOW.handler
   ```

2. Stage 4 receives executable behavior spans, including handler spans, but its LLM prompt does not carry the handler slot semantics.

3. `_filter_non_condition_exception_flows()` protects exception flow condition provenance, but it does not remove a handler span that the LLM placed in `main_flow_spans`.

4. Worker-aware flow materialization assigns exception conditions by span ownership, but there is no construct-level condition-handler ownership constraint before Stage 3.5 commits worker boundaries.

5. IRS already has the concepts needed to check source-demanded and materialized constructs, but the current architecture does not define who creates the source-demanded construct from route annotations.

This is not primarily an IRS checker bug. It is an upstream compiler-pass gap.

## Why This Is Not an IRS Responsibility

IRS design explicitly says checkers must not:

```text
- parse raw NL
- call LLM
- modify input IR
- generate new SPL constructs
- fill missing slots
- fabricate child construct reports without source demand
```

Therefore an IRS checker should not be responsible for:

```text
RouteAnnotation(EXCEPTION_FLOW.condition)
+ RouteAnnotation(EXCEPTION_FLOW.handler)
-> ExceptionFlow construct demand
```

That conversion is construct planning/materialization input, not satisfaction checking.

The intended responsibility split is:

```text
ConstructDemandPlan:
  Which constructs are demanded by source evidence?
  Which spans support each slot?
  Which spans belong to the same construct?
  What ownership/pairing constraints must downstream stages preserve?

IRS:
  Given a materialized or source-demanded construct instance,
  are its slots satisfied according to ConstructIRS / SlotSpec?
  Is it complete, partial, blocked, or renderable?
  What diagnostic should be projected?
```

## Why It Must Exist Before Stage 3.5

Stage 3.5 decides worker boundaries and span ownership. If construct demand is discovered only after Stage 3.5, the worker plan may already have split one construct across workers.

Example:

```text
s2 = EXCEPTION_FLOW.condition -> worker_main
s3 = EXCEPTION_FLOW.handler   -> worker_notify
```

Without a construct-aware plan, Stage 3.5 only sees spans. It does not know that `s2` and `s3` are slots of the same `EXCEPTION_FLOW` construct.

The plan should provide constraints like:

```text
ExceptionFlowDemand(exc_route_00):
  condition_span_ids = ["s2"]
  handler_span_ids = ["s3"]
  owner_policy = condition_owner
  atomicity = same_exception_construct
```

Then worker planning can decide:

```text
- keep handler with the condition owner
- allow dual-role handler only when explicitly annotated as process_step too
- emit cross_worker_exception_handler_split when ownership cannot be repaired
```

## Proposed Data Flow

```text
Stage 1 SpanIR
  -> Stage 2 RouteAnnotation
  -> Stage 2.5 ConstructDemandPlanner
  -> ConstructDemandPlan
  -> Stage 3.5 WorkerBoundaryPlanner
  -> Worker-aware ConstructDemandPlan
  -> Stage 4 FlowAssembler
  -> Stage 5 BlockAssembler
  -> Stage 7 StepExtractor
  -> Stage 9.5 / Post-normalize IRS
```

Stage 4 should receive separated inputs:

```text
normal_behavior_spans
reserved_construct_spans
construct_demand_plan
```

The LLM should not be asked to re-classify reserved exception handler spans as main, alternative, or exception flow spans. Those spans already belong to construct slots.

## Minimal Data Model Sketch

```python
@dataclass
class ExceptionFlowDemand:
    demand_id: str
    construct_type: str = "EXCEPTION_FLOW"
    condition_span_ids: list[str] = field(default_factory=list)
    handler_span_ids: list[str] = field(default_factory=list)
    condition_text: str | None = None
    source_section_id: str | None = None
    source_packet_id: str | None = None
    failure_item_index: int | None = None
    pairing_status: Literal[
        "complete",
        "missing_handler",
        "orphan_handler",
        "ambiguous",
        "empty_condition",
    ] = "ambiguous"
    owner_worker_id: str | None = None
    dual_role_span_ids: list[str] = field(default_factory=list)
    source_span_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

```python
@dataclass
class ConstructDemandPlan:
    exception_flows: list[ExceptionFlowDemand] = field(default_factory=list)
    reserved_span_ids: set[str] = field(default_factory=set)
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

The exact production model may differ, but it should preserve:

```text
- construct id
- construct type
- slot-specific source spans
- source section / packet provenance
- pairing status
- worker ownership constraints
- dual-role status
```

## Relationship To IRS

`ConstructDemandPlan` is upstream of IRS.

```text
ConstructDemandPlan
  -> creates source-demanded construct instances
  -> IRS checks slot satisfaction
```

Example:

```text
ExceptionFlowDemand:
  condition_span_ids = ["s2"]
  handler_span_ids = []
  pairing_status = "missing_handler"
```

becomes:

```text
ConstructInstance:
  construct_type = EXCEPTION_FLOW
  materialized = true or source_demanded = true
  slots:
    condition = source-backed
    handler = missing
```

IRS then applies `ConstructIRS` / `SlotSpec`:

```text
condition required_for_partial -> satisfied
handler required_for_complete  -> missing
partial_rendering_allowed      -> cutline_partial
diagnostic                     -> missing_handler
```

The planner decides "what should exist"; IRS decides "whether it is sufficiently complete".

## Test Boundary Examples

These examples should be retained as regression boundaries when implementing the planner.

### TC-1: Handler Must Not Leak Into Main Flow

Input:

```text
s1 process_step, executable=True
s2 EXCEPTION_FLOW.condition, executable=False
s3 EXCEPTION_FLOW.handler, executable=True
```

Bad Stage 4 LLM output:

```json
{
  "main_flow_spans": ["s1", "s3"],
  "exception_flows": []
}
```

Expected architecture-level behavior:

```text
ConstructDemandPlan reserves s3 as handler slot.
Stage 4 normal_behavior_spans excludes s3.
main_flow_spans must not contain s3 unless s3 also has process_step annotation.
```

### TC-2: Handler Misclassified As Condition

Input:

```text
s2 EXCEPTION_FLOW.condition
s3 EXCEPTION_FLOW.handler
```

Bad Stage 4 LLM output:

```json
{
  "exception_flows": [
    {"flow_id": "exc_bad", "condition_text": "retry payment", "spans": ["s3"]}
  ]
}
```

Expected behavior:

```text
s3 is reserved as handler evidence, never condition evidence.
ExceptionFlowDemand condition remains s2.
LLM-generated condition from s3 is ignored or sanitized.
```

Current code already filters this in `_filter_non_condition_exception_flows()`, but the planner should make this invariant explicit before Stage 4.

### TC-3: Condition And Handler Split Across Workers

Input:

```text
worker_main owns s2 condition
worker_notify owns s3 handler
```

Expected behavior:

```text
ConstructDemandPlan records s2 and s3 as one EXCEPTION_FLOW demand.
Stage 3.5 uses construct ownership constraint.
Either:
  handler follows condition owner
or:
  cross_worker_exception_handler_split diagnostic is emitted.
```

### TC-4: Empty Condition With Handler

Input:

```text
s2 EXCEPTION_FLOW.condition text="None"
s3 EXCEPTION_FLOW.handler
```

Expected behavior:

```text
No materialized exception flow from empty condition.
s3 becomes orphan_handler or unpaired_handler evidence.
No handler command is rendered unless it is independently process_step.
```

### TC-5: Multiple Conditions Share One Handler

Input:

```text
s2 EXCEPTION_FLOW.condition
s3 EXCEPTION_FLOW.condition
s4 EXCEPTION_FLOW.handler
```

Expected behavior:

```text
Planner must not silently pair s4 to the first condition by section fallback.
It must choose an explicit policy:
  one-to-many supported
or:
  ambiguous_exception_pairing diagnostic
```

### TC-6: Dual Role Handler And Process Step

Input:

```text
s3 has:
  process_step executable=True
  EXCEPTION_FLOW.handler executable=True
```

Expected behavior:

```text
s3 may remain in normal_behavior_spans because it is explicitly process_step.
s3 also remains handler_span_ids for the exception demand.
The dual role must be explicit in ConstructDemandPlan.dual_role_span_ids.
```

## Expected Architectural Outcomes

After this gap is addressed:

```text
- Stage 3.5 becomes construct-aware.
- Stage 4 no longer receives handler-only spans as normal flow candidates.
- Stage 5 does not need ad-hoc handler materialization helpers.
- IRS receives clear source-demanded construct instances.
- missing_handler and cross-worker split diagnostics have stable targets.
- provenance can be tied to construct slots instead of mixed span lists.
```

## Non-Goals

This plan should not:

```text
- move IRS checker responsibilities into ConstructDemandPlanner
- make the planner call LLM
- make the planner generate handler text or commands
- replace Post-normalize IRS
- replace ExecutableElementGate
- replace ProducerIndex
- implement recursive IRS traversal
```

## Open Questions

1. Should `ConstructDemandPlan` be a generic plan for all constructs, or should it start as an exception-flow-only plan and later generalize?
2. Should the planner output be part of `IRSCheckContext`, or a separate pipeline IR passed to Stage 3.5/4/5/7?
3. Should `ExceptionFlowIR` split `condition_span_ids` and `handler_span_ids`, or should the split exist only in the demand plan first?
4. Should stage-local IRS consume `ConstructDemandPlan` directly, or only consume materialized `ConstructInstance` objects derived from it?
5. What is the default policy for one handler serving multiple conditions?

