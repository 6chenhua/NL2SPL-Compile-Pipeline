# Stage 6.5 Condition Variable Reference Resolution 设计 v2

## 1. 背景

当前 SPL grammar 中：

```text
CONDITION := DESCRIPTION_WITH_REFERENCES
DESCRIPTION_WITH_REFERENCES := STATIC_DESCRIPTION {DESCRIPTION_WITH_REFERENCES} | REFERENCE {DESCRIPTION_WITH_REFERENCES}
REFERENCE := "<REF>" ["*"] NAME "</REF>"
```

这意味着 `IF`、`WHILE`、`FOR`、`ALTERNATIVE_FLOW`、`EXCEPTION_FLOW` 的 condition 与 `COMMAND` 文本一样，都可以引用变量：

```text
[IF <REF>required_information</REF> is available]
```

但真实 pipeline 中，Stage 4 / Stage 5 由 LLM 产出 flow/block structure 和原始 `condition_text`。这些 `condition_text` 未必已经包含显式 `<REF>`：

```text
when enough evidence has been collected
if source access is insufficient
when required information is available
if the newsletter draft is ready
```

这些 condition 语义上仍然可能读取变量。因此 compiler 不能只依赖 explicit `<REF>` tokenizer，而必须像 Stage 7 判断 Step input/output relation 一样，引入 LLM-guided semantic extraction，并用 SymbolTable / ResourceRegistryIR / post-normalize validator 做确定性约束。

如果不建模 condition read dependency，会出现以下问题：

```text
1. condition 读取不存在的变量，但 pipeline 不报错。
2. condition 读取未来才产生的变量，但被误认为可执行。
3. composite output lowering 后，command refs 被改写为 a_b.a / a_b.b，但 condition refs 没有同步改写。
4. condition refs 被错误塞进 StepVariableRelationPlan，导致 ProducerIndex / Step 语义被污染。
5. 纯自然语言 condition 语义上依赖变量，但 explicit-only parser 完全漏检。
```

## 2. 当前阶段顺序约束

当前 worker-aware pipeline 的相关顺序是：

```text
Stage 4  Flow Assembly
  -> 调用 LLM
  -> 产出 WorkerFlowPlanIR / AlternativeFlow / ExceptionFlow / flow-level condition_text

Stage 5  Block Assembly
  -> 调用 LLM
  -> 产出 WorkerBlockPlanIR / BlockIR / block-level condition_text

Stage 6  Resource Extraction
  -> 消费 WorkerBlockPlanIR
  -> 产出 ResourceRegistryIR / SymbolTable

Stage 7  Step Extraction
  -> 调用 LLM
  -> 消费 WorkerBlockPlanIR + SymbolTable
  -> 产出 WorkerStepPlanIR / StepIR / StepVariableRelationPlan

Stage 9.5 Normalization
  -> composite output lowering
  -> relation / producer / visibility validation
```

重要事实：

```text
Stage 6 并不独立于 Stage 5。
当前 _run_stage6_worker_scoped(...) 明确接收 worker_block_plan。
```

因此不能简单把 Stage 6 整体挪到 Stage 5 前面。更合理的方案是新增一个独立 Stage 6.5：

```text
Stage 4  owns flow-level condition placement
Stage 5  owns block-level condition placement
Stage 6  owns symbol discovery and type discovery
Stage 6.5 owns LLM-guided + symbol-constrained condition reference extraction
Stage 7  owns executable step extraction and step variable relations
Stage 9.5 owns final visibility / availability / composite rewrite validation
```

## 3. 核心原则

### 3.1 CONDITION refs 是 control read dependency

Condition variable reference 的语义是：

```text
condition reads variable
```

它不是：

```text
step consumes variable
step produces variable
handoff binding
required output fulfillment
repair affordance
```

因此 condition refs 不能直接塞进 `StepVariableRelationPlan`，除非未来把该模型泛化并重命名为 `ElementVariableRelationPlan`。

### 3.2 Stage 6.5 是 LLM-guided extraction，不是 explicit-only parser

Stage 6.5 必须支持两类 evidence source：

```text
1. explicit ref token
   condition_text 中已有 <REF>x</REF> / <REF>a_b.x</REF>

2. LLM semantic condition match
   condition_text 没有显式 <REF>，但语义上读取某个已有 symbol
```

原因是 Stage 4/5 的 `condition_text` 本来就是 LLM 产物，不能假设它已经被渲染成 SPL-level `<REF>` form。只解析 explicit `<REF>` 会漏掉大部分自然语言 condition dependency。

