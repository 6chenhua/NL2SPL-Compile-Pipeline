# Stage 4/5/7 Action Placement、Control Region 与 IO Relation 重构实施计划

本文严格基于 [stage4_5_7_action_placement_control_and_io_relation_refactor_design_zh.md](stage4_5_7_action_placement_control_and_io_relation_refactor_design_zh.md) 制定。

实施目标是将 Stage 3.5 / 4 / 5 / 7 / ProducerIndex 中混在一起的四类 authority 拆开：

```text
placement authority
control authority
materialization authority
producer authority
```

本轮不直接重写全 Pipeline，也不通过 renderer 或 final SPL text 修复 demo。所有阶段必须优先验证中间 IR、checkpoint payload、diagnostics 与 ProducerIndex。

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
Stage 1 SpanIR / segmentation records
  -> 提供 guarded_action / atomic_action_candidate / source ranges

ExecutableActionCandidate builder
  -> 判断哪些 span 有资格进入 executable action placement
  -> 不 materialize command
  -> 不注册 producer

ExecutableActionPlacementPlan
  -> 分离 placement_span_ids 与 generic_step_extraction_span_ids
  -> API-owned executable span 保留 placement ownership

ControlRegionPlanBuilder / Validator
  -> 生成并验证 local_if / top_level_alternative / exception_flow / unresolved regions
  -> LLM classification 只能作为输入证据，不能直接成为 block authority

Stage 5 BlockAssembler
  -> 消费 ControlRegionPlan
  -> 生成 local IF blocks 与 top-level alternative flow blocks
  -> 输出 APICallPlacementIR

Stage 7 Materializers
  -> 只 materialize status == placed 的 API call
  -> generic extraction 只消费 generic_step_extraction_span_ids
  -> 输出 StepVariableRelationPlan

ProducerIndex v2
  -> 只接受 StepVariableRelation.relation == produces
  -> 输出 RequiredOutputFulfillmentState

IRS / diagnostics / feedback
  -> 消费 ProducerIndex 与 fulfillment state
  -> 保留 missing / deferred / ambiguous / report-only 的区分
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. **Placement 先于 materialization**：Stage 3.5/4/5 决定 worker/flow/block/control placement，Stage 7 才决定 StepIR command type。
2. **Materialization exclusion 不得删除 placement ownership**：API span 可排除出 `GENERAL_COMMAND` extraction，但仍必须进入 control/block placement。
3. **所有 executable action span 在 placement 层一视同仁**：不得因未来 command type 是 API / REQUEST_INPUT / INVOKE_WORKER 而从 placement plan 删除。
4. **ControlRegionPlan 是 Stage 5 的控制权威**：Stage 5 不得重新用 raw text keyword 猜 IF / alternative。
5. **LLM classification 不是 block authority**：必须通过 `ControlRegionPlanValidator`。
6. **API placement 必须 exact**：`APICallPlacementIR.status != "placed"` 时 Stage 7 不得生成 `CALL_API`。
7. **禁止 nearest-block / following-block fallback**：缺 block placement 必须 fail closed。
8. **Step output 必须 relation-aware**：ProducerIndex 只接受 `relation == produces`。
9. **legacy `StepIR.outputs` 降级**：无 produces relation 的 legacy output 不得注册 producer。
10. **`pending_response_bindings` 不是 producer**：API return contract unknown 时只能是 deferred。
11. **RequiredOutputFulfillmentState 是 ProducerIndex 输出**：Stage 7 / IRS / renderer 不得直接生成最终 fulfillment truth。
12. **Renderer 只渲染 IR**：不得用 renderer 重排、删除、补全 command。
13. **Diagnostics 必须可见**：所有 fail-closed、deferred、ambiguous 状态必须进入 checkpoint / diagnostics / report 中至少一个可审计面。
14. **不新增未批准的 semantic fallback**：看到关键词后硬改 control kind、硬绑定 producer、硬猜 block 都禁止。
15. **每阶段无新增 skip / xfail**：目标行为断言不能用 skip / xfail 掩盖。

---

## 3. LLM / Rule-Based 决策约束

本计划允许 LLM 参与：

```text
Stage 4 existing flow classification
```

但本计划新增组件默认不新增 LLM 调用。

允许的确定性逻辑仅限：

