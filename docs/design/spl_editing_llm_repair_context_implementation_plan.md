# SPL Editing LLM Repair Context 实施计划

本文档严格基于 `docs/design/spl_editing_llm_repair_context_design_v2.md` 制定。实施目标是为 SPL Editing suggestion generation 引入统一的 LLM Repair Context 层，使 LLM 不再从 raw diagnostic、compiler id 或 handler-local prompt 中猜测业务语义，而是消费由后端结构化状态投影出的、可校验、可审计、可扩展的 prompt context。

适用范围：

```text
AI-assisted SPL Editing suggestion generation
MVP 三类 issue:
  missing_handler
  missing_output_producer
  worker promotion / handoff ambiguity

MVP patch types:
  AddExceptionHandlerStep
  InsertProducerStep
  BindExistingProducerStep
  CreateWorkerHandoffContract
  ConvertDelegationIntentToMainFlowStep
  ConvertDelegationIntentToRequestInput
```

不在本计划范围内：

```text
新增 editable issue 类型
新增 patch type
修改 apply / verification authority chain
让 LLM 直接生成 arbitrary IR
让 LLM 直接修改 final SPL
把 prompt context 持久化为 canonical artifact truth
完整 UI 集成
```

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
ArtifactSnapshot / EditableIssue / RepairTarget / RepairContext
  -> structured backend state

RepairCatalog
  -> repair capability truth source

PatchRegistry
  -> patch payload schema / validator / applier / verifier truth source

LLMRepairContextBuilder
  -> common LLM facts
  -> primary_extension
  -> auxiliary_extensions
  -> ContextQuality
  -> GenerationReadiness

LLMRepairContextProvider
  -> affordance / patch-specific facts collection
  -> no repair routing
  -> no patch capability declaration

PromptRenderer + SectionRendererRegistry
  -> deterministic prompt materialization
  -> no construct enum branching in core renderer
  -> internal ids rendered only as SelectableReference / internal allowed ids

RepairHandler
  -> invoke LLM
  -> parse JSON
  -> run patch payload validation
  -> produce RepairSuggestion

Apply / Verification pipeline
  -> unchanged authority chain
```

目标行为：

```text
用户选择 issue
  -> 展示 repair options
  -> 用户选择 patch type
  -> LLMRepairContextBuilder 构建上下文
  -> PromptRenderer 渲染 prompt
  -> LLM 生成同一 patch type 下的多条 suggestions
  -> PatchValidator 校验 payload
  -> 用户确认 apply
  -> typed patch apply
  -> compiler authority verification
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. `LLMRepairContext` 是 runtime projection，不是新的 compiler source of truth。
2. `RepairCatalog` 是 repair capability 的唯一 truth source。
3. `PatchRegistry` 是 patch payload schema / validator / applier / verifier 的唯一 truth source。
4. `LLMRepairContextProvider` 只收集 facts，不声明 patch capability，不选择 repair strategy。
5. `PromptRenderer` 不按 `construct_type` / `diagnostic.kind` 写巨大 if-else。
6. core DTO 不枚举 construct-specific union。
7. extension facts 必须 schema-validated，不能是无约束 `dict[str, Any]`。
8. internal ids 只能作为 `SelectableReference` 或 internal allowed ids 出现。
9. `target_ref`、`diagnostic_id`、`irs_ref`、`exc_adapter_*`、`rcd_output_*` 不得进入业务文案 section。
10. `CompileDiagnostic.message` 不能作为 primary business fact；只能作为 debug / fallback display。
11. 禁止解析 `feedback_report.md`、`compile_report.txt`、`final_spl.txt`、`stage*.json` 来构造 prompt business facts。
12. handler 不再直接拼完整 prompt。
13. generation readiness 必须区分 `repair_unavailable`、`generation_blocked`、`ready_low_confidence`、`ready`。
14. `generation_blocked` / `repair_unavailable` 时不得调用 LLM。
15. `ready_low_confidence` 可以调用 LLM，但 prompt 必须要求保守 suggestion，不得发明确定性业务事实。
16. prompt audit artifact 是 debug artifact，不是 canonical snapshot。

---

## 3. LLM / Rule-based 决策约束

本计划允许的确定性逻辑仅限：

```text
从结构化 artifact / DTO 读取字段
从 RepairCatalog / PatchRegistry 查询已声明能力和 schema
从 TargetResolver / RepairContextBuilder 获取已解析 target 和 context
从 source spans / traces / typed IR artifact 摘取事实
基于 schema 做 presence / type validation
基于 SelectableReference 渲染 id + business summary
基于 ContextQuality / GenerationReadiness 做是否调用 LLM 的门控
```

禁止新增：

```text
基于 diagnostic.message regex 提取业务事实
基于 target_ref 字符串猜测 condition / output / delegation semantics
基于 final SPL text 推断修复策略
基于 feedback report 文本反向构造 prompt facts
rule-based semantic fallback
template 中声明 supported patch type
provider 中绕过 RepairCatalog 添加 patch capability
handler 中维护独立 prompt safety rules
```

需要在实施前显式确认的行为：

```text
修改 LLM output JSON schema
新增 patch type
新增 MVP 之外的 issue family provider
允许某个低置信度场景继续调用 LLM
允许某个缺失字段从 ready_low_confidence 升级为 generation_blocked
```

如果实现中出现“为了先跑通而用规则兜底”的倾向，应停止并提交设计确认。

