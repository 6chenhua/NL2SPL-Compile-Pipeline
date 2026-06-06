# Stage 2 Neutral Prior / Executable Annotation Conflict Fix Plan

Status: proposed  
Date: 2026-06-05  
Scope: Stage 2 route annotation merge, Stage 7 executable filtering, demo final SPL rendering

## 1. Problem Statement

`examples/output/demo/final_spl.txt` contains an empty main flow:

```text
[MAIN_FLOW]
[END_MAIN_FLOW]
```

This is not because Stage 4 or Stage 5 failed to create a main flow. The
intermediate files prove that the flow shell exists:

```text
examples/output/demo/stage4_flow_assembler.json
  worker_main.main_flow_spans = ["s13", "s22", "s14", "s15"]

examples/output/demo/stage5_block_assembler.json
  worker_main.main_flow_blocks[0].block_id = "b_1"
  worker_main.main_flow_blocks[0].spans = ["s13", "s22", "s14", "s15"]
```

The final SPL is empty because Stage 7 produces no renderable main-flow steps
for the main worker after executable filtering.

## 2. Evidence Chain

### 2.1 Stage 2 Produces Conflicting Annotations

From `examples/output/demo/stage2_field_router.json`, spans `s13`, `s14`, and
`s15` each have two annotations.

Example for `s13`:

```json
{
  "span_id": "s13",
  "field": "behavior",
  "semantic_role": null,
  "construct_target": null,
  "slot_target": null,
  "executable": false,
  "metadata": {
    "prior_resolution": "no_prior_neutral_context"
  }
}
```

and later:

```json
{
  "span_id": "s13",
  "field": "behavior",
  "semantic_role": "process_step",
  "construct_target": "RESOURCE_CONTRACT",
  "slot_target": "input",
  "executable": true
}
```

Observed set calculation from the demo checkpoint:

```text
exec_set      = ["s13", "s14", "s15"]
non_exec_set  = [..., "s13", "s14", "s15", ...]
intersection = ["s13", "s14", "s15"]
```

So the same source spans are both executable and non-executable.

### 2.2 Stage 7 Treats Those Spans As Droppable Non-Executable Material

In `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py`,
Stage 7 computes:

```python
behavior_span_ids = set(routes.get_executable_behavior_span_ids())
non_exec_span_ids = set(routes.get_non_executable_behavior_span_ids())
```

Then the D6 guard drops any step whose source spans are all in
`non_exec_span_ids`:

```python
if source_ids and source_ids.issubset(non_exec_span_ids):
    continue
```

Because `s13/s14/s15` are also in `non_exec_span_ids`, any LLM-produced steps
from these spans are dropped even though the same spans have executable LLM
annotations.

### 2.3 Renderer Is Not The Root Cause

The renderer only renders steps assigned to a block. In
`src/nl2spl/pipeline/stages/stage11_spl_renderer/block_renderer.py`,
`_steps_for_block()` selects steps by `block_ref` or source span overlap.

Given Stage 5 has block `b_1` with `s13/s22/s14/s15`, the renderer would render
matching steps if they survived Stage 7 and Stage 9.5. The missing main flow is
therefore upstream of rendering.

## 3. Root Cause

`_build_deterministic_priors()` creates a default neutral annotation for spans
without deterministic semantic resolution:

```python
RouteAnnotation(
    span_id=span.span_id,
    field=field,
    executable=False,
    source_section_id=span.source_section_id,
    source_packet_id=span.source_packet_id,
    metadata={"prior_resolution": "no_prior_neutral_context"},
)
```

This annotation is meant to be a pending structural context for LLM refinement.
It is not a real semantic decision.

However, `_merge_llm_refinement()` only replaces an existing prior when all of
these fields match:

```text
span_id
field
semantic_role
construct_target
slot_target
```

For neutral priors, `semantic_role`, `construct_target`, and `slot_target` are
`None`. For LLM refinements, these fields are populated. Therefore the merge
does not replace the neutral prior; it appends the LLM annotation as a new
multi-label annotation.

The design mistake is:

> A neutral pending prior is being represented as a final non-executable
> `RouteAnnotation`, then allowed to coexist with the accepted LLM semantic
> annotation.

## 4. Design Principle

Neutral deterministic information should be evidence, not semantic output.

Rule-based Stage 2 logic may determine:

