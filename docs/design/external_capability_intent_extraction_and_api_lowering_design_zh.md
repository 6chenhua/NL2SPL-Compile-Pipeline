# NL2SPL 外部能力意图前置抽取与 API Lowering 设计

状态：Architecture direction approved；implementation conditionally approved after R0 contract tightening  
语言：中文  
适用范围：NL2SPL Pipeline 的外部能力识别、API declaration/call demand、worker boundary、资源与步骤物化  
规范关系：本文是 `api_definition_full_materialization_and_irs_design_zh.md` 与其评审修订的增量规范；发生冲突时，以本文关于 integration route、外部能力抽取和 Stage 3.5 authority 的规定为准。既有 `API_DECLARATION` IRS、Stage 6/7 materialization、Gate、Renderer、Provenance 与 Snapshot 设计继续有效。

---

## 1. 结论

`integration` 不适合仅用 `list[span_id]` 路由字段表达。本设计采用三段式 capability lifecycle：

1. Adapter/Stage 1/Stage 2 尽早捕获 source-backed `CapabilityEvidenceCandidateIR`，但没有 semantic/admission authority。
2. Stage 3 消歧后，Semantic Extractor 扫描全部 resolved spans，输出 `ExternalCapabilityIntentCandidateIR`；不能只扫描 `routes.integrations`。
3. Semantic extraction 与 DemandView 可并行；二者完成后由 Intent Resolver 执行 merge、resource binding、admission 和 stable identity。
4. Resolver 输出的 `ExternalCapabilityIntentPlanIR` 是 ConstructPlan 唯一可消费 authority。
5. `FieldRouteIR.integrations` 降级为兼容索引，不再决定 coverage、admission 或物化。
6. Stage 3.25 只从 final intent 创建 `APIDeclarationDemand` / `APICallDemand`。
7. Stage 3.5 只决定 worker boundary，不识别、不创建、不补全 API；`compile_as_call_api` 从生产 authority 移除。
8. Capability IR 不建立 API/tool/connector/repository 封闭分类，也不注册 IRS。
9. API 是 external executable capability 的受控 SPL lowering；抽取链路不宣称它一定是 HTTP API。
10. 未命名但有直接 boundary、surface 和 invocation evidence 的能力可进入 inferred-name lowering；声明保持 partial、`unknown_mechanism` 并阻止 completion。
11. 普通 `retrieve/search/collect` 动作本身不是外部能力证据。

```text
Canonical input / Stage 1 / Stage 2
  -> CapabilityEvidenceCandidateIR                 (non-authoritative)
Stage 3 resolved spans
  -> Capability Semantic Extractor
  -> ExternalCapabilityIntentCandidateIR           (semantic candidate)
DemandView + semantic candidates + adapter evidence
  -> Capability Intent Resolver
  -> ExternalCapabilityIntentPlanIR                (authority)
  -> Stage 3.25 ConstructPlan
       -> APIDeclarationDemand / APICallDemand
  -> Stage 4/5 placement -> Stage 6/7 materialization -> IRS/Gate/Renderer
```

---

## 2. 问题定义

### 2.1 当前信息损失

当前 `FieldRouteIR.integrations` 主要表达“哪些 span 与 integration 有关”，但后续 API 生命周期需要回答：

- 哪个源片段表达了外部能力边界；
- 用户是在要求执行、仅仅提及，还是表达政策偏好；
- 能力是否有显式名称；
- 源文本中用于指代能力的原始短语是什么；
- 哪个 action 使用该能力；
- 声明与调用如何配对；
- 哪些结论是 direct、normalized 或 inferred；
- 缺少名称、schema、function 时应如何诊断。

`list[span_id]` 无法承载这些信息。

### 2.2 当前 authority 冲突

现有运行可能同时出现：

```text
Stage 2: span 只是 process_step，routes.integrations 为空
Stage 3.5: candidate_kind=integration_wrapper，signal=external_integration
Stage 3.5: decision/context=compile_as_call_api
```

这意味着两个阶段在独立进行 integration semantic judgement，但没有统一 artifact，也没有一致性约束。由于 ConstructPlan 已在 Stage 3.5 前生成，Stage 3.5 的发现既不能合法回写 API demand，也不应越权创建 APISpec，最终只能静默退化为 `GENERAL_COMMAND`。

### 2.3 用户不会稳定提供 API 专用字段

结构化 adapter 可以提供显式 `apis`、`tools` 或 `integrations` 字段，此类输入应作为高强度来源证据。但通用 NL 输入通常只包含动作与能力描述。编译器必须能够建立 partial semantic intent，而不能要求用户先把自然语言改写成技术 schema。

---

## 3. 设计目标与非目标

### 3.1 目标

1. 在 worker boundary planning 前建立唯一、typed、source-backed 的外部能力意图 artifact。
2. 对显式字段、自然语言命名能力和未命名能力使用统一模型。
3. 支持同一 span 同时表达 action、external capability 和其他要求。
4. 将 extraction、admission、construct planning、lowering、materialization 分离。
5. 在无完整 API schema 时生成可审计的 partial declaration，而不是伪造完整合同。
6. 确保 Stage 3.5 不再承担 API semantic authority。
7. 保持现有 `API_DECLARATION` / `CALL_API` IRS 与 Gate authority。
8. 通过开放属性和 source surface form 避免针对当前 demo 建立封闭分类。

### 3.2 非目标

本文不设计：

- HTTP/OpenAPI 自动发现；
- endpoint、认证、参数、返回类型的无来源补全；
- API runtime execution；
- API/tool/connector/database 的完整领域本体；
- 新的 SPL `CALL_TOOL`、`QUERY_DATABASE` 等 grammar construct；
- Stage 3.5 的新 LLM API 分类 prompt；
- 基于关键词的 `retrieve/search -> CALL_API` fallback；
- API declaration 的 SPL Editing 自动修复策略。

---

## 4. 核心术语

### 4.1 External capability

External capability 指当前 worker 内部普通计算之外、执行动作时需要引用的能力边界。它是编译语义，不等同于特定传输协议。

