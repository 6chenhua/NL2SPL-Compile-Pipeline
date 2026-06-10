# Resource Contract Demand View 实施计划

本文档严格基于 `resource_contract_demand_view_design_final.md` 制定。实施目标是移除 `Stage 3.2 ResourceContractPlanner` 作为默认 production planner stage 的设计地位，同时保留并强化 resource contract demand artifact 的 identity / provenance / downstream anchor 作用。

本计划只覆盖结构化 NL 路径。Generic NL path 暂不属于当前迁移范围。

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
Stage 2 FieldRouter
  -> confirmed resource contract RouteAnnotation

Stage 3 AmbiguityResolver
  -> resolved_spans / resolved_routes

ResourceContractDemandViewBuilder
  -> pure projection from resolved annotations
  -> no CanonicalCompileInput
  -> no title/text semantic inference

ResourceContractAnnotationCoverageValidator
  -> structural coverage audit only
  -> diagnostics only
  -> no demand generation

Stage 3.5 WorkerBoundaryPlanner
  -> consumes DemandView
  -> creates worker contract placeholders

Stage 6 ResourceExtractor
  -> consumes DemandView
  -> materializes name / resource_kind / data_type / path / description

Post-normalize IRS
  -> consumes DemandView + bindings
  -> checks materialization / registry / producer
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. 不把 `ResourceContractDemandViewBuilder` 放进 `pipeline/stages`。
2. 不给 DemandView 新增 stage 编号。
3. DemandView builder 不接收 `CanonicalCompileInput`。
4. DemandView builder 不读 section title 进行语义判断。
5. DemandView builder 不读 evidence text 推断 direction 或 requiredness。
6. DemandView builder 不调用 LLM。
7. DemandView builder 不生成 resource name、resource_kind、data_type、path。
8. Coverage validator 只能产生 diagnostics，不能生成 demands。
9. Header fallback 不进入默认 production path。
10. `requiredness=unspecified` 不得在 production path 静默投影为 `required=True`。
11. Stage 6 是 resource materialization authority，但不是 requiredness authority。
12. Post-normalize IRS 只检查 satisfaction，不生成 demand，不补全 resource。
13. 所有 DemandView/view coverage diagnostics 必须进入 `compile_diagnostics`、feedback report 和 intermediate checkpoint。
14. 不新增 generic NL 支持任务。

---

## 3. LLM / Rule-based 决策约束

本计划中默认不允许新增任何 rule-based semantic fallback。

允许的确定性逻辑仅限：

- 从已存在的 structured `RouteAnnotation` 字段读取 direction / requiredness。
- 对多个 structured fields 做一致性校验。
- 根据 resolved span id / direction 生成 stable demand id。
- Coverage validator 对 structural canonical facts 做 annotation presence check。

以下行为必须在实施前向用户确认：

1. 修改 Stage 2 prompt/schema，让 LLM 输出新的 resource contract annotation 字段。
2. 在 Structural Adapter 或 Stage 2 中基于结构化 section schema 生成 confirmed annotation。
3. 保留或新增任何 runtime header fallback。
4. 使用关键词、标题、文本前缀推断 direction / requiredness / resource kind。
5. 让 Stage 6 用 LLM 重新判断 requiredness。

如果实现中出现“为了兼容先用规则兜底”的倾向，应停止并提交设计确认，不允许直接编码。

---

## 4. Phase A：DemandView 并行引入（无 schema 破坏）

### 4.1 目标

引入 `ResourceContractDemandView` 的基础模型、builder、payload 和基础 diagnostics。该阶段不替换 Stage 3.5 / Stage 6 / IRS 的生产消费路径，不修改 requiredness schema，不移除 Stage 3.2 default call。

Phase A 的核心价值是证明：annotation-derived resource contract demands 可以由独立 compiler projection utility 生成，并且不会复活 header fallback。

当前真实 Stage 2 尚未提供完整 `requiredness` contract。因此 Phase A 的 valid-demand 测试只能使用人工构造的 confirmed `RouteAnnotation`，不得声称真实结构化 NL Stage 2 输出已经能完整驱动 DemandView。真实结构化 NL happy path 是 Phase B2 之后的验收范围。

