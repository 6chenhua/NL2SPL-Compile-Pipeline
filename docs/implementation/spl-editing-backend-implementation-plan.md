# SPL Editing Backend Implementation Plan

日期：2026-06-12 (updated 2026-06-13)  
状态：**Backend Core MVP delivered. B10 final audit complete.**  
来源设计：`docs/design/spl_editing_architecture_design_v2.md`

---

## 0. 目标

本计划描述 readiness 完成后，如何实现 AI-assisted SPL Editing 后端 MVP。

MVP 覆盖三类 user-actionable issue：

```text
missing_handler
missing_output_producer
type_or_contract_ambiguity
```

核心闭环：

```text
PipelineResult
  -> EditableIssueExtractor
  -> RepairCatalog lookup by irs_ref + affordance
  -> IssueTargetResolver
  -> RepairContextBuilder
  -> IssueRepairHandler
  -> LLM candidate payloads for allowed patch types only
  -> PatchValidator
  -> RepairSuggestion
  -> user confirmation
  -> RepairPatchApplier
  -> patched artifact snapshot + overlay event
  -> VerificationRunner
  -> accepted / rejected
```

MVP 后端必须做到：

- Editing 只暴露 supported final / authoritative diagnostics。
- Repair strategy 来自 `SlotSpec.repair_affordances` 派生的 `RepairCatalog`。
- LLM 只生成 allowed `patch_type` 的 payload，不选择任意 repair strategy。
- Apply 只修改 stage-level IR artifact snapshot，不直接修改 final SPL text。
- Verification 重新调用 compiler authorities，不绕过 IRS / Gate / ProducerIndex / Renderer。

---

## 1. 非目标

本实施计划不包含：

- UI Diagnostics Console。
- 浏览器 modal 交互。
- 直接编辑 rendered SPL text。
- 让 LLM 生成 arbitrary IR / Python object 后直接替换。
- 在 IRS checker 中实现 repair。
- 在 `construct_registry.py` 中 import patch implementation。
- 让 `diagnostic.kind` 单字段决定 repair strategy。
- full NL replay / long-term rebase。MVP 使用 frozen artifact snapshot + overlay event log。

---

## 2. 已完成前置条件

以下 readiness 在当前本地工作区已完成，本计划直接依赖，不重复实现：

| 能力 | 当前事实 |
|---|---|
| IRS repair metadata | `SlotSpec.repair_affordances` 已存在 |
| Diagnostic reverse lookup | `CompileDiagnostic.metadata["irs_ref"]` / `metadata["authority"]` 已存在 |
| Catalog derivation | `RepairCatalogBuilder.from_construct_registry(...)` 已存在 |
| Producer grouping | `ProducerIssueGrouper` 已提供 primary / alias / context |
| Worker promotion | `WorkerDelegationPromoter` 已提供 selected promoted issue metadata |
| User evidence | `origin="user_confirmed_repair"` 已被 Gate / ProducerIndex / Post-normalize IRS 识别 |

现有 readiness 代码应作为 foundation 保留：

```text
src/nl2spl/compiler/spl_editing/core/catalog.py
src/nl2spl/compiler/spl_editing/issues/grouper.py
src/nl2spl/compiler/spl_editing/issues/promoter.py
```

如果在其他分支、公开 main 或新的 workspace 中执行本计划，必须先运行 B-1 readiness verification gate。B-1 不通过时，不得进入 B0-B10。

---

## 3. 全局编码规则

### 3.1 依赖方向

允许：

```text
spl_editing -> construct_registry / diagnostics / compiler artifacts
spl_editing -> IRS metadata types
spl_editing -> Gate / ProducerIndex / renderer through verification lanes
```

禁止：

```text
construct_registry -> spl_editing implementation
IRS checker -> spl_editing patches / handlers / LLM
patch applier -> final SPL text replacement
LLM handler -> arbitrary patch type outside affordance
```

### 3.2 目录规则

必须遵守设计文档中的目录结构：

```text
src/nl2spl/compiler/spl_editing/
  core/
  issues/
  targets/
  context/
  handlers/
  patches/
  evidence/
  verification/
  storage/
```

新增代码必须按职责放置：

- `core/`：数据模型、service、registry、revision、errors。
- `issues/`：issue extraction、filtering、target ref parsing、grouping orchestration。
- `targets/`：diagnostic target -> editable artifact target resolution。
- `context/`：handler context builders。
- `handlers/`：diagnostic-kind handler + prompt/parser/schema。
- `patches/`：typed patch payload / validator / applier / verifier / preview。
- `verification/`：Lane A/B/C runner、diagnostic diff、common predicates。
- `storage/`：artifact snapshot、editing session、suggestion、overlay stores。
- `evidence/`：user-confirmed repair evidence helpers only; authority recognition already lives outside SPL Editing.

### 3.3 文件增长规则

必须遵守：

```text
1. 一个 patch type 一个目录。
2. 一个 diagnostic kind 一个 handler package。
3. umbrella diagnostic 必须 subtype 化。
4. service / runner / extractor / CLI 不写 diagnostic-kind if-else。
5. patch-specific verifier 不进入通用 VerificationRunner。
6. prompt / parser / schema 跟对应 handler 放一起。
7. SPL preview 只是 preview，不是 apply authority。
```

### 3.4 数据访问规则

- issue extraction 必须通过 `DiagnosticIRSRef + diagnostic.kind + affordance`。
- 不允许通过 `feedback_report.md` 解析 issue。
- 不允许只靠 `diagnostic.kind` 查 patch type。
- `delegation_intent` 只允许作为 `original_semantic_role` / source metadata，不允许作为 `target_kind`。
- producer alias / review-only / non-repairable 语义必须来自 R4 metadata。
- worker/delegation issue exposure 必须来自 selected promoted final diagnostics，不扫描全部 stage-local reports。

---

## 4. 目标目录结构

MVP 完成后，目录应接近：

