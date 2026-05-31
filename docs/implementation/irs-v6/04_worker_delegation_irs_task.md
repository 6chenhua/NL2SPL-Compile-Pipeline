# Issue 3 实践任务：Worker / Delegation IRS

## 背景

`internal-comms-3` 的 Delegation Policy 包含：

```text
Delegable Work:
- Drafting
- Fact-checking
- Formatting
- Revision history
```

系统识别到 delegation intent 和 candidate task units，但 Stage 3.5b 将候选全部保留在 main worker。原因是缺少 source-backed input contract、output contract、invocation point 和 result handoff。

这个行为本身是保守且合理的。问题是当前系统没有用正式 IRS satisfaction report 解释这一点，而是主要依赖 prompt、decision reason 和 delegation diagnostic。

本任务用 Worker / Delegation IRS 验证 IRS v6 架构是否可扩展。

## 设计目标

1. 将 delegation intent 和 worker candidate 的可物化性转成 IRS slot satisfaction。
2. 保持当前 anti-fabrication 行为：缺 contract 不生成 child worker。
3. 输出结构化 `ConstructSatisfactionReport`，而不只是自然语言 rejection reason。
4. 为未来递归检查预留 parent/path/cutline 信息。

## 推荐新增 / 确认的 ConstructIRS

当前 registry 已有：

```text
WORKER_CANDIDATE
CHILD_WORKER
INVOKE_WORKER
```

本阶段建议新增或细化：

```text
WORKER_HANDOFF
```

如果不新增 `WORKER_HANDOFF`，也可以先把 handoff slots 保留在 `CHILD_WORKER` 和 `INVOKE_WORKER` 中，但长期建议独立。

## Slot 设计

### WORKER_CANDIDATE

| Slot | required_for_partial | required_for_complete | renderable_without | 说明 |
| --- | --- | --- | --- | --- |
| `responsibility` | true | true | false | 候选职责或子任务目的 |
| `delegation_signal` | true | true | false | delegation / subtask source signal |
| `promotion_input_contract` | false | true | true | 晋升 child worker 所需输入 |
| `promotion_output_contract` | false | true | true | 晋升 child worker 所需输出 |
| `promotion_invocation_point` | false | true | true | 父 worker 在哪里调用 |
| `promotion_result_handoff` | false | true | true | 子结果如何交回父 worker |

缺 complete slots 时：

```text
completeness = partial
renderable = false
frontier_status = cutline_partial
diagnostic = type_or_contract_ambiguity
```

### CHILD_WORKER

| Slot | required_for_partial | required_for_complete | 说明 |
| --- | --- | --- | --- |
| `responsibility` | true | true | child worker purpose |
| `input_contract` | true | true | 必须有 source-backed input |
| `output_contract` | true | true | 必须有 source-backed output |
| `invocation_point` | false | true | 调用位置 |
| `result_handoff` | false | true | output binding |

缺 required-for-partial 时：

```text
completeness = blocked
renderable = false
frontier_status = cutline_blocked
```

### WORKER_HANDOFF

| Slot | required_for_partial | required_for_complete | 说明 |
| --- | --- | --- | --- |
| `from_worker` | true | true | parent worker |
| `target` | true | true | child worker 或 API |
| `input_bindings` | true | true | parent -> child |
| `output_bindings` | true | true | child -> parent |
| `failure_policy` | false | false | optional |

## 推荐实现阶段

### Phase W1：接口与 checker 骨架

新增文件建议：

```text
src/nl2spl/compiler/irs/context.py
src/nl2spl/compiler/irs/instance.py
src/nl2spl/compiler/irs/checker.py
src/nl2spl/compiler/irs/runner.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/irs_checker.py
```

本阶段先支持：

```text
WorkerPlanIR.candidates -> WORKER_CANDIDATE reports
WorkerPlanIR.workers[kind=child] -> CHILD_WORKER reports
WorkerPlanIR.handoffs -> WORKER_HANDOFF reports
```

验收标准：

1. checker 可独立单测。
2. runner 可运行 stage3_5 checker。
3. 不修改 WorkerPlanIR。
4. 不改变 child worker 生成结果。

### Phase W2：Stage 3.5 接入

在 Stage 3.5 完成后运行 Worker IRS checker：

