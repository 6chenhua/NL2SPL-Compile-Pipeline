# Resource Contract Demand View 架构设计

**文档状态：架构方向已确定；Phase A 可开工；Phase B/C 依赖前置决策，见第 22 节。**

---

## 1. 设计结论

当前 `Stage 3.2 ResourceContractPlanner` 不应继续作为独立 planner stage 存在。它当前真正有价值的部分不是"规划"，而是为资源合约需求提供一个稳定的 source-demand ledger：

- 稳定的 demand identity
- source span / section / packet provenance
- Stage 3.5 worker contract placeholder 的锚点
- Stage 6 resource materialization 的 traceability
- Post-normalize IRS 对 source-demanded resource contract 的检查入口

因此，目标架构不是保留 `ResourceContractPlanner`，也不是删除 resource contract demand artifact，而是引入一个更清晰的逻辑概念：

```text
ResourceContractDemandView
```

它是 resolved route annotations 到 resource contract source demands 的纯投影视图，不是 semantic planner，不是 LLM stage，也不是 resource materializer。

**DemandView 是构建边界的变更，不一定是数据模型的重写。** 现有 `ResourceContractDemandIR` 如果能携带 `requiredness` 三值、`annotation_trace`、`view_status`，可以直接复用；如果字段不足，才新增字段或 wrapper，不应为名称差异重建平行类型。

---

## 2. 背景问题

当前 Stage 3.2 混合了三类职责：

1. **Demand identity**：为 source demand 分配稳定 `demand_id`。
2. **Evidence aggregation**：保留 span、section、packet provenance。
3. **Semantic fallback**：根据 section title（如 `Inputs for each run` / `Required Outputs`）静默生成 input/output demand。

前两类职责是必要的。第三类职责不应在默认生产路径存在，因为它把语义判断从 Stage 2 偷偷迁移到了 Stage 3.2，并且会掩盖 Stage 2 annotation 缺失或失败。

删除 Stage 3.2 不等于消灭这个问题——如果不做 annotation coverage audit，则 Stage 3.2 的"静默补需求"行为会被替换成 DemandView 的"静默少需求"行为。两者都是 silent failure，只是方向相反。本设计通过独立的 coverage validator 解决这一点。

资源名、`resource_kind`、`data_type`、`path`、description 等 materialized resource 字段属于 Stage 6，不属于 DemandView，也不属于 Stage 3.2。

---

## 3. 设计目标

Resource Contract Demand View 的目标是：

1. 用稳定的 demand identity 表达 source-demanded resource contract。
2. 保留 source evidence 和 provenance，供 Stage 6、IRS、报告和调试使用。
3. 让 Stage 3.5 能在 resource 尚未 materialize 前保留 worker contract placeholder。
4. 让 Stage 6 materialized resource 能绑定回原始 source demand。
5. 让 Post-normalize IRS 能检查 source demand 是否被满足。
6. 删除默认路径中的 header/title semantic fallback。
7. 明确语义判断只来自 Stage 2 confirmed annotations，而不是后续 stage 的标题或文本规则。
8. 通过独立 coverage validator 检测 Stage 2 annotation 缺失，防止 silent demand loss。
9. 把 `requiredness` 三值语义真正穿透到 Stage 6 和 IRS，不在 DemandView 层折叠为 bool。

本设计面向结构化 NL 路径。Generic NL path 暂不纳入当前迁移范围。

---

## 4. 非目标

ResourceContractDemandView 不承担以下职责：

1. 不解析 raw NL。
2. 不调用 LLM。
3. 不根据 section title 推断 input/output。
4. 不根据 evidence text 推断 required/optional 或 requiredness。
5. 不决定 resource name。
6. 不决定 `resource_kind`。
7. 不决定 `data_type`。
8. 不生成 `VariableSpec`、`FileSpec`、`APISpec`、`TypeSpec`。
9. 不补全 worker contract。
10. 不生成 SPL。
11. 不替代 Stage 6 validator。
12. 不替代 Post-normalize IRS。
13. 不根据 structural canonical facts 生成 `ResourceContractDemandIR`（此为 coverage validator 边界，见第 7 节）。