示意包括命名服务、组织提供的能力、外部系统接口等，但这些仅是样例，不构成封闭枚举。

### 4.2 Capability surface

`capability_surface` 是源文本中直接指代该能力的原始短语，例如：

```text
SearchAPI
the approved retrieval capability
the organization-provided source service
```

它必须能回指 source span，不允许由 renderer 临时发明。

### 4.3 Extraction、admission 与 lowering

三者必须分离：

```text
extraction: 源文本是否表达了一个可能的外部能力意图
admission: 该证据是否足以进入正式 construct demand
lowering: 该意图映射为何种 SPL construct
```

成立的 extraction 不必然通过 admission；通过 admission 也不意味着合同 complete。

### 4.4 API lowering

在当前 SPL grammar 只有 `CALL API_NAME` 可表达通用外部调用的前提下，满足条件的 external executable capability 可以 lowering 为 `API_DECLARATION + CALL_API`。

该 lowering 表示 SPL 的外部调用抽象，不声称源系统一定采用 HTTP API。对于未能确认具体技术机制的能力，必须设置 `mechanism_status="unknown"`。

---

## 5. 架构决策

### 5.1 不建立机制类型分类树

核心 IR 不使用如下封闭枚举：

```text
api | service | tool | connector | repository | database | recipe
```

原因：

- 类型可重叠；
- 类型会随领域变化；
- 当前 NL 通常不足以可靠区分；
- SPL lowering 关心的是边界、引用和执行需求，而不是完整技术本体。

允许保留开放、非权威的 metadata：

```python
metadata={"mechanism_hint": "source-provided free text"}
```

该字段不得参与 admission、completion 或 renderer authority。

### 5.2 使用正交 claim

能力意图通过相互独立的 claim 表达：

- boundary claim：是否有外部边界证据；
- identity claim：能力是否被命名或仅被描述；
- invocation claim：是否要求执行调用；
- admission claim：是否足以进入正式 planning。

这避免把某个具体例子编码成一条特殊分类分支。

### 5.3 全量 resolved span coverage

抽取器必须检查全部 resolved spans，并可利用 route annotations 作为上下文。不得只扫描：

```text
routes.integrations
Stage 3.5 candidates
包含 API/search/retrieve 关键词的 spans
```

Route 是 evidence/context，不是 candidate coverage gate。

### 5.4 无证据不创建

以下内容单独出现时，不构成 confirmed external capability：

- 普通动作动词；
- 领域名词或交付物；
- “最好使用外部证据”等政策偏好；
- 仅描述数据来源但未表达能力边界；
- Stage 3.5 的 `compile_as_call_api` legacy hint。

---

## 6. Pipeline 时机与阶段 authority

### 6.1 时机结论

单一 Stage 3.20 抽取器不是最优边界。Evidence 可以提前；最终语义 candidate 必须晚于 span 消歧；resource binding/admission 可以延后到 DemandView 完成后；final authority 必须早于 ConstructPlan 和 Stage 3.5。

```text
Early evidence collection
  < Stage 3 ambiguity resolution
  < semantic extraction on resolved spans
  <= DemandView（可并行）
  < intent resolution/admission
  < ConstructPlan
  < Worker Boundary Planning
```

### 6.2 Phase A：Early Capability Evidence Collection

位置在 Canonical Input、Stage 1、Stage 2 周边。捕获 adapter 显式字段、source hints、route clues 和 capability surface candidates。禁止确认 boundary/admission、创建 demand 或推断 API name。

### 6.3 Phase B：Post-Ambiguity Semantic Extraction

位置在 Stage 3 Ambiguity Resolver 后。它扫描全部 resolved spans，参考但不依赖 early evidence/routes，抽取 operation、surface、boundary、identity、invocation claims，输出 semantic candidates。它可与 DemandView 并行。

Phase B 规范性决定：首版采用独立 LLM structured call，但复用现有 `LLMClient`、prompt loader、checkpoint 与 JSON validation infrastructure。不得把该调用合并回 Field Router 或 Stage 3.5。Prompt 输入只包含 resolved source artifacts 与非权威 context；输出必须严格匹配 `ExternalCapabilityIntentCandidateIR` schema。独立 stage name、prompt version、schema version、model/config fingerprint 必须进入 checkpoint，便于离线评估与回放。

Phase B 是受约束的多维分类器和 extractive span selector，不是生成器：claim 使用闭合枚举；`operation_surface`、`capability_surface`、显式 `capability_ref_candidate` 和每条 evidence 必须锚定 resolved source。`operation_text` 只能由 deterministic normalizer 从 `operation_surface` 产生，不能由 LLM 自由改写。

### 6.4 Phase C：Pre-Construct Intent Resolution

在 semantic extraction 与 DemandView 都完成后、ConstructPlan 前运行。Resolver 不调用 LLM、不读 raw NL，只负责 validation、merge、冲突保留、resource binding、admission、stable ID 和 diagnostics，输出 final intent plan。

### 6.5 推荐 Pipeline

```text
Stage 1 -> early evidence
Stage 2 -> route clues / early evidence
Stage 3 -> resolved spans/routes
    |-> Capability Semantic Extractor --------|
    |-> Stage 3.2 DemandView -----------------|
                                              v
                              Capability Intent Resolver
                                              v
                              Stage 3.25 ConstructPlan
                                              v
                              Stage 3.5 Worker Boundary
```

不使用 `Stage 3.20` 作为实现编号，避免与 Stage 3.2 混淆。建议组件名：

```text
early_capability_evidence_collector
external_capability_semantic_extractor
external_capability_intent_resolver
```

### 6.6 Authority 表

| 组件 | Authority | 明确禁止 |
|---|---|---|
| Early Evidence Collector | 保存 source clues | semantic confirmation、admission、demand |
| Stage 2 | route context | final capability intent |
| Semantic Extractor | resolved-span semantic claims | admission、binding、SPL construct |
| DemandView | resource demand/provenance | external boundary 判断 |
| Intent Resolver | merge、binding、admission、final intent | APISpec/StepIR |
| Stage 3.25 | declaration/call demand 与 pairing | 重新解析 NL |
| Stage 3.5 | worker boundary/behavior ownership | API 识别、demand、lowering |
| Stage 4/5 | call placement | 临时识别 API |
| Stage 6/7 | APISpec/StepIR materialization | 重新判断 capability |
| IRS/Gate | completion/render authority | 修改 IR |
| Stage 11 | grammar rendering | fallback name、语义推断 |

