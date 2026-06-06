# Stage 9.5 rule-based semantic cleanup plan

## Background

Stage 9.5 is currently named `IRNormalizer`, but the implementation mixes three
different responsibilities:

1. Deterministic IR normalization and consistency checks.
2. Construct-level diagnostics that belong to post-normalize IRS.
3. Rule-based semantic repair based on text keywords.

The third category is the problem. Pure code is stable only when it consumes
stable structure. It should not infer user intent, handler semantics, flow
semantics, or interaction semantics from natural-language fragments. Those
decisions belong in LLM stages and IRS satisfaction checks. Silent fallback or
semantic repair also makes LLM failures harder to debug because the downstream
IR may look superficially valid after code has rewritten it.

This document defines a cleanup plan. It does not change production code by
itself.

## Design Principle

### Allowed in pure code

Pure code may do deterministic compiler work:

- Validate that IDs referenced by one IR exist in another IR.
- Reconcile fields from authoritative structured sources, such as
  `WorkerPlanIR` handoffs and worker ownership.
- Build graph/index views over existing structured IR.
- Normalize syntax shape required by SPL, such as one `RESULT` variable per
  command.
- Populate producer/consumer links from explicit step inputs and outputs.
- Fail fast when an LLM stage emits malformed IR.

### Not allowed in pure code

Pure code must not:

- Decide that a natural-language condition is a real exception, ordinary
  condition, loop, refusal, or retry policy by keyword.
- Decide that a `DISPLAY_MESSAGE` step is really `REQUEST_INPUT` by keyword.
- Decide that an exception-flow step is a "pseudo handler" by keyword.
- Invent, downgrade, or rewrite semantic command types to make output render.
- Patch source-specific variables such as `available_connectors` into generic
  dataflow.
- Hide LLM failures with semantic fallback.

### IRS boundary

IRS answers whether a materialized construct has the required slots and source
evidence. It may report incomplete constructs. It must not modify input IR,
generate missing constructs, or parse raw NL with keyword rules.

Post-normalize IRS should be the final authority for construct-level diagnostics
after Stage 10 assembles `WorkerIR`.

## Current Production Path

Current orchestrator path:

```text
Stage 7 worker-scoped step extraction
  -> Stage 9 constraint extraction
  -> Stage 9.5 IRNormalizer.normalize_worker_scoped()
  -> Stage 10 WorkerAssembler
  -> PostNormalizeIRSChecker.check()
  -> ExecutableElementGate
  -> Renderer
```

`PipelineOrchestrator` calls `_run_normalization_worker_scoped()`, which creates
`IRNormalizer()` and calls `normalize_worker_scoped()`.

The legacy flat `IRNormalizer.normalize()` path is not called by current
production orchestrator code. It is still referenced by direct unit and
integration tests.

## Problem Inventory

### 1. Legacy `normalize()` path

Location:

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalizer.py`

Problem:

- `normalize()` is no longer on the production orchestrator path.
- It retains old semantic repair behavior:
  - flow classification repair;
  - source-retrieval input remapping;
  - legacy child delegation candidate materialization;
  - legacy required-output finding;
  - legacy constraint reconciliation.
- Tests still call it directly, so it looks supported even though production
  has moved to worker-scoped IR.

Decision:

- Remove `normalize()` as a supported public entry point.
- If tests need flat fixtures, migrate them to worker-scoped fixtures or move
  them to focused helper tests for retained deterministic helpers.

Rationale:

- Keeping two public normalizer paths keeps semantic cleanup ambiguous.
- The flat path preserves rule-based behavior that should not be revived.

### 2. Rule-based flow classification repair

Locations:

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/flow_classification.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/helpers.py`

Problem:

- `_normalize_flow_classification()` moves flows between main, alternative, and
  exception structures.
- `_is_exception_condition()` relies on keywords such as `fail`, `missing`,
  `invalid`, `cannot`, and `blocked`.
