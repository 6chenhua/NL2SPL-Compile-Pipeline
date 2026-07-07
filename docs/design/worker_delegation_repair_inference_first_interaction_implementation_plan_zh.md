# Worker Delegation Repair Inference First Interaction 实施计划

本文档严格基于 [`../problem/worker_delegation_repair_inference_first_interaction_design.md`](../problem/worker_delegation_repair_inference_first_interaction_design.md) 制定，并以当前已完成的 `RepairDraftingSubsystem` Release 1 为前置基础。

实施目标是：在现有 drafting substrate 上，把 `WORKER_PROMOTION.define_child_worker` 的用户体验从“用户填写 technical worker contract 表单”升级为“系统基于 artifacts 推断 repair draft，用户只确认或补充核心业务语义”，同时保持既有 Admission / Materialization / Preview-Apply seal / Lane B verification authority 不变。

当前项目状态假设：

```text
已存在：
  RepairDraftingSubsystem substrate
  UserRepairInput / InferredRepairDraft / FieldInference / StoredRepairDraft
  RepairInferenceProviderRegistry / RepairDraftingService
  WorkerDelegationInferenceProvider
  DraftAdmissionBridge
  CLI/demo draft-first path
  Release 1 Freeze artifact

本计划继续强化：
  Worker Delegation inference quality
  typed read-only views
  low-confidence clarification
  dependency-aware placement
  output/result binding inference
  user-facing draft preview
  negative matrix
```

执行前置条件必须可复验，而不是口头假设。WDI0 必须确认：

```text
artifacts/reviews/repair_drafting/RD7_freeze/manifest.json 存在
RD7 freeze verdict 为 pass 或 accepted conditional_pass
WorkerDelegationInferenceProvider baseline E2E artifact 存在
```

不在本计划范围内：

```text
1. 迁移 missing_handler / missing_output_producer / REQUEST_INPUT.value_target provider。
2. 启用生产默认 LLM inference。
3. 重写 Worker Delegation v2 materialization / verifier。
4. 重写 Stage 3.5 / Stage 5 / Stage 7 pipeline。
5. 让 inference provider 构造 IR / patch payload / MaterializationPlan。
```

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
Stage 3 / Stage 3.5 artifacts
  -> PromotionCandidateView / WorkerBoundaryExclusionView / SanitizedCandidateResult
  -> 只提供 source-backed promotion signal 和 candidate facts

Stage 5 / Stage 7 artifacts
  -> WorkerPlacementView / PlacementStepView / ConsumerIndexView
  -> 只提供 block / step / source-span / data dependency read-only projection

SelectableRefSet / Symbol table / ProducerIndex
  -> SelectableRefView / OutputDemandView / ProducerDemandView
  -> 只提供合法 ref、required output、consumer / producer facts

WorkerDelegationInferenceProvider
  -> InferredRepairDraft
  -> responsibility / input refs / returned result / placement / result binding
  -> confidence / evidence_refs / trace / clarification
  -> 不 Admission、不 Materialize、不 Verify

DraftAdmissionBridge
  -> 校验 typed RepairFieldValue、refs、new outputs、placement policy
  -> 转为 existing Worker Delegation directive

Existing Worker Delegation v2 materialization
  -> materialized preview / overlay
  -> 不重新解释 free_text

Lane B + closure-specific verifier
  -> 验证 child worker / handoff / invoke / parent binding / ProducerIndex closure
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. Inference provider 不构造 `StepIR`、`BlockIR`、`WorkerIR`、`WorkerHandoffIR`。
2. Inference provider 不生成 patch payload、不写 overlay、不写 snapshot、不写 evidence。
3. Provider identity 仍为 `(affordance_id, strategy_id, option_id)`。
4. 本计划只强化 `worker_delegation.complete_closure.v2 / define_child_worker`。
5. `keep_in_main_flow` 仍走既有路径，不在本计划迁移。
6. Typed views 不得返回 `object` 作为 provider authority。
7. Typed views 不得解析 `diagnostic.message`、UI display text、rendered SPL。
8. `SelectableRefSet` 是 input refs 的唯一 ref authority。
9. `NewOutputAdmission` 是 new child output 的唯一 admission authority。
10. required output gap 存在时不得自动降级为 parent-local temporary。
11. DraftPreview 不承诺 final handoff / step / block IDs。
12. MaterializedPreview 必须与 apply 后 closure 一致。
13. API-owned span 不得成为 child-worker-owned span。
14. 所有 non-blocked inferred fields 必须有 `confidence`、非空 `evidence_refs`、trace coverage。
15. 不新增未批准 LLM prompt/schema；LLM 只能通过本计划的 Decision Gate。

