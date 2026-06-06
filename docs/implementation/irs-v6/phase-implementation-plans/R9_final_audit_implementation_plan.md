# R9 Final Audit 实施计划

## 1. 阶段定位

R9 的目标来自 `07_irs_v6_refactor_tasks.md`：

```text
确认 IRS v6 扩展路径达到设计目标。
```

R9 不是新增 checker、不是新增 IRS 语义、不是实现递归 traversal。它是 IRS v6 重构的最终审计与收敛阶段，重点确认 R0-R8 已经形成的架构是否真正满足最初目标：

```text
1. 新增 checker 不需要改 orchestrator 主流程。
2. Diagnostic 由 DiagnosticProjector 统一生成。
3. Worker candidate 与 promotion blocked 能被结构化解释。
4. ConstructSatisfactionReport 具备 parent/path/edge/frontier/cutline 字段。
5. Stage 4 / Stage 7 / Post-normalize 兼容。
6. Renderer 不承担 IRS 判断。
7. Gate / ProducerIndex authority 没有被 IRS 替代。
8. internal-comms-3 Issue 3 能被 IRS report 解释。
9. full test suite 通过。
```

R9 的产出应是一份可审核的最终审计报告、一组必要的审计测试/回归测试、以及文档和进度追踪状态的同步更新。

## 2. 设计边界

### 2.1 R9 做什么

```text
1. 审计 R0-R8 的代码、测试、文档是否一致。
2. 审计 IRS v6 feature flags 是否仍有 stale 描述或误导性默认值说明。
3. 审计是否存在 skipped / xfail IRS tests。
4. 审计是否存在弱断言 baseline tests。
5. 审计 renderer / gate / producer index / orchestrator 是否保持 authority boundary。
6. 增加必要的 audit tests，锁住最终架构契约。
7. 生成最终审计报告，记录结论、证据、残余风险和后续非 R9 工作。
8. 更新 progress tracker / README / task matrix，使状态与真实代码一致。
```

### 2.2 R9 不做什么

```text
1. 不新增 IRS checker。
2. 不新增 ConstructIRS slot 语义。
3. 不新增 DiagnosticProjector 投影规则，除非只是修复 R0-R8 已承诺但未兑现的 bug。
4. 不实现 recursive IRS traversal。
5. 不新增 raw NL keyword semantic rules。
6. 不新增 LLM 调用。
7. 不修改 renderer 以补偿 IRS 缺口。
8. 不修改 Gate / ProducerIndex 的最终裁决权。
9. 不改变 final SPL 行为，除非发现 R0-R8 实现存在明确 bug 且修复已被测试证明。
```

如果 R9 审计发现需要新增语义判断、LLM 判断、或 rule-based NL 判断，必须先记录为后续任务并向用户确认实现方式，不能在 R9 中直接实现。

## 3. 可修改文件

R9 允许修改：

```text
docs/implementation/irs-v6/**
docs/implementation/irs-v6/phase-implementation-plans/**
tests/unit/compiler/irs/**
tests/unit/test_irs_v6_r0_baseline.py
tests/unit/test_irs_v6_r1_report_schema.py
tests/unit/test_diagnostic_consolidation.py
tests/unit/test_executable_gate.py
tests/unit/pipeline/stages/test_final_irs_checker.py
```

如审计发现 feature flag 注释或导出状态与实际行为不一致，可修改：

```text
src/nl2spl/config.py
src/nl2spl/compiler/irs/__init__.py
src/nl2spl/compiler/irs/factory.py
```

但这些修改只能用于文档化、导出一致性或显式 bug 修复，不得改变默认生产行为。

如审计发现 R8 graph helper 存在显式 bug，可修改：

```text
src/nl2spl/compiler/irs/graph.py
```

但必须附带直接回归测试。

## 4. 禁止修改文件

R9 默认禁止修改：

```text
prompts/**
examples/**
output/**
src/nl2spl/pipeline/stages/stage2_field_router.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/**
src/nl2spl/pipeline/stages/stage4_flow_assembler/**
src/nl2spl/pipeline/stages/stage6_resource_extractor/**
src/nl2spl/pipeline/stages/stage7_step_extractor/**
src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/normalizer.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/producer_index.py
src/nl2spl/compiler/report_renderer.py
```

