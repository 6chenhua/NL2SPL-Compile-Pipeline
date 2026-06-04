# R6 Stage4 / Stage7 Compatibility Migration 实施计划

## 1. 阶段定位

R6 的目标是把当前 Stage 4 / Stage 7 的函数式 IRS checker 迁移为 v6-style checker，同时保持旧 public wrapper 的调用契约不变。

当前状态：

```text
Stage 4:
    src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py
        check_exception_flows_irs(...)
        check_worker_flow_plan_exception_flows_irs(...)

Stage 7:
    src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py
        check_steps_irs(...)
        check_worker_step_plan_irs(...)
```

R6 之后的目标状态：

```text
src/nl2spl/compiler/irs/checkers/exception_flow.py
    Stage4ExceptionFlowIRSChecker

src/nl2spl/compiler/irs/checkers/step.py
    Stage7StepIRSChecker

旧 public wrappers:
    继续存在
    继续返回 tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]
    内部改为通过 IRSCheckContext / IRSRunner / DiagnosticProjector 产生结果
```

R6 是兼容迁移阶段，不是语义升级阶段。它不改变 Stage 4 / Stage 7 的 construct materialization 行为，不改变 final SPL，不新增 raw NL 规则。

## 2. 前置状态

R6 依赖以下已完成内容：

```text
R1:
    ConstructSatisfactionReport 已具备 source_span_ids / source_section_id /
    source_packet_id / construct_path / related_edges / frontier_status /
    cutline_reason 等 v6 字段。

R2:
    IRSCheckContext / ConstructInstance / IRSCheckerRegistry / IRSRunner 已存在。

R3:
    DiagnosticProjector 已能把 SlotSatisfaction.diagnostic_kind 投影为
    CompileDiagnostic，并填充 missing_slot。

R4:
    WorkerDelegationIRSChecker 已证明 v6 checker 可以落地。

R5:
    runner/factory/orchestrator integration 已接入 Stage 3.5。
```

R6 不迁移 PostNormalizeIRSChecker。Post-normalize cleanup 是 R7 范围。

## 3. 设计边界

### 3.1 允许做的事情

```text
1. 新增 Stage4ExceptionFlowIRSChecker。
2. 新增 Stage7StepIRSChecker。
3. 扩展 IRS runner factory，使其可注册 exception flow checker 和 step checker。
4. 保留旧 public wrappers，并让 wrappers 内部走 v6 checker / runner / projector。
5. 更新 Stage 4 / Stage 7 IRS 单元测试，锁定旧 wrapper 行为不变。
6. 新增 runner-level tests，证明新 checker 可通过 IRSRunner 调度。
7. 新增 worker-scoped tests，证明 worker target_ref / diagnostic_id / path 不串线。
8. 在必要时更新 orchestrator 测试，但不应把 orchestrator 作为主要迁移面。
```

### 3.2 禁止做的事情

```text
1. 禁止修改 FlowAssembler / StepExtractor 的生成逻辑。
2. 禁止修改 Stage 5 / Stage 6 / Stage 8 / Stage 9 / Stage 9.5 / Gate。
3. 禁止修改 renderer。
4. 禁止改变 final SPL。
5. 禁止让 Stage 4 提前发出 missing_handler。
6. 禁止让 Stage 7 checker 生成、删除、修复 StepIR。
7. 禁止 checker 直接创建 CompileDiagnostic。
8. 禁止 checker 调用 LLM。
9. 禁止 checker 解析 raw NL 或新增关键词式语义判断。
10. 禁止用 skip / xfail / 弱断言绕过旧行为兼容。
11. 禁止默认开启新的 feature flag。
```

### 3.3 LLM / rule-based 决策约束

R6 只消费已经存在的结构化 IR：

```text
Stage4ExceptionFlowIRSChecker:
    只读 FlowStructureIR / WorkerFlowPlanIR / ExceptionFlow。

Stage7StepIRSChecker:
    只读 StepIR / WorkerStepPlanIR。
```

R6 不允许新增对自然语言的语义判断。

如果实施者认为某个 slot 需要判断“ask signal”“call action”“handler action”等自然语言语义，必须停止实现并提交设计问题给用户确认。R6 可以保留当前既有判定方式，例如：

