# NL2SPL Diagnostics 架构设计

版本: 1.0  
日期: 2026-06-08  
状态: Proposed architecture design  
范围: compiler diagnostics、内部诊断、telemetry、feedback report、compile report 以及 diagnostic consolidation 边界

## 1. 背景

当前 pipeline 使用 `CompileDiagnostic` 同时承载多种性质不同的信息：

1. 用户可行动的需求缺口，例如 `missing_handler`。
2. 编译器一致性或完整性问题，例如 handoff contract 不完整。
3. stage-local 或 provisional findings。
4. 内部 LLM refinement 修正事件，例如 `route_refinement_corrected`。

这会造成报告泄漏：Stage 2 的内部 route refinement 事件进入 `compile_diagnostics` 后，`compile_report.txt` 和 `feedback_report.md` 又都渲染同一组 diagnostics，最终导致面向用户的 feedback 中出现实现细节，例如：

```text
LLM refinement corrected: role 'profile_domain' requires route_family='profile'
```

这不是用户需求的问题，而是编译器内部观测事件。

因此 diagnostics 架构必须明确区分：

```text
compiler observability
  与
user-actionable feedback
```

本设计文档定义一套可执行的 diagnostics 分层方案，用于阻止内部系统状态泄漏到用户反馈，同时保留必要的调试能力。

## 2. 设计目标

1. 防止内部 compiler diagnostics 泄漏到用户层面的 `feedback_report.md`。
2. MVP 阶段将内部 diagnostics 保留在结构化 checkpoint 中；post-MVP 引入 audience-aware report 架构后，内部 diagnostics 可以进入 `compile_report.txt`。
3. 用户完成度、用户修复建议、assumptions 只基于最终用户可行动的 requirement diagnostics。
4. diagnostic 的 authority、audience、domain、channel 必须显式化。
5. renderer 不做业务判断。renderer 只渲染 report model，不负责分类、过滤或推断 diagnostics。
6. 保持 IRS 边界：
   - IRS 负责 construct slot satisfaction。
   - Post-normalize IRS 是最终 construct-level authority。
   - DiagnosticConsolidator 负责 merge / dedup / suppress，不创造新事实。
   - Feedback report 只渲染已投影的反馈，不重新执行 IRS 检查，也不推断 missing slot。
7. 为现有 `CompileDiagnostic` 调用方提供迁移路径。

## 3. 非目标

1. 本设计不改变 SPL rendering 行为。
2. 本设计不让 IRS 解析 raw NL、调用 LLM、推断 missing slots 或修改 IR。
3. 本设计不删除 checkpoint 中的 debug 信息。
4. 本设计不把 renderer 过滤作为主要修复方式。
5. 本设计不要求一次性修改所有 legacy tests，而是定义分阶段迁移。

## 4. 当前架构问题

当前简化路径如下：

```text
stage diagnostics / IRS diagnostics / route diagnostics
  -> DiagnosticConsolidator.final_diagnostics
  -> PipelineResult.compile_diagnostics
  -> render_report(... diagnostics=compile_diagnostics ...)
  -> render_feedback_report(... diagnostics=compile_diagnostics ...)
```

问题不在于存在两个 report，而在于两个 report 接收的是同一组未分层 diagnostics。

两个 report 的目标 audience 不同：

| Artifact | Audience | 应包含 |
|---|---|---|
| `feedback_report.md` | 用户、需求评审者 | materialized requirements、需求缺口、用户补充建议、provenance、SPL draft |
| `compile_report.txt` | 工程师、operator、pipeline 维护者 | 完整 compiler observability、用户诊断、内部诊断、telemetry summary、validation、IRS reports |

因此它们不能直接消费同一组 raw diagnostics。

## 5. Diagnostic Taxonomy

diagnostics 必须按用途建模，而不能只靠 `kind` 字符串区分。

### 5.1 RequirementDiagnostic

`RequirementDiagnostic` 描述由于源需求不完整、不明确或不可 materialize 而产生的缺口、歧义或 anti-fabrication 决策。

典型例子：

1. `missing_handler`
2. `missing_output_producer`
3. `type_or_contract_ambiguity`
4. `assumed_command_not_renderable`
5. `unmapped_behavior_span`
6. `missing_provenance`

性质：

