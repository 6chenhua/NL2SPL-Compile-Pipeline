# Stage 7 Action-Level Step Extraction PM 评审准则

本文档用于审核 `docs/design/stage7_action_level_step_extraction_implementation_plan_zh.md` 中 P0-P9 各阶段的编码实施成果。

审核目标不是确认“最终 SPL 看起来正确”，而是确认 Stage 7 的 action-level extraction authority chain 没有漂移：

```text
resolved spans / span_by_id
-> APICallDemand / WorkerHandoffIR typed demand
-> APIResidualActionProjector
-> ExecutableActionIR / ActionCoverageReportIR / WorkerActionPlanIR
-> action-owned StepIR materializer
-> SymbolTable / ProducerIndex policy
-> Stage 7 diagnostics
-> Lane / Gate / Renderer downstream consumption
```

Renderer、Gate、IRS、SPL Editing verifier 不得替 Stage 7 修复 action partition、semantic dedup、residual loss 或 duplicate `CALL_API`。

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
3. 阶段测试真实运行并通过。
4. 阶段证据包可复验。
5. 未扩大阶段范围。
6. 未新增未批准 LLM segmentation、keyword fallback、similarity fallback。
7. 未让 Renderer / Gate / IRS / SPL Editing 承担 Stage 7 action partition authority。

### 1.2 conditional_pass

仅允许以下情况：

1. 只存在 P2。
2. P2 不影响当前阶段行为、后续阶段输入、E2E、authority chain。
3. P2 已记录 owner、后续处理阶段、风险说明。

### 1.3 fail

任一条件成立即 fail：

1. 存在 P0。
2. 存在未关闭 P1。
3. 测试未运行却声称通过。
4. 缺少必须 artifact / review report / manifest。
5. 使用 skip / xfail 掩盖目标行为。
6. 越过当前 phase 实施后续 phase。
7. 修改 Renderer / Gate / SPL Editing 来掩盖 Stage 7 duplicate 或 residual loss。
8. 新增 LLM / semantic similarity / keyword heuristic 作为默认 action segmentation。
9. `StepIR.text` 仍作为 residual extraction authority。
10. 通过修改 demo fixture、source input、snapshot id、final SPL golden 掩盖问题。

---

## 2. Finding 严重级别

### 2.1 P0：必须阻断

出现以下任一情况必须判定为 fail：

```text
1. residual extraction 读取 StepIR.text、rendered SPL 或 UI display text。
2. span_by_id 来自 raw Stage 1 spans、canonical text 反查，或非 resolved spans。
3. ActionCoverageReportIR 被注册成 IRS construct、repair affordance 或 materializer input authority。
4. ExecutableActionIR 接受用户输入、写 overlay、调用 LLM 决定 command type。
5. API-only / API-covered operation 仍被 general extractor 生成 duplicate GENERAL_COMMAND。
6. mixed span 的 residual action 被 silent drop。
7. direct APICallDemand 与 WorkerHandoffIR(mode="api_call") 可静默生成两个 CALL_API。
8. no-output residual 被注册为 producer 或触发 missing_output_producer 闭环。
9. CALL_API output binding 在 StepIR / SymbolTable / ProducerIndex 中丢失。
10. ambiguous coverage 强行 materialize CALL_API 或删除唯一 source-backed fallback。
11. Renderer / Gate / SPL Editing verifier 做 semantic dedup 或 suppress Stage 7 diagnostic。
12. P9 blocking 由 Renderer/Gate/SPL Editing 兜底完成，而不是 Stage 7 action coverage authority。
```

### 2.2 P1：默认阻断

以下问题默认阻断，除非 PM 明确降级并记录原因：

