# IRS v6 重构设计文档

## 1. 文档定位

本文档描述如何将当前 IRS 相关代码从 v5/v5.5 风格迁移到 IRS v6 目标架构。

本文档回答：

```text
当前代码为什么需要重构？
目标架构是什么？
哪些设计模式被采用？
各组件的职责边界是什么？
哪些事情本轮明确不做？
如何保证兼容现有 pipeline 行为？
```

本文档不是任务清单。具体执行步骤见 `07_irs_v6_refactor_tasks.md`。

## 2. 当前代码状态

当前项目已经具备 IRS v5 基础：

```text
ConstructIRS
SlotSpec
SlotSatisfaction
ConstructSatisfactionReport
SPLConstructRegistry
DiagnosticRegistry
Stage 4 EXCEPTION_FLOW IRS checker
Stage 7 Step IRS checker
Post-normalize IRS checker
ExecutableElementGate
ProducerIndex
```

这些基础说明当前代码已经部分符合以下架构方向：

```text
Specification Pattern
Registry Pattern
Multi-pass compiler analysis
Static analysis / lint pass
```

但当前实现还没有达到 IRS v6 的目标风格。主要问题是：

```text
1. checker 接入仍然是手写函数式接入。
2. orchestrator 直接感知具体 checker。
3. 新增 IRS checker 需要同时改 checker、orchestrator、diagnostic merge、report、测试。
4. checker 直接创建 CompileDiagnostic，diagnostic 投影逻辑分散。
5. 没有统一 ConstructInstance 层。
6. ConstructSatisfactionReport 仍是 flat report，缺少 parent/path/edge/frontier/cutline 信息。
7. Worker candidate 与 promotion readiness 语义尚未系统分离。
8. 当前代码还没有为未来递归 IRS 检查准备 graph-ready 数据结构。
```

因此，本轮重构的目标不是新增更多 ad-hoc IRS 规则，而是补齐 IRS checker 的工程接入层。

## 3. 目标架构

IRS v6 的目标架构为：

```text
ConstructIRS = construct 信息需求规格层
ConstructInstance = stage IR 到可检查 construct 实例的标准化层
IRSChecker = construct-specific 检查策略
IRSCheckerRegistry = checker 注册与查找层
IRSRunner = stage-local checker 调度层
ConstructSatisfactionReport = slot satisfaction + parent/path/edge/frontier/cutline 报告层
DiagnosticProjector = report/slot -> CompileDiagnostic 的统一投影层
ConstructEdge / ConstructGraph = 未来递归 IRS 检查的数据基础
```

目标调用链：

```text
stage IR
-> IRSCheckContext
-> IRSRunner.run_stage(stage_name, context)
-> IRSCheckerRegistry 查找 checker
-> IRSChecker.extract_instances()
-> IRSChecker.check_instance()
-> ConstructSatisfactionReport
-> DiagnosticProjector.project()
-> CompileDiagnostic
-> intermediate_results["construct_satisfaction"][stage]
-> intermediate_results["stage_local_diagnostics"][stage]
```

orchestrator 的目标职责是调用 `IRSRunner`，不再直接知道具体 checker 函数。

## 4. 采用的设计模式

| 模式 / 原则 | 在 IRS v6 中的落点 |
| --- | --- |
| Specification Pattern | `ConstructIRS` / `SlotSpec` 定义 SPL construct 的信息需求 |
| Strategy Pattern | 每个 `IRSChecker` 是一个可替换的 construct 检查策略 |
| Registry / Plugin Architecture | `IRSCheckerRegistry` 注册 checker，避免 orchestrator 感知具体 checker |
| Multi-pass Compiler Static Analysis | Stage-local IRS、Post-normalize IRS、Gate、ProducerIndex 分层裁决 |
| Diagnostic Projection | `DiagnosticProjector` 统一 message/severity/blocking/dedup 语义 |
| Graph-ready Traversal Preparation | `ConstructEdge` / `ConstructGraph` 为未来递归检查预留 DAG 表达 |
| Frontier / Cutline | partial construct 显式停止下钻，避免为无 source evidence 的 child 生成噪声诊断 |
| State / Workflow Gate | `WORKER_CANDIDATE -> WORKER_PROMOTION -> CHILD_WORKER` 表达候选与晋升条件 |

