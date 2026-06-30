# SPL Editing Worker Delegation Repair Interaction 与 Construct Closure 实施计划

本文档严格基于
[`spl_editing_worker_delegation_repair_interaction_and_closure_design_zh.md`](spl_editing_worker_delegation_repair_interaction_and_closure_design_zh.md)
制定。

实施目标是把 `WORKER_PROMOTION` repair 从 patch-type-driven、free-text-only 流程迁移为：

```text
source-backed issue subject
-> stable RepairStrategyOptionSpec
-> backend-owned dynamic RepairInteractionView
-> typed RepairDirectiveDraft validation/normalization
-> admitted new facts
-> construct closure preview
-> user confirmation
-> Lane B apply/replay
```

本计划只完成 Worker Delegation 垂直闭环。Interaction contract 基础设施必须可扩展，但本轮
不迁移 missing handler、missing output producer 或 API deferred-validation 的输入体验；这些
路径只做回归保护。

---

## 1. 最终职责链路

```text
WORKER_PROMOTION SlotSpec.repair_affordances
  -> declares approved repair_strategy_id only

RepairStrategyRegistry
  -> RepairStrategySpec
  -> RepairStrategyOptionSpec
  -> owns user-visible option semantics

RepairCatalog + runtime capability resolver
  -> owns option availability

IssueSubjectResolver
  -> projects source-backed delegated task/candidate facts

RepairInteractionContractRegistry + dynamic provider
  -> owns input shape and input readiness
  -> does not own capability

Directive parser / validator / normalizer
  -> validates typed user input, selected refs, revision, and constraints

NewFactAdmissionService
  -> admits new child outputs and stable provisional identities

ConstructClosurePlanner + MaterializationPlan
  -> selects stage-slice chain and Lane B write scope

Repair-mode stage slices
  -> materialize worker boundary, flow, block, command, handoff, invoke, binding

Preview seal / confirmation / evidence
  -> guarantees preview/apply identity

VerificationRunner
  -> Lane B normalizer, assembly, Gate, IRS, provenance, Renderer acceptance

CLI / UI
  -> renders backend DTOs only
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. IRS 只声明 missing slot 和 approved affordance，不执行 repair。
2. `repair_strategy_id` 是 construct-level repair 语义来源。
3. `RepairStrategyOptionSpec` 是用户可选结果的语义来源。
4. Patch type 仅是 transitional execution adapter，不能决定 UI 文案、表单或 closure。
5. RepairCatalog/runtime capability 决定 availability；interaction provider 不得改变它。
6. `RepairInputReadiness` 与 availability 正交；`can_fix` 仅取决于 available option。
7. CLI/UI 不根据 issue kind、construct type、slot name 或 patch type推断输入 UI。
8. Existing refs 只能来自当前 snapshot 的 `SelectableRefSet`。
9. 新 child output 只能通过 typed admission 进入状态。
10. Wire JSON 必须在 transport boundary 转为 typed domain objects。
11. `additional_instruction` 不能补必填字段、改 refs、新建 symbol、改 option 或弱化验证。
12. LLM 不得输出 IR、raw refs、新 symbols、option availability 或 verification lane。
13. Preview 不持久化 accepted overlay；confirmation 后才创建 `RepairEvidencePacket`。
14. Preview/apply 必须使用相同 normalized directive、admitted facts 和 typed plans。
15. Worker Delegation 两条路径全部使用 Lane B。
16. `ConvertDelegationIntentToRequestInput` 只从 WORKER_PROMOTION affordance 移除，不全局删除。
17. v2 runtime 未闭合前，`define_child_worker` 不得显示为 available。
18. 不允许为了复用完整 Pipeline stage 伪造 SpanIR、FieldRouteIR 或 compile hints。
19. 不允许新增基于 diagnostic message、feedback text 或 rendered SPL 的 semantic fallback。
20. 每个阶段只在其验收通过后进入下一阶段，不允许最后一次性补测试。

---

## 3. LLM 与确定性逻辑边界

### 3.1 MVP 默认

本轮不新增用于决定 Worker closure 的通用 LLM fallback。

允许的确定性行为：

```text
读取 source-backed candidate/task facts
解析 stable IDs
校验 required fields 和 ref roles
规范化用户确认的责任描述
分配 deterministic provisional IDs
从 admitted outputs 建立 typed contract/binding
按冻结的最小 policy 生成一个 child command
执行 stage-local typed plan validation
```

### 3.2 Stage slice 可调用 LLM 的条件

若实现确实需要 LLM，只允许返回已冻结的 slice-local typed plan，并必须满足：

```text
输入仅来自 NormalizedRepairDirective + resolved refs + admitted facts；
输出不包含 IR；
输出不新增 commands、refs、outputs 或 placement；
typed plan validator 能确定性证明与 directive 一致；
preview 记录 generation config 和 typed plan hash。
```

不满足以上条件时，停止实施并回到设计评审，不允许加入 fallback。

---

## 4. Contract Freeze（实施前置）

以下决定在编码前冻结，不再由阶段实现者自行选择。

### 4.1 稳定标识

```text
strategy_id:
  worker_delegation.complete_closure.v2

option_id:
  define_child_worker
  keep_in_main_flow

interaction contracts:
  worker_delegation.define_child_worker.v1
  worker_delegation.keep_in_main_flow.v1

fact schemas:
  worker_delegation.new_child_output.v1
  worker_delegation.result_usage.v1

transitional adapter:
  DefineChildWorkerClosure
```

### 4.2 MVP typed plans

```text
DefineChildWorkerBoundaryPlan
  worker_id, worker_name, purpose, input_contract, output_contract

ChildWorkerFlowPlan
  flow_id, responsibility

ChildWorkerBlockPlan
  block_id, block_type=sequential, flow_ref

ChildWorkerCommandPlan
  action_text, input_ref_ids, admitted_output_ids

WorkerHandoffBindingPlan
  parent_worker_id, child_worker_id, input_bindings, output_bindings

ParentInvokePlan
  placement_mode, placement_anchor_ref, handoff_id

KeepInMainFlowPlan
  selected_task_boundary, action_text, placement_mode, placement_anchor_ref
