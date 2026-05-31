# 递归 IRS 检查预留接口设计

## 目标

未来 IRS 需要从平铺检查演进为构件层级检查。例如：

```text
EXCEPTION_FLOW
  -> handler BLOCK
      -> REQUEST_INPUT
```

当前阶段不实现通用递归 checker，但必须避免留下架构负债。本文档定义未来递归检查所需的最小接口准备。

## 递归检查的正确语义

IRS 递归不是无条件向下遍历。它必须遵守 frontier / cutline：

```text
1. 只有 materialized construct 或 source-demanded construct 才检查。
2. 当前 construct 缺少 required_for_partial slot 时，blocked，停止下钻。
3. 当前 construct 缺少 required_for_complete slot，但允许 partial rendering 时，形成 cutline。
4. 有 source-backed child evidence 时，才继续检查 child construct。
5. 无 source-backed child evidence 时，不生成 child report，也不产生 child missing-slot 噪声。
```

## 例子：ExceptionFlow

### Condition only

输入：

```text
Failure handling: Missing timeframe.
```

结果：

```text
EXCEPTION_FLOW
  condition = satisfied
  handler_action = missing
  completeness = partial
  renderable = true
  cutline_reason = missing_handler_action
```

不继续检查：

```text
handler BLOCK
REQUEST_INPUT
GENERAL_COMMAND
```

### Condition + handler

输入：

```text
If timeframe is missing, ask the user for the timeframe.
```

结果：

```text
EXCEPTION_FLOW
  condition = satisfied
  handler_action = satisfied
  child = BLOCK(handler)

BLOCK
  block_type = satisfied
  child = REQUEST_INPUT

REQUEST_INPUT
  prompt_text = satisfied
  value_target = checked
```

## Construct graph 最小模型

未来递归 checker 需要一个 construct graph，而不是直接递归原始 IR dataclass。

```python
@dataclass
class ConstructNode:
    construct_id: str
    construct_type: str
    parent_id: str | None
    child_ids: list[str]
    construct_path: tuple[str, ...]
    ir_ref: object
    source_span_ids: list[str]
    materialized: bool
    source_demanded: bool
    metadata: dict[str, Any]
```

图可以是树，也可以是 DAG。因为 SPL 中存在 cross-reference：

```text
Step -> output variable -> required output
Handoff -> child worker
ExceptionFlow -> handler step via flow_ref
```

因此未来实现应以 graph traversal 为主，不应假设严格树结构。

## Frontier report 字段

`ConstructSatisfactionReport` 建议扩展以下字段：

```python
parent_construct_id: str | None = None
child_construct_ids: list[str] = field(default_factory=list)
construct_path: tuple[str, ...] = ()
source_span_ids: list[str] = field(default_factory=list)
cutline_reason: str | None = None
frontier_status: Literal[
    "continue",
    "cutline_partial",
    "cutline_blocked",
    "leaf",
] = "leaf"
```

字段语义：

| 字段 | 作用 |
| --- | --- |
| `parent_construct_id` | 支持向上解释当前 construct 属于谁 |
| `child_construct_ids` | 支持向下遍历 |
| `construct_path` | 稳定报告路径，便于递归和 debug |
| `source_span_ids` | 支持 provenance 和 anti-fabrication |
| `cutline_reason` | 解释为什么停止下钻 |
| `frontier_status` | 未来递归 evaluator 的控制信号 |

## Future RecursiveIRSEvaluator 草案

当前不实现，但接口应可容纳：

```python
class RecursiveIRSEvaluator:
    def evaluate(
        self,
        root_ids: list[str],
        graph: ConstructGraph,
        context: IRSCheckContext,
    ) -> list[ConstructSatisfactionReport]:
        reports = []
        for root_id in root_ids:
            reports.extend(self._evaluate_node(root_id, graph, context))
        return reports

    def _evaluate_node(
        self,
        node_id: str,
        graph: ConstructGraph,
        context: IRSCheckContext,
    ) -> list[ConstructSatisfactionReport]:
        node = graph.get(node_id)
        report = self._check_current(node, context)

        if report.frontier_status in {"cutline_partial", "cutline_blocked", "leaf"}:
            return [report]

        child_reports = []
        for child_id in report.child_construct_ids:
            child_reports.extend(self._evaluate_node(child_id, graph, context))

        return [report] + child_reports
```

## 当前阶段需要做的接口准备

### 1. 新增 report 字段

先让新增 checker 输出 parent/path/cutline 信息。现有 checker 可后续迁移。

### 2. 新增 ConstructInstance

每个 stage checker 先抽取 `ConstructInstance`，不要直接在 checker 中到处解析 IR。

### 3. 新增 IRSCheckContext

统一传递 spans/routes/resources/worker_plan 等上下文。

### 4. 新增 checker registry / runner

后续递归 evaluator 可以复用同一 checker registry。

## 当前不做的事

1. 不实现 graph traversal。
2. 不改变 renderer。
3. 不把 Stage 4/7 现有 checker 全量重写。
4. 不要求所有现有 reports 立即补齐 parent/path。

## 验收标准

1. 新增 Worker IRS checker 输出的 report 带 `parent_construct_id`、`construct_path`、`frontier_status` 或兼容 metadata。
2. 对 missing child evidence 的场景产生 cutline，而不是继续制造 child missing diagnostics。
3. 对 source-backed child evidence 的场景能表达 child construct relation，即使暂不递归执行。
4. 文档和测试明确区分 stage-local checking 与 future recursive checking。
