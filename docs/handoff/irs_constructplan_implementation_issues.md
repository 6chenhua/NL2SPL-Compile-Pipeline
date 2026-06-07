# IRS / ConstructPlan Implementation Issues and Follow-up Tasks

**Document status**: Draft for implementation review  
**Scope**: `src/nl2spl/compiler/construct_plan` and `src/nl2spl/compiler/irs` integration  
**Basis**: Code inspection of current `main` branch and comparison with the IRS-driven compiler architecture  
**Primary goal**: Record current integration issues, architectural risks, and recommended repair tasks before expanding more IRS constructs.

---

## 1. Executive Summary

The current IRS / ConstructPlan implementation is directionally correct.

The implementation has already separated two important responsibilities:

```text
ConstructPlan = upstream construct-demand planning layer
IRS           = downstream slot satisfaction and diagnostic projection layer
```

This is consistent with the intended architecture:

```text
RouteAnnotation / source evidence
  -> ConstructPlan
  -> IRS checking
  -> Stage 9.5 global consolidation
  -> ExecutableElementGate / ProducerIndex final authority
  -> ReportRenderer
```

However, the current code still has two integration-level blockers that should be fixed before adding new IRS constructs:

1. `PipelineConfig` has moved to `irs: IRSRuntimeConfig`, but Stage 4 still reads the old `config.enable_irs_prompt_builder` flag.
2. The orchestrator may pass a 4-tuple containing `construct_plan` into Stage 4, but Stage 4 currently only supports 2-tuple or 3-tuple inputs.

There are also several architectural risks:

1. `ConstructPlan` is currently too EXCEPTION_FLOW-specific.
2. Stage 4 still has multiple exception materialization paths.
3. Stage-local IRS and post-normalize IRS authority need to remain explicitly separated.
4. The LLM semantic conflict analyzer is currently a no-op by default and should not be treated as a completed conflict detection capability.

The recommended next step is **not** to add more IRS constructs immediately. The next step should be to stabilize integration and then expand ConstructPlan through extractor-style modules.

---

## 2. Current Architecture Assessment

### 2.1 What is correct

The current direction is correct because the implementation separates the following concerns:

| Layer | Current role | Assessment |
|---|---|---|
| RouteAnnotation | Carries source-level route/evidence annotations | Correct as upstream evidence source |
| ConstructPlan | Converts route evidence into construct demand and slot demand | Correct as planning layer |
| IRS | Checks construct slot satisfaction and projects diagnostics | Correct as construct-level checker |
| Stage 9.5 | Consolidates global diagnostics and consistency results | Correct as global analysis pass |
| ExecutableElementGate | Final authority for renderability of executable elements | Correct authority boundary |
| ProducerIndex | Final authority for required output producer status | Correct authority boundary |
| ReportRenderer | Presents final diagnostics, assumptions, provenance, SPL | Correct output layer |

### 2.2 Important design boundary

ConstructPlan should answer:

```text
Does the source require this construct?
Which slots have source evidence?
Which spans should be reserved from normal step extraction?
Which worker owns the construct evidence?
```

IRS should answer:

```text
Are required slots satisfied?
Is the construct complete, partial, or blocked?
Which diagnostic should be emitted for missing or invalid slots?
```

Gate and ProducerIndex should answer:

```text
Can this executable element enter SPL?
Does this required output have a legal producer?
```

These boundaries should be preserved. IRS may suggest non-renderability, but it should not replace the final renderability decision made by `ExecutableElementGate`.

---

## 3. Blocking Issue A: Stage 4 Still Uses Old IRS Config Flag

### 3.1 Problem

`PipelineConfig` has been updated to use nested IRS runtime configuration:

```python
irs: IRSRuntimeConfig
```

However, Stage 4 still accesses the old field:

```python
if self.config.enable_irs_prompt_builder:
    system_prompt += "\n\n" + irs_checklist_for_stage("stage4")
```

If `enable_irs_prompt_builder` no longer exists on `PipelineConfig`, Stage 4 may fail with:

```text
AttributeError: 'PipelineConfig' object has no attribute 'enable_irs_prompt_builder'
```

### 3.2 Impact

This is a runtime integration blocker.

It can prevent Stage 4 from running when the code path reaches IRS prompt checklist injection.

### 3.3 Recommended fix

Replace the old flag access with the current nested config.

Minimal fix:

```python
if self.config.irs.enabled and self.config.irs.stage_local_enabled:
    system_prompt += "\n\n" + irs_checklist_for_stage("stage4")
```

Cleaner fix:

```python
@dataclass
class IRSRuntimeConfig:
    enabled: bool = True
    stage_local_enabled: bool = True
    prompt_checklist_enabled: bool = True
```

