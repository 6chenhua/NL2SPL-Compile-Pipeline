# Resource Contract 重构实施计划

版本: 1.1  
日期: 2026-06-08  
状态: Implementation plan  
依据: `docs/design/resource_contract_annotation_refactor_design.md` v1.2  
范围: ResourceContractPlan、Stage 3.5、Stage 6、binding、resolver、ProducerIndex、IRS、hard_facts 迁移

## 0. 实施原则

本计划是后续编码和验收的共同检查表。实现必须严格满足三个 gate：

```text
Gate 1: ResourceContractPlan 必须有 deterministic section/list-item evidence 入口。
Gate 2: ResourceContractBindingIR 必须是 scope-aware 的。
Gate 3: FileSpec 输出必须和 resolver / ProducerIndex / IRS 同步闭环。
```

禁止出现两类半成品：

```text
RouteAnnotation 没有 output_contract -> ResourceContractPlan 空
```

或：

```text
[DEFINE_FILES:] 有 finished_draft
但 worker output / producer / IRS 仍按普通变量语义处理
```

Stage 11 `<REF>` 渲染不属于本次阻塞项；当前工作区已经渲染 `<REF>{name}</REF>`。

本计划同时定义后续代码审阅标准。任何阶段的实现如果没有提交对应的验收证据，即使代码能运行，也不能视为该阶段完成。

## 1. 当前基线

当前代码事实：

1. `StructuralNLAdapter` 生成 `list_item` / `sentence` packets，并通过 legacy path 写入 `hard_facts.inputs/outputs`。
2. Stage 2 对 `Required Outputs` 可生成 structural prior；最终 `output_contract` annotation 依赖 LLM refinement 或 deterministic `runtime_input/required_output` packet。
3. Stage 3.5 从 `hard_facts.inputs/outputs` 构造 `ContractFieldIR`。
4. Stage 6 `_merge_contract_variables()` 会把 worker contract 全部转成 `VariableSpec`。
5. `ResourceRegistryIR.files` 是 `[DEFINE_FILES:]` 的唯一来源。
6. `ProducerIndex` 和 post-normalize IRS 目前按 variable producer 语义工作。

基线失败现象：

```text
Finished draft (Word or Google Doc...)
  -> VariableFact(data_type=text)
  -> ContractFieldIR(data_type=text)
  -> VariableSpec(data_type=text)
  -> [DEFINE_VARIABLES:]
```

而不是：

```text
ResourceContractDemandIR(direction=output)
  -> ResourceContractFieldIR(resource_kind=file)
  -> FileSpec(path="< >")
  -> [DEFINE_FILES:]
```

## 2. 分阶段总览

| Phase | 目标 | 可合入条件 |
|---|---|---|
| 0 | 建立基线保护和回归夹具 | 测试能稳定复现当前问题，且不改变生产行为 |
| 1 | 引入 `ResourceContractPlan` deterministic 入口 | 无最终 annotation 时仍能从 section/list item 生成 demand 或 warning |
| 2 | 接入 orchestrator checkpoint 和 provenance 骨架 | plan 进入 intermediate/checkpoint，但不破坏现有 pipeline |
| 3 | Stage 3.5 迁移到 plan | worker/candidate contract 可引用 `demand_id`，hard_facts 变 fallback |
| 4 | Stage 6 + binding + resolver + ProducerIndex + IRS 闭环 | file resource materialization 与 producer/IRS 语义一致 |
| 5 | Normalizer / assembler / renderer 对齐 | 多输出聚合不抹掉 file resource，worker outputs 可解析 |
| 6 | 关闭 legacy hard_facts 主路径 | adapter 不再在 production 写入 hard facts，旧消费点删除或降级 |
| 7 | 端到端验收 | demo 输出、feedback、diagnostics、checkpoint 全部符合标准 |

## 3. 设计 Gate 到实施项追踪矩阵

本节用于审阅时判断实现是否严格对齐设计文档 v1.2。