### 4.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/resource_contract_demand_view/
  __init__.py
  model.py
  builder.py
  diagnostics.py
  payload.py
  projector.py

tests/unit/compiler/resource_contract_demand_view/
```

Phase A 不应修改既有 ResourceContract IR schema。若需要表达 DemandView 专用字段，应在 `compiler/resource_contract_demand_view` 下定义临时 view model；Phase B0/B1 完成后再决定是否合并进既有 IR。

### 4.3 禁止改动

Phase A 禁止修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage3_2_resource_contract_planner/**
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/**
src/nl2spl/pipeline/stages/stage6_resource_extractor/**
src/nl2spl/compiler/irs/checkers/post_normalize.py
src/nl2spl/compiler/producer_index.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/**
prompts/**
examples/**
output/**
```

### 4.4 设计要求

DemandView builder 输入必须是：

```text
resolved_spans
resolved_routes
```

不得包含：

```text
canonical_input
raw_text
section title inference
header fallback
LLM client
```

DemandView 应表达：

```text
demands
view_diagnostics
warnings
to_payload()
```

首批 diagnostics 必须使用设计文档中的稳定 kind：

```text
resource_contract_annotation_missing_direction
resource_contract_annotation_conflicting_direction
resource_contract_annotation_missing_requiredness
resource_contract_annotation_conflicting_requiredness
resource_contract_duplicate_demand_id
resource_contract_invalid_annotation_contract
resource_contract_ambiguous_multi_direction_span
resource_contract_multi_annotation_requires_split
```

### 4.5 测试计划

新增单元测试必须覆盖：

1. `input_contract` annotation 生成 input demand。
2. `output_contract` annotation 生成 output demand。
3. demand id 稳定，例如 `rcd_input_s1` / `rcd_output_s2`。
4. provenance 保留：span / section / packet / hint ids。
5. builder 不接收或不使用 `CanonicalCompileInput`。
6. `construct_target=RESOURCE_CONTRACT` 但 direction 缺失时不默认 output。
7. role/slot/metadata direction 冲突时不生成 demand。
8. requiredness 缺失时产生 diagnostic。
9. 同 span input+output 默认冲突。
10. 合法多 demand 只在 split span 或不同 stable packet/list item 条件下允许。
11. header title 不会生成 demand。
12. evidence text 不会决定 direction 或 requiredness。
13. payload deterministic。
14. diagnostics deterministic。
15. ViewDiagnosticProjector 可将 view diagnostics 投影为 `CompileDiagnostic`，但 Phase A 不接入 orchestrator。

### 4.6 验收标准

Phase A 通过条件：

1. DemandView builder 存在于 `compiler/resource_contract_demand_view`，不是 pipeline stage。
2. Builder 不依赖 `CanonicalCompileInput`。
3. Builder 不调用 LLM。
4. Builder 不根据 title/text 生成 demand。
5. Annotation-derived happy path demand 与旧 Stage 3.2 annotation-derived subset 在 demand identity、direction、provenance、evidence_text 上等价；不得要求 requiredness 与旧 Stage 3.2 的 bool `required` 规则等价。
6. Header fallback 不出现在 DemandView builder。
7. 所有 Phase A 单测通过。
8. 全量单测通过。
9. 无新增 skip / xfail。
10. Projector 单测覆盖所有 Phase A view diagnostic kinds。

### 4.7 PM 审核清单

审核时必须检查：

1. 是否有任何 `canonical_input` 参数进入 DemandView builder。
2. 是否有 `"Inputs for each run"` / `"Required Outputs"` 字符串出现在 DemandView builder。
3. 是否有 `optional` 文本前缀判断。
4. 是否有 `construct_target == "RESOURCE_CONTRACT"` 默认 output。
5. 是否有 generic NL 相关实现。
6. 是否有未列入设计的 diagnostic kind。
7. 是否用真实 Stage 2 输出伪装 Phase A valid-demand happy path。
8. 是否在 Phase A 修改了 `resource_contract_ir.py` schema。
9. Projector 是否只做 diagnostic projection，没有改变 DemandView 或生成 demands。

---

