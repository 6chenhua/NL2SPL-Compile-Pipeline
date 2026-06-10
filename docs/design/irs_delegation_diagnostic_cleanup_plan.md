# IRS Construct 边界修正版方案

## 1. 背景

`type_or_contract_ambiguity` 原先有两类来源：

1. IRS 路径：
   `ConstructIRS -> ConstructSatisfactionReport -> DiagnosticProjector -> CompileDiagnostic`
2. 手写 diagnostic 路径：
   D10 / analyzer / post-normalize legacy checker 直接创建 `CompileDiagnostic`

清理手写 diagnostic 的方向是正确的：构件级信息缺口应由 IRS slot satisfaction 表达，并由 `DiagnosticProjector` 投影为 `CompileDiagnostic`。

但此前方案为了替代 D10 手写诊断，新增了 `DELEGATION_INTENT` IRS。这一做法越过了 IRS 的构件边界：

- `delegation_intent` 是 `RouteAnnotation.semantic_role` / source signal。
- 它可以作为 worker boundary / handoff / promotion 的 evidence。
- 它本身不是 SPL construct，也不是已经明确 materialized 的 compiler construct。

因此本方案重写 IRS construct 边界，并重新定义 delegation 与 resource contract 诊断的归属。

## 2. IRS 正确定义

IRS 是 SPL construct 的 Information Requirements Specification：

```text
SPL Grammar
+ Requirement Semantics
+ Compiler Policy
-> ConstructIRS
```

IRS 回答的问题是：

- 一个 construct 是否可以 materialize；
- materialize 后哪些 slot 是语法必须；
- 哪些 slot 是 semantic completeness 必须；
- 缺 slot 时应投影什么 diagnostic；
- 是否允许 partial rendering；
- 缺失 slot 是否阻止渲染。

IRS 不是：

- route annotation registry；
- planner demand registry；
- diagnostic trigger registry；
- 任意可诊断对象的规则集合；
- 修复、补全、推断或渲染 SPL 的执行器。

## 3. ConstructIRS 准入边界

一个对象只有满足以下条件，才允许注册为 `ConstructIRS`：

1. 它对应 SPL grammar construct，或被架构文档明确承认为 compiler materialization / analysis construct。
2. 它有稳定的 construct identity，可以从 structured IR 中提取 instance。
3. 它有独立的信息 slot，且这些 slot 可以通过 structured evidence 检查。
4. 它不是单纯的 source signal、route label、planner record、binding record 或 diagnostic kind。
5. 它产生的 diagnostic 不能更自然地归属于已有 construct 的 missing slot。

新增 IRS 前必须回答：

```text
1. 它代表哪个 SPL construct 或已批准的 compiler construct？
2. 它有哪些 required slots？
3. 每个 slot 由哪些 structured evidence 满足？
4. 哪个 stage materialize 或 demand 该 construct instance？
5. 如果不新增 IRS，哪个已有 construct 应拥有这个 diagnostic？
6. 为什么已有 construct 不足以表达这个信息缺口？
```

如果第 5 条有明确答案，应优先使用已有 construct。

## 4. 对象分类

### 4.1 可以成为 ConstructIRS

明确合理的 SPL construct：

- `EXCEPTION_FLOW`
- `MAIN_WORKER`
- `CHILD_WORKER`
- `GENERAL_COMMAND`
- `REQUEST_INPUT`
- `CALL_API`
- `INVOKE_WORKER`
- `REQUIRED_OUTPUT`

可接受但必须受控的 compiler analysis / materialization construct：

- `WORKER_CANDIDATE`
- `WORKER_PROMOTION`
- `WORKER_HANDOFF`

这三类 worker analysis construct 不是普通 SPL 渲染 construct，但已有架构文档将其用于 worker boundary planning / promotion / handoff consistency。它们可以作为 IRS 的扩展边界存在，但不得继续把任意 route signal 提升成同级 construct。

### 4.2 只能作为 source signal / evidence

以下对象不得注册为 `ConstructIRS`：

- `RouteAnnotation.semantic_role`
- `delegation_intent`
- `input_contract` / `output_contract` annotation
- `required_output` annotation
- section title prior
- list item structural evidence
- source span id
- source packet id
- route refinement label

这些对象只能用于：