1. 面向用户。
2. 可以影响 completeness。
3. 必须有 source evidence 或 target reference。
4. message 必须使用用户可理解语言。
5. 如果阻塞 completion，通常应提供 `suggested_resolution`。

允许进入：

```text
feedback_report.md
compile_report.txt（post-MVP）
```

### 5.2 CompilerDiagnostic

`CompilerDiagnostic` 描述编译器行为、内部一致性、normalization、validation、LLM 输出修正等工程可观测信息。它对工程调试有价值，但不是直接的用户需求问题。

典型例子：

1. `route_refinement_corrected`
2. `route_refinement_rejected`
3. `route_refinement_fallback`
4. `route_refinement_provenance_mismatch`
5. 被接受为内部审计记录的 LLM parse issue
6. validator repair event

性质：

1. 面向 developer / operator。
2. 默认不影响 requirement completeness。
3. 不应产生 user assumptions。
4. MVP 阶段保留在 checkpoint / intermediate 中。
5. post-MVP 可进入 `compile_report.txt`。

不允许进入：

```text
feedback_report.md
```

### 5.3 TelemetryEvent

`TelemetryEvent` 是更低层的运行观测，可能过于冗长，不适合默认进入 human-readable report，但必须保留在 checkpoint 或结构化运行产物中。

典型例子：

1. 每个字段的 LLM normalization detail。
2. raw parse warning。
3. prompt/response validation warning。
4. 非 authoritative 的 stage-local trace。

性质：

1. 仅用于工程调试。
2. 不影响 completeness。
3. 不产生 user assumption。
4. 可以在 post-MVP compile report 中以 summary 形式展示，但不应默认 verbatim 展示。

## 6. 统一 Diagnostic Envelope（Post-MVP）

长期架构应引入带显式分类元数据的 diagnostic envelope。

```python
DiagnosticAudience = Literal["user", "developer", "operator"]
DiagnosticDomain = Literal[
    "requirement",
    "compiler",
    "irs",
    "route_refinement",
    "validation",
    "provenance",
    "telemetry",
]
DiagnosticChannel = Literal[
    "feedback_report",
    "compile_report",
    "checkpoint",
]
DiagnosticLifecycle = Literal[
    "provisional",
    "final",
    "suppressed",
]
```

建议基础模型：

```python
@dataclass(frozen=True)
class DiagnosticEnvelope:
    diagnostic_id: str
    kind: str
    severity: Literal["info", "warning", "error"]
    message: str

    audience: DiagnosticAudience
    domain: DiagnosticDomain
    channels: frozenset[DiagnosticChannel]
    lifecycle: DiagnosticLifecycle = "final"

    target_ref: str | None = None
    source_span_ids: tuple[str, ...] = ()
    suggested_resolution: str | None = None
    missing_slot: MissingSlot | None = None

    blocks_rendering: bool = False
    blocks_completion: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)
```

兼容适配：

```python
def to_legacy_compile_diagnostic(envelope: DiagnosticEnvelope) -> CompileDiagnostic:
    ...
```

legacy adapter 只应存在于兼容边界。新的分类逻辑必须基于 `DiagnosticEnvelope` 或显式 typed wrappers。

## 7. 专用类型

代码层可以用 envelope 的特化类型表达语义：

```python
RequirementDiagnostic = DiagnosticEnvelope  # audience=user, domain=requirement
CompilerDiagnostic = DiagnosticEnvelope     # audience=developer/operator
TelemetryEvent = DiagnosticEnvelope         # domain=telemetry
```

如果未来改为独立 dataclass，也必须能转换为统一 envelope，供 routing 和 report model 构造使用。

## 8. Diagnostic Authority 边界

| Source | 可以产生 | 不应产生 |
|---|---|---|
| Stage 2 route refinement | `CompilerDiagnostic`, `TelemetryEvent` | `RequirementDiagnostic`，除非有明确 user-facing ambiguity projector |
| ConstructPlan | demand planning 不稳定时的 `RequirementDiagnostic` | IRS slot-satisfaction diagnostics |
| IRS stage-local runtime | provisional IRS reports / diagnostics | final completion authority |
| Post-normalize IRS | final construct-level `RequirementDiagnostic` | route refinement telemetry |
| ExecutableElementGate | renderability diagnostics 或 render info | construct slot satisfaction |
| ProducerIndex | required-output producer diagnostics | synthetic producer steps |
| DiagnosticConsolidator | merge、dedup、suppress、classify lifecycle | raw NL parsing、新 semantic inference |
| ReportModelBuilder | 按 report audience 选择 diagnostics | 创建新的 diagnostic facts |
| Renderers | 渲染 report models | 分类、过滤、推断或 mutate diagnostics |

