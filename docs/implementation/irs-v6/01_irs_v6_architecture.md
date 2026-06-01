# IRS v6 总体架构设计

## 背景

当前 IRS v5 已经有较好的基础：

- `SPLConstructRegistry` 定义 construct 的 information requirements。
- Stage 4 能检查 `EXCEPTION_FLOW`。
- Stage 7 能检查 executable step。
- Stage 9.5 / post-normalize pass 能产出最终 construct-level diagnostics。

但 v5 的执行方式仍偏分散：每新增一种 IRS，通常需要手写 checker、手动接 orchestrator、手动合并 diagnostics、手动更新报告和测试。随着 `BLOCK`、`FLOW`、`WORKER`、`CONSTRAINT`、`RESOURCE` 等 construct 增多，这会变成架构负债。

同时，IRS 在概念上是层级化的：

```text
Worker
  -> Flow
      -> Block
          -> Step / Command
```

但是工程上不能直接写一个无条件递归 validator，因为 IR 中存在大量 cross-reference：

```text
Step -> RequiredOutput
Handoff -> ChildWorker
ExceptionFlow -> HandlerStep
Policy -> Step / Flow / Worker
```

所以 v6 的目标不是马上做通用递归检查，而是先把可扩展 checker 接口、construct graph 关系和 frontier/cutline 信息补齐。

## 核心原则

### 1. Registry 定义需求，Checker 评估实例

`ConstructIRS` 只描述 construct 需要哪些 slot、哪些 slot 支持 partial rendering、缺失时应该产生什么 diagnostic。

checker 的职责是：

```text
ConstructInstance + ConstructIRS + IRSCheckContext
-> ConstructSatisfactionReport
```

checker 不应该把 IRS 规则重新硬编码成另一套不可复用逻辑。

### 2. Stage-local frontier checking 优先

当前不做通用递归检查。每个 stage 只检查自己已经 materialized 或 source-demanded 的 construct。

```text
Stage 3.5: WorkerCandidate / WorkerPromotion / ChildWorker / WorkerHandoff
Stage 4: Flow / ExceptionFlow
Stage 5: Block
Stage 7: Step / Command
Post-normalize: final construct-level diagnostics
```

### 3. Cutline 必须显式表达

当父 construct 缺少 required-for-complete slot，但允许 partial rendering 时，应形成 cutline。

例如：

```text
EXCEPTION_FLOW.condition satisfied
EXCEPTION_FLOW.handler_action missing
=> partial render
=> missing_handler
=> no handler block required unless source-backed handler evidence exists
```

如果 report 不表达 `cutline_reason` 和 `frontier_status`，未来递归 evaluator 就无法知道为什么没有继续检查 child construct。

### 4. construct graph 不是严格树

新增 report 可以保留 `primary_parent_id` 和 `construct_path`，但不能假设所有关系都是单父树。

必须预留 edge：

```python
@dataclass
class ConstructEdge:
    from_id: str
    to_id: str
    edge_type: Literal[
        "contains",
        "produces",
        "consumes",
        "invokes",
        "handoff_to",
        "handles",
        "applies_to",
        "derived_from",
    ]
    source_span_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

`primary_parent_id` 只表达主包含关系。非树关系由 `ConstructEdge` 表达。

### 5. Renderer 不做 IRS 判断

IRS 判断应发生在 IR materialization / normalization / gate 前后，不应发生在最终 SPL text rendering。

Renderer 只消费已经被裁决的 IR。

## 推荐模块结构

当前 v5 模块可以保留，但 v6 建议新增兼容子包：

```text
src/nl2spl/compiler/irs/
  __init__.py
  context.py
  instance.py
  checker.py
  runner.py
  projector.py
  frontier.py
```

MVP 可先不移动现有文件，只新增兼容层。后续再做模块整理。

## 核心类型草案

### IRSCheckContext

统一传递 checker 需要的上下文：

```python
@dataclass
class IRSCheckContext:
    spans: list[SpanIR]
    routes: FieldRouteIR | None = None
    worker_plan: WorkerPlanIR | None = None
    resources: ResourceRegistryIR | None = None
    symbol_table: SymbolTable | None = None
    worker_scoped_resources: WorkerScopedResourceIR | None = None
    stage_name: str | None = None
```

### ConstructInstance

把具体 IR 中的 construct 标准化：

```python
@dataclass
class ConstructInstance:
    construct_id: str
    construct_type: str
    ir_ref: object | None
    materialized: bool
    source_demanded: bool
    candidate_only: bool = False
    primary_parent_id: str | None = None
    construct_path: tuple[str, ...] = ()
    source_span_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

典型状态：

