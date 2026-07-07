# SPL Editing Repair Drafting Subsystem 实施计划

本文档严格基于 [`spl_editing_repair_drafting_subsystem_design_zh.md`](spl_editing_repair_drafting_subsystem_design_zh.md) 制定。实施目标是形成 SPL Editing Repair Drafting 通用平台路线：统一承载用户自然语言建议、结构化输入、field inference、draft preview、clarification、provider dispatch、session-scoped draft storage、admission bridge、materialized preview 和多 repair strategy 迁移。

本文档分为两个实施层级：

```text
Release 1 / MVP implementation:
  RD0-RD7。
  落地 RepairDraftingSubsystem substrate + WorkerDelegationInferenceProvider，
  解决 define_child_worker draft-first 交互问题。

Post-MVP / Full Platform Roadmap:
  RD8-RD13。
  在 Provider Migration Freeze 和 Bounded LLM Enablement 后，
  逐步迁移 missing_handler、missing_output_producer、REQUEST_INPUT.value_target、
  bounded LLM、legacy cleanup 和 full platform E2E。
```

下一轮直接执行范围是 RD0-RD7。RD8-RD13 是 gated roadmap，不作为 Release 1 完成条件。

不在本计划范围内：

```text
1. 让 RepairDraftingSubsystem 直接构造 IR / Patch payload / MaterializationPlan。
2. 建立万能 LLM repair compiler。
3. 绕过现有 RepairCatalog / Admission / Materialization / Verification authority。
4. 重写 Worker Delegation v2 closure materialization。
5. 重写 IRS / ConstructRegistry 的 repair affordance 语义。
```

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
RepairCatalog / RepairStrategyOptionSpec
  -> 决定 repair option 是否存在、用户语义是什么

RepairInteractionView
  -> 决定 UI/CLI 如何收集用户输入
  -> 不决定 repair capability

RepairDraftingSubsystem
  -> 组织 UserRepairInput、provider dispatch、field inference、trace、confidence、clarification、DraftPreview
  -> 不 Admission、不 Apply、不 Materialize、不 Verify

RepairInferenceProvider
  -> 按 affordance_id + strategy_id + option_id 理解 strategy-specific 输入
  -> 产出 InferredRepairDraft
  -> 不构造 IR、不写 overlay、不 suppress diagnostic

DraftStore
  -> 存储 session-scoped ephemeral StoredRepairDraft
  -> 不创建 artifact snapshot、不写 repair evidence

Admission / DirectiveBridge
  -> 把 InferredRepairDraft 转为 existing RepairDirectiveDraft / NormalizedRepairDirective
  -> 负责 selected refs / new facts / placement / field policy validation

Materialization / Preview / Apply
  -> 产出 MaterializedPreview、sealed preview、overlay event
  -> 仍由现有 stage-slice / materialization authority 执行

Verification
  -> Lane B / closure-specific verifier / generic verifier 共同验收
  -> DraftingSubsystem 不参与 verification shortcut
```

最终产品行为：

```text
Worker Delegation:
  用户只补核心业务意图，系统推断 placement / refs / binding 等技术字段。

Missing Handler:
  用户可以只给一句处理建议，drafting provider 推断 handler action / command family / value target。

Missing Output Producer:
  用户可以给生产输出的自然语言建议，drafting provider 推断 producer action / selected refs / placement / output binding。

REQUEST_INPUT.value_target:
  用户可以说明运行时要收集什么值，drafting provider 推断 value target / output binding。
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. `RepairDraftingSubsystem` 不拥有 repair capability；capability 仍来自 `RepairCatalog` / `RepairStrategyOptionSpec`。
2. Provider identity key 必须是 `(affordance_id, strategy_id, option_id)`。
3. `patch_type` 只能作为 provider resolve 后的兼容性约束，不能选择语义 provider。
4. 无 provider 时 drafting unavailable，不允许 fallback 到 generic LLM。
5. `UserRepairInput.free_text` 不得直接进入 patch payload、IR、materialization plan。
6. `FieldInference.value` 必须是 typed `RepairFieldValue` union，不允许自由 `dict` / `object`。
7. 新增 `RepairFieldValue` type 必须提供 owning provider scope、Admission bridge、serialization schema、validation tests、unrelated-provider negative tests。
8. `StoredRepairDraft` 只能是 session-scoped ephemeral state，不写 overlay、不写 snapshot、不写 repair evidence。
9. `draft_accepted` 只允许进入 Admission / Materialization；`materialized_preview_accepted` 才允许进入 apply / evidence path。
10. DraftPreview 不承诺 final IDs；MaterializedPreview 才展示最终 materialized closure preview。
11. Drafting provider 不得构造 `StepIR`、`BlockIR`、`WorkerIR`、`WorkerHandoffIR`。
12. Drafting provider 不得 suppress diagnostic，不得改变 verification lane。
13. CLI/API 只能通过 stable `option_id` / `draft_id` / `preview_id` 调用后端，不得使用 display index 作为 identity。
14. 新增 LLM 只能作为 provider 内部 bounded typed-plan/classification generator，不能输出 patch payload 或 IR。
15. 所有迁移 provider 必须保留现有 handler path 的可用性，直到新 path E2E 验收通过并完成原子切换。

---

## 3. LLM / Rule-based 决策约束

本计划允许 deterministic inference 和 bounded LLM inference，但二者必须有明确 authority。

允许的确定性逻辑：

- 从 `SelectableRefSet`、`ProducerIndex`、symbol table、target resolver、stage artifacts 中读取结构化字段。
- 对已有 refs、new facts、placement、result binding 做一致性校验。
- 基于可审计 artifact 生成 draft field 默认值。
- 基于 stable ID 分配 ephemeral `draft_id`，但不得分配 final construct IDs。
- 对 provider-owned typed values 做 serialization / round-trip / stale check。