- `_is_loop_condition()` relies on `"do not finalize"` and `"missing"`.

This is semantic classification from raw text. It cannot be complete and will
be brittle across domains.

Decision:

- Delete this behavior with the legacy flat path.
- Do not port it to `normalize_worker_scoped()`.
- Flow classification should be owned by Stage 4 LLM and, where needed,
  Stage 4 IRS diagnostics.

Replacement:

- Stage 4 should emit the flow classification it believes is correct.
- Stage 9.5 may validate structural consistency:
  - flow IDs referenced by blocks exist;
  - flow spans are owned by the worker;
  - no duplicate blocks for the same stable span set unless explicitly allowed.
- If Stage 4 output is inconsistent, fail or diagnose. Do not silently move
  spans between semantic flow categories.

### 3. `available_connectors` source-retrieval input repair

Location:

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`

Problem:

- `_normalize_source_retrieval_inputs()` rewrites step inputs to
  `available_connectors` when step text contains source/retriev/provenance.
- `available_connectors` is source/application-specific, not a compiler-level
  invariant.
- The rewrite can hide Stage 6/7 contract failures.

Decision:

- Delete `_normalize_source_retrieval_inputs()` together with the legacy flat
  path.
- Do not call an equivalent in worker-scoped normalization.

Replacement:

- Stage 6 should declare runtime inputs and resource variables.
- Stage 7 should choose step inputs using the `SymbolTable`.
- Handoffs should carry explicit input bindings.
- If a retrieval step lacks necessary inputs, report a missing input/contract
  diagnostic rather than rewriting it.

### 4. `DISPLAY_MESSAGE` -> `REQUEST_INPUT` repair

Location:

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`
- Called from `normalize_worker_scoped()`.

Problem:

- `_normalize_interactive_display_steps()` inspects step text and changes
  `DISPLAY_MESSAGE` to `REQUEST_INPUT` if the text contains markers such as
  ask, clarify, prompt, confirm, collect user, or iterate with user.
- Stage 7 prompt already tells the LLM how to distinguish `REQUEST_INPUT` from
  `DISPLAY_MESSAGE`.
- Reclassification hides Stage 7 mistakes and turns semantic intent into a
  hard-coded phrase list.

Decision:

- Remove command-type mutation from Stage 9.5.
- Keep only structural validation:
  - `REQUEST_INPUT` must have a source span or accepted handoff/scaffold
    evidence;
  - `DISPLAY_MESSAGE` may display already-produced values;
  - a `DISPLAY_MESSAGE` with outputs is structurally suspicious and should be a
    diagnostic/error, not auto-rewritten.

Replacement options:

1. Preferred: fail-fast validation in Stage 9.5 for impossible command shapes.
2. Optional: Stage 7 IRS diagnostic for ambiguous command type, with no IR
   mutation.
3. Optional later: a dedicated LLM repair pass only if explicitly enabled and
   visible in compile diagnostics. It must not run as hidden fallback.

Recommended near-term behavior:

```text
if command_type == DISPLAY_MESSAGE and outputs:
    emit validation error: DISPLAY_MESSAGE cannot produce outputs

if command_type == REQUEST_INPUT and no source_span_ids and no accepted handoff:
    post-normalize IRS emits type_or_contract_ambiguity

do not rewrite command_type
```

### 5. Required output producer checks