---

## 5. 架构位置

最终架构中的职责链路应为：

```text
Stage 2 FieldRouter
  -> produces confirmed RouteAnnotation
  -> resource contract semantics live here

Stage 3 AmbiguityResolver
  -> resolves span split / annotation propagation
  -> produces resolved_spans / resolved_routes

ResourceContractDemandViewBuilder
  -> input: resolved_spans, resolved_routes
  -> projects resolved resource contract annotations into source-demanded demands
  -> no semantic inference, no CanonicalCompileInput dependency

ResourceContractAnnotationCoverageValidator  [独立组件，非 DemandView 内部]
  -> input: canonical_input, resolved_spans, resolved_routes, demand_view
  -> checks Stage 2 annotation coverage against structural facts
  -> emits coverage diagnostics only, does not generate demands

ResourceContractDemandViewResult  [orchestrator 汇总点]
  -> demand_view
  -> view_diagnostics (from builder)
  -> coverage_diagnostics (from coverage validator)
  -> coverage_summary

Stage 3.5 WorkerBoundaryPlanner
  -> consumes demand_view
  -> records worker contract placeholders with contract_demand_id + requiredness

Stage 6 ResourceExtractor
  -> consumes demand_view
  -> receives requiredness tri-state, not collapsed bool
  -> materializes name / resource_kind / data_type / path / description
  -> emits ResourceContractBindingIR

Post-normalize IRS
  -> consumes demand_view + bindings + normalized worker/resource IR
  -> checks materialization, registry consistency, output producer
```

**DemandView builder 不接收 `CanonicalCompileInput`。** 接收 canonical input 是 coverage validator 的职责，二者签名必须区分，不能合并。

DemandView 的构建时机应在 Stage 3 之后。原因是 Stage 3 可能拆分 span、传播 annotation 或修正 ambiguity。Demand identity 应绑定到 resolved spans 和 resolved annotations，而不是绑定到 Stage 2 的未稳定中间状态。

ResourceContractDemandView 是 compiler projection utility，不是 pipeline stage。它不应放入 `pipeline/stages` 的架构边界中，也不应获得独立 stage 编号。推荐模块边界：

```text
compiler/resource_contract_demand_view/
  builder.py          # DemandViewBuilder: spans + routes -> demands
  coverage_validator.py  # CoverageValidator: canonical_input + view -> diagnostics
  result.py           # ResourceContractDemandViewResult
  projector.py        # ViewDiagnosticProjector: view diagnostics -> CompileDiagnostic
```

---

## 6. Stage 2 的语义契约

Stage 2 是 resource contract semantics 的唯一默认来源。

对于 resource contract annotation，Stage 2 应表达以下语义：

- 该 span 是否表达 resource contract demand。
- 该 demand 是 input 还是 output。
- 该 demand 的 requiredness 是否明确（三值：required / optional / unspecified）。
- 该 annotation 是否 non-executable。
- 该 annotation 的 source section / packet / span provenance。

推荐的逻辑字段包括：

```text
semantic_role:
  input_contract | output_contract

route_family:
  resource_contract

construct_target:
  RESOURCE_CONTRACT

slot_target:
  input | output

executable:
  false

metadata:
  direction: input | output
  requiredness: required | optional | unspecified
  contract_source: stage2_confirmed
```

这里的 `metadata` 是设计语义，不要求具体实现必须采用同名字段。但设计原则是：direction 和 requiredness 必须是 Stage 2 明确输出的 structured semantics，不能由 DemandView 从文本或标题推断。

对于结构化 NL，Structural Adapter 或 Stage 2 可以基于显式结构化 schema 信息形成 confirmed annotation（如 required/optional section、structured packet type、adapter evidence）。关键边界是：这些语义必须在 Stage 2 annotation contract 中显式落地，DemandView 只能消费结果，不得重新读取 section title 或 evidence text 做语义恢复。

---