允许的 LLM 逻辑：

- provider 内部 bounded semantic classification。
- 在后端提供的候选集合内选择或排序。
- 对用户自然语言建议做 typed field draft。
- 输出 provider-local typed plan，且必须经过 parser / schema / deterministic validation。

禁止的 LLM / rule fallback：

1. 通过 diagnostic kind 单独推断 provider。
2. 从 raw rendered SPL / prompt 文本中解析 refs。
3. 输出 raw variable name 并当作 selected ref。
4. 生成 `patch_type` 或修改 strategy option。
5. 生成 `StepIR` / `BlockIR` / `WorkerIR` / `WorkerHandoffIR`。
6. 修改 verification lane。
7. 在 provider 缺失时调用 generic LLM。
8. 用关键词兜底判断 issue family 或 materialization strategy。

需要 PM 前置确认的行为：

1. 新增 provider 的 LLM prompt/schema。
2. 新增 `RepairFieldValue` 类型。
3. 新增 provider-owned field policy。
4. 修改 Admission bridge 对 typed values 的解释。
5. 从 existing handler path 切换到 drafting path。

---

## 4. Phase RD0：Baseline 与 Characterization

### 4.1 目标

锁定当前 SPL Editing repair 行为，避免 Drafting 平台引入时破坏现有能力。该阶段不实现新功能，只建立可复验基线。

### 4.2 可编辑范围

允许新增：

```text
tests/unit/compiler/spl_editing/drafting/
tests/integration/compiler/spl_editing/drafting/
artifacts/reviews/repair_drafting/RD0/
```

允许修改：

```text
仅允许新增测试 fixture 或 review artifact manifest。
```

### 4.3 禁止改动

RD0 禁止修改：

```text
src/nl2spl/compiler/spl_editing/
src/nl2spl/compiler/construct_registry.py
examples/output/spl_editing_demo/run_demo.py
```

### 4.4 设计要求

Baseline 必须覆盖：

```text
worker_delegation.define_child_worker 当前可 E2E apply
missing_handler 当前可生成 suggestion/apply
missing_output_producer 当前可生成 suggestion/apply
REQUEST_INPUT.value_target 当前 issue visibility / non-visibility 状态
no provider path 当前不存在
```

### 4.5 测试计划

新增测试必须覆盖：

1. 当前 Worker Delegation v2 define-child E2E baseline。
2. 当前 missing_handler suggestion path baseline。
3. 当前 missing_output_producer suggestion path baseline。
4. 当前 preview/apply seal 不被 DraftingSubsystem 影响。
5. 当前 RepairCatalog option identity 使用 stable option id 或记录 display-index 旧债。

### 4.6 验收标准

RD0 通过条件：

1. 所有 baseline 测试在当前代码上通过。
2. 不新增 skip / xfail。
3. 不修改生产代码。
4. 生成 `artifacts/reviews/repair_drafting/RD0/manifest.json`。

### 4.7 PM 审核清单

审核时必须检查：

1. RD0 是否没有生产代码 diff。
2. baseline 是否覆盖所有后续迁移对象。
3. 是否记录当前交互体验和可用 repair path。
4. 是否没有把未来目标断言写成当前失败测试。

---

## 5. Phase RD1：Common Model 与 Serialization Contract

### 5.1 目标

实现 Drafting 平台的通用 DTO、typed value union、trace、confidence、clarification、preview、stored draft contract。

### 5.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/
  __init__.py
  model.py
  values.py
  serialization.py
  errors.py
  constants.py

tests/unit/compiler/spl_editing/drafting/
  test_model_contract.py
  test_value_serialization.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/__init__.py
```

### 5.3 禁止改动

RD1 禁止修改：

```text
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/materialization/
src/nl2spl/compiler/spl_editing/patches/
examples/
```

### 5.4 设计要求

必须实现：

```text
UserRepairInput
UserRepairFieldValue
InferredRepairDraft
FieldInference
RepairClarificationQuestion
InferenceTraceRecord
DraftPreview
StoredRepairDraft
RepairFieldValue typed union
Confidence enum / value object
```

`UserRepairInput` 必须包含：

```text
draft_accepted
materialized_preview_accepted
```

不得包含：

```text
confirmed
patch_payload
raw_ir
materialization_plan
```

### 5.5 测试计划

新增单元测试必须覆盖：

1. DTO frozen / equality / immutability。
2. JSON serialization round-trip。
3. `confirmed` 字段不存在。
4. `RepairFieldValue` 不接受 arbitrary dict/object。
5. unrelated provider scope 不能消费 provider-owned value。
6. `StoredRepairDraft` 不包含 overlay event / evidence fields。

### 5.6 验收标准

RD1 通过条件：

1. DTO 和 serialization 测试通过。
2. `rg -n "confirmed" src/nl2spl/compiler/spl_editing/drafting` 无误用。
3. `rg -n "StepIR|BlockIR|WorkerIR|WorkerHandoffIR" src/nl2spl/compiler/spl_editing/drafting` 无命中。
4. 无新增 skip / xfail。

### 5.7 PM 审核清单

审核时必须检查：

1. DTO 是否只表达 draft state。
2. 是否没有提前接入 service / CLI。
3. typed union 是否有明确扩展 contract。
4. serialization 是否稳定、可审计。

---

## 6. Phase RD2：Draft Store 与 Staleness Contract

### 6.1 目标

实现 session-scoped ephemeral draft store，确保 draft 不污染 artifact snapshot / overlay / evidence。

### 6.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/
  store.py
  staleness.py

tests/unit/compiler/spl_editing/drafting/
  test_draft_store.py
  test_draft_staleness.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/drafting/model.py
```

### 6.3 禁止改动

RD2 禁止修改：

```text
src/nl2spl/compiler/spl_editing/core/overlay*
src/nl2spl/compiler/spl_editing/materialization/
src/nl2spl/compiler/spl_editing/verification/
```