---

## 4. Phase L0: Contract Freeze

### 4.1 目标

冻结 LLM Repair Context 层的基础 contract，确保后续实现不会把核心 DTO、provider、renderer 写成不可维护的 ad hoc prompt 拼接层。

### 4.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/llm_context/
  __init__.py
  model.py
  provider.py
  registry.py
  section_renderer.py
  constants.py
  errors.py

tests/unit/compiler/spl_editing/llm_context/
  test_l0_contract_model.py
  test_l0_registry_contract.py
  test_l0_boundary_imports.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/__init__.py
```

### 4.3 禁止改动

Phase L0 禁止修改：

```text
src/nl2spl/compiler/spl_editing/handlers/
src/nl2spl/compiler/spl_editing/patches/
src/nl2spl/compiler/spl_editing/core/catalog.py
src/nl2spl/compiler/spl_editing/core/registry.py
src/nl2spl/compiler/spl_editing/verification/
examples/
```

### 4.4 设计要求

必须定义：

```text
LLMRepairContext
IssueFacts
SourceFacts
TargetFacts
WorkflowFacts
StepSummary
ArtifactFacts
RepairActionFacts
SafetyFacts
PreviousSuggestionFacts
InternalRoutingFacts
SelectableReference
LLMRepairContextExtension
ContextQuality
GenerationReadiness
LLMRepairContextProvider Protocol
LLMRepairContextExtensionRegistry
LLMRepairContextSectionRenderer Protocol
SectionRendererRegistry
```

`LLMRepairContext` 必须包含：

```text
primary_extension
auxiliary_extensions
quality
generation_readiness
```

不得包含：

```text
ExceptionFlowHandlerFacts | RequiredOutputProducerFacts | WorkerPromotionHandoffFacts union
RepairCatalog entry mutable reference
PatchBundle mutable reference
CompileDiagnostic raw object
RepairPatch raw object
LLM client
```

`GenerationReadiness` 必须至少表达：

```text
repair_unavailable
generation_blocked
ready_low_confidence
ready
```

### 4.5 测试计划

新增单元测试必须覆盖：

1. core DTO 不包含 construct-specific union。
2. `LLMRepairContext` 使用 `primary_extension + auxiliary_extensions`。
3. extension facts 只能通过 schema-validated payload 表达。
4. provider registry 支持 exact key lookup。
5. duplicate exact provider key 默认拒绝。
6. section renderer registry 通过 `renderer_id + facts_schema_id` 查找。
7. `contract/model` 不 import handler / patch / LLM client。
8. `PromptRenderer` 尚未引入时，L0 不应出现 prompt 拼接逻辑。

### 4.6 验收标准

Phase L0 通过条件：

1. 所有基础 DTO frozen。
2. 所有 enum / literal 状态集中定义。
3. provider / renderer protocol 不包含修复能力判断。
4. 无 construct-specific union。
5. 无 handler prompt 迁移。
6. 新增测试全部通过。
7. 无新增 skip / xfail。

### 4.7 PM 审核清单

审核时必须检查：

1. `model.py` 是否出现 `ExceptionFlow`、`RequiredOutput`、`WorkerPromotion` 等具体 provider 类型字段。
2. registry 是否按 `affordance_id + construct_type + slot_name + diagnostic_kind + patch_type` 支持 resolve。
3. `provider.py` 是否 import LLM client。
4. `section_renderer.py` 是否 import patch applier / verifier。
5. DTO 是否可 JSON 投影。

---

## 5. Phase L1: Schema / Quality / Readiness Infrastructure

### 5.1 目标

建立 extension facts schema validation、context quality evaluator、generation readiness evaluator。此阶段只做基础设施，不接 handler，不调用 LLM。

### 5.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/llm_context/
  schema.py
  quality.py
  readiness.py

tests/unit/compiler/spl_editing/llm_context/
  test_l1_schema_validation.py
  test_l1_quality_readiness.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/llm_context/model.py
src/nl2spl/compiler/spl_editing/llm_context/registry.py
```

### 5.3 禁止改动

禁止修改：

```text
handlers/
patches/
core/catalog.py
core/service.py
verification/
```

### 5.4 设计要求

schema validation 必须支持：

```text
facts_schema_id
facts_schema_version
required keys
optional keys
unknown key policy
schema version mismatch handling
renderer compatibility check
```

ContextQuality 必须能表达：

```text
confidence
has_primary_business_fact
has_source_excerpt
has_workflow_context
has_allowed_ids
missing_context_fields
warnings
```

GenerationReadiness 规则：

```text
repair_unavailable:
  RepairCatalog / selected patch type 不支持

generation_blocked:
  required target / payload id / schema facts 缺失，不能安全生成

ready_low_confidence:
  核心 target 可定位，但缺 source excerpt / optional workflow facts

ready:
  required facts 和 schema 均满足
```

### 5.5 测试计划

新增测试必须覆盖：

1. 缺 required fact 触发 blocked 或 low confidence。
2. unknown fact key 默认拒绝。
3. facts schema version mismatch 被拒绝。
4. renderer 不支持 facts schema id 时拒绝渲染。
5. `repair_unavailable` 和 `generation_blocked` 区分清楚。
6. `ready_low_confidence` 仍允许生成，但带 warnings。
7. low confidence 不允许伪造 missing facts。

