# Stage 6.5 Condition Variable Reference Resolution v2 实施计划

本文档严格基于 `docs/design/stage6_5_condition_variable_reference_resolution_design_zh.md` v2 制定。实施目标是：在 worker-aware pipeline 中建立 **LLM-guided + symbol-constrained** 的 condition variable reference extraction，并通过 Stage 9.5 完成 visibility、availability、semantic materialization、composite rewrite 与 final diagnostics 闭环。

本计划替代旧版 explicit `<REF>` only 实施计划。旧版中“Stage 6.5 不调用 LLM / MVP 只解析 `<REF>`”的假设已废弃。

适用范围：

```text
In scope:
  - IF / WHILE / FOR 的 BlockIR.condition_text
  - ALTERNATIVE_FLOW / EXCEPTION_FLOW 的 FlowStructureIR.condition_text
  - explicit grammar token: <REF>name</REF> / <REF>*name</REF> / <REF>a_b.x</REF>
  - 纯自然语言 condition_text 的 LLM semantic variable reference extraction
  - candidate symbol view construction from SymbolTable / ResourceRegistryIR
  - deterministic admission: symbol exists / qualified field valid / source-backed evidence
  - ConditionVariableReferencePlan intermediate
  - Stage 9.5 scope visibility / execution availability / semantic ref materialization / composite rewrite validation
  - final compile/report/snapshot diagnostics
  - final SPL 使用 rewrite-approved condition_text

Out of scope:
  - ELSEIF branch condition 建模
  - 让 LLM 自由发明 accepted variables
  - 让 LLM 直接修改 SymbolTable / ResourceRegistryIR
  - 让 LLM 直接决定 final severity / blocks_rendering / blocks_completion
  - StepVariableRelationPlan 泛化为 ElementVariableRelationPlan
  - ProducerIndex 消费 condition refs
  - condition ref unresolved 自动生成 Fix with AI repair affordance
  - 从 rendered SPL text 反推 condition refs
```

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
Stage 4 Flow Assembly
  -> 调用既有 LLM
  -> WorkerFlowPlanIR / AlternativeFlow.condition_text / ExceptionFlow.condition_text
  -> owns flow-level condition placement
  -> 不做 condition variable reference extraction

Stage 5 Block Assembly
  -> 调用既有 LLM
  -> WorkerBlockPlanIR / BlockIR.condition_text
  -> owns block-level condition placement
  -> 不做 condition variable reference extraction

Stage 6 Resource Extraction
  -> ResourceRegistryIR / SymbolTable / structured type definitions
  -> owns symbol/type discovery
  -> 不理解 control decision ordering

Shared ReferenceToken parser
  -> parse explicit <REF> grammar token
  -> 只作为 Stage 6.5 的 evidence source 之一
  -> 不做 semantic matching / symbol admission / LLM 调用

Stage 6.5 Condition Variable Reference Extractor
  -> owner collection
  -> explicit ReferenceToken extraction
  -> LLM semantic condition reference extraction
  -> candidate symbol view construction
  -> deterministic SymbolTable / ResourceRegistryIR admission
  -> ConditionVariableReferencePlan
  -> 不写 StepVariableRelationPlan / ProducerIndex

Stage 7 Step Extraction
  -> 继续调用既有 LLM
  -> StepIR / StepVariableRelationPlan
  -> 不消费 condition refs

Stage 9.5 Condition Variable Validator
  -> scope visibility validation
  -> execution availability validation
  -> self-block rejection
  -> semantic ref materialization
  -> composite output rewrite
  -> final condition diagnostics

Stage 10 Worker Assembly
  -> 消费 Stage 9.5 normalized flow/block plans
  -> materialize rewrite-approved condition_text into WorkerIR

Stage 11 SPL Renderer
  -> 只渲染 rewrite-approved condition_text
  -> 不做 ref extraction / LLM / symbol lookup / rewrite / validation
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. **Stage 6.5 是独立 pipeline stage，不是 IRS construct。** 不得把 `ConditionVariableReferenceIR` 注册进 IRS construct registry。
2. **Stage 4 / Stage 5 保持既有 LLM placement 职责。** 不得把 Stage 6.5 的 semantic extraction 回塞到 Stage 4/5 prompt 中。
3. **Stage 6.5 必须位于 Stage 6 后、Stage 7 前。** 它需要 SymbolTable / ResourceRegistryIR，但不得依赖 WorkerStepPlanIR。
4. **Stage 6.5 允许调用 LLM，但必须 condition-owner scoped。** 不允许给 LLM 全量无关源文档、ProducerIndex、StepVariableRelationPlan、rendered SPL text 或 repair catalog。
5. **LLM output 不是 authority。** LLM 只提出 condition read candidates；resolved admission 必须由 deterministic validator 基于 candidate symbol view、SymbolTable、ResourceRegistryIR 决定。
6. **Candidate symbol view 是唯一可接纳 symbol 来源。** LLM selected_symbol 不在 candidate_symbols 中时必须 reject，不得自动创建 SymbolTable variable。
7. **Explicit `<REF>` 是强 evidence，但不是唯一 evidence。** 纯自然语言 condition 可以经 LLM + deterministic admission 解析为 condition read dependency。
8. **Condition refs 不得进入 `StepVariableRelationPlan`。** 包括 `producing_relations()`、`consuming_relations()`、diagnostics 或任何 ProducerIndex 输入。
9. **ProducerIndex 不消费 condition refs。** condition read 只能作为 Stage 9.5 visibility / availability validation input。
10. **Stage 6.5 diagnostics 不是 final compile diagnostics。** Stage 6.5 只产出 resolver-local status/evidence；final severity、`blocks_rendering`、`blocks_completion` 由 Stage 9.5 或 diagnostic consolidator 决定。
11. **Semantic ref materialization 的提交点是 Stage 9.5。** Stage 6.5 不得直接改写 BlockIR / FlowStructureIR / WorkerIR。
12. **Composite output rewrite 的提交点是 Stage 9.5。** Stage 6.5 不得提前改写 `condition_text`。
13. **Renderer 只消费 rewrite-approved condition_text。** Renderer 不允许新增 ref parser、LLM call、SymbolTable lookup、fallback rewrite 或 validation。
14. **ELSEIF MVP 不支持。** 不得通过 rendered SPL text 反推 ELSEIF condition；完整支持必须先新增 `BranchConditionIR / ConditionalBranchIR`。
15. **`reference_id` 必须稳定。** 同一 `owner_ref` 下 explicit / llm / unresolved candidates 均按 deterministic order 生成 ID。
16. **ConditionTextRewrite 必须保留 original 与 rewritten text。** 不允许只留下最终文本而丢失 evidence。
17. **所有 checkpoint key 使用 `src/nl2spl/pipeline/intermediate_keys.py` 常量。** 禁止散落字符串 key。
18. **无 runtime semantic fallback。** 如果 LLM 不可用或 schema invalid，必须 fail closed 为 resolver-local diagnostic，不允许 keyword/substr matching 顶替 LLM。
19. **无新增 skip / xfail / 弱断言。** 所有新增测试必须能在阶段完成时稳定通过。

---

## 3. LLM / Rule-based 决策约束

本计划允许新增 **唯一一类 LLM 调用**：Stage 6.5 condition-owner scoped semantic reference extraction。

