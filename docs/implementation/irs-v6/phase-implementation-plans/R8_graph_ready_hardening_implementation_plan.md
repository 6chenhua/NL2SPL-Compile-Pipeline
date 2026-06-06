# R8 Graph-ready Hardening 实施计划

## 1. 阶段定位

R8 的目标来自 `07_irs_v6_refactor_tasks.md`：

```text
补齐未来递归 IRS checker 所需的 graph 数据，
但不实现递归 traversal。
```

R8 是 IRS v6 递归能力的前置准备阶段。它只做 graph 数据结构、edge 生成、path 稳定性和 snapshot 测试，不改变现有 checker 的 slot satisfaction 语义，不改变 pipeline 输出，不改变 renderer，不改变 final SPL。

当前真实状态：

```text
src/nl2spl/compiler/irs/graph.py
    已有 ConstructEdge / ConstructGraph / ConstructEdgeType。
    目前只是薄 dataclass，缺少稳定排序、去重、snapshot helper。

WorkerDelegationIRSChecker
    已有少量 related_edges:
        WORKER_CANDIDATE -> WORKER_PROMOTION: promotes_to
        WORKER_HANDOFF -> CHILD_WORKER: invokes

Stage4ExceptionFlowIRSChecker
    当前有 construct_path/source_span_ids/frontier/cutline，
    但没有 related_edges。

Stage7StepIRSChecker
    当前有 construct_path/source_span_ids，
    但没有 produces/consumes/invokes/handoff edges。
```

R8 完成后，`ConstructSatisfactionReport.related_edges` 应该能表达主要 DAG 关系，并且这些关系有稳定、可测试、可序列化的 snapshot 表示。

## 2. 设计边界

### 2.1 R8 做什么

```text
1. 强化 ConstructGraph / ConstructEdge 的稳定表示能力。
2. 为现有 v6 checkers 补充 related_edges。
3. 统一 virtual node id 命名，例如 variable:{name} / condition:{flow_id}。
4. 增加 edge snapshot tests，锁定顺序、去重、metadata。
5. 确保 construct_path 仍表达 primary containment path。
```

### 2.2 R8 不做什么

```text
1. 不实现 recursive traversal。
2. 不新增 RecursiveIRSEvaluator。
3. 不让 checker 下钻检查 child construct IRS。
4. 不修改 renderer。
5. 不修改 final SPL。
6. 不修改 Stage 2-11 生成逻辑。
7. 不新增 LLM 调用。
8. 不新增 raw NL keyword semantic rules。
```

## 3. 可修改文件

R8 允许修改：

```text
src/nl2spl/compiler/irs/graph.py
src/nl2spl/compiler/irs/checkers/worker_delegation.py
src/nl2spl/compiler/irs/checkers/exception_flow.py
src/nl2spl/compiler/irs/checkers/step.py
tests/unit/compiler/irs/test_construct_graph.py
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
tests/unit/compiler/irs/test_r6_exception_flow_checker.py
tests/unit/compiler/irs/test_r6_step_checker.py
tests/unit/compiler/irs/test_r6_runner_stage4_stage7.py
docs/implementation/irs-v6/
```

如确实需要新增专门测试文件，建议：

```text
tests/unit/compiler/irs/test_r8_graph_ready_hardening.py
```

R8 禁止修改：

```text
prompts/**
examples/**
output/**
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/pipeline/stages/**
src/nl2spl/compiler/diagnostic_analyzer.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py
src/nl2spl/compiler/irs/runner.py
src/nl2spl/compiler/irs/projector.py
```

如果实现者认为必须修改禁止范围，必须先提交设计问题说明，不能直接扩大 R8 scope。

## 4. LLM / Rule-based 决策约束

R8 不需要 LLM，也不允许新增 raw NL rule-based 语义判断。

允许的 edge 生成来源只能是结构化 IR 字段：

