# API Declaration 占位渲染、诊断分层与下游验证闭环实施计划

本文档严格基于：

- `docs/design/spl_editing_api_declaration_repair_strategy_and_stage_slice_design_zh.md`
- `docs/problem/api_declaration_call_api_materialization_design.md`
- 当前项目中已存在的 Stage 6 placeholder materialization、Stage 7 CALL_API materialization、ResourceDeclarationGate、IRS、Renderer 和 SPL Editing Presentation 实现

实施目标是：在不要求 NL2SPL 补齐真实 OpenAPI/API_IN_SPL contract 的前提下，让 source-backed API declaration 使用 grammar-safe placeholder 完成 NL2SPL 渲染，让 CALL_API 正常生成和显示；同时把真实 API contract 核验明确交给后续 SPL compiler/API validation layer，并让 diagnostics、feedback report、SPL Editing issue count 和 presentation state 与该 authority 边界一致。

本计划不把 `API_DECLARATION.functions` 或 `API_DECLARATION.openapi_schema` 变成 mandatory Fix with AI issue。

---

## 1. 当前基线

### 1.1 已经实现且必须保留的行为

当前代码已经具备以下基础：

```text
Stage 6:
  functions = []
  openapi_schema = StructuredTextIR("empty_placeholder", "{}")
  declaration_status = grammar_minimal_partial
  schema_status = unknown_placeholder
  functions_status = unknown_placeholder

API declaration grammar:
  grammar-safe placeholder -> grammar_minimal_partial

Post-normalize IRS:
  grammar_minimal_partial -> renderable=True

ResourceDeclarationGate:
  accepts grammar_minimal_partial

Stage 7:
  materializes CALL_API when demand/binding/placement/API identity are valid
  does not require schema/functions semantic completion

Renderer:
  emits {}
  emits {"functions":[]}
  emits CALL API_NAME
```

实际 `examples/output/demo/final_spl.txt` 已证明 placeholder declaration 和 CALL_API 可以同时出现。

### 1.2 尚未闭合的问题

当前主要缺口不是 materialization，而是状态、诊断和 presentation：

1. `type_or_contract_ambiguity` 在 DiagnosticRegistry 中全局 `blocks_completion=True`。
2. API placeholder slots 仍被投影为该 diagnostic kind，因此会使整体 PipelineResult 变成 partial。
3. `PipelineOrchestrator._annotate_editable_diagnostics_for_snapshot_contract()` 按 kind 将全部 `type_or_contract_ambiguity` 默认标成 editable，没有检查 IRS slot 是否具有 repair affordance。
4. API functions/schema diagnostics 虽无 RepairCatalog entry，却携带 `repairability=editable` metadata。
5. `EditableIssueExtractor` 以 RepairCatalog 为真源过滤掉 API diagnostics，导致 default presentation 静默缺少 deferred validation item。
6. `IssuePresentationBuilder` 只接收 editable issues，因此已有 `Deferred validation` section 没有生产数据源。
7. FeedbackReportRenderer 仅对 WORKER_PROMOTION 做专用分组，API group 在 summary/detail 中仍以两个 diagnostics 展示。
8. Report 的 requirement gap 文案没有区分 NL2SPL gap 与 downstream API validation pending。
9. 当前没有一个明确测试证明“只有 API placeholders pending 时，NL2SPL compile status 仍可为 complete”。
10. 下游验证 authority 虽在设计中明确，但没有形成可执行的 handoff contract 测试。

### 1.3 正确完成状态

实施完成后应形成：

