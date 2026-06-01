# R4 Worker/Delegation Checker 实施计划

## 1. 阶段定位

R4 是 IRS v6 的第一个真实 checker 落地阶段。目标不是改变 worker materialization，而是把 Stage 3.5 已经产生的 `WorkerPlanIR` 结构解释成可审计的 IRS satisfaction reports。

本阶段必须解决的问题是：

```text
Worker candidate 存在
≠
可以晋升为 child worker
≠
可以生成 INVOKE_WORKER
```

R4 要把这三件事分开表达：

```text
WORKER_CANDIDATE:
    说明 source / upstream stage 已经识别到一个候选任务边界。

WORKER_PROMOTION:
    说明该候选是否具备晋升为 child worker 的契约条件。

CHILD_WORKER:
    说明已经 materialized 的 child worker 是否有完整 worker contract。

WORKER_HANDOFF:
    说明已经 materialized 的 handoff 是否有 input/output/invocation/result binding。
```

R4 只做检查和报告，不生成新 worker，不生成 handoff，不生成 `INVOKE_WORKER`，不修改 `WorkerPlanIR`。

## 2. 设计边界

### 2.1 允许做的事情

```text
1. 从 WorkerPlanIR.candidates 提取 WORKER_CANDIDATE instance。
2. 从 WorkerPlanIR.candidates 提取 WORKER_PROMOTION instance。
3. 从 WorkerPlanIR.workers 中的 child/api_adapter worker 提取 CHILD_WORKER instance。
4. 从 WorkerPlanIR.handoffs 提取 WORKER_HANDOFF instance。
5. 基于已有结构化 IR 字段计算 slot satisfaction。
6. 通过 ConstructSatisfactionReport + SlotSatisfaction 表达缺失槽位。
7. 通过 R3 DiagnosticProjector 投影 type_or_contract_ambiguity。
8. 让 R0 中 R4 目标 xfail 转为正式通过测试。
```

### 2.2 禁止做的事情

```text
1. 禁止调用 LLM。
2. 禁止重新解析 raw NL。
3. 禁止用字符串关键词从 task_text / purpose 中推断 input/output/invocation/handoff。
4. 禁止修改 WorkerPlanIR、WorkerSpecIR、WorkerHandoffIR、CandidateTaskUnitIR。
5. 禁止生成 child worker。
6. 禁止生成 WorkerHandoffIR。
7. 禁止生成 INVOKE_WORKER / CALL_API step。
8. 禁止修改 Stage 3.5 planner/materializer 的 worker 决策行为。
9. 禁止修改 orchestrator 接入逻辑；R5 才做 runner 接入。
10. 禁止改 prompts/examples/output。
```

### 2.3 LLM / rule-based 决策约束

R4 不涉及新的语义理解。它只能消费已有 IR 中的结构化字段：

```text
CandidateTaskUnitIR.source_span_ids
CandidateTaskUnitIR.task_text
CandidateTaskUnitIR.purpose
CandidateTaskUnitIR.candidate_kind
CandidateTaskUnitIR.possible_inputs
CandidateTaskUnitIR.possible_outputs
CandidateTaskUnitIR.signals
CandidateTaskUnitIR.risks
WorkerBoundaryDecisionIR.decision
WorkerBoundaryDecisionIR.rejection_reason
WorkerSpecIR.input_contract
WorkerSpecIR.output_contract
WorkerHandoffIR.input_bindings
WorkerHandoffIR.output_bindings
WorkerHandoffIR.invoke_location_hint
```

允许的判断是“结构字段是否存在 / 是否为空 / 是否引用一致”。例如：

```text
possible_inputs 非空 -> promotion_input_contract satisfied
risks 包含 no_clear_input_contract -> promotion_input_contract missing
handoff.output_bindings 非空 -> result_handoff satisfied
handoff.invoke_location_hint 有 after_span_id 或 before_span_id -> invocation_site satisfied
```

不允许的判断是“从自然语言文本推断语义”。例如：

```text
task_text 包含 "delegate" -> 有 delegation_signal
purpose 包含 "draft" -> 有 output contract
task_text 包含 "when" -> 有 invocation point
```

如果实施时发现某个槽位只能通过 NL 语义判断才能可靠得出，必须暂停该槽位实现并向用户确认采用 LLM、rule-based，或延后到后续阶段。不得自行选择 rule-based 关键词方案。

## 3. 可修改文件范围

### 3.1 生产代码

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/irs/checkers/__init__.py
src/nl2spl/compiler/irs/checkers/worker_delegation.py
```

说明：

```text
construct_registry.py:
    只允许补齐 WORKER_PROMOTION / WORKER_HANDOFF construct specs，
    以及在必要时细化 WORKER_CANDIDATE slot 描述。