```text
WorkerPlanIR.workers / candidates / handoffs / decisions
WorkerSpecIR.worker_id / worker_name / owned_span_ids / input_contract / output_contract
WorkerHandoffIR.handoff_id / from_worker / to_worker / mode / input_bindings / output_bindings / invoke_location_hint
ExceptionFlow.flow_id / condition_text / spans
StepIR.step_id / command_type / inputs / outputs / integration_ref / handoff_id / source_span_ids
IRSCheckContext.flow / worker_flows / steps / worker_steps / worker_plan
```

如果某条 edge 需要判断自然语言语义，例如“这个文本是否真正表示 API call action / handler action / ask signal”，必须停止并向用户确认实现方式。R8 只能表达已有结构关系，不能重新解释 NL。

## 5. Stable Node ID 约定

R8 必须统一 graph node id，避免各 checker 临时发明不同命名。

建议约定：

| 节点类型 | ID 格式 | 说明 |
| --- | --- | --- |
| Worker candidate | `worker_candidate:{candidate_id}` | 已存在 |
| Worker promotion | `worker_promotion:{candidate_id}` | 已存在 |
| Child worker | `child_worker:{worker_id}` | 已存在 |
| Worker handoff | `worker_handoff:{handoff_id}` | 已存在 |
| Legacy exception flow | `exception_flow:{flow_id}` | Stage 4 legacy path |
| Worker-scoped exception flow | `worker:{worker_id}.exception_flow:{flow_id}` | Stage 4 worker path |
| Legacy step | `step:{step_id}` | Stage 7 legacy path |
| Worker-scoped step | `worker:{worker_id}.step:{step_id}` | Stage 7 worker path |
| Variable | `variable:{name}` | Virtual graph node，不生成 report |
| Worker-scoped variable | `worker:{worker_id}.variable:{name}` | 当 worker_id 已知时使用 |
| Exception condition | `condition:{flow_id}` | Virtual graph node，不生成 report |
| Worker-scoped condition | `worker:{worker_id}.condition:{flow_id}` | 当 worker_id 已知时使用 |

Virtual graph node 只允许出现在 `ConstructEdge.to_id/from_id` 中，不应创建 `ConstructSatisfactionReport`，也不应触发 IRS checker。

## 6. Edge 生成矩阵

R8 应优先实现以下 edge。实现时只使用当前 checker context 已可见的信息。

| 来源 checker | Edge | 触发条件 | 说明 |
| --- | --- | --- | --- |
| WorkerDelegation | `WORKER_CANDIDATE promotes_to WORKER_PROMOTION` | 每个 worker/delegation candidate | 已有，R8 需补 source spans / metadata / snapshot。 |
| WorkerDelegation | `WORKER_PROMOTION blocked_by missing slot` | promotion blocked 且有 missing slots | `to_id` 可用 `missing_slot:{promotion_id}:{slot_name}` virtual node。 |
| WorkerDelegation | `WORKER_HANDOFF handoff_to CHILD_WORKER` | invoke handoff target worker 有效 | 当前 edge_type 是 `invokes`，R8 需要决定是否改为 `handoff_to` 或同时保留 `invokes`。建议 WORKER_HANDOFF 使用 `handoff_to`。 |
| WorkerDelegation | `WORKER_HANDOFF derived_from WORKER_CANDIDATE` | 能用结构化 span overlap / accepted decision 精确绑定时 | 只能使用已有结构化匹配，不新增 text rule。 |
| Stage4 ExceptionFlow | `EXCEPTION_FLOW handles CONDITION` | exception flow 有 condition_text 或 spans | condition 是 virtual node。 |
| Stage4 ExceptionFlow | `WORKER contains EXCEPTION_FLOW` | worker-scoped path 有 worker_id | legacy path 不强造 worker。 |
| Stage7 Step | `STEP consumes VARIABLE` | `StepIR.inputs` 非空 | variable 是 virtual node。 |
| Stage7 Step | `STEP produces VARIABLE` | `StepIR.outputs` 非空 | variable 是 virtual node。 |
| Stage7 Step | `INVOKE_WORKER invokes CHILD_WORKER` | command_type=`INVOKE_WORKER` 且 `integration_ref` 非空 | 不验证 worker 是否存在；只表达 StepIR 中已有引用。 |
| Stage7 Step | `INVOKE_WORKER handoff_to WORKER_HANDOFF` | command_type=`INVOKE_WORKER` 且 `handoff_id` 非空 | `to_id=worker_handoff:{handoff_id}`。 |
| Stage7 Step | `CALL_API invokes api:{integration_ref}` | command_type=`CALL_API` 且 `integration_ref` 非空 | 可作为 virtual node；若觉得 `api:{name}` 节点未定义，应先在 R8.1 讨论并测试。 |