```text
1. 从 Stage1 segmentation_kind / guard_text_exact / action_text_exact 读取结构化字段。
2. 从 ConstructPlan / APICallDemand / route annotations 读取结构化 authority。
3. 校验 span 是否属于同一 worker / accepted action set。
4. 基于 enum / status / stable ids 生成 typed artifacts。
5. 基于 StepVariableRelation 判断 ProducerIndex eligibility。
```

以下行为必须先获得新的设计确认：

```text
1. 修改 Stage 4 prompt/schema 来新增 local_if 输出。
2. 使用关键词或正则从 raw text 推断 local IF / alternative flow。
3. 使用相似度或语义阈值匹配变量。
4. 让 LLM 判断 ProducerIndex producer。
5. 让 Stage 7 从 required output 反推 producer。
```

---

## 4. Artifact 模块位置与 Checkpoint Key Freeze

### 4.1 模块位置

本计划冻结以下模块位置，避免各 stage 复制局部 dataclass：

```text
src/nl2spl/ir/action_placement_ir.py
  ExecutableActionCandidate
  MaterializationExclusion
  WorkerExecutableActionSet
  ExecutableActionPlacementPlan

src/nl2spl/ir/control_region_ir.py
  ControlRegionDemand
  WorkerControlRegionSet
  ControlRegionPlan

src/nl2spl/ir/step_variable_relation_ir.py
  StepVariableRelation
  StepVariableRelationPlan
  RequiredOutputFulfillmentState

src/nl2spl/pipeline/stages/stage4_flow_assembler/control_region.py
  ControlRegionPlanBuilder
  ControlRegionPlanValidator

src/nl2spl/pipeline/stages/stage5_block_assembler/api_call_placement.py
  APICallPlacementIR projection must consume WorkerBlockPlanIR / ControlRegionPlan

src/nl2spl/compiler/producer_index.py
  ProducerIndex v2 relation-aware producer authority
```

如实现中需要调整文件名，必须保持单一 canonical module，不得在 Stage 4、Stage 5、Stage 7 中各自定义重复模型。

### 4.2 Checkpoint / Intermediate Keys

以下 keys 在 R1 冻结，并必须定义为共享 constants，不得由各 stage 手写字符串：

```text
intermediate["executable_action_candidates"]
intermediate["executable_action_placement_plan"]
intermediate["control_region_plan"]
intermediate["api_call_placements"]
intermediate["step_variable_relation_plan"]
intermediate["required_output_fulfillment"]
```

建议落点：

```text
src/nl2spl/pipeline/intermediate_keys.py
```

如果已有等价模块，可使用现有模块；但必须保证 orchestrator、stage、tests 引用同一组 constants。

每个 key 的 payload 必须可 JSON 序列化、可 round-trip、可在 PM review 中直接断言。

---

## 5. Phase R0：Characterization Tests

### 5.1 目标

锁定当前错误，不改生产行为。

必须证明当前 `internal_comms` 存在：

```text
s18 缺 worker/control/block placement
s18 guard 未生成 IF block
s17 被归入 top-level ALTERNATIVE_FLOW
CALL_API 被 nearest-block fallback 放进错误 block
s19 Maintain provenance 被认定为 source_evidence_set producer
pending_response_bindings 不应被当成 producer
```

### 5.2 可编辑范围

允许新增：

```text
tests/integration/pipeline/test_stage4_5_7_action_placement_current_gap.py
tests/unit/pipeline/stage5/test_api_call_placement_current_gap.py
tests/unit/compiler/test_producer_index_relation_current_gap.py
artifacts/reviews/stage4_5_7_refactor/R0/
```

允许修改：

```text
无生产代码修改。
```

### 5.3 禁止改动

```text
src/nl2spl/**
examples/usage.py
examples/output/spl_editing_demo/run_demo.py
examples/input/internal_comms.txt
```

### 5.4 测试计划

新增 current-behavior lock：

1. `stage1_span_slicer.json` 中 `s18/s20` 是 `guarded_action`。
2. `worker_main.owned_span_ids` 不含 `s18`，记录为 current gap。
3. `stage5_block_assembler.json` 中无 `sources are needed and available` IF block，记录为 current gap。
4. `stage4_flow_assembler.json` 中 `s17` 位于 `alternative_flows.alt_2`，记录为 current gap。
5. `CALL_API` StepIR 的 `block_ref` 指向非 `s18` local IF block，记录为 current gap。
6. `Maintain provenance...` StepIR outputs 含 `source_evidence_set`，记录为 current gap。