Stage 6.5 的正确职责是：

```text
LLM:
  - 判断 condition_text 是否读取变量
  - 在候选 SymbolTable symbols 中选择最匹配变量
  - 对无法匹配的语义依赖输出 unresolved condition symbol candidate

Deterministic admission:
  - 校验 selected symbol 是否存在
  - 校验 qualified field 是否存在
  - 校验 candidate 是否来自允许的 owner / source span / symbol candidate view
  - 决定 reference status: resolved / unresolved / ambiguous / invalid_qualified_ref / rejected
```

### 3.3 Stage 6.5 不拥有最终可执行性裁决

Stage 6.5 可以判断：

```text
1. condition_text 中有哪些 explicit <REF> token。
2. LLM 判断 condition_text 是否语义读取某些变量。
3. LLM 选择的 symbol 是否能被当前 SymbolTable 接纳。
4. qualified field 是否能被 ResourceRegistryIR.types 接纳。
5. ref 属于哪个 block / flow / condition owner。
6. ref 当前 admission status 是 resolved / unresolved / ambiguous / invalid_qualified_ref / rejected。
```

Stage 6.5 不能判断：

```text
1. 变量是否已在 condition 执行前被生产。
2. 变量 producer 是否在同一 execution path 上。
3. composite output lowering 后的最终 qualified ref 是否已经稳定。
4. condition 是否应该阻断 rendering / completion。
5. condition issue 是否应该成为 editable repair affordance。
```

这些必须留给 Stage 9.5 / post-normalize validator / diagnostic consolidator。

### 3.4 Stage 4 / Stage 5 condition ownership 必须拆开

SPL 中有两类 condition owner：

```text
flow-level condition:
  ALTERNATIVE_FLOW.condition
  EXCEPTION_FLOW.condition

block-level condition:
  IF.condition
  ELSEIF.condition
  WHILE.condition
  FOR.condition
```

当前 IR 中：

```text
FlowStructureIR.AlternativeFlow.condition_text
FlowStructureIR.ExceptionFlow.condition_text
  属于 Stage 4 产物。

BlockIR.condition_text
  属于 Stage 5 产物。
```

因此 Stage 6.5 必须消费两类 owner，并在同一 condition 被 flow/block mirror 时做 deterministic dedup。不得把 `EXCEPTION_FLOW.condition` 强行绑定到某个 block condition。

### 3.5 ELSEIF MVP 策略

SPL grammar 支持：

```text
[IF CONDITION] ... [ELSEIF CONDITION] ... [ELSE] ... END_IF
```

但当前 `BlockIR` 只有一个 `condition_text` 字段，尚不能显式表达多个 branch-level conditions。

MVP 决策：

```text
Stage 6.5 只解析当前 IR 可表达的 condition owner：
  - flow-level AlternativeFlow / ExceptionFlow
  - BlockIR.condition_text

ELSEIF branch condition 不在本轮建模范围内。
```

如果后续要完整支持 ELSEIF，应先新增：

```text
BranchConditionIR / ConditionalBranchIR
```

然后再让 Stage 6.5 遍历每个 branch condition。不得在 Stage 6.5 里用 rendered SPL text 反推 ELSEIF。

### 3.6 ProducerIndex 不消费 condition refs

`ProducerIndex` 的 authority 仍然来自：

```text
StepVariableRelationPlan.producing_relations()
handoff output bindings
CompositeOutputPlan
explicit API response contract
```

Condition refs 只可作为 read visibility / availability validation 输入，不能注册 producer，也不能证明 required output produced。

## 4. Shared Reference Parser 与 LLM extraction 的关系

Stage 6.5 仍应新增共享底层工具：

```text
src/nl2spl/compiler/reference_parser.py
```

但该 parser 只处理 grammar-level explicit token，是 evidence source 之一，不是完整 condition ref extractor。

模型：

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

函数：

```python
def parse_description_references(text: str) -> tuple[ReferenceToken, ...]:
    ...
```

共享规则：

```text
1. 解析 <REF>x</REF>、<REF>*x</REF>、<REF>a_b.x</REF>。
2. 保留 raw_text 与 offsets，用于后续 condition_text rewrite。
3. 只解析 grammar token，不做 symbol lookup。
4. 不做 semantic matching。
5. 不调用 LLM。
```

Stage 6.5 的完整 extraction pipeline 是：

