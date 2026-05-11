结论先说：**你现在对多 Worker 的方向是对的，但“主动识别 delegation + 被动处理不可表达嵌套”还不足以定义多 Worker 边界。**

更准确地说，**多 Worker 的边界不应该由“是否出现 subtask 字样”或“是否出现不可处理 block 嵌套”单独决定，而应该由“是否存在可调用、可契约化、可独立失败/完成的责任单元”决定**。

也就是：

> Worker 边界 = 责任边界 + 输入输出契约 + 调用点 + 失败策略 + 独立价值。

嵌套 block 只是发现信号之一，不是本质。

---

# 1. 对你当前多 Worker 方案的系统性评价

## 1.1 你把多 Worker 提到 Flow 之前，这是正确的

你最新设计文档已经把自顶向下原则改成：

1. 先判断是否需要多个 Worker，以及 Worker 之间的数据协作边界；
2. 再确定每个 Worker 内部的 Flow；
3. 再确定每个 Flow 中的 Block；
4. 最后填充 Step。

这个调整非常关键。因为 Worker 不是 Flow 下面的附属品，Worker 是比 Flow 更粗粒度的可调用单元。你的 `delegation_plan_todo.md` 也明确指出，目前把 `FlowStructureIR.delegation_candidates` 当兼容桥接，会把“执行路径分类”和“Worker 边界规划”混在一起，这是设计债；Worker 边界应该在 `FlowStructureIR` 之前决定。

所以大方向没问题：**长期目标应该是 Stage 3 后、Stage 4 前引入 WorkerBoundaryPlanner / WorkerPlanIR。**

---

## 1.2 主动识别多 Worker 是必要的，但远远不够

你说的第一类：

> 初始 NL 中明确提及 subtask 类似描述，则识别为需要多 Worker。

这是必要信号，但不能直接等价于多 Worker。

例如：

```text
Use a source gathering subtask.
Delegate template matching.
Ask a child worker to validate citations.
```

这些确实是强信号。

但下面这种就不一定：

```text
First split the task into subtasks.
Identify sub-tasks in the user's request.
Summarize each subtask.
```

这里的 “subtask” 只是内容对象，不一定是 SPL Worker。

所以主动识别需要再加一层判断：

```text
显式提到 subtask / delegate / worker
    ↓
是否有明确输入？
是否有明确输出？
是否由 parent worker 调用？
是否完成后把结果交还 parent worker？
是否有独立失败策略？
    ↓
是 → child worker
否 → 普通 step / block / concept
```

你的 TODO 里 `WorkerSpecIR` 和 `WorkerHandoffIR` 已经开始往这个方向走了：Worker 需要 `purpose`、`owned_span_ids`、`input_contract`、`output_contract`、`depends_on`，handoff 需要 `from_worker`、`to_worker`、`condition_text`、`input_bindings`、`output_bindings`、`failure_policy`。 这说明你已经意识到：**Worker 不是一个标签，而是一个带契约的调用单元。**

---

## 1.3 被动发现多 Worker 是有价值的，但不能以“嵌套 block”为唯一依据

你说的第二类：

> 如果发现多个 SPL BLOCK 嵌套，根据 SPL 语法 BLOCK 不允许嵌套，把嵌套 block 拆成子 worker。

这个思路有价值，但要小心。因为 **不可表达的控制结构不一定都应该抽成 Worker**。

有三种可能处理方式：

```text
1. 结构扁平化
2. 条件合并 / 条件提升
3. 抽成 child worker
```

只有当前两者会损失语义，且该嵌套区域本身具备清晰责任和输入输出时，才应该抽成 child worker。

你的文档明确说 Block 不嵌套 Block，`SEQUENTIAL_BLOCK` 内只能包含 `COMMAND`，不应再包含其他 block；如果遇到嵌套，应扁平化或提取为独立 Block。 SPL grammar 也定义了 `BLOCK := SEQUENTIAL_BLOCK | IF_BLOCK | LOOP_BLOCK`，而 `IF_BLOCK`、`WHILE_BLOCK`、`FOR_BLOCK` 的 body 都是 `{COMMAND}`，不是 `{BLOCK}`。

因此，从语法上看，你说“嵌套 block 是问题”没错。但从架构上看，**语法限制只能触发 repair，不能直接决定 worker boundary**。

---

