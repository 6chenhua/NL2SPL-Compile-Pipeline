# Resource Contract Annotation 重构设计

版本: 1.2  
日期: 2026-06-08  
状态: Proposed architecture design  
范围: input adapter、RouteAnnotation、resource contract、Stage 3.5、Stage 6、Stage 9.5、Stage 10、IRS、feedback report

## 0. 修订结论

本版本修正 v1.0 的一个关键问题：`RouteAnnotation` 不应被提升为 construct-level resource demand 的直接权威。

新的主链路是：

```text
StructuralNLAdapter
  -> SemanticPacket / StructuralPrior
  -> Stage 2 RouteAnnotation
  -> ResourceContractPlanner
  -> ResourceContractPlan
  -> Stage 3.5 / Stage 6 / IRS
```

其中：

1. `RouteAnnotation` 是 span-level evidence。
2. `ResourceContractPlan` 是 checkpointable、construct-level 的 source demand artifact。
3. Stage 3.5、Stage 6、IRS 不应各自直接解释 raw `RouteAnnotation`。
4. `hard_facts.inputs/outputs` 的删除必须后移，直到 Stage 3.5、Stage 6、provenance、IRS 都能消费 `ResourceContractPlan`。
5. Stage 6 的改造不只是改 prompt，还必须扩展 schema、parser、resource provenance、direction、resolver 和检查闭环。

v1.2 在 v1.1 基础上增加三条 implementation gate。任何实现如果没有满足这些 gate，都只能视为半成品：

```text
Gate 1: ResourceContractPlan 必须有 deterministic section/list-item evidence 入口。
Gate 2: ResourceContractBindingIR 必须是 scope-aware 的。
Gate 3: FileSpec 输出必须和 resolver / ProducerIndex / IRS 同步闭环。
```

特别说明：当前工作区的 Stage 11 已经在 worker `[INPUTS]` / `[OUTPUTS]` 中渲染 `<REF>{name}</REF>`，因此 `<REF>` 不属于本次 resource contract 重构的阻塞风险。

## 1. 背景

当前 `StructuralNLAdapter` 中仍存在一段 legacy compatibility path:

```python
if title in ("inputs for each run", "inputs_for_each_run"):
    inputs = self._extract_variables(section, source="input")
    ...
    hard_facts.inputs.extend(...)
elif title in ("required outputs", "required_outputs"):
    outputs = self._extract_variables(section, source="output")
    ...
    hard_facts.outputs.extend(...)
```

这段逻辑会在 adapter 层直接执行变量提取、变量命名和类型推断。它造成了两个架构问题：

1. adapter 过早做语义判断，把 `Required Outputs` 中的条目强行建模成 `VariableFact`。
2. `_infer_data_type()` 使用硬编码规则，导致 `Finished draft (Word or Google Doc...)` 被降级成 `text`，而不是可进入 SPL `[DEFINE_FILES:]` 的文件产物。

这与当前以 `RouteAnnotation` 作为语义路由结果的方向冲突。adapter 应只负责结构解析和 provenance，不应负责资源语义建模。

## 2. 当前实际链路

当前 demo 中 `Finished draft (Word or Google Doc...)` 的实际流向如下：

```text
usage.py Required Outputs
  -> StructuralNLAdapter legacy hard_facts.outputs
  -> VariableFact(name=finished_draft..., data_type=text)
  -> Stage 2 RouteAnnotation(output_contract)
  -> Stage 3.5 ContractFieldIR(data_type=text, source=output)
  -> Stage 6 _merge_contract_variables()
  -> VariableSpec(source=output, data_type=text)
  -> Stage 11 [DEFINE_VARIABLES:]
```

而 `[DEFINE_FILES:]` 的渲染只读取 `ResourceRegistryIR.files`：

```text
ResourceRegistryIR.files
  -> Stage 11 [DEFINE_FILES:]
```

因此 renderer 没有漏渲染。根因是上游从未产生 `FileSpec` 或带有 `resource_kind=file` 的 output contract。

## 3. 设计原则