```text
1. 新模型序列化不稳定。
2. diagnostic inventory 未使用统一 kind / metadata / visibility。
3. ambiguous/uncovered action 伪造 flow_ref / block_ref。
4. normalized_action_key 使用 lemmatization、stopword removal、embedding 或 similarity threshold。
5. P3 shim 缺 remove-after 生命周期说明。
6. P5 改动 Stage 7 public return type，导致 return type churn 扩散。
7. P7 未拆分 P7a/P7b，prompt contract 和 integration 一次性混合。
8. conflict_key 包含 owning_authority_family，导致 direct/handoff duplicate 检不出。
9. ActionCoverageReportIR diagnostic 只停留在 debug log。
10. 触达文件 ruff / diff-check 未通过。
11. artifact bundle 缺 manifest 或 hash 不可复验。
12. Worker Delegation repair regression 未运行。
```

### 2.3 P2：可延后但必须记录

```text
1. 文档表述不够清晰但不影响实现。
2. 测试名称不够精确但断言有效。
3. artifact 文件名不统一但可定位。
4. 非生产 fallback 注释可读性需要优化。
5. review report 摘要不够精炼但证据完整。
```

---

## 3. 全局证据要求

每个 phase 提交审核时必须提供：

```text
1. Diff summary：新增、修改、删除文件。
2. Scope statement：说明是否严格落在该 phase 可编辑范围内。
3. Prohibited-change statement：说明禁改范围未触碰。
4. Authority boundary statement：说明未让 Renderer/Gate/IRS/SPL Editing 承担 Stage 7 action authority。
5. Test evidence：命令、结果、失败/警告说明。
6. Negative evidence：该 phase 要求的负例测试和结果。
7. Artifact evidence：路径、关键字段、hash。
8. Regression statement：前置 phase 验收项是否仍通过。
9. Residual risk：未解决但不阻断当前 phase 的风险。
```

如果提交方只给出“测试通过”而没有命令、范围、负例、artifact 证据，评审不得通过。

### 3.1 推荐证据包目录

```text
artifacts/reviews/stage7_action_level/P<N>/
  review_report.md
  commands.log
  pytest_output.txt
  ruff_output.txt
  diff_check_output.txt
  artifacts/
    <phase-specific-artifact>.json
  manifest.json
```

P7 拆分阶段建议使用：

```text
artifacts/reviews/stage7_action_level/P7a/
artifacts/reviews/stage7_action_level/P7b/
```

证据包必须满足：

```text
1. review_report.md 能定位所有证据。
2. manifest.json 记录文件 hash、生成命令、生成时间。
3. 证据不只存在于聊天记录或临时控制台输出。
```

---

## 4. 全局审核命令

每个阶段至少运行：

```powershell
git status --short
git diff --check -- src/nl2spl/pipeline/stages/stage7_step_extractor tests docs/design/stage7_action_level_step_extraction_implementation_plan_zh.md docs/design/stage7_action_level_step_extraction_pm_review_criteria_zh.md
```

阶段相关测试必须使用 repo-local Python：

```powershell
.venv\Scripts\python.exe -m pytest <phase-test-targets> -q
```

建议 lint 范围：

```powershell
.venv\Scripts\ruff check src/nl2spl/pipeline/stages/stage7_step_extractor <touched-test-paths>
```

