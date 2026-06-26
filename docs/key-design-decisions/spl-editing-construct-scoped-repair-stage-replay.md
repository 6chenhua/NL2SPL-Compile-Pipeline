# SPL Editing 修复方式关键设计决策：Construct-Scoped Repair Intent + Relevant Stage Replay

日期：2026-06-25  
状态：Accepted  
适用范围：SPL Editing、IRS repair affordance、LLM repair suggestion、typed patch、verification、artifact snapshot overlay

---

## 1. 决策结论

SPL Editing 的正确修复方式不是让 patch applier 直接构造或修改最终 IR。

正确方式是：

```text
用户选择 issue
-> 用户选择 repair option / patch type
-> LLM 生成 construct-scoped repair intent
-> 用户确认
-> 将 user-confirmed repair intent 注入 artifact snapshot overlay
-> 重新运行 NL2SPL Pipeline 中负责 materialize 该 SPL Construct 的相关 Stage
-> 由 Stage authority 生成 / 规范化 / 校验对应 IR artifact
-> 再通过 IRS / Gate / ProducerIndex / Renderer / Provenance / Verification 验收
```

也就是说：

```text
RepairPatch 不应该是 direct IR mutation。
RepairPatch 应该表达对某个 SPL Construct 的 user-confirmed repair intent。
具体 SPL Construct 的生成必须回到 NL2SPL Pipeline 对应的 Stage authority。
```

这个决策适用于所有 SPL Editing repair，不只是某一个 patch：

```text
missing_handler
missing_output_producer
worker delegation / handoff contract gaps
未来任何 SPL Construct repair
```

---

## 2. 背景

当前 SPL Editing 已经建立了以下安全链路：

```text
ArtifactSnapshot
-> EditableIssue
-> RepairCatalog
-> LLM-generated RepairSuggestion
-> user confirmation
-> typed patch apply
-> Lane A / Lane B replay
-> verification
```

但在部分实现中，patch applier 仍然直接构造 stage-level IR，例如：

```text
InsertProducerStepApplier
  -> 直接 new StepIR

AddExceptionHandlerStepApplier
  -> 直接 new StepIR

CreateWorkerHandoffContractApplier
  -> 直接构造 handoff / binding artifact
```

这会产生架构风险：

```text
LLM suggestion payload
-> patch applier 直接写 IR
-> 跳过 NL2SPL Pipeline 中负责该 Construct materialization 的 Stage
-> 部分 compiler authority 无法发现语义错误
```

典型问题是 LLM 在 repair suggestion 中捏造变量：

```text
project_data
```

然后 applier 把它直接写入 StepIR.inputs，最终 renderer 输出：

```text
<REF>project_data</REF>
```

但该变量并不存在于 `DEFINE_VARIABLES`、symbol table、worker inputs、previous outputs 或任何合法 scope 中。

这个问题不是单纯的 prompt 问题，也不是 `user_confirmed_repair` 机制失效。它说明：

```text
修复路径绕过了负责生成 / 校验 COMMAND Construct 的 pipeline stage authority。
```

---

## 3. 为什么 direct IR mutation 是错误路径

### 3.1 LLM 不应生成 arbitrary IR

SPL Editing 的基本边界是：

```text
LLM 可以生成 repair suggestion。
LLM 不可以生成 arbitrary IR。
LLM 不可以直接决定最终 SPL Construct 的完整 IR 表达。
```

如果 patch payload 允许 LLM 直接提供：

```json
{
  "text": "...",
  "command_type": "GENERAL_COMMAND",
  "inputs": ["project_data"],
  "outputs": ["assumptions_log"]
}
```

并由 applier 直接变成 `StepIR`，那么 LLM 实际上已经绕过了 Stage 7 / normalizer / symbol validation 的职责边界。

### 3.2 user-confirmed evidence 不是语义合法性的证明

`user_confirmed_repair` 只能证明：

