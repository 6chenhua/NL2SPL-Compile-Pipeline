# SPL Editing API Declaration 占位渲染与可选增强设计

状态：修订后的设计基线  
语言：中文  
适用范围：`API_DECLARATION` IRS、Stage 6 API materialization、Stage 7 CALL_API、SPL Editing Presentation、后续 SPL 编译边界

---

## 1. 关键设计修正

`OPENAPI_SCHEMA` 和 `API_IN_SPL` 允许为空。NL2SPL 在缺少真实 API contract 时，应生成 grammar-safe placeholder，使 API declaration 与 `CALL_API` command 可以正常渲染。

因此，正确的核心链路不是：

```text
missing functions / schema
-> SPL Editing mandatory repair
-> user confirmation
-> only then render API declaration and CALL_API
```

而是：

```text
source-backed API intent
-> Stage 6 materializes grammar-minimal API declaration
-> OPENAPI_SCHEMA = {}
-> API_IN_SPL = {"functions": []}
-> API_DECLARATION remains semantically partial but renderable
-> Stage 7 may materialize CALL_API
-> Stage 9.5 / Gate validate NL2SPL structural requirements
-> Stage 11 renders declaration and CALL_API
-> downstream SPL compiler/API layer validates the real API contract later
```

这意味着：

1. `functions` 和 `openapi_schema` 缺失不是 NL2SPL render blocker。
2. 它们不应成为 CALL_API 显示的前置修复条件。
3. 当前为这两个 slots 增加 mandatory `repair_affordances` 不是正确的核心修复。
4. 如果未来允许用户补充 API contract，那属于 optional enrichment，不是 NL2SPL 必须完成的 issue repair。
5. NL2SPL 只对 declaration identity、source backing、grammar shape 和 CALL_API reference integrity 负责。
6. 外部 API 的真实函数、schema、endpoint 和运行时有效性由后续 SPL 编译/API validation layer 负责。

---

## 2. 与现有设计和代码的对齐

### 2.1 Minimum renderable APISpec

现有 API materialization 设计已经规定，partial API declaration 的最小渲染条件是：

```text
api_name 非空且 grammar-safe
source_span_ids 非空，或 origin=user_confirmed_repair/configured_resource
```

以下字段允许为空：

```text
description
openapi_schema
functions
retry/log policy
```

默认 authentication 可以是：

```text
auth = none
```

### 2.2 Stage 6 当前已经生成 placeholder

Stage 6 当前 partial skeleton 的核心状态是：

```text
functions = []
openapi_schema = StructuredTextIR("empty_placeholder", "{}")
declaration_status = grammar_minimal_partial
schema_status = unknown_placeholder
functions_status = unknown_placeholder
```

这不是错误或未完成 patch，而是一个合法的 NL2SPL 编译产物：

```text
grammar shape: valid
semantic API contract: deferred
renderability: allowed
```

### 2.3 Renderer 目标输出

合法 partial declaration 可以渲染为：

```spl
[DEFINE_APIS:]
    "description" ApprovedSourceRecipesAPI <none>
    {}
    {"functions": []}
[END_APIS]
```

与之对应的 CALL_API 可以正常渲染，只要：

```text
CALL_API.integration_ref 非空
integration_ref 指向已声明 API
step 有 source evidence 或 user-confirmed repair evidence
```

CALL_API 的 `inputs=[]` 和 `outputs=[]` 在没有更强 source demand 时也允许。

---

## 3. 两个正交状态：可渲染性与 API 完整性

API declaration 必须同时维护两个互不混淆的状态轴。

### 3.1 NL2SPL structural renderability

回答：当前 artifact 是否足以生成合法 SPL 结构？

```text
renderable when:
  api_name valid
  AND source evidence present
  AND auth grammar-safe or default none
  AND placeholder/schema structured text grammar-safe
  AND functions container grammar-safe
```

这个状态由 NL2SPL 的 IRS、Gate 和 Renderer 负责。

### 3.2 Downstream API contract validity

回答：这个 API contract 是否真实、完整、可供后续执行或部署？

