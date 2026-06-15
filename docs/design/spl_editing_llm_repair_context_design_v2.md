# SPL Editing LLM Repair Context 设计文档 v2.1

日期：2026-06-15
状态：Revised architecture design
适用范围：NL2SPL AI-assisted SPL Editing suggestion generation layer
建议保存编码：UTF-8
关联模块：

```text
src/nl2spl/compiler/spl_editing/
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/irs/
src/nl2spl/compiler/producer_index.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/pipeline/provenance.py
```

---

## 0. 核心结论

SPL Editing 当前已经建立了较完整的安全 apply 链路：

```text
ArtifactSnapshot
-> EditableIssue
-> RepairCatalog / patch type selection
-> LLM-generated RepairSuggestion
-> user confirmation
-> typed RepairPatch apply
-> Lane A / Lane B compiler replay
-> verification accepted / rejected
```

这条链路解决的是：

```text
LLM 不能直接修改 SPL；
LLM 不能绕过用户确认；
LLM 不能绕过 typed patch；
LLM 不能绕过 IRS / Gate / ProducerIndex / Renderer verification。
```

但 demo 暴露了 suggestion 输入侧的问题：即使最终 patch 可以被 compiler authority 接受，LLM 生成的 suggestion 仍可能语义不贴合业务场景。

典型失败样本：

```text
用户选择：
  Exception has no handler: Missing timeframe

LLM 却生成：
  Please provide instructions on how to proceed with the adapter error.
```

这说明 LLM 从 compiler-generated id 或 raw diagnostic message 猜语义，而不是从真实业务事实生成 repair suggestion。

本设计的核心结论是：

```text
LLM Repair Context 应该是 registry-driven prompt context projection layer。

它把 EditableIssue、ArtifactSnapshot、RepairTarget、RepairCatalog、
PatchRegistry、typed IR artifacts 和 presentation facts 投影成 LLM 可消费的业务上下文。

它不决定 issue 是否 repairable；
不决定 patch type 是否可用；
不成为第二套 RepairCatalog；
不替代 PatchRegistry；
不替代 VerificationRunner。
```

v2.1 相比 v2 的关键修正：

```text
1. extension 不再是 singular。
   改为 primary_extension + auxiliary_extensions。

2. extension facts 不再是 loose dict。
   必须 schema-validated，并绑定 facts_schema_id / facts_schema_version。

3. 明确区分：
   repair_unavailable
   generation_blocked
   ready_low_confidence
   ready

4. internal ids 不再只是孤立 id list。
   改为 SelectableReference，并附带 business summary。

5. PromptRenderer 不枚举 construct。
   Extension renderer 也必须绑定 facts_schema_id，不能变成新的 if-else 中心。
```

一句话总结：

```text
Stable common context
+ primary / auxiliary affordance extensions
+ schema-validated extension facts
+ explicit generation readiness
+ selectable internal ids
+ schema-bound section renderers
+ no construct enum in core DTO
+ no second RepairCatalog
```

---

## 1. 背景

AI-assisted SPL Editing 的 apply 边界已经明确：

```text
LLM 只生成 candidate RepairSuggestion；
用户确认后才形成 accepted RepairPatch；
后端 deterministic apply typed patch；
apply 后必须重新经过 compiler authorities 验证。
```

因此，LLM suggestion 的主要风险不在 “LLM 会不会直接改 SPL”，而在：

```text
LLM 看到的上下文是否正确；
LLM 是否把 compiler id 当成业务事实；
LLM 是否知道 local workflow / source excerpt / available variables；
LLM 是否知道 selected patch type 的 payload schema 和 forbidden actions；
LLM 是否被迫从 raw diagnostic.message 猜语义。
```

当前缺少一个标准化 LLM Repair Context 层，导致 handler 容易直接拼接：

```text
issue.message
target_ref
construct id
exception flow id
step id
worker promotion id
resource demand id
```

这些字段对后端 routing 有用，但对 LLM 不是稳定业务语义。

---

## 2. 当前问题

### 2.1 Handler 直接拼 prompt

当前容易形成如下流程：

```text
EditableIssue
+ RepairTarget
+ RepairContext
-> handler-specific prompt
-> LLM JSON suggestion
```

形式上已有 TargetResolver、ContextBuilder、RepairHandler 分层，但 prompt 输入没有统一语义 contract。

结果是：

```text
不同 handler 的上下文粒度不一致；
业务事实与 compiler routing id 混在一起；
Presentation 层能展示正确语义，但 LLM handler 未必使用；
raw CompileDiagnostic.message 被当成主要语义输入；
target_ref 被直接暴露给 LLM；
existing step 只给 id，不给 text / inputs / outputs / renderability。
```

### 2.2 `missing_handler` 使用 raw diagnostic message 作为 condition

实际应给 LLM：

```text
Exception condition:
  Missing timeframe
```

但当前容易给成：

```text
Exception flow 'exc_adapter_03' has condition but no handler step.
Target: worker:worker_main.exception_flow:exc_adapter_03
```

`exc_adapter_03` 是 compiler-generated id，不是业务事实。因为它包含 `adapter`，LLM 可能误以为业务问题是 adapter error。

### 2.3 ContextBuilder 偏薄

例如 exception flow context builder 理应提供：

```text
condition_text
source_excerpt
nearby steps
worker purpose
available variables
current flow context
```

但如果实际只提供：

```text
issue
target
worker_scope
user_instruction
```

handler 即使想构造高质量 prompt，也没有稳定来源。

### 2.4 Existing artifact context 不足

`missing_output_producer` 至少需要告诉 LLM：

```text
required output name
required output description
declaring worker
existing producer candidates
existing outputs already produced
candidate step text
candidate step inputs
candidate step outputs
candidate step renderability
why a step may or may not bind
```

只给：

```text
Bindable existing step ids:
  - st_1
  - st_2
```

不足以支持合理选择。

### 2.5 Verification 不能替代 suggestion 语义质量

Verification 可以保证：

```text
patch 类型合法；
patch 作用于 stage-level artifact；
user_confirmed_repair evidence 生效；
Gate / IRS / ProducerIndex / Renderer 接受；
目标 diagnostic resolved。
```

