# Worker Delegation 修复交互过度结构化与推断优先设计

日期：2026-07-04  
状态：conditional pass 后修订版，待评审  
相关组件：`WORKER_PROMOTION`、Worker Delegation v2、Repair Interaction Contract、RepairDirective、SelectableRefSet、Stage 3.5、Stage 5、Stage 7、ProducerIndex、Lane B verification

关联文档：

- [`worker_delegation_repair_interaction_contract_gap.md`](worker_delegation_repair_interaction_contract_gap.md)
- [`../design/spl_editing_worker_delegation_repair_interaction_and_closure_design_zh.md`](../design/spl_editing_worker_delegation_repair_interaction_and_closure_design_zh.md)
- [`../design/stage3_5_api_worker_promotion_boundary_solution_design_zh.md`](../design/stage3_5_api_worker_promotion_boundary_solution_design_zh.md)

---

## 1. 问题概述

Worker Delegation v2 已经把旧的三选项修复收敛为两个 construct-level 结果：

```text
1. Define this work as a child worker
2. Keep this work in the main workflow
```

并且已经通过 backend-owned `RepairInteractionView`、`RepairDirectiveDraft`、typed normalization、preview/apply seal、Lane B replay 等机制解决了 authority 问题。

但当前交互仍存在一个新的产品与架构问题：

```text
系统把后端 materialization 所需的完整 worker contract 字段，
直接暴露给普通用户填写。
```

例如 `Define this work as a child worker` 当前会要求用户补充：

```text
delegated responsibility
input refs
input empty semantics
returned results
invocation timing
placement anchor
result usage
additional instruction
```

这些字段中只有少数是用户真正应该提供的业务语义。其余大部分应由系统基于当前 NL2SPL artifacts、source span、symbol table、ProducerIndex、SelectableRefSet 和 worker-scoped plans 推断。

因此当前实现虽然安全，但体验上偏向“让用户填写 IR 表单”，不符合 SPL Editing 的产品目标。

---

## 2. 修订后的核心判断

正确方向不是删除结构化 contract，而是把交互模式从：

```text
form-first:
  先让用户填写完整结构化字段
  再生成 repair preview
```

升级为：

```text
inference-first / draft-first:
  系统先基于 artifacts 推断一个 repair draft
  只在关键业务语义缺失或低置信度时向用户提最少问题
  用户确认的是可理解的 repair result preview
  后端仍然通过既有 RepairDirective / RepairPatch / Materialization / Verification 链路 apply
```

必须注意：

```text
RepairInferenceLayer 只产出 candidate draft；
它不拥有 admission authority；
它不拥有 directive normalization authority；
它不拥有 repair apply authority；
它不直接 materialize WorkerIR / StepIR / WorkerHandoffIR。
```

更严格的分层是：

```text
RepairInferenceLayer
  -> InferredRepairDraft + field inference + trace + confidence + missing decisions

RepairAdmission / DirectiveBridge
  -> SelectableRefSet resolution
  -> NewOutputAdmission
  -> placement policy validation
  -> field policy validation
  -> existing RepairDirectiveDraft / NormalizedRepairDirective bridge

Existing RepairPatch / MaterializationRequest
  -> apply authority
  -> stage slices
  -> overlay

Verification
  -> Lane B
  -> ProducerIndex
  -> DiagnosticDiff
  -> closure-specific verifier
```

---

## 3. 当前交互的问题

### 3.1 暴露了后端 materialization 细节

`invocation_timing`、`placement_ref`、`result_usage`、`input_empty_semantics` 等字段是 materializer 和 verifier 需要的结构化信息，但普通用户很难理解。

例如：

```text
它应该插入到主流程什么位置？
```

这不应该默认交给用户。系统应该根据 source span order、main-flow step order、first consumer、required output gap 和 dependency 推断。

### 3.2 用户输入成本过高

用户选择“定义为子 worker”时，真实意图通常只是：

```text
这个子任务负责什么？
它应该返回什么业务结果？
```

如果系统要求用户同时理解 input refs、handoff binding、invoke outputs、parent scoped symbol、ProducerIndex producer closure，会显著降低可用性。

