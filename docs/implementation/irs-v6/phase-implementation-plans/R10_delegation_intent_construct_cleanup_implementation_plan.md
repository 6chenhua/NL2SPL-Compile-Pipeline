# R10 IRS Delegation Intent Construct Cleanup 实施计划

本文档严格基于 `docs/design/irs_delegation_diagnostic_cleanup_plan.md` 制定。实施目标是清除 `DELEGATION_INTENT` 作为 IRS Construct 的错误建模，并将 delegation contract 缺失诊断迁移到真实 owner construct 的 IRS slot satisfaction 路径。

适用范围：

- `DELEGATION_INTENT` registry / checker / diagnostic target 清理。
- `delegation_intent` 作为 source signal / evidence 的保留与迁移。
- `WORKER_CANDIDATE` / `WORKER_PROMOTION` / `WORKER_HANDOFF` 的 delegation evidence 承接。
- stage3.5 IRS diagnostic selective promotion 修正。
- provenance / feedback 中 `delegation_intent:*` target 展示语义修正。

暂不覆盖：

- `RESOURCE_CONTRACT_DEMAND` 删除或降级。
- ResourceEvidenceGraph 实施。
- ProducerIndex / REQUIRED_OUTPUT IRS 重构。
- LLM prompt/schema 改造。

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
RouteAnnotation(semantic_role="delegation_intent")
  -> source signal / evidence
  -> 不注册为 ConstructIRS
  -> 不作为 diagnostic host target

WorkerBoundaryPlanner / WorkerDelegationIRSChecker
  -> WORKER_CANDIDATE / WORKER_PROMOTION / WORKER_HANDOFF instance
  -> 保留 original_semantic_role / source_span_ids provenance

WORKER_PROMOTION / WORKER_HANDOFF ConstructIRS
  -> slot satisfaction
  -> missing promotion_* / handoff_* slot
  -> ConstructSatisfactionReport

DiagnosticProjector
  -> CompileDiagnostic(kind="type_or_contract_ambiguity")
  -> target_ref 指向真实 construct
  -> diagnostic_id 使用 irs_* 形式

PipelineOrchestrator selective promotion
  -> 只提升 delegation source-demanded actionable ambiguity
  -> 不打开全部 stage-local IRS diagnostics

Feedback / provenance renderer
  -> 可以说明 issue 来源于 delegation intent span
  -> 不把 delegation_intent:* 展示为 IRS construct / diagnostic host
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. `DELEGATION_INTENT` 不得作为 `ConstructIRS`、`ConstructInstance`、`ConstructSatisfactionReport.construct_type` 出现。
2. `delegation_intent` 只能作为 `RouteAnnotation.semantic_role`、source signal、metadata、provenance，不得作为 diagnostic host construct。
3. 不得删除或改名 `semantic_role="delegation_intent"`；这是上游 evidence 语义，不是待删除 construct。
4. `type_or_contract_ambiguity` 必须继续由 IRS checker + `DiagnosticProjector` 产生，不能回退到手写 `CompileDiagnostic`。
5. `WORKER_PROMOTION` candidate-only diagnostic 必须 `blocks_completion=True` 且 `blocks_rendering=False`。
6. 不得用 `target_ref.startswith("delegation_intent:")` 作为 final diagnostic promotion 条件。
7. 不得把所有 stage-local IRS diagnostics 无差别合并到 final `compile_diagnostics`。
8. 不得新增 LLM prompt/schema 变更。
9. 不得新增 rule-based semantic fallback，例如通过关键词重新判断 delegation intent。
10. 不得把不存在于当前工作区的 `fact_bridges.py` / `diag_del_*` 写入实施对象。
11. `RESOURCE_CONTRACT_DEMAND` 只做单独审计，不作为本轮 delegation cleanup 的阻塞项。
12. 每个阶段必须有可运行测试或可执行 inventory 证据。

---

## 3. LLM / Rule-based 决策约束

本计划不允许新增任何 LLM 调用、prompt/schema 变更或 rule-based semantic fallback。

允许的确定性逻辑仅限：