但它不能自动保证：

```text
handler text 业务上合适；
request input question 问的是正确缺失信息；
producer step 真正符合源需求；
handoff contract 语义贴合 delegation intent。
```

因此必须在 LLM 输入上下文层面提高 suggestion 质量。

---

## 3. 设计目标

### 3.1 核心目标

LLM Repair Context 层应提供一个标准化投影：

```text
EditableIssue
+ ArtifactSnapshot
+ RepairTarget
+ RepairContextBuilder output
+ IssuePresentation / display facts
+ RepairCatalog selected affordance / patch type
+ PatchRegistry payload schema
+ typed IR artifact summaries
-> LLMRepairContext
-> PromptRenderer
-> LLM
-> RepairSuggestion
```

目标：

```text
1. 给 LLM 足够的业务事实，避免从 compiler id 猜语义。
2. 给 LLM 足够的 artifact / workflow 约束，避免生成形式合法但业务不贴合的 patch。
3. 统一 context 构造范式，避免每个 handler 自己随意拼 prompt。
4. 不让核心 DTO 枚举 construct。
5. 不让 PromptRenderer 枚举 construct。
6. 不让 extension facts 退化成 loose dict。
7. 不让 LLMRepairContext 成为第二套 repair capability truth source。
8. 保持现有 typed patch / user confirmation / verification 边界不变。
```

### 3.2 非目标

本设计不负责：

```text
1. 发现 editable issue。
2. 决定 issue 是否 repairable。
3. 决定 patch type 是否可用。
4. 修改 final SPL。
5. 生成 arbitrary IR。
6. 替代 RepairCatalog。
7. 替代 PatchRegistry。
8. 替代 VerificationRunner。
9. 替代 IRS / Gate / ProducerIndex authority。
10. 把 prompt context 持久化为 canonical artifact truth。
```

LLMRepairContext 是从 artifact snapshot 和 backend state 派生的运行时投影，不是新的 compiler source of truth。

---

## 4. 设计原则

### 4.1 Business facts first

LLM 默认看到的是用户可理解的业务事实：

```text
condition_text
output_name
output_description
worker purpose
source excerpt
nearby step summary
available variables
missing items
selected patch type
```

而不是：

```text
diagnostic_id
target_ref
irs_ref raw dump
exc_adapter_03
rcd_output_s13
worker_promotion:candidate_x
```

### 4.2 Internal ids are routing facts

Internal id 可以进入 prompt，但必须作为 selectable routing facts 出现。

允许：

```text
Use id "st_2" only as JSON payload field "step_id".
```

禁止：

```text
Title: Fix adapter error in exc_adapter_03
Handler text: Handle exc_adapter_03 by asking the user...
Explanation: This fixes worker_promotion:candidate_x...
```

### 4.3 Context comes from structured backend state

LLM context 只能来自：

```text
ArtifactSnapshot
EditableIssue
CompileDiagnostic structured metadata
RepairTarget
RepairContextBuilder output
RepairCatalog
PatchRegistry
TargetResolver
source spans / traces
typed IR artifacts
IssuePresentation / display facts
ProducerIndex structured facts
IRS structured facts
```

禁止从以下来源解析业务事实：

```text
feedback_report.md
compile_report.txt
rendered final SPL text
stage*.json debug artifact
diagnostic.message regex
LLM self-summary
```

`CompileDiagnostic.message` 可以作为 display/debug fallback，但不能作为 primary business fact。

### 4.4 Affordance-scoped extension, not construct enum

核心 DTO 不允许写成：

```python
construct_specific: (
    ExceptionFlowRepairFacts
    | RequiredOutputRepairFacts
    | WorkerPromotionRepairFacts
    | ...
)
```

正确方式：

```text
stable common context
+ primary_extension
+ auxiliary_extensions
```

extension 由以下 key 解析：

```text
affordance_id
+ construct_type
+ slot_name
+ diagnostic_kind
+ patch_type
```

不是：

```text
if construct_type == ...
```

也不是：

```text
if diagnostic.kind == ...
```

### 4.5 Capability truth source 不变

Repair capability 由 RepairCatalog 决定。

Patch payload schema / validator / applier / verifier 由 PatchRegistry 决定。

LLMRepairContextProvider 只收集 facts，不声明新的 patch capability。

### 4.6 Prompt rendering is shared infrastructure

handler 不再直接拼完整 prompt。

正确职责划分：

```text
RepairContextBuilder:
  收集 backend-oriented structured context。

LLMRepairContextBuilder:
  组合 common facts、primary extension、auxiliary extensions。

LLMRepairContextProvider:
  收集 affordance / patch-specific facts。

ContextPacker:
  控制 source excerpt、nearby steps、candidate summaries 的 token budget。

PromptRenderer:
  渲染 common sections、extension sections、payload schema、safety rules。

RepairHandler:
  调用 LLM，解析 JSON，构造 RepairSuggestion。
```

---

## 5. 总体架构

### 5.1 Generate suggestion 流程

```text
EditableIssue
  -> RepairCatalog lookup
  -> selected affordance_id / patch_type
  -> TargetResolver.resolve(...)
  -> RepairContextBuilder.build(...)
  -> IssuePresentationView build / lookup
  -> LLMRepairContextBuilder.build(...)
      -> build common facts
      -> resolve primary provider
      -> collect primary extension
      -> resolve auxiliary providers
      -> collect auxiliary extensions
      -> validate extension facts schema
      -> compute ContextQuality
      -> compute GenerationReadiness
  -> if generation_readiness allows generation:
      -> PromptRenderer.render(...)
      -> LLM call
      -> JSON parser
      -> PatchValidator
      -> RepairSuggestion
  -> else:
      -> return generation blocked / unavailable result
```

### 5.2 Apply suggestion 流程不变

```text
RepairSuggestion
  -> user confirmation
  -> base revision check
  -> patch precondition recheck
  -> PatchApplier
  -> patched artifact snapshot
  -> VerificationRunner
  -> accepted / rejected
```

### 5.3 Verification 流程不变

```text
VerificationRunner
  -> Lane A / Lane B
  -> compiler authority chain
  -> DiagnosticDiff
  -> patch-specific verifier
  -> VerificationResult
```