Then Stage 4 can use:

```python
if (
    self.config.irs.enabled
    and self.config.irs.stage_local_enabled
    and self.config.irs.prompt_checklist_enabled
):
    system_prompt += "\n\n" + irs_checklist_for_stage("stage4")
```

### 3.4 Acceptance criteria

- No reference to `config.enable_irs_prompt_builder` remains.
- Stage 4 can run with IRS enabled.
- Stage 4 can run with IRS disabled.
- Existing v4 compatibility tests still pass.
- IRS prompt checklist behavior is covered by a small config-level unit test.

---

## 4. Blocking Issue B: Stage 4 Does Not Support ConstructPlan 4-Tuple Input

### 4.1 Problem

The orchestrator may call Stage 4 with four values:

```python
self._run_stage4(resolved_spans, resolved_routes, worker_plan, active_construct_plan)
```

This means Stage 4 receives:

```python
(spans, routes, worker_plan, construct_plan)
```

However, Stage 4 executor currently appears to support only:

```text
(spans, routes)
(spans, routes, worker_plan)
```

If the executor receives a 4-tuple but attempts to unpack it as a 2-tuple, it can fail with a tuple unpacking error.

### 4.2 Impact

This is also a runtime integration blocker.

It can break the worker-aware path when ConstructPlan is enabled.

### 4.3 Recommended fix

Update Stage 4 executor input handling to explicitly support 4-tuple input.

Recommended structure:

```python
def execute(self, input_data):
    if len(input_data) == 4:
        spans, routes, worker_plan, construct_plan = input_data
        return self._execute_worker_aware(
            spans=spans,
            routes=routes,
            worker_plan=worker_plan,
            construct_plan=construct_plan,
        )

    if len(input_data) == 3:
        spans, routes, worker_plan = input_data
        return self._execute_worker_aware(
            spans=spans,
            routes=routes,
            worker_plan=worker_plan,
            construct_plan=None,
        )

    if len(input_data) == 2:
        spans, routes = input_data
        return self._execute_legacy(
            spans=spans,
            routes=routes,
            construct_plan=None,
        )

    raise ValueError(f"Unsupported Stage 4 input arity: {len(input_data)}")
```

The helper methods should also accept `construct_plan` even if some paths do not use it yet.

### 4.4 Acceptance criteria

- Stage 4 accepts 2-tuple legacy input.
- Stage 4 accepts 3-tuple worker-aware input.
- Stage 4 accepts 4-tuple worker-aware + ConstructPlan input.
- No tuple unpacking failure occurs when `active_construct_plan` is present.
- A unit test covers all three arities.

---

## 5. Architectural Risk 1: ConstructPlan Is Still Too EXCEPTION_FLOW-Specific

### 5.1 Observation

The data model is generic enough to represent construct demand and slot demand. However, the current planner implementation is primarily focused on `EXCEPTION_FLOW`.

This is acceptable as the first implementation practice, but it should not become the long-term structure.

### 5.2 Risk

If more construct types are added directly into the same planner logic, `ConstructPlanner` may become a large if/else dispatcher with mixed rules for unrelated constructs.

That would recreate the same problem IRS was supposed to solve: construct rules become scattered and difficult to test.

### 5.3 Recommended fix

Refactor ConstructPlan into an extractor registry.

Recommended structure:

```text
src/nl2spl/compiler/construct_plan/
  model.py
  planner.py
  extractors/
    __init__.py
    exception_flow.py
    required_output.py
    request_input.py
    call_api.py
    worker_handoff.py
```

`ConstructPlanner.plan()` should only orchestrate extractors:

```python
class ConstructPlanner:
    def __init__(self, extractors: list[ConstructDemandExtractor]):
        self.extractors = extractors

    def plan(self, context: ConstructPlanningContext) -> ConstructPlan:
        demands = []
        diagnostics = []
        for extractor in self.extractors:
            result = extractor.extract(context)
            demands.extend(result.demands)
            diagnostics.extend(result.diagnostics)
        return merge_construct_demands(demands, diagnostics)
```

### 5.4 Acceptance criteria

- EXCEPTION_FLOW extraction is moved into `extractors/exception_flow.py`.
- `ConstructPlanner` no longer contains construct-specific slot logic.
- New construct support can be added by registering another extractor.
- Existing EXCEPTION_FLOW behavior remains unchanged.

---

## 6. Architectural Risk 2: Stage 4 Has Multiple Exception Materialization Paths

### 6.1 Observation

Stage 4 currently has several possible sources for exception flow creation or filtering:

```text
RouteAnnotation-based evidence
LLM flow output
ConstructPlan
ownership-driven materialization
```