worker_delegation.py:
    新增 WorkerDelegationIRSChecker。

checkers/__init__.py:
    导出 checker 类型。
```

### 3.2 测试代码

```text
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
tests/unit/test_irs_v6_r0_baseline.py
```

说明：

```text
test_r4_worker_delegation_checker.py:
    R4 主验收测试。

test_irs_v6_r0_baseline.py:
    移除或改写 R4 target xfail，使其成为正式 passing acceptance test。
```

### 3.3 禁止修改文件

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/**
src/nl2spl/pipeline/stages/stage7_step_extractor/**
src/nl2spl/pipeline/stages/stage9_5_normalizer/**
src/nl2spl/pipeline/executable_gate.py
prompts/**
examples/**
output/**
```

若实施过程中确实发现必须修改禁止范围内文件，先停止并说明原因，不能直接扩展范围。

## 4. Construct Registry 设计

### 4.1 WORKER_CANDIDATE

当前 registry 已有 `WORKER_CANDIDATE`，但它把 promotion slots 放在 candidate construct 内，容易造成语义混淆。

R4 应调整为：

```text
WORKER_CANDIDATE:
    表达候选任务边界本身是否成立。
    不表达是否可以晋升 child worker。
```

建议槽位：

```text
responsibility
delegation_signal
source_evidence
```

验收重点：

```text
candidate complete 不等于 promotion ready。
candidate report 本身不应因为缺 input/output/handoff 而变成 incomplete。
```

### 4.2 WORKER_PROMOTION

新增 `WORKER_PROMOTION` construct spec。

职责：

```text
表达候选任务是否具备晋升 child worker 的必要条件。
```

建议槽位：

```text
promotion_input_contract
promotion_output_contract
promotion_invocation_point
promotion_result_handoff
```

槽位缺失时：

```text
diagnostic_kind = type_or_contract_ambiguity
frontier_status = cutline_partial
cutline_reason = promotion_blocked
metadata["promotion_status"] = "blocked"
metadata["promotion_candidate_id"] = candidate_id
metadata["promotion_missing_slots"] = [...]
```

完整时：

```text
metadata["promotion_status"] = "ready"
renderable = false
```

注意：`WORKER_PROMOTION` 是分析 construct，不是可渲染 SPL construct，因此即使 ready 也不直接 render。

### 4.3 WORKER_HANDOFF

新增 `WORKER_HANDOFF` construct spec。

职责：

```text
表达已经存在的 WorkerHandoffIR 是否具备 handoff contract。
```

建议槽位：

```text
from_worker
target
input_bindings
output_bindings
invocation_site
```

其中：

```text
mode="invoke" 时 target 使用 to_worker。
mode="api_call" 时 target 使用 api_ref。
invocation_site 使用 invoke_location_hint。
```

### 4.4 CHILD_WORKER

当前 registry 已有 `CHILD_WORKER`。R4 不应大规模重写该 spec，只在测试中验证 checker 能针对 materialized child worker 生成 report。

## 5. WorkerDelegationIRSChecker 设计

### 5.1 Checker 元数据

```python
checker_id = "worker_delegation"
supported_construct_types = (
    "WORKER_CANDIDATE",
    "WORKER_PROMOTION",
    "CHILD_WORKER",
    "WORKER_HANDOFF",
)
supported_stages = ("stage3_5", "stage3_5_worker_boundary")
```

### 5.2 extract_instances(context)

输入：

```text
IRSCheckContext.worker_plan
```

无 `worker_plan` 时：

```text
return []
```

实例提取规则：

```text
WorkerPlanIR.candidates:
    -> WORKER_CANDIDATE instance
    -> WORKER_PROMOTION instance

WorkerPlanIR.workers where kind in {"child", "api_adapter"}:
    -> CHILD_WORKER instance

WorkerPlanIR.handoffs:
    -> WORKER_HANDOFF instance
```

实例状态：

```text
WORKER_CANDIDATE:
    materialized=False
    source_demanded=True
    candidate_only=True

WORKER_PROMOTION:
    materialized=False
    source_demanded=True
    candidate_only=True

CHILD_WORKER:
    materialized=True
    source_demanded=True
    candidate_only=False

WORKER_HANDOFF:
    materialized=True
    source_demanded=True
    candidate_only=False
```

建议 construct_id：

```text
worker_candidate:{candidate_id}
worker_promotion:{candidate_id}
child_worker:{worker_id}
worker_handoff:{handoff_id}
```

