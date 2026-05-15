# Partial SPL MVP Design

## Goal

Build a small but real NL2SPL MVP that demonstrates the teacher's core idea from the 2026-05-12 meeting:

```text
incomplete NL / structural NL
-> compiler-style pipeline
-> partial or complete SPL draft
-> diagnostics + provenance + assumptions
-> readable compile report
```

The MVP does not need a multi-turn UI, complex nested control repair, full multi-worker graph semantics, or complete semantic conflict detection. It must, however, prove that the compiler can avoid silent fabrication while still materializing source-backed partial SPL, including a simple source-backed child-worker delegation when the input provides enough contract evidence.

## Design Constraints

1. Preserve the current pipeline architecture.
2. Prefer adding stable result interfaces over rewriting every stage.
3. Keep MVP small, but use data structures compatible with the full design.
4. Do not hard-code scenario-specific output.
5. Do not require every future `TraceRef` field before producing useful provenance.
6. Diagnostics and report generation must be deterministic code, not another LLM pass.

## MVP Scenario Scope

Use inputs with:

- one main worker;
- at most one level of child workers from source-backed delegation policy;
- clear normal-flow behavior;
- simple failure conditions;
- required outputs;
- explicit child-worker responsibility, input, output, and handoff when delegation is expected to render;
- optional constraints;
- no deep nested IF/FOR/WHILE;
- no nested child workers;
- no complex worker graph or worker selection policy;
- no complex API contract inference.

The MVP should support child-worker extraction only when the source provides enough evidence. If delegation policy only hints at an optional subtask but lacks input/output/handoff evidence, the compiler should keep it as a candidate/report item and emit diagnostics instead of rendering an executable child worker or `INVOKE_WORKER`.

## MVP User-Visible Output

The user-facing result should contain:

```text
1. SPL draft
2. completeness: complete | partial | blocked
3. structured diagnostics
4. trace records
5. assumptions / suggestions
6. readable report
7. existing validation errors and warnings
```

## Data Structures

Create a new module, suggested path:

```text
src/nl2spl/compiler/compile_result.py
```

Initial types:

```python
from dataclasses import dataclass, field
from typing import Literal

DiagnosticKind = Literal[
    "missing_handler",
    "missing_output_producer",
    "type_or_contract_ambiguity",
    "assumed_command_not_renderable",
]

Severity = Literal["info", "warning", "error"]
Completeness = Literal["complete", "partial", "blocked"]
TraceRelation = Literal["direct", "normalized", "inferred", "assumed"]

@dataclass
class MissingSlot:
    slot_name: str
    required_for: str
    reason: str
    source_span_ids: list[str] = field(default_factory=list)
    suggested_question: str | None = None

@dataclass
class CompileDiagnostic:
    diagnostic_id: str
    kind: DiagnosticKind
    severity: Severity
    message: str
    target_ref: str | None
    source_span_ids: list[str] = field(default_factory=list)
    suggested_resolution: str | None = None
    missing_slot: MissingSlot | None = None
    blocks_rendering: bool = False
    blocks_completion: bool = True

@dataclass
class TraceRecord:
    target_ref: str
    source_span_ids: list[str]
    relation: TraceRelation
    explanation: str
    needs_confirmation: bool = False

@dataclass
class CompileAssumption:
    assumption_id: str
    target_ref: str
    source_span_ids: list[str]
    text: str
    reason: str
    suggested_resolution: str | None = None
    related_missing_slot: str | None = None
    related_diagnostic_id: str | None = None

@dataclass
class CompileResult:
    spl_text: str
    completeness: Completeness
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    traces: list[TraceRecord] = field(default_factory=list)
    assumptions: list[CompileAssumption] = field(default_factory=list)
    adapter_warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    readable_report: str = ""
```

These names intentionally match the full design. Future work can add `TraceRef` and `ElementStatus` without replacing the public result shape.

## Pipeline Integration

### Orchestrator

Extend `PipelineResult` with compile-result fields while preserving existing fields:

```python
@dataclass
class PipelineResult:
    spl_text: str
    validation_errors: list[str]
    validation_warnings: list[str]
    intermediate_results: dict[str, Any]
    final_spl_path: Path | None = None

    completeness: Completeness = "complete"
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    traces: list[TraceRecord] = field(default_factory=list)
    assumptions: list[CompileAssumption] = field(default_factory=list)
    adapter_warnings: list[str] = field(default_factory=list)
    readable_report: str = ""
```

