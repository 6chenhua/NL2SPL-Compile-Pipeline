# SPL Editing Construct-Level Repair Strategy and Repair-Mode Stage Slice Implementation Plan

This implementation plan is based on `docs/design/spl_editing_construct_level_repair_strategy_and_stage_slice_design.md`.

Goal: evolve SPL Editing from patch-action based repair materialization into construct-level repair strategy plus repair-mode stage-slice materialization, while preserving the R0-R11 safety baseline.

Scope:

```text
In scope:
  - RepairStrategySpec foundation.
  - RepairDirective / ConstructRepairIntent boundary hardening.
  - ConstructClosurePlan / MaterializationPlan relationship.
  - Preview dry-run / confirmed apply lifecycle.
  - RepairModeStageSlice interfaces and typed-plan boundaries.
  - missing_handler migration as the first implementation case.
  - follow-up migrations for missing_output_producer and worker delegation.
  - legacy patch-action-as-strategy cleanup.

Out of scope for the first wave:
  - Rewriting full NL2SPL stages into reusable full-stage APIs.
  - Fabricating SpanIR or compile hints to reuse full-run executors.
  - Adding non-MVP repair families beyond the documented migration path.
```

---

## 1. Overall Target Architecture

Final R12+ flow:

```text
CompileDiagnostic + IRS metadata
  -> EditableIssue
  -> RepairCatalog
  -> RepairStrategySpec
  -> TargetResolver
  -> SelectableRefSet
  -> optional RepairDirective
  -> LLM generates ConstructRepairIntent candidate
  -> IntentParser + SelectableRef validation
  -> ConstructClosurePlan
  -> Preview dry-run stage slices
  -> PreviewMaterializationResult
  -> user confirmation
  -> RepairEvidencePacket
  -> Apply materialization
  -> Artifact overlay
  -> Lane B replay
  -> IRS / Gate / ProducerIndex / Renderer / Provenance / Verification
```

Authority split:

```text
IRS / RepairAffordance:
  Declares repairability and strategy metadata only.

RepairStrategySpec:
  Describes construct-level repair direction and required construct closure.

RepairDirective:
  Captures user advice or system-default repair preference. It is provisional.

ConstructRepairIntent:
  Captures target construct, selected refs, and strategy after validation.

ConstructClosurePlan:
  Instance-level plan for ensure / bind_existing / materialize construct nodes.

MaterializationPlan:
  Executable plan that invokes repair-mode stage slices and writes audit metadata.

RepairModeStageSlice:
  Stage-authorized local construct generator. It may call LLM only for typed plans.

Verification:
  Acceptance authority. It does not generate or repair artifacts.
```

---

## 2. Global Hard Principles

1. LLM output must not become `StepIR`, `BlockIR`, `WorkerHandoffIR`, raw inputs, raw outputs, worker refs, connector refs, or handoff refs directly.
2. `RepairDirective` is not evidence authority. Confirmed evidence is created only as `RepairEvidencePacket` after user confirmation.
3. `RepairDirective.selected_ref_hints` are hints only. Materialization may consume only `ConstructRepairIntent.selected_ref_ids` validated against `SelectableRefSet`.
4. `diagnostic.message` and UI display text must not be parsed for primary materialization facts.
5. Preview dry-run must not create accepted overlay state.
6. Apply must reject stale preview results by checking base snapshot, intent hash, directive hash, closure plan hash, selected refset identity/equivalence, typed-plan hashes, preview construct hashes, and LLM generation config hash when applicable.
7. `supported_patch_types` is transitional. If `repair_strategy_id` exists, UI, prompt, and catalog semantics must use strategy id.
8. No new R12+ patch type may encode final construct shape as policy.
9. Stage 9.5 remains structural normalization only. It must not perform semantic repair.
10. IRS declares affordances and checks slots. It must not execute repair, call LLM, or decide command text.
11. Any compatibility shim must include an explicit removal phase and must not be in the default production path.
12. Each phase must be independently testable.

---

## 3. LLM and Rule-Based Decision Constraints

Allowed deterministic logic:

```text
- Reading structured fields from ArtifactSnapshot, TargetResolverResult, SelectableRefSet, and RepairCatalog.
- Validating ids, hashes, ref roles, scope, and dependency closure.
- Allocating stable ids through declared allocators.
- Comparing preview/apply hashes.
- Rendering user-facing previews from structured preview results.
```

Allowed LLM use:

```text
- LLM may generate ConstructRepairIntent candidates.
- Stage slices may invoke LLM as constrained generators for slice-local typed plans.
- Typed plans must be schema-validated and converted to IR only by stage-slice materializers.
```

Forbidden LLM use:

```text
- LLM outputting final IR objects.
- LLM outputting raw variable names as materialization authority.
- LLM inventing refs not present in SelectableRefSet.
- LLM deciding final verification acceptance.
- LLM-generated issue presentation facts.
```

---

## 4. Phase R12.0 - Baseline Contract Freeze and Gap Lock

### Goal

Lock the current gap and target contract before changing runtime behavior.

This phase must not require future R12+ production models to exist. It creates
current-behavior characterization tests and an explicit contract ledger that is
promoted into executable target-behavior tests in later phases.

### Editable Scope

Allowed additions:

