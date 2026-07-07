# Stage 7 Action-Level Step Extraction 实施计划

本文档严格基于 `docs/design/stage7_action_level_step_extraction_design_zh.md` 制定。实施目标是将 Stage 7 从脆弱的 `source span -> StepIR` 降低路径，逐步升级为可审计、可分区、可迁移的 `source span -> executable actions -> StepIR` 路径，解决同一 source span 中混杂 `GENERAL_COMMAND + CALL_API` 等不同 command type 时出现的重复 materialization 与 residual action 丢失问题。

本计划覆盖 Stage 7 action-level extraction 的 P0-P9 实施阶段。P0-P4 先关闭当前 `internal_comms` 中 `s16` 的真实缺陷；P5-P9 再把短期修复迁移为 action-level intermediate 和 action-owned materialization 主路径。

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
ConstructPlan / APICallDemand / WorkerHandoffIR
  -> 声明 typed executable action demand 与 operation coverage

resolved spans / span_by_id
  -> 提供 original source span text 与 source range authority

APIResidualActionProjector
  -> 从 APICallDemand + span_by_id + placement 投影 API action 与 residual action
  -> 不读取 StepIR.text
  -> 不写 WorkerStepPlanIR

WorkerActionPlanIR / ActionCoverageReportIR
  -> 只读 action partition intermediate
  -> 解释每个 source span 的 typed action coverage / residual coverage / overlap / uncovered 状态
  -> 不作为 IRS construct，不生成 repair affordance，不直接 materialize StepIR

APICallStepMaterializer
  -> 只消费 CALL_API action
  -> 生成 CALL_API StepIR

GeneralCommandStepMaterializer
  -> 只消费 GENERAL_COMMAND action
  -> 生成 residual / ordinary GENERAL_COMMAND StepIR

Stage 7 coverage validator
  -> 校验 action partition 是否闭合
  -> 将 duplicate / uncovered / ambiguous 行为投影为 diagnostics
  -> 不让 Gate / Renderer / SPL Editing verifier 承担 semantic dedup
```

对 `internal_comms` 的 `s16`，最终输出应为：

```text
CALL ApprovedSourceRecipesAPI
COMMAND Maintain provenance for externally sourced facts
```

不得继续输出：

```text
COMMAND Retrieve sources using approved source recipes
CALL ApprovedSourceRecipesAPI
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. **Action coverage authority 来自 resolved spans。** `span_by_id` 必须由 resolved spans 构造，不得从 raw Stage 1 spans、canonical text 或 rendered SPL 临时反查。
2. **Residual extraction 不读取 `StepIR.text`。** 对 API residual 的所有裁剪、coverage、diagnostic 都必须基于 original source span text 与 `OperationCoverageIR`。
3. **`ActionCoverageReportIR` 是 read-only intermediate。** 它不是 IRS construct，不进入 repair catalog，不生成 affordance，不 materialize StepIR。
4. **`ExecutableActionIR` 不能成为自由修复入口。** 它只表达 Stage 7 action partition，不接受用户输入，不调用 LLM，不写 overlay。
5. **CALL_API 双来源必须合流。** `APICallDemand` 与 `WorkerHandoffIR(mode="api_call")` 不得静默生成重复 `CALL_API`。
6. **No-output residual 不得伪造 producer。** `Maintain provenance...` MVP 默认 `output_policy=no_output`、`outputs=[]`，ProducerIndex 不得把它当 producer。
7. **Gate / Renderer 不做 semantic dedup。** Gate 只执行 renderability authority，Renderer 只渲染已过滤 worker，不决定 action overlap。
8. **SPL Editing 不修 pipeline duplicate。** Repair verifier 不得 suppress Stage 7 duplicate output 或 missing residual output。
9. **LLM 不进入本轮 action segmentation。** 本计划 P0-P9 均以 deterministic projection 为主，不新增生产 LLM segmentation。
10. **SymbolTable / ProducerIndex policy 必须显式。** 新增或替换 StepIR 后必须声明 symbol table 是否同步更新；`outputs=[]` 的 residual command 不得注册 producer，CALL_API output 若被后续阶段消费则必须进入 producer authority。
11. **每阶段可独立验收。** 不允许“先合入半成品，后续 phase 修正”。

