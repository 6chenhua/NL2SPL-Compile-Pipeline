# Phase 3 - Stage 4 IRS Integration for Exception Flows

## Goal

Make Stage 4 produce construct-level satisfaction metadata and stage-local diagnostics for exception flows, without changing the existing Stage 4 return contract.

## Scope

Only Stage 4 exception-flow behavior is in scope. Do not refactor Stage 5-11.

## Target Files

Likely files:

- Stage 4 implementation module under `src/nl2spl/pipeline/stages/stage4_*`
- `src/nl2spl/pipeline/orchestrator.py`
- `tests/unit/test_stage4_irs_exception_flow.py`
- Existing Stage 4 prompt tests or fixtures

## Data Landing

Do not change existing Stage 4 return values. Store metadata through orchestrator side-channel:

```python
intermediate_results["construct_satisfaction"]["stage4"] = list[ConstructSatisfactionReport]
intermediate_results["stage_local_diagnostics"]["stage4"] = list[CompileDiagnostic]
```

If current orchestrator does not have a clean side-channel point, add a private helper:

```python
def _record_stage_local_constructs(
    self,
    stage_name: str,
    reports: list[ConstructSatisfactionReport],
    diagnostics: list[CompileDiagnostic],
) -> None:
    ...
```

## Behavior Rules

Implement for `EXCEPTION_FLOW`:

| Source condition | SPL / IR behavior | Diagnostic |
| --- | --- | --- |
| no failure signal | no exception flow | none |
| concrete failure condition, source-backed (spans non-empty) | partial exception flow skeleton, condition slot satisfied | none (handler_action = not_applicable at Stage 4) |
| condition text present but spans empty | exception flow marked assumed | `type_or_contract_ambiguity` |

Note: `handler_action` is a cross-stage slot — Stage 4 does NOT assess it and does NOT emit `missing_handler`. The `missing_handler` diagnostic remains authoritative in Stage 9.5 / post-gate, where Stage 7 handler steps already exist.

## Implementation Notes

Stage 4 may still be LLM-driven. The important part is that the Stage 4 result is checked against IRS after parsing:

1. Identify candidate exception flows from Stage 4 output.
2. For each exception flow, produce `ConstructSatisfactionReport`.
3. Check `condition` slot only: source-backed (spans non-empty) → satisfied; spans empty → assumed + `type_or_contract_ambiguity`.
4. Mark `handler_action` as `not_applicable` (cross-stage slot — Stage 9.5 authority).
5. Mark `trigger_step` as `not_applicable` (post-MVP).
6. Preserve existing v4 failure bridge behavior.

## Gate Interaction

This phase produces pre-gate diagnostics for `type_or_contract_ambiguity` (assumed conditions). It does NOT emit `missing_handler`. Gate-after `missing_handler` logic is preserved in Stage 9.5 — do not remove it.

## Tests

Recommended command:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit/test_stage4_irs_exception_flow.py tests/unit/test_failure_mode_bridge.py tests/integration/test_partial_spl_mvp.py -q --basetemp=.pytest_tmp_v5_phase3
```

Required tests:

- No failure source -> no exception flow, no diagnostics.
- Failure condition, source-backed (spans non-empty) -> exception flow skeleton, condition satisfied, partial, renderable.
- Failure condition, spans empty -> condition assumed, `type_or_contract_ambiguity`, not renderable.
- `handler_action` slot is `not_applicable` at Stage 4.
- No `missing_handler` is emitted at Stage 4.
- Stage 4 return contract unchanged.
- `ConstructSatisfactionReport` appears in `intermediate_results["construct_satisfaction"]["stage4"]`.
- `stage_local_diagnostics` appear in `intermediate_results["stage_local_diagnostics"]["stage4"]`.
- Worker-aware: unique `diagnostic_id` across workers.

## Acceptance Criteria

- Stage 4 can report slot satisfaction for `EXCEPTION_FLOW`.
- Stage-local diagnostics enter orchestrator side-channel.
- Existing v4 behavior remains compatible.
- No invented `REQUEST_INPUT` or handler command appears.

## PM Review Checklist

- Does Stage 4 distinguish condition from handler action?
- Are vague policies treated conservatively?
- Is side-channel metadata present but not part of the public result schema?
- Is gate-after handler checking still preserved?