```text
tests/unit/compiler/spl_editing/construct_strategy/
  test_r12_contract_baseline.py
  test_preview_apply_contract_baseline.py
  test_strategy_transition_guards.py

docs/design/r12_contract_test_ledger.md
```

No production changes are allowed in this phase.

### Design Requirements

Executable tests must express current behavior and guard against accidental
backsliding only:

```text
- Existing R0-R11 missing_handler behavior is still the default path.
- Existing R0-R11 evidence, selectable-ref, materialization, and verification
  safeguards remain intact.
- No production module imports future R12+ placeholders.
- No default path starts using strategy metadata before the strategy runtime
  exists.
```

Target behavior that depends on future DTOs or services must be recorded in the
contract ledger, not as skipped/xfail tests.

The ledger must list the tests to promote in:

```text
R12.1:
  RepairDirective has no evidence authority.
  selected_ref_hints are not materialization authority.
  ConstructClosureNode supports ensure / bind_existing / materialize.

R12.4:
  Preview result includes typed-plan / construct / config hashes when generation is used.
  Apply without matching preview hashes is rejected.

R12.2/R13.0:
  Strategy id is the semantic source when present.
  Patch type is only an execution adapter when strategy id exists.
```

### Test Plan

1. Characterization test for the current missing_handler default path.
2. Characterization test for the current preview absence in the default path.
3. Static audit that no non-existent R12+ model is imported by production code.
4. Contract ledger entry for every target test listed above.
5. Static audit test that no new R12+ strategy is introduced as a patch-type label.

### Acceptance Criteria

1. R12.0 tests pass against the current production code.
2. No production behavior changes.
3. No new skip or xfail.
4. No executable test imports DTOs or services that do not exist yet.
5. Contract ledger lists the target tests to promote in R12.1, R12.2, R12.4, and R13.0.

### PM Review Checklist

1. Tests distinguish R0-R11 safety from R12+ semantic upgrade.
2. Tests do not permit diagnostic message parsing.
3. Tests do not treat patch type as strategy source.
4. Target behavior that cannot yet run is in the ledger, not hidden behind skip/xfail.

---

## 5. Phase R12.1 - Strategy and Directive Model Foundation

### Goal

Introduce first-class strategy, directive, closure, and preview models without wiring them into production repair behavior yet.

### Editable Scope

Allowed additions:

```text
src/nl2spl/compiler/spl_editing/strategy/
  __init__.py
  model.py
  registry.py
  errors.py

src/nl2spl/compiler/spl_editing/closure/
  __init__.py
  model.py
  planner.py
  errors.py

src/nl2spl/compiler/spl_editing/preview/
  __init__.py
  model.py
  hashes.py
  errors.py
```

Allowed modifications:

```text
src/nl2spl/compiler/spl_editing/intent/model.py
src/nl2spl/compiler/spl_editing/core/catalog.py
```

Forbidden in this phase:

```text
No handler production path changes.
No applier behavior changes.
No CLI behavior changes.
No prompt changes.
```

### Implementation Notes

Implement immutable DTOs:

```text
RepairStrategySpec
RepairDirective
ConstructClosureNode
ConstructClosurePlan
PreviewMaterializationResult
StageSliceTypedPlanRef
```

`RepairDirective` must include only provisional intent fields such as:

```text
directive_id
source
requested_behavior
selected_ref_hints
constraints
confidence
```

It must not include evidence authority fields.

`ConstructClosureNode.action` must be one of:

```text
ensure
bind_existing
materialize
```

`PreviewMaterializationResult` must include:

```text
preview_id
base_snapshot_id
intent_hash
directive_hash
closure_plan_hash
selected_refset_id
slice_typed_plan_hashes
preview_construct_hashes
llm_generation_config_hash
rendered_preview
```

### Test Plan

1. DTO immutability tests.
2. Constructor validation tests.
3. Closure action enum tests.
4. Preview hash field presence tests.
5. Negative test: `RepairDirective` cannot carry evidence authority.
6. Hash determinism tests for preview identity fields.

### Acceptance Criteria

1. Models import without handlers, appliers, LLM clients, or stage executors.
2. `RepairDirective` cannot be mistaken for confirmed evidence.
3. Preview DTO supports deterministic and LLM-generated typed-plan preview.
4. Unit tests pass.

### PM Review Checklist

1. Model layer has no side effects.
2. No dependency from strategy/closure/preview models into runtime service.
3. Field names match design doc.

---
## 6. Phase R12.2 - RepairStrategy Registry and Catalog Integration

### Goal

Make strategy id the semantic source for R12+ repairs while preserving patch types only as execution adapters during migration.

### Editable Scope

Allowed additions:

```text
src/nl2spl/compiler/spl_editing/strategy/defaults.py
src/nl2spl/compiler/spl_editing/strategy/catalog_projection.py
```

Allowed modifications:

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/spl_editing/core/catalog.py
src/nl2spl/compiler/spl_editing/presentation/templates/repair_option_copy.py
```

Forbidden in this phase:

```text
No handler prompt rewrites.
No stage-slice implementation yet.
No removal of existing patch execution adapters.
```

### Implementation Notes

Extend repair affordance / catalog projection to carry:

```text
repair_strategy_id
strategy_display_label
closure_summary
selectable_ref_policy_id
preview_required
```

Add default strategy specs:

```text
exception_flow.complete_handler_action.v1
required_output.materialize_producer.v1
worker_delegation.complete_closure.v1
```

Transition rules:

```text
- If repair_strategy_id exists, presentation uses strategy semantics.
- R12.2 may expose strategy metadata to prompt context builders, but it must not
  change concrete handler prompt schemas or LLM output schemas.