如果确实需要修改上述文件，说明 R9 审计发现的是未完成的前序阶段 bug。此时必须先提交问题记录，说明根因、影响范围、为什么不能作为后续阶段处理，并得到用户确认后再改。

## 5. 子任务拆分

### R9.1 R0-R8 验收项追溯审计

目标：逐阶段确认 R0-R8 验收标准是否真实达到，而不是只看提交报告。

实施步骤：

```text
1. 对照 R0-R8 phase implementation plans。
2. 列出每阶段关键交付：
   R0 baseline
   R1 report schema
   R2 framework skeleton
   R3 projector
   R4 worker/delegation checker
   R5 runner/orchestrator integration
   R6 Stage4/Stage7 compatibility migration
   R7 post-normalize cleanup
   R8 graph-ready hardening
3. 为每阶段记录：
   - 实际修改文件
   - 关键测试文件
   - 是否仍有 xfail/skip
   - 是否存在弱断言
   - 是否存在未兑现 acceptance
4. 写入最终审计报告。
```

验收标准：

```text
1. 审计报告中有 R0-R8 每阶段一行或一节。
2. 每阶段都列出真实代码证据或测试证据。
3. 不允许只写“通过”，必须写明通过依据。
```

### R9.2 Feature Flag 与导出边界审计

目标：确认 feature flags、factory、lazy exports 与实际接入路径一致。

重点检查：

```text
PipelineConfig:
    enable_irs_v6_runner
    enable_irs_worker_delegation_check
    enable_irs_stage4_exception_flow_check
    enable_irs_stage7_step_check
    enable_irs_post_normalize_check
    enable_irs_prompt_builder
    enable_irs_diagnostic_consolidation

Factory:
    build_irs_checker_registry()
    build_irs_runner()

Lazy exports:
    nl2spl.compiler.irs.__getattr__
```

必须确认：

```text
1. 默认配置不改变旧行为。
2. 开启 Stage 3.5 worker/delegation IRS 需要总开关 + 子开关。
3. Stage4/Stage7 flags 仍控制对应 compatibility wrapper。
4. Post-normalize IRS authority 默认状态与文档一致。
5. 不存在 stale 注释，例如 “Satisfaction” 误写、旧 v5 authority 描述、已废弃 flag 仍被描述为主路径。
```

建议测试：

```text
tests/unit/compiler/irs/test_r9_final_audit.py
    test_r9_feature_flags_document_current_authority
    test_r9_irs_lazy_exports_match_factory_surface
    test_r9_default_config_preserves_irs_v6_opt_in_paths
```

验收标准：

```text
1. 无 stale feature flag 描述。
2. lazy exports 无循环导入回归。
3. factory 注册结果与 flags 精确对应。
```

### R9.3 Authority Boundary 审计

目标：确认 IRS v6 没有越权替代 Renderer / Gate / ProducerIndex / Post-normalize authority。

必须检查：

```text
Renderer:
    不读取 ConstructSatisfactionReport / IRSRunner / DiagnosticProjector。
    不基于 IRS report 生成 SPL construct。

Gate:
    仍负责 step-level renderability。
    不生成 construct-level IRS report。

ProducerIndex:
    仍负责 output producer authority。
    IRS 不替代 producer 判定。

PostNormalizeIRSChecker:
    仍是 normalized construct-level diagnostic authority。
    missing_handler / missing_output_producer 等最终诊断不由 stage-local checker 越权替代。
```

建议测试：

```text
tests/unit/compiler/irs/test_r9_final_audit.py
    test_r9_renderer_does_not_import_irs_modules
    test_r9_gate_does_not_import_irs_runner_or_projector
    test_r9_producer_index_does_not_depend_on_irs_runner
    test_r9_post_normalize_remains_construct_diagnostic_authority
```

验收标准：

```text
1. Renderer 不承担 IRS 判断。
2. Gate / ProducerIndex authority 未被替代。
3. Post-normalize checker 的 final authority 仍有测试覆盖。
```

### R9.4 Test Hygiene 审计

目标：清理 IRS 相关测试中的 skip、xfail、弱断言和 stale baseline。

审计范围：

```text
tests/unit/compiler/irs/**
tests/unit/test_irs_v6_r0_baseline.py
tests/unit/test_irs_v6_r1_report_schema.py
tests/unit/pipeline/stages/test_final_irs_checker.py
tests/unit/test_diagnostic_consolidation.py
tests/unit/test_executable_gate.py
```