### 3.3 CLI prompt 展示泄露内部结构

当前 CLI 会把 `subject.summary` 直接放进 `input()` 默认值提示中。若 summary 包含原文换行，提示会被拆成多行：

```text
Delegated responsibility * [Optional delegated subtasks such as source gathering or template matching may be
used if bounded and the returned evidence is normalized into approved evidence
carriers]:
```

这说明当前 CLI 只是机械渲染 backend field，而不是面向用户组织 repair draft。

### 3.4 容易把“用户补事实”误解为“用户补 IR”

结构化字段越多，越容易让实现者把用户输入直接绑定到 patch payload 或 IR-like 字段。虽然当前 v2 已经通过 directive normalization 和 verifier 做了保护，但交互设计仍应避免把这种压力推给用户。

---

## 4. 设计目标

1. 用户只补充最核心的业务语义。
2. 系统尽量利用现有 NL2SPL artifacts 推断输入、输出、placement、bindings。
3. 推断结果必须是 typed、可审计、可验证的 candidate draft。
4. 推断层不直接拥有 repair / apply / materialization authority。
5. 低置信度时只提出最少、最明确的问题。
6. Preview 展示用户能理解的 repair result，而不是内部 contract 字段。
7. Apply 仍然必须通过既有 `RepairDirective` / `RepairPatch` / Materialization / Lane B / ProducerIndex / DiagnosticDiff / renderer 验证。

---

## 5. 非目标

本设计不做以下事情：

1. 不重新跑完整 NL2SPL Pipeline。
2. 不伪造 SpanIR、compile hint 或 source evidence。
3. 不允许 LLM 输出 `WorkerIR`、`StepIR`、`WorkerHandoffIR`。
4. 不取消 `RepairInteractionView` 或结构化 directive。
5. 不把 placement、binding、output admission 交给前端推断。
6. 不新增 parent required output。
7. 不改变 `WORKER_PROMOTION` 的 IRS authority。
8. 不让 `RepairInferenceLayer` 成为第二套 repair compiler。

---

## 6. 用户必须补充的信息

### 6.1 子 worker 负责什么

只有在 source signal 太宽泛、包含多个候选任务，或系统置信度不足时才问。

示例：

```text
Which task should become the child worker?
  [1] source gathering
  [2] template matching
  [3] both
```

如果只有一个明确 candidate，则系统直接使用 candidate task text。

### 6.2 子 worker 应产出什么业务结果

只有当系统无法从 required output、downstream consumer、candidate possible outputs、source text 推断出结果时才问。

示例：

```text
What should this child worker return?
```

可选输入：

```text
source_evidence_set
approved evidence set
template match result
```

这些会进入 `NewOutputAdmission`，而不是直接写入 IR。

---

## 7. 系统应推断的信息

| 信息 | 默认是否问用户 | 推断来源 | 推断策略 |
|---|---:|---|---|
| delegated responsibility | 低置信度才问 | `WORKER_PROMOTION` target、Stage 3.5 candidate、route annotation、source excerpt | 单一 candidate 直接采用；多候选时提问 |
| input refs | 不默认问 | SelectableRefSet、candidate possible inputs、nearby variables、symbol table | 语义匹配 + scope 合法性；无必要输入则 `explicit_none` |
| returned result | 低置信度才问 | required output gap、possible outputs、downstream consumer、source text | 优先绑定 existing required output；否则 admitted child output |
| invocation timing | 不问 | source span order、main-flow step order、first consumer | 默认放在 first consumer 前；无 consumer 则放在 source-near block 尾部 |
| placement anchor | 不问 | Stage 5 block plan、Stage 7 step plan、source span mapping | 由 placement slice 选择合法 anchor |
| handoff bindings | 不问 | normalized input refs、admitted outputs、symbol table | 后端 deterministic 生成 |
| invoke outputs | 不问 | admitted child outputs、parent scope | 后端 deterministic 生成 |
| result usage | 不默认问 | required output、downstream consumer、ProducerIndex | 绑定 existing target；否则 parent-local temporary |
| data type | 不问 | existing output type、symbol table、default policy | 默认 `text`；仅 advanced details 展示 |