```

所有 plan 都是 frozen typed DTO；禁止 raw `dict[str, Any]`。

### 4.3 MVP 功能范围

```text
side_effect_only:
  不支持。Child worker 必须至少声明一个 admitted output。

invocation flow:
  仅 main flow。

placement mode:
  append | before | after。
  before/after 必须引用 SelectableRefSet 中的 main-flow placement anchor。

parent result usage:
  绑定已有 parent scope ref；或
  绑定由 materializer 创建的 parent-local temporary result。

parent required output:
  本轮禁止新增。

child command:
  恰好一个 responsibility-backed command；
  outputs 覆盖全部 admitted child outputs；
  不自动扩写多步骤流程。
```

### 4.4 稳定 ID

Preview/apply ID 分配统一使用：

```text
base_snapshot_id
+ normalized_directive_id
+ closure_node_role
+ local declaration id / ordinal
```

要求：

```text
不依赖 overlay_version 作为唯一来源；
同一 preview/apply 输入产生相同 ID；
与已有 artifact 冲突时 fail-fast，不静默改名；
apply 不重新分配 preview 已使用的 ID。
```

### 4.5 v1/v2 暴露策略

```text
P0 先收紧 legacy affordance，仅保留可真实执行的 keep-main-flow。
P1-P8 在非用户暴露状态构建 v2。
P9 在所有 runtime closure 和 E2E 通过后原子切换到 v2。
不得同时向用户暴露 legacy 三选项和 v2 两选项。
```

### 4.6 Contract Freeze 验收

- 上述常量在文档和测试 fixture 中只有一个 canonical 定义。
- 实施者没有未决的 patch 名称、plan schema、lane 或 MVP empty policy。
- PM 确认本轮不支持 side-effect-only、alternative/exception invocation 或新增 parent output。

---

## 5. 阶段总览与依赖

| 阶段 | 目标 | 依赖 |
|---|---|---|
| P0 | Characterization + capability false-positive guard | Contract Freeze |
| P1 | Strategy option model、catalog projection、stable option ID | P0 |
| P2 | IssueSubjectView 与 Worker candidate projection | P1 |
| P3 | Interaction DTO、schema、dynamic provider | P1-P2 |
| P4 | DirectiveDraft validation / normalization | P3 |
| P5 | New child output admission | P4 |
| P6 | KeepInMainFlowClosure Lane B 垂直闭环 | P4 |
| P7 | DefineChildWorkerClosure 分阶段 materialization | P4-P5 |
| P8 | Preview seal、apply consistency、generic verification | P6-P7 |
| P9 | Service/CLI migration、IRS v2 原子切换、E2E、cleanup | P8 |

P6 与 P5 可在 P4 后并行，但 P7 必须等待 P5。

---

## 6. P0：Characterization 与 Capability Exposure Guard

### 6.1 目标

先锁定并消除当前产品级假阳性：不存在 concrete child worker、且完整
`DefineChildWorkerClosure` runtime 未注册时，不能把 handoff-only option 显示为 available。

### 6.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/spl_editing/strategy/defaults.py
src/nl2spl/compiler/spl_editing/presentation/resolvers/repair_options.py
src/nl2spl/compiler/spl_editing/presentation/templates/repair_option_copy.py
tests/unit/compiler/spl_editing/
tests/unit/compiler/spl_editing/presentation/
```

### 6.3 实施思路

#### P0.1 Characterization

新增最终目标导向测试，锁定：

```text
legacy WORKER_PROMOTION 当前含三个 patch adapters；
main-flow metadata 当前错误声明 Lane A；
no-child snapshot 当前可能显示 CreateWorkerHandoffContract available；
option selection 当前依赖 index；
REQUEST_INPUT adapter 当前由 WORKER_PROMOTION 暴露。
```

这些测试应验证最终期望，不长期保留“旧行为必须存在”的断言。

#### P0.2 Immediate safe registry state

在 v2 runtime 完整前，将 `worker_promotion.resolve_contract` 临时收紧为：

```text
supported_patch_types:
  ConvertDelegationIntentToMainFlowStep

default_patch_type:
  ConvertDelegationIntentToMainFlowStep

verification_lane:
  B
```

从该 affordance 临时移除：

```text
CreateWorkerHandoffContract
ConvertDelegationIntentToRequestInput
```

注意：

```text
CreateWorkerHandoffContract 仍可由已有 CHILD_WORKER/WORKER_HANDOFF 的合法 affordance 使用；
ConvertDelegationIntentToRequestInput 不从全局 registry 删除。
```

#### P0.3 Invariant tests

```text
current no-child issue has no false available handoff option；
keep-main-flow remains available when Lane B capabilities exist；
can_fix remains true because one valid option exists；
Lane A metadata is absent for Worker Promotion options。
```

P0 修改 IRS affordance 后立即运行：

```powershell
python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py `
  --construct WORKER_PROMOTION --scope all --format json
