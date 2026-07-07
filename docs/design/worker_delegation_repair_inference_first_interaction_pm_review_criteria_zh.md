# Worker Delegation Repair Inference First Interaction PM 审核准则

本文档用于审核 [`worker_delegation_repair_inference_first_interaction_implementation_plan_zh.md`](worker_delegation_repair_inference_first_interaction_implementation_plan_zh.md) 中 WDI0-WDI7 的编码实施成果。

审核目标不是确认“推断看起来更智能”，而是确认 Worker Delegation inference 在提升用户体验的同时，没有破坏 SPL Editing 既有 authority chain：

```text
UserRepairInput
-> RepairDraftingSubsystem
-> WorkerDelegationInferenceProvider
-> InferredRepairDraft
-> DraftAdmissionBridge
-> existing Worker Delegation v2 directive / materialized preview
-> Apply
-> Lane B verification
```

Drafting / inference 层只能生成 typed draft、confidence、evidence refs、trace 和 clarification；不能成为 Admission、Materialization、Verification 或 compiler authority。

---

## 1. 审核范围

本轮审核范围：

```text
WDI0  当前实现基线与差距锁定
WDI1  Typed View Hardening
WDI2  Responsibility Inference 与 Clarification
WDI3  Input Ref Inference
WDI4  Output / Result Binding Inference
WDI5  Dependency-aware Placement Inference
WDI6  Draft Preview UX 与 CLI Prompt Cleanup
WDI7  Admission / Verification Negative Matrix
```

不属于本轮完成条件：

```text
missing_handler provider migration
missing_output_producer provider migration
REQUEST_INPUT.value_target provider migration
production default LLM inference
Output Semantic Match Policy Gate
bounded LLM typed-plan enablement
Worker Delegation v2 materializer / verifier rewrite
Stage 3.5 / Stage 5 / Stage 7 pipeline rewrite
```

如果实现触及以上内容，必须作为单独设计/计划提交，不能混入 WDI phase。

---

## 2. 审核结论

每个阶段审核结论只能是：

```text
pass
conditional_pass
fail
```

### 2.1 pass

必须同时满足：

1. 无 P0。
2. 无未关闭 P1。
3. 阶段测试真实运行并通过。
4. 阶段 artifact / review report / manifest 可复验。
5. 未扩大阶段范围。
6. 未引入未批准 LLM / semantic threshold / materialization authority。
7. 相关 negative tests 覆盖真实拒绝路径，而不是只断言 UI 文案。

### 2.2 conditional_pass

仅允许以下情况：

1. 只存在 P2。
2. P2 不影响 authority chain、用户可见行为、E2E、后续阶段输入。
3. P2 已记录 owner、修复阶段、风险说明。

### 2.3 fail

任一条件成立即 fail：

1. 存在 P0。
2. 存在未关闭 P1。
3. 测试未运行却声称通过。
4. 缺少必须 artifact 或 manifest。
5. 使用 skip / xfail 掩盖目标行为。
6. 实现越过当前 phase 可编辑范围。
7. Inference provider 构造 IR / patch payload / MaterializationPlan。
8. Inference provider 写 overlay / snapshot / repair evidence。
9. provider 缺失时 fallback generic LLM。
10. DraftPreview 展示 final materialization IDs。

---

## 3. 严重级别

### 3.1 P0：必须阻断

以下问题必须阻断合入：

```text
Inference provider 构造 StepIR / BlockIR / WorkerIR / WorkerHandoffIR
Inference provider 生成 patch payload / MaterializationPlan
Inference provider 写 overlay / snapshot / repair evidence
provider identity 不使用 (affordance_id, strategy_id, option_id)
patch_type 被用作 semantic provider identity
provider 从 diagnostic.message / UI display text / rendered SPL 解析 facts
SelectableRefSet 被绕过，raw variable name 进入 draft 或 directive
NewOutputAdmission 被绕过，free_text 直接创建 output/binding
required output gap 被 silent downgrade 成 parent-local temporary
API-owned span 成为 child-worker-owned evidence
DraftPreview 被当作可 apply preview
materialized_preview_accepted=False 仍可 apply
no provider fallback 到 generic LLM
新增 production LLM inference 未经过 gate
```

### 3.2 P1：默认阻断

以下问题默认阻断，除非 PM 明确降级：

