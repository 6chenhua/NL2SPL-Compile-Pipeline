# SPL Editing Repair Drafting Subsystem 设计

日期：2026-07-04  
状态：设计基线，适合作为实施计划输入  
适用范围：SPL Editing repair suggestion / user instruction / structured interaction / draft preview / strategy-specific inference  
首个实践：`WORKER_PROMOTION` 的 `define_child_worker`  

关联文档：

- [`../problem/worker_delegation_repair_inference_first_interaction_design.md`](../problem/worker_delegation_repair_inference_first_interaction_design.md)
- [`spl_editing_worker_delegation_repair_interaction_and_closure_design_zh.md`](spl_editing_worker_delegation_repair_interaction_and_closure_design_zh.md)
- [`spl_editing_construct_level_repair_strategy_and_stage_slice_design.md`](spl_editing_construct_level_repair_strategy_and_stage_slice_design.md)
- [`stage3_5_api_worker_promotion_boundary_solution_design_zh.md`](stage3_5_api_worker_promotion_boundary_solution_design_zh.md)

---

## 1. 设计结论

SPL Editing 需要一个通用的修复输入理解与草案生成层，但这个层不应该是万能 repair compiler。

正式命名为：

```text
RepairDraftingSubsystem
```

它的定位是：

```text
统一用户输入理解、field inference、trace、confidence、clarification、draft preview；
具体 repair 语义由 affordance / strategy option 专属 provider 实现；
Admission、Patch、Materialization、Verification 仍由后续 authority 负责。
```

核心原则：

```text
RepairDraftingSubsystem 可以跨修复策略复用，
但 repair inference 必须按 affordance / strategy option 插件化。

通用层只负责组织用户输入与 artifact context，产出 typed candidate draft；
每个 provider 负责本 issue 的字段解释与候选补全；
Admission、Patch、Materialization、Verification 仍是后续 authority。
```

---

## 2. 为什么需要这个层

当前 SPL Editing 已经有：

```text
EditableIssue
RepairTarget
RepairCatalogEntry
RepairInteractionView
RepairDirectiveDraft
ConstructRepairIntent / RepairPatch
MaterializationPlan
Preview / Apply
Verification
```

但缺少一个稳定层来回答：

```text
用户给出的自然语言建议或少量结构化字段，
如何转成 strategy-specific typed candidate fields？
```

这个缺口不仅存在于 Worker Delegation，也存在于其他修复：

```text
missing_handler:
  用户说“Ask the user to provide the missing timeframe.”
  系统需要推断 handler action、command family、value target、flow/block attachment。

missing_output_producer:
  用户说“Use collected evidence to produce the final draft.”
  系统需要推断 producer command、input refs、placement、output binding。

worker_delegation:
  用户只应说明子任务负责什么、返回什么；
  系统需要推断 input refs、placement、handoff、invoke、result binding。
```

因此，纯文本建议可以被看作：

```text
一个只有 free_text 字段的 UserRepairInput
```

结构化表单可以被看作：

```text
UserRepairInput(field_values=...)
```

两者最终都应进入同一条 draft 链路：

```text
UserRepairInput
-> strategy-specific provider
-> InferredRepairDraft
-> Admission / DirectiveBridge
-> RepairPatch / MaterializationRequest
-> Preview / Apply / Verification
```

---

## 3. 反过度设计边界

本设计承认长期架构接口的必要性，但避免多余设计。

### 3.1 合理预留

以下抽象是合理的：

```text
RepairDraftingSubsystem
RepairInferenceProviderRegistry
UserRepairInput
InferredRepairDraft
FieldInference
RepairFieldValue
RepairClarificationQuestion
InferenceTraceRecord
DraftPreview / MaterializedPreview boundary
```

原因：

1. repair strategy 一定会有不同 provider。
2. 用户 free text、structured form、accepted defaults 需要统一输入模型。
3. draft 必须可审计、可解释、可澄清。
4. preview 与 apply artifact 必须区分。

### 3.2 禁止的多余设计

以下内容不应在 MVP 中建设：

```text
1. UniversalRepairInferenceLayer that understands all issues.
2. Generic free-text -> patch_type + payload parser.
3. 第二套 snapshot model。
4. 为尚未迁移的 issue 预先实现 provider。
5. 大而全的 ranking / scoring engine。
6. 复杂状态机，但没有当前消费方。
7. 让 drafting subsystem 直接生成 patch payload 或 materialization plan。
```

