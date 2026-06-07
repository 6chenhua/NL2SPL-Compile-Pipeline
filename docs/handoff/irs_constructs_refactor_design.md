# IRS / Constructs 代码组织重构设计文档

**文档状态**: Draft for implementation review  
**适用仓库**: `NL2SPL-Compile-Pipeline`  
**范围**: `src/nl2spl/compiler/construct_registry.py`, `src/nl2spl/compiler/irs/`, `src/nl2spl/compiler/construct_plan/`, `src/nl2spl/compiler/diagnostic_registry.py`, `src/nl2spl/compiler/irs_prompt_builder.py`, `src/nl2spl/compiler/report_renderer.py`  
**目标版本**: IRS / Constructs package-architecture refactor  
**核心原则**: 行为冻结、分层清晰、依赖单向、兼容迁移、可回滚

---

## 1. 背景与问题定义

当前 IRS 顶层设计本身是正确的：

```text
ConstructPlan       → source-demand planning
ConstructIRS        → static construct information requirements
IRS runtime         → runtime checking / satisfaction / diagnostic projection
ReportRenderer      → deterministic human-readable feedback
```

但当前代码组织没有完整反映这个设计。现有实现把以下不同层次的概念混在一起：

1. SPL 构件静态领域模型；
2. 构件 satisfaction 运行结果；
3. 构件图与 recursive checking 边界类型；
4. IRS checker runtime；
5. Diagnostic registry；
6. Prompt checklist renderer；
7. Human-readable feedback renderer。

最明显的架构坏味道是：

```text
compiler/construct_registry.py
  imports compiler.irs.frontier
  imports compiler.irs.graph
```

这说明 compiler-level construct domain model 反向依赖了 IRS runtime package。该依赖方向与目标架构相反。

同时，`construct_plan/model.py` 与 `construct_plan/planner.py` 也直接消费 `irs.graph.ConstructEdge`。这进一步说明 `ConstructEdge` 已经不是 IRS runtime 私有类型，而是跨 `construct_registry`、`construct_plan`、`irs` 多层共享的基础领域类型。

---

## 2. 设计目标

本次重构的目标不是改变 IRS 语义，也不是新增 construct 检查能力，而是重建 package boundary。

### 2.1 主要目标

1. 建立 `compiler.constructs` 作为 SPL construct domain layer。
2. 建立 `compiler.diagnostics` 作为 compiler-wide diagnostic domain layer。
3. 收缩 `compiler.irs`，使其只承载 runtime checking / projection / result storage / subsystem orchestration。
4. 保持 `compiler.construct_plan` 独立，作为 source-demand planning layer。
5. 建立 `compiler.reporting`，承载 deterministic report / feedback rendering。
6. 消除 `constructs -> irs` 反向依赖。
7. 通过 compatibility shims 支持渐进迁移，避免一次性破坏 16+ 源文件与 20+ 测试文件的 import path。
8. 在重构阶段保持 compile 行为、diagnostic 行为、report 内容稳定。

### 2.2 非目标

本次重构不做以下事项：

1. 不修改 IRS slot satisfaction 语义。
2. 不新增 REQUIRED_OUTPUT / REQUEST_INPUT / CALL_API / INVOKE_WORKER 的新检查规则。
3. 不改变 `PipelineResult` / `CompileResult` public schema。
4. 不移除 legacy import path，第一轮只添加 shim。
5. 不重写 Stage 4 / Stage 7 / Stage 9.5 行为。
6. 不引入新的 LLM 调用。
7. 不把 semantic conflict、dataflow、worker graph validation 规则代码化。
8. 不将 reporting 层与 IRS runtime 混合。

---

## 3. 当前依赖事实

### 3.1 `construct_registry.py` 的实际导入

```text
construct_registry.py
  ← irs.frontier  (CutlineReason, FrontierStatus)
  ← irs.graph     (ConstructEdge)
```

### 3.2 `irs/graph.py` 的跨层消费者

`ConstructEdge` / `ConstructGraph` 当前不只是 IRS 内部使用，还被 `construct_registry.py`、`construct_plan/model.py`、`construct_plan/planner.py` 等 compiler-level 模块消费。

因此 `irs/graph.py` 的位置错误。它应被视为 construct domain graph schema，而不是 runtime checker 实现。

### 3.3 `diagnostic_registry.py` 的当前消费者

当前主要消费者是：

```text
compiler/__init__.py
irs/projector.py
```

虽然目前消费者较少，但 `DiagnosticRegistry` 的 kind 范围已经是 compiler-wide，而非 construct-only。例如：

```text
missing_handler
missing_output_producer
type_or_contract_ambiguity
assumed_command_not_renderable
unmapped_behavior_span
missing_provenance
semantic_conflict
```

其中 `semantic_conflict`、`missing_provenance`、`unmapped_behavior_span` 不属于单个 construct spec，因此 diagnostic registry 不应放入 `constructs/`。

---

## 4. 目标架构

### 4.1 目标 package layout