允许的 LLM 行为：

```text
1. 判断 condition_text 是否语义读取变量。
2. 从 candidate_symbols 中选择 selected_symbol。
3. 输出 qualified_ref，但 top-level 必须等于 selected_symbol。
4. 输出 evidence_text，必须来自 condition_text 或 owner source excerpt。
5. 输出 unresolved_candidates，表示语义依赖存在但候选 symbol 表无合法匹配。
6. 输出 confidence / reason 作为 evidence metadata。
```

禁止的 LLM 行为：

```text
1. 输出不在 candidate_symbols 中的 selected_symbol 并被接纳为 resolved。
2. 直接创建或修改 SymbolTable / ResourceRegistryIR。
3. 直接决定 final severity / blocks_rendering / blocks_completion。
4. 直接输出 repair action / Fix with AI affordance。
5. 接收 ProducerIndex / StepVariableRelationPlan / WorkerStepPlanIR 作为上下文。
6. 从 rendered SPL text 反推 refs。
7. 修改 Stage 4 / Stage 5 placement。
```

允许的确定性逻辑：

```text
1. 从 WorkerFlowPlanIR / WorkerBlockPlanIR 收集 condition owners。
2. 用 ReferenceToken parser 提取 explicit <REF> tokens。
3. 从 SymbolTable / ResourceRegistryIR 构造 candidate symbol view。
4. 校验 LLM selected_symbol 是否在 candidate_symbols 中。
5. 校验 qualified field 是否在 structured DATA_TYPE 中。
6. 校验 evidence_text 是否 source-backed。
7. 对 explicit ref 与 LLM semantic ref 进行 deterministic merge / dedup / ambiguity handling。
8. 生成 stable reference_id。
9. 在 Stage 9.5 做 visibility / availability / composite rewrite / materialization。
```

以下行为必须提交新的设计确认：

1. 修改 Stage 4 / Stage 5 prompt/schema 来直接输出 condition references。
2. 在 LLM 失败时用 keyword/substr/similarity fallback 推断 refs。
3. 支持 ELSEIF branch condition。
4. 给 condition issue 加 spl editing repair affordance。
5. 将 StepVariableRelationPlan 泛化为 ElementVariableRelationPlan。
6. 让 ProducerIndex 接收 condition refs。
7. 让 renderer 接收 ConditionVariableReferencePlan 或自行 rewrite refs。
8. 自动将 unresolved LLM candidate admission 为新 variable。

---

## 4. Phase C0：Characterization 与范围锁定

该阶段不引入生产行为，只锁定当前 gap、受保护边界和 fixture。C0 的 characterization 在 C8 前必须删除或改写为新 contract tests。

### 4.1 目标

证明当前 pipeline 未建模 condition read dependency，尤其是 implicit natural-language condition dependency：

```text
1. explicit <REF>x</REF> condition 当前没有专门 ConditionVariableReferencePlan。
2. pure NL condition “when enough evidence has been collected” 当前不会形成 condition reads evidence。
3. composite output rewrite 当前不覆盖 condition_text。
4. renderer 当前直接渲染 flow/block condition_text，不负责 ref validation。
5. StepVariableRelationPlan 当前只描述 step variable relations。
```

### 4.2 可编辑范围

允许新增：

```text
tests/fixtures/condition_variable_reference/
  explicit_if_ref.json
  implicit_evidence_condition.json
  alternative_flow_implicit_ref.json
  exception_flow_unresolved_condition.json
  composite_condition_ref.json

tests/unit/pipeline/stages/test_cvr0_current_gap_characterization.py
```

允许修改：

```text
无生产代码修改。
```

### 4.3 禁止改动

Phase C0 禁止修改：

```text
src/nl2spl/compiler/
src/nl2spl/ir/
src/nl2spl/pipeline/
src/nl2spl/validator/
prompts/
```

### 4.4 设计要求

Fixture 必须覆盖：

```text
1. explicit condition:
   IF <REF>required_information</REF> is available

2. implicit condition:
   when enough evidence has been collected

3. unresolved semantic condition:
   if source access is insufficient

4. flow-level condition:
   ALTERNATIVE_FLOW / EXCEPTION_FLOW condition without block mirror

5. composite rewrite condition:
   condition semantically or explicitly reads a, later rewritten to a_b.a
```

### 4.5 测试计划

新增测试必须覆盖：

1. 当前 intermediate 中不存在 `condition_variable_reference_plan`。
2. 当前 implicit condition 不会形成 condition read dependency。
3. 当前 renderer 不解析 condition refs。
4. 当前 `StepVariableRelationPlan.producing_relations()` 不包含 condition owner。
5. 当前 composite output applier 不生成 `ConditionTextRewrite`。

### 4.6 验收标准

Phase C0 通过条件：

1. characterization tests 均通过。
2. 无生产代码 diff。
3. 无 prompt/schema diff。
4. 无新增 skip / xfail。
5. fixtures 能被 C1-C8 复用。

### 4.7 PM 审核清单

审核时必须检查：

1. C0 是否只记录当前 gap，没有提前实现 extractor。
2. fixture 是否覆盖 explicit 与 implicit condition。
3. fixture 是否覆盖 flow-level 和 block-level condition。
4. fixture 是否包含 composite rewrite 场景。
5. 是否没有 skip / xfail。

---

## 5. Phase C1：IR、checkpoint key 与 serializer

该阶段新增 read-only intermediate IR，不接入 pipeline 行为。

### 5.1 目标

新增：

```text
ConditionOwnerKind
ConditionVariableReferenceStatus
ConditionReferenceEvidenceKind
ConditionVariableReferenceIR
ConditionTextRewrite
ConditionVariableReferencePlan
CONDITION_VARIABLE_REFERENCE_PLAN checkpoint key
payload / serializer round-trip
```

### 5.2 可编辑范围

允许新增：

```text
src/nl2spl/ir/condition_variable_reference_ir.py

tests/unit/ir/test_condition_variable_reference_ir.py
tests/unit/compiler/artifacts/snapshot/test_condition_variable_reference_serializers.py
```

允许修改：

```text
src/nl2spl/ir/__init__.py
src/nl2spl/pipeline/intermediate_keys.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_plan.py
src/nl2spl/compiler/artifacts/snapshot/serialization/registry.py
```

### 5.3 禁止改动

Phase C1 禁止修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/
src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/pipeline/stages/stage9_5_normalizer/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/step_variable_relation_ir.py
prompts/
```

### 5.4 设计要求

`ConditionVariableReferenceStatus`：

```python
Literal[
    "resolved",
    "unresolved",
    "ambiguous",
    "invalid_qualified_ref",
    "rejected",
]
```

`ConditionReferenceEvidenceKind`：

```python
Literal[
    "explicit_ref_token",
    "llm_condition_semantic_match",
    "llm_unresolved_condition_symbol",
]
```

`ConditionVariableReferenceIR` 必须包含：

```python
reference_id: str
owner_kind: ConditionOwnerKind
owner_ref: str
condition_text: str
ref_text: str | None
canonical_ref: str | None
top_level_name: str | None
qualified_path: tuple[str, ...]
status: ConditionVariableReferenceStatus
source_span_ids: tuple[str, ...]
worker_id: str | None
flow_ref: str | None
block_ref: str | None
evidence_kind: ConditionReferenceEvidenceKind
evidence_text: str | None
selected_symbol: str | None
proposed_symbol_text: str | None
confidence: Literal["high", "medium", "low"] | None
reason: str | None
```

`reference_id` 规则：

```text
cond_ref_{owner_ref_hash}_{source_kind}_{index}