`evidence_refs` 可以引用 source-backed artifact、user-confirmed intent 或 policy evidence，但必须显式区分：

```text
source span evidence: s16, s31, ...
user intent evidence: user_input:free_text
policy evidence: policy_ref:worker_delegation.input.explicit_none
```

不得把 policy evidence 或 user intent evidence 伪装成 source-backed evidence。

---

## 3. LLM / Rule-based 决策约束

本计划默认 deterministic-only。

允许的确定性逻辑：

- 从 typed artifact views 读取 promotion candidate、source spans、selectable refs、consumer index、output demand。
- 根据 stable ref roles 选择 input refs / binding targets。
- 根据 first consumer 和 input availability 推断 placement。
- 根据 required output / downstream consumer / alias table 推断 returned result。
- 低置信度时生成 clarification。

禁止的 fallback：

1. 用关键词从 raw source text 直接决定 child worker closure。
2. 用 `diagnostic.message` 解析 responsibility / output / placement。
3. 根据 free_text 生成 raw variable name。
4. 根据 free_text 选择 patch type。
5. 让 LLM 或规则绕过 SelectableRefSet / NewOutputAdmission。

需要 PM 前置确认的行为：

1. 新增 bounded LLM inference。
2. 新增 semantic similarity threshold。
3. 新增 alias matching policy。
4. 改变 parent-local temporary 允许条件。
5. 修改 Worker Delegation v2 materializer/verifier。

---

## 4. Phase WDI0：当前实现基线与差距锁定

### 4.1 目标

锁定当前 RD7 后的 worker delegation draft-first 行为，并明确本计划要修正的 remaining gaps。

WDI0 同时是本专项计划的前置验收阶段，必须核查 RepairDraftingSubsystem Release 1 Freeze artifact，证明本计划确实建立在 RD0-RD7 已闭合的 substrate 上。

### 4.2 可编辑范围

允许新增：

```text
tests/unit/compiler/spl_editing/drafting/providers/test_worker_delegation_inference_gap_lock.py
artifacts/reviews/worker_delegation_inference/WDI0/
```

允许修改：

```text
仅允许测试和 review artifact。
```

### 4.3 禁止改动

WDI0 禁止修改：

```text
src/nl2spl/compiler/spl_editing/drafting/
src/nl2spl/compiler/spl_editing/presentation/
examples/output/spl_editing_demo/run_demo.py
```

### 4.4 设计要求

WDI0 prerequisite 必须记录：

```text
release1_freeze_manifest_ref
release1_worker_delegation_e2e_ref
release1_freeze_verdict
```

Characterization 必须记录：

```text
当前 responsibility from free_text 的证据行为
当前 input refs inference 行为
当前 output draft inference 行为
当前 placement = append 的默认行为
当前 result binding target 选择行为
当前 preview 中是否展示 internal refs
当前 low-confidence clarification 行为
```

### 4.5 测试计划

新增测试必须覆盖：

1. 当前 draft-first happy path 通过。
2. 当前每个 non-blocked field 有 evidence / trace。
3. 当前 typed views 是否仍返回 `object`。
4. 当前 placement 是否只固定 append。
5. 当前 result binding 是否可能落到不合适 target。
6. 当前 required-output gap 是否有保护。

### 4.6 验收标准

WDI0 通过条件：

1. Characterization tests 在当前代码上通过。
2. 不修改生产代码。
3. 差距清单写入 `review_report.md`。
4. RD7 Freeze manifest 与 worker delegation baseline E2E artifact 可复验。
5. 无 skip / xfail。

### 4.7 PM 审核清单

审核时必须检查：

1. WDI0 是否没有生产 diff。
2. 是否把当前不足记录为 gap，而不是立即修。
3. 是否没有把 Release 1 已完成作为口头前提。
4. 是否没有扩大到 missing_handler / missing_output_producer。

---

## 5. Phase WDI1：Typed View Hardening

### 5.1 目标

把 Worker Delegation inference 使用的 read-only views 从弱类型 `object` projection 收紧为明确 DTO，防止 provider 从 raw object 临时取字段。