| 设计约束 | 必须落地的代码位置 | 必须落地的测试 | 拒收条件 |
|---|---|---|---|
| Gate 1: deterministic section/list-item evidence 入口 | `ResourceContractPlanner`、orchestrator Stage 3.2、checkpoint writer | planner unit test、orchestrator checkpoint test | planner 只读取 `RouteAnnotation`；没有 final annotation 时 plan 为空 |
| Gate 2: scope-aware binding | `ResourceContractBindingIR`、Stage 6 materializer、`WorkerScopedResourceIR` | Stage 6 binding test、多 worker 同名资源 test | binding 只有 `resource_name -> demand_id`，无法区分 worker/global/handoff |
| Gate 3: FileSpec resolver / ProducerIndex / IRS 闭环 | Stage 6、resource resolver、ProducerIndex、post-normalize IRS | resolver test、producer test、IRS missing producer/kind mismatch test | 只生成 `[DEFINE_FILES:]`，但 producer/IRS 仍按普通 variable 处理 |
| RouteAnnotation 只做 evidence | Stage 2 不直接生成 construct-level demand；Stage 3.2 聚合 evidence | planner 去重/融合测试 | Stage 3.5、Stage 6、IRS 各自重新解释 raw annotations |
| hard_facts 保守迁移 | Stage 3.5 fallback、Stage 6 legacy merge、adapter flag 或默认路径 | fallback on/off 测试 | 过早删除 hard facts 导致 Stage 3.5 contract 为空 |
| renderer 被动渲染 | Stage 11 不加入 file 推断逻辑 | renderer snapshot 或 E2E test | renderer 通过名称/描述猜测 `finished_draft` 是 file |
| feedback 边界 | IRS diagnostic projection、feedback renderer | feedback report test | route refinement/system telemetry 进入 feedback report |

## 4. 每阶段审阅证据包

每个 Phase 提交验收时必须提供以下内容：

```text
Phase: <编号和名称>
Changed files:
- <file>

Design gates covered:
- Gate <n>: <说明>

Behavior before:
- <旧行为或失败链路>

Behavior after:
- <新行为或新 artifact>

Tests run:
- <命令>

Artifacts inspected:
- <checkpoint / final_spl / feedback_report / unit fixture>

Known remaining work:
- <必须只列后续 Phase 范围内的事项>
```

审阅时只接受可复现证据，不接受“代码看起来应该可以”的描述。涉及 LLM 的阶段必须提供 deterministic/mock 层测试；真实 LLM demo 只能作为补充证据，不能替代单元或集成测试。

## 5. 全局禁止项

以下做法在任意 Phase 都直接拒收：

1. 在 renderer 中根据资源名、描述、后缀或关键词推断 file。
2. 只对 `finished_draft`、`Word or Google Doc` 做特例修复。
3. 让 Stage 3.5、Stage 6、IRS 分别直接解释 raw `RouteAnnotation`。
4. 只生成 `FileSpec`，不实现 scope-aware binding、resolver、ProducerIndex、IRS 检查。
5. 把 `ResourceContractPlan` 设计成 LLM-only artifact。
6. 在 Phase 6 之前删除 `hard_facts.inputs/outputs` 的兼容 fallback。
7. 重新引入面向用户的 `compile_report.txt` 作为 MVP 主报告。
8. 把系统内部 route refinement telemetry 投射进 `feedback_report`。

## 6. Phase 0: 基线保护

### 6.1 代码改动

不改生产代码。只允许新增测试、fixture、测试工具。

建议新增 fixture：

```text
tests/fixtures/resource_contract/internal_comms_required_outputs.md
```

内容应至少包含：

```text
## Inputs for each run
- Topic summary
- Target audience

## Required Outputs
- Finished draft (Word or Google Doc, 200-500 words, no approval marks)
- Status flag (values: 'drafting', 'ready for review', 'approved')
```

### 6.2 测试

新增基线测试，允许标记为 `xfail` 或仅记录当前行为：

1. adapter 当前仍写入 `hard_facts.outputs`。
2. `Finished draft...` 当前被推断为 `text`。
3. 当前 final SPL 中 `finished_draft...` 出现在 `[DEFINE_VARIABLES:]`。
4. 当前 `[DEFINE_FILES:]` 不包含 finished draft。

### 6.3 验收标准