LLMRepairContext 不参与 verification authority。

---

## 6. 数据模型

### 6.1 JsonValue

```python
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
```

extension facts 在边界上必须 JSON-serializable，但 provider 内部可以使用 dataclass / TypedDict / Pydantic dataclass 等强类型结构。

---

### 6.2 LLMRepairContext

```python
@dataclass(frozen=True)
class LLMRepairContext:
    context_id: str
    session_id: str

    issue_facts: IssueFacts
    source_facts: SourceFacts
    target_facts: TargetFacts
    workflow_facts: WorkflowFacts
    artifact_facts: ArtifactFacts
    repair_action_facts: RepairActionFacts
    safety_facts: SafetyFacts
    previous_suggestion_facts: PreviousSuggestionFacts

    internal_routing: InternalRoutingFacts

    primary_extension: LLMRepairContextExtension
    auxiliary_extensions: tuple[LLMRepairContextExtension, ...] = ()

    quality: ContextQuality
    generation_readiness: GenerationReadiness
```

语义：

```text
primary_extension:
  由 selected affordance_id + selected patch_type 决定；
  负责主 repair action 所需 facts。

auxiliary_extensions:
  提供 supporting facts；
  例如 ProducerIndex facts、ResourceContractDemand facts、InvocationLocation facts；
  不改变 selected patch type。
```

不建议只使用：

```python
extensions: tuple[LLMRepairContextExtension, ...]
```

原因是 prompt 需要明确哪个 extension 是主任务，否则多个 extension 情况下 LLM 容易把 supporting facts 当成 repair target。

---

### 6.3 IssueFacts

```python
@dataclass(frozen=True)
class IssueFacts:
    issue_category: str
    user_facing_title: str
    what_was_detected: str
    missing_items: tuple[str, ...]
    why_it_matters: str | None
    suggested_resolution: str | None
    repairability: str
```

约束：

```text
不得把 raw diagnostic.message 直接作为 what_was_detected。
应优先复用 IssuePresentation / DisplayContext 的 user-facing summary。
```

---

### 6.4 SourceFacts

```python
@dataclass(frozen=True)
class SourceFacts:
    primary_source_excerpt: str | None
    related_source_excerpts: tuple[str, ...]
    source_section_label: str | None
    user_repair_instruction: str | None
    source_span_ids_internal: tuple[str, ...]
```

约束：

```text
source_span_ids_internal 只用于 audit / routing，不进入业务叙述。
```

---

### 6.5 TargetFacts

```python
@dataclass(frozen=True)
class TargetFacts:
    construct_type: str
    slot_name: str
    construct_role: str | None
    human_readable_target_summary: str
    current_construct_state: Mapping[str, JsonValue]
    parent_construct_summary: str | None
```

示例：

```text
Construct: EXCEPTION_FLOW
Missing slot: handler_action
Target summary: Exception flow for condition "Missing timeframe"
Parent worker: MainWorker
```

---

### 6.6 WorkflowFacts

```python
@dataclass(frozen=True)
class WorkflowFacts:
    worker_name: str | None
    worker_purpose: str | None
    flow_kind: str | None
    nearby_steps: tuple[StepSummary, ...]
    available_inputs: tuple[str, ...]
    available_outputs: tuple[str, ...]
    available_variables: tuple[str, ...]
    already_produced_variables: tuple[str, ...]
    required_outputs_still_missing: tuple[str, ...]
    relevant_constraints: tuple[str, ...]
```

```python
@dataclass(frozen=True)
class StepSummary:
    step_id_internal: str
    text: str
    command_type: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    flow_ref_internal: str | None
    block_ref_internal: str | None
    evidence_status: Literal[
        "source_backed",
        "user_confirmed_repair",
        "handoff_backed",
        "compiler_synthetic",
        "assumed",
    ]
    renderability_status: str | None
```

---

### 6.7 RepairActionFacts

```python
@dataclass(frozen=True)
class RepairActionFacts:
    affordance_id: str
    selected_patch_type: str
    patch_payload_schema: Mapping[str, JsonValue]
    allowed_command_types: tuple[str, ...]
    allowed_variable_names: tuple[str, ...]
    allowed_worker_ids: tuple[str, ...]
    allowed_step_ids: tuple[str, ...]
    allowed_output_names: tuple[str, ...]
    selectable_references: tuple[SelectableReference, ...]
    forbidden_actions: tuple[str, ...]
    verification_lane: str
```

约束：

```text
RepairActionFacts 完全由 RepairCatalog / PatchRegistry / TargetResolver 派生。
LLMRepairContextProvider 不能添加 RepairCatalog 未声明的 patch capability。
```

---

### 6.8 SelectableReference

```python
@dataclass(frozen=True)
class SelectableReference:
    id: str
    label: str
    summary: str
    kind: Literal[
        "worker",
        "step",
        "flow",
        "block",
        "output",
        "variable",
        "invocation_location",
        "resource",
        "handoff",
    ]
    payload_field: str
    business_summary: Mapping[str, JsonValue]
```

示例：

```python
SelectableReference(
    id="st_2",
    label="Candidate producer step",
    summary="Identify missing required fields.",
    kind="step",
    payload_field="step_id",
    business_summary={
        "inputs": ["user_request", "communication_type"],
        "outputs": ["missing_required_fields"],
        "command_type": "GENERAL_COMMAND",
        "renderability_status": "renderable",
    },
)
```

Prompt 中应渲染为：

```text
Allowed step id for JSON payload:
  id: st_2
  Summary: Identify missing required fields.
  Inputs: user_request, communication_type
  Outputs: missing_required_fields
  Use only as: step_id
```

规则：

```text
id 可以出现在 payload allowed ids section；
summary 必须伴随 id 出现；
LLM 不得把 id 写入 title / explanation / handler_text / producer_text。
```

---

### 6.9 InternalRoutingFacts

```python
@dataclass(frozen=True)
class InternalRoutingFacts:
    diagnostic_id: str
    target_ref: str
    irs_ref: Mapping[str, JsonValue]
    worker_id: str | None = None
    flow_id: str | None = None
    block_id: str | None = None
    step_id: str | None = None
    construct_id: str | None = None
    allowed_ids: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
```