R8 不要求实现 `FLOW contains BLOCK` / `BLOCK contains STEP`，因为当前 R8 可修改文件不包含 block assembler / worker assembler / renderer，且 Stage 4/7 checker context 不总是具备 block plan。应在文档和 tests 中明确这是 R8 后续可扩展项，而不是用不完整 context 强造 edge。

## 7. 任务拆分

### R8.1 Graph API Baseline And Snapshot Contract

Priority: P1

Goal:

为 `ConstructEdge` / `ConstructGraph` 增加稳定 snapshot 能力，并锁定当前 edge type。

Files:

```text
src/nl2spl/compiler/irs/graph.py
tests/unit/compiler/irs/test_construct_graph.py
```

Implementation notes:

```text
1. 可新增 helper：
   - ConstructEdge.key()
   - ConstructEdge.to_snapshot()
   - ConstructGraph.add_edge()
   - ConstructGraph.edge_snapshots()
   - ConstructGraph.deduped()
2. snapshot 必须稳定排序：
   - edge_type
   - from_id
   - to_id
   - sorted(source_span_ids)
   - stable metadata keys
3. 不要引入 traversal / DFS / BFS。
4. metadata 只做序列化，不做语义解释。
```

Acceptance criteria:

```text
1. ConstructEdge snapshot deterministic。
2. ConstructGraph dedupe 不丢不同 edge_type / from_id / to_id。
3. source_span_ids 顺序变化不影响 edge key。
4. metadata snapshot keys 稳定。
5. 无 recursive traversal API。
```

### R8.2 Worker/Delegation Edge Hardening

Priority: P1

Goal:

增强 `WorkerDelegationIRSChecker` 的 related_edges，使 candidate/promotion/handoff/worker 关系更接近未来 recursive graph 所需形状。

Files:

```text
src/nl2spl/compiler/irs/checkers/worker_delegation.py
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
tests/unit/compiler/irs/test_r8_graph_ready_hardening.py
```

Implementation notes:

```text
1. 保留 candidate -> promotion 的 promotes_to edge。
2. 对 blocked promotion，为每个 missing promotion slot 添加 blocked_by edge。
3. WORKER_HANDOFF 指向 child worker 时优先使用 handoff_to edge。
4. 如保留旧 invokes edge，必须解释兼容原因并加测试。
5. related_edges 必须带 source_span_ids。
6. related_edges metadata 可包括：
   - candidate_id
   - handoff_id
   - missing_slot
   - target_worker_id
   - edge_source="worker_plan"
7. 不修改 WorkerPlanIR。
```

Acceptance criteria:

```text
1. incomplete promotion 产生 blocked_by edges，数量等于 missing slots。
2. complete promotion 不产生 blocked_by edges。
3. valid invoke handoff 产生 handoff_to child worker edge。
4. invalid target 不产生 handoff_to edge。
5. 多 candidate / 多 handoff 不串线。
6. edge snapshot 稳定。
```

### R8.3 Stage4 ExceptionFlow Edges

Priority: P1

Goal:

为 `Stage4ExceptionFlowIRSChecker` 的 reports 增加 exception flow 相关 graph edges。

Files:

```text
src/nl2spl/compiler/irs/checkers/exception_flow.py
tests/unit/compiler/irs/test_r6_exception_flow_checker.py
tests/unit/compiler/irs/test_r8_graph_ready_hardening.py
```

Implementation notes:

```text
1. 每个 EXCEPTION_FLOW report 添加 handles edge：
   - from_id = report.construct_id
   - to_id = condition node id
   - edge_type = "handles"
   - source_span_ids = ExceptionFlow.spans
   - metadata.condition_text = condition_text
2. worker-scoped path 添加 contains edge：
   - from_id = worker:{worker_id}
   - to_id = worker:{worker_id}.exception_flow:{flow_id}
   - edge_type = "contains"
3. legacy path 不强造 worker contains edge。
4. 不改变 Stage 4 missing_handler 时机。
5. 不改变 condition satisfaction。
```

Acceptance criteria:

```text
1. source-backed exception flow 有 handles condition edge。
2. condition-only / no spans 的 edge source_span_ids 为空但仍稳定。
3. worker-scoped exception flow 有 worker contains edge。
4. Stage 4 不产生 missing_handler。
5. report.related_edges snapshot 稳定。
```

### R8.4 Stage7 Step Variable And Invocation Edges

Priority: P1

Goal:

为 `Stage7StepIRSChecker` 增加 step-level produces / consumes / invokes / handoff_to edges。

Files:

```text
src/nl2spl/compiler/irs/checkers/step.py
tests/unit/compiler/irs/test_r6_step_checker.py
tests/unit/compiler/irs/test_r8_graph_ready_hardening.py
```

Implementation notes:

```text
1. 所有 supported command type：
   - inputs -> consumes variable edges
   - outputs -> produces variable edges
2. INVOKE_WORKER：
   - integration_ref -> invokes child_worker edge
   - handoff_id -> handoff_to worker_handoff edge
3. CALL_API：
   - integration_ref -> invokes api:{integration_ref} edge
   - 如果实现者认为 api virtual node 不应进入 graph，必须先提出设计问题。
4. worker-scoped step variable 使用 worker-scoped variable id。
5. legacy step variable 使用 variable:{name}。
6. 不新增 ask/call/action keyword 判断。
```

Acceptance criteria:

```text
1. StepIR.inputs 产生 consumes edges。
2. StepIR.outputs 产生 produces edges。
3. INVOKE_WORKER 产生 invokes / handoff_to edges。
4. CALL_API 产生 API invocation edge，或有明确设计说明并对应测试。
5. DISPLAY_MESSAGE / unknown command type 仍不产生 instance。
6. 不修改 StepIR。
7. edge snapshot 稳定。
```

### R8.5 Construct Path Stability

Priority: P2

Goal:

锁定所有 v6 checker 的 `construct_path` 为 tuple，表达 primary containment path，不把 DAG edge 塞进 path。

Files:

```text
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
tests/unit/compiler/irs/test_r6_exception_flow_checker.py
tests/unit/compiler/irs/test_r6_step_checker.py
tests/unit/compiler/irs/test_r8_graph_ready_hardening.py
```

Implementation notes:

```text
1. WORKER_CANDIDATE:
   ("worker_plan", "candidates", candidate_id)
2. WORKER_PROMOTION:
   ("worker_plan", "promotion", candidate_id)
3. CHILD_WORKER:
   ("worker_plan", "workers", worker_id)
4. WORKER_HANDOFF:
   ("worker_plan", "handoffs", handoff_id)
5. EXCEPTION_FLOW:
   ("flow", "exception_flows", flow_id)
   ("worker_flow_plan", worker_id, "exception_flows", flow_id)
6. STEP:
   ("steps", step_id)
   ("worker_step_plan", worker_id, "steps", step_id)
```

Acceptance criteria:

```text
1. 所有 construct_path 是 tuple。
2. construct_path 不包含 variable/api/condition virtual node。
3. DAG 关系只进入 related_edges。
```

### R8.6 Runner-Level Edge Snapshot Tests

Priority: P2

Goal:

证明通过 `IRSRunner` 执行时，reports 中的 related_edges 能稳定输出，不依赖 checker 直接调用。

Files:

```text
tests/unit/compiler/irs/test_r6_runner_stage4_stage7.py
tests/unit/compiler/irs/test_r8_graph_ready_hardening.py
```

Implementation notes:

```text
1. 用 runner 跑 stage3_5 / stage4 / stage7。
2. 收集所有 report.related_edges。
3. 转成 snapshot。
4. 断言 snapshot 精确匹配。
```

