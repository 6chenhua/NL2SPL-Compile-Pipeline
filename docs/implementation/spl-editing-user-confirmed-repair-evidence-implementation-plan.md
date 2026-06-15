# SPL Editing User-Confirmed Repair Evidence 实施计划

状态：实施计划草案  
来源设计：[spl_editing_architecture_design_v2.md](../design/spl_editing_architecture_design_v2.md)  
参考模板：[implementation_plan_template.md](../templates/implementation_plan_template.md)  
目标产物：统一的 `user_confirmed_repair` evidence 机制，使当前和未来所有经过用户确认的修复结果都能被 IRS / Gate / ProducerIndex / Renderer 权威链路一致识别。

---

## 0. 背景与问题定义

`spl_editing_architecture_design_v2.md` 要求 SPL Editing 的修复结果必须是：

```text
typed RepairPatch
  -> user confirmation
  -> stage-level artifact update
  -> compiler authority replay
  -> IRS / Gate / ProducerIndex / Renderer verification
```

设计中明确规定：

```text
metadata.origin == "user_confirmed_repair"
  -> Gate recognizes it
  -> ProducerIndex recognizes it
  -> Post-normalize IRS treats it as confirmed evidence
```

当前代码中该机制已经部分存在：

- `ExecutableElementGate` 能识别 `user_confirmed_repair` 并允许其按 command-type guard rails 渲染。
- `ProducerIndex` 能把 `user_confirmed_repair` step 视为 renderable producer。
- `PostNormalizeIRSCheckerV6._source_evidence_slot()` 能把 `user_confirmed_repair` 判为 `source_evidence=satisfied`。
- 多个 SPL Editing patch applier 已经给新增 `StepIR` 打上 `metadata.origin="user_confirmed_repair"`。

但当前实现仍存在关键缺口：

```text
Post-normalize IRS 的部分 command-specific checker
仍直接使用 bool(step.source_span_ids)
判断 prompt_text / value_target / call_action / renderable。
```

这导致 `user_confirmed_repair` 只在 `_source_evidence_slot()` 生效，却没有自然贯通到所有 command slot checker。典型失败场景是：

```text
REQUEST_INPUT
  source_span_ids = []
  metadata.origin = "user_confirmed_repair"
  outputs = ["user_answer"]

当前结果：
  source_evidence = satisfied
  prompt_text = missing
  value_target = missing
  renderable = false
```

这与设计要求不一致。

---

## 1. 总体目标

本计划目标不是只修复 `REQUEST_INPUT` 的一个 if 条件，而是建立一套未来可扩展的 confirmed evidence 规则：

```text
StepIR
  -> unified evidence classification
  -> command-specific structural slot checks
  -> ConstructSatisfactionReport
  -> DiagnosticProjector
  -> CompileDiagnostic
```

最终系统应满足：

```text
用户确认后的修复结果
  -> 带有明确 user_confirmed_repair evidence
  -> 不需要原始 source_span_ids 也能作为 confirmed evidence
  -> 仍必须满足 command type 自身结构要求
  -> 不能绕过 handoff / API / output producer 等 authority
  -> 可被 Lane A / Lane B replay 稳定验证
```

目标行为：

```text
GENERAL_COMMAND + user_confirmed_repair
  -> source_evidence satisfied
  -> action_text 仍需存在

REQUEST_INPUT + user_confirmed_repair
  -> source_evidence satisfied
  -> prompt_text 由 step.text 校验
  -> value_target 由 step.outputs 校验

CALL_API + user_confirmed_repair
  -> source_evidence satisfied
  -> api_name / integration_ref / declaration 仍需校验

INVOKE_WORKER + user_confirmed_repair
  -> user confirmation 不绕过 handoff contract
  -> target_worker / handoff_id / bindings 仍由 worker authority 校验

DISPLAY_MESSAGE + user_confirmed_repair
  -> 可通过 Gate / Renderer
  -> 如不属于 IRS step construct，则不新增额外 IRS 语义
```

