# SPL Editing Repair Drafting Subsystem PM 审核准则

本文档用于审核 [`spl_editing_repair_drafting_subsystem_implementation_plan_zh.md`](spl_editing_repair_drafting_subsystem_implementation_plan_zh.md) 中 Release 1 的编码实施成果。

审核范围：

```text
Release 1:
  RD0-RD7
  Release 1 Freeze

不属于本轮审核完成条件:
  RD8-RD13
  missing_handler provider migration
  missing_output_producer provider migration
  REQUEST_INPUT.value_target provider migration
  bounded LLM production enablement
  full platform provider migration cleanup
```

PM 审核目标不是确认“代码能跑”，而是确认实现没有破坏 SPL Editing 的 authority chain：

```text
UserRepairInput
-> RepairDraftingSubsystem
-> InferredRepairDraft
-> Admission / DirectiveBridge
-> MaterializedPreview
-> Apply
-> Verification
```

Drafting 层只能帮助理解用户输入和生成 typed draft，不能成为 repair authority。

---

## 1. 审核判定规则

每个阶段审核结论只能是：

```text
pass
conditional_pass
fail
```

### 1.1 pass

满足全部条件：

1. 无 P0。
2. 无未关闭 P1。
3. 阶段验收测试真实运行并通过。
4. 阶段 artifact / review report 可复验。
5. 未扩大阶段范围。
6. 未引入未批准 LLM / semantic fallback / materialization authority。

### 1.2 conditional_pass

仅允许以下情况：

1. 只存在 P2。
2. P2 不影响 authority chain、用户可见行为、E2E、后续阶段输入。
3. 已记录 owner、修复阶段、风险说明。

### 1.3 fail

任一条件成立即 fail：

1. 存在 P0。
2. 存在未关闭 P1。
3. 测试未运行却声称通过。
4. 缺少必须 artifact。
5. 使用 skip / xfail 掩盖目标行为。
6. 实现越过当前 phase 边界。
7. Drafting 层写 overlay / snapshot / evidence。
8. Drafting 层生成 patch payload / IR / MaterializationPlan。
9. provider 缺失时 fallback generic LLM。
10. Release 1 被 RD8-RD13 反向阻塞。

---

## 2. Finding 严重级别

### 2.1 P0：必须阻断

以下问题必须阻断合入：

```text
DraftingSubsystem 构造 IR / patch payload / MaterializationPlan
DraftingSubsystem 写 overlay / snapshot / repair evidence
provider dispatch 只靠 diagnostic.kind
provider identity 使用 patch_type 作为语义 key
patch_type 选择 semantic provider
free_text 直接进入 patch payload
FieldInference.value 接受 raw dict / object
StoredRepairDraft 写入 artifact snapshot
stale draft 可进入 Admission
materialized_preview_accepted=False 仍可 apply
no provider fallback 到 generic LLM
LLM 输出 patch payload / IR-like object 被接受
RD7 未经 Admission/Materialization/Verification 直接 apply
Worker Delegation draft-first 伪装成旧 form-first
Release 1 默认路径依赖 RD8-RD13
```

### 2.2 P1：默认阻断

以下问题默认阻断，除非 PM 明确降级：

```text
缺少阶段 required test
缺少 review artifact manifest
DTO serialization 不稳定
provider trace / evidence_refs / confidence 缺失
DraftPreview 展示 final IDs
MaterializedPreview 与 apply 后结果不一致
CLI/API 使用 display index 作为后端 identity
unknown ref 未在 Admission 前拒绝
additional_instruction 可补 required field
existing missing_handler / missing_output_producer path 回退
Worker Delegation v2 negative tests 回退
Release 1 Freeze 缺真实 E2E artifact
```

### 2.3 P2：可延后

以下问题可作为 P2：

```text
文档措辞不够清楚但不影响实现
artifact 文件名不够统一但可定位
非生产路径注释缺少 remove-after 标记
测试名称不够精确但断言有效
CLI 文案可读性需优化但不影响语义
```

---

## 3. 全局审核命令

每个阶段至少运行：

```powershell
git status --short
git diff --check
```

阶段相关测试必须使用 repo-local Python：

```powershell
.venv\Scripts\python.exe -m pytest <phase-test-targets> -q
```

建议 lint 范围：

```powershell
.venv\Scripts\ruff check <touched-src-and-test-paths>
```

