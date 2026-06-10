# ResourceEvidenceGraph 与 Resource IRS 分层设计

版本: 1.0  
状态: Proposed architecture design  
范围: ResourceContractPlan、ResourceResolver、ProducerIndex、IRS、DiagnosticProjector、feedback report、后续高级 IR / 低级 IR

## 1. 背景

当前 NL2SPL pipeline 已经能发现部分 resource 相关问题，例如：

- required output 没有 producer；
- output/file/variable kind 不一致；
- worker handoff 缺 input/output binding；
- API 调用缺 response binding；
- 变量被声明但没有消费。

但这些问题的发现机制存在架构风险：

```text
发现一个新问题
-> 新增一个特殊 checker
-> checker 直接创建 CompileDiagnostic
-> feedback_report 展示该 diagnostic
```

这种方式不是框架级解决方案。它会导致：

1. `CompileDiagnostic` 生成点分散。
2. `IRS`、`ProducerIndex`、resolver、normalizer、gate 的责任边界模糊。
3. 每种 resource 问题都需要额外手写逻辑。
4. 一般程序语义问题被过早放进 NL2SPL feedback。
5. source-demanded construct 的信息缺口没有统一通过 IRS slot satisfaction 表达。

因此需要重新定义 resource 相关问题的分层：

```text
Resource evidence 统一
Construct IRS 保持 construct-centered
Diagnostic 统一由 DiagnosticProjector 投影
一般 data-flow / liveness 问题后移到后续 IR
```

## 2. 核心判断

### 2.1 ProducerIndex 不是所有 resource 的唯一 authority

ProducerIndex 的正确定位是：

```text
ProducerIndex = producer / data-production evidence authority
```

它回答：

- 哪个 step / worker / API / handoff 生产了某个 resource；
- 某个 required output 是否有 source-backed producer；
- producer 与 resource kind / scope 是否匹配；
- producer 是否 renderable。

但 resource 事实不只有 producer。resource 还涉及：

- 用户是否要求了该 resource；
- resource 是否 materialized；
- resource kind 是 variable / file / api / type；
- resource scope 是 global / worker / handoff；
- worker/API IO 是否绑定到该 resource；
- 后续是否消费该 resource；
- source provenance 来自哪里。

这些事实不能都塞进 ProducerIndex。更合理的抽象是：

```text
ResourceEvidenceGraph
  ├─ ResourceContractPlan evidence
  ├─ ResourceResolver / SymbolTable evidence
  ├─ ProducerIndex evidence
  ├─ BindingGraph evidence
  ├─ Consumer / later IR data-flow evidence
  └─ Source provenance evidence
```

ProducerIndex 是 `ResourceEvidenceGraph` 的一个子 authority，而不是整个 resource 世界的唯一 authority。

### 2.2 不应使用单一泛化 `RESOURCE IRS`

一个看似直接的方案是新增：

```text
RESOURCE IRS
  name
  kind
  direction
  producer
  consumer
  scope
  binding
  materialization
```

这个方案不推荐。原因是它会把不同 construct 的语义抹平：

- input 通常不需要 producer，它来自用户或外部环境；
- required output 通常必须有 producer，因为它是交付承诺；
- file 可能是 input file，也可能是 output file；
- API IO 往往是 `CALL_API` construct 的 slot，不一定是独立 resource construct；
- unused variable 是 liveness / optimization 问题，不一定是 NL2SPL requirement fulfillment 问题；
- worker handoff binding 是 `WORKER_HANDOFF` / `INVOKE_WORKER` 的 slot，不是普通 resource 的通用属性。

如果把这些统一进一个 `RESOURCE IRS`，IRS 会从 construct-centered 退化成 generic validator。这违背 IRS 边界：

```text
SPL Grammar + Requirement Semantics + Compiler Policy -> ConstructIRS
```

### 2.3 正确统一点在 evidence layer

本设计的核心结论：

```text
resource 的事实层应统一；
resource 的 IRS construct 不应强行统一。
```

统一的是：

```text
ResourceEvidenceGraph
```

保持分化的是：

```text
REQUIRED_OUTPUT IRS
CALL_API IRS
INVOKE_WORKER IRS
WORKER_HANDOFF IRS
CHILD_WORKER IRS
FileSpec / VariableSpec materialization checker
```