最终冻结建议运行：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7 tests/unit/pipeline tests/integration/pipeline tests/integration/compiler/spl_editing -q
.venv\Scripts\ruff check src/nl2spl/pipeline/stages/stage7_step_extractor tests/unit/pipeline/stage7 tests/integration/pipeline
python examples/output/spl_editing_demo/run_demo.py --run demo --e2e-worker-delegation
```

如果当前 checkout 不支持上述 exact demo flag，提交方必须提供等价真实 demo E2E 命令并说明差异。

---

## 5. 反模式扫描

每个阶段建议运行：

```powershell
rg -n "StepIR\\.text|rendered SPL|diagnostic\\.message|semantic.*dedup|similarity|embedding|lemmatiz|stopword|skip|xfail|suppress|repair_affordance|ConstructIRS|ActionCoverageReportIR|owning_authority_family|CALL_API" src tests docs
```

命中项必须逐条说明是否合规。尤其要检查：

```text
1. StepIR.text 是否只作为 legacy test fixture，而非 residual authority。
2. similarity / embedding 是否只存在于文档禁止项，而非生产逻辑。
3. ActionCoverageReportIR 是否没有进入 IRS / SPL Editing catalog。
4. owning_authority_family 是否没有进入 conflict_key。
5. suppress 是否没有用于隐藏 Stage 7 diagnostic。
```

---

## 6. P0 评审准则：Characterization Tests

### 6.1 必须核查的产物

```text
tests/unit/pipeline/stage7/test_api_call_residual_action_characterization.py
tests/integration/pipeline/test_stage7_action_level_internal_comms_characterization.py
fixture helper / golden target payload
```

### 6.2 必须通过的检查

1. P0 不修改生产代码。
2. 测试证明 `s16` 是 `GENERAL_COMMAND + CALL_API` mixed-action span。
3. 测试证明当前输出存在 duplicate retrieve operation。
4. 测试证明当前输出缺少 executable `Maintain provenance...` residual action。
5. 测试证明 ConstructPlan 已识别 `residual_behavior_span_ids=["s16"]`。
6. target behavior 只能以 helper / golden payload 存在，不作为默认失败断言。
7. 无 skip / xfail。

### 6.3 阻断条件

```text
P0: 修改 Stage 7 生产代码。
P0: 用 final SPL fixture 修改代替 characterization。
P1: 测试只检查文本输出，不追 artifact chain。
P1: 未证明 ConstructPlan residual 已存在。
```

### 6.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7/test_api_call_residual_action_characterization.py tests/integration/pipeline/test_stage7_action_level_internal_comms_characterization.py -q
git diff --check -- tests/unit/pipeline/stage7 tests/integration/pipeline
```

---

## 7. P1 评审准则：Action Model 与确定性序列化

### 7.1 必须核查的产物

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/action_model.py
tests/unit/pipeline/stage7/test_action_model_serialization.py
```

### 7.2 必须通过的检查

1. 新增 `SourceRangeIR`、`ExecutableActionIR`、`ActionCoverageReportIR`、`WorkerActionPlanIR`。
2. `ActionCoverageReportIR.diagnostics` 不使用弱 `tuple[str, ...]`。
3. ambiguous/uncovered action 支持 `flow_ref=None`、`block_ref=None`、`placement_status=unplaced|ambiguous`。
4. `normalized_action_key` 使用固定 canonicalization。
5. 序列化顺序 deterministic。
6. P1 不改变默认 Stage 7 输出。

### 7.3 阻断条件

```text
P0: 新模型进入 IRS registry / repair catalog。
P0: action model 调用 LLM 或接受用户输入。
P1: diagnostics 字段为裸 string tuple。
P1: ambiguous placement 被伪造为任意 flow/block。
P1: canonicalization 引入 similarity / embedding / lemmatization。
```

### 7.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7/test_action_model_serialization.py -q
.venv\Scripts\ruff check src/nl2spl/pipeline/stages/stage7_step_extractor/action_model.py tests/unit/pipeline/stage7/test_action_model_serialization.py
```

---

## 8. P2 评审准则：APIResidualActionProjector

### 8.1 必须核查的产物

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
tests/unit/pipeline/stage7/test_api_residual_action_projector.py
```

### 8.2 必须通过的检查

1. Projector 只读取 `span_by_id[span_id].text`。
2. Projector 只使用 `APICallDemand.operation_coverage` 删除 covered operation。
3. 不读取 `StepIR.text`。
4. ambiguous coverage 返回 diagnostic，不生成 silent residual。
5. residual provenance action 默认 `output_policy=no_output`、`outputs=[]`。
6. `span_by_id` 调用约定明确为 resolved spans。
7. Projector 不切生产路径。

### 8.3 阻断条件

```text
P0: residual 由 StepIR.text 或 rendered text 推断。
P0: ambiguous coverage 静默 materialize CALL_API 或 silent drop residual。
P1: source range / coverage refs 没有进入 report。
P1: residual action 默认产生 output。
```

### 8.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7/test_api_residual_action_projector.py -q
.venv\Scripts\ruff check src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py tests/unit/pipeline/stage7/test_api_residual_action_projector.py
```

---

## 9. P3 评审准则：api_call_materializer 短期 residual fix