Release 1 Freeze 必须额外运行：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/compiler/spl_editing tests/integration/compiler/spl_editing -q
python examples/output/spl_editing_demo/run_demo.py --run demo --e2e-worker-delegation
```

如果当前 checkout 不支持上述 exact demo flag，提交方必须提供等价真实 demo E2E 命令，并说明差异。

---

## 4. 反模式扫描

每个阶段审核建议运行：

```powershell
rg -n "generic.*LLM|confirmed|patch_payload|StepIR|BlockIR|WorkerIR|WorkerHandoffIR|MaterializationPlan|diagnostic\.message|display index|skip|xfail" src tests docs
```

命中项必须逐条解释。

允许命中：

```text
文档中作为禁止项出现
既有 legacy path 且本 phase 未触达
materialization / patch / verifier 层合法构造 IR
测试中断言 forbidden behavior
```

不允许命中：

```text
src/nl2spl/compiler/spl_editing/drafting/ 下构造 IR
drafting provider 中出现 patch_payload
service 默认路径 fallback generic LLM
新增测试 skip / xfail
provider 从 diagnostic.message 解析 materialization fact
```

---

## 5. 阶段审核准则

## 5.1 RD0：Baseline 与 Characterization

### 必须核查

1. RD0 不修改生产代码。
2. Baseline 覆盖：
   - Worker Delegation v2 define-child 当前 E2E。
   - missing_handler 当前 path。
   - missing_output_producer 当前 path。
   - no-provider 当前行为。
3. Baseline 测试在当前代码上通过。
4. 没有把未来目标行为写成失败测试。

### 阻断项

```text
生产代码 diff
skip / xfail
baseline 只覆盖 happy path
未记录当前用户交互问题
```

### 必须证据

```text
artifacts/reviews/repair_drafting/RD0/
  review_report.md
  pytest_output.txt
  manifest.json
```

---

## 5.2 RD1：Common Model 与 Serialization Contract

### 必须核查

1. DTO frozen / immutable。
2. `UserRepairInput` 使用：
   - `draft_accepted`
   - `materialized_preview_accepted`
3. 不存在模糊 `confirmed` 字段。
4. `RepairFieldValue` 是 typed union。
5. `StoredRepairDraft` 不包含 overlay / evidence authority 字段。
6. Serialization round-trip 稳定。

### 阻断项

```text
RepairFieldValue 接受 object / Any raw payload
UserRepairInput.confirmed
DTO 中出现 patch_payload / materialization_plan / raw_ir
draft model import materialization / patch module
```

### 必须证据

```text
test_model_contract.py
test_value_serialization.py
反模式扫描输出
```

---

## 5.3 RD2：Draft Store 与 Staleness Contract

### 必须核查

1. Draft store key 是：

```text
session_id + artifact_snapshot_id + overlay_version + draft_id
```

2. overlay_version / snapshot / session / issue / option mismatch 均 stale。
3. stale draft 在 Admission 前拒绝。
4. draft store 不写 overlay / snapshot / evidence。

### 阻断项

```text
StoredRepairDraft 写入 snapshot metadata
stale draft 可 accept
draft_id collision 静默覆盖
为了持久化 draft 创建 overlay event
```

### 必须证据

```text
test_draft_store.py
test_draft_staleness.py
覆盖 stale negative matrix
```

---

## 5.4 RD3：Provider Registry 与 Service Shell

### 必须核查

1. Provider identity key 是：

```text
(affordance_id, strategy_id, option_id)
```

2. `patch_type` 只做 compatibility check。
3. no-provider 返回 drafting unavailable。
4. no-provider 不调用 LLM。
5. registry 不决定 repair option capability。

### 阻断项

```text
patch_type 参与 provider identity
diagnostic.kind 单独 resolve provider
provider 缺失 fallback generic LLM
registry 修改 RepairCatalog 行为
service 调 Admission / Materialization
```

### 必须证据

```text
test_provider_registry.py
test_drafting_service.py
duplicate provider / incompatible patch type / no provider tests
```

---

## 5.5 RD4：Typed Context View Layer

### 必须核查

1. Views 是 read-only projection。
2. Views 只从结构化 artifact / target / selectable refs / ProducerIndex 等读取。
3. Views 不解析：
   - diagnostic message
   - UI display text
   - rendered SPL
4. Worker delegation view 不重新决定 API / worker promotion authority。
5. Exception flow facts 来自 structured target facts。

### 阻断项

```text
view 解析 diagnostic.message 作为 materialization fact
view 调 LLM
view 写 overlay
view 返回 raw variable names as authority
view 重新判断 repair strategy
```

### 必须证据

```text
tests/unit/compiler/spl_editing/drafting/views/
每个 view 的 authority source 测试
```

---

## 5.6 RD5：Admission / DirectiveBridge

### 必须核查

1. Admission bridge 是 draft 进入 repair directive 的唯一通道。
2. 必须验证：
   - staleness
   - provider scope
   - typed value schema
   - selected refs
   - new facts
   - placement policy
   - strategy option identity
3. `draft_accepted=False` 不能进入 materialized preview。
4. `materialized_preview_accepted=False` 不能 apply。
5. `additional_instruction` 不能补 required structured fields。

### 阻断项

```text
provider 绕过 Admission bridge
raw dict value accepted
unknown ref accepted
additional_instruction 覆盖 selected refs
draft acceptance 与 materialized preview acceptance 混用
```

### 必须证据

```text
tests/unit/compiler/spl_editing/drafting/admission/
stale / unknown ref / unrelated value / acceptance gate negative tests
```

---

## 5.7 RD6：Presentation / CLI / Service API Integration

### 必须核查

1. 后端调用使用 stable identity：
   - `issue_id`
   - `option_id`
   - `draft_id`
   - `preview_id`
   - `revision_token`
2. display index 只用于 UI 展示。
3. no-provider 时显示 drafting unavailable，但不破坏 existing repair path。
4. non-editable issue 不能 create draft。
5. stale revision rejected。

### 阻断项

```text
使用 option index 作为 service identity
no-provider 变成 hard crash
non-editable issue 可 create draft
未迁移 issue 的原 repair path 消失
CLI 默认进入 RD8-RD13 provider path
```

### 必须证据

```text
test_drafting_presentation.py
CLI smoke test output
display reorder negative test
```

---

## 5.8 RD7：WorkerDelegationInferenceProvider

### 必须核查

1. Provider 只支持：

```text
worker_delegation.complete_closure.v2 / define_child_worker
```

2. Provider 推断：
   - responsibility
   - selected input refs
   - output draft
   - placement intent
   - result binding
   - explicit none semantics
3. 用户默认不再填写：
   - `placement_ref`
   - handoff binding
   - invoke output
   - technical result_usage object
4. 所有 inferred fields 有：
   - confidence
   - evidence_refs
   - trace
5. Low confidence 返回 clarification，不编造字段。
6. API-owned span 不得成为 child-worker-owned span。
7. 最终仍走 existing Worker Delegation v2 Admission / Materialization / Lane B Verification。

### 阻断项

```text
provider 构造 WorkerIR / StepIR / WorkerHandoffIR
provider 直接生成 patch payload
unknown ref 通过
required output gap 被自动降级为 parent-local temporary
placement 从 raw step text 解析
用户仍被要求填写技术字段
Lane B verification 被跳过
```

### 必须证据

```text
test_worker_delegation_provider.py
test_worker_delegation_draft_flow.py
real demo E2E output
draft / trace / materialized preview / verification artifact bundle
```

---

## 6. Release 1 Freeze 审核

Release 1 Freeze 是本轮最终验收。RD8-RD13 未完成不得成为拒绝 Release 1 的理由。

### 6.1 必须通过

1. RD0-RD7 每阶段均为 pass 或已接受的 conditional_pass。
2. `define_child_worker` draft-first E2E accepted。
3. Worker Delegation v2 negative tests 不回退。
4. missing_handler existing path 不回退。
5. missing_output_producer existing path 不回退。
6. no-provider 不 fallback generic LLM。
7. Drafting 不写 overlay / snapshot / evidence。
8. Drafting 不生成 patch payload / IR。
9. CLI 用户体验确实减少技术字段。
10. artifact bundle 可复验。
11. 设计文档、实施计划、PM 审核准则已纳入 git tracking，并与实施代码处于同一评审基线。

### 6.2 必须提交

```text
artifacts/reviews/repair_drafting/RD7_freeze/
  review_report.md
  commands.log
  pytest_output.txt
  ruff_output.txt
  diff_check_output.txt
  manifest.json
  worker_delegation_draft_flow/
    user_input.json
    stored_draft.json
    inferred_draft.json
    draft_preview.txt
    materialized_preview.json
    verification_result.json
    rendered_spl_after.txt
    diagnostic_diff.json
