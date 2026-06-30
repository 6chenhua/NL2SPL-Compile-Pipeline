# API Definition Full Materialization 实施计划

状态：Approved for implementation after path/dependency corrections。

本文档严格基于以下设计规范制定：

- `docs/design/api_definition_full_materialization_and_irs_design_zh.md`
- `docs/design/api_definition_full_materialization_review_amendments_zh.md`
- `docs/spl_grammar.txt`

实施目标是补齐从 source-backed API/integration intent 到 `API_DECLARATION`、`APISpec`、`CALL_API StepIR`、Gate、Renderer、IRS diagnostics、Provenance、Snapshot 的端到端生命周期。

首轮实施范围仅覆盖 P0-P6 explicit API name vertical slice：

```text
explicit API name + executable API action
  -> API_DECLARATION demand
  -> partial APISpec skeleton
  -> placed direct CALL_API
  -> no GENERAL_COMMAND fallback
  -> ResourceDeclarationGate + ExecutableElementGate
  -> precise IRS diagnostics / feedback / snapshot
```

以下能力不在首轮 R-API-0 到 R-API-6 范围内：

```text
confirmed unnamed integration / inferred API name
approved source recipes -> api_retrieve_approved_sources demo
handoff-backed API 扩展
完整 OpenAPI schema/functions 抽取
API declaration SPL Editing repair strategy
```

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
Stage 2 annotation role contract
  -> source-backed API_DECLARATION/source_evidence annotation
  -> source-backed CALL_API/call_action annotation

ConstructPlan
  -> APIDeclarationDemand
  -> APICallDemand
  -> 只记录需求、pairing、ambiguity，不物化 APISpec/StepIR

Stage 4/5 placement authority
  -> APICallPlacementIR
  -> Stage 4 决定 owner worker / flow
  -> Stage 5 决定 block

Stage 6 API declaration materializer
  -> StructuredTextIR
  -> partial APISpec skeleton
  -> APICallBindingIR / APIMaterializationPlanIR
  -> stage-local API_DECLARATION early report

Stage 7 direct CALL_API materializer
  -> 只消费 bound + placed call demand
  -> 生成最小 CALL_API StepIR
  -> 不生成同 demand GENERAL_COMMAND fallback

Post-normalize IRS
  -> API_DECLARATION authority reports
  -> CALL_API declared_api_ref reports
  -> DiagnosticProjector / DiagnosticConsolidator

ResourceDeclarationGate
  -> RenderableResourceRegistryView
  -> 只读过滤 view，不修改 APISpec、不推断 slot、不生成声明

ExecutableElementGate / ProducerIndex
  -> CALL_API declared_api_ref renderability / producer authority

Stage 11 renderer
  -> 消费 RenderableResourceRegistryView 和 gated StepIR
  -> 只格式化 [DEFINE_APIS:] 与 [CALL ...]
  -> 不 fallback "Api"，不发明 schema/function/auth

Feedback / Provenance / Snapshot
  -> 展示已存在 reports、diagnostics、trace records、artifact 状态
  -> 不重新判断 API 是否存在，不重新执行 IRS
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. P0-P6 只做 explicit API name vertical slice。
2. `integration_hint` 保留为 source evidence role，不新增 IRS construct。
3. `mechanism_status` 内部枚举只允许 `explicit | concrete_unnamed | unknown`；`unknown_mechanism` 只允许出现在 feedback 展示层。
4. `approved source recipes` 不得作为 R-API-0 到 R-API-6 的通过条件。
5. `compile_as_call_api` 是 lowering hint，不是 API declaration source evidence，不注册 IRS construct。
6. `API_DECLARATION` 是独立 ConstructIRS；`APIS` / `[DEFINE_APIS:]` 容器不注册 ConstructIRS。
7. `APIDeclarationDemand`、`APICallDemand`、`APICallPlacementIR`、`APIMaterializationPlanIR` 是 planner/materialization IR，不注册 ConstructIRS。
8. Stage 4/5 是 placement authority；Stage 7 不临时决定 owner worker、flow 或 block。
9. Stage 6 是 API declaration materialization authority；Stage 7 不创建 APISpec。
10. Post-normalize `API_DECLARATION` reports 是 Stage 11 resource render authority；Stage 6 stage-local reports 只能用于 early feedback/debug/审计。
11. ResourceDeclarationGate 输出只读 `RenderableResourceRegistryView`，不得修改 registry 或补 slot。
12. Renderer 不做语义补全；必须删除 `api_name = step.integration_ref or "Api"` 这类 fallback。
13. 已有 `CALL_API` demand 的 action 不得静默 fallback 为 `GENERAL_COMMAND`。
14. `CALL_API.integration_evidence` 只能作为 compatibility alias，不参与新的 completion/render authority。
15. `SpecifyAPIIntegration` 不得被 RepairCatalog 路由到 `API_DECLARATION`，也不能满足其任何 slot。
16. `API_DECLARATION` 初始 `repair_affordances=()`，diagnostic `repairability=review_only`。
17. 不新增 skip / xfail / contract_pending 来掩盖默认路径失败；如确需 pending，必须是后续 P7/P8 明确范围。
18. final-authority diagnostics 必须进入 `compile_diagnostics` / feedback / checkpoint；stage-local diagnostics 必须进入 `stage_local_diagnostics` / checkpoint / early feedback 或 suppressed metadata，只有经过 `DiagnosticConsolidator` 选择后才能进入 final `compile_diagnostics`；任何 diagnostic 都不得只停留在局部 debug log。

---

## 3. LLM / Rule-based 决策约束

本计划默认不允许新增 rule-based semantic fallback。

允许的确定性逻辑仅限：