owner_ref_hash = sha256(owner_ref.encode("utf-8")).hexdigest()[:10]
source_kind = explicit | llm | unresolved
index = deterministic order within owner_ref and source_kind
```

`ConditionTextRewrite.rewrite_reason` 必须包含：

```python
Literal[
    "composite_output_rewrite",
    "qualified_ref_normalization",
    "llm_semantic_ref_materialization",
]
```

`ConditionVariableReferencePlan` 必须提供：

```text
to_payload()
from_payload()
references_by_owner()
rewrites_by_owner()
final_condition_text(owner_ref, original_text)
```

### 5.5 测试计划

新增单元测试必须覆盖：

1. explicit / llm / unresolved reference_id 均稳定。
2. `ConditionVariableReferenceIR` frozen，不可被下游静默修改。
3. evidence_kind 字段 round-trip 不丢失。
4. llm semantic fields：`evidence_text`、`selected_symbol`、`confidence` round-trip。
5. unresolved candidate fields：`proposed_symbol_text` round-trip。
6. `ConditionTextRewrite.source_reference_ids` 必须能匹配已有 reference IDs。
7. `ConditionVariableReferencePlan.to_payload()` 不丢 tuple 字段。
8. serializer round-trip 后字段完全一致。
9. intermediate key 常量存在且无散落重复字符串。

### 5.6 验收标准

Phase C1 通过条件：

1. IR / serializer tests 全部通过。
2. 生产 pipeline 行为不变。
3. IR 不 import Stage 6.5 extractor、Stage 9.5 validator、ProducerIndex 或 renderer。
4. `CONDITION_VARIABLE_REFERENCE_PLAN` 只能通过 `intermediate_keys.py` 引用。
5. 无新增 skip / xfail。

### 5.7 PM 审核清单

审核时必须检查：

1. IR 是否已支持 explicit + LLM semantic + unresolved candidate。
2. 是否没有保留 explicit-only schema。
3. serializer 是否覆盖 `text_rewrites` 和 LLM evidence fields。
4. `ConditionVariableReferencePlan` 是否 read-only intermediate，而不是 IRS construct。
5. 是否未修改 `StepVariableRelationPlan`。

---

## 6. Phase C2：Shared ReferenceToken parser

该阶段引入 grammar-level tokenizer。它是 explicit token parser，不是 semantic extractor。

### 6.1 目标

新增共享 parser：

```text
src/nl2spl/compiler/reference_parser.py
```

用于解析 `DESCRIPTION_WITH_REFERENCES` 中的 explicit `<REF>...</REF>` token，并保留 offsets 以支持后续 deterministic rewrite。

### 6.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/reference_parser.py

tests/unit/compiler/test_reference_parser.py
```

允许修改：

```text
src/nl2spl/compiler/__init__.py
```

### 6.3 禁止改动

Phase C2 禁止修改：

```text
src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/
src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/pipeline/stages/stage9_5_normalizer/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/ir/step_variable_relation_ir.py
src/nl2spl/compiler/producer_index.py
prompts/
```

### 6.4 设计要求

`ReferenceToken` 必须表达：

```python
@dataclass(frozen=True)
class ReferenceToken:
    raw_text: str
    name: str
    is_by_value: bool
    top_level_name: str
    qualified_path: tuple[str, ...]
    start_offset: int
    end_offset: int
```

Parser 必须：

```text
1. 识别 <REF>x</REF>。
2. 识别 <REF>*x</REF>，并设置 is_by_value=True。
3. 识别 <REF>a_b.x</REF>。
4. 保留 raw_text、start_offset、end_offset。
5. 按 start_offset 原序返回。
6. 不做 symbol lookup。
7. 不做 rewrite。
8. 不做 semantic matching。
9. 不调用 LLM。
```

非法 token 策略：

```text
<REF></REF>       -> parser diagnostic 或 ValueError，不能静默忽略
<REF>a.</REF>     -> invalid token，交给 grammar/parser validation，不映射成 condition_variable_invalid_qualified_ref
<REF>a..b</REF>   -> invalid token
```

### 6.5 测试计划

新增单元测试必须覆盖：

1. 单个 `<REF>x</REF>`。
2. 多个 refs 按 offset 顺序返回。
3. `<REF>*x</REF>` by-value 标记。
4. `<REF>a_b.x</REF>` qualified path。
5. raw_text 和 offset 精确等于原文区间。
6. 非 ref 纯文本返回空 tokens。
7. `<REF>a.</REF>` 不被当作合法 qualified ref。
8. 文本 `when evidence is collected` 不返回 token。

### 6.6 验收标准

Phase C2 通过条件：

1. parser tests 全部通过。
2. parser 模块不 import `SymbolTable`、`ResourceRegistryIR`、`StepIR`、`ProducerIndex` 或 LLM client。
3. 无 pipeline 行为变化。
4. 无 prompt/schema 变化。
5. 无新增 skip / xfail。

### 6.7 PM 审核清单

审核时必须检查：

1. parser 是否只是 explicit token parser。
2. 是否没有 semantic guessing。
3. offset 是否有测试。
4. parser 是否未被 renderer 调用。
5. parser 是否没有被误当作完整 Stage 6.5 extractor。

---

## 7. Phase C3：Stage 6.5 prompt/schema 与 candidate symbol view

该阶段定义 Stage 6.5 LLM 输入/输出 contract 和 candidate symbol view，但不接入 orchestrator。

### 7.1 目标

新增 Stage 6.5 LLM contract：

```text
condition-owner scoped prompt
candidate symbol view builder
strict LLM output schema
response parser / schema validator
```

### 7.2 可编辑范围

允许新增：

```text
prompts/stage6_5_condition_reference_system.txt

src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/
  __init__.py
  candidate_symbols.py
  prompt_builder.py
  schemas.py
  response_parser.py

tests/unit/pipeline/stages/test_stage6_5_condition_reference_prompt.py
tests/unit/pipeline/stages/test_stage6_5_candidate_symbol_view.py
tests/unit/pipeline/stages/test_stage6_5_condition_reference_response_parser.py
```

允许修改：

```text
src/nl2spl/llm/prompts.py
  仅允许注册 stage6_5_condition_reference prompt 名称。
```

### 7.3 禁止改动

Phase C3 禁止修改：

```text
prompts/stage4_system.txt
prompts/stage5_system.txt
prompts/stage7_system.txt
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/pipeline/stages/stage9_5_normalizer/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/step_variable_relation_ir.py
```

### 7.4 设计要求

LLM request 必须包含：

```text
owner_ref
owner_kind
worker_id
flow_ref / block_ref
condition_text
source_span_ids
source excerpts for owner
candidate_symbols visible from current worker/global scope
candidate structured fields for each structured symbol
explicit_ref_tokens parsed from condition_text, if any
```

LLM request 不得包含：

```text
full unrelated source document
ProducerIndex
StepVariableRelationPlan
WorkerStepPlanIR
rendered SPL text
repair catalog
```

LLM response schema：