```text
worker_plan
-> WorkerIRSChecker
-> construct_satisfaction["stage3_5"]
-> stage_local_diagnostics["stage3_5"]
```

验收标准：

1. `internal-comms-3` 的 4 个 candidate 有 WORKER_CANDIDATE report。
2. 每个 report 显示 responsibility satisfied。
3. input/output/invocation/result_handoff 缺失显示 missing。
4. 不生成 child worker。
5. readable report / feedback report 能说明缺哪些 slot 才能晋升 child worker。

### Phase W3：Cutline 与递归预留字段

所有 Worker IRS reports 必须带：

```text
parent_construct_id
construct_path
frontier_status
cutline_reason
```

示例：

```text
construct_id = worker_candidate:candidate_draft_using_templates
construct_type = WORKER_CANDIDATE
construct_path = ("worker_plan", "candidate_draft_using_templates")
frontier_status = cutline_partial
cutline_reason = missing_promotion_contract
```

验收标准：

1. 缺 contract 的 candidate 不产生 CHILD_WORKER child report。
2. 有完整 contract 的 candidate 可产生 CHILD_WORKER report。
3. report 能表达 parent-child relation。

### Phase W4：Prompt 边界调整

Stage 3.5 prompt 当前已经有 acceptance rules。不要直接塞完整 IRS checklist，避免破坏 JSON 输出格式。

建议只注入短版 checklist：

```text
Promotion to child worker requires source-backed:
- responsibility
- input contract
- output contract
- invocation point
- result handoff
If missing, keep as WORKER_CANDIDATE and explain missing slots.
```

验收标准：

1. JSON 输出格式不退化。
2. LLM reason 与 IRS report slot 缺失一致。
3. 没有因为 prompt 加长导致 candidate 泛滥或 worker 泛滥。

## internal-comms-3 预期行为

输入只有 delegable list，无明确 worker IO contract。

预期：

```text
WORKER_CANDIDATE reports: 4
CHILD_WORKER reports: 0
INVOKE_WORKER steps: 0
type_or_contract_ambiguity diagnostics: present
```

每个 candidate 的 IRS：

```text
responsibility = satisfied
delegation_signal = satisfied
promotion_input_contract = missing
promotion_output_contract = missing
promotion_invocation_point = missing
promotion_result_handoff = missing
completeness = partial
renderable = false
frontier_status = cutline_partial
```

## 正向用例

如果输入包含：

```text
### Drafting Worker
- Inputs: topic, audience, tone, key facts
- Outputs: initial_draft
- Invocation: after evidence gathering
- Result handoff: return initial_draft to main worker for review
```

预期：

```text
WORKER_CANDIDATE complete
CHILD_WORKER complete
WORKER_HANDOFF complete
INVOKE_WORKER allowed
```

## 负向用例

### 只有 delegation label

```text
Delegable Work: Drafting
```

不得生成 child worker。

### 有 output 无 input

```text
Drafting Worker outputs initial_draft.
```

不得生成 child worker。report 应显示 input contract missing。

### 有 worker 名但无 handoff

```text
Use DraftingWorker.
```

不得生成 `INVOKE_WORKER`，除非有 bindings 或明确 handoff contract。

## 可修改文件

优先允许修改：

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/irs/*
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/irs_checker.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
src/nl2spl/pipeline/orchestrator.py
tests/unit/test_worker_irs_checker.py
tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py
tests/unit/test_construct_registry.py
```

谨慎修改：

```text
prompts/stage3_5a_candidate_extractor_system.txt
prompts/stage3_5b_boundary_decision_system.txt
src/nl2spl/pipeline/worker_plan_validator.py
```

不应修改：

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/*
```

Renderer 不应承担 IRS 判断。

## 最终验收标准

1. 新增 Worker IRS 不改变当前保守 worker materialization 行为。
2. 缺少 worker contract 的 delegation intent 不生成 child worker。
3. 缺失原因以 IRS slot satisfaction 形式输出，而不仅是自然语言 reason。
4. Reports 进入 `construct_satisfaction["stage3_5"]`。
5. Diagnostics 进入 `stage_local_diagnostics["stage3_5"]` 和最终 compile diagnostics。
6. Feedback report 能说明晋升 child worker 缺少哪些信息。
7. 所有新增 reports 带 parent/path/cutline 信息或兼容 metadata。
8. 新增 IRS checker 不需要重写 orchestrator 主流程。