### 6.4 设计要求

Draft store key 必须是：

```text
session_id + artifact_snapshot_id + overlay_version + draft_id
```

stale 条件：

```text
artifact_snapshot_id mismatch
overlay_version mismatch
session_id mismatch
issue_id mismatch
option_id mismatch
draft schema version mismatch
```

Draft store 不得：

```text
create overlay event
create patched snapshot
write repair evidence
mutate compile artifact
```

### 6.5 测试计划

新增测试必须覆盖：

1. same session/snapshot/overlay 可读取 draft。
2. overlay version 变化后 draft stale。
3. snapshot id 变化后 draft stale。
4. stale draft 不能进入 Admission bridge。
5. store clear / expire 行为不影响 artifact snapshot。
6. draft_id collision fail-fast。

### 6.6 验收标准

RD2 通过条件：

1. stale draft negative tests 全部通过。
2. overlay / snapshot 相关模块无 production diff。
3. `StoredRepairDraft` 未出现在 snapshot metadata schema。

### 6.7 PM 审核清单

审核时必须检查：

1. draft 是否严格 ephemeral。
2. stale check 是否在 Admission 前执行。
3. 是否不存在“为了方便先写 metadata”的临时路径。

---

## 7. Phase RD3：Provider Registry 与 Service Shell

### 7.1 目标

实现 provider registry、resolve 规则、service shell 和 no-provider 行为。

### 7.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/
  provider.py
  registry.py
  service.py
  context.py

tests/unit/compiler/spl_editing/drafting/
  test_provider_registry.py
  test_drafting_service.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/drafting/__init__.py
```

### 7.3 禁止改动

RD3 禁止修改：

```text
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/presentation/
examples/
```

### 7.4 设计要求

Registry resolve 输入：

```text
affordance_id
strategy_id
option_id
patch_type
```

Provider identity key：

```text
(affordance_id, strategy_id, option_id)
```

`patch_type` 只允许：

```text
compatibility check
```

不得：

```text
select semantic provider
override strategy option
fallback generic LLM
```

### 7.5 测试计划

新增测试必须覆盖：

1. duplicate provider identity rejected。
2. same provider with multiple compatible patch types accepted。
3. incompatible patch type returns drafting unavailable。
4. no provider returns drafting unavailable，不调用 LLM。
5. diagnostic kind alone cannot resolve provider。

### 7.6 验收标准

RD3 通过条件：

1. registry contract tests 全部通过。
2. no-provider path 无 generic fallback。
3. service shell 不触碰 Admission / Materialization。

### 7.7 PM 审核清单

审核时必须检查：

1. provider identity 是否没有包含 patch_type。
2. service 是否只 orchestrate drafting。
3. no-provider 是否安全且用户可理解。

---

## 8. Phase RD4：Typed Context View Layer

### 8.1 目标

建立 provider 可消费的 typed read-only context view，避免 provider 直接读取 raw snapshot / prompt / rendered SPL。

### 8.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/views/
  __init__.py
  base.py
  selectable_refs.py
  placement.py
  producer.py
  exception_flow.py
  worker_delegation.py
  request_input.py

tests/unit/compiler/spl_editing/drafting/views/
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/drafting/context.py
```

### 8.3 禁止改动

RD4 禁止修改：

```text
src/nl2spl/compiler/pipeline/
src/nl2spl/compiler/irs/
src/nl2spl/compiler/spl_editing/materialization/
```

### 8.4 设计要求

Typed views 必须只从结构化 artifact 派生：

```text
ArtifactSnapshot
RepairTarget
SelectableRefSet
ProducerIndex
TargetResolverResult
Issue facts
Stage-specific artifact projections
```

Typed views 不得：

```text
parse diagnostic.message
parse UI display text
parse rendered SPL text
call LLM
mutate artifact
```

### 8.5 测试计划

新增测试必须覆盖：

1. selectable refs view 只返回 stable ref ids。
2. placement view 不返回 raw step text 作为 authority。
3. exception flow view condition 来自 structured target facts。
4. producer view 能识别 target output / candidate inputs。
5. worker delegation view 不重新决定 API / promotion authority。
6. request input view 能定位 value target gap。

### 8.6 验收标准

RD4 通过条件：

1. typed view tests 全部通过。
2. `rg -n "diagnostic\\.message|rendered SPL|display text" src/nl2spl/compiler/spl_editing/drafting` 无不合规命中。
3. views 不调用 LLM、不写 overlay。

### 8.7 PM 审核清单

审核时必须检查：

1. view 是否只是 read-only projection。
2. provider 是否不需要直接读 raw snapshot internals。
3. 每个 view 的 authority source 是否明确。

---

## 9. Phase RD5：Admission / DirectiveBridge

### 9.1 目标

实现 typed draft 到 existing repair directive / normalized directive 的桥接层，保持 Admission authority 不下沉到 provider。

### 9.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/admission/
  __init__.py
  bridge.py
  validators.py
  errors.py