---

## 2. 非目标

本计划不做：

- 不新增新的 repair capability。
- 不修改 LLM suggestion 生成策略。
- 不修改 final SPL text。
- 不让 IRS 生成、修复或改写 IR。
- 不把 `user_confirmed_repair` 伪装为 `source_backed`。
- 不允许 `user_confirmed_repair` 绕过 command type 的结构要求。
- 不允许 `user_confirmed_repair` 绕过 handoff contract、API declaration、ProducerIndex 或 Renderer。
- 不把 diagnostic kind 作为新的 construct truth source。
- 不修改 `DELEGATION_INTENT` 边界。
- 不为兼容失败静默 fallback 到 source span / report / debug JSON 解析。

---

## 3. 全局硬性原则

所有阶段必须遵守：

1. `user_confirmed_repair` 是 confirmed evidence，不是 source span。
2. `source_backed`、`handoff_generated`、`compiler_unpack`、`user_confirmed_repair` 必须语义分离。
3. IRS checker 只做 slot satisfaction，不调用 LLM、不应用 patch、不生成 SPL。
4. Gate 仍是 executable step renderability authority。
5. ProducerIndex 仍是 required output producer authority。
6. Post-normalize IRS 仍是 final construct-level authority。
7. Renderer 只消费 gated / assembled IR，不推断 repair evidence。
8. `user_confirmed_repair` 只能补足 evidence slot，不能补足缺失的 structural slot。
9. unconfirmed AI suggestion 不得被 Gate / IRS / ProducerIndex 当作 confirmed evidence。
10. 任何新增 patch 只要创建 executable / materialized `StepIR`，必须显式写入 repair evidence metadata。
11. 非 `StepIR` 修复 artifact 需要自己的 confirmed evidence 字段，例如 handoff binding status source。
12. 测试必须覆盖 command-specific checker，而不是只测试底层 helper。
13. 不允许通过 `diagnostic.message`、report text 或 stage debug JSON 推断 evidence。
14. 不允许新增 skip / xfail 来绕过已知失败。

---

## 4. LLM / Rule-Based 决策约束

本计划不引入新的 LLM 行为。

允许的确定性逻辑仅限：

- 从 `StepIR.source_span_ids`、`StepIR.handoff_id`、`StepIR.metadata.origin` 读取 evidence 信息。
- 从 `WorkerPlanIR.handoffs` 校验 handoff id 是否存在。
- 从 command-specific structured fields 校验结构完整性，例如 `outputs`、`integration_ref`、`handoff_id`。
- 将 evidence 分类结果投影为 `SlotSatisfaction`。
- 将不可用原因投影为明确 diagnostic。

禁止：

- 根据自然语言 prompt / title / diagnostic message 推断 evidence。
- 根据 LLM 输出文本推断 user confirmation。
- 在 IRS checker 中调用 LLM 或 repair handler。
- 为了让修复通过而降低 handoff / API / output producer 校验。

---

## 5. 目标语义模型

### 5.1 Evidence 分类

统一 evidence 分类应至少区分：

```text
source_span
valid_handoff
compiler_unpack
user_confirmed_repair
missing
```

其中：

```text
source_span:
  step.source_span_ids 非空。

valid_handoff:
  step.handoff_id 存在且能在 WorkerPlanIR.handoffs 中找到。

compiler_unpack:
  step.metadata.origin == "compiler_unpack"。

user_confirmed_repair:
  step.metadata.origin == "user_confirmed_repair"。

missing:
  以上均不成立。
```

### 5.2 Evidence 与结构 slot 的关系

Evidence 只能回答：

```text
这个 step 是否有可接受来源？
```

它不能回答：

```text
REQUEST_INPUT 是否有 value target？
CALL_API 是否有 API name？
INVOKE_WORKER 是否有 handoff contract？
required output 是否真的被 produced？
```