Acceptance criteria:

```text
1. runner stage4 snapshot 包含 EXCEPTION_FLOW handles edge。
2. runner stage7 snapshot 包含 STEP produces/consumes edges。
3. runner stage3_5 snapshot 包含 worker promotion/handoff edges。
4. snapshot 排序稳定。
```

## 8. R8 后显式不完成项

R8 完成后仍不应实现：

```text
1. RecursiveIRSEvaluator。
2. graph traversal。
3. child construct 自动检查。
4. FLOW contains BLOCK / BLOCK contains STEP 的完整 graph。
5. Renderer 使用 graph。
6. Gate 使用 graph。
7. ProducerIndex 替换为 graph traversal。
```

这些留给后续阶段。R8 只保证数据形状和 edge 快照已经准备好。

## 9. 必跑测试矩阵

R8 提交审核前必须运行：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs/test_construct_graph.py -q
.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs/test_r4_worker_delegation_checker.py -q
.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs/test_r6_exception_flow_checker.py -q
.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs/test_r6_step_checker.py -q
.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs/test_r6_runner_stage4_stage7.py -q
.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs/test_r8_graph_ready_hardening.py -q
.venv\Scripts\python.exe -m pytest tests/unit/test_irs_v6_r0_baseline.py tests/unit/test_irs_v6_r1_report_schema.py tests/unit/compiler/irs -q
.venv\Scripts\python.exe -m pytest tests/unit/ -q
```

如果没有新增 `test_r8_graph_ready_hardening.py`，必须在实施报告中说明 R8 tests 分布在哪些现有文件，并逐项对应验收标准。

## 10. 审核重点

PM 审核会重点检查：

```text
1. 是否只补 graph 数据，没有实现 traversal。
2. 是否没有新增 LLM。
3. 是否没有新增 raw NL keyword semantic rules。
4. 是否没有修改 renderer / final SPL。
5. related_edges 是否使用稳定 node id。
6. edge snapshot 是否精确断言，而不是 len > 0。
7. source_span_ids 是否保留。
8. metadata 是否稳定、可序列化。
9. construct_path 是否仍是 primary containment path。
10. virtual node 是否只出现在 edges，不生成 report。
11. 多 candidate / 多 handoff / worker-scoped step 是否不串线。
12. 全量测试是否通过。
```

## 11. 实施报告模板

提交 R8 审核时请使用：

```text
R8 Graph-ready Hardening - 提交审核

1. 修改文件列表
   - 生产代码
   - 测试代码
   - 文档

2. Graph API 变更
   - ConstructEdge:
   - ConstructGraph:
   - snapshot / dedup:

3. Edge 生成结果
   - WorkerDelegation:
   - Stage4 ExceptionFlow:
   - Stage7 Step:
   - virtual node id:

4. 明确未实现项
   - recursive traversal:
   - renderer graph usage:
   - final SPL changes:

5. 测试命令和结果
   - construct graph:
   - worker delegation:
   - stage4:
   - stage7:
   - runner:
   - R0-R8 regression:
   - full unit:

6. LLM / rule-based 决策记录
   - 是否新增 LLM 调用：必须为否
   - 是否新增 raw NL rule-based 语义判断：必须为否
   - 如果新增 structural predicate，说明它只读取哪些 IR 字段

7. 已知风险
```

## 12. R8 完成定义

R8 完成必须同时满足：

```text
1. ConstructGraph/ConstructEdge 有稳定 snapshot 能力。
2. WorkerDelegation reports 有 candidate/promotion/handoff 关键 edges。
3. Stage4 EXCEPTION_FLOW reports 有 handles condition edge。
4. Stage7 STEP reports 有 produces/consumes/invokes/handoff edges。
5. report.related_edges 可表达主要 DAG 关系。
6. construct_path 仍表达 primary containment path。
7. edge snapshot 稳定。
8. 不执行 recursive traversal。
9. 不改变 renderer。
10. 不改变 final SPL。
11. 无 LLM 调用。
12. 无新增 raw NL rule-based 语义判断。
13. 全量单元测试通过。
```