- 触发 construct planning；
- 支持 construct instance extraction；
- 满足某个 construct slot；
- 作为 diagnostic provenance。

### 4.3 只能作为 planner demand / internal IR

以下对象默认不得注册为 `ConstructIRS`：

- `ConstructPlan`
- `ResourceContractPlan`
- `ResourceContractDemandIR`
- `ResourceContractBindingIR`
- resolver record
- ProducerIndex entry
- worker boundary planner record

它们是 pipeline 内部的 planning / binding / resolution artifact。它们可以向 IRS checker 提供 evidence，但不自动拥有 construct 身份。

### 4.4 只能作为 diagnostic kind

以下对象是诊断结果，不是 construct：

- `type_or_contract_ambiguity`
- `missing_output_producer`
- `missing_resource_contract`
- `resource_kind_mismatch`
- `assumed_command_not_renderable`
- `missing_handler`

它们应出现在：

- `SlotSpec.missing_diagnostic`
- `SlotSatisfaction.diagnostic_kind`
- `DiagnosticProjector` 输出的 `CompileDiagnostic.kind`

不得用 diagnostic kind 反向创建一个 IRS construct。

## 5. Delegation 修正版设计

### 5.1 设计结论

删除 `DELEGATION_INTENT` IRS。

`delegation_intent` 只能作为 evidence/source signal，参与以下 construct 的实例提取或 slot 检查：

- `WORKER_CANDIDATE`
- `WORKER_PROMOTION`
- `WORKER_HANDOFF`
- `CHILD_WORKER`
- `INVOKE_WORKER`
- 必要时的 `CALL_API`

当 source 中存在 delegation intent，但缺少足够 worker/API contract 时，diagnostic 应由真实拥有缺口的 construct 产生：

- candidate 无法 promotion：由 `WORKER_PROMOTION` missing slot 产生；
- 已 materialized handoff 但绑定不完整：由 `WORKER_HANDOFF` missing slot 产生；
- 已 materialized `INVOKE_WORKER` 但缺 target/binding：由 `INVOKE_WORKER` missing slot 产生；
- 已 materialized child worker 但 contract 不完整：由 `CHILD_WORKER` missing slot 产生；
- API call 只有意图或 mention、缺少 call contract：由 `CALL_API` missing slot 产生。

### 5.2 推荐主路径

对当前替代 D10 的问题，主路径应是：

```text
RouteAnnotation(semantic_role="delegation_intent")
-> structured evidence
-> WORKER_CANDIDATE instance
-> WORKER_PROMOTION instance
-> missing promotion_* slot
-> ConstructSatisfactionReport
-> DiagnosticProjector
-> CompileDiagnostic(kind="type_or_contract_ambiguity")
```

`target_ref` 应指向真实 construct，例如：

```text
worker_promotion:<candidate_id>
worker_handoff:<handoff_id>
invoke_worker:<step_id>
child_worker:<worker_id>
```

原始 delegation span 应保留在：

```text
source_span_ids
source_section_id
source_packet_id
metadata.route_annotation_id
metadata.original_semantic_role = "delegation_intent"
```

不得再使用 `delegation_intent:<span_id>` 作为 IRS construct target，因为这会把 source signal 伪装成 construct。

### 5.3 Slot 归属

`WORKER_PROMOTION` 应负责 candidate 能否提升为 child worker / handoff 的必要条件：

- `promotion_input_contract`
- `promotion_output_contract`
- `promotion_invocation_point`
- `promotion_result_handoff`

这些 slot 缺失时，可以投影：

```text
type_or_contract_ambiguity
```

`WORKER_HANDOFF` 应负责已存在 handoff 的一致性：

- `from_worker`
- `target`
- `input_bindings`
- `output_bindings`
- `invocation_site`

这些 slot 缺失时，也可以投影：

```text
type_or_contract_ambiguity
```

`WORKER_HANDOFF` 不应从 bare `delegation_intent` 直接构造；只有当 pipeline 已经 materialized handoff record 时，才提取 `WORKER_HANDOFF` instance。

## 6. Resource Contract 修正版设计

### 6.1 设计结论

`RESOURCE_CONTRACT_DEMAND` 需要重新审视。严格边界下，它默认是 planner demand / internal IR，不应自动作为 top-level `ConstructIRS`。