```text
ConditionOwner collection
  -> explicit ReferenceToken extraction
  -> LLM semantic condition reference extraction
  -> deterministic symbol/type admission
  -> ConditionVariableReferencePlan
```

注意：可以共享 tokenizer，但不能共享 relation model。`condition reads x` 仍不是 `step consumes x`。

## 5. Stage 6.5 LLM extraction contract

### 5.1 输入原则

Stage 6.5 LLM 不能自由读取全局上下文，也不能自由发明 symbol。每个 LLM request 必须是 condition-owner scoped，并带有 candidate symbol view。

LLM 输入必须包含：

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
optional explicit_ref_tokens parsed from condition_text
```

LLM 输入不得包含：

```text
full unrelated source document
ProducerIndex
StepVariableRelationPlan
WorkerStepPlanIR
rendered SPL text
repair catalog
```

### 5.2 Candidate symbol view

Candidate symbol view 必须由 Stage 6 / SymbolTable / ResourceRegistryIR 确定性构造。示例：

```json
{
  "owner_ref": "block:worker_main:b_if_1:condition",
  "condition_text": "when enough evidence has been collected",
  "candidate_symbols": [
    {
      "name": "evidence",
      "data_type": "text",
      "scope": "worker",
      "worker_id": "worker_main",
      "description": "Collected evidence for sourced claims",
      "source_span_ids": ["s12"]
    },
    {
      "name": "required_information",
      "data_type": "text",
      "scope": "worker",
      "worker_id": "worker_main",
      "description": "Information required before drafting",
      "source_span_ids": ["s03"]
    }
  ]
}
```

Candidate symbol view hard rules：

```text
1. resolved candidate 必须引用 candidate_symbols 中的 symbol_id/name。
2. structured field candidate 必须来自 ResourceRegistryIR.types。
3. 如果 LLM 认为 condition 依赖的变量不在候选表内，只能输出 unresolved_candidate。
4. LLM 不得输出新的 accepted variable declaration。
5. LLM 不得修改 SymbolTable。
```

### 5.3 LLM 输出 schema

LLM 必须返回 JSON only。推荐 schema：

```json
{
  "owner_ref": "block:worker_main:b_if_1:condition",
  "references": [
    {
      "relation": "condition_reads",
      "selected_symbol": "evidence",
      "qualified_ref": "evidence",
      "evidence_text": "enough evidence has been collected",
      "confidence": "medium",
      "reason": "The condition checks whether evidence has been collected."
    }
  ],
  "unresolved_candidates": []
}
```

Unresolved example：

```json
{
  "owner_ref": "block:worker_main:b_if_2:condition",
  "references": [],
  "unresolved_candidates": [
    {
      "proposed_symbol_text": "source access",
      "evidence_text": "source access is insufficient",
      "reason": "The condition depends on source access status, but no candidate symbol matches it."
    }
  ]
}
```

LLM output hard rules：

```text
1. selected_symbol 必须来自 candidate_symbols；否则 deterministic admission 必须 reject。
2. qualified_ref 的 top-level 必须等于 selected_symbol 或 selected_symbol 的 legal qualified field。
3. evidence_text 必须是 condition_text 或 owner source excerpt 的子串；否则 confidence 降级或 reject。
4. confidence 不能作为 final authority，只能作为 evidence metadata。
5. LLM 不得输出 severity / blocks_rendering / blocks_completion。
6. LLM 不得输出 repair action。
```

## 6. 新增 IR

### 6.1 ConditionOwnerKind

```python
ConditionOwnerKind = Literal[
    "block_condition",
    "alternative_flow_condition",
    "exception_flow_condition",
]
```

### 6.2 ConditionVariableReferenceStatus

```python
ConditionVariableReferenceStatus = Literal[
    "resolved",
    "unresolved",
    "ambiguous",
    "invalid_qualified_ref",
    "rejected",
]
```

### 6.3 ConditionReferenceEvidenceKind

```python
ConditionReferenceEvidenceKind = Literal[
    "explicit_ref_token",
    "llm_condition_semantic_match",
    "llm_unresolved_condition_symbol",
]
```

含义：

```text
explicit_ref_token:
  condition_text 中已有 <REF> token。

llm_condition_semantic_match:
  LLM 根据 condition_text + source excerpt + candidate symbols 选择已有 symbol。

llm_unresolved_condition_symbol:
  LLM 判断 condition 语义上依赖某变量，但候选 SymbolTable 中无合法匹配。