```

### 6.4 验收标准

- 当前 demo 不再展示不可执行的 handoff-only option。
- 当前 demo 不再展示 `Ask user for missing information`。
- `ConvertDelegationIntentToRequestInput` 其他合法注册不受影响。
- WORKER_PROMOTION main-flow repair 使用 Lane B。
- 现有 missing handler / missing output producer 回归通过。
- P0-P8 期间 `define_child_worker` 不出现在普通用户 option list；Advanced/audit 可以显示
  `v2_pending`，但任何 service API 都不得接受其 draft、preview 或 apply 请求。

### 6.5 PM 审核清单

- [ ] 不是通过 CLI 过滤隐藏 option。
- [ ] 不是通过 diagnostic kind 手写 availability。
- [ ] 没有全局删除 REQUEST_INPUT adapter。
- [ ] 没有提前暴露 v2 define-child。

---

## 7. P1：Strategy Option 与 Catalog/Presentation Identity

### 7.1 目标

建立 `RepairStrategyOptionSpec`，使 option 成为 strategy 下的稳定语义对象，并让
RepairCatalog/Presentation 使用 `option_id`，不再把 patch metadata 当作用户语义来源。

### 7.2 可编辑范围

```text
src/nl2spl/compiler/spl_editing/strategy/model.py
src/nl2spl/compiler/spl_editing/strategy/registry.py
src/nl2spl/compiler/spl_editing/strategy/defaults.py
src/nl2spl/compiler/spl_editing/strategy/catalog_projection.py
src/nl2spl/compiler/spl_editing/core/catalog.py
src/nl2spl/compiler/spl_editing/presentation/model/issue.py
src/nl2spl/compiler/spl_editing/presentation/resolvers/repair_options.py
src/nl2spl/compiler/spl_editing/presentation/templates/repair_option_copy.py
tests/unit/compiler/spl_editing/construct_strategy/
tests/unit/compiler/spl_editing/presentation/
```

### 7.3 实施思路

#### P1.1 Model

新增 frozen `RepairStrategyOptionSpec`，包含：

```text
option_id
strategy_id
label_key
description_key
interaction_contract_id
execution_patch_types
closure_policy_id
user_facing
```

Model 校验：

```text
option_id 在 strategy 内唯一；
strategy_id 反向匹配 owner；
execution_patch_types 是 strategy supported adapters 的子集；
contract/closure IDs 非空；
option 不包含 runtime availability 或 form fields。
```

#### P1.2 Strategy v2 registration

注册 `worker_delegation.complete_closure.v2` 和两个 option，但保持非用户暴露/不可用，直到
P9 原子切换。

#### P1.3 Catalog projection

RepairCatalogEntry 增加 strategy option linkage。Catalog 仍从 IRS affordance 派生 capability
入口，但 option labels/interaction IDs 从 strategy registry 投影。

禁止新增手写：

```text
diagnostic kind -> options mapping
patch type -> form mapping
```

#### P1.4 Presentation identity

扩展 `RepairOptionView`：

```text
option_id
strategy_id
interaction_summary
```

保留 `patch_types` 仅供 transitional apply/Advanced Details。UI API 不再接受 option index 作为
identity。

### 7.4 测试计划

```text
strategy option uniqueness
invalid execution adapter rejected
catalog option projection
patch metadata cannot override option label
stable option_id across localization/order changes
can_fix invariant unchanged
v2 define-child remains unavailable before runtime registration
```

### 7.5 验收标准

- `RepairStrategyOptionSpec` 是用户选项唯一语义来源。
- v2 精确包含 `define_child_worker`、`keep_in_main_flow`。
- Presentation DTO 携带稳定 option ID。
- 旧 patch metadata label 不再影响 v2。

### 7.6 PM 审核清单

- [ ] Strategy registry 没有 import UI/CLI。
- [ ] Input contract 没有决定 capability。
- [ ] Option spec 没有 applier/verifier object。
- [ ] v2 尚未对真实用户开放。

---

## 8. P2：IssueSubjectView 与 Delegated Task Projection

### 8.1 目标

让 issue list/detail 明确展示 source-backed delegated responsibility，并区分 concrete worker、
candidate、ambiguous 和 degraded，不暴露 compiler ID。

### 8.2 可编辑范围

```text
src/nl2spl/compiler/spl_editing/presentation/model/subject.py        # new
src/nl2spl/compiler/spl_editing/presentation/resolvers/issue_subject.py  # new
src/nl2spl/compiler/spl_editing/presentation/resolvers/display_context.py
src/nl2spl/compiler/spl_editing/presentation/issue_presenters/worker_delegation.py
src/nl2spl/compiler/spl_editing/presentation/templates/issue_copy.py
src/nl2spl/compiler/spl_editing/presentation/ai_explainer.py
tests/unit/compiler/spl_editing/presentation/
```

### 8.3 实施思路

#### P2.1 Subject resolver

按以下优先级读取结构化 facts：

```text
existing WorkerPlanIR child identity/purpose
worker candidate task summary
TargetResolverResult / RepairContext structured metadata
source span excerpt
generic degraded subject
```

不得解析 diagnostic message 或 AI explanation。

#### P2.2 Current demo projection

`worker_promotion:del_s31` 应投影：

```text
subject_kind = delegated_task_candidate
specificity = ambiguous
summary = source gathering or template matching
source_ref_ids = (s31,)
```

`del_s31` 只进入 Advanced Details。

#### P2.3 Presenter / AI boundary

Worker presenter 使用 `IssueSubjectView` 构造 deterministic title/detail。AI explainer 只能消费
subject DTO，不得重新推断 target identity。

### 8.4 测试计划

```text
concrete child worker title
ambiguous candidate title
source excerpt fallback
degraded generic title
compiler ID hidden
diagnostic.message not parsed
AI explanation receives subject facts
```

### 8.5 验收标准

- Demo 用户能看懂具体候选任务。
- 无 concrete worker 时不虚构 Worker。
- 无结构化 facts 时安全 degraded。
- CLI/UI 不拼 target 文案。

### 8.6 PM 审核清单

- [ ] Subject 来自 structured artifacts/source spans，不来自 diagnostic message。
- [ ] Candidate 没有被错误显示为 concrete Worker。
- [ ] Internal IDs 只在 Advanced Details。

---

## 9. P3：Interaction DTO、Schema Registry 与 Dynamic Provider

### 9.1 目标

建立 backend-owned interaction contract，并根据当前 target facts 动态返回字段、options 和
input readiness。

### 9.2 可编辑范围

```text
src/nl2spl/compiler/spl_editing/interaction/                    # new
  __init__.py
  model.py
  registry.py
  errors.py
  defaults.py
  providers/worker_delegation.py