约束：

```text
InternalRoutingFacts 默认不进入 business sections。
只有 PromptRenderer 的 internal allowed ids section 可以渲染它。
```

---

### 6.10 LLMRepairContextExtension

```python
@dataclass(frozen=True)
class LLMRepairContextExtension:
    extension_id: str
    provider_id: str

    role: Literal["primary", "auxiliary"]

    affordance_id: str
    construct_type: str
    slot_name: str
    diagnostic_kind: str
    patch_type: str

    facts_schema_id: str
    facts_schema_version: str
    facts_schema: Mapping[str, JsonValue]
    facts: Mapping[str, JsonValue]

    required_fact_keys: tuple[str, ...]
    optional_fact_keys: tuple[str, ...]

    renderer_id: str
    quality: ContextQuality
```

说明：

```text
facts 是 provider 输出的 affordance-specific facts。
facts 必须 JSON-serializable。
facts 必须通过 facts_schema validation。
PromptRenderer 不理解 facts 的业务结构，只委托 schema-bound extension renderer 渲染。
```

---

### 6.11 ContextQuality

```python
@dataclass(frozen=True)
class ContextQuality:
    confidence: Literal["high", "medium", "low"]
    has_primary_business_fact: bool
    has_source_excerpt: bool
    has_workflow_context: bool
    has_selectable_references: bool
    missing_context_fields: tuple[str, ...]
    warnings: tuple[str, ...]
```

用途：

```text
1. 阻止 provider 在缺失关键业务事实时退回 raw diagnostic.message。
2. 让 PromptRenderer 在 low confidence 时采用更保守的 instruction。
3. 让测试可以断言 context 完整性。
```

---

### 6.12 GenerationReadiness

```python
@dataclass(frozen=True)
class GenerationReadiness:
    status: Literal[
        "ready",
        "ready_low_confidence",
        "generation_blocked",
        "repair_unavailable",
    ]
    reasons: tuple[str, ...]
    missing_required_facts: tuple[str, ...]
    blocking_authority: Literal[
        "repair_catalog",
        "patch_registry",
        "target_resolver",
        "context_provider",
        "patch_precondition",
    ] | None
```

状态语义：

| 状态                     | 决定方                                            | 含义                                          | 是否调用 LLM |
| ---------------------- | ---------------------------------------------- | ------------------------------------------- | -------- |
| `repair_unavailable`   | RepairCatalog / PatchRegistry / TargetResolver | repair option 本身不可用                         | 否        |
| `generation_blocked`   | ContextProvider / LLMRepairContextBuilder      | repair option 可用，但生成 suggestion 必需 facts 缺失 | 否        |
| `ready_low_confidence` | ContextProvider / ContextQuality               | facts 不完整，但可生成保守 suggestion                 | 是        |
| `ready`                | LLMRepairContextBuilder                        | 上下文足够                                       | 是        |

例子：

```text
CreateWorkerHandoffContract 缺 child_worker_id:
  generation_blocked。
  因为 payload 无法合法绑定 child worker。

AddExceptionHandlerStep 缺 source_excerpt 但有 condition_text:
  ready_low_confidence。
  可以生成保守 handler suggestion。

RepairCatalog 没有该 affordance:
  repair_unavailable。
  provider 不应介入。
```

Provider 不能声明 “patch unavailable”，但可以声明：

```text
selected patch type 的 required generation facts 缺失，
因此本次 suggestion generation blocked。
```

---

## 7. Extension Provider 架构

### 7.1 Provider Registry

```python
class LLMRepairContextExtensionRegistry:
    def register(self, provider: LLMRepairContextProvider) -> None:
        ...

    def resolve_primary(
        self,
        *,
        affordance_id: str,
        construct_type: str,
        slot_name: str,
        diagnostic_kind: str,
        patch_type: str,
    ) -> LLMRepairContextProvider:
        ...

    def resolve_auxiliary(
        self,
        *,
        primary: LLMRepairContextExtension,
        issue: EditableIssue,
        target: RepairTarget,
        repair_context: RepairContext,
    ) -> tuple[LLMRepairContextProvider, ...]:
        ...
```

Registry lookup key：

```text
affordance_id
+ construct_type
+ slot_name
+ diagnostic_kind
+ patch_type
```

Primary provider resolution priority：

```text
1. exact affordance_id + patch_type
2. affordance_id default provider
3. construct_type + slot_name + patch_type fallback
4. unsupported
```

禁止：

```text
PromptRenderer 内部 if construct_type == ...
RepairHandler 内部 if issue.kind == ...
Service 内部枚举所有 construct provider。
```

---

### 7.2 Provider Protocol

```python
class LLMRepairContextProvider(Protocol):
    provider_id: str
    role: Literal["primary", "auxiliary"]

    affordance_id: str | None
    construct_type: str | None
    slot_name: str | None
    diagnostic_kinds: tuple[str, ...]
    supported_patch_types: tuple[str, ...]

    facts_schema_id: str
    facts_schema_version: str
    facts_schema: Mapping[str, JsonValue]

    renderer_id: str
    required_fact_keys: tuple[str, ...]
    optional_fact_keys: tuple[str, ...]

    def collect_facts(
        self,
        *,
        issue: EditableIssue,
        target: RepairTarget,
        repair_context: RepairContext,
        artifact_snapshot: ArtifactSnapshot,
        presentation_view: IssuePresentationView | None,
    ) -> LLMRepairContextExtension:
        ...
```

Provider 只负责：

```text
1. 从 typed backend state 收集 facts。
2. 生成 schema-validated extension facts。
3. 标注 ContextQuality。
4. 声明 facts_schema / renderer_id。
```

Provider 不得：

```text
1. 决定 issue 是否 repairable。
2. 决定 patch type 是否支持。
3. 修改 IR。
4. 调用 LLM。
5. 解析 rendered SPL。
6. 解析 feedback_report.md。
7. 从 raw diagnostic.message regex 提取业务事实。
8. 创建 RepairPatch。
```

---

### 7.3 Facts schema validation

Provider 输出 facts 后必须执行：

