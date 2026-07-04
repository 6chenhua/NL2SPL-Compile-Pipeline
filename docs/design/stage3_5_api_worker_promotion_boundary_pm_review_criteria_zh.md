# Stage 3.5 API / Worker Promotion 边界修复 PM 评审准则

本文档用于评审 `docs/design/stage3_5_api_worker_promotion_boundary_implementation_plan_zh.md` 中 APW0-APW7b 各阶段的编码成果。

评审结论只能是：

```text
pass
conditional_pass
fail
```

默认规则：

```text
存在未关闭 P0 -> fail
存在未关闭 P1 -> fail，除非 PM 明确批准进入下一阶段且该 P1 不影响当前阶段验收
仅存在 P2 -> conditional_pass 或 pass，由 PM 根据风险决定
测试未运行、E2E 证据缺失、artifact 不可复验 -> fail
```

---

## 1. 总评审原则

### 1.1 阶段独立验收

每个 APW phase 必须独立提交、独立验收。禁止以下行为：

```text
1. 用后续 phase 的补丁补当前 phase 的洞。
2. 把 APW7 E2E 通过当作 APW1-APW6 的替代证明。
3. 先合入半成品，再承诺后续修。
4. 通过修改 demo fixture、source text、snapshot id 掩盖问题。
```

### 1.2 Authority chain 不得漂移

评审必须确认以下 authority chain 未被破坏：

```text
External Capability authority
  -> 只产出 WorkerBoundaryExclusionView
  -> 不创建 IRS diagnostic
  -> 不 materialize worker

Stage 3.5
  -> 只消费 exclusion view
  -> 不重新决定 API admission
  -> 不写 PromotionResolutionMarker

WORKER_PROMOTION IRS
  -> 继续以 source-side promotion candidate 为 diagnostic target
  -> 不把 derived child worker 当成未确认 issue subject

SPL Editing apply
  -> 用户确认后才写 PromotionResolutionMarker
  -> 用户确认后才 materialize child worker / handoff / invoke

Lane B compiler authority
  -> 负责最终 normalizer / assembler / IRS / Gate / ProducerIndex /
     DiagnosticDiff / Renderer 验收
```

### 1.3 禁止用展示层修复真实语义问题

以下均为阻断项：

```text
1. 只改 UI label / issue title，让错误不显眼。
2. suppress diagnostic 让 demo 变绿。
3. 从 editable issue list 过滤掉问题，但 underlying artifact 仍错误。
4. 用 confirmed marker 之后的 overlay 证明 baseline 已修好。
```

---

## 2. Severity 定义

### 2.1 P0：必须立即阻断

出现以下任一情况，评审结论为 `fail`：

```text
1. confirmed API invocation span 仍可被 materialize 为 child-worker-owned span。
2. mixed candidate 因包含 API span 被整体删除，residual evidence 静默丢失。
3. Stage 3.5 / IRS / Presentation / preview 写入 PromotionResolutionMarker。
4. 未确认 WORKER_PROMOTION issue 仍展示 derived child worker 为 primary subject。
5. patch verifier 或 presentation suppress compiler diagnostics。
6. DefineChildWorkerClosure accepted 了 result binding 不闭合的 child worker。
7. ProducerIndex / post-normalize IRS / DiagnosticDiff 被绕过或替代。
8. 通过手工改 `examples/output/demo/`、source input、snapshot id 让 E2E 通过。
9. 默认 pytest 中引入 skip / xfail 来掩盖当前阶段失败。
10. 使用不存在的 enum 作为有效实现，例如 `integration_call`。
```

### 2.2 P1：当前阶段阻断，除非 PM 明确豁免

```text
1. WorkerBoundaryExclusionView 依赖完整 ExternalCapabilityIntentPlanIR 的深层对象。
2. SanitizedCandidateResult 只存在于测试，不进入真实 intermediate / artifact / deterministic payload。
3. APW3 validator / materializer 不消费 sanitizer result，而是重新从裸 metadata 推断 residual。
4. Presentation 与 verifier 各写一套 marker validity 判断，且没有共享 helper 或共同测试。
5. marker target match 使用 substring / contains / startswith，而不是 exact match。
6. GenericEvidenceVerifier 承担 closure-specific result binding 业务语义。
7. APW7a baseline E2E 被 repair overlay 污染。
8. artifact bundle 缺 manifest 或 hash 不可复验。
9. 新增 LLM prompt/schema 字段没有 deterministic validator 或负例测试。
10. 触达文件 ruff / diff-check 未通过。
```