Locations:

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py`

Problem:

- `_ensure_required_main_outputs()` and `_ensure_required_worker_outputs()`
  record `missing_output_producer` in `construct_findings`.
- `PostNormalizeIRSChecker._check_missing_output_producers()` independently
  checks required outputs after Stage 10 with assembled worker scope.
- The normalizer-side finding is either legacy or duplicative.

Decision:

- Move final required-output producer responsibility fully to
  `PostNormalizeIRSChecker`.
- Stage 9.5 may build or refresh producer/consumer links, but it should not
  create final missing-output findings.

Replacement:

- Keep `ProducerIndex` as the deterministic structural mechanism.
- Use it in post-normalize IRS, after Stage 10, because that is where the
  full `WorkerIR` and child worker scopes are available.
- Remove `missing_output_producer` collection from `IRNormalizer`.

Rationale:

- Required output producer is an IRS completeness question:
  "does this required output have source-backed production evidence?"
- Stage 9.5 does not need to precompute a diagnostic that the final checker
  already has authority to compute.

### 6. Pseudo exception handler detection

Location:

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`
- Findings consumed by `PostNormalizeIRSChecker`.

Problem:

- `_is_pseudo_handler()` classifies a handler as pseudo if its text and spans
  match hard-coded phrase patterns such as "do not finalize", "check if",
  "confirm with the user", or "display a message".
- `_diagnose_exception_flow_handlers()` removes those steps from the step list.
- This is semantic interpretation and IR mutation. A display/report step may
  be a valid handler in some workflows.

Decision:

- Stop deleting steps as pseudo handlers in Stage 9.5.
- Stop using text-marker pseudo-handler classification.
- Missing handler should be checked structurally first:
  - does the exception flow have at least one step with matching `flow_ref`;
  - is that step renderable after Gate;
  - does the source/IRS say a handler action slot is satisfied?

Replacement:

- Stage 4/7 LLM should decide whether source text contains a handler action.
- Stage 4 IRS may report exception flow missing handler evidence from the
  stage-local view.
- Post-normalize IRS should emit `missing_handler` when the assembled IR has no
  handler step for the exception flow.
- If future handler-action semantics are required, add an IRS checker that
  consumes structured fields, not raw text keywords.

Near-term behavior:

```text
if exception_flow exists and no step.flow_ref == exception_flow.flow_id:
    PostNormalizeIRSChecker emits missing_handler

if a step exists:
    Stage 9.5 does not decide whether its text is "real enough"
```

### 7. Stage 7 command downgrade fallback

Location:

- `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py`

Problem:

- Child worker steps with invalid `INVOKE_WORKER` or `CALL_API` are rewritten
  to `GENERAL_COMMAND`.
- This is outside Stage 9.5 but directly affects Stage 9.5 input quality.
- It hides LLM command-type errors.

Decision:

- Replace downgrade with explicit validation error or diagnostic.
- Do not convert semantic command types to make the IR pass later stages.

Replacement:

```text
if child worker emits INVOKE_WORKER/CALL_API without accepted outgoing handoff:
    fail Stage 7 worker-scoped extraction or emit a blocking diagnostic
    do not mutate to GENERAL_COMMAND
```

This should be handled in the same cleanup wave because otherwise Stage 9.5
will continue receiving already-repaired semantic IR.

## Target Stage 9.5 Responsibility

After cleanup, Stage 9.5 should be reduced to a compiler consistency pass.

### Keep

1. Worker-scoped structural validation:
   - span ownership;
   - handoff step exists for each handoff;
   - handoff mode matches `CALL_API` or `INVOKE_WORKER`;
   - handoff input/output bindings match the step shape;
   - child output contract is bound back to parent where required.

2. Symbol table refresh:
   - recompute producer and consumer links from final step inputs/outputs;
   - remove stale producer links only from compiler-owned indexes, not from
     source contracts.

3. Multi-output structural aggregation:
   - one SPL command can only emit one result variable;
   - aggregate multiple outputs into a structured result variable;
   - record metadata for downstream rendering and diagnostics.

4. Reference validation:
   - step variables exist;
   - declared API references are known or handoff-bound;
   - constraint targets exist.

5. Deterministic shape checks:
   - unsupported command/output combinations;
   - missing handoff ID for handoff-generated steps;
   - malformed worker ownership references.

### Remove