- 从现有 `RouteAnnotation.semantic_role` 读取 `delegation_intent`。
- 从已有 `WorkerCandidateIR` / `WorkerPromotion` / `WorkerHandoff` 结构读取 source spans、risks、bindings、handoff hints。
- 基于已有 structured IDs 生成 `worker_promotion:<candidate_id>` 等 target refs。
- 基于 `SlotSatisfaction` 的 missing/satisfied 状态设置 diagnostic metadata。
- 基于 `IRSResultStore` 中已投影 diagnostics 做 selective promotion。
- 基于 metadata/source spans 做 provenance-preserving 过滤。

以下行为必须在实施前提交设计确认：

1. 修改 Stage 2 / Stage 3.5 LLM prompt 或 schema。
2. 新增非结构化文本关键词规则来识别 delegation。
3. 新增 `DELEGATION_INTENT` 的替代 construct。
4. 让 `DiagnosticProjector` 根据 diagnostic kind 反向推断 construct 语义。
5. 将全部 stage-local IRS diagnostics 默认合并进 final diagnostics。
6. 同步删除或降级 `RESOURCE_CONTRACT_DEMAND` IRS。

如果实现中出现“为了兼容先保留 `DELEGATION_INTENT` construct”的倾向，应停止并提交设计确认，不允许直接编码。

---

## 4. Phase 0：Characterization Tests / Inventory

该阶段不改生产代码，只锁定当前行为和待迁移耦合点。

### 4.1 目标

建立迁移前基线，证明当前工作区确实存在：

- `DELEGATION_INTENT` registry construct。
- route annotation 到 `DELEGATION_INTENT` instance 的 active checker path。
- `delegation_intent:*` final diagnostic target。
- orchestrator 基于 `delegation_intent:*` 的 selective promotion。
- `WORKER_PROMOTION` missing slots 默认缺少 `diagnostic_blocks_rendering=False`。

### 4.2 可编辑范围

优先新增：

```text
tests/unit/compiler/irs/test_r10_delegation_intent_cleanup_characterization.py
tests/unit/pipeline/test_r10_orchestrator_irs_promotion_characterization.py
tests/unit/pipeline/test_r10_provenance_delegation_trace_characterization.py
```

只有 unit 层无法覆盖当前行为时，才允许修改：

```text
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
tests/unit/test_input_adapter_pipeline.py
tests/integration/test_llm_adapter_engine_e2e.py
tests/unit/test_diagnostic_consolidator.py
tests/unit/test_feedback_report_renderer.py
```

允许新增测试 helper：

```text
tests/unit/compiler/irs/
tests/unit/pipeline/
```

### 4.3 禁止改动

Phase 0 禁止修改：

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/irs/checkers/worker_delegation.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/provenance.py
src/nl2spl/compiler/feedback_report_renderer.py
```

### 4.4 设计要求

新增测试应表达当前行为，不应把目标行为写成当前断言。

inventory 命令必须执行并记录结果：

```text
rg "DELEGATION_INTENT|delegation_intent:|target_ref=.*delegation_intent|startswith\\(\"delegation_intent:\"\\)" src tests
```

inventory 分类必须区分：

```text
保留：semantic_role="delegation_intent"
保留：metadata.original_semantic_role="delegation_intent"
清理：construct_type="DELEGATION_INTENT"
清理：diagnostic target_ref="delegation_intent:*"
迁移：TraceRecord(target_ref="delegation_intent:*")
```

### 4.5 测试计划

新增或调整 characterization tests 覆盖：

1. `delegation_intent` without contract 当前产生 `type_or_contract_ambiguity`。
2. 当前 diagnostic target_ref 是 `delegation_intent:*`。
3. 当前 provenance / trace 中存在 `delegation_intent:*` target。
4. 当前 diagnostic 通过 orchestrator selective promotion 进入 final diagnostics。
5. 当前 `WORKER_PROMOTION` missing slot 没有显式 `diagnostic_blocks_rendering=False`。
6. complete handoff 当前不产生 ambiguity。

### 4.6 验收标准

Phase 0 通过条件：

1. 所有新增 characterization tests 通过，或明确标记为只记录当前失败行为的 `xfail` 并附原因。
2. inventory 输出被保存到测试注释或阶段验收说明。
3. 没有生产代码 diff。
4. 没有新增 skip。
5. 没有修改 LLM prompt/schema。

### 4.7 PM 审核清单

审核时必须检查：

1. Phase 0 是否真的没有生产代码修改。
2. inventory 是否覆盖 `src` 和 `tests`。
3. 是否错误地把 `semantic_role="delegation_intent"` 列为待删除对象。
4. 是否错误地提到当前工作区不存在的 `diag_del_*` / `fact_bridges.py`。
5. 是否证明 orchestrator 仍使用 `startswith("delegation_intent:")`。

---

## 5. Phase 1：迁移 WorkerDelegationIRSChecker

该阶段先改 checker，不先删 registry。

### 5.1 目标

让 `delegation_intent` route annotation 不再被抽取为 `DELEGATION_INTENT` construct instance，而是作为 `WORKER_CANDIDATE` / `WORKER_PROMOTION` 的 evidence。

### 5.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/irs/checkers/worker_delegation.py
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
tests/integration/test_llm_adapter_engine_e2e.py
tests/unit/test_input_adapter_pipeline.py
```

