# 案例：WorkerDelegationIRSChecker

首个 v6-style IRS checker，检查 Stage 3.5 的 Worker/Delegation 相关 construct。

> 源码：`src/nl2spl/compiler/irs/checkers/worker_delegation.py`

---

## 检查的 Construct 类型

| Construct Type | 含义 | 状态 |
|---|---|---|
| `WORKER_CANDIDATE` | 源文本中的 delegation/subtask signal | report-only，不渲染 |
| `WORKER_PROMOTION` | candidate 是否可晋升 child worker | report-only，不渲染 |
| `CHILD_WORKER` | 已 materialized 的子 worker | 可渲染 |
| `WORKER_HANDOFF` | parent → child 的交接 | 可渲染 |

---

## 核心语义：Candidate vs Promotion

**这是最容易混淆的点**：

```text
WORKER_CANDIDATE:
  "源文本提出了一个可能的 worker/subtask demand"
  candidate_satisfaction = complete / partial / blocked
  renderable = false（candidate 本身不是 SPL construct）

WORKER_PROMOTION:
  "该 candidate 是否具备晋升为 CHILD_WORKER 的条件"
  promotion_status = ready / blocked
  需要：input_contract + output_contract + invocation_point + result_handoff
```

**candidate complete ≠ promotion ready**。Candidate 完整只说明"源文本有 delegation signal"，Promotion 需要完整的 IO contract。

---

## Slot 设计

### WORKER_CANDIDATE

| Slot | required_for_partial | required_for_complete | 说明 |
|---|---|---|---|
| `responsibility` | true | true | 候选职责 |
| `delegation_signal` | true | true | delegation 信号 |

### WORKER_PROMOTION

| Slot | required_for_partial | required_for_complete | 说明 |
|---|---|---|---|
| `promotion_input_contract` | true | true | 所需输入 |
| `promotion_output_contract` | true | true | 所需输出 |
| `promotion_invocation_point` | true | true | 调用位置 |
| `promotion_result_handoff` | true | true | 结果交接 |
| `independent_callable_value` | false | true | 独立调用价值 |

### CHILD_WORKER

| Slot | required_for_partial | required_for_complete | 说明 |
|---|---|---|---|
| `responsibility` | true | true | child 目的 |
| `input_contract` | true | true | source-backed 输入 |
| `output_contract` | true | true | source-backed 输出 |
| `invocation_point` | false | true | 调用位置 |
| `result_handoff` | false | true | output binding |

### WORKER_HANDOFF

| Slot | required_for_partial | required_for_complete | 说明 |
|---|---|---|---|
| `from_worker` | true | true | parent worker |
| `target` | true | true | child worker / API |
| `invocation_site` | true | true | 明确调用位置 |
| `input_bindings` | true | true | parent → child |
| `output_bindings` | true | true | child → parent |
| `failure_policy` | false | false | optional |

---

## 实例提取逻辑

```text
WorkerPlanIR.candidates[]
  → WORKER_CANDIDATE  (materialized=F, source_demanded=T, candidate_only=T)
  → WORKER_PROMOTION  (materialized=F, source_demanded=T, candidate_only=T)

WorkerPlanIR.workers[kind!=main]
  → CHILD_WORKER      (materialized=T, source_demanded=T, candidate_only=F)

WorkerPlanIR.handoffs
  → WORKER_HANDOFF    (materialized=T, source_demanded=T, candidate_only=F)
```

---

## internal-comms-3 预期行为

输入只有 delegable list，无明确 worker IO contract：

```text
WORKER_CANDIDATE reports: 4
WORKER_PROMOTION reports: 4
CHILD_WORKER reports: 0
WORKER_HANDOFF reports: 0
INVOKE_WORKER steps: 0
type_or_contract_ambiguity diagnostics: present
```

每个 candidate：
```text
responsibility = satisfied
delegation_signal = satisfied
candidate_satisfaction = complete
renderable = false
frontier_status = leaf
```

每个 promotion：
```text
promotion_input_contract = missing
promotion_output_contract = missing
promotion_invocation_point = missing
promotion_result_handoff = missing
promotion_readiness = blocked
frontier_status = cutline_blocked
cutline_reason = missing_promotion_contract
```

---

## 正向用例

输入包含完整 contract：
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
WORKER_PROMOTION complete
CHILD_WORKER complete
WORKER_HANDOFF complete
INVOKE_WORKER allowed
```

---

## 负向用例

| 输入 | 预期 |
|---|---|
| `Delegable Work: Drafting` | candidate complete, promotion blocked, no child worker |
| `Drafting Worker outputs initial_draft.` | promotion blocked (missing input contract) |
| `Use DraftingWorker.` | no INVOKE_WORKER (no bindings + invocation site) |