```text
缺少阶段 required test
缺少 review artifact manifest
non-blocked field 缺 confidence / evidence_refs / trace
policy evidence / user intent evidence 被伪装成 source evidence
typed view 返回 object / Any / raw IR 作为 provider authority
provider 使用 cast(Any, ...)、vars(...)、__dict__ 绕过 DTO
DraftPreview advanced details 展示 final handoff_id / invoke step id / block id
placement clarification 要求普通用户选择 raw placement_ref / step_id / block_id
文本相似度 threshold 或 LLM semantic match 未经 gate 出现在 WDI0-WDI7
unknown ref 未在 Admission 前拒绝
ambiguous responsibility 默认 both
keep_in_main_flow / missing_handler / missing_output_producer existing path 回退
Worker Delegation v2 E2E 回退
```

### 3.3 P2：可延后

以下问题可作为 P2：

```text
文档措辞不够清楚但不影响实现
artifact 文件名不够统一但可定位
测试名称不够精确但断言有效
CLI 文案可读性仍可优化但不影响语义
review report 缺少非关键截图或摘要
```

---

## 4. 全局审核命令

每个阶段至少运行：

```powershell
git status --short
git diff --check
```

阶段测试必须使用 repo-local Python：

```powershell
.venv\Scripts\python.exe -m pytest <phase-test-targets> -q
```

建议 lint 范围：

```powershell
.venv\Scripts\ruff check <touched-src-and-test-paths>
```

最终 WDI7 Freeze 必须额外运行：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/compiler/spl_editing tests/integration/compiler/spl_editing -q
python examples/output/spl_editing_demo/run_demo.py --run demo --e2e-worker-delegation
```

如果当前 checkout 不支持上述 exact demo flag，提交方必须提供等价真实 demo E2E 命令，并说明差异。

---

## 5. 全局反模式扫描

每个阶段建议运行：

```powershell
rg -n "tuple\\[object|-> object|Any|cast\\(|getattr\\(|__dict__|vars\\(|diagnostic\\.message|patch_payload|StepIR|BlockIR|WorkerIR|WorkerHandoffIR|MaterializationPlan|generic.*LLM|semantic.*threshold|placement_ref|step_id|block_id|input_empty_semantics|result_usage|skip|xfail" src/nl2spl/compiler/spl_editing/drafting src/nl2spl/compiler/spl_editing/presentation tests/unit/compiler/spl_editing/drafting tests/integration/compiler/spl_editing
```

命中项必须逐条解释。

允许命中：

```text
文档中作为禁止项出现
测试中断言 forbidden behavior
materialization / patch / verifier 层既有合法 IR 构造
typed view implementation 中经过解释且没有作为 provider authority 暴露的 internal adapter
```

不允许命中：

```text
drafting provider 中构造 IR / patch payload / MaterializationPlan
drafting provider 中通过 Any / cast / __dict__ 绕过 typed DTO
provider 从 diagnostic.message / UI display text / rendered SPL 解析 facts
新增测试 skip / xfail
WDI0-WDI7 默认路径依赖 generic LLM
普通用户交互暴露 raw technical anchor
```

---

## 6. 证据包要求

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

如果 phase 生成或修改 draft / preview / demo artifacts，还必须包含：

```text
draft_sample.json
draft_preview.txt
validation_result.json
negative_case_summary.json
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

## 7. Phase WDI0 审核准则：当前实现基线与差距锁定

### 必须核查

1. WDI0 没有生产代码 diff。
2. RD7 Freeze manifest 存在并可读。
3. `release1_freeze_verdict` 为 pass 或 accepted conditional_pass。
4. WorkerDelegationInferenceProvider baseline E2E artifact 存在。
5. Characterization 覆盖：
   - responsibility from free_text evidence。
   - input refs inference。
   - output draft inference。
   - placement 默认行为。
   - result binding target 选择。
   - DraftPreview 是否展示 internal refs。
   - low-confidence clarification。
6. WDI0 gaps 记录在 `review_report.md`，没有直接修生产行为。

### 阻断项

```text
WDI0 修改生产代码
未核查 RD7 Freeze artifact
把 Release 1 已完成作为口头前提
用 skip / xfail 表达未来目标行为
把 missing_handler / missing_output_producer 纳入本 phase
```

### 必须证据

```text
release1_freeze_manifest_ref
release1_worker_delegation_e2e_ref
characterization pytest output
gap list
git diff --check output
```

---

## 8. Phase WDI1 审核准则：Typed View Hardening

### 必须核查