- 从 Stage 2 已存在的结构化 annotation metadata 读取 explicit API name。
- 对 API name 做 grammar-safe validation / normalization。
- 基于稳定结构化字段生成 demand ID、api ID、step ID。
- 基于 `api_group_id`、annotation ID、demand ID 做 pairing。
- 基于 Stage 4/5 placement artifact 做 presence / status check。
- 基于 registry / reports / gate view 做 declared ref resolution。
- 基于 schema carrier format 做 serializer roundtrip 和 structured-text presence check。

以下行为必须另行设计确认，不得在 R-API-0 到 R-API-6 中实现：

1. 修改 LLM prompt/schema 以抽取 unnamed integration 或 inferred API name。
2. 根据普通动词、标题、关键词、policy mention 推断 API。
3. 从 `approved source recipes` 生成 `api_retrieve_approved_sources`。
4. 从 `compile_as_call_api` 单独生成 APISpec。
5. 生成 OpenAPI schema、URL、function、parameter、return contract。
6. 暴露 API declaration SPL Editing repair strategy。
7. 引入新的 renderer/runtime fallback。
8. 让 LLM 重新判断 ConstructPlan/placement/gate 已决定的结构属性。

如果实现中出现“先用规则兜底跑通 E2E”的倾向，应停止并提交设计确认。

---

## 4. Phase R-API-0：Baseline lock

本阶段只锁定当前失败行为和未来目标缺口，不改变生产输出。

### 4.1 目标

证明当前断点存在，并用测试防止后续实现绕过架构边界：

```text
compile_as_call_api 不生成 APISpec
Stage 7 只从 api_call handoff 生成 CALL_API
API action 会 fallback GENERAL_COMMAND
renderer 当前存在 "Api" fallback
```

### 4.2 可编辑范围

允许新增：

```text
tests/unit/api_materialization/
tests/integration/api_materialization/
docs/implementation/api-definition-full-materialization-implementation-plan.md
```

允许修改：

```text
tests/unit/test_construct_registry.py
tests/unit/test_executable_gate.py
tests/pipeline/stages/test_stage11_child_worker_render.py
tests/unit/compiler/irs/
```

### 4.3 禁止改动

Phase R-API-0 禁止修改生产代码：

```text
src/nl2spl/
```

### 4.4 设计要求

测试应表达 current-gap lock，而不是批准旧行为：

```text
test_renderer_currently_falls_back_to_Api
test_compile_as_call_api_currently_not_consumed_by_stage6
test_stage7_handoff_generated_call_api_requires_api_call_mode
test_stage7_currently_accepts_unbounded_llm_call_api_in_main_worker
test_api_action_currently_can_fallback_general_command
test_worker_candidate_promotion_warning_regression_lock
```

如果现有代码已经部分修复某项，或与初始假设存在行为漂移 (drift)，测试应精确拆解并锁定当前真实行为：
- **Stage 7 行为漂移记录 (Drift Note)**：Stage 7 确定性 handoff 生成器（`_generate_handoff_steps`）无 `mode="api_call"` handoff 时不生成 `CALL_API`；但对于 main worker，LLM 抽取的 `CALL_API` 步骤在 `worker_scoped.py` 中缺乏无 handoff 拦截（拦截仅作用于 `worker.kind == "child"`），导致 main worker 会直接接受未约束的 raw LLM `CALL_API`。R-API-0 分别用 `test_stage7_handoff_generated_call_api_requires_api_call_mode` 和 `test_stage7_currently_accepts_unbounded_llm_call_api_in_main_worker` 锁定了这一真实泄漏断点，R-API-4 将统一对其进行清理与 Placement 校验。

### 4.5 测试计划

新增测试必须覆盖：

1. `CALL_API` step 缺少 `integration_ref` 时 Stage 11 当前 fallback 行为或缺口。
2. demo 中 `compile_as_call_api` decision 不进入 `ResourceRegistryIR.apis`。
3. Stage 7 确定性 handoff 生成路径与 main worker 未约束 LLM `CALL_API` 接收泄漏行为。
4. `worker candidate` 被 `WORKER_PROMOTION` 误诊断的当前行为用 regression fixture 记录。
5. explicit fixture `Retrieve approved sources using SearchAPI.` 当前不能端到端生成 `[CALL SearchAPI]`。

### 4.6 验收标准

Phase R-API-0 通过条件：

1. baseline tests 能稳定复现或锁定当前断点。
2. 测试名称和注释明确标注目标行为，避免把旧 fallback 当成长期规范。
3. 未修改生产代码。
4. 无新增 skip / xfail。

### 4.7 PM 审核清单

审核时必须检查：

1. 是否没有 production diff。
2. 是否覆盖 renderer `Api` fallback。
3. 是否覆盖 `compile_as_call_api -> GENERAL_COMMAND` fallback。
4. 是否覆盖 Stage 7 direct CALL_API 缺失。
5. 是否没有把 P7 inferred-name demo 作为首轮 fixture。

---

## 5. Phase R-API-1：IR / Registry foundation

本阶段只建立数据模型、serializer、registry 和 checker skeleton；不改变默认输出。

### 5.1 目标

为 API declaration lifecycle 建立向后兼容基础：

```text
StructuredTextIR
APISpec backward-compatible extension
APIFunction grammar-aware extension
API_DECLARATION ConstructIRS registry
API_DECLARATION checker skeleton
CALL_API slot migration target shape
```

### 5.2 可编辑范围

允许新增：

```text
src/nl2spl/ir/structured_text_ir.py
src/nl2spl/compiler/irs/checkers/api_declaration.py
tests/unit/compiler/irs/test_api_declaration_registry.py
tests/unit/compiler/irs/test_api_declaration_checker.py
tests/unit/compiler/artifacts/snapshot/test_api_spec_serializers.py
```

