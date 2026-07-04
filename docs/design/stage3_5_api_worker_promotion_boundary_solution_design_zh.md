# Stage 3.5 API / Worker Promotion 边界修复方案

日期：2026-07-03
状态：设计基线草案，待实施计划拆分
适用范围：Stage 3.5 WorkerBoundaryPlanner、External Capability / API lowering、WORKER_PROMOTION IRS、SPL Editing issue presentation、Worker Delegation v2 closure

关联文档：

- `docs/design/external_capability_intent_extraction_and_api_lowering_design_zh.md`
- `docs/design/spl_editing_worker_delegation_repair_interaction_and_closure_design_zh.md`
- `docs/design/spl_editing_api_declaration_placeholder_renderability_implementation_plan_zh.md`
- `docs/design/spl_editing_construct_level_repair_strategy_and_stage_slice_design.md`

---

## 1. 背景与当前问题

重新运行 `examples/usage.py` 后，demo 中出现了一个语义冲突：

```text
s16: retrieve them using approved source recipes...
  -> API_DECLARATION ApprovedSourceRecipesAPI
  -> CALL_API ApprovedSourceRecipesAPI
  -> CHILD_WORKER Worker_retrieve_approved_sources
  -> WORKER_HANDOFF / INVOKE_WORKER
```

同一段 source span 被同时 materialize 成 API 调用和 child worker closure。随后 `run_demo.py` 又展示：

```text
Child worker definition is incomplete: Worker_retrieve_approved_sources
Missing: input contract, output contract, invocation point, result handoff
```

但 `final_spl.txt` 中已经存在 `Worker_retrieve_approved_sources` 和 `INVOKE_WORKER`。这说明问题不是单纯“worker 没生成”，而是三个状态被混在一起：

1. `s16` 已被 External Capability / API 链路接纳为 `API_DECLARATION + CALL_API`。
2. Stage 3.5 又把包含 `s16` 的 candidate 提升成 child worker。
3. `WORKER_PROMOTION` diagnostic 的真实 target 是 source-side promotion candidate，但 presentation 把它展示成已 materialized child worker。

同时还出现 required output producer 问题：

```text
Required output has no producer: source_evidence_set
```

原因是 parent required output、child output、handoff output、invoke result binding 没有形成同一条 producer closure。

---

## 2. 现有证据链

### 2.1 `s16` 已被 API 链路确认

`examples/output/demo/external_capability_intent_resolver.json` 中，`s16` 被识别为 confirmed external capability：

```json
{
  "source_span_ids": ["s16"],
  "operation_text": "retrieve them using approved source recipes",
  "boundary_status": "confirmed_external",
  "invocation_status": "executable",
  "capability_admission_status": "confirmed_capability",
  "invocation_admission_status": "confirmed_invocation"
}
```

这条链路已经授权生成：

```text
API_DECLARATION + CALL_API
```

### 2.2 Stage 3.5 又把包含 `s16` 的 candidate 提升为 child worker

`stage3_5a_candidate_task_units.json` 中存在：

```json
{
  "candidate_id": "candidate_retrieve_approved_sources",
  "source_span_ids": ["s16", "s23", "s30"],
  "candidate_kind": "integration_wrapper",
  "signals": ["external_integration", "bounded_io", "reuse_potential"]
}
```

`stage3_5b_worker_boundary_decisions.json` 中又出现：

```json
{
  "candidate_id": "candidate_retrieve_approved_sources",
  "decision": "extract_child_worker",
  "boundary_kind": "integration_wrapper"
}
```

这导致 `stage3_5c_worker_plan_materializer.json` 生成：

```text
Worker_retrieve_approved_sources
handoff_retrieve_approved_sources
```

### 2.3 `s31` 是 delegation policy，不是完整 child worker closure

`s31` 原文：

```text
Optional delegated subtasks such as source gathering or template matching may be
used if bounded and the returned evidence is normalized into approved evidence
carriers.
```