## 1.4 2.1 比 2.2 更合理，但还需要一个“不可表达区域 IR”

你提出：

### 2.1 提前发现不可处理嵌套

在 Stage 5 区分 block 时，只区分顶层 block；如果发现顶层 block 内部还有可区分 block，则把此 block 处理成 delegation_candidate。

这个方向比 2.2 好，因为它在 IR 层修复，而不是等 SPL 生成后再补救。

但我建议不要直接输出 `delegation_candidate`，而是先输出一个更中性的结构，例如：

```json
{
  "region_id": "cr_1",
  "source_span_ids": ["s12", "s13", "s14"],
  "reason": "nested_control_structure",
  "outer_control": "FOR",
  "inner_control": "IF",
  "can_flatten": false,
  "suggested_repairs": [
    "extract_child_worker",
    "compound_condition",
    "state_variable_rewrite"
  ]
}
```

可以叫：

```text
ControlComplexityRegionIR
```

或者简单一点：

```text
UnrepresentableControlRegionIR
```

然后再由 WorkerBoundaryPlanner 或 IRNormalizer 决定：

```text
能扁平化 → 扁平化
能条件合并 → 条件合并
不能表达且有清晰 IO → child worker
不能表达且没有清晰 IO → 报 warning / 保守降级为 COMMAND / 要求人工检查
```

这样比“发现嵌套 = delegation_candidate”更稳。

---

## 1.5 2.2 只能作为 validator/normalizer 的兜底，不能作为主流程

你说：

> 如果生成的 SPL 中发现未解决 block 嵌套，那么将嵌套 block……

这应该保留，但只作为最后一道防线。

原因是：一旦到了 SPL 生成阶段才发现嵌套，说明前面的 IR 已经污染了。此时再从 SPL 文本反推 WorkerPlan，很容易丢失 span provenance、变量来源、constraint target 和 handoff 信息。

所以 2.2 应该定位为：

```text
SPLSyntaxValidator / IRNormalizer fallback
```

规则是：

```text
如果发现 nested block：
    1. 阻止最终渲染为合法结果；
    2. 回溯到 BlockStructureIR / WorkerPlanIR；
    3. 尝试结构修复；
    4. 修复失败则报 validation error。
```

你 TODO 里已经有类似原则：unresolved `INVOKE_WORKER` 是 error，不能降级成普通 COMMAND；每个 `INVOKE_WORKER` 都必须有 WorkerPlanIR target、child worker contract 和 declared variable handoff。 这类原则也应该扩展到 nested block。

---

# 2. 你对“可处理嵌套 / 不可处理嵌套”的判断

你列的两种可处理嵌套基本正确，但还可以更精确。

## 2.1 顺序结构中出现 IF/LOOP：可处理

你说：

> 顺序结构中出现一个 IF/LOOP，只需要把 sequential 拆分，然后中间插入 IF/LOOP BLOCK。

这是对的。

例如自然语言：

```text
Do A. If condition, do B. Then do C.
```

不要生成：

```text
SEQUENTIAL_BLOCK
    COMMAND A
    IF condition
        COMMAND B
    END_IF
    COMMAND C
END_SEQUENTIAL_BLOCK
```

而应生成：

```text
SEQUENTIAL_BLOCK
    COMMAND A
END_SEQUENTIAL_BLOCK

DECISION-1 [IF condition]
    COMMAND B
[END_IF]

SEQUENTIAL_BLOCK
    COMMAND C
END_SEQUENTIAL_BLOCK
```

这只是 block 拆分，不需要 child worker。

---

## 2.2 IF/LOOP 中出现顺序执行：可处理，但不是 `SEQUENTIAL_BLOCK`

你说：

> IF/LOOP 结构中嵌套 sequential，这其实是 SPL 支持的，只不过 IF/LOOP 中的顺序执行 COMMAND 没有标记上 SEQUENTIAL_BLOCK。

这个判断是对的，而且要严格按 grammar 来理解。

SPL grammar 中 `IF_BLOCK` / `WHILE_BLOCK` / `FOR_BLOCK` 的 body 是 `{COMMAND}`，不是 `{BLOCK}`。也就是说，IF 里面多个命令天然就是顺序执行，不需要包一个 `SEQUENTIAL_BLOCK`。

所以：

```text
IF A:
    do B
    do C
```