允许修改：

```text
src/nl2spl/ir/resource_registry_ir.py
src/nl2spl/ir/__init__.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_resource.py
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/irs/factory.py
src/nl2spl/compiler/irs/frontier.py (扩展 CutlineReason 强类型契约)
src/nl2spl/compiler/irs_prompt_builder.py
tests/unit/test_construct_registry.py
tests/unit/test_irs_prompt_builder.py
tests/fixtures/multi_worker/scenarios.py
```

### 5.3 禁止改动

Phase R-API-1 禁止修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/
src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/producer_index.py
```

### 5.4 设计要求

`StructuredTextIR` 最小模型：

```python
@dataclass
class StructuredTextIR:
    format: Literal["json_object", "structured_text", "raw_text", "empty_placeholder"]
    canonical_text: str
    parsed_value: Any | None = None
```

R-API-1 只要求支持：

```text
json_object
empty_placeholder
```

`APISpec` 扩展必须向后兼容旧构造调用。新增字段必须有安全默认值，且默认值不得把 legacy API 自动标记为 complete。

`API_DECLARATION` registry slots：

```text
api_name
authentication
openapi_schema
functions
source_evidence
```

初始 repair contract：

```text
repair_affordances=()
repairability=review_only
```

`CALL_API` 目标 slots 迁移形态：

```text
api_name
declared_api_ref
call_action
request_bindings
response_binding
```

旧 `integration_evidence` 可保留 compatibility alias，但不得继续作为 completion authority。

### 5.5 测试计划

新增单元测试必须覆盖：

1. `API_DECLARATION` 在 default registry 中存在。
2. `API_DECLARATION` slots、requiredness、renderable_without、missing_diagnostic 符合设计。
3. `API_DECLARATION` 所有 slots 初始 `repair_affordances=()`。
4. RepairCatalog 不生成任何 `API_DECLARATION` entry。
5. `SpecifyAPIIntegration` 仍只对应 `CALL_API` compatibility path，不可 lookup 到 `API_DECLARATION`。
6. `StructuredTextIR(empty_placeholder)` serializer roundtrip。
7. legacy `APISpec(api_name, auth, description, functions)` 构造仍可工作。
8. legacy APISpec 反序列化后 `declaration_status != complete`，schema/functions unknown 或 placeholder。
9. `APIFunction` 旧字段 roundtrip 不丢失，新字段默认值不虚构 URL。

### 5.6 验收标准

Phase R-API-1 通过条件：

1. 新 IR/serializer/registry 测试通过。
2. 现有 APISpec/APIFunction fixtures 不需要大规模重写。
3. 默认 pipeline 输出不变。
4. `API_DECLARATION` checker 不调用 LLM、不修改 IR、不生成 APISpec。
5. 负向测试证明 `SpecifyAPIIntegration` 不能修复或满足 `API_DECLARATION`。
6. `API_DECLARATION` checker 注册后，在没有 ConstructPlan API demands / APIMaterializationPlanIR / APISpec provenance metadata 时，`extract_instances()` 返回空或 legacy-review-only reports，不新增 final blocking diagnostics。

### 5.7 PM 审核清单

审核时必须检查：

1. 是否把 `API_DECLARATION` 作为 grammar construct，而不是 diagnostic host。
2. 是否误把 `APIDeclarationDemand` 注册成 IRS。
3. 是否出现 `unknown_mechanism` 作为内部 enum。
4. 是否给 `API_DECLARATION` 添加了 repair affordance。
5. 是否仍存在 `CALL_API.integration_evidence` 作为唯一 completion authority 的测试。

---

## 6. Phase R-API-2：ConstructPlan + placement only

本阶段只产生 API declaration/call demand 和 placement artifact，不生成 APISpec/StepIR。

### 6.1 目标

建立 source demand 与 executable placement 的上游结构：

```text
APIDeclarationDemand
APICallDemand
APICallPlacementIR
explicit API name annotation pairing
Stage 4/5 placement authority contract
```

### 6.2 可编辑范围

允许新增：

```text
tests/unit/compiler/construct_plan/test_api_demands.py
tests/unit/compiler/construct_plan/test_api_demand_pairing.py
tests/unit/pipeline/stage4_stage5/test_api_call_placement.py
```

允许修改：

```text
src/nl2spl/compiler/annotation_role_contract/registry.py
src/nl2spl/compiler/annotation_role_contract/validator.py
src/nl2spl/compiler/construct_plan/model.py
src/nl2spl/compiler/construct_plan/planner.py
src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_plan.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage4_flow_assembler/
src/nl2spl/pipeline/stages/stage5_block_assembler/
```

### 6.3 禁止改动

Phase R-API-2 禁止修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/
src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 6.4 设计要求

Stage 2 role contract：

```text
api_candidate:
  construct_target = API_DECLARATION
  slot_target = source_evidence
  executable = false

process_step with API action:
  construct_target = CALL_API
  slot_target = call_action
  executable = true
```

R-API-2 不启用 unnamed integration。`integration_hint` 可保留 candidate metadata，但不得形成 confirmed inferred-name demand。

`APIDeclarationDemand` 最小字段：

```text
demand_id
source_span_ids
declaration_annotation_ids
explicit_name_candidates
integration_admission="confirmed" only when explicit name exists
mechanism_status="explicit"
api_group_id
owner_scope="agent_global"
```

`APICallDemand` 最小字段：

```text
demand_id
source_span_ids
call_annotation_ids
declaration_demand_id
api_group_id
action_text
owner_worker_id
```

`APICallPlacementIR` 必须由 Stage 4/5 写入：

```text
call_demand_id
owner_worker_id
flow_ref
block_ref
status = placed | unresolved | ambiguous
source_span_ids
reason
```

首轮 placement 必须采用 deterministic placement projector：

```text
Stage 4/5 正常产生 worker/flow/block plan
  -> deterministic placement projector
  -> 根据已解析的 worker/flow/block ownership 与 ConstructPlan demand 生成 APICallPlacementIR