它是合法的 worker-promotion source signal，但它不是完整 child worker contract。它应该产生：

```text
WORKER_PROMOTION issue
```

而不是直接产生：

```text
CHILD_WORKER + WORKER_HANDOFF + INVOKE_WORKER
```

### 2.4 Presentation subject 与 diagnostic target 脱节

当前 `WORKER_PROMOTION` diagnostic target 是：

```text
worker_promotion:del_s31
```

但 UI 可能展示为：

```text
Child worker definition is incomplete: Worker_retrieve_approved_sources
```

根因是 presentation 读取 `context.metadata["derived_child_worker_id"]` 后优先展示 materialized child worker name。这个逻辑只有在存在 user-confirmed `PromotionResolutionMarker` 时才成立；否则它会把 source-side promotion issue 误展示成 materialized child worker issue。

---

## 3. 设计目标

修复后应满足：

```text
1. confirmed API invocation span 不再被 Stage 3.5 自动提升为 child worker。
2. mixed candidate 中 API-covered span 不丢失，residual span 需要被重新判断或保守降级。
3. s31 这类 delegation policy 仍产生 WORKER_PROMOTION issue。
4. 未经用户确认的 WORKER_PROMOTION issue 不展示 derived child worker name。
5. 如果用户选择 Define this work as a child worker，child output / handoff output /
   invoke result / parent result usage 必须严格对齐。
6. final SPL 不再把同一 API-owned source span 同时表达为 CALL_API 和 child worker closure。
7. required output producer issue 不再由 handoff binding 名称漂移引入。
```

---

## 4. 非目标

本方案不处理：

```text
1. API placeholder 的 downstream semantic validation。
2. OPENAPI_SCHEMA / API_IN_SPL 的完整补齐。
3. REQUEST_INPUT.value_target 的 R12+ repair strategy closure。
4. 全量 worker-aware pipeline 的语义重写。
```

`REQUEST_INPUT.value_target` 可作为单独设计继续处理。它当前不进入 `run_demo.py` editable list，是因为对应 repair affordance 没有完整 R12+ runtime closure，不能仅靠 diagnostic kind 暴露为用户可修复项。

---

## 5. 核心设计原则

### 5.1 API invocation 与 child worker closure 是互斥 materialization 结果

同一 source span 可以作为上下文证据参与多个判断，但不能同时成为两个 executable construct 的 materialization authority：

```text
confirmed external capability invocation
  -> API_DECLARATION + CALL_API

confirmed child-worker directive
  -> CHILD_WORKER + WORKER_HANDOFF + INVOKE_WORKER
```

如果某个 span 已被 external capability authority 接纳为 confirmed invocation，则 Stage 3.5 不能再基于该 span 自动 `extract_child_worker`。

### 5.2 不能用简单 span intersection 删除 candidate

Stage 3.5 candidate 可能是 mixed candidate：

```text
candidate.source_span_ids = ["s16", "s23", "s30"]
s16 = API-covered span
s23/s30 = residual context or downstream behavior
```

如果直接因为 candidate 与 API span 相交就删除整个 candidate，会造成 residual delegation evidence 静默丢失。正确处理必须区分：

```text
API-only candidate:
  all source_span_ids are API-consumed
  -> downgrade/reject to compile_as_call_api

Mixed candidate:
  some source_span_ids are API-consumed, some are residual
  -> trim/split API-covered spans, re-evaluate residual candidate

Ambiguous residual:
  residual spans cannot prove a child-worker boundary
  -> keep_in_main_worker + audit/diagnostic context
```

### 5.3 Delegation policy 是 source signal，不是 worker closure

`s31` 这类文本是：

```text
delegation_intent source signal
```

它可以产生：

```text
WORKER_PROMOTION issue
```

但不能自动生成：

```text
WorkerSpecIR
WorkerHandoffIR
INVOKE_WORKER StepIR
```