1. Provider 只消费 typed view DTO。
2. View 只做 read-only projection。
3. View methods 不返回 `tuple[object, ...]` 或 `object` 作为 provider authority。
4. `SelectableRefView`、`PlacementStepView`、`OutputDemandItemView`、`PromotionCandidateDraftView` 的字段稳定、可序列化。
5. Provider 未访问 raw `SelectableRef`、raw `StepIR`、raw `WorkerIR`。
6. `Any` / `cast(` / `getattr(` / `__dict__` / `vars(` 命中项有明确合规解释。

### 阻断项

```text
typed DTO 只是包装，provider 仍读取 raw object
provider 通过 Any / cast / __dict__ 绕过 DTO
view 解析 diagnostic.message / UI text / rendered SPL
view 写入 pipeline artifact
```

### 必须证据

```text
typed view contract tests
anti-pattern scan output
RD7 E2E no-regression output
```

---

## 9. Phase WDI2 审核准则：Responsibility Inference 与 Clarification

### 必须核查

1. `user_input:free_text` 被标记为 user-confirmed intent evidence，不是 source-span evidence。
2. source-backed single candidate 使用 source span evidence。
3. multi-candidate 不默认 both。
4. ambiguous candidate 产生面向用户的 clarification。
5. API-owned spans 不进入 responsibility evidence refs。
6. blocked responsibility 不进入 Admission。

### 阻断项

```text
free_text 被伪装成 source-backed task boundary
关键词 fallback 决定 child worker responsibility
从 diagnostic.message 解析 responsibility
ambiguous “source gathering or template matching” 默认 both
blocked field 仍进入 Admission
```

### 必须证据

```text
responsibility inference unit tests
clarification sample
field/trace evidence coverage sample
negative API-owned span sample
```

---

## 10. Phase WDI3 审核准则：Input Ref Inference

### 必须核查

1. `SelectableRefSet` 仍是 input refs 唯一 authority。
2. 只选择 `ref_role == selectable_input`。
3. out-of-scope ref 不可选。
4. target output ref 不可被当 input。
5. no required input 时使用 typed explicit none，并记录 policy evidence。
6. ambiguous inputs 返回 clarification。
7. draft JSON 不出现 raw variable name。

### 阻断项

```text
provider 自己创建 selected_ref_id
raw variable name 进入 draft field
unknown ref 未被拒绝
target_output 被当作 input
ExplicitNoneValue 缺少 policy evidence
```

### 必须证据

```text
input ref inference unit tests
unknown ref negative test
draft JSON sample
Admission accepted sample
```

---

## 11. Phase WDI4 审核准则：Output / Result Binding Inference

### 必须核查

1. required output gap 存在时绑定 required output，不 silent downgrade。
2. downstream consumer 存在时绑定 consumer-visible parent symbol。
3. parent-local temporary 只在无 required output、无 downstream required consumer、无 declared alias、且不导出 `[OUTPUTS]` 时允许。
4. parent-local temporary 不触发 `missing_output_producer`。
5. NewOutputAdmission 仍是 new child output 唯一 admission authority。
6. Release WDI0-WDI7 只允许 deterministic bounded match：
   - canonical id。
   - required output canonical name。
   - approved alias table。
   - normalized symbol alias。
   - candidate possible_outputs exact/normalized match。
7. free_text 相似表达不得绕过 required output / alias policy。

### 阻断项

```text
required output gap 被 silent downgrade 成 parent-local temporary
provider 直接 admission 新 output / binding
新增文本相似度 threshold 未经 gate
LLM semantic match 未经 gate
free_text 直接生成 binding
ProducerIndex diagnostic 被 suppress
```

### 必须证据

```text
output binding inference unit tests
required output binding sample
parent-local temporary negative/positive samples
ProducerIndex closure E2E output
```

---

## 12. Phase WDI5 审核准则：Dependency-aware Placement Inference

### 必须核查

1. placement 不再固定 append。
2. first consumer 前 placement 有 trace。
3. selected input refs 在 placement 前可用。
4. invoke output 在 first consumer 前可用。
5. 不跨 exception-flow / alternative-flow 错误移动。
6. 不把 API-owned span 变成 child-worker-owned。
7. 不制造 cycle。
8. placement anchor 属于 parent worker scope。
9. precondition failure 默认 blocked draft，而不是要求用户选择 technical anchor。
10. user-facing clarification 只用于业务决策缺失，不能要求 raw `placement_ref` / `step_id` / `block_id`。

