# Task F4: Annotation-Aware AmbiguityResolver

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 Baseline Frontend Tests approved.
- F1 Adapter Hint and Evidence Strengthening approved.
- F2 RouteAnnotation IR approved.
- F3 Hint-Aware FieldRouter approved.

Related docs:

- `docs/Todo/route_contract_refactor_00_readme.md`
- `docs/Todo/route_contract_refactor_01_frontend_semantic_contract.md`
- `docs/Todo/route_contract_refactor_02_downstream_migration.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Make Stage 3 `AmbiguityResolver` preserve route annotations and provenance when
it splits ambiguous spans.

F3 made Stage 2 annotation-aware. F4 closes the compiler front-end contract by
ensuring Stage 3 does not silently drop those annotations.

## Scope

In scope:

- preserve `source_section_id` and `source_packet_id` on resolved child spans;
- preserve annotations for non-ambiguous spans;
- propagate parent annotations to split child spans when semantics are unchanged;
- derive child annotations from resolved route fields when the split separates
  action/policy material;
- optionally parse explicit annotation hints from the Stage 3 LLM response if
  present;
- keep legacy six-field route behavior compatible;
- add focused unit tests for annotation preservation and split behavior.

Out of scope:

- changing Stage 2 routing decisions;
- changing Stage 4 exception flow materialization;
- changing Stage 7 command generation;
- deleting bridge code;
- changing worker planning;
- requiring the LLM to generate perfect route annotations.

## Current Problem

`src/nl2spl/pipeline/stages/stage3_ambiguity_resolver.py` currently:

- creates new `SpanIR` objects with only `span_id` and `text`;
- drops parent `source_section_id` and `source_packet_id`;
- rebuilds `FieldRouteIR` from the six legacy lists only;
- drops `routes.annotations` entirely when any ambiguity is resolved.

That breaks the F3 contract:

```text
Stage 2 emits annotations
-> Stage 3 splits span
-> annotations disappear
```

F4 must prevent that loss before downstream stages begin relying on
annotations.

## Required Implementation

## 1. Preserve Child Span Provenance

When parsing each `resolved_spans` item:

- read `parent_span_id` when present;
- find the parent span;
- set child `source_section_id` and `source_packet_id` from explicit response
  values if present;
- otherwise inherit from the parent span.

Expected behavior:

```python
child.source_section_id = span_data.get("source_section_id") or parent.source_section_id
child.source_packet_id = span_data.get("source_packet_id") or parent.source_packet_id
```

If no parent is found, keep current tolerant behavior and log a warning rather
than failing the stage.

## 2. Preserve Non-Ambiguous Annotations

When creating `resolved_routes`, preserve annotations whose `span_id` belongs to
non-ambiguous original spans.

Example:

```text
input routes.annotations = [ann(s1), ann(s2)]
ambiguity_updates = [s1]
resolved annotations must keep ann(s2)
```

Do not duplicate preserved annotations.

## 3. Propagate Parent Annotations To Children

For every split child with a `parent_span_id`, find parent annotations and
propagate them to child spans.

Default behavior:

- copy parent annotation;
- replace `span_id` with child span id;
- keep `source_section_id`, `source_packet_id`, `source_hint_ids`,
  `route_family`, `construct_target`, `slot_target`, diagnostics, and metadata;
- update `field` from resolved route membership when known.

## 4. Derive Semantic Overrides From Resolved Routes

When the resolved child belongs to a field that clearly changes semantics, adjust
the propagated annotation conservatively:

| Resolved child field | Derived annotation behavior |
| --- | --- |
| `behavior` | `field="behavior"`, executable default `True` unless parent was explicitly non-executable failure/delegation material |
| `rules` | `field="rules"`, `semantic_role="constraint"`, `executable=False` |
| `domain` | `field="domain"`, executable `False` |
| `identity` | `field="identity"`, executable `False` |
| `audience` | `field="audience"`, executable `False` |
| `integrations` | `field="integrations"`, executable `False` |

Important exception:

- If the parent annotation is `semantic_role="failure_mode"` with
  `construct_target="EXCEPTION_FLOW"` and `slot_target="condition"`, do not turn
  it into an executable behavior annotation just because a child is in
  `behavior`. Keep it non-executable unless an explicit route annotation in the
  LLM response says otherwise and passes validation.

## 5. Optional LLM Annotation Parsing

Support, but do not require, a response field such as:

```json
{
  "route_annotations": [
    {
      "span_id": "s1a",
      "field": "behavior",
      "semantic_role": "process_step",
      "executable": true
    }
  ]
}
```

Rules:

- parse only known `RouteAnnotation` fields;
- ignore unknown keys;
- prefer explicit valid response annotations over inferred clones;
- still preserve provenance from parent when explicit annotation omits it;
- never allow explicit response annotations to remove provenance for structural
  spans.

If this is too large for F4, implement the inference path first and add explicit
response parsing as a follow-up subtask inside F4.

## 6. Checkpoint Compatibility

Stage 3 checkpoint must include serialized `resolved_routes.annotations` through
`asdict(resolved_routes)`.

The no-ambiguity fast path should continue returning the original `spans` and
`routes` objects unchanged.

## Required Tests

Add focused tests in:

- `tests/unit/test_ambiguity_resolver.py`
- optionally `tests/unit/test_stage3_prompt.py` if prompt fixture behavior needs
  compatibility checks.

### Test 1: No Ambiguity Preserves Original Routes Object

Existing behavior should remain:

- no LLM call;
- same `routes` object returned;
- annotations unchanged.

### Test 2: Split Child Spans Inherit Provenance

Input:

- parent span has `source_section_id` and `source_packet_id`;
- LLM returns child spans with `parent_span_id` only.

Assert:

- each child span inherits parent section and packet provenance.

### Test 3: Non-Ambiguous Annotation Preserved

Input:

- route annotations for `s1` and `s2`;
- only `s1` is ambiguous.

Assert:

- annotation for `s2` remains in resolved routes.

### Test 4: Action/Policy Split Produces Executable And Non-Executable Annotations

Input:

- parent span has a behavior annotation;
- LLM splits into `s1a` in `behavior` and `s1b` in `rules`.

Assert:

- `s1a` annotation has `field="behavior"` and `executable=True`;
- `s1b` annotation has `field="rules"`,
  `semantic_role="constraint"`, and `executable=False`;
- both child annotations preserve parent provenance.

### Test 5: Failure Mode Annotation Is Not Turned Into Command

Input:

- parent annotation has `semantic_role="failure_mode"`,
  `construct_target="EXCEPTION_FLOW"`, `slot_target="condition"`,
  `executable=False`;
- LLM split output includes a child in `behavior`.

Assert:

- propagated failure annotation remains `executable=False`;
- construct and slot targets are preserved.

### Test 6: Stage 3 Checkpoint Includes Annotations

Patch `save_checkpoint`, run a split case, and assert:

- `resolved_routes` contains `annotations`;
- annotation entries include span ids and provenance.

### Test 7: Legacy Route Tests Still Pass

Existing tests that only inspect old route lists should keep passing.

## Acceptance Criteria

F4 is complete when:

- split child spans preserve structural provenance;
- non-ambiguous annotations survive Stage 3;
- split child annotations are generated for behavior/rule children;
- action/policy splits produce executable behavior and non-executable rules;
- failure-mode annotations remain non-executable condition material;
- old six-field route behavior remains compatible;
- no downstream stage behavior changes;
- Stage 3 checkpoint includes annotations;
- relevant Stage 3, F0-F3, and full unit tests pass.

## Required Evidence For Review

When submitting F4 for review, provide:

1. changed files;
2. exact test commands and output summary;
3. sample split child span showing inherited `source_section_id` and
   `source_packet_id`;
4. sample resolved annotations for action/policy split;
5. sample failure-mode split annotation showing `executable=False`;
6. confirmation that old Stage 3 tests still pass;
7. confirmation that no Stage 4/7/bridge/orchestrator code was changed.

## PM Review Checklist

- [ ] Child spans inherit provenance.
- [ ] Non-ambiguous annotations are preserved.
- [ ] Ambiguous parent annotations are propagated or explicitly replaced.
- [ ] Rule children are non-executable constraints.
- [ ] Behavior children are executable unless parent semantics forbid it.
- [ ] Failure-mode annotations remain non-executable exception conditions.
- [ ] Checkpoint includes annotations.
- [ ] Legacy Stage 3 behavior remains compatible.
- [ ] No downstream migration is mixed into this phase.
