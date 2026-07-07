# Worker Delegation Define-Child 字段确认式 Draft 设计

日期：2026-07-05  
状态：设计草案，待评审  
适用范围：`WORKER_PROMOTION.resolve_contract` 中的 `define_child_worker` 修复策略  
相关组件：SPL Editing、RepairDraftingSubsystem、Worker Delegation v2、SelectableRefSet、NewOutputAdmission、Stage 3.5 / Stage 5 / Stage 7 repair slices、Lane B verification

---

## 1. 背景

当前 `Define this work as a child worker` 已经从早期的大型结构化表单改为 draft-first：

```text
用户选择 define_child_worker
-> 用户可输入一句自然语言，或直接回车
-> RepairDraftingSubsystem 推断 responsibility / input_refs / output_draft / placement / result_binding
-> CLI 展示整体 draft
-> 用户整体确认
-> materialized preview
-> apply + Lane B verification
```

这个方向解决了“让用户填写 placement、handoff、invoke output、result binding 等技术字段”的体验问题，但又引入了另一个问题：系统推断过多，用户确认过少。

`Define this work as a child worker` 不是普通文本修复，而是在创建一个新的执行单元。用户至少应该确认 child worker 的核心业务契约，否则系统可能把子任务、输入、输出和业务逻辑都替用户决定。

---

## 2. 核心问题

当前 draft 可能出现以下问题：

```text
Input variables: user_request
Returned result: del s31
Result handling: parent-local temporary
```

这些问题分别对应：

1. 输入变量可能推断错，例如 source gathering 更合理的输入可能是 `connectors_or_source_repositories`，而不是 `user_request`。
2. 输出名可能暴露内部 candidate id，例如 `del s31`，用户无法理解。
3. `parent-local temporary` 是实现细节，不是用户语义。
4. 用户只能整体接受或取消 draft，无法逐项确认或覆盖核心语义字段。

更重要的是，当前设计允许用户几乎不提供任何核心信息，仅通过回车让系统创建 child worker。这对 UX 很轻，但对语义安全不够稳。

---

## 3. 设计目标

新的交互应改为字段确认式 draft-first：

```text
用户选择 Define this work as a child worker
-> 系统立即生成四个核心问题的答案示例
-> 前端逐项展示这四个问题
-> 用户可以直接接受示例，也可以覆盖输入
-> 四个核心字段都被确认后，才进入 Admission / Materialization / Verification
```

四个核心字段是：

```text
1. 子任务到底是什么
2. child worker 需要哪些输入
3. child worker 产出什么结果
4. child worker 内部要执行什么业务逻辑
```

系统仍然负责推断技术字段：

```text
1. 插入主流程的位置
2. worker_id / block_id / step_id
3. handoff id
4. invoke step
5. parent-local temporary result name
6. exact result binding mechanics
7. verification lane
```

这些技术字段不应要求用户填写，也不应作为普通用户确认页的主要内容。

---

## 4. 用户交互语义

### 4.1 前端语义

当用户选择：

```text
Define this work as a child worker
```

后端应立即返回一个字段确认 draft，其中包含四个字段的推荐答案、置信度、证据来源和可选候选项。

前端应展示类似：

```text
1. Child worker task
   Suggested: Gather source evidence from approved connectors
   [Press Enter to accept, or edit]

2. Inputs
   Suggested: connectors_or_source_repositories
   Options:
     - user_request
     - timeframe
     - connectors_or_source_repositories
   [Press Enter to accept, or choose]

3. Output
   Suggested: source_evidence_result
   [Press Enter to accept, or edit]

4. Business logic
   Suggested: Retrieve source evidence from approved connectors and normalize the returned evidence for the main workflow.
   [Press Enter to accept, or edit]
```

终端版 `run_demo.py` 只是模拟前端。由于控制台限制，这四个字段可以逐个显示、逐个输入。但注意：四个推荐答案必须是在用户选择修复策略后一次性生成的，而不是每问一个问题再重新推断一次。

