# SPL Editing Worker Delegation Repair Interaction 与 Construct Closure PM 审核准则

日期：2026-07-01  
状态：正式审核基线  
适用对象：P0-P9 编码实施、Checkpoint 合并、最终产品验收  

依据文档：

- [`spl_editing_worker_delegation_repair_interaction_and_closure_design_zh.md`](spl_editing_worker_delegation_repair_interaction_and_closure_design_zh.md)
- [`spl_editing_worker_delegation_repair_interaction_and_closure_implementation_plan_zh.md`](spl_editing_worker_delegation_repair_interaction_and_closure_implementation_plan_zh.md)
- [`../problem/worker_delegation_repair_interaction_contract_gap.md`](../problem/worker_delegation_repair_interaction_contract_gap.md)
- [`../problem/spl_editing_issue_presentation_fact_projection_gap.md`](../problem/spl_editing_issue_presentation_fact_projection_gap.md)

本准则用于 PM 独立审核，不代替设计文档或实施计划。发生冲突时，authority 顺序为：

```text
approved design semantics
-> implementation plan contract freeze
-> this PM review procedure
-> implementation details
```

实现者不得通过修改测试、审核准则或 presentation copy 改变设计语义。

---

## 1. 审核目标

PM 必须证明：

```text
1. 实现真实完成了当前阶段，而不是只增加模型/测试壳。
2. Authority 边界与设计一致，没有产生第二套 truth source。
3. 正向路径能工作，负向路径能 fail closed。
4. 中间阶段没有提前暴露半成品 capability。
5. Preview、apply、evidence、provenance 和 verification 全链路一致。
6. 真实 run_demo 行为符合用户预期，而不只是 stub tests 通过。
7. 未通过删除断言、放宽 verifier、增加 fallback 来换取绿色测试。
```

---

## 2. Verdict 与严重级别

### 2.1 Verdict

```text
pass
  当前阶段所有 mandatory gates 通过，无未解决 P0/P1。

conditional_pass
  无 P0/P1，仅存在明确、非阻断、已登记的 P2；
  不允许以 conditional_pass 提前暴露未闭合 capability。

fail
  存在任一 P0/P1、必需证据缺失、测试不可复现、真实 E2E 缺失、
  scope/authority 偏离或 waiver 不合法。
```

### 2.2 P0：产品语义或 authority 破坏

以下任一情况直接判定 `fail`：

```text
半成品 define-child option 对普通用户显示为 available；
WORKER_PROMOTION 仍暴露 REQUEST_INPUT 修复选项；
Keep-main 或 define-child 使用 Lane A；
CLI/UI 根据 issue kind/patch type 推断表单或 repair semantics；
LLM、handler、interaction provider、patch applier 直接生成/修改任意 IR；
SelectableRefSet 之外的 ref 进入 materialization；
未 admission 的新 symbol/output 进入 IR；
preview 与 apply 结果漂移；
无 confirmation 即产生 accepted overlay/evidence；
resolution marker 按 diagnostic kind 全局 suppress；
marker 无 matching closure 仍使 diagnostic 消失；
generic verifier 被弱化以接受不完整 closure；
真实 E2E 产出错误 Worker、handoff、invoke、binding 或 SPL；
通过解析 diagnostic.message / feedback text 获取 primary materialization facts。
```

### 2.3 P1：生产闭环或必需验收缺失

```text
strategy/option/catalog/runtime linkage 不完整；
required negative tests 缺失；
snapshot/serializer round-trip 缺失；
PromotionResolutionMarker 未持久化或未验证；
temporary result 边界未覆盖 SymbolTable/ProducerIndex/Renderer/provenance；
closure-specific verifier 缺失；
IRS audit 有 unwaived P1；
真实 E2E 或 acceptance artifact bundle 缺失；
P9 未原子切换，legacy/v2 同时暴露；
阶段声明完成但依赖阶段未通过。
```

### 2.4 P2：非阻断 hardening

