# IRS Compiler Subsystem 产品化设计方案

## 1. 背景与目标

当前 IRS v6 已经具备核心基础设施：

- `ConstructIRS` / `SlotSpec` 声明 construct 的 information requirements。
- `ConstructInstance` 标准化 IR 中可检查的 construct 实例。
- `IRSChecker` 作为可插拔检查策略。
- `IRSRunner` 负责 stage-local 调度。
- `DiagnosticProjector` 负责把 report / slot 投影为 `CompileDiagnostic`。
- `ConstructGraph` / `ConstructEdge` 为未来递归检查保留 DAG 接口。
- `PostNormalizeIRSChecker` 已在生产 pipeline 中运行，承担当前 construct-level diagnostics 的主要职责。

但从产品化角度看，当前 IRS 还不是一个完整 compiler subsystem：

1. Stage-local IRS checker 存在，但生产路径未稳定触发。
2. `construct_satisfaction` 与 `compile_diagnostics` 的关系不够清晰。
3. Feedback report 目前主要消费 diagnostics，不能系统展示 construct satisfaction。
4. Stage-local IRS、Post-normalize IRS、Gate、ProducerIndex 的 authority boundary 需要固化到 runtime contract。
5. 后续新增 IRS checker 时仍可能修改 orchestrator、report、diagnostic merge，扩展成本没有完全收敛。

本方案目标是把 IRS 从“若干 checker / wrapper”产品化为一个稳定的 compiler subsystem：

```text
IRSSubsystem =
  spec registry
  + checker registry
  + stage-local runtime
  + post-normalize authority
  + diagnostic consolidation
  + construct satisfaction report store
  + feedback projection
  + future recursive frontier interface
```

## 2. 产品化原则

### 2.1 IRS 只做 construct-level information requirement analysis

IRS 检查的问题是：

> 对于一个已经 source-demanded 或 materialized 的 SPL construct，它所需的信息 slot 是否满足，缺失时缺什么，是否允许 partial，应该在哪里停止继续检查。

IRS 不负责：

- 解析 raw NL。
- 调用 LLM。
- 修改输入 IR。
- 生成新 SPL construct。
- 补全缺失 slot。
- 判断 step 是否最终可渲染。
- 替代 ProducerIndex 判断 output producer。
- 替代 renderer。

### 2.2 Stage-local IRS 与 Post-normalize IRS 分层

Stage-local IRS 是 early satisfaction analysis：

- 运行在 stage 产出 construct-shaped IR 之后。
- 生成 `ConstructSatisfactionReport`。
- 可生成 early diagnostics，但默认不作为最终 construct-level authority。
- 可用于 feedback、debug、prompt/provenance 解释、worker promotion blocked 说明。

Post-normalize IRS 是 final construct-level authority：

- 运行在 Stage 10 assembled `WorkerIR` 之后、Gate 之前。
- 消费 normalized / assembled IR。
- 产生最终 construct-level compile diagnostics。
- 对最终用户报告中的 requirement gaps 负责。

Gate 是 executable renderability authority：

- 只决定 executable element 是否能进入 SPL rendering。
- 不解释 construct-level requirement satisfaction。

ProducerIndex 是 required output producer authority：

- 判断变量/输出是否有 renderable producer。
- 不替代 construct IRS 的 slot satisfaction report。

### 2.3 Checker 必须消费 spec，而不是复制 spec

Checker 可以实现 construct-specific structural predicate，例如：

- `worker.input_contract` 是否非空。
- `handoff.output_bindings` 是否非空。
- `step.integration_ref` 是否存在。

Checker 不能硬编码 slot contract：

- `required_for_partial`
- `required_for_complete`
- `renderable_without`
- `missing_diagnostic`

这些必须来自 `ConstructIRS` / `SlotSpec`。否则 registry 会退化为文档字段。

### 2.4 Diagnostics 集中投影