### 4.2 回车语义

回车不表示“跳过这个字段”。

回车表示：

```text
accept suggested answer
```

也就是说，每个核心字段最终都必须有确认来源：

```text
source = accepted_default | user_override
```

如果某个字段没有可用示例，并且用户也没有输入，则该 draft 必须保持 blocked，不能进入 materialized preview。

### 4.3 用户可见确认页

最终用户确认页应展示业务语义，而不是内部结构：

```text
Create child worker

Task:
  Gather source evidence from approved connectors

Inputs:
  connectors_or_source_repositories

Output:
  source_evidence_result

Business logic:
  Retrieve source evidence from approved connectors and normalize the returned evidence for the main workflow.
```

Advanced / audit details 可以包含 ref_id、stage slice、closure plan、verification lane 等内部信息，但默认确认页不展示这些内容。

---

## 5. 四个核心字段定义

### 5.1 `child_task`

含义：child worker 的职责边界。

示例：

```text
Gather source evidence from approved connectors
```

来源优先级：

```text
1. 用户显式输入
2. worker promotion source candidate
3. issue subject summary
4. candidate task alternatives
```

要求：

```text
1. 必须有值。
2. 如果 source text 中存在多个候选任务，例如 "source gathering or template matching"，必须要求用户选择或改写。
3. 不得使用 `del_s31`、`candidate_xxx` 这类内部 ID 作为任务文本。
```

### 5.2 `child_inputs`

含义：child worker 执行该任务需要从 parent worker 接收哪些已有变量。

类型：

```text
tuple[SelectableRefId, ...] | explicit_none
```

来源：

```text
SelectableRefSet refs where ref_role == selectable_input
```

要求：

```text
1. 可选择项必须来自 SelectableRefSet。
2. API 名称、API resource、target_output、placement anchor 不得出现在输入变量候选列表中。
3. 候选列表必须按 canonical variable name 去重。
4. 系统可以推荐输入，但用户必须接受或覆盖。
5. explicit_none 只有在策略明确允许时才可用，并且必须作为显式确认。
```

推荐规则可以使用：

```text
1. source / connector / repository 相关任务优先推荐 connectors_or_source_repositories。
2. 内容生成或请求理解相关任务可推荐 user_request。
3. 有 candidate_possible_inputs 时优先匹配 candidate_possible_inputs。
4. 多个高置信候选时要求用户选择。
```

### 5.3 `child_output`

含义：child worker 返回给 parent workflow 的业务结果。

示例：

```text
source_evidence_result
```

来源：

```text
1. 用户显式输入
2. required output gap
3. candidate_possible_outputs
4. child_task / business_logic 推导出的业务名
```

要求：

```text
1. 不得使用 source span id、candidate id 或 diagnostic id 作为默认输出名。
2. 输出名必须经过 NewOutputAdmission。
3. 输出名必须稳定 canonicalize。
4. 默认展示应使用业务名，例如 source evidence result，而不是 del s31。
```

### 5.4 `child_business_logic`

含义：child worker 内部实际执行的业务逻辑，作为 Stage 7 repair slice 生成 command 的主要语义输入。

示例：

```text
Retrieve source evidence from approved connectors and normalize the returned evidence for the main workflow.
```

与 `child_task` 的区别：

```text
child_task:
  worker 的职责边界，偏标题 / purpose。

child_business_logic:
  worker 内部 command 的行为描述，偏可执行动作。
```

要求：

```text
1. 必须有值。
2. 可以由 child_task + child_inputs + child_output 生成推荐文本。
3. 用户可以覆盖。
4. Stage 7 repair slice 只能基于 confirmed business_logic、confirmed inputs、confirmed output 生成 command。
5. Drafting provider 不能直接构造 StepIR。
```

---

## 6. 后端对象模型

### 6.1 不新增并行 draft lifecycle