### 5.3 check_instance(instance, irs, context)

实现原则：

```text
1. 使用 instance.metadata 中的原始 IR ref。
2. 遍历 irs.slots，逐项生成 SlotSatisfaction。
3. 每个 missing required slot 必须携带 diagnostic_kind。
4. report.source_span_ids 来自对应 candidate/source evidence。
5. report.related_edges 用 R1 ConstructEdge 表达 candidate -> promotion、handoff -> worker 等关系。
6. 不修改 context 或 IR ref。
```

### 5.4 WORKER_CANDIDATE 检查

建议 satisfied 条件：

```text
responsibility:
    CandidateTaskUnitIR.purpose 非空，或 task_text 非空。

delegation_signal:
    signals 非空，或 candidate_kind != "not_a_worker"。

source_evidence:
    source_span_ids 非空。
```

注意：

```text
这里不从文本内容推断 delegation。
candidate_kind/signals 是上游结构化分类结果，R4 只消费它。
```

report 预期：

```text
completeness = complete
renderable = false
frontier_status = leaf
metadata["candidate_id"] = candidate_id
metadata["candidate_kind"] = candidate_kind
metadata["candidate_status"] = "identified"
```

### 5.5 WORKER_PROMOTION 检查

建议 satisfied 条件：

```text
promotion_input_contract:
    possible_inputs 非空，且 risks 不含 no_clear_input_contract。

promotion_output_contract:
    possible_outputs 非空，且 risks 不含 no_clear_output_contract。

promotion_invocation_point:
    risks 不含 no_parent_invocation_point，
    且已有 accepted extract_child_worker decision 或 matching handoff invoke_location_hint。

promotion_result_handoff:
    risks 不含 unclear_result_handoff，
    且已有 matching handoff.output_bindings。
```

需要谨慎的点：

```text
如果只有 risk code，没有 matching handoff，不应推断 handoff 已满足。
如果只有 possible_outputs，但没有 handoff.output_bindings，promotion_result_handoff 仍应 missing。
如果 candidate 被 rejected/keep_in_main_worker，promotion_status 应 blocked，不应 ready。
```

report 预期：

```text
missing 任一 promotion slot:
    completeness = partial 或 incomplete
    renderable = false
    frontier_status = cutline_partial
    cutline_reason = promotion_blocked
    metadata["promotion_status"] = "blocked"
    metadata["promotion_missing_slots"] = [...]

全部 promotion slot satisfied:
    completeness = complete
    renderable = false
    frontier_status = leaf
    metadata["promotion_status"] = "ready"
```

### 5.6 CHILD_WORKER 检查

建议 satisfied 条件：

```text
responsibility:
    WorkerSpecIR.purpose 非空。

input_contract:
    input_contract 非空。

output_contract:
    output_contract 非空。

invocation_point:
    存在 from main/parent 到该 worker 的 WorkerHandoffIR。

result_handoff:
    matching handoff.output_bindings 非空。
```

注意：

```text
CHILD_WORKER report 不能代替 Gate / ProducerIndex 的最终裁决。
这里只表达 construct-level satisfaction。
```

### 5.7 WORKER_HANDOFF 检查

建议 satisfied 条件：

```text
from_worker:
    handoff.from_worker 非空，且 worker_plan.workers 中存在该 worker。

target:
    mode="invoke" 时 to_worker 非空且存在。
    mode="api_call" 时 api_ref 非空。

input_bindings:
    input_bindings 非空。

output_bindings:
    output_bindings 非空。

invocation_site:
    invoke_location_hint.after_span_id 或 before_span_id 非空，
    或 ordering / condition_text 足以说明位置。
```

如果 `invocation_site` 的判断需要解释自然语言，不能实现 rule-based 文本判断；只能使用 `InvokeLocationHintIR` 的结构化字段。

## 6. Diagnostic 投影要求

R4 checker 不直接创建 `CompileDiagnostic`。它只在 missing slot 上设置：

```text
diagnostic_kind = "type_or_contract_ambiguity"
```

R3 `DiagnosticProjector` 应负责：

```text
severity
blocks_completion
missing_slot
diagnostic_id
dedup
source_span_ids copy
```

R4 测试必须验证：

```text
IRSRunner + WorkerDelegationIRSChecker + DiagnosticProjector
可以生成 type_or_contract_ambiguity CompileDiagnostic。
```

## 7. 实施任务拆分

### R4.1 Registry 补齐

Priority: P1

Files:

```text
src/nl2spl/compiler/construct_registry.py
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
```

Tasks:

```text
1. 新增 WORKER_PROMOTION ConstructIRS。
2. 新增 WORKER_HANDOFF ConstructIRS。
3. 调整 WORKER_CANDIDATE 描述，明确 candidate 与 promotion 分离。
4. 测试 registry.get("WORKER_PROMOTION") / get("WORKER_HANDOFF") 可用。
```

Acceptance:

```text
WORKER_PROMOTION 和 WORKER_HANDOFF 均有完整 slot specs。
WORKER_CANDIDATE 不再承担 promotion readiness 的主要表达职责。
旧 construct registry tests 不受影响。
```

### R4.2 WorkerDelegationIRSChecker 骨架

Priority: P1

Files:

```text
src/nl2spl/compiler/irs/checkers/__init__.py
src/nl2spl/compiler/irs/checkers/worker_delegation.py
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
```

Tasks:

```text
1. 新增 checker 类。
2. 定义 checker_id / supported_construct_types / supported_stages。
3. 实现无 worker_plan 返回 []。
4. 实现 extract_instances。
5. 确认不修改 WorkerPlanIR。
```

Acceptance:

```text
候选、promotion、child worker、handoff 均能被提取为 ConstructInstance。
ConstructInstance materialized/source_demanded/candidate_only 正确。
construct_id 稳定。
source_span_ids 保留。
```

### R4.3 Candidate 与 Promotion 检查

Priority: P1

Files:

```text
src/nl2spl/compiler/irs/checkers/worker_delegation.py
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
tests/unit/test_irs_v6_r0_baseline.py
```

Tasks:

```text
1. 实现 WORKER_CANDIDATE report。
2. 实现 WORKER_PROMOTION report。
3. 缺 input/output/invocation/result handoff 时产生 missing slot。
4. 将 R0 的 R4 target xfail 转为 passing acceptance test。
```

Acceptance:

```text
incomplete delegation candidate:
    有 WORKER_CANDIDATE report。
    candidate report 本身 complete。
    有 WORKER_PROMOTION report。
    promotion_status=blocked。
    promotion_missing_slots 包含实际缺失项。
    DiagnosticProjector 可生成 type_or_contract_ambiguity。
```

### R4.4 Child Worker 与 Handoff 检查

Priority: P1

Files:

```text
src/nl2spl/compiler/irs/checkers/worker_delegation.py
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
```

Tasks:

```text
1. 实现 CHILD_WORKER report。
2. 实现 WORKER_HANDOFF report。
3. 验证 child worker 与 handoff 的关系 edge。
4. 验证缺 binding 时产生 missing slot。
```

Acceptance:

```text
materialized child worker 能生成 CHILD_WORKER report。
materialized handoff 能生成 WORKER_HANDOFF report。
missing input/output binding 能被报告。
checker 不影响 Stage 7/Gate 的最终 renderability authority。
```

### R4.5 Runner 集成单测

Priority: P1

Files:

```text
tests/unit/compiler/irs/test_r4_worker_delegation_checker.py
```

Tasks:

```text
1. 构建 IRSCheckerRegistry。
2. 注册 WorkerDelegationIRSChecker。
3. 使用 IRSRunner.run_stage("stage3_5", context)。
4. 断言 reports 与 diagnostics 均正确。
```

Acceptance:

```text
runner 不需要 orchestrator 即可运行 worker/delegation checker。
reports 写入 IRSRunResult.reports。
diagnostics 写入 IRSRunResult.diagnostics。
unknown construct warning 不出现。
```

## 8. 测试计划

### 8.1 R4 单测

命令：

```powershell
python -m pytest tests/unit/compiler/irs/test_r4_worker_delegation_checker.py -q
```

必须覆盖：

```text
1. registry contains WORKER_PROMOTION and WORKER_HANDOFF。
2. no worker_plan returns no reports。
3. candidate extraction produces WORKER_CANDIDATE + WORKER_PROMOTION。
4. candidate complete does not mean promotion ready。
5. incomplete delegation promotion is blocked。
6. missing input contract creates missing slot diagnostic_kind。
7. missing output contract creates missing slot diagnostic_kind。
8. missing invocation point creates missing slot diagnostic_kind。
9. missing result handoff creates missing slot diagnostic_kind。
10. complete promotion has promotion_status=ready。
11. materialized child worker produces CHILD_WORKER report。
12. materialized handoff produces WORKER_HANDOFF report。
13. handoff missing bindings produces type_or_contract_ambiguity slots。
14. checker does not mutate WorkerPlanIR。
15. runner + projector produces CompileDiagnostic。
16. related_edges express candidate -> promotion and handoff -> child worker。
17. no raw text keyword inference is required by tests。
```