## 7. Annotation Coverage Audit

**Coverage audit 是外部独立组件，不是 DemandView builder 内部逻辑。**

设计边界：

```text
ResourceContractDemandViewBuilder:
  input: resolved_spans, resolved_routes
  output: demands + annotation contract diagnostics
  不接收 CanonicalCompileInput
  不用 structural facts 生成 demand

ResourceContractAnnotationCoverageValidator:
  input: canonical_input, resolved_spans, resolved_routes, demand_view
  output: coverage_diagnostics, coverage_summary
  可以读取 CanonicalCompileInput hard facts / structural packets
  只用于检查 Stage 2 是否漏 annotation
  不生成 ResourceContractDemandIR
```

Coverage audit 的工作逻辑：

```text
expected_evidence_refs = canonical_input.hard_facts.inputs + canonical_input.hard_facts.outputs
                       + structural packet refs with resource_contract semantics

for each expected_ref:
  if no matching confirmed annotation in resolved_routes:
    emit: resource_contract_annotation_missing (or coverage variant)
    do NOT generate demand
```

这样做的目的是把两类 silent failure 都变成 visible diagnostic：

- Stage 3.2 旧行为：annotation 缺失时静默生成 demand（header fallback）。
- DemandView 不做 coverage audit 时：annotation 缺失时静默不生成 demand。

两种都是 silent failure，方向相反，同样危险。Coverage audit 让缺失变成可见诊断。

**Coverage validator 明确的边界限制：**

1. 只能读取 structural canonical facts 做 annotation presence check，不能用这些 facts 生成 demand。
2. 产生的 diagnostics 进入 `view_result.coverage_diagnostics`，不直接写入 compile_diagnostics（由 projector 转换，见第 16 节）。
3. Coverage check 对 generic NL 路径不适用，因为 generic NL 没有 hard structured facts 作为 expected refs。

新增 diagnostic kinds（在第 8 节列表之外）：

```text
resource_contract_annotation_missing
resource_contract_annotation_coverage_gap
resource_contract_annotation_unmatched_structural_fact
```

---

## 8. Generic NL 的范围边界

Generic NL path 暂不属于当前迁移目标。

如果未来重新支持 generic NL，它必须先实现与结构化 NL 等价的 Stage 2 resource contract annotation contract，然后才能使用 ResourceContractDemandView。

未来 generic NL 支持不得通过 DemandView fallback 实现。正确边界仍然是：

- Stage 2 LLM/schema/validator 产生 confirmed resource contract annotations；
- DemandView 只消费 confirmed annotations；
- 无 annotation 时不生成 demand；
- 不靠 header fallback 或 keyword fallback 伪造 demand。

Coverage audit 对 generic NL 不适用（无 structural hard facts 作为 expected refs），这不是遗漏，而是范围边界。

---

## 9. DemandView 的逻辑内容

ResourceContractDemandView 是一个不可变的 source-demanded resource contract view。

它至少表达以下逻辑内容：

```text
demands:
  source-demanded resource contract demand 集合

view_diagnostics:
  DemandView 构建期间发现的 annotation contract 问题

warnings:
  非阻断但需要报告的兼容性或观测性信息
```

单个 demand 的逻辑内容包括：

```text
demand identity:
  stable demand_id

direction:
  input | output

requiredness:
  required | optional | unspecified
  [三值，必须保留，不得在 DemandView 层折叠]

required:
  bool | None
  [仅 compatibility projection；见第 12 节规则]

source evidence:
  evidence_text
  source_span_ids
  source_section_id
  source_packet_id
  source_hint_ids (if available)

annotation_trace:
  contributing annotation ids or equivalent stable references

evidence_source:
  stage2_annotation
  compat_section_title (only when compatibility path explicitly invoked)

view_status:
  valid | invalid_direction | invalid_requiredness | invalid_multi_contract | skipped
```

**`requiredness` 是架构主语义字段。`required: bool | None` 是兼容性投影，仅供无法接受三值的旧 consumer 通过 shim 使用，不得成为 production semantic source。**

