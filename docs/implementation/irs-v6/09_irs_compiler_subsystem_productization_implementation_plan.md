# IRS Compiler Subsystem 产品化多阶段实施计划

## 1. 文档定位

本文档是 `08_irs_compiler_subsystem_productization_design.md` 的工程实施计划。

目标不是继续做零散 checker 修补，而是把 IRS 产品化为一个稳定的 compiler subsystem：

```text
IRSSubsystem
  -> stage-local construct satisfaction
  -> post-normalize final construct diagnostics
  -> diagnostic consolidation
  -> feedback visibility
  -> graph-ready future recursion interface
```

本计划拆分为 R10-R14 五个阶段。每个阶段都必须可独立审核、可回归、可回滚。

## 2. 总体原则

### 2.1 必须遵守

1. IRS = Information Requirements Specification，不是生成器。
2. IRS checker 不调用 LLM。
3. IRS checker 不解析 raw NL，不用关键词规则做语义推断。
4. IRS checker 不修改输入 IR。
5. IRS checker 不生成 SPL construct，不补全缺失 slot。
6. Checker 输出 `ConstructSatisfactionReport`；diagnostic 由 projector / consolidator 统一处理。
7. Stage-local IRS 是 early satisfaction report，不抢 Post-normalize final authority。
8. Post-normalize IRS 是 construct-level final authority。
9. Gate 是 executable renderability authority。
10. ProducerIndex 是 required output producer authority。
11. Feedback report 只渲染已有 report / diagnostic / trace，不重新做 IRS 判断。
12. 新增配置必须表达产品策略，不恢复迁移期散乱 flags。

### 2.2 LLM / Rule-based 决策约束

本计划默认不新增 LLM 调用，也不新增 raw NL rule-based fallback。

如果实施中出现以下情况，必须先提交设计说明让我确认：

1. 需要根据自然语言文本判断语义。
2. 需要在 checker 中加入关键词判断。
3. 需要在 LLM 失败时增加 fallback。
4. 需要把 ambiguous construct 自动降级为 generic command。
5. 需要根据缺失 slot 生成新 construct。

默认选择：

```text
需要语义理解 -> 由上游 LLM / adapter / route annotation 提供结构化 evidence。
IRS checker -> 只消费结构化 evidence。
失败路径 -> 显式 diagnostic 或 fail-fast，不静默 fallback。
```

## 3. 目标架构验收总线

最终状态必须满足：

```text
Stage 3.5 WorkerBoundaryPlanner
  -> IRSSubsystem.run_stage_local("stage3_5")
  -> construct_satisfaction["stage3_5"]

Stage 4 FlowAssembler
  -> IRSSubsystem.run_stage_local("stage4")
  -> construct_satisfaction["stage4"]

Stage 7 StepExtractor
  -> IRSSubsystem.run_stage_local("stage7")
  -> construct_satisfaction["stage7"]

Stage 10 Worker Assembly
  -> IRSSubsystem.run_post_normalize()
  -> final construct-level diagnostics

ExecutableElementGate
  -> renderability diagnostics

DiagnosticConsolidator
  -> final compile_diagnostics

FeedbackReportRenderer
  -> diagnostics + construct satisfaction + provenance
```

## 4. R10: IRS Runtime Subsystem Foundation

### 4.1 目标

建立 IRS 产品化 runtime 基础设施，但不接入 orchestrator，不改变 pipeline 行为。

R10 只解决组件边界：

- `IRSSubsystem`
- `IRSRuntimeConfig` / `IRSPolicy`
- `IRSResultStore`
- factory construction
- deterministic payload

### 4.2 可修改文件 / 目录

允许修改：

```text
src/nl2spl/compiler/irs/
tests/unit/compiler/irs/
docs/implementation/irs-v6/phase-implementation-plans/
```

允许新增：

```text
src/nl2spl/compiler/irs/subsystem.py
src/nl2spl/compiler/irs/policy.py
src/nl2spl/compiler/irs/result_store.py
tests/unit/compiler/irs/test_r10_irs_subsystem_foundation.py
```