MVP 只允许：

```text
通用接口存在；
WorkerDelegationInferenceProvider 作为第一个 provider；
公共类型按真实 provider 需求渐进扩展。
```

---

## 4. Authority 分层

RepairDraftingSubsystem 不拥有 repair authority。

```text
RepairDraftingSubsystem
  owns:
    - user input normalization
    - provider dispatch
    - inferred candidate draft
    - field confidence
    - trace
    - clarification
    - draft preview

  does not own:
    - SelectableRefSet admission
    - new fact admission
    - patch selection authority
    - patch application
    - materialization
    - verification
    - diagnostic suppression
    - renderer output
```

完整链路：

```text
EditableIssue
+ RepairTarget
+ RepairCatalogEntry
+ selected RepairStrategyOption
+ UserRepairInput
+ SnapshotViews
    |
    v
RepairDraftingSubsystem
    |
    v
RepairInferenceProvider
    |
    v
InferredRepairDraft
    |
    v
RepairAdmission / DirectiveBridge
    |
    v
RepairPatch / MaterializationRequest
    |
    v
Materialized preview
    |
    v
User confirmation
    |
    v
Apply + Verification
```

---

## 5. Dispatch key

Provider dispatch 不得只依赖 `diagnostic.kind`。

必须至少考虑：

```text
affordance_id
strategy_id
option_id
construct_type
slot_name
target_ref shape
patch_type / execution adapter
```

原因：

1. `type_or_contract_ambiguity` 是 umbrella diagnostic。
2. 同一 diagnostic kind 下，不同 construct / slot 的 repair 语义不同。
3. patch type 是 execution adapter，不是用户语义的唯一来源。
4. strategy option 才是当前用户选择的语义 owner。

示例：

```text
worker_promotion.resolve_contract
  strategy_id = worker_delegation.complete_closure.v2
  option_id = define_child_worker
  provider = WorkerDelegationInferenceProvider

exception_flow.add_handler_step
  strategy_id = exception_flow.complete_handler_action.v1
  option_id = default_handler_action
  provider = MissingHandlerInferenceProvider
```

---

## 6. 数据模型

### 6.1 UserRepairInput

```python
@dataclass(frozen=True)
class UserRepairInput:
    input_mode: Literal["none", "free_text", "structured_form", "mixed"]
    free_text: str | None
    field_values: tuple[UserRepairFieldValue, ...]
    selected_option_id: str | None
    accepted_draft_id: str | None = None
    draft_accepted: bool = False
    materialized_preview_accepted: bool = False
```

说明：

1. `free_text` 不能直接进入 patch payload。
2. `field_values` 是用户提交的原始交互值，不是 admitted repair facts。
3. `draft_accepted=True` 只表示用户接受 inferred draft，可进入 Admission / Materialization。
4. `materialized_preview_accepted=True` 表示用户接受 materialized preview，才可进入 patch apply / evidence path。
5. 避免使用含糊的 `confirmed` 字段，因为它容易被误解为 `USER_CONFIRMED_REPAIR` evidence。

### 6.2 UserRepairFieldValue

```python
@dataclass(frozen=True)
class UserRepairFieldValue:
    field_id: str
    value: JsonValue
    source: Literal["user", "accepted_default", "ui_selection"]
```

这是 UI/CLI 输入层 DTO，不直接进入 materialization。

### 6.3 InferredRepairDraft

```python
@dataclass(frozen=True)
class InferredRepairDraft:
    draft_id: str
    issue_id: str
    affordance_id: str
    strategy_id: str
    option_id: str
    fields: tuple[FieldInference, ...]
    clarification_questions: tuple[RepairClarificationQuestion, ...]
    trace: tuple[InferenceTraceRecord, ...]
    draft_preview: DraftPreview
```

### 6.4 FieldInference

`FieldInference` 是通用层的核心输出。

```python
@dataclass(frozen=True)
class FieldInference:
    field_id: RepairFieldId
    value: RepairFieldValue | None
    confidence: Confidence
    evidence_refs: tuple[str, ...]
    alternatives: tuple[InferenceAlternative, ...]
    blocking_reason: str | None = None
```

`value` 必须是 typed union，不得使用自由 dict / object。

### 6.5 RepairFieldValue

RepairFieldValue 是渐进扩展的 typed union。MVP 只实现当前 provider 需要的类型。

初始建议：