```text
Source-backed API intent
  -> Stage 6 grammar-minimal APISpec with placeholders
  -> IRS: renderable, downstream validation pending
  -> ResourceDeclarationGate: approved
  -> Stage 7 CALL_API
  -> ExecutableGate: approved API ref
  -> Renderer: DEFINE_APIS + CALL
  -> PipelineResult: not made partial solely by deferred API validation
  -> Feedback: grouped deferred validation section
  -> SPL Editing: API group appears under Deferred validation, never under Editable issues
  -> downstream SPL compiler/API layer: validates real API contract later
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. `OPENAPI_SCHEMA={}` 和 `API_IN_SPL={"functions":[]}` 是合法 NL2SPL placeholders。
2. Placeholder 的 grammar validity 与真实 API contract validity 是两个状态轴。
3. NL2SPL 负责 structural renderability，不负责证明真实 API 可调用。
4. Stage 6 是 APISpec/placeholder materialization authority。
5. Stage 7 是 CALL_API StepIR materialization authority。
6. Stage 7、Gate 和 Renderer 不得要求 API semantic contract complete。
7. 缺少 schema/functions 不得阻止 API declaration 或 CALL_API 渲染。
8. Malformed schema/functions container 仍然是 NL2SPL structural error，必须 fail closed。
9. `unknown_placeholder` 不等于 `known_empty`，也不等于 downstream validated。
10. `known_present` 只表示 NL2SPL artifact 中存在内容，不等于外部 API 已验证。
11. API placeholder diagnostics 不得进入 mandatory Editable issues。
12. `repairability` 不得仅由 `diagnostic.kind` 推导。
13. RepairCatalog/IRS repair affordance 仍是 editable capability truth source。
14. `API_DECLARATION.functions/openapi_schema.repair_affordances` 在本计划核心范围内保持为空。
15. Feedback/UI 不得把 downstream validation pending 描述成 NL2SPL 无法渲染。
16. API deferred validation group 与 worker delegation issue 必须保持独立。
17. 不解析 feedback report、compile report 或 final SPL 来构建结构化 facts。
18. 不新增 LLM prompt、LLM fallback 或 AI-generated API contract。
19. 不把 CALL_API 降级为 GENERAL_COMMAND 来回避 declaration/binding 问题。
20. 每个阶段必须可独立验收，不允许先合入不可观测的半成品。

---

## 3. LLM 与确定性逻辑约束

本计划核心阶段不需要调用 LLM。

允许的确定性逻辑：

```text
读取 APISpec status
验证 StructuredTextIR grammar shape
验证 functions container shape
根据 construct_id/issue_group_id 分组
根据 RepairAffordanceSpec 判断 editable capability
根据 diagnostic metadata 决定 review disposition
生成稳定 group id
渲染 deterministic presentation copy
```

禁止：

```text
从 API name 推断 endpoint
从 operation text 生成 OpenAPI
从 diagnostic.message 提取 API contract
将 unknown 自动升级为 known_empty/known_present
让 LLM 判断 placeholder 是否真实有效
让 LLM 决定 diagnostic 是否 editable
```

如果未来实施 optional API contract enrichment，必须单独制定计划，不得混入本计划核心 phases。

---

## 4. Phase AP-1：Characterization 与回归基线

### 4.1 目标

在修改语义前锁定当前已经正确的 placeholder/rendering 链路和当前错误的 diagnostic/presentation 链路，防止后续把已工作的 Stage 6/7 路径改坏。

### 4.2 允许修改

```text
tests/unit/compiler/irs/
tests/unit/pipeline/stage6/
tests/unit/pipeline/stage7/
tests/unit/pipeline/
tests/unit/compiler/spl_editing/
tests/unit/compiler/spl_editing/presentation/
tests/integration/compiler/spl_editing/
```

### 4.3 禁止修改

```text
src/nl2spl/
examples/output/demo/final_spl.txt
examples/output/demo/spl_editing_snapshot.json
```

本阶段只能增加 characterization tests。

### 4.4 实施思路

新增一组明确区分状态轴的测试 fixture：

```text
Case A: valid source-backed API + unknown placeholders
Case B: malformed schema placeholder
Case C: malformed functions container
Case D: missing API name
Case E: missing source evidence
Case F: valid partial declaration + valid CALL_API demand/binding/placement
```

记录当前 demo 计数：

```text
raw compile diagnostics: 12
feedback report rows: 9
logical grouped issues: 8
editable issues: 7
```

该计数测试必须从 structured diagnostics 计算，禁止解析 feedback report 文本。

### 4.5 测试计划

新增或扩展：

```text
tests/unit/compiler/irs/test_api_declaration_checker.py
tests/unit/pipeline/stage6/test_api_materialization_skeleton.py
tests/unit/pipeline/stage7/test_api_call_materializer.py
tests/unit/pipeline/test_resource_declaration_gate.py
tests/unit/compiler/spl_editing/test_api_issue_inventory_baseline.py
```

必须覆盖：

1. Stage 6 生成 `{}` 和空 functions。
2. Grammar validator 返回 `grammar_minimal_partial`。
3. IRS report `renderable=True`。
4. ResourceDeclarationGate 接受该 API。
5. Stage 7 生成 CALL_API。
6. Renderer 输出 placeholder declaration 和 CALL。
7. API diagnostics 当前携带错误 editable metadata的 characterization。
8. Presentation 当前缺少 deferred validation item 的 characterization。

### 4.6 验收标准

1. 所有测试仅描述当前行为，不改变生产结果。
2. 测试明确区分 expected-correct 与 expected-to-change assertions。
3. 没有 snapshot/report regex parsing。
4. 没有新增 skip/xfail。
5. 全量现有测试仍通过。

### 4.7 PM 审核清单

- 检查测试是否真的经过 Stage 6/IRS/Gate/Stage 7，而不是手工拼最终 SPL。
- 检查 malformed placeholder 负例是否存在。
- 检查 baseline 是否记录 metadata inconsistency。
- 检查没有为了让测试通过而修改 fixtures 的 authority 字段。
---

## 5. Phase AP0：Deferred API Validation Diagnostic Contract

### 5.1 目标

建立专门的 non-blocking diagnostic contract，避免继续复用全局 `type_or_contract_ambiguity(blocks_completion=True)` 表达 downstream API validation pending。

### 5.2 允许修改

```text
src/nl2spl/compiler/diagnostic_registry.py
src/nl2spl/ir/diagnostics.py                 # 仅在需要新增稳定 metadata key 常量时
src/nl2spl/compiler/construct_registry.py    # 仅更新说明/slot policy，不加 repair affordance
tests/unit/compiler/
tests/unit/compiler/irs/
```

### 5.3 禁止修改

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/api_materialization.py
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/compiler/spl_editing/handlers/
src/nl2spl/compiler/spl_editing/patches/
```

### 5.4 设计要求

新增 diagnostic kind：

```text
deferred_api_contract_validation
```

建议 contract：

```text
severity: info 或 warning，固定一种并测试
authorized target: api
blocks_rendering: false
blocks_completion: false
repairability: review_only
validation_authority: downstream_spl_compiler
```