首批 view diagnostic kinds（稳定命名，禁止实现者自由拼接字符串）：

```text
resource_contract_annotation_missing_direction
resource_contract_annotation_conflicting_direction
resource_contract_annotation_missing_requiredness
resource_contract_annotation_conflicting_requiredness
resource_contract_duplicate_demand_id
resource_contract_invalid_annotation_contract
resource_contract_ambiguous_multi_direction_span
resource_contract_multi_annotation_requires_split
resource_contract_header_fallback_used          [仅限 compatibility path]
resource_contract_annotation_missing            [来自 coverage validator]
resource_contract_annotation_coverage_gap       [来自 coverage validator]
resource_contract_annotation_unmatched_structural_fact  [来自 coverage validator]
```

---

## 10. Demand Identity 规则

Demand identity 必须稳定、可重复、可追踪，并绑定到 resolved evidence。

设计原则：

1. 同一 resolved span 和同一 resource contract direction 应生成同一 demand identity。
2. 多个 annotation 指向同一 demand 时，应合并 provenance，而不是生成重复 demand。
3. Direction 冲突时，不应生成 demand；产生 `resource_contract_annotation_conflicting_direction`。
4. Requiredness 冲突时，不应静默选择其中之一；产生 `resource_contract_annotation_conflicting_requiredness`。
5. 同一 span 同时存在 input 和 output annotation 时，**默认视为冲突，不生成 demand**；仅在满足第 11 节结构化条件之一时才允许生成两个 demand。

Demand identity 不应包含 Stage 6 materialized resource name，因为 name 是 Stage 6 才决定的结果。

推荐 demand_id 格式：

```text
rcd_{direction}_{resolved_span_id}
```

当同一 span 合法拆成两个 demand 时：

```text
rcd_input_{resolved_span_id}
rcd_output_{resolved_span_id}
```

---

## 11. Direction 判定原则

DemandView 只能从结构化 annotation contract 中确认 direction。

可接受的 direction evidence 包括：

- `semantic_role=input_contract`
- `semantic_role=output_contract`
- `slot_target=input`
- `slot_target=output`
- annotation metadata 中明确的 direction

这些来源必须一致。如果多个来源给出冲突方向，DemandView 应产生 `resource_contract_annotation_conflicting_direction`，并且不生成该 demand。

**禁止行为：**

- `semantic_role` 缺失时默认 output。
- `construct_target=RESOURCE_CONTRACT` 时默认 output。
- section title 包含 `required output` 时默认 output。
- evidence text 出现 `input` / `output` 时默认对应 direction。

**同一 span 同时出现 input 和 output annotation：**

默认视为冲突（`resource_contract_ambiguous_multi_direction_span`），不生成 demand。

只有满足以下结构化条件之一时，才允许生成两个不同 demand：

1. Stage 3 已将该 span 拆成不同 resolved child spans。
2. 两个 annotations 分别带有不同的 stable `source_packet_id` 或 `list_item_id`。
3. Structural Adapter 在解析阶段明确标记该 span `contains_multiple_contract_items=true`（注意：只有 Structural Adapter 写入的此字段有效，Stage 2 LLM 写入的同名字段不作为安全判据）。

**LLM-authored `explicit_multi_contract` flag 不能作为合法多 demand 的授权依据。**

---

## 12. Requiredness 判定原则

Requiredness 必须来自 Stage 2 confirmed annotation contract。

可接受状态（三值）：

```text
required    -> required=True
optional    -> required=False
unspecified -> required=None （不允许投影为 True）
```

**禁止行为：**

- output 永远 required。
- input 默认 required。
- evidence text 以 `optional` 开头才 optional。
- section title 决定 requiredness。
- `requiredness=unspecified` 静默投影为 `required=True`。

**`requiredness=unspecified` 的处理规则（硬性约束）：**

