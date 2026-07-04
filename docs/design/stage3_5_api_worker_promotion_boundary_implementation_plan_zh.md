# Stage 3.5 API / Worker Promotion 边界修复实施计划

本文档基于 `docs/design/stage3_5_api_worker_promotion_boundary_solution_design_zh.md` 制定。实施目标是修复 demo 中同一 API source span 被同时 materialize 为 `CALL_API` 和 child worker 的边界错误，并让 `WORKER_PROMOTION` issue、SPL Editing 展示、Worker Delegation v2 closure、ProducerIndex 结果绑定保持一致。

适用范围：

```text
Stage 3.5 WorkerBoundaryPlanner
External Capability / API lowering 到 Stage 3.5 的边界视图
WORKER_PROMOTION issue subject projection
Worker Delegation v2 DefineChildWorkerClosure verifier
真实 demo E2E 与负例矩阵
```

不在本计划内：

```text
OPENAPI_SCHEMA / API_IN_SPL downstream semantic validation
REQUEST_INPUT.value_target R12+ repair closure
全量 worker-aware pipeline 语义重写
新增或重定义 ConstructIRS
```

---

## 1. 总体目标

最终系统应形成以下职责链：

```text
External Capability authority
  -> WorkerBoundaryExclusionView
  -> 标记 confirmed API invocation spans
  -> 不创建 IRS diagnostic，不执行 repair，不 materialize worker

Stage 3.5 WorkerBoundaryPlanner
  -> 消费 WorkerBoundaryExclusionView
  -> API-only candidate 降级为 compile_as_call_api
  -> mixed candidate split/trim 后只评估 residual spans
  -> 禁止 extract_child_worker 消费 api_consumed_span_ids

WORKER_PROMOTION IRS / DiagnosticProjector
  -> 继续以 source-side promotion candidate 为 diagnostic target
  -> 不把 derived child worker 当作未确认 issue subject

SPL Editing presentation
  -> 只有 confirmed PromotionResolutionMarker 才能展示 materialized child worker subject
  -> 否则展示 source-side delegated work subject

Worker Delegation v2 closure
  -> 用户确认后才 materialize child worker / handoff / invoke
  -> DefineChildWorkerClosureVerifier 校验 child output / handoff output /
     invoke result / parent result usage 全链路一致

Lane B compiler authority
  -> Stage 9.5 / Stage 10 / Post-normalize IRS / Gate / ProducerIndex /
     DiagnosticDiff / Renderer 共同验收最终结果
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. `WorkerBoundaryExclusionView` 是 Stage 3.5 输入边界视图，不是 IRS construct、diagnostic、repair target 或 materialization artifact。
2. Stage 3.5 不得直接依赖完整 `ExternalCapabilityIntentPlanIR` 做内部判断；只能消费经过收敛的 exclusion view。
3. confirmed API invocation span 可以作为上下文证据，但不得成为 child-worker-owned executable span。
4. mixed candidate 不得因为包含 API span 被整体删除；residual spans 必须被重新评估或显式 audit 为 `keep_in_main_worker`。
5. 当前 IR 枚举必须以 `WorkerPlanIR` 为准：API 降级使用 `decision="compile_as_call_api"` 和 `boundary_kind="call_api"`；不得引入 `integration_call`。
6. `WORKER_PROMOTION` issue 的 source-side target 是 `worker_promotion:{candidate_id}`；presentation 不得凭 `derived_child_worker_id` 把未确认 promotion 展示为 child worker issue。
7. `PromotionResolutionMarker` 只能由用户确认后的 SPL Editing apply 写入；Stage 3.5、IRS、DiagnosticProjector、Presentation、preview dry-run 均不得写入 marker。
8. Patch-specific verifier 只负责 patch/closure 业务不变量；不得替代 Lane B compiler authority。
9. `DefineChildWorkerClosure` 必须证明 result binding 到 parent scope 和 required output producer 的全链路一致。
10. 不得通过静默 suppress diagnostic、修改 fixture、删除 source span、或只改 UI 文案掩盖边界错误。
11. 所有新增 fallback 必须是结构化、确定性校验；禁止基于关键词或标题重新推断语义。
12. 每个阶段必须能独立验收，不允许“先合入半成品，后续再修”。

---

## 3. LLM / Rule-based 决策约束

本计划允许修改 Stage 3.5 prompt，但 prompt 只能作为第一层约束，不能成为唯一防线。

允许的确定性逻辑：

```text
读取 external capability resolver 的结构化 admission 状态
构造只读 WorkerBoundaryExclusionView
按 api_consumed_span_ids 对 candidate 做 API-only / mixed / residual 分类
校验 WorkerBoundaryDecisionIR 的现有 enum 值
校验 marker 与 issue target_ref 精确匹配
校验 result binding chain 的结构化一致性
```

禁止的逻辑：

```text
根据 source text 关键词判断 API 或 worker
让 LLM 覆盖 deterministic exclusion view
让 Stage 3.5 重新决定 API admission
让 presentation 推断 worker 是否已被用户确认
让 patch verifier suppress compiler diagnostics
把 diagnostic kind 作为 repair capability 的唯一来源
```

任何新增 LLM schema / prompt 字段都必须同时有 deterministic validator 和负例测试。

---

## 4. Phase APW0：Current Gap Lock / Characterization Tests

### 4.1 目标

锁定当前错误行为，作为后续修复的基线。APW0 只新增测试和审计辅助，不修改生产行为。

APW0 必须拆成两类产物，避免“当前坏行为锁定”和“未来目标行为断言”混在同一组默认测试中：

```text
APW0a Current-behavior lock:
  断言当前 artifact 确实存在 s16 API + child worker 双重 materialization、
  del_s31 subject 错误、producer binding drift。
  这些测试在当前代码上应通过。

