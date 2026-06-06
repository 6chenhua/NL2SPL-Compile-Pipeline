# Structured Multi-Output Aggregation: No-Unpack Revision

## Context

`examples/output/internal-comms-3/final_spl.txt` shows a bad normalization result:

```text
COMMAND-5 [COMMAND Finalize the revision package ... RESULT worker_main_st_7_result_structured: worker_main_st_7_result_structured_type SET]
COMMAND-6 [DISPLAY Deliver the polished draft and artifacts based on <REF>polished_draft</REF>, <REF>revision_history</REF>, <REF>assumptions_log</REF>, <REF>evidence_trail</REF>, and <REF>readiness_status</REF>]
COMMAND-7 [COMMAND Extract revision_history from worker_main_st_7_result_structured ... RESULT revision_history: text SET]
COMMAND-8 [COMMAND Extract assumptions_log from worker_main_st_7_result_structured ... RESULT <REF>assumptions_log</REF> SET]
COMMAND-9 [COMMAND Extract evidence_trail from worker_main_st_7_result_structured ... RESULT <REF>evidence_trail</REF> SET]
COMMAND-10 [COMMAND Extract readiness_status from worker_main_st_7_result_structured ... RESULT readiness_status: text SET]
```

The wrong behavior is not only the ordering of the unpack commands. The deeper problem is that unpacking changes the intended variable model.

## Revised Decision

For a step that semantically produces multiple output fields and the SPL grammar only allows one `RESULT` / `RESPONSE`, normalize the step into a single structured result variable and stop there.

Do not generate compiler unpack commands by default.

Expected shape:

```text
COMMAND-N [COMMAND Finalize the revision package ... RESULT worker_main_st_7_result_structured: worker_main_st_7_result_structured_type SET]
```

with:

```text
worker_main_st_7_result_structured_type = {
  revision_history: text,
  assumptions_log: text,
  evidence_trail: text,
  readiness_status: text
}
```

Downstream consumers that need the package should consume the structured result variable, not individual unpacked fields. In the internal-comms case, the delivery step should refer to the structured package plus other direct artifacts, instead of consuming `revision_history`, `assumptions_log`, `evidence_trail`, and `readiness_status` as separate late-produced variables.

## Source Interpretation Note

The source text `Finalize with revision history, assumptions log, evidence trail, readiness status` does not prove that `revision_history` or `readiness_status` are pre-existing inputs. It identifies the contents of the final package/output. Required output declarations also do not imply prior producers.

Therefore, self-referential input repair is not the primary fix. The primary fix is to preserve the structured aggregate as the produced artifact and avoid fabricating individual variables through unpack steps.

## Implementation Direction

1. Change `_normalize_multi_output_steps()` so it creates the structured type and structured result variable, updates `step.outputs` to `[result_name]`, and does not append `compiler_unpack` steps.
2. Store enough metadata on the normalized step to preserve the original fields:

```python
step.metadata["structured_aggregation"] = {
    "result_name": result_name,
    "original_outputs": original_outputs,
    "type_name": type_name,
}
```

3. Update downstream consumer rewrites so references to original multi-output fields can be redirected to the structured result when no independent producer exists.
4. Keep explicit unpack support only if a future feature needs field-level extraction. Such unpack should be opt-in and source/consumer justified, not generated as default compiler scaffolding.
5. Update diagnostics so required outputs satisfied by a structured aggregate are reported as fields of that aggregate, rather than requiring separate unpack producers.

## Duplicate Producer Semantics

Multiple steps producing or updating the same logical variable can be valid. The current warning `variable '<name>' produced by multiple steps` is too coarse when a step is performing an ordered update.

Near-term rule:

- If a repeated output is also an input of the same step, treat it as an update and do not emit a duplicate-producer warning.
- If a repeated output is not read by the later step, keep the warning because it may be an overwrite/conflict.

## Deferred Technical Debt

`SymbolTable` currently stores only one `producer_step` per variable. This is insufficient for ordered updates, repeated assignments, field-level structured outputs, and future dataflow checks.

Deferred follow-up:

- Replace or supplement `producer_step` with `producer_steps`.
- Consider variable versioning for ordered updates, for example `assumptions_log@st_4` then `assumptions_log@st_7`.
- Update reachability, provenance, and diagnostics to reason over producer history instead of a single overwritten producer pointer.

This is intentionally not part of the immediate fix.