是可处理的，因为它只是：

```text
DECISION-1 [IF A]
    COMMAND-1 [COMMAND do B]
    COMMAND-2 [COMMAND do C]
[END_IF]
```

但如果生成：

```text
DECISION-1 [IF A]
    [SEQUENTIAL_BLOCK]
        COMMAND-1 ...
    [END_SEQUENTIAL_BLOCK]
[END_IF]
```

按当前 grammar 反而不合法。这里要注意：你的 indentation spec 示例里曾出现 IF 内包含 `[SEQUENTIAL]` 的写法，但 grammar 当前定义并不是这样，建议最终以 grammar 为准，或者统一修订两份规范。

---

## 2.3 你遗漏了一类“可处理”：条件合并

有些嵌套 IF 不一定要 child worker，可以合并条件。

例如：

```text
If sources are needed:
    If sources are available:
        retrieve sources
```

可以转为：

```text
IF sources are needed and sources are available:
    retrieve sources
```

这不需要 child worker。

再比如：

```text
If user provided timeframe:
    If timeframe is valid:
        use timeframe
```

也可以变成：

```text
IF user provided timeframe and timeframe is valid:
    use timeframe
```

但注意，如果 inner IF 有 ELSE，或者 inner branch 里有多个不同结果，条件合并可能变复杂。

---

## 2.4 你还遗漏了一类“可处理”：条件提升 / guard step

有些嵌套可以通过先生成状态变量来处理。

例如：

```text
If sources are needed:
    If approved connectors are available:
        retrieve sources
```

可以先做：

```text
COMMAND-1 [COMMAND Determine whether sources are needed and approved connectors are available RESULT can_retrieve_sources: boolean]
DECISION-1 [IF can_retrieve_sources]
    COMMAND-2 [COMMAND retrieve sources]
[END_IF]
```

这也不需要 child worker。

---

## 2.5 真正不可处理的嵌套

我建议把不可处理嵌套定义为：

> 不能通过 block 拆分、条件合并、条件提升、状态变量改写，在同一个 worker 内无损表达的控制结构。

典型包括：

```text
FOR item in items:
    IF item is valid:
        retrieve evidence
    ELSE:
        ask clarification
```

因为 `FOR_BLOCK` body 只能放 COMMAND，不能放 IF_BLOCK。你可以把 “if item is valid then retrieve else ask” 压缩成一个 COMMAND，但这会丢失结构化控制流。如果这个 per-item 逻辑重要，就适合抽成：

```text
FOR each item:
    INVOKE ItemProcessingWorker
```

再由 `ItemProcessingWorker` 内部表达自己的 IF / EXCEPTION。

另一个例子：

```text
IF evidence is insufficient:
    WHILE user can provide more sources:
        ask for source
        validate source
```

如果这是一个复杂的恢复协议，也可以抽成 `EvidenceRecoveryWorker`。

---

# 3. 多 Worker 和单 Worker 的本质边界

我建议给系统一个明确的定义：

## 3.1 Worker 是什么？

在 SPL 里，一个 Worker 对应一个 `INSTRUCTION`，而 SPL prompt 可以包含多个 `INSTRUCTION`。grammar 里 `SPL_PROMPT := ... {INSTRUCTION}`，`WORKER_INSTRUCTION := [DEFINE_WORKER ...] ... [END_WORKER]`，这说明多 Worker 是 SPL 的一等结构。

所以 Worker 不是普通 block，也不是普通 step。它是：

```text
可被调用的、有输入输出契约的、拥有内部流程的任务单元。
```

## 3.2 Child Worker 的必要条件

我建议把 child worker 的必要条件定义为四个硬门槛：

```text
1. 有明确责任 purpose
2. 有明确输入 input_contract
3. 有明确输出 output_contract
4. 有明确 parent handoff / invocation point
```

如果这四个缺任何一个，就不要生成 child worker。

也就是说，下面这种不够：

```text
“Handle evidence.”
```

因为它没有明确输入输出。

下面这种更够：

```text
“Given available connectors and request context, gather source evidence, normalize it into evidence carriers, and return evidence set plus provenance log.”
```

它有：

```text
input: request_context, connectors
output: source_evidence_set, provenance_log
purpose: source gathering and provenance maintenance
handoff: parent invokes when sources are needed and available
```

---

## 3.3 多 Worker 的正向信号