### 5.6 验收标准

Phase L1 通过条件：

1. schema validator 可独立测试。
2. readiness evaluator 不调用 LLM。
3. readiness evaluator 不查询 raw diagnostics message。
4. readiness evaluator 不决定 patch type 是否可用，只消费 RepairCatalog / registry 给出的结果。

### 5.7 PM 审核清单

1. `ready_low_confidence` 是否被错误当成 `ready`。
2. `generation_blocked` 是否仍会调用 LLM。
3. provider facts 是否可能以 loose dict 未校验形式进入 renderer。
4. schema validation 是否被 renderer 绕过。

---

## 6. Phase L2: Common Context Builder

### 6.1 目标

实现 common facts builder，将 `EditableIssue + ArtifactSnapshot + RepairTarget + RepairContext + IssuePresentation + RepairCatalog + PatchRegistry` 投影为 `LLMRepairContext` 的通用部分。

### 6.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/llm_context/
  builder.py
  selectable.py
  packing.py
  common_facts.py

tests/unit/compiler/spl_editing/llm_context/
  test_l2_common_context_builder.py
  test_l2_selectable_reference.py
  test_l2_context_packing.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/targets/
src/nl2spl/compiler/spl_editing/context/
src/nl2spl/compiler/spl_editing/presentation/
```

仅允许为读取结构化 facts 增加小型 accessor，不得改变现有语义。

### 6.3 禁止改动

禁止修改：

```text
handler prompt.py
handler.py LLM invocation flow
patch validators / appliers / verifiers
compiler pipeline
snapshot persistence schema
```

### 6.4 设计要求

`LLMRepairContextBuilder` 输入：

```text
session_id
issue
snapshot
selected_patch_type
repair_catalog
patch_registry
target_resolver
repair_context_builder
issue_presentation_view | None
previous_suggestions
```

必须构建：

```text
IssueFacts
SourceFacts
TargetFacts
WorkflowFacts
ArtifactFacts
RepairActionFacts
SafetyFacts
PreviousSuggestionFacts
InternalRoutingFacts
SelectableReference
```

不得从以下来源构造 business facts：

```text
diagnostic.message regex
target_ref string parsing
feedback_report.md
compile_report.txt
final_spl.txt
stage*.json
LLM summary
```

`SelectableReference` 必须包含：

```text
id
label
summary
kind
payload_field
business_summary
```

### 6.5 测试计划

新增测试必须覆盖：

1. `IssueFacts` 优先使用 IssuePresentation / DisplayContext。
2. `SourceFacts.source_span_ids_internal` 不进入 business text。
3. `TargetFacts.human_readable_target_summary` 不包含 `target_ref`。
4. `WorkflowFacts.nearby_steps` 包含 text / inputs / outputs / renderability。
5. `RepairActionFacts.patch_payload_schema` 来自 PatchRegistry。
6. `RepairActionFacts` 不声明 catalog 未支持的 patch type。
7. `SelectableReference` 必须带 business summary。
8. raw diagnostic message 不被读取为 primary business fact。
9. final SPL text 不被读取。

### 6.6 验收标准

Phase L2 通过条件：

1. common context 可构建，但尚不要求 provider 完整覆盖。
2. builder 不调用 LLM。
3. builder 不拼完整 prompt。
4. 所有 common facts 均有 tests。
5. guardrail tests 能阻止 raw message / target_ref 泄漏到 business facts。

### 6.7 PM 审核清单

1. 搜索 `diagnostic.message`，确认没有被用于 common business facts。
2. 搜索 `feedback_report` / `compile_report` / `final_spl`，确认 llm_context 不读取。
3. 搜索 `target_ref.split` / regex，确认没有通过字符串解析 target。
4. 检查 `SelectableReference` 是否在所有 id 暴露位置带 summary。

---

## 7. Phase L3: PromptRenderer / SectionRenderer

### 7.1 目标

实现共享 `PromptRenderer` 和 schema-bound `SectionRendererRegistry`，使 handler 不再拼完整 prompt。

### 7.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/llm_context/
  rendering.py
  section_renderer.py
  renderers/
    __init__.py

tests/unit/compiler/spl_editing/llm_context/
  test_l3_prompt_renderer.py
  test_l3_section_renderer_registry.py
  test_l3_internal_id_guardrails.py
```

### 7.3 禁止改动

禁止修改：

```text
handlers/*/prompt.py
handlers/*/handler.py
```

此阶段先提供新 renderer，不迁移旧 handler。

### 7.4 设计要求

Prompt 固定 section 顺序：

```text
1. Task
2. Issue facts
3. Source facts
4. Target construct facts
5. Local workflow facts
6. Primary repair context extension
7. Auxiliary context extensions
8. Allowed repair action
9. Payload schema
10. Safety rules
11. Previous suggestions
12. Internal allowed ids / SelectableReference
13. Output JSON only
```

PromptRenderer 不得：

```text
if construct_type == ...
if diagnostic.kind == ...
if patch_type == ...  # 用于选择业务 facts renderer
```

允许：

```text
根据 generation_readiness 渲染 no-LLM result
根据 section renderer registry 渲染 extension section
根据 selected_patch_type 渲染 payload schema section
```

### 7.5 测试计划

新增测试必须覆盖：