tests/unit/compiler/spl_editing/drafting/admission/
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/drafting/service.py
```

### 9.3 禁止改动

RD5 禁止修改：

```text
src/nl2spl/compiler/spl_editing/materialization/
src/nl2spl/compiler/spl_editing/patches/
```

### 9.4 设计要求

Admission bridge 输入：

```text
StoredRepairDraft
InferredRepairDraft
UserRepairInput with draft_accepted=True
current session/snapshot/overlay identity
RepairCatalogEntry / option_id
```

Admission bridge 输出：

```text
RepairDirectiveDraft or NormalizedRepairDirective
validation result
materialized-preview request
```

Admission bridge 必须校验：

```text
staleness
provider scope
RepairFieldValue schema
selected refs
new facts
placement policy
additional instruction conflict
strategy option identity
```

### 9.5 测试计划

新增测试必须覆盖：

1. stale draft rejected。
2. unrelated provider value rejected。
3. raw dict value rejected。
4. unknown selected ref rejected。
5. additional instruction 不能补 required structured field。
6. draft_accepted=False 不能进入 materialized preview。
7. materialized_preview_accepted=False 不能 apply。

### 9.6 验收标准

RD5 通过条件：

1. Admission negative tests 全部通过。
2. Drafting provider 仍无 patch payload construction。
3. `materialized_preview_accepted` gate 已可单测证明。

### 9.7 PM 审核清单

审核时必须检查：

1. Admission 是否是唯一从 draft 进入 repair directive 的桥。
2. provider 是否没有绕过 bridge。
3. draft acceptance 和 materialized preview acceptance 是否分离。

---

## 10. Phase RD6：Presentation / CLI / Service API Integration

### 10.1 目标

把 DraftingSubsystem 接入 presentation service、CLI/API interaction flow，但不迁移任何具体 provider。

### 10.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/presentation/model/drafting.py
src/nl2spl/compiler/spl_editing/presentation/resolvers/drafting.py
tests/unit/compiler/spl_editing/presentation/test_drafting_presentation.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/presentation/service.py
src/nl2spl/compiler/spl_editing/presentation/model/__init__.py
src/nl2spl/compiler/spl_editing/cli.py
examples/output/spl_editing_demo/run_demo.py
```

### 10.3 禁止改动

RD6 禁止修改：

```text
src/nl2spl/compiler/spl_editing/materialization/
src/nl2spl/compiler/spl_editing/patches/
```

### 10.4 设计要求

新增后端 API 语义：

```text
create_repair_draft(run_id, issue_id, option_id, user_input)
accept_repair_draft(run_id, issue_id, option_id, draft_id)
create_materialized_preview_from_draft(...)
accept_materialized_preview(...)
```

UI/CLI display index 只能用于展示，调用必须使用：

```text
issue_id
option_id
draft_id
preview_id
revision_token
```

### 10.5 测试计划

新增测试必须覆盖：

1. no provider option 显示 drafting unavailable，但原有 repair path 不丢失。
2. provider available 时显示 draft-first capability。
3. stale revision token rejected。
4. display index reorder 不影响 option_id。
5. non-editable issue 不能 create draft。

### 10.6 验收标准

RD6 通过条件：

1. presentation tests 通过。
2. CLI 可显示 drafting unavailable / available 两种状态。
3. 未迁移 issue 仍走现有 path。
4. no provider 不调用 generic LLM。

### 10.7 PM 审核清单

审核时必须检查：

1. 是否没有用 display index 作为后端 identity。
2. no-provider 是否没有变成 hard failure。
3. existing repairs 是否未被削弱。

---

## 11. Phase RD7：WorkerDelegationInferenceProvider

### 11.1 目标

迁移 `worker_delegation.complete_closure.v2 / define_child_worker` 到 draft-first provider，减少用户需要填写的技术字段。

### 11.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/providers/
  __init__.py
  worker_delegation.py

tests/unit/compiler/spl_editing/drafting/providers/
  test_worker_delegation_provider.py

tests/integration/compiler/spl_editing/drafting/
  test_worker_delegation_draft_flow.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/strategy/defaults.py
src/nl2spl/compiler/spl_editing/cli.py
examples/output/spl_editing_demo/run_demo.py
```

### 11.3 禁止改动

RD7 禁止修改：

```text
src/nl2spl/compiler/spl_editing/stage_slices/worker_delegation_v2.py
src/nl2spl/compiler/spl_editing/stage_slices/worker_delegation_closure.py
```

除非发现 materialization bug，并单独提交设计确认。

### 11.4 设计要求

Provider 必须推断：

```text
responsibility
selected input refs
output draft
placement intent
result binding
explicit none semantics
```

用户默认只需确认或补充：

```text
delegated responsibility
returned result semantic description
```

不得默认询问：

```text
placement_ref
handoff binding
invoke output
technical result_usage object
```

### 11.5 测试计划

新增测试必须覆盖：

1. source-backed task boundary 可推断 responsibility。
2. input refs 从 SelectableRefSet 推断，未知 ref rejected。
3. placement 推断为 first consumer 前，不使用 raw step text。
4. required output gap 不降级为 parent-local temporary。
5. result binding 可进入 existing Worker Delegation v2 Admission。
6. low confidence 返回 clarification。
7. API-owned span 不得成为 child-worker-owned span。

### 11.6 验收标准

RD7 通过条件：

1. define_child_worker draft-first E2E Lane B accepted。
2. CLI 不再要求用户填写技术字段。
3. existing Worker Delegation v2 negative tests 不回退。
4. artifact bundle 包含 draft、trace、materialized preview、verification result。

### 11.7 PM 审核清单

审核时必须检查：

1. provider 是否没有 materialization authority。
2. 推断字段是否都有 evidence_refs / confidence / trace。
3. 用户体验是否确实减少技术字段。

---

## 12. Release 1 Freeze：Worker Delegation MVP 审核

### 12.1 目标

冻结 RD0-RD7 的第一批实施结果。该冻结审核只验收 Release 1，不要求 RD8-RD13 完成。

### 12.2 必须提交的证据

```text
artifacts/reviews/repair_drafting/RD7_freeze/
  review_report.md
  commands.log
  pytest_output.txt
  ruff_output.txt
  diff_check_output.txt
  manifest.json
  worker_delegation_draft_flow/
    user_input.json
    stored_draft.json
    inferred_draft.json
    draft_preview.txt
    materialized_preview.json
    verification_result.json
    rendered_spl_after.txt
    diagnostic_diff.json
