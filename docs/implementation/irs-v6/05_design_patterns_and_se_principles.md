# IRS v6 设计模式与软件工程原则说明

## 目标

本文档说明 IRS v6 不是 ad-hoc 的规则堆叠，而是一个面向 NL2SPL 多阶段编译器的静态分析框架。它吸收了若干成熟软件工程模式，但不等同于某一个单独 GoF pattern。

最准确的归类是：

```text
IRS v6 =
  Specification Pattern
  + Plugin / Strategy based checker framework
  + Multi-pass compiler static analysis
  + Diagnostic projection pipeline
  + Future graph / visitor traversal
  + Frontier / cutline partial evaluation
```

一句话概括：

> IRS v6 是一个 metadata-driven、plugin-based、compiler-oriented static analysis framework。

## 1. Specification Pattern

`ConstructIRS` 本质上是 SPL construct 的 specification。

它定义：

```text
construct 需要哪些 slot
哪些 slot syntax-required
哪些 slot required-for-partial
哪些 slot required-for-complete
哪些 slot 缺失时产生 diagnostic
是否允许 partial rendering
无 demand 时是否生成结构
```

对应关系：

| IRS v6 | Specification Pattern 角色 |
| --- | --- |
| `ConstructIRS` | specification definition |
| `SlotSpec` | single predicate / rule |
| `ConstructInstance` | candidate object |
| `IRSChecker.check_instance()` | specification evaluation |
| `SlotSatisfaction` | predicate evaluation result |
| `ConstructSatisfactionReport` | validation result object |

但 IRS 不是普通业务系统里的 specification。它带有 compiler 语义：

```text
partial rendering
diagnostic kind
source provenance
frontier / cutline
renderability authority
compiler phase boundary
```

因此更准确地说，它是：

```text
compiler-aware Specification Pattern
```

## 2. Multi-pass Compiler Static Analysis

NL2SPL pipeline 是 compiler architecture，而不是表单校验器或普通 rule engine。

IRS 的角色更接近：

```text
semantic analysis / static analysis / lint pass
```

例如：

```text
grammar says:
  EXCEPTION_FLOW can be rendered with an empty body

IRS says:
  condition-only exception flow is syntactically renderable but semantically partial

diagnostic says:
  missing_handler
```

IRS 不负责 parsing，也不负责 final rendering。它负责 construct-level semantic completeness analysis。

## 3. Strategy Pattern

`IRSChecker` 是典型 Strategy interface。

不同 construct 的检查逻辑被封装成不同 checker：

```text
ExceptionFlowIRSChecker
StepIRSChecker
WorkerIRSChecker
FutureBlockIRSChecker
FuturePolicyIRSChecker
FutureResourceIRSChecker
```

对应关系：

| IRS v6 | Strategy Pattern 角色 |
| --- | --- |
| `IRSChecker` protocol | strategy interface |
| `WorkerIRSChecker` | concrete strategy |
| `ExceptionFlowIRSChecker` | concrete strategy |
| `IRSRunner` | context / strategy executor |
| `IRSCheckerRegistry` | strategy lookup / registration |

这个模式的工程价值是：新增 construct IRS 时，不需要改 orchestrator 主流程。

## 4. Registry / Plugin Pattern

`SPLConstructRegistry`、`IRSCheckerRegistry`、`DiagnosticRegistry` 都是 Registry / Plugin architecture 的变体。

目标是：

```text
新增 construct IRS
  -> 注册 ConstructIRS
  -> 新增 checker
  -> 注册 checker
  -> runner 自动发现并执行
```

这体现了开放封闭原则：

```text
对扩展开放：新增 checker / registry entry
对修改关闭：不改 orchestrator / renderer / gate 主流程
```

## 5. Pipeline / Responsibility Separation

整个 NL2SPL 是 multi-pass pipeline：

```text
Adapter
-> Span / Route
-> Worker planning
-> Flow / Block / Step / Resource
-> Normalization
-> IRS / Gate / ProducerIndex
-> Renderer
-> Report
```

IRS v6 在 stage 内部又形成小 pipeline：

```text
extract ConstructInstance
-> check slot satisfaction
-> project diagnostics
-> consolidate
-> report
```

它有 Chain of Responsibility 的分层味道，但不应正式归类为 Chain of Responsibility。更准确是：

```text
multi-pass compiler pipeline with responsibility separation
```

因为每个 stage 有固定 compiler 语义，不是“谁能处理谁处理”的请求链。

## 6. Visitor Pattern 的未来形态

当前 v6 明确不实现通用递归 checker。

但未来如果实现：

```python
RecursiveIRSEvaluator.evaluate(root_ids, construct_graph, context)
```

它会接近 Visitor Pattern：

| Future recursive IRS | Visitor Pattern 角色 |
| --- | --- |
| `ConstructGraph` / `ConstructNode` | object structure |
| `RecursiveIRSEvaluator` | traversal driver |
| `IRSChecker` | operation per node type |
| `ConstructSatisfactionReport` | visit result |

当前阶段只能说：

```text
现在是 Strategy / Registry；
未来递归化后，会逐渐接近 Visitor over ConstructGraph。
```

## 7. Composite Pattern 只局部适用

SPL grammar 有天然 containment：

```text
Worker
  -> Flow
      -> Block
          -> Step
```

这部分可以借鉴 Composite Pattern。