```python
RepairFieldValue = (
    ResponsibilityValue
    | SelectedInputRefsValue
    | NewOutputDraftValue
    | PlacementIntentValue
    | ResultBindingValue
    | ExplicitNoneValue
)
```

Worker Delegation MVP 使用：

```text
ResponsibilityValue
SelectedInputRefsValue
NewOutputDraftValue
PlacementIntentValue
ResultBindingValue
ExplicitNoneValue
```

missing_handler 未来可能新增：

```text
HandlerActionTextValue
HandlerCommandFamilyValue
HandlerValueTargetValue
```

这些不在 MVP 中提前实现。

扩展 contract：

```text
新增 RepairFieldValue type 必须同时提供：

1. owning provider / affordance scope；
2. Admission / DirectiveBridge handler；
3. serialization payload schema；
4. validation tests；
5. negative tests proving it is not accepted by unrelated provider。
```

该约束用于防止 `RepairFieldValue` 逐渐变成全局字段垃圾桶。

### 6.6 RepairClarificationQuestion

```python
@dataclass(frozen=True)
class RepairClarificationQuestion:
    question_id: str
    field_id: RepairFieldId
    prompt: str
    options: tuple[InferenceAlternative, ...]
    required: bool
```

只对 blocked / low-confidence required fields 提问。

### 6.7 InferenceTraceRecord

```python
@dataclass(frozen=True)
class InferenceTraceRecord:
    field_id: RepairFieldId
    source: str
    evidence_refs: tuple[str, ...]
    decision: str
    confidence: Confidence
    alternatives: tuple[str, ...] = ()
```

Trace 是审计对象，不是 patch payload。

---

## 7. Preview 分层

必须区分：

```text
DraftPreview
MaterializedPreview
```

### 7.1 DraftPreview

DraftPreview 是 InferredRepairDraft 的用户可读解释。

它可以展示：

```text
Create child worker:
  Gather approved source evidence.

Use inputs:
  user_request

Return:
  source_evidence_set

Insert:
  before the first consumer of source_evidence_set
```

它不应承诺：

```text
final handoff_id
final step_id
final block_id
final overlay event id
```

这些由 Materialization / IdAllocator 决定。

### 7.2 MaterializedPreview

MaterializedPreview 是 Admission + RepairPatch / MaterializationRequest 后的 preview。

它必须满足：

```text
1. 与 apply 后 materialized closure 一致。
2. 包含最终 construct preview。
3. 受 preview/apply seal 保护。
4. stale preview 必须拒绝 apply。
```

---

## 8. Provider 接口

```python
class RepairInferenceProvider(Protocol):
    provider_id: str
    supported_affordance_ids: frozenset[str]
    supported_strategy_ids: frozenset[str]
    supported_option_ids: frozenset[str]
    supported_patch_types: frozenset[str]

    def build_context(
        self,
        *,
        issue: EditableIssue,
        target: RepairTarget,
        catalog_entry: RepairCatalogEntry,
        snapshot: ArtifactSnapshot,
    ) -> RepairDraftingContext:
        ...

    def infer(
        self,
        *,
        context: RepairDraftingContext,
        user_input: UserRepairInput | None,
    ) -> InferredRepairDraft:
        ...
```

Provider 只能做：

```text
artifact-driven field inference
bounded LLM semantic classification, if enabled
clarification generation
draft preview construction
```

Provider 禁止做：

```text
patch payload construction
IR construction
overlay mutation
diagnostic suppression
Lane selection override
verification shortcut
```

---

## 9. Registry

建议新增：

```text
RepairInferenceProviderRegistry
```

职责：

```text
register(provider)
resolve(affordance_id, strategy_id, option_id, patch_type)
```

注册规则：

1. 不允许两个 provider 声称同一个 `(affordance_id, strategy_id, option_id)`。
2. provider 缺失时，drafting unavailable，不 fallback 到 generic LLM。
3. registry 不决定 repair option 是否存在；repair capability 仍来自 RepairCatalog。
4. registry 不决定 verification lane；lane 来自 materialization / catalog / plan。

Provider identity key 必须是：

```text
(affordance_id, strategy_id, option_id)
```

`patch_type` 只能作为 provider resolve 之后的兼容性约束：

```text
1. 如果 option 当前 execution patch type 与 provider 支持范围不兼容，则 drafting unavailable。
2. patch_type 不得选择另一个语义 provider。
3. 同一个 strategy option 不得因为 patch_type 不同而被分派到语义不同的 provider。
```