```json
{
  "owner_ref": "...",
  "references": [
    {
      "relation": "condition_reads",
      "selected_symbol": "...",
      "qualified_ref": "...",
      "evidence_text": "...",
      "confidence": "high|medium|low",
      "reason": "..."
    }
  ],
  "unresolved_candidates": [
    {
      "proposed_symbol_text": "...",
      "evidence_text": "...",
      "reason": "..."
    }
  ]
}
```

Candidate symbol view rules：

```text
1. Candidate symbols come only from SymbolTable current worker + global visible scope.
2. Structured fields come only from ResourceRegistryIR.types.
3. Include symbol descriptions and source_span_ids when available.
4. Do not include ProducerIndex or step order information.
5. Stable ordering: worker-local symbols first, then global, sorted by name.
```

Response parser hard rules：

```text
1. owner_ref in response must match request owner_ref.
2. relation must be condition_reads.
3. selected_symbol outside candidate_symbols -> parsed as rejected candidate, not resolved.
4. confidence outside enum -> schema error.
5. evidence_text not in condition_text/source_excerpt -> low confidence or rejected by admission phase.
6. severity / repair_action / blocks_* fields in response -> schema error.
```

### 7.5 测试计划

新增测试必须覆盖：

1. prompt includes condition_text and candidate_symbols。
2. prompt excludes ProducerIndex / StepVariableRelationPlan / rendered SPL text。
3. candidate symbol view includes worker-local + global symbols。
4. candidate symbol view includes structured field candidates。
5. candidate symbol view stable sorted。
6. valid LLM response parses。
7. response owner_ref mismatch rejected。
8. selected_symbol outside candidate_symbols parsed as rejected。
9. illegal severity / repair fields rejected。
10. unresolved_candidates parse correctly。

### 7.6 验收标准

Phase C3 通过条件：

1. prompt/schema/candidate view tests 全部通过。
2. Stage 4/5/7 prompts 未修改。
3. 未接入 orchestrator。
4. 无 Stage 9.5 behavior 变化。
5. 无新增 skip / xfail。

### 7.7 PM 审核清单

审核时必须检查：

1. Stage 6.5 LLM contract 是否 condition-owner scoped。
2. LLM 是否只能从 candidate_symbols 选择 resolved candidate。
3. schema 是否禁止 severity / repair action。
4. 是否没有把 ProducerIndex 暴露给 LLM。
5. 是否没有修改 Stage 4/5 prompt。

---

## 8. Phase C4：Stage 6.5 extractor 与 deterministic admission

该阶段实现 Stage 6.5 生产 `ConditionVariableReferencePlan`，但暂不接入 orchestrator 默认路径。

### 8.1 目标

新增完整 Stage 6.5 extractor：

```text
owner collection
explicit token extraction
LLM semantic extraction
merge / dedup
SymbolTable / ResourceRegistryIR deterministic admission
resolver-local diagnostics
```

### 8.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/
  owner.py
  extractor.py
  admission.py
  diagnostics.py
  merger.py
  qualified_ref.py

tests/unit/pipeline/stages/test_stage6_5_condition_owner_collection.py
tests/unit/pipeline/stages/test_stage6_5_condition_reference_extractor.py
tests/unit/pipeline/stages/test_stage6_5_condition_reference_admission.py
tests/unit/pipeline/stages/test_stage6_5_condition_reference_boundaries.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/__init__.py
```

### 8.3 禁止改动

Phase C4 禁止修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/pipeline/stages/stage9_5_normalizer/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/step_variable_relation_ir.py
prompts/stage4_system.txt
prompts/stage5_system.txt
prompts/stage7_system.txt
```

### 8.4 设计要求

Extractor 输入必须是：

```text
resolved_spans
worker_flow_plan
worker_block_plan
worker_plan
symbol_table
resource_registry
llm_client
```

Extractor 不得包含：

```text
WorkerStepPlanIR
StepIR
StepVariableRelationPlan
ProducerIndex
WorkerIR
renderer
repair catalog
```

Owner model：

```python
@dataclass(frozen=True)
class ConditionOwner:
    owner_kind: ConditionOwnerKind
    owner_ref: str
    worker_id: str | None
    flow_ref: str | None
    block_ref: str | None
    condition_text: str
    source_span_ids: tuple[str, ...]
```

owner_ref 构造建议：

```text
block:{worker_id}:{block_id}:condition
alternative_flow:{worker_id}:{flow_id}:condition
exception_flow:{worker_id}:{flow_id}:condition
```

Admission rules：

```text
explicit_ref_token:
  - top-level exists -> selected_symbol set
  - qualified field valid -> resolved
  - missing top-level -> unresolved
  - missing field -> invalid_qualified_ref
  - same name ambiguous -> ambiguous

llm_condition_semantic_match:
  - selected_symbol in candidate_symbols -> eligible
  - qualified_ref top-level matches selected_symbol -> eligible
  - evidence_text source-backed -> eligible
  - all eligible -> resolved
  - selected_symbol outside candidate_symbols -> rejected
  - evidence not source-backed -> rejected or low-confidence unresolved

llm_unresolved_condition_symbol:
  - never creates SymbolTable variable
  - status unresolved
  - diagnostic evidence only
```

Merge rules：

```text
1. explicit_ref_token has higher priority than LLM semantic candidate for the same evidence span.
2. LLM semantic candidate may add additional condition reads not covered by explicit refs.
3. explicit and LLM disagreeing on same evidence_text -> ambiguous unless exact deterministic resolution exists.
4. duplicate references by canonical_ref under same owner are deduped with combined evidence metadata.
```

### 8.5 测试计划

新增单元测试必须覆盖：

1. IF block condition explicit `<REF>x</REF>` -> `explicit_ref_token` resolved。
2. Pure NL condition “when enough evidence has been collected” -> LLM selected `evidence` -> resolved。
3. LLM selected_symbol outside candidate_symbols -> rejected。
4. LLM unresolved candidate -> unresolved reference evidence。
5. evidence_text not source-backed -> rejected。
6. invalid qualified field -> invalid_qualified_ref。
7. explicit and LLM duplicate same ref -> dedup。
8. explicit and LLM conflict -> ambiguous。
9. alternative flow without block mirror -> owner retained。
10. exception flow without block mirror -> owner retained。
11. flow/block mirror dedup keeps block owner。
12. extractor does not import Stage 7 / ProducerIndex / renderer。
13. failed LLM call produces resolver-local diagnostic, not keyword fallback。

### 8.6 验收标准

Phase C4 通过条件：

1. extractor/admission tests 全部通过。
2. extractor 只返回 `ConditionVariableReferencePlan`。
3. no orchestrator integration yet。
4. no StepVariableRelationPlan / ProducerIndex modification。
5. no prompt changes outside Stage 6.5。
6. no skip / xfail。

### 8.7 PM 审核清单

审核时必须检查：

1. 是否支持 implicit LLM semantic condition refs。
2. 是否没有退回 explicit-only。
3. deterministic admission 是否是 resolved authority。
4. LLM failure 是否 fail closed，而非 keyword fallback。
5. unresolved 是否没有变成 producer repair。

---

## 9. Phase C5：Orchestrator integration 与 intermediate checkpoint

该阶段把 Stage 6.5 接入 Stage 6 后、Stage 7 前。仍不得改变 Stage 7 relation semantics。

