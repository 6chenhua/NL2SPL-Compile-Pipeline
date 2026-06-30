# SPL Editing Issue Presentation 缺少结构化目标事实投影

日期：2026-07-01  
状态：待设计与修复  
相关组件：SPL Editing Presentation、IssueInventory、TargetResolver、RepairContextBuilder、RepairCatalog、AI Issue Explanation

---

## 1. 问题概述

当前 SPL Editing 的部分 Editable Issue 主要通过 issue category 对应的固定模板展示。
模板能够说明问题类别，却没有稳定投影当前 issue 对应的具体目标、候选任务或来源语义。

例如当前 demo 展示：

```text
Worker delegation is underspecified
```

用户无法判断：

```text
1. 哪个 Worker 或候选任务存在问题；
2. 当前是否已经存在具体 child worker；
3. 这是具体 worker handoff 缺失，还是泛化 delegation policy 不完整；
4. 三种 repair option 分别会作用于什么目标。
```

这不是单纯的文案问题，而是 Presentation DTO 缺少 issue-specific structured facts。

---

## 2. 当前案例

当前 issue 的结构化 target 是：

```text
construct_type = WORKER_PROMOTION
target_ref = worker_promotion:del_s31
```

其来源 span `s31` 表达的是泛化委派政策：

```text
Optional delegated subtasks such as source gathering or template matching may be
used if bounded and the returned evidence is normalized into approved evidence
carriers.
```

当前 snapshot 中没有与 `del_s31` 对应的具体 child worker。`del_s31` 是 compiler
生成的 promotion candidate 标识，不是可以直接展示给普通用户的 Worker 名称。

因此，下面两种展示都不正确：

```text
Worker delegation is underspecified
```

问题：只有类别，没有目标语义。

```text
Worker delegation is underspecified: del_s31
```

问题：暴露 compiler id，并错误暗示存在具体 child worker。

更准确的用户语义应接近：

```text
Possible delegated task is underspecified:
source gathering or template matching

No concrete child worker has been defined.
```

具体文案不是本问题记录的最终设计结论，但展示必须区分 concrete worker、candidate
task、delegation policy 和 unknown target。

---

## 3. 根因

### 3.1 Presenter 只消费 category-level copy

`WorkerDelegationPresenter` 当前使用固定标题：

```text
Worker delegation is underspecified
```

`DisplayContext` 只承载 missing items 和 source excerpt，没有承载 delegation subject
的类型、名称、摘要或具体程度。

### 3.2 已有结构化事实没有进入 Presentation DTO

后端可能已经掌握以下部分事实：

```text
TargetResolverResult.canonical_name
RepairContext.metadata.derived_child_worker_id
WorkerPlanIR worker identity
promotion candidate source spans
candidate task summary
delegation policy source excerpt
```

但这些事实没有经过统一 contract 投影为用户可读的 issue subject。

### 3.3 固定模板被错误用于 issue-specific facts

固定模板适合表达稳定产品语义，例如 category label、通用影响和安全说明；它不应替代：

```text
目标对象是谁；
当前对象是否真实存在；
缺少哪些 slot；
当前可执行哪些 repair strategy；
该 issue 来自具体 construct 还是 policy-level candidate。
```

### 3.4 AI explanation 继承了不完整的 Presentation Facts

AI issue explanation 消费的基础 DTO 没有明确 delegation subject，因此即使生成了更自然的
解释，也无法可靠回答“具体是哪个 Worker”。LLM 还可能把 candidate 或 policy 错误解释成
已经存在的 child worker。

---

## 4. 架构风险

### 4.1 用户无法做出 repair option 选择

在不知道目标任务或 Worker 的情况下，用户无法判断应该：

```text
Create worker handoff contract
Convert to main-flow step
Ask user for missing information
```

### 4.2 Presentation 可能与真实 capability 不一致

当前 worker handoff repair 需要一个可解析的具体 child worker。若 snapshot 中不存在 child
worker，却仍把 `Create worker handoff contract` 显示为 available，则 UI capability 与 handler、
materializer 的实际前置条件不一致。

### 4.3 Compiler ID 可能泄漏到默认视图

如果直接使用 `target_ref` 或 `canonical_name` 兜底，`del_s31` 等 compiler-generated id
可能进入标题，违反 degraded presentation 默认不暴露内部标识的原则。