```text
REQUEST_INPUT:
    当前 Stage 7 IRS 只检查已经生成的 REQUEST_INPUT StepIR 是否有 source_span_ids。

CALL_API:
    当前 Stage 7 IRS 只检查 integration_ref 与 source_span_ids。
```

不要在 R6 中新增 raw text keyword matching。

## 4. 目标架构

### 4.1 Stage4ExceptionFlowIRSChecker

新增文件：

```text
src/nl2spl/compiler/irs/checkers/exception_flow.py
```

建议类名：

```python
class Stage4ExceptionFlowIRSChecker:
    checker_id = "stage4_exception_flow"
    supported_construct_types = ("EXCEPTION_FLOW",)
    supported_stages = ("stage4",)
```

实例提取规则：

```text
context.flow is FlowStructureIR:
    flow.exception_flows -> EXCEPTION_FLOW instances

context.worker_flows is WorkerFlowPlanIR or dict[str, FlowStructureIR]:
    each worker flow.exception_flows -> worker-scoped EXCEPTION_FLOW instances
```

ConstructInstance 要求：

```text
construct_id:
    exception_flow:{flow_id}
    worker:{worker_id}.exception_flow:{flow_id}

construct_type:
    EXCEPTION_FLOW

materialized:
    True

source_demanded:
    True

candidate_only:
    False

ir_ref:
    ExceptionFlow

source_span_ids:
    list(ExceptionFlow.spans)

construct_path:
    ("flow", "exception_flows", flow_id)
    ("worker_flow_plan", worker_id, "exception_flows", flow_id)

metadata:
    worker_id
    flow_id
    condition_text
```

检查规则必须保持当前 Stage 4 行为：

```text
condition:
    condition_text 非空且 spans 非空 -> satisfied / direct
    condition_text 非空但 spans 为空 -> assumed + type_or_contract_ambiguity

handler_action:
    not_applicable
    Stage 4 不检查 handler
    Stage 4 不发 missing_handler

trigger_step:
    not_applicable
```

Stage 4 report 语义：

```text
completeness:
    partial

renderable:
    condition source-backed 时 True
    condition assumed/no span evidence 时 False

frontier_status:
    condition source-backed -> cutline_partial
    condition 缺 source evidence -> cutline_blocked

cutline_reason:
    condition source-backed -> missing_required_for_complete
    condition 缺 source evidence -> missing_required_for_partial 或 no_source_evidence
```

如果现有 `CutlineReason` 没有合适值，不要随意新增含糊值。应先通过测试确认已有 literal 是否足够；如需扩展 `CutlineReason`，必须在 R6 计划内显式说明并加 schema tests。

### 4.2 Stage7StepIRSChecker

新增文件：

```text
src/nl2spl/compiler/irs/checkers/step.py
```

建议类名：

```python
class Stage7StepIRSChecker:
    checker_id = "stage7_step"
    supported_construct_types = (
        "GENERAL_COMMAND",
        "REQUEST_INPUT",
        "CALL_API",
        "INVOKE_WORKER",
    )
    supported_stages = ("stage7",)
```

实例提取规则：

```text
context.steps:
    StepIR list -> supported command_type instances

context.worker_steps:
    WorkerStepPlanIR or dict[str, list[StepIR]]
    -> worker-scoped supported command_type instances

unsupported command_type:
    DISPLAY_MESSAGE or unknown type -> no instance
```

ConstructInstance 要求：

```text
construct_id:
    step:{step_id}
    worker:{worker_id}.step:{step_id}

construct_type:
    mapped from StepIR.command_type

materialized:
    True

source_demanded:
    True

candidate_only:
    False

ir_ref:
    StepIR

source_span_ids:
    list(StepIR.source_span_ids)

construct_path:
    ("steps", step_id)
    ("worker_step_plan", worker_id, "steps", step_id)

metadata:
    worker_id
    step_id
    command_type
```

检查规则必须保持当前 Stage 7 行为：