### 5.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/views/types.py
tests/unit/compiler/spl_editing/drafting/views/test_worker_delegation_typed_view_contract.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/drafting/views/selectable_refs.py
src/nl2spl/compiler/spl_editing/drafting/views/placement.py
src/nl2spl/compiler/spl_editing/drafting/views/producer.py
src/nl2spl/compiler/spl_editing/drafting/views/worker_delegation.py
src/nl2spl/compiler/spl_editing/drafting/providers/worker_delegation.py
```

### 5.3 禁止改动

WDI1 禁止修改：

```text
src/nl2spl/compiler/spl_editing/materialization/
src/nl2spl/compiler/spl_editing/patches/
src/nl2spl/compiler/pipeline/
```

### 5.4 设计要求

新增或收紧 DTO：

```python
SelectableRefView
PlacementStepView
OutputDemandItemView
PromotionCandidateDraftView
```

View methods 必须返回：

```text
tuple[SelectableRefView, ...]
tuple[PlacementStepView, ...]
tuple[OutputDemandItemView, ...]
```

不得返回：

```text
tuple[object, ...]
raw SelectableRef object as provider authority
raw StepIR / WorkerIR
```

### 5.5 测试计划

新增测试必须覆盖：

1. `SelectableRefsDraftingView.refs_by_role()` 返回 `SelectableRefView`。
2. `stable_ref_ids_for_role()` 只返回 stable IDs。
3. placement view 返回 `PlacementStepView`，不暴露 raw step。
4. output demand view 区分 unresolved required output 和 binding target。
5. worker delegation provider 不直接访问 raw ref object fields。

### 5.6 验收标准

WDI1 通过条件：

1. `rg -n "tuple\\[object|-> object|Any|cast\\(|getattr\\(|__dict__|vars\\(" src/nl2spl/compiler/spl_editing/drafting/views src/nl2spl/compiler/spl_editing/drafting/providers/worker_delegation.py` 无未解释的不合规命中。
2. Typed view tests 通过。
3. Existing RD7 E2E 不回退。

### 5.7 PM 审核清单

审核时必须检查：

1. Provider 是否只消费 typed view DTO。
2. View 是否只做 read-only projection。
3. 是否没有引入 pipeline stage mutation。

---

## 6. Phase WDI2：Responsibility Inference 与 Clarification

### 6.1 目标

将 responsibility 推断从“free_text 优先 / candidate summary fallback”升级为可审计的 task-boundary inference，支持单候选直接采用、多候选 clarification。

### 6.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/drafting/providers/worker_delegation_policy.py
tests/unit/compiler/spl_editing/drafting/providers/test_worker_delegation_responsibility_inference.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/drafting/providers/worker_delegation.py
src/nl2spl/compiler/spl_editing/drafting/views/worker_delegation.py
```

### 6.3 禁止改动

WDI2 禁止修改：

```text
src/nl2spl/compiler/spl_editing/interaction/
src/nl2spl/compiler/spl_editing/materialization/
```

### 6.4 设计要求

Responsibility inference 输入：

```text
user_input.free_text
PromotionCandidateDraftView.task_text
candidate_source_span_ids
SanitizedCandidateResult residual state
subject summary
```

规则：

```text
1. user free_text 可作为 explicit user intent，evidence_ref = user_input:free_text。
2. 单一 source-backed candidate 可 high/medium confidence 采用。
3. 多任务候选不得默认 both。
4. ambiguous candidate 必须生成 RepairClarificationQuestion。
5. API-owned spans 必须从 evidence_refs 中排除。
```

`user_input:free_text` 是 user-confirmed intent evidence，不是 source-span evidence；它可以表达当前修复的用户意图，但不得用于声称原始 source text 已经具备该 task boundary。

### 6.5 测试计划

新增测试必须覆盖：

1. free_text responsibility 使用 `user_input:free_text`。
2. source-backed single candidate 使用 source span evidence。
3. multi-candidate 生成 clarification。
4. ambiguous “source gathering or template matching” 不默认 both。
5. API-owned span 不进入 evidence_refs。
6. blocked responsibility 不进入 Admission。

### 6.6 验收标准

WDI2 通过条件：

1. responsibility field/trace evidence 非空。
2. low-confidence path 有 clarification。
3. no overlay produced when required clarification missing。
4. Existing E2E 不回退。

### 6.7 PM 审核清单

审核时必须检查：

1. 是否没有关键词 fallback。
2. 是否没有从 diagnostic.message 解析 responsibility。
3. clarification 是否面向用户而非开发者。

---

## 7. Phase WDI3：Input Ref Inference

### 7.1 目标

强化 input refs 推断，使其基于 SelectableRefSet、scope legality、candidate possible inputs，而不是固定选择 `user_request`。

### 7.2 可编辑范围

允许新增：

```text
tests/unit/compiler/spl_editing/drafting/providers/test_worker_delegation_input_ref_inference.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/drafting/providers/worker_delegation.py
src/nl2spl/compiler/spl_editing/drafting/providers/worker_delegation_policy.py
src/nl2spl/compiler/spl_editing/drafting/views/selectable_refs.py
```