- Concrete prompt/schema migration belongs to R13.x.
- supported_patch_types remain available only for selecting execution adapter.
- New R12+ code cannot display patch type as the repair strategy label.
```

### Test Plan

1. RepairCatalog builds entries with strategy metadata.
2. Entries without strategy remain legacy and are not R12+ capable.
3. Presentation uses strategy label when strategy exists.
4. Static test: no R12+ presentation copy uses patch type as semantic heading.
5. Negative test: duplicate strategy registration fails.

### Acceptance Criteria

1. `RepairCatalogEntry` can carry `repair_strategy_id`.
2. R12+ strategies are visible to presentation but do not change apply behavior yet.
3. Existing tests remain green.
4. No new patch type name encodes final construct shape policy.
5. No handler prompt text, prompt schema, or LLM output schema changes in this phase.

### PM Review Checklist

1. IRS still only declares metadata.
2. Catalog does not import stage-slice implementations.
3. Presentation does not fall back to patch-action semantics when strategy exists.
4. Prompt-context metadata exposure is passive and cannot alter generation behavior yet.

---

## 7. Phase R12.3 - ConstructClosurePlan Planner

### Goal

Generate instance-level `ConstructClosurePlan` from strategy, target, directive, and selectable refs.

### Editable Scope

Allowed additions/modifications:

```text
src/nl2spl/compiler/spl_editing/closure/planner.py
src/nl2spl/compiler/spl_editing/closure/validators.py
src/nl2spl/compiler/spl_editing/closure/defaults.py
```

Forbidden in this phase:

```text
No IR construction in closure planner.
No LLM calls in closure planner.
No diagnostic.message parsing.
```

### Implementation Notes

Planner input:

```text
RepairStrategySpec
RepairTarget / TargetResolverResult
RepairDirective
SelectableRefSet summary
```

Planner output:

```text
ConstructClosurePlan
```

MVP closures:

```text
missing_handler:
  ensure handler_block
  materialize handler_action

missing_output_producer:
  ensure optional placement_block
  materialize producer_command

worker_delegation:
  materialize worker_handoff
  materialize invoke_worker_command
  bind_existing target_worker
  ensure optional placement_block
```

The planner must validate:

```text
- required target refs exist.
- node actions are legal for the strategy.
- stage_slice_id exists in the strategy stage chain.
- closure plan references materialization_plan_id.
```

### Test Plan

1. missing_handler closure plan has ensure block + materialize command.
2. missing_output_producer closure plan has materialize producer command.
3. worker_delegation closure plan has handoff + invoke + binding nodes.
4. Illegal action for strategy is rejected.
5. Missing target ref is rejected.
6. Closure plan hash is deterministic.

### Acceptance Criteria

1. Closure planner returns no IR.
2. Closure plan and materialization plan ids are linked.
3. Closure plan can be serialized or hashed for preview stale detection.
4. Tests cover ensure, bind_existing, and materialize actions.

### PM Review Checklist

1. Planner does not decide command text.
2. Planner does not allocate ids.
3. Planner does not consume selected refs directly beyond validation metadata.
4. Planner cannot create accepted overlay.

---

## 8. Phase R12.4 - Preview / Apply Lifecycle Infrastructure

This phase is intentionally split into small tasks.

### 8A. Preview Model and Hashing

#### Goal

Implement deterministic preview identity and stale-detection helpers.

#### Editable Scope

```text
src/nl2spl/compiler/spl_editing/preview/model.py
src/nl2spl/compiler/spl_editing/preview/hashes.py
src/nl2spl/compiler/spl_editing/preview/store.py
```

#### Implementation Notes

Add helpers to compute:

```text
intent_hash
directive_hash
closure_plan_hash
slice_typed_plan_hashes
preview_construct_hashes
llm_generation_config_hash
```

`PreviewMaterializationResult` must be immutable and must not contain an accepted overlay event.

`PreviewStore` lifecycle:

```text
- Keyed by preview_id.
- Scoped by session_id + base_artifact_snapshot_id + issue_id.
- Not part of the accepted overlay event log.
- May expire according to session policy.
- Stores typed plans or typed-plan refs when Gate A uses exact typed-plan promotion.
- Cannot be applied across session, issue, or snapshot mismatch.
```

#### Tests

1. Hashes are deterministic.
2. Hash changes when directive changes.
3. Hash changes when selected refs change.
4. Preview result cannot be marked accepted.
5. Preview from snapshot A cannot be applied to snapshot B.
6. Expired preview cannot be applied.
7. Preview store entry is not written to accepted overlay history.

#### Acceptance

Preview identity can be computed and stored without applying overlay.

### 8B. Preview Dry-Run Service

#### Goal

Create a service path that runs stage slices in dry-run mode and renders a preview without accepted overlay.

#### Editable Scope

```text
src/nl2spl/compiler/spl_editing/preview/service.py
src/nl2spl/compiler/spl_editing/materialization/service.py
```

#### Implementation Notes

The preview service should:

```text
1. Receive issue/session, strategy, directive, and selected refs.
2. Build ConstructRepairIntent candidate.
3. Validate selected refs against SelectableRefSet.
4. Build ConstructClosurePlan.
5. Run stage slices in dry-run mode.
6. Produce PreviewMaterializationResult.
```

It must not:

```text
- write accepted overlay.
- create RepairEvidencePacket.
- modify session current snapshot.
```

#### Tests

1. Preview does not change overlay version.
2. Preview returns rendered preview text.
3. Preview includes all required hash fields.
4. Preview fails on unknown ref.
5. Preview is scoped to the requesting session and issue.
6. Preview store does not expose entries across sessions.

#### Acceptance

CLI/service can request preview safely before confirmation, and preview state is scoped outside accepted overlay state.

### 8C. Confirmed Apply Stale Check

#### Goal

Ensure apply cannot diverge from preview.

#### Editable Scope

```text
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/preview/validators.py
src/nl2spl/compiler/spl_editing/verification/runner.py
```

#### Implementation Notes

Apply should:

```text
1. Load preview result by preview_id.
2. Check base snapshot id.
3. Check intent/directive/closure/refset hashes.
4. Check typed-plan and construct hashes if generation was used.
5. Create RepairEvidencePacket only after confirmation.
6. Apply materialization or promote exact validated typed plans.
```

If apply re-runs constrained LLM generation, it must use deterministic seed/config and verify typed-plan hashes.

#### Tests

1. Apply succeeds when preview hashes match.
2. Apply fails when directive hash differs.
3. Apply fails when selected refset differs.
4. Apply fails when typed-plan hash differs.
5. Apply fails when preview session, issue, or base snapshot does not match.
6. Apply fails when preview is expired.
7. RepairEvidencePacket is created only after confirmation.

#### Acceptance

No preview/apply drift is possible in the default path.

---

## 9. Phase R12.5 - RepairModeStageSlice Substrate

### Goal

Introduce reusable stage-slice interfaces, typed-plan validation, and result contracts before migrating individual repair families.

### Editable Scope

Allowed additions:

```text
src/nl2spl/compiler/spl_editing/stage_slices/
  __init__.py
  model.py
  registry.py
  typed_plan.py
  result.py
  errors.py