1. `normalize()` legacy flat entry point.
2. Flow semantic reclassification.
3. Source-retrieval input remapping.
4. Command-type semantic reclassification.
5. Pseudo-handler keyword detection and step deletion.
6. Normalizer-side required-output producer findings.
7. Any silent semantic fallback introduced to make LLM output pass.

## Proposed Module Shape

Current package:

```text
stage9_5_normalizer/
  normalizer.py
  normalization.py
  validation.py
  worker_scoped.py
  worker_handoffs.py
  flow_classification.py
  helpers.py
  final_irs_checker.py
```

Target package:

```text
stage9_5_normalizer/
  normalizer.py              # thin facade: normalize_worker_scoped only
  structural_normalization.py # multi-output aggregation, symbol sync
  structural_validation.py   # references, ownership, handoffs
  worker_scoped.py           # orchestration of structural passes
  helpers.py                 # ID sorting/safe names only
  final_irs_checker.py       # post-normalize IRS authority
```

Delete or empty:

- `flow_classification.py`
- legacy parts of `normalization.py`
- flat legacy entrypoint in `normalizer.py`

Optional intermediate:

- Keep filenames stable initially, but delete semantic methods and calls.
- Rename modules only after behavior cleanup is passing, to avoid mixing
  semantic and mechanical refactors.

## Implementation Plan

### Phase 0: Baseline audit

Goal:

- Confirm all production entry points and tests that still depend on legacy or
  semantic-repair behavior.

Commands:

```powershell
rg -n "\.normalize\(|normalize_worker_scoped\(|_normalize_interactive_display_steps|_normalize_flow_classification|_normalize_source_retrieval_inputs|_diagnose_exception_flow_handlers|_ensure_required.*outputs" src tests docs
```

Expected audit output:

- `src/nl2spl/pipeline/orchestrator.py` only calls
  `normalize_worker_scoped()`.
- Legacy `normalize()` references are tests/docs only.
- Worker-scoped path still calls:
  - `_normalize_interactive_display_steps()`;
  - `_normalize_multi_output_steps()`;
  - `_ensure_required_worker_outputs()`;
  - `_diagnose_exception_flow_handlers()`.

Acceptance:

- Create a checklist of tests to delete, rewrite, or preserve.

### Phase 1: Remove legacy flat normalizer support

Actions:

1. Delete `IRNormalizer.normalize()`.
2. Delete `_normalize_flow_classification()` and `flow_classification.py`.
3. Delete `_normalize_source_retrieval_inputs()`.
4. Delete legacy `_materialize_child_worker_invocations()` if no production
   worker-scoped path uses it.
5. Update `IRNormalizer` inheritance list.
6. Delete or rewrite tests that directly assert legacy flat normalization.

Candidate tests to review:

- `tests/unit/test_normalizer.py`
- `tests/integration/test_partial_spl_mvp.py`
- `tests/integration/test_multi_worker_pipeline.py`
- `tests/integration/test_llm_adapter_engine_e2e.py`
- `tests/integration/test_e2e_failure_handling.py`
- legacy direct calls inside
  `tests/unit/pipeline/stages/test_worker_plan_normalizer.py`

Migration rule:

- If a test verifies a valid structural behavior, rewrite it to
  `normalize_worker_scoped()`.
- If a test verifies semantic repair, delete it or rewrite it to assert the
  opposite: no rewrite occurs and a diagnostic/error is produced.

Acceptance:

- No production or test code imports or calls `IRNormalizer.normalize()`.
- `rg -n "\.normalize\(" tests src` has no `IRNormalizer().normalize(...)`
  calls.

### Phase 2: Remove command-type semantic repair

Actions:

1. Remove `_normalize_interactive_display_steps()` calls from
   `normalize_worker_scoped()`.
2. Delete `_normalize_interactive_display_steps()` and
   `_looks_like_user_input_step()`, unless retained only in a deleted legacy
   module during Phase 1.