Checker 输出 `ConstructSatisfactionReport` 和 `SlotSatisfaction`。

`CompileDiagnostic` 必须由统一 projector / consolidator 产生：

```text
checker -> report -> DiagnosticProjector -> CompileDiagnostic
```

这样才能统一：

- severity
- blocks_completion
- blocks_rendering
- missing_slot
- target_ref
- diagnostic_id
- dedup key
- readable report 表达

### 2.5 Feedback report 不触发 IRS

Feedback report 只消费 compiler subsystem 的产物：

- `CompileDiagnostic`
- `ConstructSatisfactionReport`
- `ConstructGraph` snapshot
- `TraceRecord`
- assumptions
- rendered SPL

它不能重新做 IRS 判断，也不能自行推断 missing slot。

## 3. 当前状态与目标状态

### 3.1 当前状态

当前生产路径中实际触发：

```text
Stage 10 Worker Assembly
-> PostNormalizeIRSChecker
-> ExecutableElementGate
-> Renderer
-> compile / feedback report
```

当前未稳定触发：

```text
Stage 3.5 Worker/Delegation IRS v6 runner
Stage 4 ExceptionFlow IRS runner
Stage 7 Step IRS runner
```

当前 feedback report 中的“检查结果”主要来自 `compile_diagnostics`，其中包括：

- Stage 2 route diagnostics。
- Stage 7 local diagnostics。
- Post-normalize IRS diagnostics。
- Gate diagnostics。
- Provenance diagnostics。
- Delegation diagnostics。
- Semantic conflict diagnostics。

它不是从 `construct_satisfaction` 系统展示 IRS report。

### 3.2 目标状态

目标生产路径：

```text
Stage 3.5 WorkerBoundaryPlanner
-> IRSSubsystem.run_stage_local("stage3_5")
-> reports stored in construct_satisfaction["stage3_5"]
-> early diagnostics stored in stage_local_diagnostics["stage3_5"]

Stage 4 FlowAssembler
-> IRSSubsystem.run_stage_local("stage4")
-> reports stored in construct_satisfaction["stage4"]
-> early diagnostics stored in stage_local_diagnostics["stage4"]

Stage 7 StepExtractor
-> IRSSubsystem.run_stage_local("stage7")
-> reports stored in construct_satisfaction["stage7"]
-> early diagnostics stored in stage_local_diagnostics["stage7"]

Stage 10 Worker Assembly
-> IRSSubsystem.run_post_normalize()
-> final construct diagnostics

ExecutableElementGate
-> renderability diagnostics

DiagnosticConsolidator
-> final compile_diagnostics

FeedbackReportRenderer
-> diagnostics + construct satisfaction + provenance
```

## 4. Subsystem 组件设计

### 4.1 `IRSSubsystem`

建议新增模块：

```text
src/nl2spl/compiler/irs/subsystem.py
```

职责：

- 作为 orchestrator 调用 IRS 的唯一入口。
- 屏蔽 checker registry / runner / projector 的组装细节。
- 负责 stage-local 与 post-normalize 两类 IRS 调用。
- 负责把结果写入统一 result store。
- 不调用 LLM。
- 不修改业务 IR。

建议接口：

```python
class IRSSubsystem:
    def __init__(
        self,
        *,
        construct_registry: SPLConstructRegistry,
        checker_registry: IRSCheckerRegistry,
        projector: DiagnosticProjector,
        policy: IRSPolicy,
    ) -> None: ...

    def run_stage_local(
        self,
        stage_name: str,
        context: IRSCheckContext,
    ) -> IRSStageResult: ...

    def run_post_normalize(
        self,
        *,
        worker: WorkerIR,
        worker_plan: WorkerPlanIR | None,
        symbol_table: SymbolTable | None,
        resources: ResourceRegistryIR | None,
        worker_scoped_resources: WorkerScopedResourceIR | None,
    ) -> IRSPostNormalizeResult: ...
```

