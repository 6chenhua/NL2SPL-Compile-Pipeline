# R5 Runner Orchestrator Integration 实施计划

## 1. 阶段定位

R5 的目标是把 R2/R3/R4 已经完成的 IRS v6 runner 链路接入主 pipeline，但只接入 Worker/Delegation IRS，不迁移 Stage 4、Stage 7、Post-normalize checker。

R5 要达成的效果是：

```text
Stage 3.5 WorkerBoundaryPlanner
-> Stage 3.6 WorkerPlanValidator
-> IRSRunner.run_stage("stage3_5", IRSCheckContext(worker_plan=...))
-> intermediate["construct_satisfaction"]["stage3_5"]
-> intermediate["stage_local_diagnostics"]["stage3_5"]
-> compile_diagnostics / readable_report 中可见 worker promotion blocked 原因
```

R5 不改变 worker planning、不改变 flow/block/step generation、不改变 final SPL rendering。它只把 R4 checker 的分析结果接入 pipeline diagnostics/report。

## 2. 前置状态

R5 依赖以下已完成内容：

```text
R1:
    ConstructSatisfactionReport 已有 construct_path / related_edges / frontier_status / cutline_reason。

R2:
    IRSCheckContext / ConstructInstance / IRSCheckerRegistry / IRSRunner 已存在。

R3:
    DiagnosticProjector 可把 SlotSatisfaction.diagnostic_kind 投影为 CompileDiagnostic。

R4:
    WorkerDelegationIRSChecker 已能从 WorkerPlanIR 产生：
        WORKER_CANDIDATE
        WORKER_PROMOTION
        CHILD_WORKER
        WORKER_HANDOFF
    并可通过 runner/projector 生成 type_or_contract_ambiguity。
```

R5 只做接入，不重写这些组件。

## 3. 设计边界

### 3.1 允许做的事情

```text
1. 在 PipelineConfig 增加 IRS v6 runner 相关 feature flags。
2. 新增 IRS runner factory / default registry factory。
3. 在 orchestrator Stage 3.6 WorkerPlanValidator 通过后运行 IRSRunner。
4. 将 Stage 3.5 v6 reports 写入 intermediate["construct_satisfaction"]["stage3_5"]。
5. 将 Stage 3.5 v6 diagnostics 写入 intermediate["stage_local_diagnostics"]["stage3_5"]。
6. 在 flag 开启时，把 Stage 3.5 v6 diagnostics 纳入 compile_diagnostics / readable_report。
7. 增加 orchestrator 级集成测试。
8. 增加默认关闭时的 no-op / output unchanged 测试。
```

### 3.2 禁止做的事情

```text
1. 禁止修改 WorkerBoundaryPlanner 的决策逻辑。
2. 禁止修改 WorkerPlanValidator 的校验规则。
3. 禁止修改 Stage 4 / Stage 5 / Stage 7 / Stage 9.5 / Gate 行为。
4. 禁止生成 child worker、handoff、INVOKE_WORKER。
5. 禁止让 checker 修改 WorkerPlanIR。
6. 禁止在 orchestrator 中直接 import WorkerDelegationIRSChecker 具体类。
7. 禁止引入 LLM 调用。
8. 禁止新增 raw NL rule-based 语义推断。
9. 禁止修改 prompts/examples/output。
10. 禁止让 flags 默认开启。
```

### 3.3 LLM / rule-based 决策约束

R5 是 wiring 阶段，不涉及语义判断：

```text
IRSRunner:
    消费 WorkerPlanIR。

WorkerDelegationIRSChecker:
    已在 R4 只消费结构化 IR 字段。

Orchestrator:
    只负责调度 runner、保存 reports/diagnostics、合并 diagnostics。
```

如果实施中需要解释自然语言或补充 worker promotion 语义，必须停止并回退到 R4 checker 设计讨论，不能在 R5 中加入规则。

## 4. 可修改文件范围

### 4.1 生产代码

```text
src/nl2spl/config.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/irs/factory.py
src/nl2spl/compiler/irs/__init__.py
```

说明：

```text
config.py:
    增加 R5 feature flags。

orchestrator.py:
    只允许新增 runner 调度 helper 和 Stage 3.5 后接入点。
    不允许直接 import concrete checker。

compiler/irs/factory.py:
    新增默认 runner/registry factory。
    这里可以 import WorkerDelegationIRSChecker。

compiler/irs/__init__.py:
    如需导出 factory，保持 lazy import 策略，避免 R2 解决过的循环导入问题复发。
```