APW0b Target-behavior pending assertions:
  写成 helper、scenario spec 或 golden expectation。
  不进入默认 pytest，不使用 skip / xfail。
  在 APW2 / APW3 / APW4 / APW6 / APW7a / APW7b 中逐步转成默认目标行为测试。
```

### 4.2 可编辑范围

允许新增：

```text
tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/
tests/integration/compiler/spl_editing/
tests/fixtures/stage3_5_api_worker_boundary/
```

允许修改：

```text
仅测试文件、fixture 读取 helper、必要的测试数据生成脚本
```

### 4.3 禁止改动

```text
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/
src/nl2spl/compiler/spl_editing/
src/nl2spl/compiler/irs/
src/nl2spl/compiler/construct_registry.py
examples/output/demo/
```

### 4.4 设计要求

APW0a current-behavior lock 必须证明：

```text
s16 在 external_capability_intent_resolver 中是 confirmed API invocation
stage3_5a 当前 candidate 包含 s16/s23/s30
stage3_5b 当前 decision 错误为 extract_child_worker
worker_promotion:del_s31 被 presentation 展示成 derived child worker
child output / handoff output / parent required output 当前未对齐
```

### 4.5 测试计划

新增默认测试必须覆盖当前行为：

1. `external_capability_intent_resolver.json` 中 `s16` admission 状态。
2. `stage3_5a_candidate_task_units.json` 中 mixed candidate 的 span 集合。
3. `stage3_5b_worker_boundary_decisions.json` 中错误 child extraction。
4. `run_demo.py` / presentation 当前 subject 映射错误。
5. final SPL / diagnostics 中 producer binding drift。

### 4.6 验收标准

APW0 通过条件：

1. APW0a current-behavior lock 在当前代码上通过。
2. APW0b target-behavior pending assertions 不进入默认 pytest，也不使用 skip / xfail。
3. APW0b 的 helper / scenario spec 清楚表达后续阶段应启用的目标行为。
4. 不修改任何生产路径。
5. 无新增 skip / xfail。

### 4.7 PM 审核清单

1. 测试是否锁定真实 artifact，而不是手写脱离 demo 的虚假数据。
2. 是否同时覆盖 Stage 3.5 artifact、presentation、final SPL / diagnostics。
3. 是否没有通过改 fixture 改变当前行为。
4. 是否没有把未来目标行为测试直接放入默认 pytest 造成预期失败。

---

## 5. Phase APW1：WorkerBoundaryExclusionView

### 5.1 目标

新增 API 到 worker-boundary 的只读边界视图，提供 Stage 3.5 所需的最小 authority 信息。

### 5.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/api_exclusion.py
tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_view.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/__init__.py
```

### 5.3 禁止改动

```text
src/nl2spl/compiler/irs/
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/spl_editing/
Stage 3.5 prompt / sanitizer / materializer behavior
```

### 5.4 设计要求

实现：