### 4.2 `IRSPolicy`

建议新增：

```text
src/nl2spl/compiler/irs/policy.py
```

用于集中控制：

- 哪些 stage-local checks 运行。
- stage-local diagnostics 是否进入 final compile diagnostics。
- 哪些 diagnostic kind 由 Post-normalize 覆盖。
- 是否收集 graph snapshot。
- 是否在 feedback report 中展示 construct satisfaction。

建议字段：

```python
@dataclass(frozen=True)
class IRSPolicy:
    stage_local_enabled: bool = True
    stage3_5_worker_delegation_enabled: bool = True
    stage4_exception_flow_enabled: bool = True
    stage7_step_enabled: bool = True
    post_normalize_enabled: bool = True
    project_stage_local_diagnostics: bool = True
    include_stage_local_in_final_diagnostics: bool = False
    include_construct_satisfaction_in_feedback: bool = True
    collect_graph_snapshot: bool = True
```

默认建议：

- `post_normalize_enabled=True`
- `stage_local_enabled=True`
- `include_stage_local_in_final_diagnostics=False`

原因：

- Stage-local report 应该默认可观察。
- 最终 compile diagnostics 仍由 Post-normalize / Gate / ProducerIndex 等 authority 决定。
- 避免 Stage 4/7 early diagnostics 和 Post-normalize final diagnostics 重复。

### 4.3 `IRSResultStore`

建议新增：

```text
src/nl2spl/compiler/irs/result_store.py
```

职责：

- 统一保存 IRS 结果。
- 替代 orchestrator 中散落的 `intermediate.setdefault(...)`。
- 提供 deterministic snapshot，便于 checkpoint、report、测试。

建议结构：

```python
@dataclass
class IRSStageResult:
    stage_name: str
    reports: list[ConstructSatisfactionReport]
    diagnostics: list[CompileDiagnostic]
    graph: ConstructGraph | None = None
    warnings: list[str] = field(default_factory=list)

@dataclass
class IRSResultStore:
    stage_results: dict[str, IRSStageResult] = field(default_factory=dict)
    post_normalize_diagnostics: list[CompileDiagnostic] = field(default_factory=list)

    def put_stage_result(self, result: IRSStageResult) -> None: ...
    def reports_for(self, stage_name: str) -> list[ConstructSatisfactionReport]: ...
    def diagnostics_for(self, stage_name: str) -> list[CompileDiagnostic]: ...
    def all_stage_local_diagnostics(self) -> list[CompileDiagnostic]: ...
    def to_intermediate_payload(self) -> dict[str, Any]: ...
```

Orchestrator 只需要：

```python
irs_store = IRSResultStore()
irs_store.put_stage_result(...)
intermediate["irs"] = irs_store.to_intermediate_payload()
```

为了兼容已有中间结果，也可同步写：

```python
intermediate["construct_satisfaction"][stage] = reports
intermediate["stage_local_diagnostics"][stage] = diagnostics
```

但这些应由 `IRSResultStore` 统一写，不由各 stage 手写。

### 4.4 `DiagnosticConsolidator`

建议新增：

```text
src/nl2spl/compiler/diagnostic_consolidator.py
```

职责：

- 合并 stage-local diagnostics、post-normalize diagnostics、gate diagnostics、provenance diagnostics。
- 明确 authority 优先级。
- 执行 dedup。
- 保留 suppressed diagnostics 作为 debug metadata，而不是静默丢弃。

建议优先级：

```text
1. validation errors
2. post-normalize IRS diagnostics
3. gate diagnostics
4. producer/provenance diagnostics
5. route/delegation/conflict diagnostics
6. stage-local IRS diagnostics
```

Stage-local IRS diagnostics 的合并策略：