我建议 WorkerBoundaryPlanner 识别以下信号。

### 信号 A：显式 delegation

例如：

```text
delegate source gathering
use a bounded subtask
invoke a template matching worker
```

强信号，但仍需检查输入输出契约。

### 信号 B：多步、可复用、独立输入输出

你的设计文档已经把 delegation 映射分得比较清楚：外部系统单次调用映射到 `CALL_API`；多步、可复用、独立输入输出映射到 `INVOKE_WORKER`；多步且依赖外部系统可以是 `INVOKE_WORKER + 内部 CALL_API`。

这个表非常重要，可以直接扩成 Worker 边界判断规则。

### 信号 C：独立失败策略

如果某段逻辑有自己的失败条件，而且失败后不只是普通 main flow 继续，而是有专门恢复策略，就适合成为 worker。

例如：

```text
SourceGatheringWorker
- source access unavailable
- evidence shortage
- provenance failure
```

这些失败和主 draft 生成不同，适合局部封装。

### 信号 D：复杂控制结构无法在当前 worker 中表达

也就是你说的被动发现。但必须加条件：

```text
不可表达控制结构 + 清晰责任 + 清晰输入输出
```

才抽 child worker。

### 信号 E：循环体内部有复杂协议

例如：

```text
For each document:
    parse metadata
    if metadata missing, recover it
    validate citation
    return normalized record
```

这类最适合：

```text
FOR each document:
    INVOKE DocumentProcessorWorker
```

### 信号 F：不同资源权限 / 集成上下文

例如：

```text
source retrieval
template matching
database search
external API normalization
```

如果只是单次 API 调用，用 `CALL_API` 即可；如果包含搜索、过滤、归一化、重试、证据构造、provenance，就适合 child worker。

### 信号 G：可独立测试

如果一个候选子任务可以单独写 inputs / expected outputs / failure cases，它就是强 child worker 信号。

---

## 3.4 多 Worker 的反向信号

以下情况默认不应该拆 worker。

### 反向信号 A：普通顺序步骤

```text
parse request → identify missing fields → draft response
```

这是 main worker 内部流程。

### 反向信号 B：单个 IF / FOR / WHILE

简单条件和循环由 Block 表达，不需要 worker。

### 反向信号 C：revision

`If the user asks for revision, revise while rechecking constraints.`

这通常是 `ALTERNATIVE_FLOW`，不是 child worker。你的 TODO 测试项里也提到：revision 不应被当成 child worker，除非明确 delegated。

### 反向信号 D：exception handling

`Evidence shortage`、`missing timeframe`、`user refusal` 默认是 `EXCEPTION_FLOW`，不是 worker。除非异常恢复本身是复杂协议，例如 `EvidenceRecoveryWorker`。

### 反向信号 E：单次外部 API 调用

```text
Call search API.
Call calendar API.
Call maps API.
```

默认是 `CALL_API`，不是 `api_adapter worker`。

### 反向信号 F：只是为了绕开语法限制

如果没有清晰 IO，只是为了不生成嵌套 block，就不要轻易 child worker。可以用条件合并、状态变量、普通 COMMAND 或 validation error。

---

# 4. 我建议的多 Worker 判断框架

可以把 WorkerBoundaryPlanner 设计成两阶段。

## 4.1 先生成 CandidateTaskUnit

不要一上来决定 worker。先让 LLM 找候选任务单元：

```json
{
  "candidate_id": "tu_1",
  "source_span_ids": ["s7", "s8"],
  "task_text": "retrieve sources using approved source recipes and maintain provenance",
  "purpose": "source gathering and provenance maintenance",
  "candidate_kind": "delegated_subtask",
  "possible_inputs": ["request_context", "connectors_or_source_repositories"],
  "possible_outputs": ["source_evidence_set", "provenance_log"],
  "signals": [
    "multi_step",
    "bounded_io",
    "external_resource",
    "independent_failure_policy"
  ]
}
```

## 4.2 再做 WorkerBoundaryDecision

对每个 candidate 做判断：

```json
{
  "candidate_id": "tu_1",
  "decision": "extract_child_worker",
  "reason": "The task has a coherent responsibility, bounded inputs, bounded outputs, external source access, and separate provenance failure handling.",
  "worker_name": "SourceGatheringWorker",
  "boundary_kind": "bounded_delegated_subtask"
}
```