### 9.1 目标

在 worker-aware pipeline 中新增执行点：

```text
Stage 6 Resource Extraction
  -> Stage 6.5 Condition Variable Reference Extraction
  -> Stage 7 Step Extraction
```

并将 `ConditionVariableReferencePlan` 写入 `intermediate` 与可选 checkpoint。

### 9.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/intermediate_keys.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_compile.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_plan.py
```

允许新增：

```text
tests/integration/pipeline/test_stage6_5_condition_reference_integration.py
tests/unit/pipeline/test_condition_reference_intermediate_key.py
```

### 9.3 禁止改动

Phase C5 禁止修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/step_variable_relation_ir.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/
prompts/stage4_system.txt
prompts/stage5_system.txt
prompts/stage7_system.txt
```

### 9.4 设计要求

Orchestrator 中必须在以下位置插入：

```text
worker_scoped_resources, symbol_table, filter_warns = _run_stage6_worker_scoped(...)
...
condition_variable_reference_plan = _run_stage6_5_condition_reference_extraction(
    resolved_spans,
    worker_flow_plan,
    worker_block_plan,
    worker_plan,
    symbol_table,
    resources,
)
...
_run_stage7_worker_scoped(...)
```

Intermediate 写入必须使用：

```python
ik.CONDITION_VARIABLE_REFERENCE_PLAN
```

如果 `save_intermediate` 开启，checkpoint payload 必须写入：

```text
examples/output/<run>/condition_variable_reference_plan.json
```

Stage 7 调用不得新增参数：

```text
condition_variable_reference_plan
```

MVP 中 Stage 7 不消费 condition refs。

### 9.5 测试计划

新增测试必须覆盖：

1. pipeline intermediate 包含 `condition_variable_reference_plan`。
2. `save_intermediate=True` 时输出 checkpoint payload。
3. Stage 6.5 在 Stage 7 前执行。
4. Stage 7 的 `StepVariableRelationPlan` 不包含 condition owner。
5. implicit NL condition 通过 Stage 6.5 mock LLM 形成 condition read reference。
6. LLM selected_symbol outside candidates 被 rejected，不进入 resolved。
7. Stage 6.5 resolver-local diagnostics 不直接进入 final compile diagnostics。
8. flow-level exception condition without block mirror 被写入 plan。

### 9.6 验收标准

Phase C5 通过条件：

1. integration tests 全部通过。
2. `CONDITION_VARIABLE_REFERENCE_PLAN` 无散落字符串 key。
3. Stage 7 signature 未因 condition refs 膨胀。
4. ProducerIndex 结果不因 condition refs 变化。
5. Stage 4/5/7 prompts 未修改。
6. 无新增 skip / xfail。

### 9.7 PM 审核清单

审核时必须检查：

1. Stage 6.5 是否确实在 Stage 6 后、Stage 7 前。
2. 是否没有把 condition refs 传入 Stage 7。
3. LLM mock 是否符合 strict schema。
4. rejected LLM candidate 是否没有被 admitted。
5. final compile diagnostics 是否尚未由 Stage 6.5 直接决定。

---

## 10. Phase C6：Stage 9.5 visibility / availability / materialization / composite rewrite

该阶段是 final semantic authority。它消费 Stage 6.5 analysis artifact，并产出 final diagnostics 与 rewrite-approved condition text。

### 10.1 目标

新增 Stage 9.5 validator：

```text
ConditionVariableVisibilityValidator
ConditionReferenceRewriteApplier
ConditionSemanticRefMaterializer
```

负责：

```text
1. scope visibility validation
2. execution availability validation
3. self-block rejection
4. llm semantic ref materialization
5. composite output reference rewrite
6. ConditionTextRewrite generation
7. final condition variable diagnostics
8. 更新 normalized WorkerFlowPlanIR / WorkerBlockPlanIR 中的 renderable condition_text
```

### 10.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/condition_variable_validator.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/condition_text_rewriter.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/condition_semantic_materializer.py

tests/unit/pipeline/stages/test_stage9_5_condition_variable_validator.py
tests/unit/pipeline/stages/test_stage9_5_condition_text_rewriter.py
tests/unit/pipeline/stages/test_stage9_5_condition_semantic_materializer.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/diagnostic_registry.py
src/nl2spl/compiler/diagnostic_consolidator.py
```

### 10.3 禁止改动

Phase C6 禁止修改：

```text
src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/extractor.py
  除非只是补充 evidence 字段，不得把 final validation 前移到 Stage 6.5。

src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/step_variable_relation_ir.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/
prompts/
```

### 10.4 设计要求

Validator 输入必须是：

```text
ConditionVariableReferencePlan
WorkerFlowPlanIR
WorkerBlockPlanIR
WorkerStepPlanIR
SymbolTable
StepVariableRelationPlan
CompositeOutputPlan
ProducerIndex or producer lookup view
```

Validator 不得：

```text
1. 调用 LLM。
2. 猜测 missing refs。
3. 发明 variables。
4. 生成 repair affordance。
5. 向 StepVariableRelationPlan 写入 condition relation。
6. 修改 ProducerIndex。
7. 从 rendered SPL text 反推 refs。
```

Visibility 判断：

```text
pass:
  - top-level variable 在 current worker scope 可见
  - 或 global scope 可见

fail:
  - variable 不在 owner worker/global visible scope
  - 或 ambiguous/rejected 未被 Stage 6.5 admitted as resolved
```

Availability 判断：

```text
pass:
  - worker input / global input
  - 或 producer 在 decision point 之前且同一 execution path 可保守确认

fail:
  - producer 位于后续 block
  - producer 位于同一 IF/WHILE/FOR block 内部，而 condition 读取该 variable
  - producer order 无法确定但可能晚于 decision point