原因是：

```text
RepairStrategyOptionSpec 是用户语义 owner；
patch type 只是执行 adapter；
Drafting provider 理解的是 strategy option 的用户输入语义，不是 patch adapter 名称。
```

---

## 10. RepairDraftingService

```python
class RepairDraftingService:
    def create_draft(
        self,
        *,
        issue: EditableIssue,
        target: RepairTarget,
        catalog_entry: RepairCatalogEntry,
        option_id: str,
        snapshot: ArtifactSnapshot,
        user_input: UserRepairInput | None,
    ) -> InferredRepairDraft:
        ...
```

职责：

```text
1. resolve provider
2. build drafting context
3. call provider.infer()
4. store draft
5. return DraftPreview / clarification questions
```

Draft 存储必须是 session-scoped ephemeral state，而不是 artifact revision。

建议模型：

```python
@dataclass(frozen=True)
class StoredRepairDraft:
    draft_id: str
    session_id: str
    artifact_snapshot_id: str
    overlay_version: int
    issue_id: str
    option_id: str
    draft: InferredRepairDraft
    created_at: str
```

存储 key：

```text
session_id
+ artifact_snapshot_id
+ overlay_version
+ draft_id
```

硬约束：

```text
1. StoredRepairDraft 不创建 overlay event。
2. StoredRepairDraft 不创建 patched artifact snapshot。
3. StoredRepairDraft 不写入 snapshot metadata 作为 repair evidence。
4. overlay_version / artifact_snapshot_id 变化后，旧 draft stale。
5. stale draft 不得进入 Admission / DirectiveBridge。
6. 只有 materialized preview 被用户接受后，才进入 apply / evidence path。
```

不做：

```text
Admission
Patch creation
Materialization
Apply
Verification
```

---

## 11. 与 RepairInteractionView 的关系

现有 interaction 可以演进为三种模式：

```text
form_first:
  直接展示字段表单；
  适合低智能 fallback 或 developer mode。

draft_first:
  系统先推断 draft；
  用户确认或补少量字段；
  Worker Delegation define_child_worker 属于这里。

suggestion_first:
  用户先输入一句自然语言建议；
  系统理解建议并生成 draft；
  missing_handler / missing_output_producer 未来可能属于这里。
```

三种模式最终收敛到同一后端链路：

```text
UserRepairInput
-> RepairInferenceProvider
-> InferredRepairDraft
-> Admission / DirectiveBridge
-> RepairPatch / MaterializationRequest
-> MaterializedPreview
-> user confirmation
-> Apply / Verification
```

---

## 12. 首个实践：WorkerDelegationInferenceProvider

MVP 只实现：

```text
provider = WorkerDelegationInferenceProvider
strategy_id = worker_delegation.complete_closure.v2
option_id = define_child_worker
```

暂不迁移：

```text
keep_in_main_flow
missing_handler
missing_output_producer
API deferred validation
```

### 12.1 需要推断的字段

```text
responsibility
selected input refs
output draft
placement intent
result binding
explicit none input semantics
```

### 12.2 可用 artifacts

```text
WORKER_PROMOTION target
Stage 3 / Stage 3.5 promotion candidate
WorkerBoundaryExclusionView
SanitizedCandidateResult
SelectableRefSet
worker step plan
block plan
symbol table projection
required output diagnostics
ProducerIndex
```

### 12.3 默认用户体验

用户选择 `Define this work as a child worker` 后，系统先展示 DraftPreview：

```text
Planned repair

Create child worker:
  Gather approved source evidence.

Use inputs:
  user_request

Return:
  source_evidence_set

Insert:
  before the first consumer of source_evidence_set

Bind result:
  source_evidence_set

[Enter] accept
[e] edit key details
[c] cancel
```

### 12.4 只在低置信度时提问

例如：

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

不再默认询问：

```text
placement_ref
input_empty_semantics
result_usage
handoff binding
invoke output
```

---

## 13. LLM 使用边界

LLM 可以参与，但必须是 provider 内部的 bounded semantic classification。

允许：

```text
task boundary classification
responsibility paraphrase
expected result label classification
```

禁止：

```text
raw variable name
unknown ref
handoff_id
placement step id
WorkerIR / StepIR / WorkerHandoffIR
patch_type selection as authority
verification lane override
```

仲裁规则：

