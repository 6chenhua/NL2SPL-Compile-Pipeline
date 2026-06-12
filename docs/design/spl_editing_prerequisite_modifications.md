# SPL Editing 前置修改准备清单

日期：2026-06-12  
状态：Planning checklist only  
适用范围：进入 AI-assisted SPL Editing 后端实现前，需要先完成或确认的 IRS / diagnostic / documentation 准备工作。

---

## 0. 文档目的

本文只记录进入 SPL Editing 功能前需要修改或补齐的事项。

本文不记录：

- 具体代码实现方案。
- patch applier / verifier 的内部流程。
- LLM prompt、parser、payload schema 的详细设计。
- UI Diagnostics Console / modal 的交互细节。

核心目标是让 SPL Editing 在进入实现前具备一致的 IRS truth source：

```text
ConstructIRS / SlotSpec
  -> declares requirement gaps
  -> declares repair affordances
  -> projects authoritative diagnostics
  -> lets SPL Editing derive repair catalog
```

---

## 1. IRS Skill 需要更新

需要同步更新以下 skill，避免 Codex / agent 在后续实现时继续使用旧边界：

- `.codex/skills/irs-knowledge/SKILL.md`
- `.agents/skills/irs-knowledge/SKILL.md`
- `.claude/skills/irs-knowledge/SKILL.md`

需要补充的内容：

- `ConstructIRS / SlotSpec` 可以声明 machine-readable repair affordances。
- IRS repair affordance 只是静态元数据，不是 repair engine。
- IRS checker 仍然不得调用 LLM、修改 IR、生成 SPL、应用 patch 或生成 repair suggestion。
- SPL Editing 可以读取 IRS registry 并派生 `RepairCatalog`。
- `repair_affordance` 必须绑定 construct slot，而不是只绑定 diagnostic kind。
- `delegation_intent` 仍然是 source signal / evidence，不是 `ConstructIRS`。
- `WORKER_PROMOTION` / `WORKER_HANDOFF` / `INVOKE_WORKER` 等真实 construct slot 才能承载 delegation repair affordance。

---

## 2. IRS 架构文档需要更新

需要更新或补充以下文档：

- `docs/nl_2_spl_compiler_architecture_irs_v_5 (1).md`
- `docs/implementation/irs-v6/08_irs_compiler_subsystem_productization_design.md`
- `docs/implementation/irs-v6/01_irs_v6_architecture.md`
- `docs/implementation/irs-v6/02_irs_checker_extension_contract.md`
- `docs/design/spl_editing_architecture_design_v2.md`

需要新增或修订的主题：

- IRS-integrated Repair Affordance Metadata。
- `SlotSpec` 除 `missing_diagnostic` 外，还可声明 `repair_affordances`。
- `RepairCatalog` 是从 construct registry 派生的 runtime index，不是平行手写真相源。
- LLM 只能在允许的 patch type 范围内生成 payload。
- IRS 不执行 repair，也不生成 suggestion。
- `CompileDiagnostic` 需要携带足够的 IRS 来源信息，供 Editing 反查 construct slot。
- `type_or_contract_ambiguity` 不能按 diagnostic kind 统一修复，必须按 construct type + slot subtype 分派。
- `DELEGATION_INTENT` 相关旧表述需要迁移为 `WORKER_PROMOTION` / source-signal metadata 表述。

---

## 3. Construct Registry 数据模型需要修改

需要修改 `src/nl2spl/compiler/construct_registry.py` 中的 IRS 数据模型。

需要新增或确认的模型：

- `RepairAffordanceSpec`。
- repair applicability metadata。
- patch type ID 列表。
- default patch type。
- editable artifact level。
- default verification lane。
- required evidence kind。
- resolver / context builder / handler 的字符串 ID。

需要扩展的现有模型：

- `SlotSpec`。

需要保持不变的边界：

- `ConstructIRS` 和 `SlotSpec` 仍然是纯数据。
- `construct_registry.py` 不应 import `spl_editing` patch class。
- `construct_registry.py` 不应包含 applier、verifier、LLM prompt、parser 或 service 逻辑。

---

## 4. 现有 ConstructIRS 定义需要补充 repair affordance

需要为第一批 SPL Editing 可修复 slot 补充 affordance metadata。

MVP 前置必须覆盖：