```text
非关键命名/模块组织偏差；
可读性或重复代码问题但不改变 authority；
额外性能、日志、开发者体验改进；
已覆盖核心路径后的补充边界测试建议。
```

P2 必须有 owner、影响、后续 issue；不能用 P2 标签掩盖 runtime closure 缺失。

---

## 3. 证据标准

### 3.1 不接受的证据

以下内容不能单独证明完成：

```text
“全部测试通过”；
“ruff clean”；
测试数量截图；
walkthrough 总结；
控制台显示 accepted；
只给出修改文件清单；
只给出 happy-path preview；
LLM/开发者对代码行为的文字描述；
只运行 stub LLM E2E；
只修改测试以适应当前实现。
```

### 3.2 每阶段必交 Evidence Pack

实现者必须提交：

```text
phase_id
base commit / reviewed diff boundary
changed files with purpose
design acceptance mapping
exact commands executed
full command results / exit codes
positive tests
negative tests
audit results when registry/IRS changes
known limitations and residual risks
generated acceptance artifacts when applicable
explicit statement of files mechanically formatted
```

### 3.3 PM 必须独立复现

PM 至少独立执行：

```text
review git diff
targeted unit tests
phase negative tests
scoped Ruff
git diff --check
required IRS audit
real demo/E2E for P6-P9
```

不能直接采用实现者声称的测试结果作为 verdict。

---

## 4. 审核流程

### 4.1 Step 1：确认审核边界

```text
当前 phase/checkpoint 是什么？
依赖 phase 是否已 pass？
diff 是否混入无关重构或格式化？
工作树是否包含用户既有改动？
是否明确区分本阶段修改与历史改动？
```

无法确定 diff ownership 时，不得给出 pass。

### 4.2 Step 2：先读代码，再运行测试

PM 必须先检查：

```text
authority 归属
数据流
runtime registration
error paths
fallback
serialization
verification
UI/CLI boundary
```

测试通过不能覆盖代码层 authority 违规。

### 4.3 Step 3：运行 deterministic audits

只要修改 `ConstructIRS`、SlotSpec、repair affordance 或 strategy linkage，必须运行 focused
audit。P9 还必须运行 registry-wide audit。

### 4.4 Step 4：运行正向和负向测试

每个 positive scenario 至少有一个对应 negative scenario。只有 happy path 的阶段不得 pass。

### 4.5 Step 5：检查真实 artifact

P6-P9 必须检查 materialized artifacts，而不只看 `VerificationResult.accepted`。

### 4.6 Step 6：输出 findings-first verdict

报告顺序：

```text
Verdict
P0 findings
P1 findings
P2 findings
Phase acceptance matrix
Commands/results
Artifact evidence
Waivers
Residual risks
```

---

## 5. 全局 Authority Gates

### Gate A：IRS Boundary

必须满足：

```text
IRS 只声明 slot satisfaction/actionability/affordance；
IRS 不创建 directive、option、form、patch、closure 或 IR；
delegation_intent 仍是 source signal，不是新 ConstructIRS；
diagnostic 由真实 WORKER_PROMOTION/CHILD_WORKER/WORKER_HANDOFF/INVOKE_WORKER slots 拥有。
```

### Gate B：Strategy 与 Capability

```text
RepairStrategySpec 是 construct repair 语义 source；
RepairStrategyOptionSpec 是用户 option source；
RepairCatalog/runtime 是 availability source；
patch metadata 不决定 option label/form/closure；
interaction provider 不得提升 availability。
```

### Gate C：Interaction 与 Directive

```text
input shape 由 backend contract 声明；
availability/readiness 正交；
wire JSON 立即转 typed domain objects；
required fields 不可由 additional_instruction 满足；
invalid/stale input 在 preview 前失败。
```

### Gate D：Refs 与 New Facts

```text
existing refs 来自 SelectableRefSet；
new outputs 来自 admission；
名称冲突 fail-fast；
preview/apply identity 稳定；
本轮不新增 parent required output。
```

### Gate E：Stage Authority

