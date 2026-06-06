# R7 Post-normalize Cleanup 实施计划

## 1. 阶段定位

R7 的目标来自 `07_irs_v6_refactor_tasks.md`：

```text
收敛 final construct-level diagnostic authority，
减少 DiagnosticAnalyzer / PostNormalizeIRSChecker / Gate 之间的职责重叠。
```

R7 不是新增语义 checker 的阶段，也不是改写 SPL 生成、渲染或 gate 规则的阶段。它要完成的是：把当前分散的 diagnostic 责任边界收紧，明确哪些 diagnostic 由 PostNormalizeIRSChecker 最终裁决，哪些只属于 Gate 的 post-gate renderability，哪些 legacy analyzer 只保留为兼容工具。

当前代码中的实际状态：

```text
PostNormalizeIRSChecker:
    src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py
    当前已经是 orchestrator 默认启用的 final construct-level authority。

ExecutableElementGate:
    src/nl2spl/pipeline/executable_gate.py
    当前负责过滤不可渲染 step，也会发出 gate 后 diagnostic。

DiagnosticAnalyzer:
    src/nl2spl/compiler/diagnostic_analyzer.py
    当前仍保留一套与 PostNormalizeIRSChecker 高度重叠的 diagnostic 规则，
    但生产 orchestrator 不直接调用它。
```

R7 的核心不是“删除所有重复代码”，而是让重复职责不再参与生产路径，并通过测试锁定：最终 compile diagnostics 不重复、readable report 信息不减少、completeness 计算不回归。

## 2. 权威边界

R7 必须把以下边界落实到代码和测试中：

| Diagnostic kind | 最终权威来源 | 说明 |
| --- | --- | --- |
| `missing_handler` | `PostNormalizeIRSChecker` | exception flow 从未有真实 handler 时由 post-normalize 发出；Gate 只处理“曾经有 handler，但被 gate 过滤后消失”的 post-gate 情况。 |
| `missing_output_producer` | `PostNormalizeIRSChecker` / Gate unpack guard | required output 无 producer 由 post-normalize 发出；compiler unpack 依赖的 producer 不可渲染时，Gate 可发出 scoped blocking diagnostic。 |
| `type_or_contract_ambiguity` | `PostNormalizeIRSChecker` | CALL_API / INVOKE_WORKER / REQUEST_INPUT 的 normalized contract ambiguity 由 post-normalize 发出。Stage-local IRS 可产生早期 report，但默认不作为最终裁决。 |
| `assumed_command_not_renderable` | `PostNormalizeIRSChecker` | source evidence 缺失且非合法 compiler scaffolding 的 step，由 post-normalize 发出。Gate 负责过滤，不重复发同类 final diagnostic。 |
| `unmapped_behavior_span` | Stage 7 / route-stage diagnostic | 不属于 R7 construct-level final authority cleanup 范围。 |
| `route_refinement_*` | Stage 2 FieldRoute | 不属于 R7 范围。 |
| `delegation_intent_without_handoff` 等 delegation diagnostics | D10 / Stage 3.5 IRS | 不属于 R7 范围。 |

## 3. 允许修改范围