- span id
- section id
- packet id
- section title
- list item / colon-pair structure
- hard structural facts such as runtime inputs and required outputs

It should not decide:

- `process_step`
- `failure_mode`
- `delegation_intent`
- handler/condition split
- whether a neutral behavior span is executable or non-executable

The LLM semantic mapper is the authority for these decisions, subject to
validator checks. No fallback should silently override or repair this.

## 5. Recommended Fix

### Phase A: Treat Neutral Priors As Replaceable Pending Context

Modify `_merge_llm_refinement()` so that an accepted LLM annotation replaces
same-span neutral pending priors.

Definition of a neutral pending prior:

```python
existing.span_id == span_id
existing.semantic_role is None
existing.construct_target is None
existing.slot_target is None
existing.metadata.get("prior_resolution") in {
    "no_prior_neutral_context",
    "weak_section_context",
}
```

When accepted LLM annotation exists for that span:

1. remove these neutral pending annotations from `merged`;
2. add the accepted LLM annotation with prior provenance preserved;
3. do not leave the old `executable=False` annotation behind.

This is the smallest correct fix because it preserves:

- deterministic provenance
- LLM authority for semantics
- existing multi-label support for genuinely distinct semantic labels

It removes only pending neutral placeholders.

### Phase B: Make Executable / Non-Executable Helpers Conflict-Safe

Update `FieldRouteIR.get_non_executable_behavior_span_ids()` so that a span
with an executable behavior annotation is not also returned as non-executable
only because a neutral pending annotation remains.

Recommended rule:

```text
non_exec_effective = non_exec_set - executable_set
```

This should be a defensive guard, not the primary fix. The primary fix remains
Stage 2 merge cleanup.

Important: if a span truly needs both executable and non-executable semantics,
that should be expressed through a split recommendation or separate source
spans. The system should not silently let contradictory annotations decide
different downstream behavior.

### Phase C: Add Validator Warning Or Error For Contradictory Same-Span Semantics

After merge, validate that no span has contradictory executable state unless
the combination is explicitly allowed.

Suggested rule:

```text
If a span has both executable=True and executable=False annotations:
  - ignore neutral pending annotations if they are still present;
  - otherwise emit route_refinement_conflict diagnostic or fail validation.
```

For MVP, prefer fail-fast for non-neutral contradictions. This aligns with the
current no-fallback direction.

### Phase D: Longer-Term Refactor

Separate the concepts currently mixed in `RouteAnnotation`:

1. `StructuralPrior` or `PriorEvidence`
   - section id
   - packet id
   - title
   - packet type
   - list/colon-pair metadata
   - suggested field if deterministic

2. `RouteAnnotation`
   - final semantic routing decision consumed by Stage 4/5/7

After this refactor:

```text
_build_deterministic_priors()
  -> StructuralPrior[]

LLM semantic mapper + validator
  -> RouteAnnotation[]

Stage 4/5/7
  -> consume RouteAnnotation[] only
```

This removes the possibility that an "unknown/pending" state is interpreted as
a real non-executable semantic decision.

## 6. Non-Recommended Fixes

### Do Not Fix In Renderer

Renderer only renders existing steps. Adding renderer fallback commands would
hide Stage 2/7 semantic routing defects.

### Do Not Disable D6 Guard

D6 guard is useful: failure conditions and unresolved delegation boundaries
must not become accidental commands. The bug is not that D6 exists; the bug is
that executable spans are also present in the non-executable set.

### Do Not Add Rule-Based "Process Step" Keyword Detection

Adding code rules such as "if text contains drafts/routes/provides then
executable" reintroduces the same hard-coded semantic problem. This decision
belongs to LLM semantic mapping plus validation.

### Do Not Add LLM Failure Fallback

If Stage 2 LLM refinement fails, expose the failure. Do not infer executable
steps from deterministic fallback rules.

## 7. Concrete Implementation Sketch

### 7.1 Stage 2 Merge Cleanup

In `_merge_llm_refinement()`, before replacing/appending an accepted LLM
annotation:

```python
def _is_pending_neutral_prior(existing: RouteAnnotation, span_id: str) -> bool:
    return (
        existing.span_id == span_id
        and existing.semantic_role is None
        and existing.construct_target is None
        and existing.slot_target is None
        and existing.metadata.get("prior_resolution") in {
            "no_prior_neutral_context",
            "weak_section_context",
        }
    )
```

