我的判断：**概念上 IRS 检查是递归/层级化的，但当前实现不应该做一个通用递归检查器。**
MVP/v5 更合理的做法是：**按 SPL 构件层级逐层 materialize + 逐层 slot check，在不完整构件处设置 cutline，停止向更细结构下钻。**

更准确地说，不应叫“逐层渲染时检查”，而应叫：

> **逐层构件生成 / IR materialization 时检查；渲染阶段只消费已经裁决过的 IR。**

因为当前设计里 Stage 11 SPLRenderer 不应该负责补洞、猜 handler、猜 producer 或判断语义完整性。v4/v5 的定位本来就是 partial SPL + diagnostics + provenance，而不是一次性生成完整 SPL；文档也明确说 NL2SPL 输出应包括 partial/complete SPL draft、diagnostics、traces、assumptions/report，而完整 SPL 才近似“完善后的需求 + 高层系统设计”。

---

## 1. IRS 检查应该是“有边界的递归”

SPL 本身有明显层级：

```text
Agent
  -> Worker
      -> Inputs / Outputs
      -> MainFlow / AlternativeFlow / ExceptionFlow
          -> Block
              -> Command / CALL_API / REQUEST_INPUT / INVOKE_WORKER
```

语法上 flow 下面可以有多个 block，block 下面是 command；例如 grammar 里 `MAIN_FLOW`、`ALTERNATIVE_FLOW`、`EXCEPTION_FLOW` 都包含 `{BLOCK}`，而 `BLOCK` 又分为 `SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK`，这些 block 再包含 `{COMMAND}`。

所以从理论上讲，IRS 的 slot satisfaction 也天然是层级化的：

```text
检查 Worker 是否有 main_flow
  -> 检查 Flow 是否有 condition / blocks
      -> 检查 Block 是否有 commands
          -> 检查 Command 是否有 source evidence / action_text / bindings
```

但这个“递归”不能无脑向下走。它必须受两个东西约束：

1. **source signal / materialization**：没有源文本需求，就不生成该构件，也不检查该构件缺什么。
2. **partial cutline**：当前构件已经不完整，且更细结构没有独立 source evidence 时，就停止下钻。

这和 v4 的 “No demand, no structure” 原则一致：用户没有表达某类 SPL 结构时，不生成该结构，也不输出该结构缺失诊断。

---

## 2. 你的理解基本对：发现不完整结构后，当前结构下更细结构通常不用管

例如 `Failure handling: Missing timeframe, conflicting instructions`。

此时能确定的是：

```text
存在 failure condition
```

所以可以 materialize：

```spl
[EXCEPTION_FLOW: missing timeframe]
[END_EXCEPTION_FLOW]
```

然后报：

```text
missing_handler
```

但**不应该继续检查 handler block 下面应该有什么 command**，因为 handler_action 根本没有 source-backed evidence。v5 IRS 文档里也明确说：`EXCEPTION_FLOW` 有 condition 无 handler_action 时是 partial exception flow，handler_action 不应由系统猜测。

所以 cutline 是：

```text
ExceptionFlow.condition satisfied
ExceptionFlow.handler_action missing
=> render partial ExceptionFlow
=> emit missing_handler
=> 不继续生成/检查 handler Block / Command
```

这也正好对应老师当时说的：failure 只说明了失败类型，没有说 failure 之后怎么处理，所以应该得到 partial SPL，而不是 complete SPL。

---

## 3. 但有一个例外：如果更细结构本身有 source evidence，就可以继续下钻

例如原文是：

```text
Failure handling:
If timeframe is missing, ask the user to provide the timeframe.
```

这时不只是有 condition：

```text
condition = timeframe is missing
```

还有 handler action：

```text
handler_action = ask the user to provide the timeframe
```

那就应该继续检查更细层：

```text
ExceptionFlow
  -> handler Block
      -> REQUEST_INPUT
```

然后 REQUEST_INPUT IRS 再检查：

```text
prompt_text 是否有
value_target 是否有
是否明确 source 表达 ask/request/prompt/confirm
```

v5 文档中 Stage 7 的 IRS prompt 规则也说，`REQUEST_INPUT` 只有在 source 明确说 ask/request clarification/prompt/confirm 时才能生成，不能仅仅因为信息缺失就自动生成。

所以不是“发现不完整结构后绝对不看下面”，而是：

> **没有 source-backed child evidence，就不下钻；有明确 child evidence，才继续 materialize child construct 并检查 child IRS。**

---

## 4. 推荐的工程规则：top-down frontier checking

可以把当前设计改成这个规则：

```text
1. 从高层构件开始检查。
2. 只有 source signal 足够时，才 materialize 构件。
3. 对 materialized 构件检查它自己的 IRS slots。
4. 如果 required_for_partial 缺失：
   - 不渲染该构件；
   - 只输出 candidate/report/diagnostic；
   - 停止下钻。
5. 如果 required_for_complete 缺失，但 renderable_without=True：
   - 渲染 partial 构件；
   - 输出 diagnostic；
   - 除非有明确 source-backed child evidence，否则停止下钻。
6. 如果当前构件 complete：
   - 继续检查已经 materialized 的 child constructs。
```

伪代码大概是：