### 9.1 必须核查的产物

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
tests/unit/pipeline/stage7/test_api_call_materializer_residual_fix.py
tests/integration/pipeline/test_internal_comms_api_residual_e2e.py
```

### 9.2 必须通过的检查

1. `materialize_direct_api_calls()` 接收 resolved `span_by_id` 或已投影 projection result。
2. `api_call_augments_behavior` 生成 `CALL_API + residual GENERAL_COMMAND`。
3. covered duplicate `GENERAL_COMMAND Retrieve sources...` 被删除。
4. residual `Maintain provenance...` 出现在 final SPL。
5. residual command `outputs=[]`，不注册 producer。
6. CALL_API output binding 不丢 producer authority。
7. ambiguous coverage 不新增 `CALL_API`，不裁剪 fallback，输出 `stage7_api_residual_coverage_ambiguous`。
8. P3 shim 标注 remove-after P6/P7。
9. 不修改 Gate / Renderer / SPL Editing。

### 9.3 阻断条件

```text
P0: 仍从 StepIR.text 裁剪 residual。
P0: ambiguous coverage 强行生成 CALL_API。
P0: no-output residual 进入 ProducerIndex。
P0: CALL_API output binding 丢失。
P1: P3 shim 无生命周期说明。
P1: unrelated GENERAL_COMMAND 被误删。
```

### 9.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7/test_api_call_materializer_residual_fix.py tests/integration/pipeline/test_internal_comms_api_residual_e2e.py -q
.venv\Scripts\ruff check src/nl2spl/pipeline/stages/stage7_step_extractor tests/unit/pipeline/stage7/test_api_call_materializer_residual_fix.py tests/integration/pipeline/test_internal_comms_api_residual_e2e.py
```

---

## 10. P4 评审准则：Action-Aware Unmapped Detection

### 10.1 必须核查的产物

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
tests/unit/pipeline/stage7/test_action_aware_unmapped_detection.py
```

### 10.2 必须通过的检查

1. mixed span 不再因 `CALL_API.source_span_ids=["s16"]` 被误判 fully covered。
2. coverage 判定基于 action partition，而非 span-level `source_span_ids` 集合。
3. uncovered residual 产生 report 或 diagnostic。
4. duplicate API + general same operation 产生 incompatible overlap。
5. API-only span 仍 fully partitioned。
6. IRS / SPL Editing 未参与 action partition。

### 10.3 阻断条件

```text
P0: 最终判断仍是 covered_span_ids = {step.source_span_ids}。
P0: residual action loss 没有 diagnostic。
P1: diagnostic 只存在 debug log。
```

### 10.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7/test_action_aware_unmapped_detection.py -q
```

---

## 11. P5 评审准则：Read-Only WorkerActionPlanIR Intermediate

### 11.1 必须核查的产物

```text
stage7_worker_action_plan intermediate
stage7_action_coverage_reports intermediate
tests/integration/pipeline/test_worker_action_plan_intermediate.py
```

### 11.2 必须通过的检查

1. 明确采用方案 A 或方案 B 接入 intermediate。
2. 不扩散 Stage 7 public return type churn。
3. intermediate payload deterministic。
4. action coverage report 包含 `s16` partition。
5. no-output residual 不进入 ProducerIndex。
6. 默认 StepIR 行为与 P3/P4 修复后保持一致。
7. `WorkerActionPlanIR` 不被 Renderer / IRS / SPL Editing 消费。

### 11.3 阻断条件

```text
P0: WorkerActionPlanIR 成为 materialization authority。
P0: intermediate 被注册成 IRS report 或 repair affordance。
P1: 未说明选择方案 A 或 B。
P1: direct stage unit tests 被迫整体迁移到新 return type。
```

### 11.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/pipeline/test_worker_action_plan_intermediate.py -q
```

---

## 12. P6 评审准则：API Materializer Action Path

### 12.1 必须核查的产物

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
tests/unit/pipeline/stage7/test_api_action_materializer.py
```

### 12.2 必须通过的检查