```text
这个 repair intent 是用户确认后引入的。
```

它不能证明：

```text
1. 新变量是合法变量。
2. input refs 已声明。
3. output binding 合法。
4. handoff contract 完整。
5. StepIR 符合 pipeline construction policy。
```

用户确认是 evidence source，不是 construct materialization authority。

### 3.3 Verifier 不能替代 construct generation stage

Verifier 可以拒绝错误结果，但不应该成为生成 Construct 的主要逻辑。

正确职责应是：

```text
Stage authority:
  生成 / 规范化 / 校验 construct artifact

Verifier:
  检查 replay 后目标 diagnostic 是否 resolved，是否产生新 blocking diagnostic
```

如果 repair applier 直接写 IR，然后希望 verifier 补所有缺口，系统会不断增加补丁式校验，形成脆弱架构。

---

## 4. 正确抽象

### 4.1 RepairSuggestion

LLM 输出的 suggestion 应表达：

```text
用户可理解的修复建议
可预览的修复意图
typed payload 的候选值
```

但它不应是最终 IR。

### 4.2 ConstructRepairIntent

应新增或明确一个中间抽象：

```text
ConstructRepairIntent
```

它表示：

```text
用户确认后，希望补充 / 修改哪个 SPL Construct 的哪个 slot，
补充的业务意图是什么，
允许使用哪些已有 structured facts，
希望由哪个 materialization authority 重新生成 artifact。
```

概念字段：

```text
intent_id
target_construct_type
target_construct_id
target_slot_name
repair_affordance_id
patch_type
intent_kind
user_confirmed_text
selected_existing_refs
candidate_bindings
source_evidence_refs
related_diagnostic_id
materialization_plan_id
```

### 4.3 StageReplayPlan

每个 repair affordance 应声明：

```text
修复该 slot 需要重新运行哪些 pipeline stage slice。
```

概念字段：

```text
materialization_plan_id
target_construct_type
required_input_artifacts
editable_artifacts
stage_slice
normalization_required
verification_lanes
expected_output_artifacts
```

### 4.4 Construct Materialization Authority

不同 Construct 的生成权威属于不同 pipeline stage。

示例：

```text
COMMAND / REQUEST_INPUT / DISPLAY_MESSAGE StepIR
  authority:
    Stage 7 WorkerStepPlan construction
    Stage 9.5 normalizer
    Stage 10 worker assembly / renderer

REQUIRED_OUTPUT producer step
  authority:
    Stage 7 WorkerStepPlan construction
    Stage 9.5 normalizer
    ProducerIndex
    Stage 10 renderer

EXCEPTION_FLOW.handler_action
  authority:
    Stage 4/5 flow/block context when needed
    Stage 7 handler StepIR construction
    Stage 9.5 normalizer
    Stage 10 renderer

WORKER_HANDOFF / INVOKE_WORKER
  authority:
    Stage 3.5 worker boundary planner
    Stage 4/5 flow/block planner when needed
    Stage 7 step construction
    Stage 9.5 normalizer
    Stage 10 renderer
```

---

## 5. IRS / repair affordance 中应声明什么

IRS 不执行 repair，也不调用 pipeline stage。

但 IRS / SlotSpec / RepairAffordanceSpec 应声明足够的 repair materialization metadata：

```text
1. target_construct_type
2. target_slot_name
3. supported_patch_types
4. repair decision policy id
5. materialization_plan_id
6. required stage artifacts
7. editable stage artifacts
8. verification lane requirements
9. required context facts
10. forbidden direct mutation targets
```

示例：

```python
RepairAffordanceSpec(
    affordance_id="required_output.insert_or_bind_producer",
    supported_patch_types=("InsertProducerStep", "BindExistingProducerStep"),
    decision_policy_id="required_output.producer.v1",
    materialization_plan_id="stage7.step_producer_repair.v1",
    required_context_facts=(
        "target_output_name",
        "worker_id",
        "available_variables",
        "nearby_steps",
        "symbol_table",
    ),
    editable_artifacts=(
        "worker_step_plan",
    ),
    replay_lanes=("lane_a",),
)
```