---

## 3. LLM / Rule-based 决策约束

本计划中默认不允许新增任何 rule-based semantic fallback。允许的确定性逻辑仅限：

- 从 `APICallDemand.operation_coverage` 读取 source range。
- 从 resolved `SpanIR.text` 中按 range 删除 API-covered operation，得到 residual text。
- 对 residual text 做 whitespace / punctuation cleanup。
- 基于稳定 source ids、demand ids、coverage ids 生成 action ids。
- 对 `normalized_action_key` 做确定性 canonicalization。
- 对 action coverage overlap / uncovered / ambiguous 做结构化校验。

以下行为必须在实施前重新提交设计确认：

1. 使用 LLM 判断一个 residual action 的 command type。
2. 使用 text similarity、embedding、semantic threshold 判断重复 action。
3. 使用关键词兜底判断 `Maintain provenance` 等 residual output policy。
4. 让 `api_call_materializer` 根据 `StepIR.text` 再次推断 residual。
5. 让 Stage 7 IRS、Gate、Renderer 或 SPL Editing verifier 补救 action partition。

`normalized_action_key` 的 MVP canonicalization 固定为：

```text
1. lowercase
2. trim surrounding punctuation
3. collapse whitespace to single space
4. remove trailing sentence punctuation
5. do not lemmatize
6. do not remove stopwords
7. source range equality takes precedence over text similarity
```

---

## 3.5 Diagnostic Inventory

Stage 7 action-level extraction 相关 diagnostic 必须使用统一 inventory，不能散落为 debug log、临时 warning string 或测试专用字段。

MVP diagnostic 清单：

| kind | severity 初始值 | blocks_rendering | blocks_completion | target_ref | source_span_ids | 必备 metadata | 可见性 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `stage7_api_residual_coverage_ambiguous` | warning | false | true | `api_call_demand:<id>` 或 action coverage ref | required | `call_demand_id`, `coverage_id`, `reason` | compile diagnostics + action coverage report |
| `stage7_residual_action_unmaterialized` | warning | false | true | action ref | required | `action_id`, `coverage_refs`, `residual_text_hash` | compile diagnostics + action coverage report |
| `stage7_incompatible_action_overlap` | warning | false | true | action coverage report ref | required | `action_ids`, `normalized_action_key`, `overlap_reason` | compile diagnostics + action coverage report |
| `duplicate_api_action_claim` | warning | false | true | conflict key ref | required | `conflict_key`, `direct_api_demand_id`, `handoff_id` | compile diagnostics + action coverage report |
| `ambiguous_typed_action_coverage` | warning | false | true | action coverage report ref | required | `action_id`, `coverage_refs`, `reason` | compile diagnostics + action coverage report |

P9 允许将其中影响 action materialization correctness 的 diagnostic 从 warning 迁移为 blocking，但不得通过 Renderer、Gate 或 SPL Editing verifier 兜底阻断。

---

## 4. Phase P0：Characterization Tests

### 4.1 目标

锁定当前真实缺陷，证明问题发生在 Stage 7 API lowering / residual materialization，而不是 Renderer、Gate、SPL Editing repair 或 Lane B replay。

### 4.2 可编辑范围

允许新增：

```text
tests/unit/pipeline/stage7/test_api_call_residual_action_characterization.py
tests/integration/pipeline/test_stage7_action_level_internal_comms_characterization.py
```

允许修改：

```text
tests/fixtures/
```

仅限新增 fixture helper，不得修改生产代码。

### 4.3 禁止改动

P0 禁止修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/compiler/construct_plan/
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/spl_editing/
```

### 4.4 设计要求

P0 测试必须明确区分：

```text
current-behavior lock:
  当前代码确实会输出 duplicate API operation 且 missing residual provenance action。

target-behavior pending expectation:
  后续阶段应输出 CALL_API + residual GENERAL_COMMAND。
