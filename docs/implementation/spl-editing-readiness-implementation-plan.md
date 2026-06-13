# SPL Editing Readiness Implementation Plan

日期：2026-06-12  
状态：**R0-R7 completed. Ready for SPL Editing backend implementation.**  
来源文档：`docs/design/spl_editing_prerequisite_modifications.md`

---

## 0. 目标

本计划把 SPL Editing readiness 拆成可逐阶段实施的 R0-R7 工作包。

目标是在实现 SPL Editing handler / patch / verifier 之前，先完成以下基础能力：

- IRS slot 可声明 repair affordance。
- final diagnostic 可反查 IRS construct slot。
- repair catalog 可从 IRS registry 派生。
- worker/delegation 与 producer diagnostics 有稳定 editable exposure 语义。
- user-confirmed repair evidence 能被 IRS / Gate / ProducerIndex / provenance 共同识别。

---

## 1. 非目标

本计划不实现：

- AI suggestion generation。
- patch applier。
- patch verifier。
- editing session。
- artifact snapshot / overlay store。
- CLI / API。
- UI Diagnostics Console。

这些属于 readiness 完成后的 SPL Editing 实现阶段。

---

## 2. 阶段依赖图

```text
R0 current-state lock tests
  -> R1 diagnostic metadata foundation
  -> R2 RepairAffordanceSpec + SlotSpec extension
  -> R3 RepairCatalogBuilder
  -> R4 producer issue grouping policy
  -> R5 worker/delegation exposure policy
  -> R6 user-confirmed evidence foundation
  -> R7 documentation and skill sync
```

R1-R3 是 SPL Editing issue extraction 的基础。  
R4-R5 是 first MVP issue set 可稳定暴露的基础。  
R6 是任何 apply-capable patch 进入实现前的硬前置。  
R7 应在代码行为稳定后统一更新，避免文档超前于实现。

---

## 3. 全局实施规则

- 不让 IRS checker 调用 LLM、修改 IR、生成 SPL、应用 patch 或生成 repair suggestion。
- 不在 `construct_registry.py` 中 import SPL Editing patch implementation。
- `RepairAffordanceSpec` 只保存可序列化 ID / metadata，不保存 callable 或 class reference。
- `CompileDiagnostic.kind` 不作为完整 repair lookup key。
- Repair lookup 必须依赖 IRS source metadata。
- `DELEGATION_INTENT` 不得作为 active construct owner 或 repair target kind 回流。
- `ProducerIndex` 仍是 producer status authority。
- `ExecutableElementGate` 仍是 executable step renderability authority。

---

## R0. Current-State Lock Tests

### 目标

在改动 readiness 基础设施前，先用测试锁定当前事实，防止后续迁移误判。

### 修改范围

主要新增或更新测试，不改变生产行为。

候选测试范围：

- `tests/unit/test_construct_registry.py`
- `tests/unit/compiler/irs/test_r10_delegation_intent_cleanup_characterization.py`
- `tests/unit/test_diagnostic_consolidator.py`
- `tests/unit/test_executable_gate.py`
- `tests/unit/test_producer_index.py`
- `tests/unit/compiler/irs/test_r6_step_checker.py`
- `tests/unit/compiler/irs/test_r9_final_audit.py`

### 任务清单

- 锁定 `CompileDiagnostic.metadata` 字段存在。
- 锁定 default registry 不包含 `DELEGATION_INTENT`。
- 锁定 `WorkerDelegationIRSChecker` 不产出 `DELEGATION_INTENT` instance。
- 锁定 `delegation_intent` evidence 进入 `WORKER_CANDIDATE` / `WORKER_PROMOTION` metadata。
- 锁定 Gate 当前是否识别 `origin=user_confirmed_repair`。
- 锁定 ProducerIndex 当前是否识别 `origin=user_confirmed_repair`。
- 锁定 post-normalize IRS source evidence predicate 当前是否识别 `origin=user_confirmed_repair`。
- 锁定 `unspecified_output_missing_producer` 当前投影行为。

### 验收标准

- 当前事实测试通过。
- 没有生产代码行为变更。
- 测试名清楚表达这是 readiness baseline，而不是最终期望行为。

### 风险

- 如果当前测试已经与代码不一致，应先修正测试理解，不应借 R0 改生产行为。

---

## R1. Diagnostic Metadata Foundation