```

### 6.4 ConditionVariableReferenceIR

建议新增模块：

```text
src/nl2spl/ir/condition_variable_reference_ir.py
```

模型：

```python
@dataclass(frozen=True)
class ConditionVariableReferenceIR:
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
    evidence_text: str | None = None
    selected_symbol: str | None = None
    proposed_symbol_text: str | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    reason: str | None = None
```

字段规则：

```text
explicit_ref_token:
  ref_text must not be None
  canonical_ref may be resolved by deterministic admission
  selected_symbol may be set when top-level symbol exists

llm_condition_semantic_match:
  ref_text may be None
  selected_symbol must not be None before admission
  canonical_ref must be derived from selected_symbol / qualified_ref after admission

llm_unresolved_condition_symbol:
  proposed_symbol_text must not be None
  selected_symbol must be None
  canonical_ref must be None
  status must be unresolved or rejected
```

`reference_id` 必须稳定、可序列化、可复验。

建议格式：

```text
cond_ref_{owner_ref_hash}_{source_kind}_{index}
```

其中：

```text
owner_ref_hash = sha256(owner_ref)[:10]
source_kind = explicit | llm | unresolved
index = 同一 owner_ref 内按 deterministic order 排序后的 0-based index
```

排序规则：

```text
1. explicit_ref_token 按 ReferenceToken.start_offset 排序。
2. llm_condition_semantic_match 按 selected_symbol + evidence_text 排序。
3. llm_unresolved_condition_symbol 按 proposed_symbol_text + evidence_text 排序。
```

### 6.5 ConditionTextRewrite

Composite output lowering 后，不能只改 `canonical_ref`，还必须让最终渲染使用改写后的 condition text。

新增：

```python
@dataclass(frozen=True)
class ConditionTextRewrite:
    owner_ref: str
    original_condition_text: str
    rewritten_condition_text: str
    rewrite_reason: Literal[
        "composite_output_rewrite",
        "qualified_ref_normalization",
        "llm_semantic_ref_materialization",
    ]
    source_reference_ids: tuple[str, ...]
```

其中：

```text
composite_output_rewrite:
  <REF>a</REF> -> <REF>a_b.a</REF>

qualified_ref_normalization:
  explicit ref 已有 qualified form 或需要字段规范化。

llm_semantic_ref_materialization:
  LLM 识别出 condition reads evidence，但原 condition_text 没有 <REF>。
  Stage 9.5 可选择将 condition_text materialize 为包含 <REF>evidence</REF> 的 renderable text。
```

### 6.6 ConditionVariableReferencePlan

```python
@dataclass(frozen=True)
class ConditionVariableReferencePlan:
    references: tuple[ConditionVariableReferenceIR, ...] = ()
    text_rewrites: tuple[ConditionTextRewrite, ...] = ()
    diagnostics: tuple[CompileDiagnostic, ...] = ()
```

该 plan 是 read-only intermediate：

```text
不是 IRS construct
不是 repair target
不 materialize StepIR
不写 ProducerIndex
不改变 StepVariableRelationPlan
```

## 7. Stage 6.5 输入输出

### 7.1 输入

```text
resolved_spans
worker_flow_plan
worker_block_plan
worker_plan
symbol_table
resource_registry
llm_client
```

其中：

```text
worker_flow_plan 来自 Stage 4
worker_block_plan 来自 Stage 5
symbol_table / resource_registry 来自 Stage 6
llm_client 使用 pipeline 现有 stage client 机制
```

### 7.2 输出

```text
ConditionVariableReferencePlan
```

并写入 intermediate：

```python
CONDITION_VARIABLE_REFERENCE_PLAN = "condition_variable_reference_plan"
```

建议新增 constant：

```text
src/nl2spl/pipeline/intermediate_keys.py
```

## 8. Stage 6.5 解析逻辑

### 8.1 owner 收集

Stage 6.5 遍历以下 condition owner：

```text
Stage 4 flow-level:
  WorkerFlowPlanIR.worker_flows[*].alternative_flows[*].condition_text
  WorkerFlowPlanIR.worker_flows[*].exception_flows[*].condition_text

Stage 5 block-level:
  WorkerBlockPlanIR.worker_blocks[*].main_flow_blocks[*].condition_text
  WorkerBlockPlanIR.worker_blocks[*].alternative_flow_blocks[*][*].condition_text
  WorkerBlockPlanIR.worker_blocks[*].exception_flow_blocks[*][*].condition_text