```text
GENERAL_COMMAND:
    source_span_ids 非空 -> renderable
    source_span_ids 为空 -> assumed_command_not_renderable

REQUEST_INPUT:
    source_span_ids 非空 -> renderable
    source_span_ids 为空 -> type_or_contract_ambiguity

CALL_API:
    integration_ref 非空且 source_span_ids 非空 -> renderable
    integration_ref 缺失 -> type_or_contract_ambiguity(api_name)
    source_span_ids 缺失 -> type_or_contract_ambiguity(call_action)

INVOKE_WORKER:
    handoff_id 非空且 integration_ref 非空 -> renderable
    handoff_id 缺失 -> type_or_contract_ambiguity(handoff_id)
    integration_ref 缺失 -> type_or_contract_ambiguity(target_worker)
```

重要限制：

```text
REQUEST_INPUT 的 ask signal 不在 R6 中重新解释 raw NL。
CALL_API 的 call action 不在 R6 中通过关键词判断。
R6 只迁移当前 checker 行为到 v6 checker 形式。
```

## 5. Compatibility Wrapper 设计

旧 public function 必须保留：

```python
check_exception_flows_irs(...)
check_worker_flow_plan_exception_flows_irs(...)
check_steps_irs(...)
check_worker_step_plan_irs(...)
```

这些函数的返回契约不变：

```python
tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]
```

推荐实现方式：

```text
old wrapper
-> build local IRSCheckContext
-> build IRSRunner with only the corresponding checker registered
-> runner.run_stage(...)
-> return result.reports, result.diagnostics
```

注意：

```text
1. wrapper 可以继续接受 registry 参数，用于兼容旧测试。
2. wrapper 不应直接创建 CompileDiagnostic。
3. wrapper 不应修改输入 IR。
4. wrapper 不应改变 report/diagnostic 数量、kind、target_ref、source_span_ids、blocks_rendering、blocks_completion 的语义。
5. 如果 DiagnosticProjector 生成的 diagnostic_id 与旧 ID 不同，必须新增测试证明：
   - ID deterministic
   - worker-scoped ID 不重复
   - compile diagnostic dedup 不误合并
```

## 6. Factory / Runner 扩展

建议扩展：

```text
src/nl2spl/compiler/irs/factory.py
```

新增参数：

```python
enable_exception_flow: bool = False
enable_step: bool = False
```

行为：

```text
enable_exception_flow=True:
    register Stage4ExceptionFlowIRSChecker

enable_step=True:
    register Stage7StepIRSChecker
```

R6 不要求新增 PipelineConfig flags，因为现有 flags 已经存在：

```python
enable_irs_stage4_exception_flow_check: bool = False
enable_irs_stage7_step_check: bool = False
```

R6 中 orchestrator 可以继续通过旧 wrappers 运行 Stage 4 / Stage 7 IRS。不要为了迁移 checker 而大改 orchestrator 主流程。

## 7. 任务拆分

### R6.1 Baseline Compatibility Audit

Priority: P1

Goal:

确认 Stage 4 / Stage 7 当前 public wrappers 的可观察行为，避免迁移后回归。

Files:

```text
tests/unit/test_stage4_irs_exception_flow.py
tests/unit/test_stage7_irs_step_extraction.py
tests/unit/test_irs_v6_r0_baseline.py
tests/unit/test_irs_v6_r1_report_schema.py
```

Acceptance criteria:

```text
1. 当前 Stage 4 / Stage 7 tests 先在未改生产代码前通过。
2. 明确记录当前 diagnostics 数量、kind、target_ref、source_span_ids、blocking flags。
3. 如果新增 target tests，只允许用于 R6 新 checker runner-level 行为，不允许 xfail 绕过兼容。
```

### R6.2 Implement Stage4ExceptionFlowIRSChecker

Priority: P1

Goal:

把 EXCEPTION_FLOW Stage 4 slot satisfaction 逻辑迁移到 v6 checker。

Files:

```text
src/nl2spl/compiler/irs/checkers/exception_flow.py
src/nl2spl/compiler/irs/checkers/__init__.py
tests/unit/compiler/irs/test_r6_exception_flow_checker.py
```

Acceptance criteria:

```text
1. checker.extract_instances() 支持 FlowStructureIR。
2. checker.extract_instances() 支持 WorkerFlowPlanIR 或 worker flow dict。
3. condition source-backed -> condition slot satisfied。
4. condition text with no spans -> condition slot assumed + type_or_contract_ambiguity。
5. handler_action 在 Stage 4 为 not_applicable。
6. 不产生 missing_handler。
7. report 包含 construct_path / source_span_ids / frontier_status / cutline_reason。
8. 不修改 FlowStructureIR / WorkerFlowPlanIR。
```