这些 construct/checker 消费同一套 resource evidence，但根据各自 construct slot 解释这些 evidence。

## 3. 责任边界

### 3.1 ResourceEvidenceGraph

职责：

1. 汇总 resource 事实。
2. 统一 resource identity、kind、scope、provenance。
3. 表达 declaration / requirement / binding / producer / consumer / materialization 之间的 edge。
4. 为 IRS checker、resolver、ProducerIndex、feedback renderer 提供只读 evidence。

不负责：

1. 创建 `CompileDiagnostic`。
2. 判断 construct 是否 complete。
3. 决定是否渲染 SPL。
4. 推断用户没有要求的 resource。
5. 把 planner demand 提升成 IRS construct。

### 3.2 ProducerIndex

职责：

1. 从 WorkerIR / Stage 10 IR / normalized SPL IR 中建立 producer facts。
2. 标记 producer 的 source span、scope、resource kind、renderability。
3. 提供查询接口，例如：

```text
find_producers(resource_name, resource_kind, scope)
has_renderable_producer(resource_ref)
producer_kind_matches(resource_ref)
```

不负责：

1. 直接创建 `missing_output_producer`。
2. 直接写入 feedback report。
3. 判断所有 resource 是否 semantic complete。
4. 检查 unused variable。

### 3.3 IRS

职责：

1. 对 construct instance 做 slot satisfaction。
2. 消费 `ResourceEvidenceGraph` 中的 structured evidence。
3. 输出 `ConstructSatisfactionReport`。
4. 通过 missing slot 表达 construct-level issue。

不负责：

1. 自己重新扫描所有 IR 猜 producer。
2. 创建 resource facts。
3. 直接创建 `CompileDiagnostic`。
4. 处理后续 IR 的 liveness / optimization 问题。

### 3.4 DiagnosticProjector

职责：

1. 从 `ConstructSatisfactionReport` 投影 `CompileDiagnostic`。
2. 统一 diagnostic id、target_ref、source_span_ids、severity、message。
3. 保证用户可见 diagnostic 具有 construct owner 和 provenance。

不负责：

1. 检查 resource 事实。
2. 推断 slot 是否满足。
3. 修改 report 或 IR。

### 3.5 后续高级 IR / 低级 IR

职责：

1. liveness 分析；
2. unused variable；
3. dead assignment；
4. low-level type compatibility；
5. control-flow reachability；
6. execution target 相关约束。

这些问题不应默认进入 NL2SPL feedback report。它们可以进入后续 compiler/linter report。

## 4. ResourceEvidenceGraph 数据模型

### 4.1 ResourceRef

```python
ResourceKind = Literal["variable", "file", "api", "type"]
ResourceDirection = Literal["input", "output", "internal", "api_input", "api_output"]
ScopeKind = Literal["global", "worker", "handoff"]

@dataclass(frozen=True)
class ResourceRef:
    name: str
    kind: ResourceKind
    scope_kind: ScopeKind
    scope_id: str | None = None
```

说明：

- `name` 不是全局唯一键；
- `kind + scope_kind + scope_id + name` 共同标识 resource；
- 同名 worker-local resource 不应互相覆盖；
- file 和 variable 同名时不能混淆。

### 4.2 ResourceNode

```python
@dataclass
class ResourceNode:
    ref: ResourceRef
    direction: ResourceDirection
    declared: bool = False
    required: bool = False
    materialized: bool = False
    data_type: str | None = None
    description: str | None = None
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    demand_ids: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
```

### 4.3 ResourceEdge

```python
ResourceEdgeKind = Literal[
    "requires",
    "materializes_as",
    "produces",
    "consumes",
    "binds_input",
    "binds_output",
    "api_request",
    "api_response",
]

@dataclass
class ResourceEdge:
    edge_id: str
    kind: ResourceEdgeKind
    source_id: str
    target_ref: ResourceRef
    source_construct_type: str | None = None
    source_construct_id: str | None = None
    renderable: bool | None = None
    source_span_ids: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
```

### 4.4 ResourceEvidenceGraph