R7 允许修改：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py
src/nl2spl/compiler/diagnostic_analyzer.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/irs/projector.py
src/nl2spl/compiler/__init__.py
tests/unit/pipeline/stages/test_final_irs_checker.py
tests/unit/test_executable_gate.py
tests/unit/test_diagnostic_analyzer.py
tests/unit/test_diagnostic_consolidation.py
tests/unit/test_orchestrator_result.py
tests/unit/test_report_renderer.py
tests/unit/compiler/irs/
docs/implementation/irs-v6/
```

R7 禁止修改：

```text
prompts/**
examples/**
output/**
src/nl2spl/pipeline/stages/stage2_*
src/nl2spl/pipeline/stages/stage3_*
src/nl2spl/pipeline/stages/stage4_*
src/nl2spl/pipeline/stages/stage5_*
src/nl2spl/pipeline/stages/stage6_*
src/nl2spl/pipeline/stages/stage7_*
src/nl2spl/pipeline/stages/stage8_*
src/nl2spl/pipeline/stages/stage9_constraint_extractor.py
src/nl2spl/pipeline/stages/stage10_*
src/nl2spl/pipeline/stages/stage11_*
```

如实现时发现必须修改上述禁止范围，必须先停止并提交设计问题说明，不能直接扩大范围。

## 4. LLM / Rule-based 决策约束

R7 不需要 LLM，也不允许新增 raw NL rule-based 语义判断。

R7 只允许消费已经存在的结构化 IR 字段，例如：

```text
WorkerIR.exception_flows
WorkerIR.steps
WorkerIR.child_workers
WorkerPlanIR.workers / handoffs
StepIR.command_type / source_span_ids / integration_ref / handoff_id / metadata
ResourceRegistryIR.variables
SymbolTable
ProducerIndex
NormalizationMixin.construct_findings
```

如果实现者认为某个 diagnostic 需要重新判断“是否像 handler action / ask signal / API call action”等自然语言语义，必须先向用户确认实现方式。未经确认，不允许用关键词规则或 LLM 增补。

## 5. 目标架构

R7 完成后的目标边界：

```text
Stage 9.5 Normalizer:
    可以记录 construct_findings。
    不直接生成 final CompileDiagnostic。

PostNormalizeIRSChecker:
    final construct-level diagnostic authority。
    负责 missing_handler / missing_output_producer /
         type_or_contract_ambiguity / assumed_command_not_renderable。

DiagnosticProjector:
    继续作为 v6 report -> CompileDiagnostic 的统一投影器。
    R7 可扩展 helper，但不强制一次性把 PostNormalizeIRSChecker 全部改成 v6 checker。

DiagnosticAnalyzer:
    不再被描述为 IRS final authority。
    若保留，只能是 legacy compatibility / fixture utility / non-IRS analyzer。

ExecutableElementGate:
    只负责 post-gate renderability。
    只在 gate 过滤导致新的可渲染性事实变化时产生 gate diagnostic。
    不重复发 post-normalize 已经负责的 construct-level diagnostic。

Orchestrator:
    默认继续使用 enable_irs_post_normalize_check=True。
    不因为 R7 减少 compile_diagnostics / readable_report 信息。
```

## 6. 任务拆分

### R7.1 Authority Baseline Audit

Priority: P1

Goal:

用测试锁定当前生产路径中 PostNormalizeIRSChecker、Gate、DiagnosticAnalyzer 的实际职责，避免后续 cleanup 时把信息删掉或重复引入。

Files:

```text
tests/unit/pipeline/stages/test_final_irs_checker.py
tests/unit/test_executable_gate.py
tests/unit/test_diagnostic_analyzer.py
tests/unit/test_diagnostic_consolidation.py
tests/unit/test_orchestrator_result.py
```

Implementation notes:

```text
1. 不改生产代码。
2. 增加 current-behavior tests：
   - PostNormalizeIRSChecker 产生四类 final construct-level diagnostics。
   - Gate 对“从未有 handler”的 exception flow 不发 missing_handler。
   - Gate 对“pre-gate 有 handler 但被过滤”的 exception flow 可发 post-gate missing_handler。
   - DiagnosticAnalyzer 不在 orchestrator 生产路径中被调用。
3. 不使用 xfail。
```

Acceptance criteria:

```text
1. R7.1 新增测试全部 pass。
2. 明确记录四类 diagnostic 的 production authority。
3. 没有生产代码改动。
4. 没有 skip / xfail / 空断言。
```

### R7.2 DiagnosticAnalyzer Legacy Boundary

Priority: P1

Goal:

将 `DiagnosticAnalyzer` 明确降级为 legacy compatibility / fixture-test utility，避免它继续被误解为 IRS final authority。

Files:

```text
src/nl2spl/compiler/diagnostic_analyzer.py
src/nl2spl/compiler/__init__.py
tests/unit/test_diagnostic_analyzer.py
tests/unit/test_orchestrator_result.py
```

Implementation notes:

```text
1. 不要直接删除 DiagnosticAnalyzer，除非确认所有外部 import 都不再依赖。
2. 更新 docstring：
   - 不再称为 IRS final authority。
   - 明确 production final construct-level diagnostics 由 PostNormalizeIRSChecker 负责。
3. 增加测试证明 PipelineOrchestrator 不调用 DiagnosticAnalyzer。
4. 如需从 compiler.__init__ 移除导出，必须先用 rg 确认项目内无生产依赖，并补兼容说明。
```

Acceptance criteria:

```text
1. DiagnosticAnalyzer 的职责说明与 R7 authority matrix 一致。
2. 生产 orchestrator 不依赖 DiagnosticAnalyzer。
3. 现有 DiagnosticAnalyzer 单测仍通过，作为 legacy behavior tests。
4. 不影响 compile result / readable report。
```

### R7.3 PostNormalizeIRSChecker Diagnostic Shape Hardening

Priority: P1

Goal:

收紧 PostNormalizeIRSChecker 输出的 `CompileDiagnostic` 形状，使它更接近 v6 DiagnosticProjector 的输出契约，便于未来进一步迁移到 report/projector 路径。

Files:

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py
src/nl2spl/ir/diagnostics.py
tests/unit/pipeline/stages/test_final_irs_checker.py
```

Implementation notes:

```text
1. 不要求一次性把 PostNormalizeIRSChecker 改写成 IRSChecker。
2. 可以新增内部 helper，例如：
   - _emit_missing_slot_diagnostic(...)
   - _make_missing_slot(...)
   - _make_target_ref(...)
3. 对四类 construct-level diagnostic 尽量填充：
   - missing_slot.slot_name
   - missing_slot.required_for
   - missing_slot.reason
   - missing_slot.source_span_ids
   - target_ref
   - source_span_ids
   - blocks_rendering / blocks_completion
4. 不改变 diagnostic kind、blocking 语义、message 中关键信息。
5. 如果某类 diagnostic 没有合理 missing_slot，不要硬造；应在测试中明确记录原因。
```

Acceptance criteria:

```text
1. missing_handler diagnostic 有稳定 target_ref 和 source_span_ids。
2. missing_output_producer diagnostic 有 output/variable target_ref。
3. type_or_contract_ambiguity diagnostic 有 step target_ref。
4. assumed_command_not_renderable diagnostic 有 step target_ref。
5. final completeness 计算不变。
6. readable report 中仍能看到原来的关键信息。
```

### R7.4 Duplicate Diagnostic Consolidation Tests

Priority: P1

Goal:

锁定四类 diagnostic 不重复，尤其是 Stage-local IRS、PostNormalizeIRSChecker、Gate、consolidation 同时存在时的合并行为。

Files:

```text
tests/unit/test_diagnostic_consolidation.py
tests/unit/test_orchestrator_result.py
tests/unit/pipeline/stages/test_final_irs_checker.py
tests/unit/test_executable_gate.py
```

Implementation notes:

```text
1. 针对每一类 diagnostic 建立 exactly-once tests：
   - missing_handler
   - missing_output_producer
   - type_or_contract_ambiguity
   - assumed_command_not_renderable
2. 测试必须覆盖：
   - post-normalize 默认开启。
   - stage-local diagnostics 存在但不应重复进入最终 diagnostics。
   - gate post-gate missing_handler 只在 handler 被过滤后出现。
3. 不用弱断言，例如只检查 len(diags) > 0。
```

Acceptance criteria:

```text
1. 每类 diagnostic 在目标场景中 exactly once。
2. dedup key 不误合并不同 target_ref / missing_slot。
3. dedup key 能合并同一 target_ref / same missing_slot 的重复项。
4. readable report 中每个 expected diagnostic 至少出现一次，不重复刷屏。
```

### R7.5 Gate Boundary Cleanup

Priority: P2

Goal:

确保 Gate 只承担 post-gate renderability，不重新承担 PostNormalizeIRSChecker 的 construct-level final diagnostics。

Files:

```text
src/nl2spl/pipeline/executable_gate.py
tests/unit/test_executable_gate.py
```

Implementation notes:

```text
1. 保留 Gate 对 blocked compiler_unpack 的 diagnostic，因为这是 gate-local producer/renderability 事实。
2. 保留 Gate 对 pre-gate handler 被过滤后的 post-gate missing_handler。
3. Gate 不应对“从未有 handler”的 exception flow 发 missing_handler。
4. Gate 不应发 assumed_command_not_renderable 来重复 PostNormalizeIRSChecker。
5. Gate 的 filtered render_info 仍必须完整。
```

Acceptance criteria:

```text
1. blocked unpack diagnostic 仍可见。
2. gate-filtered handler diagnostic 仍可见。
3. never-had-handler 场景不由 Gate 发 missing_handler。
4. assumed command 被过滤，但 final diagnostic authority 仍是 PostNormalizeIRSChecker。
```

### R7.6 Optional Projector Bridge Spike

Priority: P3

Goal:

评估 PostNormalizeIRSChecker 是否可以用局部 `ConstructSatisfactionReport` + `DiagnosticProjector` 生成部分 diagnostics，为未来 R8/R9 继续统一 diagnostic projection 做准备。

Files:

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py
src/nl2spl/compiler/irs/projector.py
tests/unit/pipeline/stages/test_final_irs_checker.py
tests/unit/compiler/irs/test_r3_diagnostic_projector.py
```

Implementation notes:

```text
1. 这是可选子任务，不应阻塞 R7 核心验收。
2. 不要一次性重写全部 PostNormalizeIRSChecker。
3. 可以只为 missing_handler 做一个 report/projector bridge 实验。
4. 如果 bridge 使 diagnostic shape、message、dedup 出现大范围变化，应停止并记录为后续阶段任务。
```

Acceptance criteria:

```text
1. 如果实施，必须证明 diagnostic kind / target_ref / missing_slot / blocking semantics 不回归。
2. 如果不实施，必须在实施报告中说明 PostNormalizeIRSChecker 仍直接创建 CompileDiagnostic 的剩余原因。
```

## 7. 必跑测试矩阵

R7 提交审核前必须运行：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/test_final_irs_checker.py -q
.venv\Scripts\python.exe -m pytest tests/unit/test_executable_gate.py -q
.venv\Scripts\python.exe -m pytest tests/unit/test_diagnostic_analyzer.py -q
.venv\Scripts\python.exe -m pytest tests/unit/test_diagnostic_consolidation.py -q
.venv\Scripts\python.exe -m pytest tests/unit/test_orchestrator_result.py -q
.venv\Scripts\python.exe -m pytest tests/unit/test_report_renderer.py tests/unit/test_feedback_report_renderer.py -q
.venv\Scripts\python.exe -m pytest tests/unit/test_irs_v6_r0_baseline.py tests/unit/test_irs_v6_r1_report_schema.py tests/unit/compiler/irs -q
.venv\Scripts\python.exe -m pytest tests/unit/ -q
```

如果本地 pytest cache 出现 Windows cache warning，不视为失败；但测试退出码必须为 0。

## 8. 审核重点

PM 审核不会只看实施报告，会逐条检查真实代码：

```text
1. 是否正确读取 R7 原始任务：Post-normalize Cleanup。
2. 是否没有把 R7 做成新增语义 checker。
3. 是否没有新增 LLM 调用。
4. 是否没有新增 raw NL keyword semantic rules。
5. DiagnosticAnalyzer 是否不再被描述为 IRS final authority。
6. PostNormalizeIRSChecker 是否仍是 final construct-level authority。
7. Gate 是否只处理 post-gate renderability。
8. 四类 diagnostic 是否 exactly once。
9. readable report 信息是否未减少。
10. final completeness 是否不变。
11. 是否没有通过 skip / xfail / 弱断言绕过验收。
12. 是否没有修改 prompts/examples/output。
```

## 9. 实施报告模板

提交 R7 审核时请使用以下结构：

```text
R7 Post-normalize Cleanup - 提交审核

1. 修改文件列表
   - 生产代码
   - 测试代码
   - 文档

2. Authority boundary 结果
   - missing_handler:
   - missing_output_producer:
   - type_or_contract_ambiguity:
   - assumed_command_not_renderable:
   - Gate-only diagnostics:
   - Legacy DiagnosticAnalyzer status:

3. 行为不变确认
   - final completeness:
   - readable report:
   - gate renderability:
   - post-normalize diagnostics:

4. 测试命令和结果
   - final_irs_checker:
   - executable_gate:
   - diagnostic_analyzer:
   - diagnostic_consolidation:
   - report/feedback renderer:
   - IRS regression:
   - full unit:

5. LLM / rule-based 决策记录
   - 是否新增 LLM 调用：必须为否
   - 是否新增 raw NL rule-based 语义判断：必须为否
   - 如果有结构化 predicate 调整，说明只消费了哪些 IR 字段

6. 已知风险
```

## 10. R7 完成定义

R7 完成必须同时满足：

```text
1. PostNormalizeIRSChecker 的 final authority 明确且测试覆盖。
2. DiagnosticAnalyzer 不再与 PostNormalizeIRSChecker 争夺 IRS final authority。
3. Gate 的职责限定为 post-gate renderability。
4. missing_handler / missing_output_producer /
   type_or_contract_ambiguity / assumed_command_not_renderable 不重复。
5. final completeness 计算不变。
6. readable report 信息不减少。
7. 全量单元测试通过。
8. 无 prompt / example / output churn。
9. 无 LLM 调用。
10. 无新增 raw NL rule-based 语义判断。
```
