# Worker Delegation 修复策略与交互输入 Contract 缺口

日期：2026-07-01  
状态：待设计与修复  
相关组件：WORKER_PROMOTION IRS、RepairStrategySpec、RepairCatalog、Presentation DTO、RepairDirective、SelectableRefSet、CLI/UI

关联问题：[`spl_editing_issue_presentation_fact_projection_gap.md`](spl_editing_issue_presentation_fact_projection_gap.md)

---

## 1. 问题概述

当前 `Worker delegation is underspecified` issue 提供三个 repair options：

```text
1. Create a worker handoff contract
2. Convert to main-flow step
3. Ask the user for missing information
```

这组选项混淆了三种不同语义：

```text
1. 当前正在编辑 SPL 的用户补充编译期需求；
2. 修改最终 SPL，让未来运行工作流的用户提供业务值；
3. 用户选择一种 construct-level repair strategy。
```

其中选项 3 当前实际对应 `ConvertDelegationIntentToRequestInput`，其行为是在最终
`MainWorker` 中生成 `REQUEST_INPUT`。它不是让当前用户补充 child worker 定义，无法解决
Worker 静态 contract 缺失。

同时，当前所有 issue 基本共享一个自然语言 `Optional repair instruction` 输入框，无法表达
某些 repair option 在生成 suggestion 前必须收集结构化信息。

---

## 2. 当前案例的正确语义

当前 source-backed delegation intent 表达：

```text
Optional delegated subtasks such as source gathering or template matching may be
used if bounded and the returned evidence is normalized into approved evidence
carriers.
```

该文本虽然没有完整定义 child worker contract，但已经表达了创建或使用 child worker 的
意图。因此不应把它降级为纯 policy，也不应默认认为不存在 delegation demand。

正确判断是：

```text
delegation intent = present
concrete task boundary = incomplete
child worker contract = incomplete
invocation/result handoff = incomplete
```

用户最终需要在两个 construct-level 结果之间选择：

```text
1. Define this work as a child worker
2. Keep this work in the main workflow
```

第二项与现有 `ConvertDelegationIntentToMainFlowStep` 的结果语义一致。无需再增加一个
“Keep as policy only”选项。

---

## 3. `Ask user for missing information` 的问题

### 3.1 面向对象和措辞错误

当前界面的受众就是用户。`Ask user for missing information` 使用第三人称和系统开发者视角，
用户无法判断它指的是：

```text
当前由自己补充信息；
还是最终工作流运行时向另一个用户提问。
```

### 3.2 实际行为不能补齐 Worker contract

Worker delegation closure 至少需要在编译时确定：

```text
delegated responsibility
child worker inputs
child worker outputs
invocation timing/placement
result handoff bindings
```

生成一个运行时 `REQUEST_INPUT` 不能建立这些静态 construct 和 binding。

### 3.3 与当前用户补充建议的交互重叠

系统已经允许当前用户提供 repair instruction。若用户需要补充编译期信息，应该扩展当前
authoring interaction，而不是把“向用户提问”建模成第三个 patch strategy。

### 3.4 处理结论

`ConvertDelegationIntentToRequestInput` 不应继续作为
`worker_promotion.resolve_contract` 的 repair option。

该 patch 是否在其他“缺少运行时业务值”的 IRS slot 中保留，应由对应 repair affordance
单独决定；本问题不要求全局删除 patch type。

---

## 4. 需要补充的结构化信息

选择 `Define this work as a child worker` 后，系统应帮助当前用户补充以下业务信息：

```text
Delegated responsibility
  Which work should the child worker perform?

Required information
  What information does it need from the main workflow?

Returned result
  What should it return?

Invocation timing
  When should the main workflow invoke it?

Result usage
  How should the main workflow use the returned result?
```

这些字段必须使用用户可理解的业务语言，不应暴露：

```text
handoff_id
WorkerHandoffIR
input_binding_status
output_binding_status
stage slice id
verification lane
```

后端可以根据 source facts、snapshot 和 `SelectableRefSet` 预填候选值，用户负责确认或调整。

---

## 5. 自然语言输入不足以替代结构化输入