### 目标

标准化 `CompileDiagnostic.metadata` 中供 SPL Editing 使用的 IRS 来源信息。

### 修改范围

候选文件：

- `src/nl2spl/ir/diagnostics.py`
- `src/nl2spl/compiler/irs/projector.py`
- `src/nl2spl/compiler/diagnostic_consolidator.py`
- `src/nl2spl/compiler/report_renderer.py`
- `src/nl2spl/compiler/feedback_report_renderer.py`
- `tests/unit/compiler/irs/test_r3_diagnostic_projector.py`
- `tests/unit/test_diagnostic_consolidator.py`

### 任务清单

- 定义 `metadata["irs_ref"]` 的稳定字段形状。
- 定义 `metadata["authority"]` 或等价 source authority 字段。
- 让 IRS `DiagnosticProjector` 写入 construct type、construct id、slot name、construct path。
- 让 post-normalize IRS diagnostics 带 `authority=post_normalize_irs`。
- 让 promoted stage-local diagnostics 带 `authority=stage_local_irs` 或等价 metadata。
- 让 producer-backed missing output diagnostics 标记 ProducerIndex 相关 authority。
- 明确 grouped / alias / related diagnostic metadata 的字段名。
- 确认 report / feedback renderer 不删除 metadata。
- 确认 DiagnosticConsolidator 在 dedup 后保留 repair-relevant metadata。

### 验收标准

- IRS projector 输出的 diagnostic 可通过 metadata 反查 construct type + slot name。
- same diagnostic kind + different construct slot 在 metadata 上可区分。
- DiagnosticConsolidator 不丢失 `irs_ref` / `authority`。
- feedback rendering 行为不因为 metadata 增加而改变用户可见文本，除非明确更新。

### 测试要求

- `missing_handler` diagnostic 带 `irs_ref.construct_type=EXCEPTION_FLOW` 和 `slot_name=handler_action`。
- `missing_output_producer` diagnostic 可区分 `REQUIRED_OUTPUT.producer` 与 `RESOURCE_CONTRACT_DEMAND.producer`。
- `type_or_contract_ambiguity` diagnostic 可区分 REQUEST_INPUT / CALL_API / INVOKE_WORKER / WORKER_PROMOTION slot 来源。
- Consolidator dedup 后 metadata 仍存在。

### 风险

- metadata 字段变成 ad hoc dump。必须只放 repair / provenance / authority 所需的稳定 payload。

---

## R2. RepairAffordanceSpec + SlotSpec Extension

### 目标

让 IRS slot 声明允许的 repair affordance，但不引入 repair implementation。

### 修改范围

候选文件：

- `src/nl2spl/compiler/construct_registry.py`
- `src/nl2spl/compiler/irs_prompt_builder.py`
- `tests/unit/test_construct_registry.py`
- `tests/unit/test_irs_prompt_builder.py`

### 任务清单

- 新增 `RepairAffordanceSpec` 数据模型。
- 在 `SlotSpec` 上新增 `repair_affordances`。
- 确保 affordance payload 可序列化。
- 确保 affordance 不包含 callable / class reference。
- 为 final / post-normalize slots 补充第一批 affordance。
- 为 promoted worker/delegation slots 补充第一批 affordance。
- 确认 prompt builder 默认不把 repair affordance 注入 stage prompt，除非后续明确需要。
- 更新 registry shape tests。

### 第一批 final / post-normalize slots

- `EXCEPTION_FLOW.handler_action`
- `REQUIRED_OUTPUT.producer`
- `RESOURCE_CONTRACT_DEMAND.producer`
- `REQUEST_INPUT.value_target`
- `CALL_API.api_name`
- `CALL_API.call_action`
- `CALL_API.integration_evidence`
- `INVOKE_WORKER.target_worker`
- `INVOKE_WORKER.handoff_id`
- `INVOKE_WORKER.input_bindings`
- `INVOKE_WORKER.output_bindings`

### 第一批 promoted worker/delegation slots

- `WORKER_PROMOTION.promotion_input_contract`
- `WORKER_PROMOTION.promotion_output_contract`
- `WORKER_PROMOTION.promotion_invocation_point`
- `WORKER_PROMOTION.promotion_result_handoff`
- `WORKER_HANDOFF.target`
- `WORKER_HANDOFF.input_bindings`
- `WORKER_HANDOFF.output_bindings`
- `WORKER_HANDOFF.invocation_site`