```python
@dataclass(frozen=True)
class WorkerBoundaryExclusionView:
    api_consumed_span_ids: frozenset[str]
    api_residual_span_ids: frozenset[str]
    api_call_demand_ids_by_span: Mapping[str, tuple[str, ...]]
    exclusion_authority: Literal["external_capability_intent_plan"]
    audit_payload: Mapping[str, Any]
```

构造函数应只从结构化 external capability resolver output 读取：

```text
source_span_ids
capability_admission_status
invocation_admission_status
boundary_status
invocation_status
operation / demand identity
```

只有 confirmed/executable/admitted invocation 才能进入 `api_consumed_span_ids`。

### 5.5 测试计划

新增单元测试覆盖：

1. `s16` 类 confirmed API invocation 进入 `api_consumed_span_ids`。
2. 非 confirmed / non-executable API 不进入 consumed set。
3. `api_call_demand_ids_by_span` 保留 demand 映射。
4. `audit_payload` 不为空且不影响业务判断。
5. view 不产生 diagnostic，不依赖 IRS registry。

### 5.6 验收标准

APW1 通过条件：

1. View 可从 demo artifact 构造。
2. View 不改变 Stage 3.5 输出。
3. View 不引入新 ConstructIRS。
4. APW0a current-behavior lock 继续通过；APW0b pending assertions 仍不进入默认 pytest。

### 5.7 PM 审核清单

1. 是否没有把 full external capability plan 传入 Stage 3.5 深层逻辑。
2. 是否没有新增 diagnostic / repair affordance。
3. 是否只用结构化 admission 字段，不解析自然语言。

---

## 6. Phase APW2：Stage 3.5 Candidate Sanitizer

### 6.1 目标

在 Stage 3.5a 之后加入 deterministic sanitizer，处理 API-only 与 mixed candidate，防止 API-owned spans 进入 child worker owned spans。

### 6.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/candidate_sanitizer.py
tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_candidate_sanitizer.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
src/nl2spl/ir/worker_plan_ir.py
```

`worker_plan_ir.py` 只允许添加可选 audit 字段，禁止修改现有 enum 字符串。

### 6.3 禁止改动

```text
Stage 3.5 materializer child worker generation policy
SPL Editing repair flow
IRS checker
```

### 6.4 设计要求

Sanitizer 必须输出结构化结果，禁止只靠临时 metadata 表达 mixed/residual 状态。建议内部 DTO：

```python
@dataclass(frozen=True)
class SanitizedCandidateResult:
    original_candidate_id: str
    result_kind: Literal[
        "unchanged",
        "api_only_auto_decision",
        "mixed_trimmed_candidate",
        "mixed_residual_keep_in_main_worker",
        "rejected_invalid",
    ]
    residual_candidate_id: str | None
    residual_source_span_ids: tuple[str, ...]
    removed_api_span_ids: tuple[str, ...]
    auto_decision: WorkerBoundaryDecisionIR | None
    residual_policy_reason: str | None
    requires_residual_re_evaluation: bool
    audit: Mapping[str, Any]
```

如果实现中采用不同名称，必须保持等价字段语义，并有测试证明 APW3 可以可靠判断 residual 是否已经重新评估。

Sanitizer 必须表达三类核心结果：

```text
API-only candidate:
  AutoDecision(decision="compile_as_call_api", boundary_kind="call_api")

Mixed candidate:
  TrimmedCandidate(source_span_ids=residual_spans,
                   audit_removed_api_span_ids=api_spans,
                   requires_residual_re_evaluation=True)

No API overlap:
  原 candidate