```

Dedup key：

```text
worker_id + owner_kind + normalized_condition_text + source_span_ids
```

如果同一个 condition 同时出现在 flow-level 和 block-level owner，保留更具体的 owner：

```text
block_condition > flow_condition
```

但 `EXCEPTION_FLOW.condition` / `ALTERNATIVE_FLOW.condition` 没有 block mirror 时必须保留 flow-level owner。

### 8.2 explicit ref token extraction

通过共享 parser 识别 grammar form：

```text
<REF>name</REF>
<REF>*name</REF>
<REF>a_b.x</REF>
```

explicit token 生成 `evidence_kind = explicit_ref_token` 的 reference candidate。

### 8.3 LLM semantic extraction

对每个 condition owner，Stage 6.5 构造 owner-scoped LLM request：

```text
condition_text
source excerpts
candidate_symbols
explicit_ref_tokens
```

LLM 返回：

```text
condition_reads selected candidate symbols
unresolved condition symbol candidates
```

LLM 不能直接产生 resolved symbol。所有 LLM references 必须经过 deterministic admission。

### 8.4 deterministic admission

Admission 规则：

```text
1. explicit_ref_token:
   - top-level name 必须能在当前 worker scope 或 global scope 中找到。
   - qualified field 必须能在 structured DATA_TYPE 中找到。
   - 否则 status = unresolved / ambiguous / invalid_qualified_ref。

2. llm_condition_semantic_match:
   - selected_symbol 必须在 candidate_symbols 中。
   - qualified_ref top-level 必须等于 selected_symbol。
   - evidence_text 必须 source-backed。
   - 通过后 status = resolved。
   - 不通过则 status = rejected 或 unresolved。

3. llm_unresolved_condition_symbol:
   - 不创建新 SymbolTable variable。
   - 不作为 resolved reference。
   - status = unresolved。
```

Ambiguity 规则：

```text
1. LLM 对同一 evidence_text 选择多个 symbols 且无唯一高置信候选 -> ambiguous。
2. selected_symbol 在多个 visible scope 中同名，且 current worker > global 仍无法唯一决策 -> ambiguous。
3. explicit ref 与 LLM ref 指向不同 symbols，且无法按 explicit > llm resolve -> ambiguous diagnostic。
```

优先级：

```text
1. explicit_ref_token 是最强 evidence。
2. llm_condition_semantic_match 可补充 implicit condition reads。
3. llm_unresolved_condition_symbol 只产生 condition-specific unresolved diagnostic evidence。
```

### 8.5 unresolved 不是 producer missing

如果 condition ref 无法解析：

```text
status = unresolved
diagnostic = condition_variable_ref_unresolved
```

但不得生成：

```text
missing_output_producer
required_output_missing_source_backed_producer
editable repair issue
```

除非后续 IRS/diagnostic projector 明确引入 condition-specific repair affordance。

## 9. Stage 9.5 可见性与可用性校验

Stage 9.5 新增 validator：

```text
ConditionVariableVisibilityValidator
```

输入：

```text
ConditionVariableReferencePlan
WorkerBlockPlanIR
WorkerStepPlanIR
SymbolTable
StepVariableRelationPlan
CompositeOutputPlan
ProducerIndex
```

校验：

```text
1. scope visibility:
   resolved ref 的 top-level variable 在 condition 所属 worker/global scope 中可见。

2. execution availability:
   变量如果不是 worker/global input，则必须在该 decision point 之前已可用。

3. self-block rejection:
   变量不得由该 IF / WHILE / FOR block 内部 step 生产后再被同一 block condition 读取。

4. composite rewrite:
   condition refs 必须应用 composite output rewrite，并生成 text_rewrites。

5. llm semantic ref materialization:
   对 resolved llm_condition_semantic_match，如果 final renderer 需要 SPL grammar-level ref，
   Stage 9.5 可生成 ConditionTextRewrite，将自然语言 condition_text materialize 为带 <REF> 的 condition_text。

6. unresolved / ambiguous / invalid_qualified_ref / rejected:
   产生 condition-specific diagnostic。
