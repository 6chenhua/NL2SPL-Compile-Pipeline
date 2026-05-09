# Internal Comms SPL Generation Review

Date: 2026-05-09

## Scope

This note records issues observed in the generated SPL and intermediate IR files under:

`examples/output/internal-comms`

The reviewed output is structurally valid enough to render as SPL, but it does not yet meet the expected semantic fidelity or executability bar.

## Summary

The generated SPL has the correct high-level sections:

- `[DEFINE_AGENT]`
- `[DEFINE_PERSONA]`
- `[DEFINE_AUDIENCE]`
- `[DEFINE_CONSTRAINTS]`
- `[DEFINE_VARIABLES]`
- `[DEFINE_WORKER]`
- `[INPUTS]`
- `[OUTPUTS]`
- `[MAIN_FLOW]`
- `[ALTERNATIVE_FLOW]`
- `[EXCEPTION_FLOW]`

However, several semantic and dataflow issues remain.

## Findings

### 1. Normal Conditional Work Was Classified As Exception Flow

Input span:

`s7`: `If sources are needed and available, retrieve them using approved source recipes.`

This is a normal conditional branch in the reusable process, not an exception path. Stage 4 classified it as:

```json
{
  "flow_id": "exc_1",
  "condition_text": "If sources are needed and available",
  "spans": ["s7"]
}
```

The final SPL therefore renders:

```spl
[EXCEPTION_FLOW: sources are needed and available]
```

This is semantically wrong. Source retrieval is a conditional main-path operation.

### 2. Main Flow Step Order Violates Source Order And Data Dependencies

Original source order:

- `s7`: retrieve sources if needed and available
- `s8`: maintain provenance for externally sourced facts
- `s9`: produce a draft when enough required information is available

Generated main flow ordering:

- `s9`: produce draft
- `s8`: maintain provenance

Additionally, `s8` consumes `retrieved_sources`, but `retrieved_sources` is produced in an exception flow. This means the main path can reference a value that is not guaranteed to exist.

### 3. Required Outputs Are Not All Produced On Normal Completion Paths

Required outputs include:

- `draft`
- `source_evidence_set`
- `assumptions_log`
- `completion_status`

Observed issues:

- `assumptions_log` is declared as required but no command produces it.
- `completion_status` is produced only in an exception flow, not on a normal successful completion path.

This violates the expected output reachability requirement.

### 4. Placeholder Worker Invocation Is Not Executable

The final SPL contains commands like:

```spl
COMMAND-4 [INVOKE Worker WITH <REF>required_information</REF> RESPONSE <REF>draft</REF> SET]
COMMAND-7 [INVOKE Worker WITH <REF>needed_sources</REF>, <REF>approved_recipes</REF> RESPONSE <REF>retrieved_sources</REF> SET]
```

`Worker` is a placeholder. No concrete child worker is defined or referenced. This makes the SPL less executable and less faithful to the delegation model.

Expected behavior should be one of:

- Render these as ordinary `[COMMAND ...]` steps unless a concrete child worker exists.
- Generate concrete child worker names from delegation candidates.
- Validate and reject unresolved `INVOKE_WORKER` steps before final rendering.

### 5. Some Step Variables Have No Clear Producer

The final SPL references:

- `needed_sources`
- `approved_recipes`
- `retrieved_sources`
- `required_information`

`required_information` and `retrieved_sources` have producers, but `needed_sources` and `approved_recipes` are used without clear producer steps.

`available_connectors` is declared as a required input but is not used in the source retrieval command, even though the original input says available connectors or source repositories are part of the run input.

## Likely Root Causes

### Stage 4: FlowAssembler

Stage 4 is too eager to classify conditional branches as exception flows. It needs a stronger distinction:

- Normal conditional branch: condition changes whether a normal process step runs.
- Alternative flow: user-requested alternate path or non-primary valid mode.
- Exception flow: failure, error, refusal, unavailable resource, invalid input, or blocked completion.

### Stage 5: BlockAssembler

Stage 5 does not preserve source/dataflow order strongly enough after Stage 4 classification. It allowed `s9` to render before `s8` even though `s8` precedes `s9` in the source process.

### Stage 7: StepExtractor

Stage 7 emits `INVOKE_WORKER` without a concrete `integration_ref`. The renderer then falls back to the placeholder `Worker`.

Stage 7 also does not ensure that required outputs are produced on normal completion paths.

### Stage 9.5: IRNormalizer

The normalizer currently checks basic references, but should add stronger consistency rules:

- Required output reachability.
- No unresolved `INVOKE_WORKER`.
- No variable consumed before a producer exists on the same path.
- No normal process span incorrectly placed under exception flow when its condition is not exceptional.

## Recommended Fixes

1. Strengthen Stage 4 prompt rules for flow classification.
2. Add deterministic post-processing for known structured input formats.
3. Strengthen Stage 9.5 normalizer with path-aware validations.
4. Render `INVOKE_WORKER` only when the worker target is concrete.
5. Add tests using `examples/output/internal-comms` expectations:
   - Source retrieval is not an exception flow.
   - Required outputs are all produced.
   - No unresolved `INVOKE Worker`.
   - `available_connectors` participates in source retrieval.
   - Main flow respects original process order.