---

## 7. IR 设计

### 7.1 Artifact authority

```text
CapabilityEvidenceCandidateIR
  = 早期 clue，无 semantic/admission authority
ExternalCapabilityIntentCandidateIR
  = 消歧后 semantic claims，无 merge/binding/admission authority
ExternalCapabilityIntentIR / ExternalCapabilityIntentPlanIR
  = Resolver 输出，ConstructPlan 唯一 authority
```

```python
@dataclass(frozen=True)
class CapabilityEvidenceCandidateIR:
    evidence_id: str
    source_span_id: str | None
    source_hint_ids: tuple[str, ...]
    surface_text: str
    claim_hint: Literal["possible_boundary", "possible_identity", "possible_invocation", "adapter_declaration"]
    origin: Literal["adapter", "stage1", "stage2_annotation"]

@dataclass(frozen=True)
class ExternalCapabilityIntentCandidateIR:
    candidate_id: str
    source_span_ids: tuple[str, ...]
    operation_surface: str
    operation_text: str
    capability_surface: str | None
    capability_ref_candidate: str | None
    boundary_claim: Literal["external", "candidate_external", "unresolved"]
    identity_claim: Literal["explicit_name", "described_unnamed", "missing", "ambiguous"]
    invocation_claim: Literal["executable", "mention_only", "policy_only", "unresolved"]
    evidence: tuple[CapabilityEvidenceIR, ...]
```

Early evidence 不能直接进入 ConstructPlan；semantic candidate 不能被 Stage 6/7、Gate 或 Renderer 消费。最终 `intent_id` 只能由 Resolver 基于 resolved spans 和稳定 source fields 生成。

### 7.2 Semantic evidence claim

```python
@dataclass(frozen=True)
class CapabilityEvidenceIR:
    evidence_id: str
    source_span_id: str
    claim: Literal["boundary", "identity", "invocation", "operation"]
    surface_text: str
    relation: Literal["direct", "normalized", "inferred"]
    source_section_id: str | None = None
    source_packet_id: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)
```

规则：

- `surface_text` 必须是 span 中的直接文本或可审计 normalized form；
- `inferred` evidence 不能单独将 admission 提升为 confirmed；
- MVP 不要求 character offsets，但后续可向后兼容增加；
- metadata 不得存放未声明的 completion authority。

### 7.3 Final ExternalCapabilityIntentIR

```python
@dataclass
class ExternalCapabilityIntentIR:
    intent_id: str
    source_candidate_ids: tuple[str, ...]
    source_span_ids: tuple[str, ...]

    operation_text: str
    capability_surface: str | None
    capability_ref: str | None

    boundary_status: Literal[
        "confirmed_external",
        "candidate_external",
        "unresolved",
    ]
    identity_status: Literal[
        "explicit_name",
        "described_unnamed",
        "missing",
        "ambiguous",
    ]
    invocation_status: Literal[
        "executable",
        "mention_only",
        "policy_only",
        "unresolved",
    ]
    capability_admission_status: Literal[
        "confirmed_capability",
        "candidate_capability",
        "rejected",
    ]
    invocation_admission_status: Literal[
        "confirmed_invocation",
        "candidate_invocation",
        "no_invocation",
        "ambiguous_invocation",
    ]

    evidence: tuple[CapabilityEvidenceIR, ...]
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    binding_status: Literal["fully_bound", "partially_bound", "unbound", "not_required"] = "not_required"
    unresolved_binding_claims: tuple[str, ...] = ()
    source_section_id: str | None = None
    source_packet_id: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)
```

### 7.4 字段语义

`capability_ref` 只能包含：

- 源文本中的显式 grammar-safe 名称；或
- adapter 明确提供的 canonical name。

未命名能力在 final intent 中必须保持：

```python
capability_ref = None
identity_status = "described_unnamed"
```

确定性 inferred API name 属于 lowering/materialization plan，不写回成“显式 capability_ref”。

`operation_text` 是动作语义，不是 API function schema。不得从它自动生成参数或返回合同。

`input_refs/output_refs` 由 Intent Resolver 绑定，只接收 DemandView/adapter 中已存在且 source-backed 的 reference；不允许为了让调用完整而发明变量。

Binding 与 capability/invocation admission 正交：direct boundary evidence 已满足时，partial/unbound 不把 capability 降回 candidate。Resolver 保持 `capability_admission_status="confirmed_capability"`，独立设置 invocation admission、binding status 与 unresolved claims。只有源文本没有表达任何参数需求时才使用 `not_required`。缺失 source-required binding 阻止 completion，但最小无参 CALL 是否可渲染仍由 CALL_API IRS/Gate 判断。

### 7.5 Plan container

```python
@dataclass(frozen=True)
class CapabilityExtractionDispositionIR:
    source_span_id: str
    status: Literal[
        "candidate_emitted", "no_external_boundary", "policy_only",
        "insufficient_evidence", "rejected_invalid_evidence",
    ]
    related_candidate_ids: tuple[str, ...] = ()
    reason_code: str | None = None

@dataclass
class ExternalCapabilityIntentPlanIR:
    plan_id: str
    intents: tuple[ExternalCapabilityIntentIR, ...]
    dispositions: tuple[CapabilityExtractionDispositionIR, ...]
    candidate_resolution_map: Mapping[str, str | None]
    diagnostics: tuple[CompileDiagnostic, ...]
```

`dispositions` 记录 semantic extraction 审查但未形成 final intent 的 span；它是审计信息，不参与 admission 或 lowering。

`candidate_resolution_map` 是 merge coverage authority：每个 semantic `candidate_id` 必须映射到 canonical `intent_id`，或以 `None` 明确表示 rejected/unresolved。ConstructPlan 只能读取 final intents，禁止读取 candidate IDs；因此 canonical merge 完成前不会产生 demand，也不会形成悬挂引用。Final intent 的 `source_candidate_ids` 必须与反向映射一致。