适用条件仅限：

```text
APISpec grammar shape valid
AND declaration_status == grammar_minimal_partial
AND schema_status/functions_status contains unknown_placeholder
```

不适用于：

```text
malformed StructuredTextIR
functions container grammar invalid
api_name invalid
source evidence missing
auth grammar invalid
```

这些仍使用 structural diagnostics，例如 `type_or_contract_ambiguity`，并按现有 blocking policy 处理。

`ConstructRegistry` 中 API slots：

```text
openapi_schema.repair_affordances = ()
functions.repair_affordances = ()
```

必须保持不变。

### 5.5 测试计划

1. DiagnosticRegistry 能查询新 kind。
2. `blocks_completion=False`。
3. `compute_completeness()` 在只有 deferred diagnostics 时返回 `complete`。
4. `type_or_contract_ambiguity` 仍保持 blocking，不做全局降级。
5. API slots 不新增 repair affordance。
6. Snapshot diagnostic serializer 可 round-trip 新 kind 和 metadata。

### 5.6 验收标准

1. 新 diagnostic kind 语义唯一，不复用为其他普通 contract gap。
2. 不修改 `type_or_contract_ambiguity` 的全局行为。
3. 不新增 feature flag。
4. 不新增 LLM。
5. 全量 diagnostic registry/completeness tests 通过。

### 5.7 PM 审核清单

- 搜索 `deferred_api_contract_validation`，确认只用于 API placeholder pending。
- 搜索 `repair_affordances`，确认 API functions/schema 仍为空。
- 检查新 diagnostic 不会 blocks completion。
- 检查 malformed API 仍走 blocking kind。

---

## 6. Phase AP1：IRS 两轴状态与 Diagnostic Projection

本阶段可拆为 AP1.1、AP1.2、AP1.3 三个独立提交。

### 6.1 AP1.1：API declaration slot classification

#### 目标

让 APIDeclarationIRSChecker 精确区分 grammar-safe placeholder 与 malformed contract shape。

#### 允许修改

```text
src/nl2spl/compiler/irs/checkers/api_declaration.py
src/nl2spl/compiler/irs/checkers/api_declaration_grammar.py
tests/unit/compiler/irs/test_api_declaration_checker.py
```

#### 实施思路

为 schema/functions 分别形成结构化分类：

```text
known_present/known_empty + grammar valid:
  slot satisfied
  no deferred placeholder diagnostic

unknown_placeholder + grammar valid + grammar_minimal_partial:
  slot unresolved for downstream contract
  diagnostic_kind = deferred_api_contract_validation
  diagnostic_required_for = downstream_api_validation
  diagnostic_blocks_rendering = false

invalid shape/status contradiction:
  diagnostic_kind = type_or_contract_ambiguity
  diagnostic_required_for = render
  diagnostic_blocks_rendering = true
```

ConstructSatisfactionReport：

```text
renderable = true for grammar_minimal_partial
completeness may remain partial at construct-level
metadata.nl2spl_renderable = true
metadata.api_contract_validation_status = pending
metadata.validation_authority = downstream_spl_compiler
metadata.issue_group_id = api_contract_deferred:{api_id}
metadata.repairability = review_only
metadata.presentation_disposition = deferred_validation
```

这里的 construct-level `partial` 不得再通过 projected diagnostic 使 PipelineResult partial。

#### 验收

1. Placeholder slots 产生 deferred kind。
2. Malformed slots 产生 structural kind。
3. `renderable=True` 不受 deferred slots 影响。
4. Report metadata 明确两个状态轴。

### 6.2 AP1.2：Projector metadata whitelist

#### 目标

让 IRS report 中明确声明的 disposition/group/authority metadata 安全进入 CompileDiagnostic。

#### 允许修改

```text
src/nl2spl/compiler/irs/projector.py
src/nl2spl/ir/diagnostics.py
tests/unit/compiler/irs/
```

#### 实施思路

扩展 projector 的显式白名单，只允许复制：

```text
issue_group_id
repairability
validation_authority
nl2spl_renderable
api_contract_validation_status
placeholder_fields
```

不得复制任意 report metadata。

Projector 仍从 DiagnosticRegistry 获取默认 severity/blocks_completion；新 deferred kind 已确保不阻塞。Malformed structural kind 继续阻塞。

#### 验收

1. Deferred diagnostic metadata round-trip 完整。
2. 任意未白名单 metadata 不会泄漏。
3. IRS ref/authority 保持不变。
4. Projector 不根据 message 推断 disposition。

### 6.3 AP1.3：Construct completeness 与 pipeline completeness 回归

#### 目标

证明 construct-level partial 和 PipelineResult complete 可以同时成立且语义清楚。

#### 测试计划

```text
API report:
  completeness=partial
  renderable=True
  api_contract_validation_status=pending

CompileDiagnostic:
  kind=deferred_api_contract_validation
  blocks_completion=False

PipelineResult:
  completeness=complete when no other gaps exist
```

#### 验收

1. 只有 API placeholder pending 时整体 compile complete。
2. 任何 malformed API structural diagnostic 仍使 compile partial/blocked，按现有 validation flow 决定。
3. Feedback 不再把 deferred kind 当 requirement gap。

### 6.4 PM 总审核