### 2.3 P2：非阻断但必须记录

```text
1. 文档注释、变量名、artifact 文件名不够清晰但不影响行为。
2. 测试覆盖充分但断言 message 不够具体。
3. artifact bundle 包含冗余文件。
4. Review output 中缺少局部摘要，但原始证据可追踪。
```

---

## 3. 通用证据要求

每个 phase 提交评审时必须提供：

```text
1. Diff summary：列出新增/修改/删除文件。
2. Scope statement：说明是否严格落在该 phase 可编辑范围内。
3. Prohibited-change statement：说明禁改范围未触碰。
4. Test evidence：命令、结果、失败/警告说明。
5. Negative evidence：该 phase 要求的负例测试清单和结果。
6. Artifact evidence：如果 phase 产出 artifact，提供路径和关键字段摘要。
7. Regression statement：说明前置 phase 验收项是否仍通过。
8. Residual risk：列出未解决但不阻断当前 phase 的风险。
```

如果提交方只给出“全部测试通过”而没有命令、范围、负例、artifact 证据，评审不得通过。

### 3.1 Phase 证据包最小目录结构

每个 APW phase 必须提交一个可复验的证据包。推荐目录结构：

```text
artifacts/reviews/APW<N>/
  review_report.md
  commands.log
  pytest_output.txt
  ruff_output.txt
  diff_check_output.txt
  artifacts/
    <phase-specific-artifact-1>.json
    <phase-specific-artifact-2>.json
  manifest.json
```

要求：

```text
review_report.md:
  必须使用本文档第 15 节格式。

commands.log:
  记录实际运行的命令，不能只写摘要。

pytest_output.txt / ruff_output.txt / diff_check_output.txt:
  如果某 phase 不适用其中某项，必须在 review_report.md 中解释。

artifacts/:
  存放该 phase 的关键 intermediate、before/after、preview、verification、
  audit 或 E2E 产物。

manifest.json:
  记录文件路径、hash、生成命令、生成时间、base snapshot / overlay 信息。
```

证据包路径可以按仓库实际约定调整，但必须满足：

```text
1. reviewer 能从 review_report.md 定位所有证据。
2. manifest hash 可复验。
3. 证据不只存在于聊天记录或临时控制台输出。
```

---

## 4. APW0 评审准则：Current Gap Lock

### 4.1 必须核查的产物

```text
APW0a Current-behavior lock tests
APW0b Target-behavior pending assertions / scenario specs
fixture reader / helper
```

### 4.2 必须通过的检查

1. APW0a 默认测试在当前代码上通过。
2. APW0a 明确锁定真实 artifact：
   - `s16` 是 confirmed API invocation。
   - Stage 3.5 candidate 包含 `s16/s23/s30`。
   - Stage 3.5 decision 当前错误为 `extract_child_worker`。
   - `worker_promotion:del_s31` 当前被展示为 derived child worker。
   - producer binding drift 存在。
3. APW0b 不进入默认 pytest。
4. APW0b 不使用 skip / xfail。
5. 没有修改任何生产代码。

### 4.3 阻断条件

```text
P0: APW0 修改生产路径。
P0: APW0b 目标行为断言进入默认 pytest 并预期失败。
P1: APW0a 使用手写假数据而非真实 demo artifact。
P1: APW0a 只锁定一个问题，遗漏 Stage 3.5 / presentation / producer drift 之一。
```

### 4.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest <APW0 test paths> -q
git diff --name-only
git diff --check
```

---

## 5. APW1 评审准则：WorkerBoundaryExclusionView

### 5.1 必须核查的产物

```text
api_exclusion.py 或等价模块
WorkerBoundaryExclusionView dataclass
view builder
unit tests
demo artifact 构造样例
```

### 5.2 必须通过的检查

1. View 只从结构化 external capability resolver output 读取。
2. confirmed/executable/admitted invocation 才进入 `api_consumed_span_ids`。
3. non-confirmed / non-executable API 不进入 consumed set。
4. `api_call_demand_ids_by_span` 可追踪 API demand。
5. View 不创建 diagnostic、不注册 IRS、不触发 repair。
6. APW1 不改变 Stage 3.5 输出。

### 5.3 阻断条件

```text
P0: View 被注册为 ConstructIRS 或 diagnostic owner。
P0: View 直接 materialize / suppress worker candidate。
P1: View 依赖完整 ExternalCapabilityIntentPlanIR 深层对象，而非收敛边界 DTO。
P1: View 从自然语言文本推断 consumed spans。
```

### 5.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_view.py -q
rg -n "WorkerBoundaryExclusionView|api_consumed_span_ids|ConstructIRS|CompileDiagnostic" src tests
git diff --check
```