---

## 8. 可复用的 NL2SPL Pipeline 信息

本设计复用现有 Pipeline 的 artifact 和 stage authority，而不是重新跑完整 Pipeline。

### 8.1 Stage 3 / Stage 3.5

可复用信息：

```text
route annotation
delegation intent
promotion candidate
candidate task text
possible inputs
possible outputs
source span ownership
WorkerBoundaryExclusionView
SanitizedCandidateResult
```

用途：

```text
推断 delegated responsibility
判断 task boundary 是否单一
排除 API-owned spans
确定 WORKER_PROMOTION target
```

### 8.2 Stage 5

可复用信息：

```text
worker block plan
main-flow block structure
exception / sequential block placement
source span to block relation
```

用途：

```text
推断 parent invoke placement
选择合法 placement anchor
判断是否需要创建 placement block
```

### 8.3 Stage 7

可复用信息：

```text
worker step plan
main-flow step order
step inputs / outputs
command source spans
available variables
```

用途：

```text
推断 first consumer
推断 input refs
生成 child worker command typed plan
生成 parent invoke command typed plan
```

### 8.4 Stage 9.5 / Stage 10 / ProducerIndex

可复用信息：

```text
normalization result
WorkerIR assembly
symbol table
ProducerIndex
post-normalize IRS diagnostics
```

用途：

```text
验证 result binding
验证 required output producer closure
验证 no orphan worker / handoff / invoke
```

---

## 9. 新增 Repair Inference Layer

建议新增一层：

```text
RepairInferenceLayer
```

其位置在：

```text
Issue + Target + Snapshot
-> RepairInferenceContext
-> InferredRepairDraft
-> RepairAdmission / DirectiveBridge
-> existing RepairDirectiveDraft / RepairPatch / MaterializationRequest
-> Preview
-> Apply + Lane B
```

### 9.1 Typed read-only views

`RepairInferenceContext` 不应直接持有完整 artifact object。它应消费 typed read-only views，避免越权读取、临时解析或绕过 resolver。

建议的 view/protocol：

```python
class PromotionCandidateView(Protocol):
    candidate_id: str
    target_ref: str
    source_span_ids: tuple[str, ...]
    task_text: str
    possible_input_names: tuple[str, ...]
    possible_output_names: tuple[str, ...]
```

所有 view 方法必须返回只读 DTO，避免把 `object` 风险从 context 层转移到 view 返回值层。

建议 DTO：

```python
@dataclass(frozen=True)
class SelectableRefView:
    ref_id: str
    name: str
    ref_role: str
    worker_scope: str | None
    data_type: str | None
    source_span_ids: tuple[str, ...]
    availability: Literal["available", "future", "out_of_scope"]


@dataclass(frozen=True)
class PlacementStepView:
    step_id: str
    worker_id: str
    block_ref: str
    flow_ref: str
    ordinal: int
    input_names: tuple[str, ...]
    output_names: tuple[str, ...]
    source_span_ids: tuple[str, ...]


@dataclass(frozen=True)
class OutputDemandItemView:
    output_id: str
    canonical_name: str
    declared_name: str
    required: bool
    unresolved: bool
    aliases: tuple[str, ...]
    source_span_ids: tuple[str, ...]
```

收紧后的 protocol 应返回这些 DTO：

```python
class SelectableRefSetView(Protocol):
    def refs_by_role(self, role: str) -> tuple[SelectableRefView, ...]: ...


class WorkerPlacementView(Protocol):
    def main_flow_steps(self, worker_id: str) -> tuple[PlacementStepView, ...]: ...
    def first_consumer_of(self, symbol_name: str) -> PlacementStepView | None: ...


class ConsumerIndexView(Protocol):
    def consumers_of(self, symbol_name: str) -> tuple[PlacementStepView, ...]: ...


class OutputDemandView(Protocol):
    def required_outputs(self) -> tuple[OutputDemandItemView, ...]: ...
    def unresolved_required_outputs(self) -> tuple[OutputDemandItemView, ...]: ...
```

### 9.2 RepairInferenceContext