1. 测试能稳定描述当前失败链路。
2. 不要求当前测试通过新期望。
3. 不改变 demo 当前输出。

## 7. Phase 1: ResourceContractPlan deterministic 入口

### 7.1 新增 IR

建议新增文件：

```text
src/nl2spl/ir/resource_contract_ir.py
```

新增：

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
    evidence_sources: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

@dataclass
class ResourceContractPlanIR:
    demands: list[ResourceContractDemandIR] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

`evidence_sources` 建议使用值：

```text
section_title
list_item_packet
route_annotation
structural_prior
legacy_hard_fact_fallback
```

### 7.2 新增 planner

建议新增：

```text
src/nl2spl/pipeline/stages/stage3_2_resource_contract_planner/
```

命名为 Stage 3.2，是因为它必须消费 Stage 3 后的 resolved spans/routes，且应在 Stage 3.25 ConstructPlan 和 Stage 3.5 WorkerBoundaryPlanner 前运行。

输入：

```python
resolved_spans: list[SpanIR]
resolved_routes: FieldRouteIR
canonical_input: CanonicalCompileInput
```

必须消费：

1. resolved spans。
2. `source_section_id` / `source_packet_id`。
3. `canonical_input.raw_sections` 的 section title。
4. `canonical_input.semantic_packets` 的 list item text。
5. `resolved_routes.structural_priors`。
6. validated `resolved_routes.annotations`。

不得只消费 `resolved_routes.annotations`。

### 7.3 demand 生成规则

规则一：annotation evidence。

当 annotation 满足：

```text
semantic_role in {"input_contract", "output_contract"}
route_family == "resource_contract" 或 construct_target == "RESOURCE_CONTRACT"
```

生成 demand。

规则二：deterministic section/list-item evidence。

当 span 所属 section title 是：

```text
inputs for each run
inputs_for_each_run
required outputs
required_outputs
```

且 backing packet 是 list item 或 sentence，生成对应 demand，即使没有最终 annotation。

规则三：warning 而非静默丢失。

如果 `Required Outputs` 或 `Inputs for each run` section 下存在非空 list item，但无法映射到 resolved span，必须生成 planner warning。

### 7.4 demand_id

建议稳定格式：

```text
rcd_input_<span_id>
rcd_output_<span_id>
```

如果一个 packet 被拆分成多个 resolved span，可追加序号：

```text
rcd_output_<source_packet_id>_<n>
```

### 7.5 测试

新增测试文件：

```text
tests/unit/test_resource_contract_planner.py
```

必须覆盖：

1. `Required Outputs` list item 在没有 final annotation 时仍生成 output demand。
2. `Inputs for each run` list item 在没有 final annotation 时仍生成 input demand。
3. annotation 和 section evidence 指向同一 packet 时去重。
4. demand 不包含 `resource_kind`、`name`、`data_type`。
5. 空 section 或 empty marker 不生成 demand。
6. 找不到 resolved span 时生成 warning。

### 7.6 验收标准

Phase 1 通过条件：

1. `ResourceContractPlanIR` 可序列化到 JSON。
2. 对 demo 输入，即使 Stage 2 LLM 不返回 `output_contract` annotation，也能得到两个 output demands。
3. `hard_facts.inputs/outputs` 仍保持兼容，不被关闭。

## 8. Phase 2: Orchestrator 接入与 checkpoint

### 8.1 代码改动

在 orchestrator 中插入：

```text
Stage 3: Ambiguity Resolution
Stage 3.2: Resource Contract Planning
Stage 3.25: Construct Demand Planning
Stage 3.5: Worker Boundary Planning
```

保存：

```python
intermediate["resource_contract_plan"] = resource_contract_plan
intermediate["resource_contract_plan_payload"] = resource_contract_plan.to_payload()
```

checkpoint 文件建议：

```text
stage3_2_resource_contract_plan.json
```

### 8.2 兼容要求

1. 不改变 Stage 3.5 输入行为，Stage 3.5 仍可使用 hard facts。
2. 不改变 Stage 6 输入行为。
3. 不改变 final SPL。

### 8.3 测试

新增或更新 orchestrator 测试：