1. adapter 不做语义提取。adapter 只输出 raw sections、semantic packets、structural provenance 和弱 structural priors。
2. `RouteAnnotation` 只表达 span-level semantic evidence，不直接作为 construct-level demand 权威。
3. `ResourceContractPlan` 聚合 resolved spans、deterministic structural evidence 和 validated `RouteAnnotation`，形成稳定的 source-demanded resource contracts。
4. resource contract materialization 由 LLM-backed resource extraction 阶段生成，并由 deterministic validator/IRS 检查。
5. 文件产物、变量、API、类型必须在 IR 中显式区分，不能靠 renderer 从名称或描述猜测。
6. renderer 只渲染 IR，不做资源类型推断。
7. IRS 只检查已有 construct/resource 的满足度，不从 raw NL 重新抽取资源。
8. legacy `hard_facts` 必须有明确废弃路径，但删除顺序必须保守：先建新路径，再关闭旧路径。

## 4. 目标架构

### 4.1 Adapter 层

adapter 负责：

1. 解析 section。
2. 生成 list item / sentence packet。
3. 保留 `source_section_id`、`source_packet_id`、offset、原文。
4. 对明确标题生成 structural prior，例如：
   - `Inputs for each run` -> `suggested_semantic_role=input_contract`
   - `Required Outputs` -> `suggested_semantic_role=output_contract`

adapter 不负责：

1. 变量名生成。
2. 类型推断。
3. 判断 output 是 variable 还是 file。
4. 生成 authoritative `VariableFact`。
5. 生成 `ContractFieldIR`。

### 4.2 RouteAnnotation 层

Stage 2 继续把 structural prior 和 LLM refinement 合并成 `RouteAnnotation`。

对 resource contract，annotation 只表达 span evidence：

```python
RouteAnnotation(
    span_id="s11",
    field="<legacy-compatible-field>",
    semantic_role="output_contract",
    route_family="resource_contract",
    construct_target="RESOURCE_CONTRACT",
    slot_target="output",
    executable=False,
    source_section_id="sec_required_outputs",
    source_packet_id="p_list_item_finished_draft..."
)
```

Stage 2 只判断“这个 span 提供 output contract evidence”，不判断该 evidence 是 variable/file/API，也不直接形成 construct-level demand。

注意：不得依赖 `RouteAnnotation.field` 承载新的 resource schema。`field` 是 legacy compatibility 字段；resource contract 语义应由 `semantic_role`、`route_family`、`construct_target`、`slot_target` 和后续 `ResourceContractPlan` 承载。

### 4.3 ResourceContractPlan

在 Stage 2 之后新增或明确一个 compiler artifact：`ResourceContractPlan`。

它的职责是把 span-level route evidence 聚合为稳定的 source-demanded resource contract instances。
`ResourceContractPlan` 的入口不得只依赖最终 `RouteAnnotation`。它必须同时消费 deterministic structural evidence，例如 section title、list item packet、source section / packet provenance，以及经过验证的 `RouteAnnotation`。

硬性要求：

1. `Inputs for each run` 下的 list item 必须能形成 input demand。
2. `Required Outputs` 下的 list item 必须能形成 output demand。
3. 如果 LLM refinement 没有生成 `input_contract` / `output_contract` annotation，planner 仍应基于 deterministic section/list-item evidence 生成 demand，或产生明确 planner warning。
4. LLM refinement 只能增强、修正或补充 evidence，不能成为 resource contract demand 的唯一入口。

建议模型：

```python
ContractDirection = Literal["input", "output"]

@dataclass
class ResourceContractDemandIR:
    demand_id: str
    direction: ContractDirection
    required: bool
    evidence_text: str
    source_span_ids: list[str]
    source_section_id: str | None = None
    source_packet_id: str | None = None
    route_annotation_ids: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

@dataclass
class ResourceContractPlanIR:
    demands: list[ResourceContractDemandIR] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

`ResourceContractPlan` 不决定 `resource_kind`，只决定 source demand 是否存在、方向、requiredness 和 provenance。

示例：

```python
ResourceContractDemandIR(
    demand_id="rcd_output_s11",
    direction="output",
    required=True,
    evidence_text="Finished draft (Word or Google Doc, 200-500 words, no approval marks)",
    source_span_ids=["s11"],
    source_section_id="sec_required_outputs",
    source_packet_id="p_list_item_finished_draft_word_or_google_doc_200_500_words_no_approval_marks",
)
```

后续阶段消费 `ResourceContractPlan`，而不是各自重新解释 `routes.annotations`。

### 4.4 Resource Contract Field IR

新增一层显式资源合约 IR，作为 Stage 6 的输出或 Stage 6 内部中间结果。

建议模型：

```python
ResourceKind = Literal["variable", "file", "api", "type"]
ContractDirection = Literal["input", "output"]