```

R-API-2 不新增 Stage 4/5 LLM 语义判断，不扩展 prompt/schema 要求 LLM 显式输出 API placement。无法从已解析 ownership 稳定映射时，`status="unresolved"` 或 `status="ambiguous"`，并保留 reason；不得让 Stage 7 临时放置。

### 6.5 测试计划

新增测试必须覆盖：

1. `Retrieve approved sources using SearchAPI.` 产生 declaration demand + call demand。
2. declaration demand 含 `explicit_name_candidates=["SearchAPI"]`。
3. call demand 通过 `api_group_id` 绑定 declaration demand。
4. 同 span 的非 API action 不被 API call demand 吞掉。
5. 多 API / 多 call pairing ambiguity 不静默选第一个。
6. `approved source recipes` 在 R-API-2 不产生 confirmed inferred demand。
7. placement unresolved/ambiguous 保留 artifact 和 reason。
8. ConstructPlan serializer roundtrip 保留 API demands。
9. deterministic placement projector 不调用 LLM、不解析 raw NL，只消费已结构化 ownership/demand。

### 6.6 验收标准

Phase R-API-2 通过条件：

1. ConstructPlan 只产出 demand，不产出 APISpec/StepIR。
2. Stage 4/5 产出 placement，但 Stage 7 不消费。
3. P7 inferred-name fixture 不作为通过条件。
4. 无 renderer/output 行为变化。
5. 未新增 Stage 4/5 prompt/schema semantic placement 字段。

### 6.7 PM 审核清单

审核时必须检查：

1. `integration_hint` 是否被误注册为 construct。
2. `APICallPlacementIR` 是否由 Stage 7 创建；如果是，拒绝。
3. demand ID 是否使用稳定结构字段，而不是列表序号。
4. pairing ambiguity 是否 diagnostic-ready，而不是自动猜测。
5. `mechanism_status` 是否只出现允许 enum。
6. placement 是否由 deterministic projector 从结构化 ownership 生成，而不是由 LLM 新语义判断生成。

---

## 7. Phase R-API-3：Stage 6 explicit-name skeleton

本阶段只支持 explicit API name，生成 partial APISpec skeleton 和 binding plan。

### 7.1 目标

实现 Stage 6 deterministic API declaration materializer：

```text
APIDeclarationDemand(explicit SearchAPI)
  -> APISpec(api_name="SearchAPI", partial_skeleton)

APICallDemand + APISpec
  -> APICallBindingIR(status="bound")
```

### 7.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/api_materializer.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/api_name_resolver.py
tests/unit/pipeline/stage6/test_api_materializer_explicit.py
tests/unit/pipeline/stage6/test_api_materialization_plan.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/irs/checkers/api_declaration.py
src/nl2spl/compiler/irs/factory.py
src/nl2spl/compiler/artifacts/snapshot/serialization/
```

### 7.3 禁止改动

Phase R-API-3 禁止修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/pipeline/executable_gate.py
```

### 7.4 设计要求

Stage 6 新输入：

```text
Resource extraction context
ConstructPlan
WorkerPlanIR lowering decisions as context only
```

Stage 6 新输出：

```text
ResourceRegistryIR.apis += APISpec partial skeleton
APIMaterializationPlanIR
stage-local API_DECLARATION satisfaction reports
stage-local diagnostics for debug/early feedback only
```

`APIMaterializationPlanIR` 的中间产物落点必须固定为：

```python
intermediate["api_materialization_plan"] = api_materialization_plan
intermediate["api_materialization_plan_payload"] = api_materialization_plan.to_payload()
```

checkpoint/snapshot 应优先持久化 deterministic payload，不直接依赖 mutable runtime object。

Partial skeleton 默认：

```text
auth = "none"
auth_status = "compiler_default_none"
openapi_schema = StructuredTextIR(format="empty_placeholder", canonical_text="{}")
schema_status = "unknown_placeholder"
functions = []
functions_status = "unknown_placeholder"
declaration_status = "partial_skeleton"
name_status = "explicit_source_name" or "normalized_explicit_name"
origin = "source_backed"
```

Stage 6 不得：

```text
从 compile_as_call_api 单独生成 APISpec
生成 inferred name
生成 schema/functions/URL
把 stage-local report 作为 render authority
```

### 7.5 测试计划

新增测试必须覆盖：

1. explicit `SearchAPI` demand 生成 partial APISpec skeleton。
2. invalid but normalizable explicit name 生成 normalized name 并保留 original metadata。
3. 无 explicit name 的 demand 在 R-API-3 unresolved。
4. `compile_as_call_api` without declaration demand 不生成 APISpec。
5. duplicate compatible declaration merge 到同一 APISpec。
6. conflicting explicit declaration 进入 conflict/unresolved diagnostic-ready 状态。
7. `APICallBindingIR` status `bound/unresolved/ambiguous` 正确。
8. Stage-local API_DECLARATION report 只写 intermediate，不被 Stage 11 使用。
9. `api_materialization_plan_payload` deterministic，roundtrip 后 ID/order/status 不漂移。

### 7.6 验收标准

Phase R-API-3 通过条件：

1. Stage 6 能为 explicit fixture 生成 APISpec skeleton。
2. Stage 6 不改变最终 SPL 输出。
3. stage-local report 带 source spans / demand IDs / construct path。
4. `approved source recipes` 仍不生成 APISpec。
5. 无新增 LLM prompt/schema requirement。
6. intermediate 中存在 deterministic `api_materialization_plan_payload`。

### 7.7 PM 审核清单

审核时必须检查：

1. name resolver 是否只处理 explicit name。
2. `StructuredTextIR` 是否被正确使用，而不是硬编码 dict-only。
3. Stage 6 是否把 `{}` / empty functions 标记为 unknown placeholder，而非 complete。
4. 是否把 `compile_as_call_api` 当 source evidence。
5. APIMaterializationPlanIR 是否未注册 IRS。

---

## 8. Phase R-API-4：Stage 7 direct CALL_API

本阶段只消费 bound + placed + explicit-name API binding，生成最小 direct CALL_API。

### 8.1 目标

实现 direct CALL_API materialization：

```text
APICallDemand
AND APICallBindingIR(status="bound")
AND APICallPlacementIR(status="placed")
AND APISpec exists
  -> StepIR(command_type="CALL_API", integration_ref="SearchAPI")