### 7.3 禁止改动

WDI3 禁止修改：

```text
src/nl2spl/compiler/spl_editing/selectable_refs/model.py
src/nl2spl/compiler/spl_editing/interaction/validation.py
```

### 7.4 设计要求

Input inference 必须：

```text
1. 只选择 ref_role == selectable_input。
2. 优先 parent worker scope 可用 refs。
3. 优先 candidate possible_inputs 显式匹配 refs。
4. 若无必要输入，使用 ExplicitNoneValue。
5. 多个同等候选时生成 clarification。
6. 不生成 raw variable name。
```

### 7.5 测试计划

新增测试必须覆盖：

1. `user_request` 不再是硬编码唯一选择。
2. possible input name 匹配到 selectable ref。
3. out-of-scope ref 不可选。
4. target_output ref 不可被当 input。
5. 无输入时 `ExplicitNoneValue`。
6. ambiguous inputs 返回 clarification。

### 7.6 验收标准

WDI3 通过条件：

1. unknown ref 无法进入 draft field。
2. selected input refs 均可被 Admission 接受。
3. no raw variable name 出现在 draft JSON。

### 7.7 PM 审核清单

审核时必须检查：

1. SelectableRefSet 是否仍是唯一 input ref authority。
2. provider 是否没有自己创建 ref ids。
3. input inference trace 是否可解释。

---

## 8. Phase WDI4：Output / Result Binding Inference

### 8.1 目标

强化 returned result 与 parent binding 推断，避免 silent downgrade required output gap 到 parent-local temporary。

### 8.2 可编辑范围

允许新增：

```text
tests/unit/compiler/spl_editing/drafting/providers/test_worker_delegation_output_binding_inference.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/drafting/providers/worker_delegation.py
src/nl2spl/compiler/spl_editing/drafting/providers/worker_delegation_policy.py
src/nl2spl/compiler/spl_editing/drafting/views/producer.py
src/nl2spl/compiler/spl_editing/drafting/views/worker_delegation.py
```

### 8.3 禁止改动

WDI4 禁止修改：

```text
src/nl2spl/compiler/spl_editing/admission/output_declaration.py
src/nl2spl/compiler/spl_editing/verification/
```

### 8.4 设计要求

Output matching priority：

```text
1. exact canonical id
2. declared required output canonical name
3. alias / normalized symbol alias
4. deterministic bounded match from approved alias table / normalized symbol alias / candidate possible_outputs exact or normalized match
5. clarification required
```

Release WDI0-WDI7 默认禁止：

```text
文本相似度 threshold
LLM semantic match
从 free_text 直接 admission 新 binding
```

如确需引入更宽的 semantic match，必须先通过独立的 `Output Semantic Match Policy Gate`，明确 allowed candidates、threshold、preview disclosure 和 negative tests。

Parent-local temporary 仅允许：

```text
no required output gap
no downstream required consumer
no declared output alias
not exported to [OUTPUTS]
```

### 8.5 测试计划

新增测试必须覆盖：

1. required output gap 存在时绑定 required output。
2. downstream consumer 存在时绑定 consumer-visible parent symbol。
3. no required output / no consumer 时才允许 parent-local temporary。
4. parent-local temporary 不进入 `[OUTPUTS]`。
5. parent-local temporary 不触发 `missing_output_producer`。
6. ambiguous output 返回 clarification。
7. free_text 相似表达不得绕过 required output / alias policy 直接产生 binding。

### 8.6 验收标准

WDI4 通过条件：

1. required output gap 不 silent downgrade。
2. ProducerIndex closure E2E 通过。
3. result binding field/trace evidence 非空。

### 8.7 PM 审核清单

审核时必须检查：

1. 是否仍由 NewOutputAdmission admit new child output。
2. 是否没有新增 parent required output。
3. 是否没有 suppress `missing_output_producer`。

---

## 9. Phase WDI5：Dependency-aware Placement Inference

### 9.1 目标

将 placement 从固定 `append` 升级为 dependency-aware policy：优先放在 first consumer 前，同时确保 input refs 已可用、不会跨错误 flow/block。

### 9.2 可编辑范围

允许新增：

```text
tests/unit/compiler/spl_editing/drafting/providers/test_worker_delegation_placement_inference.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/drafting/providers/worker_delegation.py
src/nl2spl/compiler/spl_editing/drafting/providers/worker_delegation_policy.py
src/nl2spl/compiler/spl_editing/drafting/views/placement.py
```

### 9.3 禁止改动

WDI5 禁止修改：