```python
@dataclass(frozen=True)
class RepairInferenceContext:
    issue_id: str
    target_ref: str
    strategy_id: str
    option_id: str
    snapshot_id: str
    overlay_version: int
    promotion_candidate: PromotionCandidateView
    source_excerpt: str
    selectable_refs: SelectableRefSetView
    placement_view: WorkerPlacementView
    consumer_index: ConsumerIndexView
    output_demand_view: OutputDemandView
```

该对象只消费 snapshot 中已有 artifact 的 read-only projection，不解析 `diagnostic.message`，不伪造 source facts。

### 9.3 Field-level inference

不使用单一 draft-level `confidence` 驱动 readiness。每个字段都必须有独立 inference result。`FieldInference.value` 必须是 field-specific typed value union，因为该字段会进入 Admission / DirectiveBridge，是最容易重新退化为 dict parsing 的位置。

建议：

```python
RepairFieldValue = (
    ResponsibilityValue
    | SelectedInputRefsValue
    | OutputBindingValue
    | NewOutputDraftValue
    | PlacementIntentValue
    | ResultBindingValue
    | ExplicitNoneValue
)


@dataclass(frozen=True)
class FieldInference:
    field_id: RepairFieldId
    value: RepairFieldValue | None
    confidence: Confidence
    evidence_refs: tuple[str, ...]
    alternatives: tuple[InferenceAlternative, ...]
    blocking_reason: str | None = None
```

Admission / DirectiveBridge 只能消费 typed `RepairFieldValue`，不得解析自由 dict、任意 object 或 raw string 结构。

`input_readiness` 必须由 required fields 的最低 readiness 决定：

```text
如果任一 required field = blocked -> input_required / blocked clarification
如果任一 required field = low 且无 safe default -> input_required
如果 required fields 均 high/medium 且 policy 允许 -> draft acceptable
```

### 9.4 InferredRepairDraft

```python
@dataclass(frozen=True)
class InferredWorkerDelegationDraft:
    draft_id: str
    issue_id: str
    option_id: str
    fields: tuple[FieldInference, ...]
    missing_user_decisions: tuple[RepairClarificationQuestion, ...]
    inference_trace: tuple[InferenceTraceRecord, ...]
```

### 9.5 InferenceTraceRecord

每条推断都必须可解释：

```python
@dataclass(frozen=True)
class InferenceTraceRecord:
    field_id: str
    source: str
    evidence_refs: tuple[str, ...]
    confidence: str
    decision: str
    alternatives: tuple[str, ...] = ()
```

例如：

```text
field_id = placement
source = stage7.first_consumer
evidence_refs = ("step:worker_main:st_6",)
decision = before first consumer of source_evidence_set
confidence = high
```

---

## 10. 推断策略

### 10.1 Responsibility inference

输入：

```text
promotion candidate task_text
route annotation text
source excerpt
SanitizedCandidateResult
```

规则：

1. 若 candidate 指向单一 responsibility，直接采用。
2. 若 text 包含多个任务边界，例如 `source gathering or template matching`，默认不选 `both`。
3. 只有 source 明确表达多个任务属于同一个 delegated unit，且共享同一个 returned result，才可自动推断 `both`。
4. 否则必须生成 clarification：

```text
[1] source gathering
[2] template matching
[3] both
```

5. 若用户不回答关键 clarification，则不得生成 overlay。

### 10.2 Input ref inference

输入：

```text
SelectableRefSet
candidate possible_inputs
nearby steps
symbol table projection
responsibility text
```

规则：

1. 只选择 `ref_role == selectable_input` 的 ref。
2. 优先 source-near variables。
3. 优先与 responsibility 语义匹配的变量。
4. 若没有必要输入，自动设为 `explicit_none`。
5. 若存在多个同等高置信候选，生成 clarification。
6. LLM 不能直接发明 raw variable name，只能引用 selectable ref id 或 bounded alternative。

### 10.3 Output inference

输入：

```text
WORKER_PROMOTION possible_outputs
REQUIRED_OUTPUT diagnostics
downstream consumer
source text
existing symbol names
alias table / normalized symbol aliases
```

匹配优先级：