本设计不得新增一套独立于现有 RepairDraftingSubsystem 的 draft 生命周期。

必须继续复用现有对象：

```text
UserRepairInput
InferredRepairDraft
FieldInference
RepairFieldValue
StoredRepairDraft
DraftAdmissionBridge
```

也就是说：

```text
StoredRepairDraft 仍是唯一 draft store 对象。
DraftAdmissionBridge 仍是 draft -> directive 的唯一入口。
Child worker semantic contract 只能作为 provider-scoped projection / view。
```

禁止新增一条并行链路：

```text
ChildWorkerSemanticDraftStore
-> ChildWorkerSemanticAdmission
-> independent materialization path
```

否则会形成第二套 drafting authority，与现有 Admission / Materialization / Lane B 链路冲突。

### 6.2 `ChildWorkerSemanticDraft` 只是投影视图

建议新增 provider-scoped typed draft：

```python
@dataclass(frozen=True)
class ChildWorkerSemanticDraft:
    child_task: ConfirmableField[ResponsibilityValue]
    child_inputs: ConfirmableField[SelectedInputRefsValue | ExplicitNoneValue]
    child_output: ConfirmableField[NewOutputDraftValue]
    child_business_logic: ConfirmableField[BusinessLogicValue]
```

该对象只允许作为 `InferredRepairDraft` 的 provider-scoped semantic projection，不能成为新的 root draft state。

更推荐的落地方式是：

```text
InferredRepairDraft.fields:
  child_task: FieldInference[Confirmable ResponsibilityValue]
  child_inputs: FieldInference[Confirmable SelectedInputRefsValue | ExplicitNoneValue]
  child_output: FieldInference[Confirmable NewOutputDraftValue]
  child_business_logic: FieldInference[Confirmable BusinessLogicValue]
```

或者将确认语义包进 provider-scoped value：

```python
@dataclass(frozen=True)
class ConfirmableRepairFieldValue(Generic[T]):
    suggested_value: T | None
    confirmed_value: T | None
    confirmation_source: ConfirmationSource
```

但无论采用哪种实现，均不得绕过 `InferredRepairDraft` / `StoredRepairDraft` / `DraftAdmissionBridge`。

### 6.3 `ConfirmableField`

```python
@dataclass(frozen=True)
class ConfirmableField(Generic[T]):
    field_id: str
    suggested_value: T | None
    confirmed_value: T | None
    confirmation_source: Literal[
        "unconfirmed",
        "accepted_default",
        "user_override",
    ]
    confidence: Literal["high", "medium", "low", "blocked"]
    evidence_refs: tuple[str, ...]
    alternatives: tuple[InferenceAlternative, ...] = ()
    blocking_reason: str | None = None
```

规则：

```text
1. suggested_value 是系统生成的示例。
2. confirmed_value 是用户接受或覆盖后的值。
3. 进入 Admission 前，四个核心字段必须 confirmed。
4. confirmed_value 不能来自 free text 直接拼 patch payload，必须转成 provider-scoped typed value。
```

### 6.4 `BusinessLogicValue`

当前 `RepairFieldValue` 中还没有业务逻辑值类型，建议增加：

```python
@dataclass(frozen=True)
class BusinessLogicValue:
    provider_id: str
    text: str
```

它只作为 Stage 7 repair slice 的 typed semantic input，不是 `StepIR.text` authority。

更严格地说：

```text
BusinessLogicValue 是 user-confirmed semantic input。
BusinessLogicValue 不是 StepIR。
BusinessLogicValue 不是 patch payload。
BusinessLogicValue 不是 final rendered command 的唯一 authority。
BusinessLogicValue 必须经过 Admission / DirectiveBridge / Stage 7 repair slice validation。
```

禁止实现者直接做：

```python
StepIR(text=business_logic.text)
```

Stage 7 repair slice 只能通过 normalized WorkerDelegationDirective 消费 `BusinessLogicValue`，并必须校验：