```text
src/nl2spl/compiler/spl_editing/
  __init__.py

  core/
    __init__.py
    model.py
    catalog.py
    service.py
    registry.py
    revision.py
    errors.py

  issues/
    __init__.py
    extractor.py
    filters.py
    target_ref.py
    grouper.py
    promoter.py

  targets/
    __init__.py
    base.py
    exception_flow.py
    required_output.py
    worker_promotion.py
    worker_handoff.py
    step.py
    handoff.py

  context/
    __init__.py
    registry.py
    base.py
    exception_flow_context.py
    required_output_context.py
    worker_promotion_context.py
    worker_handoff_context.py
    request_input_context.py
    call_api_context.py
    invoke_worker_context.py

  handlers/
    __init__.py
    base.py

    missing_handler/
      __init__.py
      handler.py
      prompt.py
      parser.py
      schemas.py

    missing_output_producer/
      __init__.py
      handler.py
      prompt.py
      parser.py
      schemas.py

    type_or_contract_ambiguity/
      __init__.py
      handler.py
      classifier.py
      context.py
      subhandlers/
        __init__.py
        worker_promotion_contract.py
        worker_handoff_contract.py
        request_input_contract.py
        call_api_contract.py
        invoke_worker_contract.py

  patches/
    __init__.py
    base.py
    registry.py

    add_exception_handler_step/
      __init__.py
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

    insert_producer_step/
      __init__.py
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

    bind_existing_producer_step/
      __init__.py
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

    create_worker_handoff_contract/
      __init__.py
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

    convert_delegation_to_main_flow_step/
      __init__.py
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

    convert_delegation_to_request_input/
      __init__.py
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

  evidence/
    __init__.py
    model.py

  verification/
    __init__.py
    runner.py
    lanes.py
    diagnostic_diff.py
    predicates.py

  storage/
    __init__.py
    artifact_snapshot_store.py
    session_store.py
    suggestion_store.py
    overlay_store.py
```

---

## 5. 阶段依赖图

```text
B-1 readiness verification gate
  -> B0 implementation baseline and registries
  -> B1 core model, revision, storage
  -> B2 editable issue extraction and target resolution
  -> B3 context builders and suggestion handler framework
  -> B4 patch framework and verification runner
  -> B4.5 Lane B harness proof
  -> B5 missing_handler repair
  -> B6 missing_output_producer repair
  -> B7a worker/delegation issue grouping proof
  -> B7b ConvertDelegationIntentToMainFlowStep
  -> B7c ConvertDelegationIntentToRequestInput
  -> B7d CreateWorkerHandoffContract
  -> B8 service orchestration
  -> B9 Demo CLI / API MVP
  -> B10 integration, anti-fabrication, docs
```

B-1 证明 readiness 前提真实存在。  
B0-B4 建立共享框架和 Lane A verification。  
B4.5 证明 Lane B 可用，之后才能 auto-apply worker handoff contract。  
B5-B7 实现三类 MVP issue。  
B8-B10 完成可调用闭环与验证。

---

## B-1. Readiness Verification Gate

### 目标

在进入实现前，用测试证明 readiness 前提在当前代码分支真实存在。该阶段不新增业务能力，只做 guardrail。

### 修改范围

优先复用已存在的 readiness tests。必要时新增一个聚合测试文件：

```text
tests/unit/compiler/spl_editing/test_b_minus_1_readiness_gate.py
```

### 任务

- Assert `SlotSpec.repair_affordances` exists and MVP slots declare affordances.
- Assert `RepairCatalogBuilder.from_construct_registry(...)` derives catalog entries.
- Assert `ProducerIssueGrouper` exists and groups `REQUIRED_OUTPUT.producer` / `RESOURCE_CONTRACT_DEMAND.producer`.
- Assert `WorkerDelegationPromoter` exists and emits `selected_promoted_stage_local_irs`.
- Assert `CompileDiagnostic.metadata["irs_ref"]` is emitted and preserved.
- Assert Gate accepts `origin="user_confirmed_repair"`.
- Assert ProducerIndex accepts `origin="user_confirmed_repair"`.
- Assert Post-normalize IRS source evidence accepts `origin="user_confirmed_repair"`.
- Assert `DELEGATION_INTENT` is not an active construct target or repair target.

### 验收

- B-1 tests pass before B0 starts.
- If any readiness test fails, stop and restore readiness before implementing SPL Editing backend.
- No production behavior changes in B-1.

---

## B0. Implementation Baseline and Registry Wiring

### 目标

在新增业务实现前，建立 backend implementation 的入口、registry skeleton 和测试边界。

### 修改范围

```text
src/nl2spl/compiler/spl_editing/core/registry.py
src/nl2spl/compiler/spl_editing/core/errors.py
src/nl2spl/compiler/spl_editing/__init__.py
tests/unit/compiler/spl_editing/test_b0_backend_registry.py
```

### 任务

- 定义 SPL Editing 专用异常：
  - `SPLEditingError`
  - `UnsupportedIssueError`
  - `UnsupportedPatchTypeError`
  - `PatchValidationError`
  - `StaleRevisionError`
  - `VerificationFailedError`
- 定义 runtime registry shell：
  - handler registry
  - target resolver registry
  - context builder registry
  - patch registry
- registry 只保存 service ID -> implementation object / factory。
- registry 初始化不触发 LLM、不读取 run artifact、不修改 IR。
- 明确 readiness-provided registry：
  - `RepairCatalogBuilder`
  - `ProducerIssueGrouper`
  - `WorkerDelegationPromoter`

### 验收

- 可以构建 empty / default runtime registry。
- default registry 不产生 patch side effect。
- `construct_registry.py` 不 import `spl_editing` implementation。
- tests 继续证明 `RepairCatalog` 是 IRS-derived，不是手写 catalog。

---

## B1. Core Model, Revision, and Storage

### 目标

实现 SPL Editing 的核心数据模型、revision token 和 in-memory storage MVP。

### 修改范围

```text
src/nl2spl/compiler/spl_editing/core/model.py
src/nl2spl/compiler/spl_editing/core/revision.py
src/nl2spl/compiler/spl_editing/storage/artifact_snapshot_store.py
src/nl2spl/compiler/spl_editing/storage/session_store.py
src/nl2spl/compiler/spl_editing/storage/suggestion_store.py
src/nl2spl/compiler/spl_editing/storage/overlay_store.py
tests/unit/compiler/spl_editing/test_b1_core_model_storage.py
```

### 任务

- 定义 data model：
  - `EditableIssue`
  - `EditingSession`
  - `RepairTarget`
  - `RepairContext`
  - `RepairSuggestion`
  - `RepairPatch`
  - `RepairEvidence`
  - `VerificationResult`
  - `ArtifactSnapshot`
  - `OverlayEvent`
- 定义 revision token：
  - `compile_run_id`
  - `artifact_snapshot_id`
  - `overlay_version`