```text
facts_schema validation
required_fact_keys check
optional_fact_keys normalization
unknown key policy
renderer compatibility check
```

建议 policy：

```text
required_fact_keys 缺失:
  generation_blocked 或 ready_low_confidence，视 patch type 要求决定。

unknown facts key:
  默认拒绝。
  只有 schema 明确允许 additionalProperties 时才允许。

facts_schema_version mismatch:
  renderer registry 拒绝渲染，除非 renderer 声明兼容。
```

---

## 8. Section Renderer 架构

### 8.1 Renderer Protocol

```python
class LLMRepairContextSectionRenderer(Protocol):
    renderer_id: str
    facts_schema_ids: tuple[str, ...]

    def render(
        self,
        *,
        extension: LLMRepairContextExtension,
    ) -> str:
        ...
```

### 8.2 Renderer Registry

```python
class LLMRepairContextSectionRendererRegistry:
    def register(self, renderer: LLMRepairContextSectionRenderer) -> None:
        ...

    def get(
        self,
        *,
        renderer_id: str,
        facts_schema_id: str,
        facts_schema_version: str,
    ) -> LLMRepairContextSectionRenderer:
        ...
```

### 8.3 Renderer 约束

```text
1. 一个 renderer 只能服务一个 schema，或一组显式兼容 schema。
2. renderer registry 只做 lookup。
3. renderer 内部不得按 construct_type / patch_type 写大型 if-else。
4. schema 版本升级必须有 renderer compatibility test。
5. renderer 不得读取未声明 facts key。
6. renderer 不得决定 repair availability。
```

错误写法：

```python
if extension.construct_type == "EXCEPTION_FLOW":
    ...
elif extension.construct_type == "REQUIRED_OUTPUT":
    ...
```

正确写法：

```python
assert extension.facts_schema_id in self.facts_schema_ids
condition_text = extension.facts["exception_condition_text"]
...
```

---

## 9. PromptRenderer 设计

### 9.1 PromptRenderer 不枚举 construct

错误写法：

```python
if context.target_facts.construct_type == "EXCEPTION_FLOW":
    render_exception_flow_context(...)
elif context.target_facts.construct_type == "REQUIRED_OUTPUT":
    render_required_output_context(...)
```

正确写法：

```python
prompt = common_renderer.render_common_sections(context)

primary_renderer = renderer_registry.get(
    renderer_id=context.primary_extension.renderer_id,
    facts_schema_id=context.primary_extension.facts_schema_id,
    facts_schema_version=context.primary_extension.facts_schema_version,
)
prompt += primary_renderer.render(extension=context.primary_extension)

for extension in context.auxiliary_extensions:
    auxiliary_renderer = renderer_registry.get(
        renderer_id=extension.renderer_id,
        facts_schema_id=extension.facts_schema_id,
        facts_schema_version=extension.facts_schema_version,
    )
    prompt += auxiliary_renderer.render(extension=extension)

prompt += common_renderer.render_allowed_references(
    context.repair_action_facts.selectable_references
)
prompt += common_renderer.render_payload_schema(
    context.repair_action_facts.patch_payload_schema
)
prompt += common_renderer.render_safety_rules(context.safety_facts)
prompt += common_renderer.render_json_only_instruction()
```

### 9.2 标准 prompt 顺序

```text
1. Task
2. Issue facts
3. Source facts
4. Target construct facts
5. Local workflow facts
6. Primary repair context extension
7. Auxiliary context extensions
8. Allowed repair action
9. Selectable internal references
10. Payload schema
11. Safety rules
12. Previous suggestions
13. Output JSON only
```

### 9.3 Internal ids section

Internal ids section 必须明确标注：

```text
Internal allowed ids, do not use as business wording.
Use these only in JSON payload fields where ids are required.
Do not mention these ids in title, explanation, handler text,
producer text, request prompt text, or user-visible preview.
```

### 9.4 Low confidence behavior

当：

```python
context.generation_readiness.status == "ready_low_confidence"
```

PromptRenderer 应增加：

```text
The available context is incomplete.
Prefer a conservative clarification-style suggestion.
Do not invent missing business facts.
Use user_repair_instruction if provided.
If required business facts are absent, produce a suggestion that asks for the missing fact rather than fabricating an action.
```

当：

```python
context.generation_readiness.status in {
    "generation_blocked",
    "repair_unavailable",
}
```

不得调用 LLM。

---

## 10. 与 RepairCatalog / PatchRegistry 的关系

### 10.1 RepairCatalog 是 repair capability truth source

RepairCatalog 决定：

```text
which issue is editable
which affordance applies
which patch types are supported
which handler is used
which artifacts are editable
which verification lane is default
```

LLMRepairContext 只能消费这些结果，不能新增 capability。

### 10.2 PatchRegistry 是 payload truth source

PatchRegistry 决定：

```text
payload schema
validator
applier
verifier
preview generator
```

LLMRepairContext 中的 `patch_payload_schema` 必须由 PatchRegistry 提供。

### 10.3 Provider 是 facts collector，不是 capability owner

Provider 只补充：

```text
patch-specific facts
business context
artifact summaries
candidate summaries
selectable reference summaries
context quality
```

Provider 不应声明：

```text
new patch type
new verification lane
new repairability
```

---

## 11. 与 Presentation 层的关系

Issue Presentation 面向 UI / CLI 用户展示。

LLMRepairContext 面向 LLM suggestion generation。

二者可以共享 user-facing facts，但不能混同。

### 11.1 可以复用 Presentation 的内容

LLMRepairContext 可以复用：

```text
user_facing_title
human_readable_target_summary
suggested_resolution display text
missing item display text
```

### 11.2 不能依赖 Presentation 的内容

LLMRepairContext 不应依赖 Presentation 来决定：

```text
patch availability
payload schema
artifact facts
source provenance
producer candidates
worker handoff contracts
selectable ids
verification lane
```

### 11.3 Presentation copy 不是事实来源

规则：

```text
Presentation copy 可以影响“怎么向用户描述 issue”，
不应影响“LLM 认为有哪些业务事实可用于生成 patch”。
```

construct / slot / patch-specific facts 仍必须来自：