```text
如果和 post-normalize diagnostic 同 kind + target_ref + missing_slot + source_span_ids:
  不进入 final compile_diagnostics
  作为 suppressed_stage_local_diagnostics 保留

如果是 stage-local 独有的 report-only diagnostic:
  可进入 feedback 的 early IRS section
  默认不 blocks_completion
```

建议 dedup key：

```python
(
    diagnostic.kind,
    diagnostic.target_ref,
    missing_slot_name,
    tuple(sorted(diagnostic.source_span_ids)),
)
```

### 4.5 `ConstructSatisfactionFeedbackProjector`

建议新增：

```text
src/nl2spl/compiler/irs/feedback_projector.py
```

职责：

- 将 `ConstructSatisfactionReport` 渲染成 feedback report 的结构化 section。
- 不产生 `CompileDiagnostic`。
- 不判断新语义。

Feedback report 新增 section：

```text
## Construct Satisfaction

### Stage 3.5 Worker / Delegation
- WORKER_CANDIDATE cand_1: complete
- WORKER_PROMOTION cand_1: blocked
  - missing promotion_input_contract
  - missing promotion_output_contract
  - missing promotion_invocation_point
  - missing promotion_result_handoff

### Stage 4 Exception Flows
- EXCEPTION_FLOW exc_adapter_00: partial

### Stage 7 Steps
- GENERAL_COMMAND st_1: complete
- CALL_API st_2: blocked, missing api_name
```

这个 section 用来解释 stage-local IRS；最终是否 partial / blocked 仍由 final diagnostics 和 completeness 决定。

## 5. Runtime 触发设计

### 5.1 Stage 3.5 触发点

触发位置：

```text
WorkerBoundaryPlanner.execute(...)
-> WorkerPlanValidator.validate(...)
-> IRSSubsystem.run_stage_local("stage3_5", ...)
```

前置条件：

- `WorkerPlanValidator` 通过。
- 不修改 `WorkerPlanIR`。

Context：

```python
IRSCheckContext(
    stage_name="stage3_5",
    spans=tuple(resolved_spans),
    routes=resolved_routes,
    worker_plan=worker_plan,
    metadata={
        "source_schema": canonical_input.source_schema,
    },
)
```

产物：

- `WORKER_CANDIDATE`
- `WORKER_PROMOTION`
- `CHILD_WORKER`
- `WORKER_HANDOFF`

使用价值：

- 明确 delegation candidate 为什么没有晋升 child worker。
- 明确已 materialized handoff 是否有完整 contract。
- 为 Issue 3 的 feedback report 提供结构化解释。

### 5.2 Stage 4 触发点

触发位置：

```text
FlowAssembler.execute(...)
-> IRSSubsystem.run_stage_local("stage4", ...)
```

Context：

```python
IRSCheckContext(
    stage_name="stage4",
    flow=flow_structure,
    worker_flows=worker_flow_plan,
    routes=resolved_routes,
    spans=tuple(resolved_spans),
)
```

产物：

- `EXCEPTION_FLOW` satisfaction reports。

规则：

- Stage 4 可以报告 condition slot。
- Stage 4 不负责最终 missing_handler。
- `handler_action` 属于 cross-stage slot，最终由 Post-normalize 判断。

### 5.3 Stage 7 触发点

触发位置：

```text
StepExtractor.execute(...)
-> IRSSubsystem.run_stage_local("stage7", ...)
```

Context：

```python
IRSCheckContext(
    stage_name="stage7",
    steps=tuple(steps),
    worker_steps=worker_step_plan,
    routes=resolved_routes,
    symbol_table=symbol_table,
)
```

产物：

- `GENERAL_COMMAND`
- `REQUEST_INPUT`
- `CALL_API`
- `INVOKE_WORKER`

规则：

- Stage 7 IRS 可以解释 step slot satisfaction。
- Stage 7 IRS 不决定最终 renderability。
- Gate 仍是 executable renderability authority。

### 5.4 Post-normalize 触发点

触发位置不变：