```text
requiredness=unspecified:
  required = None                    [不允许为 True 或 False]
  demand 仍可生成（保留 source demand）
  DemandView 必须 emit view diagnostic: resource_contract_annotation_missing_requiredness
  downstream 消费 required 字段时必须能接受 None
  不允许任何 production consumer 把 None 静默当作 True
  Stage 6 context 必须传递三值 requiredness，不得仅传递 bool
  Renderer 不允许因 requiredness=unspecified 输出 REQUIRED
```

如果某个旧 consumer 暂时无法接受 `None`，只能通过显式 legacy shim 处理，且 shim 输出不得成为 production semantic source。

在结构化 NL 路径中，requiredness 可以由 Structural Adapter 或 Stage 2 从显式结构化 schema 中确认（如 required/optional section 或 adapter packet evidence）。但确认结果必须写入 Stage 2 annotation metadata 或等价 structured contract，DemandView 不得重新解析标题或文本来判断 requiredness。

---

## 13. Header Fallback 策略

默认生产路径不应使用 header fallback。

以下行为应退出默认生产路径：

```text
"Inputs for each run"  -> input demand  [删除]
"Required Outputs"     -> output demand [删除]
```

如果为了历史兼容必须保留，应作为显式 compatibility capability：

```text
compat_resource_contract_header_demands
```

兼容路径必须满足：

1. 默认不启用；通过显式 flag 开启（`enable_resource_contract_header_fallback: bool = False`）。
2. 仅用于 migration tests、legacy adapter path 或显式兼容运行。
3. 不覆盖 Stage 2 annotation。
4. 输出中明确标记 `evidence_source=compat_section_title`。
5. 必须产生 `resource_contract_header_fallback_used` diagnostic，不得静默。
6. 报告中明确显示 compatibility inferred。

兼容路径不应被称为 planner，也不应掩盖 Stage 2 annotation 缺失。

---

## 14. Stage 3.5 关系

Stage 3.5 仍然需要消费 DemandView。

原因是 worker boundary 规划发生在 Stage 6 resource materialization 之前。此时系统尚不知道最终 resource name、kind、type，但已经需要表达：

```text
某个 worker 受这个 source-demanded input/output contract 约束
```

因此 Stage 3.5 应只写入 placeholder 语义：

```text
contract_demand_id
direction
requiredness           [三值，不仅是 bool]
required               [bool | None，兼容 projection]
source evidence
```

Stage 3.5 不应决定 name、kind、type。Stage 6 materialize 后，再通过 `contract_demand_id` 回填 resolved worker contract fields。

**Stage 3.5 的 worker contract placeholder 字段也必须支持 `requiredness: ContractRequiredness`，不能只有 `required: bool`。**

---

## 15. Stage 6 关系

Stage 6 是 resource materialization authority。

Stage 6 消费 DemandView 的目的不是重新判断是否存在 demand，而是对每个 source-demanded resource contract 生成 materialized resource model：

```text
name
resource_kind
data_type
path
description
requiredness       [三值，pass-through from DemandView, not re-decided]
required           [bool | None，仅兼容 projection]
binding to demand_id
```

Stage 6 可以使用 LLM，因为 name/resource_kind/data_type/path/description 需要语义理解和命名判断。

**Stage 6 不决定 requiredness。** Stage 6 从 DemandView 接收 `requiredness`，pass-through 到输出 IR，不修改。如果 target IR 仍然强制 `required: bool`，则必须先完成 Schema Impact Audit（见第 22 节）并修改相关 IR 字段类型。

Stage 6 context builder 必须传递三值 requiredness，不得只传 bool：

```json
{
  "demand_id": "rcd_output_s3",
  "direction": "output",
  "requiredness": "unspecified",
  "evidence_text": "..."
}
```

Stage 6 的输入应明确区分：

- Stage 2 confirmed demand（`evidence_source=stage2_annotation`）
- Compatibility inferred demand（`evidence_source=compat_section_title`）
- Unresolved or invalid demand annotation（`view_status=invalid_*`）

---

## 16. Post-normalize IRS 关系

Post-normalize IRS 应消费 DemandView 和 Stage 6 bindings。

IRS 的问题不是"是否应该生成 resource"，而是：