- 检查是否错误地把 placeholder slot 标成 satisfied/validated。
- 检查是否保留 `unknown_placeholder`，没有自动改成 known_empty。
- 检查 `type_or_contract_ambiguity` 没有被全局弱化。
- 检查 report metadata 不承担 RepairCatalog 能力声明。

---

## 7. Phase AP2：Diagnostic Disposition 与 Grouping 重构

本阶段解决当前 blanket editable annotation。

### 7.1 目标

将 diagnostic user-facing disposition 从 `diagnostic.kind` 硬编码改为 structured authority：

```text
explicit IRS/projector disposition
+ ConstructRegistry repair affordance
+ promoted diagnostic policy
```

### 7.2 允许修改

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/spl_editing/issues/
src/nl2spl/ir/diagnostics.py
tests/unit/compiler/spl_editing/
tests/unit/pipeline/
```

建议新增：

```text
src/nl2spl/compiler/diagnostic_issue_grouping.py
```

或等价 compiler-owned grouping 模块。它不得依赖 SPL Editing runtime。

### 7.3 禁止改动

```text
src/nl2spl/compiler/spl_editing/presentation/templates/
src/nl2spl/compiler/spl_editing/handlers/
src/nl2spl/compiler/spl_editing/patches/
```

### 7.4 实施思路

将 `_annotate_editable_diagnostics_for_snapshot_contract()` 重构为 capability-aware annotator。

禁止继续使用：

```text
if diagnostic.kind == type_or_contract_ambiguity:
    repairability = editable
```

正确规则：

```text
if diagnostic already carries explicit review_only/non_repairable:
  preserve it

elif IRS slot has at least one RepairAffordanceSpec:
  editable

elif promoted worker diagnostic policy explicitly marks editable:
  preserve promoted metadata

else:
  review_only or developer_only according to structured disposition
```

API deferred diagnostics：

```text
issue_group_id = api_contract_deferred:{api_id}
repairability = review_only
presentation_disposition = deferred_validation
one primary + remaining aliases
related_diagnostic_ids includes functions/schema diagnostics
```

Primary selection必须 deterministic，例如按固定 slot order：

```text
functions
openapi_schema
authentication
```

该顺序只决定 presentation identity，不决定 semantic severity。

### 7.5 测试计划

1. API functions/schema 形成一个 deferred-validation group，底层 repairability 保持 review_only。
2. Worker promotion 仍为一个 editable group。
3. Missing handler/output producer 仍 editable。
4. Generic type ambiguity without affordance 不会 editable。
5. Existing explicit metadata 不被 blanket annotation 覆盖。
6. Group primary/alias 稳定。
7. Diagnostic order permutation 不改变 group identity。
8. Snapshot round-trip 不改变 group metadata。

### 7.6 验收标准

1. API diagnostics 不再携带 editable metadata。
2. API group 有且只有一个 primary。
3. Worker promotion 现有行为不回归。
4. 不依赖 diagnostic.message、target text regex 或 report parser。
5. Compiler grouping 模块不 import SPL Editing service/runtime。

### 7.7 PM 审核清单

- 搜索 `editable_kinds`，确认不再包含 blanket `type_or_contract_ambiguity`。
- 检查 worker promotion 的 editable metadata 仍来自 promoter/affordance policy。
- 检查 API group key 使用 construct identity。
- 检查没有 API-specific字符串正则提取 api_name。
---

## 8. Phase AP3：Stage 6 → Stage 7 → Gate → Renderer Contract Hardening

当前核心路径已经可工作。本阶段以 contract tests 和边界收敛为主，不允许无理由重写已工作的 pipeline。

### 8.1 AP3.1：Stage 6 placeholder policy

#### 允许修改

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/api_materialization.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/api_contract_extraction.py
tests/unit/pipeline/stage6/
```

#### 实施思路

把 placeholder policy 表达为明确的 deterministic contract：

```text
schema placeholder:
  format=empty_placeholder
  canonical_text={}
  schema_status=unknown_placeholder

functions placeholder:
  functions=[]
  functions_status=unknown_placeholder

declaration_status=grammar_minimal_partial
```

保证 replay idempotence：

```text
同一 declaration demand 重放不会重复创建 API；
existing APISpec identity/provenance 被复用；
placeholder 不覆盖 known_present/known_empty slots。
```

#### 验收

1. Placeholder exact shape 稳定。
2. Known contract 不被降级为 placeholder。
3. 无 source-backed demand 不创建 API。
4. 不调用 LLM。

### 8.2 AP3.2：ResourceDeclarationGate

#### 允许修改

```text
src/nl2spl/pipeline/resource_declaration_gate.py
tests/unit/pipeline/test_resource_declaration_gate.py
```

#### 实施思路

Gate approval 只依赖：

```text
report.renderable
grammar status in grammar_minimal_partial|complete
grammar_valid
api_name satisfied
source_evidence satisfied
```

不得新增：

```text
schema_status != unknown_placeholder
functions_status != unknown_placeholder
report.completeness == complete
```

#### 验收

1. Approved partial API 进入 renderable registry view。
2. Malformed/identity/evidence failures 被拒绝。
3. `incomplete_api_names` 可保留用于 audit，但不能阻止 CALL_API。

### 8.3 AP3.3：Stage 7 CALL_API admission