1. section 顺序固定。
2. core renderer 不出现 construct branch。
3. primary extension 在 auxiliary extension 前。
4. internal ids 只出现在 internal allowed ids / selectable references section。
5. `target_ref` / `diagnostic_id` 不出现在 business sections。
6. `ready_low_confidence` prompt 包含 conservative instruction。
7. `generation_blocked` / `repair_unavailable` 不渲染 LLM prompt。
8. prompt 以 JSON-only instruction 结束。

### 7.6 验收标准

Phase L3 通过条件：

1. PromptRenderer 可渲染无 provider 的 common context fixture。
2. renderer registry 可注册 / resolve section renderer。
3. renderer 不依赖 handler。
4. renderer 不调用 LLM。

### 7.7 PM 审核清单

1. `rendering.py` 是否包含 construct-specific strings。
2. `section_renderer.py` 是否读取 RepairCatalog 来决定 capability。
3. rendered prompt golden 是否泄漏 `exc_adapter_*` 到 business sections。
4. `SelectableReference` 是否带 payload_field。

---

## 8. Phase L4: Provider Migration 1 - `missing_handler`

### 8.1 目标

迁移 `missing_handler` / `AddExceptionHandlerStep` suggestion 生成，使其使用 LLM Repair Context 层，并修复 “Missing timeframe -> adapter error” 类语义跑偏。

### 8.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/llm_context/providers/
  __init__.py
  exception_flow_handler.py

src/nl2spl/compiler/spl_editing/llm_context/renderers/
  exception_flow_handler_section.py

tests/unit/compiler/spl_editing/llm_context/
  test_l4_exception_flow_provider.py
  test_l4_exception_flow_renderer.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/handlers/missing_handler/handler.py
src/nl2spl/compiler/spl_editing/handlers/missing_handler/prompt.py
```

### 8.3 禁止改动

禁止修改：

```text
patches/add_exception_handler_step/
verification/
compiler/irs/
pipeline/
```

### 8.4 设计要求

`ExceptionFlowHandlerContextProvider` 必须收集：

```text
exception_condition_text
exception_source_excerpt
parent_worker_purpose
nearby_main_flow_steps
available_variables_relevant_to_condition
allowed_handler_command_types
```

必须禁止：

```text
把 exc_adapter_* 当 condition text
把 target_ref 当 prompt 主语
把 raw diagnostic.message 当 exception condition
```

readiness 规则：

```text
condition_text 缺失但 target 可定位:
  ready_low_confidence

handler target 不可定位:
  generation_blocked

selected patch type 不是 AddExceptionHandlerStep:
  repair_unavailable 或 registry unsupported
```

### 8.5 测试计划

新增测试必须覆盖：

1. provider 从 structured target / context 提取 condition text。
2. condition text 为 `Missing timeframe` 时，prompt 包含该文本。
3. business sections 不包含 `exc_adapter_*`。
4. raw diagnostic.message 不作为 condition。
5. 缺 condition 进入 low confidence。
6. target 不可定位进入 generation blocked。
7. handler 使用 PromptRenderer，不再直接拼完整 prompt。
8. selected patch type 过滤仍生效。
9. LLM 返回多条 suggestion 时仍走现有 parser / validator。

### 8.6 验收标准

Phase L4 通过条件：

1. missing_handler 的 LLM prompt 由 `LLMRepairContext -> PromptRenderer` 产生。
2. demo regression 中 `Missing timeframe` 不再被描述为 adapter error。
3. AddExceptionHandlerStep payload schema 仍由 PatchRegistry / parser / validator 校验。
4. apply / verify 行为不变。

### 8.7 PM 审核清单

1. `missing_handler/prompt.py` 是否仍承载完整 prompt。
2. `handler.py` 是否仍直接把 `issue.message` 注入 user prompt。
3. prompt golden 是否包含 `Missing timeframe`。
4. prompt golden 是否不包含 `exc_adapter_*` 作为业务文本。

---

## 9. Phase L5: Provider Migration 2 - `missing_output_producer`

### 9.1 目标

迁移 `missing_output_producer` / `InsertProducerStep` / `BindExistingProducerStep` suggestion 生成，使 LLM 获得 required output、candidate producer、existing step summary、renderability 和 SelectableReference 上下文。

### 9.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/llm_context/providers/
  required_output_producer.py
  producer_index_auxiliary.py
  resource_contract_auxiliary.py

src/nl2spl/compiler/spl_editing/llm_context/renderers/
  required_output_producer_section.py
  producer_index_auxiliary_section.py
  resource_contract_auxiliary_section.py

tests/unit/compiler/spl_editing/llm_context/
  test_l5_required_output_provider.py
  test_l5_producer_index_auxiliary.py
  test_l5_required_output_renderer.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/handlers/missing_output_producer/handler.py
src/nl2spl/compiler/spl_editing/handlers/missing_output_producer/prompt.py
```

### 9.3 禁止改动

禁止修改：

```text
patches/insert_producer_step/
patches/bind_existing_producer_step/
producer_index core semantics
```

除非发现缺少只读 accessor，可新增 accessor，不得改变 ProducerIndex 判定逻辑。

### 9.4 设计要求

`RequiredOutputProducerContextProvider` 必须收集：

```text
required_output_name
required_output_description
declaring_worker
existing_producer_candidates
existing_outputs_already_produced
allowed_producer_command_types
bind_existing_step_is_allowed
```

每个 existing producer candidate 必须包含：