因此每个 command checker 必须拆成两层：

```text
confirmed evidence check
command structural slot check
```

### 5.3 Renderability 组合规则

推荐组合：

```text
renderable =
  evidence_satisfied
  AND command_structural_slots_satisfied
  AND authority_specific_constraints_satisfied
```

其中 authority-specific constraints 包括：

- `INVOKE_WORKER` 必须有有效 handoff / target worker / bindings。
- `CALL_API` 必须有具体 API target，并满足声明或 handoff-backed API 规则。
- output producer 是否有效仍由 ProducerIndex 判定。

---

## 6. Phase U-1：Contract Freeze / Current Gap Lock

### 6.1 目标

先锁定当前缺口和目标 contract，避免后续实现把 `user_confirmed_repair` 简化成 `source_backed` 或绕过结构 slot。

### 6.2 可编辑范围

允许新增或修改：

```text
tests/unit/compiler/irs/
tests/unit/compiler/spl_editing/
docs/implementation/
```

### 6.3 禁止改动

本阶段禁止修改：

```text
src/nl2spl/compiler/irs/checkers/post_normalize.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/producer_index.py
src/nl2spl/compiler/spl_editing/patches/
```

### 6.4 设计要求

新增 characterization tests，明确当前缺口：

```text
REQUEST_INPUT + user_confirmed_repair + outputs + no source spans
  当前 post-normalize IRS 仍可能报 prompt/value diagnostics。

_source_evidence_slot(user_confirmed_repair)
  当前已 satisfied，但不足以证明完整 command checker 已接入。
```

同时新增 expected contract tests，可以先标记为将要修复的目标测试，但不得长期 xfail。

### 6.5 测试计划

必须覆盖：

1. `_source_evidence_slot()` 对 `user_confirmed_repair` 返回 satisfied。
2. 完整 `_check_request_input()` 当前与目标行为的差异。
3. `GENERAL_COMMAND` 当前能通过 user-confirmed evidence。
4. `CALL_API` / `INVOKE_WORKER` 当前是否存在类似直接 `source_span_ids` 判断。
5. 现有 Gate / ProducerIndex 行为快照。

### 6.6 验收标准

1. 当前缺口被测试精确描述。
2. 测试不靠 diagnostic message regex。
3. 没有生产代码行为变更。
4. PM 能从测试名直接看出待修复 contract。

---

## 7. Phase U0：Unified Step Evidence Model

### 7.1 目标

引入 compiler-owned 的统一 step evidence predicate，使 IRS / Gate / ProducerIndex 可以共享同一套 evidence 语义或至少使用同一 contract。

### 7.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/evidence/
  __init__.py
  step_evidence.py

tests/unit/compiler/evidence/
```

允许修改：

```text
src/nl2spl/compiler/irs/checkers/post_normalize.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/producer_index.py
```

### 7.3 禁止改动

禁止：

```text
src/nl2spl/compiler/spl_editing/handlers/
src/nl2spl/compiler/spl_editing/presentation/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 7.4 设计要求

统一 evidence model 必须：

```text
输入：
  StepIR
  optional valid_handoff_ids / handoff_index

输出：
  evidence kind
  satisfied / missing
  relation
  source_span_ids
  explanation
```

不得包含：

```text
diagnostic.kind 推断
command type repair strategy
LLM prompt / parser
SPL rendering logic
PatchApplier
```

关键语义：

```text
source_span_ids 非空 -> source_span evidence
valid handoff -> valid_handoff evidence
compiler_unpack -> compiler_unpack evidence
user_confirmed_repair -> user_confirmed_repair evidence
none -> missing
```

### 7.5 测试计划

新增测试覆盖：

1. source span evidence。
2. valid handoff evidence。
3. compiler unpack evidence。
4. user-confirmed repair evidence。
5. unconfirmed AI-like step without source spans remains missing。
6. handoff id present but invalid does not become user-confirmed by accident。
7. source span 优先级不抹掉 user-confirmed metadata，但 evidence kind 必须稳定。