```

P0 不允许通过 `skip` / `xfail` 伪装目标行为。若需要 pending target assertion，应以 helper/golden payload 记录，不进入默认 pytest 断言失败路径。

### 4.5 测试计划

新增测试必须覆盖：

1. 构造或读取 `s16` fixture：
   ```text
   retrieve them using approved source recipes. Maintain provenance for externally sourced facts.
   ```
2. 构造 paraphrased fallback step：
   ```text
   Retrieve sources using approved source recipes.
   ```
3. 构造 `APICallDemand.behavior_lowering_policy=api_call_augments_behavior`。
4. 断言当前 Stage 7 output 包含 duplicate retrieve operation。
5. 断言当前 Stage 7 output 不包含 executable `Maintain provenance...` step。
6. 断言 ConstructPlan 已有 `residual_behavior_span_ids=["s16"]`。

### 4.6 验收标准

P0 通过条件：

1. Characterization tests 在当前代码上通过。
2. 测试证明 duplicate 与 residual loss 的实际 artifact 链。
3. 不修改生产代码。
4. 无新增 skip / xfail。

### 4.7 PM 审核清单

审核时必须检查：

1. 是否确实验证 `s16` 是 mixed-action span。
2. 是否证明 `ConstructPlan` 已识别 residual。
3. 是否证明 Stage 7 output 没有 residual action。
4. 是否没有改生产代码。

---

## 5. Phase P1：Action Model 与确定性序列化

### 5.1 目标

新增 action-level 中间模型与 payload 序列化，不改变默认 Stage 7 输出。

### 5.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/action_model.py
tests/unit/pipeline/stage7/test_action_model_serialization.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/__init__.py
```

### 5.3 禁止改动

P1 禁止修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
```

### 5.4 设计要求

必须实现：

```python
SourceRangeIR
ExecutableActionIR
ActionCoverageReportIR
WorkerActionPlanIR
```

P0 guardrails：

```text
1. ActionCoverageReportIR.diagnostics 不得使用弱 tuple[str, ...]。
   允许：
     diagnostic_ids: tuple[str, ...]
   或：
     diagnostics: tuple[CompileDiagnostic, ...]

2. ambiguous/uncovered action 不得伪造 placement。
   ExecutableActionIR 必须支持：
     flow_ref: str | None
     block_ref: str | None
     placement_status: placed | unplaced | ambiguous

3. normalized_action_key 必须使用固定 canonicalization。
```

`ExecutableActionIR` 必须包含：

```text
action_id
action_kind
source_span_ids
coverage_refs
covered_ranges
excluded_ranges
action_text
normalized_action_key
command_type
owning_authority
source_construct_demand_id
source_handoff_id
flow_ref
block_ref
placement_status
input_hints
output_hints
output_policy
coverage_status
metadata
```

### 5.5 测试计划

新增单元测试必须覆盖：

1. action model round-trip serialization。
2. deterministic ordering。
3. `normalized_action_key` canonicalization。
4. ambiguous action 可没有 placement，不伪造 `flow_ref/block_ref`。
5. `ActionCoverageReportIR` diagnostics 字段不使用弱 string payload。
6. `no_output` action 不携带 output hints。

### 5.6 验收标准

P1 通过条件：

1. 新模型不改变任何 Stage 7 默认输出。
2. 序列化 deterministic。
3. 无新增 LLM / prompt / schema 调用。
4. 无新增 skip / xfail。

### 5.7 PM 审核清单

审核时必须检查：

1. `diagnostics: tuple[str, ...]` 是否不存在。
2. `placement_status` 是否存在，且 ambiguous/uncovered 不要求非空 placement。
3. canonicalization 是否没有 semantic similarity / lemmatization。
4. 是否没有默认路径消费 `WorkerActionPlanIR`。

---

## 6. Phase P2：APIResidualActionProjector

### 6.1 目标

新增 deterministic residual projector，从 `APICallDemand + span_by_id + APICallPlacementIR` 生成 CALL_API action、residual GENERAL_COMMAND action 与 `ActionCoverageReportIR`。

### 6.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
tests/unit/pipeline/stage7/test_api_residual_action_projector.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/__init__.py
```

### 6.3 禁止改动

P2 禁止修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
```

### 6.4 设计要求

必须实现：

```python
class APIResidualActionProjector:
    def project(
        self,
        *,
        call: APICallDemand,
        span_by_id: Mapping[str, SpanIR],
        placement: APICallPlacementIR,
    ) -> APIResidualActionProjection: ...