---

## 6. Residual Candidate Policy Gate 评审准则

该 gate 必须在 APW1 后、APW2 前完成。

### 6.1 必须核查的产物

```text
APW1 产出的真实 WorkerBoundaryExclusionView payload
Residual Candidate Policy 决策记录
mixed candidate 示例
```

### 6.2 必须回答

1. residual candidate 是否继续送入 Stage 3.5b LLM decision。
2. residual candidate 的 `risks/signals/status` 是否重算。
3. ambiguous residual 是 diagnostic 还是 audit。
4. artifact 如何解释 API span 被移除但 residual 被保留。

### 6.3 阻断条件

```text
P0: 允许 mixed candidate 被整体删除。
P1: gate 只基于文档推演，没有使用 APW1 真实 view payload。
P1: residual ambiguous 行为没有明确规则。
```

---

## 7. APW2 评审准则：Candidate Sanitizer

### 7.1 必须核查的产物

```text
candidate_sanitizer.py 或等价模块
SanitizedCandidateResult 或等价结构化 DTO
API-only / mixed / unchanged / invalid 分支测试
artifact projection 或 deterministic intermediate payload
```

### 7.2 必须通过的检查

1. API-only candidate 产生 `compile_as_call_api` / `call_api`。
2. mixed candidate 只移除 API spans，保留 residual。
3. residual ambiguous 产生 `keep_in_main_worker` + audit reason。
4. `SanitizedCandidateResult` 进入真实 intermediate / artifact / deterministic payload。
5. APW3 可消费该结构判断 residual 是否完成 re-evaluation。
6. 没有修改现有 `WorkerPlanIR` enum。

### 7.3 阻断条件

```text
P0: 存在 if overlap: drop candidate 这类整体删除逻辑。
P0: residual evidence 静默丢失。
P1: SanitizedCandidateResult 只存在于测试，不进入真实运行路径。
P1: sanitizer result 无法被 APW3 validator/materializer guard 消费。
P1: 使用 ad hoc metadata 代替稳定结构化产物。
```

### 7.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_candidate_sanitizer.py -q
rg -n "SanitizedCandidateResult|mixed_trimmed_candidate|api_only_auto_decision|if .*overlap|integration_call" src tests
git diff --check
```

---

## 8. APW3 评审准则：Prompt Context + Decision / Materializer Guard

### 8.1 必须核查的产物

```text
prompt_builder changes
decision_validator changes
materializer guard
stale LLM output negative tests
```

### 8.2 必须通过的检查

1. Prompt 包含 API-consumed spans 和 mixed candidate instruction。
2. Prompt 不是唯一防线。
3. Validator 拒绝 stale enum，例如 `integration_call`。
4. Validator/materializer 拒绝 API-owned `extract_child_worker`。
5. Materializer 不创建 `owned_span_ids` 包含 API-consumed spans 的 child worker。
6. Mixed accepted child decision 缺 residual re-evaluation 时 fail closed。

### 8.3 阻断条件

```text
P0: 只改 prompt，没有 deterministic guard。
P0: stale fixture 可绕过 validator 生成 child worker。
P1: APW3 重新从自然语言或裸 metadata 推断 residual，而非消费 sanitizer result。
P1: materializer guard 与 validator guard 逻辑不一致。
```

### 8.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/stage3_5_worker_boundary_planner/test_api_exclusion_decision_guard.py -q
rg -n "integration_call|compile_as_call_api|api_consumed_span_ids|extract_child_worker" src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner tests
git diff --check
```

---

## 9. APW4 评审准则：WORKER_PROMOTION Subject Projection

### 9.1 必须核查的产物

```text
issue_subject resolver changes
display context changes
worker promotion context changes
subject projection tests
```

### 9.2 必须通过的检查

1. 无 confirmed marker 时，subject 来自 source-side promotion。
2. `derived_child_worker_id` 不再是 presentation truth source。
3. `user_confirmed=false` marker 被忽略。
4. target mismatch marker 被忽略。
5. confirmed marker 才能展示 child worker subject。
6. UI 仍保留 source-side promotion context。

### 9.3 阻断条件