```

对 mixed candidate：

```text
1. 不得整体删除。
2. residual candidate 必须重新计算或标记 risks/signals/status 为需重新评估。
3. 如果 residual 无法形成清晰 worker boundary，必须输出 keep_in_main_worker + audit reason。
4. APW3 validator / materializer guard 必须消费 `SanitizedCandidateResult` 或等价结构，而不是重新从自然语言或裸 metadata 推断 residual 状态。
```

### 6.5 测试计划

新增测试覆盖：

1. API-only candidate 降级为 `compile_as_call_api` / `call_api`。
2. mixed candidate 只移除 API spans，保留 residual。
3. residual 空时不进入 LLM decision 池。
4. residual ambiguous 时显式 `keep_in_main_worker`。
5. sanitizer 产生 audit 字段，便于解释被移除的 API spans。
6. silent residual loss 负例。
7. `SanitizedCandidateResult` round-trip / serialization 或 artifact projection 覆盖关键字段。
8. APW3 可通过 sanitizer result 判断 mixed candidate 是否完成 residual re-evaluation。

### 6.6 验收标准

APW2 通过条件：

1. `extract_child_worker` 不再接收 API-only candidate。
2. mixed candidate residual 不丢失。
3. 现有非 API worker candidate 不受影响。
4. sanitizer result 有稳定结构化产物，后续 guard 不依赖 ad hoc metadata。
5. 不新增 skip / xfail。

### 6.7 PM 审核清单

1. 是否存在 `if overlap: drop candidate` 这类粗暴逻辑。
2. 是否所有 residual loss 都有测试覆盖。
3. 是否没有新增不在 `WorkerPlanIR` 中的 enum。
4. 是否 APW3 能直接消费结构化 sanitizer result，而不是重复实现 residual 推断。

---

## 7. Phase APW3：Stage 3.5 Prompt Context 与 Decision / Materializer Guard

### 7.1 目标

把 API exclusion 信息接入 Stage 3.5 prompt，并在 decision validator / materializer 层建立 fail-closed guard。

### 7.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/prompt_builder.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/decision_validator.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/materializer.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
```

允许新增：

```text
tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_decision_guard.py
```

### 7.3 禁止改动

```text
LLM schema 之外的 downstream repair path
SPL Editing presentation
Worker Delegation v2 closure verifier
```

### 7.4 设计要求

Prompt 必须包含：

```text
API-consumed spans
API demand / call identity
mixed candidate handling instruction
禁止把 API-consumed spans 作为 child-worker evidence
```

Validator / materializer 必须 enforce：

```text
extract_child_worker MUST NOT consume api_consumed_span_ids
boundary_kind MUST be valid WorkerPlanIR BoundaryKind
API-only stale accepted decision must downgrade/reject to compile_as_call_api/call_api
mixed accepted child decision without residual re-evaluation must fail closed
```

### 7.5 测试计划

新增测试覆盖：

1. Prompt 中包含 API-consumed span section。
2. stale LLM output `boundary_kind="integration_call"` 被拒绝。
3. stale LLM output `extract_child_worker` + API-only span 被拒绝或降级。
4. mixed accepted child decision 缺 residual re-evaluation 时被拒绝。
5. Materializer 不创建 owned spans 包含 `api_consumed_span_ids` 的 child worker。

### 7.6 验收标准

APW3 通过条件：

1. API exclusion 由 prompt、validator、materializer 三层共同保护。
2. 任何绕过 prompt 的 stale fixture 也不能生成 API-owned child worker。
3. `compile_as_call_api` / `call_api` 路径可被 artifact 记录。

### 7.7 PM 审核清单

1. 是否只改 prompt，没有 deterministic guard。
2. 是否 validator 和 materializer 均有 fail-closed 覆盖。
3. 是否所有 enum 都来自 `WorkerPlanIR`。

---

## 8. Phase APW4：WORKER_PROMOTION Subject Projection

### 8.1 目标

修复 presentation subject 误导：未确认 `WORKER_PROMOTION` issue 不得显示 derived child worker name。

### 8.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/spl_editing/presentation/resolvers/issue_subject.py
src/nl2spl/compiler/spl_editing/context/worker_promotion_context.py
src/nl2spl/compiler/spl_editing/presentation/resolvers/display_context.py
```

允许新增：

```text
tests/unit/compiler/spl_editing/presentation/test_worker_promotion_subject_projection.py
```

### 8.3 禁止改动

```text
src/nl2spl/compiler/irs/checkers/worker_delegation.py
src/nl2spl/compiler/construct_registry.py
Stage 3.5 artifacts
```

### 8.4 设计要求

Subject projection 必须使用决策表：

```text
无 marker:
  source-side promotion subject

marker.user_confirmed=false:
  忽略 marker

marker target 与 issue target 不一致:
  忽略 marker

confirmed marker + defined_child_worker:
  可展示 child worker subject，同时保留 source-side promotion context

confirmed marker + converted_to_main_flow_step:
  展示 main-flow resolution context