src/nl2spl/compiler/spl_editing/presentation/model/interaction.py  # new
src/nl2spl/compiler/spl_editing/presentation/resolvers/repair_interaction.py  # new
src/nl2spl/compiler/spl_editing/presentation/service.py
tests/unit/compiler/spl_editing/interaction/
tests/unit/compiler/spl_editing/presentation/
```

### 9.3 实施思路

#### P3.1 Models

实现设计文档中的：

```text
RepairInputReadiness（含 not_evaluated）
RepairInteractionView
RepairInputFieldView
RepairInputOptionView
RepairInputSchemaView
RepairInputValidationError
RepairInteractionContractSpec
```

Schema invariants：

```text
structured_object -> object_schema_id 必填；
new_fact_list -> fact_schema_id 必填；
所有 schema refs 在同一 view 中恰好解析一次；
schema 有限、无环、版本化；
contract 不包含 capability/lane/patch handler。
```

#### P3.2 Define-child provider

返回 `structured_with_notes`，包含 responsibility、input refs、returned results、main-flow
placement、result usage 和 optional additional instruction。

#### P3.3 Keep-main provider

```text
concrete task -> natural_language + not_required
ambiguous task -> structured_with_notes + input_required
```

当前 demo 返回 source gathering/template matching/both 的 source-backed choices。

#### P3.4 Capability/readiness separation

Service 先解析 option availability：

```text
unavailable -> readiness=not_evaluated；不返回 actionable field values；
available -> provider 计算 input readiness。
```

Provider 不得把 unavailable 改成 available。

### 9.4 Service API

新增：

```python
get_repair_interaction(
    run_id,
    issue_id,
    option_id,
    revision_token,
) -> RepairInteractionView
```

### 9.5 测试计划

```text
schema invariants
unknown contract/provider rejected
unavailable -> not_evaluated
ambiguous/concrete dynamic forms
stable option ID lookup
stale revision rejection
no session/suggestion created by GET interaction
```

### 9.6 验收标准

- 前端无需知道 Worker Promotion 类型即可渲染表单。
- Dynamic provider 只投影输入，不决定 capability。
- 无 raw runtime object 进入 DTO。
- Contract/schema round-trip 稳定。

### 9.7 PM 审核清单

- [ ] Provider 没有注册或隐藏 repair options。
- [ ] Unavailable option 不返回可提交的 actionable form。
- [ ] 前端渲染所需 schema 全部由 DTO 提供。

---

## 10. P4：RepairDirectiveDraft Validation 与 Normalization

### 10.1 目标

把 wire JSON 转成 typed Worker Delegation draft，完成 revision、required fields、refs、empty
semantics、additional instruction 边界校验，并输出 sealed normalized directive。

### 10.2 可编辑范围

```text
src/nl2spl/compiler/spl_editing/interaction/model.py
src/nl2spl/compiler/spl_editing/interaction/validation/worker_delegation.py
src/nl2spl/compiler/spl_editing/interaction/normalization/worker_delegation.py
src/nl2spl/compiler/spl_editing/interaction/store.py
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/presentation/service.py
tests/unit/compiler/spl_editing/interaction/
```

### 10.3 实施思路

#### P4.1 Transport/domain split

Transport request 可以使用 JSON mapping，但 parser 必须立即生成：

```text
WorkerDelegationDirectiveDraft
DelegatedResponsibilityDraft
InvocationTimingDraft
ResultUsageDraft
NewOutputDeclarationDraft
```

Normalizer、closure planner、materializer 禁止接收通用 mapping。

#### P4.2 Validation pipeline

严格按设计顺序执行：

```text
identity/revision
-> availability
-> contract id/version
-> typed parse
-> required fields
-> SelectableRefSet roles
-> empty policy
-> new fact shape（admission 在 P5）
-> result usage coherence
-> additional instruction boundary
```

#### P4.3 Additional instruction

Additional instruction 不进入 required-field calculation，也不能修改 normalized fields。任何
deterministically detectable conflict 返回 `input_invalid`。后续 typed plan 与 directive 不一致
时同样拒绝。

#### P4.4 Normalized directive store

Store 以 `directive_id + base revision + contract hash` 为 identity。对象 immutable；修改输入
必须生成新 directive ID。

### 10.4 API

```python
submit_repair_directive_draft(request) -> RepairDirectiveValidationResult
```

### 10.5 测试计划

```text
all error codes
unknown option/contract/version
invalid/stale revision
invalid ref/role
additional instruction cannot satisfy fields
typed domain object boundary
input_required / complete / invalid transitions
immutable store behavior
```

### 10.6 验收标准

- Input incomplete 时无 suggestion、preview、session、overlay。
- Normalized directive 不含 user-selectable lane/patch type。
- Verification lane 只读派生为 B。
- Free text 不能绕过 structured fields。

### 10.7 PM 审核清单

- [ ] Wire mapping 未泄漏到 domain/materialization。
- [ ] Revision、contract version 和 ref roles 均 fail-fast。
- [ ] Normalized directive 是 immutable sealed object。

---

## 11. P5：New Child Output Admission

### 11.1 目标

允许用户声明新的 child outputs，并把它们安全转换为 stable、typed、evidence-linked admitted
facts；不允许同一 repair 新增 parent required output。

### 11.2 可编辑范围

```text
src/nl2spl/compiler/spl_editing/admission/                 # new
  __init__.py
  model.py
  registry.py
  output_declaration.py
  errors.py