必须检查：

```text
1. 无 pytest.skip。
2. 无 pytest.mark.skip。
3. 无 pytest.mark.xfail。
4. 无 “pass-only” 空测试。
5. 无只断言 len(...) > 0 的弱断言作为验收。
6. R0 中的 target-future 测试已经随着 R4-R8 转为 passing 或移除 xfail。
```

允许存在：

```text
1. 对 DISPLAY_MESSAGE “skipped by checker” 的业务用语。
2. 非 pytest skip 的说明性注释。
3. 全量测试中的非 IRS skip，但必须在最终审计报告中说明它们与 IRS 无关。
```

建议新增审计测试：

```text
test_r9_no_pytest_skip_or_xfail_in_irs_tests
test_r9_no_empty_pass_tests_in_irs_tests
test_r9_no_weak_len_only_acceptance_tests
```

注意：弱断言审计不能过度机械化。可以用文本扫描锁定明显模式，再人工复核并在报告中记录结论。

### R9.5 Test Matrix 对齐审计

目标：确认 `07_irs_v6_refactor_tasks.md` 的测试矩阵都有对应测试或明确的非 R9 说明。

测试矩阵：

```text
failure condition only
failure condition + handler evidence
required output no producer
incomplete delegation
worker candidate only
complete source-backed delegation
REQUEST_INPUT without ask signal
CALL_API with repository mention only
assumed command
compiler unpack without renderable producer
gate-filtered handler
```

实施要求：

```text
1. 为每个场景找到对应测试文件和测试名。
2. 如果场景由非 IRS 阶段覆盖，例如 Gate 或 StepExtractor，仍需记录。
3. 如果场景当前没有足够覆盖，新增 focused regression test。
4. 不允许用 E2E LLM 输出作为唯一证据。
```

建议报告格式：

```markdown
| 场景 | 覆盖测试 | 层级 | 结论 | 备注 |
| --- | --- | --- | --- | --- |
```

验收标准：

```text
1. 测试矩阵 11 个场景全部有证据。
2. 没有 “未确认” 项。
3. 如果某项是后续工作，必须说明为什么不属于 R9，并形成 residual item。
```

### R9.6 internal-comms-3 Issue 3 解释能力审计

目标：确认 IRS v6 能解释 “识别到 delegation / worker candidate，但不能晋升 child worker” 的原因。

R9 不要求重新运行真实 LLM E2E。优先使用 source-backed IR fixture 或已有中间结果复现。

必须验证：

```text
1. 对 incomplete delegation candidate，产生 WORKER_CANDIDATE report。
2. 对同一 candidate，产生 WORKER_PROMOTION report。
3. WORKER_PROMOTION metadata["promotion_status"] == "blocked"。
4. missing slots 至少能表达：
   promotion_input_contract
   promotion_output_contract
   promotion_invocation_point
   promotion_result_handoff
5. DiagnosticProjector 可投影 type_or_contract_ambiguity。
6. diagnostics / readable report 能说明 blocked promotion 原因。
7. 不生成 child worker / handoff / INVOKE_WORKER 作为补偿。
```

建议新增或确认测试：

```text
test_r9_internal_comms_issue3_worker_promotion_blocked_explained
test_r9_worker_promotion_diagnostics_appear_in_readable_report
```

验收标准：

```text
1. Issue 3 可由 Worker/Delegation IRS report 解释。
2. 解释是结构化的，不依赖人工读 raw NL。
3. 没有改变 child worker materialization 行为。
```

### R9.7 最终审计报告

目标：生成最终文档，作为 IRS v6 重构闭环证据。

建议新增：

```text
docs/implementation/irs-v6/R9_final_audit_report.md
```

报告必须包含：

```text
1. 总体结论。
2. R0-R8 阶段验收追溯。
3. R9 审计测试结果。
4. Feature flags 当前状态。
5. Authority boundary 当前状态。
6. Test matrix 覆盖表。
7. internal-comms-3 Issue 3 解释能力。
8. 残余工作列表。
9. 不属于 R9 的后续方向：
   - 真正 recursive IRS traversal
   - 更多 SPL construct IRS checker
   - 更精细 evidence_kinds
   - 更完整 graph builder / graph visualizer
```

验收标准：