```

Presentation 不得凭 `derived_child_worker_id` 单独决定 subject。

### 8.5 测试计划

新增测试覆盖：

1. `worker_promotion:del_s31` 无 marker 时展示 source excerpt / delegated work。
2. unconfirmed marker 被忽略。
3. target mismatch marker 被忽略。
4. confirmed `defined_child_worker` marker 才展示 child worker。
5. confirmed `converted_to_main_flow_step` 展示 main-flow resolution。

### 8.6 验收标准

APW4 通过条件：

1. demo issue list 不再把未确认 `del_s31` 展示为 `Worker_retrieve_approved_sources`。
2. 用户能看懂具体是哪段 delegated policy 缺信息。
3. 已确认 repair 后仍能展示 materialized resolution。

### 8.7 PM 审核清单

1. 是否彻底消除 `derived_child_worker_id` 的单点 truth。
2. 是否 marker 必须精确 target match。
3. 是否没有改 IRS diagnostic target 来掩盖问题。

---

## 9. Phase APW5：PromotionResolutionMarker Lifecycle Hardening

### 9.1 目标

明确 marker 只能由用户确认后的 apply 写入，并让 preview、Stage 3.5、IRS、presentation 都不能伪造 marker。

### 9.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/spl_editing/resolution/model.py
src/nl2spl/compiler/spl_editing/resolution/store.py
src/nl2spl/compiler/spl_editing/core/snapshot_adapter.py
src/nl2spl/compiler/spl_editing/stage_slices/worker_delegation_v2.py
src/nl2spl/compiler/spl_editing/materialization/worker_handoff/contract.py
```

允许新增：

```text
tests/unit/compiler/spl_editing/resolution/test_promotion_resolution_marker_lifecycle.py
```

### 9.3 禁止改动

```text
Stage 3.5 writes
IRS checker writes
Diagnostic projector writes
Preview dry-run persistent overlay writes
```

### 9.4 设计要求

Marker 至少应表达：

```text
source_promotion_target_ref
resolution_kind
repair_patch_id
user_confirmed
child_worker_id
handoff_id
invoke_step_id
output_binding_ids
```

如果保持现有字段命名，也必须建立等价语义，并在 verifier / store 中强制：

```text
target exact match
user_confirmed=true
repair_patch_id present
materialized refs coherent
```

### 9.5 测试计划

新增测试覆盖：

1. Preview dry-run 不持久化 marker。
2. Stage 3.5 / IRS artifact 中的 marker-like metadata 不被接受。
3. `user_confirmed=false` marker 被 presentation 和 verifier 拒绝。
4. `repair_patch_id` 缺失时拒绝。
5. target mismatch 时拒绝。

### 9.6 验收标准

APW5 通过条件：

1. Marker lifecycle 只有 confirmed apply path 可写。
2. Presentation 和 verifier 使用同一套 marker validity 判定。
3. 旧 snapshot adapter round-trip 不丢 marker 字段。

### 9.7 PM 审核清单

1. 是否存在 presentation 或 preview 写 marker。
2. 是否 marker 可以被 metadata 字符串伪造。
3. 是否 serializer round-trip 覆盖新增字段。

---

## 10. Phase APW6：DefineChildWorkerClosure Result Binding Invariant

### 10.1 目标

增强 DefineChildWorkerClosure 的 patch-specific verifier，防止 child output、handoff output、invoke result、parent required output 之间漂移。