### 4.2 测试代码

```text
tests/unit/compiler/irs/test_r5_runner_factory.py
tests/unit/test_pipeline_orchestrator.py
tests/unit/test_irs_v6_r0_baseline.py
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
```

实际测试文件可按项目现有组织调整，但必须覆盖本计划第 9 节的验收场景。

### 4.3 禁止修改文件

```text
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/**
src/nl2spl/pipeline/stages/stage4_flow_assembler/**
src/nl2spl/pipeline/stages/stage7_step_extractor/**
src/nl2spl/pipeline/stages/stage9_5_normalizer/**
src/nl2spl/pipeline/executable_gate.py
prompts/**
examples/**
output/**
```

## 5. Feature Flags 设计

在 `PipelineConfig` 新增：

```python
enable_irs_v6_runner: bool = False
enable_irs_worker_delegation_check: bool = False
```

语义：

```text
enable_irs_v6_runner:
    IRS v6 runner 总开关。

enable_irs_worker_delegation_check:
    Worker/Delegation checker 专项开关。
```

R5 接入条件必须同时满足：

```text
enable_worker_boundary_planner is True
enable_irs_v6_runner is True
enable_irs_worker_delegation_check is True
worker_plan is not None
WorkerPlanValidator validation passed
```

默认值必须都是 `False`，保证现有 pipeline 默认输出不变。

## 6. Factory 设计

新增文件：

```text
src/nl2spl/compiler/irs/factory.py
```

建议 API：

```python
def build_irs_checker_registry(
    *,
    enable_worker_delegation: bool = False,
) -> IRSCheckerRegistry:
    ...

def build_irs_runner(
    *,
    enable_worker_delegation: bool = False,
) -> IRSRunner:
    ...
```

职责：

```text
1. 创建 IRSCheckerRegistry。
2. 根据 flags 注册 WorkerDelegationIRSChecker。
3. 创建 SPLConstructRegistry.default()。
4. 创建 DiagnosticProjector。
5. 返回 IRSRunner。
```

边界：

```text
orchestrator 只 import build_irs_runner。
orchestrator 不 import WorkerDelegationIRSChecker。
```

测试必须验证：

```text
enable_worker_delegation=False:
    registry 不注册 worker_delegation checker。

enable_worker_delegation=True:
    runner 可对 stage3_5 context 产出 R4 reports/diagnostics。
```

## 7. Orchestrator 接入点

当前真实代码位置：

```text
src/nl2spl/pipeline/orchestrator.py

Stage 3.5:
    worker_plan = self._run_stage3_5(...)

Stage 3.6:
    worker_validation = WorkerPlanValidator().validate(...)
    if not worker_validation.is_valid:
        raise ValueError(...)

intermediate:
    intermediate["stage3_5_worker_plan"] = worker_plan
    intermediate["stage3_6_worker_plan_validation"] = worker_validation

Stage 4:
    if worker_plan is not None:
        flow_output = self._run_stage4(..., worker_plan)
```

R5 接入必须放在：

```text
WorkerPlanValidator 通过之后
Stage 4 Flow Assembly 之前
```

建议新增 helper：

```python
def _run_stage3_5_irs_v6(
    self,
    *,
    worker_plan: WorkerPlanIR,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    canonical_input: CanonicalCompileInput | None,
) -> IRSRunResult:
    ...
```

`IRSCheckContext` 至少包含：

```text
stage_name="stage3_5"
spans=tuple(resolved_spans)
routes=resolved_routes
worker_plan=worker_plan
metadata={
    "canonical_input_schema": canonical_input.source_schema if available,
    "planner_enabled": True,
}
```

注意：

```text
R5 不要求 checker 使用 spans/routes/canonical_input。
这些字段用于 future checker/report context。
```

## 8. Intermediate 与 Diagnostics 合并

### 8.1 Intermediate 写入

当 R5 flags 开启时：

```python
intermediate.setdefault("construct_satisfaction", {})
intermediate.setdefault("stage_local_diagnostics", {})
intermediate["construct_satisfaction"]["stage3_5"] = result.reports
intermediate["stage_local_diagnostics"]["stage3_5"] = result.diagnostics
```

如果 result.warnings 非空：

```python
intermediate.setdefault("irs_v6_warnings", {})
intermediate["irs_v6_warnings"]["stage3_5"] = result.warnings
```

