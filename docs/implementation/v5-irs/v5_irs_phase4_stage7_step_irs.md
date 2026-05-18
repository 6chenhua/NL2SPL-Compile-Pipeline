# Phase 4 - Stage 7 IRS Integration for Executable Steps

## Goal

Make Stage 7 IRS-aware for executable elements: `GENERAL_COMMAND`, `REQUEST_INPUT`, `CALL_API`, and `INVOKE_WORKER`.

## Scope

Stage 7 prompt/schema/checking only. Final renderability still belongs to `ExecutableElementGate`.

## Target Files

Likely files:

- Stage 7 implementation module under `src/nl2spl/pipeline/stages/stage7_*`
- `prompts/stage7_system.txt`
- `src/nl2spl/pipeline/orchestrator.py`
- `tests/unit/test_stage7_irs_step_extraction.py`

## Required Behavior

Stage 7 should avoid producing unsafe executable steps when the source does not satisfy IRS slots.

Rules:

```text
GENERAL_COMMAND:
  executable behavior must be source-backed.

REQUEST_INPUT:
  source must explicitly say ask/request/prompt/confirm user.
  missing information alone is not enough.

CALL_API:
  requires named API/tool/connector evidence plus executable call action.
  source repositories as context are not executable CALL_API.

INVOKE_WORKER:
  requires accepted handoff.
  incomplete delegation becomes diagnostic/report data, not executable invoke.
```

## Output Side-Channel

Write Stage 7 reports to:

```python
intermediate_results["construct_satisfaction"]["stage7"]
intermediate_results["stage_local_diagnostics"]["stage7"]
```

Do not change Stage 7's existing return value unless absolutely necessary.

## Relationship to Gate

Stage 7 IRS is a proactive guard. It is not the final authority.

Keep this boundary:

```text
IRS may suggest non-renderability.
ExecutableElementGate decides final renderability.
```

If Stage 7 emits an unsafe step anyway, Gate must still block it.

## Tests

Recommended command:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit/test_stage7_irs_step_extraction.py tests/unit/test_executable_gate.py tests/integration/test_partial_spl_mvp.py -q --basetemp=.pytest_tmp_v5_phase4
```

Required tests:

- Missing slot does not become `REQUEST_INPUT` unless source explicitly asks.
- Connector mention without call action does not become `CALL_API`.
- Incomplete delegation does not become executable `INVOKE_WORKER`.
- Source-backed normal command still becomes `GENERAL_COMMAND`.
- Stage 7 emits construct satisfaction metadata.
- Gate still blocks an unsafe step if one leaks through.

## Acceptance Criteria

- Stage 7 prompt includes IRS checklist.
- Stage 7 stage-local diagnostics are recorded.
- Existing v4 tests still pass.
- No new path bypasses `ExecutableElementGate`.

## PM Review Checklist

- Does Stage 7 keep assumptions out of executable SPL?
- Are source-backed handoffs still allowed?
- Are CALL_API and REQUEST_INPUT stricter than generic command extraction?
- Is there test coverage for leaked unsafe steps reaching Gate?