```text
SelectableRefSet / symbol legality / placement legality / output admission:
  deterministic authority wins.

task_boundary / responsibility label / expected result label:
  LLM may assist within bounded alternatives.
```

MVP 建议先不接入 LLM，只实现 deterministic inference。

---

## 14. Admission / DirectiveBridge

Drafting 输出不是 admitted repair input。

Admission / DirectiveBridge 负责：

```text
SelectableRefSet resolution
NewOutputAdmission
placement policy validation
field policy validation
typed RepairFieldValue -> existing RepairDirectiveDraft / NormalizedRepairDirective
```

禁止：

```text
解析 raw dict
解析 arbitrary object
把 free_text 直接塞入 patch payload
绕过 existing validator / normalizer
```

---

## 15. 验收标准

### 15.1 通用子系统验收

1. Provider dispatch 不基于 `diagnostic.kind` 单独判断。
2. 无 provider 时不 fallback 到 generic LLM。
3. `UserRepairInput.free_text` 不直接进入 patch payload。
4. `FieldInference.value` 为 typed union。
5. DraftPreview 不承诺 final IDs。
6. MaterializedPreview 与 apply 后 closure 一致。
7. Drafting 不写 overlay。
8. Drafting 不构造 IR。
9. Drafting 不 suppress diagnostic。

### 15.2 Worker Delegation MVP 验收

1. CLI 不再默认询问 `placement_ref`、`input_empty_semantics`、`result_usage`、handoff binding、invoke output。
2. 若 required output gap 存在，不得自动降级为 parent-local temporary。
3. invoke placement 前，所有 input refs 已在 parent scope 可用。
4. invoke output 在 first consumer 前可用。
5. no API-owned source span may become child-worker-owned span。
6. `PromotionResolutionMarker` target 精确匹配 `WORKER_PROMOTION` target。
7. stale marker 不得 resolve 新 diagnostic。
8. LLM typed plan 引用未知 ref、raw variable name、free-text placement id 时 rejected。
9. DraftPreview 展示内容与 MaterializedPreview / apply closure 语义一致。
10. 原 `WORKER_PROMOTION` group resolved。
11. 不新增 `missing_output_producer`、`type_or_contract_ambiguity`、orphan handoff、orphan invoke。
12. `subject.summary` 含换行时不会污染 input prompt。

---

## 16. MVP 实施范围

这里的 MVP 指：

```text
RepairDraftingSubsystem 的最小可用切片。
```

它不重新定义 SPL Editing 整体 MVP，也不要求所有现有 repair handler 立即迁移。

MVP 做：

```text
1. RepairDraftingSubsystem 基础接口。
2. RepairInferenceProviderRegistry。
3. UserRepairInput / InferredRepairDraft / FieldInference / DraftPreview。
4. WorkerDelegationInferenceProvider only.
5. define_child_worker only.
6. deterministic inference only.
7. existing Worker Delegation v2 admission / materialization / verification chain.
8. CLI draft-first display for define_child_worker.
```

MVP 不做：

```text
1. missing_handler provider.
2. missing_output_producer provider.
3. keep_in_main_flow draft-first migration.
4. API repair provider.
5. LLM bounded inference.
6. generic semantic parser.
7. second snapshot model.
8. new materialization authority.
```

因此：

```text
missing_handler / missing_output_producer 仍可继续使用现有 handler / patch / prompt / materialization path；
它们只是暂时不接入 RepairDraftingSubsystem provider；
不得因为本 MVP 未实现 provider 就移除或削弱现有可用 repair 能力。
```

---

## 17. 未来扩展路径

### 17.1 missing_handler

可能 provider：

```text
MissingHandlerInferenceProvider
```

输入：

```text
free_text user suggestion
target exception flow
available vars
handler affordance
```

输出：

```text
HandlerActionTextValue
HandlerCommandFamilyValue
HandlerValueTargetValue
```

但不在 MVP 中实现。

### 17.2 missing_output_producer

可能 provider：

```text
MissingOutputProducerInferenceProvider
```

输入：

```text
target required output
ProducerIndex
available producer candidates
user instruction
```

输出：

```text
ProducerActionValue
SelectedInputRefsValue
PlacementIntentValue
OutputBindingValue
```

但不在 MVP 中实现。

### 17.3 REQUEST_INPUT.value_target

可能 provider：

```text
RequestInputContractInferenceProvider
```

用于真正的 runtime user input command 缺口，不应混入 Worker Delegation closure repair。

---

## 18. 最小实施顺序