```

Projector 必须：

```text
1. 只从 span_by_id[span_id].text 读取 original source text。
2. 只使用 APICallDemand.operation_coverage 的 ranges 删除 covered operation。
3. 不读取 StepIR.text。
4. coverage ambiguous 时返回 diagnostic，不生成 silent residual。
5. residual provenance action 默认 output_policy=no_output，outputs=[]。
6. placement 来自 APICallPlacementIR；若 placement 不完整，则 placement_status=unplaced/ambiguous。
```

### 6.5 测试计划

新增单元测试必须覆盖：

1. `retrieve... Maintain provenance...` -> CALL_API action + residual GENERAL_COMMAND action。
2. API-only span -> only CALL_API action。
3. ambiguous coverage -> diagnostic + no residual materialization。
4. normalized whitespace coverage。
5. multiple operation ranges。
6. projector 不读取 `StepIR.text`。
7. residual action `output_policy=no_output`。

### 6.6 验收标准

P2 通过条件：

1. Projector 单元测试通过。
2. 无生产路径切换。
3. 无 LLM / prompt change。
4. `span_by_id` 来自 resolved spans 的调用约定写入 docstring / type docs。

### 6.7 PM 审核清单

审核时必须检查：

1. 是否存在任何 `StepIR.text` residual 裁剪。
2. ambiguous coverage 是否不会 silent keep duplicate fallback。
3. residual output 是否默认 no-output。
4. source range / coverage refs 是否进入 report。

---

## 7. Phase P3：api_call_materializer 短期 residual fix

### 7.1 目标

在不重写 Stage 7 主路径的前提下，修复当前 `api_call_materializer.py` 对 API residual 的错误处理：删除 duplicate fallback，生成 residual command。

### 7.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
```

允许新增：

```text
tests/unit/pipeline/stage7/test_api_call_materializer_residual_fix.py
tests/integration/pipeline/test_internal_comms_api_residual_e2e.py
```

### 7.3 禁止改动

P3 禁止修改：

```text
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/spl_editing/
```

### 7.4 设计要求

`materialize_direct_api_calls()` 必须新增 `spans` 或 `span_by_id` 输入，或调用一个已传入 `span_by_id` 的 residual projection result。

行为要求：

```text
1. behavior_lowering_policy=api_call_replaces_behavior:
   - 删除 covered GENERAL_COMMAND fallback。
   - materialize CALL_API。

2. behavior_lowering_policy=api_call_augments_behavior:
   - 删除 covered GENERAL_COMMAND fallback。
   - materialize CALL_API。
   - materialize residual GENERAL_COMMAND if residual text exists。
   - residual GENERAL_COMMAND outputs=[] unless explicit output_policy exists。

3. behavior_lowering_policy=ambiguous:
   - 不新增 CALL_API StepIR。
   - 不裁剪或替换 GENERAL_COMMAND fallback。
   - 仅当 fallback 本身 source-backed 且不是 same-demand fallback 时保留。
   - emit stage7_api_residual_coverage_ambiguous diagnostic。
   - diagnostic metadata 必须包含 call_demand_id、coverage_id、source_span_ids、reason。
```

P3 只允许 API-specific short-term shim；必须标注生命周期：

```text
remove after P6/P7 action-owned materializers become default
```

SymbolTable / ProducerIndex policy：

```text
1. residual GENERAL_COMMAND outputs=[] 时不得调用 add_producer，不得进入 ProducerIndex producer 语义。
2. CALL_API action 若产生 outputs，必须确认 ProducerIndex 是否从 WorkerIR 重建。
3. 若 Stage 7 后续阶段仍消费 SymbolTable producer/consumer 状态，则 CALL_API output 必须同步 add_producer。
4. 所有新增/替换 StepIR 必须在测试中覆盖 producer/consumer 不丢失与不误增。
```

### 7.5 测试计划

新增测试必须覆盖：

1. 当前 `s16` fixture 生成 `CALL_API + Maintain provenance GENERAL_COMMAND`。
2. 不再生成 `GENERAL_COMMAND Retrieve sources using approved source recipes`。
3. API-only span 只生成 CALL_API。
4. unrelated GENERAL_COMMAND in same block 不被删除。
5. residual step `outputs=[]`。
6. residual step source provenance 指向同一 source span 和 residual range。
7. ambiguous coverage 生成 diagnostic。
8. residual no-output 不产生 producer。
9. CALL_API output binding 不丢 producer。