```

### 6.3 阻断项

```text
RD8-RD13 被做成 Release 1 依赖
missing_handler / missing_output_producer 被迁移但无单独 gate
LLM 默认进入 RD7 provider
old form-first path 和 draft-first path 同时生成 suggestion
E2E 只跑 unit test，没有真实 demo artifact
```

---

## 7. PM Review Report 格式

每个阶段提交必须包含：

```markdown
# RD<N> PM Review Report

Verdict: pass | conditional_pass | fail

## Scope
- Planned phase:
- Files changed:
- Out-of-scope changes:

## Evidence
- Tests:
- Ruff:
- git diff --check:
- Demo/E2E:
- Artifacts:

## Findings
### P0
- none

### P1
- none

### P2
- ...

## Authority Boundary Check
- Drafting writes overlay/snapshot/evidence: yes/no
- Drafting constructs IR/patch payload: yes/no
- Provider identity uses affordance/strategy/option: yes/no
- patch_type only compatibility: yes/no
- no generic LLM fallback: yes/no

## Residual Risk
- ...

## PM Decision
- approved / rejected / needs rework
```

口头“已通过”不接受。没有 P0/P1 也必须显式写 `none`。

---

## 8. 最终审核口径

本准则的最终判断口径：

```text
Release 1 readiness:
  RD0-RD7 + Release 1 Freeze。

Post-MVP roadmap:
  RD8-RD13 只作为越界和未来扩展检查。

Bounded LLM:
  未经过 Bounded LLM Enablement 前，不能进入生产默认路径。
```

如果实现者试图用“完整平台未来会处理”来解释 RD0-RD7 的缺陷，PM 应判定为 fail。Release 1 必须独立闭合。