```

MVP 中，执行顺序判断可以保守：

```text
- worker input / global input: visibility pass + availability pass
- visible 但 producer 位于后续 block: visibility pass + availability fail
- producer step 位于同一 IF/WHILE/FOR block 内部: availability fail
- 无法确定 order: diagnostic，blocks_completion=true，blocks_rendering=false
```

## 10. Composite output rewrite 与 semantic ref materialization

Composite output lowering 可能把：

```text
a, b
```

聚合为：

```text
a_b
```

并要求引用改写为：

```text
<REF>a_b.a</REF>
<REF>a_b.b</REF>
```

因此 Stage 9.5 必须对 `ConditionVariableReferencePlan` 执行同样的 reference rewrite，并产出 `ConditionTextRewrite`。

规则：

```text
1. explicit ref rewrite:
   如果 condition ref 原来是 a，且 CompositeOutputPlan.reference_rewrites 有 a -> a_b.a：
   - condition canonical_ref 改为 a_b.a
   - owner_ref 对应的 rewritten_condition_text 中 <REF>a</REF> 改为 <REF>a_b.a</REF>

2. llm semantic ref materialization:
   如果 LLM resolved condition reads a，但原 condition_text 没有 <REF>a</REF>：
   - Stage 9.5 可以生成 rewritten_condition_text，将 evidence_text 附近 materialize 为 <REF>a</REF>
   - 如果同时存在 composite rewrite a -> a_b.a，则直接 materialize 为 <REF>a_b.a</REF>

3. already-qualified ref:
   如果 condition ref 原来是 a_b.a，且 type schema 合法，保持。

4. removed without rewrite:
   如果 condition ref 原来是 a，但 a 已从 DEFINE_VARIABLES / SymbolTable 中删除，且没有 rewrite plan，
   diagnostic = condition_variable_ref_removed_by_composite_without_rewrite。
```

Materialization guard：

```text
Stage 9.5 可以 materialize <REF>，但必须满足：
1. reference status = resolved。
2. evidence_kind = llm_condition_semantic_match。
3. evidence_text 可定位到 condition_text substring，或使用 append-style canonical clause 策略。
4. 所有 rewrite 都保留 original_condition_text / rewritten_condition_text / source_reference_ids。
5. Renderer 不参与 materialization。
```

推荐渲染输入规则：

```text
condition_text =
  condition_text_rewrite_by_owner.get(owner_ref, original_condition_text)
```

Renderer 只渲染 rewrite-approved condition text，不做 extraction / rewrite / validation。

## 11. Diagnostic Inventory

### 11.1 condition_variable_ref_unresolved

```text
severity: warning
blocks_rendering: false
blocks_completion: true
target: owner_ref
message: CONDITION references or semantically depends on an unknown variable.
```

### 11.2 condition_variable_ref_ambiguous

```text
severity: warning
blocks_rendering: false
blocks_completion: true
target: owner_ref
message: CONDITION variable reference is ambiguous in the current scope.
```

### 11.3 condition_variable_invalid_qualified_ref

```text
severity: warning
blocks_rendering: false
blocks_completion: true
target: owner_ref
message: CONDITION references a structured field that does not exist.
```

语法非法的 `<REF>a.</REF>` 属于 grammar/parser validation，不属于本 diagnostic。

### 11.4 condition_variable_not_visible_in_scope

```text
severity: warning
blocks_rendering: false
blocks_completion: true
target: owner_ref
message: CONDITION reads a variable that is not visible in this control scope.
```

### 11.5 condition_variable_not_available_before_decision

```text
severity: warning
blocks_rendering: false
blocks_completion: true
target: owner_ref
message: CONDITION reads a variable that is not available before this decision point.
```

### 11.6 condition_variable_ref_removed_by_composite_without_rewrite

```text
severity: warning
blocks_rendering: false
blocks_completion: true
target: owner_ref
message: CONDITION references a variable removed by composite output lowering without a valid rewrite.
```

### 11.7 condition_variable_llm_candidate_rejected

```text
severity: warning
blocks_rendering: false
blocks_completion: true
target: owner_ref
message: CONDITION semantic variable candidate was rejected by deterministic admission.
```

### 11.8 Diagnostic authority split

Stage 6.5 diagnostic authority:

```text
resolver-local status / diagnostic
  - unresolved
  - ambiguous
  - invalid_qualified_ref
  - rejected llm candidate
  - duplicate owner mirror dedup notes
```

Stage 6.5 diagnostics are analysis artifacts. They are stored inside `ConditionVariableReferencePlan.diagnostics`, but they are not final compile diagnostics by themselves.

Stage 9.5 / diagnostic consolidator authority:

```text
final condition variable diagnostics
  - scope visibility
  - execution availability
  - composite rewrite consistency
  - semantic ref materialization validity
  - final severity / blocks_rendering / blocks_completion