```

Semantic materialization：

```text
1. Only resolved llm_condition_semantic_match can be materialized.
2. If evidence_text exact substring exists in condition_text, materialize that span with <REF>{canonical_ref}</REF> or append canonical ref phrase according to D1.
3. If composite rewrite maps canonical_ref -> new_ref, materialize new_ref directly.
4. If no safe materialization strategy applies, keep original condition_text but emit final diagnostic/evidence as configured by D1.
5. Renderer must not perform materialization.
```

Composite rewrite：

```text
1. For explicit refs, replace by token offsets from back to front.
2. For LLM semantic refs, materialize to final canonical ref after composite rewrite.
3. Never use global string replace.
4. Each ConditionTextRewrite.source_reference_ids must point to real reference_id.
```

Normalized plan update：

```text
Stage 9.5 is the only commit point for renderable condition_text rewrite.
推荐方案：更新 normalized WorkerFlowPlanIR / WorkerBlockPlanIR condition_text，再让 Stage 10/11 自然消费。
```

### 10.5 测试计划

新增测试必须覆盖：

1. worker input condition ref visibility pass + availability pass。
2. global input condition ref visibility pass + availability pass。
3. 不可见 variable 产生 `condition_variable_not_visible_in_scope`。
4. unresolved / ambiguous / invalid_qualified_ref / rejected 被转换为 final condition-specific diagnostics。
5. producer 位于后续 block 产生 `condition_variable_not_available_before_decision`。
6. IF block 内部 step produce 的 variable 被同一 IF condition 读取，availability fail。
7. explicit composite rewrite 将 `<REF>a</REF>` 改为 `<REF>a_b.a</REF>`。
8. LLM semantic ref materialization 将 `when enough evidence has been collected` materialize 为带 `<REF>evidence</REF>` 或 D1 批准策略。
9. LLM semantic ref + composite rewrite 直接 materialize 为 `<REF>a_b.a</REF>`。
10. rewrite/materialization 不误替换普通文本中的同名词。
11. normalized `BlockIR.condition_text` / flow condition text 被更新。
12. condition refs 不进入 StepVariableRelationPlan。
13. final diagnostics severity / blocks flags 由 Stage 9.5 或 consolidator 决定。

### 10.6 验收标准

Phase C6 通过条件：

1. Stage 9.5 validator/materializer/rewrite tests 全部通过。
2. normalized condition_text 会被 Stage 10/11 使用。
3. Stage 6.5 diagnostics 不直接作为 final completion gate。
4. ProducerIndex 和 StepVariableRelationPlan 无 condition refs。
5. No LLM calls in Stage 9.5。
6. 无新增 skip / xfail。

### 10.7 PM 审核清单

审核时必须检查：

1. final authority 是否确实在 Stage 9.5。
2. semantic materialization 是否不在 Stage 6.5 / renderer。
3. rewrite 是否同时保留 evidence 与更新 renderable condition_text。
4. rewrite 是否按 reference_id / offset 精确替换。
5. diagnostics 是否 condition-specific，而不是 producer missing。

---

## 11. Phase C7：Stage 10 / Stage 11 渲染闭环

该阶段保证 final SPL 使用 rewrite-approved condition_text。原则是尽量不改 renderer 语义；如果 Stage 9.5 已更新 normalized plans，Stage 10/11 应自然消费。

### 11.1 目标

验证并必要时修正 Stage 10 / Stage 11：

```text
1. Stage 10 assembly 使用 Stage 9.5 返回的 WorkerFlowPlanIR / WorkerBlockPlanIR。
2. WorkerIR 中 flow/block condition_text 已是 rewrite-approved text。
3. Stage 11 renderer 直接渲染 condition_text。
4. Renderer 不解析 / 不 rewrite / 不 validate refs。
```

### 11.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage10_worker_assembler/
src/nl2spl/pipeline/stages/stage11_spl_renderer/block_renderer.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py
```

Renderer 修改仅允许用于：

```text
1. 接收已经 materialized 的 rewritten condition_text。
2. 修复现有 fallback condition_text 默认值。
3. 增加 static guard，禁止 renderer 自行解析 refs。
```

允许新增：

```text
tests/unit/rendering/test_condition_text_rewrite_renderer.py
tests/integration/pipeline/test_condition_text_rewrite_rendering.py
```

### 11.3 禁止改动

Phase C7 禁止修改：

```text
src/nl2spl/compiler/reference_parser.py
  Renderer 不得 import parse_description_references。

src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/
  Renderer 闭环阶段不得回改 Stage 6.5 extraction semantics。

src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/step_variable_relation_ir.py
prompts/
```

### 11.4 设计要求

Renderer hard gate：

```text
Stage 11 must not import:
  - nl2spl.compiler.reference_parser
  - ConditionVariableReferencePlan
  - ConditionVariableVisibilityValidator
  - ConditionSemanticRefMaterializer
  - CompositeOutputPlanApplier for condition refs
```

不得新增：

```text
renderer-level LLM call
renderer-level symbol lookup
renderer-level condition rewrite fallback
```

### 11.5 测试计划

新增测试必须覆盖：

1. final SPL 中 explicit condition 使用 `<REF>a_b.a</REF>`。
2. final SPL 中不再出现旧 explicit `<REF>a</REF>`。
3. final SPL 中 LLM semantic condition materialized 为 `<REF>...</REF>`。
4. ALTERNATIVE_FLOW condition 使用 rewritten/materialized text。
5. EXCEPTION_FLOW condition 使用 rewritten/materialized text。
6. renderer 没有 import reference parser 或 ConditionVariableReferencePlan。
7. renderer 不因 unresolved condition ref 阻断 rendering。
8. final compile diagnostics 仍可标记 blocks_completion=true。

### 11.6 验收标准

Phase C7 通过条件：

1. rendering tests 全部通过。
2. Stage 11 不承担 ref extraction / rewrite / validation。
3. final SPL 使用 rewrite-approved condition_text。
4. unresolved/rejected condition ref 不导致 renderer error。
5. 无新增 skip / xfail。

### 11.7 PM 审核清单

审核时必须检查：

1. renderer 是否没有新增 parser / LLM / symbol import。
2. Stage 10 是否使用 normalized plans。
3. final SPL 是否有 semantic materialized condition refs。
4. final SPL 是否有 composite rewritten condition refs。
5. 是否没有通过字符串全局替换生成 condition text。

---

## 12. Phase C8：Diagnostics、reports、snapshot 与 final E2E

该阶段将 final condition diagnostics 接入 compile/report/snapshot，并完成全路径 E2E。不得引入 repair affordance。

### 12.1 目标

实现 condition-specific diagnostic inventory，并证明完整闭环：

```text
source/canonical input
  -> Stage 4/5 LLM condition placement
  -> Stage 6 symbol/type discovery
  -> Stage 6.5 LLM semantic extraction + deterministic admission
  -> Stage 9.5 visibility/availability/materialization/rewrite validation
  -> Stage 10 materialization
  -> Stage 11 final SPL rendering
  -> final diagnostics/report/snapshot
```

### 12.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/diagnostic_registry.py
src/nl2spl/compiler/diagnostic_consolidator.py
src/nl2spl/compiler/report_renderer.py
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_compile.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_plan.py
src/nl2spl/main.py