## 5. Decision Gate：Stage 2 Requiredness Contract 方案确认

### 5.1 目标

在进入 schema audit 和 requiredness 三值迁移前，必须确认 Stage 2 如何产生 `direction` 和 `requiredness`。这是后续 B1/B2/B3/B4 的共同前置决策。

当前代码尚未提供稳定的一等 `requiredness` annotation contract。Phase A 可以用 synthetic confirmed annotations 验证 DemandView builder，但真实结构化 NL 路径必须在本决策点明确 requiredness 来源。

### 5.2 可选方案

允许提交但必须评审确认的方案包括：

```text
方案 A：Stage 2 adapter-guided LLM schema 输出 requiredness
方案 B：RouteAnnotation 新增 requiredness 字段，Stage 2 prompt/schema 同步输出
方案 C：Structural Adapter / Stage 2 基于显式结构化 schema 生成 requiredness annotation metadata
```

在结构化 NL 专用前提下，优先考虑方案 C 或 C+B 的组合。无论采用哪种方案，都不得在 DemandView 层根据标题、关键词或 evidence text 兜底推断 requiredness。

### 5.3 必须明确的问题

方案确认文档必须回答：

1. `requiredness` 存放在 `RouteAnnotation` 一等字段，还是 `metadata`。
2. `direction` 存放在 `slot_target`、metadata，还是两者一致性校验。
3. `requiredness=unspecified` 如何由 Stage 2 表达。
4. Stage 2 annotation 缺 requiredness 时是否允许生成 demand。
5. Structural Adapter / Stage 2 是否会使用 required/optional section schema。
6. 是否需要修改 prompt/schema；若需要，必须单独确认。
7. DemandView Phase A fixtures 是否与最终 annotation shape 一致；不一致时应更新 fixtures。

### 5.4 验收标准

该决策门禁通过条件：

1. requiredness 来源明确。
2. direction 来源明确。
3. annotation shape 明确。
4. 不依赖 DemandView fallback。
5. 不引入未确认 rule-based semantic recovery。
6. PM 明确批准后方可进入 B0/B1/B2。

---

## 6. Phase B0：ResourceContract IR Schema Impact Audit

### 6.1 目标

在修改 `ResourceContractDemandIR`、`ResourceContractFieldIR`、`ResourceContractBindingIR`、`ContractFieldIR` 以及 handoff binding required 字段前，完成 consumer impact audit。该阶段以审计测试和文档化清单为交付物，不做 schema 破坏。

Phase B0 还必须覆盖 downstream worker/rendering 链路，因为 resource contract requiredness 会通过 worker contract placeholder 继续传播到 `WorkerIR` 和 SPL renderer。仅审计 ResourceContract IR 不足以保证 `requiredness=unspecified` 不被折叠。

### 6.2 可编辑范围

允许新增：

```text
tests/unit/compiler/resource_contract_demand_view/test_schema_impact_audit.py
docs/implementation/resource-contract-demand-view/resource_contract_schema_impact_audit.md
```

允许读取但不应修改生产代码。

### 6.3 必须审计的 consumer

最低清单：

```text
orchestrator.py
stage3_5_worker_boundary_planner
stage6_resource_extractor/context_builder.py
stage6_resource_extractor/worker_scoped.py
compiler/irs/checkers/post_normalize.py
compiler/producer_index.py
stage10_worker_assembler
stage11_spl_renderer
worker_ir.WorkerInput / WorkerOutput
feedback report renderer
ResourceContract*IR fixtures in tests
WorkerPlanIR.ContractFieldIR fixtures in tests
InputBindingIR / OutputBindingIR required semantics
checkpoint payload serialization
```

### 6.4 测试计划

新增审计测试应锁定：

1. 所有读取 `required` 的生产文件清单。
2. 所有构造 `ResourceContractDemandIR` 的位置。
3. 所有构造 `ResourceContractFieldIR` 的位置。
4. 所有构造 `ResourceContractBindingIR` 的位置。
5. 所有构造 `ContractFieldIR` 的位置。
6. 所有读取 `InputBindingIR.required` / `OutputBindingIR.required` 的位置。
7. Stage 3.5 placeholder 当前依赖 bool required。
8. Stage 6 prompt 当前传递 bool required。
9. Post-normalize IRS 当前 producer check 依赖 bool required。
10. Renderer 是否根据 required 输出 REQUIRED / OPTIONAL。
11. 所有使用 `if field.required` / `if demand.required` truthiness 的位置。
12. `WorkerInput.required` / `WorkerOutput.required` 的构造、传递、渲染路径。