- storage MVP 使用 in-memory store 或 existing run output adapter。
- 所有 model 保持 typed dataclass，避免 `dict[str, Any]` 扩散到业务主流程。
- `RepairPatch` 必须包含：
  - `patch_type`
  - `affordance_id`
  - `irs_ref`
  - `target_ref`
  - `artifact_snapshot_id`
  - `overlay_version`
  - `payload`
- `RepairSuggestion` 必须包含 preview text，但 preview 不能成为 apply authority。
- 定义 concrete `ArtifactSnapshot` schema，不允许 patch 在各自实现里随意解析 `intermediate_results`。

Recommended schema:

```python
@dataclass(frozen=True)
class ArtifactSnapshot:
    snapshot_id: str
    compile_run_id: str
    overlay_version: int

    canonical_input: object | None
    spans: tuple[object, ...]
    routes: object | None

    worker_plan: object | None
    worker_flow_plan: object | None
    worker_block_plan: object | None
    worker_step_plan: object | None

    resources: object | None
    worker_scoped_resources: object | None
    symbol_table: object | None

    constraints: tuple[object, ...]
    agent_profile: object | None

    final_worker: object | None
    final_spl: str | None
    compile_diagnostics: tuple[CompileDiagnostic, ...]
    traces: tuple[object, ...] = ()
```

Implementation should replace `object` with existing project IR types where stable imports are available. If a type is not stable yet, keep the field typed narrowly enough for storage and verification adapters, but do not expose raw nested dicts to patch code.

Snapshot rules:

- Base snapshot is immutable.
- Patch applier always works on a deep copy / derived snapshot.
- Patched snapshot stores before/after diagnostic sets or references to them.
- Snapshot must be deterministic serializable for CLI demo fixtures.
- Gate may mutate assembled `WorkerIR`; verification must treat pre-gate and post-gate workers as separate artifacts.
- Access to required artifacts should go through explicit accessors:

```python
snapshot.require_worker_step_plan()
snapshot.require_worker_block_plan()
snapshot.require_worker_plan()
snapshot.require_compile_diagnostics()
```

- Patch appliers should not directly inspect optional fields and hand-roll `None` handling. Missing required artifacts should fail early with typed SPL Editing errors.

### 验收

- stale revision 可被检测。
- overlay version 单调递增。
- suggestion 未 apply 前不修改 artifact snapshot。
- model 可 JSON serialize / deserialize。
- tests 覆盖 empty payload、unknown patch type、stale revision。
- snapshot schema includes all artifacts needed by Lane A and Lane B harnesses.
- patch-specific code reads artifacts through snapshot accessors, not ad hoc `intermediate_results` keys.
- missing required artifact produces a typed error before patch validation / apply mutates anything.

---

## B2. EditableIssueExtractor and Target Resolution

### 目标

从 `PipelineResult.compile_diagnostics` 提取 UI 可展示的 editable issues。

### 修改范围

```text
src/nl2spl/compiler/spl_editing/issues/extractor.py
src/nl2spl/compiler/spl_editing/issues/filters.py
src/nl2spl/compiler/spl_editing/issues/target_ref.py
src/nl2spl/compiler/spl_editing/targets/base.py
src/nl2spl/compiler/spl_editing/targets/exception_flow.py
src/nl2spl/compiler/spl_editing/targets/required_output.py
src/nl2spl/compiler/spl_editing/targets/worker_promotion.py
src/nl2spl/compiler/spl_editing/targets/worker_handoff.py
src/nl2spl/compiler/spl_editing/targets/step.py
src/nl2spl/compiler/spl_editing/targets/handoff.py
tests/unit/compiler/spl_editing/test_b2_editable_issue_extractor.py
tests/unit/compiler/spl_editing/test_b2_target_resolvers.py
```

### 任务

- `EditableIssueExtractor` input：
  - compile diagnostics
  - intermediate artifacts / snapshot handle
  - derived `RepairCatalog`
- Filter conditions：
  - `metadata["irs_ref"]` exists
  - authoritative source is accepted
  - repair affordance exists
  - `repairability == editable`
  - `issue_role == primary` when grouped
  - supported handler exists
- Accepted authorities:
  - `post_normalize_irs`
  - `producer_index`
  - `producer_index_backed_irs`
  - `selected_promoted_stage_local_irs`
- Exclude:
  - `route_refinement_corrected`
  - validation warning
  - ConstructPlan warning
  - `review_only`
  - `non_repairable`
  - alias / context diagnostics as primary UI issue
- Apply R4/R5 grouping metadata:
  - `issue_group_id`
  - `primary_diagnostic_id`
  - `related_diagnostic_ids`
  - `issue_role`
  - `repairability`
- Implement target resolvers selected by affordance / catalog entry, not by hard-coded service if-else.
- MVP-required target resolvers:
  - `EXCEPTION_FLOW.handler_action`
  - `REQUIRED_OUTPUT.producer`
  - `WORKER_PROMOTION.*`
  - `WORKER_HANDOFF.*`
- Stub-allowed target resolvers:
  - `REQUEST_INPUT.value_target`
  - `CALL_API.integration_evidence`
  - `INVOKE_WORKER.*`
- Stub-allowed resolvers may return `unsupported_for_mvp` / `suggestion_only` until corresponding patch family is implemented. They must not block B5/B6/B7.

### 验收

- Only three MVP issue families are exposed.
- Same diagnostic kind from different construct slots maps to different affordance entries.
- Producer alias diagnostics do not create duplicate editable issue.
- `WORKER_PROMOTION` multi-slot group becomes one issue.
- `delegation_intent` does not appear as target kind.
- No extraction from `feedback_report.md`.
- MVP can proceed even if REQUEST_INPUT / CALL_API / INVOKE_WORKER non-demo subtype resolvers are only stubs.

---

## B3. Context Builders and Suggestion Handler Framework

### 目标

实现 `Fix with AI` 的后端 suggestion generation 框架，让 LLM 只能在 allowed patch type 范围内生成 payload。

### 修改范围

```text
src/nl2spl/compiler/spl_editing/context/base.py
src/nl2spl/compiler/spl_editing/context/registry.py
src/nl2spl/compiler/spl_editing/context/exception_flow_context.py
src/nl2spl/compiler/spl_editing/context/required_output_context.py
src/nl2spl/compiler/spl_editing/context/worker_promotion_context.py
src/nl2spl/compiler/spl_editing/context/worker_handoff_context.py
src/nl2spl/compiler/spl_editing/context/request_input_context.py
src/nl2spl/compiler/spl_editing/context/call_api_context.py
src/nl2spl/compiler/spl_editing/context/invoke_worker_context.py
src/nl2spl/compiler/spl_editing/handlers/base.py
src/nl2spl/compiler/spl_editing/handlers/missing_handler/
src/nl2spl/compiler/spl_editing/handlers/missing_output_producer/
src/nl2spl/compiler/spl_editing/handlers/type_or_contract_ambiguity/
tests/unit/compiler/spl_editing/test_b3_context_builders.py
tests/unit/compiler/spl_editing/test_b3_repair_handlers.py
```