```python
def check_construct(node, irs, context):
    if not node.materialized and not has_source_signal(node, irs, context):
        return no_report()

    report = check_slots(node, irs, context)

    if missing_required_for_partial(report):
        report.renderable = False
        report.completeness = "blocked"
        return [report]  # cutline

    if missing_required_for_complete(report):
        if irs.partial_rendering_allowed:
            report.renderable = True
            report.completeness = "partial"

            if not has_source_backed_child_evidence(node, context):
                return [report]  # cutline

        else:
            report.renderable = False
            report.completeness = "blocked"
            return [report]  # cutline

    child_reports = []
    for child in materialized_children(node):
        child_irs = registry.get(child.construct_type)
        child_reports.extend(check_construct(child, child_irs, context))

    return [report] + child_reports
```

但我不建议你现在真的实现这个 generic recursive engine。当前应该先做 **stage-local frontier checking**。

---

## 5. 当前 MVP/v5 不要做“通用递归 IRS validator”

原因是工程复杂度会迅速膨胀：

```text
Worker -> Flow -> Block -> Step
Required output -> ProducerIndex -> Step/Handoff/API
Child worker -> Handoff -> Binding -> Parent/Child SymbolTable
Exception flow -> Handler block -> REQUEST_INPUT/CALL_API/COMMAND
```

这些不是单纯树结构，有很多跨边引用。文档也明确说 IRS 只负责 local construct-level checking，Stage 9.5 仍要保留做 global consistency checking，因为 required output producer、variable use-before-def、worker handoff binding、constraint-step conflict、child worker 调用关系等问题不是单个 construct 内部能发现的。

所以当前实现建议是：

```text
Stage 4: 只检查 Flow 级 IRS
Stage 5: 可暂时只组装 Block，不做复杂 IRS
Stage 7: 检查 Step/Command 级 IRS
Stage 9.5: 汇总 stage-local diagnostics + 做全局检查
Gate: 最终决定 command 是否可渲染
ProducerIndex: 最终决定 required output 是否有 producer
Renderer: 只渲染已裁决结构
```

这和 v4 pipeline 现状也匹配：Stage 4 做 Flow Assembly，Bridge 生成 partial ExceptionFlow，Stage 7 做 Step Extraction，Stage 9.5 做 IR Normalization，Gate 做可渲染过滤，Stage 11 才渲染 SPL。

---

## 6. 几个典型 cutline 例子

### 例 1：ExceptionFlow

```text
有 failure condition
无 handler action
```

结果：

```text
生成 partial ExceptionFlow
报 missing_handler
不检查 handler block / command
```

### 例 2：Required Output

```text
Required outputs: source/evidence set
但 process 里没有任何 producer step
```

结果：

```text
渲染 required output declaration
ProducerIndex 报 missing_output_producer
不合成 producer command
```

文档也明确说 declared required output 可以渲染，missing producer 是 completion diagnostic，不是发明 producer step 的理由。

### 例 3：Child Worker / Delegation

```text
用户只说 optional subtask / source gathering / template matching
但没有 input/output contract、invocation point、result handoff
```

结果：

```text
只保留 WORKER_CANDIDATE / delegation intent
不生成 CHILD_WORKER
不检查 child worker 内部 flow/step
报 type_or_contract_ambiguity
```

### 例 4：REQUEST_INPUT

```text
系统发现缺 timeframe
但原文没有说 ask user
```

结果：

```text
不能生成 REQUEST_INPUT
只能报 missing slot / assumption / suggested clarification
```

如果原文明确说：

```text
Ask the user for missing timeframe.
```

才继续生成并检查 REQUEST_INPUT。

---

## 7. 所以你的表述可以修正成这样

你原话是：

> 应该是在 SPL 逐层渲染时，直到发现有不完整的结构？当前结构下更细的结构就不用管了？

我建议改成：

> IRS 检查应发生在 SPL 构件逐层 materialize / IR assembly 的过程中，而不是最终文本渲染时。检查从高层构件向低层构件推进；一旦某个构件缺失 `required_for_complete` slot，但允许 partial rendering，就在该构件处形成 cutline：渲染可确定的 partial structure，输出 diagnostic，不再为其缺失的子结构生成或检查更细 IRS。只有当源文本中存在明确的 child construct evidence 时，才继续下钻检查子构件。

这个定义比较稳，也能避免当前实现复杂化。

---

## 8. 最终建议

当前先不要实现 recursive IRS checker。先实现这个更轻量的版本：

```text
IRS registry:
  定义 construct slots

Stage 4:
  检查 EXCEPTION_FLOW / MAIN_FLOW / ALTERNATIVE_FLOW 的 slot satisfaction

Stage 7:
  检查 GENERAL_COMMAND / REQUEST_INPUT / CALL_API / INVOKE_WORKER 的 slot satisfaction

Stage 9.5:
  读取 stage-local reports
  去重 diagnostics
  跑 ProducerIndex
  接 Gate 后 diagnostics

Renderer:
  不做 IRS 检查
  只渲染已通过裁决的 IR
```

这样你获得的是**递归思想上的层级检查**，但工程上是**分阶段、有限边界、可控实现**。这比一上来写一个通用递归 validator 更符合当前 MVP 目标。