这些只能由 Worker Delegation v2 repair flow 在用户确认后 materialize。

### 5.4 Stage 3.5 必须使用现有 IR 枚举

当前 `WorkerBoundaryDecisionIR.decision` 已包含：

```text
extract_child_worker
keep_in_main_worker
compile_as_call_api
compile_as_constraint
compile_as_exception_flow
compile_as_alternative_flow
needs_repair_or_warning
```

当前 `BoundaryKind` 已包含：

```text
call_api
integration_wrapper
...
```

因此本方案必须使用：

```text
decision = compile_as_call_api
boundary_kind = call_api
```

不能引入不存在的 `integration_call` 或其它 stale enum。所有设计、测试、fixture、LLM schema 都必须以当前 `WorkerPlanIR` 为准。

---

## 6. 新增边界视图：WorkerBoundaryExclusionView

Stage 3.5 不应直接依赖完整 `ExternalCapabilityIntentPlanIR`。它只需要一个由 External Capability authority 派生的只读 exclusion view：

```python
@dataclass(frozen=True)
class WorkerBoundaryExclusionView:
    api_consumed_span_ids: frozenset[str]
    api_residual_span_ids: frozenset[str]
    api_call_demand_ids_by_span: Mapping[str, tuple[str, ...]]
    exclusion_authority: Literal["external_capability_intent_plan"]
    audit_payload: Mapping[str, Any]
```

字段语义：

```text
api_consumed_span_ids:
  已经被 confirmed API invocation 消费的 source spans。

api_residual_span_ids:
  与 API capability 相邻、相关，但没有被 API invocation 消费的 spans。
  它们不能自动删除，必须进入 residual 判断。

api_call_demand_ids_by_span:
  span -> API declaration / call demand id 的审计映射。

exclusion_authority:
  声明该 view 的 authority 来自 external_capability_intent_plan。

audit_payload:
  保存原始 API admission 状态、operation_text、capability id 等调试信息。
```

该 view 是 Stage 3.5 的输入边界，不是 IRS construct，不是 repair target，也不创建 diagnostics。

---

## 7. Stage 3.5 三层防线

### 7.1 Prompt context 防线

Stage 3.5a / 3.5b prompt 必须显式告知 LLM：

```text
The following spans are already consumed by confirmed API invocation and must
not be proposed as child-worker-owned executable work:
  - s16 -> ApprovedSourceRecipesAPI / CALL_API demand ...
```

对 mixed candidate，prompt 应要求：

```text
If a candidate mixes API-consumed spans and residual spans, decide only on the
residual task boundary. Do not use API-consumed spans as child-worker evidence.
```

Prompt context 只是第一层约束，不能作为唯一防线。

### 7.2 Post-parse candidate sanitizer 防线

Stage 3.5a 解析 candidate 后必须进行 deterministic sanitizer：

```python
def sanitize_candidate(candidate, exclusion_view):
    spans = set(candidate.source_span_ids)
    api = spans & exclusion_view.api_consumed_span_ids
    residual = spans - exclusion_view.api_consumed_span_ids

    if api and not residual:
        return AutoDecision(
            decision="compile_as_call_api",
            boundary_kind="call_api",
            rejection_reason="single_api_call",
        )

    if api and residual:
        return TrimmedCandidate(
            source_span_ids=sorted(residual),
            audit_removed_api_span_ids=sorted(api),
            requires_residual_re_evaluation=True,
        )

    return candidate
```

规则：

```text
1. API-only candidate 不能进入 extract_child_worker 候选池。
2. mixed candidate 必须 split/trim；API-covered spans 不能成为 child worker owned spans。
3. residual candidate 必须重新评估 input/output contract、signals、risks。
4. 如果 residual insufficient 或 ambiguous，则 keep_in_main_worker，不得静默丢弃。
```

### 7.3 Decision validator / materializer guard 防线

即使 LLM 或旧 fixture 仍输出：