保守目标：

```text
ResourceContractPlan / ResourceContractDemandIR
-> evidence / planning input
-> REQUIRED_OUTPUT / FileSpec / VariableSpec / binding / producer 检查
```

而不是：

```text
ResourceContractDemandIR
-> RESOURCE_CONTRACT_DEMAND ConstructIRS
```

### 6.2 诊断归属

资源相关诊断应优先归属于真实 SPL construct 或 materialization construct：

- required output 缺 producer：`REQUIRED_OUTPUT` slot 或 ProducerIndex final authority；
- output 应为 file 但进入 variable：`FileSpec` / `DEFINE_FILES` materialization 检查；
- variable/file kind mismatch：resource resolver / materialization checker；
- binding 指向不存在 resource：resolver / binding checker；
- worker output 引用 file resource 不完整：worker boundary / handoff / producer consistency。

如果未来确实要保留 `RESOURCE_CONTRACT_DEMAND` IRS，必须先补一份架构说明，证明它是已批准的 compiler materialization construct，并定义：

- construct identity；
- lifecycle；
- source demand 到 materialized resource 的关系；
- 与 `REQUIRED_OUTPUT`、`FileSpec`、`VariableSpec`、resolver、ProducerIndex 的权威边界；
- 为什么不能由上述已有 construct 表达。

在完成该证明前，`RESOURCE_CONTRACT_DEMAND` 应视为待收回对象。

## 7. Diagnostic 投影规则

正确路径：

```text
ConstructIRS slot missing
-> SlotSatisfaction(status="missing", diagnostic_kind=...)
-> ConstructSatisfactionReport
-> DiagnosticProjector
-> CompileDiagnostic
```

禁止路径：

```text
manual if/else
-> CompileDiagnostic(kind="type_or_contract_ambiguity")
```

也禁止：

```text
RouteAnnotation label / DiagnosticKind
-> new ConstructIRS
-> diagnostic host construct
```

`CompileDiagnostic` 的用户可见性来自它是否解释用户需求为何无法 materialize 或无法 complete，而不是来自它是否有一个人工创建的 diagnostic host。

## 8. Final diagnostics 合并策略

不应把所有 stage-local IRS diagnostics 自动塞入 final `compile_diagnostics`。

允许进入 final diagnostics 的 IRS 诊断必须满足：

1. 来源于 source-demanded construct 或已 materialized construct；
2. diagnostic 对用户可解释、可行动；
3. diagnostic target 指向真实 construct；
4. provenance 指回原始 source span；
5. 不是 route refinement、planner bookkeeping 或内部修复提示。

对 delegation 场景，允许提升的目标 construct 类型为：

- `WORKER_PROMOTION`
- `WORKER_HANDOFF`
- `CHILD_WORKER`
- `INVOKE_WORKER`
- `CALL_API`

不得以 `DELEGATION_INTENT` 为 construct type 进行提升。

## 9. 实施计划

### Phase 1: Registry 边界修正

1. 从 `SPLConstructRegistry.default()` 删除 `DELEGATION_INTENT`。
2. 删除依赖 `DELEGATION_INTENT` 的 registry tests。
3. 保留并审查 `WORKER_CANDIDATE`、`WORKER_PROMOTION`、`WORKER_HANDOFF`。
4. 标记 `RESOURCE_CONTRACT_DEMAND` 为待审对象；除非补齐架构证明，否则后续 phase 收回到 resource materialization / required output 检查。

验收：

```text
registry.has("DELEGATION_INTENT") == False
rg "DELEGATION_INTENT" src tests
```

只允许命中文档或迁移说明，不允许命中生产 registry / checker / active tests。

### Phase 2: WorkerDelegationIRSChecker 改造

1. 不再从 route annotations 提取 `DELEGATION_INTENT` instance。
2. 将 `delegation_intent` route annotation 转为 `WORKER_CANDIDATE` / `WORKER_PROMOTION` 的 evidence。
3. 当 candidate 缺 input/output/invocation/result handoff 时，由 `WORKER_PROMOTION` missing slots 产生 `type_or_contract_ambiguity`。
4. 当已 materialized handoff 缺 target/binding/site 时，由 `WORKER_HANDOFF` missing slots 产生 `type_or_contract_ambiguity`。
5. `source_span_ids` 必须保留原 route annotation span。
6. metadata 中保留原始 `semantic_role="delegation_intent"`，用于 report trace。