### 4.4 LLM 可能成为事实来源

若为解决标题不具体而让 LLM 自由生成目标描述，LLM 可能发明 child worker、任务边界或
handoff 关系。Presentation facts 必须来自结构化 artifact，LLM 只能做语言增强。

### 4.5 新 issue family 会重复出现同类缺口

该问题不只影响 worker delegation。以下 issue 都需要 issue-specific subject projection：

```text
missing_handler -> exception condition / exception flow subject
missing_output_producer -> required output subject
worker delegation -> concrete worker / candidate task / policy subject
API deferred validation -> API declaration subject
future construct issues -> construct-specific subject
```

---

## 5. 必须保持的边界

### 5.1 可以使用固定模板的内容

```text
category label
通用 impact / why-it-matters
repair option label 和通用说明
confirmation safety copy
verification status copy
unavailable reason copy
```

### 5.2 必须由结构化后端事实生成的内容

```text
具体 target identity 或 target summary
subject specificity：concrete / candidate / policy / unknown
missing slots
source-backed summary
当前 artifact 是否存在
repair option availability
degraded reason
```

不得通过解析 `CompileDiagnostic.message`、feedback report 或 UI 文案取得这些主要事实。

### 5.3 LLM 的允许范围

LLM 可以异步生成：

```text
更自然的问题解释
选项 trade-off
选择建议
面向用户的澄清问题
```

LLM 不得决定或覆盖：

```text
issue category
target identity
missing slots
repairability
available repair strategies
compiler authority facts
```

LLM 不可用时，确定性 issue list 和 detail 必须仍然完整可用。

---

## 6. 大致解决方向

后续设计应引入统一的 issue subject projection contract。概念上可表达为：

```python
@dataclass(frozen=True)
class IssueSubjectView:
    subject_kind: str
    display_name: str | None
    summary: str | None
    specificity: Literal["concrete", "candidate", "policy", "unknown"]
    source_excerpt: str | None
    source_ref_ids: tuple[str, ...]
```

预期数据流：

```text
ArtifactSnapshot
+ EditableIssue / UserFacingIssue
+ TargetResolverResult
+ RepairContext
+ structured source facts
  -> IssueSubjectView
  -> deterministic IssuePresentationView
  -> optional cached AI explanation
  -> CLI / UI
```

各 issue family 可以拥有自己的 subject resolver，但必须输出统一 contract。Presenter 只组合：

```text
固定产品文案
+ IssueSubjectView
+ missing slots
+ capability-derived repair options
```

---

## 7. Worker Delegation 的后续审查点

后续修复该案例时至少需要回答：

```text
1. 当前 target 是 concrete worker、candidate task，还是 delegation policy？
2. 是否存在结构化且用户可读的 task summary？
3. 是否存在具体 child worker identity？
4. CreateWorkerHandoffContract 的前置条件是否满足？
5. 若不存在 child worker，该选项应 unavailable，还是 strategy closure 应先创建 worker？
6. Convert to main-flow step 实际转换的是哪个 source-backed task？
7. 默认标题和详情如何避免暴露 promotion candidate id？
8. AI explanation 是否只能消费已确认的 IssueSubjectView？
```

---

## 8. 初步验收方向

未来解决方案至少应满足：

```text
1. 默认 issue list 能说明问题作用于哪个用户可理解的对象或任务。
2. concrete、candidate、policy 和 unknown subject 被明确区分。
3. 无具体 child worker 时不得显示或暗示一个虚构 Worker。
4. compiler-generated id 只进入 Advanced Details。
5. repair option availability 与真实 runtime capability 一致。
6. Presentation 不解析 diagnostic.message 获取主要目标事实。
7. LLM explanation 不得覆盖结构化 subject facts。
8. LLM 失败时 deterministic presentation 仍完整可用。
9. missing_handler、required output、worker delegation 和 API review 均有 subject projection 测试。
10. CLI/UI 只消费 Presentation DTO，不自行推断 target subject。
```

---

## 9. 非目标

本问题记录暂不定义：

```text
1. IssueSubjectView 的最终字段和模块路径；
2. 每个 issue family 的完整 resolver 实现；
3. worker promotion 的最终 repair strategy closure；
4. UI 的最终文案和布局；
5. LLM explanation prompt 的具体格式。
```

这些内容应在后续设计和实施计划中单独闭合。