```

并禁止同 demand `GENERAL_COMMAND` fallback。

### 8.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
tests/unit/pipeline/stage7/test_direct_call_api_materializer.py
tests/unit/pipeline/stage7/test_call_api_no_general_command_fallback.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/ir/step_ir.py
src/nl2spl/compiler/irs/checkers/step.py
```

### 8.3 禁止改动

Phase R-API-4 禁止修改：

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/pipeline/resource_declaration_gate.py
```

如果 `resource_declaration_gate.py` 尚不存在，本阶段也不得新增。

### 8.4 设计要求

Stage 7 输入必须包含：

```text
ConstructPlan API demands
APIMaterializationPlanIR call_bindings
APICallPlacementIR
ResourceRegistryIR.apis
```

Stage 7 不得包含：

```text
raw API name inference
APISpec creation
flow/block placement decision
renderer fallback
```

最小 StepIR metadata：

```text
origin = source_backed
construct_demand_ids = [api_call_demand_id]
api_id = ...
declaration_demand_id = ...
api_binding_id = ...
placement_ref = ...
```

去重规则：

```text
same call_demand_id => at most one primary CALL_API StepIR
same source span but different annotation/demand => may produce separate command
```

### 8.5 测试计划

新增测试必须覆盖：

1. explicit fixture 生成 `CALL_API` StepIR，`integration_ref="SearchAPI"`。
2. `inputs=[]`、`outputs=[]` 时最小 CALL_API 合法。
3. binding unresolved 不生成 CALL_API，也不生成同 demand GENERAL_COMMAND。
4. placement unresolved/ambiguous 不生成 CALL_API，也不 fallback GENERAL_COMMAND。
5. 同 span API call + provenance action：API call 生成 CALL_API，provenance 仍可生成 GENERAL_COMMAND。
6. LLM 返回同 demand GENERAL_COMMAND 时被删除或拒绝，并记录 warning/diagnostic。
7. handoff-backed path 不被本阶段改写。

### 8.6 验收标准

Phase R-API-4 通过条件：

1. Stage 7 能生成 direct `CALL_API` StepIR。
2. 无 APISpec 生成逻辑进入 Stage 7。
3. 不存在同 demand `GENERAL_COMMAND` fallback。
4. 未修改 renderer。
5. 同 demand GENERAL_COMMAND sanitation 有 traceable warning/diagnostic，不静默删除。

### 8.7 PM 审核清单

审核时必须检查：

1. Stage 7 是否根据 raw text 推断 API name。
2. Stage 7 是否创建 placement。
3. 去重是否使用 demand/annotation identity，而不是整个 span ID。
4. unresolved binding 是否被隐藏成 GENERAL_COMMAND。
5. handoff-backed CALL_API 现有测试是否仍通过。

### 8.8 Warning / diagnostic authority

当 Stage 7 删除或拒绝 LLM 返回的同 demand `GENERAL_COMMAND` 时，必须记录 stage-local sanitation diagnostic 或 normalization warning：

```text
target_ref = api_call_demand:<id>
kind = stage7_sanitized_general_command_fallback
blocks_rendering = false
blocks_completion = false
```

只有当该 fallback 是唯一 materialization attempt 且 CALL_API demand 未被成功物化时，才允许由后续 authority 把该 demand 诊断为 incomplete/blocking。R-API-4 的 sanitation warning 本身不得替代 `CALL_API` / `API_DECLARATION` IRS diagnostics。

---

## 9. Phase R-API-5：Gates + renderer cleanup

本阶段引入 resource declaration gate，收紧 executable gate，删除 renderer fallback。

### 9.1 目标

建立 render authority：

```text
post-normalize API_DECLARATION authority reports
  -> ResourceDeclarationGate
  -> RenderableResourceRegistryView
  -> Stage 11 [DEFINE_APIS:]

CALL_API StepIR + declared_api_ref
  -> ExecutableElementGate
  -> Stage 11 [CALL SearchAPI]
```

### 9.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/resource_declaration_gate.py
tests/unit/pipeline/test_resource_declaration_gate.py
tests/unit/pipeline/test_call_api_declared_ref_gate.py
```

允许修改：

```text
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/producer_index.py
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/compiler/irs/checkers/post_normalize.py
src/nl2spl/compiler/irs/checkers/api_declaration.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/block_renderer.py
tests/pipeline/stages/test_stage11_child_worker_render.py
tests/unit/test_executable_gate.py
tests/unit/test_producer_index.py
```

### 9.3 禁止改动