### 7.6 验收标准

P3 通过条件：

1. `internal_comms` final SPL 不再重复 retrieve operation。
2. `Maintain provenance...` 作为 executable command 出现。
3. 不改 Gate / Renderer / SPL Editing。
4. API materialization tests 通过。

### 7.7 PM 审核清单

审核时必须检查：

1. `materialize_direct_api_calls` 是否拿到 resolved spans / span_by_id。
2. 是否还存在基于 `StepIR.text` offset 的主路径 residual 裁剪。
3. residual command 是否 no-output。
4. CALL_API output 是否有明确 SymbolTable / ProducerIndex policy。
5. ambiguous coverage 是否遵守“不新增 CALL_API、不裁剪 fallback、发 diagnostic”的策略。
6. 是否存在 renderer/gate 语义去重。

---

## 8. Phase P4：Action-Aware Unmapped Detection

### 8.1 目标

将 Stage 7 unmapped behavior detection 从 span-level coverage 升级为 action-level coverage，避免 `CALL_API.source_span_ids=["s16"]` 掩盖 residual action 丢失。

### 8.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
```

允许新增：

```text
tests/unit/pipeline/stage7/test_action_aware_unmapped_detection.py
```

### 8.3 禁止改动

P4 禁止修改：

```text
src/nl2spl/compiler/irs/
src/nl2spl/compiler/spl_editing/
src/nl2spl/pipeline/executable_gate.py
```

### 8.4 设计要求

旧规则：

```text
span covered if any StepIR.source_span_ids contains span_id
```

必须替换或扩展为：

```text
source span partition covered iff every executable action slice is owned by exactly one materialized action or explicitly diagnosed
```

### 8.5 测试计划

新增测试必须覆盖：

1. CALL_API 覆盖 API action，但 residual action 未覆盖 -> diagnostic。
2. CALL_API + residual GENERAL_COMMAND -> fully_partitioned。
3. duplicate CALL_API + GENERAL_COMMAND same operation -> incompatible overlap。
4. API-only span -> fully_partitioned。
5. ambiguous residual -> diagnostic。

### 8.6 验收标准

P4 通过条件：

1. mixed span 不再被单个 `CALL_API.source_span_ids` 误判为 fully covered。
2. Diagnostic 可见，进入 Stage 7 warnings/diagnostics。
3. 无 skip / xfail。

### 8.7 PM 审核清单

审核时必须检查：

1. 是否仍有 `covered_span_ids = {span for step.source_span_ids}` 作为最终判断。
2. 是否所有 uncovered residual 都有 report 或 diagnostic。
3. 是否没有让 IRS 创建 action partition。

---

## 9. Phase P5：Read-Only WorkerActionPlanIR Intermediate

### 9.1 目标

将 `WorkerActionPlanIR` 和 `ActionCoverageReportIR` 接入 Stage 7 intermediate / debug payload，但不改变 StepIR 默认生成结果。

### 9.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
src/nl2spl/pipeline/orchestrator.py
```

允许新增：

```text
tests/integration/pipeline/test_worker_action_plan_intermediate.py
```

### 9.3 禁止改动

P5 禁止修改：

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/spl_editing/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 9.4 设计要求

Intermediate payload 应可 checkpoint：

```text
intermediate["stage7_worker_action_plan"]
intermediate["stage7_action_coverage_reports"]
```

P5 接入方式必须二选一并在实现中固定，不得临时扩散 Stage 7 public return type：

```text
方案 A：
  StepExtractor 暴露只读属性：
    self.stage7_worker_action_plan
    self.stage7_action_coverage_reports
  orchestrator 在 stage run 后读取并写入 intermediate。

方案 B：
  新增 Stage7ExecutionResult，但只在 orchestrator 内部适配。
  direct stage unit tests 不被迫整体迁移到新 return type。
```

但不得：

```text
1. 作为 IRS report。
2. 生成 repair affordance。
3. 改变 StepIR output。
4. 被 Renderer 消费。
```

### 9.5 测试计划

新增测试必须覆盖：