```text
Stage 3.5 只写 worker boundary/handoff；
Stage 4 只写 flow；
Stage 5 只写 block/placement；
Stage 7 只写 command/invoke；
PatchApplier 不 direct mutate IR；
单个 facade 不写穿全部 artifacts。
```

### Gate F：Preview、Evidence 与 Verification

```text
preview 不 accepted；
apply 使用 sealed plans/facts；
user confirmation 后才创建 evidence；
generic verifier 只做通用约束；
closure verifier 做 Worker-specific 语义；
Lane B replay 是最终 authority。
```

### Gate G：Presentation/CLI

```text
IssueSubjectView 来自 structured facts；
compiler ID 默认隐藏；
CLI/UI 只渲染 DTO；
display index 不进入 service identity；
普通用户确认结果，不确认内部 strategy/stage IDs。
```

任一 Gate 失败至少是 P1；造成错误产品行为或绕过 authority 时是 P0。

---

## 6. P0 审核准则

### Mandatory code checks

```text
WORKER_PROMOTION affordance 临时只暴露 keep-main-flow；
CreateWorkerHandoffContract 没有被全局删除；
ConvertDelegationIntentToRequestInput 没有被全局删除；
WORKER_PROMOTION patch metadata 不再声明 Lane A；
安全收缩发生在 backend registry/catalog，不是 CLI 隐藏。
```

### Mandatory behavior

```text
普通用户看不到 handoff-only false-positive；
普通用户看不到 Ask user for missing information；
keep-main-flow 仍 available；
can_fix 仍为 true；
P0-P8 define-child API 请求被拒绝。
```

### Mandatory evidence

```text
targeted registry/catalog/presentation tests
negative API test for hidden v2 option
WORKER_PROMOTION IRS audit
demo option list output
```

### Fail conditions

```text
只在 CLI 过滤；
REQUEST_INPUT adapter 全局消失；
define-child 仍可通过 service API 调用；
main-flow 仍走 Lane A。
```

---

## 7. P1 审核准则

### Mandatory code checks

```text
RepairStrategyOptionSpec 是 frozen typed model；
option_id 在 strategy 内唯一；
execution adapters 是 strategy supported adapters 子集；
option model 不含 runtime availability/form fields/service objects；
v2 注册但未用户暴露；
RepairOptionView 携带 option_id/strategy_id。
```

### Mandatory negative tests

```text
duplicate option ID rejected；
unknown interaction contract rejected；
patch metadata cannot override v2 label；
localization/order changes do not change option identity；
partial runtime keeps define-child unavailable。
```

### Fail conditions

```text
option 仍按 patch type 构造；
option index 仍作为 service identity；
v2 提前 available；
strategy registry import CLI/presentation renderer。
```

---

## 8. P2 审核准则

### Mandatory source hierarchy

```text
existing child WorkerPlan facts
-> structured candidate task facts
-> TargetResolver/RepairContext facts
-> source excerpt
-> degraded generic fallback
```

### Mandatory behavior

当前 demo 必须展示用户可理解的：

```text
source gathering or template matching
```

不得展示：

```text
del_s31
worker_promotion:del_s31
虚构的 concrete child worker name
```

### Mandatory negative tests

```text
diagnostic.message 不影响 title/subject；
AI explanation 不覆盖 subject facts；
missing structured facts -> degraded generic title；
internal IDs only in Advanced Details。
```

---

## 9. P3 审核准则

### Mandatory models

```text
RepairInputReadiness including not_evaluated
RepairInteractionView
RepairInputFieldView
RepairInputOptionView
RepairInputSchemaView
RepairInputValidationError
RepairInteractionContractSpec
```

### Schema invariants

```text
structured_object requires object_schema_id；
new_fact_list requires fact_schema_id；
schema IDs resolve exactly once in the view；
schemas are finite, acyclic, versioned；
contract has no capability/lane/handler/applier fields。
```

### Dynamic behavior