```text
step_id_internal
step_text
inputs
outputs
command_type
renderability_status
why_it_may_or_may_not_bind
```

对于 `BindExistingProducerStep`：

```text
必须提供 SelectableReference(kind="step", payload_field="step_id")
不得只提供裸 step id
候选 step 缺 renderability summary 时不得进入 ready
```

对于 `InsertProducerStep`：

```text
必须提供 output_name
应提供 output_description / contract facts
缺 description 时 ready_low_confidence
缺 output_name 时 generation_blocked
```

### 9.5 测试计划

新增测试必须覆盖：

1. prompt 包含 required output name。
2. output description 存在时进入 prompt。
3. bind candidate 包含 step text / inputs / outputs / renderability。
4. SelectableReference 为每个 bindable step 提供 summary。
5. 裸 step id 不出现在 business sections。
6. `BindExistingProducerStep` suggestion payload 可使用 `step_id`。
7. candidate 缺 renderability summary 时 blocked 或 low confidence。
8. `InsertProducerStep` 缺 output description 时 low confidence。
9. provider 不伪造 ProducerIndex candidate。

### 9.6 验收标准

Phase L5 通过条件：

1. missing_output_producer handler 不再使用旧 full prompt builder。
2. bind-existing prompt 不再只有 step ids。
3. insert-producer prompt 包含 required output semantic context。
4. selected patch type 过滤仍确保 LLM 只生成对应 patch type。
5. existing parser / validator / applier / verifier 不被绕过。

### 9.7 PM 审核清单

1. `missing_output_producer/prompt.py` 是否仍包含完整 prompt。
2. prompt golden 是否出现 candidate step text。
3. prompt golden 是否出现 naked `st_*` 且无 summary。
4. `RequiredOutputProducerContextProvider` 是否自己决定 bind capability。
5. Provider 是否通过 ProducerIndex / context facts 获取候选，而非自行猜测。

---

## 10. Phase L6: Provider Migration 3 - Worker Promotion / Handoff

### 10.1 目标

迁移 worker promotion / handoff ambiguity 相关 suggestion 生成，覆盖：

```text
CreateWorkerHandoffContract
ConvertDelegationIntentToMainFlowStep
ConvertDelegationIntentToRequestInput
```

使 LLM 能区分三种 repair strategy，并获得 delegation candidate、parent/child purpose、missing slots、binding candidates、invocation location candidates 等上下文。

### 10.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/llm_context/providers/
  worker_promotion_handoff.py
  invocation_location_auxiliary.py

src/nl2spl/compiler/spl_editing/llm_context/renderers/
  worker_promotion_handoff_section.py
  invocation_location_auxiliary_section.py

tests/unit/compiler/spl_editing/llm_context/
  test_l6_worker_promotion_provider.py
  test_l6_invocation_location_auxiliary.py
  test_l6_worker_promotion_renderer.py
```

允许修改：

```text
src/nl2spl/compiler/spl_editing/handlers/type_or_contract_ambiguity/handler.py
src/nl2spl/compiler/spl_editing/handlers/type_or_contract_ambiguity/prompt.py
```

### 10.3 禁止改动

禁止修改：

```text
patches/create_worker_handoff_contract/
patches/convert_delegation_to_main_flow_step/
patches/convert_delegation_to_request_input/
issues/promoter.py
issues/grouper.py
```

除非新增只读 accessor，不得改变 grouping / promoter 语义。

### 10.4 设计要求

`WorkerPromotionHandoffContextProvider` 必须收集：

```text
candidate_source_excerpt
why_considered_delegation
parent_worker_purpose
child_worker_purpose
missing_handoff_slots
available_parent_variables
child_input_contract_candidates
child_output_contract_candidates
expected_invocation_location_candidates
nearby_parent_flow_steps
```

不同 patch type 的 emphasis：

```text
CreateWorkerHandoffContract:
  child_worker_id
  input/output binding candidates
  invocation point candidates
  result handoff mapping

ConvertDelegationIntentToMainFlowStep:
  original action source text
  parent flow insertion context
  expected outputs

ConvertDelegationIntentToRequestInput:
  missing information question
  value target
  why user input is needed
```

readiness 规则：

```text
CreateWorkerHandoffContract 缺 child_worker_id:
  generation_blocked

CreateWorkerHandoffContract 缺 binding candidates:
  generation_blocked 或 ready_low_confidence，按 schema requiredness 决定

ConvertDelegationIntentToMainFlowStep 缺 source excerpt:
  ready_low_confidence

ConvertDelegationIntentToRequestInput 缺 missing information summary:
  ready_low_confidence 或 generation_blocked，按 payload 是否可安全生成决定