如需导出类型，可修改：

```text
src/nl2spl/compiler/irs/__init__.py
src/nl2spl/compiler/irs/factory.py
```

### 4.3 禁止改动

R10 禁止修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/config.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/pipeline/stages/
src/nl2spl/compiler/report_renderer.py
src/nl2spl/compiler/feedback_report_renderer.py
prompts/
examples/
output/
```

### 4.4 实施方案

#### R10.1 新增 `IRSRuntimeConfig` / `IRSPolicy`

建议字段：

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

注意：

- `enabled=False` 表示整个 IRS subsystem 禁用。
- 不在 R10 接入 `PipelineConfig`。
- 不恢复旧 flags。

#### R10.2 新增 `IRSResultStore`

职责：

- 保存 stage-local reports / diagnostics / warnings / graph snapshot。
- 保存 post-normalize diagnostics。
- 提供 deterministic `to_intermediate_payload()`。
- 复制输入 list，避免共享可变对象。

建议类型：

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
```

#### R10.3 新增 `IRSSubsystem`

职责：

- 组合 `IRSRunner`、`IRSCheckerRegistry`、`DiagnosticProjector`。
- 暴露 `run_stage_local()`。
- 暴露 `run_post_normalize()` 的接口骨架。
- 不接 orchestrator。

R10 的 `run_post_normalize()` 可以先委托现有 `PostNormalizeIRSChecker`，但必须通过接口封装，不能把 checker 逻辑复制进 subsystem。

### 4.5 测试计划

新增测试文件：

```text
tests/unit/compiler/irs/test_r10_irs_subsystem_foundation.py
```

必须覆盖：

1. `IRSRuntimeConfig` 默认值符合产品化设计。
2. `IRSResultStore` 能保存多个 stage result。
3. `IRSResultStore.to_intermediate_payload()` deterministic。
4. `IRSResultStore` 不共享 mutable list。
5. `IRSSubsystem.run_stage_local()` 调用 runner。
6. 空 checker registry 返回空 result。
7. `IRSSubsystem.run_post_normalize()` 通过 wrapper 调用，不直接复制逻辑。
8. No LLM import / no LLM call。
9. No orchestrator import。

### 4.6 验收标准

R10 通过条件：

1. 新增 subsystem 基础设施。
2. 不改变 pipeline runtime 行为。
3. 不修改 orchestrator。
4. 不修改 config。
5. 不新增 raw NL rules。
6. 不新增 fallback。
7. 全量 IRS 单测通过。
8. 全量单元测试通过。

### 4.7 PM 审核清单

审核时我会检查：

1. 是否有 orchestrator diff。
2. 是否有 config diff。
3. `IRSSubsystem` 是否只做调度，不做语义判断。
4. `IRSResultStore` 是否 deterministic。
5. 是否存在共享 mutable list。
6. 是否出现 LLM/client/prompt import。
7. 是否出现 raw text keyword 判断。
8. 测试是否真实调用 subsystem，而不是只测 dataclass。

## 5. R11: Stage-local IRS Runtime Integration

### 5.1 目标

把 Stage 3.5 / Stage 4 / Stage 7 的 IRS stage-local runtime 接入 orchestrator。

R11 只负责让 reports 可观察，不改变最终 SPL 生成结果。

### 5.2 可修改文件 / 目录

允许修改：

```text
src/nl2spl/config.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/irs/
tests/unit/compiler/irs/
tests/unit/pipeline/
```

允许新增：

```text
tests/unit/compiler/irs/test_r11_stage_local_runtime_integration.py
```

### 5.3 禁止改动

R11 禁止修改：

```text
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/report_renderer.py
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/pipeline/stages/stage2_field_router.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/
src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py
src/nl2spl/pipeline/stages/stage7_step_extractor/
prompts/
examples/
output/
```

除非发现接入无法完成，否则不要改 stage 内部逻辑。

### 5.4 实施方案

#### R11.1 `PipelineConfig` 新增单一 IRS 配置

建议只新增：