可能的 decision：

```text
keep_in_main_worker
extract_child_worker
compile_as_call_api
compile_as_constraint
compile_as_exception_flow
compile_as_alternative_flow
needs_repair_or_warning
```

这样比直接让模型输出 WorkerPlanIR 稳，因为它先暴露中间判断依据。

---

# 5. 多 Worker 的判定规则：建议版本

我建议写进设计文档里的核心规则如下。

## 5.1 必须拆 Worker

满足以下之一，并且有清晰输入输出契约：

```text
1. NL 明确要求 delegated subtask / child worker / separate worker / invoke worker。
2. 子任务是多步、可复用、可独立完成的任务单元。
3. 子任务有独立失败策略，失败不应污染主流程。
4. 子任务内部需要复杂控制结构，而当前 SPL block 无法无损表达。
5. 子任务需要独立资源访问、证据归一化、provenance 维护或其他封装协议。
```

## 5.2 应该保留在单 Worker

满足以下情况：

```text
1. 只是普通顺序步骤。
2. 只是简单 IF / FOR / WHILE。
3. 只是 alternative flow 或 exception flow。
4. 只是普通 constraint。
5. 只是单次 API 调用。
6. 没有清晰输入输出契约。
7. parent worker 无法在明确调用点调用它。
```

## 5.3 可以拆，但不是必须

```text
1. 某个步骤很复杂，但仍可由单个 COMMAND 表达。
2. 某个子流程未来可能复用，但当前输入没有明确复用要求。
3. 某个流程有多个输出，但不复杂。
4. 某个流程有独立测试价值，但没有明确 delegation 描述。
```

这类可以在 MVP 阶段保守不拆，后续通过配置打开：

```text
worker_planning_mode = conservative | balanced | aggressive
```

我建议默认：

```text
conservative
```

即：**能单 Worker 表达就单 Worker，只有强证据才拆。**

---

# 6. 关于 api_adapter worker 的边界

TODO 里有一个开放问题：

> api-only subtasks 应该成为 `api_adapter` worker，还是保留为普通 `CALL_API`？

我的建议：

## 默认：保留为 CALL_API

例如：

```text
Call search API with query.
```

就是：

```spl
COMMAND-1 [CALL SearchApi WITH query=<REF>query</REF> RESPONSE search_result: text SET]
```

## 只有以下情况才做 api_adapter worker

```text
1. API 调用前后有多步处理；
2. 需要重试、分页、过滤、排序、归一化；
3. 需要把多个 API 的结果统一成同一结构；
4. 需要维护 provenance / audit log；
5. API 失败有独立恢复策略；
6. 多个 main/child worker 都要复用这层 API 封装。
```

例如：

```text
Search approved source repositories, normalize results into evidence carriers, maintain provenance, and report evidence shortage.
```

这不是单纯 `CALL_API`，而是：

```text
SourceGatheringWorker 内部可能 CALL SourceRetrievalApi
```

---

# 7. 关于 failure policy 编译到哪里

TODO 里另一个开放问题：

> failure policy 应编译成 `EXCEPTION_FLOW`、local IF/WHILE，还是 constraints？

我的建议是分层：

## 7.1 Worker 内部失败

如果失败属于 child worker 自己的职责范围：

```text
source access unavailable
no source found
provenance invalid
```

放进 child worker 的 `EXCEPTION_FLOW`。

## 7.2 Parent 调用失败

如果失败影响 parent 如何继续：

```text
child worker failed → ask user for sources / produce blocked status
```

放在 parent worker 的 handoff `failure_policy`，然后编译成 parent 的 exception flow 或 IF decision。

## 7.3 全局禁止或门控

例如：

```text
Do not finalize if provenance fails.
```

这是 `ConstraintIR(kind=gate)`，同时应绑定到相关 flow/block/step。

也就是说：

```text
failure event → EXCEPTION_FLOW
failure response at handoff → handoff.failure_policy
failure-related rule → ConstraintIR
```

三者不要混在一个字段里。

---

# 8. 关于 WorkerPlanIR 应该是全局还是每个 Worker 一个 FlowStructureIR

我的建议：

## WorkerPlanIR 应该是全局的

WorkerPlanIR 描述的是 worker graph：

```text
workers
handoffs
ownership
contracts
dependencies
```