```text
Stage 10 Worker Assembly
-> IRSSubsystem.run_post_normalize(...)
-> ExecutableElementGate
```

产物：

- final construct-level compile diagnostics。

当前 `PostNormalizeIRSChecker` 可先保留，但应由 `IRSSubsystem` 包装调用，避免 orchestrator 直接创建 checker。

## 6. Orchestrator 目标结构

Orchestrator 不应直接知道具体 checker。

目标调用结构：

```python
irs = build_irs_subsystem(policy=self.config.irs_policy)
irs_store = IRSResultStore()

# Stage 3.5
worker_plan = self._run_stage3_5(...)
validate(worker_plan)
irs_store.put_stage_result(
    irs.run_stage_local("stage3_5", context)
)

# Stage 4
worker_flow_plan = self._run_stage4(...)
irs_store.put_stage_result(
    irs.run_stage_local("stage4", context)
)

# Stage 7
worker_step_plan = self._run_stage7_worker_scoped(...)
irs_store.put_stage_result(
    irs.run_stage_local("stage7", context)
)

# Stage 10
worker = self._run_stage10_worker_scoped(...)
post_norm = irs.run_post_normalize(...)

# Consolidation
all_diagnostics = diagnostic_consolidator.consolidate(
    stage2=stage2_diags,
    stage7=stage7_diags,
    irs_store=irs_store,
    post_normalize=post_norm.diagnostics,
    gate=gate_diags,
    provenance=provenance_diags,
    delegation=delegation_diags,
    conflict=conflict_diags,
)
```

## 7. Configuration 设计

当前 `PipelineConfig` 已经清理掉旧 IRS flags。产品化后不建议恢复大量散乱 flags。

建议新增一个整体配置对象：

```python
@dataclass(frozen=True)
class IRSRuntimeConfig:
    enabled: bool = True
    stage_local_enabled: bool = True
    worker_delegation_enabled: bool = True
    exception_flow_enabled: bool = True
    step_enabled: bool = True
    post_normalize_enabled: bool = True
    include_stage_local_diagnostics_in_compile: bool = False
    include_construct_satisfaction_in_feedback: bool = True
    collect_graph_snapshot: bool = True
```

`PipelineConfig` 中只放一个字段：

```python
irs: IRSRuntimeConfig = field(default_factory=IRSRuntimeConfig)
```

不建议恢复：

- `enable_irs_v6_runner`
- `enable_irs_stage4_exception_flow_check`
- `enable_irs_stage7_step_check`
- `enable_irs_diagnostic_consolidation`

原因：

- 这些 flags 混合了 runtime、migration、diagnostic merge、prompt injection，不适合作为产品级配置。
- 产品化后应由 `IRSRuntimeConfig` 明确表达 policy。

## 8. Diagnostic 与 report 策略

### 8.1 Compile diagnostics

默认进入 `compile_diagnostics`：

- Stage 2 route diagnostics。
- Post-normalize IRS diagnostics。
- Gate diagnostics。
- Provenance diagnostics。
- Delegation diagnostics。
- Semantic conflict diagnostics。
- Stage 7 extractor 自身 diagnostics。

默认不进入 `compile_diagnostics`：

- Stage-local IRS diagnostics，如果它们会被 Post-normalize 覆盖。

默认进入 feedback 的 construct satisfaction section：

- 所有 stage-local `ConstructSatisfactionReport`。

### 8.2 Missing slot source

所有 IRS diagnostics 必须有：

- `missing_slot.slot_name`
- `missing_slot.required_for`
- `missing_slot.reason`
- `source_span_ids`

Stage-local report 如果缺 `source_span_ids`，应解释原因：

- materialized construct 无来源。
- compiler scaffold。
- synthetic compatibility path。

不允许静默空 provenance。

### 8.3 Completeness

`compute_completeness()` 仍只看 final compile diagnostics 和 validation errors。