```text
1. exact canonical id match
2. same declared required output canonical name
3. alias table / normalized symbol alias match
4. bounded semantic match with explicit preview disclosure
5. clarification required
```

规则：

1. 若存在 required output gap 且语义匹配，不得降级为 parent-local temporary。
2. 若存在 downstream required consumer，temporary 必须绑定到 consumer-visible parent scoped symbol。
3. 若存在 declared output alias，必须走 alias / required-output binding。
4. 只有在没有对应 required output gap、没有 downstream required consumer、没有 declared output alias 时，才允许 parent-local temporary。
5. `NewOutputDeclarationDraft` 必须通过 admission，生成 canonical output id。
6. 本轮不允许新增 parent required output。

### 10.4 Placement inference

输入：

```text
source span order
main-flow step order
first consumer
Stage 5 block plan
Stage 7 step plan
input availability index
```

默认策略：

1. 若 result 有 first consumer，parent invoke 放在 first consumer 前。
2. 若 result 是 evidence producer，放在 source/provenance 相关步骤附近。
3. 若无 consumer，放在对应 source-near block 尾部。

但 placement 必须先通过 dependency-aware preconditions：

```text
1. invoke step 所需 input refs 在该位置前已可用；
2. invoke output 在 first consumer 前可用；
3. 不跨 exception-flow / alternative-flow 边界错误移动；
4. 不把 API-owned span 或 reserved span 变成 child-worker-owned；
5. 不制造 cycle：child worker input 不能依赖自己的 output；
6. selected placement anchor 必须属于当前 parent worker scope。
```

若 precondition 不满足，则 placement inference 必须 blocked 或生成 clarification，不得让 Lane B 才发现基本 placement 错误。

### 10.5 Result binding inference

输入：

```text
admitted child output
required output gaps
parent symbol table projection
ProducerIndex
downstream consumer
```

规则：

1. child output 若能满足 existing required output，则绑定到该 output。
2. 若只是中间结果，且不存在 required output / downstream required consumer / declared output alias，才允许 parent-local temporary。
3. parent-local temporary 不得进入 `[OUTPUTS]`。
4. parent-local temporary 不得触发 `missing_output_producer`。
5. 最终由 `DefineChildWorkerClosureVerifier` 检查 ProducerIndex closure。

---

## 11. LLM 的位置与仲裁规则

LLM 可以参与低置信度语义判断，但只能输出 typed inference plan，不能输出 IR。

允许：

```json
{
  "task_boundary": "source_gathering",
  "expected_result": "source_evidence_set",
  "confidence": "medium",
  "reason": "source text says returned evidence must be normalized"
}
```

禁止：

```text
WorkerIR
StepIR
WorkerHandoffIR
raw variable names not in SelectableRefSet
handoff_id
placement step id by free text
```

仲裁规则：

```text
SelectableRefSet / symbol legality / placement legality / output admission:
  deterministic authority wins; LLM 只能提出候选。

task_boundary / responsibility paraphrase / expected_result label:
  LLM 可以在 bounded alternatives 内辅助分类。

raw variable name / handoff_id / placement step id / output id:
  LLM 不可直接产生 authority value。
```

LLM 输出必须经过：

```text
schema validation
SelectableRefSet resolution
NewOutputAdmission
placement precondition validation
stage-slice policy validation
preview/apply seal
Lane B verification
```

---

## 12. 用户体验设计

### 12.0 Preview 分层

本设计必须区分两类 preview：

```text
Draft preview:
  InferredRepairDraft 的用户可读解释；
  用于让用户理解系统计划如何修复；
  不承诺所有 IDs / anchors / handoff refs 已最终 materialized。

Materialized preview:
  Admission + RepairPatch / MaterializationRequest 之后生成的 preview；
  由 stage slices / id allocator / materialization plan 产出；
  必须与 apply 后 materialized closure 一致。
```

因此，draft 阶段可以展示：

```text
Create child worker:
  Gather approved source evidence.

Insert:
  before the first consumer of source_evidence_set
```

但不应默认展示最终 `handoff_id`、`invoke step id`、`block id` 等尚未由 materialization / id allocator 最终确认的内部 ID。内部 ID 应进入 materialized preview 或 advanced details。