### 5.5 验收标准

1. R0 不修改生产行为。
2. 所有 characterization tests 在当前代码上通过。
3. 生成 R0 review report，标明每个 gap 是 `current behavior`，不是目标行为。
4. 无 skip / xfail。

### 5.6 PM 审核清单

1. 确认 R0 没有生产代码 diff。
2. 确认测试断言的是当前错误链路，不是假装目标已满足。
3. 确认 artifact bundle 记录 demo snapshot / stage1 / stage4 / stage5 / StepIR evidence。

---

## 6. Phase R1：Shared Model Freeze

### 6.1 目标

冻结所有跨 stage typed artifacts 的 dataclass、payload schema、round-trip 与 checkpoint keys。

### 6.2 可编辑范围

允许新增：

```text
src/nl2spl/ir/action_placement_ir.py
src/nl2spl/ir/control_region_ir.py
src/nl2spl/ir/step_variable_relation_ir.py
src/nl2spl/pipeline/intermediate_keys.py
tests/unit/ir/test_action_placement_ir.py
tests/unit/ir/test_control_region_ir.py
tests/unit/ir/test_step_variable_relation_ir.py
```

允许修改：

```text
src/nl2spl/ir/__init__.py
```

### 6.3 禁止改动

```text
src/nl2spl/pipeline/stages/**
src/nl2spl/compiler/producer_index.py
src/nl2spl/rendering/**
```

### 6.4 设计要求

必须实现：

```text
ExecutableActionCandidate
MaterializationExclusion
WorkerExecutableActionSet
ExecutableActionPlacementPlan
ControlRegionDemand
WorkerControlRegionSet
ControlRegionPlan
StepVariableRelation
StepVariableRelationPlan
RequiredOutputFulfillmentState
```

每个 artifact 必须具备：

```text
to_payload()
from_payload()
deterministic ordering where applicable
diagnostics field where applicable
explicit enum literals
```

不得包含：

```text
StepIR / BlockIR mutable references
LLM client
raw renderer text
ProducerIndex instance
```

### 6.5 测试计划

1. 每个 artifact round-trip 后 payload 相同。
2. set/list 输入序列稳定排序。
3. invalid enum value fail closed。
4. `RequiredOutputFulfillmentState` 不接受 `produced` 且 producer list 为空。
5. `ControlRegionDemand(local_if)` 可包含多个 action spans。

### 6.6 验收标准

1. R1 只冻结模型，不接入 stage。
2. Checkpoint key names 写入 shared constants。
3. Ruff scoped pass。

### 6.7 PM 审核清单

1. 检查没有重复 dataclass 定义在 Stage 4/5/7。
2. 检查 models 不 import pipeline stages。
3. 检查 payload schema 可由 review 直接读取。
4. 检查所有新增 intermediate keys 都来自 shared constants，orchestrator/tests 不手写不同字符串。

---

## 7. Phase R2：ExecutableActionPlacement Contract

### 7.1 目标

生成 `ExecutableActionCandidate` 与 `ExecutableActionPlacementPlan`，拆分：

```text
placement_span_ids
generic_step_extraction_span_ids
materialization_exclusions
```

### 7.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/action_placement.py
tests/unit/pipeline/test_executable_action_placement.py
```

允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
```