Stage 9.5 should return a normalization/diagnostic result object rather than only tuple lists in the long term. For MVP, it can return extra diagnostics through `intermediate["stage9_5_diagnostics"]` if that is less invasive.

Keep the warning classes separate:

- `adapter_warnings`: input-shape/schema issues from adapters;
- `diagnostics`: requirement incompleteness, ambiguity, assumptions, and non-renderable behavior;
- `validation_errors` / `validation_warnings`: SPL syntax, reference, and structural validation.

`missing_output_producer` should normally be a compile diagnostic, not a validation error. It should only become blocking when the caller explicitly asks for final executable SPL rather than a partial design draft.

### Stage 9.5 Diagnostic Analyzer

Add a diagnostic analyzer after existing normalization but before Stage 10.

Responsibilities:

- detect partial exception flows;
- detect required outputs without source-backed producer;
- detect unresolved or ambiguous worker/API contracts;
- detect child-worker candidates that lack enough contract evidence to render;
- detect non-renderable assumed/synthetic commands;
- compute overall completeness.

Suggested path:

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/diagnostics.py
```

The analyzer should be pure and fixture-testable.

Stage 9.5 should run its checks in this internal order:

```text
1. Build producer index from current IR.
2. Gate executable steps and mark renderability.
3. Diagnose required outputs using renderable producer index.
4. Diagnose exception flows after non-renderable handler steps have been removed or marked.
5. Diagnose worker/API/handoff ambiguity.
6. Compute completeness from diagnostics and validation state.
```

This order matters: an exception flow may appear to have a handler before the executable gate, but if that handler is assumed or synthetic, it is still missing a source-backed handler.

### Executable Element Gate

Add a gate before rendering, either in Stage 9.5 or immediately before Stage 11:

```text
StepIR -> renderable steps + diagnostics + assumptions
```

Gate rules:

- Render source-backed commands.
- Render deterministic handoff commands only when backed by accepted `WorkerHandoffIR` with concrete child worker target, input bindings, output bindings, and invocation location.
- Do not render commands whose only basis is a compiler suggestion.
- Do not render synthetic required-output producers.
- Do not render `REQUEST_INPUT` unless source explicitly requested asking/requesting/prompting the user.

For MVP, a conservative rule is acceptable:

```text
source_span_ids == [] and command is executable -> not renderable
```

This is necessary but not sufficient. A step can have `source_span_ids` and still be non-renderable if the span is vague and the concrete command is invented. The MVP should add a lightweight renderability annotation without requiring full `TraceRef`:

```python
StepRenderInfo:
    step_id: str
    origin: Literal[
        "source_backed",
        "compiler_synthetic",
        "assumed",
        "handoff_generated",
    ]
    renderable: bool
    render_block_reason: str | None
```

If modifying `StepIR` is too invasive for the first implementation, store equivalent data in a side table keyed by `step_id`. Avoid relying on only `source_span_ids`.

Exceptions must be explicit and narrow, for example accepted worker handoff steps with valid `handoff_id`.

Renderability defaults:

| origin | default renderability |
|---|---|
| `source_backed` | renderable unless blocked by contract/type ambiguity |
| `handoff_generated` | renderable only when handoff target and IO bindings are valid |
| `compiler_synthetic` | not renderable if executable behavior |
| `assumed` | not renderable |

### Producer Index

`missing_output_producer` depends on a precise producer definition. Add a small producer index before diagnostics:

```python
@dataclass
class ProducerRef:
    variable_name: str
    producer_kind: Literal["step", "handoff", "api", "compiler_scaffold"]
    producer_ref: str
    source_span_ids: list[str]
    renderable: bool