3. Add validation for impossible command shapes:
   - `DISPLAY_MESSAGE` with outputs should be error or blocking diagnostic.
   - `REQUEST_INPUT` without source evidence should remain a post-normalize
     IRS diagnostic, not a normalizer rewrite.

Test changes:

- Change tests that expect `DISPLAY_MESSAGE` to become `REQUEST_INPUT`.
- New tests should assert:
  - command type remains unchanged;
  - invalid shape is reported;
  - Stage 7 classification errors are visible.

Acceptance:

- Stage 9.5 never mutates `step.command_type` based on `step.text`.

### Phase 3: Move required-output producer authority to post-normalize IRS

Actions:

1. Remove `_ensure_required_worker_outputs()` call from
   `normalize_worker_scoped()`.
2. Delete `_ensure_required_worker_outputs()` and
   `_ensure_required_main_outputs()` if legacy path is gone.
3. Keep `ProducerIndex` usage in `PostNormalizeIRSChecker`.
4. Ensure `PostNormalizeIRSChecker` covers:
   - main worker required outputs;
   - child worker required outputs;
   - handoff output bindings;
   - structured aggregation outputs.

Test changes:

- Tests should call `PostNormalizeIRSChecker.check()` for
  `missing_output_producer`, not inspect `normalizer.construct_findings`.
- Remove expectations that normalizer records `missing_output_producer`.

Acceptance:

- `normalizer.construct_findings` no longer contains
  `missing_output_producer`.
- `PostNormalizeIRSChecker` remains the only producer of final
  `missing_output_producer` diagnostics.

### Phase 4: Remove pseudo-handler text rules

Actions:

1. Delete `_is_pseudo_handler()`.
2. Delete pseudo-handler removal from `_diagnose_exception_flow_handlers()`.
3. Replace `_diagnose_exception_flow_handlers()` with a structural helper or
   remove it entirely.
4. Let `PostNormalizeIRSChecker` detect missing handler from assembled
   `WorkerIR`:
   - no step in the exception flow -> `missing_handler`;
   - step exists -> no normalizer decision about semantic adequacy.

Optional future work:

- Add a real IRS checker for `EXCEPTION_HANDLER_ACTION` only if it consumes
  structured evidence created by Stage 4/7, not raw text keywords.

Test changes:

- Delete tests that expect `pseudo_handlers` findings from Stage 9.5.
- Add tests:
  - exception flow with no handler step -> post-normalize `missing_handler`;
  - exception flow with a display step remains present and is judged later by
    renderability/IRS, not deleted by normalizer.

Acceptance:

- Stage 9.5 never deletes a step based on text content.
- No code references `pseudo_exception_handler` metadata unless it is produced
  by a future explicit source-backed mechanism.

### Phase 5: Remove Stage 7 semantic downgrade fallback

Actions:

1. In `stage7_step_extractor/worker_scoped.py`, replace child-worker
   `INVOKE_WORKER`/`CALL_API` downgrade with fail-fast validation.
2. If the current API cannot fail at that point, return a blocking diagnostic
   and leave the command unchanged.
3. Ensure invalid LLM output is visible in logs and compile diagnostics.

Test changes:

- Replace tests expecting downgraded `GENERAL_COMMAND`.
- Add tests that invalid child worker handoff commands fail or diagnose.

Acceptance:

- No semantic command type is downgraded to `GENERAL_COMMAND` to preserve
  compilation.

### Phase 6: Documentation and README cleanup

Actions:

1. Update README Stage 9.5 description:
   - "Normalized IRs, structural validation, SPL shape normalization".
   - Do not advertise "diagnostics" broadly unless specifically referring to
     structural errors/warnings.
2. Update IRS docs:
   - Post-normalize IRS owns construct-level diagnostics.
   - Stage 9.5 does not parse raw NL or classify semantic intent.
3. Remove docs that describe legacy flat `normalize()` as current behavior.

Acceptance:

- Docs match current production path and cleanup principles.

## Test Strategy

### Tests to keep

Keep tests that verify deterministic structure:

- worker span ownership;
- handoff shape and binding;
- API handoff target matching;
- structured multi-output aggregation;
- symbol table producer/consumer refresh;
- reference validation;
- post-normalize IRS diagnostics.

### Tests to delete or rewrite

Delete or rewrite tests that verify semantic keyword behavior:

- ordinary condition moved out of exception flow;
- source retrieval input rewritten to `available_connectors`;
- display step reclassified as request input;
- pseudo handler text detection;
- normalizer-side missing-output findings.

### New regression tests

Add negative tests:

1. `DISPLAY_MESSAGE` with ask-like text is not reclassified.
2. `DISPLAY_MESSAGE` with outputs reports invalid shape.
3. Exception flow handler step is not removed by normalizer.
4. Required output producer diagnostic comes only from
   `PostNormalizeIRSChecker`.
5. Invalid child-worker `INVOKE_WORKER` is not downgraded to
   `GENERAL_COMMAND`.
6. Legacy `IRNormalizer.normalize()` import/call is gone.

### Suggested test commands

```powershell
python -m pytest tests/unit/pipeline/stages/test_worker_plan_normalizer.py -q
python -m pytest tests/unit/pipeline/stages/test_final_irs_checker.py -q
python -m pytest tests/unit/test_producer_index.py -q
python -m pytest tests/pipeline/test_worker_aware_integration.py -q
python -m pytest tests/integration/test_e2e_failure_handling.py -q
```

Use a local `--basetemp` under the repo if pytest temporary writes collide with
the sandbox.

## Migration Risk

### Risk: LLM output quality drops because code no longer repairs it

This is expected. The goal is to expose LLM mistakes.

Mitigation:

- Improve Stage 4/7 prompts and schema validators.
- Add direct diagnostics for invalid IR.
- Keep examples of invalid LLM output as regression fixtures.

### Risk: More partial SPL or diagnostics

This is acceptable if the source evidence is incomplete or LLM output is
ambiguous. Rendering an invented command is worse.

Mitigation:

- Make diagnostics precise.
- Keep partial SPL behavior.
- Do not convert diagnostics into synthetic commands.

### Risk: Tests reveal hidden dependency on legacy flat path

Mitigation:

- Migrate only structurally valuable tests.
- Delete tests that lock obsolete semantic repair.
- Keep one explicit test that legacy entrypoint is unavailable, if public API
  breakage needs to be visible.

### Risk: Required output diagnostics change timing

Mitigation:

- Assert final compile diagnostics, not intermediate normalizer findings.
- Ensure `PostNormalizeIRSChecker` is always run before Gate.

## Implementation Order Summary

Recommended order:

1. Remove legacy `normalize()` and old semantic helpers from the public path.
2. Remove worker-scoped `DISPLAY_MESSAGE` semantic reclassification.
3. Move required-output producer diagnostics fully to post-normalize IRS.
4. Remove pseudo-handler keyword detection and step deletion.
5. Replace Stage 7 command downgrade fallback with fail-fast behavior.
6. Update tests and docs.

This order first removes dead code, then removes active semantic mutation, then
cleans diagnostic authority duplication.

## Definition of Done

The cleanup is complete when:

- `IRNormalizer` exposes only worker-scoped normalization used by production.
- Stage 9.5 does not mutate command types based on text.
- Stage 9.5 does not move flows between semantic categories.
- Stage 9.5 does not rewrite source-specific variables such as
  `available_connectors`.
- Stage 9.5 does not delete handler steps based on text keywords.
- Required output producer final diagnostics come from
  `PostNormalizeIRSChecker`.
- Stage 7 does not downgrade invalid command types to `GENERAL_COMMAND`.
- Tests verify structural compiler behavior and final diagnostics, not hidden
  semantic fallback.