```

Allowed modifications:

```text
src/nl2spl/compiler/spl_editing/materialization/model.py
src/nl2spl/compiler/spl_editing/materialization/registry.py
```

Forbidden in this phase:

```text
No migration of missing_handler yet.
No production prompt rewrite yet.
No direct CLI changes.
```

### Design Requirements

Define:

```text
RepairModeStageSlice protocol
StageSliceInput
StageSliceResult
TypedPlan
TypedPlanValidator
StageSliceRegistry
```

Stage slice may call LLM only through a constrained interface that returns typed plans.

Typed-plan examples:

```text
BlockShapePlan
CommandIntentPlan
HandoffContractPlan
InvokeWorkerPlan
```

### Test Plan

1. Registry duplicate slice id fails.
2. Stage authority mismatch fails.
3. Typed plan schema validation fails on raw IR fields.
4. StageSliceResult includes generated construct refs and consumed directive id.
5. LLM typed-plan hash is stable for a fixture.

### Acceptance Criteria

1. Stage-slice substrate exists and is not tied to missing_handler.
2. No stage slice accepts raw `StepIR` from LLM.
3. No stage slice can produce accepted overlay directly.
4. Unit tests pass.

### PM Review Checklist

1. Stage slice registry does not duplicate materialization registry responsibilities.
2. Typed plan validators reject IR-shaped payloads.
3. LLM usage is behind explicit constrained generator interface.

---
## 10. Phase R13.0 - missing_handler Strategy Wiring

### Goal

Make `missing_handler` use `CompleteExceptionHandlerAction` strategy semantics while still allowing legacy execution path only if explicitly isolated.

### Editable Scope

Allowed modifications:

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/spl_editing/core/catalog.py
src/nl2spl/compiler/spl_editing/handlers/missing_handler/
src/nl2spl/compiler/spl_editing/presentation/
```

Forbidden in this phase:

```text
No Stage5/Stage7 slice implementation in this phase.
No direct new BlockIR/StepIR construction outside existing legacy path.
No prompt answer leakage.
```

### Implementation Notes

Update missing_handler affordance/catalog projection in shadow mode:

```text
repair_strategy_id = exception_flow.complete_handler_action.v1
closure = ensure handler_block + materialize handler_action
preview_required = true (shadow/feature-gated until R13.3)
verification_lane = B
```

R13.0 must not switch the default `Fix with AI` path to preview/apply.
Default production behavior remains the legacy R0-R11 path until R13.3 E2E
passes and the preview feature gate is explicitly enabled.

Presentation should show user-facing strategy text:

```text
Complete exception handler action
```

It should not show these by default:

```text
AddExceptionHandlerStep
Stage5ExceptionHandlerBlockRepairSlice
Lane B
```

These may appear only in advanced details.

### Test Plan

1. missing_handler catalog entry has strategy id.
2. user-facing presentation uses strategy label.
3. advanced details still include patch/plan/lane for developer mode.
4. prompt generation does not ask for concrete command type as final answer.
5. Default CLI/service path does not use preview_required while the R13.3 gate is disabled.

### Acceptance Criteria

