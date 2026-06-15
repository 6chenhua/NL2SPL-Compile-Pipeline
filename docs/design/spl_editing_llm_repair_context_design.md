# SPL Editing LLM Repair Context 初步方案

## 1. 背景

SPL Editing 后端当前已经具备较完整的安全链路：

```text
ArtifactSnapshot
-> EditableIssue
-> RepairCatalog / patch type selection
-> LLM-generated RepairSuggestion
-> user confirmation
-> typed RepairPatch apply
-> Lane A / Lane B compiler replay
-> verification accepted / rejected
```

这条链路解决的是“LLM 不能直接修改 SPL、不能绕过用户确认、不能绕过 compiler authority”的问题。

但最近的 demo 暴露了另一个问题：即使 patch 最终能被 compiler authority 接受，LLM 生成的 suggestion 仍可能语义不贴合业务场景。例如用户选择：

```text
Exception has no handler: Missing timeframe
```

LLM 却生成：

```text
Please provide instructions on how to proceed with the adapter error.
```

这说明当前缺少一个标准化的 **LLM Repair Context 层**。现有 handler 直接拼 prompt，容易把 raw diagnostic message、target_ref、compiler-generated id 暴露给 LLM，导致 LLM 从内部 id 猜语义。

本设计文档的目标是定义一套初步方案：未来 LLM 在生成任意 SPL construct repair suggestion 时，应该消费哪些通用上下文、哪些特定上下文，以及哪些信息不能作为业务语义暴露。

## 2. 当前问题

### 2.1 Handler 直接拼 prompt，缺少统一上下文范式

当前大致流程是：

```text
EditableIssue
+ RepairTarget
+ RepairContext
-> handler-specific prompt
-> LLM JSON suggestion
```

形式上已经有 `TargetResolver`、`ContextBuilder`、`RepairHandler` 三层，但 `RepairContextBuilder` 目前没有形成稳定的语义 contract。不同 handler 自己决定 prompt 里放什么字段。

结果是：

```text
不同 issue family 的上下文粒度不一致；
业务事实与 compiler routing id 混在一起；
presentation 层能展示正确语义，但 LLM handler 没有使用；
raw CompileDiagnostic.message 被当成主要语义输入；
target_ref 被直接暴露给 LLM。
```

### 2.2 `missing_handler` 使用 raw diagnostic message 作为 condition

`missing_handler` 当前给 LLM 的 condition 不是用户可读的 exception condition，而是 diagnostic message。

实际应该给：

```text
Exception condition:
  Missing timeframe
```

但当前容易给成：

```text
Exception flow 'exc_adapter_03' has condition but no handler step.
Target: worker:worker_main.exception_flow:exc_adapter_03
```

`exc_adapter_03` 是 compiler-generated id，不是业务事实。因为它包含 `adapter`，LLM 会误以为业务问题是 adapter error。

### 2.3 ContextBuilder 多数偏薄

例如 exception flow context builder 的职责描述是：

```text
Gather exception flow context: worker, flow id, condition, nearby steps.
```

但实际上下文只有 issue、target、worker scope、user instruction，未稳定提供：

```text
condition_text
source_excerpt
nearby steps
worker purpose
available variables
current flow context
```

这导致 handler 即使想构造高质量 prompt，也没有统一来源。

### 2.4 Prompt 暴露 internal routing id

当前多个 handler 会把以下字段直接放进 prompt：

```text
target_ref
diagnostic message
construct id
worker_promotion id
resource contract demand id
exception flow id
step id
```

这些字段对后端 routing 很重要，但对 LLM 不是稳定业务语义。默认暴露这些 id 会带来两类风险：

```text
LLM 把 compiler id 当作业务词汇；
LLM 生成带有 internal id 语义的用户可见 suggestion。
```

### 2.5 Existing artifact context 不足

`missing_output_producer` 已经比 `missing_handler` 稍好，因为它至少会给真实 output name，并能收集 existing steps。

但它给 LLM 的 bindable context 仍然偏薄：

```text
Bindable existing step ids:
  - st_1
  - st_2
```

这不足以让 LLM 判断哪个 step 适合作为 producer。更合理的是给出：

```text
st_1:
  text: Produce the draft communication artifact.
  inputs: source_evidence_set, user_request
  outputs: draft_communication_artifact, completion_status
```

### 2.6 Verification 能保证结构合法，不能保证 suggestion 语义贴切

当前 compiler replay 和 verifier 可以保证：

```text
patch 类型合法；
patch 作用于 stage-level artifact；
user_confirmed_repair evidence 生效；
Gate / IRS / ProducerIndex / Renderer 接受；
目标 diagnostic resolved。
```

但它不能自动保证：