## 9. DiagnosticRouter（Post-MVP）

post-MVP 应在 diagnostic producers 与 report model builders 之间引入 `DiagnosticRouter`。

职责：

1. 接收 diagnostic envelopes、legacy diagnostics、telemetry events、IRS result stores。
2. 将 legacy diagnostics 规范化为 envelopes。
3. 根据 registry policy 分配 audience、domain、channel、lifecycle。
4. 按 audience/channel 使用 authority-safe keys 去重。
5. 生成 report-specific diagnostic views。

非职责：

1. 不解析 raw NL。
2. 不调用 LLM。
3. 不创造 missing slots。
4. 不把内部 telemetry 自动改写成用户反馈，除非有显式 projector。

建议 API：

```python
@dataclass(frozen=True)
class DiagnosticRoutingInput:
    requirement_diagnostics: Sequence[DiagnosticEnvelope] = ()
    compiler_diagnostics: Sequence[DiagnosticEnvelope] = ()
    telemetry_events: Sequence[DiagnosticEnvelope] = ()
    legacy_compile_diagnostics: Sequence[CompileDiagnostic] = ()
    irs_store: IRSResultStore | None = None

@dataclass(frozen=True)
class DiagnosticRoutingResult:
    all_diagnostics: tuple[DiagnosticEnvelope, ...]
    requirement_diagnostics: tuple[DiagnosticEnvelope, ...]
    compiler_diagnostics: tuple[DiagnosticEnvelope, ...]
    telemetry_events: tuple[DiagnosticEnvelope, ...]
    feedback_diagnostics: tuple[DiagnosticEnvelope, ...]
    compile_report_diagnostics: tuple[DiagnosticEnvelope, ...]
    suppressed_diagnostics: tuple[DiagnosticEnvelope, ...]
    routing_warnings: tuple[str, ...]
```

channel 选择规则：

```python
feedback_diagnostics =
    diagnostics where
      audience == "user"
      and "feedback_report" in channels
      and lifecycle == "final"

compile_report_diagnostics =
    diagnostics where
      "compile_report" in channels
      and lifecycle in {"final", "provisional", "suppressed"}
```

## 10. DiagnosticRegistry Policy

`DiagnosticRegistry` 不应只记录 kind / severity，还应成为 classification policy 的来源。

建议扩展：

```python
@dataclass(frozen=True)
class DiagnosticSpec:
    kind: str
    severity: str
    description: str

    default_audience: DiagnosticAudience
    default_domain: DiagnosticDomain
    default_channels: frozenset[DiagnosticChannel]
    affects_completeness: bool
    user_actionable: bool
```

示例策略：

| Kind | Audience | Domain | Channels | Completeness |
|---|---|---|---|---|
| `missing_handler` | user | requirement | feedback_report, compile_report | yes |
| `missing_output_producer` | user | requirement | feedback_report, compile_report | yes |
| `type_or_contract_ambiguity` | user | requirement | feedback_report, compile_report | blocking 时 yes |
| `route_refinement_corrected` | developer | route_refinement | checkpoint, compile_report | no |
| `route_refinement_diagnostic` | developer | route_refinement | checkpoint, compile_report | no |
| `route_refinement_rejected` | developer | route_refinement | checkpoint, compile_report | 默认 no |
| `missing_provenance` | user 或 developer，取决于来源 | provenance | policy-dependent | policy-dependent |

未知 diagnostic kind 的默认策略必须保守：

```text
audience=developer
domain=compiler
channels={checkpoint, compile_report}
blocks_completion=false
```

未知 kind 不允许默认进入 `feedback_report.md`。

## 11. Report Models（Post-MVP）

renderer 必须消费 report model，而不是直接消费 pipeline raw state。

### 11.1 CompileReportModel