### 任务

- Define `RepairContextBuilder` interface.
- Define `IssueRepairHandler` interface:
  - input: `EditableIssue`, `RepairTarget`, `RepairContext`, catalog entries, user instruction
  - output: candidate `RepairPatch` payloads wrapped in `RepairSuggestion`
- Define LLM adapter boundary:
  - implementation can be stubbed in unit tests
  - adapter wraps the existing project LLM client instead of creating a parallel LLM stack
  - use JSON/schema-constrained output where supported
  - default deterministic settings: temperature 0 or equivalent
  - prompt must include allowed patch types from catalog
  - parser must reject patch types not in affordance
- Define shared `SuggestionPolicy`:
  - `max_suggestions = 3`
  - `min_suggestions = 1`
  - suggestions are "up to 3", not exactly 3
  - fallback template suggestions are allowed only when handler can validate a safe typed payload
- Parser flow must be:

```text
raw LLM output
  -> parse JSON/schema
  -> reject unsupported patch_type against allowed_patch_types
  -> validate payload schema
  -> run patch validator preconditions
```

- Keep prompt/parser/schema inside corresponding handler package.
- `type_or_contract_ambiguity` handler must subtype by `construct_type + slot_name + affordance_id`, not by free-form classifier alone.
- Worker/delegation subtype handlers:
  - `worker_promotion_contract.py`
  - `worker_handoff_contract.py`
  - optional request/call/invoke subhandlers for later expansion.

### 验收

- LLM output with unsupported `patch_type` is rejected before validation.
- Handler can produce up to 3 suggestions for supported issue.
- Suggestion includes human-readable explanation and preview, but patch payload remains typed authority.
- No handler writes IR.
- No handler imports patch applier.
- Unsupported patch type is rejected before applier lookup.

---

## B4. Patch Framework and Verification Runner

### 目标

实现 typed patch 的通用接口、registry、validator/applier/verifier 调度和 verification lane 框架。

### 修改范围

```text
src/nl2spl/compiler/spl_editing/patches/base.py
src/nl2spl/compiler/spl_editing/patches/registry.py
src/nl2spl/compiler/spl_editing/verification/runner.py
src/nl2spl/compiler/spl_editing/verification/lanes.py
src/nl2spl/compiler/spl_editing/verification/diagnostic_diff.py
src/nl2spl/compiler/spl_editing/verification/predicates.py
tests/unit/compiler/spl_editing/test_b4_patch_registry.py
tests/unit/compiler/spl_editing/test_b4_verification_runner.py
```

### 任务

- Define interfaces:
  - `PatchPayload`
  - `PatchValidator`
  - `PatchApplier`
  - `PatchPreviewer`
  - `PatchVerifier`
- Patch registry maps `patch_type` string -> implementation bundle.
- Validator must check:
  - patch type allowed by affordance
  - target matches `irs_ref`
  - base revision not stale
  - required evidence kind is user confirmed
  - payload schema valid
- Applier must:
  - apply to artifact snapshot copy
  - write `metadata.origin = "user_confirmed_repair"` where executable behavior is introduced
  - append overlay event
  - not mutate base snapshot
- Verification runner chooses lane:
  - Lane A: assembler / Stage 10 replay on patched worker/block/step artifacts
  - Lane B: normalizer / Stage 9.5+ replay on worker plan / handoff / resource artifacts
  - Lane C: future full NL replay; not required for MVP
- Lane A invocation contract must define:
  - required input artifacts: worker flow/block/step plans plus any resources/profile required by assembler
  - assembled pre-gate `WorkerIR`
  - gated `WorkerIR`
  - post-normalize IRS diagnostics
  - gate diagnostics
  - render diagnostics
  - consolidated diagnostics
  - rendered SPL
- Gate may filter/mutate worker structures. Verification must deep-copy assembled `WorkerIR` and keep `pre_gate_worker` separate from `gated_worker`.
- Verification result should expose:

```text
VerificationArtifacts:
  pre_gate_worker
  gated_worker
  render_info
  post_normalize_diagnostics
  gate_diagnostics
  render_diagnostics
  consolidated_diagnostics
rendered_spl
```

- Define replay adapters so patch verifiers do not call compiler stages directly:

```python
class LaneAReplayAdapter:
    def replay(self, snapshot: ArtifactSnapshot) -> VerificationArtifacts: ...

class LaneBReplayAdapter:
    def replay(self, snapshot: ArtifactSnapshot) -> VerificationArtifacts: ...
```

- `VerificationRunner` owns adapter invocation. Patch-specific verifiers consume only `VerificationArtifacts` and patch context.

- `DiagnosticDiff` compares before/after diagnostics:
  - target diagnostic resolved
  - no new blocking diagnostic regression
  - related diagnostics resolved or explicitly accepted by patch-specific verifier
- Patch-specific verifier remains inside patch directory.

### 验收

- Unsupported patch type rejected.
- Stale revision rejected.
- Patch cannot directly edit rendered SPL.
- Generic runner does not know patch-specific success rules.
- Lane A/B dispatch is explicit.
- Lane A unchanged snapshot replay is deterministic before B5 starts.
- Patch verifiers do not call Stage 10 / Stage 9.5 / Gate / Renderer directly.

---

## B4.5. Lane B Harness Proof

### 目标

在 auto-apply worker handoff contract 前，证明 Lane B replay 可以稳定处理 worker plan / handoff / resource artifact changes。

### 修改范围

```text
src/nl2spl/compiler/spl_editing/verification/lanes.py
src/nl2spl/compiler/spl_editing/verification/runner.py
tests/unit/compiler/spl_editing/test_b4_5_lane_b_harness.py
tests/integration/compiler/spl_editing/test_b4_5_lane_b_replay.py
```

### 任务

- Define Lane B input artifact contract.
- Define which normalizer / Stage 9.5+ entrypoint is called.
- Prove an unchanged snapshot replay produces equivalent:
  - WorkerIR
  - diagnostics
  - rendered SPL
- Define how patched worker handoff artifacts are reassembled.
- Define how Lane B output feeds Post-normalize IRS, Gate, Renderer, and DiagnosticDiff.