```text
WORKER_CANDIDATE: materialized=False, source_demanded=True, candidate_only=True
CHILD_WORKER:     materialized=True,  source_demanded=True, candidate_only=False
No demand:        不创建 ConstructInstance
```

### ConstructSatisfactionReport 扩展

建议正式扩展 schema，并提供默认值以兼容 v5 测试：

```python
@dataclass
class ConstructSatisfactionReport:
    construct_id: str
    construct_type: str
    slots: list[SlotSatisfaction]
    completeness: ConstructCompleteness
    renderable: bool
    diagnostics: list = field(default_factory=list)

    primary_parent_id: str | None = None
    child_construct_ids: list[str] = field(default_factory=list)
    related_edges: list[ConstructEdge] = field(default_factory=list)
    construct_path: tuple[str, ...] = ()
    source_span_ids: list[str] = field(default_factory=list)
    cutline_reason: str | None = None
    frontier_status: Literal[
        "continue",
        "cutline_partial",
        "cutline_blocked",
        "leaf",
    ] = "leaf"
    metadata: dict[str, Any] = field(default_factory=dict)
```

### IRSChecker

每个 checker 实现同一接口：

```python
class IRSChecker(Protocol):
    checker_id: str
    construct_types: frozenset[str]
    stage_names: frozenset[str]

    def extract_instances(
        self,
        ir: object,
        context: IRSCheckContext,
    ) -> list[ConstructInstance]:
        ...

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        ...
```

### DiagnosticProjector

checker 不应各自拼装完整 diagnostic。推荐由统一 projector 从 report/slot 投影：

```python
class DiagnosticProjector:
    def project(
        self,
        report: ConstructSatisfactionReport,
        diagnostic_registry: DiagnosticRegistry,
        context: IRSCheckContext,
    ) -> list[CompileDiagnostic]:
        ...
```

checker 只负责写清：

```text
slot status
diagnostic_kind
missing_slot
source_span_ids
explanation
```

severity、target_ref、blocks_completion、blocks_rendering、message template、dedup key 由 projector 和 diagnostic registry 统一决定。

## Orchestrator 接入方式

v6 目标是：

```python
reports, diagnostics = irs_runner.run_stage(
    stage_name="stage3_5",
    ir=worker_plan,
    context=context,
)
```

统一写入：

```python
intermediate["construct_satisfaction"][stage_name] = reports
intermediate["stage_local_diagnostics"][stage_name] = diagnostics
```

MVP 可以保留现有 Stage 4/7 checker 调用，但新增 Worker IRS 时应优先使用 runner 形式，以验证扩展接口。

## Authority Boundary

| 层 | 作用 | 是否最终裁决 |
| --- | --- | --- |
| Stage-local IRS | early slot satisfaction report，帮助 prompt/diagnostics/provenance | 否 |
| Post-normalize IRS | normalized / assembled IR 上的 construct-level diagnostic authority | 是，construct-level |
| ExecutableElementGate | executable step 是否可渲染 | 是，step-level |
| ProducerIndex | required output 是否有 producer | 是，output-level |
| DiagnosticProjector / Consolidator | 投影、合并、去重，不重新解释 slot | 否 |
| Future RecursiveIRSEvaluator | construct graph traversal | 未来；不得替代 Gate / ProducerIndex |

## 可扩展性验收标准

新增一种 IRS checker 时，理想改动范围应控制在：

1. 新增或更新 `ConstructIRS` registry 定义。
2. 新增 checker 文件。
3. 注册 checker。
4. 新增单元测试和 stage 集成测试。

不应要求：

1. 大幅修改 orchestrator 主流程。
2. 修改 renderer。
3. 修改 gate，除非该 construct 是 executable element。
4. 复制已有 diagnostic consolidation 逻辑。
5. 在 checker 内手写完整 diagnostic 投影逻辑。

## 风险

### 风险 1：过早做通用递归 evaluator

SPL IR 中有很多 cross-reference，例如 producer index、handoff binding、symbol table、worker graph。过早实现通用递归 evaluator 会把局部 construct 检查和全局一致性检查混在一起。

处理方式：本阶段只设计接口，不实现递归 evaluator。

### 风险 2：checker 继续分散

如果新增 Worker IRS 仍然直接塞到 `WorkerPlanValidator` 或 orchestrator 中，扩展性不会改善。

处理方式：Worker IRS 必须作为第一个 `IRSChecker` 实践。

### 风险 3：DAG 被压扁成单父树

如果只靠 `parent_construct_id`，未来 required output、handoff、policy、exception handler 等 cross-reference 无法准确表达。

处理方式：从 v6 开始预留 `ConstructEdge`。