#### 允许修改

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
tests/unit/pipeline/stage7/test_api_call_materializer.py
```

#### 实施思路

Stage 7 继续要求：

```text
call demand
unique declaration binding
valid placement
existing APISpec identity
valid argument binding status
unambiguous operation coverage
```

不得要求 API semantic complete。

#### 验收

1. Partial API 可生成 CALL_API。
2. Empty inputs/outputs 在 binding_status=not_required 时合法。
3. Missing declaration/binding/placement 仍 fail closed。
4. 不降级为 GENERAL_COMMAND。

### 8.4 AP3.4：ExecutableGate 与 Renderer

#### 允许修改

```text
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py
tests/unit/pipeline/
tests/unit/pipeline/stages/
```

#### 实施思路

ExecutableGate：

```text
CALL_API integration_ref must resolve in ResourceDeclarationGate-approved view
binding metadata must match API identity
placeholder status is not a rejection reason
```

Renderer：

```text
always render approved API declaration
render StructuredTextIR.canonical_text
render functions list, including empty list
render CALL_API command
```

#### 验收

1. DEFINE_APIS 和 CALL 同时出现。
2. Placeholder exact syntax 稳定。
3. Undeclared API ref 被拒绝。
4. Renderer 不做 API semantic validation。

### 8.5 PM 总审核

- 对比生产 diff，确认不是无意义重写 Stage 6/7。
- 检查任何新 `complete` 判断是否错误进入 CALL_API path。
- 检查 no-fallback invariant。
- 检查 known contract 不被 placeholder 覆盖。

---

## 9. Phase AP4：Feedback Report Generic Grouping 与 Deferred Section

### 9.1 目标

让 feedback report 区分 requirement gaps 与 downstream validation pending，并基于 structured group metadata统一分组。

### 9.2 允许修改

```text
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/compiler/report_renderer.py
tests/unit/test_feedback_report_renderer.py
```

建议新增内部纯 projection：

```text
GroupedDiagnosticView
DiagnosticSectionKind
```

### 9.3 禁止改动

```text
CompileDiagnostic.message 作为分组来源
正则解析 target_ref 文本以猜 construct type
SPL Editing presentation templates
```

### 9.4 实施思路

将 `_grouped_diag_items()` 从 worker-promotion-only 特例升级为：

```text
1. 读取 issue_group_id / primary / related ids。
2. 一组只输出一个 summary item。
3. slot details 从 missing_slot/irs_ref 读取。
4. construct-specific copy 由 deterministic renderer 提供。
5. 无 structured group metadata 时仍按 raw diagnostic 输出，不做猜测分组。
```

Report sections：

```text
Blocking/partial NL2SPL gaps
Deferred downstream validation
Assumptions/provenance
Developer details
```

API group 示例：

```text
Deferred API contract validation: ApprovedSourceRecipesAPI
  Placeholder declaration rendered.
  Pending downstream validation:
    - OpenAPI schema
    - API_IN_SPL functions
```

不得写成：

```text
Result is partial because API schema/functions are missing
```

除非同一 run 还有其他 blocks_completion diagnostics，PipelineResult 才显示 partial。

### 9.5 测试计划

1. API functions/schema 只显示一个 grouped summary。
2. Group detail显示两个 slots。
3. Worker promotion grouping不回归。
4. Deferred diagnostics不进入 requirement gaps section。
5. Malformed API structural diagnostic进入blocking/partial section。
6. Raw diagnostics detail仍可在developer section追踪。
7. Diagnostic order permutation不改变report。

### 9.6 验收标准

1. Feedback report count名称明确。
2. API group只出现一次于user summary。
3. 无report parsing。
4. Worker-specific详细文案仍可保留，但grouping mechanism必须通用。
5. Snapshot中的diagnostic identity可追溯。

### 9.7 PM 审核清单

- 搜索 `_WORKER_PROMOTION_SLOT_ORDER`，确认它只控制detail order，不再控制唯一grouping capability。
- 检查API group是否来自issue_group_id。
- 检查deferred section不会改变PipelineResult completeness。
- 检查report仍保留diagnostic IDs于advanced/detail。
---

## 10. Phase AP5：User-Facing Issue Inventory 与 Deferred Validation Presentation

本阶段任务较重，拆为 AP5.1 到 AP5.4。

### 10.1 AP5.1：Canonical issue inventory model

#### 目标

解决 Presentation 只能消费 EditableIssue 的结构性问题。

#### 建议模型

```text
UserFacingIssue
  issue_id
  disposition: editable | review_only | deferred_validation | developer_only
  primary_diagnostic_id
  related_diagnostic_ids
  issue_group_id
  kind
  target_ref
  irs_ref
  missing_slots
  blocks_rendering
  blocks_completion
  validation_authority
  affordance_ids

IssueInventory
  editable
  review
  deferred
  developer
```

现有 `EditableIssue` 可在迁移期作为 compatibility projection，但不得继续作为 deferred validation issue 的错误容器。

#### 允许修改

```text
src/nl2spl/compiler/spl_editing/core/model.py
src/nl2spl/compiler/spl_editing/issues/
tests/unit/compiler/spl_editing/
```

#### 验收

1. 一个 API group生成一个deferred validation issue。
2. Editable issues仍由RepairCatalog affordance gating。
3. Review和Deferred issues均不含actionable affordance。
4. Developer diagnostics与review分离。

### 10.2 AP5.2：Issue inventory extractor

#### 实施思路

新增 canonical extractor：

```text
IssueInventoryExtractor.extract(diagnostics)
```

流程：

```text
validate IRS refs/authority
-> group by structured issue_group_id
-> validate exactly one primary
-> derive disposition from explicit metadata + catalog capability
-> emit editable/review/deferred/developer partitions
```

规则：

```text
editable:
  at least one user-facing catalog entry
  + runtime path is potentially supported