### 7.3 禁止改动

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/**
src/nl2spl/pipeline/stages/stage5_block_assembler/**
src/nl2spl/pipeline/stages/stage7_step_extractor/**
src/nl2spl/compiler/producer_index.py
```

### 7.4 设计要求

Builder 输入：

```text
resolved_spans
resolved_routes
construct_plan
capability_intent_plan / worker_boundary_exclusion_view
worker_plan
```

准入：

```text
accepted:
  atomic_action_candidate
  guarded_action
  executable construct demand
  executable route role
  adapter hard fact executable behavior

rejected:
  failure condition only
  pure definition
  persona / concept / profile
  constraint-only
  required output declaration
  API declaration-only evidence
```

API-owned executable span：

```text
in placement_span_ids
not in generic_step_extraction_span_ids
has MaterializationExclusion(owning_authority="api_call")
```

### 7.5 测试计划

1. `s18` accepted for placement but excluded from generic extraction.
2. failure handling spans rejected from placement unless executable handler exists.
3. required output declaration spans rejected.
4. API declaration-only evidence rejected.
5. ambiguous candidate emits diagnostic and does not enter placement.

### 7.6 验收标准

1. `intermediate["executable_action_candidates"]` exists.
2. `intermediate["executable_action_placement_plan"]` exists.
3. R0 behavior remains unchanged except new intermediate payloads.

### 7.7 PM 审核清单

1. 确认 `api_consumed_span_ids` 没有被用于删除 placement ownership。
2. 确认 no raw keyword semantic fallback。
3. 确认 all rejected categories 有测试。

---

## 8. Phase R3：Stage 3.5 Ownership Repair

### 8.1 目标

确保 API-owned executable spans 保留 worker placement ownership，同时继续排除出 generic worker/candidate/materialization 路径。

### 8.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/materializer.py
```

允许新增：

```text
tests/integration/pipeline/test_stage3_5_api_span_placement_ownership.py
```

### 8.3 禁止改动

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/**
src/nl2spl/pipeline/stages/stage5_block_assembler/**
src/nl2spl/pipeline/stages/stage7_step_extractor/**
```

### 8.4 设计要求

当前类似逻辑：

```text
behavior_span_ids = routes.behavior - api_consumed_span_ids
```

不得再用于 worker ownership / placement ownership。

必须拆分：

```text
worker placement ownership:
  includes API-owned executable spans

generic worker candidate extraction:
  excludes API-owned executable spans
```

### 8.5 测试计划

1. `worker_main.owned_span_ids` includes `s18` after repair.
2. `s18` still excluded from generic child-worker candidate extraction.
3. API-only span does not generate child worker.
4. Existing Stage 3.5 API/worker boundary tests still pass.

### 8.6 验收标准

1. `s18` appears in placement ownership.
2. No duplicate child worker / API materialization regression.
3. No Stage 4/5/7 behavior change required yet.

### 8.7 PM 审核清单

1. 检查 API exclusion 只影响 generic extraction。
2. 检查 no broad re-add of non-executable spans.
3. 检查 WorkerBoundaryExclusionView metadata preserved.

---

## 9. Phase R4：ControlRegionPlan Builder / Validator

### 9.1 目标

实现 `ControlRegionPlanBuilder` 与 `ControlRegionPlanValidator`，但先不让 Stage 5 消费它。

### 9.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/control_region.py
tests/unit/pipeline/stage4/test_control_region_plan.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/__init__.py
src/nl2spl/pipeline/orchestrator.py
```

### 9.3 禁止改动

```text
src/nl2spl/pipeline/stages/stage5_block_assembler/**
src/nl2spl/pipeline/stages/stage7_step_extractor/**
```

### 9.4 设计要求

Builder sources：

```text
Stage1 guarded_action metadata
Stage4 LLM flow classification
route annotations
ConstructPlan hints
ExecutableActionPlacementPlan accepted candidates
```

`source text` 或 Stage 4 LLM classification 只能作为结构化证据输入，不得由 builder 直接使用 raw keyword 规则改写 control kind。`s17` 的 derived local IF 必须是：

```text
classification_source = llm_classified 或 route_derived
validator accepted
```

不能是：

```text
deterministic keyword reclassifier
```

Validator 必须拒绝：

```text
direct relation without direct guard evidence
derived relation without condition_source_span_ids
action_span_ids outside accepted executable placement set
cross-worker condition/action region without explicit authority
unresolved / ambiguous region as materializable
```

当前 demo 目标：

```text
s17 -> local_if, relation=derived, condition_source_span_ids=[s16,s17]
s18 -> local_if, relation=direct
s20 -> local_if, relation=direct
s21 -> top_level_alternative, relation=direct
```

### 9.5 测试计划

1. Stage1 guarded_action becomes local_if.
2. `s17` derived local IF uses `[s16, s17]`.
3. `s17` not top-level alternative in ControlRegionPlan.
4. revision branch remains top-level alternative.
5. invalid direct relation without guard fails validation.
6. unresolved region remains non-materializable.

### 9.6 验收标准

1. `intermediate["control_region_plan"]` exists.
2. Stage 5 output unchanged in this phase.
3. Validator diagnostics visible in intermediate payload.

### 9.7 PM 审核清单

1. 检查没有关键词 reclassifier。
2. 检查 `classification_source` 与 `relation` 被持久化。
3. 检查 builder 与 validator 分离。

---

## 10. Phase R5：Stage 4/5 Control Placement + APICallPlacementIR

### 10.1 目标

让 Stage 5 消费 validated `ControlRegionPlan`，生成 local IF blocks，并把 `APICallPlacementIR` 作为 first-class output。

### 10.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage5_block_assembler/executor.py
src/nl2spl/pipeline/stages/stage5_block_assembler/api_call_placement.py
src/nl2spl/pipeline/stages/stage5_block_assembler/block_postprocess.py
src/nl2spl/pipeline/orchestrator.py
```

允许新增：

```text
tests/unit/pipeline/stage5/test_control_region_block_materialization.py
tests/unit/pipeline/stage5/test_api_call_placement_first_class.py
tests/integration/pipeline/test_stage4_5_control_region_internal_comms.py
```

### 10.3 禁止改动

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/**
src/nl2spl/compiler/producer_index.py
```

### 10.4 设计要求

Stage 5 must：

```text
1. local_if -> BlockIR(block_type="IF")
2. IF block may contain multiple spans.
3. top_level_alternative -> alternative_flow_blocks
4. unresolved region -> no block materialization + diagnostic
5. API-owned guarded_action receives exact block_ref.
6. APICallPlacementIR emitted for every APICallDemand.
```

冲突优先级：

```text
When legacy main_flow_spans / alternative_flows conflict with validated ControlRegionPlan,
ControlRegionPlan wins for block materialization.
Legacy flow output remains provenance/debug input only.
```

因此，如果旧 `alternative_flows.alt_2` 仍包含 `s17`，而 `ControlRegionPlan` 已将 `s17` 验证为 `local_if`，Stage 5 必须生成 local IF，不得同时保留 top-level alternative placement。

Stage 5 must not：

```text
1. Generate StepIR.
2. Infer API inputs/outputs.
3. Register producers.
4. Guess block placement from nearest span.
```

### 10.5 测试计划

1. `s18` local IF block condition = `sources are needed and available`.
2. `s17` local IF block condition = `required information is missing`.
3. `s20` local IF block preserved.
4. `s21` remains top-level alternative.
5. APICallPlacementIR for `s18` status = placed and block_ref = `s18` local IF block.
6. unresolved API placement emits diagnostic and not placed.

### 10.6 验收标准

1. `intermediate["api_call_placements"]` exists and matches checkpoint payload.
2. Stage 5 no longer omits API-owned guarded_action block.
3. No Stage 7 changes in this phase.

### 10.7 PM 审核清单

1. 确认 Stage 5 uses `ControlRegionPlan`, not raw text.
2. 确认 APICallPlacementIR has exact status for every API demand.
3. 确认 no new StepIR materialization in Stage 5.

---

## 11. Phase R6：Stage 7 Fail-Closed API Materialization

### 11.1 目标

删除 API placement silent fallback。Stage 7 只 materialize `status == placed` 的 API call。

### 11.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage5_block_assembler/api_call_placement.py
```

允许新增：

```text
tests/unit/pipeline/stage7/test_api_materializer_fail_closed_placement.py
tests/integration/pipeline/test_api_call_placement_internal_comms.py
```

### 11.3 禁止改动

```text
src/nl2spl/compiler/producer_index.py
src/nl2spl/rendering/**
```

### 11.4 设计要求

必须删除或禁用：

```text
_nearest_main_flow_block
following-block fallback
raw text block guessing
```

Materializer 行为：

```text
placement.status == placed:
  generate CALL_API using owner_worker_id / flow_ref / block_ref

placement.status != placed:
  do not generate CALL_API
  emit stage7_unresolved_api_call_materialization or api_call_missing_block_placement
```

### 11.5 测试计划

1. status unresolved -> no CALL_API.
2. status ambiguous -> no CALL_API.
3. status placed -> CALL_API exact block_ref.
4. `internal_comms` CALL_API block_ref is `sources are needed and available` IF block.
5. `pending_response_bindings` remains metadata, not outputs.

### 11.6 验收标准

1. No nearest-block fallback remains in active path.
2. API materialization diagnostics are visible.
3. Existing API deferred-validation behavior remains.

### 11.7 PM 审核清单

1. `rg "_nearest_main_flow_block|following-block|nearest" src/nl2spl/pipeline/stages/stage5_block_assembler src/nl2spl/pipeline/stages/stage7_step_extractor` has no active fallback.
2. Missing placement no longer creates CALL_API.
3. Rendered SPL no longer places CALL API under unrelated IF.

---

## 12. Phase R7：ProducerIndex v2 Relation-Aware Migration

### 12.1 目标

引入 `StepVariableRelationPlan`，让 ProducerIndex 只接受 `relation == produces`。

### 12.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
src/nl2spl/compiler/producer_index.py
src/nl2spl/pipeline/orchestrator.py
```

允许新增：

```text
tests/unit/pipeline/stage7/test_step_variable_relation_plan.py
tests/unit/compiler/test_producer_index_v2_relations.py
tests/integration/pipeline/test_internal_comms_relation_producer_index.py
```

### 12.3 禁止改动

```text
src/nl2spl/rendering/**
```

### 12.4 设计要求

Stage 7 must produce:

```text
intermediate["step_variable_relation_plan"]
```

ProducerIndex v2:

```text
primary source = StepVariableRelationPlan
relation == produces -> producer
relation != produces -> not producer
legacy StepIR.outputs without relation -> ignored or diagnostic step_variable_relation_missing
```

Relation matching must use:

```text
source text evidence
api contract evidence
user-confirmed repair evidence
symbol table variable candidates
```

`source text evidence` 必须通过以下结构化来源之一进入 relation：

```text
Stage 7 structured extraction output
route / construct metadata
API contract
user-confirmed repair
```

raw keyword matching alone is not valid relation authority. 例如不能因为看到 `record`、`maintain`、`produce` 等词就直接注册 producer；必须有变量提及、稳定别名或明确 relation evidence。

It must not use:

```text
required output pressure
renderer text
semantic similarity threshold
raw keyword fallback as sole authority
```

### 12.5 测试计划

1. `Maintain provenance...` relation to `source_evidence_set` is not produces.
2. `CALL_API` with unknown return contract is not produces.
3. `Produce a draft` produces `draft_communication_artifact`.
4. `Record assumptions log and completion status` produces both required outputs.
5. legacy `StepIR.outputs` without relation does not satisfy ProducerIndex.
6. relation diagnostics emitted for missing relation on legacy output.

### 12.6 验收标准

1. `source_evidence_set` has no producer from provenance step.
2. Existing legitimate producers still work.
3. ProducerIndex tests cover both v1 compatibility and v2 relation authority.

### 12.7 PM 审核清单

1. 检查 ProducerIndex does not trust StepIR.outputs alone.
2. 检查 required output missing does not create relation.
3. 检查 no raw renderer text dependency.

---

## 13. Phase R8：RequiredOutputFulfillmentState + Diagnostics Consolidation

### 13.1 目标

由 ProducerIndex 输出 `RequiredOutputFulfillmentState`，并整理 final/stage-local/report-only diagnostics。

### 13.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/producer_index.py
src/nl2spl/compiler/irs/checkers/post_normalize.py
src/nl2spl/compiler/diagnostic_registry.py
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/pipeline/orchestrator.py
```

允许新增：

```text
tests/unit/compiler/test_required_output_fulfillment_state.py
tests/unit/compiler/irs/test_required_output_deferred_diagnostics.py
tests/integration/pipeline/test_internal_comms_required_output_fulfillment.py
```

### 13.3 禁止改动

```text
src/nl2spl/rendering/**
examples/output/spl_editing_demo/run_demo.py
```

### 13.4 设计要求

ProducerIndex emits:

```text
intermediate["required_output_fulfillment"]
```

Diagnostic registry must include:

```text
api_call_missing_block_placement
control_region_unresolved
local_condition_unresolved
step_variable_relation_ambiguous
required_output_deferred
required_output_missing_source_backed_producer
```

Diagnostic layering:

```text
api_call_missing_block_placement -> final when API call cannot materialize
control_region_unresolved -> final if action cannot placement
local_condition_unresolved -> visible if action blocked
step_variable_relation_ambiguous -> final if required output affected
required_output_deferred -> visible, completion policy dependent
required_output_missing_source_backed_producer -> final for required output
```

### 13.5 测试计划

1. `source_evidence_set` is deferred or missing, not produced.
2. Deferred required output appears distinctly from missing.
3. Feedback report preserves missing/deferred/ambiguous/report-only.
4. SPL Editing issue inventory does not mark deferred API return as editable unless repair affordance exists.

### 13.6 验收标准

1. RequiredOutputFulfillmentState is emitted only by ProducerIndex.
2. IRS consumes fulfillment state, does not infer producers.
3. Feedback report has stable sections for deferred vs missing.

### 13.7 PM 审核清单

1. 检查 Stage 7 does not emit fulfillment state.
2. 检查 diagnostics are registered, not ad hoc strings.
3. 检查 deferred does not become produced.

---

## 14. Phase R9：E2E + Audit Freeze

### 14.1 目标

用真实 `internal_comms` demo 验证完整链路，并做静态反模式扫描。

### 14.2 可编辑范围

允许新增：

```text
artifacts/reviews/stage4_5_7_refactor/R9/
tests/integration/pipeline/test_internal_comms_stage4_5_7_refactor_e2e.py
```

允许修改：

```text
examples/usage.py  # only if explicit intermediate artifact dump is needed
```

### 14.3 禁止改动

```text
examples/input/internal_comms.txt
src/nl2spl/rendering/** for semantic fixes
```

### 14.4 E2E 验收矩阵

必须验证：

1. `examples/usage.py` 可重新生成 demo artifacts。
2. `stage1_span_slicer.json` 中 `s18/s20` guarded_action 正确。
3. `executable_action_placement_plan` 中 `s18` placement accepted。
4. `control_region_plan` 中：
   - `s17 local_if`
   - `s18 local_if`
   - `s20 local_if`
   - `s21 top_level_alternative`
5. `stage5_block_assembler.json` 中：
   - `IF sources are needed and available`
   - `IF required information is missing`
   - `IF enough required information is available`
6. `api_call_placements` 中 s18 API call status = placed with exact block_ref。
7. `WorkerStepPlanIR` 中 CALL_API block_ref matches `sources are needed and available` IF。
8. `StepVariableRelationPlan` 中 provenance does not produce `source_evidence_set`。
9. `ProducerIndex` 中 `source_evidence_set` is not produced by provenance step。
10. `RequiredOutputFulfillmentState` marks `source_evidence_set` as deferred or missing unless API return known。
11. final SPL does not contain:
    - CALL API inside `IF enough required information is available`
    - `Maintain provenance ... RESULT source_evidence_set SET`
    - top-level `ALTERNATIVE_FLOW required information is missing...`

### 14.5 静态反模式扫描

最终冻结必须运行并解释命中：

```powershell
rg -n "_nearest_main_flow_block|following-block|nearest.*block|pending_response_bindings.*producer|StepIR\\.outputs|ALTERNATIVE_FLOW.*required information is missing|Maintain provenance.*source_evidence_set" src tests docs examples
```

命中必须分类：

```text
allowed legacy test
allowed documentation
blocked production path
waived with owner/removal condition
```

### 14.6 必跑命令

```powershell
.venv\Scripts\python.exe examples\usage.py
.venv\Scripts\python.exe -m pytest tests\unit\ir tests\unit\pipeline tests\unit\compiler tests\integration\pipeline -q
.venv\Scripts\ruff check src\nl2spl\ir src\nl2spl\pipeline src\nl2spl\compiler tests\unit tests\integration
git diff --check
```

如全量测试过慢，阶段验收可先跑 scoped tests；R9 freeze 必须至少跑所有受影响目录的测试。

### 14.7 PM 审核清单

1. 确认所有 R0-R8 review reports 存在。
2. 确认 artifact manifest 含设计文档、实施计划、PM 证据 hash。
3. 确认无新增 skip / xfail。
4. 确认 renderer 未承担 semantic fix。
5. 确认 final SPL 只是观察面，核心验收来自 IR / ProducerIndex / diagnostics。

---

## 15. Decision Gate：ProducerIndex v2 Compatibility

### 15.1 目标

R7 前必须决定 legacy `StepIR.outputs` 的兼容策略，避免一次性破坏旧测试与旧路径。

### 15.2 推荐方案

```text
方案 A（推荐）：
  ProducerIndex v2 primary source = StepVariableRelationPlan。
  legacy StepIR.outputs 无 relation 时 ignored + diagnostic。
  对 legacy fixtures 通过 compatibility adapter 生成 relation == produces。

方案 B：
  ProducerIndex 同时信任 StepIR.outputs 与 relation plan。
  不推荐，会保留旧 authority leak。

方案 C：
  一次性删除 StepIR.outputs producer 语义。
  风险较高，可能扩大本轮范围。
```

### 15.3 必须回答的问题

1. 哪些 legacy tests 需要 adapter？
2. adapter 的移除阶段是什么？
3. `step_variable_relation_missing` 是否进入 final diagnostics？
4. SPL Editing repair-created StepIR 如何提供 relation？

### 15.4 验收标准

1. PM 明确批准后才能进入 R7。
2. 兼容 adapter 必须有 owner 和 removal condition。
3. 不得保留 ProducerIndex 双 truth source。

---

## 16. 端到端验收场景

### 16.1 internal_comms happy path

期望：

```text
IF required information is missing:
  INPUT ask highest-value clarifying questions

IF sources are needed and available:
  CALL ApprovedSourceRecipesAPI
  COMMAND maintain provenance for externally sourced facts

IF enough required information is available:
  COMMAND produce draft
```

且 `source_evidence_set` 不被 provenance step 生产。

### 16.2 API placement missing negative

构造 API call demand 无 exact block placement：

```text
APICallPlacementIR.status = unresolved
CALL_API not materialized
diagnostic visible
```

### 16.3 local conditional vs alternative flow

Clarification local gate 不得成为 top-level alternative；revision branch 保持 top-level alternative。

### 16.4 Producer relation negative

Provenance / validation / metadata action 不得满足 required output producer。

### 16.5 Deferred API response

API call 存在但 return contract unknown：

```text
pending binding exists
ProducerIndex producer absent
RequiredOutputFulfillmentState.status = deferred or missing
```

---

## 17. PM 总审核清单

每个阶段提交审核时，PM 必须检查：

1. 是否严格对齐设计文档。
2. 是否扩大了范围到 renderer 或 unrelated SPL Editing behavior。
3. 是否新增未确认的 LLM prompt/schema 改动。
4. 是否新增 rule-based semantic fallback。
5. 是否新增或保留 nearest-block / following-block fallback。
6. API-owned span 是否仍保留 placement ownership。
7. generic extraction exclusion 是否没有影响 placement。
8. ControlRegionPlan 是否通过 validator 后才被 Stage 5 消费。
9. top-level alternative 与 local IF 是否按 control scope 区分。
10. StepVariableRelation 是否成为 ProducerIndex primary source。
11. legacy StepIR.outputs 是否被降级。
12. RequiredOutputFulfillmentState 是否只由 ProducerIndex 输出。
13. diagnostics 是否进入 final / stage-local / report-only 的明确分层。
14. deferred 是否没有被当成 produced。
15. 是否有新增 skip / xfail。
16. 是否有新增代码路径无测试。
17. artifact/checkpoint key 是否稳定。
18. review report 是否包含命令输出、artifact paths、residual risk。

---

## 18. 阶段完成顺序

```text
R0  Characterization Tests
R1  Shared Model Freeze
R2  ExecutableActionPlacement Contract
R3  Stage 3.5 Ownership Repair
R4  ControlRegionPlan Builder / Validator
R5  Stage 4/5 Control Placement + APICallPlacementIR
R6  Stage 7 Fail-Closed API Materialization
Gate ProducerIndex v2 Compatibility
R7  ProducerIndex v2 Relation-Aware Migration
R8  RequiredOutputFulfillmentState + Diagnostics Consolidation
R9  E2E + Audit Freeze
```

依赖关系：

```text
R1 blocks all implementation phases.
R2 must precede R3/R4.
R4 must precede R5.
R5 must precede R6.
ProducerIndex v2 compatibility gate must precede R7.
R7 must precede R8.
R9 requires R0-R8 independently accepted.
```

---

## 19. 最终冻结条件

本计划完成时必须满足：

```text
1. internal_comms final SPL 业务顺序与 source intent 一致。
2. s18 API action has local IF placement: sources are needed and available.
3. s17 clarification is local IF, not top-level ALTERNATIVE_FLOW.
4. CALL_API has exact block placement or is not materialized.
5. Maintain provenance does not produce source_evidence_set.
6. source_evidence_set is produced only by source-backed producer, otherwise deferred/missing.
7. ProducerIndex no longer trusts legacy StepIR.outputs alone.
8. all new artifacts are checkpointed and round-trip serializable.
9. diagnostics preserve final/stage-local/report-only disposition.
10. renderer has no semantic repair logic.
```