### 8.2 compile_diagnostics / readable_report 可见性

当前 orchestrator 只显式纳入：

```text
stage2_diags
stage7_diags
post_norm_diags
conflict_diags
gate_diags
provenance_diags
delegation_diags
```

R5 必须在 flag 开启时纳入 Stage 3.5 v6 diagnostics：

```python
stage3_5_irs_diags = (
    intermediate.get("stage_local_diagnostics", {}).get("stage3_5", [])
    if self.config.enable_irs_v6_runner
    and self.config.enable_irs_worker_delegation_check
    else []
)

all_diagnostics = (
    stage2_diags
    + stage3_5_irs_diags
    + stage7_diags
    + post_norm_diags
    + conflict_diags
    + gate_diags
    + provenance_diags
    + delegation_diags
)
```

原因：

```text
Stage 4/7 IRS diagnostics 在 post-normalize enabled 时保持 report-only，
因为 post-normalize 是 construct-level final authority。

Worker promotion diagnostics 当前没有 post-normalize authority 覆盖，
所以 R5 需要把 stage3_5 v6 diagnostics 纳入 final compile diagnostics。
```

不得开启旧的 `enable_irs_diagnostic_consolidation` 作为替代方案。

## 9. 测试计划

### 9.1 Runner Factory 单测

命令：

```powershell
python -m pytest tests/unit/compiler/irs/test_r5_runner_factory.py -q
```

必须覆盖：

```text
1. factory 默认不注册 worker_delegation checker。
2. enable_worker_delegation=True 时注册 checker。
3. build_irs_runner(enable_worker_delegation=True) 可运行 stage3_5。
4. factory 不需要 LLM client。
5. factory 不修改 WorkerPlanIR。
```

### 9.2 Orchestrator 默认关闭测试

必须覆盖：

```text
enable_worker_boundary_planner=True
enable_irs_v6_runner=False
enable_irs_worker_delegation_check=False
```

验收：

```text
1. 不调用 IRSRunner。
2. intermediate 不新增 construct_satisfaction["stage3_5"]。
3. intermediate 不新增 stage_local_diagnostics["stage3_5"]。
4. final SPL / compile_diagnostics 与 R4 前基线一致。
```

可以通过 mock `_run_stage3_5_irs_v6` 或 runner factory spy 验证不调用。

### 9.3 Orchestrator flag 开启测试

必须覆盖：

```text
enable_worker_boundary_planner=True
enable_irs_v6_runner=True
enable_irs_worker_delegation_check=True
```

构造一个 incomplete delegation worker_plan：

```text
candidate_kind="explicit_delegation"
possible_inputs=[]
possible_outputs=[]
risks=["no_clear_input_contract", "no_clear_output_contract"]
handoffs=[]
```

验收：

```text
1. intermediate["construct_satisfaction"]["stage3_5"] 存在。
2. 包含 WORKER_CANDIDATE report。
3. 包含 WORKER_PROMOTION report。
4. WORKER_PROMOTION metadata["promotion_status"] == "blocked"。
5. intermediate["stage_local_diagnostics"]["stage3_5"] 存在。
6. diagnostics 是 CompileDiagnostic 对象。
7. diagnostics kind 包含 type_or_contract_ambiguity。
8. diagnostics missing_slot.slot_name 指向 promotion_* slot。
```

### 9.4 Compile Report 可见性测试

必须通过 `PipelineOrchestrator.run()` 或足够接近的 orchestrator 级测试验证：

```text
1. result.compile_diagnostics 包含 Stage 3.5 worker promotion diagnostics。
2. result.readable_report 包含 worker promotion blocked / missing slot 相关信息。
3. result.intermediate_results["stage_local_diagnostics"]["stage3_5"] 与 compile_diagnostics 中对应对象一致或语义一致。
```

注意：

```text
不能只测 intermediate。
R5 的用户价值是 readable report 可见。
```

### 9.5 Stage 4/7 不受影响测试

必须覆盖：

```text
1. 开启 R5 flags 不改变 Stage 4 flow output。
2. 开启 R5 flags 不改变 Stage 7 step output。
3. R5 diagnostics 不参与 worker materialization。
```

实现方式：

```text
使用 mock stage outputs 或白盒 orchestrator test。
断言 worker_plan.workers/handoffs 在 IRS runner 前后相同。
```

### 9.6 回归测试命令

R0-R5：