```

A required output counts as produced only when at least one producer is renderable and source-backed or valid handoff-backed:

1. `StepIR.outputs` produces the variable and the step is renderable.
2. Child-worker `OutputBindingIR.parent_variable` produces the variable and the handoff is renderable.
3. `CALL_API` response produces the variable and the API call has explicit integration evidence.
4. Deterministic compiler scaffolding produces the variable only if that scaffold is explicitly allowed and non-fabricating.

Declaring a variable in worker `OUTPUTS` does not count as producing it.

### Report Renderer

Add deterministic report renderer:

```text
src/nl2spl/compiler/report_renderer.py
```

Input:

- `spl_text`
- `completeness`
- diagnostics
- traces
- assumptions
- validation errors/warnings
- span lookup map for quoted source text

Output:

- plain text report string

Do not use LLM for report generation.

## Diagnostic Rules

### missing_handler

Trigger when:

- an `ExceptionFlow` exists;
- condition is source-backed;
- after the executable gate, there are no renderable handler blocks or no renderable executable steps in the exception flow.

Output:

- `severity="warning"`
- `target_ref="exception_flow:{flow_id}"`
- `source_span_ids=exception_flow.spans`
- suggested resolution asks user to specify handler action.

SPL behavior:

- keep the exception flow;
- render it empty if grammar allows;
- do not invent handler command.

### missing_output_producer

Trigger when:

- variable is required final output;
- no renderable source-backed or valid handoff-backed producer produces it according to the producer index.

Output:

- `severity="warning"` or `"error"` depending on whether finalization is blocked;
- `target_ref="variable:{name}"`
- source spans from output declaration if known.

SPL behavior:

- keep variable in `OUTPUTS`;
- do not add synthetic producer step.

### type_or_contract_ambiguity

Trigger when:

- variable type conflicts across source-backed mentions;
- worker handoff lacks required IO;
- delegation policy names a subtask but does not specify enough responsibility/input/output/handoff evidence;
- API call lacks concrete API target;
- source says vague policy such as `handle failures properly` without concrete condition/action.

SPL behavior:

- render source-backed non-executable definitions when safe;
- do not render concrete behavior that depends on ambiguous contract.

### assumed_command_not_renderable

Trigger when:

- a command exists only because the compiler inferred a useful behavior;
- the source does not explicitly support it;
- the command would be executable SPL.

SPL behavior:

- remove from renderable steps;
- add a `CompileAssumption` with suggested resolution and `related_diagnostic_id`.

## Trace Rules

MVP trace generation should start from existing source-carrying fields:

- `SpanIR.span_id`
- `SpanIR.text`
- `SpanIR.source_section_id`
- `SpanIR.source_packet_id`
- `StepIR.source_span_ids`
- `ConstraintIR.source_span_ids`
- `ExceptionFlow.spans`
- `AlternativeFlow.spans`
- `WorkerSpecIR.owned_span_ids`
- `CandidateTaskUnitIR.source_span_ids`
- `ControlComplexityRegionIR.source_span_ids`
- `HandoffFailurePolicyIR.source_span_ids`
- adapter hard facts and compile hints with `source_section_id`

`VariableSpec.source` is not provenance. It is a resource category such as `input`, `output`, `step`, or `api`. For variables, MVP trace aggregation should recover source evidence from:

- adapter hard facts when available;
- source spans used by the resource extraction stage;
- producer `StepIR.source_span_ids` for step-produced variables;
- worker input/output contracts when the variable comes from delegation policy;
- structural input/output sections through `source_section_id`.

If none of these exists, the variable should receive a missing-source diagnostic or a conservative trace warning rather than pretending `VariableSpec.source` is enough.

Relation defaults:

| relation | MVP rule |
|---|---|
| `direct` | source text directly states the element |
| `normalized` | source text states it, compiler only normalizes name/type/format |
| `inferred` | source text implies a structure, but not new behavior |
| `assumed` | compiler proposes behavior not confirmed by source |

MVP should not require all IR objects to carry `trace_refs`; it should produce `TraceRecord` from the available provenance. Later full design can push `TraceRef` into each IR and keep `TraceRecord` as the report-facing aggregation.

## Completeness Rules

Compute final `completeness` as:

```text
blocked:
  validation_errors contain blocking syntax/reference errors
  or no renderable main worker task exists

partial:
  no blocking errors
  and at least one warning/error diagnostic describes missing required information

complete:
  no blocking errors
  and no missing/ambiguity/fabrication diagnostics
```

For MVP, `missing_handler` and `missing_output_producer` should usually make the result `partial`, not `blocked`, if SPL syntax remains valid.

Diagnostic status mapping:

| diagnostic | blocks_rendering | result impact |
|---|---:|---|
| `missing_handler` | false | partial |
| `missing_output_producer` | false by default | partial |
| `type_or_contract_ambiguity` | depends on target | partial or blocked |
| `assumed_command_not_renderable` | true for that command | partial |

`validation_errors` should only represent SPL syntax/reference/structure failures. `diagnostics` should represent requirement incompleteness, ambiguity, assumptions, and anti-fabrication decisions.

## Readable Report Shape

Example:

```text
NL2SPL Compile Report

Status: partial

Summary:
- SPL draft generated: yes
- Adapter warnings: 0
- Diagnostics: 2 warnings, 0 errors
- Validation warnings: 0
- Trace records: 8
- Assumptions not rendered: 1