```text
handler text 业务上合适；
question 问的是正确缺失信息；
producer step 真正符合源需求；
handoff contract 语义贴合 delegation intent。
```

因此必须在 LLM 输入上下文层面提高 suggestion 质量，而不是指望 verification 补足所有语义问题。

## 3. 设计目标

LLM Repair Context 层应提供一个标准化投影：

```text
EditableIssue
+ ArtifactSnapshot
+ RepairTarget
+ RepairContextBuilder output
+ IssuePresentation / display facts
+ RepairCatalog selected patch type
-> LLMRepairContext
-> PromptRenderer
-> LLM
-> RepairSuggestion
```

核心目标：

```text
1. 给 LLM 足够的业务事实，避免从 compiler id 猜语义。
2. 给 LLM 足够的 artifact / flow 约束，避免生成形式合法但业务不贴合的 patch。
3. 统一 context 构造范式，避免每个 handler 自己随意拼 prompt。
4. 保留现有安全边界：LLM 只生成 suggestion，不决定 issue、patch availability、apply 或 verification。
```

## 4. 非目标

本方案不改变以下边界：

```text
LLM 不负责发现 issue。
LLM 不负责决定 repair option 是否可用。
LLM 不负责选择 compiler authority。
LLM 不直接修改 final SPL。
LLM 不绕过 typed RepairPatch。
LLM 不绕过 user confirmation。
LLM 不绕过 Lane A / Lane B verification。
```

本方案也不要求把 prompt context 持久化进 canonical artifact snapshot。LLM Repair Context 是从 snapshot 和 backend state 派生出的运行时投影。

## 5. 高层原则

### 5.1 Business facts first

LLM 默认看到的是用户可理解的业务事实：

```text
condition_text
output_name
output_description
worker purpose
source excerpt
nearby step summary
available variables
missing items
selected patch type
```

而不是：

```text
diagnostic_id
target_ref
irs_ref raw dump
exc_adapter_03
rcd_output_s13
worker_promotion:candidate_x
```

### 5.2 Internal ids are routing facts, not semantic facts

internal routing id 可以存在于 context 中，但必须标记为 internal，并且默认不进入自然语言 task description。

如果某个 patch payload 必须使用 worker_id、flow_id、step_id，应该作为 allowed id / routing metadata 提供，而不是作为业务解释文本提供。

### 5.3 Context comes from structured backend state

LLM context 只能来自：

```text
ArtifactSnapshot
EditableIssue
CompileDiagnostic structured metadata
RepairTarget
RepairContextBuilder output
RepairCatalog
TargetResolver
source spans / traces
typed IR artifacts
presentation display facts
```

禁止从以下来源解析业务事实：

```text
feedback_report.md
compile_report.txt
stage*.json debug artifact
rendered final SPL text
diagnostic.message regex
LLM self-summary
```

### 5.4 Prompt rendering is shared infrastructure

具体 issue handler 不应直接拼完整 prompt。更合理的职责划分是：

```text
ContextBuilder:
  收集结构化 repair facts

LLMRepairContextBuilder:
  统一组合通用上下文和 construct-specific 上下文

PromptRenderer:
  按标准模板渲染 prompt

RepairHandler:
  调用 LLM，解析 JSON，生成 RepairSuggestion
```

## 6. 通用上下文

所有 SPL construct issue 的 LLM suggestion 都应该具备以下通用上下文。

### 6.1 Issue Facts

用于说明“现在修什么”。

建议字段：

```text
issue_category
user_facing_title
what_was_detected
missing_items
why_it_matters
suggested_resolution
repairability
selected_patch_type
```

`suggested_resolution` 是 informational guidance，不是 repair authority。只有 RepairCatalog 支持的 patch type 才能进入 actionable repair option。

### 6.2 Source Facts

用于说明“这个问题来自哪些需求文本”。

建议字段：

```text
primary_source_excerpt
related_source_excerpts
source_section_label
source_span_ids_internal
user_repair_instruction
```

`source_span_ids_internal` 可用于 audit / routing，但默认不作为业务语义展示给 LLM。

### 6.3 Target Construct Facts

用于说明“修复落在哪个 construct 上”。

建议字段：

```text
construct_type
slot_name
construct_role
human_readable_target_summary
current_construct_state
parent_construct_summary
```

示例：

```text
Construct: EXCEPTION_FLOW
Missing slot: handler_action
Target summary: Exception flow for condition "Missing timeframe"
Parent worker: MainWorker
```

### 6.4 Local Workflow Facts

用于让 LLM 理解局部流程。

建议字段：

```text
worker_id_internal
worker_name
worker_purpose
flow_kind
nearby_steps
available_inputs
available_outputs
available_variables
already_produced_variables
required_outputs_still_missing
relevant_constraints
```