src/nl2spl/compiler/spl_editing/materialization/id_allocator.py
src/nl2spl/compiler/spl_editing/interaction/normalization/worker_delegation.py
src/nl2spl/ir/symbol_table.py
src/nl2spl/compiler/producer_index.py                              # only if boundary tests expose a defect
src/nl2spl/pipeline/stages/stage11_spl_renderer/                  # only if boundary tests expose a defect
tests/unit/compiler/spl_editing/admission/
```

### 11.3 实施思路

#### P5.1 Output admission

实现：

```text
name normalization
reserved-name validation
child scope symbol conflict check
data type admissibility
stable provisional output ID
evidence/provenance link
```

名称冲突 fail-fast，不自动改名。

#### P5.2 Parent result usage

MVP 只允许：

```text
bind existing parent ref；
或创建 parent-local temporary result。
```

Temporary result：

```text
scope = parent worker local
origin = user_confirmed_repair after apply
identity inputs = directive_id + admitted output local_id
not a required output
not exported globally
```

它必须进入 parent worker-local SymbolTable/binding scope 和 provenance，但不得：

```text
创建 REQUIRED_OUTPUT instance；
进入全局 output contract；
被 Renderer 输出为 [OUTPUTS] declaration；
触发 missing_output_producer；
被 ProducerIndex 当成 required-output producer demand。
```

ProducerIndex 可以把产生该 temporary result 的 handoff/step 记录为普通 local producer，但
不得提升为 required output authority。

#### P5.3 Preview/apply stability

Admission result在 preview 前 sealed。Apply 只能 promote，不重新 canonicalize 或重新分配 ID。

### 11.4 测试计划

```text
valid output admission
reserved/conflicting name
unsupported type
stable IDs
preview/apply same identity
parent temporary result scope
temporary result appears in parent worker-local SymbolTable only
temporary result is absent from REQUIRED_OUTPUT inventory and rendered [OUTPUTS]
temporary result does not trigger missing_output_producer
temporary result provenance becomes user_confirmed_repair after apply
new parent required output rejected
evidence linkage
```

### 11.5 验收标准

- Materializer 不接收 raw output names。
- 所有 child outputs 有 admitted identity。
- SelectableRefSet 没有被滥用于新事实。
- Parent required output 不在本轮隐式创建。

### 11.6 PM 审核清单

- [ ] New facts 没有伪装成 SelectableRef。
- [ ] Preview/apply 复用同一 admitted identity。
- [ ] 名称冲突没有静默重命名。

---

## 12. P6：KeepInMainFlowClosure Lane B 垂直闭环

### 12.1 目标

先迁移较小的 `keep_in_main_flow` 路径，验证 option ID、dynamic interaction、normalized
directive、preview 和 Lane B apply/replay 的完整链路。

### 12.2 可编辑范围

```text
src/nl2spl/compiler/spl_editing/closure/model.py
src/nl2spl/compiler/spl_editing/closure/planner.py
src/nl2spl/compiler/spl_editing/closure/defaults.py
src/nl2spl/compiler/spl_editing/resolution/model.py              # new
src/nl2spl/compiler/spl_editing/resolution/store.py              # new
src/nl2spl/compiler/spl_editing/core/revision.py
src/nl2spl/compiler/artifacts/snapshot/model/editing_history.py
src/nl2spl/compiler/artifacts/snapshot/serialization/
src/nl2spl/compiler/spl_editing/stage_slices/stage5/
src/nl2spl/compiler/spl_editing/stage_slices/stage7/delegation_resolution.py
src/nl2spl/compiler/spl_editing/materialization/worker_handoff/contract.py
src/nl2spl/compiler/spl_editing/verification/
tests/unit/compiler/spl_editing/construct_strategy/
tests/integration/compiler/spl_editing/
```

### 12.3 实施思路

#### P6.1 Closure plan

```text
resolve selected task boundary
ensure/bind main-flow placement block when required
materialize exactly one GENERAL_COMMAND
record promotion resolution as main-flow work
```

#### P6.1A PromotionResolutionMarker

新增 first-class typed artifact：

```python
@dataclass(frozen=True)
class PromotionResolutionMarker:
    marker_id: str
    target_worker_promotion_id: str
    resolved_diagnostic_group_id: str
    resolution_kind: Literal["kept_in_main_flow", "defined_child_worker"]
    normalized_directive_id: str
    materialized_construct_refs: tuple[str, ...]
    evidence_ref: str