可能涉及：

```text
真实 endpoint
OpenAPI semantic validity
operation/function correspondence
parameter schema
return schema
authentication configuration
provider availability
runtime credentials
```

这些不是 NL2SPL 阶段的最终 authority，应由后续 SPL compiler/API validation layer 负责。

### 3.3 禁止将两个状态合并

错误判断：

```text
schema/functions unknown
=> declaration unrenderable
=> CALL_API cannot render
```

正确判断：

```text
schema/functions unknown but grammar-safe placeholders exist
=> declaration renderable partial
=> CALL_API may render
=> downstream API validation remains pending
```

---

## 4. IRS 语义修正

### 4.1 Slot policy

`API_DECLARATION` slots 应保持以下语义：

| Slot | Required for render | Required for semantic completion | Placeholder allowed | Blocks CALL_API rendering |
|---|---:|---:|---:|---:|
| `api_name` | yes | yes | no | yes |
| `source_evidence` | yes | yes | no | yes |
| `authentication` | no | downstream-dependent | default `<none>` | no |
| `openapi_schema` | no | downstream-dependent | `{}` | no |
| `functions` / `API_IN_SPL` | no | downstream-dependent | `{"functions":[]}` | no |

### 4.2 Placeholder status

必须区分：

```text
invalid shape:
  不是合法 structured text / functions container
  -> blocks rendering

unknown placeholder:
  grammar-safe placeholder，真实 contract 未知
  -> does not block rendering
  -> deferred API validation

known empty:
  authoritative source 或用户明确确认为空
  -> does not block rendering
  -> downstream validator may still apply policy

known present:
  当前 artifact 有结构化内容
  -> does not automatically prove external API correctness
```

`known_present` 也只表示 NL2SPL artifact 中存在内容，不等于外部 API 已验证。

### 4.3 Diagnostic policy

缺少 schema/functions 时，可以产生非阻断诊断，但不能混入 mandatory editable issues：

```text
kind: type_or_contract_ambiguity or deferred_api_validation
required_for: downstream_api_validation
blocks_rendering: false
blocks_call_api_materialization: false
repairability: review_only
presentation_disposition: deferred_validation
```

如果继续使用 `type_or_contract_ambiguity`，必须通过 metadata 明确：

```text
validation_authority = downstream_spl_compiler
nl2spl_placeholder_renderable = true
blocks_nl2spl_rendering = false
```

### 4.4 Completion 术语

为了避免把 NL2SPL completion 与 downstream API validation 混淆，建议把状态命名区分为：

```text
nl2spl_renderable
nl2spl_structurally_complete
api_contract_validation_pending
api_contract_validated
```

NL2SPL 不得自行宣布 `api_contract_validated=true`。

---

## 5. 正确的 Stage authority

### 5.1 Stage 3.25 / ConstructPlan

负责：

```text
识别 source-backed external capability intent
产生 API declaration demand
产生 API call demand
维护 declaration/call pairing
```

不负责生成真实 OpenAPI contract。

### 5.2 Stage 6

负责：

```text
创建或复用 APISpec
解析稳定 API identity
附加 source provenance
填充 default auth
在真实 contract 缺失时生成 grammar-safe placeholders
标记 declaration_status=grammar_minimal_partial
维护 APIMaterializationPlanIR records/bindings
```

Stage 6 不需要等待 SPL Editing 修复才能生成 placeholders。

### 5.3 Stage 7

负责：

```text
根据 API call demand 与 renderable API declaration 生成 CALL_API StepIR
确保 integration_ref 指向已声明 API
```

Stage 7 不应要求 API declaration semantic complete。它只应要求 declaration 对 NL2SPL 来说可渲染。

### 5.4 Stage 9.5 / Gate / Renderer

负责：

```text
校验 declaration grammar shape
校验 CALL_API.integration_ref
保留 renderable partial declaration
保留指向该 declaration 的 CALL_API
渲染 placeholder declaration 和 CALL_API
```

不得因为 `schema_status/functions_status=unknown_placeholder` 删除 API declaration 或 CALL_API。