### 5.3 禁止改动

Phase 1 禁止修改：

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/irs/projector.py
src/nl2spl/compiler/diagnostic_registry.py
```

### 5.4 设计要求

`WorkerDelegationIRSChecker` 必须：

```text
不再 include supported construct DELEGATION_INTENT
不再从 routes.get_annotations_by_role("delegation_intent") 创建 DELEGATION_INTENT ConstructInstance
不再生成 construct_id="delegation_intent:<span_id>"
不再调用 _check_delegation_intent
```

`delegation_intent` evidence 必须进入：

```text
WORKER_CANDIDATE metadata/source_span_ids
WORKER_PROMOTION metadata/source_span_ids
related_edges 或 metadata 中的 original_semantic_role
```

如果 route annotation 的 `span_id` 不在 `candidate.source_span_ids` 中，必须通过显式合并策略保留：

```text
source_span_ids += [route_annotation.span_id]
metadata.original_route_annotation_id = <annotation id 或 span id>
metadata.original_semantic_role = "delegation_intent"
metadata.original_source_span_ids = [...]
```

不得只依赖 `WorkerPlanIR.candidates` 当前已有的 `source_span_ids`，否则 Phase 4 无法证明 final diagnostic 源自 delegation source signal。

不得包含：

```text
construct_type="DELEGATION_INTENT"
diagnostic_target_ref="delegation_intent:<span_id>"
```

### 5.5 测试计划

新增或修改测试覆盖：

1. route annotation `delegation_intent` 不产生 `DELEGATION_INTENT` instance。
2. 同一 annotation 产生或关联到 `WORKER_CANDIDATE` / `WORKER_PROMOTION`。
3. candidate 缺 contract 时 `WORKER_PROMOTION` report 有 missing promotion slot。
4. missing promotion slot diagnostic kind 为 `type_or_contract_ambiguity`。
5. source_span_ids 保留原始 delegation span。
6. complete handoff 情况不产生 ambiguity。

### 5.6 验收标准

Phase 1 通过条件：

1. `rg 'construct_type="DELEGATION_INTENT"|construct_id=f"delegation_intent:' src/nl2spl/compiler/irs/checkers/worker_delegation.py` 无命中。
2. `WorkerDelegationIRSChecker.supported_construct_types` 不包含 `DELEGATION_INTENT`。
3. `delegation_intent` without contract 仍能得到 `WORKER_PROMOTION` missing slot report。
4. 相关 IRS checker tests 通过。
5. 不修改 registry。

### 5.7 PM 审核清单

审核时必须检查：

1. checker 是否先于 registry 完成迁移。
2. 是否保留 `delegation_intent` 作为 evidence。
3. 是否没有引入新的 route-level construct。
4. 是否没有新增手写 `CompileDiagnostic`。
5. 是否没有依赖 raw text / keyword。

---

## 6. Phase 2：保证 Delegation Signal 不丢失

本阶段分为 Phase 2A / Phase 2B。Phase 2A 是优先路径；只有证明 Stage 3.5 / WorkerPlanIR 无法表达某类 confirmed `delegation_intent` 时，才允许进入 Phase 2B 的兼容路径。

### 6.1 目标

确保每个 confirmed `delegation_intent` source signal 都被表示为 `WORKER_CANDIDATE` / `WORKER_PROMOTION`，或产生明确 planner/checker warning。

### 6.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/irs/checkers/worker_delegation.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
tests/unit/pipeline/stages/
```

只有当现有 checker 无法保证 source signal 表示时，才允许修改 Stage 3.5 worker boundary planner。

### 6.3 禁止改动