### R6.3 Implement Stage7StepIRSChecker

Priority: P1

Goal:

把 StepIR command-type IRS 检查迁移到 v6 checker。

Files:

```text
src/nl2spl/compiler/irs/checkers/step.py
src/nl2spl/compiler/irs/checkers/__init__.py
tests/unit/compiler/irs/test_r6_step_checker.py
```

Acceptance criteria:

```text
1. GENERAL_COMMAND source_span_ids 为空 -> assumed_command_not_renderable。
2. GENERAL_COMMAND source_span_ids 非空 -> complete/renderable。
3. REQUEST_INPUT source_span_ids 为空 -> type_or_contract_ambiguity。
4. CALL_API 缺 integration_ref -> type_or_contract_ambiguity(api_name)。
5. CALL_API 缺 source_span_ids -> type_or_contract_ambiguity(call_action)。
6. INVOKE_WORKER 缺 integration_ref -> type_or_contract_ambiguity(target_worker)。
7. INVOKE_WORKER 缺 handoff_id -> type_or_contract_ambiguity(handoff_id)。
8. DISPLAY_MESSAGE / unknown command type 不产生 instance。
9. worker-scoped target_ref / construct_id 不串线。
10. 不修改 StepIR / WorkerStepPlanIR。
```

### R6.4 Migrate Public Wrappers To v6 Runner

Priority: P1

Goal:

让旧 Stage 4 / Stage 7 public wrappers 内部使用 v6 checker / runner / projector，同时保持外部调用方式不变。

