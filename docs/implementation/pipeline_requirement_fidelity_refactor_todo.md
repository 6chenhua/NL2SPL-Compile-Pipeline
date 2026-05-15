# NL2SPL Pipeline Requirement-Fidelity Refactor TODO

## Purpose

This document tracks changes needed to bring the current NL2SPL pipeline back in line with the teacher's core direction from the 2026-05-12 meeting:

- NL2SPL is a progressive compiler/transpiler from incomplete natural language requirements to an SPL high-level design draft.
- The compiler should materialize source-backed information as far as possible.
- Missing, unclear, conflicting, inferred, or assumed information must not be silently filled or discarded.
- The output should include partial SPL plus diagnostics, provenance, assumptions, and a readable report.
- MVP may simplify scope, but must not become hard-coded or block the future full design.

This document is about correcting existing pipeline behavior. The MVP feature design is tracked separately in `partial_spl_mvp_design.md`.

## Current Risk Summary

The current pipeline has a sound compiler-style shape: adapter -> spans -> routes -> worker/flow/block/resource/step/profile/constraint IR -> normalizer -> worker assembler -> renderer. That architecture should stay.

The main problem is not architecture. The problem is that several stages still optimize for producing complete renderable SPL even when the source requirement is incomplete. That causes semantic drift:

- missing required output producers are synthesized;
- behavior spans are forced into executable steps;
- some worker/API/handoff gaps are downgraded or repaired instead of surfaced;
- warnings are plain strings, not structured compiler diagnostics;
- provenance exists in fragments but is not a first-class result.

## Non-Negotiable Refactor Principles

1. Do not silently invent executable behavior.
2. Do not remove source-backed partial structure merely because it is incomplete.
3. Do not report missing structures the user never expressed.
4. Keep source-backed structures renderable where the SPL grammar permits partial form.
5. Put suggestions in diagnostics/report, not executable SPL.
6. Use existing `source_span_ids`, `source_section_id`, and `source_packet_id` as the first provenance layer.
7. Leave extension points for full `TraceRef`, `ElementStatus`, and richer diagnostics.

## Target Interface Direction

The refactor should introduce compatibility-friendly result structures. These can start minimal, but their names and fields should match the full design so later work extends them instead of replacing them.

```python
@dataclass
class CompileDiagnostic:
    diagnostic_id: str
    kind: str
    severity: str
    message: str
    target_ref: str | None
    source_span_ids: list[str]
    suggested_resolution: str | None = None
    blocks_rendering: bool = False
    blocks_completion: bool = True

@dataclass
class TraceRecord:
    target_ref: str
    source_span_ids: list[str]
    relation: str
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
    completeness: str
    diagnostics: list[CompileDiagnostic]
    traces: list[TraceRecord]
    assumptions: list[CompileAssumption]
    adapter_warnings: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]
    readable_report: str
```

For the refactor stage, `PipelineResult` may keep existing fields and add these fields rather than being replaced immediately.

## TODO 1: Stop Stage 9.5 From Inventing Required Output Producers

### Problem

`src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py` currently calls `_ensure_required_main_outputs()`. When a required output has no producer, it creates a synthetic `GENERAL_COMMAND` with `source_span_ids=[]`.

This directly conflicts with the meeting guidance: if the source says an output is required but does not say how to produce it, the compiler should report a missing producer instead of inventing a producer step.

### Required Change

- Replace automatic producer synthesis with structured diagnostic generation.
- Keep the required output in worker `OUTPUTS`.
- Do not add a synthetic command to `steps`.
- Create `missing_output_producer` diagnostic.
- Optionally create a `CompileAssumption` with suggested resolution, but do not render it into SPL.
- Add a producer index so required-output diagnostics are based on renderable source-backed or valid handoff-backed producers, not just variable declarations.

### Acceptance Criteria

- Required output without producer remains declared as output.
- SPL does not contain `COMMAND Produce required output ...` unless source explicitly said so.
- `CompileDiagnostic.kind == "missing_output_producer"` is emitted.
- Worker `OUTPUTS` declaration alone does not count as a producer.
- Existing validation errors do not obscure the compiler diagnostic.

## TODO 2: Make Stage 7 Stop Forcing Every Behavior Span Into Executable Steps