### 7.6 Stable identity

`intent_id` 必须由稳定结构字段生成：

```text
source_schema
ordered source_span_ids
normalized capability_surface
normalized operation_text
```

允许使用短 digest；禁止使用列表序号、LLM 输出顺序或 worker ID。worker ownership 尚未建立，也不应进入 identity。

Merge 必须保守且确定性：相同显式 canonical ref 且 evidence 不冲突时可合并；未命名 candidates 只有 deterministic normalized surface 相等、operation relationship 明确且 source scope 兼容时才可合并。Span overlap、动词相同或 fuzzy similarity 只能产生 `possible_merge`/ambiguity context，不能直接合并。冲突必须保留，禁止选择第一个。

### 7.7 不注册 IRS

`ExternalCapabilityIntentIR` 不是 SPL grammar construct，因此：

- 不加入 `SPLConstructRegistry`；
- 不新增 `CAPABILITY_INTENT` IRS checker；
- 不向 SPL Editing 暴露 repair affordance；
- 缺口通过 stage-local semantic diagnostics 表达；
- lowering 后的缺口由 `API_DECLARATION` / `CALL_API` IRS 接管。

---

## 8. Evidence、Extraction 与 Resolution 契约

### 8.1 Early Evidence Collector

输入 CanonicalCompileInput、Stage 1 structures 和 Stage 2 annotations，输出 `CapabilityEvidenceCandidateIR`。不得使用关键词确认 capability、修改 routes 或产生 final intent。

### 8.2 Semantic Extractor

输入全部 resolved spans、resolved routes 与 early evidence（后二者仅作 context），通过独立 LLM structured call 输出 semantic candidates。它只判断 external boundary、surface、invocation、identity，不生成技术类型、API name、参数、返回值或 schema。

Output schema 必须拒绝 unknown fields；每个 claim 必须带 resolved span evidence。LLM 不输出 admission、final intent ID、resource binding、API name 或 construct demand。

Post-validation 是强制生产边界，不能只依赖 prompt：

```python
validate_span_ids_exist(candidate)
validate_exact_or_normalized_anchor(candidate.operation_surface, resolved_spans)
validate_exact_or_normalized_anchor(candidate.capability_surface, resolved_spans)
validate_explicit_ref_anchor(candidate.capability_ref_candidate, resolved_spans, adapter_hints)
validate_each_claim_has_evidence(candidate)
```

允许的 normalized anchor 仅包括版本化的 Unicode、空白、大小写与标点规范化，并保留原 surface 和映射关系。Anchor 失败时不得自动修补：对应 claim 降级为 unresolved，或拒绝 candidate，并产生 stage-local diagnostic。Prompt/schema 需要单独版本号，并建立跨领域 golden、negative 与 metamorphic evaluation。

### 8.3 Intent Resolver

输入 semantic candidates、early evidence、DemandView、adapter declarations 和 admission policy，输出 final plan。Resolver 不调用 LLM、不读 raw NL。

### 8.4 共同边界

整个 lifecycle 不消费 WorkerPlanIR、Stage 3.5 decisions、Flow/BlockPlanIR、APISpec 或 StepIR。`api_candidate/integration_hint` 只作为 context，不独立决定 admission。一个 resolved span 可以有多个 candidates，且不得删除普通 behavior。

### 8.5 Failure policy

Production 切换后 semantic extraction/schema failure 不得返回空 plan或回退 Stage 3.5。显式 adapter evidence可继续解析；NL extraction unavailable 必须诊断并阻止相关 completion，但其他 source-backed partial SPL 可继续。建议 kind：`capability_intent_extraction_unavailable`。

---

## 9. Capability admission 与 Invocation admission

单一 `admission_status` 同时控制声明与调用会造成内部矛盾，因此拆为两个正交维度。

### 9.1 Capability admission

`confirmed_capability` 至少要求 direct external boundary evidence、非空 capability surface、无 identity/boundary conflict。它不要求 executable invocation。

```text
confirmed_capability -> 可创建 APIDeclarationDemand
candidate_capability -> 只进入 feedback/diagnostic context
rejected -> 不创建 API demand
```

显式 adapter/API declaration 即使没有调用动作，也可以成为 `confirmed_capability`。

### 9.2 Invocation admission

```text
confirmed_invocation -> 可创建 APICallDemand
candidate_invocation / ambiguous_invocation -> 不创建 renderable call demand
no_invocation -> declaration-only
```

只有 capability 和 invocation 均 confirmed 时才创建 `APICallDemand`。Policy-only mention 固定为 `no_invocation`，不能因 capability confirmed 而升级。

### 9.3 典型组合

| Capability | Invocation | Lowering |
|---|---|---|
| confirmed | confirmed | declaration + call demand |
| confirmed | no invocation | declaration demand only |
| confirmed | candidate/ambiguous | declaration + invocation diagnostic |
| candidate | 任意 | no renderable demand；candidate feedback |
| rejected | 任意 | no demand |

### 9.4 Binding 独立性

Binding 不完整不改变 capability/invocation 的语义 admission。Confirmed invocation 可以保持 confirmed，同时设置 `binding_status=partially_bound/unbound`。是否允许无参 CALL rendering 由 CALL_API IRS/Gate 根据 source-required binding 判断，不由 Resolver 偷补参数。

---

## 10. ConstructPlan lowering

### 10.1 声明与调用仍然分离

`ExternalCapabilityIntentIR` 可产生：

```text
declaration only
call only but unresolved declaration
declaration + call
no API lowering
```

规则：

- confirmed external capability 可形成 `APIDeclarationDemand`；
- `invocation_status="executable"` 可形成 `APICallDemand`；
- mention/policy 不形成 call demand；
- candidate intent 只进入 planner diagnostics/context，不形成 renderable demand。

### 10.2 Named capability

```text
identity_status=explicit_name
capability_ref present
admission=confirmed
  -> APIDeclarationDemand(mechanism_status=explicit)
  -> optional APICallDemand
```

### 10.3 Described unnamed capability