Then:

```python
pending_prior = next(
    (a for a in merged if _is_pending_neutral_prior(a, span_id)),
    None,
)

if pending_prior is not None:
    merged = [
        a for a in merged
        if not _is_pending_neutral_prior(a, span_id)
    ]
    merged.append(RouteAnnotation(
        span_id=span_id,
        field=field,
        semantic_role=sem_role,
        route_family=llm_ann.route_family or pending_prior.route_family,
        construct_target=construct,
        slot_target=slot,
        executable=executable,
        source_section_id=pending_prior.source_section_id or llm_ann.source_section_id,
        source_packet_id=pending_prior.source_packet_id or llm_ann.source_packet_id,
        primary=llm_ann.primary,
    ))
    continue
```

### 7.2 FieldRouteIR Defensive Helper

In `get_non_executable_behavior_span_ids()`:

```python
exec_set = {
    a.span_id
    for a in self.annotations
    if a.executable and a.field == "behavior"
}
non_exec_set = {
    a.span_id
    for a in self.annotations
    if not a.executable and a.field == "behavior"
}
non_exec_set -= exec_set
```

This prevents accidental D6 drops if a neutral annotation leaks through.

### 7.3 Conflict Diagnostic

After merge, inspect annotations grouped by span:

```python
for span_id, anns in annotations_by_span.items():
    has_exec = any(a.executable for a in anns)
    has_non_exec = any(not a.executable for a in anns)
    has_non_neutral_conflict = any(
        not a.executable and a.semantic_role is not None
        for a in anns
    )
    if has_exec and has_non_exec and has_non_neutral_conflict:
        raise StageError(...)
```

## 8. Tests To Add

### 8.1 Stage 2 Merge Test

Input:

- deterministic prior for `s13`:
  - `field=behavior`
  - `executable=False`
  - `semantic_role=None`
  - `metadata.prior_resolution=no_prior_neutral_context`
- LLM accepted annotation:
  - `span_id=s13`
  - `field=behavior`
  - `semantic_role=process_step`
  - `executable=True`

Expected:

- merged annotations contain only one `s13` annotation;
- it is executable;
- it preserves `source_section_id` and `source_packet_id`;
- `s13` is not returned by `get_non_executable_behavior_span_ids()`.

### 8.2 Stage 7 D6 Regression Test

Build a `FieldRouteIR` with `s13` executable after merge and a main block
covering `s13`.

Expected:

- Stage 7 prompt receives `s13` in behavior spans;
- D6 guard does not drop the resulting step;
- worker step plan contains at least one main worker step.

### 8.3 Demo Regression Test

Run the demo pipeline or a focused fixture matching the demo route state.

Expected final SPL:

```text
[MAIN_FLOW]
    COMMAND-...
[END_MAIN_FLOW]
```

At minimum assert:

```text
final_spl contains [MAIN_FLOW]
text between [MAIN_FLOW] and [END_MAIN_FLOW] contains [COMMAND
```

### 8.4 Negative Test

A true failure condition span such as `s19` should remain non-executable:

```text
s19 semantic_role=failure_mode
s19 executable=false
```

Expected:

- Stage 4 creates `ExceptionFlow`;
- Stage 7 does not create command from `s19`;
- missing handler diagnostic remains if no handler is provided.

## 9. Acceptance Criteria

1. No span appears in both effective executable and effective non-executable
   behavior sets due to neutral pending priors.
2. Neutral pending priors are replaced by accepted LLM annotations for the
   same span.
3. Real non-executable semantics, such as failure conditions, remain
   non-executable.
4. Stage 7 D6 guard remains enabled.
5. Demo final SPL renders non-empty main flow commands when executable process
   spans exist.
6. No renderer fallback is added.
7. No rule-based semantic keyword table is added for process-step detection.
8. LLM failure remains fail-fast; no fallback is introduced.

## 10. Suggested Verification Commands

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\test_adapter_guided_fieldroute_refinement.py tests\unit\test_stage7_irs_step_extraction.py tests\unit\pipeline\stages\test_worker_plan_normalizer.py -q --basetemp=.pytest-tmp-stage2-neutral-prior
```

```powershell
.venv\Scripts\python.exe examples\usage.py
```

Then inspect:

```powershell
Get-Content examples\output\demo\final_spl.txt
```

and verify `[MAIN_FLOW]` is not empty.