### Problem

`prompts/stage7_system.txt` says every behavior span must map to at least one step and `source_span_ids` must never be empty. This encourages the LLM to turn vague, policy-like, or partial failure descriptions into executable commands.

### Required Change

Update the Stage 7 prompt and parser contract:

- Every source-backed executable behavior should map to a step.
- Non-executable partial behavior should be reported as diagnostic material, not forced into `StepIR`.
- A failure condition span can be represented by `ExceptionFlow` without a handler `StepIR`.
- Do not create `REQUEST_INPUT` unless source explicitly says ask/request/prompt the user and receive input.

### Acceptance Criteria

- A source span such as `Missing timeframe` can produce an `ExceptionFlow` with no command.
- A source span such as `Handle failures properly` does not become a concrete exception command.
- Tests assert that unsupported behavior is surfaced through diagnostics/report.

## TODO 3: Keep Partial Exception Flows Instead of Repairing Them

### Current Good Basis

`WorkerAssembler` and `SPLRenderer` already tolerate exception flows with no blocks. This is aligned with partial SPL.

### Required Change

- Preserve exception conditions when source-backed.
- If no handler block or handler step exists, emit `missing_handler`.
- Do not remove the exception flow.
- Do not synthesize handler commands such as `Ask user for timeframe`.
- Run this check after the executable element gate. If a handler step exists but is assumed/synthetic and therefore not renderable, the flow still receives `missing_handler`.

### Acceptance Criteria

Input:

```text
Failure handling:
Missing timeframe.
```

Expected:

- SPL contains `[EXCEPTION_FLOW: Missing timeframe]` and `[END_EXCEPTION_FLOW]`.
- SPL does not contain invented `INPUT` or `COMMAND`.
- Report contains `missing_handler`.

## TODO 4: Add a Structured Diagnostic Collector to Stage 9.5

### Problem

Stage 9.5 currently returns `errors: list[str]` and `warnings: list[str]`. That is insufficient for compiler-style output because warnings need target references, source spans, and suggested resolutions.

### Required Change

Create a small diagnostic analyzer used by both legacy and worker-aware Stage 9.5 paths.

Initial diagnostic kinds:

- `missing_handler`
- `missing_output_producer`
- `type_or_contract_ambiguity`
- `assumed_command_not_renderable`

The analyzer should produce structured `CompileDiagnostic` records while preserving existing string warnings for backward compatibility.

Diagnostic result mapping:

| diagnostic | blocks rendering | result impact |
|---|---:|---|
| `missing_handler` | false | partial |
| `missing_output_producer` | false by default | partial |
| `type_or_contract_ambiguity` | depends on target | partial or blocked |
| `assumed_command_not_renderable` | true for that command | partial |

Keep validation concerns separate: `validation_errors` are syntax/reference/structure failures, while compile diagnostics are requirement incompleteness, ambiguity, assumptions, and anti-fabrication decisions.

### Acceptance Criteria

- Orchestrator can collect structured diagnostics from normalization.
- Existing callers still receive `validation_warnings`.
- Unit tests cover each diagnostic kind with minimal IR fixtures.

## TODO 5: Add Provenance Aggregation Without Requiring Full TraceRef Yet

### Problem

The full design proposes `trace_refs` on every major IR. That is correct long-term, but changing every stage at once is high-risk.

### Required Change

Add a first-pass provenance aggregator:

- Build `TraceRecord` from existing `source_span_ids`.
- Resolve `source_section_id` and `source_packet_id` through `SpanIR` where available.
- For variables, do not treat `VariableSpec.source` as provenance. It is only a resource category. Recover variable provenance from adapter hard facts, resource-extraction source spans, producer step source spans, worker contracts, or structural input/output sections.
- Use conservative relation defaults:
  - `direct` for copied source-backed conditions and constraints;
  - `normalized` for named variables/resources derived from source wording;
  - `inferred` for structural materialization such as failure condition -> exception flow;
  - `assumed` only for compiler-created suggestions, never silently renderable behavior.

### Acceptance Criteria