1. Direct API call 默认从 `ExecutableActionIR(command_type=CALL_API)` 生成 StepIR。
2. StepIR metadata 保留 action/demand refs。
3. missing API binding 产生 diagnostic。
4. missing placement 产生 diagnostic。
5. same `action_id` rerun 不生成 duplicate StepIR。
6. sanitizer 不再是主路径，仅作为 fallback guard 并标注 deprecated after P7/P8。
7. CALL_API output SymbolTable / ProducerIndex policy 明确并有测试。

### 12.3 阻断条件

```text
P0: 仍以 append then sanitize 作为默认路径。
P0: CALL_API action metadata 丢失 demand/action refs。
P0: CALL_API output binding 丢 producer。
P1: deprecated fallback 无 remove-after 注释。
```

### 12.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7/test_api_action_materializer.py -q
```

---

## 13. P7a 评审准则：Action-slice Prompt Contract Characterization

### 13.1 必须核查的产物

```text
tests/unit/pipeline/stage7/test_stage7_prompt_action_slice.py
action-slice payload shape / schema fixture
```

### 13.2 必须通过的检查

1. P7a 不改变生产 prompt 默认行为。
2. 测试证明当前 prompt 是否仍包含 full span authority。
3. 新 action-slice payload shape deterministic。
4. action-slice payload 不把 typed API-covered text 作为 general command authority。
5. payload 包含 allowed command type、forbidden command types、input/output hints。

### 13.3 阻断条件

```text
P0: P7a 直接切换生产 prompt。
P1: action-slice payload shape 未固定。
P1: 测试无法证明 full span authority 是否仍存在。
```

### 13.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7/test_stage7_prompt_action_slice.py -q
```

---

## 14. P7b 评审准则：General Command Action Path Integration

### 14.1 必须核查的产物

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
tests/unit/pipeline/stage7/test_general_command_action_materializer.py
tests/unit/pipeline/stage7/test_stage7_prompt_action_slice.py
```

### 14.2 必须通过的检查

1. General extractor 只消费 `GENERAL_COMMAND` action slice。
2. typed API action 不再被 general extractor materialize。
3. prompt/schema 显式禁止 `CALL_API` / `INVOKE_WORKER` / `REQUEST_INPUT`。
4. residual action 生成 `GENERAL_COMMAND`。
5. no-output residual `outputs=[]`。
6. unrelated general action 仍正常 materialize。
7. P7a contract tests 仍通过。

### 14.3 阻断条件

```text
P0: prompt 仍把 full span 作为自由 command authority。
P0: LLM 可从 GENERAL_COMMAND slice 生成 CALL_API / INVOKE_WORKER。
P0: typed API action 被普通 extractor 再次 materialize。
P1: residual normal action 丢失。
```

### 14.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7/test_general_command_action_materializer.py tests/unit/pipeline/stage7/test_stage7_prompt_action_slice.py -q
```

---

## 15. P8 评审准则：CALL_API Handoff/Direct Conflict Detection

### 15.1 必须核查的产物

```text
conflict_key / idempotency_key implementation
tests/unit/pipeline/stage7/test_call_api_action_conflict_detection.py
```

### 15.2 必须通过的检查

1. `conflict_key` 不包含 `owning_authority_family`。
2. `idempotency_key` 包含 authority family 与 source demand / handoff id。
3. direct API + handoff API same operation 产生 `duplicate_api_action_claim`。
4. direct API + handoff API different operation 允许。
5. same action rerun idempotent。
6. diagnostic 包含 direct demand id 与 handoff id。
7. 不出现两个 independent append paths 产生 silent duplicate。

### 15.3 阻断条件

```text
P0: conflict_key 包含 owning_authority_family。
P0: same operation direct/handoff 可生成两个 CALL_API。
P1: diagnostic 未进入 compile diagnostics / action coverage report。
P1: idempotency rerun 仍重复生成 StepIR。
```