它不应该直接包含完整 FlowStructureIR。否则它会重新承担 FlowAssembler 的职责。

但 Stage 4 之后，应该产生：

```json
{
  "worker_flows": {
    "worker_main": "FlowStructureIR",
    "worker_source_gathering": "FlowStructureIR"
  }
}
```

也就是：

```text
WorkerPlanIR 是全局 worker 图；
FlowStructureIR 是每个 worker 内部的 flow。
```

这样边界清楚。

---

# 9. 我建议的目标 pipeline

结合你的设计，我建议最终 pipeline 改成：

```text
Stage 1: SpanSlicer
Stage 2: FieldRouter
Stage 3: AmbiguityResolver

Stage 3.5: WorkerBoundaryPlanner
    input: resolved spans + routes + compact source context + optional CanonicalCompileInput hard facts
    output: WorkerPlanIR

Stage 4: FlowAssembler
    input: WorkerPlanIR + spans + routes
    output: Dict[worker_id, FlowStructureIR]

Stage 5: BlockAssembler
    input: worker-specific FlowStructureIR
    output: Dict[worker_id, BlockStructureIR]

Stage 6: ResourceExtractor
    input: WorkerPlanIR + worker-specific flows/blocks
    output: ResourceRegistryIR + SymbolTable

Stage 7: StepExtractor
    input: WorkerPlanIR + handoffs + worker-specific flows/blocks + symbols
    output: worker-specific StepIR

Stage 8: ProfileExtractor
Stage 9: ConstraintExtractor
Stage 9.5: IRNormalizer
Stage 10: WorkerAssembler
Stage 11: SPLRenderer
```

这和你的 TODO 中“Phase 2 新增 Worker Boundary Planner、Phase 3 让 FlowAssembler 消费 WorkerPlanIR、Phase 4 让 StepExtractor 和 Normalizer worker-aware、Phase 5 让 WorkerAssembler 从 WorkerPlanIR 构造 child workers”的迁移路径一致。

---

# 10. 对你当前方案的修改建议

## 10.1 不要把 `delegation_candidates` 继续作为长期核心

短期可以保留兼容，但长期必须迁到 WorkerPlanIR。你现在的 TODO 已经写了 Phase 6：移除或废弃 `FlowStructureIR.delegation_candidates`，生产阶段不再读取它，Worker planning 只由 `WorkerPlanIR` 表示。

这个方向正确。

---

## 10.2 WorkerSpecIR 里不要保留 confidence

你的 TODO 里 `WorkerSpecIR` 有：

```text
confidence: optional confidence score
```

我建议删掉。理由和我们讨论 InputAdapter 时一样：这种 confidence 通常没有可靠校准，容易制造伪精确。

改成：

```json
{
  "decision_evidence": [
    "explicit_delegation",
    "bounded_input_output",
    "independent_failure_policy"
  ],
  "reason": "..."
}
```

或者：

```json
{
  "boundary_strength": "strong | moderate | weak",
  "reason": "..."
}
```

如果 `boundary_strength = weak`，默认不拆 worker。

---

## 10.3 增加 rejected_candidates

这很重要。

WorkerBoundaryPlanner 不应该只输出接受的 child workers，还应该输出被拒绝的候选：

```json
{
  "rejected_candidates": [
    {
      "candidate_id": "tu_revision",
      "text": "If the user asks for revision, revise while rechecking constraints.",
      "decision": "keep_as_alternative_flow",
      "reason": "Revision is an alternative flow inside the main worker, not a delegated task."
    }
  ]
}
```

这能显著提高可调试性，也能防止模型反复把 revision、exception、simple API call 误判为 worker。

---

## 10.4 增加 boundary_kind

建议给每个 child worker 标注边界来源：

```text
explicit_delegation
bounded_subtask
integration_wrapper
complex_control_extraction
loop_body_worker
evidence_or_provenance_protocol
template_or_format_protocol
```

这样后续 validator 可以针对不同类型做不同检查。

---

## 10.5 增加 invoke_location_hint

WorkerPlanIR 里有 handoff，但建议更明确地记录调用位置：

```json
{
  "handoff_id": "h1",
  "from_worker": "worker_main",
  "to_worker": "worker_source_gathering",
  "condition_text": "sources are needed and available",
  "invoke_location_hint": {
    "flow": "main",
    "after_span_id": "s10",
    "before_span_id": "s12"
  }
}
```

