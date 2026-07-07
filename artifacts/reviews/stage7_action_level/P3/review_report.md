# Stage 7 Action-Level Extraction Review Report - P3 (v2)

## Verdict
pass

## Scope
- Phase: P3 (api_call_materializer Short-Term Residual Fix) — **REVISED v2**
- Blockers addressed since v1:
  1. **P0 blocker (upstream coverage)**: `planner.py` now expands `OperationCoverageIR` to cover full
     conditional trigger sentence when the uncovered prefix matches a known conditional keyword.
     Proven with `test_conditional_trigger_coverage_expansion_upstream` (unit test calls
     `ConstructPlanner().plan(...)` with the real s16 span and raw operation evidence, asserts
     `char_start=0, char_end=81, operation_surface=<full first sentence>`).
  2. **P1/P0 risk (fallback deletion authority)**: Removed the `st_fallback_*` step_id → metadata
     auto-promotion block from `materialize_direct_api_calls`. Fallback deletion now requires
     explicit `metadata["fallback_for_api_call_demand_id"]` set by the caller (test fixture,
     future Stage 7 registry in P6). Stage-owned metadata is the sole authority.
  3. **metadata forwarding gap**: `worker_scoped.py` and `extractor.py` StepIR parsing now forward
     `metadata=step_data.get("metadata", {})` so stage-owned metadata from fixtures propagates
     correctly.
- Files changed:
  - `src/nl2spl/compiler/construct_plan/planner.py` [MODIFY]
  - `src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py` [MODIFY]
  - `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py` [MODIFY]
  - `src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py` [MODIFY]
  - `src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py` [MODIFY — no change this round]
  - `tests/unit/compiler/construct_plan/test_api_demands.py` [MODIFY]
  - `tests/unit/pipeline/stage7/test_api_call_materializer.py` [MODIFY]
  - `tests/unit/pipeline/stage7/test_api_call_materializer_residual_fix.py` [MODIFY]
  - `tests/unit/pipeline/stage7/test_api_call_residual_action_characterization.py` [MODIFY]
  - `tests/unit/pipeline/stage7/test_action_projection_negative.py` [MODIFY]
  - `tests/integration/pipeline/test_stage7_action_level_internal_comms_characterization.py` [MODIFY]
  - `tests/integration/pipeline/test_worker_action_plan_intermediate.py` [MODIFY]

## Evidence
- Test commands:
  `.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7 tests/integration/pipeline tests/unit/compiler/construct_plan tests/integration/test_multi_worker_pipeline.py -q`
- Test results:
  `63 passed, 10 skipped` (all 10 skips are pre-existing, no failures)
- Ruff / diff-check:
  All checks passed. Only expected CRLF warnings (no error-level issues).
- E2E proof:
  `test_conditional_trigger_coverage_expansion_upstream` — PASSED. ConstructPlanner given raw
  partial operation evidence `"retrieve them using approved source recipes"` for span s16
  returns `char_start=0, char_end=81, operation_surface="If sources are needed and available,
  retrieve them using approved source recipes."`.

## Authority Boundary Check
- **Upstream coverage expansion**: Done at `planner.py._operation_coverage()`. Algorithm:
  - After `_locate_operation_surface` returns `(start, end)`, scan containing sentence.
  - If leading text before `start` matches `^(if|when|unless|in case|...)`, expand start to
    sentence start and update `operation_surface` to the full sentence.
  - Keyword check is on the **uncovered prefix** only — not used for action segmentation.
    This is deterministic projection from span geometry, not keyword-driven parsing.
- **Fallback deletion authority**: Only `metadata["fallback_for_api_call_demand_id"]` or
  `metadata["api_call_demand_id"]` triggers deletion. No bare step_id pattern matching.
- **Renderer/Gate/SPL Editing involvement**: None (untouched).
- **SymbolTable / ProducerIndex policy**: residual GENERAL_COMMAND `outputs=[]` unchanged.

## Findings from Previous Review Round
- `_is_fallback_step` previously promoted `st_fallback_{demand_id}` / `st_fallback_{span_id}`
  naming patterns to stage-owned metadata inside `materialize_direct_api_calls`. This shim has
  been **completely removed**. No more LLM-controlled step_id → deletion path.
- Production upstream coverage was confirmed to still emit only partial operation surface
  (`"retrieve them..."`) when the raw LLM evidence doesn't include the conditional prefix.
  This is now fixed upstream in `planner.py` before the coverage IR is frozen.

## Negative Tests Added
- `test_conditional_trigger_coverage_expansion_upstream` (construct_plan unit test):
  Proves ConstructPlanner expands partial evidence to full conditional sentence in upstream IR.

## Regression
- All 30 Stage 7 unit/integration tests pass.
- All 33 construct_plan + multi_worker_pipeline tests pass (10 pre-existing skips).
- No changes to Renderer, Gate, SPL Editing, or other stages.

## PM Decision
- Ready for re-review. P3 v2 addresses all three blockers from the previous fail verdict.