每个 step summary 应包含：

```text
step_id_internal
text
command_type
inputs
outputs
flow_ref
block_ref
source_backed / user_confirmed / handoff_backed status
```

### 6.5 Allowed Repair Facts

用于约束 LLM 输出。

建议字段：

```text
selected_patch_type
patch_payload_schema
allowed_command_types
allowed_variable_names
allowed_worker_ids
allowed_step_ids
allowed_output_names
forbidden_actions
verification_lane
```

RepairCatalog / runtime registry 是 repair capability truth source。LLMRepairContext 不能声明额外 patch capability。

### 6.6 Safety and Authority Facts

统一提示 LLM 的边界：

```text
Do not invent source facts.
Do not invent variables unless explicitly allowed.
Do not use compiler ids as business wording.
Do not include SPL syntax when renderer owns syntax.
Do not output final SPL text.
Output only JSON patch payload.
Use only selected patch type.
```

### 6.7 Previous Suggestions Facts

用于生成多条不同 suggestion。

建议字段：

```text
previous_suggestion_titles
previous_payload_summaries
avoid_repeating_same_text
avoid_repeating_same_payload
```

这只用于多样性，不影响 repair availability。

## 7. Construct-Specific Context

通用上下文不足以覆盖所有 issue。不同 construct family 需要额外上下文。

### 7.1 EXCEPTION_FLOW.handler_action / missing_handler

必须提供：

```text
exception_condition_text
exception_source_excerpt
parent_worker_purpose
exception_flow_id_internal
nearby_main_flow_steps
available_variables_relevant_to_condition
allowed_handler_command_types
```

对 `Missing timeframe`，LLM 应看到：

```text
Exception condition:
  Missing timeframe

Relevant variables:
  timeframe: Optional time range or deadline context.
  missing_required_fields: Required fields that are still missing.

Nearby workflow:
  Identify missing required fields.
  Ask highest-value clarifying questions.
```

而不是：

```text
Exception flow exc_adapter_03
Target: worker:worker_main.exception_flow:exc_adapter_03
```

### 7.2 REQUIRED_OUTPUT.producer / missing_output_producer

必须提供：

```text
required_output_name
required_output_description
declaring_worker
output_contract_entry
existing_producer_candidates
existing_outputs_already_produced
allowed_producer_command_types
whether_bind_existing_step_is_allowed
```

existing producer candidate 不应只有 step id，而应包含：

```text
step_id_internal
step_text
inputs
outputs
command_type
renderability_status
why_it_may_or_may_not_bind
```

### 7.3 RESOURCE_CONTRACT_DEMAND.producer

必须提供：

```text
materialized_resource_names
resource_kind
requiredness
resource_description
primary_or_alias_role
related_diagnostics_summary
resource_contract_binding_context
```

`rcd_output_s13` 这类 id 不应作为业务名给 LLM。应转成：

```text
Required materialized resource:
  assumptions_log

Description:
  Short log of assumptions for unresolved items.
```

### 7.4 WORKER_PROMOTION / WORKER_HANDOFF

必须提供：

```text
candidate_source_excerpt
why_considered_delegation
parent_worker_id_internal
parent_worker_purpose
child_worker_id_internal
child_worker_purpose
child_input_contract
child_output_contract
missing_handoff_slots
available_parent_variables
expected_invocation_location_candidates
nearby_parent_flow_steps
existing_handoff_summary
```

不同 patch type 需要不同重点：

```text
CreateWorkerHandoffContract:
  input/output binding candidates
  invocation point candidates
  parent-child variable compatibility

ConvertDelegationIntentToMainFlowStep:
  original action source text
  parent flow insertion context
  expected outputs

ConvertDelegationIntentToRequestInput:
  missing information question
  value target
  reason user input is needed
```

### 7.5 REQUEST_INPUT gaps

必须提供：

```text
question_purpose
missing_value_name
expected_data_type
available_variable_namespace
whether_user_input_is_allowed_here
```

### 7.6 CALL_API gaps

必须提供：

```text
desired_external_action
available_apis_or_connectors
required_inputs
expected_response_outputs
source_excerpt_authorizing_api_use
```

LLM 不应发明 API 名，除非 selected patch type 明确允许创建新的 API declaration。

### 7.7 INVOKE_WORKER / handoff invocation gaps

必须提供：

```text
parent_worker
child_worker
known_handoff_contracts
required_input_bindings
required_output_bindings
missing_binding_names
valid_invocation_location_candidates
```

这与 worker promotion 不同：这里 worker 已存在，问题是 invocation / binding correctness。

## 8. 建议的 Context DTO 形状

初步建议定义一个统一投影模型：