1. `PipelineResult.intermediate_results` 包含 `resource_contract_plan`。
2. checkpoint 存在。
3. demo plan 中包含 finished draft output demand。

### 8.4 验收标准

Phase 2 通过条件：

1. 现有单元测试不因新增 stage 失败。
2. demo 输出 SPL 可以不变，但 checkpoint 中必须出现 resource contract demands。

## 9. Phase 3: Stage 3.5 迁移到 ResourceContractPlan

### 9.1 IR 扩展

扩展 `ContractFieldIR`，增加可选字段，必须带默认值以兼容现有 positional 构造：

```python
contract_demand_id: str | None = None
source_span_ids: list[str] = field(default_factory=list)
source_section_id: str | None = None
source_packet_id: str | None = None
```

### 9.2 Stage 3.5 输入扩展

扩展 `PlannerInput` 和 `_run_stage3_5`：

```python
tuple[
    list[SpanIR],
    FieldRouteIR,
    CanonicalCompileInput | None,
    ResourceContractPlanIR | None,
]
```

保留旧 tuple 输入兼容。

### 9.3 Prompt 改造

在 Stage 3.5 prompt 中新增：

```text
Resource contract demands:
- demand_id=rcd_input_s8, direction=input, required=true,
  text="Topic summary", span=s8, section=sec_inputs_for_each_run, packet=...
- demand_id=rcd_output_s11, direction=output, required=true,
  text="Finished draft (Word or Google Doc...)", span=s11, section=sec_required_outputs, packet=...
```

`hard inputs` / `hard outputs` 仍可保留，但标注为 legacy fallback。

### 9.4 Materializer 改造

1. candidate possible input/output 可以引用 `contract_demand_id`。
2. source-backed guard 优先使用 `contract_demand_id`。
3. 没有 demand id 时才 fallback 到 legacy hard fact name matching。
4. worker main input/output contract 应保留 demand provenance。

### 9.5 测试

新增或更新：

```text
tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py
```

必须覆盖：

1. Stage 3.5 prompt 包含 resource contract demands。
2. Materializer 能用 `demand_id` 验证 output contract source-backed。
3. hard facts 缺失但 plan 存在时，main worker contract 不为空。
4. plan 缺失但 hard facts 存在时，legacy fallback 仍可工作。

### 9.6 验收标准

Phase 3 通过条件：

1. Stage 3.5 不再必须依赖 `canonical_input.hard_facts.inputs/outputs`。
2. WorkerPlan output contract 中可追溯到 `rcd_output_s11`。
3. 关闭 hard fact fallback 的测试模式下，demo 仍能生成 main worker IO contract。

## 10. Phase 4: Stage 6 + binding + resolver + ProducerIndex + IRS 闭环

Phase 4 是一个不可拆开的 gate。不得只实现 `FileSpec` materialization 后合入为完成。

### 10.1 新增 IR

在 `resource_contract_ir.py` 或 `resource_registry_ir.py` 中新增：

```python
ResourceKind = Literal["variable", "file", "api", "type"]
ResourceScopeKind = Literal["global", "worker", "handoff"]

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
    justification: str | None = None

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

扩展 `WorkerScopedResourceIR`：

```python
resource_contract_bindings: list[ResourceContractBindingIR] = field(default_factory=list)
```

### 10.2 Stage 6 context builder

新增 ResourceContractPlan section：

```text
Resource contract demands
- demand_id: rcd_output_s11
  direction: output
  required: true
  evidence: Finished draft (Word or Google Doc...)
  section: sec_required_outputs
  packet: p_list_item_finished_draft...