### 5.5 Downstream SPL compiler/API layer

负责：

```text
真实 OpenAPI semantic validation
API_IN_SPL function contract validation
operation/schema consistency
endpoint/provider/auth validation
runtime/deployment readiness
```

这些错误不应被伪装成 NL2SPL materialization failure。

---

## 6. SPL Editing 中的正确展示

### 6.1 当前 9 与 7 的差异

当前反馈中的 9 个 IRS report rows 包含：

```text
6 missing_handler
2 non-blocking API declaration completion diagnostics
1 grouped worker promotion issue
```

SPL Editing 中的 7 个 editable issues 是：

```text
6 missing_handler
1 worker delegation
```

在本设计边界下，这个 editable count 是合理的。两个 API diagnostics 不应为了凑齐数量而变成 Fix with AI。

### 6.2 推荐 presentation

```text
Editable issues: 7
Deferred validation: 1

Deferred validation
  API contract validation deferred: ApprovedSourceRecipesAPI
  Placeholder schema and function list were emitted so the SPL can render.
  Full API contract validation will run in the downstream SPL compiler.
```

同一个 API declaration 的 `functions` 和 `openapi_schema` 必须分组为一个 deferred validation item，不能显示为两个用户 issue。

### 6.3 Advanced details

Developer mode 可展示：

```text
schema_status: unknown_placeholder
functions_status: unknown_placeholder
declaration_status: grammar_minimal_partial
nl2spl_renderable: true
validation_authority: downstream_spl_compiler
```

### 6.4 不应出现的 UI

```text
Fix with AI: Invent OpenAPI schema
Fix with AI: Generate callable functions
CALL_API unavailable until API contract is complete
```

这些文案会错误地把下游 API validation 变成 NL2SPL 的前置职责。

---

## 7. `repair_affordances` 的正确结论

### 7.1 functions/schema 不需要 mandatory repair affordance

如果目标只是让 API declaration 和 CALL_API 正常渲染，那么：

```text
API_DECLARATION.openapi_schema.repair_affordances = ()
API_DECLARATION.functions.repair_affordances = ()
```

可以继续保持为空。

正确修复点是：

```text
Stage 6 确保 placeholders 存在；
IRS 将 placeholders 视为 renderable partial；
Stage 7 使用 renderability，而不是 semantic completeness；
Gate/Renderer 不删除 partial declaration 或 CALL_API；
Presentation 将 diagnostics 放入 Deferred validation，而不是 Editable issues。
```

### 7.2 何时才需要 repair affordance

只有当产品明确支持“用户主动补充 API metadata”时，才需要可选 affordance。即使如此，其语义也应是：

```text
Enhance API declaration metadata
```

而不是：

```text
Repair API declaration so CALL_API can render
```

可选增强不得改变基础 renderability，也不得成为 CALL_API 的前置条件。

### 7.3 API identity/source evidence 是另一类问题

如果缺少的是：

```text
api_name
source_evidence
```

那么 declaration 确实不可渲染。此时可以单独设计受控 repair affordance，但必须依赖 configured resource、adapter hard fact 或用户明确确认，不能从 placeholder 推导。

这与 functions/schema 的 deferred validation 不是同一问题。

---

## 8. 可选 contract enrichment 设计

本节属于后续增强，不是 CALL_API 渲染闭环的必要条件。

### 8.1 目标

允许用户在 NL2SPL 编辑阶段主动提供：

```text
OpenAPI schema
API_IN_SPL function declarations
auth configuration reference
```

系统只负责规范化、预览、确认和保存这些用户/配置提供的内容。

### 8.2 安全边界

```text
configured contract -> 可直接作为 authoritative input
user-provided contract -> preview + confirmation 后成为 user evidence
LLM -> 只允许 typed normalization，不允许发明 contract facts
```

### 8.3 Stage 6 optional enrichment slice

可选 slice：

```text
stage6.api_declaration_metadata_enrichment.v1
```

职责：