```

Final `compile_diagnostics` must be emitted by Stage 9.5 or a post-normalize diagnostic consolidator. Stage 6.5 may supply evidence and resolver status, but it must not be the final completion gate authority.

## 12. Authority Boundary

### Stage 4

Owns:

```text
LLM-driven flow-level condition placement
ALTERNATIVE_FLOW.condition_text
EXCEPTION_FLOW.condition_text
```

Does not own:

```text
condition variable reference extraction
symbol resolution
producer validation
variable visibility
qualified field schema validation
```

### Stage 5

Owns:

```text
LLM-driven block-level condition placement
IF / WHILE / FOR condition_text
condition source spans for BlockIR
```

Does not own:

```text
condition variable reference extraction
symbol resolution
producer validation
variable visibility
qualified field schema validation
```

### Stage 6

Owns:

```text
ResourceRegistryIR
SymbolTable
structured type definitions
```

Does not own:

```text
control block semantics
step producer semantics
condition execution ordering
```

### Stage 6.5

Owns:

```text
condition owner collection
explicit ref token extraction
LLM-guided condition semantic reference extraction
candidate symbol view construction
symbol/type admission for condition references
resolver-local condition reference diagnostics
```

Does not own:

```text
StepIR
StepVariableRelationPlan
ProducerIndex
repair affordance
rendering
condition block materialization
final compile diagnostic authority
```

### Stage 7

Owns:

```text
StepIR
step variable relations
executable action materialization
```

Does not own:

```text
block / flow condition refs
```

### Stage 9.5

Owns:

```text
condition read visibility validation
condition read availability validation
composite ref rewrite validation
semantic ref materialization
post-normalize consistency
final condition diagnostics
```

Does not own:

```text
guessing missing refs without Stage 6.5 evidence
inventing variables
renderer-level repair
```

### Renderer

Owns:

```text
rendering rewrite-approved condition_text
```

Does not own:

```text
LLM condition extraction
symbol lookup
condition ref rewrite
condition validation
```

## 13. Examples

### 13.1 explicit ref token

Input SPL fragment:

```text
[IF <REF>required_information</REF> is available]
  COMMAND-3 [COMMAND produce draft RESULT draft:text SET]
END_IF
```

Stage 5 output:

```text
BlockIR(
  block_id="b_if_1",
  block_type="IF",
  condition_text="<REF>required_information</REF> is available",
  spans=["s17"]
)
```

Stage 6 output:

```text
SymbolTable:
  required_information: text, source=input