否则 StepExtractor 仍然可能不知道在哪里放 `INVOKE_WORKER`。

---

# 11. 对你的 internal-comms 示例怎么判定

以前面的输入为例：

## 应该是 child worker 的候选

### SourceGatheringWorker：强烈建议 child worker

理由：

```text
- 明确属于可委托 subtask；
- 有外部 source repositories/connectors；
- 有 approved source recipes；
- 有 source/evidence set 输出；
- 有 provenance log；
- 有 evidence shortage / source access failure / provenance failure；
- 有独立失败策略；
- 输出需要 normalized evidence carriers。
```

这是非常典型的 child worker。

### TemplateMatchingWorker：中等强度候选

如果只是：

```text
choose a format
```

可以留在 main worker。

如果是：

```text
match templates, normalize format guidance, enforce internal comms template rules
```

可以 child worker。

所以它是 `may_extract_child_worker`，不是必然。

---

## 不应该是 child worker 的内容

### Revision

```text
If the user asks for revision, revise while rechecking constraints.
```

这是 alternative flow，不是 child worker，除非输入明确说 revision should be delegated。

### Missing timeframe

这是 exception flow 或 clarification flow，不是 child worker。

### Deny finalization

这是 gate constraint + decision，不是 child worker。

### Ask clarifying questions

通常是 main worker 内部 `INPUT` step，不是 child worker。

---

# 12. 最终建议：多 Worker 边界的一句话标准

我建议你把多 Worker 判断标准写成：

> 当一组行为 span 构成一个具有独立责任、明确输入输出契约、明确 parent handoff、可独立完成或失败，并且拆分后能提升语义保真、复用性、测试性或解决 SPL 控制结构表达限制的任务单元时，应生成独立 Worker；否则应保留在当前 Worker 内，通过 Flow、Block、Step、Constraint 或 CALL_API 表达。

这个定义能同时覆盖你的两类识别方式：

```text
主动识别：
explicit delegation → 检查是否满足 worker 边界

被动发现：
unrepresentable nested control → 检查是否满足 worker 边界
```

但它不会被 “subtask 字样” 或 “嵌套 block” 单独绑架。

---

# 13. 可直接落地的判定表

| 语义现象                 | 默认编译目标                     | 什么时候升级为 child worker          |
| -------------------- | -------------------------- | ----------------------------- |
| 普通顺序步骤               | SEQUENTIAL_BLOCK + COMMAND | 几乎不升级                         |
| 简单 IF                | IF_BLOCK                   | 不升级                           |
| 简单 LOOP              | FOR/WHILE_BLOCK            | 不升级                           |
| Revision             | ALTERNATIVE_FLOW           | 只有明确 delegated revision 才升级   |
| Failure handling     | EXCEPTION_FLOW             | 失败恢复本身是复杂协议时升级                |
| 单次 API 调用            | CALL_API                   | 需要多步封装、归一化、重试、provenance 时升级  |
| Source gathering     | CALL_API 或 child worker    | 多源检索 + 证据归一化 + provenance 时升级 |
| Template matching    | COMMAND 或 child worker     | 有复杂匹配、格式约束、复用价值时升级            |
| FOR 内有 IF            | 尝试条件合并 / guard step        | per-item 逻辑复杂且有 IO 时升级        |
| IF 内有 LOOP           | 尝试条件提升                     | loop body 是独立协议时升级            |
| 多输出子流程               | 结构化变量                      | 多步、独立失败、可复用时升级                |
| 明确 delegated subtask | child worker candidate     | 通过 IO/handoff 检查后确认           |

---

# 14. 我对你当前设计的最终评价

你的设计目前已经到达一个关键转折点：**原来的 Flow → Block → Step 粒度已经不够了，必须在 Flow 之前引入 Worker 边界规划。**

你现在的主动识别和被动发现思路都对，但需要升维：

```text
不要问：这里有没有 subtask？
不要问：这里有没有嵌套 block？

要问：这里有没有一个可调用的责任单元？
```

如果有，再问：

```text
它的输入是什么？
它的输出是什么？
谁调用它？
何时调用它？
失败怎么办？
结果如何回填 parent worker？
```

只有这些问题都有答案时，才是真正的多 Worker。