```text
src/nl2spl/compiler/
  constructs/
    __init__.py
    spec.py
    satisfaction.py
    graph.py
    registry.py
    defaults.py
    prompt_builder.py
    definitions/
      __init__.py
      exception_flow.py
      required_output.py
      command.py
      worker.py
      api.py
      policy.py

  diagnostics/
    __init__.py
    spec.py
    registry.py
    defaults.py
    kinds.py

  construct_plan/
    __init__.py
    model.py
    planner.py
    extractors/
      __init__.py
      exception_flow.py
      required_output.py
      request_input.py
      call_api.py
      worker_handoff.py

  irs/
    __init__.py
    config.py
    context.py
    instance.py
    checker.py
    checker_registry.py
    runner.py
    projector.py
    result_store.py
    subsystem.py
    factory.py
    traversal.py
    graph_snapshot.py
    checkers/
      __init__.py
      exception_flow.py
      worker_delegation.py
      post_normalize/
        __init__.py
        checker.py
        exception_flow.py
        required_output.py
        general_command.py
        request_input.py
        call_api.py
        invoke_worker.py
      steps/
        __init__.py
        checker.py
        general_command.py
        request_input.py
        call_api.py
        invoke_worker.py

  reporting/
    __init__.py
    report_renderer.py
    construct_satisfaction_renderer.py
```

---

## 5. 分层职责定义

### 5.1 `compiler.constructs`

`constructs` 是 SPL construct domain layer。

它负责：

1. 静态 construct spec；
2. slot spec；
3. satisfaction report 数据结构；
4. construct graph schema；
5. construct registry；
6. default construct definitions；
7. construct spec 到 prompt checklist 的纯渲染。

它不负责：

1. IRS runtime checking；
2. Stage orchestration；
3. diagnostic projection；
4. report rendering；
5. LLM 调用；
6. pipeline-specific stage policy。

推荐文件职责：

| 文件 | 职责 |
|---|---|
| `spec.py` | `SlotSpec`, `ConstructIRS`, `ExistencePolicy`, `NoDemandBehavior` |
| `satisfaction.py` | `SlotSatisfaction`, `ConstructSatisfactionReport`, `FrontierStatus`, `CutlineReason`, `ConstructCompleteness` |
| `graph.py` | `ConstructEdge`, `ConstructGraph`, `ConstructEdgeType`, graph serialization/dedup helpers |
| `registry.py` | `SPLConstructRegistry` |
| `defaults.py` | `build_default_construct_registry()` |
| `definitions/*` | 各 construct 的 IRS definitions |
| `prompt_builder.py` | `ConstructPromptBuilder`, construct checklist rendering |

### 5.2 `compiler.diagnostics`

`diagnostics` 是 compiler-wide diagnostic domain layer。

它负责：

1. `DiagnosticSpec`；
2. `DiagnosticRegistry`；
3. default diagnostic kinds；
4. enabled/reserved kind 管理；
5. diagnostic kind 常量。

它不负责：

1. 生成 `CompileDiagnostic`；
2. 读取 IRS context；
3. 投影 satisfaction report；
4. report rendering；
5. pipeline orchestration。

推荐文件职责：

| 文件 | 职责 |
|---|---|
| `spec.py` | `DiagnosticSpec`, `Severity` |
| `registry.py` | `DiagnosticRegistry` |
| `defaults.py` | `build_default_diagnostic_registry()` |
| `kinds.py` | diagnostic kind constants, if needed |

### 5.3 `compiler.construct_plan`

`construct_plan` 是 source-demand planning layer。

它负责：

1. 从 route annotation / semantic role / evidence 中识别 construct demand；
2. 记录 slot-level evidence；
3. 记录 reserved spans / dual-role spans；
4. 对 EXCEPTION_FLOW 等 source-demand 做 ownership enforcement；
5. 输出 downstream stages 与 IRS 可消费的 `ConstructPlan`。

它不负责：

1. 定义 ConstructIRS；
2. 执行 IRS checking；
3. 生成 SPL IR；
4. 生成 `ConstructSatisfactionReport`；
5. 生成 final compile diagnostics。

### 5.4 `compiler.irs`

`irs` 是 runtime checking layer。

它负责：

1. `IRSCheckContext`；
2. `ConstructInstance`；
3. `IRSChecker` protocol；
4. checker registry；
5. runner；
6. diagnostic projector；
7. result store；
8. subsystem facade；
9. runtime graph traversal / graph snapshot；
10. concrete checkers。

它不负责：

1. 定义 SPL construct static spec；
2. 定义 diagnostic registry；
3. 渲染人类可读 report；
4. 维护 pipeline-specific prompt policy。

### 5.5 `compiler.reporting`

`reporting` 是 presentation layer。

它负责：

1. deterministic compile report rendering；
2. construct satisfaction feedback rendering；
3. diagnostic / assumption / trace 的人类可读文本组织。

它不负责：

1. IRS checking；
2. diagnostic projection；
3. construct slot 判断；
4. 修改 IR / SPL。

---

## 6. 关键设计决策

### 6.1 `DiagnosticRegistry` 不归入 `constructs`

虽然 `DiagnosticRegistry` 和 `SPLConstructRegistry` 都是 registry，但二者不是父子关系。

