# API 完整物化设计：架构评审规范性修订

状态：已批准设计的规范性修订；实现时优先于原设计中的冲突表述。

本文记录对 `api_definition_full_materialization_and_irs_design_zh.md` 的收紧项。后续实现计划必须同时满足原设计与本文；冲突时以本文为准。

## 1. Integration evidence admission

保留单一 `integration_hint` semantic role，不新增 IRS construct。通过 typed metadata 区分：

```text
integration_admission = candidate | confirmed
mechanism_status = explicit | concrete_unnamed | unknown
```

- `candidate` 只进入需求候选、诊断上下文和审计记录，不能生成 inferred name 或 APISpec。
- `confirmed` 才能形成正式 `APIDeclarationDemand`，并在严格条件下生成 inferred partial skeleton。
- `unknown` 是内部 IR 枚举值；feedback 展示层可渲染为用户可读标签 `unknown_mechanism`。
- `approved source recipes` 不属于 P0-P6 explicit-name vertical slice；进入 P7 inferred-name slice 后可标记 confirmed，但必须同时设置 `mechanism_status=unknown`；feedback 显示 `inferred_from_source + unknown_mechanism`，completion blocked。
- 普通 retrieval 动词和 policy-only mention 最多是 candidate。

## 2. OpenAPI schema carrier

`APISpec.openapi_schema` 不固定为 `dict[str, Any]`。采用：

```python
@dataclass
class StructuredTextIR:
    format: Literal[
        "json_object",
        "structured_text",
        "raw_text",
        "empty_placeholder",
    ]
    canonical_text: str
    parsed_value: Any | None = None


APISpec.openapi_schema: StructuredTextIR
```

MVP 只要求支持 `json_object` 与 `empty_placeholder`，但 serializer 和 IRS 不得把 dict 当作唯一长期模型。

## 3. Stage 4/5 placement contract

`APICallDemand` 是 executable demand。Stage 4/5 必须在 Stage 7 前确定 placement：

```python
@dataclass
class APICallPlacementIR:
    call_demand_id: str
    owner_worker_id: str
    flow_ref: str
    block_ref: str
    status: Literal["placed", "unresolved", "ambiguous"]
    source_span_ids: list[str]
    reason: str | None = None
```

Authority：

- Stage 4 决定 owner worker 与 flow。
- Stage 5 决定 block placement。
- Stage 7 只消费 `status="placed"` 的 placement，不临时决定 flow/block。
- unresolved/ambiguous placement 投影精确诊断，禁止 fallback `GENERAL_COMMAND`。
- 去重按 demand/annotation identity，不按整个 span ID；同 span 的非 API action 仍可进入普通 step。

## 4. ResourceDeclarationGate artifact contract

```python
@dataclass(frozen=True)
class ResourceDeclarationGateInput:
    resources: ResourceRegistryIR
    api_reports: tuple[ConstructSatisfactionReport, ...]


@dataclass(frozen=True)
class RenderableResourceRegistryView:
    variables: tuple[VariableSpec, ...]
    files: tuple[FileSpec, ...]
    types: tuple[TypeSpec, ...]
    apis: tuple[APISpec, ...]


@dataclass(frozen=True)
class ResourceDeclarationGateResult:
    renderable_resources: RenderableResourceRegistryView
    render_infos: tuple[ResourceRenderInfo, ...]
    diagnostics: tuple[CompileDiagnostic, ...]
```

`api_reports` 必须来自 post-normalize `API_DECLARATION` authority reports。Stage-local Stage 6 reports 只能用于 early feedback、debug 和中间产物审计，不得作为 Stage 11 resource render authority。

Stage 11 只能消费 `RenderableResourceRegistryView`。Gate 不修改 APISpec、不推断 slot、不生成声明。

## 5. CALL_API IRS migration

目标 slots：

```text
api_name
declared_api_ref
call_action
request_bindings
response_binding
```

迁移规则：