### D0 Baseline / Characterization

目标：

```text
锁定当前 define_child_worker 交互过度结构化的问题；
锁定当前 Worker Delegation v2 admission / materialization / verification 仍可用；
证明 DraftingSubsystem 引入前后不改变已有 apply authority。
```

验收：

```text
1. 现有 define_child_worker E2E baseline 可复现。
2. 现有 Worker Delegation v2 negative tests 保持通过。
3. 不新增 Drafting provider 时，repair option capability 不发生变化。
```

### D1 Common Model

目标：

```text
新增 UserRepairInput、InferredRepairDraft、FieldInference、RepairFieldValue、
DraftPreview、StoredRepairDraft 等通用 DTO。
```

验收：

```text
1. DTO frozen / serializable / round-trip tested。
2. UserRepairInput 使用 draft_accepted / materialized_preview_accepted，不使用 confirmed。
3. RepairFieldValue 为 typed union，不接受自由 object。
4. StoredRepairDraft 不写 overlay / snapshot。
```

### D2 Registry + Service Shell

目标：

```text
实现 RepairInferenceProviderRegistry 与 RepairDraftingService skeleton。
```

验收：

```text
1. provider identity key 为 (affordance_id, strategy_id, option_id)。
2. patch_type 只作为兼容性约束。
3. provider 缺失时 drafting unavailable，不 fallback generic LLM。
4. stale draft 不能进入 Admission。
```

### D3 Worker Delegation Provider Context

目标：

```text
为 define_child_worker 构建 strategy-specific typed context。
```

验收：

```text
1. context 只消费 snapshot / issue / target / selectable refs 的 typed read-only view。
2. 不读取 raw rendered prompt 作为 materialization fact。
3. 不重新决定 API / worker promotion authority。
```

### D4 Deterministic Inference

目标：

```text
实现 WorkerDelegationInferenceProvider 的 deterministic field inference。
```

验收：

```text
1. 能推断 placement / selected inputs / result usage 等非用户核心字段。
2. required output gap 不得自动降级为 parent-local temporary。
3. confidence / evidence_refs / trace 完整。
4. 无法可靠推断时返回 clarification，不编造字段。
```

### D5 Admission Bridge

目标：

```text
把 InferredRepairDraft 转入现有 Worker Delegation v2 directive / admission 链路。
```

验收：

```text
1. Draft layer 不生成 patch payload。
2. Admission 负责 selected refs / new facts / placement / result binding 验证。
3. materialized_preview_accepted 前不得 apply。
4. DraftPreview 与 MaterializedPreview 的语义差异清楚展示。
```

### D6 CLI Draft-First Flow

目标：

```text
define_child_worker CLI 从 form-first 改为 draft-first。
```

验收：

```text
1. 用户只需补核心业务信息。
2. 推断字段以可读方式展示，可接受或要求澄清。
3. 不再默认询问 placement_ref、handoff binding、invoke output 等技术字段。
4. UI 展示仍不泄漏内部 IDs，Advanced / audit 可保留。
```

### D7 E2E / Negative Matrix

目标：

```text
证明 DraftingSubsystem 没有削弱 Worker Delegation v2 的 authority chain。
```

验收：

```text
1. define_child_worker draft-first E2E: preview -> confirmation -> Lane B accepted。
2. stale draft rejected。
3. unknown ref / raw variable / free-text placement rejected。
4. missing_handler / missing_output_producer existing tests 不回退。
5. no provider -> no generic LLM fallback。
6. artifact bundle 包含 draft、materialized preview、verification、rendered SPL、diagnostic diff。
```

---

## 19. 最终结论

通用 RepairDraftingSubsystem 是合理的长期架构层，不属于过度设计。它给未来保留了稳定接口：

```text
provider registry
common draft model
trace
confidence
clarification
draft preview
admission bridge boundary
```

但必须避免多余实现：

```text
不做万能 LLM repair compiler；
不提前实现没有当前消费方的 provider；
不构建第二套 snapshot model；
不让 draft layer 拥有 apply / materialization / verification authority。
```

首个实践应保持窄切片：

```text
WorkerDelegationInferenceProvider
define_child_worker
deterministic artifact-driven inference
draft-first CLI
existing Worker Delegation v2 materialization / verification
```

这样既能解决当前 child worker 修复交互过度结构化的问题，也能为后续其他 repair strategy 复用用户输入理解与 draft 机制保留清晰、克制的接口。