Stage-local reports 不直接改变 completeness，除非经过 `DiagnosticConsolidator` 明确投影为 final diagnostic。

## 9. 未来递归 IRS 预留接口

产品化 subsystem 必须为未来递归 IRS 留接口，但本阶段不实现递归 traversal。

需要保留：

- `ConstructGraph`
- `ConstructEdge`
- `frontier_status`
- `cutline_reason`
- `construct_path`
- `primary_parent_id`
- `candidate_only`
- `materialized`
- `source_demanded`

未来递归 evaluator 的入口可以是：

```python
class RecursiveIRSEvaluator:
    def evaluate(
        self,
        *,
        root_construct_id: str,
        graph: ConstructGraph,
        reports: list[ConstructSatisfactionReport],
        policy: RecursiveIRSPolicy,
    ) -> RecursiveIRSResult: ...
```

递归规则：

- 遇到 `cutline_blocked` 停止下钻。
- 遇到 source-demanded child 才检查 child。
- 不为不存在 source demand 的 child 生成 report。
- 不替代 Gate / ProducerIndex。

## 10. 落地阶段建议

### R10: IRS Runtime Subsystem Foundation

目标：

- 新增 `IRSSubsystem`、`IRSPolicy`、`IRSResultStore`。
- 不改变 pipeline 行为。
- 通过单元测试验证 stage-local / post-normalize 调用接口。

验收：

- Orchestrator 尚不接入。
- No LLM。
- No IR mutation。
- ResultStore 可生成 deterministic intermediate payload。

### R11: Stage-local Runtime Integration

目标：

- Orchestrator 接入 Stage 3.5 / 4 / 7 stage-local IRS。
- Reports 写入 `construct_satisfaction`。
- Diagnostics 写入 `stage_local_diagnostics`。
- 默认不把 stage-local diagnostics 并入 final compile diagnostics。

验收：

- Stage 3.5 Worker/Delegation reports 出现在 intermediate。
- Stage 4 ExceptionFlow reports 出现在 intermediate。
- Stage 7 Step reports 出现在 intermediate。
- SPL 输出不因 stage-local IRS 改变。
- WorkerPlanIR / FlowIR / StepIR 不被 IRS 修改。

### R12: Diagnostic Consolidation Productization

目标：

- 新增 `DiagnosticConsolidator`。
- 统一 all diagnostics 汇总。
- stage-local diagnostics 与 post-normalize diagnostics 去重。
- suppressed diagnostics 可追踪。

验收：

- 同一 missing slot 不重复出现在 compile diagnostics。
- Post-normalize 优先于 Stage-local。
- Gate diagnostics 不被 IRS 覆盖。
- Required output producer diagnostics 仍由 ProducerIndex/Post-normalize 权威路径产生。

### R13: Feedback Report Productization

目标：

- Feedback report 展示 construct satisfaction section。
- 区分 early IRS report 与 final diagnostics。
- Issue 3 worker promotion blocked 的原因清晰可见。

验收：

- Feedback report 明确列出 `WORKER_PROMOTION` 缺四个 promotion slots。
- Feedback report 不把 candidate complete 误写成 child worker ready。
- Feedback report 不重新做 IRS 判断。

### R14: Cleanup and Audit

目标：

- 清理旧 wrapper 与旧 flags 文档漂移。
- 更新 IRS skill。
- 更新 R9 audit。

验收：

- `rg enable_irs_` 不再出现旧 migration flags，除文档历史说明外。
- Orchestrator 不直接 import concrete checker。
- Renderer / Gate / ProducerIndex 不依赖 IRS runner。
- 全量测试通过。

## 11. 测试矩阵

### 11.1 Unit tests

`IRSSubsystem`：

- 空 checker registry 返回空 stage result。
- Stage 3.5 context 调用 WorkerDelegation checker。
- Stage 4 context 调用 ExceptionFlow checker。
- Stage 7 context 调用 Step checker。
- Post-normalize wrapper 调用 `PostNormalizeIRSChecker`。