```text
identity_status=described_unnamed
capability_surface present
admission=confirmed
  -> APIDeclarationDemand(
       integration_admission=confirmed,
       mechanism_status=unknown,
       inferred_name_allowed=true,
     )
  -> optional APICallDemand
```

此规则是通用 source-backed unnamed capability lowering，不为某个固定 phrase 建立特例。

### 10.4 Name generation

确定性 inferred API name 在 Stage 6 materialization plan 中生成，要求：

- 由 normalized operation + capability surface 生成；
- grammar-safe；
- 同输入跨运行稳定；
- collision 使用稳定 source digest，不使用运行序号；
- APISpec 标记 `name_status="inferred_from_source"`；
- 保留原 capability surface 和 intent ID；
- feedback 显示 `unknown_mechanism`。

### 10.5 Pairing

声明与调用通过 `capability_intent_id` 配对，不再依赖 Stage 3.5 candidate ID。

```text
ExternalCapabilityIntentIR.intent_id
  -> APIDeclarationDemand.capability_intent_id
  -> APICallDemand.capability_intent_id
```

一个 capability intent 可以对应多个 call demands；一个 call demand 不得自动绑定多个 declaration demands。冲突进入 ambiguous diagnostic。

---

## 11. Stage 3.5 重构

### 11.1 新职责

Stage 3.5 只回答：

```text
某个行为集合是否形成独立 worker boundary？
若不形成，它归属哪个 worker？
```

### 11.2 移除 API semantic decisions

生产模型中逐步移除：

```text
candidate_kind=integration_wrapper 作为 API evidence
signal=external_integration 作为 API admission
decision=compile_as_call_api 作为 API lowering authority
```

Stage 3.5 可以读取 capability intent IDs 作为 ownership context，但不得修改其 admission、identity、operation 或 lowering。

### 11.3 Compatibility

迁移期可以读取 legacy `compile_as_call_api`，但只能：

- 与已有 `APICallDemand` 做一致性比对；
- 写入 suppressed/debug metadata；
- 产生 stage-local consistency diagnostic。

不得：

- 创建 declaration/call demand；
- 生成 APISpec；
- 生成 CALL_API StepIR；
- 将 candidate 升级为 confirmed。

### 11.4 Cross-stage invariant

迁移期必须检查：

```text
compile_as_call_api
  => matching capability intent and APICallDemand must already exist
```

不满足时产生：

```text
stage35_api_lowering_hint_without_capability_demand
```

该诊断用于暴露旧模型分歧，不作为创建 API 的后门。

---

## 12. Stage 4–7 与后续阶段

### 12.1 Stage 4/5

继续以 `APICallDemand` 为 placement 输入。Placement projector 不消费 raw NL 或 Stage 3.5 API hint。

### 12.2 Stage 6

Stage 6 消费：

```text
APIDeclarationDemand
ExternalCapabilityIntentPlanIR（只用于 provenance/source surface）
ResourceRegistryIR
```

生成 partial `APISpec` 与 `APIMaterializationPlanIR`。不得重新判断 external boundary。

### 12.3 Stage 7

Stage 7 仍要求：

```text
APICallDemand
bound APICallBindingIR
placed APICallPlacementIR
declared APISpec
```

缺少任一项时不生成 CALL_API，也不得为同一 demand fallback 为 GENERAL_COMMAND。

### 12.4 IRS、Gate 与 Renderer

既有 authority 不变：

- `API_DECLARATION` IRS 检查声明合同；
- `CALL_API` IRS 检查调用及 declared ref；
- post-normalize reports 决定 Gate；
- Stage 11 只渲染 gate-approved view；
- renderer 不读取 capability intent，也不生成名称。

---

## 13. Diagnostics

### 13.1 Stage-local semantic diagnostics

建议新增：

| Kind | 条件 | 默认阻塞 |
|---|---|---|
| `capability_intent_ambiguous_boundary` | 无法确认内部/外部边界 | completion only |
| `capability_intent_ambiguous_identity` | 多个能力指代无法配对 | completion only |
| `capability_intent_unresolved_invocation` | mention 与执行要求不清楚 | completion only |
| `capability_intent_admitted_as_candidate_only` | 发现可能能力，但 evidence 不足以 lowering | completion only |
| `capability_intent_unresolved_input_binding` | confirmed intent 的 source-required binding 未解析 | completion only |
| `capability_intent_rejected_unanchored_evidence` | operation/capability/ref/evidence 无 source anchor | rendering + completion |
| `capability_intent_duplicate_conflict` | 同 identity 出现冲突 claim | completion only |
| `stage35_api_lowering_hint_without_capability_demand` | legacy Stage 3.5 与前置 authority 不一致 | completion only |

Stage-local diagnostics 必须进入 checkpoint；只有经 `DiagnosticConsolidator` 选择后才能进入 final `compile_diagnostics`。

Candidate feedback 必须显示 source excerpt、缺失 claim（boundary/identity/invocation）、未执行 API lowering 的原因和建议用户补充的信息；不得只显示“未识别 API”。Candidate 不生成 APISpec/CALL_API，也不 fallback 成同一 demand 的伪 API。

### 13.2 Final construct diagnostics

一旦 intent lowering 为 API constructs，最终问题由既有 construct IRS 表达：

```text
API_DECLARATION missing schema/functions/name contract
CALL_API missing/ambiguous declared_api_ref
CALL_API unresolved placement/binding
```

不得同时用 capability diagnostic 和 API diagnostic 重复报告同一缺口。Consolidator 应以 construct-level final authority 为主，capability diagnostic 作为 related context。

---

## 14. Provenance 与 Snapshot

### 14.1 Trace chain

至少保留：

```text
source span
  -> CapabilityEvidenceIR
  -> ExternalCapabilityIntentIR
  -> APIDeclarationDemand / APICallDemand
  -> APISpec / StepIR
  -> rendered SPL
```

Relation 只允许使用已定义值：

```text
direct
normalized
inferred
```

未命名能力生成 API name 的边必须标记 `inferred`。

### 14.2 Snapshot keys

建议：