@dataclass
class ResourceContractFieldIR:
    demand_id: str
    name: str
    resource_kind: ResourceKind
    direction: ContractDirection
    data_type: str
    required: bool
    description: str
    path: str | None = None
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    evidence_text: str | None = None
```

示例：

```python
ResourceContractFieldIR(
    demand_id="rcd_output_s11",
    name="finished_draft",
    resource_kind="file",
    direction="output",
    data_type="text",
    required=True,
    description="Finished draft, Word or Google Doc, 200-500 words, no approval marks.",
    path="< >",
    source_span_ids=["s11"],
    source_section_id="sec_required_outputs",
    source_packet_id="p_list_item_finished_draft_word_or_google_doc_200_500_words_no_approval_marks",
)
```

### 4.5 ResourceRegistryIR

`ResourceRegistryIR` 继续保留：

```python
variables: list[VariableSpec]
files: list[FileSpec]
apis: list[APISpec]
types: list[TypeSpec]
```

但 Stage 6 从 `ResourceContractFieldIR` materialize 到对应 registry：

```text
resource_kind=variable -> VariableSpec
resource_kind=file     -> FileSpec
resource_kind=api      -> APISpec
resource_kind=type     -> TypeSpec
```

不允许把所有 contract field 默认转换为 `VariableSpec`。

同时必须补充 provenance / direction 的承载方式。两种方案二选一：

1. 扩展 `VariableSpec` / `FileSpec`，增加 `direction`、`required`、`source_span_ids`、`source_section_id`、`source_packet_id`、`contract_demand_id`。
2. 保持现有 spec 简洁，新增 `ResourceContractBindingIR` sidecar，记录 scope-aware 的 resource 到 demand 绑定关系。

MVP 推荐 sidecar，降低对 renderer 和旧测试的冲击。

`ResourceContractBindingIR` 必须是 scope-aware 的，不能只是 `resource_name -> demand_id`：

```python
ResourceScopeKind = Literal["global", "worker", "handoff"]

@dataclass
class ResourceContractBindingIR:
    contract_demand_id: str
    resource_name: str
    resource_kind: ResourceKind
    direction: ContractDirection
    scope_kind: ResourceScopeKind
    scope_id: str | None
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
```

原因：当前 pipeline 已有 `WorkerScopedResourceIR.global_resources` 和 per-worker `worker_resources`。如果 binding 不带 scope，多 worker 或同名资源场景下，IRS 和 feedback 无法可靠解释“哪个 worker 的哪个 output contract 未满足”。

## 5. Stage 职责调整

### 5.1 StructuralNLAdapter

修改目标：

1. 保留 section / list item packet / provenance。
2. 保留 production 兼容路径，直到 `ResourceContractPlan`、Stage 3.5、Stage 6、provenance、IRS 都完成迁移。
3. 新增 feature flag 或 config：新路径可并行生成 `ResourceContractPlan`，但不立即关闭 `hard_facts`。
4. 最终删除或停用 `_extract_variables()` 和 `_infer_data_type()` 在主路径中的使用。

目标行为：

```text
StructuralNLAdapter.adapt()
  -> raw_sections
  -> semantic_packets
  -> compile_hints / route_priors
  -> hard_facts.inputs/outputs remain compatibility-only until Phase 5