```python
irs: IRSRuntimeConfig = field(default_factory=IRSRuntimeConfig)
```

不恢复旧 flags：

```text
enable_irs_v6_runner
enable_irs_worker_delegation_check
enable_irs_stage4_exception_flow_check
enable_irs_stage7_step_check
enable_irs_diagnostic_consolidation
```

#### R11.2 Orchestrator 初始化 IRS subsystem

建议在 `PipelineOrchestrator.__init__` 或 `run()` 开始处：

```python
irs = build_irs_subsystem(config.irs)
irs_store = IRSResultStore()
```

如果 `config.irs.enabled=False`，subsystem 返回 no-op result。

#### R11.3 Stage 3.5 接入

触发点：

```text
WorkerPlanValidator 通过之后
behavior ownership defensive repair 之前或之后需要明确
```

建议：

1. WorkerPlanValidator 通过。
2. Defensive repair 完成。
3. 运行 Stage 3.5 IRS。

原因：IRS 应检查实际进入后续 pipeline 的 worker_plan。

写入：

```python
irs_store.put_stage_result(result)
intermediate["construct_satisfaction"]["stage3_5"] = result.reports
intermediate["stage_local_diagnostics"]["stage3_5"] = result.diagnostics
```

#### R11.4 Stage 4 接入

触发点：

```text
FlowAssembler 完成后
Stage 5 之前
```

Context 必须兼容 worker-aware path：

```python
IRSCheckContext(
    stage_name="stage4",
    worker_flows=worker_flow_plan,
    routes=resolved_routes,
    spans=tuple(resolved_spans),
)
```

#### R11.5 Stage 7 接入

触发点：

```text
StepExtractor 完成后
Stage 8 之前
```

Context 必须兼容 worker-aware path：

```python
IRSCheckContext(
    stage_name="stage7",
    worker_steps=worker_step_plan,
    routes=resolved_routes,
    spans=tuple(resolved_spans),
    symbol_table=symbol_table,
)
```

#### R11.6 Final diagnostics 暂不合并 stage-local IRS

R11 默认：

```python
include_stage_local_diagnostics_in_compile = False
```

所以 `stage_local_diagnostics` 写入 intermediate，但不进入 `compile_diagnostics`。

### 5.5 测试计划

新增测试：

```text
tests/unit/compiler/irs/test_r11_stage_local_runtime_integration.py
```

必须覆盖：

1. `config.irs.enabled=False` 时不产生 `construct_satisfaction`。
2. `config.irs.stage_local_enabled=True` 时产生 stage3_5 reports。
3. 产生 stage4 reports。
4. 产生 stage7 reports。
5. Stage-local IRS 不修改 `WorkerPlanIR`。
6. Stage-local IRS 不修改 `WorkerFlowPlanIR`。
7. Stage-local IRS 不修改 `WorkerStepPlanIR`。
8. Stage-local diagnostics 默认不进入 `compile_diagnostics`。
9. Existing SPL output 不因 stage-local IRS 改变。
10. WorkerPlanValidator 失败时不运行 IRS。

### 5.6 验收标准

R11 通过条件：

1. Stage 3.5 / 4 / 7 stage-local IRS 在生产路径触发。
2. Reports 写入 `construct_satisfaction`。
3. Diagnostics 写入 `stage_local_diagnostics`。
4. 默认不并入 final `compile_diagnostics`。
5. SPL 输出稳定。
6. No LLM。
7. No raw NL rule。
8. No fallback。

### 5.7 PM 审核清单

审核时我会检查：

1. Orchestrator 是否只调用 `IRSSubsystem`，不直接 import concrete checker。
2. 是否恢复了旧 flags。
3. stage-local diagnostics 是否误进 final diagnostics。
4. 是否存在重复 diagnostics。
5. stage-local IRS 是否修改 IR。
6. tests 是否真实跑 `PipelineOrchestrator.run()`。
7. 是否只靠 mock 断言，没有验证 intermediate。

## 6. R12: Diagnostic Consolidation Productization