验收：

```text
delegation_intent source signal
-> no DELEGATION_INTENT report
-> WORKER_PROMOTION report exists
-> missing promotion_* slot
-> projected type_or_contract_ambiguity
```

### Phase 3: Final diagnostic promotion 修正

1. 删除所有基于 `target_ref.startswith("delegation_intent:")` 的提升逻辑。
2. 改为基于 construct type + diagnostic kind + source-demand provenance 提升：

```text
construct_type in {
  WORKER_PROMOTION,
  WORKER_HANDOFF,
  CHILD_WORKER,
  INVOKE_WORKER,
  CALL_API
}
and diagnostic.kind == "type_or_contract_ambiguity"
and source_span_ids 非空
```

3. final diagnostic target 指向真实 construct。
4. feedback report 中可以展示原始 delegation span，但不能把它当 construct。

验收：

```text
diagnostic_id startswith "irs_"
diagnostic.kind == "type_or_contract_ambiguity"
diagnostic.target_ref != "delegation_intent:<span_id>"
diagnostic.source_span_ids contains original delegation span
feedback_report contains no diag_d10_*
```

### Phase 4: Legacy 手写 diagnostic 清理

继续删除或保持删除：

- `pipeline/delegation_diagnostics.py`
- `PipelineOrchestrator._run_delegation_diagnostics`
- `DiagnosticConsolidationInput.delegation_diagnostics`
- legacy `DiagnosticAnalyzer`
- legacy `PostNormalizeIRSChecker`

验收：

```text
rg "diag_d10|delegation_diagnostics|DiagnosticAnalyzer|AnalyzeInput|final_irs_checker|PostNormalizeIRSChecker\\b" src tests
```

不得命中生产路径或 active tests。

### Phase 5: ResourceContractDemand 审计

1. 审查 `RESOURCE_CONTRACT_DEMAND` 是否已有明确架构批准。
2. 如果没有，制定迁移：
   - demand 留在 `ResourceContractPlan`；
   - materialization 检查归属 `FileSpec` / `VariableSpec` / resolver；
   - producer 检查归属 `REQUIRED_OUTPUT` / ProducerIndex；
   - kind mismatch 归属 resolver / materialization checker。
3. 删除或降级 `RESOURCE_CONTRACT_DEMAND` IRS。

验收：

```text
ResourceContractDemandIR 不直接等同 ConstructIRS
resource diagnostics target 指向 REQUIRED_OUTPUT / FileSpec / VariableSpec / binding / producer owner
```

## 10. 总体验收标准

1. `DELEGATION_INTENT` 不再是 IRS construct。
2. `delegation_intent` 只作为 source signal / evidence。
3. delegation contract 缺失仍能产生 `type_or_contract_ambiguity`。
4. 该 diagnostic 来自 IRS checker + DiagnosticProjector。
5. diagnostic target 指向 `WORKER_PROMOTION` / `WORKER_HANDOFF` / `CHILD_WORKER` / `INVOKE_WORKER` / `CALL_API` 等真实 construct。
6. diagnostic provenance 指回原始 delegation span。
7. final feedback 不出现 `diag_d10_*`。
8. 不把全部 stage-local IRS diagnostics 无差别提升到 final diagnostics。
9. `RESOURCE_CONTRACT_DEMAND` 不再被默认视为合法 top-level IRS；保留必须有明确架构证明。
10. 测试覆盖 registry、checker extraction、slot satisfaction、projector、orchestrator promotion、feedback report。

## 11. 非目标

本方案不要求：

- 重新设计整个 IRS subsystem；
- 取消 `WORKER_CANDIDATE` / `WORKER_PROMOTION` / `WORKER_HANDOFF`；
- 让 IRS 取代 ProducerIndex、ExecutableElementGate 或全局 graph consistency；
- 为所有 planner demand 都建立 IRS；
- 把内部 compile/debug diagnostics 暴露给 feedback report。

本方案的核心目标只有一个：

```text
让 IRS 回到 construct slot satisfaction，
让 source signal、planner IR、diagnostic kind 各自留在正确层级。
```