```text
只更新用户选择的 slots
保留 API identity/source provenance
记录 slot-level evidence
不创建 CALL_API StepIR
不改变 unrelated APIs
不把 enrichment 失败转成 NL2SPL rendering failure
```

### 8.4 Preview/Apply

用户确认页展示最终 declaration 片段。Apply 使用 sealed typed plan，不能二次调用 LLM 生成不同 contract。

### 8.5 Presentation category

建议将其作为显式用户操作：

```text
Optional action: Add API contract details
```

而不是默认 `Editable issues` 中的 blocking repair。

---

## 9. 系统性修复方案

### P0：锁定正确 contract

任务：

1. 锁定 minimum renderable APISpec。
2. 锁定 placeholder declaration 可渲染。
3. 锁定 CALL_API 可引用 partial declaration。
4. 锁定 API contract validity 属于 downstream authority。

验收：

```text
测试明确区分 nl2spl_renderable 与 api_contract_validated；
不得用同一 complete flag 表达两个概念。
```

### P1：IRS 与 diagnostic 语义对齐

任务：

1. 确认 grammar-safe placeholder 不 blocks rendering。
2. 将 schema/functions diagnostics 标记为 non-blocking/deferred。
3. 移除错误的 static editable metadata。
4. 保留 invalid placeholder shape 的 blocking diagnostic。

验收：

```text
unknown_placeholder + grammar-minimal declaration -> renderable；
malformed placeholder -> blocked；
functions/schema review diagnostics 不进入 EditableIssueExtractor。
```

### P2：Stage 6 placeholder materialization hardening

任务：

1. 确保所有 source-backed API demands 都产出稳定 placeholder skeleton。
2. 确保 ResourceRegistryIR 与 APIMaterializationPlanIR 一致。
3. 确保 placeholder policy 显式且可审计。
4. 禁止 Stage 6 从 operation text 发明 schema/functions。

验收：

```text
没有 API contract 时仍生成 {}, {"functions":[]}；
placeholder identity/provenance 稳定；
重复 replay 不生成 duplicate API。
```

### P3：Stage 7 CALL_API admission 修正

任务：

1. CALL_API admission 使用 `nl2spl_renderable`。
2. 不要求 API semantic complete。
3. declaration/call pairing 仍必须唯一且稳定。
4. 空 inputs/outputs 在无更强 demand 时合法。

验收：

```text
partial renderable declaration -> CALL_API generated；
missing declaration identity -> CALL_API rejected；
unknown schema/functions 不影响 CALL_API。
```

### P4：Gate 与 Renderer 对齐

任务：

1. Gate 保留 grammar-minimal API declaration。
2. Gate 保留指向该 declaration 的 CALL_API。
3. Renderer 输出 placeholder declaration。
4. Renderer 输出 CALL_API command。

验收：

```text
rendered SPL 同时包含 DEFINE_APIS 与 CALL；
不会因 downstream validation pending 而丢失 CALL_API。
```

### P5：Presentation 与计数修正

任务：

1. 将同一 API 的 functions/schema diagnostics 分为一个 deferred validation item。
2. 分别显示 raw diagnostics、grouped issues、editable issues、review needed counts。
3. 文案明确 downstream validation authority。
4. API deferred validation item 与 worker delegation issue 保持独立。

验收：

```text
Editable issues: 7；
Deferred validation: 1；
API group 不显示 Fix with AI；
worker promotion 仍显示 Worker delegation。
```

### P6：Downstream handoff contract

任务：

1. 在 rendered artifact/manifest 中保留 API validation pending metadata。
2. 定义 downstream compiler 接收 placeholder declaration 的 contract。
3. 确保 downstream diagnostics 能指回 API declaration identity/source evidence。

验收：

```text
NL2SPL 成功不等于 API validated；
downstream compiler 能明确识别 pending contract；
错误归属不会回流成 NL2SPL materialization failure。
```

### P7：Optional enrichment（非阻塞）

任务：

1. 仅在产品需要时实现 metadata enrichment action。
2. 使用 Stage 6 optional slice、preview、confirmation 和 slot evidence。
3. 保证 enrichment availability 不影响基础 rendering。