- `EXCEPTION_FLOW.handler_action`
- `REQUIRED_OUTPUT.producer`
- `RESOURCE_CONTRACT_DEMAND.producer`
- `WORKER_PROMOTION.promotion_input_contract`
- `WORKER_PROMOTION.promotion_output_contract`
- `WORKER_PROMOTION.promotion_invocation_point`
- `WORKER_PROMOTION.promotion_result_handoff`

建议同步审计但不一定进入 MVP apply：

- `REQUEST_INPUT.value_target`
- `CALL_API.api_name`
- `CALL_API.call_action`
- `CALL_API.integration_evidence`
- `INVOKE_WORKER.target_worker`
- `INVOKE_WORKER.handoff_id`
- `INVOKE_WORKER.input_bindings`
- `INVOKE_WORKER.output_bindings`
- `WORKER_HANDOFF.target`
- `WORKER_HANDOFF.input_bindings`
- `WORKER_HANDOFF.output_bindings`
- `WORKER_HANDOFF.invocation_site`
- `GENERAL_COMMAND.source_evidence`

---

## 5. `type_or_contract_ambiguity` 需要 slot-level subtype 化

需要明确 `type_or_contract_ambiguity` 不是单一 repair target。

需要在 IRS slot / diagnostic metadata / repair catalog 中区分：

- request-input target ambiguity。
- call-api integration ambiguity。
- invoke-worker handoff ambiguity。
- worker handoff contract ambiguity。
- worker promotion contract ambiguity。
- delegation-intent-sourced worker promotion ambiguity。

需要删除或避免的表述：

- `DELEGATION_INTENT` 作为 repair target kind。
- `type_or_contract_ambiguity` handler 自行猜测所有 repair strategy。
- 只靠 diagnostic kind 决定 patch type。

---

## 6. Diagnostic projection 需要补充 IRS 来源 metadata

需要修改 diagnostic 投影链路，使 final `CompileDiagnostic` 能反查 IRS slot。

需要补充的信息：

- construct type。
- construct id。
- slot name。
- construct path。
- source authority。
- original source signal metadata。
- grouped diagnostic membership metadata。

需要涉及的组件：

- `src/nl2spl/compiler/irs/projector.py`
- `src/nl2spl/ir/diagnostics.py`
- `src/nl2spl/compiler/diagnostic_consolidator.py`
- feedback / report renderer 中读取 diagnostic metadata 的位置。

需要保持的边界：

- checker 仍输出 `ConstructSatisfactionReport` / `SlotSatisfaction`。
- `DiagnosticProjector` 仍是 IRS diagnostic 的投影入口。
- `CompileDiagnostic.kind` 仍是 projected outcome，不是 construct identity。

---

## 7. RepairCatalog 的来源需要调整

需要把 SPL Editing 中的 `RepairCatalog` 定义为派生 runtime index。

需要准备的能力：

- 从 `SPLConstructRegistry` 读取 slot repair affordances。
- 按 diagnostic 的 IRS 来源查找 repair affordance。
- 按 construct type + slot name + diagnostic kind 查找 repair affordance。
- 支持 grouped issue / alias issue。
- 支持 `WORKER_PROMOTION` 多 slot 归并后的 repair exposure。
- 支持 `REQUIRED_OUTPUT.producer` 与 `RESOURCE_CONTRACT_DEMAND.producer` 的 producer issue 去重或分组。

需要避免：

- 在 Editing service 中维护另一套 diagnostic kind -> patch type 的手写 truth source。
- 在主流程中大量写 `if issue.kind == ...` 分派。

---

## 8. `missing_output_producer` 的 target 语义需要整理

进入 SPL Editing 前需要明确 producer issue 的 target 归属。

至少需要覆盖两类现有 target：

- worker output target。
- resource contract demand target。

需要定义：

- 哪类 target 是 UI primary issue。
- 哪类 target 是 alias / related issue。
- 一个 patch resolve 多个 producer diagnostics 时如何表达。
- `ProducerIndex` authority 如何进入 diagnostic metadata。
- resource kind mismatch 与 missing producer 的边界。

不应在 SPL Editing 阶段再临时决定这些语义。

---

## 9. `delegation_intent` 相关文档需要清理

进入 SPL Editing 前需要统一 delegation 术语。

需要确认：