### 8.2 R0-R4 回归

命令：

```powershell
python -m pytest `
  tests/unit/test_irs_v6_r0_baseline.py `
  tests/unit/test_irs_v6_r1_report_schema.py `
  tests/unit/compiler/irs/test_r2_framework_skeleton.py `
  tests/unit/compiler/irs/test_r3_diagnostic_projector.py `
  tests/unit/compiler/irs/test_r4_worker_delegation_checker.py `
  -q
```

要求：

```text
R0 中与 R4 相关的 target xfail 必须移除或改为通过。
不得新增 skip。
不得新增 xfail。
```

### 8.3 全量单测

命令：

```powershell
python -m pytest tests/unit/ -q --basetemp=.pytest-tmp-r4
```

要求：

```text
全量单测通过。
如果存在环境性失败，必须列明失败测试、失败原因和与 R4 的关系。
不能把 R4 相关失败归为环境问题。
```

## 9. 验收标准

R4 通过必须同时满足：

```text
1. WORKER_PROMOTION 和 WORKER_HANDOFF construct specs 存在且 slot 清晰。
2. WorkerDelegationIRSChecker 使用 R2 Protocol 接入。
3. checker 不调用 LLM。
4. checker 不解析 raw NL。
5. checker 不使用关键词规则推断语义。
6. checker 不修改 WorkerPlanIR。
7. checker 不生成 child worker / handoff / INVOKE_WORKER。
8. incomplete delegation 产生 WORKER_CANDIDATE report。
9. incomplete delegation 产生 WORKER_PROMOTION blocked report。
10. candidate complete 与 promotion ready 被清楚区分。
11. promotion missing slots 可经 DiagnosticProjector 生成 CompileDiagnostic。
12. report 包含 source_span_ids、construct_path、frontier_status、cutline_reason、metadata。
13. related_edges 至少覆盖 candidate -> promotion。
14. R0 的 R4 xfail 被处理为正式 passing test。
15. R0-R4 回归通过。
16. 全量单测通过。
```

## 10. 审核清单

提交审核时必须提供：

```text
1. 修改文件列表。
2. 是否修改禁止范围文件。
3. WorkerPlanIR 是否保持不可变。
4. 是否引入 LLM 调用。
5. 是否引入 raw text keyword 规则。
6. R4 单测结果。
7. R0-R4 回归结果。
8. 全量单测结果。
9. R0 target xfail 的处理方式。
10. 一个 incomplete delegation 的 report 示例。
11. 一个 complete promotion 或 materialized handoff 的 report 示例。
12. DiagnosticProjector 输出的 CompileDiagnostic 示例。
```

我审核时会基于实际代码逐项核验，不接受只看实施报告。

## 11. 风险与处理

### 风险 1：promotion readiness 和 candidate completeness 混淆

处理：

```text
通过独立 WORKER_PROMOTION construct 表达 promotion readiness。
WORKER_CANDIDATE 只表达候选边界已经被识别。
```

### 风险 2：为了通过测试引入关键词规则

处理：

```text
测试 fixture 必须通过结构化字段表达 inputs/outputs/risks/handoff。
不得依赖 task_text/purpose 中的关键词。
```

### 风险 3：R4 误改 worker materialization

处理：

```text
禁止修改 Stage 3.5 planner/materializer。
测试断言 WorkerPlanIR 输入对象未被修改。
```

### 风险 4：diagnostic 重复或缺少 missing_slot

处理：

```text
使用 R3 DiagnosticProjector。
测试断言 CompileDiagnostic.missing_slot.slot_name 与缺失 promotion slot 一致。
```

### 风险 5：R4 被误认为解决 E2E 报告展示

处理：

```text
R4 只提供 checker 和 runner-level reports。
orchestrator intermediate / readable report 展示由 R5 负责。
```

## 12. R4 完成后的预期效果

R4 完成后，项目应具备以下能力：

```text
给定一个 WorkerPlanIR：
    如果存在 delegation candidate，
    系统可以结构化说明：
        1. 候选边界是否成立；
        2. 为什么尚不能晋升 child worker；
        3. 缺少 input/output/invocation/result handoff 中哪些条件；
        4. 对应诊断可以由统一 projector 生成；
        5. 该分析不改变任何 worker 生成行为。
```

对于 internal-comms Issue 3，R4 的直接价值是：

```text
不再只能看到“没有 child worker”这个结果；
可以在 IRS report 层看到“候选存在，但 promotion blocked，因为缺少明确 contract / invocation / result handoff”等结构化原因。
```

E2E report 中展示这些原因属于 R5。