```

### 10.5 测试计划

新增测试必须覆盖：

1. prompt 包含 candidate source excerpt。
2. prompt 包含 missing handoff slots 的用户可读 labels。
3. CreateWorkerHandoffContract 缺 child worker id 时 generation_blocked。
4. ConvertToMainFlow prompt 强调 parent flow insertion context。
5. ConvertToRequestInput prompt 强调 missing information question。
6. internal worker ids 不进入 user-facing wording。
7. invocation location candidate 使用 SelectableReference。
8. selected patch type 下只生成对应 schema 的 suggestion。
9. provider 不重新决定 worker delegation 是否 editable。

### 10.6 验收标准

Phase L6 通过条件：

1. type_or_contract_ambiguity handler 使用新 context / renderer。
2. 三种 patch type 的 prompt emphasis 明确不同。
3. CreateWorkerHandoffContract 不再在缺 child_worker_id 时让 LLM 猜。
4. grouped issue 的 related diagnostics 能投影为 missing items。
5. existing patch validators / appliers / verifiers 继续生效。

### 10.7 PM 审核清单

1. `type_or_contract_ambiguity/prompt.py` 是否仍有完整 prompt。
2. prompt golden 是否将 `promotion_input_contract` 仅作为 slot id 展示，而非用户可读 missing item。
3. provider 是否调用 promoter/grouper 重新判断 issue。
4. CreateWorkerHandoffContract blocked path 是否真的不调用 LLM。

---

## 11. Phase L7: Service Integration / Handler Adapter Cleanup

### 11.1 目标

统一 handler 调用 LLMRepairContextBuilder + PromptRenderer 的路径，删除 handler-local full prompt builder 的默认路径。

### 11.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/spl_editing/handlers/
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/core/registry.py
src/nl2spl/compiler/spl_editing/demo.py
src/nl2spl/compiler/spl_editing/cli.py
examples/output/spl_editing_demo/run_demo.py
```

允许新增：

```text
src/nl2spl/compiler/spl_editing/llm_context/service.py

tests/unit/compiler/spl_editing/llm_context/
  test_l7_handler_integration.py
  test_l7_no_legacy_prompt_path.py
```

### 11.3 禁止改动

禁止修改：

```text
patch apply semantics
verification semantics
snapshot persistence schema
issue extraction semantics
```

### 11.4 设计要求

handler 允许保留：

```text
LLM invocation
JSON parse
RepairSuggestion assembly
retry / dedup logic
previous suggestions handling
```

handler 不得保留：

```text
full prompt composition
direct issue.message injection
direct target_ref injection
manual payload schema text duplication
manual safety rules duplication
```

Suggestion API 必须返回：

```text
ready
ready_low_confidence
generation_blocked
repair_unavailable
```

并保证：

```text
generation_blocked / repair_unavailable:
  suggestions = []
  no LLM call
```

### 11.5 测试计划

新增测试必须覆盖：

1. missing_handler handler 通过 context renderer 生成 prompt。
2. missing_output_producer handler 通过 context renderer 生成 prompt。
3. type_or_contract_ambiguity handler 通过 context renderer 生成 prompt。
4. blocked status 不调用 fake LLM。
5. low confidence status 调用 fake LLM，并带 conservative instruction。
6. selected patch type 传入 context builder。
7. previous suggestions 进入 prompt。
8. handler prompt files 不再包含完整 prompt body。

### 11.6 验收标准

Phase L7 通过条件：

1. 所有 MVP handler 默认走 LLMRepairContext。
2. 旧 prompt builder 不再作为生产路径使用。
3. CLI / demo 能显示 blocked / low-confidence 状态。
4. 全量 handler tests 通过。

### 11.7 PM 审核清单

1. 搜索 `build_*_user_prompt`，确认不再是默认路径。
2. 搜索 `issue.message`，确认 handler 不注入 prompt。
3. 搜索 `target_ref`，确认 handler 不注入 business prompt。
4. fake LLM call count tests 是否覆盖 blocked path。

---

## 12. Phase L8: Prompt Audit Artifacts

### 12.1 目标

新增可选 debug artifact，用于审计 context payload、rendered prompt、readiness 和 provider facts，帮助定位 suggestion 质量问题。

### 12.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/spl_editing/llm_context/audit.py

tests/unit/compiler/spl_editing/llm_context/
  test_l8_prompt_audit_artifacts.py
```

允许修改：

```text
examples/output/spl_editing_demo/run_demo.py
src/nl2spl/compiler/spl_editing/core/service.py
```

仅允许增加 debug opt-in。

### 12.3 禁止改动

禁止修改：

```text
canonical snapshot persistence
verification result semantics
apply result semantics
```

### 12.4 设计要求

可输出 debug artifacts：

```text
prompt_context_snapshot.json
rendered_prompt.txt
generation_readiness.json
provider_facts_payloads.json
```

必须声明：

```text
这些 artifact 是 debug output，不是 repair truth。
它们不得参与 apply / verification decision。
```

### 12.5 测试计划

新增测试必须覆盖：

1. audit disabled 时不写文件。
2. audit enabled 时写出四类 artifact。
3. audit JSON 不包含 non-serializable runtime object。
4. audit artifact 不影响 suggestion result。
5. rendered prompt audit 中 internal ids 只在允许 section。

### 12.6 验收标准

Phase L8 通过条件：

1. debug artifacts 可用于复现 prompt。
2. no audit path remains default production dependency。
3. no canonical snapshot hash includes prompt audit artifacts。

### 12.7 PM 审核清单

1. audit 是否默认关闭。
2. audit 是否被误用于 readiness / verification。
3. audit 是否写入 snapshot JSON。

---

## 13. Phase L9: Legacy Cleanup / Guardrail Hardening

### 13.1 目标

清理 legacy prompt paths，补齐边界测试，防止后续回归到 handler-local prompt 拼接。

### 13.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/spl_editing/handlers/
src/nl2spl/compiler/spl_editing/llm_context/
tests/unit/compiler/spl_editing/
tests/integration/compiler/spl_editing/
```

### 13.3 禁止改动

禁止修改：