```text
ArtifactSnapshot
typed IR
RepairContext
source spans
traces
ProducerIndex structured facts
IRS structured metadata
TargetResolver output
```

---

## 12. MVP Provider 示例

注意：以下只是 MVP 注册项示例，不是核心 DTO 的静态枚举。

### 12.1 ExceptionFlowHandlerContextProvider

适用：

```text
construct_type = EXCEPTION_FLOW
slot_name = handler_action
patch_type = AddExceptionHandlerStep
```

facts schema id：

```text
exception_flow.handler_action.add_exception_handler_step.v1
```

强类型内部 facts 示例：

```python
@dataclass(frozen=True)
class ExceptionFlowHandlerFacts:
    exception_condition_text: str
    exception_source_excerpt: str | None
    parent_worker_purpose: str | None
    nearby_main_flow_steps: tuple[StepSummary, ...]
    available_variables_relevant_to_condition: tuple[str, ...]
    allowed_handler_command_types: tuple[str, ...]
```

JSON facts 示例：

```python
{
    "exception_condition_text": "Missing timeframe",
    "exception_source_excerpt": "Failure handling: Missing timeframe.",
    "parent_worker_purpose": "Draft internal communication.",
    "nearby_main_flow_steps": [
        {
            "text": "Identify missing required fields.",
            "outputs": ["missing_required_fields"]
        }
    ],
    "available_variables_relevant_to_condition": [
        "timeframe",
        "missing_required_fields"
    ],
    "allowed_handler_command_types": [
        "GENERAL_COMMAND",
        "REQUEST_INPUT",
        "DISPLAY_MESSAGE"
    ]
}
```

禁止：

```text
把 exc_adapter_03 当成 condition text。
把 target_ref 当成 prompt 主语。
把 raw diagnostic.message 当成 exception condition。
```

---

### 12.2 RequiredOutputProducerContextProvider

适用：

```text
construct_type = REQUIRED_OUTPUT
slot_name = producer
patch_type in {
  InsertProducerStep,
  BindExistingProducerStep
}
```

facts schema id：

```text
required_output.producer.producer_step.v1
```

facts 示例：

```python
{
    "required_output_name": "assumptions_log",
    "required_output_description": "Short log of assumptions for unresolved items.",
    "declaring_worker": "MainWorker",
    "existing_producer_candidates": [
        {
            "step_id_internal": "st_2",
            "step_text": "Identify missing required fields.",
            "inputs": ["user_request"],
            "outputs": ["missing_required_fields"],
            "command_type": "GENERAL_COMMAND",
            "renderability_status": "renderable",
            "why_it_may_or_may_not_bind": "Produces missing fields, not assumptions_log."
        }
    ],
    "existing_outputs_already_produced": [
        "draft_communication_artifact"
    ],
    "allowed_producer_command_types": [
        "GENERAL_COMMAND",
        "REQUEST_INPUT",
        "CALL_API"
    ],
    "bind_existing_step_is_allowed": true
}
```

SelectableReference 示例：

```python
SelectableReference(
    id="st_2",
    label="Existing renderable step",
    summary="Identify missing required fields.",
    kind="step",
    payload_field="step_id",
    business_summary={
        "inputs": ["user_request"],
        "outputs": ["missing_required_fields"],
        "command_type": "GENERAL_COMMAND",
        "renderability_status": "renderable",
    },
)
```

禁止：

```text
只给 step id，不给 step text / inputs / outputs。
伪造 ProducerIndex entry。
建议直接修改 OUTPUTS declaration。
```

---

### 12.3 WorkerPromotionHandoffContextProvider

适用：

```text
construct_type in {
  WORKER_PROMOTION,
  WORKER_HANDOFF
}

patch_type in {
  CreateWorkerHandoffContract,
  ConvertDelegationIntentToMainFlowStep,
  ConvertDelegationIntentToRequestInput
}
```

facts schema id 示例：

```text
worker_promotion.handoff_contract.create_or_convert.v1
```

facts 示例：

```python
{
    "candidate_source_excerpt": "Retrieve sources using approved source recipes.",
    "why_considered_delegation": "Source retrieval appears separable from drafting.",
    "parent_worker_purpose": "Orchestrate newsletter drafting.",
    "child_worker_purpose": "Retrieve approved sources.",
    "missing_handoff_slots": [
        "promotion_input_contract",
        "promotion_output_contract",
        "promotion_invocation_point",
        "promotion_result_handoff"
    ],
    "available_parent_variables": [
        "user_request",
        "known_topics"
    ],
    "child_input_contract_candidates": [
        "known_topics",
        "source_repositories"
    ],
    "child_output_contract_candidates": [
        "source_evidence_set"
    ],
    "expected_invocation_location_candidates": [
        "after determining communication type",
        "before drafting claims"
    ],
    "nearby_parent_flow_steps": []
}
```

不同 patch type 的 emphasis：

```text
CreateWorkerHandoffContract:
  强调 input/output binding candidates、invocation point、result handoff。

ConvertDelegationIntentToMainFlowStep:
  强调 original action source text、parent flow insertion context、expected outputs。

ConvertDelegationIntentToRequestInput:
  强调 missing information question、value target、why user input is needed。
```

---

### 12.4 Auxiliary Provider 示例

#### ProducerIndexAuxiliaryProvider

适用：

```text
missing_output_producer
resource contract producer issue
```

用途：

```text
提供 ProducerIndex structured candidate state；
不决定 patch type 是否可用；
不伪造 producer。
```

#### ResourceContractDemandAuxiliaryProvider

适用：

```text
REQUIRED_OUTPUT.producer
RESOURCE_CONTRACT_DEMAND.producer
```

用途：

```text
提供 required resource / materialized resource / alias issue group facts。
```

#### InvocationLocationAuxiliaryProvider

适用：

```text
CreateWorkerHandoffContract
INVOKE_WORKER binding repair
```

用途：

```text
提供可选 invocation location candidates；
每个 candidate 必须有 summary 和 payload id。
```

---

## 13. 代码目录建议