```

存储与传播要求：

```text
MaterializationResult 显式返回 resolution_markers；
marker 持久化到 typed snapshot editing/overlay payload，并支持 serializer round-trip；
materialized command/worker/handoff metadata 记录 marker_id；
replay context 以 promotion target + diagnostic group 建立 marker index；
marker 只能在 user confirmation 后成为 accepted artifact；
preview marker 只能是 provisional，不能抑制 diagnostics。
```

IRS/verification 消费规则：

```text
marker target 必须精确匹配 WORKER_PROMOTION instance；
diagnostic group 必须精确匹配，不得按 diagnostic kind 全局 suppress；
materialized_construct_refs 必须真实存在；
对应 keep-main/define-child closure-specific verifier 必须通过；
evidence_ref 必须指向当前 confirmed patch；
满足以上条件后，原 promotion group 才可被判定 resolved。
```

#### P6.2 Stage slices

- Stage 5 只处理 placement block/anchor。
- Stage 7 从 normalized responsibility 生成一个 command。
- Command refs 只能来自 resolved refs。
- 不生成 REQUEST_INPUT、handoff 或 child worker。

#### P6.3 Lane B

Materialization 写 pre-normalize block/step artifacts；VerificationRunner 必须执行 normalizer、
assembly、Gate、IRS、Renderer replay。

### 12.4 测试计划

```text
ambiguous task requires selection
concrete task uses not_required input
before/after anchor validation
command in MainWorker
no child/handoff/invoke created
promotion diagnostic resolved
resolution marker + materialized closure jointly resolve diagnostic group
marker without matching command is rejected
command without marker does not silently suppress promotion diagnostics
Lane A rejected
rendered SPL contains command
```

### 12.5 验收标准

- 两种 task specificity 都可生成可确认 preview。
- Apply 后 command 位于 MainWorker。
- 无 orphan worker/handoff。
- Lane B accepted，且无新 blocking diagnostics。

### 12.6 PM 审核清单

- [ ] Main-flow command 来自 confirmed task boundary。
- [ ] 没有创建 child、handoff 或 REQUEST_INPUT。
- [ ] Lane A 路径已由负例测试阻止。

---

## 13. P7：DefineChildWorkerClosure

该阶段较重，拆成 P7A-P7D。每个子阶段必须独立测试，但 P7D 完成前 option 仍不可用。

### 13.1 P7A：Worker Boundary 与 Contract

#### 目标

创建或复用 child worker identity/purpose 和 input/output contract。

#### 可编辑范围

```text
src/nl2spl/compiler/spl_editing/stage_slices/stage3_5/define_child_worker.py
src/nl2spl/compiler/spl_editing/stage_slices/stage3_5/worker_handoff_contract.py
src/nl2spl/compiler/spl_editing/stage_slices/model.py
src/nl2spl/compiler/spl_editing/stage_slices/result.py
```

#### 实施要求

```text
consume NormalizedWorkerDelegationDirective only；
reuse matching existing child；
new child ID deterministic；
purpose equals delegated responsibility；
input contract from resolved parent refs；
output contract from admitted outputs；
no StepIR/BlockIR generated in Stage 3.5。
```

#### 验收

- New child 与 existing-child reuse 都通过。
- 不重复创建 child。
- Contract/status/evidence 完整。

### 13.2 P7B：Child Flow、Block 与最小 Command

#### 可编辑范围

```text
src/nl2spl/compiler/spl_editing/stage_slices/stage4/child_worker_flow.py
src/nl2spl/compiler/spl_editing/stage_slices/stage5/child_worker_block.py
src/nl2spl/compiler/spl_editing/stage_slices/stage7/child_worker_command.py
src/nl2spl/compiler/spl_editing/stage_slices/typed_plan.py
```

#### 实施要求

```text
Stage 4: one main flow tied to child responsibility；
Stage 5: one sequential block；
Stage 7: exactly one user-confirmed command；
action_text from normalized responsibility；
inputs match selected refs；
outputs cover all admitted outputs；
side_effect_only rejected；
no extra LLM-generated commands。
```

#### 验收

- Child worker 非空且完整可归一化。
- Command 超出 directive 或漏 output 时拒绝。
- 各 stage 只写自己的 artifact layer。

### 13.3 P7C：Handoff、Parent Invoke 与 Result Usage

#### 可编辑范围

```text
src/nl2spl/compiler/spl_editing/stage_slices/stage3_5/worker_handoff_contract.py
src/nl2spl/compiler/spl_editing/stage_slices/stage5/parent_invocation_placement.py
src/nl2spl/compiler/spl_editing/stage_slices/stage7/worker_invoke.py
src/nl2spl/compiler/spl_editing/materialization/worker_handoff/contract.py
```

#### 实施要求

```text
handoff bindings use resolved/admitted identities；
main-flow placement only；
append/before/after validated anchor；
INVOKE_WORKER references exact handoff；
parent result usage binds existing ref or admitted temporary result；
no parent required output creation。
```

完成 closure 后创建：

```text
PromotionResolutionMarker.resolution_kind = defined_child_worker
materialized_construct_refs = child + flow + block + command + handoff + invoke refs
```

Marker 不得在 P7A-P7C 的半成品阶段成为 accepted artifact。

#### 验收

- Handoff/invoke 双向一致。
- Existing handoff/step 可 bind_existing，不重复创建。
- Invalid binding direction、missing anchor、orphan artifacts 被拒绝。

### 13.4 P7D：Closure Orchestration 与 Capability Registration

#### 实施要求

```text
ConstructClosurePlan 包含全部 closure nodes；
MaterializationPlan 按 stage authority 排序；
changed refs/evidence refs 完整；
planner/materializer/verifier bundle 原子注册；
只有 bundle 全部存在时 capability resolver 返回 available。
closure-specific verifier 通过后才接受 defined_child_worker resolution marker。
```

#### 验收

- Bundle 缺任一组件时仍 unavailable/not_evaluated。
- Bundle 完整时 define-child available + input_required。
- Dry-run 可生成完整 preview artifact graph。

### 13.5 P7 聚合测试计划

```text
new child creation
existing child reuse
child contract from selected/admitted facts
one responsibility-backed command
all admitted outputs produced
side_effect_only rejected
main-flow placement anchors
handoff/invoke/result binding coherence
partial bundle remains unavailable
full bundle changes availability to available
```

### 13.6 PM 审核清单

- [ ] 每个 stage slice 只写自己的 artifact layer。
- [ ] Define-child 不是 handoff-only facade。
- [ ] Child command 没有额外 unsourced behavior。
- [ ] Capability 只在完整 bundle 注册后开放。

---

## 14. P8：Preview Seal、Apply Consistency 与 Verification

### 14.1 目标

把 normalized directive、admitted facts、closure plan 和 slice typed plans 纳入现有 preview
seal，保证用户确认结果与 apply 完全一致。

### 14.2 可编辑范围

```text
src/nl2spl/compiler/spl_editing/preview/model.py
src/nl2spl/compiler/spl_editing/preview/hashes.py
src/nl2spl/compiler/spl_editing/preview/service.py
src/nl2spl/compiler/spl_editing/preview/store.py
src/nl2spl/compiler/spl_editing/preview/validators.py
src/nl2spl/compiler/spl_editing/materialization/service.py
src/nl2spl/compiler/spl_editing/verification/
src/nl2spl/compiler/spl_editing/verification/worker_delegation/   # new
src/nl2spl/compiler/spl_editing/core/service.py
tests/unit/compiler/spl_editing/construct_strategy/
```

### 14.3 实施思路

#### P8.1 Seal content

加入：

```text
strategy/option IDs
interaction contract hash
normalized directive hash
admitted fact hashes
closure plan hash
slice typed plan hashes
preview construct hash
LLM config hash（若使用）
```

#### P8.2 Apply

优先 promote preview sealed typed plans。若必须重建，要求所有 hashes 一致。任何 base revision、
directive、fact、plan 或 config 变化都返回 stale preview。

#### P8.3 Generic verification

Generic verifier 只负责跨 strategy 的通用不变量：

```text
revision/hash consistency
strategy/option/contract linkage
selected refs and admitted fact identities
changed artifact evidence coverage
declared stage authority/write layers
provenance relation
replay artifacts and rendered visibility availability
```

Generic verifier 不得判断 Worker Delegation 的 handoff、invoke、result usage 或“不得创建
child”等 closure 业务语义。

#### P8.4 Closure-specific verification

新增独立 verifier：

```text
DefineChildWorkerClosureVerifier:
  child identity/contract/flow/block/command coherence
  handoff/invoke/result binding coherence
  one responsibility-backed command
  admitted outputs produced
  no orphan graph artifacts
  defined_child_worker marker matches full closure

KeepInMainFlowClosureVerifier:
  command exists in MainWorker
  selected task boundary matches directive
  no child/handoff/invoke/REQUEST_INPUT introduced
  kept_in_main_flow marker matches command