```

要求 Stage 6 prompt：

1. 输出 `resource_contracts`。
2. 每个 item 必须引用 `demand_id`。
3. 每个 item 必须有 `resource_kind`。
4. document output artifact 无编译期路径时，`path="< >"`。
5. 不得把所有 output contract 默认变成 variables。

### 10.3 Stage 6 parser / materializer

新 schema 优先，旧 schema 兼容：

```json
{
  "resource_contracts": [
    {
      "demand_id": "rcd_output_s11",
      "name": "finished_draft",
      "resource_kind": "file",
      "direction": "output",
      "data_type": "text",
      "required": true,
      "path": "< >",
      "description": "...",
      "source_span_ids": ["s11"]
    }
  ],
  "variables": [],
  "files": [],
  "apis": [],
  "types": []
}
```

Materialization：

```text
resource_kind=variable -> VariableSpec
resource_kind=file     -> FileSpec
resource_kind=api      -> APISpec
resource_kind=type     -> TypeSpec
```

同时生成 scope-aware binding。

### 10.4 ResourceResolver

新增：

```text
src/nl2spl/pipeline/resource_resolver.py
```

建议 API：

```python
@dataclass(frozen=True)
class ResolvedResourceRef:
    name: str
    resource_kind: ResourceKind
    data_type: str
    scope_kind: ResourceScopeKind
    scope_id: str | None
    binding: ResourceContractBindingIR | None = None

def resolve_resource_ref(
    name: str,
    resources: ResourceRegistryIR,
    bindings: Sequence[ResourceContractBindingIR] = (),
    scope_kind: ResourceScopeKind = "global",
    scope_id: str | None = None,
) -> ResolvedResourceRef | None:
    ...