### 阻断项

```text
provider 在 Stage 5/7 artifacts 中直接重排或写入
placement clarification 要求普通用户选择 technical anchor
input unavailable 仍选择该 anchor
cross-flow invalid placement 进入 Admission
API-owned span placement 被接受
```

### 必须证据

```text
placement inference unit tests
first consumer trace sample
blocked precondition sample
non-technical clarification sample
Lane B no-regression output
```

---

## 13. Phase WDI6 审核准则：Draft Preview UX 与 CLI Prompt Cleanup

### 必须核查

1. CLI 不再询问 `placement_ref`、`input_empty_semantics`、`result_usage`、handoff binding、invoke output。
2. 用户可通过 Enter 接受 high-confidence draft。
3. multiline subject summary 不破坏 prompt。
4. DraftPreview 默认只展示用户可理解内容：
   - Create child worker。
   - Use inputs。
   - Return。
   - Insert。
   - Bind result。
   - Clarification questions。
5. DraftPreview advanced details 只展示 intent / policy / expected binding：
   - selected_ref_ids。
   - placement_intent。
   - placement_policy_reason。
   - expected binding target。
   - parent-local temporary intent。
   - verification lane intent。
6. final handoff_id、invoke step id、block id、stage slices、marker refs 只能出现在 MaterializedPreview 或 audit details。

### 阻断项

```text
DraftPreview 展示 final internal IDs
Advanced details 混淆 DraftPreview 与 MaterializedPreview
普通用户默认界面暴露 technical worker contract fields
只是换文案，没有改变 interaction flow
keep_in_main_flow existing path 回退
```

### 必须证据

```text
presentation/CLI tests
draft preview sample
materialized preview sample
prompt sanitization sample
manual or scripted demo output
```

---

## 14. Phase WDI7 审核准则：Admission / Verification Negative Matrix

### 必须核查

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

每个 negative case 必须满足：

1. rejected before overlay 或 verifier rejected。
2. rejected case 不产生 overlay。
3. rejected case 不 suppress diagnostic。
4. failure reason 可审计。

Accepted case 必须满足：

1. Draft accepted。
2. Admission accepted。
3. MaterializedPreview generated。
4. Apply confirmed。
5. Lane B accepted。
6. 原 WORKER_PROMOTION diagnostic resolved。
7. 无新增 `missing_output_producer`、`type_or_contract_ambiguity`、orphan diagnostics。

### 阻断项

```text
negative case 只测试 UI，不测试 Admission/Verifier 拒绝
rejected case 仍产生 overlay
diagnostic 被 suppress 而不是 resolved
accepted case 未跑真实 Lane B
artifact bundle 缺 before/after diagnostics
demo E2E 未运行
```

### 必须证据

```text
negative matrix pytest output
run_demo.py --run demo --e2e-worker-delegation output
worker_delegation_inference_e2e artifact bundle
manifest hash verification
full scoped SPL Editing test output
ruff output
git diff --check output
```

---

## 15. Bounded LLM Gate 审核准则

该 gate 不属于 WDI0-WDI7 完成条件。任何实现如果启用 LLM，必须先提交独立 gate 文档并通过审核。

Gate 审核必须回答：

1. LLM 输入是否包含 raw source text。
2. LLM 输出 schema 是什么。
3. LLM 是否允许输出 selected_ref_ids。
4. unknown refs 如何拒绝。
5. LLM output hash 是否进入 preview seal。
6. deterministic conflict 谁优先。
7. no generic LLM fallback 如何保证。

未通过 gate 前，WDI0-WDI7 中出现 production LLM inference 一律 P0。

---

## 16. 最终冻结审核

WDI7 完成后，最终冻结审核必须确认：

1. WDI0-WDI7 每阶段都有 review report 和 manifest。
2. 所有 P0/P1 已关闭。
3. P2 有 owner 和后续处理计划。
4. 真实 demo E2E 通过。
5. Negative matrix 通过。
6. Existing paths 未回退：
   - `keep_in_main_flow`。
   - `missing_handler`。
   - `missing_output_producer`。
7. Drafting / inference 未构造 IR / patch payload / MaterializationPlan。
8. DraftPreview 与 MaterializedPreview 边界清楚。
9. Required output binding 没有 silent downgrade。
10. API-owned span 没有进入 child-worker-owned evidence。

