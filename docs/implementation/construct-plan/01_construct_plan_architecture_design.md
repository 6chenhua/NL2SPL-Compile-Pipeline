# ConstructPlan 架构设计

日期：2026-06-06

状态：Draft for implementation planning

## 1. 背景

当前 pipeline 已经具备三类能力：

```text
Stage 2 RouteAnnotation:
  把 span 标注为某个 semantic_role / construct_target / slot_target。

Downstream materialization:
  Stage 3.5 / Stage 4 / Stage 5 / Stage 7 直接或间接消费 RouteAnnotation。

IRS:
  对 materialized 或 source-demanded construct 做 satisfaction analysis。
```

但目前缺少一个明确的 compiler artifact，用于把 span-level route evidence 聚合为 construct-level demand。

现状链路是：

```text
RouteAnnotation
  -> downstream stages 各自解释 annotation
  -> IRS 事后检查 materialized IR
```

目标链路是：

```text
RouteAnnotation
  -> ConstructPlan
  -> downstream stages 按 construct-level demand / reservation / ownership constraint 工作
  -> IRS 检查 materialized + source-demanded construct satisfaction
```

本文档定义这个 `ConstructPlan` 架构。第一期只落地 `EXCEPTION_FLOW`，但数据模型、stage 接口和 IRS 边界必须按可扩展架构设计，避免后续新增 `WORKER_HANDOFF`、`API_CALL`、`RESOURCE_CONTRACT`、`CONSTRAINT` 等 construct 时重写整套 pipeline。

## 2. 核心问题

`RouteAnnotation` 是 span-level evidence，不是 construct-level plan。

例如：

```text
s2: construct_target=EXCEPTION_FLOW, slot_target=condition
s3: construct_target=EXCEPTION_FLOW, slot_target=handler
```

这只能说明：

```text
s2 是某个 exception flow 的 condition evidence
s3 是某个 exception flow 的 handler evidence
```

它不能稳定表达：

```text
s2 和 s3 是否属于同一个 ExceptionFlow
s3 是否 handler-only，还是同时也是 process_step
多个 condition 和多个 handler 如何配对
Stage 3.5 是否允许把 condition 和 handler 分到不同 worker
Stage 4 是否应该把 handler span 作为 main_flow candidate
Stage 5 是否应该为某个 exception flow 保留 handler block demand
IRS 是否应该检查 source-demanded 但未 materialized 的 construct
```

这些信息不能放在 IRS checker 里临时推断。IRS 的职责是检查 construct 是否满足 IRS，不是决定 construct 应该如何由 route evidence 组成。

## 3. 设计目标

1. 在 Stage 3.5 之前建立 construct-level demand。
2. 将 RouteAnnotation 聚合成 stable construct demand instance。
3. 记录 slot-specific source evidence，而不是混合 span list。
4. 向 Stage 3.5 提供 ownership / atomicity / reserved span 约束。
5. 向 Stage 4 提供 normal behavior spans 与 reserved construct spans 的分离。
6. 向 Stage 5 提供 handler block demand 与 source-backed handler evidence。
7. 向 Stage 7 提供 dual-role handler/process-step 边界。
8. 向 IRS 提供 source-demanded construct instances。
9. 不调用 LLM，不解析 raw NL，不增加 rule-based semantic fallback。
10. 不生成 SPL construct，不补全缺失 slot，只做 construct demand planning。

## 4. 非目标

ConstructPlan 不负责：

```text
- 调用 LLM
- 解析 raw NL
- 根据关键词推断语义
- 生成 ExceptionFlow / Block / Step / Worker
- 补全 missing handler
- 修改 RouteAnnotation
- 替代 IRS checker
- 替代 PostNormalizeIRSChecker
- 替代 ExecutableElementGate
- 替代 ProducerIndex
- 实现 recursive IRS traversal
```

如果未来某一步需要语义理解且可能使用 LLM 或 rule-based 方法，必须单独提交设计并确认实现方式。不得把 raw NL 关键词规则偷偷塞进 ConstructPlan。

## 5. 架构位置

推荐新增 Stage 2.5：

```text
Stage 1 SpanSlicer
  -> Stage 2 FieldRouter
  -> Stage 2.5 ConstructPlanner
  -> Stage 3 AmbiguityResolver
  -> Stage 3.5 WorkerBoundaryPlanner
  -> Stage 4 FlowAssembler
  -> Stage 5 BlockAssembler
  -> Stage 7 StepExtractor
  -> Stage 9.5 Post-normalize IRS
```