```python
intermediate["capability_evidence_candidates_payload"] = evidence_plan.to_payload()
intermediate["external_capability_semantic_extraction_payload"] = extraction.to_payload()
intermediate["external_capability_intent_plan"] = intent_plan
intermediate["external_capability_intent_plan_payload"] = intent_plan.to_payload()
```

Snapshot 持久化三阶段 payload。Roundtrip 必须保持 evidence origin、resolved span refs、candidate claims、intent IDs、admission、DemandView bindings 和 pairing；只有 final plan 是 ConstructPlan authority。

---

## 15. `routes.integrations` 迁移策略

### 15.1 目标状态

`routes.integrations` 变为从 route annotations/capability evidence 派生的兼容索引：

```text
用途：调试、旧 prompt context、可视化
非用途：API admission、API name、declaration/call demand authority
```

### 15.2 迁移阶段

1. Evidence shadow：新增 Early Evidence Collector，只记录不改变输出。
2. Extraction shadow：在 resolved spans 上运行 Semantic Extractor。
3. Resolver shadow：join DemandView，持久化 final plan但不驱动 ConstructPlan。
4. Compare：比较旧 routes/Stage 3.5 hints 与 final intents。
5. Demand switch：Stage 3.25 API demands 改为只消费 confirmed capability intents。
6. Stage 3.5 cleanup：移除 API semantic decision，保留 compatibility validator。
7. Route de-authorize：禁止任何 materializer 直接从 `routes.integrations` 创建 API。
8. Cleanup：旧字段保留 serializer compatibility，后续大版本再决定是否删除。

---

## 16. 反过拟合与反幻觉要求

### 16.1 禁止例子驱动分支

生产代码不得出现针对 fixture 的判断：

```text
if text contains "approved source recipes"
if api_name == "SearchAPI"
if verb in {retrieve, search}
```

Fixture phrase 只能出现在测试数据或文档示例中。

### 16.2 开放词汇

`capability_surface` 保留 source vocabulary。系统不要求能力属于预设产品类型。

### 16.3 Metamorphic tests

测试必须验证：

- 替换领域名词但保持外部边界语义时，结构状态不漂移；
- 替换动词但不增加外部边界证据时，不应突然生成 capability intent；
- 删除 capability surface 后，confirmed 必须降级；
- 将执行要求改成 policy mention 后，不产生 APICallDemand；
- 显式名称改为描述性短语后，只改变 identity/name status，不应丢失 operation；
- 同义改写不依赖固定关键词。

### 16.4 跨领域评估集

验收语料至少覆盖多个互不相关领域，并包含：

- 显式命名外部能力；
- 描述性未命名外部能力；
- 普通内部处理；
- 数据对象但无调用边界；
- policy-only mention；
- 多能力歧义；
- declaration-only 与 executable call 分离。

不得只使用 source retrieval 场景。

---

## 17. 测试矩阵

| 场景 | Capability intent | API declaration demand | API call demand |
|---|---:|---:|---:|
| 显式命名能力并要求执行 | confirmed / explicit | yes | yes |
| 显式声明能力但未要求调用 | confirmed / explicit | yes | no |
| 明确使用描述性未命名能力 | confirmed / described | yes, inferred allowed | yes |
| 普通 retrieve/search，无能力 surface | none/candidate | no | no |
| 只提及外部能力 | candidate/confirmed mention | policy-dependent declaration | no |
| policy-only preference | candidate/rejected | no | no |
| 多个能力指代无法配对 | ambiguous | no renderable demand | no |
| adapter 提供名称，NL 提供调用 | confirmed / explicit | yes | yes |
| Stage 3.5 legacy hint，无前置 intent | none + consistency diagnostic | no | no |

E2E 必须证明：

1. 显式名称链路仍生成 `DEFINE_APIS + CALL`；
2. source-backed unnamed capability 可生成 inferred partial declaration；
3. feedback 明确显示 inferred name 与 unknown mechanism；
4. generic action 不生成 API；
5. Stage 3.5 删除 API decision 后不影响已规划 CALL_API；
6. 同 span 的其他 behavior/provenance action 不被 CALL_API sanitation 删除；
7. snapshot roundtrip 不改变 admission/lowering；
8. renderer 仍无 fallback；
9. Stage 2 漏标时全量 extraction 仍可发现 source-backed boundary；
10. split/merge 后 final intent 只引用 resolved spans；
11. extraction 与 DemandView 顺序互换不改变 resolver 结果；
12. extractor unavailable 不返回空 plan或 Stage 3.5 fallback。

---

## 18. 验收标准

### 18.1 Architecture

- Early Collector 只产生非权威 clues；
- Semantic Extractor 只产生 resolved-span candidates；
- Intent Resolver 是 final intent 唯一 authority；
- extraction 与 DemandView 可并行且无循环依赖；
- 只有 Stage 3.25 产生 API construct demands；
- Stage 3.5 不产生 API semantic truth；
- Stage 6/7 不解析 raw NL 重新识别能力；
- `routes.integrations` 不再是 materialization authority。

### 18.2 Source backing

- 每个 confirmed intent 有可追溯 boundary、identity/surface、invocation evidence；
- inferred name 明确标记，不能伪装为 explicit；
- schema/functions/auth 不从 operation text 发明；
- generic action 不因关键词命中升级。

### 18.3 API lifecycle

- confirmed named capability 可形成声明与调用 demand；
- confirmed described capability 可形成 partial inferred declaration；
- candidate intent 不进入 renderer；
- API declaration/call 仍由 IRS/Gate 决定 completion/rendering；
- 无 declared API 的 call 不可渲染。

### 18.4 Auditability

- checkpoint 包含 capability plan payload；
- feedback 能区分 semantic extraction issue 与 API contract issue；
- Stage 3.5/final intent 分歧有明确 consistency diagnostic；
- full test suite 与跨领域 metamorphic suite 通过。

---

## 19. 必须禁止的实现捷径