tests/fixtures/stage_expected_outputs.py
tests/fixtures/sample_outputs.py
examples/output/demo/*.json
examples/output/demo/final_spl.txt
examples/output/demo/feedback_report.md
```

允许新增：

```text
tests/unit/test_condition_variable_diagnostic_consolidator.py
tests/unit/test_condition_variable_feedback_report.py
tests/unit/compiler/artifacts/snapshot/test_condition_variable_snapshot.py
tests/integration/pipeline/test_condition_variable_reference_e2e.py
tests/integration/test_condition_variable_reference_demo_output.py
tests/unit/rendering/test_condition_variable_static_guardrails.py
```

### 12.3 禁止改动

Phase C8 禁止修改：

```text
src/nl2spl/compiler/spl_editing/core/catalog.py
src/nl2spl/compiler/spl_editing/handlers/
src/nl2spl/compiler/spl_editing/materialization/
src/nl2spl/compiler/irs/registry.py
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/step_variable_relation_ir.py
```

除非另有设计确认。MVP 不新增 repair affordance 或 IRS construct。

### 12.4 设计要求

Diagnostic inventory：

```text
condition_variable_ref_unresolved
condition_variable_ref_ambiguous
condition_variable_invalid_qualified_ref
condition_variable_not_visible_in_scope
condition_variable_not_available_before_decision
condition_variable_ref_removed_by_composite_without_rewrite
condition_variable_llm_candidate_rejected
```

Diagnostic flags：

```text
severity: warning
blocks_rendering: false
blocks_completion: true
```

Report visibility：

```text
compile_report:
  - 必须包含 final condition diagnostics。

feedback_report:
  - 可展示为用户需要补充/修正的 condition variable issue。
  - 不展示为 producer missing。
  - 不自动提供 Fix with AI。

snapshot:
  - 必须保留 ConditionVariableReferencePlan payload。
  - 必须保留 final condition diagnostics。
```

Static audit 必须覆盖：

```text
1. Stage 11 不 import reference_parser / ConditionVariableReferencePlan。
2. ProducerIndex 不 import ConditionVariableReferencePlan。
3. StepVariableRelationPlan 不包含 condition owner kind。
4. spl editing catalog 不包含 condition_variable_* repair affordance。
5. Stage 4/5/7 prompts 未发生 condition-ref-specific 修改。
6. CONDITION_VARIABLE_REFERENCE_PLAN key 只通过 intermediate_keys 常量引用。
7. rendered SPL text 没有被用作 condition ref source。
8. LLM selected_symbol outside candidate_symbols cannot be resolved。
```

### 12.5 E2E 测试计划

最终必须覆盖：

1. **Explicit IF input ref pass**
   - condition_text = `<REF>required_information</REF> is available`。
   - Stage 6.5 生成 `explicit_ref_token` resolved block_condition。
   - Stage 9.5 visibility + availability pass。
   - final SPL 保持合法 ref。

2. **Implicit LLM semantic ref pass**
   - condition_text = `when enough evidence has been collected`。
   - candidate_symbols 包含 `evidence`。
   - mock LLM selected_symbol=`evidence`。
   - deterministic admission resolved。
   - Stage 9.5 materializes final condition_text。

3. **LLM selected_symbol outside candidates rejected**
   - mock LLM selected_symbol=`invented_status`。
   - admission rejected。
   - final diagnostic = `condition_variable_llm_candidate_rejected`。

4. **LLM unresolved condition symbol**
   - condition_text = `if source access is insufficient`。
   - no matching candidate_symbols。
   - unresolved candidate evidence recorded。
   - final diagnostic = `condition_variable_ref_unresolved`。
   - not missing_output_producer。

5. **Flow-level alternative condition retained**
   - AlternativeFlow.condition_text has implicit or explicit ref。
   - no block mirror。
   - Stage 6.5 generates `alternative_flow_condition`。

6. **Flow-level exception condition retained**
   - ExceptionFlow.condition_text has implicit or unresolved dependency。
   - no block mirror。
   - Stage 6.5 generates `exception_flow_condition`。

7. **Composite output rewrite reaches final SPL**
   - condition explicitly or semantically reads `a`。
   - Stage 9.5 composite lowering maps `a -> a_b.a`。
   - final SPL uses `<REF>a_b.a</REF>`。

8. **Invalid qualified ref**
   - `<REF>a_b.missing_field</REF>` top-level exists but field does not。
   - final diagnostic = `condition_variable_invalid_qualified_ref`。

9. **Not available before decision**
   - condition reads future-produced variable。
   - final diagnostic = `condition_variable_not_available_before_decision`。

10. **Self-block rejection**
    - IF condition reads variable produced inside same IF block。
    - Stage 9.5 availability fail。

11. **No relation pollution**
    - all E2Es assert `step_variable_relation_plan.json` has no condition owner。
    - ProducerIndex map does not change because of condition refs。

12. **Renderer remains passive**
    - Stage 11 no parser / LLM / ConditionVariableReferencePlan import。
    - Renderer only renders materialized condition_text。

### 12.6 验收标准

Phase C8 通过条件：

1. 所有新增 unit / integration / E2E tests 通过。
2. C0 current-gap tests 已删除或改写为新 contract tests。
3. `git diff --check` 通过。
4. Ruff / type checks 按项目现有命令通过。
5. demo output 更新后，final SPL、feedback_report、condition_variable_reference_plan checkpoint 一致。
6. 无新增 skip / xfail。
7. 静态审计无 hard gate violation。

### 12.7 PM 审核清单

审核时必须检查：

1. E2E 是否覆盖 explicit 与 implicit condition refs。
2. LLM semantic extraction 是否受 candidate_symbols 约束。
3. rejected LLM candidate 是否没有被 admitted。
4. semantic materialization 是否真的进入 final SPL。
5. composite rewrite 是否真的进入 final SPL。
6. diagnostics 是否进入 final report，而不是只留在 intermediate。
7. condition refs 是否没有进入 StepVariableRelationPlan。
8. ProducerIndex 是否没有 condition-specific import/输入。
9. Renderer 是否没有 parser/LLM/rewrite/validation 逻辑。
10. spl editing 是否没有新增 repair affordance。

---

## 13. Decision Gate D1：Semantic ref materialization strategy

### 13.1 目标

确认 LLM semantic ref 如何 materialize 成最终 renderable condition_text。

### 13.2 可选方案

允许提交但必须评审确认的方案包括：

```text
方案 A：Exact evidence_text replacement
  仅当 evidence_text 是 condition_text 的精确 substring 时，将该 span materialize 为 <REF>{canonical_ref}</REF> 相关文本。
  推荐默认方案。

方案 B：Append-style canonical clause
  原 condition_text 不可安全替换时，在 condition 末尾追加 canonical ref phrase。
  需要更强语法和可读性测试。

方案 C：No materialization for implicit refs
  保留原 condition_text，只在 diagnostics/snapshot 中表达 semantic dependency。
  最保守，但 final SPL 不体现 refs，弱于 SPL grammar intended representation。
```

推荐方案：**A 默认，B 必须 PM 批准，C 仅作为临时 fallback 且必须记录 diagnostic/evidence。**

### 13.3 必须明确的问题

方案确认文档必须回答：

1. evidence_text 找不到时如何处理？
2. materialized text 是否仍符合 SPL grammar？
3. composite rewrite 与 semantic materialization 的执行顺序是什么？
4. final SPL 如何和 `ConditionTextRewrite` 对齐测试？
5. child worker condition_text 是否同样覆盖？
6. 是否会改变用户可读性或 source provenance？

### 13.4 验收标准

该决策门禁通过条件：

1. 默认采用方案 A 时，不需要额外批准。
2. 若采用 B/C，必须更新设计文档和 implementation plan。
3. PM 明确批准后方可进入 C6/C7 对应实现。

---

## 14. Decision Gate D2：Non-MVP expansion gate

### 14.1 目标

防止 implementation 过程中把非 MVP 功能顺手塞入默认路径。

### 14.2 可选方案

以下扩展必须单独设计评审：

```text
方案 A：支持 ELSEIF branch condition。
  需要 BranchConditionIR / ConditionalBranchIR。

方案 B：让 LLM 新增 accepted variable declaration。
  需要 new fact admission / user confirmation / SymbolTable mutation 设计。

方案 C：给 condition ref issue 加 Fix with AI repair affordance。
  需要 spl editing issue taxonomy、closure、preview/apply 设计。

方案 D：将 StepVariableRelationPlan 泛化为 ElementVariableRelationPlan。
  需要 ProducerIndex、required output fulfillment、reporting 全链路重构。

方案 E：将 Stage 6.5 extraction 前移到 Stage 4/5 prompt。
  需要重新定义 Stage 4/5 authority，不在本计划内。
```

### 14.3 必须明确的问题

方案确认文档必须回答：

1. 新 artifact 是否仍是 analysis artifact，还是 SPL construct？
2. 是否改变 Stage 7 / ProducerIndex authority？
3. 是否改变 renderer contract？
4. 是否需要 Stage 4/5/7 prompt/schema 修改？
5. 是否引入 repair affordance？
6. 是否改变 final diagnostics severity / blocking policy？

### 14.4 验收标准

该决策门禁通过条件：

1. 没有 PM 批准时，C1-C8 不得实现上述扩展。
2. 静态审计能证明默认生产路径没有 non-MVP expansion。
3. 若批准扩展，必须新建独立设计文档与实施计划。

---

## 15. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐 `stage6_5_condition_variable_reference_resolution_design_zh.md` v2。
2. 是否仍残留 explicit-only MVP 假设。
3. 是否扩大了 MVP 范围。
4. Stage 6.5 是否确实调用 LLM 做 condition semantic extraction。
5. Stage 6.5 LLM 是否 condition-owner scoped。
6. Candidate symbol view 是否由 SymbolTable / ResourceRegistryIR 确定性构造。
7. LLM selected_symbol 是否必须来自 candidate_symbols。
8. LLM unresolved candidate 是否没有自动变成 accepted variable。
9. Deterministic admission 是否是 resolved authority。
10. Stage 6.5 是否仍位于 Stage 6 后、Stage 7 前。
11. Stage 4/5 是否仍只 owns condition placement。
12. Stage 6.5 是否没有接收 `WorkerStepPlanIR`、`ProducerIndex`、`StepVariableRelationPlan`。
13. Stage 6.5 是否没有修改 BlockIR / FlowStructureIR / StepIR。
14. Stage 6.5 diagnostics 是否没有直接成为 final compile diagnostics。
15. Stage 9.5 是否是 final visibility / availability / materialization / rewrite authority。
16. ConditionTextRewrite 是否保留 original 和 rewritten text。
17. `source_reference_ids` 是否能指向稳定 `reference_id`。
18. `reference_id` 是否稳定且可复验。
19. `CONDITION_VARIABLE_REFERENCE_PLAN` 是否只通过 `intermediate_keys.py` 引用。
20. condition refs 是否没有进入 `StepVariableRelationPlan`。
21. ProducerIndex 是否没有 condition-specific 输入或 import。
22. Renderer 是否没有 import `reference_parser`、LLM client 或 ConditionVariableReferencePlan。
23. Renderer 是否没有 condition rewrite / validation 逻辑。
24. unresolved / ambiguous / invalid / rejected 是否是 condition-specific diagnostic。
25. condition diagnostics 是否没有被投影成 missing output producer。
26. feedback_report 是否没有自动出现 Fix with AI。
27. spl editing catalog 是否没有新增 condition repair affordance。
28. ELSEIF 是否仍被明确排除。
29. rendered SPL text 是否没有被用作 condition ref source。
30. semantic materialization 是否影响 final rendered condition_text。
31. composite output rewrite 是否影响 final rendered condition_text。
32. demo/golden 更新是否包含 intermediate、final_spl、feedback_report 一致性。
33. 是否存在 skip / xfail / 弱断言。
34. 是否有新代码路径没有测试覆盖。
35. 是否有过期文档、checkpoint 名称或注释。
36. 是否存在 truthiness 处理 `None` 的代码，尤其是 required/status/diagnostic flags。
37. 是否存在字符串散落 key。
38. 是否有临时 shim 未标注 remove phase。

---

## 16. 阶段完成顺序

推荐顺序：

```text
Phase C0      Characterization 与范围锁定
Phase C1      IR、checkpoint key 与 serializer
Phase C2      Shared ReferenceToken parser
Phase C3      Stage 6.5 prompt/schema 与 candidate symbol view
Phase C4      Stage 6.5 extractor 与 deterministic admission
Phase C5      Orchestrator integration 与 intermediate checkpoint
Decision D1   Semantic ref materialization strategy
Phase C6      Stage 9.5 visibility / availability / materialization / composite rewrite
Phase C7      Stage 10 / Stage 11 渲染闭环
Phase C8      Diagnostics、reports、snapshot 与 final E2E
Decision D2   Non-MVP expansion gate
```

依赖关系：

```text
C0:
  可立即开工。

C1:
  必须在 C4 前完成。

C2:
  可与 C1 并行，但必须在 C4 前完成。

C3:
  必须在 C1 后完成，确保 schema 与 IR 字段一致。

C4:
  必须在 C1/C2/C3 后完成。
  不得接入 orchestrator。

C5:
  必须在 C4 后完成。
  C5 后 intermediate 才出现 condition_variable_reference_plan。

D1:
  必须在 C6 materialization 实现前确认。
  默认采用 exact evidence_text replacement。

C6:
  必须在 C5 和 D1 后完成。

C7:
  必须在 C6 后完成。

C8:
  必须在 C1-C7 全部完成后进行。
  C8 负责删除或改写 C0 temporary current-gap tests。

D2:
  默认不批准任何 non-MVP expansion。
  如需要 ELSEIF / accepted variable creation / repair affordance，必须新文档。
```

---

## 17. 推荐提交拆分

建议按以下 PR 拆分，避免单 PR 过重：

```text
PR-1: C0 + C1 + C2
  - characterization fixtures
  - IR / serializer / checkpoint key
  - shared explicit ReferenceToken parser

PR-2: C3
  - Stage 6.5 prompt/schema
  - candidate symbol view
  - response parser

PR-3: C4
  - Stage 6.5 extractor
  - deterministic admission
  - resolver-local diagnostics

PR-4: C5
  - orchestrator integration
  - intermediate checkpoint
  - no Stage 9.5 final behavior yet

PR-5: C6 + D1 default strategy
  - Stage 9.5 visibility / availability
  - semantic materialization
  - composite condition rewrite

PR-6: C7 + C8
  - render path closure
  - report / snapshot / feedback integration
  - E2E / golden output / static audit
```

每个 PR 必须可独立通过 tests，不允许“先合入再补测试”。

---

## 18. 最终冻结条件

整个实施完成后，必须同时满足：

```text
1. ConditionVariableReferencePlan 在 intermediate 中稳定出现。
2. explicit CONDITION <REF> 被解析为 condition read dependency。
3. implicit natural-language condition 可经 LLM + SymbolTable 解析为 condition read dependency。
4. LLM selected_symbol outside candidate_symbols 被 rejected。
5. LLM unresolved condition symbol 不创建 accepted variable。
6. condition refs 不进入 StepVariableRelationPlan。
7. condition refs 不进入 ProducerIndex。
8. unresolved / ambiguous / invalid / rejected / unavailable condition refs 有 final diagnostics。
9. final diagnostics flags 符合 warning / blocks_rendering=false / blocks_completion=true。
10. semantic ref materialization 同步更新 condition_text。
11. composite output rewrite 同步更新 condition_text。
12. final SPL 使用 rewrite-approved condition_text。
13. Renderer 不做 ref extraction / LLM / rewrite / validation。
14. Stage 6.5 不直接拥有 final diagnostic authority。
15. ELSEIF / accepted variable creation / repair affordance 均未进入 MVP 默认路径。
16. 所有新增 unit / integration / E2E tests 通过。
17. 无 skip / xfail。
18. 静态审计无 hard gate violation。
```