```text
define-child -> structured_with_notes；
concrete keep-main -> natural_language + not_required；
ambiguous keep-main -> structured_with_notes + input_required；
unavailable option -> not_evaluated, no actionable submission；
GET interaction creates no session/suggestion/overlay。
```

### Fail conditions

```text
frontend-specific form branching；
provider changes availability；
schema only exists in Python type but not DTO；
unavailable form can be submitted。
```

---

## 10. P4 审核准则

### Mandatory validation order

```text
identity/revision
-> availability
-> contract ID/version
-> typed parse
-> required fields
-> ref role validation
-> empty semantics
-> new fact shape
-> result usage
-> additional instruction boundary
```

### Domain boundary

```text
transport mapping stops at parser；
normalizer/closure/materializer receive typed objects only；
normalized directive is immutable and version-bound；
lane/patch type cannot be supplied by user。
```

### Side-effect checks

Invalid/incomplete draft 必须产生：

```text
no session
no suggestion
no preview
no admitted fact
no overlay
```

### Fail conditions

```text
free text fills missing structured field；
invalid refs deferred to materializer；
stale revision accepted；
normalizer consumes raw dict。
```

---

## 11. P5 审核准则

### Mandatory admission checks

```text
canonicalization
reserved name rejection
scope conflict rejection
data type admissibility
stable provisional ID
evidence linkage
preview/apply identity stability
```

### Parent-local temporary result matrix

必须证明：

```text
存在于 parent worker-local SymbolTable/binding scope；
不创建 REQUIRED_OUTPUT；
不进入 global output contract；
不渲染为 [OUTPUTS]；
不触发 missing_output_producer；
ProducerIndex 不把它提升为 required output demand；
apply 后 provenance origin=user_confirmed_repair。
```

### Fail conditions

```text
自动重命名冲突 symbol；
new output 作为 raw string 进入 IR；
new fact 伪装成 SelectableRef；
同一 repair 新增 parent required output。
```

---

## 12. P6 审核准则

### Mandatory closure result

```text
exactly one MainWorker GENERAL_COMMAND；
task boundary is source-backed/user-confirmed；
no child worker；
no handoff；
no INVOKE_WORKER；
no REQUEST_INPUT；
Lane B replay accepted。
```

### PromotionResolutionMarker

必须检查：

```text
typed model and serializer round-trip；
target promotion ID exact match；
diagnostic group exact match；
resolution_kind=kept_in_main_flow；
marker references real command；
marker evidence belongs to current patch；
marker + closure jointly resolve diagnostic group。
```

### Mandatory negative tests

```text
marker without command rejected；
command without marker does not silently suppress diagnostic；
wrong target/group marker rejected；
Lane A rejected；
orphan child/handoff rejected。
```

### Real E2E requirement

PM 必须运行真实 keep-main flow，不接受仅 stub test。

---

## 13. P7A-P7D 审核准则

### P7A Worker Boundary

```text
new child ID deterministic；
existing matching child reused；
purpose equals normalized responsibility；
input contract from resolved refs；
output contract from admitted outputs；
Stage 3.5 does not create BlockIR/StepIR。
```

### P7B Flow/Block/Command

```text
Stage 4 creates one child main flow；
Stage 5 creates one sequential block；
Stage 7 creates exactly one command；
action text derives from responsibility；
command outputs cover all admitted outputs；
side_effect_only rejected；
extra/unsourced commands rejected。
```

### P7C Handoff/Invoke/Result

```text
handoff directions valid；
invoke references exact handoff；
main-flow placement only；
before/after anchor validated；
result usage binds existing ref or parent-local temporary result；
no parent required output；
resolution marker references full closure。
```

### P7D Capability Registration

```text
closure planner/materializer/verifier bundle registered atomically；
missing any component -> unavailable/not_evaluated；
full bundle -> available/input_required；
marker accepted only after closure-specific verifier passes。
```

### Stage ownership audit

PM 必须检查每个 stage slice 的 diff。任何 slice 写入其他 stage artifact 是 P0/P1，不能以
“closure 方便”接受。

---