1. missing_handler strategy metadata is available end-to-end.
2. No behavior change in apply path yet unless feature-gated by preview path.
3. Existing missing_handler tests still pass.
4. `preview_required=true` is shadow/feature-gated and cannot affect default production flow before R13.3.

### PM Review Checklist

1. Patch type is not visible as strategy label.
2. No new hardcoded concrete command choice in prompt.
3. No parsing of diagnostic.message for condition text.
4. Preview metadata is present but not default-routable until R13.3.

---

## 11. Phase R13.1 - Stage5ExceptionHandlerBlockRepairSlice

### Goal

Move handler block decision authority into a Stage 5 repair slice.

### Editable Scope

Allowed additions:

```text
src/nl2spl/compiler/spl_editing/stage_slices/stage5/
  __init__.py
  exception_handler_block.py
  block_shape_plan.py
```

Allowed modifications:

```text
src/nl2spl/compiler/spl_editing/materialization/stage7/exception_handler_step.py
src/nl2spl/compiler/spl_editing/materialization/registry.py
```

Forbidden in this phase:

```text
No command generation in Stage5 slice.
No StepIR construction in Stage5 slice.
No diagnostic.message parsing.
```

### Implementation Notes

Stage5 slice input:

```text
Target exception flow
TargetResolverResult structured facts
existing WorkerFlowPlanIR
existing WorkerBlockPlanIR
ConstructClosurePlan node: handler_block
directive
id allocator
```

Stage5 slice behavior:

```text
- If handler block already exists: action is ensure/bind_existing and no duplicate block is created.
- If no handler block exists: materialize a block and record allocated block id + authority.
- Default no-user-advice policy: create minimal SEQUENTIAL block.
- Directive-driven policy may choose another allowed block shape through BlockShapePlan.
```

`BlockShapePlan` must not be `BlockIR`. It may contain:

```text
block_type
rationale
child_action_slots
```

Legacy materializer downgrade rule:

```text
Stage7ExceptionHandlerStepMaterializer may be touched only as a legacy adapter
or thin orchestration facade. It must not decide handler block shape, construct
both BlockIR and StepIR, bypass Stage5/Stage7 StageSliceResult, or become the
R13+ default path. R16 must delete it or make it explicitly non-default.
```

### Test Plan

1. Existing handler block is reused or bound, not duplicated.
2. Missing handler block creates exactly one block.
3. Allocated block id is stable and recorded.
4. Stage5 slice rejects diagnostic.message sourced condition text.
5. LLM BlockShapePlan cannot include BlockIR fields.
6. Stage5 slice produces StageSliceResult with generated construct refs.

### Acceptance Criteria

1. Stage5 owns handler block shape.
2. Stage5 does not generate command or step IR.
3. Duplicate handler block prevention is tested.
4. No direct overlay acceptance in preview mode.

### PM Review Checklist

1. ensure / bind_existing / materialize actions are handled explicitly.
2. Existing block reuse path is not a truthiness shortcut.
3. No fallback to creating a duplicate block.

---

## 12. Phase R13.2 - Stage7ExceptionHandlerCommandRepairSlice

### Goal

Move handler command decision authority into a Stage 7 repair slice.

### Editable Scope

Allowed additions:

```text
src/nl2spl/compiler/spl_editing/stage_slices/stage7/
  __init__.py
  exception_handler_command.py
  command_intent_plan.py
```

Allowed modifications:

```text
src/nl2spl/compiler/spl_editing/materialization/stage7/exception_handler_step.py
src/nl2spl/compiler/spl_editing/handlers/missing_handler/
```

Forbidden in this phase:

```text
No block shape decision in Stage7 slice.
No raw variable names from LLM.
No StepIR from LLM.
No direct consumption of RepairDirective.selected_ref_hints.
```

### Implementation Notes

Stage7 slice input:

```text
handler_block_ref from Stage5 slice
RepairDirective
ConstructRepairIntent.selected_ref_ids
resolved selected refs
existing WorkerStepPlanIR
Stage7 command policy
step id allocator
```

Typed plan:

```text
CommandIntentPlan:
  command_family: REQUEST_INPUT | DISPLAY_MESSAGE | GENERAL_COMMAND
  user_facing_text
  selected_ref_ids
  output_intent
  rationale
```

Stage7 slice behavior:

```text
- No-user-advice path: minimal command policy.
- User directive path: constrained typed-plan generation.
- Inputs and outputs come only from resolved refs or declared allocator policy.
- Final StepIR is created by Stage7 slice materializer, not LLM.
```

Directive failure behavior:

```text
If a user directive clearly requests a supported family such as REQUEST_INPUT,
but refs or policy are insufficient to produce that family legally, preview must
fail with an actionable reason or ask the user to explicitly choose the minimal
fallback policy. It must not silently fall back to GENERAL_COMMAND.
```

`Stage7ExceptionHandlerStepMaterializer` downgrade boundary continues to apply:
R13+ logic must route through Stage5/Stage7 StageSliceResult rather than letting
that legacy materializer own block + command policy.

### Test Plan

1. Minimal default creates a simple command.
2. Directive-driven path can select REQUEST_INPUT only through typed plan validation.
3. Raw LLM `inputs` / `outputs` are rejected.
4. Unknown selected ref id is rejected.
5. Generated StepIR has materialization authority and evidence metadata.
6. Generated StepIR references the Stage5 handler block.
7. Unsupported directive path fails with an actionable reason or requires explicit minimal fallback confirmation.
8. Legacy materializer cannot bypass StageSliceResult in the R13+ path.