```text
对于这个 source-demanded RESOURCE_CONTRACT_DEMAND，
它的 IRS slots 是否被满足？
```

典型检查包括：

1. **Materialization**：是否有 binding 指向该 demand。
2. **Registry consistency**：binding 指向的 resource 是否存在于 ResourceRegistryIR。
3. **Producer**：`requiredness=required` 的 output demand 是否有 producer。对于 `requiredness=unspecified`，IRS 应产生 warning 而不是 error，并在 feedback report 中标注不确定性。

IRS 不应：

- 从 raw NL 推断 demand。
- 从 section title 生成 demand。
- 修改 DemandView。
- 修改 ResourceRegistryIR。
- 补全 Stage 6 漏掉的 resource。

---

## 17. Diagnostic Runtime Integration

**这是一个硬性 runtime contract，不是"顺手处理"。** DemandView 和 coverage validator 产生的诊断必须进入 `compile_diagnostics` 和 feedback report，否则等同于没有诊断。

**Orchestrator 中间结果存储：**

```python
# Orchestrator run() 中的必要步骤
view = build_resource_contract_demand_view(resolved_spans, resolved_routes)

coverage = validate_resource_contract_annotation_coverage(
    canonical_input, resolved_spans, resolved_routes, view
)

view_result = ResourceContractDemandViewResult(
    view=view,
    diagnostics=view.view_diagnostics + coverage.diagnostics,
    coverage_summary=coverage.summary,
)

intermediate["resource_contract_demand_view"] = view
intermediate["resource_contract_demand_view_payload"] = view.to_payload()
intermediate["resource_contract_view_diagnostics"] = view_result.diagnostics
intermediate["resource_contract_coverage_summary"] = view_result.coverage_summary
```

**Diagnostic 投影（必须存在，不可省略）：**

```python
# ResourceContractViewDiagnosticProjector 必须将 view diagnostics 转换为 CompileDiagnostic
projected_view_diags = ResourceContractViewDiagnosticProjector.project(
    view_result.diagnostics
)
# 投影结果必须合并进 all_diagnostics
all_diagnostics = [..., *projected_view_diags, ...]
```

**进入路径（三处，全部必须）：**

```text
compile_diagnostics:
  包含所有投影后的 view diagnostics 和 coverage diagnostics

feedback_report.md:
  包含 Resource Contract Demand 专属 section，展示：
    confirmed Stage 2 demand
    compatibility inferred demand（如有）
    invalid annotation / coverage gap

intermediate checkpoint:
  resource_contract_demand_view_payload:
    demands
    view_diagnostics
    coverage_summary
    evidence_source per demand
```

**验收门禁：如果 DemandView 检测到 annotation 问题但 feedback_report.md 里没有对应条目，则视为 diagnostic 丢失，不予通过。**

---

## 18. 与 ConstructPlan 的区别

ResourceContractDemandView 不等同于 ConstructPlan。

ExceptionFlow ConstructPlan 需要解决：

- condition 和 handler 是否属于同一个 ExceptionFlow。
- handler 是否只属于 handler，还是也是 process_step。
- condition 和 handler 被分到不同 worker 时的 ownership。
- 多 condition / 多 handler 如何配对。
- 缺 handler 时是否保留 partial skeleton。

Resource contract demand 不需要这些 pairing 和 skeleton 策略。一个 confirmed input/output contract annotation 通常直接对应一个 source-demanded resource contract demand。

因此它不需要独立 planner stage，也不应复用 ConstructPlanner 的复杂模型。

---

## 19. 架构决策

最终架构决策如下：