```

`VerificationRunner` 只编排：

```text
generic verifier
-> selected closure-specific verifier
-> compiler-authority Lane B replay checks
-> diagnostic diff
```

不得把 closure-specific 条件复制到 runner 的全局 if/else。

### 14.4 测试计划

```text
every hash mismatch
stale snapshot/overlay
preview does not write accepted overlay
apply does not rerun divergent LLM generation
evidence/provenance on all new artifacts
Lane B accepted/rejected paths
generic verifier does not contain worker patch-type branches
each closure-specific negative invariant is rejected by its own verifier
```

### 14.5 验收标准

- 用户看到的 Worker/command/bindings 与最终 apply 完全一致。
- Stale preview 无任何 overlay。
- Diagnostic 消失但 evidence/graph 不完整时仍 rejected。

### 14.6 PM 审核清单

- [ ] Preview 没有 accepted overlay side effect。
- [ ] Apply 没有重新生成漂移的 typed plans。
- [ ] Generic verifier 覆盖 refs、facts、authority、evidence 和 provenance。

---

## 15. P9：Service/CLI Migration、IRS v2 Switch、Cleanup 与 E2E

### 15.1 目标

原子启用 v2 用户路径，迁移 CLI/demo，清除 Worker Delegation 的 legacy option-index/free-text
authority，并完成真实 E2E。

### 15.2 可编辑范围

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/spl_editing/core/service.py
src/nl2spl/compiler/spl_editing/presentation/service.py
src/nl2spl/compiler/spl_editing/cli.py
src/nl2spl/compiler/spl_editing/demo.py
examples/output/spl_editing_demo/run_demo.py
tests/unit/compiler/spl_editing/
tests/integration/compiler/spl_editing/
```

### 15.3 实施思路

#### P9.1 IRS/Catalog atomic switch

四个 WORKER_PROMOTION slots 切换到：

```text
repair_strategy_id = worker_delegation.complete_closure.v2
supported adapters = DefineChildWorkerClosure + ConvertDelegationIntentToMainFlowStep
default lane = B
```

移除该 affordance 的 `ConvertDelegationIntentToRequestInput`，并运行 IRS audit。

#### P9.2 Service API

Worker Delegation 生产路径只允许：

```text
option_id
-> interaction
-> draft
-> normalized directive
-> preview
-> confirmation
-> apply
```

旧 option index 只作为 CLI 显示序号；不得进入 service identity。

#### P9.3 CLI/demo renderer

CLI 动态遍历 interaction fields/schema，不包含 Worker-specific branching。用户确认页只显示
结果，不显示 strategy/stage/lane IDs；Advanced Details 可显示审计信息。

#### P9.4 Legacy cleanup

清理：

```text
WORKER_PROMOTION 三选项 copy
main-flow Lane A metadata
Worker Delegation option-index API path
free text directly成为 Worker intent authority 的路径
handler 根据 patch type生成表单语义的分支
```

不得删除其他合法 issue 使用的 REQUEST_INPUT adapter。

### 15.4 真实 E2E

使用 `examples/output/spl_editing_demo/run_demo.py`：

#### Scenario A：Define child worker

```text
select Worker delegation issue
-> title shows source gathering/template matching
-> select Define this work as a child worker
-> fill structured fields
-> preview child + handoff + invoke
-> confirm
-> Lane B accepted
-> final SPL contains child worker and MainWorker invocation
```

#### Scenario B：Keep in main flow

```text
select same issue
-> select Keep this work in main workflow
-> select concrete task boundary
-> preview main-flow command
-> confirm
-> Lane B accepted
-> final SPL contains command in MainWorker and no new child/handoff
```

#### Scenario C：Negative

```text
missing field / invalid ref / new parent required output / stale preview
-> no accepted overlay
```

#### Regression

真实运行并确认：

```text
missing_handler remains accepted
missing_output_producer remains accepted
API deferred issue remains non-editable
```

#### E2E Artifact Bundle

每个真实场景必须输出机器可读 acceptance bundle。默认写入测试临时目录或 CI artifact，
不得污染 `examples/output` 的 canonical fixture：

```text
.test-artifacts/spl_editing/worker_delegation_v2/{scenario_id}/
  manifest.json
  before_final.spl
  after_final.spl
  before_diagnostics.json
  after_diagnostics.json
  preview_summary.json
  verification_result.json
  evidence_provenance_summary.json
  artifact_diff.json
```

`manifest.json` 至少记录：

```text
scenario_id
base_snapshot_id / overlay_version
strategy_id / option_id
normalized_directive_id
preview_id
patch/evidence IDs
verification lane/status
all file hashes
```

Artifact diff 必须按 typed artifact 分类，不能只保存文本 diff：

```text
WorkerPlanIR
WorkerFlowPlanIR
WorkerBlockPlanIR
WorkerStepPlanIR
handoff/invoke bindings
PromotionResolutionMarker
SymbolTable local temporary results
```

PM gate 必须检查 bundle，而不是只看控制台 `accepted`。

### 15.5 Audit 与测试

```powershell
python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py `
  --construct WORKER_PROMOTION --scope all --format json

python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py `
  --construct CHILD_WORKER --scope all --format json

python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py `
  --construct WORKER_HANDOFF --scope all --format json

python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py `
  --construct INVOKE_WORKER --scope all --format json
```

### 15.6 验收标准

- 两个 option 均真实 E2E accepted。
- 旧第三 option 不再出现。
- 无 compiler ID 泄漏。
- CLI 无 Worker-specific form branching。
- IRS audits 无新增 unwaived P0/P1。
- 全量 SPL Editing unit/integration 和 scoped Ruff 通过。

### 15.7 PM 审核清单

- [ ] v2 是原子切换，不存在两套用户选项并行。
- [ ] CLI 仅把 display number 映射到 stable option_id。
- [ ] REQUEST_INPUT adapter 在其他合法 affordance 中仍存在。
- [ ] 真实 demo 结果已人工检查，不只依赖 stub E2E。

---

## 16. 阶段测试目录建议

```text
tests/unit/compiler/spl_editing/worker_delegation_v2/
  test_p0_capability_exposure.py
  test_strategy_options.py
  test_issue_subject.py
  test_interaction_contract.py
  test_dynamic_interaction_provider.py
  test_directive_validation.py
  test_directive_normalization.py
  test_output_admission.py
  test_keep_main_flow_closure.py
  test_define_child_worker_boundary.py
  test_child_flow_block_command.py
  test_handoff_invoke_result_binding.py
  test_preview_apply_seal.py
  test_verification_contract.py

tests/integration/compiler/spl_editing/
  test_worker_delegation_v2_e2e.py
```

测试重点是 contract/authority，不应大量断言完整英文文案。

---

## 17. 全局负例矩阵