### 6.1 目标

新增产品化 `DiagnosticConsolidator`，统一 final diagnostics 汇总、去重、authority 优先级。

### 6.2 可修改文件 / 目录

允许新增：

```text
src/nl2spl/compiler/diagnostic_consolidator.py
tests/unit/test_diagnostic_consolidator.py
tests/unit/compiler/irs/test_r12_diagnostic_consolidation_productization.py
```

允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/irs/result_store.py
src/nl2spl/compiler/irs/subsystem.py
```

### 6.3 禁止改动

R12 禁止修改：

```text
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py
src/nl2spl/compiler/feedback_report_renderer.py
prompts/
examples/
```

### 6.4 实施方案

#### R12.1 新增 `DiagnosticConsolidator`

输入：

```python
DiagnosticConsolidationInput(
    stage2_diagnostics,
    stage7_diagnostics,
    irs_store,
    post_normalize_diagnostics,
    gate_diagnostics,
    provenance_diagnostics,
    delegation_diagnostics,
    conflict_diagnostics,
)
```

输出：

```python
DiagnosticConsolidationResult(
    final_diagnostics,
    suppressed_stage_local_diagnostics,
    warnings,
)
```

#### R12.2 Dedup key

必须使用：

```python
(
    diagnostic.kind,
    diagnostic.target_ref,
    missing_slot_name,
    tuple(sorted(diagnostic.source_span_ids)),
)
```

不能只用 kind / target_ref，避免不同 missing slot 被误合并。

#### R12.3 Authority 优先级

默认优先级：

```text
post-normalize IRS > Gate > Producer/Provenance > route/delegation/conflict > stage-local IRS
```

Stage-local duplicate 默认 suppressed。

### 6.5 测试计划

必须覆盖：

1. 同 key stage-local diagnostic 被 post-normalize suppress。
2. 不同 missing_slot 不误合并。
3. Gate diagnostic 保留。
4. Provenance diagnostic 保留。
5. Stage-local 独有 diagnostic 在 policy 允许时可进入 final diagnostics。
6. Stage-local 独有 diagnostic 默认不进入 final diagnostics。
7. Suppressed diagnostics 可在 result 中查看。
8. Diagnostic order deterministic。
9. Consolidator 不修改输入 diagnostic 对象。

### 6.6 验收标准

R12 通过条件：

1. Orchestrator 使用 `DiagnosticConsolidator` 汇总 diagnostics。
2. Final `compile_diagnostics` 无重复 missing slot。
3. Post-normalize 仍是 final construct-level authority。
4. Gate diagnostics 不被 IRS 覆盖。
5. Suppressed diagnostics 可观察。
6. 全量测试通过。

### 6.7 PM 审核清单

审核时我会检查：

1. Dedup key 是否包含 missing_slot。
2. 是否有 weak assertion，例如只断言 `len > 0`。
3. 是否把 stage-local diagnostics 默认并入 final diagnostics。
4. 是否误删 gate/provenance/delegation diagnostics。
5. 是否出现 fallback 合并逻辑掩盖错误。

## 7. R13: Feedback Report Productization

### 7.1 目标

让 feedback report 展示 construct satisfaction，而不是只展示 final diagnostics。

### 7.2 可修改文件 / 目录

允许新增：

```text
src/nl2spl/compiler/irs/feedback_projector.py
tests/unit/compiler/irs/test_r13_construct_satisfaction_feedback.py
```

允许修改：

```text
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/compiler/report_renderer.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/main.py
src/nl2spl/main.py
```

具体修改入口以当前生成 feedback report 的真实代码为准。

### 7.3 禁止改动

R13 禁止修改：

```text
src/nl2spl/compiler/irs/checkers/
src/nl2spl/pipeline/stages/
src/nl2spl/pipeline/executable_gate.py
prompts/
```

### 7.4 实施方案

#### R13.1 新增 `ConstructSatisfactionFeedbackProjector`

输入：

```python
IRSResultStore 或 intermediate["construct_satisfaction"]
```

输出：

```python
list[str] 或 structured markdown section model
```

职责：

- 展示 stage-local reports。
- 展示 construct type、construct id、completeness、frontier、cutline。
- 展示 missing slots。
- 展示 source spans。
- 展示 graph edges summary。

不允许：

- 生成 diagnostic。
- 重新计算 slot satisfaction。
- 根据 text 推断语义。

#### R13.2 Feedback report 新增 section

建议新增：

```text
## Construct Satisfaction