```text
P0: 未确认 WORKER_PROMOTION 仍展示 derived child worker 为 primary subject。
P1: marker target match 使用 substring / contains / startswith。
P1: presentation 和 verifier marker validity 判断开始漂移。
```

### 9.4 共享 helper 要求

若 APW4 已引入 marker validity helper，应为 APW5/APW6 复用做准备。若 APW4 暂不引入 helper，必须在评审说明中列出 APW5 如何收敛到共享 helper。

建议 helper 语义：

```text
is_valid_promotion_resolution_marker(
  marker,
  issue_target_ref,
) -> bool / detailed result

required checks:
  target exact match
  user_confirmed=true
  repair_patch_id present
  materialized refs coherent
```

---

## 10. APW5 评审准则：PromotionResolutionMarker Lifecycle

### 10.1 必须核查的产物

```text
PromotionResolutionMarker model/store
snapshot adapter round-trip
confirmed apply write path
negative lifecycle tests
shared marker validity helper
```

### 10.2 必须通过的检查

1. Marker 只能由 confirmed apply path 写入。
2. Preview dry-run 不持久化 marker。
3. Stage 3.5 / IRS / DiagnosticProjector / Presentation 不写 marker。
4. `user_confirmed=false` marker 被拒绝。
5. `repair_patch_id` 缺失被拒绝。
6. target mismatch 被拒绝。
7. Serializer round-trip 保留 marker 字段。
8. APW4 presentation 与 APW5 verifier/store 复用同一 validity helper 或同一测试矩阵。

### 10.3 阻断条件

```text
P0: Stage 3.5、IRS、presentation 或 preview 可写 marker。
P0: marker-like metadata 可被当成 confirmed marker。
P1: presentation 接受但 verifier 拒绝同一个 marker，或反向漂移。
P1: snapshot round-trip 丢失 marker authority 字段。
```

---

## 11. APW6 评审准则：DefineChildWorkerClosure Result Binding

### 11.1 必须核查的产物

```text
DefineChildWorkerClosureVerifier changes
worker_delegation_v2 / closure slices changes
result binding invariant tests
forced bad apply / compiler authority tests
```

### 11.2 必须通过的检查

1. Marker target 精确等于 issue target。
2. Marker confirmed 且 patch/evidence 可追溯。
3. Child worker、handoff、invoke step 互相引用一致。
4. Child output contract 覆盖 admitted returned results。
5. Handoff output binding 覆盖 child output。
6. Invoke result binding 写入 parent scope。
7. 如果 closure 声称解决 required output，parent variable 必须等于 required output。
8. Unrelated / duplicate / stale materialized refs 被拒绝。
9. Forced bad apply 后 ProducerIndex / DiagnosticDiff 仍能报告 producer gap。

### 11.3 阻断条件

```text
P0: Result binding 不闭合但 Lane B accepted。
P0: ProducerIndex diagnostic 被 suppress。
P1: GenericEvidenceVerifier 承担 closure-specific binding 语义。
P1: 只检查 marker refs，不检查真实 artifact。
```

