# 05 Downstream Alignment Regression：验证下游阶段与新 FieldRoute 对齐

## 目标

在 adapter-guided LLM FieldRoute 接入后，系统必须证明 downstream stages 没有重新把 mixed semantics 编译错。

本任务关注：

- Stage 4 FlowAssembler；
- Stage 5 BlockAssembler；
- Stage 7 StepExtractor；
- Stage 8 ProfileExtractor；
- Stage 9 ConstraintExtractor；
- diagnostics / provenance / report；
- worker-aware path。

## 背景

R3 会让 FieldRoute annotations 更细：

```text
failure condition
exception handler action candidate
delegation intent
api candidate
worker handoff candidate
delegation boundary constraint
process step
precondition / constraint
```

这会影响 downstream 消费逻辑。

下游不能简单依赖：

```text
routes.behavior
routes.rules
section title
```

而应继续优先使用：

```text
RouteAnnotation
executable
semantic_role
construct_target
slot_target
route_family
provenance
```

## 必须验证的关键行为

### 1. Stage 4：只 materialize condition

输入：

```text
Failure handling:
Missing timeframe: ask one clarifying question.
```

预期：

- `Missing timeframe` -> `ExceptionFlow.condition`；
- `ask one clarifying question` 不应被当成另一个 condition；
- 如果 handler action 只是 candidate，Stage 4 不应虚构 handler block。

### 2. Stage 5：不虚构 handler

如果只有 condition：

```text
Failure handling:
Missing timeframe.
```

预期：

- partial skeleton preserved；
- no fabricated handler block；
- missing handler diagnostic 后续出现。

如果有明确 handler：

```text
Missing timeframe: ask one clarifying question.
```

预期行为需要根据当前 IR 能力确定：

- 如果 handler action 尚未 materialize，至少不能虚构；
- 如果实现 handler candidate downstream materialization，必须 source-backed。

### 3. Stage 7：只提取 executable action

预期：

- failure condition 不产生 `GENERAL_COMMAND`；
- pure delegation intent 不产生 `INVOKE_WORKER`；
- API candidate 不产生 `CALL_API`，除非后续有 valid API contract；
- process step 正常生成 command；
- explicit exception handler action 可作为 handler-scoped action candidate，但不能污染 main flow。

### 4. Stage 9：constraint 仍可被提取

例如：

```text
Only delegate if returned evidence can be normalized.
Do not delegate final approval.
Do not finalize if required slots are missing.
```

预期：

- 这些应进入 constraint extraction；
- pure delegation intent 仍排除；
- failure condition 仍排除。

### 5. Stage 6：resource contracts 不被污染

如果 input/output section 混入行为文本，资源抽取仍应：

- 保留真实 input/output contract；
- 不把 failure condition / delegation intent 变成 variable；
- 对混入行为产生 route conflict 或后续 diagnostic。

### 6. Worker-aware path

预期：

- worker planner 不把 non-executable failure/delegation span 当 child worker source；
- worker-aware Stage 4 仍能 materialize owned failure conditions；
- unowned / ambiguous condition 仍 deterministic fallback + warning；
- delegation candidate 不直接创建 handoff，除非 valid contract 存在。

## 建议修改文件

可修改测试：

- `tests/unit/test_flow_assembler.py`
- `tests/unit/test_block_assembler.py`
- `tests/unit/test_step_extractor.py`
- `tests/unit/pipeline/stages/test_stage7_worker_scoped.py`
- `tests/unit/test_input_adapter_pipeline.py`
- `tests/unit/test_failure_mode_bridge.py`
- `tests/unit/test_provenance.py`
- `tests/unit/test_feedback_report_renderer.py`
- `tests/unit/pipeline/stages/test_worker_aware_flow_assembler.py`
- `tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py`

可修改生产代码：

- downstream consumers only if tests expose actual mismatch；
- Stage 7 prompt/context builder；
- Stage 9 constraint filters；
- Stage 4 materializer if new roles require explicit filtering。

不建议修改：

- InputAdapter；
- FieldRoute prompt / validator，除非发现 R3 contract 本身不足；
- bridge fallback，除非 import/compatibility issue。

## 注意事项

- 这个任务不是新增 FieldRoute LLM 能力，而是验证下游消费不回退。
- 不要为了通过测试删除 diagnostics。
- 不要把 handler action 直接变成 main-flow command。
- 不要从 API candidate 直接生成 `CALL_API`。
- 不要从 worker handoff candidate 直接生成 `INVOKE_WORKER`。
- 不要削弱 D6 executable filtering。
- 不要破坏 D7 provenance exactly-once diagnostic。

## 验收标准

本任务通过需满足：

1. Stage 4 只从 `EXCEPTION_FLOW.condition` materialize exception conditions。
2. Stage 4 不把 handler action candidate 当 condition。
3. Stage 5 不虚构 handler block。
4. Stage 7 不从 failure condition 生成 command。
5. Stage 7 不从 pure delegation intent 生成 `INVOKE_WORKER`。
6. Stage 7 不从 API candidate 生成 `CALL_API`，除非已有 valid API contract。
7. Stage 9 能提取 delegation boundary / prohibition / precondition constraints。
8. Stage 9 仍排除 pure delegation intent 和 failure condition。
9. Stage 6 不把 failure/delegation text 变成 variable。
10. Worker-aware flow materialization 仍保留 failure semantics。
11. Provenance 能追踪到 source section / packet / span。
12. Feedback report 能展示 route conflict 和 missing handler，不重复。
13. Internal-Comms happy path 仍稳定。
14. Mixed structural NL integration test 通过。
15. 全量单元测试通过。

## 最小测试

至少新增或更新：

- `test_stage4_mixed_failure_handler_not_condition`
- `test_stage5_condition_only_still_no_fabricated_handler`
- `test_stage7_failure_condition_not_command_after_llm_refinement`
- `test_stage7_delegation_policy_not_invoke_worker_without_contract`
- `test_stage7_api_candidate_not_call_api_without_contract`
- `test_stage9_delegation_boundary_constraint_survives`
- `test_stage9_reusable_process_precondition_survives`
- `test_stage6_mixed_section_resource_contract_not_polluted`
- `test_worker_aware_mixed_failure_condition_preserved`
- `test_feedback_report_route_conflict_provenance`

## 建议验证命令

至少运行：

```bash
pytest tests/unit/test_flow_assembler.py tests/unit/test_block_assembler.py tests/unit/test_step_extractor.py -q
pytest tests/unit/test_input_adapter_pipeline.py tests/unit/test_failure_mode_bridge.py -q
pytest tests/unit/pipeline/stages/test_stage7_worker_scoped.py tests/unit/pipeline/stages/test_worker_aware_flow_assembler.py -q
pytest tests/unit/ -q
```

## 提交审核时说明

提交时请包含：

- downstream 受影响文件；
- mixed failure handling 的 Stage 4 / Stage 7 输出摘要；
- mixed delegation policy 的 Stage 7 / Stage 9 输出摘要；
- worker-aware path 是否受影响；
- diagnostics / provenance 示例；
- 全量测试结果。