```python
@dataclass(frozen=True)
class CompileReportModel:
    spl_text: str
    completeness: Completeness
    requirement_diagnostics: tuple[DiagnosticEnvelope, ...]
    compiler_diagnostics: tuple[DiagnosticEnvelope, ...]
    telemetry_summary: tuple[str, ...]
    assumptions: tuple[CompileAssumption, ...]
    traces: tuple[TraceRecord, ...]
    construct_satisfaction: Mapping[str, Sequence[ConstructSatisfactionReport]]
    adapter_warnings: tuple[str, ...]
    validation_errors: tuple[str, ...]
    validation_warnings: tuple[str, ...]
```

compile report sections：

1. Summary。
2. Requirement diagnostics。
3. Internal compiler diagnostics。
4. Telemetry summary。
5. Assumptions。
6. Provenance。
7. Construct satisfaction。
8. Validation。
9. Generated SPL。

### 11.2 FeedbackReportModel

```python
@dataclass(frozen=True)
class FeedbackReportModel:
    spl_text: str
    completeness: Completeness
    diagnostics: tuple[DiagnosticEnvelope, ...]  # user-facing only
    assumptions: tuple[CompileAssumption, ...]
    traces: tuple[TraceRecord, ...]
    adapter_warnings: tuple[str, ...]
    validation_errors: tuple[str, ...]
    validation_warnings: tuple[str, ...]
```

feedback report sections：

1. Overall compile state。
2. Materialized source-backed structure。
3. Not materialized / kept partial。
4. User-facing diagnostics。
5. Assumptions / suggestions。
6. Provenance。
7. Anti-fabrication explanation。
8. Validation。
9. SPL draft。

feedback report 不允许渲染：

1. `audience != "user"`。
2. `domain in {"compiler", "route_refinement", "telemetry"}`。
3. `lifecycle != "final"`。
4. 未注册 diagnostic kind。

## 12. PipelineResult Shape（Post-MVP）

长期 `PipelineResult` 建议：

```python
@dataclass
class PipelineResult:
    spl_text: str
    validation_errors: list[str]
    validation_warnings: list[str]

    requirement_diagnostics: list[DiagnosticEnvelope]
    compiler_diagnostics: list[DiagnosticEnvelope]
    telemetry_events: list[DiagnosticEnvelope]

    compile_report: str
    feedback_report: str

    traces: list[TraceRecord]
    adapter_warnings: list[str]
    completeness: Completeness
    assumptions: list[CompileAssumption]
    intermediate_results: dict[str, Any]
    final_spl_path: Path | None
```

兼容属性：

```python
@property
def compile_diagnostics(self) -> list[CompileDiagnostic]:
    return [
        to_legacy_compile_diagnostic(d)
        for d in self.requirement_diagnostics
    ]

@property
def diagnostics(self) -> list[CompileDiagnostic]:
    return self.compile_diagnostics
```

兼容属性故意只返回用户层面的 requirement diagnostics。内部 diagnostics 必须通过 `compiler_diagnostics` 获取。

## 13. Completeness 规则

Completeness 只能基于 validation errors 和最终用户可行动 requirement diagnostics 计算。

```python
completeness = compute_completeness(
    validation_errors=validation_errors,
    diagnostics=requirement_diagnostics,
)
```

规则：

1. `CompilerDiagnostic` 默认不阻塞 completion。
2. `TelemetryEvent` 永不阻塞 completion。
3. 阻塞 completion 的 diagnostic 必须是 user-actionable，或是 validation error。
4. 如果内部问题导致输出不可信，应升级为 validation error 或 compiler failure，而不是伪装成用户 feedback diagnostic。

## 14. Assumption 规则

`AssumptionBuilder` 只能消费最终用户可行动 requirement diagnostics。

```python
assumptions = AssumptionBuilder().build(requirement_diagnostics)
```

内部 diagnostics 不得生成 user assumptions。

## 15. Route Refinement Case Study

当前事件：

```text
LLM refinement corrected: role 'profile_domain' requires route_family='profile',
got None for span 's1'
```

长期架构中的正确分类：

```python
DiagnosticEnvelope(
    diagnostic_id="diag_rf_000",
    kind="route_refinement_corrected",
    severity="info",
    message="LLM refinement corrected ...",
    audience="developer",
    domain="route_refinement",
    channels=frozenset({"compile_report", "checkpoint"}),
    lifecycle="final",
    target_ref="stage2:field_route:s1",
    source_span_ids=("s1",),
    blocks_completion=False,
)
```

