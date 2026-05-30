# Task F3: Hint-Aware FieldRouter

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 Baseline Frontend Tests approved.
- F1 Adapter Hint and Evidence Strengthening approved.
- F2 RouteAnnotation IR approved.

Related docs:

- `docs/Todo/route_contract_refactor_00_readme.md`
- `docs/Todo/route_contract_refactor_01_frontend_semantic_contract.md`
- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Teach Stage 2 `FieldRouter` to consume adapter evidence and emit
`RouteAnnotation` entries for structural NL, while preserving the legacy
six-field route lists.

This phase creates the route contract needed by downstream migration. It must
not change Stage 3, Stage 4, Stage 7, bridge code, or orchestrator behavior.

## Scope

In scope:

- build packet, section, hard fact, and compile hint indexes in the canonical
  routing path;
- emit `RouteAnnotation` for structural packet-backed spans;
- emit annotations for adapter-consumed hard fact spans;
- preserve old list routing compatibility;
- include route provenance from section, packet, and hint ids;
- add route diagnostics only when hints are missing or conflict with packet
  semantics;
- add focused unit tests.

Out of scope:

- moving failure mode spans out of `routes.rules`;
- making Stage 4 materialize exception flows from annotations;
- making Stage 7 consume only executable behavior;
- deleting or weakening `bridge_failure_modes()`;
- changing generic NL LLM routing behavior;
- changing ambiguity splitting behavior.

## Required Implementation

## 1. Preserve Legacy Lists Exactly

For this phase, keep the current old-list behavior:

| Packet type | Legacy list behavior for F3 |
| --- | --- |
| `task_family` | `routes.domain` |
| `process_step` | `routes.behavior` |
| `policy` | `routes.rules` |
| `failure_mode` | `routes.rules` |
| `delegation_rule` | `routes.behavior` |
| `runtime_input` | no old route list entry |
| `required_output` | no old route list entry |

The existing F0 test
`test_stage2_canonical_routing_per_packet_type` must still pass without
semantic rewrites.

## 2. Add Canonical Indexes

In `src/nl2spl/pipeline/stages/stage2_field_router.py`, the canonical path
should index:

- `semantic_packets` by `packet_id`;
- `raw_sections` by `section_id`;
- `compile_hints` by packet id and/or source section id;
- hard fact inputs and outputs by evidence packet id when available.

Prefer small private helpers over a large inline block inside
`_execute_canonical()`.

Suggested helper shape:

```python
def _build_canonical_route_context(
    self,
    canonical_input: CanonicalCompileInput,
) -> CanonicalRouteContext:
    ...
```

A private dataclass is acceptable if it keeps the routing logic readable.

## 3. Emit RouteAnnotation For Packet-Backed Spans

Every structural span with `source_packet_id` should receive at least one
annotation, including spans that are intentionally not inserted into old route
lists.

Expected annotation semantics:

| Packet type | Annotation expectation |
| --- | --- |
| `task_family` | `field="domain"`, `semantic_role="profile_domain"`, `executable=False` |
| `runtime_input` | `field="resources"`, `semantic_role="input_contract"`, `route_family="resource_contract"`, `executable=False` |
| `required_output` | `field="resources"`, `semantic_role="output_contract"`, `route_family="resource_contract"`, `executable=False` |
| `process_step` | `field="behavior"`, `semantic_role="process_step"`, `route_family="flow_relevant"`, `executable=True` |
| `policy` | `field="rules"`, `semantic_role="constraint"`, `executable=False` |
| `failure_mode` | `field="behavior"`, `semantic_role="failure_mode"`, `route_family="flow_relevant"`, `construct_target="EXCEPTION_FLOW"`, `slot_target="condition"`, `executable=False` |
| `delegation_rule` | `field="behavior"`, `semantic_role="delegation_intent"`, `route_family="delegation_boundary"`, `executable=False` |

Important compatibility rule:

- failure mode annotations may say `field="behavior"` because they are
  flow-relevant;
- the old list must still keep the same span in `routes.rules` until Stage 4
  and Stage 7 are annotation-aware.

## 4. Use Adapter Hints As Evidence, Not Final Truth

Compile hints from F1 should populate annotation fields when they are available:

- `source_hint_ids`;
- `construct_target`;
- `slot_target`;
- `route_family`;
- `semantic_role`;
- `executable`.

Packet semantics remain the fallback when hints are absent.

If a hint conflicts with the packet type, prefer the packet type for F3 and add
a diagnostic string to the annotation. Do not fail the stage.

Examples:

- `failure_mode` packet without hint still becomes an
  `EXCEPTION_FLOW.condition` candidate.
- `failure_mode` packet with `slot_target=handler` should be corrected to
  `condition` and record a diagnostic.