Stage 2.5 可以在 Stage 3 前或 Stage 3 后运行，但第一期建议：

```text
Stage 2 FieldRouter
  -> Stage 3 AmbiguityResolver
  -> Stage 2.5 ConstructPlanner on resolved spans/routes
  -> Stage 3.5 WorkerBoundaryPlanner
```

理由：

```text
AmbiguityResolver 可能拆分 span，并传播 annotations。
ConstructPlan 应基于 resolved spans/routes，避免 parent/child span 映射二次转换。
ConstructPlan 必须早于 Stage 3.5，因为 worker ownership 一旦提交，再修复 construct split 成本高。
```

如果实现上希望固定 stage 编号，也可以命名为 `Stage3_25ConstructPlanner`。架构语义是“worker planning 前的 construct demand planning”。

## 6. 总体数据流

```text
SpanIR + FieldRouteIR
  -> ConstructPlanner
  -> ConstructPlan

ConstructPlan:
  -> Stage 3.5: ownership constraints / reserved spans / candidate exclusions
  -> Stage 4: flow assembly input partition + exception demand materialization
  -> Stage 5: handler block demand / condition-only partial skeleton policy
  -> Stage 7: executable span filtering with dual-role awareness
  -> IRS: source-demanded ConstructInstance extraction
  -> feedback/provenance: stable construct target ids and slot evidence
```

## 7. 通用模型

第一期可以只实现 `ExceptionFlowDemand`，但外层模型必须可扩展。

### 7.1 ConstructPlan

