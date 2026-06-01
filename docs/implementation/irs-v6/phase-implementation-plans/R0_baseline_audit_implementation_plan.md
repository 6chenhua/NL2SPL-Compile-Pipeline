# R0 Baseline Audit 实施计划

## 1. 阶段定位

R0 是 IRS v6 重构的基线审计阶段。

目标不是实现 IRS v6，也不是修复现有行为，而是锁定当前 IRS 相关行为，使后续 R1-R9 的改动可以被严格比较和审查。

R0 必须只增加测试和审计文档，不修改生产代码。

```text
R0 = baseline capture
R0 != behavior change
R0 != schema refactor
R0 != checker implementation
```

## 2. 阶段目标

R0 需要完成：

```text
1. 记录当前 full test count。
2. 锁定 Stage 4 EXCEPTION_FLOW IRS 当前行为。
3. 锁定 Stage 7 Step IRS 当前行为。
4. 锁定 Post-normalize IRS 当前行为。
5. 记录 Stage 3.5 IRS checklist 当前实际状态。
6. 记录 Worker/Delegation promotion report 当前缺口。
7. 建立 current-behavior 与 target-future 测试边界。
8. 明确本阶段不引入任何 LLM/rule-based 新语义逻辑。
```

## 3. 允许修改范围

R0 允许修改：

```text
tests/unit/
tests/integration/            # 如果项目已有该目录并适合放 orchestrator 级测试
docs/implementation/irs-v6/
```

R0 不允许修改：

```text
src/nl2spl/
prompts/
examples/
output/
```

如果确实发现生产代码存在明显 bug，也只能在 R0 文档中记录，不应在 R0 修复。

## 4. 禁止事项

```text
1. 不修改生产代码。
2. 不新增 IRS v6 runtime module。
3. 不新增 feature flag。
4. 不接 orchestrator。
5. 不迁移 Stage 4 / Stage 7 checker。
6. 不实现 Worker/Delegation checker。
7. 不用 rule-based 方式补偿语义理解缺口。
8. 不调用 LLM 实现任何新增逻辑。
9. 不用 skip 掩盖失败。
10. current-behavior baseline tests 不允许 xfail。
```

## 5. LLM / Rule-based 决策约束

R0 理论上不需要新增任何语义处理逻辑，因此不应出现 LLM/rule-based 实现选择。

如果实施者认为某个 baseline 测试需要生成语义判断，例如：

```text
判断一个 span 是否真的表达 delegation intent
判断一个 REQUEST_INPUT 是否有 ask signal
判断一个 API mention 是否等于 executable CALL_API
判断一个 candidate 是否应该晋升 child worker
```

则不得直接写 rule-based 逻辑进入生产代码，也不得把复杂语义判断硬编码进测试 helper 作为事实来源。

处理方式：

```text
1. 测试应使用人工构造的 IR fixture 明确表达输入状态。
2. 只断言当前 checker / validator 对该 IR fixture 的既有行为。
3. 如果需要 LLM 或规则来判断真实自然语言语义，必须先向用户确认实现方式。
```

R0 的原则是：测试 fixture 可以手工构造；生产语义判断不新增。

## 6. 建议测试文件

可以新增一个聚合 baseline 文件：

```text
tests/unit/test_irs_v6_r0_baseline.py
```

也可以在现有测试附近补充：

```text
tests/unit/test_flow_assembler.py
tests/unit/test_step_extractor.py
tests/unit/test_normalizer.py
tests/unit/test_executable_gate.py
tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py
```

推荐优先使用聚合文件，便于阶段审核。

## 7. 必须覆盖的 baseline

### 7.1 Stage 4 EXCEPTION_FLOW IRS

目标：锁定当前 Stage 4 IRS checker 对 exception flow 的行为。

建议测试：

```text
test_r0_stage4_condition_with_spans_is_partial_renderable
test_r0_stage4_condition_without_spans_reports_type_contract_ambiguity
test_r0_stage4_does_not_emit_missing_handler
```

验收点：

```text
1. condition_text + spans -> condition slot satisfied。
2. condition_text + no spans -> type_or_contract_ambiguity。
3. Stage 4 不负责 missing_handler。
4. report.construct_type == EXCEPTION_FLOW。
5. 当前函数式 checker 仍能直接调用。
```

### 7.2 Stage 7 Step IRS

目标：锁定当前 Stage 7 IRS checker 对 StepIR 的行为。

建议测试：

```text
test_r0_stage7_general_command_without_source_is_not_renderable
test_r0_stage7_request_input_without_source_reports_contract_ambiguity
test_r0_stage7_call_api_requires_integration_ref_and_source
test_r0_stage7_invoke_worker_requires_target_and_handoff
```

验收点：