### 验收标准

- Registry 可列出每个可修复 slot 的 affordance。
- `construct_registry.py` 不依赖 SPL Editing implementation。
- `SlotSpec` 默认无 affordance，不影响不支持 repair 的 slots。
- 现有 IRS checker 行为不变。

### 测试要求

- `EXCEPTION_FLOW.handler_action` 暴露 missing handler repair affordance。
- `REQUIRED_OUTPUT.producer` 和 `RESOURCE_CONTRACT_DEMAND.producer` 暴露不同但可关联的 producer affordance。
- `WORKER_PROMOTION.*` slots 暴露 delegation/contract repair affordance。
- `DELEGATION_INTENT` 不作为 repair target kind 出现在 affordance 中。

### 风险

- 把 patch strategy 写成自然语言 notes。affordance 必须 machine-readable。

---

## R3. RepairCatalogBuilder

### 目标

建立从 IRS registry 派生 repair catalog 的 runtime index。

### 修改范围

候选新增位置：

- `src/nl2spl/compiler/spl_editing/core/catalog.py`
- `src/nl2spl/compiler/spl_editing/core/model.py`
- `src/nl2spl/compiler/spl_editing/issues/target_ref.py`

候选测试：

- `tests/unit/compiler/spl_editing/test_repair_catalog_builder.py`
- `tests/unit/compiler/spl_editing/test_editable_issue_lookup.py`

### 任务清单

- 定义 `RepairCatalog` 派生模型。
- 定义 `RepairCatalogBuilder.from_construct_registry(...)`。
- 支持通过 `diagnostic.metadata["irs_ref"]` 查找 affordance。
- 支持通过 construct type + slot name + diagnostic kind 查找 affordance。
- 支持 same diagnostic kind different slot 分派。
- 支持 no-affordance diagnostic 返回 non-repairable。
- 支持 catalog payload 快照或 debug dump。

### 验收标准

- RepairCatalog 不再是手写 diagnostic-kind map。
- `missing_handler`、`missing_output_producer`、`type_or_contract_ambiguity` 均可通过 IRS source metadata 找到支持的 affordance。
- 只使用 `diagnostic.kind` 无法完成 lookup 的测试存在。
- Catalog builder 不依赖 LLM、patch applier 或 verifier。

### 测试要求

- `missing_handler` from `EXCEPTION_FLOW.handler_action` 找到 handler affordance。
- `type_or_contract_ambiguity` from `REQUEST_INPUT.value_target` 与 `CALL_API.api_name` 得到不同 affordance。
- `DELEGATION_INTENT` target kind lookup 被拒绝或映射到真实 construct slot。
- 无 `irs_ref` 的 diagnostic 不会被误判 repairable。

### 风险

- 过早创建完整 SPL Editing service。R3 只需要 catalog derivation 和 lookup。

---

## R4. Producer Issue Grouping Policy

### 目标

明确 producer 类 diagnostics 如何分组、去重、暴露为 editable issue。

### 修改范围

候选文件：

- `src/nl2spl/compiler/irs/checkers/post_normalize.py`
- `src/nl2spl/compiler/irs/projector.py`
- `src/nl2spl/compiler/diagnostic_consolidator.py`
- `src/nl2spl/compiler/diagnostic_registry.py`
- `tests/unit/test_post_normalize_resource_contract_irs.py`
- `tests/unit/test_diagnostic_consolidator.py`
- `tests/unit/compiler/spl_editing/test_producer_issue_grouping.py`

### 任务清单

- 定义 producer diagnostic repairability matrix。
- 标记 `missing_output_producer` 为 editable candidate。
- 标记 `unspecified_output_missing_producer` 为 review-only 或默认不可编辑。
- 明确 `resource_kind_mismatch` 不作为 producer patch 处理。
- 明确 `missing_resource_contract` 不作为 producer patch 处理。
- 定义 worker output 与 resource contract demand 的 primary / alias / related 关系。
- 定义一个 patch resolve 多个 diagnostics 时的 related diagnostic metadata。
- 定义 suppressed duplicate ids / related ids 的保留方式。

### 验收标准