Phase R-API-5 禁止修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/api_materializer.py
src/nl2spl/pipeline/stages/stage7_step_extractor/api_call_materializer.py
```

除非是为了适配 gate input/output signature，且不能改变 materialization semantics。

### 9.4 设计要求

`ResourceDeclarationGateInput`：

```text
resources: ResourceRegistryIR
api_reports: tuple[ConstructSatisfactionReport, ...]
```

`api_reports` 必须来自 post-normalize `API_DECLARATION` authority reports。

`ResourceDeclarationGateResult`：

```text
renderable_resources: RenderableResourceRegistryView
render_infos: tuple[ResourceRenderInfo, ...]
diagnostics: tuple[CompileDiagnostic, ...]
```

Gate 不得：

```text
修改 APISpec
推断 missing slot
生成 API declaration
消费 Stage 6 stage-local report 作为 render authority
```

R-API-5 必须前移最小 post-normalize `API_DECLARATION` report extraction，作为生产路径切换到 `RenderableResourceRegistryView` 的前置条件。最小能力仅包括：

```text
extract demanded/materialized API_DECLARATION instances from structured IR
check api_name / source_evidence / authentication / openapi_schema / functions presence/status
mark partial skeleton as renderable but incomplete
fill construct_path / frontier_status / cutline_reason / source_span_ids / related_edges
emit ConstructSatisfactionReport
```

R-API-5 不负责 feedback wording、trace graph、snapshot E2E 或完整 diagnostic presentation；这些留给 R-API-6。

Renderer 必须删除：

```python
step.integration_ref or "Api"
```

### 9.5 测试计划

新增测试必须覆盖：

1. post-normalize report satisfied/partial renderable 时 API 进入 `RenderableResourceRegistryView.apis`。
2. missing `api_name/source_evidence` 阻止 API declaration rendering。
3. Stage 6 stage-local report 不能让 API 进入 renderable view。
4. `CALL_API` integration_ref 必须 resolve 到 gate-approved APISpec。
5. undeclared `CALL_API` 阻止 render 和 completion。
6. renderer 对缺失 integration_ref 不输出 `Api`。
7. `[DEFINE_APIS:]` 只在至少一个 gate-approved API 时输出。
8. no-output minimal CALL_API 不产生 ProducerIndex producer，但合法。
9. CALL_API with output 只有 gate pass + output refs valid 才成为 producer。
10. 最小 post-normalize `API_DECLARATION` report extraction 存在，且 production Stage 11 切换不依赖 Stage 6 local reports。
11. ProducerIndex 只接受 gated/renderable executable step view 或显式 gate pass metadata，不得直接通过 `ResourceRegistryIR.apis` 判断 CALL_API producer 可用。

### 9.6 验收标准

Phase R-API-5 通过条件：

1. Stage 11 只消费 `RenderableResourceRegistryView`。
2. Renderer fallback `Api` 被删除。
3. ExecutableElementGate 校验 `declared_api_ref`。
4. ProducerIndex 不把未声明 CALL_API 当 producer。
5. Stage 6 stage-local reports 不具备 render authority。
6. 最小 post-normalize `API_DECLARATION` authority reports 已可供 ResourceDeclarationGate 消费。
7. ProducerIndex 依赖 gate result / gate pass metadata，不重新判断 API renderability。

### 9.7 PM 审核清单

审核时必须检查：

1. `ResourceDeclarationGate` 是否只读。
2. Gate 是否误用 stage-local reports。
3. Renderer 是否仍存在 `"Api"` fallback。
4. ExecutableElementGate 是否依赖 IRS runner/projector；不应耦合。
5. ProducerIndex 是否绕过 Gate 自己发明 API renderability。
6. 生产路径切换 Stage 11 前，是否已有最小 post-normalize API_DECLARATION reports。

---

## 10. Phase R-API-6：Diagnostics / provenance / snapshot E2E

本阶段完成 post-normalize authority、diagnostic projection、feedback、trace、snapshot 和 E2E。

### 10.1 目标

让首轮 explicit API name vertical slice 可审计、可持久化、可诊断：

```text
Retrieve approved sources using SearchAPI.
  -> [DEFINE_APIS:] SearchAPI <none> {} {"functions":[]}
  -> [CALL SearchAPI]
  -> API_DECLARATION partial diagnostics
  -> CALL_API declared_api_ref satisfied
  -> TraceRecords
  -> Snapshot roundtrip