```

### 12.3 验收标准

Release 1 通过条件：

1. RD0-RD7 全部独立验收通过。
2. `define_child_worker` draft-first E2E accepted。
3. existing Worker Delegation v2 negative tests 不回退。
4. missing_handler / missing_output_producer existing path 不回退。
5. no provider 不 fallback generic LLM。
6. Drafting 不写 overlay / snapshot / evidence。
7. Drafting 不生成 patch payload / IR。
8. RD8-RD13 未完成不得阻塞 Release 1。

### 12.4 PM 审核清单

审核时必须检查：

1. 是否把 RD8-RD13 偷偷做成 Release 1 依赖。
2. 是否存在 hidden fallback 到旧 Worker Delegation form-first path。
3. 是否真实改善用户输入体验，而不是仅换展示文案。
4. 是否保留后续 provider expansion 的接口而没有提前实现多余 provider。

---

## 13. Post-MVP Phase RD8：MissingHandlerInferenceProvider

RD8 属于 Post-MVP Provider Expansion。只有通过 `Provider Migration Freeze` 后才可进入实施；未批准前不得修改 missing_handler 默认生产路径。

### RD8.1 目标

将 `EXCEPTION_FLOW.handler_action` 的 missing handler suggestion 迁移为 suggestion-first provider。

### RD8.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/providers/missing_handler.py
tests/unit/compiler/spl_editing/drafting/providers/test_missing_handler_provider.py
tests/integration/compiler/spl_editing/drafting/test_missing_handler_draft_flow.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/handlers/missing_handler/
src/nl2spl/compiler/spl_editing/strategy/defaults.py
```

### RD8.3 禁止改动

RD8 禁止修改：

```text
src/nl2spl/compiler/spl_editing/materialization/stage5/
src/nl2spl/compiler/spl_editing/materialization/stage7/
```

除非实施计划另行确认 Stage5/Stage7 repair slice migration。

### RD8.4 前置条件

RD8 开工前必须满足：

```text
ExceptionFlow target resolver 能提供 structured condition / flow_ref / worker_id / source_span_ids。
```

如果该 structured target fact 不存在，RD8 不得开工，且不得 fallback 到 `diagnostic.message` 或 UI display text 解析 condition。

### RD8.5 设计要求

Provider 输入：

```text
free_text user suggestion
target exception flow typed facts
available variables
handler affordance / strategy option
```

Provider 输出 typed values：

```text
HandlerActionTextValue
HandlerCommandFamilyValue
HandlerValueTargetValue
PlacementIntentValue
```

严禁：

```text
从 diagnostic.message 解析 condition
把 prompt few-shot 答案当作 patch payload
直接选择 DISPLAY_MESSAGE / REQUEST_INPUT 作为硬编码答案
```

### RD8.6 测试计划

新增测试必须覆盖：

1. condition text 来自 structured target fact。
2. free_text 建议生成 typed handler draft。
3. missing / ambiguous value target 返回 clarification。
4. unknown variable rejected。
5. no user suggestion 时 minimal default policy 可生成 draft。
6. MaterializedPreview 与 apply 后 rendered handler 一致。

### RD8.7 验收标准

RD8 通过条件：

1. missing_handler draft-first/suggestion-first E2E Lane B accepted。
2. 旧 prompt 过拟合路径不再是默认生产路径。
3. no-provider fallback 不存在。
4. existing missing_handler tests 迁移或保留等价覆盖。

### RD8.8 PM 审核清单

审核时必须检查：

1. 是否不再把答案写进 prompt。
2. 是否没有从 raw diagnostic message 取 materialization fact。
3. handler action 是否经 Admission / Materialization 验证。

---

## 14. Post-MVP Phase RD9：MissingOutputProducerInferenceProvider

RD9 属于 Post-MVP Provider Expansion。只有通过 `Provider Migration Freeze` 后才可进入实施；未批准前不得修改 missing_output_producer 默认生产路径。

### RD9.1 目标

将 `Required output has no producer` 的 InsertProducerStep suggestion 迁移为 Drafting provider，继续保持 SelectableRefSet 反幻觉边界。

### RD9.2 Scope Freeze

RD9 开工前必须在 Provider Migration Freeze 中二选一：

```text
方案 A：RD9 只迁移 InsertProducerStep，不迁移 BindExistingProducerStep。
方案 B：RD9 同时迁移 Insert + Bind，但必须拆成两个 strategy option / field policy。
```

默认采用方案 A。

禁止让 provider 根据 free_text 自行决定 Insert vs Bind，因为这会把 provider 变成 patch_type selector。

### RD9.3 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/providers/missing_output_producer.py
tests/unit/compiler/spl_editing/drafting/providers/test_missing_output_producer_provider.py
tests/integration/compiler/spl_editing/drafting/test_missing_output_producer_draft_flow.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/handlers/missing_output_producer/
src/nl2spl/compiler/spl_editing/strategy/defaults.py
```

### RD9.4 禁止改动

RD9 禁止修改：

```text
src/nl2spl/compiler/spl_editing/patches/insert_producer_step/applier.py
src/nl2spl/compiler/spl_editing/patches/insert_producer_step/verifier.py
```

除非发现 verifier bug，并单独记录。

### RD9.5 设计要求

Provider 输入：

```text
target required output
ProducerIndex
SelectableRefSet
available producer candidates
user free_text instruction
placement view
```

Provider 输出：

```text
ProducerActionValue
SelectedInputRefsValue
PlacementIntentValue
OutputBindingValue
```

必须拒绝：

```text
project_data 这类 unknown ref
raw variable name
required output 被误当 selected input
free_text 覆盖 selected refs
```

### RD9.6 测试计划

新增测试必须覆盖：

1. hallucinated ref rejected before materialization。
2. valid selected refs 进入 Admission。
3. target output role 不得被选为 input role。
4. no user suggestion 时 minimal producer draft 可生成。
5. user suggestion 只能影响 action text / preference，不新增 refs。
6. ProducerIndex repair resolved。

### RD9.7 验收标准

RD9 通过条件：

1. missing_output_producer draft flow E2E accepted。
2. `project_data` 负例无 overlay。
3. InsertProducerStep verifier 不接收 legacy dict payload。
4. Required output issue resolved 且不新增 undefined `<REF>`。

### RD9.8 PM 审核清单

审核时必须检查：

1. SelectableRefSet 是否仍是唯一 ref authority。
2. provider 是否没有直接构造 StepIR。
3. free_text 是否被降权为 preference。

---

## 15. Post-MVP Phase RD10：REQUEST_INPUT.value_target Provider

RD10 属于 Post-MVP Provider Expansion。只有通过 `Provider Migration Freeze` 后才可进入实施；未批准前不得修改 REQUEST_INPUT 相关默认生产路径。

### RD10.1 目标

为真正的 runtime user input command 缺口提供 Drafting provider，避免其与 Worker Delegation closure repair 混淆。

### RD10.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/providers/request_input_value_target.py
tests/unit/compiler/spl_editing/drafting/providers/test_request_input_value_target_provider.py
tests/integration/compiler/spl_editing/drafting/test_request_input_value_target_draft_flow.py
```