- 同一 output 的 worker output diagnostic 与 resource contract demand diagnostic 不会变成两个互相冲突的 editable issues。
- `unspecified_output_missing_producer` 不会默认进入 apply-capable editing flow。
- ProducerIndex authority 可以从 diagnostic metadata 反查。
- Consolidator 不会丢掉 producer issue grouping metadata。

### 测试要求

- required output without producer 生成 editable producer issue。
- resource contract demand required output without producer 生成 related/alias metadata。
- unspecified output without producer 不进入 editable apply flow。
- resource kind mismatch 不使用 InsertProducerStep / BindExistingProducerStep affordance。

### 风险

- 将 resource contract materialization 问题误当成 producer 问题。必须通过 matrix 区分。

---

## R5. Worker/Delegation Exposure Policy

### 目标

明确 stage-local `WORKER_PROMOTION` / `WORKER_HANDOFF` repairable diagnostics 如何成为 final editable issues。

### 修改范围

候选文件：

- `src/nl2spl/pipeline/orchestrator.py`
- `src/nl2spl/compiler/irs/result_store.py`
- `src/nl2spl/compiler/diagnostic_consolidator.py`
- `src/nl2spl/compiler/irs/checkers/worker_delegation.py`
- `src/nl2spl/compiler/feedback_report_renderer.py`
- `tests/unit/pipeline/test_r10_orchestrator_irs_promotion_characterization.py`
- `tests/unit/compiler/irs/test_r10_delegation_intent_cleanup_characterization.py`
- `tests/unit/compiler/spl_editing/test_worker_delegation_issue_exposure.py`

### 任务清单

- 选择并记录 worker/delegation diagnostics exposure policy。
- 确定 selected promotion/mapping 进入 final diagnostics 的规则。
- 确定 grouped `WORKER_PROMOTION` 多 slot issue 的 metadata。
- 确定 delegation-intent-sourced subtype 到真实 construct slot 的映射。
- 确认 final diagnostics 中不会出现 `DELEGATION_INTENT` construct target。
- 确认 `WORKER_PROMOTION` analysis construct diagnostics 不误标 render-blocking。
- 确认 feedback grouped rendering 与 editable issue metadata 一致。

### 推荐策略

采用 selected promoted diagnostics：

```text
stage-local WORKER_PROMOTION / WORKER_HANDOFF
  -> if repairable and delegation/user-actionable
  -> promote/mapped diagnostic enters final diagnostics
  -> carries irs_ref + original_semantic_role metadata
```

### 验收标准

- Editing 从 final diagnostics 即可看到 repairable worker/delegation issue。
- `delegation_intent` 只作为 metadata/source signal 出现。
- `WORKER_PROMOTION` 多 slot 可被 grouped 为一个 editable issue。
- Non-repairable stage-local diagnostics 仍可 suppressed。

### 测试要求

- delegation_intent-sourced incomplete worker promotion 进入 final repairable issue。
- final issue metadata 指向 `WORKER_PROMOTION.*` slots。
- no `DELEGATION_INTENT` construct target in active final repairable diagnostics。
- grouped promotion issue 包含 related slot diagnostics。

### 风险

- 过度 promotion 导致 final diagnostics 噪声增加。只 promotion user-actionable repairable diagnostics。

---

## R6. User-Confirmed Evidence Foundation

### 目标

让 user-confirmed repair 成为 compiler authorities 共同认可的 evidence kind。

### 修改范围

候选文件：

- `src/nl2spl/ir/step_ir.py`
- `src/nl2spl/pipeline/executable_gate.py`
- `src/nl2spl/compiler/producer_index.py`
- `src/nl2spl/compiler/irs/checkers/post_normalize.py`
- `src/nl2spl/pipeline/provenance.py`
- `src/nl2spl/ir/diagnostics.py`
- `tests/unit/test_executable_gate.py`
- `tests/unit/test_producer_index.py`
- `tests/unit/compiler/irs/test_r6_step_checker.py`
- `tests/unit/test_provenance.py`

### 任务清单

- 定义 `USER_CONFIRMED_REPAIR` evidence kind / origin string。
- Gate `classify_origin` 识别 user-confirmed repair。
- Gate renderability rules 对 user-confirmed repair 使用与 source-backed 等价或受限等价的策略。
- ProducerIndex 识别 user-confirmed producer step。
- Post-normalize IRS source evidence predicate 识别 user-confirmed repair。
- ProvenanceAggregator 为 user-confirmed repair 生成 trace。
- Trace / diagnostic metadata 记录 repair patch id、related diagnostic id、user text。
- 明确 AI suggestion 未确认时不算 user-confirmed evidence。