### 6.5 验收标准

Phase B0 通过条件：

1. 审计文档列出所有 consumer 和迁移策略。
2. 审计测试能防止遗漏新增 consumer。
3. 未修改 schema。
4. 未修改 production 行为。
5. 全量单测通过。

### 6.6 PM 审核清单

审核时必须确认：

1. 审计清单不是手写猜测，测试确实扫描或覆盖代码路径。
2. 没有直接开始改 `required` 类型。
3. 没有把 `unspecified` 投影为 True。

---

## 7. Phase B1：Requiredness 三值 Schema 引入

### 7.1 目标

把 `requiredness` 三值语义引入 ResourceContract 相关 IR、worker contract placeholder IR、assembled WorkerIR input/output，并保证 `required: bool | None` 只是兼容投影，不再作为唯一语义来源。

### 7.2 可编辑范围

允许修改：

```text
src/nl2spl/ir/resource_contract_ir.py
src/nl2spl/ir/worker_plan_ir.py
src/nl2spl/ir/worker_ir.py
src/nl2spl/pipeline/stages/stage10_worker_assembler/**
src/nl2spl/pipeline/stages/stage11_spl_renderer/**
tests/unit/**/*
```

允许为兼容新增 shim：

```text
src/nl2spl/compiler/resource_contract_demand_view/compat.py
```

### 7.3 禁止改动

本阶段禁止修改：

```text
orchestrator default path
Stage 3.2 default call
Stage 6 prompt
Post-normalize IRS behavior
```

Stage 11 renderer 文件在本阶段允许修改，但修改范围只限于 schema propagation 和 `required=None` truthiness 防护；不得改变 SPL construct rendering semantics。

### 7.4 设计要求

语义必须遵守：

```text
requiredness=required    -> required=True
requiredness=optional    -> required=False
requiredness=unspecified -> required=None
```

禁止：

```text
unspecified -> True
unspecified -> False
```

除非显式 legacy shim，并且 shim 不得成为 production semantic source。

### 7.5 测试计划

新增/修改测试覆盖：

1. `ResourceContractDemandIR.requiredness` 三值。
2. `ResourceContractFieldIR.requiredness` 三值。
3. `ResourceContractBindingIR.requiredness` 三值。
4. `ContractFieldIR.requiredness` 三值。
5. `WorkerInput.requiredness` / `WorkerOutput.requiredness` 三值。
6. Stage 10 assembler 传递 requiredness，不折叠为 bool。
7. Stage 11 renderer 对 `required=None` / `requiredness=unspecified` 显式分支，不通过 truthiness 渲染为 OPTIONAL。
8. `InputBindingIR` / `OutputBindingIR` required semantics 的迁移策略被测试锁定，或明确保持 bool 并说明不承载 source-demand requiredness。
9. `to_payload()` 保留 requiredness。
10. `required=None` 可序列化。
11. legacy fixture 通过 shim 兼容，但标记为 migration shim。
12. `unspecified` 不被默认投影为 True。

### 7.6 验收标准

Phase B1 通过条件：

1. ResourceContract IR、worker contract placeholder IR、WorkerIR input/output 均支持 requiredness。
2. `requiredness=unspecified` 对应 `required=None`。
3. payload 中可见 requiredness。
4. 旧测试通过或通过明确 migration shim 通过。
5. 无 production 逻辑把 unspecified 当 True。
6. Renderer 不会把 `required=None` 静默渲染为 OPTIONAL。
7. 全量单测通过。

---

## 8. Phase B2：Stage 2 Structural Resource Contract Annotation Contract

### 8.1 目标

确保结构化 NL 路径在 Stage 2 后产生 confirmed resource contract annotations，携带 direction、requiredness、provenance。