```text
src/nl2spl/pipeline/stages/stage5*
src/nl2spl/pipeline/stages/stage7*
src/nl2spl/compiler/spl_editing/materialization/
```

### 9.4 设计要求

Placement preconditions：

```text
1. selected input refs 在 placement 前可用。
2. invoke output 在 first consumer 前可用。
3. 不跨 exception-flow / alternative-flow 边界错误移动。
4. 不把 API-owned span 变成 child-worker-owned。
5. 不制造 cycle。
6. placement anchor 属于 parent worker scope。
```

placement precondition failure 的默认行为是 blocked draft，并给出 system-facing explanation。只有当缺失的是业务决策，并且该业务决策会改变 placement 时，才允许提出 user-facing clarification。普通用户不得被要求选择 raw `placement_ref`、`step_id`、`block_id` 或 technical anchor。

### 9.5 测试计划

新增测试必须覆盖：

1. first consumer 前 placement。
2. input unavailable before anchor -> blocked；只有业务决策缺失时才产生非技术 clarification。
3. no consumer -> source-near block tail / append fallback with trace。
4. cross-flow invalid placement rejected。
5. API-owned span placement rejected。
6. placement draft preview 不展示 final step id。
7. clarification 不要求用户选择 raw placement_ref / step_id / block_id。

### 9.6 验收标准

WDI5 通过条件：

1. placement 不再固定 append。
2. invalid placement 不进入 Admission。
3. Lane B E2E 不回退。

### 9.7 PM 审核清单

审核时必须检查：

1. 是否没有在 provider 内重排 Stage 5/7 artifacts。
2. placement trace 是否说明 first consumer / fallback reason。
3. MaterializedPreview 是否仍由 existing preview/apply 产生。

---

## 10. Phase WDI6：Draft Preview UX 与 CLI Prompt Cleanup

### 10.1 目标

让 CLI / demo 展示用户可理解的 draft preview，而不是 internal contract 表单；修复 subject summary 换行污染 input prompt 的问题。

### 10.2 可编辑范围

允许新增：

```text
tests/unit/compiler/spl_editing/presentation/test_worker_delegation_draft_preview_ux.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/presentation/service.py
src/nl2spl/compiler/spl_editing/presentation/model/drafting.py
examples/output/spl_editing_demo/run_demo.py
```

### 10.3 禁止改动

WDI6 禁止修改：

```text
src/nl2spl/compiler/spl_editing/drafting/admission/
src/nl2spl/compiler/spl_editing/materialization/
```

### 10.4 设计要求

Draft preview 默认展示：

```text
Create child worker
Use inputs
Return
Insert
Bind result
Clarification questions, if any
```

Advanced details 才展示：

```text
selected_ref_ids
placement_intent
placement_policy_reason
expected binding target
parent-local temporary intent
verification lane intent
```

以下内容只能出现在 MaterializedPreview 或 audit details 中：

```text
final handoff_id
final invoke step id
final block id
final stage slices
final marker refs
```

CLI input prompt 必须：

```text
sanitize multiline subject summary
wrap long text
not expose raw target_ref by default
```

### 10.5 测试计划

新增测试必须覆盖：

1. multiline subject summary 不破坏 prompt。
2. DraftPreview 不显示 final internal IDs。
3. DraftPreview advanced details 只显示 intent / policy / expected binding，不显示 final IDs。
4. clarification questions 只在需要时显示。
5. default Enter accept path 不要求 technical fields。
6. MaterializedPreview / audit details 才显示 final handoff / invoke / block / marker refs。

### 10.6 验收标准

WDI6 通过条件：

1. CLI 不再询问 `placement_ref`、`input_empty_semantics`、`result_usage`、handoff binding、invoke output。
2. 用户可通过 Enter 接受 high-confidence draft。
3. Preview 与 materialized preview 语义一致。

### 10.7 PM 审核清单

审核时必须检查：

1. 是否只是换文案而没有改变 interaction flow。
2. 是否没有把 internal fields 默认暴露给普通用户。
3. 是否没有破坏 keep_in_main_flow existing path。

---

## 11. Phase WDI7：Admission / Verification Negative Matrix

### 11.1 目标

补齐 Worker Delegation inference 到 Admission / Verification 的负例矩阵，确保推断质量问题不会到 materialization 后才暴露。

### 11.2 可编辑范围

允许新增：

```text
tests/integration/compiler/spl_editing/test_worker_delegation_inference_negative_matrix.py
artifacts/reviews/worker_delegation_inference/WDI7/
```

允许修改：

```text
tests/integration/compiler/spl_editing/test_worker_delegation_drafting_e2e.py
examples/output/spl_editing_demo/run_demo.py
```