当前 `Optional repair instruction` 适用于：

```text
用户已选择合法 strategy；
目标 construct 已确定；
用户只需要表达行为偏好。
```

它不适用于：

```text
具体 delegated responsibility 尚未确定；
必须选择合法 input/output refs；
必须明确 invocation/result handoff；
缺少必要字段时 generation 必须被阻止。
```

因此需要把用户输入模式建模为 repair option contract，而不是继续增加特例输入框。

---

## 6. 解决方案：Backend-owned Repair Interaction Contract

### 6.1 核心原则

前端不能根据以下字段自行决定渲染结构化表单还是自然语言输入框：

```text
issue.kind
construct_type
slot_name
patch_type
repair strategy name
```

输入方式必须由后端 Presentation DTO 明确声明。

### 6.2 Presentation DTO

建议引入：

```python
@dataclass(frozen=True)
class RepairInteractionView:
    interaction_kind: Literal[
        "none",
        "natural_language",
        "structured",
        "structured_with_notes",
    ]
    contract_id: str
    fields: tuple[RepairInputFieldView, ...]
    additional_instruction: RepairInputFieldView | None
    readiness: Literal["ready", "input_required", "blocked"]
```

字段 contract：

```python
@dataclass(frozen=True)
class RepairInputFieldView:
    field_id: str
    label: str
    description: str | None
    input_type: Literal[
        "short_text",
        "long_text",
        "single_choice",
        "multi_choice",
        "reference_select",
    ]
    required: bool
    value: object | None
    options: tuple[RepairInputOptionView, ...]
    ref_role: str | None
```

该 DTO 只描述用户输入界面和 readiness，不承载 patch capability truth。

### 6.3 Contract 来源

建议关系：

```text
RepairStrategySpec / repair option
-> directive_input_contract_id
-> RepairInputContractRegistry
-> RepairInteractionView
-> CLI/UI renderer
```

例如：

```text
worker_delegation.complete_closure.v1
  option = define_child_worker
  directive_input_contract_id = worker_delegation.define_child_worker.v1

worker_delegation.complete_closure.v1
  option = keep_in_main_flow
  directive_input_contract_id = common.optional_instruction.v1
```

`RepairCatalog` 和 runtime registry 仍决定 option 是否可用；input contract 不能成为第二套
repair capability source。

---

## 7. 不同 Repair Option 的输入模式

### 7.1 Define this work as a child worker

```text
interaction_kind = structured_with_notes
readiness = input_required（必要字段不完整时）
```

结构化字段：

```text
delegated responsibility    required
required input refs         required or explicitly known_empty
returned result definitions required or explicitly known_empty
invocation timing           required
result usage/bindings        required or explicitly known_empty
additional instruction      optional
```

`reference_select` 的选项必须来自 `SelectableRefSet`。前端不得提交任意已有变量名作为 ref。
用户明确创建的新业务输出必须作为 user-provided evidence 进入后端验证流程，不能直接写 IR。

### 7.2 Keep this work in the main workflow

```text
interaction_kind = natural_language
readiness = ready
additional instruction = optional
```

没有用户建议时走 minimal main-flow policy；有建议时生成 directive-driven main-flow command。

### 7.3 其他 Issue Family

统一 contract 也适用于其他 issue：

```text
missing_handler
  -> natural_language，通常 optional

missing_output_producer
  -> structured_with_notes，可选择合法 input refs

API review-only issue
  -> none，不进入 repair interaction
```

输入模式属于具体 repair option，不应对整个 issue family 写死。

---

## 8. 提交与生成流程

建议流程：

```text
IssuePresentationView
-> user selects RepairOptionView
-> backend returns RepairInteractionView
-> frontend renders declared fields
-> user submits RepairDirectiveDraft
-> backend validates required fields and refs
-> backend returns readiness/errors
-> normalized RepairDirective
-> ConstructRepairIntent
-> ConstructClosurePlan
-> preview stage-slice materialization
-> user confirms preview
-> RepairEvidencePacket
-> apply materialization
-> verification
```

必要字段未完成时：

```text
readiness = input_required
suggestion generation = blocked
preview generation = blocked
```