```

### 5.2 Stage 2 Field Router

修改目标：

1. 继续基于 section title、packet shape、LLM refinement 生成 `RouteAnnotation`。
2. `input_contract` / `output_contract` annotation 只表达 resource contract evidence。
3. 不把 annotation 反写成新的 `hard_facts`。
4. route refinement diagnostics 继续保留在 stage-local checkpoint，不进入 feedback report。
5. 不要求 `RouteAnnotation.field="resources"` 成为新的 legacy field。

说明：

当前 `FieldRouteIR` 的 legacy fields 只有 `identity/audience/rules/domain/integrations/behavior`。如果要新增 `resources` 字段，必须做完整 schema migration，包括 helper、checkpoint、tests。MVP 更稳妥的方式是：ResourceContractPlanner 可以接受 `annotation.field="resources"`，但不得依赖不存在的 `routes.resources` legacy list；主键必须是 `semantic_role="output_contract"`、`route_family="resource_contract"`、`construct_target="RESOURCE_CONTRACT"`、`slot_target="output"` 以及 source provenance。

### 5.3 ResourceContractPlanner

新增 planner，输入为 resolved spans + deterministic structural evidence + validated `FieldRouteIR.annotations`，输出 `ResourceContractPlanIR`。

职责：

1. 收集 `semantic_role in {"input_contract", "output_contract"}` 的 annotations。
2. 收集 deterministic structural evidence：
   - resolved spans
   - source section title
   - source packet id
   - list item text
   - section title priors，例如 `Inputs for each run` / `Required Outputs`
3. 对 `Required Outputs` / `Inputs for each run` 下的 list item，即使没有最终 contract annotation，也必须生成 demand 或 planner warning。
4. 读取对应 span 原文、section、packet。
5. 生成稳定 demand id。
6. 合并同一 source packet 的重复 evidence。
7. 保存 checkpoint，供 Stage 3.5、Stage 6、IRS 复用。

非职责：

1. 不生成变量名。
2. 不判断 `resource_kind`。
3. 不判断 data type。
4. 不 materialize `VariableSpec` 或 `FileSpec`。
5. 不调用 LLM。

### 5.4 Stage 3.5 Worker Boundary Planner

当前 Stage 3.5 从 `canonical_input.hard_facts.inputs/outputs` 构造 hard contracts。该路径需要迁移。

修改目标：

1. 消费 `ResourceContractPlanIR`，不直接解释 raw `routes.annotations`。
2. 在 prompt 中提供 resource contract demands，格式包含原文和 provenance，而不是 hard facts 的变量名/类型。
3. Stage 3.5 只需要确认 worker IO 和 handoff 有 source-backed demand，不决定 file/variable/type。
4. candidate 的 possible_inputs/possible_outputs 可以由 LLM 提议，但必须引用 `demand_id`。
5. materializer 的 source backing guard 改为基于 `demand_id`，而不是 hard fact names。

建议 prompt context：

```text
Resource contract demands:
- input: demand=rcd_input_s8, span=s8, text="Topic summary", section=sec_inputs_for_each_run, packet=...
- output: demand=rcd_output_s11, span=s11, text="Finished draft (Word or Google Doc, 200-500 words, no approval marks)", section=sec_required_outputs, packet=...
```

兼容策略：

在 Stage 3.5 完成迁移前，`hard_facts` 兼容路径继续保留。只有当 `ResourceContractPlanIR` 被用于 prompt、materializer guard、worker plan provenance 后，才能关闭 production 默认写入 `hard_facts.inputs/outputs`。

### 5.5 Stage 6 Resource Extractor

Stage 6 是资源语义建模的主位置。

修改目标：

1. Prompt 明确要求从 `ResourceContractPlanIR` 中 materialize resource contracts。
2. LLM 必须输出 `resource_kind`、`demand_id`、`name`、`data_type`、`direction`、`required`、`description`。
3. 对 output file artifact，无编译期路径时使用 `path="< >"`。
4. 区分 input file resource 和 output file artifact。
5. 删除 `_merge_contract_variables()` 对所有 contract field 的无条件变量化。
6. 将 LLM 输出解析为 `ResourceContractFieldIR`，再 materialize 到 `ResourceRegistryIR` 和 sidecar bindings。

Stage 6 输出建议：

```json
{
  "resource_contracts": [
    {
      "name": "finished_draft",
      "resource_kind": "file",
      "direction": "output",
      "data_type": "text",
      "required": true,
      "path": "< >",
      "description": "Finished draft in Word or Google Doc format, 200-500 words, no approval marks.",
      "source_span_ids": ["s11"]
    }
  ],
  "variables": [],
  "files": [],
  "apis": [],
  "types": []
}
```

Parser 可以兼容旧格式，但新格式优先。

仅改 prompt 不足够。Stage 6 必须同步改：

1. context builder：新增 ResourceContractPlan section。
2. system prompt：新增 `resource_contracts` schema。
3. parser：支持 `resource_kind` 和 `demand_id`。
4. materializer：根据 kind 写入 variables/files/apis/types。
5. provenance：保留 demand 到 materialized resource 的绑定。
6. diagnostics：当 LLM 输出缺 kind、缺 provenance、非法 kind 时产生 compiler diagnostic 或 requirement diagnostic。

### 5.6 Stage 9.5 Normalizer

当前 Stage 9.5 会把多输出 step 聚合为 structured result，这是为了满足 SPL command 单 RESULT 约束。

修改目标：

1. 聚合结构化结果时保留 resource kind。
2. 如果 structured result 包含 file output，type definition 中字段可以引用 file resource 名称或数据类型，但不能删除 `FileSpec`。
3. Worker output contract 可以引用 structured result，但 `[DEFINE_FILES:]` 仍必须声明 file resource。

关键规则：

```text
multi-output aggregation may replace worker [OUTPUTS],
but must not erase ResourceRegistryIR.files.
```

### 5.7 Stage 10 Worker Assembler

修改目标：

1. Worker inputs/outputs 应能引用 variable 或 file。
2. `WorkerOutput` 如果暂时保持 `name/required` 结构，则必须保证 referenced name 可在 variable/file registry 中解析。
3. 后续可扩展 `WorkerOutput.resource_kind`，但 MVP 可先依赖 `ResourceRegistryIR` lookup。

必须补充 resolver 闭环：

```python
def resolve_resource_ref(name: str, resources: ResourceRegistryIR) -> ResolvedResourceRef | None:
    ...