### 11.3 禁止改动

WDI7 禁止修改：

```text
src/nl2spl/compiler/spl_editing/verification/
src/nl2spl/compiler/spl_editing/materialization/
```

除非发现真实 bug，并单独回到对应 phase 修复。

### 11.4 设计要求

Negative matrix 必须覆盖：

```text
unknown ref
raw variable name
free-text placement id
API-owned span
required output silent downgrade
orphan child worker
orphan handoff
orphan invoke
stale draft
missing materialized preview acceptance
ambiguous responsibility unanswered
```

### 11.5 测试计划

新增测试必须覆盖：

1. 每个 negative case rejected before overlay 或 verifier rejected。
2. rejected case 不产生 overlay。
3. rejected case 不 suppress diagnostic。
4. accepted case Lane B accepted。

### 11.6 验收标准

WDI7 通过条件：

1. Negative matrix 全部通过。
2. Release E2E artifact bundle 可复验。
3. no new `missing_output_producer` / `type_or_contract_ambiguity` / orphan diagnostics。
4. `run_demo.py --run demo --e2e-worker-delegation` 通过。

### 11.7 PM 审核清单

审核时必须检查：

1. 是否真实跑 demo E2E。
2. negative 是否无 overlay。
3. artifact bundle 是否包含 before/after diagnostics、draft、materialized preview、verification result。

---

## 12. Decision Gate：Bounded LLM Inference

### 12.1 目标

确认是否在 Worker Delegation inference 中引入 LLM typed-plan。默认不启用。

### 12.2 可选方案

```text
方案 A：保持 deterministic-only。
方案 B：只在 responsibility / expected result 的 bounded alternatives 内使用 LLM。
方案 C：允许 LLM 生成 provider-local typed plan。
```

推荐方案 A 作为本轮交付；方案 B 作为后续灰度。

### 12.3 必须明确的问题

方案确认文档必须回答：

1. LLM 输入是否包含 raw source text。
2. LLM 输出 schema 是什么。
3. 是否允许 LLM 输出 selected_ref_ids。
4. 如何验证 unknown refs。
5. LLM output hash 是否进入 preview seal。
6. deterministic conflict 谁优先。

### 12.4 验收标准

该门禁通过条件：

1. PM 明确批准。
2. typed-plan schema 有负例测试。
3. no generic LLM fallback。
4. LLM 不成为 WDI0-WDI7 的依赖。

---

## 13. 端到端验收场景

最终必须具备以下 E2E 或高保真集成覆盖：

1. **High-confidence draft accept**
   - 用户选择 `Define this work as a child worker`。
   - 系统生成 draft preview。
   - 用户 Enter 接受。
   - MaterializedPreview 显示 child worker + invoke。
   - Apply 后 Lane B accepted。
   - 原 WORKER_PROMOTION diagnostic resolved。

2. **Ambiguous responsibility clarification**
   - candidate 包含多个任务边界。
   - 系统不默认 both。
   - CLI 显示最少 clarification。
   - 用户选择后生成 draft。
   - 未选择时不产生 overlay。

3. **Required output binding**
   - 存在 matching required output gap。
   - 系统绑定 required output。
   - 不创建 parent-local temporary。
   - ProducerIndex closure accepted。

4. **Placement before first consumer**
   - child output 有 first consumer。
   - invoke placement 在 first consumer 前。
   - input refs 在该位置前可用。
   - final SPL 顺序正确。

5. **Negative unknown ref**
   - draft 或 user edit 引入 unknown ref。
   - Admission rejected。
   - 无 overlay。

6. **Negative API-owned span**
   - candidate span 已被 API authority 消费。
   - 不进入 child worker responsibility evidence。
   - 无 child-worker-owned API span。

---

## 14. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐本计划和设计文档。
2. 是否只修改 `define_child_worker` worker delegation inference。
3. 是否没有迁移 RD8-RD13 provider。
4. 是否新增未确认 LLM。
5. 是否让 provider 构造 IR / patch payload。
6. 是否让 typed view 返回 `object`。
7. 是否从 `diagnostic.message` / UI text / rendered SPL 解析事实。
8. 是否用 raw variable name 代替 selectable ref id。
9. 是否 silent downgrade required output。
10. 是否默认暴露 technical fields 给用户。
11. 是否跳过 Admission / MaterializedPreview / Lane B。
12. 是否有 skip / xfail / 弱断言。
13. 是否真实运行 demo E2E。
14. 是否生成可复验 artifact bundle。

建议反模式扫描：