Files:

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py
src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py
tests/unit/test_stage4_irs_exception_flow.py
tests/unit/test_stage7_irs_step_extraction.py
```

Acceptance criteria:

```text
1. check_exception_flows_irs(...) 仍返回 (reports, diagnostics)。
2. check_worker_flow_plan_exception_flows_irs(...) 仍返回聚合结果。
3. check_steps_irs(...) 仍返回 (reports, diagnostics)。
4. check_worker_step_plan_irs(...) 仍返回聚合结果。
5. 原有 Stage 4 / Stage 7 public function tests 全部通过。
6. 新增测试确认 wrappers 不直接创建 CompileDiagnostic，而是使用 DiagnosticProjector 输出。
7. 新增测试确认 result diagnostics 带 missing_slot。
8. 新增测试确认 deterministic diagnostic_id。
```

### R6.5 Extend Factory And Runner-Level Tests

Priority: P2

Goal:

让 R6 checkers 可通过统一 factory 注册，便于后续 orchestrator 直接 runner 化。

Files:

```text
src/nl2spl/compiler/irs/factory.py
tests/unit/compiler/irs/test_r5_runner_factory.py
tests/unit/compiler/irs/test_r6_runner_stage4_stage7.py
```

Acceptance criteria:

```text
1. build_irs_checker_registry(enable_exception_flow=True) 注册 Stage4ExceptionFlowIRSChecker。
2. build_irs_checker_registry(enable_step=True) 注册 Stage7StepIRSChecker。
3. build_irs_runner(enable_exception_flow=True) 可运行 stage4。
4. build_irs_runner(enable_step=True) 可运行 stage7。
5. 默认 registry 仍为空。
6. enable_worker_delegation 行为不回归。
7. 无 circular import。
```

### R6.6 Orchestrator Compatibility Tests

Priority: P2

Goal:

确认 R6 不改变 orchestrator 对 Stage 4 / Stage 7 IRS flags 的可观察行为。

Files:

```text
tests/unit/pipeline/test_worker_aware_orchestrator.py
tests/unit/test_diagnostic_consolidation.py
tests/unit/compiler/irs/test_r6_orchestrator_compatibility.py
```

Acceptance criteria:

```text
1. enable_irs_stage4_exception_flow_check=False 时，无 stage4 construct_satisfaction。
2. enable_irs_stage4_exception_flow_check=True 时，stage4 reports/diagnostics 写入 intermediate。
3. enable_irs_stage7_step_check=False 时，无 stage7 construct_satisfaction。
4. enable_irs_stage7_step_check=True 时，stage7 reports/diagnostics 写入 intermediate。
5. compile_diagnostics / readable_report 行为不因 R6 减少信息。
6. worker-aware path 保持通过。
```

## 8. 测试矩阵

### 8.1 必跑测试

```powershell
python -m pytest tests/unit/compiler/irs/test_r6_exception_flow_checker.py -q
python -m pytest tests/unit/compiler/irs/test_r6_step_checker.py -q
python -m pytest tests/unit/compiler/irs/test_r6_runner_stage4_stage7.py -q
python -m pytest tests/unit/test_stage4_irs_exception_flow.py tests/unit/test_stage7_irs_step_extraction.py -q
python -m pytest tests/unit/test_irs_v6_r0_baseline.py tests/unit/test_irs_v6_r1_report_schema.py -q
python -m pytest tests/unit/ -q
```

### 8.2 审核时会重点检查

```text
1. 是否存在 skip / xfail / 弱断言。
2. 是否直接创建 CompileDiagnostic。
3. 是否新增 raw NL keyword matching。
4. 是否改变 final SPL。
5. 是否改变 Stage 4 missing_handler 时机。
6. 是否改变 StepExtractor 输出。
7. 是否保持 worker-scoped diagnostic target_ref。
8. 是否保留 source_span_ids / source_section_id / source_packet_id。
9. 是否通过 DiagnosticProjector 填充 missing_slot。
10. 是否所有 public wrappers 仍可用。
```

## 9. 验收标准

R6 完成必须同时满足：

```text
1. Stage4ExceptionFlowIRSChecker 存在并通过独立单测。
2. Stage7StepIRSChecker 存在并通过独立单测。
3. 旧 Stage 4 public wrappers 调用方式不变。
4. 旧 Stage 7 public wrappers 调用方式不变。
5. Stage 4 condition-only exception flow 行为不变。
6. Stage 4 不提前发 missing_handler。
7. Stage 7 assumed command not renderable 行为不变。
8. REQUEST_INPUT 不因 R6 新增 raw NL 规则。
9. CALL_API 不因 R6 新增 raw NL 规则。
10. Worker-scoped Stage 4 / Stage 7 diagnostics target_ref 不串线。
11. Diagnostics 由 DiagnosticProjector 生成，且带 missing_slot。
12. R0-R6 相关测试通过。
13. 全量单元测试通过。
14. 无 prompt / examples / output 修改。
15. 无 LLM 调用。
```

## 10. 实施报告模板

提交审核时，请按以下格式报告：

```text
R6 Stage4 / Stage7 Compatibility Migration — 提交审核

1. 修改文件列表
   - 生产代码
   - 测试代码
   - 文档

2. 迁移说明
   - Stage4ExceptionFlowIRSChecker 如何提取 instance
   - Stage7StepIRSChecker 如何提取 instance
   - public wrappers 如何保持兼容
   - DiagnosticProjector 如何参与

3. 未改变行为确认
   - Stage 4 missing_handler 时机
   - Stage 7 StepIR 生成逻辑
   - worker-scoped target_ref
   - final SPL

4. 测试命令和结果
   - R6 checker tests
   - Stage 4 / Stage 7 wrapper tests
   - R0-R6 regression
   - full tests

5. LLM / rule-based 决策记录
   - 是否新增 LLM 调用：必须为否
   - 是否新增 raw NL rule-based 语义判断：必须为否

6. 已知风险
```

## 11. PM 审核清单

审核不会只看实施报告。审核时会逐项核验真实代码：

```text
1. 新 checker 是否实现 IRSChecker protocol。
2. 新 checker 是否只消费结构化 IR。
3. 新 checker 是否不直接创建 CompileDiagnostic。
4. wrappers 是否真的通过 runner/projector，而不是复制旧逻辑。
5. 旧 tests 是否仍覆盖 wrappers。
6. 新 tests 是否覆盖 runner-level path。
7. diagnostics 是否带 missing_slot。
8. stage4/stage7 flags 默认行为是否不变。
9. orchestrator 是否没有直接 import concrete checker。
10. 是否没有新增 prompt / output / example churn。
```