```powershell
python -m pytest `
  tests/unit/test_irs_v6_r0_baseline.py `
  tests/unit/test_irs_v6_r1_report_schema.py `
  tests/unit/compiler/irs/test_r2_framework_skeleton.py `
  tests/unit/compiler/irs/test_r3_diagnostic_projector.py `
  tests/unit/compiler/irs/test_r4_worker_delegation_checker.py `
  tests/unit/compiler/irs/test_r5_runner_factory.py `
  -q
```

全量：

```powershell
python -m pytest tests/unit/ -q --basetemp=.pytest-tmp-r5
```

## 10. 验收标准

R5 通过必须同时满足：

```text
1. PipelineConfig 新增 enable_irs_v6_runner，默认 False。
2. PipelineConfig 新增 enable_irs_worker_delegation_check，默认 False。
3. 默认配置下 pipeline 行为不变。
4. orchestrator 不直接 import WorkerDelegationIRSChecker。
5. runner factory 可按 flag 注册 worker_delegation checker。
6. Stage 3.5 IRS runner 只在 WorkerPlanValidator 通过后运行。
7. Stage 3.5 IRS runner 在 Stage 4 前运行。
8. intermediate["construct_satisfaction"]["stage3_5"] 正确写入 reports。
9. intermediate["stage_local_diagnostics"]["stage3_5"] 正确写入 diagnostics。
10. compile_diagnostics 纳入 Stage 3.5 worker promotion diagnostics。
11. readable_report 可见 worker promotion blocked 原因。
12. R5 不修改 WorkerPlanIR。
13. R5 不生成 child worker / handoff / INVOKE_WORKER。
14. R5 不调用 LLM。
15. R5 不新增 raw NL rule-based 语义判断。
16. Stage 4/7/Post-normalize/Gate 生产行为不变。
17. R0-R5 回归通过。
18. 全量单测通过。
```

## 11. 审核清单

提交审核时必须提供：

```text
1. 修改文件列表。
2. 是否修改禁止范围文件。
3. 新增 flags 默认值。
4. orchestrator import 列表，证明没有直接 import concrete checker。
5. runner factory 的注册逻辑。
6. Stage 3.5 IRS 接入点代码位置。
7. intermediate 写入示例。
8. compile_diagnostics / readable_report 可见性证据。
9. 默认关闭 no-op 测试结果。
10. flag 开启 integration 测试结果。
11. R0-R5 回归结果。
12. 全量单测结果。
13. 是否引入 LLM。
14. 是否引入 raw NL rule-based 判断。
15. WorkerPlanIR 前后不可变验证。
```

我审核时会逐项核验真实代码和测试，不接受只看实施报告。

## 12. 风险与处理

### 风险 1：默认行为漂移

处理：

```text
两个 flags 都默认 False。
默认关闭测试必须证明没有 stage3_5 IRS intermediate。
```

### 风险 2：orchestrator 直接依赖具体 checker

处理：

```text
通过 factory 隔离 concrete checker。
orchestrator 只 import build_irs_runner。
```

### 风险 3：diagnostic 重复或与 post-normalize 混淆

处理：

```text
R5 只纳入 stage3_5 worker promotion diagnostics。
不改变 Stage 4/7 report-only 策略。
不启用旧 consolidation 作为替代。
```

### 风险 4：R5 被误用为 worker materialization 修复

处理：

```text
R5 只报告，不生成。
测试断言 WorkerPlanIR workers/handoffs/decisions 不变。
```

### 风险 5：compile report 只写 intermediate，不面向用户可见

处理：

```text
必须测试 result.compile_diagnostics 和 result.readable_report。
只测 intermediate 不满足 R5 验收。
```

## 13. R5 完成后的预期效果

R5 完成后，当显式开启：

```python
PipelineConfig(
    enable_worker_boundary_planner=True,
    enable_irs_v6_runner=True,
    enable_irs_worker_delegation_check=True,
)
```

用户应能在 pipeline 结果中看到：

```text
1. Stage 3.5 worker candidate IRS reports。
2. Stage 3.5 worker promotion IRS reports。
3. promotion_status=blocked 的结构化原因。
4. missing promotion_input_contract / promotion_output_contract / promotion_invocation_point / promotion_result_handoff 等 CompileDiagnostic。
5. readable report 中解释为什么没有晋升 child worker。
```

同时：

```text
final SPL 不因为 R5 改变。
worker_plan 不因为 R5 改变。
Stage 4/7/Gate 不因为 R5 改变。
默认配置不因为 R5 改变。
```