| 场景 | 必须结果 |
|---|---|
| Define closure runtime 缺组件 | option unavailable + readiness not_evaluated |
| Required field 缺失 | input_required，无 preview |
| Invalid existing ref | input_invalid |
| Ref role 不匹配 | input_invalid |
| New output 名称冲突 | admission rejected |
| Unsupported output type | admission rejected |
| 新增 parent required output | rejected |
| side_effect_only | rejected in MVP |
| Alternative/exception invocation | rejected in MVP |
| Additional instruction 补字段/改 ref | rejected |
| Additional instruction 与 typed plan 冲突 | plan rejected |
| Resolution marker 无 matching closure | verification rejected; diagnostic remains |
| Materialized closure 无 resolution marker | verification rejected; no silent suppression |
| Extra child command | rejected |
| Child command 漏 admitted output | rejected |
| Handoff 无 invoke | verification rejected |
| Invoke 无 handoff | verification rejected |
| Preview hash drift | stale preview |
| Lane A | rejected |
| Diagnostic 消失但 evidence 缺失 | rejected |
| Temporary result 被投影为 required/global output | rejected |

---

## 18. PM 总审核清单

### Contract 与 authority

- [ ] IRS 未执行 repair 逻辑。
- [ ] Strategy option 是用户语义 owner。
- [ ] RepairCatalog 是 capability source。
- [ ] Interaction contract 只声明输入要求。
- [ ] MaterializationPlan 是 lane/write authority。

### Presentation 与 API

- [ ] Issue subject 来源结构化且 source-backed。
- [ ] 默认视图不显示 compiler IDs。
- [ ] API 使用 option_id 和 revision token。
- [ ] Index 仅用于显示。
- [ ] Availability/readiness 正交。

### Directive 与 admission

- [ ] Wire mapping 在边界转为 typed objects。
- [ ] Required fields 无法由 free text满足。
- [ ] Existing refs 经过 SelectableRefSet。
- [ ] New outputs 经过 admission。
- [ ] Parent required output 未被隐式新增。

### Closure 与 stage authority

- [ ] Define-child 是完整 closure，不是 handoff-only。
- [ ] Existing child 被复用。
- [ ] Child command 恰好一个且 responsibility-backed。
- [ ] Handoff/invoke/result usage 一致。
- [ ] Keep-main 不创建 child/handoff。
- [ ] 两条路径均 Lane B。

### Preview、evidence 与 verification

- [ ] Preview 不写 accepted overlay。
- [ ] Apply 使用 sealed directive/facts/plans。
- [ ] 所有 changed artifacts 有 evidence refs。
- [ ] Provenance 不是 assumed。
- [ ] Gate/IRS/Renderer 均验证真实结果。

### Cleanup

- [ ] WORKER_PROMOTION 不再暴露 REQUEST_INPUT option。
- [ ] REQUEST_INPUT adapter 未被全局误删。
- [ ] Patch metadata 不再承担 option copy/form semantics。
- [ ] CLI/UI 无语义推断分支。
- [ ] 无临时 fallback、message parsing 或 raw IR generation。

---

## 19. 阶段完成顺序

```text
Contract Freeze
  -> P0 Characterization + safety guard
  -> P1 Strategy options / stable identity
  -> P2 Issue subject
  -> P3 Interaction DTO/provider
  -> P4 Directive validation/normalization
  -> P5 New output admission
  -> P6 Keep-main-flow closure
  -> P7A Worker boundary
  -> P7B Child flow/block/command
  -> P7C Handoff/invoke/result usage
  -> P7D Closure orchestration/capability registration
  -> P8 Preview/apply/verification
  -> P9 Atomic switch/CLI/E2E/cleanup
```

不得提前执行：

```text
P3 before stable option identity；
P5 before typed draft boundary；
P7 before output admission；
P9 user exposure before P8 seal/verification；
legacy cleanup before v2 E2E accepted。
```

### 19.1 可合并 Checkpoints

#### Checkpoint 1：P0-P3

```text
安全收缩完成；
strategy option / stable option ID 完成；
用户可看到 source-backed delegated task subject；
backend-owned interaction view 可生成；
define-child 仍不对普通用户暴露。
```

产品收益：入口不再误导，前端 contract 已稳定，但不会产生半成品 v2 closure。

#### Checkpoint 2：P4-P6

```text
typed directive validation/normalization 完成；
keep-main-flow Lane B preview/apply/replay 闭环；
PromotionResolutionMarker 可审计；
define-child 仍保持 unavailable。
```

产品收益：已有一条完整 v2 repair path，可独立验收。

#### Checkpoint 3：P7-P9

```text
DefineChildWorkerClosure 完成；
preview/apply seal 和 closure-specific verification 完成；
IRS v2 原子切换；
CLI/real E2E/artifact bundles/cleanup 完成。
```

每个 checkpoint 必须满足其阶段 PM checklist、测试和 lint，不能以“后续阶段会修复”为理由
合并未通过的 checkpoint。

---

## 20. 完成定义

本计划只有在以下条件同时满足时才算完成：

```text
1. 当前 Worker Delegation issue 对用户展示具体 source-backed candidate task。
2. 用户只看到 define child worker / keep in main flow 两个结果选项。
3. 每个 option 的输入由 backend-owned contract 动态声明。
4. Define-child 必填输入不完整时不会生成 suggestion/preview。
5. Define-child 生成完整、可渲染、可验证的 child worker closure。
6. Keep-main 生成 MainWorker 内的 source/user-confirmed command。
7. 两条路径 preview 与 apply 一致并由 Lane B accepted。
8. 所有 refs、new facts、IDs、evidence 和 provenance 可审计。
9. 旧 option-index/free-text Worker authority path 被移除。
10. IRS audit、unit/integration、真实 demo 和 lint 全部通过。
11. PromotionResolutionMarker 与真实 materialized closure 联合解析原 diagnostic group。
12. Parent-local temporary result 不进入 REQUIRED_OUTPUT、全局 outputs 或 missing-output diagnostics。
13. Generic verifier 与两个 closure-specific verifiers 职责分离。
14. 每个真实 E2E 场景产出完整、可校验的 acceptance artifact bundle。
```