```text
1. 报告中所有结论都有代码或测试证据。
2. 残余工作不能掩盖 R0-R8 已承诺验收项。
3. 报告明确说明 R9 不实现 recursive traversal。
```

## 6. 建议新增测试文件

建议新增：

```text
tests/unit/compiler/irs/test_r9_final_audit.py
```

测试分组：

```text
TestR9FeatureFlags
TestR9AuthorityBoundary
TestR9TestHygiene
TestR9TestMatrixCoverage
TestR9InternalCommsIssue3Explanation
```

注意：

```text
1. 审计测试可以读源码文本，但不能只做文本存在性测试。
2. 对关键行为必须构造 IR fixture 并调用真实 checker / runner / projector。
3. 文档一致性测试只用于防止 stale 描述，不能替代行为测试。
```

## 7. 建议命令

### 7.1 R9 focused tests

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/unit/compiler/irs/test_r9_final_audit.py `
  -q --basetemp=.pytest-tmp-r9
```

### 7.2 IRS regression

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/unit/compiler/irs `
  tests/unit/test_irs_v6_r0_baseline.py `
  tests/unit/test_irs_v6_r1_report_schema.py `
  tests/unit/pipeline/stages/test_final_irs_checker.py `
  tests/unit/test_diagnostic_consolidation.py `
  tests/unit/test_executable_gate.py `
  -q --basetemp=.pytest-tmp-r9-irs
```

### 7.3 Full unit tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/ -q --basetemp=.pytest-tmp-r9-full
```

### 7.4 Audit scans

```powershell
rg -n "pytest\.mark\.skip|pytest\.skip|pytest\.mark\.xfail|xfail\(" tests/unit/compiler/irs tests/unit/test_irs_v6_r0_baseline.py
rg -n "pass\s*$|assert len\([^)]*\) > 0" tests/unit/compiler/irs tests/unit/test_irs_v6_r0_baseline.py
rg -n "Information Requirements Satisfaction|stale|TODO|temporary|legacy primary|bridge-first" docs/implementation/irs-v6 src/nl2spl/compiler src/nl2spl/pipeline
rg -n "nl2spl\.compiler\.irs|IRSRunner|DiagnosticProjector|ConstructSatisfactionReport" src/nl2spl/pipeline/stages/stage11_spl_renderer.py src/nl2spl/pipeline/executable_gate.py src/nl2spl/compiler/producer_index.py
```

扫描命令只提供候选项，最终必须人工判断。

## 8. 验收标准

R9 完成必须满足：

```text
1. 所有 R0-R8 验收项被追溯审计，并在报告中有证据。
2. 文档与代码一致。
3. 无 stale feature flag 描述。
4. IRS 相关测试无 pytest skip / pytest xfail。
5. IRS 相关测试无空测试、无弱断言验收。
6. Renderer 不承担 IRS 判断。
7. Gate / ProducerIndex authority 未被 IRS 替代。
8. internal-comms-3 Issue 3 能由 WORKER_CANDIDATE / WORKER_PROMOTION report 解释。
9. 生成最终审计报告。
10. R9 focused tests 通过。
11. IRS regression tests 通过。
12. full unit tests 通过，或明确说明非 IRS 环境失败并附失败原因。
```

## 9. 审核清单

提交 R9 审核时，必须提供：

```text
1. 修改文件列表。
2. 新增/修改测试列表。
3. R9 focused tests 结果。
4. IRS regression tests 结果。
5. full unit tests 结果。
6. skip / xfail 扫描结果。
7. weak assertion 扫描结果与人工复核结论。
8. feature flag 审计结论。
9. authority boundary 审计结论。
10. test matrix 覆盖表。
11. internal-comms-3 Issue 3 解释证据。
12. 最终审计报告路径。
```

审核时会根据真实代码逐项核验，不接受只看实施报告。

## 10. R9 成功后的状态

R9 通过后，IRS v6 重构可以视为完成以下目标：

```text
1. IRS checker 可新增、可注册、可 runner 调度。
2. Diagnostic 投影集中化。
3. Stage3.5 Worker/Delegation IRS 真实落地。
4. Stage4/Stage7 compatibility wrapper 迁移到 v6 checker。
5. Post-normalize final authority 边界收敛。
6. Construct graph/path/frontier/cutline 数据为未来递归检查预留接口。
7. 未来递归 IRS traversal 是明确的后续工作，而不是当前隐藏实现。
```