1. 将 `routes.integrations` 直接改名为 `CapabilityIntentIR`，但仍只保存 span IDs。
2. 只扫描 integration route，导致 route 漏标不可恢复。
3. 使用关键词规则确认 external boundary。
4. 建立 API/tool/connector/repository/recipe 封闭分类树。
5. 让 Stage 3.5 回写 ConstructPlan 或 ResourceRegistry。
6. 将 `compile_as_call_api` 当作 API declaration source evidence。
7. 抽取阶段生成 inferred API name。
8. 将 source object（例如 sources/documents）误当 capability surface。
9. 仅凭 capability mention 生成 executable call。
10. 让 renderer 从 capability intent 发明声明或调用。
11. 让 stage-local capability diagnostics 绕过 consolidator 直接污染 final diagnostics。
12. 用当前 demo 的通过替代跨领域、负向和 metamorphic 验收。
13. 让 early evidence 直接进入 ConstructPlan。
14. 在 span 消歧前固化 final intent ID。
15. 让 DemandView/Resolver 重新做 LLM semantic extraction。
16. extractor 失败时返回空 plan并声称没有 integration。

---

## 20. 参考流程

### 20.1 显式命名能力

```text
Source
  -> operation + explicit capability surface + executable invocation
Resolved spans -> semantic candidate
DemandView + candidate -> confirmed final intent(capability_ref present)
Stage 3.25
  -> APIDeclarationDemand + APICallDemand
Stage 6/7
  -> partial APISpec + CALL_API StepIR
Gate/Renderer
  -> DEFINE_APIS + CALL
```

### 20.2 描述性未命名能力

```text
Source
  -> operation + direct described capability surface + executable invocation
Resolved spans -> semantic candidate
DemandView + candidate -> confirmed final intent(capability_ref=None)
Stage 3.25
  -> declaration demand(inferred_name_allowed, mechanism unknown)
Stage 6
  -> deterministic inferred name + partial APISpec
Stage 7
  -> CALL_API
Feedback
  -> inferred_from_source + unknown_mechanism + incomplete contract
```

### 20.3 普通动作

```text
Source
  -> operation only, no external boundary evidence
Semantic extraction -> no confirmed candidate
Intent Resolver -> no confirmed final intent
Stage 3.25
  -> no API demand
Downstream
  -> normal behavior lowering or unresolved behavior diagnostic
```

---

## 21. MVP 实施轮廓与已决策事项

1. Semantic Extractor 必须是独立、版本化的 LLM structured call；复用基础设施但不复用 Field Router/Stage 3.5 的 semantic authority。它是 lifecycle 唯一不确定性注入点，必须完整 checkpoint 和可离线回放。
2. `CapabilityEvidenceCandidateIR` 是目标模型；MVP 可暂不物化独立 dataclass，但 route/adapter context 的 source provenance 必须原样进入 semantic evidence，且不得成为 coverage gate。
3. `CapabilityExtractionDispositionIR` 的完整 dataclass 可后置；MVP 至少写入 structured suppressed metadata/checkpoint，不能只留不可查询的普通日志。
4. 不采用全局 fail-fast。Extractor failure 使 capability 子链路 unavailable、阻止相关 completion，但其他 source-backed partial compilation 继续；禁止空 plan和 Stage 3.5 fallback。
5. Candidate 必须有用户可见 soft-failure feedback。
6. Binding 不完整不改变 semantic admission；使用 binding status 与诊断表达。
7. Resolver merge 后 canonical ID 和 candidate coverage map 是 demand 创建前置条件。

---

## 22. R0 尚待验证的项目门禁

架构决策已经收敛；以下是必须用项目代码/测试验证的 implementation gates，而不是开放的语义方向：

1. Grammar validator 是否接受 `{}` 与 empty functions 作为明确标记的 grammar-minimal placeholder；authentication 缺省已确定为 `<none>`，不再属于该门禁。验证失败则 schema/functions partial declaration blocked。
2. 现有 DemandView 是否扩展稳定 `resource_ref`；未扩展前参数 binding 必须保持 unbound/partially_bound。
3. `APICallBindingIR -> APIDeclarationBindingIR` 的 schema/type-tag 迁移版本与兼容周期。
4. `CapabilityNameResolverV1` 的确定性、collision、snapshot roundtrip 与跨运行 golden。
5. Capability diagnostics 与既有 API_DECLARATION/CALL_API diagnostics 的 consolidator 去重测试。

这些门禁完成前，Architecture direction 保持 approved，但 implementation readiness 仅 conditionally approved。

---

## 23. R0 Contract Tightening（实施前阻塞项）

本节是前述设计的规范性收紧；发生冲突时以本节为准。R0 完成前不得切换生产 demand authority。

### 23.1 Partial APISpec 与 grammar/renderability

必须区分：

```text
APIDeclarationDemand
  -> Partial APISpec / APIMaterializationPlanIR
  -> grammar-minimal API declaration candidate
  -> Gate-approved renderable API_DECLARATION
```

`docs/spl_grammar.txt` 要求 API declaration 包含 name、authentication、OPENAPI_SCHEMA 与 API_IN_SPL。因而：

- 用户完全未提供 authentication evidence 时，按语言默认规则物化为 `<none>`；这属于 `defaulted` relation，不得标记为 direct source evidence；
- 用户显式声明无需认证时，`<none>` 属于 direct evidence；
- 用户明确表示“需要认证”但未说明 `<apikey>`/`<oauth>` 时，不得默认 `<none>`，authentication 保持 unresolved 并阻止渲染；
- 因为缺省 authentication 已有确定语义，普通混合 step 不再仅因未提认证而阻止 declaration；
- name-only APISpec 仍不可渲染；
- intermediate partial APISpec 可以进入 snapshot、feedback、IRS；
- `{}` 与 `{"functions":[]}` 只有在 grammar validator 确认合法、并明确标为 unknown placeholders 时，才可成为 `grammar_minimal_partial`；
- placeholder 不能被标记 complete，必须阻止 completion；
- 若项目 policy 不批准 placeholder rendering，则状态为 `partial_blocked`，不进入 `RenderableResourceRegistryView`；
- `CALL_API` 只有 declared ref 指向 Gate-approved declaration 时才可渲染，禁止悬挂 CALL。

统一状态：