```

### 10.2 可编辑范围

允许新增：

```text
tests/integration/api_materialization/test_explicit_api_name_vertical_slice.py
tests/integration/api_materialization/test_api_materialization_snapshot_roundtrip.py
tests/unit/compiler/irs/test_api_declaration_post_normalize.py
tests/unit/compiler/diagnostics/test_api_declaration_projection.py
```

允许修改：

```text
src/nl2spl/compiler/irs/checkers/post_normalize.py
src/nl2spl/compiler/irs/checkers/api_declaration.py
src/nl2spl/compiler/diagnostics/
src/nl2spl/pipeline/provenance.py
src/nl2spl/compiler/feedback_report_renderer.py
src/nl2spl/compiler/report_renderer.py
src/nl2spl/compiler/diagnostic_consolidator.py
src/nl2spl/compiler/artifacts/snapshot/
src/nl2spl/pipeline/orchestrator.py
examples/output/demo/
```

### 10.3 禁止改动

Phase R-API-6 禁止实现：

```text
inferred API name
approved source recipes demo as pass condition
handoff-backed API extension beyond existing behavior
API declaration repair strategy
full OpenAPI schema/functions extraction
```

### 10.4 设计要求

R-API-6 假设 R-API-5 已经具备最小 post-normalize `API_DECLARATION` report extraction。本阶段只加固 projection、diagnostic consolidation、feedback、provenance、snapshot 和 E2E。

Post-normalize `API_DECLARATION` authority reports 在本阶段必须进一步保证：

```text
projected diagnostics contain irs_ref metadata
stage-local and post-normalize diagnostics are deduplicated by DiagnosticConsolidator
partial skeleton diagnostics are primary/review_only where appropriate
CALL_API declared_api_ref alias/context diagnostics are grouped with API_DECLARATION primary diagnostics
```

Diagnostic projection：

```text
API_DECLARATION missing schema/functions => primary, review_only, blocks_completion
CALL_API declared_api_ref issue => alias/context as appropriate
compile_as_call_api => context only
```

TraceRecords 至少包含：

```text
source span -> APIDeclarationDemand
source span -> APICallDemand
APIDeclarationDemand -> APISpec
APICallDemand -> APICallBindingIR
APICallPlacementIR -> CALL_API StepIR
CALL_API StepIR -> APISpec
```

Snapshot 必须 roundtrip：

```text
StructuredTextIR
APISpec status fields
API demands
APICallPlacementIR
APIMaterializationPlanIR
RenderableResourceRegistryView if persisted
diagnostic irs_ref metadata
```

### 10.5 测试计划

新增测试必须覆盖：

1. explicit E2E 输出包含 `[DEFINE_APIS:]` 和 `[CALL SearchAPI]`。
2. partial APISpec skeleton renderable，但 completion blocked。
3. feedback 展示 API declaration primary diagnostic，不出现 worker promotion invocation hint。
4. `CALL_API.declared_api_ref` satisfied 时不产生 undeclared diagnostic。
5. undeclared call 产生 alias diagnostic，阻止 rendering/completion。
6. `irs_ref` metadata 包含 construct type、id、slot、authority。
7. TraceRecords 可从 source span 追到 APISpec 和 StepIR。
8. snapshot roundtrip 后 gate/render 结果一致。
9. `SpecifyAPIIntegration` 负向测试仍通过。
10. P7 fixture `approved source recipes` 不作为 R-API-6 pass condition。

### 10.6 验收标准

Phase R-API-6 通过条件：

1. explicit vertical slice E2E 通过。
2. API declaration diagnostics 进入 compile diagnostics、feedback report、checkpoint。
3. post-normalize reports 是 ResourceDeclarationGate 唯一 authority input。
4. Snapshot roundtrip 不把 partial skeleton 升级为 complete。
5. 没有新增 skip / xfail。
6. stage-local diagnostics 未经 DiagnosticConsolidator 选择不得进入 final `compile_diagnostics`。

### 10.7 PM 审核清单

审核时必须检查：

1. 是否仍出现 `WORKER_PROMOTION.promotion_invocation_point` 诊断误报给 `compile_as_call_api`。
2. feedback 是否重新解析 raw text；不允许。
3. TraceRecords relation 是否区分 direct/normalized/inferred/user_confirmed_repair；R-API-6 只应出现 direct/normalized。
4. snapshot defaults 是否误标 complete。
5. demo 更新是否把 P7 inferred-name 作为首轮验收。

---

## 11. Decision Gate D-API-7：Inferred name / unnamed integration

### 11.1 目标

确认是否进入 P7：

```text
confirmed unnamed integration
  -> deterministic inferred API name
  -> unknown mechanism diagnostics