## 14. P8 审核准则

### Preview seal

必须覆盖：

```text
strategy/option
interaction contract hash
normalized directive hash
admitted fact hashes
closure plan hash
typed plan hashes
preview construct hash
LLM config hash when used
base revision
```

每个字段修改都必须有 stale-preview negative test。

### Verifier 分工

Generic verifier 只能检查：

```text
revision/hash/linkage
refs/facts identity
evidence coverage
stage authority/write layers
provenance
replay/render artifacts availability
```

Closure-specific verifier 检查：

```text
Define-child graph/contract/command/handoff/invoke/result coherence；
Keep-main no-child/no-handoff/no-invoke/no-request-input invariant；
resolution marker 与 closure 一致性。
```

### Runner anti-bloat check

`VerificationRunner` 不得出现按 Worker patch type 复制 closure 业务规则的大型 if/else。

### Fail conditions

```text
apply rerun divergent LLM generation；
hash mismatch 仍 apply；
generic verifier 吞并 closure verifier；
diagnostic 消失即 accepted；
preview 产生 accepted overlay。
```

---

## 15. P9 审核准则

### Atomic switch

```text
四个 WORKER_PROMOTION slots 都指向 v2；
用户只看到两个 options；
legacy/v2 不并行；
REQUEST_INPUT option absent only from this affordance；
both options Lane B；
option ID is service identity；
index is display only。
```

### CLI/UI source audit

禁止出现：

```text
if issue.kind == ... to choose form
if patch_type == ... to choose fields
raw diagnostic/IRS metadata interpretation
direct RepairCatalog access from renderer
option index passed as backend identity
```

### Required regression

```text
missing handler repair accepted
missing output producer repair accepted
API deferred issue remains non-editable
REQUEST_INPUT legitimate registrations remain
```

### IRS audits

```text
WORKER_PROMOTION
CHILD_WORKER
WORKER_HANDOFF
INVOKE_WORKER
registry-wide scope all
```

任何新增 unwaived P0/P1 均 fail。

---

## 16. Checkpoint Gate

### Checkpoint 1：P0-P3

必须证明：

```text
错误入口已安全收缩；
stable strategy options 已建立；
subject 展示可理解；
interaction DTO 可动态生成；
define-child 不对用户/API开放。
```

不得声称：define-child 功能已可用。

### Checkpoint 2：P4-P6

必须证明：

```text
typed directive closure 完成；
keep-main 真实 Lane B accepted；
resolution marker 可审计；
define-child 仍 unavailable。
```

### Checkpoint 3：P7-P9

必须证明：

```text
define-child full closure 完成；
preview/apply seal 完成；
closure-specific verifiers 完成；
v2 原子切换；
真实 E2E artifact bundles 完整。
```

Checkpoint 不能以“剩余问题将在下一 checkpoint 修复”为由带 P0/P1 合并。

---

## 17. 测试与命令基线

### 17.1 Diff/format

```powershell
git status --short
git diff --stat
git diff --check
```

### 17.2 Unit/integration

至少运行：

```powershell
python -m pytest tests/unit/compiler/spl_editing/worker_delegation_v2 -q
python -m pytest tests/unit/compiler/spl_editing/construct_strategy -q
python -m pytest tests/unit/compiler/spl_editing/presentation -q
python -m pytest tests/integration/compiler/spl_editing -q
```

最终 P9 还必须运行完整 SPL Editing/IRS 相关范围；测试目录不存在时，PM 应按实际新增目录
调整命令并记录，不得跳过对应 contract。

### 17.3 Ruff

```powershell
ruff check `
  src/nl2spl/compiler/spl_editing `
  tests/unit/compiler/spl_editing `
  tests/integration/compiler/spl_editing `
  examples/output/spl_editing_demo
```

### 17.4 IRS audits

```powershell
python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py `
  --construct WORKER_PROMOTION --scope all --format json

python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py `
  --construct CHILD_WORKER --scope all --format json

python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py `
  --construct WORKER_HANDOFF --scope all --format json