### 12.1 推荐交互

用户选择 `Define this work as a child worker` 后，系统先生成 draft：

```text
Planned repair

Create child worker:
  Gather approved source evidence.

Use inputs:
  user_request
  approved_source_recipes

Return:
  source_evidence_set

Insert:
  before the first step that consumes source_evidence_set

Bind result:
  source_evidence_set

[Enter] accept
[e] edit key details
[c] cancel
```

### 12.2 低置信度交互

仅当系统不能可靠推断时提问：

```text
Which task should become the child worker?
  [1] source gathering
  [2] template matching
  [3] both
```

或者：

```text
What should this child worker return?
```

### 12.3 Advanced details

内部字段放入 advanced details：

```text
selected_ref_ids
placement_anchor
handoff_id
invoke step id
parent scoped temporary
verification lane
stage slices
marker refs
```

普通用户不默认看到这些字段。

---

## 13. 与现有 RepairInteractionView 的关系

`RepairInteractionView` 不应被删除，而应增加一个上层模式：

```text
interaction_mode:
  draft_first
  form_first
```

首期只迁移：

```text
define_child_worker -> draft_first
```

暂不迁移：

```text
keep_in_main_flow
```

原因是 `keep_in_main_flow` 更像 resolution marker + main-flow materialization 路径，不是 child worker closure materialization。它应后续单独设计，避免把 marker validity、closure verification、result binding 混在同一轮迁移里。

建议新增：

```python
@dataclass(frozen=True)
class RepairDraftInteractionView:
    issue_id: str
    option_id: str
    draft_id: str
    summary: str
    planned_changes: tuple[RepairDraftChangeView, ...]
    clarification_questions: tuple[RepairClarificationQuestion, ...]
    advanced_fields: tuple[RepairInputFieldView, ...]
    input_readiness: str
```

如果 `clarification_questions` 为空，则用户可以直接 preview/confirm。

---

## 14. Verification 要求

所有推断结果最终必须满足现有 Worker Delegation v2 的 verification：

1. `PromotionResolutionMarker` 必须 user-confirmed。
2. marker target 必须精确匹配 `WORKER_PROMOTION` target。
3. child worker output 必须存在。
4. handoff output binding 必须存在。
5. invoke outputs 必须存在。
6. parent scoped symbol 必须存在。
7. ProducerIndex 必须能识别 producer closure。
8. 原 `WORKER_PROMOTION` diagnostic group 必须由 marker + materialized closure 解决。
9. no orphan worker / handoff / invoke。
10. no API-owned source span may become child-worker-owned span.
11. 若 required output gap 存在，不得 silent downgrade 为 parent-local temporary。
12. preview 展示的 responsibility / inputs / returns / insert position / binding 必须与 apply 后 materialized closure 一致。

---

## 15. 迁移计划建议

### Phase I0：Characterization

锁定当前行为：

```text
用户选择 define_child_worker 后必须填写多个 technical fields
默认 responsibility 提示包含换行
placement/result_usage/input refs 都暴露给用户
```

### Phase I1：Draft model only

新增：

```text
InferredWorkerDelegationDraft
FieldInference
InferenceTraceRecord
RepairClarificationQuestion
```

只建模型和单元测试，不接 CLI，不产生 directive。

### Phase I2：Read-only typed views

新增：

```text
PromotionCandidateView
SelectableRefSetView
WorkerPlacementView
ConsumerIndexView
OutputDemandView
SelectableRefView
PlacementStepView
OutputDemandItemView
```

禁止 inference layer 直接持有完整 artifact object。
禁止 typed view 方法继续返回 `tuple[object, ...]`。

### Phase I3：Deterministic inference provider

只做 artifact-driven deterministic inference：

```text
responsibility
input refs
output
placement
result binding
```

暂不接入 LLM，先证明 deterministic path 可闭合。

### Phase I4：Admission + bridge

把 draft 转为现有 `RepairDirectiveDraft` / `RepairPatch` / `MaterializationRequest` 所需输入。

所有 selectable ref、new output、placement anchor 在这里验证。
`FieldInference.value` 必须是 typed `RepairFieldValue` union，不得使用 `object`、dict parsing 或 raw string patch payload。