```text
1. GENERAL_COMMAND 无 source_span_ids -> assumed_command_not_renderable。
2. REQUEST_INPUT 无 source_span_ids -> type_or_contract_ambiguity。
3. CALL_API 缺 integration_ref 或 source evidence -> type_or_contract_ambiguity。
4. INVOKE_WORKER 缺 integration_ref 或 handoff_id -> type_or_contract_ambiguity。
5. 当前 checker 仍直接创建 CompileDiagnostic，这是 R0 记录，不在 R0 修复。
```

### 7.3 Post-normalize IRS

目标：锁定 PostNormalizeIRSChecker 当前 final construct-level diagnostics 行为。

建议测试：

```text
test_r0_post_normalize_missing_handler_emits_once
test_r0_post_normalize_required_output_without_producer
test_r0_post_normalize_assumed_command_not_renderable
```

验收点：

```text
1. exception flow 无真实 handler -> missing_handler。
2. required output 无 producer -> missing_output_producer。
3. 无 source evidence 且非 compiler scaffolding step -> assumed_command_not_renderable。
4. diagnostic_id / kind / target_ref / blocks_completion 基线明确。
```

### 7.4 Stage 3.5 IRS checklist 当前状态

目标：记录当前 `irs_checklist_for_stage("stage3_5")` 的真实行为。

建议测试：

```text
test_r0_stage3_5_irs_checklist_current_state
```

验收点：

```text
1. 明确当前 stage3_5 checklist 是否为空。
2. 如果为空，测试名称和断言必须说明这是 current baseline，不是目标行为。
3. 不在 R0 修改 prompt builder。
```

### 7.5 Worker/Delegation promotion 缺口

目标：记录当前系统无法用 IRS satisfaction report 解释 promotion blocked 的缺口。

建议测试：

```text
test_r0_worker_candidate_has_no_worker_promotion_report_current_baseline
test_target_worker_promotion_report_for_incomplete_delegation
```

验收点：

```text
1. current baseline test 必须 pass，断言当前没有 WORKER_PROMOTION report。
2. target-future test 可以 xfail，但必须 strict=True。
3. xfail reason 必须关联 R4 Worker/Delegation Checker。
4. 不允许 skip。
```

## 8. xfail 规则

R0 中允许 target-future xfail，但必须满足：

```text
1. current-behavior baseline tests 不允许 xfail。
2. xfail 只能用于目标行为测试。
3. xfail 必须 strict=True。
4. xfail reason 必须包含后续任务编号，例如 R4。
5. 如果 target test XPASS，必须移除 xfail 或升级为正式验收测试。
```

示例：

```python
@pytest.mark.xfail(
    reason="R4 will add WORKER_PROMOTION reports for incomplete delegation.",
    strict=True,
)
def test_target_worker_promotion_report_for_incomplete_delegation():
    ...
```

## 9. 测试命令

R0 提交审核时至少提供：

```powershell
pytest tests/unit/test_irs_v6_r0_baseline.py -v
pytest tests/unit/ -q
```

如果分散修改到邻近测试文件，还必须运行对应邻近测试：

```powershell
pytest tests/unit/test_flow_assembler.py tests/unit/test_step_extractor.py tests/unit/test_normalizer.py -v
pytest tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py -v
```

## 10. 审核清单

审核时我会逐条核验：

```text
1. git diff 中是否只有测试和文档。
2. 是否没有 src/nl2spl 生产代码改动。
3. 是否没有 prompt 改动。
4. current-behavior tests 是否全部 pass。
5. target-future tests 若存在，是否 strict xfail 且 reason 关联任务编号。
6. 是否没有 skip。
7. 是否没有空断言、弱断言或仅检查“不报错”的测试。
8. 是否真实调用 Stage 4 / Stage 7 / PostNormalizeIRSChecker，而不是只 mock。
9. 是否记录当前 full test count。
10. 是否未引入新的 rule-based 语义判断。
```

## 11. 提交审核时需要填写的信息

实施者提交 R0 审核时，请提供：

```text
1. 修改文件列表。
2. 新增测试列表。
3. 每个测试覆盖的 baseline 行为。
4. xfail 列表及 reason。
5. 执行的测试命令。
6. 测试结果。
7. 是否修改生产代码：必须为否。
8. 是否引入 LLM/rule-based 新逻辑：必须为否。
9. 当前 full test count。
10. 已知风险或后续阶段依赖。
```

## 12. R0 完成标准

R0 完成必须满足：

```text
1. baseline tests 已覆盖 Stage 4 / Stage 7 / Post-normalize / Stage3.5 checklist / Worker promotion 缺口。
2. full unit test suite 通过。
3. 没有生产代码改动。
4. 没有 prompt 改动。
5. 没有 skip。
6. current baseline 不使用 xfail。
7. target-future xfail 合规。
8. 进度跟踪 HTML 的 R0 区块已填写。
```