review:
  final-authority user-relevant diagnostic
  + repairability=review_only
  + no mandatory action

deferred:
  final-authority downstream-validation diagnostic
  + repairability=review_only
  + presentation_disposition=deferred_validation
  + no current user action

developer:
  malformed grouping, metadata/catalog conflict, unsupported internal contract
```

保留：

```text
SPLEditingService.list_editable_issues()
```

但实现改为从 inventory `.editable` 返回，避免破坏 session API。

新增：

```text
SPLEditingService.list_issue_inventory()
```

#### 验收

1. API group进入inventory.deferred。
2. API group不进入list_editable_issues。
3. Worker promotion进入editable。
4. Metadata声称editable但catalog无affordance时进入developer或review，按明确规则测试，不静默消失。
5. Group identity稳定。

### 10.3 AP5.3：Presentation builders/service

#### 允许修改

```text
src/nl2spl/compiler/spl_editing/presentation/model/
src/nl2spl/compiler/spl_editing/presentation/builders/
src/nl2spl/compiler/spl_editing/presentation/issue_presenters/
src/nl2spl/compiler/spl_editing/presentation/templates/
src/nl2spl/compiler/spl_editing/presentation/service.py
```

#### 实施思路

新增 API deferred validation category/presenter：

```text
IssueCategory.API_CONTRACT_REVIEW
ApiContractReviewPresenter
```

文案只使用：

```text
api name from structured target/context
missing slots from grouped diagnostics
placeholder/renderability metadata
validation authority
```

Presentation Service 使用完整 IssueInventory：

```text
Editable issues section <- inventory.editable
Review needed section <- inventory.review
Deferred validation section <- inventory.deferred
Developer diagnostics <- inventory.developer when enabled
```

API deferred validation card：

```text
API contract validation deferred: ApprovedSourceRecipesAPI
The API declaration and CALL_API are renderable using placeholders.
Full contract validation belongs to the downstream SPL compiler.
Missing metadata: OpenAPI schema, API_IN_SPL functions
```

必须：

```text
can_fix = false
available_repairs = ()
fix_label = "Validation deferred"
```

不得显示 `Fix with AI`。

#### 验收

1. Deferred validation section真实有数据，不再是空壳。
2. API card不访问raw message。
3. `can_fix` invariant成立。
4. Advanced details可追踪diagnostics/slots/authority。

### 10.4 AP5.4：Run summary、CLI 与 demo

#### 允许修改

```text
src/nl2spl/compiler/spl_editing/presentation/model/run.py
src/nl2spl/compiler/spl_editing/presentation/builders/run_builder.py
src/nl2spl/compiler/spl_editing/cli.py
src/nl2spl/compiler/spl_editing/demo.py
examples/output/spl_editing_demo/run_demo.py
tests/unit/compiler/spl_editing/
tests/integration/compiler/spl_editing/
```

#### 实施思路

Run DTO 增加明确字段：

```text
editable_issue_count
review_issue_count
deferred_validation_count
developer_diagnostic_count (developer mode only)
```

迁移期 `issue_count` 可以保留为 editable count alias，并标注移除阶段。不得把review/deferred count加进旧`issue_count`后改变含义。

CLI 示例：

```text
Editable issues: 7
Deferred validation: 1
```

用户选择issue的编号只覆盖editable issues；deferred validation item可查看但不能进入suggestion/apply flow。

#### 验收

1. `run_demo.py`显示7 editable + 1 deferred validation。
2. API deferred validation不能选择Fix with AI。
3. Worker delegation仍可选择并修复。
4. CLI不import raw diagnostic类型做语义判断。
5. Presentation DTO是唯一渲染输入。

### 10.5 PM 总审核

- 检查是否新增了名为EditableIssue但repairability=review_only的混乱对象。
- 检查deferred validation item是否来自inventory而非CLI拼接。
- 检查API card是否错误显示可修复。
- 检查旧service API兼容周期是否标明。
- 检查issue_count含义是否稳定。
---

## 11. Phase AP6：Downstream Validation Handoff Contract

### 11.1 目标

明确 NL2SPL 输出如何把“API contract validation pending”交给后续 SPL compiler/API layer，不在本仓库伪装完成下游验证。

### 11.2 决策

本计划默认使用现有两类 handoff，不新增 SPL grammar：

```text
1. Rendered SPL:
   {} + {"functions":[]}

2. Structured compile artifacts:
   APISpec.schema_status/functions_status
   APISpec.declaration_status
   deferred_api_contract_validation diagnostics
   APIMaterializationPlanIR payload in intermediate results
```

如果下游只能消费 SPL 文本，则placeholder syntax本身是唯一normative handoff。若下游可消费PipelineResult/snapshot，则结构化statuses和diagnostics提供额外审计信息。

### 11.3 允许修改

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/artifacts/snapshot/
src/nl2spl/compiler/artifacts/snapshot/serialization/
docs/design/ 或 docs/integration/
tests/unit/compiler/artifacts/snapshot/
tests/integration/
```