`SPLConstructRegistry` 属于 construct domain。  
`DiagnosticRegistry` 属于 compiler-wide diagnostic domain。

因此目标是：

```text
compiler.constructs      # construct domain
compiler.diagnostics     # diagnostic domain
```

而不是：

```text
compiler.constructs.diagnostic_registry
```

这样可以避免未来 `semantic_conflict`、`missing_provenance`、`use_before_def`、`worker_graph_inconsistency` 等 cross-cutting diagnostics 被错误绑定到 construct domain。

### 6.2 `feedback_projector.py` 不归入 `constructs`

`feedback_projector.py` 当前只依赖 `ConstructSatisfactionReport`，但它的职责是文本渲染。依赖某个领域对象不代表属于该领域层。

因此它应进入：

```text
compiler.reporting.construct_satisfaction_renderer
```

而不是：

```text
compiler.constructs.feedback_projector
```

### 6.3 `irs_prompt_builder.py` 应拆分

当前 `irs_prompt_builder.py` 同时包含：

1. construct spec checklist rendering；
2. stage-specific construct mapping；
3. stage-specific critical rules。

应拆分为：

```text
constructs/prompt_builder.py
  只负责 construct checklist rendering

pipeline/stage_prompt_profiles.py
  负责 stage → constructs mapping 与 stage-specific notes
```

这样 `constructs` 不需要知道 pipeline stage names。

### 6.4 `graph.py` 类型移入 `constructs`，算法留在 `irs`

`ConstructEdge` / `ConstructGraph` 是 construct domain graph schema。它们可以包含轻量 serialization / dedup helper。

但 recursive checking traversal、frontier expansion、cutline decision、runtime graph snapshot building 应留在 `irs/`。

---

## 7. 依赖规则

### 7.1 允许的依赖

```text
construct_plan -> constructs
irs            -> constructs + diagnostics
reporting      -> constructs + diagnostics + compile_result / ir diagnostics
pipeline       -> construct_plan + irs + reporting + constructs
```

### 7.2 禁止的依赖

```text
constructs -> irs
constructs -> pipeline
constructs -> reporting
constructs -> construct_plan

diagnostics -> irs
diagnostics -> pipeline
diagnostics -> reporting

irs -> reporting
irs -> pipeline
```

### 7.3 兼容 shim 例外

迁移期允许保留以下 shim：

```text
compiler/construct_registry.py
compiler/diagnostic_registry.py
compiler/irs/graph.py
compiler/irs/frontier.py
compiler/irs_prompt_builder.py
compiler/report_renderer.py
```

但 shim 只能 re-export，不得承载新逻辑。

---

## 8. Public API 兼容策略

### 8.1 保留旧路径

第一轮重构后，旧 import path 必须继续可用：

```python
from nl2spl.compiler.construct_registry import ConstructIRS
from nl2spl.compiler.diagnostic_registry import DiagnosticRegistry
from nl2spl.compiler.irs.graph import ConstructEdge
from nl2spl.compiler.irs.frontier import FrontierStatus
from nl2spl.compiler.irs_prompt_builder import irs_checklist_for_stage
from nl2spl.compiler.report_renderer import render_report
```

这些路径在迁移期通过 shim 实现。

### 8.2 新路径

新代码应使用：

```python
from nl2spl.compiler.constructs import ConstructIRS, SPLConstructRegistry
from nl2spl.compiler.constructs.graph import ConstructEdge, ConstructGraph
from nl2spl.compiler.constructs.satisfaction import ConstructSatisfactionReport
from nl2spl.compiler.diagnostics import DiagnosticRegistry
from nl2spl.compiler.reporting.report_renderer import render_report
```

### 8.3 shim 退出策略

shim 不在本轮删除。建议在至少一个 minor version 或一个重构周期后再逐步移除。

---

## 9. 验收原则

本次重构完成后必须满足：

1. `constructs/*` 不 import `irs/*`。
2. `diagnostics/*` 不 import `irs/*`。
3. `construct_plan/*` 不 import `irs.graph`。
4. `reporting/*` 不 import `irs.feedback_projector`。
5. `irs/*` 不包含 human-readable report renderer。
6. `construct_registry.py` 只作为 shim 存在。
7. `diagnostic_registry.py` 只作为 shim 存在。
8. `irs/graph.py` 与 `irs/frontier.py` 只作为 shim 存在。
9. 全量测试行为不变。
10. report snapshot / diagnostic snapshot 不发生非预期变化。

---

## 10. 最终设计结论

本次重构的核心不是简单移动文件，而是建立清晰的 compiler package architecture：

```text
constructs      = SPL construct domain model
diagnostics     = compiler diagnostic domain model
construct_plan  = source-demand planning
irs             = runtime checking / projection
reporting       = human-readable rendering
pipeline        = orchestration
```

重构完成后，IRS 目录将从“所有与 IRS 相关的东西”收缩为真正的 runtime checking framework。SPL construct spec、diagnostic registry、construct graph schema、prompt checklist renderer、report renderer 都将回到各自更准确的层次。