### Acceptance Criteria

1. Stage7 owns handler command shape.
2. Stage7 consumes only validated selected refs.
3. Existing `Stage7ExceptionHandlerStepMaterializer` no longer hardcodes both block and command shape as a single unit.
4. Tests cover minimal and directive-driven paths.
5. No silent fallback to `GENERAL_COMMAND` when a directive requested another supported command family.

### PM Review Checklist

1. No prompt contains answer-shaped examples for missing_handler.
2. No StepIR-shaped LLM payload schema exists.
3. No hidden fallback to `GENERAL_COMMAND` when directive requested a different supported family.

---

## 13. Phase R13.3 - missing_handler Preview, Apply, and Lane B E2E

### Goal

Close missing_handler end-to-end through preview, confirmation, apply, Lane B replay, and verification.

### Editable Scope

Allowed modifications:

```text
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/preview/service.py
src/nl2spl/compiler/spl_editing/materialization/service.py
src/nl2spl/compiler/spl_editing/verification/
src/nl2spl/compiler/spl_editing/cli.py
examples/output/spl_editing_demo/run_demo.py
```

Forbidden in this phase:

```text
No accepted overlay during preview.
No user confirmation before preview.
No bypass of Lane B.
No final SPL text patching.
```

### Implementation Notes

User flow:

```text
select issue
-> select repair strategy/fix option
-> optional user advice
-> generate preview
-> user confirms preview
-> create RepairEvidencePacket
-> apply materialization
-> Lane B replay
-> show verification result and updated SPL
```

Default confirmation page shows only:

```text
Issue
Proposed fix
Preview
Expected effect
Confirm apply
```

Advanced details can show:

```text
target construct
repair strategy
closure plan
stage slice chain
selected refs
verification lane
```

Default routing requirement:

```text
After this phase, missing_handler default production flow must use the R13+
preview/apply path with Stage5 and Stage7 StageSliceResult. The legacy
Stage7ExceptionHandlerStepMaterializer may remain only as an explicitly isolated
compatibility adapter and must not be reachable from the default CLI/demo/service path.
```

### Test Plan

1. Preview does not increment overlay version.
2. Confirmed apply increments overlay version.
3. Preview stale detection rejects modified directive.
4. Preview stale detection rejects changed selected refs.
5. Lane B accepted for minimal default missing_handler.
6. Lane B accepted for directive-driven missing_handler fixture.
7. User-facing confirmation does not show internal strategy ids by default.
8. Advanced details include audit fields.
9. Default missing_handler path cannot invoke the legacy step materializer directly.
10. StageSliceResult audit fields are present in preview and apply artifacts.

### Acceptance Criteria

1. missing_handler E2E passes with preview/apply lifecycle.
2. User confirms result preview, not backend internals.
3. Verification proves target diagnostic resolved.
4. No new blocking diagnostics.
5. Rendered SPL contains no undefined refs.
6. Default missing_handler flow uses Stage5/Stage7 StageSliceResult rather than the legacy materializer path.

### PM Review Checklist

1. CLI cannot apply without preview id.
2. Service cannot apply stale preview.
3. Confirmation creates RepairEvidencePacket only after user confirmation.
4. E2E uses real snapshot artifacts, not report parsing.

---
## 14. Phase R14 - missing_output_producer Strategy Migration

### Goal

Upgrade `InsertProducerStep` execution into `MaterializeRequiredOutputProducer` construct-level strategy.

### Editable Scope

Allowed modifications:

```text
src/nl2spl/compiler/spl_editing/handlers/missing_output_producer/
src/nl2spl/compiler/spl_editing/materialization/stage7/producer_step.py
src/nl2spl/compiler/spl_editing/stage_slices/stage5/
src/nl2spl/compiler/spl_editing/stage_slices/stage7/
src/nl2spl/compiler/spl_editing/presentation/
```

Forbidden in this phase:

```text
No resurrection of BindExistingProducerStep legacy path unless represented as bind_existing closure node.
No raw input/output names from LLM.
No project_data-style fabricated refs.
```

### Implementation Notes

Strategy:

```text
required_output.materialize_producer.v1
```

Closure:

```text
ensure optional placement_block
materialize producer_command
```

Default policy:

```text
Create one minimal producer command for the required output.
```

Directive-driven policy:

```text
If user advice requires multi-step handling, Stage5 may create or bind a placement block before Stage7 creates producer command.
```

### Test Plan

1. project_data unknown ref is rejected before preview/apply.
2. Valid selected refs produce a producer command.
3. No-input low-context producer records warning if allowed by policy.
4. Existing placement block can be ensured/bound.
5. Stage7 producer command cannot consume raw LLM inputs.
6. ProducerIndex sees target output producer after apply.

### Acceptance Criteria

1. missing_output_producer uses strategy semantics.
2. InsertProducerStep is an execution adapter only.
3. Required output producer E2E passes.
4. No undefined `<REF>` appears in rendered SPL.

### PM Review Checklist

1. No legacy direct binding path reappears.
2. No handler prompt asks LLM for raw inputs/outputs.
3. Producer command shape is stage-slice owned.

---

## 15. Phase R15 - Worker Delegation Closure Migration

### Goal