1. payload deterministic。
2. action coverage report 包含 `s16` partition。
3. no-output residual action 不进入 ProducerIndex。
4. no default StepIR behavior change。
5. chosen intermediate interface 不改变现有 direct stage tests 的调用契约，或有清晰 adapter。

### 9.6 验收标准

P5 通过条件：

1. Intermediate 可观测。
2. 默认 rendered SPL 与 P3/P4 修复后行为一致。
3. Action plan 不被下游误用为 authority。

### 9.7 PM 审核清单

审核时必须检查：

1. `WorkerActionPlanIR` 是否只读。
2. 是否没有新增 IRS construct。
3. 是否没有新增 SPL Editing repair catalog entry。
4. 是否明确采用方案 A 或方案 B，且没有扩大 return type churn。

---

## 10. Phase P6：API Materializer Action Path

### 10.1 目标

让 direct API materialization 从 `CALL_API` action 生成 StepIR，逐步淘汰 append 后 sanitize fallback 的主路径。

### 10.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
```

允许新增：

```text
tests/unit/pipeline/stage7/test_api_action_materializer.py
```

### 10.3 禁止改动

P6 禁止修改：

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/pipeline/executable_gate.py
```

### 10.4 设计要求

API materializer 新主路径：

```text
ExecutableActionIR(command_type=CALL_API)
  -> StepIR(command_type=CALL_API)
```

兼容 sanitizer 只能作为 fallback guard，并必须在代码注释中标注：

```text
deprecated after P7/P8
```

### 10.5 测试计划

新增测试必须覆盖：

1. CALL_API action -> StepIR。
2. missing API binding -> diagnostic。
3. missing placement -> diagnostic。
4. no duplicate StepIR if same action_id rerun。
5. API action provenance metadata 保留 demand/action refs。

### 10.6 验收标准

P6 通过条件：

1. direct API call 默认从 action path 生成。
2. sanitizer 不再是主路径。
3. API materialization regression 全部通过。

### 10.7 PM 审核清单

审核时必须检查：

1. 是否仍先 append 再 sanitize 作为默认路径。
2. CALL_API StepIR metadata 是否包含 action/demand refs。
3. 是否没有 renderer/gate 兜底。

---

## 11. Phase P7：General Command Action Path

### 11.1 目标

让普通 general command extraction 消费 `GENERAL_COMMAND` action slices，不再整体消费已被 typed action claim 的 full span。

P7 拆成两个可独立验收的小阶段：

```text
P7a Action-slice prompt contract characterization
  - 不改生产 prompt。
  - 新增测试证明当前 prompt 是否仍包含 full span authority。
  - 固定新的 action-slice payload shape。

P7b GeneralCommandActionMaterializer integration
  - 只把 GENERAL_COMMAND action slice 交给 LLM 或 deterministic wording builder。
  - prompt/schema 显式禁止 CALL_API / INVOKE_WORKER / REQUEST_INPUT。
```

### 11.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
```

允许新增：

```text
tests/unit/pipeline/stage7/test_general_command_action_materializer.py
tests/unit/pipeline/stage7/test_stage7_prompt_action_slice.py
```

### 11.3 禁止改动

P7 禁止修改：

```text
src/nl2spl/compiler/spl_editing/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 11.4 设计要求

如果仍调用 LLM 生成 command wording，prompt 输入必须是 action slice：

```text
Action text
Allowed command_type
Allowed inputs / outputs hints
Forbidden command types
```

不得把 full span 重新交给 LLM 让其自由决定 command type。

### 11.5 测试计划

新增测试必须覆盖：

P7a：

1. 当前 prompt contract 是否包含 full span authority。
2. 新 action-slice payload shape deterministic。
3. action-slice payload 不包含 typed API-covered text as command authority。

P7b：

1. residual action -> GENERAL_COMMAND。
2. typed API action 不再被 general extractor materialize。
3. prompt 不包含 full span as free-form authority。
4. no-output residual action outputs=[]。
5. unrelated general action 仍正常 materialize。

### 11.6 验收标准

P7 通过条件：

1. P7a 先通过，不改变生产 prompt 默认行为。
2. P7b 后 `GENERAL_COMMAND + CALL_API` mixed span 不再重复 API operation。
3. residual normal action 不丢失。
4. LLM prompt/schema 变更若存在，必须有 action-slice contract test。