长期架构中允许进入：

```text
compile_report.txt
stage2_field_router.json
intermediate_results
```

MVP 中允许进入：

```text
stage2_field_router.json
intermediate_results
logs, if configured
```

MVP 不生成 human-readable internal compile report，因此内部 route refinement 事件只通过结构化 checkpoint 暴露。

禁止进入：

```text
feedback_report.md
AssumptionBuilder input
completeness input
```

如果 route 问题确实需要用户行动，必须显式投影成另一个用户语义 kind，例如：

```text
source_route_ambiguous:
  The source span can be interpreted as either a process step or a policy.
  Please clarify whether it should be executable.
```

内部 LLM repair 文本不得直接复用为用户 feedback。

## 16. MVP Implementation Plan

MVP 决策：停止维护两个 audience 不清的 human-readable reports。MVP 只生成一个人工阅读报告：

```text
feedback_report.md
```

内部 compiler observations 保留在结构化 checkpoints 和 `intermediate_results` 中，但不渲染成人工报告。

### 16.1 MVP 输出产物

MVP 保留：

```text
final_spl.txt
feedback_report.md
stage*_*.json checkpoints
```

MVP 停止生成：

```text
compile_report.txt
```

理由：

1. 当前 `compile_report.txt` 和 `feedback_report.md` 消费同一个 `compile_diagnostics` list。
2. 在没有 audience-aware routing 的情况下，两个 report 只是形式上分离，实际上仍会把内部 diagnostics 泄漏到 feedback。
3. checkpoint 已经保留调试内部 diagnostics 所需的信息。
4. 未来如果恢复 `compile_report.txt`，必须先实现 `DiagnosticRouter` 和 report models。

### 16.2 MVP Diagnostic 语义

MVP 中，`PipelineResult.compile_diagnostics` 的语义收窄为：

```text
final user-actionable requirement diagnostics
```

不得包含：

1. `route_refinement_corrected`
2. `route_refinement_diagnostic`
3. `route_refinement_rejected`
4. `route_refinement_fallback`
5. `route_refinement_suppressed`
6. LLM parse issues
7. validator repair logs
8. stage-local provisional diagnostics，除非被 final authority 显式提升

可以包含：

1. `missing_handler`
2. `missing_output_producer`
3. `type_or_contract_ambiguity`
4. `assumed_command_not_renderable`
5. `unmapped_behavior_span`
6. user-actionable 的 `missing_provenance`

Completeness 和 assumptions 只能基于这组收窄后的 diagnostics 计算。

### 16.3 Planned Code Changes

#### Change A: 停止提升 Stage 2 内部 diagnostics

当前行为：

```text
routes.structured_route_diagnostics
  -> intermediate["stage_local_diagnostics"]["stage2"]
  -> DiagnosticConsolidator.stage2_diagnostics
  -> PipelineResult.compile_diagnostics
  -> feedback_report.md
```

MVP 行为：

```text
routes.route_diagnostics
routes.structured_route_diagnostics
  -> stage2_field_router.json
  -> intermediate_results["stage2_routes"]
  -> not DiagnosticConsolidator
  -> not PipelineResult.compile_diagnostics
  -> not feedback_report.md
```

修改位置：

```text
src/nl2spl/pipeline/orchestrator.py
```

删除或禁用把 `routes.structured_route_diagnostics` 转换成 `CompileDiagnostic` 的 Stage 2 block。保留 `FieldRouteIR` 上的 route diagnostics，确保 checkpoint/debug inspection 仍可用。

#### Change B: 停止将 Stage 2 diagnostics 传给 consolidation

当前行为：

```python
stage2_diags = intermediate.get("stage_local_diagnostics", {}).get("stage2", [])
DiagnosticConsolidationInput(stage2_diagnostics=list(stage2_diags), ...)
```

MVP 行为：

```python
DiagnosticConsolidationInput(stage2_diagnostics=[], ...)
```

或者直接移除 Stage 2 diagnostic group，直到未来有明确 route diagnostic projector 可以创建用户可行动的 requirement diagnostic。

#### Change C: 停止写入 compile_report.txt

当前行为：