不要求新增字段；只有测试证明现有artifact无法保留所需状态时才允许扩展schema。

### 11.4 禁止改动

```text
SPL grammar placeholder syntax
让NL2SPL调用外部API validator
网络访问/endpoint probe
runtime credential validation
```

### 11.5 实施思路

验证并固定：

```text
ResourceRegistryIR/APISpec round-trip保留：
  declaration_status
  schema_status
  functions_status
  source provenance

CompileDiagnostic round-trip保留：
  deferred kind
  validation_authority
  issue grouping metadata

PipelineResult/intermediate保留：
  api_materialization_plan_payload
```

增加一份downstream contract文档，明确：

```text
unknown_placeholder means validation required later；
known_present does not imply external validation success；
known_empty means authoritative empty declaration，不代表provider可调用；
malformed placeholders不应离开NL2SPL。
```

### 11.6 测试计划

1. Snapshot round-trip保留APISpec statuses。
2. Diagnostic round-trip保留deferred metadata。
3. PipelineResult中可定位pending API identity。
4. Rendered SPL placeholder语法稳定。
5. 不依赖intermediate debug JSON作为唯一authority。

### 11.7 验收标准

1. 下游可以从SPL文本识别placeholder declaration。
2. Structured consumer可以识别pending状态。
3. NL2SPL不宣称API validated。
4. 不新增网络或外部validator依赖。

### 11.8 PM 审核清单

- 检查是否误把`known_present`写成validated。
- 检查snapshot status fields是否完整。
- 检查intermediate不是唯一持久化authority。
- 检查没有修改SPL grammar。

---

## 12. Phase AP7：End-to-End Regression 与 Final Cleanup

### 12.1 目标

通过真实 Pipeline、真实 snapshot、真实 Presentation Service 和真实 `run_demo.py` 验收完整链路，并移除迁移期死代码。

### 12.2 允许修改

```text
tests/integration/
tests/e2e/（若项目已有）
examples/output/spl_editing_demo/run_demo.py
docs/
前述阶段明确标记的compatibility shim
```

### 12.3 E2E 场景

#### 场景 1：只有 API placeholder pending

输入：

```text
source-backed external API intent
valid API name/source evidence
no OpenAPI schema
no API_IN_SPL functions
valid API call demand/binding/placement
```

预期：

```text
Stage 6 APISpec grammar_minimal_partial
final SPL包含{}和{"functions":[]}
final SPL包含CALL API_NAME
PipelineResult.completeness == complete
compile diagnostics包含non-blocking deferred API validation
```

#### 场景 2：Demo 混合 issues

运行：

```text
examples/output/spl_editing_demo/run_demo.py
run = demo
```

预期：

```text
Editable issues: 7
Deferred validation: 1
6 exception handling
1 worker delegation
1 grouped API deferred validation review
```

API deferred validation item：

```text
不显示Fix with AI
说明placeholder已渲染
说明下游负责真实contract validation
```

#### 场景 3：Malformed OpenAPI placeholder

预期：

```text
IRS structural diagnostic
ResourceDeclarationGate rejects API
CALL_API rejected/not rendered
compile not complete
不得降级GENERAL_COMMAND
```

#### 场景 4：Missing API identity/source evidence

预期：

```text
declaration unrenderable
CALL_API unavailable
blocking structural diagnostic
不是deferred validation
```

#### 场景 5：Known complete/known empty contract

预期：

```text
valid declaration rendered
CALL_API rendered
无placeholder deferred diagnostic
仍不宣称external provider validated
```

#### 场景 6：API deferred validation 与 worker delegation 同时存在

预期：

```text
API group -> Deferred validation
worker promotion -> Editable issues
两者target/category/title不混淆
```

#### 场景 7：Permutation/metamorphic

对diagnostics、API declarations、source domains进行顺序和命名变化：

```text
分组结果稳定
repairability不变
placeholder policy不变
不依赖ApprovedSourceRecipesAPI特例
```

### 12.4 静态审计

必须执行：

```text
搜索API functions/schema repair_affordances，确认仍为空
搜索type_or_contract_ambiguity blanket editable annotation
搜索feedback_report/message regex parsing
搜索CALL_API -> GENERAL_COMMAND fallback
搜索schema/functions complete gating in Stage 7/Gate
搜索新增LLM调用
```

### 12.5 验收标准

1. 所有E2E场景通过。
2. 全量unit/integration tests通过。
3. Ruff检查通过项目既定范围。
4. 无新增skip/xfail。
5. 无demo-specific hardcode。
6. 无未清理compatibility shim。
7. 设计文档、downstream contract和实际代码一致。

### 12.6 PM 审核清单

- 亲自查看真实final SPL中的DEFINE_APIS和CALL。
- 亲自查看run_demo的editable/review counts。
- 检查API deferred validation无法进入apply flow。
- 检查malformed negative path。
- 检查只有deferred diagnostic时overall completeness。
- 检查git diff中是否混入无关格式化。

---

## 13. Optional Phase AO1：API Contract Enrichment（不属于核心完成条件）

只有在产品明确要求用户可在NL2SPL阶段主动补充API metadata时才启动。