```text
compiler pipeline normal compile behavior
snapshot canonical JSON contract
patch apply / verification authority chain
```

### 13.4 设计要求

必须清理：

```text
handler-specific full prompt builders
direct issue.message injection into prompt
direct target_ref injection into prompt
duplicated prompt safety instructions
loose extension facts without schema validation
construct-type if-else in PromptRenderer
```

允许保留：

```text
small prompt snippets used only by section renderers
patch-specific output schema labels sourced from PatchRegistry
test fixtures for legacy behavior marked as regression examples
```

### 13.5 测试计划

新增 / 强化测试必须覆盖：

1. business prompt sections 不包含 `exc_adapter_*`。
2. business prompt sections 不包含 `target_ref`。
3. business prompt sections 不包含 `diagnostic_id`。
4. handler text / title / explanation 不得包含 internal ids。
5. prompt 不直接包含 raw `CompileDiagnostic.message`。
6. prompt 不包含 rendered SPL 作为 source。
7. prompt 不包含 feedback report content。
8. Selectable ids 只出现在 internal allowed ids / payload reference section。
9. PromptRenderer 不含 construct-type if-else。
10. SectionRenderer 不成为巨大 if-else。

### 13.6 验收标准

Phase L9 通过条件：

1. MVP 三类 issue 全部迁移完成。
2. 旧 prompt path 不再默认可达。
3. guardrail tests 覆盖所有禁止行为。
4. full test suite 通过。
5. 无新增 skip / xfail。

### 13.7 PM 审核清单

1. `rg "diagnostic.message|issue.message|target_ref" src/nl2spl/compiler/spl_editing` 的命中是否都在 allowed debug / routing 范围。
2. `rg "feedback_report|compile_report|final_spl|stage" src/nl2spl/compiler/spl_editing/llm_context` 是否无业务读取。
3. `PromptRenderer` 是否仍纯 renderer。
4. `templates` / `renderers` 是否声明 patch capability。
5. `Provider` 是否调用 LLM。

---

## 14. Decision Gate A: Output Schema Ownership

### 14.1 目标

确认 LLM output JSON schema 的唯一来源。实施必须避免 handler prompt、PromptRenderer 和 PatchRegistry 各自维护一份 schema。

### 14.2 可选方案

```text
方案 A:
  PatchRegistry / PatchBundle 暴露 prompt-facing schema。

方案 B:
  parser / validator 暴露 schema 描述，PromptRenderer 从 registry 获取。

方案 C:
  临时保留 handler schema constants，但由 PatchRegistry re-export。
```

推荐：方案 A 或 B。方案 C 只能作为迁移 shim，必须标注 remove after L7。

### 14.3 必须明确的问题

1. 每个 patch type 的 prompt schema 从哪里读取？
2. parser / validator 与 prompt schema 如何防漂移？
3. selected patch type filtering 是否发生在 context builder 前还是 handler 前？
4. schema change 是否需要独立测试 golden？

### 14.4 验收标准

Decision Gate A 通过条件：

1. 文档明确 schema ownership。
2. 后续 L3-L7 不新增第二份 schema truth source。
3. PM 明确批准后方可进入 L7 handler migration。

---

## 15. Decision Gate B: Low-confidence Generation Policy

### 15.1 目标

确认哪些缺失字段应导致 `ready_low_confidence`，哪些应导致 `generation_blocked`。

### 15.2 初始建议

```text
missing_handler:
  condition_text missing -> ready_low_confidence
  target flow missing -> generation_blocked

missing_output_producer:
  output_name missing -> generation_blocked
  output_description missing -> ready_low_confidence
  bind candidate id missing -> generation_blocked for BindExistingProducerStep

CreateWorkerHandoffContract:
  child_worker_id missing -> generation_blocked
  invocation location candidates missing -> generation_blocked or low-confidence, pending design confirmation

ConvertDelegationIntentToMainFlowStep:
  source excerpt missing -> ready_low_confidence

ConvertDelegationIntentToRequestInput:
  missing information summary missing -> ready_low_confidence or generation_blocked, pending design confirmation
```

### 15.3 必须明确的问题

1. low-confidence 是否允许 LLM 生成 actionable patch？
2. 哪些 patch type 在缺 source excerpt 时必须 blocked？
3. CLI 是否要求用户二次确认 low-confidence suggestion？
4. low-confidence prompt 是否需要固定 safety copy？

### 15.4 验收标准

Decision Gate B 通过条件：

1. 每个 MVP patch type 有明确 readiness matrix。
2. readiness matrix 有 unit tests。
3. PM 明确批准后方可进入 L4-L6 provider migration。

---

## 16. 端到端验收场景

最终必须具备以下 E2E 或高保真集成覆盖：

1. **Missing timeframe handler**
   - 输入 snapshot 中存在 `missing_handler` issue。
   - 用户选择 `AddExceptionHandlerStep`。
   - prompt 包含 `Missing timeframe`。
   - prompt business sections 不包含 `exc_adapter_*`。
   - fake LLM 返回 REQUEST_INPUT handler。
   - payload validator 通过。
   - apply 后 verification 通过。

2. **Missing output producer - bind existing**
   - 输入 snapshot 中存在 required output 和 candidate step。
   - 用户选择 `BindExistingProducerStep`。
   - prompt 包含 output name / description。
   - prompt 包含 candidate step text / inputs / outputs / renderability。
   - LLM payload 使用 `step_id`。
   - 用户可见 suggestion 不包含 naked internal id。