### 11.7 PM 审核清单

审核时必须检查：

1. 普通 extractor 是否仍整体消费 typed action span。
2. prompt 是否允许 LLM 生成 `CALL_API` / `INVOKE_WORKER`。
3. no-output residual 是否未进入 ProducerIndex。

---

## 12. Phase P8：CALL_API Handoff/Direct Conflict Detection

### 12.1 目标

统一 `APICallDemand` 与 `WorkerHandoffIR(mode="api_call")` 的 CALL_API action claim，防止 `CALL_API + CALL_API` 重复 materialization。

### 12.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
```

允许新增：

```text
tests/unit/pipeline/stage7/test_call_api_action_conflict_detection.py
```

### 12.3 禁止改动

P8 禁止修改：

```text
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 12.4 设计要求

唯一性 key：

```text
conflict_key:
  source_span_ids
  normalized_operation_surface
  command_type

idempotency_key:
  source_span_ids
  normalized_operation_surface
  command_type
  owning_authority_family
  source_construct_demand_id / source_handoff_id
```

冲突检测必须使用 `conflict_key`，不得把 `owning_authority_family` 放入 duplicate conflict key；同一 authority 重跑去重才使用 `idempotency_key`。

旧式单一 key 禁止作为冲突检测依据：

```text
source_span_ids
normalized_operation_surface
command_type
owning_authority_family
```

冲突：

```text
same operation claimed by APICallDemand and WorkerHandoffIR(mode="api_call")
-> duplicate_api_action_claim diagnostic
-> no silent double materialization
```

### 12.5 测试计划

新增测试必须覆盖：

1. direct API + handoff API same operation -> diagnostic。
2. direct API + handoff API different operation -> allowed。
3. same action rerun -> idempotent。
4. diagnostic includes both source refs。

### 12.6 验收标准

P8 通过条件：

1. 不出现 `CALL_API + CALL_API` silent duplicate。
2. Conflict diagnostic 可见。
3. Existing handoff API tests 不回退。

### 12.7 PM 审核清单

审核时必须检查：

1. 是否有两个 independent append paths。
2. conflict key 是否不包含 owning_authority_family。
3. diagnostic 是否进入 compile diagnostics / report。

---

## 13. Phase P9：Coverage Validator Gate Warning -> Blocking Migration

### 13.1 目标

将 action partition validator 从 read-only/warning 模式逐步接入 Stage 7 gate，形成可阻断的 action coverage authority。

### 13.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/action_projection.py
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
```

允许新增：

```text
tests/integration/pipeline/test_stage7_action_coverage_validator_e2e.py
```

### 13.3 禁止改动

P9 禁止修改：

```text
src/nl2spl/compiler/spl_editing/
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 13.4 设计要求

Validator states：

```text
warning mode:
  duplicate / uncovered / ambiguous 进入 diagnostics，但不阻断 rendering。

blocking mode:
  ambiguous typed coverage 和 incompatible overlap 阻断该 action materialization。
```

P9 必须明确哪些 diagnostic 先 warning，哪些可以 blocking：

```text
blocking:
  duplicate_api_action_claim
  ambiguous_typed_action_coverage
  incompatible_action_overlap

warning:
  residual_action_unmaterialized in migration mode
```

### 13.5 测试计划

新增测试必须覆盖：

1. duplicate API operation -> blocking diagnostic。
2. missing residual action -> diagnostic。
3. ambiguous coverage -> blocking diagnostic。
4. clean partition -> no diagnostic。
5. internal_comms demo clean。

### 13.6 验收标准

P9 通过条件：

1. Validator gate 接入默认 Stage 7 path。
2. Internal comms final SPL 包含 API call + provenance residual command。
3. 不出现 duplicate retrieve command。
4. All Stage 7 / API materialization / SPL Editing worker delegation regression tests pass。

### 13.7 PM 审核清单

审核时必须检查：

1. Blocking 行为是否只阻断 action materialization，不由 Renderer/Gate 兜底。
2. Diagnostic 是否可见。
3. 是否没有新增 skip / xfail。

---

## 14. 端到端验收场景

最终必须具备以下 E2E 或高保真集成覆盖：