Upgrade worker delegation repairs into `CompleteWorkerDelegationClosure` with coordinated handoff, invoke command, bindings, and placement.

### Editable Scope

Allowed modifications/additions:

```text
src/nl2spl/compiler/spl_editing/stage_slices/stage3_5/
src/nl2spl/compiler/spl_editing/stage_slices/stage5/
src/nl2spl/compiler/spl_editing/stage_slices/stage7/
src/nl2spl/compiler/spl_editing/materialization/worker_handoff/
src/nl2spl/compiler/spl_editing/handlers/type_or_contract_ambiguity/
```

Forbidden in this phase:

```text
No LLM-created WorkerHandoffIR.
No LLM-created INVOKE_WORKER StepIR.
No raw binding variable names.
No handoff id mismatch between invoke step and handoff contract.
```

### Implementation Notes

Closure nodes:

```text
materialize worker_handoff
materialize invoke_worker_command
bind_existing target_worker
ensure optional placement_block
```

Stage ownership:

```text
Stage3.5 slice:
  worker boundary / handoff contract plan.

Stage5 slice:
  placement block ensure/bind/materialize.

Stage7 slice:
  invoke worker command plan.
```

### Test Plan

1. Handoff contract and invoke step share the same handoff id.
2. Input/output bindings come from SelectableRefSet.
3. Existing target worker can be bound.
4. Placement block can be reused.
5. Lane B rejects mismatched handoff/invoke artifacts.
6. Lane B accepts complete delegation closure.

### Acceptance Criteria

1. Worker delegation E2E accepted for fixture snapshot.
2. No direct handoff or invoke IR generation in patch appliers.
3. Verification catches any closure mismatch.
4. Provenance records directive/evidence/closure lineage.

### PM Review Checklist

1. No new worker/handoff ids are generated by LLM.
2. Binding refs are validated before materialization.
3. Existing worker reuse and new handoff creation are explicit closure actions.

---

## 16. Phase R16 - Legacy Strategy Cleanup and Audit

### Goal

Remove patch-action-as-strategy behavior from default production paths and lock the R12+ architecture with audits.

### Editable Scope

Allowed modifications:

```text
src/nl2spl/compiler/spl_editing/handlers/
src/nl2spl/compiler/spl_editing/patches/
src/nl2spl/compiler/spl_editing/materialization/
src/nl2spl/compiler/spl_editing/presentation/
tests/unit/compiler/spl_editing/
tests/integration/compiler/spl_editing/
```

Forbidden in this phase:

```text
No new legacy compatibility switch.
No hidden fallback to old applier direct mutation.
No default display of patch type as strategy.
```

### Implementation Notes

Static audits:

```text
rg "StepIR\(" src/nl2spl/compiler/spl_editing/patches
rg "BlockIR\(" src/nl2spl/compiler/spl_editing/patches
rg "WorkerHandoffIR\(" src/nl2spl/compiler/spl_editing/patches
rg "payload\.get\(\"inputs\"" src/nl2spl/compiler/spl_editing
rg "payload\.get\(\"outputs\"" src/nl2spl/compiler/spl_editing
rg "diagnostic\.message" src/nl2spl/compiler/spl_editing/materialization src/nl2spl/compiler/spl_editing/stage_slices
rg "Stage7ExceptionHandlerStepMaterializer" src/nl2spl/compiler/spl_editing
```

The final audit must prove that any remaining `Stage7ExceptionHandlerStepMaterializer`
reference is deleted, test-only, or explicitly non-default. It must not be reachable
from default missing_handler CLI/demo/service flow.

Replace or remove any remaining default path that:

```text
- treats patch type as repair strategy.
- lets handler prompt decide final construct shape.
- lets applier build final stage IR.
- consumes unvalidated refs.
```

### Test Plan

1. Static boundary tests for forbidden imports/constructors.
2. No default patch-action strategy presentation.
3. No diagnostic message parsing in materialization/stage slices.
4. No legacy path is reachable in CLI/demo default flow.
5. Legacy exception-handler step materializer is deleted or non-default.
6. Full integration tests for three MVP issue families.

### Acceptance Criteria

1. Static audits pass.
2. Unit and integration suites pass.
3. Demo default flow uses strategy + preview + confirmation + apply.
4. No new skip/xfail.
5. Documentation and tests agree on R12+ terms.
6. Old exception-handler step materializer is removed from default routing or deleted.

### PM Review Checklist

1. Any remaining legacy adapter is explicitly marked non-default or removed.
2. All compatibility shims have removal status.
3. No handler owns final construct shape policy.
4. No materializer owns both block and command policy when stage slices exist.
5. `Stage7ExceptionHandlerStepMaterializer` is deleted or has a documented non-default owner.

---

## 17. Decision Gates

### 17.1 Gate A - Preview LLM Determinism Strategy

Before implementing preview/apply lifecycle, decide one of:

```text
Option A:
  Preview stores exact typed plans and apply promotes them if hashes match.

Option B:
  Apply re-runs generation with deterministic seed/config and requires typed-plan hash match.

Option C:
  Both are supported, but each strategy declares which mode it uses.
```

Recommended: Option C, with missing_handler MVP using Option A first.

Gate acceptance:

```text
1. Decision is documented in preview module docs.
2. Tests cover stale preview for the selected mode.
3. No apply path can silently accept drift.
```