```text
1. command inputs == confirmed child_inputs。
2. command outputs 覆盖 confirmed child_output。
3. command 不引入未声明 ref。
4. business_logic 不得绕过 capability authority 引入新的 API/tool/resource 调用。
5. command plan 仍由 Stage 7 repair slice 生成和验证。
```

---

## 7. Draft 生命周期

新的生命周期：

```text
1. create_repair_draft
   -> 生成四个字段的 suggested answers
   -> 返回 ChildWorkerSemanticDraft
   -> 不写 overlay
   -> 不生成 patch payload

2. user confirms fields
   -> 每个字段为 accepted_default 或 user_override
   -> 返回 UserRepairInput(field_values=...)

3. accept_repair_draft
   -> 校验四个核心字段已确认
   -> SelectableRefSet resolution
   -> NewOutputAdmission
   -> normalize to NormalizedWorkerDelegationDirective

4. create_materialized_preview_from_draft
   -> Stage-slice materialized preview
   -> 展示最终 worker / invoke preview

5. user confirms materialized preview
   -> apply
   -> Lane B replay
   -> verifier / ProducerIndex / DiagnosticDiff
```

注意：`create_repair_draft` 可以一次性生成四个推荐答案；终端逐项展示不意味着逐项调用 provider。

---

## 8. 与 NL2SPL Pipeline 的关系

不应完整重跑原始 NL2SPL pipeline，也不应伪造 `SpanIR` 或 `compile_hint`。

正确做法是使用 repair-mode stage slices：

```text
confirmed child worker semantic contract
-> Stage 3.5 repair slice
   materialize child worker boundary, input/output contract, handoff skeleton

-> Stage 5 repair slice
   materialize child worker block shape

-> Stage 7 repair slice
   materialize command(s) from confirmed business_logic + inputs + output

-> Stage 9.5 / Stage 10 / Stage 11
   normalize, assemble, render through Lane B
```

### 8.1 Stage 3.5 authority

Stage 3.5 repair slice 负责：

```text
1. child worker identity
2. child input contract
3. child output contract
4. handoff contract
5. parent invoke boundary
```

它不负责生成 command 行为文本。

### 8.2 Stage 5 authority

Stage 5 repair slice 负责：

```text
1. child worker block structure
2. default minimal SEQUENTIAL block
3. optional future directive-driven block shape
```

MVP 中可以固定为一个 `SEQUENTIAL_BLOCK`。

### 8.3 Stage 7 authority

Stage 7 repair slice 负责：

```text
confirmed child_business_logic
+ confirmed child_inputs
+ confirmed child_output
-> child worker command plan
-> StepIR
```

MVP 约束：

```text
1. 生成恰好一个 child command。
2. command action_text 必须来自 confirmed child_business_logic。
3. command inputs 必须来自 confirmed child_inputs。
4. command outputs 必须覆盖 confirmed child_output。
5. 不允许 LLM 额外拆分多个未确认 commands。
```

未来可在 gated design 下允许 Stage 7 repair slice 使用 constrained LLM 生成 `CommandIntentPlan`，但不能直接输出 `StepIR`。

---

## 9. CLI / Frontend Contract

### 9.1 Backend DTO

建议 `DraftPreview` 或新增 `DraftConfirmationView` 支持字段级确认：

```python
@dataclass(frozen=True)
class DraftConfirmationFieldView:
    field_id: str
    label: str
    suggested_display_value: str | None
    input_kind: Literal["text", "reference_multi_select", "reference_single_select"]
    options: tuple[DraftFieldOptionView, ...] = ()
    required: bool = True
    confidence: str = "medium"
    evidence_summary: str | None = None
```

### 9.2 CLI 行为

终端可以逐项展示：

```text
Child worker task [Gather source evidence from approved connectors]:
Inputs [connectors_or_source_repositories]:
  [1] user_request
  [2] timeframe
  [3] connectors_or_source_repositories
Select number(s), or press Enter:
Output [source_evidence_result]:
Business logic [Retrieve source evidence from approved connectors...]:
```