含义是：

```text
RepairCatalog 决定该 repair option 是否可用；
materialization_plan_id 决定应调用哪个 stage slice；
LLM Context 根据 required_context_facts 提供上下文；
applier 不能直接 new StepIR，只能提交 ConstructRepairIntent；
stage slice 负责 materialize StepIR。
```

---

## 6. Missing Output Producer 的正确修复路径

### 6.1 当前错误路径

```text
LLM payload:
  producer_text = "Generate assumptions log based on current project data"
  inputs = ["project_data"]
  outputs = ["assumptions_log"]

InsertProducerStepApplier:
  directly new StepIR(...)

Renderer:
  <REF>project_data</REF>
```

问题：

```text
project_data 没有经过 symbol table / variable scope / stage builder 校验。
```

### 6.2 正确路径

```text
LLM output:
  ConstructRepairIntent(
    target_construct_type="REQUIRED_OUTPUT",
    target_slot_name="producer",
    target_output="assumptions_log",
    intent_kind="insert_producer_step",
    user_confirmed_text="Create an assumptions log from available missing-field and evidence context.",
    candidate_existing_refs=("missing_required_fields", "source_evidence_set"),
    materialization_plan_id="stage7.step_producer_repair.v1",
  )

Stage replay:
  Stage 7 producer step materializer
    validates candidate refs against symbol table / worker scope
    builds StepIR

  Stage 9.5 normalizer
    normalizes step / bindings / symbol refs

  ProducerIndex
    confirms assumptions_log now has producer

  Renderer
    produces SPL
```

如果 LLM proposes `project_data`，stage materializer must reject it because it is not a legal selectable ref.

---

## 7. Missing Handler 的正确修复路径

### 7.1 当前风险

`AddExceptionHandlerStepApplier` 直接构造 handler StepIR。

这有同样问题：

```text
LLM 可以直接决定 command_type / inputs / outputs。
applier 可能直接写入 StepIR。
Stage 7 handler step construction policy 被绕过。
```

### 7.2 正确路径

```text
Issue:
  EXCEPTION_FLOW.handler_action missing

LLM output:
  ConstructRepairIntent(
    target_construct_type="EXCEPTION_FLOW",
    target_slot_name="handler_action",
    target_exception_flow_id="exc_adapter_03",
    intent_kind="request_missing_information",
    requested_information="timeframe",
    preferred_existing_output_ref="timeframe",
    user_confirmed_text="Ask the user to provide the missing timeframe.",
    materialization_plan_id="stage7.exception_handler_step_repair.v1",
  )

Stage replay:
  Stage 7 exception handler materializer
    validates exception flow id
    validates preferred output ref against symbol table
    chooses REQUEST_INPUT StepIR if policy allows

  Stage 9.5 normalizer
    normalizes handler step and flow placement

  IRS / Gate
    confirms handler_action is satisfied and renderable

  Renderer
    produces SPL
```

这意味着 missing_handler 也不应由 applier 直接 `new StepIR`。

---

## 8. Worker Delegation 的正确修复路径

Worker delegation / handoff repair 更不能直接 patch IR。

正确路径应是：

```text
WORKER_PROMOTION / WORKER_HANDOFF slot diagnostic
-> ConstructRepairIntent
-> Stage 3.5 worker boundary / handoff materialization slice
-> Stage 4/5 flow/block adjustment if needed
-> Stage 7 invoke step construction
-> Stage 9.5 normalizer
-> Stage 10 renderer
-> Lane B / Lane A verification
```

直接构造：

```text
WorkerHandoffIR
INVOKE_WORKER StepIR
Child worker binding
```

都属于高风险路径，必须被 stage materialization authority 替代。