但 IRS v6 不能被建模成纯 Composite，因为它还有 DAG / cross-reference：

```text
Step -> RequiredOutput
Handoff -> ChildWorker
Policy -> Worker / Flow / Step
ExceptionFlow -> HandlerStep
```

因此：

```text
containment hierarchy: 可借鉴 Composite
global IRS graph: 必须使用 ConstructGraph / ConstructEdge
```

这也是 v6 引入 `ConstructEdge` 的原因。

## 8. Frontier / Cutline: Fail-fast + Partial Evaluation

frontier / cutline 是 IRS v6 的关键机制。

行为：

```text
缺 required_for_partial
  -> blocked
  -> 停止下钻

缺 required_for_complete 但允许 partial
  -> partial
  -> cutline
  -> 不为缺失 child evidence 制造 child report

有 source-backed child evidence
  -> 才继续检查 child construct
```

对应工程思想：

| IRS 行为 | 工程思想 |
| --- | --- |
| 缺 required_for_partial 直接停止 | fail-fast |
| 缺 required_for_complete 但允许 partial | partial evaluation |
| 无 source-backed child evidence 不下钻 | demand-driven / lazy evaluation |
| `frontier_status` 控制遍历 | short-circuit traversal |

这不是单一 GoF pattern，而是 partial compiler 中的分析边界策略。

## 9. DiagnosticProjector: Projection / Mapper Layer

IRS checker 不直接拼完整 `CompileDiagnostic`，而是：

```text
IRSChecker
  -> ConstructSatisfactionReport / SlotSatisfaction
  -> DiagnosticProjector
  -> CompileDiagnostic
```

这是一种 projection / mapper layer。

好处：

1. checker 只关心 slot 是否满足。
2. severity、message、blocks_completion、dedup key 统一处理。
3. readable report / feedback report 可消费同一套 diagnostics。
4. 未来替换 message template 不影响 checker。
5. 未来做多语言 report 更容易。

这也符合 compiler diagnostic system 的常见实践：analysis pass 发现问题，diagnostic formatting/reporting 不散落在每个 pass 中。

## 10. WorkerPromotion: State / Workflow Gate

Worker / Delegation IRS 不是单纯 validation，它还有状态流转语义：

```text
delegation mention
  -> worker candidate
  -> promotion ready
  -> child worker
  -> handoff
  -> invoke worker
```

`WORKER_CANDIDATE` 与 `WORKER_PROMOTION` 分离后，可以表达：

```text
candidate itself is valid as report-only construct
promotion to child worker is blocked by missing contracts
```

这比把 “candidate incomplete” 和 “promotion blocked” 混在一起更清晰。

## 11. 不应强行套用的模式

### 不是普通 Rule Engine

IRS checker 不调用 LLM、不修改 IR、不补全 slot、不生成 construct。它是 static analysis，不是 active rule engine。

### 不是纯 Composite

SPL containment 可以借鉴 Composite，但全局 construct relation 是 DAG。

### 现在还不是 Visitor

Visitor 是未来递归 evaluator 可能接近的形态。当前只是预留接口。

### 不是 Parser Validator

SPL grammar 只管语法合法性。IRS 管信息需求、partial renderability 和 diagnostic policy。

## 推荐写法

英文表述：

```text
The IRS mechanism adopts a metadata-driven specification model for SPL
constructs, combined with a plugin-based checker architecture and
multi-pass compiler-style static analysis. ConstructIRS defines information
requirements declaratively; IRSChecker implementations evaluate concrete IR
instances through a Strategy-like extension model; DiagnosticProjector
separates analysis results from diagnostic presentation; and a future
RecursiveIRSEvaluator can traverse a construct graph using frontier/cutline
semantics rather than unconditional tree recursion.
```

中文表述：

```text
IRS 机制不是单纯校验器，而是一个面向 NL2SPL 渐进式编译流程的构件级静态分析框架。它借鉴 Specification Pattern，将 SPL 构件的信息需求显式化为 ConstructIRS；借鉴 Strategy/Plugin 架构，将不同构件的检查逻辑封装为可注册的 IRSChecker；借鉴多阶段编译器设计，将局部构件检查、全局一致性检查、可渲染性裁决和最终渲染分层处理；同时通过 frontier/cutline 机制支持 partial SPL，并为未来基于 construct graph 的递归检查预留接口。
```

## 总结

IRS v6 最本质的工程模型是：

```text
Specification Pattern 驱动的 compiler static analysis framework
```

它隐式使用并组合了：

| 模式 / 原则 | IRS v6 中的体现 |
| --- | --- |
| Specification Pattern | `ConstructIRS` / `SlotSpec` |
| Strategy Pattern | `IRSChecker` |
| Registry / Plugin | `SPLConstructRegistry` / `IRSCheckerRegistry` |
| Multi-pass Compiler | stage-local / post-normalize / gate / renderer 分层 |
| Static Analysis | checker 不修改 IR，只输出 reports / diagnostics |
| Visitor Pattern | 未来 recursive evaluator over construct graph |
| Composite Pattern | Worker / Flow / Block / Step containment |
| Graph / DAG | `ConstructEdge` |
| Fail-fast / Partial Evaluation | frontier / cutline |
| Mapper / Projection | `DiagnosticProjector` |
| State / Workflow Gate | `WORKER_CANDIDATE -> WORKER_PROMOTION -> CHILD_WORKER` |