```json
{
  "decision": "extract_child_worker",
  "source_span_ids": ["s16"]
}
```

Stage 3.5b validator / Stage 3.5c materializer 也必须 fail closed：

```text
extract_child_worker MUST NOT consume any api_consumed_span_ids.
```

处理方式：

```text
API-only accepted child decision:
  reject/downgrade to compile_as_call_api + boundary_kind=call_api

Mixed accepted child decision:
  reject original decision;
  require residual re-evaluation;
  if residual was not explicitly evaluated, keep_in_main_worker + audit warning

Invalid enum:
  reject stale boundary_kind such as integration_call
```

Materializer 不得创建 owned_span_ids 包含 `api_consumed_span_ids` 的 child worker。

---

## 8. WORKER_PROMOTION subject projection 修复

### 8.1 未确认 promotion 不展示 derived child worker

UI 展示 `WORKER_PROMOTION` issue 时，默认 subject 应来自 source-side promotion target：

```text
worker_promotion:del_s31
source excerpt: Optional delegated subtasks such as source gathering...
candidate responsibility: source gathering or template matching
```

只有当存在 user-confirmed `PromotionResolutionMarker`，并且 marker 与当前 diagnostic target 精确匹配时，presentation 才能展示 child worker subject：

```text
Child worker definition is incomplete: Worker_retrieve_approved_sources
```

否则应展示：

```text
Delegated work is underspecified: source gathering or template matching
```

### 8.2 Marker 生命周期

`PromotionResolutionMarker` 只能由 SPL Editing 用户确认后的 apply 写入。以下组件不得写入 marker：

```text
Stage 3.5
IRS checker
Diagnostic projector
Presentation resolver
Preview dry-run
```

建议 marker schema：

```python
@dataclass(frozen=True)
class PromotionResolutionMarker:
    marker_id: str
    source_promotion_target_ref: str
    resolution_kind: Literal[
        "defined_child_worker",
        "converted_to_main_flow_step",
        "converted_to_request_input",
        "dismissed_not_a_worker",
    ]
    repair_patch_id: str
    user_confirmed: bool
    child_worker_id: str | None
    handoff_id: str | None
    invoke_step_id: str | None
    output_binding_ids: tuple[str, ...]
```

其中：

```text
source_promotion_target_ref:
  必须等于 diagnostic target_ref，例如 worker_promotion:del_s31。

user_confirmed:
  必须为 true，且对应 RepairEvidencePacket / patch apply result 可追溯。

child_worker_id / handoff_id / invoke_step_id:
  只能在 resolution_kind=defined_child_worker 时存在。
```

### 8.3 Presentation subject 决策表

| 条件 | 展示 subject |
| --- | --- |
| 无 marker | source-side promotion excerpt / candidate responsibility |
| marker.user_confirmed=false | 忽略 marker，展示 source-side promotion |
| marker target 与 issue target 不一致 | 忽略 marker，展示 source-side promotion |
| marker confirmed 且 kind=defined_child_worker | 展示 child worker + source-side promotion context |
| marker confirmed 且 kind=converted_to_main_flow_step | 展示 main-flow resolution context |

---

## 9. Result binding invariant

如果用户选择 Define this work as a child worker，结果闭环必须同时满足：

```text
child worker output contract
-> handoff output binding child_output
-> invoke step result binding / parent variable
-> parent scope producer
-> required output demand, if applicable
```

禁止以下状态：

```text
child output = sourced_facts_with_provenance
parent required output = source_evidence_set
no binding / producer bridge between them
```

### 9.1 Patch-specific verifier 职责

`DefineChildWorkerClosureVerifier` 必须检查：

```text
1. marker.source_promotion_target_ref 精确等于 issue target_ref。
2. marker.user_confirmed 为 true。
3. marker.child_worker_id / handoff_id / invoke_step_id 均存在且互相引用一致。
4. child output contract 覆盖 admitted returned results。
5. handoff output bindings 覆盖 child output。
6. invoke result binding 写入 parent scope。
7. 如果 closure 声称解决 parent required output，则 parent variable 必须等于该 required output。
8. materialized refs 不得包含 unrelated worker / duplicate refs / stale refs。
```