前端不得通过空字符串、默认变量名或 LLM 推断绕过 readiness。

---

## 9. RepairDirective 边界

结构化表单提交后形成的是 provisional `RepairDirectiveDraft`，不是 patch 或 IR。

后端必须：

```text
1. 校验 contract_id 和 schema version；
2. 校验 snapshot/overlay version；
3. 校验 required fields；
4. 校验 selected refs 属于当前 SelectableRefSet；
5. 将用户新提供的业务事实标记为 user evidence；
6. 生成 normalized RepairDirective；
7. 仅允许 ConstructRepairIntent 消费已验证的 selected_ref_ids；
8. 在 preview/apply 中继续执行 stage policy 和 verification。
```

结构化输入不能直接成为 `WorkerIR`、`WorkerHandoffIR` 或 `StepIR` payload。

---

## 10. 预期用户展示

Issue card/detail 应接近：

```text
Potential child-worker responsibility:
source gathering or template matching

The intent to delegate is present, but the task boundary, inputs, outputs,
invocation timing, and result handoff are incomplete.

[1] Define this work as a child worker
    Requires task and handoff details before a preview can be generated.

[2] Keep this work in the main workflow
    Uses a simple main-flow implementation unless you provide a preference.
```

选择选项 1 后，UI 显示后端声明的结构化表单。选择选项 2 后，UI 显示可选自然语言建议。

不再展示：

```text
Ask user for missing information
```

---

## 11. 架构风险

### 11.1 前端形成第二套 repair semantics

若前端按 issue kind 或 patch type 硬编码表单，会重现 CLI/UI 各自推断语义的问题。

### 11.2 Input contract 形成第二套 capability registry

`RepairInputContractRegistry` 只定义输入要求，不得声明 supported patch types、verification lane
或 materialization authority。

### 11.3 结构化字段退化为任意字符串

已有变量、worker、output、placement 等引用必须使用 stable ref IDs，不能仅提交显示名称。

### 11.4 LLM 在 readiness 前补造缺失信息

必填业务事实缺失时必须阻止 generation。LLM 不能替用户定义 task boundary 或 contract。

### 11.5 自然语言和结构化数据相互冲突

结构化字段是 materialization 可消费事实；additional instruction 只能表达偏好。二者冲突时
必须报 validation error 或要求用户确认，不能让 LLM自行选择。

---

## 12. 初步验收标准

未来实现至少应满足：

```text
1. WORKER_PROMOTION issue 只展示两个结果策略：define child worker / keep in main flow。
2. ConvertDelegationIntentToRequestInput 不再由 worker_promotion.resolve_contract 暴露。
3. option 1 返回 structured_with_notes interaction contract。
4. option 2 返回 optional natural-language interaction contract。
5. 前端不按 issue kind、construct type 或 patch type 决定输入 UI。
6. required structured fields 不完整时 suggestion/preview generation 被阻止。
7. reference_select 只接受当前 SelectableRefSet 中允许的 ref IDs。
8. 用户新增业务事实进入 RepairDirective 和 RepairEvidencePacket，不直接进入 IR。
9. option availability 仍由 RepairCatalog/runtime capability 决定。
10. input contract 不声明 patch capability、stage authority 或 verification lane。
11. CLI 与 UI 消费同一个 RepairInteractionView contract。
12. preview 展示最终用户可理解的 child worker、inputs、outputs、invocation 和 result usage。
13. apply 结果经过 stage slices 和 Lane B verification。
14. negative tests 证明前端提交任意 ref、缺字段或 stale snapshot 会失败。
15. E2E 覆盖有/无用户补充的 define-child-worker 和 keep-in-main-flow 两条路径。
```

---

## 13. 非目标

本问题记录暂不定义：

```text
1. RepairInteractionView 的最终模块路径；
2. 表单的具体视觉设计；
3. Worker closure 的全部 stage-slice 实现；
4. 用户新建 variable/output 的最终 symbol admission contract；
5. ConvertDelegationIntentToRequestInput 在其他 issue family 中是否保留。
```

这些内容应在后续正式设计和实施计划中进一步闭合。
