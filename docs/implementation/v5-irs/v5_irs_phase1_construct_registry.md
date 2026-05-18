# Phase 1 - SPLConstructRegistry and DiagnosticRegistry

## Goal

Introduce the v5 IRS data model without wiring it into Stage 4 or Stage 7 yet. This phase creates a stable, testable registry of SPL construct information requirements.

## Scope

New compiler modules only. No prompt changes and no pipeline behavior changes in this phase.

## Target Files

Create:

- `src/nl2spl/compiler/construct_registry.py`
- `src/nl2spl/compiler/diagnostic_registry.py`
- `tests/unit/test_construct_registry.py`
- `tests/unit/test_diagnostic_registry.py`

Update:

- `src/nl2spl/compiler/__init__.py`
- `src/nl2spl/compiler/compile_result.py` if `DiagnosticKind` Literal needs new values

## Required Types

Implement:

```python
@dataclass
class SlotSpec:
    slot_name: str
    syntax_required: bool = False
    required_for_partial: bool = False
    required_for_complete: bool = False
    renderable_without: bool = False
    evidence_kinds: list[str] = field(default_factory=list)
    missing_diagnostic: str | None = None
    can_be_inferred: bool = False
    can_be_suggested: bool = True
    notes: str | None = None

@dataclass
class ConstructIRS:
    construct_type: str
    existence_policy: Literal[
        "source_signal_required",
        "compiler_default_allowed",
        "grammar_required_if_parent_exists",
    ]
    source_signals: list[str]
    slots: list[SlotSpec]
    no_demand_behavior: Literal[
        "do_not_generate",
        "generate_default",
        "report_ambiguity",
    ] = "do_not_generate"
    partial_rendering_allowed: bool = False
    description: str | None = None

@dataclass
class SlotSatisfaction:
    slot_name: str
    status: Literal["satisfied", "missing", "inferred", "assumed", "not_applicable"]
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    relation: Literal["direct", "normalized", "inferred", "assumed"] | None = None
    diagnostic_kind: str | None = None
    explanation: str | None = None

@dataclass
class ConstructSatisfactionReport:
    construct_id: str
    construct_type: str
    slots: list[SlotSatisfaction]
    completeness: Literal["complete", "partial", "blocked"]
    renderable: bool
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
```

Implement `SPLConstructRegistry` with:

- `register(irs: ConstructIRS) -> None`
- `get(construct_type: str) -> ConstructIRS`
- `has(construct_type: str) -> bool`
- `list_constructs() -> list[str]`
- `default() -> SPLConstructRegistry`

## Initial Constructs

The default registry must include:

- `EXCEPTION_FLOW`
- `REQUIRED_OUTPUT`
- `GENERAL_COMMAND`
- `REQUEST_INPUT`
- `CALL_API`
- `INVOKE_WORKER`
- `CHILD_WORKER`
- `WORKER_CANDIDATE`

## Slot Rule Semantics

Implement helper logic or tests around this priority table:

| Case | Meaning | Expected result |
| --- | --- | --- |
| missing `syntax_required` | invalid materialized construct | blocked or validation-level failure |
| missing `required_for_partial` | insufficient for partial construct | do not materialize construct |
| missing `required_for_complete` and `renderable_without=True` | partial construct allowed | render partial and emit diagnostic |
| missing `required_for_complete` and `renderable_without=False` | not safe to render | block affected element and emit diagnostic |
| slot satisfied by source evidence | source-backed | may continue to Gate or ProducerIndex |
| slot satisfied by assumption only | assumed | report-only, not executable SPL |

## Diagnostic Registry

Create `DiagnosticSpec`:

```python
@dataclass
class DiagnosticSpec:
    kind: str
    default_severity: Literal["info", "warning", "error"]
    blocks_completion: bool
    description: str
    allowed_targets: list[str]
```

Default enabled kinds:

- `missing_handler`
- `missing_output_producer`
- `type_or_contract_ambiguity`
- `assumed_command_not_renderable`
- `unmapped_behavior_span`
- `missing_provenance`
- `semantic_conflict`

Reserved kinds:

- `redundant_requirement`
- `policy_step_conflict`
- `use_before_def`
- `worker_graph_inconsistency`

## Tests

Recommended command:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit/test_construct_registry.py tests/unit/test_diagnostic_registry.py -q --basetemp=.pytest_tmp_v5_phase1
```

## Acceptance Criteria

- Default registry contains all initial constructs.
- `EXCEPTION_FLOW` allows partial rendering when handler is missing.
- `REQUIRED_OUTPUT` does not require exact type for partial declaration.
- `CALL_API` distinguishes integration mention from executable call evidence.
- `WORKER_CANDIDATE` exists separately from `CHILD_WORKER`.
- Diagnostic registry rejects unknown kinds in tests.
- No pipeline behavior changes.

## PM Review Checklist

- Are construct rules explicit rather than hidden in tests?
- Are registry defaults deterministic?
- Are public result fields unchanged?
- Are `semantic_conflict` and reserved diagnostic kinds handled deliberately?

