# Phase 5 - Stage 9.5 Diagnostic Consolidation

## Goal

Teach Stage 9.5 to consume stage-local IRS diagnostics and construct satisfaction reports, deduplicate diagnostics, preserve final Gate/ProducerIndex authority, and prepare completeness inputs.

## Scope

Consolidation only. Do not move final renderability from Gate or producer status from ProducerIndex.

## Target Files

Likely files:

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/*`
- `src/nl2spl/pipeline/orchestrator.py`
- `src/nl2spl/compiler/diagnostic_analyzer.py`
- `tests/unit/test_diagnostic_consolidation.py`

## Responsibilities

Stage 9.5 should:

1. Read stage-local diagnostics from `intermediate_results`.
2. Read construct satisfaction reports from `intermediate_results`.
3. Merge with existing normalizer diagnostics.
4. Run or consume `ProducerIndex` required-output checks.
5. Preserve Gate-after diagnostics.
6. Deduplicate repeated diagnostics.
7. Keep validation errors, adapter warnings, and compile diagnostics separate.

## Dedup Key

Use a deterministic key:

```python
dedup_key = (
    diagnostic.kind,
    diagnostic.target_ref,
    tuple(sorted(normalize_span_ids(diagnostic.source_span_ids))),
    diagnostic.missing_slot.slot_name if diagnostic.missing_slot else None,
)
```

If a future `metadata` field is added to diagnostics, it can participate in the key, but do not require it in this phase.

## Missing Handler Priority

Gate-after `missing_handler` is authoritative.

Rules:

```text
If Stage 4 says handler exists but Gate filters the handler step, keep/add missing_handler.
Gate-after missing_handler overrides pre-gate clean state.
Duplicate missing_handler entries for the same target should be merged.
```

## Tests

Recommended command:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit/test_diagnostic_consolidation.py tests/unit/test_diagnostic_analyzer.py tests/unit/test_executable_gate.py -q --basetemp=.pytest_tmp_v5_phase5
```

Required tests:

- Stage-local `missing_handler` merges into final compile diagnostics.
- Duplicate diagnostics are deduplicated.
- Different targets are not deduplicated.
- Gate-after `missing_handler` is retained after assumed handler is filtered.
- `missing_output_producer` still comes from ProducerIndex authority.
- Validation errors remain separate from compile diagnostics.

## Acceptance Criteria

- Final diagnostics include stage-local IRS diagnostics.
- No duplicate `missing_handler` for the same exception flow.
- Gate and ProducerIndex remain final authorities.
- Completeness calculation remains based on final diagnostics with `blocks_completion=True`.

## PM Review Checklist

- Is consolidation deterministic?
- Is diagnostic ordering stable enough for reports/tests?
- Are stage-local reports preserved in `intermediate_results` for debugging?
- Did any validation warning get incorrectly converted into compile diagnostic?