- `delegation_intent` 是 source signal / evidence。
- `delegation_intent` 不注册为 `ConstructIRS`。
- repair target 应落在 `WORKER_PROMOTION`、`WORKER_HANDOFF`、`CHILD_WORKER` 或 `INVOKE_WORKER` 的 slot 上。
- provenance / trace 中可以保留 source signal 表达，但不能把它当 construct target。
- SPL Editing 的 issue subtype 可以叫 `delegation_intent_contract`，但它必须反查到真实 IRS construct slot。

需要更新存在旧表述的文档、测试说明和示例 report。

---

## 10. User-confirmed repair evidence 需要作为 shared evidence kind 准备

虽然这是 SPL Editing apply 的基础，但进入 repair affordance 设计前需要先确定它在 IRS/Gate/ProducerIndex/provenance 中的位置。

需要准备：

- `USER_CONFIRMED_REPAIR` evidence kind。
- Gate 可识别 user-confirmed repair step。
- ProducerIndex 可识别 user-confirmed producer step。
- IRS source-evidence predicate 可识别 user-confirmed repair evidence。
- ProvenanceAggregator 可表达 user-confirmed repair trace。
- Diagnostic / trace metadata 可记录 repair patch id 与 related diagnostic id。

需要避免：

- 仅在 `StepIR.metadata` 中写 `origin=user_confirmed_repair`，但各 authority 不识别。
- 把 AI suggestion 未确认状态当作 confirmed evidence。

---

## 11. Tests 需要先补齐 registry / metadata 层断言

进入 SPL Editing 实现前，需要先有测试锁定 IRS repair metadata 的静态契约。

需要新增或更新的测试范围：

- `SlotSpec` 支持 repair affordance metadata。
- default construct registry 中指定 slots 暴露预期 affordance。
- construct registry 不依赖 `spl_editing` patch implementation。
- `DiagnosticProjector` 输出 IRS source metadata。
- `RepairCatalogBuilder` 可从 registry 派生 catalog。
- `type_or_contract_ambiguity` 可按 construct slot 分派 subtype。
- `DELEGATION_INTENT` 不作为 IRS construct 或 repair target kind。
- `missing_output_producer` 支持 worker output 与 resource contract demand 两类来源。
- user-confirmed repair evidence 在 Gate / ProducerIndex / provenance 中有一致识别入口。

---

## 12. 文档验收清单

进入 SPL Editing 功能实现前，文档层至少应满足：

- IRS skill 明确 repair affordance boundary。
- IRS v5/v6 文档包含 `SlotSpec.repair_affordances` 概念。
- SPL Editing v2 文档改为从 IRS registry 派生 `RepairCatalog`。
- 所有文档都不把 `DELEGATION_INTENT` 作为 construct owner。
- 所有文档都区分 repair affordance metadata 与 repair implementation。
- 所有文档都声明 LLM 只生成 allowed patch payload。
- 所有文档都声明 final verification 回到 IRS / Gate / ProducerIndex / Renderer。

---

## 13. 代码准备清单

进入 SPL Editing 功能实现前，代码层至少应完成或预留：

- IRS data model 可承载 repair affordance metadata。
- default construct registry 可声明第一批 repair affordances。
- diagnostic projector 可输出 IRS source metadata。
- diagnostic consolidator 保留 repair-relevant metadata。
- report / feedback renderer 不破坏 repair metadata。
- shared evidence kind 支持 user-confirmed repair。
- RepairCatalogBuilder 可从 IRS registry 生成 catalog。
- tests 锁定 registry、diagnostic metadata、catalog derivation 的基础行为。

---

## 14. 非目标

本阶段不实现：

- actual patch applier。
- actual patch verifier。
- actual LLM repair handler。
- editing session storage。
- artifact snapshot store。
- overlay event log。
- CLI / API。
- UI Diagnostics Console。

这些属于 SPL Editing 后续实现阶段。

---

## 15. 最终准备判断

进入 SPL Editing 功能前，需要先把 IRS 从：

```text
slot gap -> diagnostic
```

扩展为：

```text
slot gap -> diagnostic -> allowed repair affordance metadata
```

但不能扩展为：

```text
slot gap -> diagnostic -> IRS executes repair
```

完成本文清单后，SPL Editing 才能在不让 LLM 猜策略、不污染 IRS checker、不绕过 compiler authority 的前提下进入后端实现。
