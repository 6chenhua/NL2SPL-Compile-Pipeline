# Phase 2 - IRSDrivenPromptBuilder

## Goal

Generate Stage 4 and Stage 7 prompt checklist text from `SPLConstructRegistry`, so prompt rules are no longer manually duplicated.

## Scope

This phase builds prompt infrastructure and snapshot tests. It should not yet change live Stage 4/7 behavior unless guarded behind a feature flag or explicit injection point.

## Target Files

Create:

- `src/nl2spl/compiler/irs_prompt_builder.py`
- `tests/unit/test_irs_prompt_builder.py`

Update if needed:

- `prompts/stage4_system.txt`
- `prompts/stage7_system.txt`
- Stage classes only to expose optional prompt assembly hooks

## Design

Implement:

```python
class IRSDrivenPromptBuilder:
    def __init__(self, registry: SPLConstructRegistry):
        self.registry = registry

    def render_for_stage(self, stage_name: str) -> str:
        ...

    def render_construct_checklist(self, irs: ConstructIRS) -> str:
        ...
```

Stage mapping:

```text
stage4 -> EXCEPTION_FLOW
stage7 -> GENERAL_COMMAND, REQUEST_INPUT, CALL_API, INVOKE_WORKER
stage9_5 -> REQUIRED_OUTPUT, CHILD_WORKER, WORKER_CANDIDATE
```

## Prompt Requirements

Rendered checklist must include:

- construct type
- existence policy
- source signals
- partial rendering rule
- slots
- missing diagnostic kind
- anti-fabrication notes

For Stage 4, checklist must state:

```text
No failure signal -> do not generate EXCEPTION_FLOW.
Concrete failure condition -> generate partial EXCEPTION_FLOW.
Condition + handler action -> complete EXCEPTION_FLOW.
Condition only -> missing_handler.
Vague "handle failures properly" -> type_or_contract_ambiguity, no concrete flow.
```

For Stage 7, checklist must state:

```text
GENERAL_COMMAND requires source evidence.
REQUEST_INPUT requires explicit ask/request/prompt/confirm source.
CALL_API requires named API/tool/connector plus executable call action.
INVOKE_WORKER requires accepted handoff.
If the action is only a suggested fix, emit assumption/report data, not executable StepIR.
```

## Feature Flag Guidance

If prompt injection is wired in this phase, use a conservative flag:

```text
PipelineConfig.enable_irs_prompt_builder: bool = False
```

Default must remain off until Phase 3/4 tests validate behavior.

## Tests

Recommended command:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit/test_irs_prompt_builder.py -q --basetemp=.pytest_tmp_v5_phase2
```

Snapshot tests should verify:

- Stage 4 checklist includes `EXCEPTION_FLOW` and `missing_handler`.
- Stage 7 checklist includes all command constructs.
- Checklist output is stable across calls.
- Unknown stage either returns empty text or raises a documented error.

## Acceptance Criteria

- Prompt builder uses registry data, not duplicated hardcoded prompt prose.
- Stage mappings are explicit and tested.
- Snapshot output is deterministic.
- Existing prompt files remain valid.
- Live pipeline behavior is unchanged unless an explicit flag is enabled.

## PM Review Checklist

- Can a construct rule change in Phase 1 automatically affect prompt text?
- Is generated prompt concise enough for LLM context?
- Is the feature flag default backward-compatible?
- Are Stage 4/7 prompts still readable after injection?