用户按 Enter：

```text
confirmation_source = accepted_default
```

用户输入或选择：

```text
confirmation_source = user_override
```

### 9.3 不再使用整体 “Use this draft?” 替代字段确认

可以保留最终 summary 确认，但不能只靠：

```text
Use this draft? [Y/n]
```

来隐式确认四个核心字段。

更合理的是：

```text
1. 逐项确认四个字段。
2. 展示汇总。
3. 用户确认进入 materialized preview。
```

---

## 10. Evidence / Provenance

每个 confirmed field 都必须记录：

```text
field_id
suggested_value
confirmed_value
confirmation_source
evidence_refs
confidence
trace
```

字段来源规则：

```text
accepted_default:
  证据包括原始 artifact refs + "user_confirmation:accepted_default:<field_id>"

user_override:
  证据包括 "user_input:<field_id>"

reference selection:
  证据包括 SelectableRefSet ref_id + "user_input:<field_id>"
```

这些 evidence 进入 `RepairEvidencePacket`，但不得伪装成 source span。

---

## 11. 失败与阻断规则

以下情况必须 blocked，不能进入 materialized preview：

```text
1. child_task 未确认。
2. child_inputs 未确认，且没有合法 explicit_none。
3. child_output 未确认。
4. child_business_logic 未确认。
5. 用户选择了不属于 SelectableRefSet 的 input ref。
6. 用户输入的 output name 无法通过 NewOutputAdmission。
7. business_logic 与 child_task 明显冲突。
8. confirmed input/output 无法被 Stage 7 command plan 覆盖。
```

以下情况不能通过 silent fallback 处理：

```text
1. input ref 不合法时自动改回 user_request。
2. output name 不合法时自动改回 del_s31。
3. business_logic 缺失时直接使用 issue title。
4. Stage 7 生成 command 时忽略 confirmed inputs / output。
```

---

## 12. 与当前实现的差异

当前实现：

```text
free text / Enter
-> provider 推断所有字段
-> 展示整体 draft
-> 用户整体确认
```

目标实现：

```text
选择 define_child_worker
-> provider 一次性生成四个字段的 suggested answers
-> 用户逐项接受或覆盖
-> confirmed semantic contract
-> Admission / DirectiveBridge
-> Stage 3.5 / Stage 5 / Stage 7 repair slices
-> materialized preview
-> Lane B verification
```

当前实现中已经自动推断了部分字段，例如 input/output/placement/result binding。后续应调整为：

```text
input/output/business_logic/task:
  作为用户必须确认的 semantic fields

placement/result binding/handoff/invoke:
  作为系统推断的 technical fields
```

---

## 13. MVP 范围建议

MVP 只改 `define_child_worker`。

MVP 包含：

```text
1. 四个核心字段的 suggested answer 生成。
2. CLI 逐项确认。
3. accepted_default / user_override 记录。
4. input ref 从 SelectableRefSet 候选中选择。
5. output 走 NewOutputAdmission。
6. business_logic 进入 Stage 7 repair slice command generation。
7. 不再暴露 del_s31 / parent-local temporary 等内部文案。
8. Lane B E2E accepted。
```

MVP 不包含：

```text
1. production LLM 生成复杂多步 child workflow。
2. 多 command child worker。
3. 条件 block / loop block。
4. 新增 parent required output。
5. 迁移 missing_handler / missing_output_producer 到同一字段确认模式。
```

---

## 14. 验收标准

### 14.1 UX 验收

真实 `run_demo.py` 中，选择 `Define this work as a child worker` 后，应立即出现四个字段确认：

```text
Child worker task
Inputs
Output
Business logic
```

用户可直接回车接受示例，也可覆盖。

### 14.2 Draft 验收

`InferredRepairDraft` 必须包含：