```python
@dataclass
class ResourceEvidenceGraph:
    nodes: dict[ResourceRef, ResourceNode] = field(default_factory=dict)
    edges: list[ResourceEdge] = field(default_factory=list)

    def find_node(self, ref: ResourceRef) -> ResourceNode | None: ...
    def producers_for(self, ref: ResourceRef) -> list[ResourceEdge]: ...
    def consumers_for(self, ref: ResourceRef) -> list[ResourceEdge]: ...
    def bindings_for(self, ref: ResourceRef) -> list[ResourceEdge]: ...
    def requirements_for(self, ref: ResourceRef) -> list[ResourceEdge]: ...
```

该 graph 是只读 evidence artifact。它不拥有 diagnostic policy。

## 5. 与 ResourceContractPlan 的关系

`ResourceContractPlan` 是 source demand artifact。它回答：

```text
用户是否要求某个 input/output resource contract？
```

它不回答：

```text
这个 demand 是否已经 materialized？
这个 resource 是 file 还是 variable？
这个 output 是否有 producer？
```

`ResourceEvidenceGraph` 消费 `ResourceContractPlan` 后应产生：

```text
ResourceContractDemandIR
-> ResourceNode(required=True)
-> ResourceEdge(kind="requires")
```

后续 Stage 6 / resolver materialize 出 `FileSpec` 或 `VariableSpec` 后，应产生：

```text
FileSpec / VariableSpec
-> ResourceNode(materialized=True, kind=file|variable)
-> ResourceEdge(kind="materializes_as")
```

这样 `ResourceContractDemandIR` 本身不需要成为 `ConstructIRS`。它是 evidence 的来源之一。

## 6. 为什么保留 `REQUIRED_OUTPUT IRS`

`REQUIRED_OUTPUT` 应保留为 IRS construct。理由：

1. 它对应用户明确要求的最终交付承诺。
2. 它不是普通 resource，而是 requirement fulfillment construct。
3. 它的完整性不能只由 generic resource node 判断。
4. 它需要把 source demand、materialized resource、producer evidence 组合成 construct slot satisfaction。

推荐 slots：

```text
REQUIRED_OUTPUT
  output_name
  output_kind
  materialized_resource
  producer
  delivery_scope
```

slot evidence 来源：

| Slot | Evidence 来源 |
|---|---|
| `output_name` | ResourceContractPlan / source annotation / structural evidence |
| `output_kind` | ResourceResolver / Stage 6 materialization |
| `materialized_resource` | ResourceEvidenceGraph materializes_as edge |
| `producer` | ProducerIndex produces edge |
| `delivery_scope` | ResourceEvidenceGraph scope / binding evidence |

缺 producer 的诊断路径：

```text
Required output demand
-> REQUIRED_OUTPUT instance
-> ResourceEvidenceGraph has no renderable produces edge
-> producer slot missing
-> ConstructSatisfactionReport
-> DiagnosticProjector
-> CompileDiagnostic(kind="missing_output_producer")
```

这里 ProducerIndex 只提供事实：

```text
no renderable producer found
```

它不直接创建 diagnostic。

## 7. 其他 resource 相关 construct 的消费方式

### 7.1 `CALL_API IRS`

使用 `ResourceEvidenceGraph` 检查：

- `api_name` 是否有 declared/ref evidence；
- `call_action` 是否有 executable action evidence；
- `response_binding` 是否绑定到 output resource；
- api response 是否 materialized 为 variable/file/resource。

诊断仍归属于 `CALL_API` missing slot，而不是归属于 generic resource。

### 7.2 `INVOKE_WORKER IRS`

使用 `ResourceEvidenceGraph` 检查：

- target worker 是否存在；
- input bindings 是否指向可用 resource；
- output bindings 是否 materialized；
- worker invocation 是否产生 expected output。

诊断归属于 `INVOKE_WORKER`。

### 7.3 `WORKER_HANDOFF IRS`

使用 `ResourceEvidenceGraph` 检查：

- `from_worker`；
- `target`；
- input/output bindings；
- invocation site；
- handoff output 是否能流回 parent 或 final output。

诊断归属于 `WORKER_HANDOFF`。

### 7.4 FileSpec / VariableSpec materialization checker

`FileSpec` / `VariableSpec` 是否应该作为 `ConstructIRS` 需要单独论证。保守方案是先作为 materialization checker 使用 `ResourceEvidenceGraph`：