python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py `
  --construct INVOKE_WORKER --scope all --format json

python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py `
  --scope all --format json
```

### 17.5 Skill mirror/guardrail

```powershell
python scripts/check_skill_mirrors.py `
  --skill irs-knowledge `
  --skill audit-irs-contract

python -m pytest tests/unit/compiler/irs/test_irs_contract_audit_guardrail.py -q
```

---

## 18. 静态防劣化审查

`rg` 结果是审查线索，不是唯一证明。PM 至少检查：

```powershell
rg -n "CompileDiagnostic\.message|diagnostic\.message" `
  src/nl2spl/compiler/spl_editing

rg -n "option_index|selected_patch_types" `
  src/nl2spl/compiler/spl_editing `
  examples/output/spl_editing_demo

rg -n "ConvertDelegationIntentToRequestInput" `
  src/nl2spl/compiler/construct_registry.py `
  src/nl2spl/compiler/spl_editing

rg -n "StepIR\(|BlockIR\(|WorkerHandoffIR\(|WorkerIR\(" `
  src/nl2spl/compiler/spl_editing/patches `
  src/nl2spl/compiler/spl_editing/stage_slices

rg -n "if .*issue\.kind|if .*patch_type|match .*patch_type" `
  src/nl2spl/compiler/spl_editing/cli.py `
  src/nl2spl/compiler/spl_editing/presentation `
  examples/output/spl_editing_demo
```

判读规则：

```text
Stage slices 中按 owning typed plan 构造 IR 可以合法；
patch applier/CLI/presentation 中 direct IR construction 不合法；
legacy adapter reference 可以存在，但不能进入 WORKER_PROMOTION 用户路径；
category projection 可以读取 issue.kind，但不能据此决定 repair form/capability。
```

推荐为关键边界增加 AST/source-boundary tests，避免只靠人工 grep。

---

## 19. 真实 E2E 审核

### 19.1 Define child worker

PM 必须亲自确认：

```text
issue title shows delegated task candidate；
structured form fields are backend-derived；
preview contains child responsibility/input/output/invocation/result usage；
confirmed apply is Lane B accepted；
final SPL contains child worker and MainWorker invocation；
no undefined refs；
original promotion diagnostic group resolved；
evidence/provenance complete。
```

### 19.2 Keep in main flow

```text
ambiguous task requires task selection；
preview shows MainWorker command；
apply is Lane B accepted；
no new child/handoff/invoke/request-input；
resolution marker matches command；
diagnostic group resolved。
```

### 19.3 Negative

至少实际验证：

```text
missing required field
invalid ref
conflicting new output
new parent required output
stale preview
tampered preview hash
```

所有 negative 场景必须无 accepted overlay。

---

## 20. Acceptance Artifact Bundle 审核

每个真实场景必须包含：

```text
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

PM 检查：

```text
manifest hashes 可重算；
snapshot/overlay identity 连续；
strategy/option/directive/preview/evidence IDs 对齐；
verification lane=B；
before/after diagnostics 与 marker/closure 一致；
typed artifact diff 覆盖 WorkerPlan/Flow/Block/Step/Handoff/SymbolTable；
bundle 位于 test/CI artifact 目录，不覆盖 canonical demo fixture。
```

缺任一核心文件是 P1。

---

## 21. Waiver 政策

### 21.1 不可 waiver

以下不接受 waiver：

```text
用户可见 capability 假阳性；
authority 绕过；
preview/apply drift；
undefined refs/new symbol bypass；
Lane A；
真实 E2E 失败；
无 confirmation apply；
global diagnostic suppression。
```

### 21.2 可申请 waiver

仅限非阻断既有 P1/P2，且不得由本次 change 新增。必须包含：

```text
finding_id
construct
reason
owner
issue_ref
created_at
expires
```

过期、模糊或 wildcard waiver 直接 fail。

---

## 22. Scope 与代码质量审核

### 22.1 Scope drift

以下情况需要停止审核并要求拆分：