最终冻结建议命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/compiler/spl_editing tests/integration/compiler/spl_editing -q
.venv\Scripts\ruff check src/nl2spl/compiler/spl_editing/drafting src/nl2spl/compiler/spl_editing/presentation tests/unit/compiler/spl_editing/drafting tests/integration/compiler/spl_editing
python examples/output/spl_editing_demo/run_demo.py --run demo --e2e-worker-delegation
git diff --check
```

---

## 17. PM 审核报告模板

每次阶段提交必须按以下格式输出：

```text
Phase:
Verdict: pass | conditional_pass | fail

Scope:
- touched files:
- explicitly out of scope:

Evidence:
- tests:
- lint:
- diff check:
- demo/e2e:
- artifact bundle:

Findings:
P0:
- none | ...

P1:
- none | ...

P2:
- none | ...

Authority Boundary Check:
- provider IR construction: pass/fail
- patch payload generation: pass/fail
- overlay/snapshot/evidence writes: pass/fail
- SelectableRefSet boundary: pass/fail
- NewOutputAdmission boundary: pass/fail
- DraftPreview vs MaterializedPreview boundary: pass/fail
- Lane B verification boundary: pass/fail

Residual Risks:
- ...

PM Decision:
- approved to proceed to next phase | blocked pending fixes
```

---

## 18. 2026-07-05 修订：Field-confirmed Define-Child Draft PM 审核补充

本节是 WDI PM 审核准则的正式补充。若本节与前文存在冲突，以本节为准。

适用设计：

- [`worker_delegation_child_worker_field_confirmed_draft_design_zh.md`](worker_delegation_child_worker_field_confirmed_draft_design_zh.md)

适用实施计划修订：

- `worker_delegation_repair_inference_first_interaction_implementation_plan_zh.md` 第 17 节。

### 18.1 新增全局 P0

以下问题一律 P0，必须 fail：

```text
新增第二套 draft root / draft store / directive bridge / apply authority
ChildWorkerSemanticDraft 作为独立 persisted draft root
四个 semantic fields 未确认仍进入 DraftAdmissionBridge
Accept-all 未展示四个 fields 却确认 semantic contract
Accept-all 未逐字段记录 confirmation_source=accepted_default
child_inputs 使用 raw variable name 绕过 SelectableRefSet
child_inputs UI 提交 display string 而不是 SelectableRefId
child_output 绕过 NewOutputAdmission
Draft 阶段承诺 admitted_output_id
BusinessLogicValue 直接构造 StepIR / patch payload / MaterializationPlan
Stage 7 command 忽略 confirmed child_inputs / child_output
business_logic 引入未 admission API/tool/resource
WDI0-WDI7 默认路径使用 LLM 语义裁决 business_logic conflict
```

### 18.2 新增全局 P1

以下问题默认 P1，除非 PM 明确降级：

```text
四个 semantic fields 缺 confidence / evidence_refs / trace
confirmation_source 缺失或不是 unconfirmed / accepted_default / user_override
child_inputs 候选未去重
child_inputs 候选展示 raw ref id 作为主要文本
child_output 未区分 display_name / proposed_canonical_name / admitted_output_id
business_logic conflict 规则不可审计
复杂语义冲突 silent accept，未进入 clarification
DraftConfirmationView 与 MaterializedPreview 边界不清
review artifact 缺字段级 confirmation_source
E2E 未覆盖 input/output/business_logic override
```

### 18.3 WDI2 审核补充：child_task

WDI2 通过条件新增：

```text
1. 输出 child_task confirmable field。
2. child_task 有 suggested_value 和 confirmation_source。
3. 多候选任务时不得默认 both，必须 clarification 或用户选择。
4. 不得使用 del_s31 / candidate id / source span id 作为 task text。
```

阻断项：

```text
child_task unconfirmed 仍进入 admission
child_task 来自 diagnostic.message / UI display text
child_task 缺 field-level evidence
```

### 18.4 WDI3 审核补充：child_inputs

WDI3 通过条件新增：

```text
1. 输出 child_inputs confirmable field。
2. 候选项全部来自 SelectableRefSet ref_role=selectable_input。
3. API resource / target_output / placement anchor 不出现在候选列表。
4. UI 展示 label / description / canonical variable name / scope hint。
5. 提交值是 SelectableRefId。
6. Enter / accept-all 记录 accepted_default。
7. 用户 override 记录 user_override。
```

阻断项：

```text
raw variable name 进入 directive
display string 被当作 ref authority
illegal input override 未在 admission 前拒绝
```

### 18.5 WDI4 审核补充：child_output

WDI4 通过条件新增：

```text
1. 输出 child_output confirmable field。
2. 默认 output name 不得是 source span id / candidate id / diagnostic id。
3. Draft 阶段只展示 display_name / proposed_canonical_name。
4. admitted_output_id 只能在 NewOutputAdmission 后出现。
5. result_binding 保持 technical inferred field，不要求普通用户确认。
```

阻断项：

```text
del_s31 作为默认用户可见 output
NewOutputAdmission 被绕过
DraftPreview 承诺 final admitted output id
required output gap silent downgrade
```

### 18.6 新增 WDI4.5 审核准则：Business Logic Inference

WDI4.5 必须审核：

```text
1. 输出 child_business_logic confirmable field。
2. suggested business_logic 可由 child_task + child_inputs + child_output 推导。
3. 用户可 override。
4. accepted_default / user_override 逐字段记录。
5. business_logic 不直接生成 StepIR。
6. business_logic 通过 normalized directive 进入 Stage 7 repair slice。
```

阻断项：

```text
BusinessLogicValue 直接写 StepIR.text
business_logic 缺失仍进入 materialized preview
business_logic 引用未确认 input/output
business_logic 引入未 admission API/tool/resource
自由语义冲突判断未经 LLM gate
```

必须提供测试：

```text
accepted_default business_logic
user_override business_logic
empty business_logic blocked
undeclared ref in business_logic rejected
raw candidate/source id in business_logic rejected
```

### 18.7 WDI5 审核补充：placement remains technical

WDI5 审核必须确认：

```text
1. placement 仍由系统推断。
2. placement 不进入普通用户四字段必确认列表。
3. 普通用户不需要选择 raw placement_ref / step_id / block_id。
4. Placement evidence 仍可审计。
```

阻断项：

```text
CLI 要求普通用户选择 raw placement anchor
Accept-all 隐式确认 placement
placement 推断绕过 dependency / availability check
```

### 18.8 WDI6 审核补充：DraftConfirmationView

WDI6 通过条件新增：

```text
1. DraftPreview / equivalent CLI 展示四个 semantic fields。
2. 每个 field 可接受 suggested value 或 user override。
3. 支持 visible-field accept-all。
4. accept-all 逐字段写 accepted_default。
5. summary confirmation 不替代字段级 confirmation。
6. MaterializedPreview 仍独立展示最终 worker / invoke / binding result。
```

阻断项：

```text
只显示 Use this draft? [Y/n] 作为四字段确认
未显示四字段却允许 accept-all
DraftConfirmationView 展示 final worker_id / handoff_id / step_id
DraftPreview 与 MaterializedPreview 混合
```

### 18.9 WDI7 Negative Matrix 补充

WDI7 必须新增并通过：

```text
unconfirmed child_task -> blocked, no overlay
unconfirmed child_inputs -> blocked, no overlay
unconfirmed child_output -> blocked, no overlay
unconfirmed child_business_logic -> blocked, no overlay
illegal input override -> rejected before materialization
invalid output admission -> rejected before materialization
business_logic undeclared ref -> rejected
business_logic unadmitted API/tool/resource -> rejected
accept-all without visible fields -> rejected
accept-all without field-level accepted_default -> rejected
BusinessLogicValue direct-to-StepIR anti-pattern scan -> no production hit
```

### 18.10 Release Freeze 补充

最终 WDI7 Freeze 必须额外确认：

```text
1. 四个 semantic fields 在 review artifact 中可见。
2. 每个 field 有 confirmation_source。
3. E2E 覆盖全部 accepted_default。
4. E2E 覆盖 input override。
5. E2E 覆盖 output override。
6. E2E 覆盖 business_logic override。
7. 缺任一 field confirmation 时 no overlay。
8. Stage 7 child command 使用 confirmed business_logic / inputs / output。
```

审核报告模板中必须增加：

```text
Field-confirmed draft contract:
  child_task confirmed: pass/fail
  child_inputs confirmed: pass/fail
  child_output confirmed: pass/fail
  child_business_logic confirmed: pass/fail
  accept-all field-level evidence: pass/fail
  business_logic Stage 7 boundary: pass/fail
```

没有 P0/P1 也必须显式写 `none`。不接受口头“已通过”。