Phase 2 禁止修改：

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/irs/projector.py
```

### 6.4 设计要求

### 6.4.1 Phase 2A：Stage 3.5 / WorkerPlanIR authoritative representation

优先路径：

```text
Stage 3.5 deterministic materializer / WorkerPlanIR
-> confirmed delegation_intent
-> CandidateTaskUnitIR / WorkerCandidateIR
-> WORKER_CANDIDATE / WORKER_PROMOTION instance
```

权威边界：

```text
WorkerBoundaryPlanner / WorkerPlanIR 是 candidate/promotion representation 的主 authority。
WorkerDelegationIRSChecker 只消费 structured candidate/promotion evidence。
```

Phase 2A 不允许 checker 从 bare route annotation 直接制造完整 candidate / promotion IR。

### 6.4.2 Phase 2B：受限兼容路径

如果 Phase 2A 证明当前 WorkerPlanIR 缺少某类 confirmed `delegation_intent` 的 representation，则允许 checker 创建 source-demanded candidate-only report，但必须满足：

```text
metadata.synthetic_from_route_annotation = True
metadata.original_semantic_role = "delegation_intent"
metadata.original_route_annotation_id = ...
metadata.original_source_span_ids = [...]
renderable = False
frontier_status = "cutline_partial" 或 "cutline_blocked"
```

该兼容 report 只能用于 IRS diagnostic/provenance，不得被 renderer、gate 或 WorkerAssembler 当成 materialized worker construct。

禁止路径：

```text
checker 直接把 bare route annotation 当作完整 WORKER_CANDIDATE / WORKER_PROMOTION IR
checker 生成可渲染 worker / handoff / invoke construct
checker 直接创建 CompileDiagnostic
```

最终必须满足：

```text
confirmed delegation_intent
-> WORKER_CANDIDATE
or WORKER_PROMOTION
or explicit planner/checker warning
```

不得出现：

```text
delegation_intent source signal
-> no candidate
-> no promotion
-> no diagnostic/warning
-> only TraceRecord remains
```

如果新增 warning，必须是 internal planner/checker warning，不得直接进入 feedback report，除非经 construct IRS diagnostic 投影。

### 6.5 测试计划

新增测试覆盖：

1. 有 `delegation_intent` annotation 但无 worker candidate 时，不静默丢失。
2. 该 signal 至少产生 candidate-only promotion report 或 explicit warning。
3. warning/report 带原 source_span_ids。
4. 只有 provenance trace、不产生 report/warning 的情况失败。
5. Phase 2B 兼容 report 必须带 `metadata.synthetic_from_route_annotation=True`。
6. Phase 2B 兼容 report 不得被标记为 renderable。

### 6.6 验收标准

Phase 2 通过条件：

1. 每个 confirmed `delegation_intent` 在测试中可追踪到 candidate/promotion/warning。
2. 没有使用 `DELEGATION_INTENT` construct 兜底。
3. 不新增用户可见的非 IRS diagnostic。
4. Stage 3.5 / IRS checker 相关测试通过。
5. 如使用 Phase 2B，必须有测试证明 checker 没有制造 materialized worker/handoff construct。

### 6.7 PM 审核清单

审核时必须检查：

1. 是否存在 signal 静默丢失路径。
2. warning 是否误进 feedback report。
3. 是否用 `TraceRecord` 代替 construct satisfaction report。
4. source span 是否贯穿 candidate/promotion/warning。
5. checker 是否越权承担 planner/materializer 职责。
6. `synthetic_from_route_annotation` 是否只用于 candidate-only analysis report。

---

## 7. Phase 3：修正 WORKER_PROMOTION Diagnostic Render Blocking 语义

### 7.1 目标

`WORKER_PROMOTION` 是 candidate-only analysis construct，不是 renderable SPL construct。其 missing promotion slot 应表示 completion gap，而不是 render-blocking。

### 7.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/irs/checkers/worker_delegation.py
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
tests/unit/compiler/irs/test_r3_diagnostic_projector.py
```

只有 slot-level 显式设置无法满足时，才允许修改：

```text
src/nl2spl/compiler/irs/projector.py
```

### 7.3 禁止改动

Phase 3 禁止修改：

```text
src/nl2spl/compiler/diagnostic_registry.py
src/nl2spl/compiler/construct_registry.py
src/nl2spl/pipeline/orchestrator.py
```

### 7.4 设计要求

以下 missing slots 必须显式设置：