```powershell
rg -n "tuple\\[object|-> object|Any|cast\\(|getattr\\(|__dict__|vars\\(|diagnostic\\.message|patch_payload|StepIR|BlockIR|WorkerIR|WorkerHandoffIR|generic.*LLM|semantic.*threshold|placement_ref|step_id|block_id|input_empty_semantics|result_usage|skip|xfail" src/nl2spl/compiler/spl_editing/drafting src/nl2spl/compiler/spl_editing/presentation tests/unit/compiler/spl_editing/drafting tests/integration/compiler/spl_editing
```

命中项必须逐条说明是否合规。

---

## 15. 阶段完成顺序

推荐顺序：

```text
WDI0  当前实现基线与差距锁定
WDI1  Typed View Hardening
WDI2  Responsibility Inference 与 Clarification
WDI3  Input Ref Inference
WDI4  Output / Result Binding Inference
WDI5  Dependency-aware Placement Inference
WDI6  Draft Preview UX 与 CLI Prompt Cleanup
WDI7  Admission / Verification Negative Matrix
Gate  Bounded LLM Inference
```

依赖关系：

- WDI0 必须最先完成。
- WDI1 是 WDI2-WDI5 的前置条件。
- WDI2-WDI5 可分支开发，但 WDI7 前必须全部完成。
- WDI6 依赖 WDI2-WDI5 的 draft field 语义稳定。
- WDI7 是最终冻结审核。
- Bounded LLM gate 不属于 WDI0-WDI7 完成条件。

---

## 16. 交付证据要求

每个 phase 必须提交：

```text
artifacts/reviews/worker_delegation_inference/WDI<N>/
  review_report.md
  commands.log
  pytest_output.txt
  ruff_output.txt
  diff_check_output.txt
  manifest.json
```

WDI7 必须额外提交：

```text
worker_delegation_inference_e2e/
  user_input.json
  inferred_draft.json
  draft_preview.txt
  materialized_preview.json
  before_diagnostics.json
  after_diagnostics.json
  rendered_spl_after.txt
  verification_result.json
  diagnostic_diff.json
```

PM 不接受仅口头说明“已通过”。所有结果必须可复验。

---

## 17. 2026-07-05 修订：Field-confirmed Define-Child Draft Contract

本节是 WDI0-WDI7 的正式修订基线。若本节与前文阶段描述存在冲突，以本节为准。

修订来源：

- [`worker_delegation_child_worker_field_confirmed_draft_design_zh.md`](worker_delegation_child_worker_field_confirmed_draft_design_zh.md)

### 17.1 修订目标

`define_child_worker` 不能只展示一个整体 draft 并让用户一键确认。它创建的是新的执行单元，因此必须把 child worker 的核心业务契约拆成四个可见、可确认、可覆盖的 semantic fields：

```text
child_task
child_inputs
child_output
child_business_logic
```

系统可以先生成 suggested answers，但用户必须对四个字段逐项接受默认值或覆盖。只有四个 semantic fields 都被确认后，才能进入 `DraftAdmissionBridge`、materialized preview、apply 和 Lane B verification。

### 17.2 不新增并行 Draft 生命周期

本修订不得新增第二套 draft root、draft store、directive bridge 或 apply authority。

必须继续复用：

```text
UserRepairInput
InferredRepairDraft
FieldInference
RepairFieldValue
StoredRepairDraft
DraftAdmissionBridge
NormalizedWorkerDelegationDirective
Worker Delegation v2 materialization
Lane B verification
```

允许新增 provider-scoped projection / view，但它只能挂在现有 `InferredRepairDraft` / `FieldInference` 体系下。

禁止新增：

```text
ChildWorkerSemanticDraftStore
ChildWorkerSemanticAdmission
independent materialization path
```

### 17.3 Phase Mapping 修订

原 WDI2-WDI7 调整为：

```text
WDI2 Responsibility Inference
  输出 child_task confirmable field。

WDI3 Input Ref Inference
  输出 child_inputs confirmable field。
  input candidates 来自 SelectableRefSet ref_role=selectable_input。
  UI 展示 label/description/canonical variable name/scope hint。
  提交值必须是 SelectableRefId。

WDI4 Output / Result Binding Inference
  输出 child_output confirmable field。
  child_output 区分 display_name / proposed_canonical_name / admitted_output_id。
  result_binding 仍是 technical inferred field，不要求普通用户确认。

WDI4.5 Business Logic Inference
  新增阶段。
  输出 child_business_logic confirmable field。
  该字段是 Stage 7 repair slice 的 semantic input，但不是 StepIR authority。

WDI5 Dependency-aware Placement Inference
  placement 仍是 technical inference。
  不进入普通用户必确认字段。

WDI6 Draft Preview UX 与 CLI Prompt Cleanup
  改为 DraftConfirmationView / equivalent CLI flow。
  四个 semantic fields 必须可见展示。
  允许 Accept all suggested semantic fields，但必须逐字段记录 accepted_default。

WDI7 Admission / Verification Negative Matrix
  扩展负例矩阵，覆盖四个字段未确认、非法 input override、invalid output admission、
  business_logic undeclared ref、accept-all 字段级 evidence 等。
```