```text
child_task confirmed
child_inputs confirmed
child_output confirmed
child_business_logic confirmed
```

每个字段必须有：

```text
confidence
evidence_refs
confirmation_source
trace
```

### 14.3 Authority 验收

Drafting 层不得：

```text
1. 构造 StepIR / WorkerIR / WorkerHandoffIR。
2. 构造 patch payload。
3. 写 overlay。
4. suppress diagnostics。
5. 跳过 SelectableRefSet / NewOutputAdmission。
```

### 14.4 Stage 验收

Stage 7 child command 必须：

```text
1. 使用 confirmed child_business_logic。
2. 使用 confirmed child_inputs。
3. 产出 confirmed child_output。
4. 不使用未确认字段。
```

### 14.5 E2E 验收

真实 demo 至少覆盖：

```text
1. 用户全部接受默认示例 -> Lane B accepted。
2. 用户覆盖 input variable -> Lane B accepted。
3. 用户覆盖 output name -> Lane B accepted。
4. 用户覆盖 business logic -> final SPL child command 使用覆盖后的业务逻辑。
5. 缺任一核心字段 -> blocked，无 overlay。
6. 非法 input ref -> rejected，无 overlay。
```

---

## 15. 最终判断

该设计不是回退到旧的复杂结构化表单，而是在 draft-first 基础上增加必要的字段级确认。

正确产品形态是：

```text
系统生成示例，用户确认语义；
系统推断技术结构，compiler 验证结果。
```

对于 `Define this work as a child worker`，四个核心字段必须由用户接受或覆盖：

```text
1. 子任务是什么
2. 输入是什么
3. 输出是什么
4. 业务逻辑是什么
```

而 worker / handoff / invoke / placement / result binding 的具体 SPL construct 生成，应继续由 repair-mode Stage 3.5、Stage 5、Stage 7 和 Lane B compiler authority 负责。

---

## 16. 评审修订与收口

本节吸收 conditional-pass 评审意见，作为实施前必须遵守的修订边界。

### 16.1 该方案是 WDI 交互 contract 修订，不是新平台

本设计必须嵌入现有链路：

```text
RepairDraftingSubsystem
-> WorkerDelegationInferenceProvider
-> StoredRepairDraft
-> DraftAdmissionBridge
-> NormalizedWorkerDelegationDirective
-> Worker Delegation v2 materialization
-> Lane B verification
```

它不是新增并行链路：

```text
new semantic draft root
-> new semantic admission
-> new materialization path
```

实施时不得新增第二套 draft store、第二套 directive bridge 或第二套 worker delegation apply authority。

### 16.2 Confirmable fields 必须集成到现有 draft model

四个核心字段的确认语义应落入现有 `InferredRepairDraft.fields`。

推荐模型：

```text
child_task:
  FieldInference[Confirmable ResponsibilityValue]

child_inputs:
  FieldInference[Confirmable SelectedInputRefsValue | ExplicitNoneValue]

child_output:
  FieldInference[Confirmable NewOutputDraftValue]

child_business_logic:
  FieldInference[Confirmable BusinessLogicValue]
```

或者将确认语义封装为 provider-scoped `RepairFieldValue`：

```python
@dataclass(frozen=True)
class ConfirmableRepairFieldValue(Generic[T]):
    suggested_value: T | None
    confirmed_value: T | None
    confirmation_source: Literal[
        "unconfirmed",
        "accepted_default",
        "user_override",
    ]
```

但 `StoredRepairDraft` 仍然是唯一持久化 draft 对象。

### 16.3 `BusinessLogicValue` 不能成为 StepIR 后门

`BusinessLogicValue` 只是用户确认过的语义输入，不是 `StepIR`，也不是 patch payload。

禁止：

```python
StepIR(text=business_logic.text)
```

Stage 7 repair slice 只能通过 normalized directive 消费 business logic，并必须验证：