```text
promotion_input_contract
promotion_output_contract
promotion_invocation_point
promotion_result_handoff
```

缺失时：

```text
diagnostic_kind = "type_or_contract_ambiguity"
diagnostic_target_ref = "worker_promotion:<candidate_id>"
diagnostic_blocks_rendering = False
```

投影后：

```text
blocks_completion = True
blocks_rendering = False
```

### 7.5 测试计划

新增或修改测试覆盖：

1. missing input contract -> diagnostic blocks_rendering=False。
2. missing output contract -> diagnostic blocks_rendering=False。
3. missing invocation point -> diagnostic blocks_rendering=False。
4. missing result handoff -> diagnostic blocks_rendering=False。
5. diagnostic target_ref 为 `worker_promotion:<candidate_id>`。
6. blocks_completion 仍为 True。
7. 同一 candidate 缺多个 promotion slot 时，每条 projected diagnostic 都 `blocks_rendering=False`。

### 7.6 验收标准

Phase 3 通过条件：

1. `WORKER_PROMOTION` missing slots 不再依赖 `not report.renderable` 推导 blocks_rendering。
2. `type_or_contract_ambiguity` severity / blocks_completion 仍来自 `DiagnosticRegistry`。
3. `DiagnosticProjector` 未被扩大成 construct semantic dispatcher。
4. IRS projector tests 和 worker delegation checker tests 通过。

### 7.7 PM 审核清单

审核时必须检查：

1. 是否每个 promotion missing slot 都显式设置 `diagnostic_blocks_rendering=False`。
2. 是否错误修改了 diagnostic registry 的全局 `type_or_contract_ambiguity` 语义。
3. 是否仍有 `target_ref="delegation_intent:*"`。
4. 是否保持 `blocks_completion=True`。

---

## 8. Phase 4：重写 Orchestrator Selective Promotion

### 8.1 目标

删除基于 `delegation_intent:*` target 的 selective promotion，改为基于真实 construct target + source-demand provenance 的 selective promotion。

### 8.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/irs/projector.py
tests/unit/test_diagnostic_consolidator.py
tests/unit/test_input_adapter_pipeline.py
tests/integration/test_llm_adapter_engine_e2e.py
```

如需更容易测试，可新增：

```text
tests/unit/pipeline/test_orchestrator_irs_promotion.py
```

### 8.3 禁止改动

Phase 4 禁止修改：

```text
src/nl2spl/compiler/irs/policy.py
src/nl2spl/compiler/diagnostic_consolidator.py
src/nl2spl/compiler/construct_registry.py
```

不得把 `include_stage_local_diagnostics_in_compile` 默认改为 True。

### 8.4 设计要求

删除：

```text
target_ref.startswith("delegation_intent:")
```

改为：

```text
diagnostic.kind == "type_or_contract_ambiguity"
and target_ref prefix in {
  "worker_promotion:",
  "worker_handoff:",
  "child_worker:",
  "invoke_worker:",
  "call_api:"
}
and source_span_ids 非空
and diagnostic.metadata.original_semantic_role == "delegation_intent"
```

本计划选择以下机制作为默认实现：

```text
DiagnosticProjector 将 ConstructSatisfactionReport.metadata 中的安全 provenance 字段投影到 CompileDiagnostic.metadata。
```

至少投影：

```text
original_semantic_role
original_route_annotation_id
original_source_span_ids
synthetic_from_route_annotation
promotion_candidate_id
```

`DiagnosticProjector` 不得根据这些 metadata 推断 diagnostic kind、severity、blocks_completion 或 construct 语义；它只做 metadata 复制。

如果无法采用 projector metadata projection，必须提交设计确认后才允许改为 orchestrator 通过 `IRSResultStore` reports 回查。禁止在 orchestrator 中重新解释 raw route annotations。

### 8.5 测试计划

新增测试覆盖：

1. `worker_promotion:*` 的 delegation-sourced `type_or_contract_ambiguity` 被提升。
2. 无 source_span_ids 的 diagnostic 不提升。
3. 非 delegation-sourced stage-local ambiguity 不提升。
4. `delegation_intent:*` target 不再是提升条件。
5. `include_stage_local_diagnostics_in_compile=False` 时不提升全部 stage-local diagnostics。
6. final diagnostic target_ref 为真实 construct。
7. `DiagnosticProjector` 将 `original_semantic_role="delegation_intent"` 投影到 `CompileDiagnostic.metadata`。
8. 没有 delegation metadata 的同 kind / 同 target prefix diagnostic 不提升。

### 8.6 验收标准

Phase 4 通过条件：

1. `rg 'startswith\\("delegation_intent:"\\)' src/nl2spl/pipeline/orchestrator.py` 无命中。
2. `irs_promoted_diagnostics` 仍只包含 selective delegation diagnostics。
3. final diagnostics 中保留 `type_or_contract_ambiguity`。
4. final diagnostics 中不出现 `target_ref="delegation_intent:*"`。
5. Orchestrator / consolidator tests 通过。
6. Projector metadata projection tests 通过。

### 8.7 PM 审核清单

审核时必须检查：

1. 是否误开全局 stage-local diagnostics。
2. selective promotion 是否只看真实 construct target。
3. 是否能证明 diagnostic 源自 delegation source signal。
4. 是否保留 source_span_ids。
5. 是否没有新增 D10/手写 diagnostic path。
6. `DiagnosticProjector` 是否只复制 metadata，没有承担 semantic dispatcher 职责。

---

## 9. Phase 5：删除 Registry 中的 DELEGATION_INTENT

### 9.1 目标

在 checker 与 final promotion 迁移完成后，删除 `DELEGATION_INTENT` registry construct 和依赖它的 active tests。

### 9.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/construct_registry.py
tests/unit/test_construct_registry.py
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
tests/unit/test_irs_prompt_builder.py
```