3. **Missing output producer - insert producer**
   - 用户选择 `InsertProducerStep`。
   - prompt 包含 available variables / required output contract。
   - output description 缺失时状态为 `ready_low_confidence`。
   - LLM 不生成 unsupported command type。

4. **Worker delegation - create handoff blocked**
   - worker promotion issue 缺 child worker id。
   - 用户选择 `CreateWorkerHandoffContract`。
   - result 为 `generation_blocked`。
   - LLM 未被调用。

5. **Worker delegation - convert to main flow**
   - 用户选择 `ConvertDelegationIntentToMainFlowStep`。
   - prompt 包含 candidate source excerpt 和 parent flow insertion context。
   - prompt 不把 worker promotion id 当业务文本。
   - LLM payload validated。

6. **Worker delegation - convert to request input**
   - 用户选择 `ConvertDelegationIntentToRequestInput`。
   - prompt 包含缺失信息的用户可读问题。
   - REQUEST_INPUT payload 包含 prompt_text 和 value_target。
   - apply 后 user_confirmed_repair evidence 继续通过 IRS / Gate / ProducerIndex。

7. **Internal id leakage regression**
   - 对所有 MVP prompt golden 扫描：
     `target_ref`、`diagnostic_id`、`exc_adapter_*`、`worker_promotion:*` 不出现在 business sections。
   - SelectableReference section 允许出现 internal ids，但必须带 summary 和 payload_field。

8. **Audit artifact**
   - 开启 debug audit。
   - 写出 `prompt_context_snapshot.json`、`rendered_prompt.txt`、`generation_readiness.json`、`provider_facts_payloads.json`。
   - 关闭 debug audit 后不写文件。
   - audit artifact 不影响 suggestion / apply / verification。

---

## 17. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐 `spl_editing_llm_repair_context_design_v2.md`。
2. 是否扩大了 MVP issue / patch type 范围。
3. 是否新增未确认的 LLM output schema。
4. 是否新增 rule-based semantic fallback。
5. 是否绕过 RepairCatalog 决定 repair capability。
6. 是否绕过 PatchRegistry 决定 payload schema。
7. 是否让 provider 调用 LLM。
8. 是否让 renderer 查询 repair capability。
9. 是否让 handler 继续拼完整 prompt。
10. 是否从 diagnostic.message 解析 business fact。
11. 是否从 target_ref 解析 business fact。
12. 是否读取 report / final SPL / stage debug JSON。
13. 是否让 internal ids 进入 title / explanation / handler text。
14. 是否存在 loose dict extension facts。
15. 是否存在 schema validation bypass。
16. 是否存在 blocked 状态仍调用 LLM。
17. 是否存在 low-confidence 状态未加 conservative instruction。
18. 是否新增 skip / xfail。
19. 是否有关键路径无测试。
20. 是否有迁移 shim 未标注 removal phase。

---

## 18. 阶段完成顺序

推荐顺序：

```text
Phase L0   Contract Freeze
Phase L1   Schema / Quality / Readiness Infrastructure
Decision Gate A   Output Schema Ownership
Decision Gate B   Low-confidence Generation Policy
Phase L2   Common Context Builder
Phase L3   PromptRenderer / SectionRenderer
Phase L4   Provider Migration 1 - missing_handler
Phase L5   Provider Migration 2 - missing_output_producer
Phase L6   Provider Migration 3 - worker promotion / handoff
Phase L7   Service Integration / Handler Adapter Cleanup
Phase L8   Prompt Audit Artifacts
Phase L9   Legacy Cleanup / Guardrail Hardening
E2E Acceptance
Final PM Audit
```

依赖关系：

```text
L0 必须最先完成。
L1 依赖 L0。
Decision Gate A / B 必须在 L4-L7 前完成。
L2 依赖 L0 / L1。
L3 依赖 L0 / L1。
L4-L6 依赖 L2 / L3。
L7 依赖 L4-L6。
L8 可在 L3 后并行，但最终必须覆盖 L4-L6 context。
L9 必须最后执行。
```

---

## 19. 最终完成定义

本计划完成后，系统必须满足：

```text
1. MVP 三类 issue 的 suggestion generation 均通过 LLMRepairContext。
2. handler 不再直接拼完整 prompt。
3. PromptRenderer 不按 construct enum 分支。
4. provider 不声明 repair capability。
5. extension facts schema-validated。
6. selected patch type 控制 LLM 生成范围。
7. internal ids 仅在 SelectableReference / internal allowed ids section 出现。
8. missing_handler prompt 使用真实 condition_text。
9. missing_output_producer prompt 使用 output facts + candidate step summaries。
10. worker delegation prompt 使用 delegation source + missing slots + binding/invocation candidates。
11. generation_blocked / repair_unavailable 不调用 LLM。
12. ready_low_confidence 调用 LLM 时带保守指令。
13. prompt audit artifact 可用于定位语义跑偏。
14. apply / verification authority chain 不变。
15. 全量测试通过，无新增 skip / xfail。
```

最终目标不是让 LLM 拥有新的 repair authority，而是让 LLM 在生成 candidate suggestion 时看到正确、足够、结构化的业务上下文。最终是否接受修复，仍由用户确认、typed patch apply 和 compiler authorities 决定。