### 7.6 验收标准

1. Evidence predicate 不 import SPL Editing patch / handler / service。
2. Evidence predicate 不调用 LLM。
3. Evidence predicate 不读取 report / stage debug JSON。
4. Gate / ProducerIndex / IRS 可复用或对齐该 contract。

---

## 8. Phase U1：Post-Normalize IRS Step Checker Refactor

### 8.1 目标

让 post-normalize IRS 的所有 step command checker 都使用统一 evidence 语义，并把 evidence slot 与 command structural slot 分离。

### 8.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/irs/checkers/post_normalize.py
tests/unit/compiler/irs/
tests/unit/compiler/spl_editing/
```

### 8.3 禁止改动

禁止：

```text
src/nl2spl/compiler/spl_editing/handlers/
src/nl2spl/compiler/spl_editing/patches/*/handler.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 8.4 设计要求

#### GENERAL_COMMAND

```text
action_text:
  satisfied if step.text 非空。

source_evidence:
  satisfied if unified evidence satisfied。

renderable:
  action_text satisfied
  AND source_evidence satisfied。
```

#### REQUEST_INPUT

```text
prompt_text:
  satisfied if step.text 非空。

value_target:
  satisfied if step.outputs 非空。

source_evidence:
  satisfied if unified evidence satisfied。

renderable:
  prompt_text satisfied
  AND value_target satisfied
  AND source_evidence satisfied。
```

`user_confirmed_repair` 不得让缺少 `outputs` 的 `REQUEST_INPUT` 通过。

#### CALL_API

```text
api_name:
  satisfied if integration_ref / declared API / api handoff condition satisfied。

call_action:
  satisfied if step.text 非空 AND unified evidence satisfied。

source_evidence:
  satisfied if unified evidence satisfied。

renderable:
  api constraints satisfied
  AND call_action satisfied
  AND source_evidence satisfied。
```

`user_confirmed_repair` 不得让缺少 API target 的 `CALL_API` 通过。

#### INVOKE_WORKER

```text
target_worker:
  satisfied if integration_ref points to declared child worker.

handoff_id:
  satisfied if handoff_id exists and resolves to a valid handoff.

source_evidence:
  satisfied by valid handoff or confirmed repair evidence,
  but confirmed repair evidence must not bypass handoff_id / target_worker slots.

renderable:
  target_worker satisfied
  AND handoff_id satisfied
  AND handoff binding constraints satisfied。
```

#### DISPLAY_MESSAGE

如果 `DISPLAY_MESSAGE` 不属于 post-normalize IRS step construct registry，则本阶段不新增 construct。其 evidence 仍由 Gate / Renderer 处理。

### 8.5 测试计划

必须新增：

1. `REQUEST_INPUT + user_confirmed_repair + outputs + no source spans` -> complete/renderable。
2. `REQUEST_INPUT + user_confirmed_repair + no outputs` -> source_evidence satisfied，但 value_target missing。
3. `GENERAL_COMMAND + user_confirmed_repair + no source spans` -> complete/renderable。
4. `GENERAL_COMMAND + no evidence` -> remains partial/non-renderable。
5. `CALL_API + user_confirmed_repair + missing integration_ref` -> still missing api_name。
6. `CALL_API + user_confirmed_repair + valid integration_ref/declaration` -> complete/renderable。
7. `INVOKE_WORKER + user_confirmed_repair + missing handoff_id` -> still missing handoff_id。
8. `INVOKE_WORKER + valid handoff` -> complete/renderable。
9. `unconfirmed AI step` with no source spans -> still rejected。

### 8.6 验收标准

1. `REQUEST_INPUT` 不再直接用 `bool(step.source_span_ids)` 判定所有 slot。
2. `CALL_API` / `INVOKE_WORKER` 不再把 evidence 与结构要求混在一起。
3. `user_confirmed_repair` 只补足 evidence，不补足结构字段。
4. 所有现有 IRS tests 通过。

---

## 9. Phase U2：Gate / ProducerIndex Alignment Hardening

### 9.1 目标

确认 Gate 和 ProducerIndex 与统一 evidence contract 一致，并补足回归测试，避免它们未来与 IRS evidence 语义漂移。

### 9.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/producer_index.py
tests/unit/compiler/spl_editing/
tests/unit/pipeline/
```

### 9.3 设计要求

Gate 仍负责：

```text
source_backed -> renderable with command guard rails
handoff_generated -> renderable only with valid handoff contract
compiler_unpack -> renderable for deterministic unpack scaffolding
user_confirmed_repair -> renderable with same command guard rails as source-backed
assumed -> non-renderable
```

ProducerIndex 仍负责：

```text
renderable producer discovery
required output producer validation
user_confirmed_repair producer recognition
```

不得让 ProducerIndex 伪造 producer entry，也不得让 Gate 跳过 handoff contract。

### 9.4 测试计划

1. Gate accepts `GENERAL_COMMAND user_confirmed_repair`。
2. Gate accepts `REQUEST_INPUT user_confirmed_repair` with outputs。
3. Gate rejects invalid `CALL_API` even if user-confirmed。
4. Gate rejects invalid `INVOKE_WORKER` without valid handoff。
5. ProducerIndex recognizes output produced by user-confirmed producer step。
6. ProducerIndex does not recognize unconfirmed no-source step。

### 9.5 验收标准

1. Gate / ProducerIndex behavior 与 post-normalize IRS evidence contract 一致。
2. 没有新 fallback。
3. 没有绕过 existing authority。

---

## 10. Phase U3：Patch Applier Evidence Stamping Contract

### 10.1 目标

确保所有当前和未来 patch applier 创建的修复 artifact 都显式携带 confirmed evidence，并通过测试约束防止新 patch 遗漏。

### 10.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/spl_editing/patches/
tests/unit/compiler/spl_editing/
```

### 10.3 设计要求

所有创建 `StepIR` 的 patch applier 必须写入：

```text
metadata.origin = "user_confirmed_repair"
metadata.repair_patch_id
metadata.related_diagnostic_id
```

如果 patch 创建非 StepIR 的 authority artifact，则必须使用该 artifact 的结构化 evidence 字段。例如：

```text
WorkerHandoffIR.input_binding_status_source = "user_confirmed_repair"
WorkerHandoffIR.output_binding_status_source = "user_confirmed_repair"
```

`BindExistingProducerStep` 不新增 step，但必须：

```text
只允许绑定 source-backed 或 user-confirmed renderable step；
写入 repair_output_bindings audit metadata；
不把不可渲染 step 变成 producer。
```

### 10.4 测试计划

1. 每个 StepIR-producing patch 都验证 `origin=user_confirmed_repair`。
2. 每个 StepIR-producing patch 都验证 `repair_patch_id` 和 related diagnostic metadata。
3. CreateWorkerHandoffContract 同时验证 handoff status source 和 generated invoke step metadata。
4. BindExistingProducerStep 验证不能绑定 assumed step。
5. 新增 patch bundle 时必须有 evidence stamping 测试。

### 10.5 验收标准

1. 当前所有 patch 类型符合 stamping contract。
2. 新 patch 类型没有测试就无法通过。
3. Stamping 不由 LLM 决定，只由 apply confirmation boundary 决定。

---

## 11. Phase U4：Lane A / Lane B Verification Integration

### 11.1 目标

确保修复后的 evidence 语义在 SPL Editing replay 中真实生效，而不是只在单元测试中通过。

### 11.2 可编辑范围

允许修改：

```text
tests/unit/compiler/spl_editing/
tests/integration/compiler/spl_editing/
examples/output/spl_editing_demo/
```

生产代码仅限必要接线修复。

### 11.3 测试计划

必须覆盖：

1. `AddExceptionHandlerStep(command_type=REQUEST_INPUT)` -> Lane A accepted。
2. `InsertProducerStep(command_type=REQUEST_INPUT)` -> ProducerIndex resolves missing output -> Lane A accepted。
3. `ConvertDelegationIntentToRequestInput` -> Lane A accepted 或按 patch lane 预期 accepted。
4. `CreateWorkerHandoffContract` -> Lane B accepted，handoff + invoke step 不被 user-confirmed evidence 错误绕过。
5. unconfirmed suggestion preview 不影响 replay。
6. user-confirmed repair step 出现在 rendered SPL。

### 11.4 验收标准

1. Lane A / Lane B replay 都实际调用 compiler authorities。
2. 没有 patch 直接修改 rendered SPL。
3. `VerificationResult.accepted=True` 只在 diagnostics / Gate / ProducerIndex / Renderer 均满足时出现。
4. `REQUEST_INPUT` user-confirmed repair 不再产生 assumed / value target false positive。

---

## 12. Phase U5：Stage-Local IRS Policy Decision

### 12.1 目标

决定 stage-local IRS checker 是否也接入 unified evidence model，避免未来 full recompile / Lane C 或 early stage overlay 使用时再次出现不一致。

### 12.2 当前判断

当前 SPL Editing verification 主要依赖 post-normalize IRS，因此 stage-local checker 不是立即 blocker。

但 stage-local checker 中也存在：

```text
source_backed = bool(step.source_span_ids)
```

如果未来 patched artifact 会进入 stage-local IRS，则该 checker 也需要接入 confirmed evidence。

### 12.3 推荐策略

本计划建议：

```text
U5a: 先补文档和测试，明确 stage-local checker 当前不消费 SPL Editing overlay。
U5b: 如果后续 Lane C / full recompile 引入 overlay stage-local checking，则同步迁移 stage-local checker。
```

不得在 stage-local checker 中引入特殊 LLM / report fallback。

### 12.4 验收标准

1. 文档明确 stage-local checker 与 SPL Editing overlay 的关系。
2. 若 stage-local checker 保持不改，必须有测试证明当前 SPL Editing verification 不依赖它。
3. 若 stage-local checker 接入 unified evidence，行为必须与 post-normalize IRS 对齐。

---

## 13. Phase U6：Future Patch Compliance Guardrails

### 13.1 目标

确保“所有未来修复结果自动适用”不是靠口头约定，而是靠测试、注册检查和文档 guardrail 约束。

### 13.2 可编辑范围

允许修改：

```text
tests/unit/compiler/spl_editing/
tests/unit/compiler/irs/
docs/implementation/
docs/design/
```

### 13.3 设计要求

新增或强化以下审核规则：

```text
任何 patch applier 如果创建 StepIR：
  必须设置 origin=user_confirmed_repair。

任何 patch applier 如果创建 WorkerHandoffIR / binding / contract artifact：
  必须设置对应 status_source / evidence metadata。

任何 command checker 如果新增 source/evidence 判断：
  必须使用 unified evidence predicate。

任何 verification path：
  不得只检查 rendered_spl string。
```

### 13.4 测试计划

1. Patch applier evidence stamping audit。
2. IRS checker source evidence usage audit。
3. `rg` / AST-level boundary test：禁止新增裸 `bool(step.source_span_ids)` 作为 renderable 判定。
4. 新 patch skeleton test：缺 origin 的 StepIR-producing patch 失败。
5. Unconfirmed AI suggestion still non-renderable。

### 13.5 验收标准

1. 新 patch 不可能静默绕过 evidence stamping。
2. 新 command checker 不可能静默回到 source-span-only evidence。
3. 文档与测试共同锁住 future patch contract。

---

## 14. Phase U7：Documentation / Skill Sync / Final Audit

### 14.1 目标

更新设计实现状态，使文档准确反映 user-confirmed repair evidence 的真实覆盖面。

### 14.2 可编辑范围

允许修改：

```text
docs/design/spl_editing_architecture_design_v2.md
docs/implementation/spl-editing-readiness-implementation-plan.md
docs/implementation/spl-editing-backend-implementation-plan.md
.codex/skills/irs-knowledge/SKILL.md
.agents/skills/irs-knowledge/SKILL.md
```

### 14.3 文档要求

必须补充：

```text
confirmed evidence 不等于 source-backed。
user_confirmed_repair 只满足 evidence slot。
command structural slots 仍由各 construct IRS 校验。
Gate / ProducerIndex / IRS 三方的职责分工。
future patch stamping contract。
stage-local checker policy。
```

### 14.4 验收标准

1. 文档不再笼统写“IRS recognizes user_confirmed_repair”，而要说明识别层级。
2. Skill 文档同步更新，不误导后续实现者。
3. final audit 列出当前覆盖的 command types 和未覆盖的未来边界。

---

## 15. Decision Gate：Unified Evidence Predicate 的归属

### 15.1 目标

在进入 U0 前确认统一 evidence predicate 的代码归属，避免 Gate / ProducerIndex / IRS 各自维护平行逻辑。

### 15.2 可选方案

```text
方案 A：放在 src/nl2spl/compiler/evidence/
  推荐。compiler-owned，中立，不依赖 SPL Editing。

方案 B：放在 src/nl2spl/compiler/irs/
  不推荐。Gate / ProducerIndex 也需要该语义，会造成反向依赖。

方案 C：放在 src/nl2spl/compiler/spl_editing/
  禁止。普通 compiler authorities 不应依赖 SPL Editing runtime。
```

### 15.3 推荐方案

采用方案 A：

```text
src/nl2spl/compiler/evidence/
```

理由：

- 这是 compiler authority 共享语义，不属于 SPL Editing UI / service。
- 不污染 construct registry。
- 不让 Gate / ProducerIndex import SPL Editing。
- 未来非 SPL Editing 的 confirmed compiler artifact 也可复用。

### 15.4 决策通过标准

1. PM 明确批准模块归属。
2. 依赖方向为 `compiler authority -> compiler.evidence`。
3. `compiler.evidence` 不 import `spl_editing`。

---

## 16. End-to-End 验收场景

最终必须具备以下 E2E 或高保真集成覆盖。

### 16.1 Missing Handler -> REQUEST_INPUT

```text
given:
  missing_handler issue

when:
  user selects AddExceptionHandlerStep
  LLM returns command_type=REQUEST_INPUT with output target
  user confirms apply

then:
  new StepIR has origin=user_confirmed_repair
  post-normalize IRS has no false prompt/value diagnostics
  Gate keeps the step
  Renderer emits INPUT command
  VerificationResult.accepted=True
```

### 16.2 Missing Output Producer -> REQUEST_INPUT Producer

```text
given:
  missing_output_producer issue

when:
  user confirms InsertProducerStep(command_type=REQUEST_INPUT)

then:
  new StepIR produces required output
  ProducerIndex recognizes it
  post-normalize IRS accepts confirmed evidence
  final diagnostics no longer include that missing_output_producer
```

### 16.3 Worker Delegation -> Request Input Conversion

```text
given:
  type_or_contract_ambiguity on worker promotion

when:
  user chooses ConvertDelegationIntentToRequestInput

then:
  new REQUEST_INPUT step is user-confirmed
  value target is satisfied by outputs
  replay accepted
```

### 16.4 Worker Handoff Contract

```text
given:
  worker promotion missing handoff contract

when:
  user confirms CreateWorkerHandoffContract

then:
  handoff has user_confirmed_repair status source
  generated invoke step has user_confirmed_repair origin
  Lane B normalizer finds corresponding step
  Gate validates handoff consistency
  IRS does not accept missing handoff merely because origin is user_confirmed_repair
```

### 16.5 Negative: Unconfirmed AI Suggestion

```text
given:
  AI suggestion generated but not confirmed

when:
  verification/replay runs without apply

then:
  no new StepIR enters snapshot
  no user_confirmed_repair evidence exists
  Gate / ProducerIndex / IRS behavior unchanged
```

### 16.6 Negative: Structurally Invalid Confirmed Repair

```text
given:
  confirmed REQUEST_INPUT has no outputs

then:
  source_evidence = satisfied
  value_target = missing
  verification rejected
```

---

## 17. PM 总审核清单

每个阶段提交时必须检查：

1. 是否仍严格对齐 `spl_editing_architecture_design_v2.md`。
2. 是否把 `user_confirmed_repair` 当作 evidence，而不是 source-backed。
3. 是否把 evidence slot 与 command structural slots 分离。
4. 是否新增了未经批准的 LLM prompt / schema 变更。
5. 是否新增了 rule-based semantic fallback。
6. 是否让 IRS checker 修改 IR、调用 LLM 或生成 SPL。
7. 是否绕过 Gate / ProducerIndex / Renderer。
8. 是否让 `user_confirmed_repair` 绕过 handoff contract。
9. 是否让 `user_confirmed_repair` 绕过 API declaration。
10. 是否让 `user_confirmed_repair` 绕过 REQUEST_INPUT value target。
11. 是否有新的 naked `bool(step.source_span_ids)` 被用于 renderable / evidence 判断。
12. 是否所有 StepIR-producing patch 都写入 `origin=user_confirmed_repair`。
13. 是否非 StepIR repair artifact 有结构化 evidence 字段。
14. 是否 unconfirmed AI suggestion 仍不可渲染。
15. 是否所有 diagnostics 仍来自 IRS / Gate / ProducerIndex 等 authority。
16. 是否没有新增 skip / xfail。
17. 是否新增路径均有测试覆盖。
18. 是否文档和 skill 同步。

---

## 18. 阶段完成顺序

推荐顺序：

```text
U-1  Contract Freeze / Current Gap Lock
Gate Unified Evidence Predicate Ownership
U0   Unified Step Evidence Model
U1   Post-Normalize IRS Step Checker Refactor
U2   Gate / ProducerIndex Alignment Hardening
U3   Patch Applier Evidence Stamping Contract
U4   Lane A / Lane B Verification Integration
U5   Stage-Local IRS Policy Decision
U6   Future Patch Compliance Guardrails
U7   Documentation / Skill Sync / Final Audit
```

依赖关系：

- U-1 必须先做，用于锁定当前缺口。
- U0 必须在 U1 前完成。
- U1 是核心修复阶段。
- U2 / U3 可在 U1 后并行推进。
- U4 必须在 U1-U3 完成后进行。
- U5 是策略收敛阶段，可以在 U4 后完成。
- U6 必须在最终 E2E 前完成，防止未来 patch 回归。
- U7 最后完成，确保文档描述的是实际行为。

---

## 19. 最终完成定义

本计划完成后，必须满足：

```text
所有当前 SPL Editing repair patch 产生的修复结果：
  通过 user confirmation 获得 user_confirmed_repair evidence；
  在 IRS / Gate / ProducerIndex / Renderer replay 中被一致识别；
  不依赖原始 source_span_ids 才能作为 confirmed repair evidence；
  不绕过 command-specific structural requirements；
  不绕过 handoff / API / producer authorities。

所有未来 StepIR-producing patch：
  默认必须遵守 same evidence stamping contract；
  默认被 unified evidence predicate 支持；
  默认被 tests / audit 阻止遗漏 evidence。
```

一句话验收：

> `user_confirmed_repair` 成为 compiler authority 层的统一 confirmed evidence，而不是某几个 checker 的局部特殊判断。