### 9.3 禁止改动

Phase 5 禁止修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/irs/checkers/worker_delegation.py
src/nl2spl/compiler/irs/projector.py
```

除非 Phase 1-4 验收发现遗漏，否则本阶段不应再改生产逻辑。

### 9.4 设计要求

删除：

```text
ConstructIRS(construct_type="DELEGATION_INTENT")
registry tests expecting DELEGATION_INTENT
prompt builder mappings expecting DELEGATION_INTENT
checker tests expecting DELEGATION_INTENT reports
```

保留：

```text
semantic_role="delegation_intent"
metadata.original_semantic_role="delegation_intent"
source signal / route annotation / provenance source span
```

### 9.5 测试计划

修改测试覆盖：

1. registry 不包含 `DELEGATION_INTENT`。
2. IRS prompt builder 不渲染 `CONSTRUCT: DELEGATION_INTENT`。
3. worker delegation tests 断言 no `DELEGATION_INTENT` reports。
4. semantic role `delegation_intent` 仍可作为 evidence 被使用。

### 9.6 验收标准

Phase 5 通过条件：

1. `registry.has("DELEGATION_INTENT") == False`。
2. `rg 'DELEGATION_INTENT' src tests` 在生产 `src/nl2spl` 和 active tests 中无命中。
3. 只允许文档、迁移说明或 historical comments 命中大写 `DELEGATION_INTENT`。
4. `semantic_role="delegation_intent"` 仍允许存在。
5. Registry / prompt builder / checker tests 通过。

### 9.7 PM 审核清单

审核时必须检查：

1. 是否只删除 construct，不删除 source signal。
2. 是否仍有 active tests 期待 `DELEGATION_INTENT`。
3. 是否在 prompt builder 中残留 `DELEGATION_INTENT`。
4. 是否没有动 `RESOURCE_CONTRACT_DEMAND`。

---

## 10. Phase 6：清理 Provenance / Feedback 的 delegation_intent:* Target 展示语义

### 10.1 目标

移除 `delegation_intent:*` 作为 diagnostic/construct target 的展示语义。feedback 可以说明 issue 来源于 delegation intent span，但不能把它当 IRS construct。

### 10.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/provenance.py
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/compiler/report_renderer.py
tests/unit/test_feedback_report_renderer.py
tests/unit/test_report_renderer.py
tests/unit/test_input_adapter_pipeline.py
```

### 10.3 禁止改动

