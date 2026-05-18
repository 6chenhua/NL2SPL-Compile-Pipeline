# Phase 6 - Evidence-Bound LLMConflictAnalyzer MVP

## Goal

Add an optional semantic conflict analyzer that uses an LLM for broad conflict review but only emits evidence-bound `CompileDiagnostic` records.

## Scope

This phase adds the analyzer interface, a guarded LLM implementation, a verifier, and report integration. It does not implement a rule-based conflict engine.

## Target Files

Create:

- `src/nl2spl/compiler/analyzers/__init__.py`
- `src/nl2spl/compiler/analyzers/semantic_conflict.py`
- `tests/unit/test_semantic_conflict_analyzer.py`

Update:

- `src/nl2spl/config.py` for feature flag
- `src/nl2spl/pipeline/orchestrator.py` or Stage 9.5 integration
- `src/nl2spl/compiler/compile_result.py` if `DiagnosticKind` needs `semantic_conflict`
- report renderers if they filter known kinds

## Interface

Implement:

```python
class SemanticConflictAnalyzer(Protocol):
    def analyze(
        self,
        constraints: list[ConstraintIR],
        steps: list[StepIR],
        flows: FlowStructureIR | WorkerFlowPlanIR,
        symbols: SymbolTable,
        context: ConflictAnalysisContext,
    ) -> list[CompileDiagnostic]: ...
```

Implement:

- `NoOpSemanticConflictAnalyzer`
- `LLMSemanticConflictAnalyzer`
- `LLMConflictDiagnosticVerifier`

## Feature Flag

Default must be off:

```text
PipelineConfig.enable_llm_conflict_analyzer = False
```

If enabled, analyzer may call LLM. If disabled, behavior must match v4.

## Evidence-Bound Rules

Every `semantic_conflict` diagnostic must satisfy:

1. Known diagnostic kind.
2. Known `target_ref`.
3. Known `source_span_ids` or known section/packet evidence.
4. No invented construct references.
5. No IR or SPL mutation.
6. Default `severity` is `warning` or `info`.
7. Default `blocks_completion=False`.

Uncited conflicts should be dropped or converted to non-compile analysis warnings. They should not enter `compile_diagnostics`.

## Prompt Requirements

The LLM prompt must say:

```text
Identify only clear or likely semantic conflicts.
Do not rewrite SPL.
Do not invent missing steps.
Do not create new workers, policies, variables, or commands.
Return diagnostics only.
Every diagnostic must cite existing spans or section/packet evidence.
```

## Tests

Recommended command:

```powershell
$env:PYTHONPATH = ".pytest_deps;src"
python -m pytest tests/unit/test_semantic_conflict_analyzer.py tests/unit/test_report_renderer.py tests/unit/test_feedback_report_renderer.py -q --basetemp=.pytest_tmp_v5_phase6
```

Required tests:

- NoOp analyzer returns empty list.
- LLM diagnostic with valid evidence is accepted.
- LLM diagnostic without evidence is rejected.
- LLM diagnostic with invalid target_ref format (missing colon) is rejected.
- Analyzer does not mutate IR inputs.
- Disabled flag preserves v4 behavior.
- ReportRenderer and FeedbackReportRenderer show `semantic_conflict`.

## Acceptance Criteria

- Conflict analysis is optional.
- All emitted conflict diagnostics are evidence-bound.
- No LLM output directly modifies IR or SPL.
- Reports display conflict diagnostics when present.

## PM Review Checklist

- Is the feature flag default off?
- Is the verifier strict enough?
- Are uncited LLM claims prevented from becoming compile diagnostics?
- Does the analyzer preserve current pipeline behavior when disabled?