`IRSResultStore`：

- 可保存多 stage result。
- deterministic payload。
- 不共享 mutable lists。

`DiagnosticConsolidator`：

- Post-normalize diagnostic 覆盖 stage-local duplicate。
- 不同 missing_slot 不误合并。
- Gate diagnostic 保留。
- Suppressed diagnostics 可观察。

### 11.2 Integration tests

Orchestrator：

- Stage 3.5 reports 写入 intermediate。
- Stage 4 reports 写入 intermediate。
- Stage 7 reports 写入 intermediate。
- 默认 SPL 不因 IRS report 改变。
- Final compile diagnostics 不重复。

Feedback：

- Construct satisfaction section 出现。
- Final diagnostics section 仍来自 `compile_diagnostics`。
- Worker promotion blocked 显示 missing slots。

### 11.3 Regression scenarios

- Failure condition only -> partial exception flow + missing handler final diagnostic。
- Failure condition + handler evidence -> handler not materialized as condition。
- Worker delegation candidate missing contracts -> candidate complete, promotion blocked。
- CALL_API without declared API -> type_or_contract_ambiguity。
- GENERAL_COMMAND without source evidence -> assumed_command_not_renderable。
- Required output without producer -> missing_output_producer。

## 12. 验收标准

产品化完成时必须满足：

1. IRS 有唯一 runtime subsystem 入口，orchestrator 不直接组装 checker。
2. Stage 3.5 / 4 / 7 stage-local IRS 都按设计触发。
3. Post-normalize IRS 仍是 final construct-level authority。
4. Gate 仍是 executable renderability authority。
5. Feedback report 展示 construct satisfaction，但不重新做检查。
6. Checker 不调用 LLM、不解析 raw NL、不修改 IR、不生成 construct。
7. Checker 从 `ConstructIRS` 读取 slot contract。
8. Diagnostics 由 projector / consolidator 统一投影与合并。
9. Stage-local diagnostics 与 final diagnostics 不重复误导用户。
10. 新增一个 IRS checker 不需要修改 renderer、gate、ProducerIndex。
11. 所有 intermediate output 可追踪 stage、construct、slot、source span。
12. 为未来 recursive IRS 保留 graph/frontier/cutline 接口。

## 13. 关键风险与控制

### 风险 1: stage-local diagnostics 与 final diagnostics 重复

控制：

- 默认不把 stage-local diagnostics 放入 final compile diagnostics。
- 通过 `DiagnosticConsolidator` 显式合并。
- Post-normalize 优先。

### 风险 2: checker 重新变成 rule-based NL parser

控制：

- Checker 只能消费结构化 IR 字段。
- 需要语义理解的判断必须来自上游 LLM / adapter / route annotation。
- 若某一步存在 LLM 与 rule-based 两种方案，必须先确认实现方式。

### 风险 3: feedback report 暗中承担判断

控制：

- Feedback projector 只渲染 report，不产生 diagnostic。
- 所有判断必须来自 `ConstructSatisfactionReport` 或 `CompileDiagnostic`。

### 风险 4: 递归接口过早实现

控制：

- 当前只保留 `ConstructGraph` / frontier / cutline。
- 不实现 recursive evaluator。
- 不改变现有 stage-local checking。

## 14. 总结

IRS 产品化的核心不是“多跑几个 checker”，而是建立一个稳定的 compiler subsystem：

```text
spec-driven
checker-pluggable
stage-local observable
post-normalize authoritative
diagnostic-consolidated
feedback-visible
graph-ready
non-generative
```

按本方案落地后，IRS 将能支撑后续新增 construct IRS、worker/delegation 解释、feedback report 可观察性，以及未来递归 IRS 检查，而不会把复杂度继续堆到 orchestrator、Gate 或 renderer 中。