```

该 resolver 至少服务于：

1. Worker input/output validation。
2. ProducerIndex required output producer 检查。
3. IRS resource contract checker。
4. Feedback provenance。

### 5.8 Stage 11 SPL Renderer

renderer 不做推断，只做以下渲染：

```text
ResourceRegistryIR.variables -> [DEFINE_VARIABLES:]
ResourceRegistryIR.files     -> [DEFINE_FILES:]
ResourceRegistryIR.types     -> [DEFINE_TYPES:]
WorkerIR.outputs             -> [OUTPUTS] <REF>name</REF>
```

验收点：

```spl
[DEFINE_FILES:]
    "Finished draft in Word or Google Doc format, 200-500 words, no approval marks." finished_draft < >: text
[END_FILES]
```

### 5.9 IRS / Post-normalize Checker

IRS 不负责抽取 file output，但负责检查已 materialized 的 resource contract 是否满足 source demand。

新增或扩展检查：

1. source-demanded output contract 是否 materialized。
2. materialized resource kind 是否与 source evidence 一致。
3. required output 是否有 producer。
4. file output 是否在 `[DEFINE_FILES:]` 中声明。
5. worker output 是否引用可解析 resource。

如果 source demand 是 `Finished draft (Word or Google Doc...)`，但最终只有 text variable，没有 file resource，应产生 user-facing diagnostic：

```text
kind=resource_kind_mismatch
target=resource_contract:s11
message=Required output appears to be a document/file artifact, but was materialized as a text variable.
```

## 6. hard_facts 废弃策略

### 6.1 当前问题

`hard_facts` 当前仍被以下路径消费：

1. Stage 3.5 prompt 中作为 hard inputs/outputs。
2. Stage 3.5 materializer 中用于 contract recovery。
3. Stage 6 context 中作为 authoritative contract。
4. Provenance 中作为 normalized variable source。
5. 测试中作为 adapter hard fact 预期。

因此不能只删除 adapter 中几行代码。必须同步迁移消费者。

### 6.2 目标定义

`hard_facts` 在新架构中不再表示 resource contract。

保留选项：

1. 短期保留 dataclass 字段以兼容序列化和旧测试。
2. Phase 5 之后 production 默认为空。
3. 只允许表达 truly deterministic non-semantic facts；如果没有明确需求，应完全废弃。

### 6.3 禁止事项

1. 禁止新增 downstream 对 `hard_facts.inputs/outputs` 的依赖。
2. 禁止 downstream 将 `hard_facts.outputs` 当作 final output contract 长期权威。
3. 禁止从 hardcoded keyword 推断 SPL data type。
4. 禁止在 `ResourceContractPlan` 迁移完成后继续用 adapter compatibility path 影响 production compile result。
5. 禁止先清空 `hard_facts.inputs/outputs` 再补 Stage 3.5 / Stage 6 消费链路。

## 7. LLM 与 deterministic code 的边界

LLM 负责：

1. 从 `ResourceContractPlan` demand 中识别 resource kind。
2. 生成 resource name。
3. 推断 data type。
4. 判断 document/file artifact 是否应进入 `FileSpec`。
5. 识别 enum、structured type、list type。

deterministic code 负责：

1. 校验 LLM 输出 schema。
2. 校验 source provenance 是否存在。
3. 校验 resource kind 是否在允许集合内。
4. 应用 SPL grammar normalization，例如 runtime path `< >`。
5. 去重、合并、冲突诊断。
6. 不从关键词重新发明资源语义。

### 7.1 文档产物产品规则

`Finished draft` 不是语法上必然等于 file。它成为 file output artifact 是产品语义规则，而不是 SPL grammar 自动结论。

建议规则：

1. 当 required output 明确指向可交付文档 artifact，例如 Word、Google Doc、PDF、doc、document、file upload/download 时，优先 materialize 为 output file resource。
2. 当 required output 只是普通 draft text、message、summary、response，且没有文档 artifact 格式要求时，可以 materialize 为 variable。
3. 当证据不足以区分 file artifact 和 text variable 时，Stage 6 应输出 ambiguity diagnostic，不能静默降级为 text。
4. LLM 输出应包含 justification 或 evidence reference；deterministic validator 只校验证据存在和 schema 合法，不靠关键词重做语义判断。

## 8. 分阶段实施计划

### Phase 0: 保护测试和可观测性

1. 新增 regression fixture：`Finished draft (Word or Google Doc...)`。
2. 记录当前失败行为：
   - finished draft 出现在 `[DEFINE_VARIABLES:]`。
   - `[DEFINE_FILES:]` 缺少 finished draft。
   - feedback provenance 显示它来自 adapter hard fact。
3. 增加测试先标记为 expected failure 或在重构分支中启用。

### Phase 1: 引入 ResourceContractPlan，并保证 deterministic structural evidence 稳定进入 plan

1. 新增 `ResourceContractDemandIR` / `ResourceContractPlanIR`。
2. 新增 `ResourceContractPlanner`，输入不只看 `RouteAnnotation`，还必须消费：
   - resolved spans
   - source_section_id / source_packet_id
   - section title priors
   - list item structural packets
   - validated RouteAnnotation
3. 对 `Required Outputs` / `Inputs for each run` 下的 list item，即使 LLM refinement 没有生成 `output_contract` / `input_contract` annotation，也应生成 demand 或 planner warning。
4. RouteAnnotation 仍作为 span-level evidence；LLM refinement 只能增强或修正，不是唯一入口。
5. 保存 checkpoint，例如 `stage2_5_resource_contract_plan.json`。
6. 不关闭 `hard_facts.inputs/outputs`。
7. 新增测试验证：
   - `Required Outputs` 生成 output demand。
   - `Inputs for each run` 生成 input demand。
   - demand 包含 source span、section、packet、raw evidence text。
   - demand 不包含 `resource_kind`、name、data_type。
   - 当最终 annotations 缺少 `output_contract` 时，planner 仍能基于 section/list-item evidence 生成 demand 或 warning。

### Phase 2: Stage 3.5 迁移到 ResourceContractPlan

1. Stage 3.5 prompt 同时接收 legacy hard facts 和 `ResourceContractPlan`。
2. materializer 的 source backing guard 增加 `demand_id` 路径。
3. worker/candidate contract 记录 demand provenance。
4. 当新路径稳定后，`hard_fact_inputs/hard_fact_outputs` 只作为 fallback，不再作为首选权威。

### Phase 3: Stage 6 资源合约建模 + binding / resolver / ProducerIndex / IRS 闭环

1. 引入 `ResourceContractFieldIR`。
2. 更新 Stage 6 context builder，加入 `ResourceContractPlan` section。
3. 更新 Stage 6 prompt schema，要求 `resource_contracts` 和 `resource_kind`。
4. 解析新 schema。
5. 将 `resource_kind=file` materialize 为 `FileSpec(path="< >")`。
6. 新增 scope-aware `ResourceContractBindingIR` sidecar，保留 demand 到 materialized resource 的映射。
7. 停止 `_merge_contract_variables()` 对新路径 contract 的无条件变量化行为。
8. 同步新增 resource resolver，同时查询 variables 和 files。
9. 同步扩展 ProducerIndex：承认 file output producer，或明确报告 file output producer 缺失。
10. 同步扩展 IRS：使用 `ResourceContractPlan + ResourceContractBindingIR + ResourceRegistryIR` 检查 materialization、producer 和 kind mismatch。

硬性要求：不允许只生成 `FileSpec` 而没有 resolver / ProducerIndex / IRS 语义闭环。

必须定义：

1. worker output 如何引用 file resource。
2. file output 是否需要 producer。
3. step / handoff / structured aggregation 怎样产生 file output。
4. Post-normalize IRS 怎样判断 missing producer / kind mismatch。
5. 如果只有 text variable 满足了疑似 file artifact demand，输出 `resource_kind_mismatch`。

### Phase 4: Normalizer / Assembler / Renderer 对齐

1. 确保 Stage 9.5 多输出聚合不删除 file resources。
2. 确保 Worker output references 能解析到 variable 或 file。
3. Renderer 无需猜测，只验证 `resources.files` 是否渲染。

### Phase 5: 删除 legacy hard_facts 消费

1. 默认关闭 adapter 写入 `hard_facts.inputs/outputs`。
2. 删除 Stage 3.5 hard fact recovery。
3. 删除 Stage 6 canonical hard fact merge。
4. 删除 provenance 中 adapter `VariableFact` 特例，改为 resource contract provenance。
5. 更新或删除相关 legacy tests。

## 9. MVP 落地边界

最小可接受 MVP 不应该只是给 `Finished draft` 写关键词补丁。MVP 应至少完成：

1. 新增 `ResourceContractPlan`，并让 Stage 3.5 / Stage 6 消费它。
2. adapter hard facts 保留为兼容 fallback，但新路径不再依赖 hardcoded `_infer_data_type()`。
3. Stage 6 能从 `ResourceContractPlan` 中生成 file resource。
4. `Finished draft` 在明确是 document artifact 时稳定进入 `[DEFINE_FILES:]`。
5. feedback report 不再把该 output 解释为 adapter hard fact variable。
6. 没有 file resource 或 kind mismatch 时，IRS/feedback 能报告 resource materialization gap。
7. resource resolver 能解析 worker output 引用的 variable 或 file。

MVP gate：

```text
Gate 1: ResourceContractPlan 有 deterministic section/list-item evidence 入口。
Gate 2: ResourceContractBindingIR 是 scope-aware 的。
Gate 3: FileSpec 输出和 resolver / ProducerIndex / IRS 同步闭环。
```

不允许出现以下半成品状态：

```text
RouteAnnotation 没有 output_contract -> ResourceContractPlan 空
```

或：

```text
[DEFINE_FILES:] 有 finished_draft
但 worker output / producer / IRS 仍按普通变量语义处理
```

MVP 可以暂缓：

1. 完整废弃 `HardFacts` dataclass。
2. 所有 worker input/output 都显式携带 `resource_kind`。
3. 完整 enum/type inference 重构。
4. compile report 重新引入。

## 10. 验收标准

对 demo 输入：

```text
- Finished draft (Word or Google Doc, 200-500 words, no approval marks)
- Status flag (values: 'drafting', 'ready for review', 'approved')
```

期望 SPL：

```spl
[DEFINE_FILES:]
    "Finished draft in Word or Google Doc format, 200-500 words, no approval marks." finished_draft < >: text