### Stage 3.5 Worker / Delegation
...

### Stage 4 Exception Flows
...

### Stage 7 Steps
...
```

#### R13.3 Issue 3 展示

Worker delegation candidate 场景必须能显示：

```text
WORKER_CANDIDATE: complete
WORKER_PROMOTION: blocked
Missing:
  - promotion_input_contract
  - promotion_output_contract
  - promotion_invocation_point
  - promotion_result_handoff
```

同时必须避免误导：

```text
candidate complete != child worker ready
promotion blocked != compiler failed
```

### 7.5 测试计划

必须覆盖：

1. Feedback report 出现 Construct Satisfaction section。
2. Stage 3.5 worker promotion blocked 显示四个 missing slots。
3. Candidate complete 和 promotion blocked 分开展示。
4. Stage 4 exception flow partial 显示。
5. Stage 7 step blocked / partial 显示。
6. 没有 construct satisfaction 时 report 正常渲染。
7. Feedback projector 不修改 reports。
8. Feedback projector 不产生 diagnostics。

### 7.6 验收标准

R13 通过条件：

1. Feedback report 能展示 stage-local IRS reports。
2. Final diagnostics section 仍来自 `compile_diagnostics`。
3. Construct satisfaction section 不改变 completeness。
4. Report 不做新判断。
5. Internal-Comms / Issue 3 场景解释清晰。

### 7.7 PM 审核清单

审核时我会检查：

1. feedback renderer 是否出现新语义判断。
2. 是否根据字符串关键词判定 missing slot。
3. 是否把 report-only candidate 写成 materialized worker。
4. 是否把 stage-local report 当 final diagnostic。
5. 是否缺少 source span / construct path。

## 8. R14: Cleanup, Audit, and Documentation Alignment

### 8.1 目标

清理产品化后遗留的文档漂移、旧 wrapper 误导、旧 flag 说明，并进行最终审计。

### 8.2 可修改文件 / 目录

允许修改：

```text
docs/implementation/irs-v6/
docs/Todo/
.codex/skills/irs-knowledge/
.agents/skills/irs-knowledge/
tests/unit/compiler/irs/
```

可根据审计结果修改：

```text
src/nl2spl/compiler/irs/
src/nl2spl/compiler/diagnostic_consolidator.py
src/nl2spl/pipeline/orchestrator.py
```

### 8.3 禁止改动

R14 禁止新增功能。

禁止修改：

```text
prompts/
examples/output/
```

除非只是更新审计用例引用，不得改变 pipeline 行为。

### 8.4 实施方案

#### R14.1 文档审计

检查：

- `01-09` 文档是否一致。
- 是否仍描述不存在的 flags。
- 是否仍说 stage-local IRS 没接入。
- 是否仍把 DiagnosticAnalyzer 当 production authority。

#### R14.2 代码审计

必须用 `rg` 检查：

```text
enable_irs_v6_runner
enable_irs_worker_delegation_check
enable_irs_stage4_exception_flow_check
enable_irs_stage7_step_check
enable_irs_diagnostic_consolidation
DiagnosticAnalyzer
construct_satisfaction
stage_local_diagnostics
IRSSubsystem
DiagnosticConsolidator
```

#### R14.3 Skill 更新

更新：

```text
.codex/skills/irs-knowledge/
.agents/skills/irs-knowledge/
```

内容必须包含：

- IRSSubsystem runtime entry。
- Stage-local vs Post-normalize。
- DiagnosticConsolidator。
- Feedback construct satisfaction section。
- 禁止 checker 直接 diagnostic / raw NL rules。

### 8.5 测试计划

新增：

```text
tests/unit/compiler/irs/test_r14_productization_final_audit.py
```

必须覆盖：

1. Orchestrator 不 import concrete checker。
2. Renderer 不 import IRS runner / checker。
3. Gate 不 import IRS runner / checker。
4. ProducerIndex 不 import IRS runner / checker。
5. Config 不包含旧 migration flags。
6. IRS skill 不含错误定义。
7. R10-R13 测试矩阵都有覆盖。
8. No pytest skip / xfail in IRS productization tests。

### 8.6 验收标准

R14 通过条件：

1. 文档与代码一致。
2. Skill 与代码一致。
3. 旧 flags 不再作为产品配置出现。
4. Final audit tests 通过。
5. 全量单元测试通过。

### 8.7 PM 审核清单

审核时我会检查：

1. 是否只改文档却没有审计测试。
2. 是否删除历史说明导致上下文丢失。
3. 是否把未实现内容写成已实现。
4. 是否遗漏 `.codex` / `.agents` 双 skill 同步。
5. 是否有 skip / xfail 掩盖失败。

## 9. 跨阶段测试命令建议

每阶段至少运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs -q
```