### 10.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/spl_editing/patches/define_child_worker_closure/verifier.py
src/nl2spl/compiler/spl_editing/stage_slices/worker_delegation_closure.py
src/nl2spl/compiler/spl_editing/stage_slices/worker_delegation_v2.py
```

允许新增：

```text
tests/integration/compiler/spl_editing/test_worker_delegation_result_binding_invariant.py
tests/unit/compiler/spl_editing/patches/test_define_child_worker_closure_verifier.py
```

### 10.3 禁止改动

```text
GenericEvidenceVerifier 承担 closure-specific 业务语义
ProducerIndex suppress diagnostics
Post-normalize IRS suppress diagnostics
```

### 10.4 设计要求

Verifier 必须校验：

```text
marker.source_promotion_target_ref == issue.target_ref
marker.user_confirmed is True
marker.child_worker_id / handoff_id / invoke_step_id 互相引用一致
child output contract 覆盖 admitted returned results
handoff output binding 覆盖 child output
invoke result binding 写入 parent scope
如果 closure 声称解决 parent required output，则 parent variable 等于 required output
materialized refs 无 unrelated / duplicate / stale refs
```

Generic verification 只负责：

```text
evidence refs
authority metadata
changed refs
provenance
rendered visibility
```

不得把 result binding 业务不变量塞入 generic runner。

### 10.5 测试计划

新增测试覆盖：

1. child output 与 handoff output mismatch 被拒绝。
2. handoff output 与 invoke result mismatch 被拒绝。
3. parent required output 未被 producer bridge 覆盖时被拒绝。
4. unrelated materialized refs 被拒绝。
5. duplicate refs 被拒绝。
6. forced bad apply 后 ProducerIndex / DiagnosticDiff 仍能报告 producer gap。

### 10.6 验收标准

APW6 通过条件：

1. Define child worker closure 不能 accepted 半闭环结果。
2. Patch-specific verifier 与 Lane B authority 均覆盖 result binding。
3. 不新增 required output producer regression。

### 10.7 PM 审核清单

1. 是否把业务闭环塞进 GenericEvidenceVerifier。
2. 是否只检查 marker refs 而不检查真实 artifact。
3. 是否 ProducerIndex 仍作为最终 producer authority。

---

## 11. Phase APW7a：Demo Baseline E2E

### 11.1 目标

完成 Stage 3.5 / presentation 层面的真实 demo baseline 验收，先证明 API / worker boundary 已修复，不把 Worker Delegation repair closure 的复杂度压到同一个阶段。

### 11.2 可编辑范围

允许修改：

```text
examples/output/spl_editing_demo/run_demo.py
tests/integration/compiler/spl_editing/
scripts/ 或 tests/helpers/ 中用于 artifact bundle 的辅助脚本
```

禁止用手工编辑 `examples/output/demo/` 作为验收通过方式；demo artifact 必须由 pipeline / demo 命令生成。

### 11.3 禁止改动

```text
通过删除 source span 或修改 input 文本掩盖问题
通过固定 snapshot id 跳过 pipeline
通过关闭 diagnostic projection 达到绿色
通过执行 repair closure 掩盖 baseline boundary 仍错误
```

### 11.4 设计要求

APW7a E2E 必须覆盖：

```text
s16 API invocation 不生成 child worker
s31 delegation policy 仍生成 WORKER_PROMOTION issue
未确认 promotion subject 展示 source-side delegated work
API deferred validation 仍为 review_only，不进入 editable
```

Baseline artifact bundle 必须包含：

```text
final_spl.txt
compile diagnostics
stage3_5a_candidate_task_units.json
stage3_5b_worker_boundary_decisions.json
stage3_5c_worker_plan_materializer.json
worker_boundary_exclusion_view.json
issue inventory / run_demo list-only output
manifest.json with hashes
```

### 11.5 测试计划

运行并记录：

```text
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/stage3_5_worker_boundary_planner -q
.venv\Scripts\python.exe -m pytest tests/unit/compiler/spl_editing/presentation tests/integration/compiler/spl_editing -q
.venv\Scripts\python.exe examples/output/spl_editing_demo/run_demo.py --run demo --list-only
ruff check <touched files>
git diff --check
```

### 11.6 验收标准

APW7a 通过条件：

1. APW0a 中与 Stage 3.5 / presentation 相关的 current-behavior locks 已转为目标行为断言。
2. Demo 不再出现 `s16` 同时 API + child worker closure。
3. `WORKER_PROMOTION` issue subject 不再误指 `Worker_retrieve_approved_sources`，除非有 confirmed marker。
4. API deferred validation 仍在 review/deferred 分区，不进入 editable。
5. Baseline artifact bundle hash 可复验。

### 11.7 PM 审核清单

1. 是否使用真实 demo 命令，而不是单元测试替代 E2E。
2. 是否保存 Stage 3.5 和 issue inventory baseline artifact。
3. 是否 demo fixture 未被手工污染。
4. 是否 artifact manifest 可复验。
5. 是否没有把 Worker Delegation repair closure 的失败混入 APW7a 结论。

---

## 12. Phase APW7b：Repair Closure E2E、Artifact Bundle 与 Cleanup

### 12.1 目标

完成 Worker Delegation repair closure 的真实 E2E，保存 before/after artifact bundle，并清理临时兼容路径。

### 12.2 可编辑范围

允许修改：

```text
examples/output/spl_editing_demo/run_demo.py
tests/integration/compiler/spl_editing/
scripts/ 或 tests/helpers/ 中用于 repair closure artifact bundle 的辅助脚本
```

### 12.3 禁止改动

```text
通过 suppress diagnostic 让 repair accepted
通过跳过 Lane B replay 让 overlay accepted
通过手工编辑 examples/output/demo/ 让 artifact 看起来正确
```

### 12.4 设计要求

APW7b E2E 必须覆盖：

```text
Define child worker user-confirmed repair 后生成一致 child closure
Keep in main flow user-confirmed repair 后不生成 child / handoff / invoke
required output producer 不因 binding drift 产生
负例不产生 overlay
```

Repair closure artifact bundle 必须包含：

```text
before/after final_spl.txt
before/after compile diagnostics
before/after issue inventory
preview summary
verification result
PromotionResolutionMarker summary
child worker / handoff / invoke / result binding summary
provenance/evidence summary
manifest.json with hashes
```

### 12.5 测试计划

运行并记录：

```text
.venv\Scripts\python.exe -m pytest tests/unit/compiler/spl_editing tests/integration/compiler/spl_editing -q
.venv\Scripts\python.exe examples/output/spl_editing_demo/run_demo.py --run demo --e2e-worker-delegation
python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py --scope all --format json
ruff check <touched files>
git diff --check
```

### 12.6 验收标准

APW7b 通过条件：

1. APW0a 中与 repair closure / producer binding 相关的 current-behavior locks 已转为目标行为断言。
2. Define child worker 和 keep-main-flow 均 Lane B accepted。
3. 负例不产生 overlay。
4. Artifact bundle hash 可复验。
5. 无新增未豁免 P0/P1 IRS audit finding。

### 12.7 PM 审核清单

1. 是否 Define child worker 和 keep-main-flow 都用真实 demo 路径验证。
2. 是否保存 before/after artifact。
3. 是否 marker / result binding / ProducerIndex 证据完整。
4. 是否没有通过关闭 diagnostic 或跳过 replay 让 E2E 变绿。

---

## 13. Decision Gate：Residual Candidate Policy

### 13.1 目标

确认 mixed candidate 的 residual spans 在信息不足时如何处理，避免实现中出现 silent loss 或过度 worker extraction。

### 13.2 推荐决策

本计划采用：

```text
如果 residual spans 不能独立证明 worker boundary：
  decision = keep_in_main_worker
  audit reason = residual_after_api_exclusion_insufficient

