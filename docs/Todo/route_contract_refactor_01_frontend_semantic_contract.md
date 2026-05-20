# Route Contract Refactor 01: Frontend Semantic Contract

Date: 2026-05-18

## Purpose

This document defines the front-end part of the route contract refactor.

It covers:

- `CanonicalCompileInput`
- `InputAdapter`
- `SpanSlicer`
- `FieldRouteIR`
- `FieldRouter`
- `AmbiguityResolver`

The goal is to make `FieldRoute` the unified semantic routing layer without
breaking current downstream stages.

## Target Relationship

```text
InputAdapter = schema-aware pre-understanding layer
FieldRoute = schema-agnostic semantic routing layer
Later stages = SPL construct / IR generation layer
```

`InputAdapter` should provide evidence and hints. It should not generate final
compiler IR.

`FieldRoute` should interpret spans plus adapter evidence and produce a stable
route contract for downstream stages.

## Current Frontend Problems

### Problem 1: FieldRouteIR only has six field lists

Current shape:

```text
identity
audience
rules
domain
integrations
behavior
```

This cannot represent:

- semantic role;
- construct target;
- slot target;
- executable versus non-executable material;
- adapter hint usage;
- packet provenance;
- multi-label spans;
- route diagnostics.

### Problem 2: FieldRouter canonical path routes by packet type only

Current structural routing mostly does this:

```text
task_family      -> domain
process_step     -> behavior
policy           -> rules
failure_mode     -> rules
delegation_rule  -> behavior
runtime_input    -> consumed
required_output  -> consumed
```

This does not fully consume adapter hints and hard facts.

### Problem 3: Failure handling is under-specified

Failure modes currently reach `EXCEPTION_FLOW` through downstream bridge logic.
That works as a patch, but the route layer should explicitly represent:

```text
failure_mode -> EXCEPTION_FLOW.condition candidate, executable=false
```

### Problem 4: Ambiguity resolution can drop future route metadata

Stage 3 currently rebuilds `FieldRouteIR` from old lists. Once route
annotations exist, split spans must preserve provenance and route semantics.

## Target Frontend Contract

### RouteAnnotation

Add a route annotation model:

```python
@dataclass
class RouteAnnotation:
    span_id: str
    field: str
    semantic_role: str | None = None
    route_family: str | None = None
    source_section_id: str | None = None
    source_packet_id: str | None = None
    source_hint_ids: list[str] = field(default_factory=list)
    construct_target: str | None = None
    slot_target: str | None = None
    executable: bool = True
    primary: bool = True
    diagnostics: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

Extend `FieldRouteIR` compatibly:

```python
@dataclass
class FieldRouteIR:
    identity: list[str] = field(default_factory=list)
    audience: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    domain: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    behavior: list[str] = field(default_factory=list)
    annotations: list[RouteAnnotation] = field(default_factory=list)