Diagnostics:
[W001 missing_handler]
Target: exception_flow:exc_1
Source: s12 "Missing timeframe"
Message: Failure condition is present, but no handler action is specified.
Suggested resolution: Specify whether the agent should ask for a timeframe, block finalization, or continue with an explicit assumption.

[W002 missing_output_producer]
Target: variable:final_report
Source: s4 "Required output: final report"
Message: Required output is declared, but no source-backed step produces it.
Suggested resolution: Add a process step that produces final_report.

Trace:
- exception_flow:exc_1 <- inferred from s12 "Missing timeframe"
- variable:final_report <- normalized from s4 "Required output: final report"
- step:st_1 <- direct from s7 "Retrieve source material"

Assumptions / Suggestions:
- Related to exception_flow:exc_1:
  The compiler suggests asking the user for the missing timeframe, but this was not rendered because the source did not specify that behavior.
```

## Test Plan

### Unit Tests

Add tests for:

- `DiagnosticAnalyzer` detects missing handler.
- `DiagnosticAnalyzer` detects missing output producer.
- executable gate filters synthetic command with empty `source_span_ids`.
- trace aggregation produces records for exception flow, step, variable, and constraint.
- report renderer produces stable sections.

### Pipeline Tests

Add integration fixtures for:

1. Failure condition only:
   - SPL renders partial exception flow;
   - no invented handler;
   - report contains `missing_handler`.

2. Required output only:
   - output remains declared;
   - no invented producer command;
   - report contains `missing_output_producer`.

3. Complete failure handling:
   - condition and source-backed handler render normally;
   - no `missing_handler`.

4. No failure section:
   - no exception flow;
   - no missing-handler diagnostic.

5. Vague policy:
   - no concrete exception flow;
   - `type_or_contract_ambiguity` diagnostic.

6. Complete delegation policy:
   - source-backed child worker is created;
   - parent renders `INVOKE_WORKER`;
   - child worker inputs, outputs, and handoff are traceable to source spans or adapter hard facts.
   - keep this to one minimal happy-path fixture; do not expand it into a multi-worker graph test.

7. Incomplete delegation policy:
   - candidate is preserved in diagnostics/report;
   - no executable child worker or `INVOKE_WORKER` is rendered;
   - `type_or_contract_ambiguity` identifies missing responsibility/input/output/handoff evidence.

## Implementation Order

1. Add compile result dataclasses.
2. Extend `PipelineResult` / orchestrator passthrough while keeping old fields.
3. Add `DiagnosticAnalyzer` with unit fixtures.
4. Replace synthetic required-output producer behavior.
5. Preserve partial exception flows and emit `missing_handler`.
6. Add executable element gate and renderability side table.
7. Add producer index and use it for required-output diagnostics.
8. Add `TraceRecord` aggregation.
9. Add deterministic `ReportRenderer`.
10. Update Stage 7 prompt and related tests.
11. Add MVP integration scenarios.

## Extension Points For Full Design

The MVP must leave these extension points intact:

- `TraceRecord` remains report-facing; future `TraceRef` can be added per IR.
- `CompileDiagnostic.kind` can grow beyond four MVP kinds.
- `MissingSlot` can later move into `ElementStatus` on each IR.
- `CompileAssumption` can later support human confirmation workflows.
- `readable_report` can later be rendered in a UI without changing compiler output.
- `completeness` can later be computed per worker, per flow, and per element.
- Multi-worker diagnostics can later reuse the same diagnostic/trace/report contracts.
- Single-level child-worker support can later grow into nested workers, worker selection, and richer worker graph validation without changing `CompileResult`.

## Explicit Non-Goals

- Do not implement a multi-turn UI.
- Do not implement full semantic duplicate detection.
- Do not implement full policy conflict detection.
- Do not implement deep nested-flow repair.
- Do not implement nested child-worker extraction.
- Do not implement complex worker graph planning or runtime worker selection.
- Do not require all prompts to output `trace_refs` in the first MVP.
- Do not support every input schema equally before the first proof.

## Definition of Done

The MVP is done when a realistic but scoped NL/structural NL input can produce:

- syntactically valid partial SPL;
- no invented handler/producer commands;
- structured diagnostics for missing pieces;
- trace records back to source spans;
- source-backed single-level child-worker delegation when contract evidence is complete;
- diagnostics instead of executable child workers when delegation evidence is incomplete;
- assumptions separated from SPL text;
- a deterministic readable report;
- tests proving the anti-fabrication behavior.