### 17.4 Confirmable Field Contract

每个 semantic field 必须携带：

```text
field_id
suggested_value
confirmed_value
confirmation_source
confidence
evidence_refs
trace
alternatives, if applicable
blocking_reason, if blocked
```

`confirmation_source` 只能是：

```text
unconfirmed
accepted_default
user_override
```

进入 `DraftAdmissionBridge` 前，以下字段不得为 `unconfirmed`：

```text
child_task
child_inputs
child_output
child_business_logic
```

### 17.5 Accept-all Contract

允许前端或 CLI 提供：

```text
Accept all suggested semantic fields
```

但必须满足：

```text
1. 四个 semantic fields 已可见展示。
2. 四个字段都有 suggested_value。
3. 后端逐字段写入 confirmation_source=accepted_default。
4. Accept-all 不确认隐藏技术字段。
```

隐藏技术字段包括：

```text
placement
handoff
invoke
binding mechanics
worker_id / step_id / block_id
verification lane
```

### 17.6 BusinessLogicValue Boundary

`child_business_logic` 必须转换为 provider-scoped typed value，例如 `BusinessLogicValue` 或等价 confirmable value。

禁止：

```python
StepIR(text=business_logic.text)
```

Stage 7 repair slice 只能通过 normalized directive 消费 business logic，并必须校验：

```text
command inputs == confirmed child_inputs
command outputs cover confirmed child_output
no undeclared ref appears
no unadmitted API/tool/resource is introduced
```

生产默认路径仍为 deterministic-only。复杂语义判断不得在 WDI0-WDI7 中引入 LLM，除非先通过 Bounded LLM Gate。

### 17.7 Child Input / Output Authority

`child_inputs`：

```text
Display: label / description / canonical variable name / scope hint
Submit: SelectableRefId
Authority: SelectableRefSet
```

`child_output`：

```text
Draft display: display_name
Draft canonical proposal: proposed_canonical_name
After admission: admitted_output_id
Authority: NewOutputAdmission
```

Draft 阶段不得承诺 final admitted output id。

### 17.8 Business Logic Conflict Rules

MVP 只允许 deterministic conflict rules：

```text
1. business_logic empty or too short。
2. business_logic references unconfirmed input/output names。
3. business_logic explicitly requests a different output from child_output。
4. business_logic introduces API/tool/resource without admission。
5. business_logic uses raw candidate/source/diagnostic id as business object。
```

复杂语义冲突必须进入 clarification；不得 silent accept 或自由语义裁决。

### 17.9 Updated WDI7 Negative Matrix

WDI7 必须新增负例：

```text
unconfirmed child_task -> blocked, no overlay
unconfirmed child_inputs -> blocked, no overlay
unconfirmed child_output -> blocked, no overlay
unconfirmed child_business_logic -> blocked, no overlay
illegal input override -> rejected before materialization
invalid output admission -> rejected before materialization
business_logic undeclared ref -> rejected
business_logic unadmitted API/tool/resource -> rejected
accept-all without visible four fields -> rejected
accept-all records no field-level accepted_default -> rejected
BusinessLogicValue directly converted to StepIR -> rejected by review
```

### 17.10 Updated E2E Requirements

真实 demo / E2E 必须覆盖：

```text
1. 用户逐项回车接受四个 suggested semantic fields -> Lane B accepted。
2. 用户 override child_inputs -> Lane B accepted。
3. 用户 override child_output -> Lane B accepted。
4. 用户 override child_business_logic -> final child command reflects confirmed logic。
5. Accept-all visible fields -> each field records accepted_default。
6. 缺任一 semantic field confirmation -> blocked, no overlay。
```

### 17.11 Implementation Freeze Condition

WDI0-WDI7 不得进入最终 freeze，除非：

```text
1. WDI implementation plan 已包含本节 contract。
2. WDI PM review criteria 已包含对应 P0/P1/P2 与阶段审核口径。
3. Review artifacts 显示四个 semantic fields 的 confirmation_source。
4. E2E artifact 包含 DraftConfirmationView / equivalent CLI transcript。
```