Stage 5 and Stage 7 already consume ConstructPlan, but Stage 4 integration appears less stable.

### 6.2 Risk

If RouteAnnotation, ConstructPlan, and LLM output all independently materialize exception flows, duplicate or inconsistent exception flows can appear.

Possible symptoms:

- Same failure condition appears twice.
- Condition-only failure is incorrectly treated as handler action.
- Handler span is consumed both as exception handler and as normal main-flow step.
- Worker ownership becomes inconsistent.

### 6.3 Recommended fix

Make ConstructPlan the single source of construct demand after Stage 3.25.

Recommended rule:

```text
RouteAnnotation is input to ConstructPlan.
ConstructPlan is input to Stage 4 / Stage 5 / Stage 7.
Stage 4 / Stage 5 / Stage 7 should not independently reinterpret RouteAnnotation for the same construct type.
```

For EXCEPTION_FLOW:

```text
RouteAnnotation -> ConstructPlan -> Stage 4/5 materialization
```

not:

```text
RouteAnnotation -> Stage 4
RouteAnnotation -> ConstructPlan -> Stage 5
LLM output -> Stage 4
```

### 6.4 Acceptance criteria

- Stage 4 prefers ConstructPlan when present.
- RouteAnnotation fallback is only used when ConstructPlan is absent.
- Duplicate exception flow generation is covered by regression tests.
- Condition-only failure does not create executable handler blocks.

---

## 7. Architectural Risk 3: Stage-local IRS Must Not Compete with Post-normalize IRS

### 7.1 Observation

The current IRS runtime policy appears to distinguish stage-local IRS from post-normalize IRS.

This is correct.

Stage-local IRS is useful for early feedback and explainability, but final diagnostics should usually come from post-normalize IRS, Gate, ProducerIndex, and Stage 9.5 consolidation.

### 7.2 Risk

If stage-local diagnostics are treated as final compile diagnostics too early, the system may produce stale diagnostics.

Example:

```text
Stage 4 thinks exception handler is missing.
Stage 7 later extracts a source-backed handler step.
Gate accepts the handler.
But stale Stage 4 missing_handler remains in final report.
```

The reverse can also happen:

```text
Stage 4 thinks handler exists.
Gate later filters the handler as non-renderable.
Final report must still show missing_handler.
```

### 7.3 Recommended rule

```text
Stage-local IRS may produce provisional findings.
Post-normalize IRS + Gate + ProducerIndex provide final compile diagnostics.
DiagnosticConsolidator decides what enters final compile_diagnostics.
```

For `missing_handler`, gate-after recalculation must have higher authority than stage-local IRS.

### 7.4 Acceptance criteria

- Stage-local IRS findings are visible in intermediate results or debug/report sections.
- Final compile diagnostics do not contain stale stage-local diagnostics.
- Gate-after `missing_handler` overrides pre-gate optimistic checks.
- Diagnostic deduplication preserves only the final authoritative diagnostic per target.

---

## 8. Architectural Risk 4: Semantic Conflict Analyzer Is Not Yet a Completed Capability

### 8.1 Observation

The semantic conflict analyzer infrastructure exists, but the production path currently defaults to no-op unless an LLM call function is injected.

This is acceptable for MVP.

### 8.2 Risk

Documentation or reports may overstate semantic conflict detection capability.

The current system should be described as:

```text
Semantic conflict analyzer interface exists.
LLM implementation path is prepared.
Default production behavior is no-op unless configured.
```

not:

```text
Semantic conflict detection is fully implemented.
```

### 8.3 Recommended fix

Keep the no-op default, but make capability status explicit in implementation docs and runtime config.

Suggested config wording:

```python
semantic_conflict_enabled: bool = False
semantic_conflict_mode: Literal["noop", "llm"] = "noop"
```

### 8.4 Acceptance criteria

- Report does not claim conflict analysis was performed when analyzer is no-op.
- LLM conflict analyzer requires explicit configuration.
- LLM conflict diagnostics are evidence-bound and verified before entering compile diagnostics.

---

## 9. Recommended Repair Order

### Phase 1: Fix runtime blockers

1. Replace old `enable_irs_prompt_builder` config access.
2. Add Stage 4 support for 4-tuple input.
3. Add regression tests for both issues.

### Phase 2: Stabilize ConstructPlan authority

1. Make ConstructPlan the preferred source of EXCEPTION_FLOW demand.
2. Ensure RouteAnnotation fallback is only used when ConstructPlan is absent.
3. Add duplicate exception flow regression tests.

### Phase 3: Refactor ConstructPlan into extractor registry

1. Move EXCEPTION_FLOW logic into `extractors/exception_flow.py`.
2. Introduce `ConstructDemandExtractor` protocol.
3. Keep current behavior unchanged.