这些模式不是为了形式化命名，而是为了解决具体工程问题：

```text
新增 IRS checker 必须变成局部工程动作。
diagnostic 语义必须集中。
orchestrator 不应该随着 checker 增加而持续膨胀。
future recursive IRS checker 需要稳定 instance/edge/frontier 数据。
```

## 5. 当前状态与目标状态对比

| 方面 | 当前状态 | 目标状态 |
| --- | --- | --- |
| IRS rule definition | 已有 `ConstructIRS` / `SlotSpec` | 保持，并按需要扩展 construct specs |
| Satisfaction report | v5 flat report | 增加 parent/path/edge/frontier/cutline/source metadata |
| Checker 接入 | Stage 4 / Stage 7 / Post-normalize 手写函数接入 | `IRSChecker` + `IRSRunner` + registry |
| Diagnostic 生成 | checker 直接创建 `CompileDiagnostic` | checker 输出 report，`DiagnosticProjector` 统一投影 |
| Orchestrator | 感知具体 checker | 只调用 runner |
| Worker delegation IRS | candidate、child worker、handoff、promotion 原因分散表达 | `WORKER_CANDIDATE` 与 `WORKER_PROMOTION` 分离 |
| 递归检查 | 不支持 | 本轮只预留 ConstructGraph / Edge / Frontier 接口 |
| Renderer | 只渲染已裁决 IR | 保持不变 |

## 6. Authority Boundary

IRS v6 重构必须保持裁决边界清楚。

| 组件 | 负责 | 不负责 |
| --- | --- | --- |
| Stage-local IRS | 早期 construct slot satisfaction report | 不做最终 renderability 裁决 |
| Post-normalize IRS | normalized construct-level diagnostics 的最终权威 | 不替代 Gate / ProducerIndex |
| DiagnosticProjector | 从 report 投影 diagnostic message/severity/blocking | 不重新解释 construct slot |
| ExecutableElementGate | step/command 是否能进入可渲染 SPL | 不判断 required output producer |
| ProducerIndex | required output 是否有合法 producer | 不判断 step 是否可渲染 |
| Renderer | SPL 文本渲染 | 不补 handler、producer、contract |
| Future RecursiveIRSEvaluator | 未来 graph traversal | 不替代 Gate / ProducerIndex / post-normalize authority |

如果同一问题可能被多个层发现，应明确最终权威：

```text
construct-level incompleteness -> Post-normalize IRS
step renderability -> ExecutableElementGate
required output producer -> ProducerIndex / Post-normalize IRS
worker promotion readiness -> Worker/Delegation IRS
diagnostic merge/dedup -> DiagnosticConsolidator
```

## 7. 新增模块设计

目标目录：

```text
src/nl2spl/compiler/irs/
  __init__.py
  context.py
  instance.py
  graph.py
  checker.py
  registry.py
  runner.py
  projector.py
  frontier.py
  checkers/
    __init__.py
    worker_delegation.py
```

类型归属必须固定，避免实现时分散：

```text
ConstructEdge / ConstructGraph:
    定义在 src/nl2spl/compiler/irs/graph.py

FrontierStatus / CutlineReason:
    定义在 src/nl2spl/compiler/irs/frontier.py

ConstructSatisfactionReport:
    兼容期仍保留在 src/nl2spl/compiler/construct_registry.py。
    如需引用 graph/frontier 类型，应从 compiler/irs 子包 import。

未来可选迁移:
    如果 IRS v6 代码稳定，可再考虑把 report 类型迁移到 compiler/irs/report.py。
    本轮不做该迁移，避免扩大改动面。
```

### 7.1 context.py

定义 `IRSCheckContext`。

职责：

```text
统一携带 stage_name、spans、routes、flow IR、step IR、worker_plan、
resources、symbol_table、construct_findings、feature flags 等上下文。
```

要求：

```text
1. context 是只读输入容器。
2. checker 不应通过 context 修改 IR。
3. context 允许部分字段为空，以支持不同 stage。
```

### 7.2 instance.py

定义 `ConstructInstance`。

最低字段：