```text
LLMRepairContext
  issue_facts
  source_facts
  target_facts
  workflow_facts
  artifact_facts
  repair_action_facts
  safety_facts
  previous_suggestion_facts
  internal_routing
  construct_specific
```

其中：

```text
issue_facts:
  用户可理解的问题摘要

source_facts:
  source excerpts 和 provenance

target_facts:
  construct / slot / worker / flow 的用户可读摘要

workflow_facts:
  nearby steps、available vars、producer state

artifact_facts:
  相关 typed IR artifact 的摘要

repair_action_facts:
  selected patch type、schema、allowed values

safety_facts:
  全局和 patch-specific 禁止项

internal_routing:
  diagnostic_id、target_ref、worker_id、flow_id
  默认不进入业务语义 prompt

construct_specific:
  按 construct family 扩展
```

## 9. Prompt 渲染原则

标准 prompt 应按固定顺序渲染：

```text
1. Task
2. Issue facts
3. Source facts
4. Target construct facts
5. Local workflow facts
6. Allowed repair action
7. Payload schema
8. Safety rules
9. Previous suggestions
10. Output JSON only
```

默认不渲染 raw target_ref / diagnostic_id。若确实需要给 LLM 可选 id，应放在明确标注的 section：

```text
Internal allowed ids, do not use as business wording:
  worker_id: worker_main
  exception_flow_id: exc_adapter_03
```

## 10. 与现有 Presentation 层的关系

Issue Presentation 层已经能生成用户可读 issue view：

```text
Exception has no handler: Missing timeframe
Required output has no producer: assumptions_log
Worker delegation is underspecified
```

LLM Repair Context 层不应重复 invent 这套语义，而应复用或对齐 presentation/display facts：

```text
EditableIssue
-> IssuePresentationView / DisplayContext
-> LLMRepairContext.issue_facts / target_facts
```

区别是：

```text
Presentation DTO 面向 CLI / UI 用户展示；
LLMRepairContext 面向 LLM suggestion 生成；
二者都从 backend structured state 派生；
二者都不能解析 report；
二者都不能成为 repair capability truth source。
```

## 11. 初步落地阶段

### L0: Context Contract Freeze

冻结：

```text
LLMRepairContext 顶层分区
internal id exposure policy
raw diagnostic message policy
source facts policy
selected patch type policy
```

### L1: Context Builders Refactor

将现有 context builder 从薄包装升级为结构化 facts collector：

```text
ExceptionFlowContextBuilder
RequiredOutputContextBuilder
WorkerPromotionContextBuilder
```

优先覆盖三类 MVP issue。

### L2: PromptRenderer

新增统一 prompt renderer：

```text
LLMRepairContext -> prompt text
```

handler 不再直接拼 `issue.message` / `target_ref`。

### L3: Handler Migration

按风险顺序迁移：

```text
1. missing_handler
2. type_or_contract_ambiguity
3. missing_output_producer
```

### L4: Guardrail Tests

增加边界测试：

```text
LLM prompt 不包含 exc_adapter_* 作为业务文本
LLM prompt 不直接使用 raw diagnostic.message
missing_handler prompt 包含 condition_text / source_excerpt
missing_output prompt 包含 step summaries, not only step ids
worker delegation prompt 包含 candidate source text / parent-child contracts
```

### L5: Demo Regression

针对 demo 验收：

```text
Missing timeframe
-> suggestions 应围绕 timeframe / deadline context
-> 不应出现 adapter error
```

## 12. 开放问题

1. `LLMRepairContext` 是否应直接复用 `IssuePresentationView`，还是单独定义 display facts DTO？
2. internal routing id 是否完全不进 prompt，还是进入单独的 internal allowed ids section？
3. source excerpt 的最大长度和 nearby steps 的数量如何限制？
4. 对高风险 patch type，是否要求用户额外输入 repair instruction 后才调用 LLM？
5. 是否需要记录 LLM prompt context 的 audit snapshot，便于回溯 suggestion 质量问题？

## 13. 初步结论

当前 SPL Editing 的 LLM suggestion 问题不是单个 prompt 文案错误，而是缺少标准化 LLM Context 层。

现有系统已经有较强的输出安全边界：

```text
typed patch
user confirmation
user_confirmed_repair evidence
Lane A / Lane B verification
```

但输入侧还缺少：

```text
业务事实优先的上下文；
结构化 source / target / workflow facts；
internal id 隔离策略；
统一 prompt 渲染范式；
construct-specific context contract。
```

因此应新增 LLM Repair Context 层，将 prompt 构造从 handler 内部临时拼接升级为后端统一投影。这样才能让未来修复任意 SPL construct issue 的 LLM suggestion 更稳定、更贴合业务语境，同时不破坏现有 compiler authority chain。