如果 residual spans 明确是 delegation policy：
  保留 WORKER_PROMOTION source signal，不直接 materialize child worker

如果 residual spans 明确是 executable main-flow work：
  进入正常 main-flow / Stage 7 路径，不创建 child worker
```

### 13.3 必须回答的问题

该 gate 必须在 APW1 完成后、APW2 开始前确认。原因是 residual policy 依赖 `WorkerBoundaryExclusionView` 的真实字段语义，尤其是 `api_consumed_span_ids`、`api_residual_span_ids` 和 `api_call_demand_ids_by_span`。

进入 APW2 前必须确认：

1. residual candidate 是否允许继续送入 Stage 3.5b LLM decision。
2. residual candidate 的 risks/signals/status 是否重算，还是标记为 needs re-evaluation。
3. ambiguous residual 是否产生 diagnostic，还是仅 audit。
4. 如何在 artifact 中解释 API span 被移除但 residual 被保留。

### 13.4 验收标准

1. PM 明确批准 residual policy 后进入 APW2。
2. APW2 tests 必须覆盖该 policy 的所有分支。
3. Gate review 使用 APW1 产出的真实 view payload，而不是只停留在文档推演。

---

## 14. 端到端验收场景

### 14.1 API-only span 不生成 child worker

步骤：

1. 运行 `examples/usage.py` 生成 demo。
2. 检查 `external_capability_intent_resolver.json` 中 `s16` 为 confirmed API invocation。
3. 检查 Stage 3.5 artifacts。
4. 检查 final SPL。

期望：

```text
s16 -> API_DECLARATION + CALL_API
s16 不出现在 child worker owned_span_ids
无 Worker_retrieve_approved_sources 自动生成
```

### 14.2 Delegation policy 仍产生 WORKER_PROMOTION

步骤：

1. 检查 `s31` 对应 diagnostic。
2. 运行 `run_demo.py --run demo --list-only`。

期望：

```text
存在 WORKER_PROMOTION issue
subject 指向 delegated policy / source gathering or template matching
不显示未确认 child worker name
```

### 14.3 Define child worker repair

步骤：

1. 在 demo 中选择 WORKER_PROMOTION issue。
2. 选择 `Define this work as a child worker`。
3. 提交结构化输入。
4. preview、confirm、apply。

期望：

```text
Lane B accepted
PromotionResolutionMarker(user_confirmed=true)
child output / handoff output / invoke result / parent binding 一致
无 missing_output_producer regression
final SPL 可见 child worker closure
```

### 14.4 Keep in main flow repair

步骤：

1. 选择同一 WORKER_PROMOTION issue。
2. 选择 `Keep this work in the main workflow`。
3. preview、confirm、apply。

期望：

```text
Lane B accepted
不生成 child worker / handoff / invoke
marker resolution_kind=converted_to_main_flow_step
原 promotion diagnostic resolved
```

### 14.5 负例矩阵

必须覆盖：

```text
API-only extract_child_worker stale decision
mixed candidate silent residual loss
invalid boundary_kind=integration_call
unconfirmed marker
marker target mismatch
result binding mismatch
duplicate materialized refs
unrelated worker refs
```

期望：

```text
被 validator / verifier 拒绝
不产生 overlay
不 suppress compiler diagnostic
```

---

## 15. PM 总审核清单

每个阶段提交审核时，PM 必须检查：

1. 是否严格对齐 `stage3_5_api_worker_promotion_boundary_solution_design_zh.md`。
2. 是否扩大到 API semantic validation、REQUEST_INPUT repair closure 或全量 worker rewrite。
3. 是否新增未确认的 LLM prompt/schema 变更。
4. 是否新增 rule-based keyword fallback。
5. 是否直接删除 mixed candidate 而不是 split/trim residual。
6. 是否使用了不存在的 enum，例如 `integration_call`。
7. 是否让 Stage 3.5 直接写 `PromotionResolutionMarker`。
8. 是否让 presentation 单独信任 `derived_child_worker_id`。
9. 是否把 marker target match 写成 substring match。
10. 是否让 patch verifier 代替 ProducerIndex / post-normalize IRS / DiagnosticDiff。
11. 是否 GenericEvidenceVerifier 膨胀为 closure-specific 业务 verifier。
12. 是否通过 suppress diagnostic 让 demo 绿色。
13. 是否所有新增路径都有负例测试。
14. 是否无新增 skip / xfail。
15. 是否触达文件 ruff clean。
16. 是否 `git diff --check` 通过。
17. 是否真实运行 demo E2E。
18. 是否保存可复查 artifact bundle。

---

## 16. 阶段完成顺序

推荐顺序：

```text
APW0  Current Gap Lock
APW1  WorkerBoundaryExclusionView
Gate  Residual Candidate Policy
APW2  Candidate Sanitizer
APW3  Prompt Context + Decision / Materializer Guard
APW4  WORKER_PROMOTION Subject Projection
APW5  PromotionResolutionMarker Lifecycle Hardening
APW6  DefineChildWorkerClosure Result Binding Invariant
APW7a Demo Baseline E2E
APW7b Repair Closure E2E + Artifact Bundle + Cleanup
```

依赖关系：

```text
APW0 必须最先完成。
APW1 是 APW2 / APW3 的前置。
Residual Candidate Policy gate 必须在 APW1 后、APW2 前完成。
APW2 必须在 APW3 materializer guard 前完成。
APW4 可在 APW2 后并行推进，但最终 E2E 依赖 APW3。
APW5 是 APW6 的前置。
APW7a 依赖 APW1-APW4。
APW6 是 APW7b Define-child E2E 的前置。
APW7b 只能在 APW1-APW6 和 APW7a 全部完成后执行。
```

---

## 17. 最终交付物

最终提交必须包含：

```text
1. WorkerBoundaryExclusionView 实现与测试。
2. Stage 3.5 sanitizer / prompt context / validator / materializer guard。
3. WORKER_PROMOTION subject projection 修复。
4. PromotionResolutionMarker lifecycle hardening。
5. DefineChildWorkerClosure result binding verifier。
6. Unit / integration / E2E tests。
7. Demo acceptance artifact bundle。
8. IRS audit / ruff / diff-check / pytest 结果。
9. 更新后的设计文档或补充说明，如实现中出现已批准的设计偏差。
```

最终验收必须证明：

```text
s16 只作为 API invocation materialization authority。
s31 作为 worker promotion source signal 保留。
未确认 promotion 不展示 derived child worker。
用户确认后才允许 materialize child worker closure。
child closure 的 result binding 到 parent required output producer 全链路闭合。
```