1. **internal_comms API + residual provenance**
   - 输入 `examples/input/internal_comms.txt`。
   - `s16` 输出 `CALL ApprovedSourceRecipesAPI`。
   - `s16` 同时输出 `COMMAND Maintain provenance for externally sourced facts`。
   - 不输出 duplicate `COMMAND Retrieve sources using approved source recipes`。

2. **API-only span**
   - span 只包含 API invocation。
   - 只生成 `CALL_API`。
   - 不生成 residual `GENERAL_COMMAND`。

3. **API + validation residual**
   - span 包含 API call 和普通 validation residual。
   - 输出 `CALL_API + GENERAL_COMMAND validation`。

4. **Ambiguous residual**
   - coverage offsets missing 或 invalid。
   - 输出 diagnostic。
   - 不静默保留 duplicate fallback。

5. **Direct API / Handoff API conflict**
   - 同 operation 同时由 `APICallDemand` 和 `WorkerHandoffIR(mode="api_call")` claim。
   - 输出 `duplicate_api_action_claim`。
   - 不 materialize 两个 `CALL_API`。

6. **Worker Delegation repair regression**
   - `run_demo.py --run demo --e2e-worker-delegation` 仍通过。
   - Worker Delegation repair 后 API call 不丢失。
   - 不引入 duplicate API-backed child worker 行为。

---

## 15. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐 `stage7_action_level_step_extraction_design_zh.md`。
2. 是否扩大到 Stage 7 之外的 renderer/gate/SPL Editing 语义修复。
3. 是否新增未确认的 LLM segmentation。
4. 是否新增 keyword / similarity / embedding fallback。
5. 是否仍从 `StepIR.text` 裁剪 residual。
6. `span_by_id` 是否来自 resolved spans。
7. `ActionCoverageReportIR` 是否不是 IRS construct。
8. `ExecutableActionIR` 是否包含审计字段和 placement status。
9. no-output residual 是否没有 producer side effect。
10. CALL_API 双来源是否有合流/冲突规则。
11. unmapped detection 是否 action-aware。
12. diagnostics 是否可见，不只留在 debug log。
13. SymbolTable / ProducerIndex policy 是否覆盖 CALL_API output 与 residual no-output。
14. ambiguous coverage 是否有确定策略与 diagnostic。
15. P5 是否避免 Stage 7 return type churn 扩散。
16. P7 是否按 P7a/P7b 分阶段验收。
17. 是否存在 skip / xfail / 弱断言。
18. 是否存在 renderer/gate semantic dedup。
19. 是否存在 SPL Editing verifier suppress pipeline duplicate。
20. 是否修改 final SPL fixture 而不修 pipeline。
21. 是否缺少 internal_comms E2E 证据。

建议最终审核命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/pipeline/stage7 tests/unit/pipeline tests/integration/pipeline tests/integration/compiler/spl_editing -q
.venv\Scripts\ruff check src/nl2spl/pipeline/stages/stage7_step_extractor tests/unit/pipeline/stage7 tests/integration/pipeline
git diff --check -- src/nl2spl/pipeline/stages/stage7_step_extractor tests docs/design/stage7_action_level_step_extraction_implementation_plan_zh.md
```

---

## 16. 阶段完成顺序

推荐顺序：

```text
P0  Characterization Tests
P1  Action Model 与确定性序列化
P2  APIResidualActionProjector
P3  api_call_materializer 短期 residual fix
P4  Action-Aware Unmapped Detection
P5  Read-Only WorkerActionPlanIR Intermediate
P6  API Materializer Action Path
P7a Action-slice prompt contract characterization
P7b General Command Action Path integration
P8  CALL_API Handoff/Direct Conflict Detection
P9  Coverage Validator Gate Warning -> Blocking Migration
```

其中：

- P0 可立即开工。
- P1 必须在 P2 前完成。
- P2 是 P3 的前置条件。
- P3/P4 完成后应已修复 `internal_comms` 当前用户可见问题。
- P5 是 P6/P7 的观测前置条件。
- P6/P7 不得在 P5 前切换默认路径。
- P8 必须在 P9 blocking migration 前完成。
- P9 是最终冻结门，要求 E2E 与 regression matrix 同时通过。