```text
1. command inputs == confirmed child_inputs。
2. command outputs 覆盖 confirmed child_output。
3. command 不引入未声明 ref。
4. command 不引入未 admission 的 API/tool/resource。
5. command plan 仍由 Stage 7 repair slice 生成和验证。
```

如果未来要用 LLM 从 business logic 生成更复杂 command plan，必须经过 Bounded LLM Gate；LLM 输出也只能是 slice-local typed plan，不能是 IR。

### 16.4 允许显式 Accept All，但必须字段级记录

不要求终端或前端强制用户完成四次输入。

允许：

```text
显示四个 semantic fields
-> 用户选择 Accept all suggested semantic fields
-> 后端逐字段记录 confirmation_source=accepted_default
```

不允许：

```text
只显示泛化的 Use this draft?
-> 用户按 Y
-> 后端隐式确认四个隐藏字段
```

Accept-all 只能确认已可见的 semantic fields，不得确认隐藏技术字段：

```text
placement
handoff
invoke
binding mechanics
worker_id / step_id / block_id
verification lane
```

### 16.5 `child_inputs` 展示 label，提交 ref id

用户界面不得展示 raw `SelectableRefId` 作为主要选项文本。

展示层应使用：

```text
display label
business description
canonical variable name
scope hint
```

提交层必须使用：

```text
SelectableRefId
```

因此：

```text
UI text:
  connectors_or_source_repositories
  Available connectors or source repositories for retrieving evidence.

Submitted value:
  selectable_ref_id
```

不得把 display string 当作 authority。

### 16.6 `child_output` 区分 display / canonical / admitted id

输出字段必须区分三个层次：

```text
display_name:
  用户可见文本，例如 "source evidence result"

proposed_canonical_name:
  draft 阶段建议的 canonical name，例如 "source_evidence_result"

admitted_output_id:
  NewOutputAdmission 后才产生的 stable output id
```

Draft 阶段不能承诺 `admitted_output_id`。Materialized preview 才能展示 admission 后的最终绑定结果。

### 16.7 business logic 冲突规则必须 deterministic

MVP 不允许引入自由语义冲突判断。

可阻断规则限定为：

```text
1. business_logic 为空或过短。
2. business_logic 引用了未确认 input/output 名。
3. business_logic 明确要求不同 output，但 child_output 不匹配。
4. business_logic 引入 API/tool/resource，但该 capability 未被 admission。
5. business_logic 包含 raw candidate/source/diagnostic id 并把它当作业务对象。
```

复杂语义冲突，例如：

```text
child_task = source gathering
business_logic = template matching
```

MVP 应进入 clarification，不做自动裁决。若未来需要 LLM 判断，必须进入 Bounded LLM Gate。

### 16.8 对 WDI 实施计划的影响

本设计应修订 WDI 专项计划，而不是新开一条实施路线。

建议映射：

```text
WDI2 Responsibility Inference
  输出 child_task confirmable field。

WDI3 Input Ref Inference
  输出 child_inputs confirmable field。

WDI4 Output / Result Binding Inference
  输出 child_output confirmable field。
  result_binding 仍是 technical inferred field，不作为普通用户必确认字段。

新增 WDI4.5 Business Logic Inference
  输出 child_business_logic confirmable field。

WDI5 Placement Inference
  保持 technical inference，不进入普通用户必确认字段。

WDI6 Draft Preview UX
  改为 DraftConfirmationView + visible-field accept-all + summary confirmation。

WDI7 Negative Matrix
  增加未确认四字段、非法 input override、invalid output admission、
  business_logic undeclared ref、accept-all 字段级 evidence 等负例。
```

### 16.9 最终收口判断

修订后，本设计的定位是：

```text
Product / UX direction: pass
Semantic safety improvement: pass
Architecture integration: pass after this section
Implementation readiness: pass after WDI plan update
```

实施前必须先更新 WDI implementation plan 和 PM review criteria，使其与本节边界一致。