1. 删除 Stage 3.2 作为默认 production planner stage 的设计地位。
2. 保留 resource contract demand artifact，以 DemandView 表达。
3. DemandView 在 Stage 3 resolved routes 之后构建。
4. DemandView builder 只接收 resolved_spans + resolved_routes，不接收 CanonicalCompileInput。
5. Direction 和 requiredness 必须来自 Stage 2 structured annotation contract。
6. Requiredness 以三值表达，`required: bool | None`，`unspecified` 不投影为 `True`。
7. Stage 3.5、Stage 6、Post-normalize IRS 共享同一个 DemandView。
8. Annotation coverage audit 由独立 ResourceContractAnnotationCoverageValidator 负责，不放入 DemandView builder。
9. Header fallback 不进入默认 production path。
10. Generic NL 不属于当前迁移范围。
11. Stage 6 继续作为 resource name / kind / type / path 的唯一 materialization authority，pass-through requiredness，不决定 requiredness。
12. IRS 继续作为 construct-level satisfaction analysis authority，不生成 demand，不补全 resource。
13. DemandView view diagnostics 和 coverage diagnostics 必须通过 projector 进入 compile_diagnostics、feedback_report、checkpoint。
14. DemandView 优先复用现有 `ResourceContractDemandIR`，必要时新增字段，不重建平行类型。

---

## 20. ResourceContract IR Schema Impact Audit（前置要求）

**在修改 `ResourceContractDemandIR`、`ResourceContractFieldIR`、`ResourceContractBindingIR` 任何字段之前，必须先完成 consumer impact audit。** 这是 Phase B 开工的前置条件，不是实现过程中"顺手检查"的内容。

需要审计的 consumer 清单（最低覆盖范围）：

```text
1.  orchestrator.py — intermediate 序列化与 checkpoint 写入
2.  stage3_5_worker_boundary_planner — placeholder 生成逻辑
3.  stage6_resource_extractor — context builder、prompt 构建
4.  stage6_resource_extractor — parser / worker_scoped binding
5.  stage6_resource_extractor — backfill logic
6.  compiler/irs/checkers/post_normalize.py — demand-satisfaction check
7.  compiler/producer_index.py — required output producer check
8.  stage10_worker_assembler — input/output rendering
9.  stage11_spl_renderer — REQUIRED / OPTIONAL keyword rendering
10. compiler/feedback_report_renderer.py — resource contract section
11. 所有 tests 中使用 ResourceContractDemandIR / FieldIR / BindingIR 的 fixture 和 assertion
12. checkpoint payload 的 to_payload() 序列化和反序列化
```

**每个读取 `required: bool` 的 consumer，必须迁移到 `requiredness` 三值，或通过显式 legacy adapter shim 包裹，并标注为 legacy。**

**没有 production consumer 可以在 audit 未完成前静默把 `requiredness=unspecified` 当作 `required=True` 使用。**

---

## 21. Migration Compatibility

删除 Stage 3.2 的含义是：从默认 orchestrator production path 移除独立 `ResourceContractPlanner` stage。

这不要求第一步物理删除所有旧类型。为了迁移稳定性，旧类型可以作为过渡 shim 保留：

```text
ResourceContractPlanIR      [可作为 compatibility container shim]
ResourceContractDemandIR    [优先复用，必要时新增字段]
ResourceContractPlanner     [废弃，仅限 migration tests]
```

边界必须明确：

1. Default orchestrator path 不再调用 `ResourceContractPlanner`。
2. 新 production code 不应继续依赖 `ResourceContractPlanner`。
3. 旧 `ResourceContractPlanIR` 可以临时作为 adapter shim 或测试兼容层，但不得重新引入 header fallback。
4. Shim 必须显式标注为 `# MIGRATION SHIM: remove after Phase B complete`。
5. 最终 source of truth 迁移到 ResourceContractDemandView。

---

## 22. Implementation-Ready 判断与迁移分阶段

当前文档状态：**架构方向已确定，Phase A 可以开工，Phase B 和 C 需要先完成各自前置决策。**

### Phase A：无 schema 破坏的准备工作（可现在开工）

```text
A1. 新增 ResourceContractDemandViewBuilder
    - 只消费 resolved_spans + resolved_routes
    - 实现 direction conflict / missing direction diagnostics
    - 不使用 header fallback
    - 并行生成 payload，暂不替换 Stage 6 / IRS 消费路径

A2. 新增 annotation direction conflict / missing direction 测试

A3. 确认不使用 header fallback 的回归测试

A4. 确认 DemandView happy path 与旧 Stage 3.2 输出在 annotation-derived demands 上等价
```