### 17.2 Gate B - Stage Slice LLM Provider Boundary

Before allowing stage slices to call LLM, define:

```text
- constrained generator interface.
- typed-plan schema validation path.
- deterministic config hashing.
- audit log fields.
```

Gate acceptance:

```text
1. Stage slices cannot import generic LLM clients directly.
2. Typed plan schemas reject IR-shaped payloads.
3. Generation config hash is included in preview result.
```

### 17.3 Gate C - Legacy Adapter Removal Timing

Before R16, decide which adapters are removed and which remain as non-default test-only compatibility.

Gate acceptance:

```text
1. Default CLI/demo path uses R12+ strategy for all MVP issue families.
2. Any remaining adapter has explicit owner and removal reason.
3. PM approves non-default compatibility scope.
```

---

## 18. End-to-End Acceptance Scenarios

### 18.1 missing_handler without user advice

```text
1. Load demo snapshot with missing_handler issue.
2. Select CompleteExceptionHandlerAction.
3. Provide no user advice.
4. Generate preview.
5. Confirm preview.
6. Apply.
7. Verify Lane B.
```

Expected:

```text
- Preview shows minimal handler block + command.
- No accepted overlay before confirmation.
- Apply creates RepairEvidencePacket.
- Stage5 ensures/materializes handler block.
- Stage7 materializes handler command.
- Target diagnostic resolved.
- No new blocking diagnostics.
```

### 18.2 missing_handler with user advice

```text
1. Load missing_handler issue for insufficient source access.
2. User advice: ask for access or alternative sources.
3. Generate preview.
4. Confirm preview.
5. Apply.
6. Verify Lane B.
```

Expected:

```text
- Preview reflects user advice.
- Directive remains provisional until confirmation.
- Apply checks preview hashes.
- Rendered SPL reflects confirmed repair result.
```

### 18.3 stale preview rejection

```text
1. Generate preview for missing_handler.
2. Change directive or selected refs before apply.
3. Attempt apply with old preview_id.
```

Expected:

```text
- Apply rejected as stale preview.
- No overlay accepted.
- User must regenerate preview.
```

### 18.4 missing_output_producer rejects hallucinated ref

```text
1. Load required output issue.
2. LLM attempts to select project_data.
3. Intent parser validates selected refs.
```

Expected:

```text
- Unknown ref rejected before preview/apply.
- No StepIR created.
- No overlay accepted.
```

### 18.5 missing_output_producer valid selected refs

Expected:

```text
- Producer command generated from validated refs.
- Required output has producer after verification.
- Rendered SPL contains no undefined <REF>.
```

### 18.6 worker delegation closure

Expected:

```text
- Handoff contract and invoke step are generated through stage slices.
- Handoff id is consistent.
- Bindings come from SelectableRefSet.
- Lane B accepted.
```

---

## 19. PM Master Audit Checklist

For every phase review, check:

1. Does the implementation match the R12+ design doc, not just passing tests?
2. Does the phase preserve R0-R11 safety guarantees?
3. Does any LLM output become IR or raw refs?
4. Does any patch applier direct-mutate final stage IR?
5. Is `RepairDirective` still provisional?
6. Is `RepairEvidencePacket` created only after user confirmation?
7. Are selected refs validated through SelectableRefSet?
8. Does preview avoid accepted overlay?
9. Does apply reject stale preview?
10. Is strategy id the semantic source when present?
11. Is patch type only an execution adapter in R12+ paths?
12. Are closure nodes explicit about ensure / bind_existing / materialize?
13. Do stage slices own construct shape by stage authority?
14. Does verification check closure/materialization consistency?
15. Does any code parse diagnostic.message for primary materialization facts?
16. Does UI default confirmation show user-facing result rather than backend internals?
17. Are advanced details still available for developer/audit use?
18. Are there new skips, xfails, weak assertions, or test-only bypasses?
19. Are legacy shims explicitly isolated or removed?
20. Does demo E2E prove real snapshot behavior?

---

## 20. Recommended Phase Order

```text
R12.0  Baseline Contract Freeze and Gap Lock
R12.1  Strategy and Directive Model Foundation
R12.2  RepairStrategy Registry and Catalog Integration
R12.3  ConstructClosurePlan Planner
Gate A Preview LLM Determinism Strategy
R12.4  Preview / Apply Lifecycle Infrastructure
Gate B Stage Slice LLM Provider Boundary
R12.5  RepairModeStageSlice Substrate
R13.0  missing_handler Strategy Wiring
R13.1  Stage5ExceptionHandlerBlockRepairSlice
R13.2  Stage7ExceptionHandlerCommandRepairSlice
R13.3  missing_handler Preview, Apply, and Lane B E2E
R14    missing_output_producer Strategy Migration
R15    Worker Delegation Closure Migration
Gate C Legacy Adapter Removal Timing
R16    Legacy Strategy Cleanup and Audit
```

Dependency notes:

```text
- R12.1 and R12.2 can start after R12.0.
- R12.4 requires R12.1 and R12.3.
- R12.5 requires R12.4 contracts but can be developed with test fixtures.
- R13.1 and R13.2 require R12.5.
- R13.3 requires R13.0-R13.2.
- R14 should start only after missing_handler proves preview/apply lifecycle.
- R15 should start after R14 unless PM explicitly accepts higher risk.
- R16 must be last.
```