- `runtime_input` and `required_output` remain non-executable even if a hint is
  incomplete.

## 5. Preserve Provenance

Each annotation should include:

- `span_id`;
- `source_section_id` from the span or packet evidence;
- `source_packet_id`;
- `source_hint_ids` when hints informed the route.

Do not drop provenance for adapter-consumed resource contract spans.

## 6. Checkpoint Compatibility

The existing `asdict(routes)` checkpoint should include `annotations`
automatically after F2. Add a test or assertion that Stage 2 checkpoint data
contains serialized annotations for canonical structural input.

Do not change checkpoint format for generic NL beyond the new optional
`annotations` field on `FieldRouteIR`.

## Required Tests

Add focused tests in one or both files:

- `tests/unit/test_field_router.py`
- `tests/unit/test_input_adapter_pipeline.py`

### Test 1: Structural Canonical Route Emits Annotations

Run `StructuralNLAdapter -> SpanSlicer -> FieldRouter`.

Assert:

- `routes.annotations` is non-empty;
- packet-backed spans have annotations;
- annotations include section and packet provenance;
- `ambiguity_updates == []`;
- `mock_client.call_json.assert_not_called()`.

### Test 2: Failure Mode Annotation

For each `failure_mode` packet span, assert:

- old list compatibility: span remains in `routes.rules`;
- annotation has `field == "behavior"`;
- `semantic_role == "failure_mode"`;
- `route_family == "flow_relevant"`;
- `construct_target == "EXCEPTION_FLOW"`;
- `slot_target == "condition"`;
- `executable is False`;
- `source_section_id` and `source_packet_id` are present.

### Test 3: Resource Contracts Are Annotated But Not Routed

For `runtime_input` and `required_output` packet spans, assert:

- span is not in `routes.get_all_span_ids()`;
- annotation exists;
- annotation uses `route_family == "resource_contract"`;
- annotation has `executable is False`;
- semantic role is `input_contract` or `output_contract`.

### Test 4: Delegation Is Non-Executable Boundary Material

For `delegation_rule` packet spans, assert:

- old list compatibility: span remains in `routes.behavior`;
- annotation has `semantic_role == "delegation_intent"`;
- annotation has `route_family == "delegation_boundary"`;
- annotation has `executable is False`.

### Test 5: Process Step Remains Executable

For `process_step` packet spans, assert:

- span remains in `routes.behavior`;
- annotation has `semantic_role == "process_step"`;
- annotation has `executable is True`;
- `routes.get_executable_behavior_span_ids()` includes these spans in behavior
  order.

### Test 6: Legacy Baseline Still Passes

Keep or extend `test_stage2_canonical_routing_per_packet_type`.

Do not rewrite it to the downstream target semantics yet.

### Test 7: Generic NL Path Remains Compatible

For LLM/generic `FieldRouter.execute(spans)` tests, assert:

- mocked LLM routing still works;
- constructing `FieldRouteIR` from old route JSON still produces
  `annotations == []`.

## Acceptance Criteria

F3 is complete when:

- canonical structural Stage 2 emits route annotations;
- all packet-backed structural spans have annotation provenance;
- failure modes have non-executable `EXCEPTION_FLOW.condition` annotations;
- runtime input and required output spans have non-executable resource contract
  annotations and still do not enter old route lists;
- delegation spans have non-executable delegation boundary annotations and
  still preserve old-list compatibility;
- process steps remain executable behavior;
- old six-field routing baseline is unchanged;
- generic NL path remains compatible;
- Stage 2 checkpoint includes annotations;
- no Stage 3/4/7/downstream/bridge/orchestrator production code is changed;
- all F0/F1/F2/F3 relevant unit tests pass.

## Required Evidence For Review

When submitting F3 for review, provide:

1. changed files;
2. exact test commands and output summary;
3. sample failure mode annotation;
4. sample runtime input or required output annotation;
5. confirmation that `test_stage2_canonical_routing_per_packet_type` still
   passes;
6. confirmation that generic NL tests still pass;
7. confirmation that Stage 3/4/7/downstream/bridge/orchestrator code was not
   changed.

## PM Review Checklist

- [ ] Failure mode old list remains `rules`.
- [ ] Failure mode annotation targets `EXCEPTION_FLOW.condition`.
- [ ] Failure mode annotation is non-executable.
- [ ] Resource contracts are annotated but not old-list routed.
- [ ] Delegation intent is non-executable.
- [ ] Process steps remain executable.
- [ ] Provenance includes section and packet ids.
- [ ] Hints populate annotation metadata without overriding packet semantics
      unsafely.
- [ ] Generic NL path remains backward compatible.
- [ ] No downstream migration is mixed into this phase.