### Phase B：IR schema audit 后再集成（需先完成第 20 节 impact audit）

```text
B1. 完成 ResourceContract*IR consumer impact audit（第 20 节清单）
B2. 引入 requiredness tri-state schema
    - ResourceContractDemandIR: add requiredness, required -> bool | None
    - ResourceContractFieldIR: add requiredness, required -> bool | None
    - ResourceContractBindingIR: add requiredness
B3. 修改 Stage 6 prompt / output schema / parser / validator
    - context builder 传递 requiredness tri-state
    - 不允许 Stage 6 修改 requiredness
B4. 修改 Stage 3.5 placeholder 字段
B5. 修改 Post-normalize IRS producer/materialization checks
    - unspecified output demand 产生 warning，不产生 error
B6. 修改 renderer / feedback report
    - REQUIRED 只来自 requiredness=required，不来自 unspecified
B7. 移除 Stage 3.2 default orchestrator path
B8. 新增 ResourceContractViewDiagnosticProjector
B9. 接入 orchestrator 的 intermediate 存储和 diagnostic 汇聚路径
```

### Phase C：Coverage Validator（可与 Phase A 并行设计，Phase B 前后均可实现）

```text
C1. 实现 ResourceContractAnnotationCoverageValidator
    - input: canonical_input + resolved_spans + resolved_routes + demand_view
    - output: coverage_diagnostics, coverage_summary
    - 只产生 diagnostics，不生成 demands

C2. 接入 orchestrator intermediate 和 diagnostic 路径

C3. 用结构化 NL hard facts 测试 Stage 2 annotation coverage gap 场景

C4. 验收：Stage 2 annotation 缺失时，feedback_report.md 有对应 coverage gap 条目
```

---

## 23. 成功标准

该设计成功时，系统应满足：

1. 没有独立 Stage 3.2 planner 作为默认生产阶段。
2. 不再依赖 `Inputs for each run` / `Required Outputs` 标题静默生成 demands。
3. Resource contract demand 的存在来自 Stage 2 confirmed annotation。
4. DemandView 的 demand identity 稳定且可追溯。
5. Stage 3.5 能保留 worker contract placeholder，包含 `requiredness` 三值。
6. Stage 6 能 materialize resource 并绑定回 demand，pass-through requiredness 而不重新判断。
7. Post-normalize IRS 能发现 missing materialization、registry mismatch、missing producer。
8. `requiredness=unspecified` 不会在任何 production path 静默投影为 `required=True` 并驱动 REQUIRED 渲染。
9. Stage 2 annotation 缺失时，系统产生 visible diagnostic，而不是静默少需求。
10. 结构化 NL 使用 Stage 2 resource contract annotation contract；Generic NL 只有在未来实现同等 annotation contract 后才可接入该设计。
11. 没有新的 rule-based semantic fallback 被引入。
12. `compile_diagnostics` 包含 DemandView 和 coverage validator 的所有诊断；不存在诊断被静默丢弃的情况。
13. `feedback_report.md` 能区分：confirmed demand、compatibility inferred demand、invalid annotation / coverage gap。
14. Intermediate checkpoint 包含 `resource_contract_demand_view_payload`，内含 demands、view_diagnostics、coverage_summary、evidence_source。

---

## 24. 核心原则

最终设计必须遵守以下原则：

```text
Semantic decision belongs to Stage 2.
Demand identity belongs to DemandView.
Annotation coverage check belongs to CoverageValidator.
Resource materialization belongs to Stage 6.
Requiredness is tri-state; it must not be collapsed at DemandView boundary.
Construct satisfaction belongs to IRS.
Diagnostic visibility belongs to projector + orchestrator.
Rendering belongs to renderer.
No hidden fallback.
No downstream guessing.
No silent demand loss.
No rule-based semantic recovery unless explicitly approved.
```