### 验收

- Given an unchanged artifact snapshot, Lane B replay is equivalent to baseline.
- Lane B does not mutate base snapshot.
- Lane B returns `VerificationArtifacts` with rendered SPL and diagnostics.
- If this proof fails, `CreateWorkerHandoffContract` remains suggestion-only or is postponed; it must not be auto-applied.

---

## B5. missing_handler Repair

### 目标

实现 `EXCEPTION_FLOW.handler_action` 的最小完整闭环。

### 修改范围

```text
src/nl2spl/compiler/spl_editing/handlers/missing_handler/
src/nl2spl/compiler/spl_editing/context/exception_flow_context.py
src/nl2spl/compiler/spl_editing/targets/exception_flow.py
src/nl2spl/compiler/spl_editing/patches/add_exception_handler_step/
tests/unit/compiler/spl_editing/test_b5_missing_handler_patch.py
tests/integration/compiler/spl_editing/test_b5_missing_handler_flow.py
```

### 任务

- Context builder gathers:
  - target worker
  - exception flow id
  - condition / failure mode
  - nearby source spans
  - existing steps/blocks
- Handler suggests `AddExceptionHandlerStep`.
- Payload:
  - `worker_id`
  - `exception_flow_id`
  - `handler_text`
  - `command_type`
  - `inputs`
  - `outputs`
  - `insertion_policy`
- Validator:
  - target exception flow exists
  - `handler_action` currently missing
  - command type is allowed
  - patch type matches `exception_flow.add_handler_step`
  - Step id / command index generation follows existing stage naming rules and avoids collisions
  - `REQUEST_INPUT` handler has value target / outputs
  - `DISPLAY_MESSAGE` handler does not create outputs
  - `GENERAL_COMMAND` outputs are explicit when present
- Applier:
  - ensures exception-flow-local sequential block exists
  - creates block id / block ordering according to existing `WorkerBlockPlanIR` structure
  - creates StepIR
  - sets `flow_ref` / `block_ref`
  - writes `metadata.origin = "user_confirmed_repair"`
  - writes `repair_patch_id`, `related_diagnostic_id`, `user_text`, and `related_source_span_ids` when available
  - updates WorkerStepPlanIR / WorkerBlockPlanIR snapshot
- Verifier:
  - Lane A
  - original `missing_handler` disappears
  - target exception flow has renderable handler step
  - `flow_ref` equals target exception flow id
  - `block_ref` belongs to target exception flow
  - handler step survives Gate
  - rendered SPL contains non-empty exception flow body

### 验收

- Patch creates no arbitrary SPL text replacement.
- Unconfirmed suggestion does not affect SPL.
- Applied patch makes exception flow non-empty.
- Gate accepts user-confirmed handler step.
- Duplicate step id / command index is rejected.

---

## B6. missing_output_producer Repair

### 目标

实现 required output producer 修复，支持新增 producer step 或绑定已有 producer step。

### 修改范围

```text
src/nl2spl/compiler/spl_editing/handlers/missing_output_producer/
src/nl2spl/compiler/spl_editing/context/required_output_context.py
src/nl2spl/compiler/spl_editing/targets/required_output.py
src/nl2spl/compiler/spl_editing/patches/insert_producer_step/
src/nl2spl/compiler/spl_editing/patches/bind_existing_producer_step/
tests/unit/compiler/spl_editing/test_b6_missing_output_producer_patch.py
tests/integration/compiler/spl_editing/test_b6_missing_output_producer_flow.py
```

### 任务

- Context builder gathers:
  - required output name / type / contract
  - producer-adjacent related diagnostics
  - candidate existing steps
  - resource contract demand aliases
- Handler suggests:
  - `InsertProducerStep`
  - `BindExistingProducerStep`
- `InsertProducerStep` applier:
  - creates user-confirmed StepIR
  - sets output binding
  - places in main flow or selected block
  - does not directly modify ProducerIndex
  - MVP allowed command types are `GENERAL_COMMAND` and `REQUEST_INPUT`
  - `CALL_API` is allowed only if context proves existing API declaration / integration evidence and the corresponding affordance permits it
- `BindExistingProducerStep` applier:
  - validates existing step is renderable
  - updates output binding / result binding
  - records user-confirmed binding provenance
  - does not introduce new executable behavior
- If per-output metadata is unavailable, record output binding provenance under step metadata:

```python
metadata["repair_output_bindings"] = {
    output_name: {
        "repair_patch_id": patch_id,
        "related_diagnostic_id": diagnostic_id,
        "user_text": user_text,
    }
}
```

- Verifier:
  - Lane A
  - ProducerIndex recognizes producer after replay
  - original primary `missing_output_producer` resolved
  - alias/context diagnostics handled through diagnostic diff

### 验收

- `RESOURCE_CONTRACT_DEMAND.producer` alias does not become duplicate editable issue.
- `unspecified_output_missing_producer` remains review-only.
- Patch cannot mark required output optional.
- Patch cannot fake ProducerIndex.
- Generic missing-output repair cannot create `CALL_API` without API contract evidence.
- Producer step with `origin=user_confirmed_repair` is recognized.

---

## B7. type_or_contract_ambiguity Worker/Delegation Repair

### 目标

实现 MVP demo subtype：delegation-intent-sourced `WORKER_PROMOTION` / `WORKER_HANDOFF` contract gap。

该阶段必须拆细。`CreateWorkerHandoffContract` 不得和两个 conversion patch 以同等复杂度处理；它依赖 B4.5 Lane B proof。

### Shared 修改范围

```text
src/nl2spl/compiler/spl_editing/handlers/type_or_contract_ambiguity/
src/nl2spl/compiler/spl_editing/context/worker_promotion_context.py
src/nl2spl/compiler/spl_editing/context/worker_handoff_context.py
src/nl2spl/compiler/spl_editing/targets/worker_promotion.py
src/nl2spl/compiler/spl_editing/targets/worker_handoff.py
src/nl2spl/compiler/spl_editing/core/model.py
tests/unit/compiler/spl_editing/test_b7_type_contract_worker_patch.py
```

### Shared 任务

- Subtype resolution must use:
  - `irs_ref.construct_type`
  - `irs_ref.slot_name`
  - `affordance_id`
  - `metadata["original_semantic_role"]`
- Do not use `DELEGATION_INTENT` as construct or target.
- Context builder gathers:
  - worker promotion candidate id
  - parent worker
  - proposed child worker name
  - missing input/output contract slots
  - invocation point
  - source signal id when available