```

The old lists remain during migration.

### Helper API

Add helper methods to `FieldRouteIR`:

```python
get_annotations(span_id: str) -> list[RouteAnnotation]
get_primary_field(span_id: str) -> str | None
get_executable_behavior_span_ids() -> list[str]
get_non_executable_behavior_span_ids() -> list[str]
get_construct_slot_candidates(construct: str, slot: str) -> list[RouteAnnotation]
get_annotations_by_role(role: str) -> list[RouteAnnotation]
```

Downstream stages should migrate to these helpers rather than directly reading
raw field lists.

## CanonicalCompileInput Changes

### Required Changes

Strengthen `CompileHint` usage without changing the whole model immediately.

For failure handling:

```text
target = EXCEPTION_FLOW
suggested_condition = failure text
metadata.route_family = flow_relevant
metadata.slot_target = condition
metadata.executable = false
```

For failure semantic packets:

```text
packet_type = failure_mode
compile_targets = ["flow.exception.condition"]
modality = hard_fact
```

For delegation policy:

```text
metadata.route_family = delegation_boundary
metadata.executable = false
metadata.requires_contract = true
```

For inputs / outputs:

```text
metadata.route_family = resource_contract
metadata.executable = false
```

### Acceptance Criteria

- Structural failure modes carry explicit exception-flow condition hints.
- No confidence score is introduced.
- Existing canonical validator still rejects invalid section/packet references.
- Existing adapter tests remain compatible.

## InputAdapter Changes

### StructuralNLAdapter

Required changes:

1. Emit packet-level evidence when creating hard facts.
2. Strengthen `failure_handling` compile hints.
3. Strengthen `delegation_policy` compile hints.
4. Keep `inputs_for_each_run` and `required_outputs` as hard facts, not
   behavior spans.
5. Do not generate `ExceptionFlow`, `WorkerPlanIR`, or `StepIR`.

### GenericNLAdapter

Required changes:

1. Keep freeform behavior compatible.
2. If LLM fact extraction is enabled, produce packet evidence.
3. Do not fabricate route annotations in the adapter itself.

### Acceptance Criteria

- Structural input produces deterministic hard facts and hints.
- Generic input still falls back to legacy LLM span routing if no canonical
  packets exist.
- Adapter output remains a `CanonicalCompileInput`.

## SpanSlicer Changes

Current canonical path creates one span per semantic packet, then section spans
for uncovered sections.

Required changes:

1. Preserve `source_section_id`.
2. Preserve `source_packet_id`.
3. If packet evidence later includes quote offsets, preserve enough span data
   for downstream trace resolution.

Acceptance criteria:

- Every structural packet-backed span has both section and packet provenance.
- No current Stage 1 tests regress.

## FieldRouter Changes

### Routing Priorities

Canonical routing should use this priority order:

1. hard fact resource contracts;
2. failure modes as exception condition candidates;
3. process steps as executable behavior;
4. policies as constraints;
5. delegation intents as non-executable delegation boundary material;
6. profile/domain context;
7. fallback behavior for unknown packet types.

### Expected Structural Mapping

| Source | Route Annotation |
| --- | --- |
| `task_family` | `field=domain`, `semantic_role=profile_domain`, `executable=false` |
| `inputs_for_each_run` | `semantic_role=input_contract`, `route_family=resource_contract`, `executable=false` |
| `required_outputs` | `semantic_role=output_contract`, `route_family=resource_contract`, `executable=false` |
| `reusable_process` | `field=behavior`, `semantic_role=process_step`, `executable=true` |
| `policies` | `field=rules`, `semantic_role=constraint`, `executable=false` |
| `failure_handling` | `field=behavior`, `semantic_role=failure_mode`, `construct_target=EXCEPTION_FLOW`, `slot_target=condition`, `executable=false` |
| `delegation_policy` | `semantic_role=delegation_intent`, `route_family=delegation_boundary`, `executable=false` |

Note: putting failure modes in `field=behavior` is acceptable only after
downstream stages use `executable=false` correctly. Until then, the old field
list may keep them out of `routes.behavior` while annotations carry the target
semantics.

### Compatibility Rule

During the transition:

- old lists must remain valid;
- annotations are authoritative for new code;
- old list fields are fallback for stages not yet migrated.

### Acceptance Criteria

- `FieldRouter` emits route annotations for structural input.
- Failure handling has exception condition annotations.
- Inputs and outputs are not executable.
- Delegation policy is not executable by default.
- Stage 2 checkpoint includes annotations.
- Existing tests that inspect old field lists still pass or are updated only
  where semantics intentionally change.

## AmbiguityResolver Changes

Required changes:

1. Preserve provenance when splitting spans.
2. Propagate parent annotations to child spans when the split does not change
   semantics.
3. Allow split output to override semantic role when LLM explicitly separates
   action and constraint.
4. Do not drop `source_section_id` or `source_packet_id`.

Acceptance criteria:

- Ambiguous action/policy span can split into executable behavior and
  non-executable rule annotations.
- Split failure/policy spans retain section and packet provenance.
- No annotation silently disappears during Stage 3.

## Frontend Phase Plan

### F0: Baseline Frontend Tests

Tasks:

1. Add tests for current adapter output.
2. Add tests for current Stage 1 section/packet provenance.
3. Add tests documenting current failure-mode route behavior.

Acceptance:

- Baseline tests pass or are marked as known gaps.
- No production behavior changes.

### F1: Adapter Hint and Evidence Strengthening

Tasks:

1. Add stronger failure hints.
2. Add stronger delegation hints.
3. Add packet evidence where available.

Acceptance:

- Failure modes cite condition target.
- Delegation remains non-executable.
- Validator passes.

### F2: RouteAnnotation IR

Tasks:

1. Add `RouteAnnotation`.
2. Extend `FieldRouteIR`.
3. Add helper methods.
4. Keep old field lists.

Acceptance:

- Old tests constructing `FieldRouteIR(behavior=[...])` still work.
- New annotation helper tests pass.

### F3: Hint-Aware FieldRouter

Tasks:

1. Build packet / section / hint indexes.
2. Emit annotations.
3. Keep old list compatibility.
4. Add route diagnostics.

Acceptance:

- Structural failure mode annotation exists.
- Hard facts are non-executable.
- Generic NL path remains compatible.

### F4: Annotation-Aware AmbiguityResolver

Tasks:

1. Preserve annotation/provenance across split.
2. Update ambiguity output parsing.
3. Add tests for mixed action/constraint/failure spans.

Acceptance:

- Split spans keep provenance.
- Split routes include annotations.

## Frontend Completion Gate

Frontend work is complete when:

- `FieldRouteIR.annotations` exists and is populated for structural input;
- failure modes are represented as non-executable exception condition
  candidates;
- downstream stages can query executable behavior candidates without reading
  `routes.behavior` directly;
- no adapter directly generates final compiler IR.