- Major worker, flow, step, constraint, and variable records have trace output when source spans exist.
- Variable trace records identify the real source evidence or report missing provenance; they do not rely only on `VariableSpec.source`.
- Missing source spans are reported as diagnostics or warnings.
- Future `TraceRef` can be added to IR without changing report/output schema.

## TODO 6: Add an Executable Element Gate Before Rendering

### Problem

Renderer currently renders whatever `StepIR` it receives, except for some unresolved worker invocation validation. This is too late and too narrow.

### Required Change

Before Stage 11 renders commands, filter or block executable elements that violate source-fidelity rules:

- `GENERAL_COMMAND`, `REQUEST_INPUT`, `CALL_API`, and `INVOKE_WORKER` must be source-backed or handoff-backed.
- `REQUEST_INPUT` must be explicitly requested by source, not just a useful suggestion.
- `CALL_API` must have explicit integration/API evidence.
- `INVOKE_WORKER` must have concrete accepted handoff evidence, including child worker target, input bindings, output bindings, and invocation location.
- Steps with `source_span_ids=[]` are not renderable unless explicitly marked as deterministic compiler scaffolding.

Do not use `source_span_ids == []` as the only gate condition. Add a lightweight renderability side table keyed by `step_id`:

```python
StepRenderInfo:
    step_id: str
    origin: str  # source_backed | compiler_synthetic | assumed | handoff_generated
    renderable: bool
    render_block_reason: str | None
```

Default rules:

- `source_backed` is renderable unless blocked by ambiguity.
- `handoff_generated` is renderable only with valid handoff target and IO bindings.
- `compiler_synthetic` executable behavior is not renderable by default.
- `assumed` is not renderable.

### Acceptance Criteria

- Assumed/synthetic behavior goes to assumptions/report.
- Unresolved worker/API behavior does not degrade to generic command.
- Renderer receives only renderable commands or emits clear diagnostics.

## TODO 7: Keep Adapter Warnings Separate From Compile Diagnostics

### Problem

Adapter warnings are currently stored in `intermediate["adapter_diagnostics"]` and merged into `validation_warnings`. This loses semantic distinction.

### Required Change

- Keep adapter warnings as adapter diagnostics.
- Convert relevant adapter issues into compile diagnostics only when they affect SPL materialization.
- Preserve source section IDs.
- Expose adapter warnings separately in `PipelineResult` / `CompileResult` or, at minimum, `intermediate_results["adapter_warnings"]`.
- The readable report summary should show adapter warnings, compile diagnostics, and validation warnings separately.

### Acceptance Criteria

- Duplicate/missing structural sections remain adapter warnings.
- Compile diagnostics remain about compilation/materialization problems.

## TODO 8: Update Tests Around Anti-Fabrication

Add or update tests for:

- no failure source -> no exception flow and no missing handler;
- failure condition only -> partial exception flow + `missing_handler`;
- failure condition + handler -> complete exception flow + handler command;
- required output without producer -> `missing_output_producer`, no synthetic producer;
- vague exception policy -> `type_or_contract_ambiguity`, no concrete exception flow;
- API retrieval without named API -> no `CALL_API`;
- complete single-level delegation policy -> child worker + `INVOKE_WORKER`;
- incomplete delegation policy -> candidate/report + `type_or_contract_ambiguity`, no executable child worker;
- assumed command -> report only, not rendered.

## Sequencing

1. Add result/diagnostic dataclasses.
2. Extend `PipelineResult` / orchestrator passthrough while keeping old fields.
3. Add `DiagnosticAnalyzer` with unit fixtures.
4. Replace `_ensure_required_main_outputs()` behavior with diagnostics.
5. Preserve partial exception flows and emit `missing_handler`.
6. Add executable element gate and renderability side table.
7. Add producer index and use it for required-output diagnostics.
8. Add `TraceRecord` provenance aggregation.
9. Add deterministic report renderer.
10. Update prompts to align with source-fidelity rules.
11. Extend tests and fixtures.

## Out of Scope For This Refactor

- Deep semantic duplicate detection.
- Full policy conflict detection.
- Multi-turn user clarification UI.
- Complete `trace_refs` on every IR type.
- Complex nested-flow repair.
- Nested child-worker extraction and multi-worker deep completeness analysis beyond preserving and validating single-level worker-aware behavior.