```text
src/nl2spl/compiler/spl_editing/
  llm_context/
    __init__.py

    model.py
      # LLMRepairContext, facts DTO, extension DTO,
      # ContextQuality, GenerationReadiness, SelectableReference

    builder.py
      # LLMRepairContextBuilder

    registry.py
      # LLMRepairContextExtensionRegistry

    provider.py
      # LLMRepairContextProvider Protocol

    rendering.py
      # PromptRenderer, common renderer

    section_renderer.py
      # LLMRepairContextSectionRenderer Protocol / registry

    packing.py
      # ContextPacker, excerpt budget, step ranking

    quality.py
      # ContextQuality evaluator

    readiness.py
      # GenerationReadiness evaluator

    schema.py
      # facts schema validation utilities

    selectable.py
      # SelectableReference builder helpers

    providers/
      __init__.py

      exception_flow_handler.py
      required_output_producer.py
      worker_promotion_handoff.py
      producer_index_auxiliary.py
      resource_contract_auxiliary.py
      invocation_location_auxiliary.py

    renderers/
      __init__.py

      exception_flow_handler_section.py
      required_output_producer_section.py
      worker_promotion_handoff_section.py
      producer_index_auxiliary_section.py
      resource_contract_auxiliary_section.py
      invocation_location_auxiliary_section.py
```

注意：

```text
providers/ 下可以有 MVP provider；
renderers/ 下可以有 MVP renderer；
但 model.py 中不能枚举这些 provider / renderer 类型。
```

---

## 14. 实施阶段

### L0: Contract Freeze

冻结：

```text
LLMRepairContext top-level DTO
primary_extension + auxiliary_extensions
LLMRepairContextExtension DTO
Provider Protocol
SectionRenderer Protocol
SelectableReference
GenerationReadiness
internal id exposure policy
raw diagnostic message policy
schema validation policy
```

验收：

```text
核心 DTO 不包含 construct-specific union。
PromptRenderer 不包含 construct_type if-else。
ProviderRegistry 支持按 affordance_id + patch_type resolve primary provider。
Extension facts 必须 schema validate。
```

---

### L1: Common Context Builder

实现：

```text
IssueFacts builder
SourceFacts builder
TargetFacts builder
WorkflowFacts builder
RepairActionFacts builder
InternalRoutingFacts builder
SelectableReference builder
ContextQuality baseline evaluator
GenerationReadiness evaluator
```

验收：

```text
不解析 feedback_report.md。
不解析 final SPL text。
不 regex parse raw diagnostic.message 作为业务事实。
RepairActionFacts 来自 RepairCatalog / PatchRegistry。
```

---

### L2: PromptRenderer / SectionRenderer

实现：

```text
common PromptRenderer
section renderer registry
internal allowed ids section
SelectableReference rendering
JSON-only output section
low-confidence prompt behavior
generation-blocked no-LLM behavior
```

验收：

```text
handler 不再直接拼完整 prompt。
target_ref / diagnostic_id 默认不进入 business sections。
internal ids 只能出现在 selectable references / internal allowed ids section。
```

---

### L3: MVP Provider 迁移 1 — missing_handler

实现：

```text
ExceptionFlowHandlerContextProvider
ExceptionFlowHandlerSectionRenderer
missing_handler handler migration
```

验收：

```text
Missing timeframe demo 中 prompt 包含 condition_text = Missing timeframe。
prompt business sections 不出现 exc_adapter_*。
LLM suggestion 不再围绕 adapter error。
```

---

### L4: MVP Provider 迁移 2 — missing_output_producer

实现：

```text
RequiredOutputProducerContextProvider
RequiredOutputProducerSectionRenderer
ProducerIndexAuxiliaryProvider
missing_output_producer handler migration
```

验收：

```text
prompt 包含 required_output_name / description。
existing producer candidates 包含 step text / inputs / outputs / renderability。
Bindable context 不再只是 step ids。
SelectableReference 为 step_id 提供 summary。
```

---

### L5: MVP Provider 迁移 3 — worker promotion / handoff

实现：

```text
WorkerPromotionHandoffContextProvider
WorkerPromotionHandoffSectionRenderer
InvocationLocationAuxiliaryProvider
type_or_contract_ambiguity handler migration for delegation subtype
```

验收：

```text
prompt 包含 candidate source excerpt。
prompt 区分 CreateWorkerHandoffContract / ConvertToMainFlowStep / ConvertToRequestInput 的不同 facts emphasis。
internal worker ids 不进入 user-facing wording。
CreateWorkerHandoffContract 缺 child_worker_id 时 generation_blocked。
```

---

### L6: Cleanup

清理：

```text
handler-specific full prompt builders
direct issue.message injection
direct target_ref injection
construct-type if-else in PromptRenderer
duplicated prompt safety instructions
loose facts dict without schema validation
```

---

### L7: Prompt audit snapshot

实现：

```text
prompt_context_snapshot.json
rendered_prompt.txt
generation_readiness.json
provider_facts_payloads.json
```

用途：

```text
debug suggestion 质量；
回归 Missing timeframe -> adapter error；
审计 internal id 是否泄漏到 business sections。
```

注意：

```text
audit snapshot 是 debug artifact，不是 canonical repair truth。
```

---

## 15. 测试矩阵

### 15.1 Model / Registry Tests

```text
LLMRepairContext core DTO does not enumerate construct-specific classes.
LLMRepairContext has primary_extension + auxiliary_extensions.
ExtensionRegistry resolves exact affordance_id + patch_type.
ExtensionRegistry rejects unsupported affordance.
Provider cannot register duplicate exact key unless explicitly overridden.
SectionRendererRegistry resolves renderer_id + facts_schema_id.
```

### 15.2 Schema Tests

```text
Provider facts must validate against facts_schema.
required_fact_keys missing triggers generation_blocked or ready_low_confidence.
unknown facts keys are rejected unless schema allows additionalProperties.
renderer cannot render unsupported facts_schema_id.
facts_schema_version mismatch is rejected unless renderer declares compatibility.
```

### 15.3 Common Context Tests

```text
IssueFacts uses IssuePresentationView when available.
SourceFacts carries source_span_ids_internal but does not expose them as business text.
TargetFacts builds human_readable_target_summary without target_ref.
RepairActionFacts is derived from RepairCatalog / PatchRegistry.
SelectableReference includes id + summary + payload_field.
InternalRoutingFacts contains target_ref and ids.
ContextQuality marks missing primary business fact as low confidence.
GenerationReadiness distinguishes repair_unavailable, generation_blocked, ready_low_confidence, ready.
```