```text
examples/usage.py writes result.readable_report to compile_report.txt
```

MVP 行为：

```text
examples/usage.py only writes feedback_report.md
```

过渡期内 pipeline 可以保留 `readable_report` 字段，但 example output 不再把 `compile_report.txt` 当作受支持产物生成。

#### Change D: feedback_report.md 成为唯一人工报告

`feedback_report.md` 继续由以下输入生成：

```text
result.spl_text
result.completeness
result.compile_diagnostics
result.assumptions
result.traces
result.adapter_warnings
result.validation_errors
result.validation_warnings
```

因为 `result.compile_diagnostics` 已被收窄为最终 requirement diagnostics，feedback renderer 不需要知道内部 diagnostic kind。

#### Change E: 保留内部 observability

不得删除：

```text
FieldRouteIR.route_diagnostics
FieldRouteIR.structured_route_diagnostics
stage2_field_router.json result.routes.route_diagnostics
stage2_field_router.json result.routes.structured_route_diagnostics
stage2_field_router.json result.llm_refinement
```

这些是 MVP 阶段 Stage 2 的 debug/audit surface。

### 16.4 Planned Test Changes

删除或改写“Stage 2 route diagnostics become final CompileDiagnostic”的测试。

新增以下 invariants：

1. `route_refinement_corrected` 仍保留在 `intermediate_results["stage2_routes"]`。
2. `route_refinement_corrected` 不出现在 `PipelineResult.compile_diagnostics`。
3. `route_refinement_corrected` 不出现在 `feedback_report.md`。
4. `missing_handler` 等最终 requirement diagnostics 仍出现在 `PipelineResult.compile_diagnostics`。
5. completeness 仍基于最终 requirement diagnostics。
6. `examples/usage.py` 不写 `compile_report.txt`。
7. Stage checkpoint JSON 仍包含 route refinement diagnostics 供调试。

### 16.5 MVP 验收标准

MVP 完成时必须满足：

1. `feedback_report.md` 是唯一生成的 human-readable report artifact。
2. `compile_report.txt` 不再由 `examples/usage.py` 生成。
3. `feedback_report.md` 只包含最终用户可行动 requirement diagnostics。
4. `route_refinement_*` diagnostics 不出现在 `feedback_report.md`。
5. `route_refinement_*` diagnostics 仍保留在 Stage 2 checkpoint JSON。
6. completeness 和 assumptions 不消费内部 route refinement diagnostics。
7. IRS/Post-normalize、Gate、ProducerIndex、provenance、delegation 产生的最终用户可行动 diagnostics 仍能进入 feedback。

### 16.6 Post-MVP 延后项

以下内容明确延后：

1. 恢复 `compile_report.txt`。
2. 引入 `DiagnosticEnvelope`。
3. 引入 `DiagnosticRouter`。
4. 引入 `CompileReportModel`。
5. 在 human-readable report 中渲染内部 compiler diagnostics。

这些内容必须作为一组完整架构改造实现，不能零散打补丁，否则会重新制造当前的 diagnostic 边界问题。

## 17. Long-Term Migration Plan

### Phase 1: Classification Metadata

1. 扩展 `DiagnosticSpec`，加入 audience / domain / channel metadata。
2. 添加 helper functions，用于分类现有 `CompileDiagnostic` kinds。
3. 将 route refinement kinds 注册为 developer-facing、checkpoint/compile-report-only。
4. 增加 unknown kind 默认策略测试。

### Phase 2: Diagnostic Router

1. 添加 `DiagnosticEnvelope`。
2. 添加 `DiagnosticRouter`。
3. 将现有 final diagnostics 转换成 routed views。
4. 保留 `compile_diagnostics` 作为兼容属性。
5. route refinement diagnostics 进入 `compiler_diagnostics`。

### Phase 3: Report Models

1. 添加 `CompileReportModel` 和 `FeedbackReportModel`。
2. 修改 report renderers，使其消费 report models。
3. 将 report-specific selection 从 renderer 移到 router/model builder。
4. 在 orchestrator 或专门的 report builder 中生成 `result.compile_report` 和 `result.feedback_report`。

### Phase 4: Producer Migration

