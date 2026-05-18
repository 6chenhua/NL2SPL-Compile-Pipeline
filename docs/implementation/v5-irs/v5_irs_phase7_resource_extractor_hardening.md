# Phase 7 - Resource Extractor Hardening

## Goal

Reduce Stage 6 schema-looking variable noise and prevent internal IR/schema fields from becoming business variables.

## Scope

Resource extraction filters and prompt hardening. Do not change public resource IR shape unless necessary.

## Target Files

Likely files:

- Stage 6 resource extractor module under `src/nl2spl/pipeline/stages/stage6_*`
- `prompts/stage6_system.txt`
- Stage 9.5 resource cleanup if currently responsible for pruning
- `tests/unit/test_resource_extractor_hardening.py`

## Reserved Names

At minimum reject or quarantine:

```text
span_id
source_span_id
source_span_ids
source_section_id
source_packet_id
main_flow_spans
exception_flows
block_id
flow_id
step_id
worker_id
target_ref
diagnostic_id
```

## Implementation Guidance

Add deterministic helpers:

```python
RESERVED_RESOURCE_NAMES: set[str] = {...}

def looks_like_ir_field(name: str) -> bool:
    ...

def is_allowed_resource_variable(name: str) -> bool:
    ...
```

Use these helpers in the resource extraction parse/normalization boundary, not only after rendering.

If a rejected variable came from LLM output, emit a validation warning or adapter/compile warning according to current project convention. Do not silently accept it.

## Prompt Hardening

Stage 6 prompt should explicitly say:

```text
Do not extract schema, IR, JSON, diagnostic, span, flow, block, step, source_section, or source_packet fields as domain variables.
Only extract variables that the user requirement itself needs as task inputs, outputs, or resources.
```

## Tests

Recommended command:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit/test_resource_extractor_hardening.py tests/unit/test_normalizer.py tests/integration/test_partial_spl_mvp.py -q --basetemp=.pytest_tmp_v5_phase7
```

Required tests:

- Reserved names are rejected.
- Case and separator variants are rejected, for example `sourceSectionId`, `source-section-id`.
- Legitimate user variables are preserved.
- Internal-comms style inputs do not produce schema variables.
- Required outputs still remain declared.
- Rejected variables do not create missing producer false positives.

## Acceptance Criteria

- Stage 6 no longer promotes IR/schema-looking fields to business variables.
- Warnings are visible when LLM output contains rejected variables.
- Existing valid variables and hard facts are preserved.
- No unrelated resource refactor is included.

## PM Review Checklist

- Is the filter deterministic?
- Are legitimate variables not over-filtered?
- Does the warning explain what was rejected?
- Does this phase avoid changing SPL rendering rules?