### 11.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/compiler/spl_editing/patches/test_define_child_worker_closure_verifier.py -q
.venv\Scripts\python.exe -m pytest tests/integration/compiler/spl_editing/test_worker_delegation_result_binding_invariant.py -q
rg -n "GenericEvidenceVerifier|DefineChildWorkerClosureVerifier|materialized_construct_refs|target_worker_promotion" src/nl2spl/compiler/spl_editing tests
```

---

## 12. APW7a 评审准则：Demo Baseline E2E

### 12.1 必须核查的产物

```text
run_demo.py --run demo --list-only output
final_spl.txt
compile diagnostics
stage3_5a/b/c artifacts
worker_boundary_exclusion_view.json
issue inventory
manifest.json with hashes
```

### 12.2 必须通过的检查

1. `s16` 只作为 API invocation materialization authority。
2. `s16` 不在 child worker owned spans 中。
3. `Worker_retrieve_approved_sources` 不因 `s16` 自动生成。
4. `s31` 仍产生 source-side `WORKER_PROMOTION` issue。
5. 未确认 promotion subject 不显示 derived child worker。
6. API deferred validation 仍为 review/deferred，不进入 editable。
7. APW7a 未应用 repair overlay。

### 12.3 阻断条件

```text
P0: APW7a 证据来自用户确认后的 overlay。
P0: baseline 仍存在 s16 API + child worker 双重 materialization。
P1: artifact bundle 缺 Stage 3.5 artifacts 或 issue inventory。
P1: manifest hash 不可复验。
```

### 12.4 审核命令建议

```powershell
.venv\Scripts\python.exe examples/output/spl_editing_demo/run_demo.py --run demo --list-only
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/stage3_5_worker_boundary_planner -q
.venv\Scripts\python.exe -m pytest tests/unit/compiler/spl_editing/presentation tests/integration/compiler/spl_editing -q
ruff check <touched files>
git diff --check
```

---

## 13. APW7b 评审准则：Repair Closure E2E

### 13.1 必须核查的产物

```text
run_demo.py --run demo --e2e-worker-delegation output
before/after final_spl.txt
before/after diagnostics
before/after issue inventory
preview summary
verification result
PromotionResolutionMarker summary
child worker / handoff / invoke / result binding summary
provenance/evidence summary
manifest.json with hashes
IRS audit output
```

### 13.2 必须通过的检查

1. Define child worker Lane B accepted。
2. Keep in main flow Lane B accepted。
3. Negative cases 不产生 overlay。
4. Marker confirmed 且 target exact match。
5. Result binding 到 parent scope / required output producer 闭合。
6. 无新增 missing_output_producer regression。
7. 无新增未豁免 P0/P1 IRS audit finding。

### 13.3 阻断条件

```text
P0: 跳过 Lane B replay。
P0: 通过关闭 diagnostic 让 verification accepted。
P0: Define child worker 或 keep-main-flow 只验证了一个路径。
P1: artifact bundle 没有 before/after 对比。
P1: acceptance bundle 不含 manifest hash。
```

### 13.4 审核命令建议

```powershell
.venv\Scripts\python.exe examples/output/spl_editing_demo/run_demo.py --run demo --e2e-worker-delegation
.venv\Scripts\python.exe -m pytest tests/unit/compiler/spl_editing tests/integration/compiler/spl_editing -q
python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py --scope all --format json
ruff check <touched files>
git diff --check
```

---

## 14. 最终冻结审核

APW0-APW7b 全部完成后，最终审核必须重新跑一组组合验证，不能只引用各阶段历史结果。

### 14.1 必跑命令

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stages/stage3_5_worker_boundary_planner -q
.venv\Scripts\python.exe -m pytest tests/unit/compiler/spl_editing tests/integration/compiler/spl_editing -q
.venv\Scripts\python.exe examples/output/spl_editing_demo/run_demo.py --run demo --list-only
.venv\Scripts\python.exe examples/output/spl_editing_demo/run_demo.py --run demo --e2e-worker-delegation
python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py --scope all --format json
rg -n "integration_call|if .*overlap.*drop|derived_child_worker_id|PromotionResolutionMarker|user_confirmed|target_worker_promotion_ref_id|materialized_construct_refs|GenericEvidenceVerifier|suppress|skip|xfail" src tests docs
ruff check <touched files>
git diff --check
```

反模式扫描命中项不一定是错误，但最终审核报告必须逐条说明：

```text
1. 命中位置。
2. 是否符合本准则允许的语义。
3. 如合规，为什么不是 P0/P1。
4. 如不合规，对应修复或阻断结论。
```

### 14.2 最终通过条件

```text
1. s16 只作为 API invocation materialization authority。
2. s31 作为 worker promotion source signal 保留。
3. 未确认 promotion 不展示 derived child worker。
4. 用户确认后才允许 materialize child worker closure。
5. child closure result binding 到 parent required output producer 全链路闭合。
6. API deferred validation 仍为 review_only。
7. 无新增未豁免 P0/P1 IRS audit finding。
8. acceptance artifacts 可复验。
```

---

## 15. 评审报告格式

每次评审输出建议使用：

```text
Verdict: pass | conditional_pass | fail

Phase:
  APW#

Scope:
  touched files:
  forbidden areas touched: yes/no

P0 findings:
  - ...

P1 findings:
  - ...

P2 findings:
  - ...

Evidence reviewed:
  - commands:
  - artifacts:
  - negative tests:

Required follow-up:
  - ...

Residual risk:
  - ...
```

如果没有 P0/P1，也必须明确写：

```text
P0 findings: none
P1 findings: none
```

---

## 16. 常见错误模式

评审时重点搜索以下模式：

```text
integration_call
if .*overlap.*drop
derived_child_worker_id
PromotionResolutionMarker
user_confirmed
target_worker_promotion_ref_id
materialized_construct_refs
GenericEvidenceVerifier
suppress
skip
xfail
```

这些关键词出现不一定错误，但必须解释其语义是否符合本准则。