```text
无关大范围格式化；
顺便迁移其他 issue families；
重写 Pipeline stages 而非 repair slices；
修改 grammar 或 API placeholder semantics；
删除大量 legacy code 但无静态审计和 regression；
把设计外功能塞进同一 checkpoint。
```

### 22.2 Code structure

拒绝以下形态：

```text
巨型 interaction provider；
巨型 closure materializer；
VerificationRunner 中 patch-specific 大型分支；
全局 template dict 同时承载 capability/form/semantics；
raw dict 贯穿 domain；
CLI 业务判断；
catch-all exception 后静默 fallback；
测试专用 production branch。
```

### 22.3 Tests quality

```text
不得只断言对象存在；
不得只 snapshot 整段文案；
不得通过 monkeypatch 跳过真实 resolver/normalizer/verifier；
不得把 parser/validation failures 统统视为同一错误；
不得用 stub 输出掩盖 prompt/context/runtime 缺失；
必须检查 artifact 和 authority，而不只检查 accepted boolean。
```

---

## 23. PM Phase Acceptance Matrix

PM 每阶段填写：

| Phase | Contract | Positive | Negative | Audit | Real artifact | Scope | Verdict |
|---|---|---|---|---|---|---|---|
| P0 |  |  |  |  |  |  |  |
| P1 |  |  |  | N/A |  |  |  |
| P2 |  |  |  | N/A |  |  |  |
| P3 |  |  |  | N/A |  |  |  |
| P4 |  |  |  | N/A |  |  |  |
| P5 |  |  |  | N/A |  |  |  |
| P6 |  |  |  |  |  |  |  |
| P7A |  |  |  | N/A |  |  |  |
| P7B |  |  |  | N/A |  |  |  |
| P7C |  |  |  | N/A |  |  |  |
| P7D |  |  |  |  |  |  |  |
| P8 |  |  |  | N/A |  |  |  |
| P9 |  |  |  |  |  |  |  |

每个单元格必须填写 evidence path、test node ID、audit result 或具体 `N/A` 原因，不能只写
勾号。

---

## 24. 最终 PM Verdict 模板

```text
Verdict: pass | conditional_pass | fail

Reviewed scope:
- base revision:
- head revision:
- phases/checkpoint:
- changed files:

P0 findings:
- [file:line] finding / impact / required fix

P1 findings:
- [file:line] finding / impact / required fix

P2 findings:
- [file:line] finding / residual risk / owner

Authority matrix:
| concern | expected owner | actual owner | evidence | result |

Phase acceptance matrix:
| phase | contract | positive | negative | audit | artifact | verdict |

Commands independently executed:
- command
  result / exit code

IRS audit:
- construct:
- unwaived findings:
- waivers:

Real E2E:
- define child worker:
- keep in main flow:
- negative scenarios:
- regression scenarios:

Artifact bundles:
- scenario/path/hash verification:

Missing tests:
- ...

Residual risks:
- ...

Required next action:
- merge allowed | fixes required | redesign required
```

---

## 25. 最终通过条件

最终只能在以下条件全部满足时判定 `pass`：

```text
1. P0-P9 和三个 checkpoints 均通过。
2. 无未解决 P0/P1。
3. 所有 authority gates 通过。
4. Focused 与 registry-wide IRS audit 通过，waivers 合法。
5. Unit/integration/negative tests 可独立复现。
6. Define-child 与 keep-main 真实 E2E 均 Lane B accepted。
7. Negative E2E 无 accepted overlay。
8. Acceptance artifact bundles 完整且 hashes 可验证。
9. Missing handler、missing output producer、API deferred regressions 通过。
10. Scoped Ruff 与 git diff --check 通过。
11. CLI/UI 无 semantic inference。
12. Legacy/v2 原子切换完成，无双路径。
13. REQUEST_INPUT adapter 未被全局误删。
14. 代码结构未形成新的巨型 builder/provider/runner。
15. PM 能从代码和 artifacts 独立证明完成，不依赖实现者总结。
```