- Define `RepairResolutionMarker`:

```python
@dataclass(frozen=True)
class RepairResolutionMarker:
    marker_id: str
    resolved_diagnostic_id: str
    original_target_ref: str
    resolution_kind: Literal[
        "converted_to_main_flow_step",
        "converted_to_request_input",
        "handoff_contract_created",
    ]
    repair_patch_id: str
    applies_to_issue_group_id: str | None
```

- MVP marker storage:
  - marker is persisted in overlay event and patched snapshot metadata.
  - patch-specific verifier and `DiagnosticDiff` consume marker.
  - long-term `DiagnosticConsolidator` marker awareness is optional and not required for MVP.
- Define group-level success rules:
  - `CreateWorkerHandoffContract` should resolve all relevant contract diagnostics in the group.
  - `ConvertDelegationIntentToMainFlowStep` may resolve the entire group through marker.
  - `ConvertDelegationIntentToRequestInput` may resolve the entire group through marker.
- Marker acceptance rules:
  - `marker.resolved_diagnostic_id` must be in `issue.related_diagnostic_ids`.
  - `marker.applies_to_issue_group_id` must equal `issue.issue_group_id` when group id exists.
  - marker must match the original target ref.
  - patch-specific positive artifact effect must exist.
  - marker cannot suppress unrelated `type_or_contract_ambiguity`.
  - marker cannot suppress newly introduced blocking diagnostics.

### B7a. Worker/delegation issue grouping proof

任务：

- Prove selected promoted `WORKER_PROMOTION` multi-slot diagnostics are grouped as one editable issue.
- Prove primary is stable, preferably `promotion_input_contract`.
- Prove catalog lookup resolves `worker_promotion.resolve_contract`.

验收：

- One UI issue for one worker promotion candidate.
- Related diagnostic ids include all same-group promotion slot diagnostics.
- `delegation_intent` appears only as source metadata.

### B7b. ConvertDelegationIntentToMainFlowStep

修改范围：

```text
src/nl2spl/compiler/spl_editing/patches/convert_delegation_to_main_flow_step/
tests/unit/compiler/spl_editing/test_b7b_convert_delegation_to_main_flow_step.py
```

任务：

- Create main-flow user-confirmed StepIR.
- Record marker `converted_to_main_flow_step`.
- Use Lane A verification.
- Do not create worker handoff or invoke worker.

验收：

- Step survives Gate.
- Marker resolves original worker promotion/handoff ambiguity group.
- No new blocking diagnostic regression.

### B7c. ConvertDelegationIntentToRequestInput

修改范围：

```text
src/nl2spl/compiler/spl_editing/patches/convert_delegation_to_request_input/
tests/unit/compiler/spl_editing/test_b7c_convert_delegation_to_request_input.py
```

任务：

- Create REQUEST_INPUT StepIR with explicit value target.
- Record marker `converted_to_request_input`.
- Use Lane A verification.

验收：

- REQUEST_INPUT has value target.
- Step survives Gate.
- Marker resolves original worker promotion/handoff ambiguity group.
- No new blocking diagnostic regression.

### B7d. CreateWorkerHandoffContract

修改范围：

```text
src/nl2spl/compiler/spl_editing/patches/create_worker_handoff_contract/
tests/unit/compiler/spl_editing/test_b7d_create_worker_handoff_contract.py
tests/integration/compiler/spl_editing/test_b7d_create_worker_handoff_contract_flow.py
```

任务：

- Only enable auto-apply if B4.5 Lane B harness proof passes.
- Update WorkerPlanIR / WorkerHandoffIR snapshot.
- Fill input bindings, output bindings, invocation point, and result handoff.
- Record marker `handoff_contract_created`.
- Use Lane B verification.

验收：

- Handoff contract is complete enough for downstream worker/invoke materialization.
- WorkerHandoffIR has parent worker and child worker target identity, or the project-equivalent target fields.
- Input bindings and output bindings are non-empty when corresponding slots were missing.
- Invocation point resolves to an existing parent worker flow/block/step location.
- Result handoff maps child output to parent required output or named continuation.
- Lane B output contains materialized INVOKE_WORKER only through normalizer / compiler replay, not direct applier injection.
- Patch cannot create INVOKE_WORKER without complete handoff contract.
- Group-level diagnostics are resolved or accepted by marker-aware verifier.
- If Lane B proof is not available, patch remains suggestion-only.

---

## B8. Service Orchestration

### 目标

实现可被 CLI / API 调用的 backend service。

### 修改范围

```text
src/nl2spl/compiler/spl_editing/core/service.py
tests/unit/compiler/spl_editing/test_b8_editing_service.py
```

### 任务

- Define service methods:
  - `register_compile_result(result: PipelineResult) -> run_id`
  - `list_editable_issues(run_id: str)`
  - `list_editable_issues_from_result(result: PipelineResult)`
  - `create_session(run_id, issue_id)`
  - `generate_suggestions(session_id, instruction)`
  - `apply_suggestion(session_id, suggestion_id)`
  - `verify_session(session_id)`
- Define `RunOutputLoader` only if CLI needs `--run <directory>`:
  - must load structured diagnostics and artifacts.
  - must not parse `feedback_report.md` as source of editable issues.
  - may render report text for display only.
- Service orchestration must use registries:
  - no direct diagnostic-kind branch in service
  - no direct patch-specific verifier in service
- Stale revision check before apply.
- Persist:
  - artifact snapshot
  - overlay event
  - suggestion
  - verification result
- Enforce user confirmation:
  - only `apply_suggestion` can write user-confirmed repair evidence
  - `generate_suggestions` cannot mutate artifacts

### 验收

- List -> suggest -> apply -> verify works with stub LLM and in-memory stores.
- Service can register a `PipelineResult` directly and list issues without filesystem run output.
- Directory-based run loading fails clearly if structured artifacts are missing.
- Applying same stale suggestion twice is rejected.
- Suggestion generation does not change SPL output.
- Service does not contain patch-specific success logic.

---

## B9. Demo CLI / API MVP

### 目标

提供 minimal backend entry points for demo and future UI integration。

B9 required deliverable 是 Demo CLI。HTTP API 在 MVP 中只要求定义 service-level request/response schema；实际 HTTP server / router 是 optional。

其中 Demo CLI 是明确交付物。它用于在没有 UI 的情况下展示未来 Diagnostics Console / Fix with AI 所需的核心能力：