允许修改：

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/spl_editing/strategy/defaults.py
```

### RD10.3 禁止改动

RD10 禁止修改：

```text
src/nl2spl/compiler/spl_editing/stage_slices/worker_delegation*
```

### RD10.4 设计要求

Provider 必须只处理：

```text
REQUEST_INPUT.value_target
runtime business value collection
```

不得用于：

```text
WORKER_PROMOTION.resolve_contract
static child worker contract gap
API deferred validation
```

### RD10.5 测试计划

新增测试必须覆盖：

1. REQUEST_INPUT 缺 outputs 时显示可 draft repair。
2. Worker Delegation option list 不出现 "Ask the user for missing information"。
3. user free_text 可生成 value target draft。
4. unknown output name 走 new output admission，不直接写 raw output。
5. repaired REQUEST_INPUT renders with output target。

### RD10.6 验收标准

RD10 通过条件：

1. REQUEST_INPUT.value_target issue 可修复。
2. Worker Delegation 不再暴露 REQUEST_INPUT fallback option。
3. runtime user input 与 compile-time authoring gap 语义分离。

### RD10.7 PM 审核清单

审核时必须检查：

1. 是否没有把 request input provider 挂回 worker promotion。
2. 新 output 是否走 admission。
3. UI 文案是否面向当前 authoring user，而不是系统开发者。

---

## 16. Post-MVP Phase RD11：Bounded LLM Inference Infrastructure

RD11 属于 Post-MVP expansion。RD11 可以开发基础设施，但不得成为 RD0-RD7 的依赖；RD7 必须在 deterministic-only 模式下通过。RD11 不得修改 RD7 provider 的默认生产行为，除非通过 `Bounded LLM Enablement`。

### RD11.1 目标

实现 provider 内部可选的 bounded LLM typed-plan 生成能力，并为所有 provider 保持 deterministic fallback / no-generic-fallback 边界。

### RD11.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/llm/
  __init__.py
  prompt.py
  schema.py
  parser.py
  policy.py

tests/unit/compiler/spl_editing/drafting/llm/
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/drafting/provider.py
src/nl2spl/compiler/spl_editing/drafting/providers/*.py
```

### RD11.3 禁止改动

RD11 禁止修改：

```text
src/nl2spl/compiler/spl_editing/materialization/
src/nl2spl/compiler/spl_editing/patches/
```

### RD11.4 设计要求

LLM 输出必须是 provider-local typed plan，例如：

```text
WorkerDelegationTaskBoundaryPlan
HandlerCommandIntentPlan
ProducerActionIntentPlan
RequestInputValueTargetPlan
```

LLM 输出不得包含：

```text
Patch payload
IR object
raw variable refs
unknown ref IDs
verification lane
overlay event
```

每个 prompt/schema 必须声明：

```text
provider_id
affordance_id
strategy_id
option_id
allowed field ids
allowed ref ids
low-confidence behavior
```

### RD11.5 测试计划

新增测试必须覆盖：

1. valid typed plan accepted。
2. unknown field rejected。
3. unknown ref rejected。
4. patch payload-like output rejected。
5. prompt 不包含答案过拟合 few-shot。
6. disabled LLM path 不调用 model。
7. no provider 不调用 generic model。

### RD11.6 验收标准

RD11 通过条件：

1. LLM parser/schema tests 通过。
2. 所有 provider 可配置 deterministic-only。
3. LLM 结果必须经过 deterministic validation。
4. prompt 审计无 answer leakage。

### RD11.7 PM 审核清单

审核时必须检查：

1. 是否新增了通用 LLM repair parser。
2. LLM 是否被限制在 provider typed plan。
3. 是否存在 prompt 过拟合或 answer-in-prompt。

---

## 17. Post-MVP Phase RD12：Atomic Provider Migration 与 Legacy Cleanup

RD12 属于 Post-MVP full platform migration。只有 RD8-RD10 对应 provider E2E 全部通过，并且 Provider Migration Freeze 明确批准后，才可进入 RD12。

### RD12.1 目标

将 migrated repair families 的默认路径切到 DraftingSubsystem，同时保留必要 migration shim 并明确移除时间。