---

## 9. Applier 的新职责

旧职责：

```text
PatchApplier.apply()
  -> mutate stage artifact / create IR object
```

新职责：

```text
PatchApplier.apply()
  -> validate patch revision
  -> create user-confirmed ConstructRepairIntent
  -> call materialization plan executor
  -> receive normalized artifact overlay
  -> persist overlay event
```

Applier 不再是 IR constructor，而是：

```text
repair intent submitter + materialization plan invoker
```

---

## 10. Verification 的新职责

Verification 不应只检查：

```text
目标 diagnostic 消失
```

还应检查：

```text
1. repair intent 被 materialization plan 消费。
2. produced construct artifact 来自 declared stage authority。
3. changed refs 对应 user_confirmed_repair evidence。
4. 新 construct 通过 IRS / Gate / ProducerIndex / Renderer。
5. 没有 undefined symbol refs。
6. 没有未声明 variable / worker / handoff ref。
```

但注意：

```text
Verifier 是验收方，不是 construct generator。
```

---

## 11. 禁止路径

以下路径明确禁止：

```text
1. LLM payload 直接变成 StepIR。
2. PatchApplier 直接 new StepIR / WorkerHandoffIR / WorkerIR。
3. 仅靠 user_confirmed_repair origin 接受 arbitrary IR。
4. 仅靠 ProducerIndex 确认 output producer，而不检查 producer step 自身合法性。
5. Renderer 输出 undefined <REF> 后仍 accepted。
6. 为每个 patch 增加零散 validator 来替代 stage materialization authority。
```

Validator 可以作为防线，但不能替代 pipeline stage authority。

---

## 12. 与 Repair Decision Policy 的关系

Repair Decision Policy 解决：

```text
LLM 应生成什么样的修复意图。
```

Construct-scoped stage replay 解决：

```text
这个修复意图如何被正确 materialize 成 SPL Construct。
```

两者关系：

```text
RepairDecisionPolicy
  -> 约束 LLM suggestion / ConstructRepairIntent

StageReplayPlan
  -> 约束 ConstructRepairIntent 如何生成 IR artifact
```

两者都可以由 IRS / repair_affordance 引用，但职责不同。

---

## 13. 后续实施方向

建议后续实施分阶段进行：

```text
S0  定义 ConstructRepairIntent DTO
S1  定义 StageReplayPlan / MaterializationPlan registry
S2  扩展 RepairAffordanceSpec，加入 materialization_plan_id
S3  为 missing_handler 建立 exception handler step materializer
S4  为 missing_output_producer 建立 producer step materializer
S5  为 worker delegation 建立 handoff / invoke materializer
S6  重构 applier：从 direct IR mutation 改为 intent + materializer
S7  增加 undefined ref / symbol scope verification
S8  E2E：证明 project_data 这类捏造变量被拒绝
S9  删除 direct StepIR construction 的旧路径
```

---

## 14. 验收标准

该决策落实后，应满足：

```text
1. 任意 repair patch 不直接构造最终 IR。
2. 每个 repair affordance 都声明 materialization_plan_id。
3. 新增 Construct 必须由对应 pipeline stage slice materialize。
4. LLM payload 中的变量 / worker / handoff ref 必须来自 selectable structured refs。
5. 未声明 refs 会在 materialization 或 verification 阶段被拒绝。
6. missing_handler、missing_output_producer、worker delegation 均遵循同一模式。
7. E2E 中 LLM 捏造 project_data 不会 accepted。
```

---

## 15. 一句话总结

SPL Editing 修复的对象是 SPL Construct，不是任意 IR object。

因此：

```text
RepairPatch 应表达 user-confirmed construct repair intent；
Construct 的实际生成必须回到 NL2SPL Pipeline 对应 Stage authority；
applier 不应直接写最终 IR；
verification 只做验收，不替代 stage materialization。
```