- demand 要求 file，但 materialized 为 variable -> `resource_kind_mismatch`；
- FileSpec 缺 path placeholder -> materialization warning；
- variable/file 同名冲突 -> resolver warning；
- binding 指向不存在 resource -> resolver diagnostic。

这些检查可以先进入 compile report；只有当它们影响 source-demanded construct fulfillment 时，才通过对应 construct IRS 投影到 feedback report。

## 8. NL2SPL 与后续 IR 的问题分界

### 8.1 NL2SPL 应负责的问题

NL2SPL 应检查 source-demanded construct 是否满足信息需求：

- required output 是否 materialized；
- required output 是否有 producer；
- child worker 是否有 input/output contract；
- worker handoff 是否有 binding；
- API call 是否有 target、call action、response binding；
- exception flow 是否有必要 handler policy；
- request input 是否有 prompt 和 target variable。

这些问题应通过 IRS 或 IRS 消费的 evidence layer 表达。

### 8.2 后续 IR 应负责的问题

后续高级 IR / 低级 IR 更适合检查：

- unused variable；
- dead assignment；
- general liveness；
- general use-before-def；
- low-level type coercion；
- backend-specific execution constraints；
- optimization-only warnings。

这些问题不应作为 NL2SPL feedback report 的默认内容。它们可以进入后续 compiler/linter report。

### 8.3 边界判断规则

判断某个 resource issue 是否属于 NL2SPL：

```text
如果它说明 source-demanded SPL construct 无法 materialize 或无法 complete，
则属于 NL2SPL。

如果它只是说明已生成 IR 存在一般程序质量 / 数据流 / 优化问题，
则属于后续 IR。
```

示例：

| Issue | 所属阶段 | 原因 |
|---|---|---|
| required output 没有 producer | NL2SPL | 用户交付承诺无法 fulfill |
| 普通 internal variable 没有 consumer | 后续 IR | liveness / dead code |
| input 没有 producer | 通常不是问题 | input 来自用户或外部 |
| output file materialized 为 variable | NL2SPL | source demand materialization 错误 |
| API response binding 缺失 | NL2SPL | `CALL_API` / handoff slot 不完整 |
| worker-local variable 未使用 | 后续 IR | worker body liveness |

## 9. Diagnostic 投影原则

禁止：

```text
ResourceEvidenceGraph / ProducerIndex / Resolver
-> CompileDiagnostic
```

推荐：

```text
ResourceEvidenceGraph / ProducerIndex / Resolver
-> structured evidence
-> ConstructIRS slot satisfaction
-> ConstructSatisfactionReport
-> DiagnosticProjector
-> CompileDiagnostic
```

例外：

非 construct-level 的系统内部问题可以进入 compile/debug report，但不得进入用户层 feedback report，除非被明确投影为 source-demanded construct issue。

## 10. Feedback Report 边界

`feedback_report` 应展示用户需求层面的问题：

- source-demanded construct 缺必要信息；
- required output 无法 fulfill；
- worker/API handoff contract 不完整；
- 用户需要补充的 input 或 policy。

`feedback_report` 不应展示：

- route refinement telemetry；
- resolver 内部 bookkeeping；
- ProducerIndex 内部 edge mismatch；
- unused variable；
- optimizer warning；
- backend lowering warning。

如果内部 evidence 最终导致用户需求无法 fulfill，应通过 construct IRS diagnostic 投影后展示。

## 11. 实施方案

### Phase 1: 定义 ResourceEvidenceGraph IR

新增：

```text
src/nl2spl/ir/resource_evidence_graph.py
```

包含：

- `ResourceRef`
- `ResourceNode`
- `ResourceEdge`
- `ResourceEvidenceGraph`

验收：

- 同名不同 scope resource 不冲突；
- file / variable 同名不冲突；
- graph 可表达 requirement、materialization、producer、binding edge。

### Phase 2: 接入 ResourceContractPlan 与 resolver

实现：

- `ResourceContractDemandIR -> requires edge`
- `FileSpec / VariableSpec -> materializes_as edge`
- resolver 输出 `ResourceRef` 和 scope 信息；
- binding 使用 `ResourceRef`，不再只用裸 `resource_name`。