```text
1. 运行或读取 NL2SPL compile result。
2. 在终端列出所有 user-facing editable issues。
3. 用户选择 issue 编号。
4. CLI 触发 suggestion generation。
5. 返回一段描述性文本 + up to 3 条可 apply 的 SPL construct / IR preview。
6. 用户选择 suggestion 编号并确认 apply。
7. 后端应用 typed RepairPatch、执行 verification。
8. CLI 输出修改后的完整 SPL。
```

注意：CLI 展示的 SPL construct / IR 是 preview。真正 apply 的 authority 仍然是 typed `RepairPatch` payload + deterministic applier。

### 修改范围

候选位置需要按现有项目 CLI / API 约定落位。若项目已有 CLI framework，应挂载在现有入口；否则先建立 internal command module。

```text
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/cli.py              # only if project has matching CLI convention
tests/unit/compiler/spl_editing/test_b9_cli_contract.py
tests/integration/compiler/spl_editing/test_b9_demo_cli_flow.py
```

Service-level API contract:

```text
GET  /runs/{run_id}/editable-issues
POST /runs/{run_id}/issues/{issue_id}/suggestions
POST /editing-sessions/{session_id}/apply
GET  /editing-sessions/{session_id}/verification
```

These route shapes are contract placeholders for future UI integration. Implementing an HTTP server is optional in MVP unless the project already has a matching web/API framework.

CLI contract:

```bash
spl-edit issues --run examples/output/demo
spl-edit suggest --run examples/output/demo --diagnostic irs_xxx --instruction "..."
spl-edit apply --session edit_001 --suggestion sug_001
spl-edit verify --session edit_001
```

Interactive demo contract:

```bash
spl-edit demo --run examples/output/demo
```

Expected terminal flow:

```text
Editable issues:
  [1] missing_handler
      target: EXCEPTION_FLOW.handler_action
      summary: Exception flow has a condition but no handler step.
      repairability: editable

  [2] missing_output_producer
      target: REQUIRED_OUTPUT.producer
      summary: Required output has no renderable producer.
      repairability: editable

Select issue number: 1

AI repair suggestions:
  [1] Add a REQUEST_INPUT handler asking the user for the approved template.
      Preview:
        REQUEST_INPUT ...

  [2] Add a DISPLAY_MESSAGE handler explaining the fallback.
      Preview:
        DISPLAY_MESSAGE ...

  [3] Add a GENERAL_COMMAND handler that records the fallback action.
      Preview:
        GENERAL_COMMAND ...

Apply suggestion number: 1
Confirm apply? y

Verification:
  status: accepted
  lane: A
  resolved diagnostics: [...]
  new blocking diagnostics: none

Updated SPL:
  <full rendered SPL after patched artifact snapshot>
```

### 任务

- Define request/response schema for each endpoint/command.
- Implement interactive `spl-edit demo` flow as thin orchestration over service methods.
- Demo CLI supports two structured input modes:
  - direct compile invocation, if existing compiler CLI can return `PipelineResult`.
  - `--run <directory>` only when `RunOutputLoader` can load structured artifacts.
- Demo CLI must fail fast if only markdown/text reports exist and no structured artifacts are available for apply.
- Responses must expose:
  - `issue_id`
  - stable terminal issue number
  - primary diagnostic summary
  - related diagnostics
  - affordance ids
  - suggestions and previews
  - verification result
  - updated full SPL after successful apply
- Responses must not expose raw internal object graphs.
- API/CLI must not apply without explicit user confirmation action.
- Demo CLI must distinguish:
  - issue list output
  - suggestion description
  - preview SPL construct / IR
  - apply confirmation
  - verification result
  - final rendered SPL
- Demo CLI must support non-interactive fixtures for tests.

### 验收

- CLI/API can drive all three MVP issue families in tests or fixture runs.
- `spl-edit demo` can list user-facing editable issues and let user select one by number.
- `spl-edit demo` returns up to 3 applyable suggestions when the handler can produce them.
- Each suggestion has descriptive text and preview, but apply uses typed patch payload.
- Applying a suggestion renders and prints the full patched SPL.
- Cancelling before confirmation leaves artifacts unchanged.
- Output is stable and UI-friendly.
- Errors are typed and actionable.

---

## B10. Integration, Anti-fabrication, and Documentation

### 目标

完成 end-to-end verification, anti-fabrication tests, and implementation docs update。

### 修改范围

```text
tests/integration/compiler/spl_editing/
docs/design/spl_editing_architecture_design_v2.md       # only if implementation requires design note update
docs/implementation/spl-editing-backend-implementation-plan.md
```

### 任务

- Add integration tests:
  - missing_handler full flow
  - missing_output_producer full flow
  - type_or_contract_ambiguity worker/delegation full flow
- Add anti-fabrication tests:
  - unconfirmed AI suggestions do not affect SPL
  - patch cannot create CALL_API without API contract evidence
  - patch cannot create INVOKE_WORKER without handoff contract
  - patch cannot silently mark required output optional
  - patch cannot modify final SPL text directly
  - patch cannot bypass Gate / IRS / ProducerIndex
- Add regression tests:
  - no new blocking diagnostic regression
  - no duplicate producer issue
  - no `DELEGATION_INTENT` construct target
  - no handler-generated unsupported patch type
- Update docs only after code behavior is stable.

### 验收

- MVP acceptance criteria from design section 15 all pass.
- Readiness tests still pass.
- SPL Editing tests pass.
- Full relevant compiler test subset passes.

---

## 6. Testing Plan

### Unit test groups

```text
test_b_minus_1_readiness_gate.py
test_b0_backend_registry.py
test_b1_core_model_storage.py
test_b2_editable_issue_extractor.py
test_b2_target_resolvers.py
test_b3_context_builders.py
test_b3_repair_handlers.py
test_b4_patch_registry.py
test_b4_verification_runner.py
test_b4_5_lane_b_harness.py
test_b5_missing_handler_patch.py
test_b6_missing_output_producer_patch.py
test_b7a_worker_delegation_grouping.py
test_b7b_convert_delegation_to_main_flow_step.py
test_b7c_convert_delegation_to_request_input.py
test_b7d_create_worker_handoff_contract.py
test_b8_editing_service.py
test_b9_cli_contract.py
```

### Integration test groups

```text
tests/integration/compiler/spl_editing/test_missing_handler_flow.py
tests/integration/compiler/spl_editing/test_missing_output_producer_flow.py
tests/integration/compiler/spl_editing/test_lane_b_replay.py
tests/integration/compiler/spl_editing/test_type_contract_worker_flow.py
tests/integration/compiler/spl_editing/test_anti_fabrication.py
```