Phase 6 禁止修改：

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/irs/checkers/worker_delegation.py
src/nl2spl/pipeline/orchestrator.py
```

### 10.4 设计要求

需要迁移的对象：

```text
TraceRecord(target_ref="delegation_intent:...")
feedback/report 中把 delegation_intent:* 格式化为 construct target 的逻辑
```

当前 `TraceRecord` 没有 `metadata` 字段。本阶段默认采用方案 A，不扩展 `TraceRecord` schema：

```text
TraceRecord.target_ref = "source_signal:delegation_intent:<name>"
TraceRecord.explanation 保留原始 delegation intent 说明
TraceRecord.source_span_ids 保留原始 source spans
```

方案 B 仅在单独设计确认后允许：

```text
扩展 TraceRecord.metadata，并更新所有序列化 / renderer / tests。
```

方案 C 可作为更激进替代，但必须单独确认：

```text
删除 standalone delegation-intent TraceRecord，只依赖 WORKER_PROMOTION diagnostic metadata / report metadata。
```

诊断 target 表达：

```text
diagnostic target_ref:
  worker_promotion:<candidate_id>
  worker_handoff:<handoff_id>
  child_worker:<worker_id>
  invoke_worker:<step_id>
  call_api:<step_id>
```

允许：

```text
feedback 展示“该 issue 来源于 delegation intent span”
```

禁止：

```text
feedback 把 delegation_intent:* 展示成 IRS construct / diagnostic host
```

### 10.5 测试计划

新增或修改测试覆盖：

1. feedback report 不显示 `delegation_intent:*` 作为 target。
2. feedback report 可显示原始 source span / role 说明。
3. report renderer 不把 `delegation_intent:*` 格式化为 construct。
4. provenance trace 不再把 `delegation_intent:*` 作为 primary target，或明确降级为 metadata/source trace。
5. 如果采用默认方案 A，trace target 为 `source_signal:delegation_intent:<name>`，且 renderer 不把它当 construct。

### 10.6 验收标准

Phase 6 通过条件：

1. `rg 'delegation_intent:' src/nl2spl` 无生产 diagnostic / construct target 命中。
2. 默认方案 A 下，只允许 `source_signal:delegation_intent:` 作为 provenance-only trace target。
3. `rg 'startswith\\("delegation_intent:"\\)' src/nl2spl` 无生产路径命中。
4. feedback report 中没有 `delegation_intent:*` diagnostic host。
5. provenance 仍能追踪原始 source span。
6. Feedback/report renderer tests 通过。

### 10.7 PM 审核清单

审核时必须检查：

1. 是否误删 source provenance。
2. 是否仍把 `delegation_intent:*` 当 target 展示。
3. 是否错误新增 `diag_del_*` 相关逻辑。
4. 是否保持用户可解释性。
5. 是否未经确认扩展了 `TraceRecord` schema。

---

## 11. Decision Gate：RESOURCE_CONTRACT_DEMAND 单独审计

### 11.1 目标

明确 `RESOURCE_CONTRACT_DEMAND` 不属于本轮 delegation cleanup 实施范围。它是否保留为 IRS construct，必须独立审计。

### 11.2 可选方案

允许提交但必须评审确认的方案包括：

```text
方案 A：保留 RESOURCE_CONTRACT_DEMAND，补充 approved compiler materialization construct 架构证明。
方案 B：降级为 legacy compatibility，不进入 final diagnostics。
方案 C：删除 RESOURCE_CONTRACT_DEMAND IRS，将诊断归属迁移到 REQUIRED_OUTPUT / FileSpec / VariableSpec / resolver / ProducerIndex owner。
```

推荐先执行独立审计，不在本轮 PR 中选择 A/B/C。

### 11.3 必须明确的问题

方案确认文档必须回答：

1. `RESOURCE_CONTRACT_DEMAND` 是否有独立 construct identity。
2. 它是否只是 `ResourceContractPlan` planner demand。
3. 它与 `REQUIRED_OUTPUT` 的权威边界。
4. 它与 FileSpec / VariableSpec materialization checker 的权威边界。
5. 它与 ProducerIndex 的 producer evidence 边界。
6. 它是否进入 feedback report。

### 11.4 验收标准

该决策门禁通过条件：

1. 本轮 delegation cleanup 没有删除或新增 `RESOURCE_CONTRACT_DEMAND` 行为。
2. 文档明确它是待审对象。
3. 后续单独计划获 PM 批准后方可进入 resource cleanup。

---

## 12. 端到端验收场景

最终必须具备以下 E2E 或高保真集成覆盖：

1. **Delegation intent without contract**
   - 输入含 confirmed `delegation_intent`。
   - 没有 valid worker/API handoff contract。
   - 期望生成 `type_or_contract_ambiguity`。
   - diagnostic_id 以 `irs_` 开头。
   - target_ref 为 `worker_promotion:*` 或其他真实 construct。
   - target_ref 不是 `delegation_intent:*`。
   - blocks_completion=True。
   - blocks_rendering=False。

2. **Delegation intent with complete handoff**
   - 输入含 confirmed `delegation_intent`。
   - 有 target、input binding、output binding、invocation site。
   - 期望不产生 delegation ambiguity。
   - 不产生 `DELEGATION_INTENT` report。

3. **Source signal preservation**
   - 输入含 delegation span。
   - 期望 final diagnostic 或 report metadata 保留原 `source_span_ids`。
   - feedback 可解释 issue 来源于 delegation intent span。
   - feedback 不把 `delegation_intent:*` 当 construct target。

4. **Stage-local diagnostics remain selective**
   - stage3.5 存在多个 IRS diagnostics。
   - 只有 delegation source-demanded actionable ambiguity 被提升。
   - `include_stage_local_diagnostics_in_compile=False` 时不合并全部 stage-local diagnostics。

5. **Registry cleanup**
   - `SPLConstructRegistry.default().has("DELEGATION_INTENT") == False`。
   - `WORKER_CANDIDATE` / `WORKER_PROMOTION` / `WORKER_HANDOFF` 仍存在。

---

## 13. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐 `docs/design/irs_delegation_diagnostic_cleanup_plan.md`。
2. 是否扩大到 `RESOURCE_CONTRACT_DEMAND` 实施。
3. 是否新增 LLM prompt/schema 改动。
4. 是否新增 rule-based semantic fallback。
5. 是否删除了 `semantic_role="delegation_intent"`。
6. 是否仍有 `ConstructIRS("DELEGATION_INTENT")`。
7. 是否仍有 `ConstructInstance(construct_type="DELEGATION_INTENT")`。
8. 是否仍有 `ConstructSatisfactionReport(construct_type="DELEGATION_INTENT")`。
9. 是否仍有 final diagnostic `target_ref="delegation_intent:*"`。
10. 是否仍有 orchestrator `startswith("delegation_intent:")`。
11. 是否把所有 stage-local diagnostics 合并进 final diagnostics。
12. 是否新增手写 `CompileDiagnostic(kind="type_or_contract_ambiguity")`。
13. 是否设置 promotion missing slot `diagnostic_blocks_rendering=False`。
14. 是否保持 `blocks_completion=True`。
15. 是否保留 source_span_ids。
16. 是否有 tests 只检查“有 diagnostic”但不检查 target / blocks flags。
17. 是否有 skip / xfail 没有明确生命周期。
18. 是否把当前工作区不存在的 `diag_del_*` / `fact_bridges.py` 当实施对象。

---

## 14. 阶段完成顺序

推荐顺序：

```text
Phase 0      Characterization tests / inventory
Phase 1      迁移 WorkerDelegationIRSChecker
Phase 2A     确认 Stage 3.5 / WorkerPlanIR 能表示 confirmed delegation_intent
Phase 2B     必要时实现受限 checker compatibility report
Phase 3      修正 WORKER_PROMOTION render blocking 语义
Phase 4A     Projector metadata projection
Phase 4B     重写 orchestrator selective promotion
Phase 5      删除 registry 中的 DELEGATION_INTENT
Phase 6A     选择 TraceRecord 处理策略，默认 source_signal target
Phase 6B     清理 provenance / feedback target 展示语义
Decision Gate RESOURCE_CONTRACT_DEMAND 单独审计
```

其中：

- Phase 0 可立即开工。
- Phase 1 必须在 Phase 5 前完成。
- Phase 2 必须在 Phase 4 前完成，否则 selective promotion 可能没有真实 construct target。
- Phase 3 必须在 Phase 4 前完成，否则 final promoted diagnostic 可能错误 blocks_rendering。
- Phase 4A 必须在 Phase 4B 前完成，除非 PM 批准改用 IRSResultStore report lookup。
- Phase 4 必须在 Phase 5 前完成，否则删除 registry 后 final diagnostic 可能丢失。
- Phase 6 必须在 Phase 4 和 Phase 5 后完成，否则 target 语义仍可能被旧 diagnostic 路径污染。
- `RESOURCE_CONTRACT_DEMAND` 审计必须独立进行，不阻塞本轮 delegation cleanup。