```python
construct_id: str
construct_type: str
ir_ref: object | None
materialized: bool
source_demanded: bool
candidate_only: bool
primary_parent_id: str | None
construct_path: tuple[str, ...]
source_span_ids: list[str]
source_section_id: str | None
source_packet_id: str | None
metadata: dict
```

状态语义：

```text
No demand:
    不创建 ConstructInstance

WORKER_CANDIDATE:
    materialized=False
    source_demanded=True
    candidate_only=True

WORKER_PROMOTION:
    materialized=False
    source_demanded=True
    candidate_only=True

CHILD_WORKER:
    materialized=True
    source_demanded=True
    candidate_only=False
```

### 7.3 graph.py

定义 `ConstructEdge` 和可选 `ConstructGraph`。

`ConstructEdge` 用于表达 DAG / cross-reference，而不是强行塞进 parent/child tree。

建议 edge types：

```text
contains
produces
consumes
invokes
handoff_to
handles
applies_to
derived_from
promotes_to
blocked_by
```

本轮只生产和存储 edge，不实现全局递归 traversal。

### 7.4 checker.py

定义 `IRSChecker` Protocol。

建议接口：

```python
class IRSChecker(Protocol):
    checker_id: str
    supported_construct_types: tuple[str, ...]
    supported_stages: tuple[str, ...]

    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        ...

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        ...
```

checker 禁止事项：

```text
1. 不调用 LLM。
2. 不修改 IR。
3. 不生成新 SPL construct。
4. 不补全缺失 slot。
5. 不直接拼装完整 CompileDiagnostic。
6. 不为没有 source demand 的 child construct 制造 report。
```

### 7.5 registry.py

定义 `IRSCheckerRegistry`。

职责：

```text
1. 注册 checker。
2. 按 stage_name / construct_type 查找 checker。
3. 支持默认 registry。
4. 支持测试中注入 checker。
```

### 7.6 runner.py

定义 `IRSRunner`。

职责：

```text
1. 接收 stage_name + context。
2. 找到该 stage 的 checker。
3. 调用 extract_instances。
4. 根据 instance.construct_type 获取 ConstructIRS。
5. 调用 check_instance。
6. 调用 DiagnosticProjector。
7. 返回 reports + diagnostics。
```

runner 只负责调度，不解释 slot 语义。

### 7.7 projector.py

定义 `DiagnosticProjector`。

职责：

```text
1. 从 SlotSatisfaction / ConstructSatisfactionReport 读取 diagnostic_kind。
2. 查 DiagnosticRegistry。
3. 统一生成 CompileDiagnostic。
4. 统一 target_ref、severity、blocks_completion、blocks_rendering、dedup key。
```

checker 可以在 slot/report 中写：

```text
diagnostic_kind
explanation
source_span_ids
target metadata
```

但不直接拼装最终 diagnostic message。

### 7.8 frontier.py

定义 frontier / cutline 相关类型。

建议：

```text
frontier_status:
  continue
  leaf
  cutline_partial
  cutline_blocked

cutline_reason:
  missing_required_for_complete
  no_source_demand
  promotion_blocked
  non_renderable_candidate
  blocked_by_gate
```

本轮不实现 recursive evaluator，但所有 report 应能表达是否允许未来 traversal 继续下钻。

## 8. ConstructSatisfactionReport 扩展

当前 `ConstructSatisfactionReport` 需要兼容扩展。

新增字段必须有默认值：

```python
primary_parent_id: str | None = None
child_construct_ids: list[str] = field(default_factory=list)
related_edges: list[ConstructEdge] = field(default_factory=list)
construct_path: tuple[str, ...] = ()
source_span_ids: list[str] = field(default_factory=list)
source_section_id: str | None = None
source_packet_id: str | None = None
cutline_reason: str | None = None
frontier_status: str = "leaf"
metadata: dict[str, Any] = field(default_factory=dict)
```

兼容要求：

```text
1. 旧 checker 不传这些字段时行为不变。
2. 旧 tests 不需要大规模修改。
3. report renderer 可以暂时忽略新字段。
4. 新 v6 checker 必须填充 source/path/frontier 信息。
```

## 9. Worker / Delegation IRS 作为首个实践点

首个 v6-style checker 应选择 Worker/Delegation，而不是先迁移 Stage 4 / Stage 7。

原因：