[END_FILES]
```

这是产品语义验收：当 required output 明确声明 Word / Google Doc / PDF / document artifact 时，优先 materialize 为 output file resource。普通 draft text 不自动进入 `[DEFINE_FILES:]`。

期望变量/类型：

```spl
[DEFINE_VARIABLES:]
    "Status flag..." status_flag: status_flag_type
[END_VARIABLES]

[DEFINE_TYPES:]
    status_flag_type = enum { drafting, ready_for_review, approved }
[END_TYPES]
```

enum 不是本次 resource contract MVP 的硬门槛。如果 enum MVP 暂不实现，可接受 `status_flag: text`，但必须保留 source evidence 和后续 enum upgrade TODO。

不允许：

```spl
"Finished draft word or google doc..." finished_draft_word_or_google_doc_200_500_words_no_approval_marks: text
```

作为唯一 materialization。

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Stage 2 没有最终 `output_contract` annotation，导致 ResourceContractPlan 为空 | Planner 必须消费 deterministic section/list-item evidence；annotation 不是唯一入口 |
| 删除 hard_facts 后 Stage 3.5 contract 变空 | hard_facts 删除后移到 Phase 5；先完成 ResourceContractPlan、Stage 3.5、Stage 6、IRS 迁移 |
| LLM 输出不稳定 | schema validator + provenance validator + IRS diagnostic |
| 文件产物与文本变量边界模糊 | 明确产品规则；证据不足时输出 ambiguity diagnostic，不静默降级 |
| 多输出聚合隐藏 file output | Stage 9.5 保留 FileSpec，不把 registry 资源视为 step-local field |
| 只生成 FileSpec 但 worker output/producer 无法解析 | 新增 unified resource resolver，并接入 ProducerIndex / IRS |
| legacy tests 大量失败 | 分阶段更新测试，先改 adapter expectations，再改 planner/resource expectations |

## 12. 需要修改的主要文件

预计涉及：

```text
src/nl2spl/adapters/structural_nl.py
src/nl2spl/canonical/compile_input.py
src/nl2spl/ir/field_route_ir.py
src/nl2spl/ir/resource_registry_ir.py
src/nl2spl/ir/worker_plan_ir.py
src/nl2spl/pipeline/stages/stage2_5_resource_contract_planner/*
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/*
src/nl2spl/pipeline/stages/stage6_resource_extractor/*
src/nl2spl/pipeline/stages/stage9_5_normalizer/*
src/nl2spl/pipeline/stages/stage10_worker_assembler/*
src/nl2spl/pipeline/stages/stage11_spl_renderer/*
src/nl2spl/pipeline/resource_resolver.py
src/nl2spl/compiler/irs/checkers/*
src/nl2spl/pipeline/provenance.py
tests/unit/test_input_adapters.py
tests/unit/test_resource_extractor.py
tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py
```

## 13. 决策记录

1. `hard_facts.inputs/outputs` 不再作为 resource contract 主路径。
2. adapter 不再负责变量提取和类型推断。
3. `RouteAnnotation` 只是 span-level evidence，不是 construct-level demand authority。
4. `ResourceContractPlan` 是 Stage 3.5、Stage 6、IRS 的共同 demand artifact。
5. hard_facts 的删除必须后移，不能先删再补。
6. 文件产物通过 `FileSpec` 进入 `[DEFINE_FILES:]`，但只有明确 document artifact demand 才优先 file。
7. renderer 不负责把变量修正成文件。
8. IRS 负责检查 source-demanded resource contract 是否被满足。