### 8.2 LLM / Rule-based 确认要求

本阶段涉及 Stage 2 语义契约，实施前必须确认具体方案：

1. 如果通过 Stage 2 adapter-guided LLM prompt/schema 输出 annotation，必须先提交 prompt/schema 设计。
2. 如果通过 Structural Adapter / Stage 2 deterministic structural schema 生成 annotation，必须先提交 schema mapping 设计。
3. 不允许直接用 header keyword fallback。

在结构化 NL 专用前提下，优先考虑显式 structural schema mapping，而不是先扩大 LLM prompt：例如 `runtime_input` / `required_output` packet 或 hard fact 中已有 required 信息时，由 Stage 2 annotation normalization 写入 `direction` 和 `requiredness`。但该 mapping 必须在开工前作为方案提交确认；不得在实现中临时加入标题/关键词兜底。

### 8.3 可编辑范围

在确认方案后允许修改：

```text
src/nl2spl/pipeline/stages/stage2_field_router.py
src/nl2spl/pipeline/stages/stage2_field_router_prompt.py
prompts/stage2_adapter_guided_system.txt
src/nl2spl/adapters/structural_nl.py
tests/unit/test_adapter_guided_fieldroute_refinement.py
```

实际可改文件取决于已确认方案。

### 8.4 禁止事项

禁止：

1. DemandView builder 补 annotation。
2. Stage 3.2 补 annotation。
3. Stage 6 补 annotation。
4. 根据 title/text 在 DemandView 层推断。
5. 静默生成 missing requiredness。

### 8.5 测试计划

测试覆盖：

1. 结构化 required input list item -> `input_contract` annotation。
2. 结构化 required output list item -> `output_contract` annotation。
3. optional section / explicit optional schema -> `requiredness=optional`。
4. unspecified schema -> `requiredness=unspecified`。
5. annotation 包含 source span/section/packet provenance。
6. annotation `executable=False`。
7. no generic NL scope。
8. Stage 2 diagnostics 对冲突 annotation 可见。

### 8.6 验收标准

Phase B2 通过条件：

1. 结构化 NL resource contracts 在 Stage 2 后形成 confirmed annotations。
2. Annotation direction 和 requiredness 明确。
3. Annotation provenance 完整。
4. 无 DemandView fallback。
5. 全量单测通过。

---

## 9. Phase B3：Stage 3.5 切换到 DemandView

### 9.1 目标

Stage 3.5 从 DemandView 生成 worker contract placeholder，替代从 `ResourceContractPlanIR.demands` 生成 placeholder。

当前旧转换层 `_resource_contract_demand_contracts(resource_contract_plan)` 必须被显式替换为 DemandView 路径，例如 `_build_contract_fields_from_demand_view(...)`。旧方法如需保留，只能作为标注清楚的 migration shim，不能与新方法在默认路径静默共存。