### RD12.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/presentation/service.py
src/nl2spl/compiler/spl_editing/handlers/
src/nl2spl/compiler/spl_editing/strategy/defaults.py
src/nl2spl/compiler/spl_editing/cli.py
examples/output/spl_editing_demo/run_demo.py
```

允许新增：

```text
tests/integration/compiler/spl_editing/drafting/test_provider_migration_matrix.py
artifacts/reviews/repair_drafting/RD12/
```

### RD12.3 禁止改动

RD12 禁止修改：

```text
src/nl2spl/compiler/irs/
src/nl2spl/compiler/pipeline/
```

### RD12.4 设计要求

迁移策略：

```text
1. provider E2E green 后才可切默认路径。
2. old handler path 可保留为 migration shim，但必须标注 remove-after phase。
3. default production path 不得同时生成 old suggestion 和 draft suggestion。
4. no provider family 仍走原 path，不因 DraftingSubsystem 存在而失败。
```

### RD12.5 测试计划

新增测试必须覆盖：

1. migrated family 默认走 drafting path。
2. legacy handler 不再生成重复 suggestion。
3. no-provider family 保持原能力。
4. migration shim 不接收新 Drafting DTO。
5. old raw dict payload path 不再可达。

### RD12.6 验收标准

RD12 通过条件：

1. Worker Delegation / missing_handler / missing_output_producer / REQUEST_INPUT.value_target 默认路径清晰。
2. 不存在重复 suggestion。
3. no-provider fallback 行为符合设计。
4. legacy shim 生命周期写入文档和测试。

### RD12.7 PM 审核清单

审核时必须检查：

1. 是否发生半迁移导致双路径同时生效。
2. 是否有 dead prompt / dead parser 残留。
3. 是否有 raw dict payload bridge 残留。

---

## 18. Post-MVP Phase RD13：Audit、Artifacts 与 Full E2E

RD13 是 full platform freeze，不是 Release 1 freeze。RD13 不允许通过压缩 full platform 范围来替代，但 RD13 未完成不得阻塞 RD0-RD7 的 Release 1 交付。

### RD13.1 目标

完成完整平台验收：多 provider、多 interaction mode、draft store、stale rejection、materialized preview、apply/verification、artifact bundle。

### RD13.2 可编辑范围

允许新增：

```text
tests/integration/compiler/spl_editing/drafting/test_full_repair_drafting_e2e.py
artifacts/reviews/repair_drafting/RD13/
.test-artifacts/spl_editing/repair_drafting/
```

允许修改：

```text
examples/output/spl_editing_demo/run_demo.py
```

### RD13.3 禁止改动

RD13 禁止修改：

```text
src/ production code
```

除非 E2E 暴露真实 bug；若修改生产代码，必须回到对应 phase 补测试。

### RD13.4 设计要求

E2E artifact bundle 必须包含：

```text
before snapshot id / overlay version
issue inventory
selected issue / option id
UserRepairInput
StoredRepairDraft
InferredRepairDraft
DraftPreview
Admission result
MaterializedPreview
apply request
verification result
after diagnostics
rendered SPL diff
manifest hash
```

### RD13.5 测试计划

最终 E2E 必须覆盖：

1. Worker Delegation define_child_worker draft-first。
2. Missing Handler suggestion-first。
3. Missing Output Producer suggestion-first。
4. REQUEST_INPUT.value_target draft repair。
5. no provider unavailable。
6. stale draft rejected。
7. unknown ref rejected。
8. LLM disabled deterministic path。
9. LLM enabled typed-plan path with stub model。
10. non-editable issue rejected。

### RD13.6 验收标准

RD13 通过条件：

1. 全量 drafting tests 通过。
2. SPL Editing unit + integration tests 通过。
3. `run_demo.py` 真实 E2E 覆盖 migrated provider。
4. artifact bundle manifest hash 校验通过。
5. Ruff / `git diff --check` 通过。
6. IRS audit 无新增 unwaived P0/P1。

### RD13.7 PM 审核清单

审核时必须检查：

1. artifact bundle 是否可复验。
2. E2E 是否真实走 DraftingSubsystem。
3. 是否存在 hidden fallback 到 old prompt path。
4. verification 是否仍由 Lane / verifier authority 接管。

---

## 19. Decision Gate：Provider Migration Freeze

### 19.1 目标

在 RD8-RD12 迁移多个 repair family 前，冻结每个 family 的 provider scope、field values、Admission bridge 和 E2E 目标，避免通用平台膨胀。

### 19.2 可选方案

允许提交但必须评审确认的方案包括：

```text
方案 A：一次迁移所有 provider。
方案 B：按 provider 逐个迁移并保留 old path shim。
方案 C：只迁移 Worker Delegation，其他 provider 延后。
```

推荐方案 B。原因是完整平台必须覆盖多个 provider，但每个 provider 都要独立验收，不能通过一个 provider 证明通用平台完整。

### 19.3 必须明确的问题

方案确认文档必须回答：

1. provider identity key 是什么。
2. provider-owned `RepairFieldValue` 类型有哪些。
3. 对应 Admission bridge handler 是什么。
4. 是否允许 LLM，若允许 typed-plan schema 是什么。
5. default path 切换后 old handler 如何退出。
6. E2E 验收 issue 是什么。

### 19.4 验收标准

该门禁通过条件：

1. 每个 provider 的 scope 和 non-goals 写清楚。
2. 每个 provider 有 negative matrix。
3. PM 明确批准后方可进入 RD8-RD12。

---

## 20. Decision Gate：Bounded LLM Enablement

### 20.1 目标

确认是否在生产默认路径启用 LLM inference。RD11 可以实现 LLM infrastructure，但默认启用必须单独过门禁。

### 20.2 可选方案

```text
方案 A：默认 deterministic-only，LLM 仅测试 / developer flag。
方案 B：部分 provider 默认启用 LLM typed-plan。
方案 C：全部 provider 默认启用 LLM typed-plan。
```

推荐方案 A 作为 first release，方案 B 作为后续灰度。

### 20.3 必须明确的问题

方案确认文档必须回答：

1. 哪些 provider 允许 LLM。
2. prompt/schema 是否通过 answer leakage 审计。
3. LLM output hash 是否进入 preview seal。
4. 失败时是否 fallback deterministic，还是要求 clarification。
5. 成本、延迟、缓存策略是什么。

### 20.4 验收标准

该门禁通过条件：

1. LLM typed-plan schema 有单测和负例。
2. 无 generic repair LLM。
3. PM 明确批准后才可生产默认启用。

---

## 21. 端到端验收场景

最终必须具备以下 E2E 或高保真集成覆盖：

1. **Worker Delegation draft-first**
   - 选择 `Define this work as a child worker`。
   - 系统生成 DraftPreview。
   - 用户接受 draft。
   - Admission 生成 MaterializedPreview。
   - 用户确认 materialized preview。
   - Apply + Lane B accepted。
   - 原 WORKER_PROMOTION diagnostic resolved。

2. **Missing Handler suggestion-first**
   - 用户输入一句自然语言处理建议。
   - Provider 生成 handler typed draft。
   - MaterializedPreview 显示 handler action。
   - Apply 后 exception flow 不再为空。

3. **Missing Output Producer suggestion-first**
   - 用户输入输出生产建议。
   - Provider 只选择 SelectableRefSet 中合法 refs。
   - hallucinated ref 负例 rejected。
   - Apply 后 ProducerIndex resolved。

4. **REQUEST_INPUT.value_target**
   - 选择 runtime input value target repair。
   - 用户说明要收集的值。
   - New output / value target 走 Admission。
   - Apply 后 REQUEST_INPUT 有 output target。

5. **No provider unavailable**
   - 某 option 无 provider。
   - UI 显示 drafting unavailable。
   - 不调用 generic LLM。
   - 既有 non-drafting repair path 不受影响。

6. **Stale draft rejection**
   - 生成 draft。
   - overlay version 变化。
   - 尝试 accept draft。
   - 后端拒绝，不产生 overlay。

7. **LLM typed-plan negative**
   - Stub LLM 输出 unknown ref / patch payload / raw IR-like object。
   - parser 或 validator rejected。
   - 不进入 Admission。

---

## 22. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐设计文档。
2. 是否把 DraftingSubsystem 做成 repair authority。
3. 是否扩大为万能 LLM repair compiler。
4. 是否新增未确认的 rule-based semantic fallback。
5. provider identity 是否使用 `(affordance_id, strategy_id, option_id)`。
6. `patch_type` 是否仍只是 compatibility constraint。
7. no-provider 是否不调用 generic LLM。
8. free_text 是否没有直接进入 patch payload。
9. `RepairFieldValue` 是否 typed 且 provider-scoped。
10. `StoredRepairDraft` 是否未写 overlay / snapshot / evidence。
11. stale draft 是否在 Admission 前拒绝。
12. DraftPreview 是否没有 final IDs。
13. materialized preview 是否受 preview/apply seal 保护。
14. migrated provider 是否有 negative matrix。
15. legacy handler path 是否没有重复 suggestion。
16. 是否存在 skip / xfail / 弱断言。
17. 是否存在 hidden fallback 到旧 prompt。
18. 是否存在 raw dict payload bridge。
19. 是否真实运行 demo E2E。
20. artifact bundle 是否可复验。

建议反模式扫描：

```powershell
rg -n "generic.*LLM|confirmed|patch_payload|StepIR|BlockIR|WorkerIR|WorkerHandoffIR|diagnostic\\.message|display index|skip|xfail" src tests docs
```

命中项必须逐条说明是否合规。

---

## 23. 阶段完成顺序

Release 1 / MVP 推荐顺序：

```text
RD0  Baseline 与 Characterization
RD1  Common Model 与 Serialization Contract
RD2  Draft Store 与 Staleness Contract
RD3  Provider Registry 与 Service Shell
RD4  Typed Context View Layer
RD5  Admission / DirectiveBridge
RD6  Presentation / CLI / Service API Integration
RD7  WorkerDelegationInferenceProvider
Release 1 Freeze
```

Post-MVP / Full Platform Roadmap 推荐顺序：

```text
Gate Provider Migration Freeze
RD8  MissingHandlerInferenceProvider
RD9  MissingOutputProducerInferenceProvider
RD10 REQUEST_INPUT.value_target Provider
RD11 Bounded LLM Inference Infrastructure
Gate Bounded LLM Enablement
RD12 Atomic Provider Migration 与 Legacy Cleanup
RD13 Audit、Artifacts 与 Full E2E
```

依赖关系：

- RD0 必须最先完成。
- RD1-RD3 可作为公共平台基础，必须在任何 provider 前完成。
- RD4-RD5 必须在 provider E2E 前完成。
- RD6 可在 RD4 后启动，但 default path 切换必须等 RD7+。
- RD7 是第一个 provider，必须先于其他 provider 迁移。
- RD0-RD7 + Release 1 Freeze 是下一轮直接执行范围。
- RD8-RD10 必须经过 Provider Migration Freeze，且不得作为 Release 1 完成条件。
- RD11 可在 RD7 后并行开发，但不得成为 RD0-RD7 依赖；生产启用必须经过 Bounded LLM Enablement。
- RD12 必须等 RD8-RD10 E2E 全部通过。
- RD13 是 full platform 最终冻结审核，不允许通过压缩 full platform 范围来替代；但 RD13 未完成不得阻塞 Release 1。

---

## 24. 交付证据要求

每个 phase 必须提交：

```text
artifacts/reviews/repair_drafting/RD<N>/
  review_report.md
  commands.log
  pytest_output.txt
  ruff_output.txt
  diff_check_output.txt
  manifest.json
```

涉及 E2E 的 phase 还必须提交：

```text
before_snapshot.json
after_snapshot.json
draft.json
materialized_preview.json
verification_result.json
rendered_spl_before.txt
rendered_spl_after.txt
diagnostic_diff.json
```

PM 不接受仅口头说明“已通过”。所有结果必须可复验。