### 验收标准

- `origin=user_confirmed_repair` 的 handler step 不被 Gate 过滤。
- `origin=user_confirmed_repair` 的 producer step 可被 ProducerIndex 识别。
- post-normalize IRS 不再把已确认 repair step 视为 assumed。
- provenance 可区分 source-backed、user-confirmed repair、compiler synthetic、assumed。
- 未确认 suggestion 不影响 SPL renderability。

### 测试要求

- user-confirmed GENERAL_COMMAND passes Gate。
- user-confirmed REQUEST_INPUT passes Gate only when required fields present。
- user-confirmed CALL_API still requires integration evidence if policy requires it。
- user-confirmed producer output resolves missing producer in ProducerIndex.
- unconfirmed AI suggestion remains non-renderable / non-producer。

### 风险

- 将 user confirmation 变成万能 bypass。应保留 command-type guard rails。

---

## R7. Documentation and Skill Sync

### 目标

在 R1-R6 行为稳定后，同步更新 skill、IRS docs、SPL Editing docs 和示例说明。

### 修改范围

候选文件：

- `.codex/skills/irs-knowledge/SKILL.md`
- `.agents/skills/irs-knowledge/SKILL.md`
- `.claude/skills/irs-knowledge/SKILL.md`
- `docs/nl_2_spl_compiler_architecture_irs_v_5 (1).md`
- `docs/implementation/irs-v6/01_irs_v6_architecture.md`
- `docs/implementation/irs-v6/02_irs_checker_extension_contract.md`
- `docs/implementation/irs-v6/08_irs_compiler_subsystem_productization_design.md`
- `docs/design/spl_editing_architecture_design_v2.md`
- `docs/design/spl_editing_prerequisite_modifications.md`
- relevant feedback report examples

### 任务清单

- 更新 IRS skill，加入 repair affordance boundary。
- 更新 IRS docs，加入 `SlotSpec.repair_affordances`。
- 更新 SPL Editing v2，说明 catalog 从 IRS registry 派生。
- 移除 `DELEGATION_INTENT` 作为 repair target 的旧表述。
- 更新 diagnostics / feedback 示例中的 worker promotion grouping 说明。
- 更新 user-confirmed repair evidence 说明。
- 更新 readiness 文档，标记已完成项与后续 SPL Editing 入口。

### 验收标准

- 文档与代码行为一致。
- skill 明确 IRS 不执行 repair。
- SPL Editing 文档不再把 LLM 描述为策略选择者。
- 所有示例 target kind 与 active registry 一致。

### 测试要求

- 文档不需要单独测试，但应结合 R1-R6 的行为测试一起通过。

### 风险

- 文档先于代码落地导致后续 agent 误用。R7 应在 R1-R6 后执行。

---

## 4. Readiness 完成判定

全部阶段完成后，必须满足：

- ✅ `SlotSpec` 可声明 repair affordances。
- ✅ `RepairCatalog` 可从 IRS registry 派生。
- ✅ final diagnostics 可通过 metadata 反查 IRS construct slot。
- ✅ producer issue 有 primary / alias / review-only 语义。
- ✅ worker/delegation repairable diagnostics 可进入 final editable exposure。
- ✅ `delegation_intent` 不作为 construct owner 或 repair target kind。
- ✅ user-confirmed repair evidence 被 Gate / ProducerIndex / IRS / provenance 共同识别。
- ✅ 所有 readiness tests 通过（546 tests）。

**Readiness 已完成（R0-R6）。** 可以进入 SPL Editing 后端实现：

```text
EditableIssueExtractor
SuggestionService
Patch validators
Patch appliers
Verification lanes
CLI / API
```

---

## 5. R7 阶段：Documentation & Skill Sync (已完成)

纯文档同步，不改变 runtime 逻辑：

- 更新 `docs/design/spl_editing_prerequisite_modifications.md` — 标记完成
- 更新 `docs/design/spl_editing_architecture_design_v2.md` — readiness assumptions → 已完成前置
- 更新 IRS skill — 补充 `SlotSpec.repair_affordances`、`DiagnosticIRSRef`、`UserConfirmedRepair` 等新事实
- 一致性检查：旧 key/target/assumption 清理