该阶段必须另行设计：

```text
Stage 6 optional enrichment slice
configured/user-provided contract refs
constrained typed normalization
preview/confirmation
slot-level evidence
no effect on baseline renderability
```

禁止将AO1作为AP0-AP7的依赖。关闭AO1时，placeholder declaration和CALL_API仍必须完整工作。

---

## 14. 总体 E2E 验收矩阵

| 场景 | Declaration | CALL_API | Pipeline completeness | SPL Editing | Downstream |
|---|---|---|---|---|---|
| Valid placeholders only | rendered partial | rendered | complete if no other gaps | grouped deferred validation | validation pending |
| Malformed schema shape | rejected | rejected | partial/blocked | structural issue | not reached |
| Missing API identity | rejected | rejected | partial/blocked | structural issue | not reached |
| Complete local contract | rendered | rendered | complete if no other gaps | no placeholder deferred item | still validates externally |
| API + worker promotion | rendered | independent | based on real editable gaps | API deferred validation + worker editable | API pending |
| Optional enrichment unavailable | rendered | rendered | unaffected | no Fix with AI | pending |

---

## 15. PM 总审核清单

每个阶段提交审核时必须逐项检查：

1. 是否严格对齐修订后的placeholder设计。
2. 是否误把真实API contract validation拉回NL2SPL。
3. 是否新增functions/schema mandatory repair affordance。
4. 是否让unknown_placeholder阻止rendering。
5. 是否把known_empty当成自动默认。
6. 是否把known_present当成external validated。
7. 是否修改了Stage 6/7 authority边界。
8. 是否让Stage 7依赖semantic completeness。
9. 是否让Gate/Renderer删除partial declaration或CALL_API。
10. 是否继续按diagnostic.kind blanket标editable。
11. 是否让API deferred validation item静默消失。
12. 是否把API diagnostics拆成两个user issues。
13. 是否把API deferred validation与worker delegation混淆。
14. 是否从diagnostic.message/report/final SPL反向解析facts。
15. 是否新增未经设计批准的LLM/schema/prompt。
16. 是否新增CALL_API fallback。
17. 是否保留malformed placeholder负向验证。
18. 是否真实测试PipelineResult.completeness。
19. 是否真实测试run_demo presentation。
20. 是否保留snapshot/provenance/diagnostic identity。
21. 是否存在skip/xfail或弱断言。
22. 是否存在demo名称、source retrieval关键词等过拟合。
23. 是否有无关重构、全仓格式化或metadata churn。
24. 是否更新downstream validation contract文档。
25. 是否完成全部phase-specific验收。

---

## 16. 阶段顺序与依赖

推荐顺序：

```text
AP-1  Characterization
  -> AP0  Deferred diagnostic contract
  -> AP1  IRS two-axis status and projection
  -> AP2  Diagnostic disposition/grouping
  -> AP3  Stage6/Stage7/Gate/Renderer hardening
  -> AP4  Feedback report grouping
  -> AP5  Issue inventory and Review presentation
  -> AP6  Downstream validation handoff
  -> AP7  E2E and cleanup

AO1 Optional enrichment
  -> independent future project after AP7
```

依赖约束：

1. AP0必须在AP1前完成，否则projected diagnostic仍会错误blocks completion。
2. AP1必须在AP2前完成，否则API diagnostics缺少明确disposition/group metadata。
3. AP2必须在AP5前完成，否则Presentation没有可靠issue inventory输入。
4. AP3可与AP2部分并行，但必须在AP7前全部完成。
5. AP4依赖AP2的structured group metadata。
6. AP5依赖AP2，且不能通过CLI临时拼deferred validation item绕过。
7. AP6必须在final E2E前完成。
8. AO1不得阻塞任何核心phase。

---

## 17. 最终完成定义

只有满足全部条件，项目才算形成API declaration完整闭环：

```text
1. Source-backed API在缺少真实contract时稳定产生grammar-safe placeholders。
2. API declaration在placeholder状态下通过IRS renderability和ResourceDeclarationGate。
3. CALL_API在declaration partial但renderable时正常生成。
4. ExecutableGate和Renderer保留declaration及CALL_API。
5. Placeholder pending使用独立non-blocking diagnostic。
6. 只有deferred API diagnostics时PipelineResult仍为complete。
7. Malformed API shape继续fail closed。
8. API diagnostics按declaration分为一个deferred validation group。
9. API group不进入Editable issues，也不显示Fix with AI。
10. Worker delegation仍独立、可编辑且分类正确。
11. Feedback report将API pending放入deferred downstream validation section。
12. Run summary清楚显示editable与review counts。
13. Snapshot/PipelineResult保留placeholder statuses和validation authority。
14. Rendered SPL是下游compiler可消费的normative handoff。
15. NL2SPL不宣称真实API contract已验证。
16. Optional enrichment不是基础rendering依赖。
17. 全量unit/integration/真实E2E验收通过。
```

最终用户可观察行为：

```text
NL2SPL成功生成：
  [DEFINE_APIS]
  {}
  {"functions":[]}
  CALL API_NAME

SPL Editing显示：
  Editable issues: 实际可修复问题数量
  Deferred validation: API contract validation deferred

后续SPL compiler：
  对真实OpenAPI/API_IN_SPL contract执行最终核验
```