### Readiness regression gate

Run before SPL Editing backend tests:

```text
tests/unit/compiler/spl_editing/test_r0_readiness_baseline.py
tests/unit/compiler/spl_editing/test_r1_diagnostic_metadata.py
tests/unit/compiler/spl_editing/test_r2_repair_affordance.py
tests/unit/compiler/spl_editing/test_r3_repair_catalog.py
tests/unit/compiler/spl_editing/test_r4_producer_grouping.py
tests/unit/compiler/spl_editing/test_r5_worker_promotion.py
```

Minimum facts to protect:

- `SlotSpec.repair_affordances` exists and default registry declares MVP affordances.
- `CompileDiagnostic.metadata["irs_ref"]` is emitted and preserved.
- `RepairCatalogBuilder` derives catalog.
- `ProducerIssueGrouper` groups required output / resource contract demand.
- `WorkerDelegationPromoter` emits selected promoted diagnostics.
- Gate / ProducerIndex / Post-normalize IRS accept `origin="user_confirmed_repair"`.
- `DELEGATION_INTENT` is not a construct target.

### Recommended commands

```bash
.venv/Scripts/python.exe -m pytest tests/unit/compiler/spl_editing -q -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/integration/compiler/spl_editing -q -p no:cacheprovider
```

On Windows PowerShell:

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\compiler\spl_editing -q -p no:cacheprovider
.venv\Scripts\python.exe -m pytest tests\integration\compiler\spl_editing -q -p no:cacheprovider
```

---

## 7. MVP Acceptance Checklist

MVP 完成时必须全部满足：

- Editing 只暴露三类 repairable issue，不暴露内部 compiler health diagnostics。
- issue extraction 通过 `irs_ref + affordance` 判断 repairability，不通过 `diagnostic.kind` 单字段判断。
- `RepairCatalog` 从 IRS registry 派生，不维护平行手写 truth source。
- 三类 issue 都能生成 AI suggestions。
- 三类 issue 都至少有一个 typed patch 可以 apply。
- LLM 不输出 arbitrary IR，不直接输出 final SPL patch。
- apply 后产生 patched artifact snapshot 和 overlay record。
- verification 通过 Lane A / Lane B 明确执行，不默认假设 Stage 9.5 幂等。
- `missing_handler` repair 后 exception flow 不再为空。
- `missing_output_producer` repair 后 ProducerIndex 能识别 producer。
- `type_or_contract_ambiguity` repair 使用 construct slot subtype 和 resolution marker。
- no new blocking diagnostic regression。
- 所有 patch 均可审计、可撤销到上一 artifact snapshot。

---

## 8. Implementation Stop Conditions

遇到以下情况应停止并回到设计确认：

- 需要让 IRS checker 直接生成 repair suggestion。
- 需要在 `construct_registry.py` import patch class。
- 需要通过 `diagnostic.kind` 单字段决定 patch type。
- 需要把 `delegation_intent` 建模为 construct / target kind。
- 需要直接修改 rendered SPL text 才能完成 patch。
- 需要让 unconfirmed AI suggestion 进入 renderable SPL。
- 需要绕过 Gate / ProducerIndex / IRS 才能让 verification pass。
- B-1 readiness gate 未通过但仍继续实现。
- B4 Lane A unchanged replay 未通过但继续实现 apply-capable patches。
- B4.5 Lane B proof 未通过但仍 auto-apply `CreateWorkerHandoffContract`。
- `RepairResolutionMarker` 被用作 generic suppress mechanism，而不是精确匹配原 issue group。

---

## 9. Suggested Milestone Order

推荐提交顺序：

| Milestone | 内容 | 可独立验证 |
|---|---|---|
| M0 | B-1 readiness verification gate | readiness preconditions proven in this branch |
| M1 | B0-B2 issue extraction and MVP target resolution | list issues works |
| M2 | B3 suggestion framework with stub LLM | up to 3 suggestions generated but no apply |
| M3 | B4 patch framework + Lane A harness | fake patch can validate/apply/verify in Lane A |
| M3.5 | B4.5 Lane B harness proof | unchanged snapshot Lane B replay equivalent |
| M4 | B5 missing_handler | first end-to-end apply |
| M5 | B6 missing_output_producer | ProducerIndex-backed apply |
| M6a | B7a-B7c worker/delegation conversion patches | grouped issue can convert to step/request-input |
| M6b | B7d CreateWorkerHandoffContract | auto-apply only if Lane B proof passes |
| M7 | B8-B9 service and Demo CLI/API | interactive terminal demo lists issues, suggests fixes, applies one, prints patched SPL |
| M8 | B10 integration and docs | MVP acceptance |

每个 milestone 都应保持 readiness tests 通过。

---

## 10. Delivery Status (2026-06-13)

### Backend Core MVP — Delivered

| Phase | Status | Tests |
|---|---|---|
| B-1 → B10 | Delivered | 452 passed (unit + integration) |
| R0-R7 readiness | Still passing | ~156 |
| IRS compiler subset | Still passing | 340 passed |

### C1-C6 Compiler-Authority Extensions

| Stage | Status |
|---|---|
| C1 Lane A real replay | ✅ Delivered |
| C2 B9 interactive demo CLI | ✅ Delivered |
| C3 Verification result persistence | ✅ Delivered |
| C4 BindExistingProducerStep via handler | ✅ Delivered |
| C5 Lane B real replay | ✅ Delivered |
| C6a-d CreateWorkerHandoffContract | ✅ Delivered (primitives + context + service) |

### Known Boundaries (not blocking core MVP)

- B7d full handoff semantic repair (input/output bindings, invocation point resolution, result handoff mapping) — minimal path accepted, full semantic hardening deferred
- `BindExistingProducerStep` step selection from full snapshot context — handler currently selects first renderable step
- `CreateWorkerHandoffContract` child_worker_id — context builder requires exactly one child worker
- Lane B real replay normalizer integration — strict validation requires exact step/handoff consistency

### Test Commands

```powershell
# SPL Editing unit tests
python -m pytest tests/unit/compiler/spl_editing -q

# SPL Editing integration tests
python -m pytest tests/integration/compiler/spl_editing -q

# Full SPL Editing suite
python -m pytest tests/unit/compiler/spl_editing tests/integration/compiler/spl_editing -q

# IRS compiler subset
python -m pytest tests/unit/compiler/irs -q
```