```

Resolver 必须：

1. 同时查 `variables` 和 `files`。
2. 优先匹配当前 scope。
3. 对同名冲突返回 deterministic diagnostic 或显式冲突结果。

### 10.5 ProducerIndex

扩展 producer 语义：

1. `ProducerRef` 增加 `resource_kind`，默认 `"variable"`。
2. 查询方法支持：
   ```python
   is_produced(name: str, resource_kind: ResourceKind | None = None) -> bool
   ```
3. step output 如果通过 binding 绑定到 file resource，应被记录为 file producer。
4. handoff output binding 如果绑定 file demand，也应支持 file producer。
5. worker `[OUTPUTS]` declaration 仍不算 producer。

### 10.6 IRS / diagnostics

新增或扩展 post-normalize checker：

1. 每个 `ResourceContractDemandIR` 是否有 binding。
2. binding 的 `resource_kind` 是否匹配 materialized registry。
3. output demand 是否有 renderable producer。
4. file demand 是否进入 `ResourceRegistryIR.files`。
5. 只有 text variable 满足 document artifact demand 时，产生 `resource_kind_mismatch`。

诊断必须 user-facing，仅当 source demand 真的无法满足时进入 feedback report。

### 10.7 测试

新增或更新：

```text
tests/unit/test_resource_contract_stage6.py
tests/unit/test_resource_resolver.py
tests/unit/test_producer_index.py
tests/unit/test_post_normalize_resource_contract_irs.py
```

必须覆盖：

1. `ResourceContractFieldIR(resource_kind=file)` 生成 `FileSpec(path="< >")`。
2. scope-aware binding 包含 scope、direction、demand id、source evidence。
3. resolver 能解析 file resource。
4. ProducerIndex 能识别 step-produced file output。
5. IRS 能报告 missing file producer。
6. IRS 能报告 kind mismatch。
7. 只生成 `FileSpec` 但没有 producer 时，不能误判 complete。

### 10.8 验收标准

Phase 4 通过条件：

1. `finished_draft` 可以进入 `[DEFINE_FILES:]`。
2. `finished_draft` 的 binding 可追溯到 `rcd_output_s11`。
3. worker output / step output / ProducerIndex / IRS 对 file resource 语义一致。
4. 没有 producer 时产生 diagnostic，而不是假装 complete。

## 11. Phase 5: Normalizer / Assembler / Renderer 对齐

### 11.1 Normalizer

Stage 9.5 多输出聚合不得删除 `FileSpec` 或 binding。

如果 step 原始 outputs 包含 file demand：

1. structured result 可以作为 worker output。
2. file resource 仍保留在 registry。
3. binding 仍指向原 demand。
4. ProducerIndex 必须能通过 structured aggregation 或原 step metadata 判断 file output producer。

### 11.2 Assembler

Worker inputs/outputs 可以暂时保持 `name/required`，但 assembler 或后续 validator 必须通过 resolver 验证该 name 能解析到 variable 或 file。

### 11.3 Renderer

Renderer 不猜测，不修正：

```text
resources.variables -> [DEFINE_VARIABLES:]
resources.files     -> [DEFINE_FILES:]
worker.outputs      -> [OUTPUTS] <REF>name</REF>
```

### 11.4 测试

必须覆盖：

1. file resource 在 multi-output aggregation 后仍存在。
2. final SPL 包含 finished draft file declaration。
3. worker output 引用的 resource 可被 resolver 解析。

## 12. Phase 6: 关闭 legacy hard_facts 主路径

### 12.1 代码改动

1. `StructuralNLAdapter` 默认不再写入 `hard_facts.inputs/outputs`。
2. `_extract_variables()` / `_infer_data_type()` 从 production path 移除或仅保留在 legacy flag 下。
3. Stage 3.5 hard fact recovery 删除或降级为测试/legacy fallback。
4. Stage 6 canonical hard fact merge 删除或降级。
5. provenance 中 adapter `VariableFact` 特例改为 resource contract provenance。

### 12.2 测试

更新旧测试：

1. adapter tests 不再期望 hard facts。
2. provenance tests 改为 demand/binding provenance。
3. Stage 3.5 tests 以 `ResourceContractPlan` 为主。

### 12.3 验收标准

Phase 6 通过条件：

1. 关闭 hard facts 后 demo 仍能生成 input/output contract。
2. `Finished draft` 不再来自 adapter hard fact variable。
3. 删除 hard facts 不造成 Stage 3.5 contract 为空。

## 13. Phase 7: 端到端验收

### 13.1 demo 验收

运行 `examples/usage.py` 或等价 pipeline 后，应满足：

1. `feedback_report.md` 存在。
2. `compile_report.txt` 不作为 MVP human report 生成。
3. `final_spl.txt` 中：
   ```spl
   [DEFINE_FILES:]
       "Finished draft ..." finished_draft < >: text
   [END_FILES]
   ```
4. `final_spl.txt` 中不能把 finished draft 仅作为 text variable materialize。
5. `status_flag` 可暂为 `text`，enum 不作为本次硬门槛。
6. checkpoint 中有 `stage3_2_resource_contract_plan.json`。
7. checkpoint 或 intermediate 中有 scope-aware binding。

### 13.2 diagnostics 验收

1. 缺少 file producer 时，feedback report 应出现 user-facing requirement diagnostic。
2. route refinement corrected 不进入 feedback report。
3. 内部 compiler telemetry 留在 checkpoint。

### 13.3 回归测试

建议至少运行：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/unit/test_input_adapters.py `
  tests/unit/test_resource_contract_planner.py `
  tests/unit/test_resource_contract_stage6.py `
  tests/unit/test_resource_resolver.py `
  tests/unit/test_producer_index.py `
  tests/unit/test_post_normalize_resource_contract_irs.py `
  tests/unit/test_orchestrator_result.py `
  tests/unit/test_feedback_report_renderer.py `
  -q
```

## 14. 审阅清单

后续验收编码成果时，逐项检查：

### Gate 1

1. `ResourceContractPlanner` 是否能在没有 final `output_contract` annotation 时生成 demand。
2. 是否消费 section/list-item structural evidence。
3. 是否保存 checkpoint。
4. 是否不生成 `resource_kind/name/data_type`。

### Gate 2

1. binding 是否包含 `scope_kind/scope_id`。
2. binding 是否包含 `contract_demand_id`。
3. binding 是否包含 source span / section / packet。
4. 多 worker 同名资源是否可区分。

### Gate 3

1. `FileSpec` 是否有 matching binding。
2. resolver 是否能解析 file resource。
3. ProducerIndex 是否支持 file producer。
4. IRS 是否检查 missing producer / kind mismatch。
5. structured aggregation 是否保留 file resource 语义。

### hard_facts 迁移

1. hard facts 是否只作为 fallback 存在。
2. 是否能关闭 fallback 后仍通过 demo。
3. 是否删除 adapter hardcoded type inference 对 production 的影响。

### feedback 边界

1. feedback 只展示 user-facing requirement diagnostics。
2. route refinement telemetry 不进入 feedback。
3. resource materialization gap 有清晰用户可行动建议。