### 9.2 Compiler authority 仍必须复跑

Patch-specific verifier 不能替代 compiler authority。Apply 后仍必须由 Lane B 复跑确认：

```text
Stage 9.5 normalizer
Stage 10 worker assembly
Post-normalize IRS
Gate
ProducerIndex
DiagnosticDiff
Renderer visibility
Provenance / evidence audit
```

验收条件：

```text
1. 原 WORKER_PROMOTION diagnostic group 被 marker + materialized closure 解决。
2. 不产生新的 missing_output_producer。
3. 不产生 orphan handoff / orphan invoke / orphan child worker。
4. final SPL 中 child worker、handoff、invoke、result usage 一致可见。
```

---

## 10. 数据模型与组件改动点

### 10.1 Stage 3.5 输入

新增或派生：

```text
WorkerBoundaryExclusionView
```

来源：

```text
external_capability_intent_plan
```

消费方：

```text
Stage 3.5 prompt builder
Stage 3.5 candidate sanitizer
Stage 3.5 decision validator
Stage 3.5 materializer guard
```

### 10.2 Stage 3.5 输出

必须保留审计字段：

```text
candidate.audit_removed_api_span_ids
candidate.residual_source_span_ids
decision.downgraded_from_extract_child_worker
decision.exclusion_authority
decision.api_call_demand_ids
```

这些字段用于解释为什么某 candidate 没有成为 child worker，不能用于 IRS repair target。

### 10.3 Presentation

`issue_subject_for()` 不得仅凭 `derived_child_worker_id` 展示 child worker。它必须通过 resolution marker store 验证：

```text
target_ref exact match
user_confirmed
repair_patch_id present
marker refs coherent
```

未满足时使用 source-side subject：

```text
Delegated work is underspecified: <source excerpt / task candidate>
```

### 10.4 Worker Delegation v2 closure

`DefineChildWorkerClosure` 必须把 result binding 作为 closure 的 required node：

```text
CHILD_WORKER output contract
WORKER_HANDOFF output binding
INVOKE_WORKER result binding
parent local producer / required output producer
```

如果任一节点缺失，preview/apply 不得 accepted。

---

## 11. 实施阶段建议

### Phase 0：Characterization tests

锁定当前问题，不改行为：

```text
1. external_capability_intent_plan 中 s16 是 confirmed API invocation。
2. stage3_5a 当前 candidate 包含 s16/s23/s30。
3. stage3_5b 当前 decision 错误为 extract_child_worker。
4. run_demo 当前把 worker_promotion:del_s31 展示成 derived child worker。
5. final SPL 中 child output / parent required output 不对齐。
```

验收：

```text
新增 characterization tests 均能复现当前失败。
```

### Phase 1：WorkerBoundaryExclusionView

实现只读 view，不改变 Stage 3.5 结果：

```text
external_capability_intent_plan
-> WorkerBoundaryExclusionView
```

验收：

```text
1. s16 进入 api_consumed_span_ids。
2. API demand id 可从 api_call_demand_ids_by_span 查到。
3. view 不直接创建 diagnostic，不进入 IRS registry。
```

### Phase 2：Stage 3.5 deterministic guard

增加 prompt context、candidate sanitizer、decision validator/materializer guard。

验收：

```text
1. API-only candidate -> compile_as_call_api + boundary_kind=call_api。
2. mixed candidate -> trim/split API spans，residual 重新评估。
3. ambiguous residual -> keep_in_main_worker + audit warning。
4. extract_child_worker consuming api_consumed_span_ids 被拒绝。
5. stale enum integration_call 被拒绝。
```

### Phase 3：WORKER_PROMOTION subject projection

修复 issue subject：