```text
materialization_status = partial | grammar_minimal_partial | complete | blocked
renderability_status = renderable | blocked
authentication_status = explicit | defaulted_none | unresolved
missing_contract_slots = (...)
```

R0 必须用 grammar parser/validator 锁定 `{}` 和 empty functions 是否属于允许的 grammar-minimal placeholder；不得由 renderer 自行决定。

### 23.2 DemandView 最小消费契约

不新建平行 resource truth source。Resolver 消费现有 `DemandViewDemand` 的只读投影：

```python
@dataclass(frozen=True)
class CapabilityDemandBindingViewIR:
    demand_id: str
    direction: Literal["input", "output"]
    requiredness: Literal["required", "optional", "unspecified"]
    evidence_text: str
    source_span_ids: tuple[str, ...]
    source_section_id: str | None
    source_packet_id: str | None
    source_hint_ids: tuple[str, ...]
    view_status: str
    resource_ref: str | None
```

当前项目 `DemandViewDemand` 尚无稳定 `resource_ref`。因此 R0 必须二选一：

1. 为 DemandView 增加 source-backed canonical `resource_ref`；或
2. 保持 `resource_ref=None`，Resolver 只标记 partially_bound/unbound。

禁止 Resolver 从 `evidence_text` 或 raw NL 临时生成变量名。DemandView unavailable 不降低 boundary/capability admission，只影响 binding status。

### 23.3 现有 Stage 4/5/6/7 DTO 的规范性扩展

项目已有：

- `APICallPlacementIR`：`call_demand_id/owner_worker_id/flow_ref/block_ref/status/source_span_ids/reason`；
- `APICallBindingIR`：当前实际表达 declaration demand 到 materialized APISpec 的绑定；
- `APIMaterializationPlanIR`：当前承载 `api_specs/bindings/unsupported_declaration_demand_ids`。

不得另建同名平行 DTO。R0 扩展规则：

```text
APICallPlacementIR.status = placed | unresolved | ambiguous
```

现有 `APICallBindingIR` 建议在下一 schema 版本更名为 `APIDeclarationBindingIR`；兼容期保留旧 type tag。调用参数绑定另建：

```python
@dataclass(frozen=True)
class APICallArgumentBindingIR:
    call_demand_id: str
    input_bindings: Mapping[str, str]
    output_bindings: Mapping[str, str]
    binding_status: Literal["fully_bound", "partially_bound", "unbound", "not_required"]
    unresolved_binding_claims: tuple[str, ...]
    source_span_ids: tuple[str, ...]
```

`APIMaterializationPlanIR` 增加 declaration demand 级 materialization/renderability record，不把 post-normalize Gate authority塞回 Stage 6。

Stage 7 规则：缺 placement 不生成 StepIR；缺 source-required binding 保留 demand并诊断；缺 Gate-approved declaration 不渲染 CALL_API；任何情形都不 fallback 同一 demand 为 GENERAL_COMMAND。

### 23.4 Operation coverage 与 duplicate prevention

`APICallDemand` 必须新增：

```python
operation_span_ids: tuple[str, ...]
consumes_behavior_span_ids: tuple[str, ...]
residual_behavior_span_ids: tuple[str, ...]
behavior_lowering_policy: Literal[
    "api_call_replaces_behavior",
    "api_call_augments_behavior",
    "keep_residual_behavior_only",
    "ambiguous",
]
```

规则：

- replaces：CALL_API 覆盖 operation，不再生成同义 GENERAL_COMMAND；
- augments：只为 residual processing 生成 GENERAL_COMMAND；
- keep residual only：API 消费外部动作，保留明确的 provenance/transform 等残余行为；
- ambiguous：不生成重复命令，产生 completion diagnostic。

Stage 7 sanitation 必须按 demand/operation coverage identity 匹配，不得以共享 span 的集合关系删除所有 GENERAL_COMMAND。

### 23.5 Failure policy

1. 有 explicit adapter capability evidence：可解析 declaration-only final intent；invocation 必须有 NL extractor 或 explicit invocation evidence。
2. 有 Stage 2 API/integration early evidence但 extractor unavailable：输出 `capability_intent_extraction_unavailable`，不声称无 capability，不创建 call demand。
3. 无任何 early evidence且 extractor unavailable：只写 checkpoint/suppressed metadata，不制造 capability-specific completion blocker。
4. 所有分支禁止 Stage 3.5 fallback。

### 23.6 Diagnostic consolidation

Capability diagnostics 默认进入 feedback 的 capability section。只有以下情况可进入 final `compile_diagnostics`：

- extractor unavailable 且存在 explicit adapter capability evidence；
- confirmed final intent lowering 后没有对应 construct diagnostic覆盖；
- legacy Stage 3.5 hint 与 final intent 冲突且影响 completion。

同一缺口已有 API_DECLARATION/CALL_API final-authority diagnostic 时，capability diagnostic 必须 suppressed/related，不得重复展示。

### 23.7 已确认决策

- `CALL_API` 是当前 grammar 对 external executable capability 的 lowering target，不表示底层一定是 HTTP/OpenAPI；unknown mechanism 必须保留。
- Authentication 无任何来源信息时默认 `<none>`，记录 `authentication_status=defaulted_none`；存在“需要认证”证据但方式不明时不得应用该默认。
- Source-backed described unnamed capability 可 confirmed capability，但不自动获得 renderability。
- Confirmed capability + no invocation 允许 declaration demand only。
- `compile_as_call_api` 采用 shadow compare -> consistency diagnostic -> schema removal。
- `routes.integrations` 短期保留 derived index，下一 major schema 再评估删除。
- Inferred name resolver 独立版本化为 `CapabilityNameResolverV1`，不得隐藏在 Stage 6 私有逻辑中。

### 23.8 实施切片

```text
R0 Contract tightening
R1 Baseline characterization
R2 Early evidence shadow
R3 Semantic extractor shadow
R4 Resolver shadow
R5 ConstructPlan authority switch
R6 Stage 4-7 placement/binding/materialization
R7 IRS/Gate/Renderer hardening
R8 Feedback and migration cleanup
```

每一切片独立验收，不得在 R2-R4 shadow 阶段改变最终 SPL。