1. Stage 2 将 route refinement events 作为 `CompilerDiagnostic` 或 `TelemetryEvent` 输出，而不是 `CompileDiagnostic`。
2. IRS/projectors 只为 construct-level user gaps 输出 `RequirementDiagnostic`。
3. stage-local IRS diagnostics 保持 provisional，除非被 policy 提升。
4. Gate 和 ProducerIndex 继续负责 renderability 和 producer diagnostics。

### Phase 5: Compatibility Cleanup

1. 废弃内部 events 直接构造 broad `CompileDiagnostic` 的用法。
2. 更新 legacy `compile_diagnostics` 文档，明确它表示 user-facing requirement diagnostics。
3. 更新 examples 和 docs。
4. 删除或改写“所有 stage diagnostics 都会成为 compile diagnostics”的测试。

## 18. Long-Term Required Tests

### 18.1 Router Tests

1. `route_refinement_corrected` 只进入 compile report 和 checkpoint。
2. `missing_handler` 进入 feedback report 和 compile report。
3. unknown diagnostic kind 默认只进入 compile report / checkpoint。
4. internal diagnostics 不影响 completeness。
5. internal diagnostics 不产生 assumptions。

### 18.2 Report Model Tests

1. `FeedbackReportModel` 只包含 `audience="user"` 的 diagnostics。
2. `CompileReportModel` 同时包含 requirement diagnostics 和 compiler diagnostics。
3. suppressed/provisional diagnostics 只在配置允许的 compile report section 出现。

### 18.3 Renderer Invariant Tests

1. feedback renderer 不接收 raw stage diagnostics。
2. feedback renderer output 永不包含 `route_refinement_`。
3. compile renderer output 可以包含 `route_refinement_corrected`。
4. renderer tests 使用 report models，而不是 raw `PipelineResult`。

### 18.4 Pipeline Regression Tests

1. `examples/output/demo/feedback_report.md` 不包含 `route_refinement_corrected`。
2. post-MVP 架构下，`examples/output/demo/compile_report.txt` 在 internal diagnostics section 中包含 route refinement diagnostics。
3. MVP 中，`examples/usage.py` 不生成 `compile_report.txt`。
4. `PipelineResult.compile_diagnostics` 只包含 requirement diagnostics。
5. post-MVP 架构下，`PipelineResult.compiler_diagnostics` 包含 Stage 2 route refinement diagnostics。

## 19. Long-Term Acceptance Criteria

长期架构完成时必须满足：

1. 内部 Stage 2 route refinement events 在 `compile_report.txt` 中可见。
2. 内部 Stage 2 route refinement events 不出现在 `feedback_report.md`。
3. completeness 只基于 validation errors 和最终用户可行动 requirement diagnostics。
4. assumptions 只基于最终用户可行动 requirement diagnostics 生成。
5. IRS authority boundaries 保持不变。
6. unknown diagnostic kinds 默认不能泄漏到 feedback。
7. renderers 消费 report models，不自行分类 diagnostics。

## 20. Open Questions

1. post-MVP 中，route refinement corrections 应在 compile report 中 verbatim 展示，还是按 kind/span 汇总？
2. compiler 已成功 repair 的 `CompilerDiagnostic` 默认 severity 是否应为 `info`，而不是 `warning`？
3. post-MVP 中，`compile_report.txt` 是否默认包含 suppressed stage-local IRS diagnostics，还是只在 debug mode 中包含？
4. `PipelineResult.compile_diagnostics` 应继续作为 requirement diagnostics 的兼容 alias，还是在 breaking release 中重命名？

## 21. 总结

diagnostics 架构必须从 flat list 升级为 audience-aware diagnostic system。

长期关键变化：

```text
raw diagnostic facts
  -> DiagnosticRouter
  -> report-specific models
  -> renderers
```

MVP 阶段只生成 `feedback_report.md` 作为 human-readable report。内部 diagnostics 保留在结构化 checkpoints 中。

post-MVP 阶段可以恢复 `compile_report.txt` 作为 engineering report，其中可以包含内部 compiler diagnostics。`feedback_report.md` 始终是用户层面报告，只能包含最终用户可行动 requirement diagnostics。

这样可以阻止 `route_refinement_corrected` 等实现细节泄漏到用户反馈，同时通过 checkpoint 保留调试与审计能力；未来完整架构落地后，再通过 routed compile report 提供更友好的工程可观测性。