```text
without confirmed marker:
  show source-side promotion subject

with confirmed marker:
  may show materialized child worker subject
```

验收：

```text
1. del_s31 issue 不再显示 Worker_retrieve_approved_sources。
2. marker.user_confirmed=false 不影响 subject。
3. marker target mismatch 不影响 subject。
4. confirmed marker 才展示 child worker。
```

### Phase 4：DefineChildWorkerClosure result binding invariant

增强 patch-specific verifier 与 Lane B 验收。

验收：

```text
1. child output / handoff output / invoke result / parent variable 全链路一致。
2. parent required output 如果被声明解决，必须有 producer。
3. mismatch 会被 patch verifier 拒绝。
4. ProducerIndex / post-normalize IRS / DiagnosticDiff 共同确认无新增 producer gap。
```

### Phase 5：真实 E2E 与负例矩阵

覆盖：

```text
1. s16 API invocation 不生成 child worker。
2. s31 delegation policy 仍生成 WORKER_PROMOTION issue。
3. Define child worker user-confirmed repair 后生成一致 child closure。
4. Keep in main flow user-confirmed repair 后不生成 child / handoff / invoke。
5. Required output producer 不因 binding drift 产生。
```

必须保存 artifact：

```text
before/after final_spl
before/after diagnostics
stage3_5a/b/c artifacts
worker boundary exclusion view
preview summary
verification result
provenance/evidence summary
```

---

## 12. 必须新增的负例测试

### 12.1 API-only candidate

```text
candidate spans = {s16}
s16 in api_consumed_span_ids
```

期望：

```text
decision = compile_as_call_api
boundary_kind = call_api
no child worker
```

### 12.2 Mixed candidate

```text
candidate spans = {s16, s23, s30}
s16 in api_consumed_span_ids
s23/s30 residual
```

期望：

```text
s16 removed from worker-owned spans
residual candidate evaluated
residual not silently lost
```

### 12.3 Invalid stale enum

输入：

```text
boundary_kind = integration_call
```

期望：

```text
parse/validation fails
```

### 12.4 Stale or unconfirmed marker

输入：

```text
PromotionResolutionMarker(user_confirmed=false)
```

期望：

```text
presentation ignores derived child worker
repair verification rejects marker as evidence
```

### 12.5 Result binding mismatch

输入：

```text
child output = sourced_facts_with_provenance
parent required output = source_evidence_set
no explicit binding
```

期望：

```text
DefineChildWorkerClosureVerifier rejects
ProducerIndex still reports missing producer if apply is forced in test
```

### 12.6 Silent residual loss

输入：

```text
mixed candidate has residual spans with delegation evidence
sanitizer drops entire candidate
```

期望：

```text
test fails; residual must be re-evaluated or explicitly audited as keep_in_main_worker
```

---

## 13. 最终设计决策

本方案的最终边界是：

```text
External Capability authority owns confirmed API invocation spans.
Stage 3.5 may use those spans as context, but cannot make them child-worker-owned work.
Delegation policy spans remain WORKER_PROMOTION source signals.
SPL Editing user confirmation is the only authority that can turn a promotion issue
into materialized child worker closure.
Presentation can display materialized child worker subject only after confirmed marker.
DefineChildWorkerClosure must prove result binding all the way to parent scope and
required output producer authority.
```

因此，`s16` 应最终表现为：

```text
API_DECLARATION ApprovedSourceRecipesAPI
CALL_API ApprovedSourceRecipesAPI
```

而 `s31` 应表现为：

```text
WORKER_PROMOTION issue:
  delegated work policy is underspecified
  options:
    - Define this work as a child worker
    - Keep this work in the main workflow
```

只有用户确认 `Define this work as a child worker` 后，系统才允许生成：

```text
CHILD_WORKER
WORKER_HANDOFF
INVOKE_WORKER
result binding
PromotionResolutionMarker(user_confirmed=true)
```

并且必须通过 Lane B compiler-authority verification。