```

Stage 6.5 output:

```text
ConditionVariableReferenceIR(
  reference_id="cond_ref_3fa4c2a901_explicit_0",
  owner_kind="block_condition",
  owner_ref="block:worker_main:b_if_1:condition",
  ref_text="required_information",
  canonical_ref="required_information",
  top_level_name="required_information",
  status="resolved",
  worker_id="worker_main",
  block_ref="b_if_1",
  evidence_kind="explicit_ref_token",
  confidence="high"
)
```

Stage 9.5 validation:

```text
required_information is worker input -> visible before decision -> pass
```

### 13.2 LLM semantic condition match

Stage 5 output:

```text
BlockIR(
  block_id="b_if_2",
  block_type="IF",
  condition_text="when enough evidence has been collected",
  spans=["s21"]
)
```

Stage 6 candidate symbols:

```text
evidence: text, source=step_or_input, description="Collected evidence for sourced claims"
required_information: text, source=input
```

Stage 6.5 LLM output:

```json
{
  "owner_ref": "block:worker_main:b_if_2:condition",
  "references": [
    {
      "relation": "condition_reads",
      "selected_symbol": "evidence",
      "qualified_ref": "evidence",
      "evidence_text": "enough evidence has been collected",
      "confidence": "medium"
    }
  ],
  "unresolved_candidates": []
}
```

Stage 6.5 admitted reference:

```text
ConditionVariableReferenceIR(
  reference_id="cond_ref_8df13aa991_llm_0",
  owner_kind="block_condition",
  owner_ref="block:worker_main:b_if_2:condition",
  condition_text="when enough evidence has been collected",
  ref_text=None,
  canonical_ref="evidence",
  top_level_name="evidence",
  qualified_path=("evidence",),
  status="resolved",
  evidence_kind="llm_condition_semantic_match",
  evidence_text="enough evidence has been collected",
  selected_symbol="evidence",
  confidence="medium"
)
```

Stage 9.5 validation then decides whether `evidence` is available before the decision point.

### 13.3 LLM unresolved condition symbol

Condition:

```text
if source access is insufficient
```

Candidate symbols do not include source access status.

Stage 6.5 LLM output:

```json
{
  "owner_ref": "exception_flow:worker_main:exc_1:condition",
  "references": [],
  "unresolved_candidates": [
    {
      "proposed_symbol_text": "source access status",
      "evidence_text": "source access is insufficient",
      "reason": "The condition checks source access, but no candidate symbol matches it."
    }
  ]
}
```

Stage 6.5 admitted diagnostic evidence:

```text
status = unresolved
evidence_kind = llm_unresolved_condition_symbol
canonical_ref = None
```

This must not become `missing_output_producer`.

## 14. Non-goals

本设计不做：

```text
1. 让 LLM 自由发明 accepted variables。
2. 让 LLM 直接修改 SymbolTable / ResourceRegistryIR。
3. 让 LLM 直接决定 final severity / blocks_rendering / blocks_completion。
4. 把 condition refs 塞进 StepVariableRelationPlan。
5. 让 ProducerIndex 消费 condition refs。
6. 让 Stage 5 依赖完整 SymbolTable。
7. 重新排序 Stage 5 / Stage 6。
8. 让 renderer 做 ref extraction / rewrite / validation。
9. 给 condition ref unresolved 自动创建 Fix with AI。
10. 在 MVP 中支持 ELSEIF branch condition。
11. 从 rendered SPL text 反推 condition refs。
```

## 15. Implementation Gate

进入实现前需要冻结：

```text
1. ConditionVariableReferenceIR schema。
2. ConditionReferenceEvidenceKind enum。
3. ConditionVariableReferencePlan checkpoint key。
4. explicit <REF> extraction grammar。
5. Stage 6.5 LLM input schema / output schema。
6. candidate symbol view construction policy。
7. deterministic admission policy。
8. flow-level / block-level condition owner collection and dedup policy。
9. ELSEIF MVP exclusion policy。
10. structured qualified ref validation rule。
11. Stage 9.5 scope visibility vs execution availability validation policy。
12. semantic ref materialization policy。
13. composite output rewrite rule for condition refs and condition_text。
14. diagnostic inventory severity / blocks_rendering / blocks_completion。
15. hard gate that condition refs do not enter StepVariableRelationPlan / ProducerIndex。
```

最小验收：

```text
1. CONDITION explicit <REF>x</REF> 被记录为 block_condition read relation。
2. 纯自然语言 condition “when enough evidence has been collected” 可经 LLM + SymbolTable 解析为 condition reads evidence。
3. LLM selected_symbol 不在 candidate_symbols 中时必须被 deterministic admission reject。
4. LLM unresolved condition symbol 产生 condition-specific unresolved diagnostic evidence。
5. CONDITION ref 不进入 StepVariableRelationPlan.producing_relations。
6. unresolved condition ref 不被投影为 missing_output_producer。
7. composite output lowering 后 condition ref a 被改写为 a_b.a。
8. LLM semantic ref 在 final rendered condition_text 中可 materialize 为 `<REF>...</REF>`。
9. condition 读取 IF block 内部才产生的变量会被 Stage 9.5 拒绝。
10. `EXCEPTION_FLOW.condition` 没有 block mirror 时仍被 Stage 6.5 解析。
11. ELSEIF condition 明确不在 MVP 范围，不能用 rendered text 反推。
12. Renderer 不参与 condition ref extraction / rewrite / validation。
```

## 16. 推荐实施阶段

```text
C0: Characterization
  锁定当前 condition refs 未建模、implicit condition dependency 漏检的问题。

C1: IR + checkpoint key
  新增 ConditionVariableReferenceIR / EvidenceKind / Plan / serializers。

C2: Shared Reference Parser
  explicit <REF> token parser，作为 evidence source 之一。

C3: Stage 6.5 prompt/schema
  新增 condition-owner scoped LLM extraction prompt 与 strict output schema。

C4: Stage 6.5 extractor + deterministic admission
  owner collection + candidate symbol view + LLM extraction + SymbolTable/ResourceRegistryIR admission。

C5: Orchestrator integration
  Stage 6 后、Stage 7 前运行 Stage 6.5。

C6: Stage 9.5 visibility / availability / rewrite validator
  scope / producer-order / composite rewrite / semantic materialization validation。

C7: Diagnostics projection
  condition-specific diagnostics 进入 compile/feedback/report，但不进入 producer repair。

C8: E2E
  explicit refs + LLM semantic refs + composite output + qualified refs + unresolved refs。
```