```

### 11.2 可选方案

允许提交但必须评审确认的方案包括：

```text
方案 A：只支持明确 connector/tool/service noun phrase，不支持 policy phrase。
方案 B：允许 approved source recipes，但 completion blocked 且 feedback unknown_mechanism。
方案 C：继续禁止所有 unnamed integration，只保留 candidate diagnostics。
```

推荐方案是 B，但必须有强 admission gate 和 negative fixtures。

### 11.3 必须明确的问题

方案确认文档必须回答：

1. 哪些结构化 evidence 可把 `integration_hint` 从 candidate 升级为 confirmed。
2. `mechanism_status=unknown` 如何进入 feedback，但不污染内部 enum。
3. inferred name 的确定性算法、冲突 suffix 和 source digest。
4. 普通 retrieval/policy-only mention 的负向样例。
5. P7 是否允许生成 `api_retrieve_approved_sources`。

### 11.4 验收标准

该决策门禁通过条件：

1. 设计文档补充 P7 admission rules。
2. negative tests 先行。
3. PM 明确批准后方可进入 P7。

---

## 12. Decision Gate D-API-8：Handoff-backed API / full schema / repair strategy

### 12.1 目标

确认是否进入 P8：

```text
handoff-backed API 扩展
完整 OpenAPI schema/functions extraction
API declaration SPL Editing repair strategy
```

### 12.2 可选方案

允许提交但必须评审确认的方案包括：

```text
方案 A：先做 handoff-backed API 与 direct CALL_API 统一 gate。
方案 B：先做 schema/functions structured extraction，但不暴露 repair。
方案 C：先设计 api_declaration.complete_contract.v1 repair strategy，再实现 repair slice。
```

不推荐在同一 PR 中同时做 A/B/C。

### 12.3 必须明确的问题

方案确认文档必须回答：

1. handoff-backed API 与 direct CALL_API 的共同 slots 与差异 slots。
2. OpenAPI schema/functions 的来源 authority、schema format 和 anti-fabrication rules。
3. repair strategy 的 construct closure、stage slices、preview/apply、Lane B verification。
4. TargetResolver / SelectableRefSet / RepairEvidencePacket 是否齐备。
5. 如何防止 `SpecifyAPIIntegration` 被复用为 API declaration repair。

### 12.4 验收标准

该决策门禁通过条件：

1. 有独立设计文档。
2. 有负向 contract tests。
3. PM 明确批准后方可进入 P8。

---

## 13. 端到端验收场景

最终必须具备以下 E2E 或高保真集成覆盖。

1. **Explicit API name minimal call**
   - 输入：`Retrieve approved sources using SearchAPI.`
   - Stage 2 产生 declaration + call annotations。
   - ConstructPlan 产生 declaration + call demands。
   - Stage 4/5 placement status 为 `placed`。
   - Stage 6 生成 partial APISpec skeleton。
   - Stage 7 生成 `CALL_API` StepIR。
   - Stage 11 输出 `[DEFINE_APIS:]` 和 `[CALL SearchAPI]`。
   - completion blocked by partial schema/functions diagnostics。

2. **Explicit API name plus same-span provenance action**
   - 输入：`Retrieve approved sources using SearchAPI and maintain provenance.`
   - API retrieval 生成 CALL_API。
   - provenance action 保留 GENERAL_COMMAND。
   - 不出现 duplicate retrieval GENERAL_COMMAND。

3. **Unresolved declaration**
   - 输入有 CALL_API action demand，但无 explicit API name。
   - R-API-0 到 R-API-6 不生成 APISpec。
   - 不 fallback GENERAL_COMMAND。
   - 产生 API declaration/call binding diagnostic。

4. **Renderer fallback removed**
   - 构造缺少 `integration_ref` 的 CALL_API。
   - Stage 11 不输出 `[CALL Api]`。
   - Gate/diagnostic 阻止 render。

5. **ResourceDeclarationGate authority**
   - 只有 Stage 6 local report，无 post-normalize authority report。
   - API 不进入 `RenderableResourceRegistryView`。
   - Stage 11 不渲染该 API。

6. **RepairCatalog negative**
   - Registry 同时包含 `CALL_API` compatibility alias 和 `API_DECLARATION`。
   - `SpecifyAPIIntegration` 只 lookup 到 CALL_API side。
   - API_DECLARATION 无 repair entries。

7. **Snapshot roundtrip**
   - 保存 explicit API skeleton + call demand + binding + step。
   - 反序列化后 rerun gate/render。
   - 输出和 diagnostics 不漂移，不把 partial 变 complete。

8. **P7 fixture remains out of scope**
   - 输入：`Retrieve them using approved source recipes.`
   - 在 R-API-6 前不要求输出 `api_retrieve_approved_sources`。
   - 如果产生 candidate diagnostics，必须标记 out-of-scope / not materialized。

---

## 14. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐最终设计文档和修订文档。
2. 是否扩大到 P7/P8 范围。
3. 是否新增未确认的 LLM prompt/schema 改动。
4. 是否新增未确认的 rule-based semantic fallback。
5. 是否把 route role、planner IR、diagnostic kind 注册成 IRS construct。
6. 是否让 IRS checker 修改 IR、生成 construct、调用 LLM 或直接创建 CompileDiagnostic。
7. 是否让 Stage 7 创建 APISpec 或 placement。
8. 是否让 renderer / normalizer / gate 补造 API name、schema、function、auth。
9. 是否仍存在 `step.integration_ref or "Api"`。
10. 是否存在同 call demand 的 GENERAL_COMMAND fallback。
11. 是否误用 Stage 6 local report 作为 Stage 11 render authority。
12. 是否把 `CALL_API.integration_evidence` 当新的 completion authority。
13. 是否把 `SpecifyAPIIntegration` 路由到 `API_DECLARATION`。
14. 是否给 `API_DECLARATION` 添加了未经批准的 repair affordance。
15. 是否 final-authority diagnostics 都进入 compile diagnostics、feedback、checkpoint。
15a. 是否区分 final-authority diagnostics 与 stage-local diagnostics，避免 early IRS 报告污染 final `compile_diagnostics`。
16. 是否 snapshot 默认值把 unknown/partial 静默升级为 complete。
17. 是否 demand/placement/binding IDs 使用稳定结构字段。
18. 是否存在 truthiness 把 `None`、空列表、空 schema 误当 satisfied 的代码。
19. 是否新增 skip / xfail / weak assertion。
20. 是否更新过期文档、注释和 fixture 名称，避免旧设计误导实现。

---

## 15. 阶段完成顺序

推荐顺序：

```text
R-API-0  Baseline lock
R-API-1  IR / Registry foundation
R-API-2  ConstructPlan + placement only
R-API-3  Stage 6 explicit-name skeleton
R-API-4  Stage 7 direct CALL_API
R-API-5  Gates + renderer cleanup
R-API-6  Diagnostics / provenance / snapshot E2E
D-API-7  Inferred name / unnamed integration decision gate
D-API-8  Handoff-backed API / full schema / repair strategy decision gate
```

依赖关系：

- R-API-0 可立即开工。
- R-API-1 必须在任何 runtime materialization 前完成。
- R-API-2 必须在 R-API-3/R-API-4 前完成，因为后者只能消费 demand/placement。
- R-API-3 必须在 R-API-4 前完成，因为 CALL_API 必须绑定已声明 API。
- R-API-5 必须在 R-API-6 前完成，因为 E2E render authority 依赖 gate view。
- D-API-7 之前不得实现 inferred name。
- D-API-8 之前不得实现 handoff-backed API 扩展、完整 schema/functions 或 API declaration repair strategy。

---

## 16. 首轮交付边界

R-API-0 到 R-API-6 完成后，允许宣称的能力仅限：

```text
显式 API 名称 + 可执行 API action
  -> source-backed partial API declaration
  -> minimal direct CALL_API
  -> grammar-conformant partial SPL
  -> precise diagnostics and snapshot provenance
```

不得宣称：

```text
自动识别 unnamed integration
自动生成 OpenAPI schema
自动生成 functions
自动修复 API declaration
完整支持 handoff-backed API lifecycle
```