### Phase I5：Draft-first presentation

新增：

```text
RepairDraftInteractionView
draft preview
materialized preview handoff
minimal clarification rendering
advanced details
```

CLI 不再逐字段渲染完整 schema。

### Phase I6：LLM bounded inference

只在低置信度 task boundary / expected result label 上接入 LLM typed plan。

必须经过：

```text
schema validation
bounded alternatives validation
selectable resolution
deterministic legality validation
```

### Phase I7：E2E + negative matrix

真实 demo 验收：

```text
define_child_worker Enter accept
preview/apply Lane B accepted
final SPL 出现 child worker + invoke
原 WORKER_PROMOTION group resolved
```

负例：

```text
no unknown ref
no raw variable name
no free-text placement id
no API-owned span
no unresolved WORKER_PROMOTION
no orphan child worker / handoff / invoke
no hidden missing_output_producer
no silent required-output downgrade
```

---

## 16. 必加验收标准

1. CLI 不再询问 `placement_ref`、`input_empty_semantics`、`result_usage`、handoff binding、invoke output。
2. 如果 required output gap 存在，不能自动降级为 parent-local temporary。
3. invoke placement 前，所有 input refs 已在 parent scope 可用。
4. invoke output 在 first consumer 前可用。
5. no API-owned source span may become child-worker-owned span。
6. `PromotionResolutionMarker` target 精确匹配 `WORKER_PROMOTION` target。
7. stale marker 不得 resolve 新 diagnostic。
8. LLM typed plan 引用未知 ref、raw variable name、free-text placement id 时 rejected。
9. preview 展示内容必须与 apply 后 materialized closure 一致。
10. 原 `WORKER_PROMOTION` group resolved，且不新增 `missing_output_producer` / `type_or_contract_ambiguity` / orphan handoff / orphan invoke。
11. `subject.summary` 含换行时不会污染 input prompt。
12. Typed view methods must not return `object`.
13. `FieldInference.value` must be a typed `RepairFieldValue` union.
14. Draft preview and materialized preview must be distinct; final internal IDs must not be promised by draft preview.

---

## 17. 开放问题的当前建议

### 17.1 多候选文本默认是否选 both

不默认。只有 source 明确绑定为同一个 delegated unit 且共享同一个 returned result 时才自动 `both`，否则必须问用户。

### 17.2 近似 output 名称阈值

不设单一文本相似度阈值。采用：

```text
canonical id
declared required output
alias
bounded semantic match
clarification
```

进入 bounded semantic match 时 preview 必须显式展示绑定关系。

### 17.3 parent-local temporary 是否展示

默认不展示，只进 advanced details。若它是 downstream consumer 的绑定结果，preview 应展示“Bind result for later use”，但不暗示它进入 `[OUTPUTS]`。

### 17.4 draft-first 是否迁移 keep_in_main_flow

暂不迁移。先只做 `define_child_worker`。

### 17.5 LLM 与 deterministic 冲突谁优先

legality / id / ref / placement 由 deterministic authority 决定；responsibility label 和 expected result 语义分类可由 LLM 在 bounded alternatives 内辅助，但必须经 deterministic validation。

---

## 18. 结论

Worker Delegation v2 当前已经解决了安全和 authority 问题，但用户交互仍然过度暴露后端结构化 contract。

下一步应引入 repair inference layer，把 `Define this work as a child worker` 从 form-first 改为 draft-first：

```text
Issue + Snapshot
-> Typed read-only views
-> Artifact-driven inference
-> Inferred repair draft
-> Admission / DirectiveBridge
-> existing RepairPatch / Materialization
-> preview/apply
-> Lane B verification
```

这份设计的关键边界是：

```text
Inference 只做 draft；
Admission / DirectiveBridge 做合法性归一；
RepairPatch / Materialization 才拥有 apply authority；
Verification 仍由 Lane B、ProducerIndex、DiagnosticDiff 和 closure verifier 执行。
```

这样既保留 R12+/APW 的强 authority 边界，又能让普通用户只处理业务语义，而不是填写 internal worker closure wiring。