### 15.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7/test_call_api_action_conflict_detection.py -q
```

---

## 16. P9 评审准则：Coverage Validator Gate Warning -> Blocking Migration

### 16.1 必须核查的产物

```text
action coverage validator
tests/integration/pipeline/test_stage7_action_coverage_validator_e2e.py
diagnostic severity migration config / policy
```

### 16.2 必须通过的检查

1. `duplicate_api_action_claim`、`ambiguous_typed_action_coverage`、`stage7_incompatible_action_overlap` 可迁移为 blocking。
2. blocking 只阻断 action materialization，不由 Renderer / Gate / SPL Editing 兜底。
3. API-only、API+residual、direct/handoff conflict regression 全覆盖。
4. diagnostic 可见，包含 inventory 要求的 metadata。
5. warning mode 与 blocking mode 均有测试。
6. 无新增 skip / xfail。

### 16.3 阻断条件

```text
P0: blocking 行为由 Renderer/Gate/SPL Editing suppress 实现。
P0: duplicate/incompatible action 在 blocking mode 仍 materialize。
P1: diagnostic metadata 不完整。
P1: warning/blocking migration 缺测试。
```

### 16.4 审核命令建议

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/pipeline/test_stage7_action_coverage_validator_e2e.py -q
```

---

## 17. 端到端冻结审核

P9 后必须进行最终冻结审核。冻结审核必须覆盖：

1. `examples/input/internal_comms.txt`：
   - final SPL 包含 `CALL ApprovedSourceRecipesAPI`。
   - final SPL 包含 `COMMAND Maintain provenance for externally sourced facts`。
   - final SPL 不包含 duplicate `COMMAND Retrieve sources using approved source recipes`。
2. API-only span：
   - 只生成 `CALL_API`。
   - 不生成 residual `GENERAL_COMMAND`。
3. API + validation residual：
   - 输出 `CALL_API + GENERAL_COMMAND validation`。
4. Ambiguous residual：
   - 输出 diagnostic。
   - 不静默保留 duplicate fallback。
5. Direct API / Handoff API conflict：
   - 输出 `duplicate_api_action_claim`。
   - 不 materialize 两个 `CALL_API`。
6. Worker Delegation repair regression：
   - `run_demo.py --run demo --e2e-worker-delegation` 仍通过。
   - Worker Delegation repair 后 API call 不丢失。
   - 不引入 duplicate API-backed child worker 行为。

冻结审核必须附带：

```text
before/after final_spl
before/after Stage 7 intermediate
action coverage reports
compile diagnostics
ProducerIndex / SymbolTable relevant summary
demo E2E output
manifest.json
```

---

## 18. Review Report 模板

每个阶段提交必须使用以下格式：

```markdown
# Stage 7 Action-Level Extraction Review Report - P<N>

## Verdict
pass | conditional_pass | fail

## Scope
- Phase:
- Implementation plan version / commit:
- Files changed:
- Explicitly untouched forbidden areas:

## Evidence
- Test commands:
- Test results:
- Ruff / diff-check:
- Artifact bundle:
- Manifest:

## Authority Boundary Check
- span_by_id source:
- residual extraction source:
- ActionCoverageReportIR usage:
- Renderer/Gate/SPL Editing involvement:
- SymbolTable / ProducerIndex policy:

## Findings
### P0
- none

### P1
- none

### P2
- none

## Negative Tests
- ...

## Regression
- Prior phase checks:
- Worker Delegation regression:

## Residual Risk
- ...

## PM Decision
- ...
```

没有 P0/P1 也必须显式写 `none`。不得只写“全部通过”。

---

## 19. 最终冻结判定

最终冻结结论只能在以下条件全部满足时给出 `pass`：

```text
1. P0-P9 全部独立验收通过。
2. P7a/P7b 均独立通过。
3. internal_comms E2E 真实通过。
4. Direct/handoff API conflict negative 通过。
5. ambiguous coverage negative 通过。
6. Worker Delegation repair regression 通过。
7. No-output residual 未进入 producer。
8. CALL_API output producer 不丢失。
9. Renderer/Gate/SPL Editing 未承担 Stage 7 action authority。
10. 文档、实施计划、PM 准则与代码处于同一 review baseline。
```

若 RD / WDI / SPL Editing 相关既有测试因非本阶段原因失败，提交方必须提供失败归因、owner 和隔离证明；否则冻结不得通过。