```python
@dataclass
class ConstructPlan:
    plan_id: str
    source_schema: str | None = None
    demands: list[ConstructDemand] = field(default_factory=list)
    reserved_span_ids: set[str] = field(default_factory=set)
    dual_role_span_ids: set[str] = field(default_factory=set)
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 7.2 ConstructDemand

`ConstructDemand` 是通用接口，具体类型可以通过 dataclass + protocol 实现。

```python
@dataclass
class ConstructDemand:
    demand_id: str
    construct_type: str
    slots: dict[str, ConstructSlotDemand] = field(default_factory=dict)
    pairing_status: str = "unknown"
    materialization_policy: str = "source_backed_only"
    owner_policy: str = "unspecified"
    owner_worker_id: str | None = None
    reserved_span_ids: set[str] = field(default_factory=set)
    dual_role_span_ids: set[str] = field(default_factory=set)
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    construct_path: tuple[str, ...] = ()
    related_edges: list[ConstructEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 7.3 ConstructSlotDemand

```python
@dataclass
class ConstructSlotDemand:
    slot_name: str
    source_span_ids: list[str] = field(default_factory=list)
    semantic_roles: list[str] = field(default_factory=list)
    executable_values: list[bool | None] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    evidence_relation: Literal["direct", "derived", "ambiguous"] = "direct"
    status: Literal[
        "present",
        "missing",
        "ambiguous",
        "orphan",
        "invalid",
    ] = "present"
    metadata: dict[str, Any] = field(default_factory=dict)
```

## 8. ExceptionFlowDemand 第一实践

第一期只实现：

```python
@dataclass
class ExceptionFlowDemand(ConstructDemand):
    construct_type: str = "EXCEPTION_FLOW"
    condition_span_ids: list[str] = field(default_factory=list)
    handler_span_ids: list[str] = field(default_factory=list)
    condition_text: str | None = None
    pairing_status: Literal[
        "condition_only",
        "condition_with_handler",
        "missing_condition",
        "orphan_handler",
        "ambiguous_pairing",
        "empty_condition",
    ] = "condition_only"
    owner_policy: Literal[
        "condition_owner",
        "same_worker_required",
        "allow_cross_worker_with_diagnostic",
    ] = "condition_owner"
    owner_worker_id: str | None = None
    dual_role_span_ids: set[str] = field(default_factory=set)
```

### 8.1 Demand id

`demand_id` 必须稳定。

推荐：

```text
exc_demand_{index:02d}
```

如果有 packet metadata：

```text
exc_demand_{source_packet_id}
```

不要使用 LLM 生成 id。

### 8.2 Pairing policy

第一期只允许 structured evidence pairing：

```text
1. Same source_packet_id with same failure_item_index
2. Same source_section_id + same failure_item_index
3. Single condition + single handler in same failure section
```

禁止：

```text
- 根据 raw text 相似度配对
- 根据关键词配对
- 多 condition / 多 handler 时默认取第一个
- section fallback 在多候选情况下静默配对
```

当无法确定配对：

```text
pairing_status = ambiguous_pairing
diagnostic = ambiguous_exception_pairing
handler remains reserved but unmaterialized
```

如果该 diagnostic kind 尚未注册，第一期可以记录为 planner warning，并在后续 diagnostic registry 阶段正式注册。但不要静默成功。

### 8.3 Empty condition

空 condition 只能用结构化/显式规则判断，例如 existing `_is_empty_condition()` 的 marker 逻辑：

```text
None / N/A / not applicable / empty
```

这是格式/marker 判断，不是语义推断。遇到 empty condition：

```text
pairing_status = empty_condition
不生成 materialized ExceptionFlow
handler evidence 如果存在，标记 orphan_handler 或 ambiguous_pairing
```

### 8.4 Dual role

一个 span 可以同时是：

```text
EXCEPTION_FLOW.handler
process_step
```

这必须显式来自多条 `RouteAnnotation`。

规则：

```text
handler-only span:
  reserved_span_ids 包含该 span
  Stage 4 normal_behavior_spans 排除该 span

handler + process_step span:
  reserved_span_ids 包含该 span
  dual_role_span_ids 包含该 span
  Stage 4 normal_behavior_spans 可保留该 span
  Stage 7 可生成 command，但 provenance 必须保留 dual-role metadata
```

## 9. Stage 消费契约

### 9.1 Stage 3.5 WorkerBoundaryPlanner

输入新增：

```python
WorkerBoundaryPlanner.execute((spans, routes, canonical_input, construct_plan))
```

或在保持兼容时：

```python
WorkerBoundaryPlanner.execute((spans, routes, canonical_input))
```

内部通过 optional 参数启用 construct-aware behavior。

Stage 3.5 必须消费：

```text
construct_plan.reserved_span_ids
construct_plan.dual_role_span_ids
ExceptionFlowDemand.owner_policy
ExceptionFlowDemand.condition_span_ids
ExceptionFlowDemand.handler_span_ids
```

预期行为：

```text
handler-only span 不作为 child worker candidate source_span_ids
condition + handler 同一 demand 不应被拆成不同 worker
若已经被拆分且无法修复，发 cross_worker_exception_handler_split diagnostic/warning
dual-role handler 可继续作为 process_step candidate
```

### 9.2 Stage 4 FlowAssembler

Stage 4 输入应分离：

```text
normal_behavior_spans
reserved_construct_spans
construct_plan
```

Stage 4 LLM 不应被要求重新分类 reserved handler-only spans。

ExceptionFlow materialization 应来自 `ExceptionFlowDemand`，不是 Stage 4 临时从 RouteAnnotation 查 condition。

```text
condition_only demand:
  materialize partial ExceptionFlow(condition, spans=condition_span_ids)

condition_with_handler demand:
  materialize ExceptionFlow with condition_span_ids
  keep handler_span_ids in demand for Stage 5 block materialization

orphan_handler / ambiguous_pairing:
  do not materialize condition from handler
  preserve diagnostics/warnings
```

### 9.3 Stage 5 BlockAssembler

Stage 5 应消费 `ExceptionFlowDemand.handler_span_ids`。

预期行为：

```text
condition-only:
  preserve empty exception_flow_blocks entry
  no fabricated handler block

condition_with_handler:
  handler block can be source-backed from handler_span_ids

ambiguous/orphan handler:
  no handler block materialized unless dual-role process_step is independently present
```

Stage 5 不应再通过 section fallback 静默把 handler 配到第一个 condition。

### 9.4 Stage 7 StepExtractor

Stage 7 必须继续依赖 executable filtering，但需要识别 dual-role：

```text
failure_mode condition:
  non-executable, cannot become command

handler-only exception handler:
  reserved for exception construct, can become command only if explicitly executable handler_action and Stage 5/flow context demands handler action

handler + process_step dual role:
  may become normal command because process_step role is explicit
```

第一期可以不修改 Stage 7 生成逻辑，但必须把 dual-role 信息保留到 intermediate，避免后续误判。

### 9.5 IRS

IRS 不构建 ConstructPlan。

IRS 可以从 ConstructPlan 派生 source-demanded `ConstructInstance`：

```python
ConstructInstance(
    construct_type="EXCEPTION_FLOW",
    materialized=False,
    source_demanded=True,
    candidate_only=True,
    metadata={"demand_id": "...", "slots": ...},
)
```

如果 downstream 已 materialized `ExceptionFlow`，IRS 检查 materialized instance。

如果 source demanded 但未 materialized，IRS 可以报告：

```text
blocked / missing required slot / ambiguous pairing
```

但 IRS 不能决定如何配对 handler。

## 10. Diagnostics 边界

ConstructPlanner 可以产生 planner-level diagnostics/warnings，用于说明 demand 无法稳定形成。

建议新增或预留 diagnostic kinds：

```text
ambiguous_exception_pairing
orphan_exception_handler
empty_exception_condition
cross_worker_exception_handler_split
reserved_span_leaked_to_main_flow
```

第一期如果 diagnostic registry 还没扩展，可以先用 warnings + structured metadata，但最终必须进入 `CompileDiagnostic`，否则 feedback report 不稳定。

Diagnostic authority：

```text
ConstructPlanner:
  pairing / reservation / ownership planning diagnostics

IRS:
  slot satisfaction diagnostics

ExecutableElementGate:
  executable renderability diagnostics

ProducerIndex:
  output producer diagnostics
```

## 11. Graph 与 provenance

ConstructPlan 应为未来 recursive IRS 留接口，但不做 traversal。

推荐 edges：

```text
EXCEPTION_FLOW_DEMAND --requires_slot--> condition span virtual node
EXCEPTION_FLOW_DEMAND --requires_slot--> handler span virtual node
EXCEPTION_FLOW_DEMAND --owns_or_reserves--> span
EXCEPTION_FLOW_DEMAND --materializes_to--> ExceptionFlow
Worker --owns--> EXCEPTION_FLOW_DEMAND
```

第一期只需要保留 `related_edges`，不需要 runner 遍历。

## 12. 中间结果与 checkpoint

`ConstructPlan` 必须进入 intermediate：

```python
intermediate["construct_plan"] = construct_plan
intermediate["construct_plan_payload"] = construct_plan.to_payload()
```

checkpoint 必须是 deterministic payload，不应直接存 mutable object。

Payload 示例：

```json
{
  "demands": [
    {
      "demand_id": "exc_demand_00",
      "construct_type": "EXCEPTION_FLOW",
      "slots": {
        "condition": {"source_span_ids": ["s2"]},
        "handler_action": {"source_span_ids": ["s3"]}
      },
      "pairing_status": "condition_with_handler",
      "reserved_span_ids": ["s3"],
      "dual_role_span_ids": [],
      "source_section_id": "sec_failure_handling",
      "source_packet_id": "p_failure_0"
    }
  ],
  "reserved_span_ids": ["s3"],
  "dual_role_span_ids": [],
  "diagnostics": [],
  "warnings": []
}
```

## 13. Testing contract

第一期必须覆盖以下架构边界。

### TC-1 Handler 不进入 main flow

输入：

```text
s1 process_step
s2 EXCEPTION_FLOW.condition
s3 EXCEPTION_FLOW.handler
```

预期：

```text
ConstructPlan.reserved_span_ids contains s3
Stage 4 normal_behavior_spans excludes s3 unless dual role
LLM output main_flow_spans containing s3 is sanitized or rejected
```

### TC-2 Handler 不当 condition

预期：

```text
handler span never materializes condition
condition_span_ids only from condition slot
```

### TC-3 Condition / handler 跨 worker

预期：

```text
ConstructPlan records one demand
Stage 3.5 preserves ownership or emits cross_worker_exception_handler_split
```

### TC-4 Empty condition

预期：

```text
empty condition does not materialize ExceptionFlow
handler becomes orphan/ambiguous evidence
```

### TC-5 多 condition / handler ambiguity

预期：

```text
no first-condition fallback
ambiguous_exception_pairing visible
```

### TC-6 Dual role handler/process_step

预期：

```text
dual_role_span_ids contains span
normal behavior keeps span
handler demand also keeps span
```

## 14. 可扩展性原则

新增 construct demand 时必须遵守：

```text
1. 新增具体 Demand type，不改 ConstructPlan 核心语义。
2. Slot evidence 必须以 ConstructSlotDemand 表达。
3. Pairing/ownership/materialization policy 必须显式字段化。
4. 不允许在 downstream stage 私自重新从 RouteAnnotation 推断 construct demand。
5. 不允许 checker 生成 demand。
6. 不允许 renderer 消费 RouteAnnotation。
```

未来可扩展 construct：

```text
WORKER_HANDOFF_DEMAND
API_CALL_DEMAND
RESOURCE_CONTRACT_DEMAND
CONSTRAINT_DEMAND
ALTERNATIVE_FLOW_DEMAND
LOOP_DEMAND
```

## 15. 实施顺序建议

### P0: Baseline tests

只加测试，锁定当前缺陷：

```text
handler-only span leaks into main_flow_spans
handler condition misclassification guarded only post-hoc
condition/handler worker split lacks construct-level warning
multiple condition/handler fallback ambiguity
```

### P1: Model + planner

新增：

```text
src/nl2spl/compiler/construct_plan/
  model.py
  planner.py
  payload.py
```

只实现 `ExceptionFlowDemand`。

### P2: Stage 3.5 integration

Stage 3.5 消费 reserved spans 和 ownership constraints。

### P3: Stage 4 integration

Stage 4 从 ConstructPlan materialize ExceptionFlow，分离 normal/reserved spans。

### P4: Stage 5 integration

Stage 5 消费 handler demand，移除 section-first fallback。

### P5: IRS integration

IRS 从 ConstructPlan 生成 source-demanded ConstructInstance。

### P6: Audit and cleanup

删除重复 ad-hoc fallback 或把它们降级为 compatibility guard。

## 16. 验收标准

架构验收：

```text
ConstructPlan exists and is checkpointable.
ExceptionFlowDemand records condition / handler slot evidence separately.
Reserved spans are visible before Stage 3.5.
Stage 3.5 cannot silently split condition/handler without warning.
Stage 4 does not classify handler-only spans as main flow candidates.
Stage 5 does not pair handler by first condition fallback in ambiguous cases.
IRS can receive source-demanded EXCEPTION_FLOW instances.
No LLM calls in planner.
No raw NL keyword semantic rules in planner.
No renderer dependency on ConstructPlan.
```

Behavior 验收：

```text
condition-only failure handling still renders partial EXCEPTION_FLOW.
condition + handler produces source-backed handler block only when pairing is explicit.
handler-only evidence never becomes condition.
empty condition does not create ExceptionFlow.
dual-role handler/process_step remains executable only because process_step role is explicit.
ambiguous pairing produces visible diagnostic/warning.
```

## 17. PM 审核清单

代码审核时逐项核验：

```text
1. 是否新增了 ConstructPlan/ExceptionFlowDemand，而不是继续在 Stage 4/5 写局部 guard。
2. Planner 是否只消费 SpanIR / FieldRouteIR / structured provenance。
3. Planner 是否完全不调用 LLM。
4. Planner 是否没有 raw NL keyword semantic inference。
5. Slot evidence 是否分开存储，而不是混合 spans list。
6. reserved_span_ids / dual_role_span_ids 是否进入 intermediate。
7. Stage 3.5 是否真正消费 construct ownership constraint。
8. Stage 4 是否真正从 behavior candidates 排除 handler-only spans。
9. Stage 5 是否停止 ambiguous first-condition fallback。
10. IRS 是否只检查 demand/materialized instance，不做 pairing。
11. 所有 diagnostics/warnings 是否可见并可追踪。
12. Tests 是否覆盖 TC-1 到 TC-6。
13. 不得用“兼容 fallback”掩盖 planner 失败。
14. 不得把本阶段改动混入 unrelated config/orchestrator 清理。
```

## 18. 最终判断

`ConstructPlan` 不是为了增加一层抽象，而是为了补齐 compiler 中从 span-level semantics 到 construct-level intent 的缺口。

如果没有它，Stage 3.5/4/5/7 会继续各自解释 RouteAnnotation，IRS 只能事后检查 materialized IR，系统会继续依赖局部 guard 和 fallback。

第一期以 `EXCEPTION_FLOW` 作为实践点是合理的，因为它同时覆盖：

```text
slot pairing
partial construct
handler source backing
worker ownership
reserved span filtering
IRS source-demanded instance
```

这足以验证架构是否真正可扩展。