验收：

```text
关闭 enrichment capability 时 API/CALL 仍可渲染；
用户提供 contract 时可安全保存；
LLM 不发明 endpoint/schema/functions。
```

### P8：真实 E2E 与 final audit

真实场景：

```text
1. source-backed API，无 schema/functions
   -> placeholder declaration rendered
   -> CALL_API rendered
   -> downstream validation pending

2. malformed schema placeholder
   -> NL2SPL blocked with structural diagnostic

3. missing API name/source evidence
   -> declaration and CALL_API blocked

4. API deferred validation item + worker delegation issue 同时存在
   -> 分类、数量和文案准确

5. optional user-provided API contract
   -> preview/confirm/enrich，不影响基础 call admission
```

---

## 10. 测试矩阵

| 场景 | NL2SPL declaration | CALL_API | Presentation | Downstream state |
|---|---|---|---|---|
| name/evidence valid，schema/functions unknown | renderable partial | allowed | Deferred validation | validation pending |
| schema `{}`，functions `[]` | renderable partial | allowed | grouped deferred validation | validation pending |
| schema malformed | blocked | blocked | structural issue | not reached |
| functions container malformed | blocked | blocked | structural issue | not reached |
| API name missing | blocked | blocked | blocking issue | not reached |
| source evidence missing | blocked | blocked | blocking issue | not reached |
| CALL_API ref points to undeclared API | declaration unaffected | blocked | CALL_API issue | not reached |
| configured complete contract | renderable | allowed | no review or optional detail | downstream validates |
| user enriches contract | renderable | allowed | optional confirmed action | downstream validates enriched contract |
| worker promotion also exists | independent | independent | separate worker issue | independent |

---

## 11. 禁止事项

1. 把 schema/functions unknown 当成 API declaration unrenderable。
2. 要求先完成 SPL Editing repair 才允许 CALL_API 显示。
3. 为了消除 review diagnostic 让 LLM 发明 OpenAPI 或 API_IN_SPL。
4. 把 `{}` / `{"functions":[]}` 自动声明成真实 API contract 已验证。
5. 把 downstream API compiler 的责任放回 NL2SPL IRS。
6. 把 non-blocking API diagnostics 混进 Editable issues。
7. 为凑 issue 数量给 functions/schema 增加虚假的 repair affordance。
8. 从 feedback report 或 diagnostic message 重建 API contract。
9. 因 API contract pending 把相关行为降级成 GENERAL_COMMAND。
10. 把 API declaration issue 与 worker delegation issue 合并。
11. optional enrichment 失败时撤销原本可渲染的 placeholder declaration。
12. 用一个 `complete` 字段同时表示 NL2SPL renderability 与真实 API validity。

---

## 12. 最终完成定义

修复完成必须满足：

```text
1. Stage 6 对 source-backed API 自动生成 grammar-safe placeholders。
2. API declaration 在 schema/functions unknown 时仍可渲染。
3. Stage 7 可为该 declaration 生成 CALL_API。
4. Gate 和 Renderer 不因 downstream validation pending 删除 declaration/CALL_API。
5. IRS 只把 malformed structure 视为 render blocker。
6. schema/functions unknown 仅形成 grouped deferred-review 信息。
7. Editable issues 与 Deferred validation 计数清楚分离。
8. API deferred validation item 与 worker delegation issue 保持独立。
9. NL2SPL 不宣称外部 API contract 已验证。
10. downstream SPL compiler/API layer 接管真实 contract validation。
11. optional enrichment 不成为基础 rendering 前置条件。
12. 所有正向、负向和真实 E2E 场景通过。
```

最终正确流程是：

```text
Source-backed API intent
-> grammar-minimal API declaration with placeholders
-> CALL_API materialization
-> NL2SPL structural verification
-> rendered SPL
-> downstream SPL/API contract validation
```

而不是：

```text
Source-backed API intent
-> mandatory AI repair of schema/functions
-> only then render CALL_API
```