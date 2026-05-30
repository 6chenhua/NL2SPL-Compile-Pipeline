# Task F2: RouteAnnotation IR

Date assigned: 2026-05-20

Owner: TBD

Reviewer: PM / Codex

Prerequisites:

- F0 Baseline Frontend Tests approved.
- F1 Adapter Hint and Evidence Strengthening approved.

Related docs:

- `docs/Todo/route_contract_refactor_00_readme.md`
- `docs/Todo/route_contract_refactor_01_frontend_semantic_contract.md`
- `docs/Todo/route_contract_refactor_progress_tracker.html`

## Objective

Introduce a backward-compatible route annotation model.

This phase creates the IR contract that later phases will use. It must not
change `FieldRouter` behavior yet.

## Scope

In scope:

- add `RouteAnnotation`;
- extend `FieldRouteIR` with `annotations`;
- add route helper methods;
- update serialization/checkpoint compatibility if needed;
- add unit tests for annotations and helper behavior.

Out of scope:

- changing `FieldRouter` routing decisions;
- making `FieldRouter` emit annotations;
- changing Stage 3, Stage 4, Stage 7, or worker-aware stages;
- moving failure modes from `rules` to annotation-driven exception routing;
- deleting bridge code.

## Required Implementation

## 1. Add RouteAnnotation

Preferred location:

- `src/nl2spl/ir/field_route_ir.py`

Add:

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

If importing `Any`, keep it local and minimal.

## 2. Extend FieldRouteIR

Add:

```python
annotations: list[RouteAnnotation] = field(default_factory=list)
```

Do not remove or rename the existing six fields:

- `identity`
- `audience`
- `rules`
- `domain`
- `integrations`
- `behavior`

Existing construction patterns such as:

```python
FieldRouteIR(behavior=["s1"])
```

must keep working.

## 3. Add Helper Methods

Add methods:

```python
get_annotations(span_id: str) -> list[RouteAnnotation]
get_primary_field(span_id: str) -> str | None
get_executable_behavior_span_ids() -> list[str]
get_non_executable_behavior_span_ids() -> list[str]
get_construct_slot_candidates(construct: str, slot: str) -> list[RouteAnnotation]
get_annotations_by_role(role: str) -> list[RouteAnnotation]
```

Expected behavior:

- if annotations exist, helper methods should prefer annotations;
- if annotations do not exist, executable behavior fallback should return
  `routes.behavior`;
- `get_primary_field()` should fall back to current `get_field_for_span()`;
- construct/role helpers return empty lists when no annotations exist.

## 4. Keep Overlap Compatibility

Do not remove `validate_no_overlap()` yet.

Clarify by test or docstring:

- old six-field overlap is still checked;
- annotation-level multi-label semantics are allowed and should not be blocked
  by `validate_no_overlap()`.

## Required Tests

Add or update tests in:

- `tests/unit/test_field_router.py`
- or a new focused test file such as `tests/unit/test_field_route_ir.py`

### Test 1: Backward Compatibility

Assert existing construction still works:

```python
routes = FieldRouteIR(behavior=["s1"])
assert routes.get_executable_behavior_span_ids() == ["s1"]
assert routes.get_primary_field("s1") == "behavior"
```

### Test 2: Annotation Lookup

Create annotations and assert:

- `get_annotations("s1")` returns matching annotations;
- `get_annotations_by_role("failure_mode")` works;
- `get_construct_slot_candidates("EXCEPTION_FLOW", "condition")` works.

### Test 3: Executable Behavior Filtering

Create:

- one executable behavior annotation;
- one non-executable behavior annotation with `semantic_role="failure_mode"`.

Assert:

- executable helper returns only executable span;
- non-executable helper returns the failure span.

### Test 4: Primary Field Fallback

Assert:

- primary annotation wins when present;
- old list fallback works when no annotation exists.

### Test 5: Annotation Multi-Label Does Not Count As Old Overlap

Create two annotations for the same span with different semantic roles.

Assert:

- helper returns both annotations;
- `validate_no_overlap()` does not report overlap unless the old six lists
  overlap.

## Acceptance Criteria

F2 is complete when:

- `RouteAnnotation` exists;
- `FieldRouteIR.annotations` exists;
- helper methods work with annotations;
- helper methods preserve old-list fallback behavior;
- old `FieldRouteIR(...)` test fixtures remain compatible;
- no `FieldRouter` route behavior changes;
- no downstream stage changes;
- F0/F1 tests still pass;
- new annotation tests pass;
- progress tracker F2 section is updated or a JSON progress export is provided.

## Required Evidence For Review

When submitting for review, provide:

1. changed files;
2. exact test commands and output summary;
3. example `FieldRouteIR` with both old lists and annotations;
4. confirmation that `FieldRouter` behavior was not changed;
5. confirmation that no Stage 3/4/7/downstream code was changed;
6. note on backward compatibility.

## PM Review Checklist

- [ ] Existing six route fields preserved.
- [ ] Existing tests constructing `FieldRouteIR(behavior=[...])` still pass.
- [ ] Annotation helpers support failure-mode condition candidates.
- [ ] Executable filtering helper exists but is not wired into Stage 7 yet.
- [ ] Annotation multi-label support does not break old overlap validation.
- [ ] No routing behavior changed in this phase.