验收：

- `finished_draft` demand 能映射到 file resource；
- `ResourceContractDemandIR` 不被注册为 IRS construct；
- graph 中能追踪 source span。

### Phase 3: ProducerIndex 降级为 evidence provider

实现：

- ProducerIndex 输出或填充 `produces` edge；
- ProducerIndex 不直接创建 `CompileDiagnostic`；
- renderability / source provenance 写入 edge metadata。

验收：

- required output 无 producer 时，ProducerIndex 只返回 empty producers；
- 没有任何 `ProducerIndex -> CompileDiagnostic` 直接路径。

### Phase 4: REQUIRED_OUTPUT IRS 消费 graph

实现：

- `REQUIRED_OUTPUT` checker 从 `ResourceEvidenceGraph` 提取 instance；
- 检查 `materialized_resource` 和 `producer` slot；
- producer 缺失时生成 `ConstructSatisfactionReport`；
- `DiagnosticProjector` 投影 `missing_output_producer`。

验收：

```text
required output demand exists
resource materialized
no producer edge
-> REQUIRED_OUTPUT report has missing producer slot
-> diagnostic_id starts with irs_
-> kind == missing_output_producer
```

### Phase 5: 其他 construct 消费 graph

逐步迁移：

- `CALL_API`
- `INVOKE_WORKER`
- `WORKER_HANDOFF`
- `CHILD_WORKER`

验收：

- checker 不手写扫描 resource registry；
- checker 只消费 graph 查询结果；
- diagnostic 归属于真实 construct。

### Phase 6: 后续 IR 问题后移

实现：

- unused variable 不进入 NL2SPL feedback；
- liveness / dead code 保留给后续 IR/linter；
- compile/debug report 可保留内部 warning，但和 feedback report 分离。

验收：

- feedback report 不出现 unused variable；
- compile/debug report 可包含内部 resource graph warning；
- 用户可见 diagnostic 均有 source-demanded construct owner。

## 12. 验收标准

1. 不新增泛化 `RESOURCE IRS` 作为所有 resource 问题的宿主。
2. `REQUIRED_OUTPUT IRS` 保留，并消费 `ResourceEvidenceGraph`。
3. `ResourceContractDemandIR` 不直接等同 `ConstructIRS`。
4. ProducerIndex 不直接创建 `CompileDiagnostic`。
5. ProducerIndex 只作为 producer edge evidence provider。
6. `missing_output_producer` 由 `REQUIRED_OUTPUT` missing slot 经 `DiagnosticProjector` 产生。
7. `resource_kind_mismatch` 归属于 materialization / resolver owner；只有影响 source-demanded construct fulfillment 时才进入 feedback。
8. `unused variable` 默认不进入 NL2SPL feedback。
9. Worker/API/file/input/output 共享 `ResourceEvidenceGraph`，但保持各自 construct IRS。
10. 所有用户可见 resource diagnostic 都有 construct owner、source span 和可解释的 missing slot。

## 13. 非目标

本设计不要求：

- 立即实现完整后续高级 IR / 低级 IR；
- 把所有 resource checker 一次性迁移；
- 删除 `REQUIRED_OUTPUT IRS`；
- 用单一 `RESOURCE IRS` 取代所有 construct IRS；
- 让 ProducerIndex 成为万能 resource authority；
- 把 optimizer / linter 级问题提前到 NL2SPL feedback。

## 14. 最终结论

resource 相关问题需要统一框架，但统一点不是 `RESOURCE IRS`，而是 evidence layer：

```text
ResourceEvidenceGraph 统一 resource facts
ProducerIndex 提供 producer facts
Resolver 提供 materialization/kind/scope facts
ConstructIRS 解释这些 facts 对具体 SPL construct 是否满足
DiagnosticProjector 统一生成 CompileDiagnostic
```

因此：

```text
保留 REQUIRED_OUTPUT IRS
不引入泛化 RESOURCE IRS
建立 ResourceEvidenceGraph
让所有 resource-aware construct IRS 消费同一 evidence layer
```

这能同时避免两种错误：

1. 为每个 resource 问题写一个补丁式 checker；
2. 把所有 resource 语义塞进一个过宽的 generic IRS。