- `integration_evidence` 仅保留为 snapshot/diagnostic compatibility alias。
- compatibility alias 不参与新的 completion/render authority。
- `declared_api_ref` 必须 resolve 到 gate-approved APISpec。
- 有 required request parameter demand 而 binding 缺失时，阻止 rendering 和 completion。
- 有 required response/output demand 而 binding 缺失时，阻止 completion；CALL grammar 本身仍可渲染。

## 6. SPL Editing 隔离

- `API_DECLARATION` 所有初始 slots 均 `repair_affordances=()`、`repairability=review_only`。
- 当前 `CALL_API.integration_evidence -> SpecifyAPIIntegration` 只能修改 CALL_API step-side integration reference。
- `SpecifyAPIIntegration` 不能满足或 alias `API_DECLARATION` 的任何 slot。
- API declaration repair 只有在独立 `api_declaration.complete_contract.v1` strategy、Stage 6 slice、preview/apply 和 Lane B verification 全部注册后才能暴露。
- 增加负向 contract test，确保 RepairCatalog 不把旧 affordance 路由到 `API_DECLARATION`。

## 7. Vertical slice 实施顺序

第一条实现切片严格限定为：

```text
explicit API name + executable API action
-> API_DECLARATION demand
-> partial APISpec skeleton
-> placed direct CALL_API
-> no GENERAL_COMMAND fallback
-> ResourceDeclarationGate + ExecutableElementGate
-> precise IRS diagnostics
```

阶段：

1. P0：锁定当前失败行为与 renderer `Api` fallback。
2. P1：向后兼容扩展 APISpec/serializer，并增加 API_DECLARATION registry/checker；不改变输出。
3. P2：ConstructPlan 增加 declaration/call demand 和 Stage 4/5 placement；只产出计划。
4. P3：Stage 6 只实现 explicit name 的 deterministic partial skeleton。
5. P4：Stage 7 只实现 bound、placed direct CALL_API，并禁止同 demand fallback。
6. P5：ResourceDeclarationGate、declared API gate 与 renderer fallback 删除。
7. P6：post-normalize IRS、diagnostics、feedback、provenance、snapshot E2E。
8. P7：另行启用 confirmed unnamed integration/inferred name。
9. P8：另行启用 handoff-backed API、完整 schema/functions 和 repair strategy。

任何阶段不得为了让 E2E 提前通过而跨 authority 生成下游 IR。

## 8. Fixture 与 demo 输出修正

P0-P6 vertical slice fixture 必须使用 explicit API name，避免为了跑通 demo 提前实现 inferred name：

```text
Retrieve approved sources using SearchAPI.
```

对应最低合法输出为：

```spl
[DEFINE_APIS:]
    "Retrieve approved sources using SearchAPI." SearchAPI <none>
    {}
    {"functions":[]}
[END_APIS]

COMMAND-n [CALL SearchAPI]
```

P7 inferred-name demo fixture 才使用 unnamed integration：

```text
Retrieve them using approved source recipes.
```

对应最低合法输出为：

```spl
[DEFINE_APIS:]
    "Retrieve them using approved source recipes." api_retrieve_approved_sources <none>
    {}
    {"functions":[]}
[END_APIS]

COMMAND-n [CALL api_retrieve_approved_sources]
COMMAND-n+1 [COMMAND Maintain provenance for externally sourced facts ...]
```

只有 binding resolver 已证明 upstream contract 中存在对应变量时，才允许增强为：

```spl
COMMAND-n [CALL api_retrieve_approved_sources WITH <REF>available_connectors_or_source_repositories</REF> RESPONSE <REF>source_evidence_set</REF> SET]
```

因此 demo fixture 若确实已有 `available_connectors_or_source_repositories` input 和 `source_evidence_set` required output，可以渲染增强形式；测试仍必须单独覆盖无参数、无响应的最小 `[CALL api_name]`。

Implementation plan 不得把 P7 inferred-name fixture 作为 R-API-0 到 R-API-6 的通过条件。