涉及 orchestrator 后必须运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs tests/unit/test_irs_v6_r0_baseline.py tests/unit/test_irs_v6_r1_report_schema.py -q
```

R11-R14 必须补充 orchestrator / report 相关测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs tests/unit/pipeline tests/unit/test_diagnostic_consolidation.py tests/unit/test_executable_gate.py -q
```

最终阶段必须运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/ -q
```

如果出现环境相关失败，必须明确列出失败文件、失败原因、是否与本阶段相关。不能只写“环境问题”。

## 10. PM 审核总清单

每次你提交阶段实现时，我会按以下顺序审核：

1. `git diff --stat` 确认改动范围。
2. 逐文件检查是否改了禁止目录。
3. 检查是否新增 LLM 调用。
4. 检查是否新增 raw NL keyword rule。
5. 检查是否新增 fallback 掩盖错误。
6. 检查 checker 是否消费 `ConstructIRS` / `SlotSpec`。
7. 检查 checker 是否直接生成 `CompileDiagnostic`。
8. 检查是否修改输入 IR。
9. 检查 diagnostics 是否由 projector / consolidator 处理。
10. 检查 stage-local reports 是否进入 `construct_satisfaction`。
11. 检查 final diagnostics 是否去重且 authority 正确。
12. 检查 feedback report 是否只渲染，不判断。
13. 检查 tests 是否真实调用代码路径。
14. 检查是否存在空断言、弱断言、skip、xfail。
15. 运行针对性测试。
16. 必要时运行全量测试。

## 11. 阶段提交格式要求

每个阶段提交审核时，必须提供：

```text
1. 修改文件列表
2. 每个文件的作用
3. 是否触碰禁止目录
4. LLM / rule-based 决策说明
5. 测试命令与结果
6. 新增/修改测试列表
7. intermediate / report 输出样例
8. 已知风险
9. 是否需要我确认的设计选择
```

如果某阶段存在你认为可以 rule-based 或 LLM 两种方案的步骤，提交前必须先问，不要实现后再解释。

## 12. 总体验收标准

R10-R14 全部完成后，必须达到：

1. IRS 有唯一 runtime subsystem 入口。
2. Stage 3.5 / 4 / 7 stage-local IRS 按设计触发。
3. Post-normalize IRS 仍是 final construct-level authority。
4. Gate 仍是 executable renderability authority。
5. ProducerIndex 仍是 required output producer authority。
6. Feedback report 展示 construct satisfaction。
7. Feedback report 不重新做 IRS 判断。
8. Stage-local diagnostics 与 final diagnostics 不重复误导。
9. 新增 checker 不需要改 renderer / gate / ProducerIndex。
10. 所有 IRS result 都可追踪 stage、construct、slot、source span。
11. Future recursive IRS 所需 graph/frontier/cutline 接口保留。
12. 全量单元测试通过。