### 15.4 Prompt Rendering Tests

```text
PromptRenderer renders fixed section order.
PromptRenderer does not branch on construct_type.
PromptRenderer renders primary extension before auxiliary extensions.
PromptRenderer renders internal ids only in selectable/internal allowed ids section.
PromptRenderer includes selected_patch_type and payload schema.
PromptRenderer adds conservative instruction for ready_low_confidence.
PromptRenderer refuses LLM call for generation_blocked / repair_unavailable.
PromptRenderer ends with JSON-only instruction.
```

### 15.5 Provider Tests

```text
ExceptionFlowHandlerContextProvider:
  extracts exception_condition_text from structured artifact / presentation facts.
  does not use raw diagnostic.message as condition.
  marks quality low if condition_text absent.
  blocks generation if handler payload cannot be targeted.

RequiredOutputProducerContextProvider:
  emits required output name and description.
  emits existing producer candidates with step text / inputs / outputs.
  emits SelectableReference for bindable step ids.
  rejects bind candidate with no renderability summary.

WorkerPromotionHandoffContextProvider:
  emits candidate source excerpt.
  emits parent / child purpose.
  emits missing handoff slots.
  adjusts facts by selected patch_type.
  blocks CreateWorkerHandoffContract generation if required child worker identity is absent.
```

### 15.6 Section Renderer Tests

```text
Each section renderer declares facts_schema_ids.
Renderer reads only declared facts keys.
Renderer does not branch on construct_type / patch_type with giant if-else.
Renderer golden output includes no target_ref in business text.
Renderer golden output includes selectable references with summaries.
```

### 15.7 Guardrail Tests

```text
Business sections do not include exc_adapter_*.
Business sections do not include target_ref.
Business sections do not include diagnostic_id.
LLM-generated title / explanation / handler_text must not include internal ids.
Prompt does not directly include raw CompileDiagnostic.message.
Prompt does not include rendered SPL as source.
Prompt does not include feedback_report.md content as source.
Selectable ids appear only in internal allowed ids / payload reference section.
```

### 15.8 Demo Regression Tests

```text
Missing timeframe:
  prompt contains "Missing timeframe";
  prompt does not frame the issue as adapter error;
  suggestion should ask for timeframe / deadline context or define a handler for missing timeframe.

Missing output producer:
  prompt contains output name and candidate step summaries;
  bind-existing suggestions reference step ids only in payload.

Delegation ambiguity:
  prompt contains source excerpt and missing handoff slots;
  prompt does not treat delegation_intent as ConstructIRS target;
  CreateWorkerHandoffContract missing child_worker_id returns generation_blocked.
```

---

## 16. API / CLI Behavior

### 16.1 Suggestion API response

When generation is ready:

```json
{
  "status": "ready",
  "suggestions": [...]
}
```

When context is low confidence:

```json
{
  "status": "ready_low_confidence",
  "warnings": [
    "source_excerpt_missing"
  ],
  "suggestions": [...]
}
```

When generation is blocked:

```json
{
  "status": "generation_blocked",
  "reasons": [
    "CreateWorkerHandoffContract requires child_worker_id, but no child worker target could be resolved."
  ],
  "missing_required_facts": [
    "child_worker_id"
  ],
  "suggestions": []
}
```

When repair is unavailable:

```json
{
  "status": "repair_unavailable",
  "reasons": [
    "No RepairCatalog entry supports the selected diagnostic target."
  ],
  "suggestions": []
}
```

### 16.2 CLI display

CLI should distinguish:

```text
Repair unavailable:
  This issue is not supported by Fix with AI.

Generation blocked:
  Fix with AI is supported, but required context is missing.

Low confidence:
  Fix with AI can generate a conservative suggestion, but review carefully.

Ready:
  Fix with AI can generate suggestions.
```

---

## 17. 验收标准

本设计完成后，必须满足：

```text
1. LLMRepairContext core DTO 不枚举 construct。
2. LLMRepairContext 使用 primary_extension + auxiliary_extensions。
3. extension facts 必须 schema-validated。
4. provider 由 affordance_id + patch_type registry resolve。
5. PromptRenderer 不写 construct_type if-else。
6. SectionRenderer 绑定 facts_schema_id，不成为新的巨型 if-else。
7. handler 不直接拼完整 prompt。
8. handler 不直接把 issue.message / target_ref 作为业务语义输入。
9. internal ids 只作为 SelectableReference / internal allowed ids 出现。
10. SelectableReference 必须包含 business summary 和 payload_field。
11. RepairActionFacts 只来自 RepairCatalog / PatchRegistry。
12. LLMRepairContext 不声明额外 patch capability。
13. 明确区分 repair_unavailable / generation_blocked / ready_low_confidence / ready。
14. low-confidence context 不强行生成确定性业务行为。
15. generation_blocked / repair_unavailable 不调用 LLM。
16. MVP 三类 issue 都完成 provider migration。
17. demo 中 Missing timeframe 不再生成 adapter error suggestion。
```

---

## 18. 最终判断

v2.1 的核心架构原则是：

```text
LLM Repair Context 是 registry-driven prompt context projection layer。
它不是 construct enum DTO；
不是第二套 RepairCatalog；
不是 handler-specific prompt 拼接工具；
不是 verification authority。
```

最终形态：

```text
Stable common context
+ primary / auxiliary affordance extensions
+ schema-validated extension facts
+ explicit generation readiness
+ selectable internal ids
+ schema-bound section renderers
+ shared PromptRenderer
+ no construct enum in core DTO
+ no repair capability outside RepairCatalog
```

与 SPL Editing 整体架构的关系：

```text
LLM 只生成 suggestion；
用户确认后才形成 repair evidence；
后端 apply typed IR patch；
compiler authorities 负责最终验证。
```

v2.1 的最大价值：

```text
直接解决 Missing timeframe -> adapter error 这类语义跑偏；
同时为未来大量 construct issue 和多 repair strategy 保留 registry/plugin 扩展路径。
```