### Phase 4: Only then add more constructs

Recommended next constructs:

```text
REQUIRED_OUTPUT
REQUEST_INPUT
CALL_API
INVOKE_WORKER / WORKER_HANDOFF
```

Do not add these before Phase 1 and Phase 2 are complete.

---

## 10. Concrete Task List

### Task 1: Replace old IRS config flag

**Priority**: P0  
**Type**: Bug fix  
**Target files**:

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py
src/nl2spl/config.py
```

**Work**:

- Remove `config.enable_irs_prompt_builder` access.
- Use `config.irs.enabled`, `config.irs.stage_local_enabled`, and optionally `config.irs.prompt_checklist_enabled`.

**Done when**:

- Stage 4 runs with IRS enabled and disabled.
- No old config field references remain.

---

### Task 2: Support ConstructPlan in Stage 4 input contract

**Priority**: P0  
**Type**: Bug fix  
**Target file**:

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py
```

**Work**:

- Add 4-tuple input handling.
- Pass `construct_plan` into worker-aware Stage 4 path.
- Preserve 2-tuple and 3-tuple compatibility.

**Done when**:

- 2-tuple, 3-tuple, and 4-tuple Stage 4 inputs are all tested.

---

### Task 3: Define ConstructPlan authority rule

**Priority**: P1  
**Type**: Architecture cleanup  
**Target files**:

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py
src/nl2spl/pipeline/stages/stage5_block_assembler/*
src/nl2spl/pipeline/stages/stage7_step_extractor/*
```

**Work**:

- Establish rule: ConstructPlan preferred, RouteAnnotation fallback only.
- Remove or guard duplicate exception materialization paths.

**Done when**:

- Same failure condition cannot produce duplicate exception flows.
- Handler spans are not consumed as normal behavior steps unless dual-role evidence exists.

---

### Task 4: Refactor ConstructPlan into extractor registry

**Priority**: P1  
**Type**: Refactor  
**Target files**:

```text
src/nl2spl/compiler/construct_plan/planner.py
src/nl2spl/compiler/construct_plan/extractors/*
```

**Work**:

- Introduce `ConstructDemandExtractor` protocol.
- Move EXCEPTION_FLOW extraction into its own extractor.
- Keep public `ConstructPlanner.plan()` behavior stable.

**Done when**:

- Existing tests pass.
- Adding a new construct does not require editing EXCEPTION_FLOW logic.

---

### Task 5: Clarify stage-local IRS reporting semantics

**Priority**: P2  
**Type**: Reporting semantics  
**Target files**:

```text
src/nl2spl/compiler/irs/*
src/nl2spl/compiler/diagnostic_consolidator.py
src/nl2spl/compiler/reporting/*
```

**Work**:

- Clearly mark stage-local IRS diagnostics as provisional unless configured otherwise.
- Ensure final compile diagnostics come from consolidated authority.

**Done when**:

- Report distinguishes provisional IRS findings from final diagnostics.
- Stale stage-local diagnostics do not affect final completeness.

---

## 11. Regression Tests to Add

### Config compatibility tests

```text
IRS enabled + Stage 4 prompt checklist enabled -> no AttributeError
IRS disabled -> no checklist injection, no error
```

### Stage 4 input arity tests

```text
Stage 4 accepts (spans, routes)
Stage 4 accepts (spans, routes, worker_plan)
Stage 4 accepts (spans, routes, worker_plan, construct_plan)
Unsupported arity raises clear ValueError
```

### Exception materialization tests

```text
Failure condition only -> partial exception flow + missing_handler
Failure condition + source-backed handler -> complete exception flow
Failure condition duplicated in RouteAnnotation and ConstructPlan -> one exception flow
Handler span reserved by ConstructPlan -> not extracted as normal main-flow step
Dual-role handler span -> may be used in both places only when explicitly marked dual-role
```

### Diagnostic authority tests

```text
Stage-local missing_handler suppressed when post-normalize handler exists
Gate-after missing_handler emitted when handler step is filtered
Duplicate missing_handler appears once in final report
```

---

## 12. Final Recommendation

Do not expand IRS to more construct types until the two P0 blockers are fixed.

Recommended immediate branch goal:

```text
Stabilize IRS / ConstructPlan integration for EXCEPTION_FLOW end-to-end.
```

Only after that should the project add ConstructPlan extractors for:

```text
REQUIRED_OUTPUT
REQUEST_INPUT
CALL_API
INVOKE_WORKER / WORKER_HANDOFF
```

This keeps the architecture aligned with the intended IRS-driven compiler model while avoiding premature expansion on top of unstable integration points.