```text
1. Stage 4 / Stage 7 已经可用，先迁移风险高、收益低。
2. Worker/Delegation 正好暴露当前扩展痛点。
3. internal-comms-3 的 Issue 3 需要解释“为什么没有晋升 child worker”。
4. Worker candidate / promotion readiness 非常适合验证 ConstructInstance、frontier、DiagnosticProjector。
```

必须区分：

```text
WORKER_CANDIDATE:
    表示 source 中存在一个可能的 delegation / subtask demand。
    candidate 本身可以 complete。
    candidate complete 不等于可以生成 child worker。

WORKER_PROMOTION:
    表示该 candidate 是否具备晋升为 CHILD_WORKER + WORKER_HANDOFF + INVOKE_WORKER 的条件。
    缺 input/output/invocation/result handoff 时，应 promotion blocked。
```

报告语义：

```text
candidate_satisfaction = complete / partial / blocked
promotion_status = ready / blocked / not_applicable
promotion_missing_slots = [...]
frontier_status = cutline_partial when promotion blocked
```

这可以解决当前报告中“系统只是没生成 child worker，但没有解释原因”的问题。

## 10. 兼容策略

重构必须是兼容式迁移。

原则：

```text
1. 不一次性重写现有 IRS checker。
2. 不改变现有 Stage 4 / Stage 7 / Post-normalize 默认行为。
3. 不改变 renderer。
4. 新字段全部有默认值。
5. 新 runner 先通过 feature flag 接入。
6. 旧 checker 和新 runner 可以短期并存。
7. Worker/Delegation v6 checker 先只增加 report/diagnostics，不放宽 child worker materialization。
```

建议 feature flags：

```python
enable_irs_v6_runner: bool = False
enable_irs_worker_delegation_check: bool = False
enable_irs_stage4_v6_checker: bool = False
enable_irs_stage7_v6_checker: bool = False
```

`DiagnosticProjector` 不建议作为独立可关闭路径。

```text
enable_irs_v6_runner = False:
    v6 runner 与 projector 都不运行。

enable_irs_v6_runner = True:
    runner 内部必须使用 DiagnosticProjector。

原因:
    新 checker 输出 report/slot，不直接生成 CompileDiagnostic。
    如果 runner 开启但 projector 关闭，会出现 report 存在但 diagnostics/report 不可见的半接入状态。
```

## 11. 非目标

本轮明确不做：

```text
1. 不实现通用递归 IRS evaluator。
2. 不一次性补齐所有 SPL construct IRS。
3. 不放宽 child worker materialization 条件。
4. 不让 checker 调用 LLM。
5. 不让 checker 修改 IR。
6. 不让 checker 生成新 construct。
7. 不改变 renderer。
8. 不替代 ExecutableElementGate。
9. 不替代 ProducerIndex。
10. 不一次性删除旧 Stage 4 / Stage 7 / Post-normalize checker。
```

## 12. 风险与缓解

| 风险 | 表现 | 缓解 |
| --- | --- | --- |
| 重构范围膨胀 | 试图一次性迁移 Stage 4/7/Post-normalize | 先做 schema + framework + Worker/Delegation |
| diagnostic 重复 | old checker 和 new checker 同时报同一问题 | 使用 projector + dedup key；feature flag 控制并存期 |
| authority 混乱 | checker、Gate、ProducerIndex 重复裁决 | 固定 authority boundary |
| graph 过早复杂化 | 试图实现全局递归 evaluator | 本轮只定义 edge，不 traversal |
| report 不可读 | 技术字段过多 | report renderer 分 summary 与 technical detail |
| checker 越界 | checker 根据缺失信息补 construct | checker contract 明确禁止生成 construct |

## 13. 成功标准

本轮重构成功的标准不是“所有 IRS 都迁移完成”，而是：

```text
1. 新增一个 IRS checker 不再要求改 orchestrator 主流程。
2. Worker/Delegation IRS 能通过 v6 runner 接入。
3. Worker candidate 与 promotion blocked 原因能结构化报告。
4. Diagnostic 由 projector 统一生成。
5. ConstructSatisfactionReport 具备 future recursive checker 所需字段。
6. 现有 Stage 4 / Stage 7 / Post-normalize 行为保持兼容。
7. full test suite 通过。
```