### 9.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/**
tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py
tests/unit/compiler/resource_contract_demand_view/**
```

### 9.3 禁止事项

禁止：

1. Stage 3.5 决定 resource name。
2. Stage 3.5 决定 resource_kind。
3. Stage 3.5 决定 data_type。
4. Stage 3.5 修改 requiredness。
5. Stage 3.5 从 section title 生成 demand。
6. 默认路径继续调用 `_resource_contract_demand_contracts(resource_contract_plan)`。
7. 旧 `ResourceContractPlanIR` 路径和 DemandView 路径同时静默参与 placeholder 生成。

### 9.4 测试计划

测试覆盖：

1. DemandView input demand -> worker input placeholder。
2. DemandView output demand -> worker output placeholder。
3. Placeholder 保留 `contract_demand_id`。
4. Placeholder 保留 requiredness 三值。
5. Placeholder `required=None` 时不强制 True。
6. Placeholder 保留 source provenance。
7. 无 DemandView 时旧路径兼容按迁移策略处理。
8. 默认路径调用 `_build_contract_fields_from_demand_view(...)` 或等价新方法。
9. 旧 `_resource_contract_demand_contracts(...)` 若保留，必须带 `MIGRATION SHIM` 标记，并且默认路径测试证明不调用。

### 9.5 验收标准

Phase B3 通过条件：

1. Stage 3.5 消费 DemandView。
2. Worker contract placeholder 包含 contract_demand_id 和 requiredness。
3. Stage 3.5 不做 materialization。
4. 默认路径不调用旧 `ResourceContractPlanIR` placeholder 转换方法。
5. 全量单测通过。

---

## 10. Phase B4：Stage 6 切换到 DemandView

### 10.1 目标

Stage 6 从 DemandView 构建 resource contract context，materialize resource，并 pass-through requiredness。

### 10.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/context_builder.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py
tests/unit/test_resource_contract_stage6.py
```

Phase B4 开工前必须提交并确认 Stage 6 prompt/schema 设计。该设计至少要说明：

```text
1. Stage 6 context 如何呈现 requiredness 三值。
2. Prompt 如何要求 LLM pass-through requiredness，而不是重新判断。
3. LLM output schema 如何允许 requiredness=required|optional|unspecified。
4. Parser 如何拒绝或诊断缺失/非法 requiredness。
5. Binding / field IR 如何保留 requiredness。
```

这不是“如需才确认”的事项；Stage 6 切换到 DemandView 必然涉及 prompt/context/schema 边界。

### 10.3 禁止事项

禁止：

1. Stage 6 重新判断 requiredness。
2. Stage 6 把 unspecified 当 required。
3. Stage 6 从 header fallback 补 demand。
4. Stage 6 忽略 demand_id。
5. 使用 Python truthiness 处理 `required=None`，例如 `if field.required` / `required if f.required else optional`。

### 10.4 测试计划

测试覆盖：

1. Context builder 输出 requiredness 三值。
2. LLM output parser 保留 requiredness。
3. ResourceContractFieldIR 保留 demand_id。
4. ResourceContractBindingIR 保留 demand_id 和 requiredness。
5. `unspecified` 不渲染为 required。
6. Stage 6 不修改 DemandView requiredness。
7. Stage 6 materializes name/resource_kind/data_type/path。
8. Invalid LLM output 不覆盖 DemandView contract。
9. `_build_contract_section()`、resource contract demand prompt section、LLM output parser / binding builder 均显式处理 `requiredness` 三值。
10. `required=None` 不会被渲染或提示为 optional。

### 10.5 验收标准

Phase B4 通过条件：

1. Stage 6 以 DemandView 为 source demand 输入。
2. Stage 6 仍是 name/kind/type authority。
3. Requiredness 只 pass-through。
4. Bindings 可追溯回 demand_id。
5. 所有 Stage 6 prompt 构建和 parser 路径都无 `required` truthiness 处理。
6. 全量单测通过。

---

## 11. Phase B5：Post-normalize IRS 与 ProducerIndex 对齐

### 11.1 目标

Post-normalize IRS 从 DemandView + bindings 检查 resource contract satisfaction，并正确处理 requiredness 三值。

### 11.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/irs/checkers/post_normalize.py
src/nl2spl/compiler/producer_index.py
tests/unit/test_post_normalize_resource_contract_irs.py
```

### 11.3 禁止事项

禁止：

1. IRS 从 raw NL 生成 demand。
2. IRS 从 section title 生成 demand。
3. IRS 补 ResourceRegistryIR。
4. IRS 把 unspecified 当 required error。

### 11.4 测试计划

测试覆盖：

1. DemandView demand 无 binding -> missing materialization diagnostic。
2. Binding 不在 ResourceRegistryIR -> registry mismatch。
3. `requiredness=required` output 无 producer -> missing producer。
4. `requiredness=optional` output 无 producer -> 不报 required producer error。
5. `requiredness=unspecified` output 无 producer -> warning，不是 error。
6. IRS report 保留 demand provenance。
7. DiagnosticProjector missing_slot 完整。

### 11.5 验收标准

Phase B5 通过条件：

1. Post-normalize IRS 消费 DemandView。
2. Producer check 按 requiredness 三值运行。
3. 不生成 demand，不补资源。
4. 全量单测通过。

---

## 12. Phase C：Coverage Validator 与 Diagnostic Runtime Integration

### 12.1 目标

引入独立 `ResourceContractAnnotationCoverageValidator`，检测结构化 facts 是否缺 Stage 2 confirmed annotation，并确保 diagnostics 进入 compile diagnostics、feedback report、checkpoint。

ViewDiagnosticProjector 的基础投影能力应已在 Phase A 建立。Phase C 的重点是 coverage validator、orchestrator runtime 汇聚、feedback report 展示和 diagnostic visibility，而不是第一次定义 projector。

### 12.2 可编辑范围

允许新增：

```text
src/nl2spl/compiler/resource_contract_demand_view/coverage_validator.py
tests/unit/compiler/resource_contract_demand_view/test_coverage_validator.py
```

允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/feedback_report_renderer.py
```

### 12.3 禁止事项

禁止：

1. Coverage validator 生成 demand。
2. Coverage validator 修改 routes。
3. Coverage validator 修改 DemandView。
4. Diagnostics 只留在 intermediate，不进入 final report。

### 12.4 测试计划

测试覆盖：

1. Structural hard fact 有 expected resource contract，但无 annotation -> coverage gap diagnostic。
2. Expected fact 有 matching annotation -> 无 coverage gap。
3. Coverage diagnostic 不生成 demand。
4. Projector 生成 `CompileDiagnostic`。
5. Orchestrator intermediate 包含 payload 和 coverage summary。
6. Final `compile_diagnostics` 包含 view diagnostics。
7. Feedback report 包含 Resource Contract Demand section。
8. Diagnostic dedup 不吞掉 coverage gap。

### 12.5 验收标准

Phase C 通过条件：

1. Coverage validator 独立于 DemandView builder。
2. Coverage gap 可见于 compile diagnostics。
3. Coverage gap 可见于 feedback report。
4. Coverage validator 不生成 demands。
5. 全量单测通过。

---

## 13. Phase D：Orchestrator 默认路径切换并移除 Stage 3.2 默认调用

### 13.1 目标

Orchestrator default production path 不再调用 `ResourceContractPlanner`。DemandViewResult 成为 Stage 3.5 / Stage 6 / IRS 的 source of truth。

### 13.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage3_2_resource_contract_planner/**
tests/unit/test_orchestrator*.py
tests/unit/compiler/resource_contract_demand_view/**
```

允许保留旧文件为 migration shim，但不得被 default path 调用。

### 13.3 禁止事项

禁止：

1. Default path 调用 `ResourceContractPlanner().plan(...)`。
2. `orchestrator.py` 继续 import `ResourceContractPlanner`。
3. Default path 写 `stage3_2_resource_contract_plan` checkpoint。
4. Default path 静默运行 header fallback。
5. 删除旧类型导致兼容测试无计划崩溃。

### 13.4 测试计划

测试覆盖：

1. Orchestrator default path 不 import/call `ResourceContractPlanner`。
2. Orchestrator 写 `resource_contract_demand_view_payload`。
3. Orchestrator 不写旧 `stage3_2_resource_contract_plan` checkpoint。
4. Stage 3.5 收到 DemandView。
5. Stage 6 收到 DemandView。
6. Post-normalize IRS 收到 DemandView。
7. Header fallback 仅 compat helper 可触发。
8. Existing structural NL happy path 通过。
9. Missing annotation path 产生 visible diagnostic，不静默少需求。

### 13.5 验收标准

Phase D 通过条件：

1. Stage 3.2 不再是默认 production path。
2. DemandViewResult 是 source of truth。
3. Header fallback 不在默认路径。
4. `orchestrator.py` 不再 import `ResourceContractPlanner`。
5. Intermediate、compile diagnostics、feedback report 完整。
6. 全量单测通过。

---

## 14. Phase E：Legacy Shim 收敛与清理

### 14.1 目标

确认旧 `ResourceContractPlanner` 和 `ResourceContractPlanIR` 的剩余用途，只保留必要 migration shim，删除或标记废弃生产依赖。

### 14.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage3_2_resource_contract_planner/**
src/nl2spl/ir/resource_contract_ir.py
tests/unit/**/*
docs/implementation/resource-contract-demand-view/**
```

### 14.3 禁止事项

禁止：

1. 删除仍被 production path 使用的类型。
2. 保留未标注的 legacy dependency。
3. 保留无测试覆盖的 compat fallback。

### 14.4 测试计划

测试覆盖：

1. AST scan：default production code 不引用 `ResourceContractPlanner`。
2. AST scan：`pipeline/stages/stage3_2_resource_contract_planner` 不在 orchestrator import path。
3. Compat helper 仅测试路径或显式 legacy path 使用。
4. No stale checkpoint name。
5. No stale docs claiming Stage 3.2 is production stage。

### 14.5 验收标准

Phase E 通过条件：

1. Legacy status 清晰。
2. 无默认生产依赖。
3. 文档、测试、checkpoint 命名一致。
4. 全量单测通过。

---

## 15. 端到端验收场景

最终必须具备以下 E2E 或高保真集成覆盖：

1. **结构化 NL happy path**
   - Stage 2 产生 input/output annotations。
   - DemandView 生成 demands。
   - Stage 3.5 生成 placeholders。
   - Stage 6 materializes resources。
   - IRS 无 missing materialization。

2. **Stage 2 漏 annotation**
   - Coverage validator 产生 diagnostic。
   - 不生成 fallback demand。
   - Feedback report 可见。

3. **Direction conflict**
   - DemandView 不生成 demand。
   - Diagnostic 可见。

4. **Requiredness unspecified**
   - Demand 保留。
   - `required=None`。
   - Stage 6 pass-through。
   - Renderer 不输出 REQUIRED。
   - IRS producer check warning 而非 error。

5. **Header-only legacy input**
   - Default path 不生成 demand。
   - Compat path 显式启用时才生成，并标记 compatibility inferred。

---

## 16. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐最终设计文档。
2. 是否扩大到 generic NL。
3. 是否新增未确认的 LLM prompt/schema 改动。
4. 是否新增未确认的 rule-based semantic fallback。
5. 是否让 DemandView 读取 `CanonicalCompileInput`。
6. 是否让 DemandView 读取 section title / evidence text 做语义判断。
7. 是否让 Coverage validator 生成 demand。
8. 是否把 `requiredness=unspecified` 当作 `required=True`。
9. 是否让 Stage 6 修改 requiredness。
10. 是否让 IRS 生成或补全 demand/resource。
11. 是否让 default orchestrator path 继续调用 Stage 3.2。
12. 是否把 diagnostics 留在 intermediate 但没有进入 final compile diagnostics/report。
13. 是否存在 skip / xfail / 弱断言。
14. 是否有新代码路径没有测试覆盖。
15. 是否有 stale docs / checkpoint names / comments 表示 Stage 3.2 仍是 production stage。
16. 是否遗漏 `ContractFieldIR`、`WorkerInput`、`WorkerOutput` 的 requiredness 传播。
17. 是否仍存在 `if field.required` / `if inp.required` 处理 `None` 的 truthiness 代码。
18. Stage 6 prompt/schema 是否已在 B4 开工前完成确认。
19. `_resource_contract_demand_contracts()` 是否仍在默认路径被调用。
20. `orchestrator.py` 是否仍 import `ResourceContractPlanner`。

---

## 17. 阶段完成顺序

推荐顺序：

```text
Phase A        DemandView 并行引入
Decision Gate  Stage 2 requiredness contract 方案确认
Phase B0       Schema Impact Audit
Phase B1       Requiredness schema
Phase B2       Stage 2 structural annotation contract
Phase B3       Stage 3.5 switch
Phase B4       Stage 6 switch
Phase B5       Post-normalize IRS switch
Phase C        Coverage validator + diagnostic runtime integration
Phase D        Orchestrator default path switch
Phase E        Legacy shim cleanup
```

其中：

- Phase A 可立即开工。
- Decision Gate 必须在 Phase A 后、B0/B1/B2 前完成；它决定 requiredness 存放位置和 Stage 2 annotation shape。
- Phase B1 之前必须完成 Phase B0。
- Phase B2 涉及 LLM / rule-based 边界，必须先确认方案。
- Phase B4 开工前必须确认 Stage 6 prompt/schema 设计。
- Phase D 必须等 B3/B4/B5/C 完成后再做。
