# AI-assisted SPL Editing 架构设计文档 v2

日期：2026-06-11  
状态：Revised architecture design for MVP implementation  
适用范围：NL2SPL 后端核心能力；未来 UI Diagnostics Console / Fix with AI 的后端基础

---

## 0. 核心结论

AI-assisted SPL Editing 不是“让 AI 重写 SPL”，也不是“让 AI 直接替换任意 IR”。它应定义为：

```text
Final diagnostic driven
+ IRS / compiler-authority scoped
+ user-confirmed evidence
+ typed IR repair patch
+ artifact snapshot based revision
+ existing compiler authority verification
```

实际 apply 的修复应该是 **IR 层面的 typed repair patch**，但必须明确：

```text
允许：后端确定性地把用户确认后的 RepairPatch 应用到 stage-level IR artifacts。
禁止：LLM 生成 arbitrary IR / Python object / SPL text 后直接替换。
禁止：绕过 IRS、Gate、ProducerIndex、DiagnosticConsolidator 和 Renderer。
```

MVP 必须覆盖三类用户可行动的 IRS / authority-backed issue：

```text
1. missing_handler
2. missing_output_producer
3. type_or_contract_ambiguity
```

但三类 issue 的 patch 深度不同：

```text
missing_handler:
  最小闭环最清晰，支持 AddExceptionHandlerStep。

missing_output_producer:
  支持 InsertProducerStep / BindExistingProducerStep，但必须由 ProducerIndex 验证。

type_or_contract_ambiguity:
  必须 subtype 化。MVP 至少覆盖 demo 中 delegation_intent missing handoff_contract 场景。
```

同时必须前置解决一个地基问题：

```text
user_confirmed_repair 必须被 Gate / IRS source-evidence predicate / provenance 正式识别。
```

否则 patch 写入 `StepIR` 后，新增 step 仍可能被 `ExecutableElementGate` 视为 assumed content 并过滤，导致“patch applied but SPL unchanged”的隐蔽失败。

---

## 1. 背景与定位

NL2SPL 当前已经是多阶段编译器，而不是 one-shot SPL generator：

```text
raw NL / canonical input
  -> span / route / worker planning / flow / block / resource / step
  -> normalization
  -> IRS / Gate / ProducerIndex / provenance
  -> SPL rendering + diagnostics + feedback report
```

其核心产品语义是：

```text
source-backed partial SPL
```

也就是：

```text
源文本或用户确认可以证明的内容才进入 SPL；
缺失的信息通过 diagnostics 暴露；
compiler 和 LLM 不应编造 executable behavior、handler、producer 或 handoff contract。
```

在这个基础上，Diagnostics Console 可以成为 AI-assisted SPL Editing 的 UI 入口。用户点击 issue 后，modal 展示 issue 信息，并提供 `Fix with AI`。AI 可以生成建议性文本和若干可预览的 SPL construct，但后端真正应用的是 typed repair patch。

UI 可展示：

```text
Suggested SPL construct preview
```

后端实际存储 / 应用：

```text
RepairSuggestion
  -> RepairPatch
  -> user confirmation
  -> deterministic patch apply to stage-level IR artifacts
  -> verification by existing compiler authorities
```

---

## 2. 修复边界

### 2.1 只修用户可行动的 IRS / authority-backed issue

AI-assisted SPL Editing 不修所有 diagnostics。MVP 只开放三类：

```text
missing_handler
missing_output_producer
type_or_contract_ambiguity
```

这些 issue 的共同特征是：

1. 来自 final / authoritative diagnostics。
2. 指向 SPL construct-level requirement gap。
3. 有可定位的 `target_ref` 或可解析的 target subtype。
4. 用户可以通过确认新增 requirement evidence 来修复。
5. 修复结果可以被 IRS、Gate、ProducerIndex、Renderer 或 DiagnosticDiff 验证。

### 2.2 不修内部 compiler health signal

以下 issue 不进入 Fix with AI apply 流程：

```text
route_refinement_corrected
ConstructPlan ownership fallback warning
validation warning
normalization note
missing_provenance
adapter warning
LLM output sanitation note
internal diagnostic dedup / consolidation note
```

这些可以展示在 developer console 或 advanced diagnostics 中，但不能作为用户-facing editable issue。原因是它们不是业务 requirement gap，而是 compiler 自身运行、修正、验证或可观测性信号。

### 2.3 final diagnostics 是入口，但不是修复规则本身

Editing 后端入口应来自结构化结果：

```text
PipelineResult.compile_diagnostics
+ intermediate_results / artifact snapshot
+ traces
+ assumptions
+ final SPL
```

而不是解析 `feedback_report.md`。`feedback_report.md` 是 human-readable artifact，不能作为后端修复依据。

`EditableIssueExtractor` 应执行如下过滤：

```text
Input:
  PipelineResult.compile_diagnostics

Filter:
  diagnostic.kind in RepairCatalog
  diagnostic is final / authoritative
  target_ref parseable or subtype-resolvable
  user_facing = true
  supported handler exists

Output:
  EditableIssue[]
```

如果当前 `CompileDiagnostic` 还没有 authority 字段，MVP 可以先使用：

```text
kind allowlist
+ target_ref shape
+ missing_slot
+ source_span_ids / metadata
```

长期应增加：

```python
DiagnosticAuthority = Literal[
    "post_normalize_irs",
    "producer_index",
    "gate",
    "construct_planner",
    "route_refinement",
    "validation",
    "provenance",
]
```

Editing 只接受：

```text
post_normalize_irs
producer_index    # 仅限 missing_output_producer 类 output producer 缺口
```

---

## 3. 对 demo 目录 issue 的修复认知

当前 demo 中适合 AI-assisted SPL Editing 的问题归为三类。

### 3.1 `missing_handler`

语义：

```text
EXCEPTION_FLOW 有 condition，但缺 handler_action。
```

这通常表现为：

```text
[EXCEPTION_FLOW: Template unavailable]
[END_EXCEPTION_FLOW]
```

这不是 compiler bug。它是 partial SPL 的预期行为：compiler 保留 source-backed exception condition，但不编造 handler。用户需要补充“发生该异常时应该做什么”。

MVP 修复方式：

```text
AddExceptionHandlerStep
```

后端 apply 的不是 SPL 文本，而是：

```text
在目标 worker 的 WorkerBlockPlanIR / WorkerStepPlanIR 中新增 exception-flow-local handler block / step。
```

必须设置：

```text
step.flow_ref = exception_flow_id
step.block_ref = exception-flow-local block_id
step.metadata.origin = user_confirmed_repair
step.metadata.repair_patch_id = patch_id
step.metadata.related_diagnostic_id = diagnostic_id
```

验证：

```text
原 missing_handler 消失；
目标 exception flow 有 renderable handler step；
Gate 不过滤新增 step；
最终 SPL 中该 EXCEPTION_FLOW 不再是空 skeleton；
无新增 blocking diagnostic。
```

### 3.2 `missing_output_producer`

语义：

```text
Required output 被声明，但没有合法、可渲染 producer。
```

这不能通过“修改 OUTPUTS 文本”解决。最终 authority 是 ProducerIndex / post-normalize 检查。有效修复必须让某个可渲染 step、worker handoff 或绑定关系实际 produce required output。

MVP 支持两个安全 patch type：

```text
InsertProducerStep
BindExistingProducerStep
```

`InsertProducerStep`：

```text
新增一个 user-confirmed producer step；
该 step.outputs 包含 missing required output；
该 step 位于 main flow 或指定 block；
ProducerIndex rerun 后能识别 producer。
```

`BindExistingProducerStep`：

```text
用户确认已有可渲染 step 的产物就是 required output；
后端更新该 step 的 output binding；
不新增 executable behavior。
```

禁止在 MVP 中做：

```text
直接把 required output 改成 optional；
删除 output declaration；
伪造 ProducerIndex entry；
只修改 final WorkerIR output；
只 patch SPL text。
```

验证：

```text
原 missing_output_producer 消失；
ProducerIndex 能找到 renderable producer；
新增或绑定的 step 未被 Gate 过滤；
未新增更严重 type_or_contract_ambiguity / missing_output_producer。
```

### 3.3 `type_or_contract_ambiguity`

语义：

```text
某个 construct 具有执行或委托意图，但缺少足够 type / contract 信息。
```

它不是单一问题，而是 umbrella diagnostic。可能包括：

```text
CALL_API 缺 api declaration / integration_ref
INVOKE_WORKER 缺 target_worker / handoff_id / input/output bindings
REQUEST_INPUT 缺 value target / source evidence
delegation_intent 缺 handoff_contract
ambiguous action 到底是 worker、API、main-flow step 还是 request-input
```

MVP 至少覆盖 demo 中的：

```text
delegation_intent:<span_or_fact_id> missing handoff_contract
```

对该 subtype，必须提供三种用户确认路径：

```text
CreateWorkerHandoffContract
  用户确认这是独立 worker delegation，补齐 input/output binding、invoke point、result handoff。

ConvertDelegationIntentToMainFlowStep
  用户确认这不是 delegation，而是 main worker 内部执行步骤。

ConvertDelegationIntentToRequestInput
  用户确认该动作需要向用户请求缺失信息或澄清，而不是自动执行。
```

注意：`type_or_contract_ambiguity` 修复不只是新增 step。对于 delegation intent，如果用户确认它不再是 delegation，还需要 resolution marker，避免原 delegation diagnostic 在 verification 中继续出现。

建议引入：

```text
RepairResolutionMarker:
  resolved_diagnostic_id
  original_target_ref
  resolution_kind
  repair_patch_id
```

例如：

```text
resolution_kind = converted_to_main_flow_step
```

---

## 4. Apply 层：IR patch 与 repair overlay

### 4.1 apply 是 IR 层面的，但不是 arbitrary IR replacement

正确路径：

```text
LLM generates candidate RepairPatch payload
  -> backend validates schema and preconditions
  -> user confirms
  -> backend deterministically applies typed patch
  -> compiler verification
```

错误路径：

```text
LLM generates proposed_ir: Any
  -> replace WorkerIR / StepIR / BlockIR
  -> rerender
```

后端 apply 的对象是 stage-level worker-scoped IR artifacts，例如：

```text
WorkerPlanIR
WorkerFlowPlanIR
WorkerBlockPlanIR
WorkerStepPlanIR
ResourceRegistryIR
SymbolTable
```

不应优先 patch Stage 10 `WorkerIR`。`WorkerIR` 是 assembler output，适合验证和 rendering，不适合作为持久编辑源。

### 4.2 持久化以 artifact snapshot + overlay event log 为准

原始方案中 “original NL + repair overlay -> regenerated compile result” 在长期方向上合理，但不能作为 MVP correctness foundation。原因是上游 LLM stage 可能漂移，target_ref 可能失效，完整 replay 不一定稳定。

MVP 持久化语义应改为：

```text
frozen editable artifact snapshot
+ repair overlay event log
+ patched artifact snapshot
+ verification result
```

推荐模型：

```python
@dataclass(frozen=True)
class EditRevision:
    base_compile_run_id: str
    artifact_snapshot_id: str
    overlay_version: int
    parent_overlay_id: str | None = None

@dataclass(frozen=True)
class RepairOverlayRecord:
    overlay_id: str
    base_compile_run_id: str
    base_artifact_snapshot_id: str
    overlay_version: int
    accepted_patches: list[AcceptedRepairPatch]
    patched_artifact_snapshot_id: str
```

多轮编辑语义：

```text
run_001 + artifact_snapshot_001 + overlay_version=0
  -> apply patch A
  -> artifact_snapshot_002 + overlay_version=1
  -> apply patch B
  -> artifact_snapshot_003 + overlay_version=2
```

hash 可以作为 artifact integrity check，但不作为 revision identity。MVP 使用：

```text
(run_id, artifact_snapshot_id, overlay_version_int)
```

作为并发与 stale patch 检查依据。

### 4.3 长期 full replay 是 rebase 问题，不是 MVP 保证

长期如果要支持：

```text
raw NL + overlay -> full recompile
```

需要额外能力：

```text
stable construct ids
target_ref remapping
overlay rebase
LLM output drift detection
patch conflict detection
```

MVP 不承诺 full NL replay 稳定。MVP 保证的是：

```text
从 frozen artifact snapshot 应用 patch 并重新验证。
```

---

## 5. User-confirmed repair evidence foundation

### 5.1 为什么必须前置

新增 `StepIR` 如果没有原始 source span，会被现有 anti-fabrication 机制视为 assumed content。仅写入 IR 不代表它能进入 SPL。必须让 compiler 区分：

```text
AI suggested but unconfirmed
user confirmed repair
source-backed original requirement
compiler synthetic scaffold
assumed unsourced content
```

用户确认后的 repair 不是 AI assumption，而是用户补充的 requirement evidence。

### 5.2 MVP evidence 表示

MVP 可以先使用 `StepIR.metadata` 表示：

```python
metadata = {
    "origin": "user_confirmed_repair",
    "repair_patch_id": patch_id,
    "related_diagnostic_id": diagnostic_id,
}
```

但这不是只写 metadata。必须同时修改 recognition layer。

### 5.3 必须集成的组件

新增：

```text
EvidenceKind.USER_CONFIRMED_REPAIR
```

并让以下组件识别：

```text
ExecutableElementGate
  metadata.origin == user_confirmed_repair 的 step 不应被判为 assumed。

Post-normalize IRS / source-evidence predicate
  user_confirmed_repair 可以作为 confirmed evidence，用于 handler、producer、request-input 等已确认修复。

ProvenanceAggregator
  记录 repair_patch_id、related_diagnostic_id、user_text、related_source_span_ids。
```

建议 origin 分类：

```python
class EvidenceKind(str, Enum):
    SOURCE_BACKED = "source_backed"
    USER_CONFIRMED_REPAIR = "user_confirmed_repair"
    COMPILER_SYNTHETIC = "compiler_synthetic"
    HANDOFF_GENERATED = "handoff_generated"
    ASSUMED = "assumed"
```

Gate 逻辑应近似为：

```text
source_span_ids 非空
  -> source_backed

metadata.origin == user_confirmed_repair
  -> user_confirmed_repair

metadata.origin == compiler_unpack
  -> compiler_synthetic

handoff_id 非空
  -> handoff_generated

else
  -> assumed
```

验收测试必须包括：

```text
StepIR.metadata.origin = user_confirmed_repair 的 step 不被 Gate 过滤。
该 step 能进入 rendered SPL。
provenance 中能看到 user-confirmed repair 来源。
```

---

## 6. Verification 设计

### 6.1 不默认 replay Stage 9.5

Stage 9.5 的 normalization 是否完全幂等需要代码级确认，不能作为 MVP 默认前提。VerificationRunner 应支持多条 lane。

### 6.2 Verification lanes

#### Lane A: Assembler Replay

适用：patch 只修改 worker-scoped flow/block/step artifacts，不涉及 handoff materialization、resource extraction、symbol reconstruction。

```text
patched WorkerFlowPlanIR / WorkerBlockPlanIR / WorkerStepPlanIR
  -> Stage 10 WorkerAssembler
  -> Post-normalize IRS
  -> ExecutableElementGate
  -> SPLRenderer
  -> DiagnosticConsolidator / DiagnosticDiff
```

适用 patch：

```text
AddExceptionHandlerStep
InsertProducerStep
BindExistingProducerStep
ConvertDelegationIntentToMainFlowStep
ConvertDelegationIntentToRequestInput
```

#### Lane B: Normalizer Replay

适用：patch 修改 worker plan、handoff contract、worker invocation、resource contract、symbol / binding 等需要 normalization 的结构。

```text
patched WorkerPlanIR / handoff / resource / symbol artifacts
  -> Stage 9.5 IRNormalizer
  -> Stage 10 WorkerAssembler
  -> IRS / Gate / Renderer / Diff
```

适用 patch：

```text
CreateWorkerHandoffContract
复杂 UpdateHandoffContract
API integration binding that affects normalization
```

Lane B 启用前必须确认目标 Stage 9.5 path 的幂等性，或将 normalizer 拆出纯函数化 verification entry。

#### Lane C: Full Recompile

```text
raw NL + repair overlay
  -> Stage 0-11
```

不作为 MVP 默认路径。仅作为长期能力或 debug mode。

### 6.3 通用 verification 成功条件

所有 patch 都必须满足：

```text
patch preconditions still hold
base revision not stale
patch target exists
original diagnostic resolved or explicitly marked resolved
no new error diagnostic
no new blocking completion diagnostic unless user explicitly accepts trade-off
rendered SPL changed as expected
```

### 6.4 patch-specific verification

patch-specific 条件不应写进通用 runner，而应放在：

```text
patches/<patch_type>/verifier.py
```

例如：

```text
AddExceptionHandlerStepVerifier:
  target exception flow has renderable handler step.

InsertProducerStepVerifier:
  ProducerIndex recognizes output producer.

CreateWorkerHandoffContractVerifier:
  WorkerPlanIR handoff valid, INVOKE_WORKER materialized, no handoff contract ambiguity.
```

---

## 7. 数据模型

### 7.1 EditableIssue

```python
@dataclass(frozen=True)
class EditableIssue:
    issue_id: str
    diagnostic_id: str
    kind: str
    target_ref: str
    missing_slot: str | None
    source_span_ids: list[str]
    message: str
    suggested_resolution: str | None
    blocks_rendering: bool
    blocks_completion: bool
    authority: str | None = None
    repairable: bool = True
    repair_catalog_entry_id: str | None = None
```

### 7.2 EditingSession

```python
@dataclass(frozen=True)
class EditingSession:
    session_id: str
    compile_run_id: str
    artifact_snapshot_id: str
    overlay_version: int
    issue: EditableIssue
    created_at: str
```

### 7.3 RepairTarget

```python
@dataclass(frozen=True)
class RepairTarget:
    target_ref: str
    target_kind: str
    construct_path: tuple[str, ...]
    worker_id: str | None
    editable_artifacts: list[str]
    subtype: str | None = None
```

### 7.4 RepairContext

```python
@dataclass(frozen=True)
class RepairContext:
    issue: EditableIssue
    target: RepairTarget
    related_diagnostics: list[CompileDiagnostic]
    related_traces: list[TraceRecord]
    source_spans: list[SpanIR]
    worker_scope: str | None
    related_steps: list[StepIR]
    related_outputs: list[str]
    related_worker_plan_refs: list[str]
    user_instruction: str | None
```

`RepairContext` 必须是 issue-specific 的，不能把整个 `intermediate` dump 给 LLM。

### 7.5 RepairSuggestion

```python
@dataclass(frozen=True)
class RepairSuggestion:
    suggestion_id: str
    session_id: str
    title: str
    explanation: str
    patch: RepairPatch
    spl_preview: str | None
    expected_effect: list[str]
    risks: list[str]
```

### 7.6 RepairPatch

```python
@dataclass(frozen=True)
class RepairPatch:
    patch_id: str
    patch_type: str
    target_ref: str
    base_compile_run_id: str
    artifact_snapshot_id: str
    overlay_version: int
    payload: RepairPatchPayload
    preconditions: list[PatchPrecondition]
    evidence: RepairEvidence
    verification_lane: str
```

### 7.7 RepairEvidence

```python
@dataclass(frozen=True)
class RepairEvidence:
    evidence_kind: Literal["user_confirmed_repair"]
    user_text: str
    related_source_span_ids: list[str]
    related_diagnostic_id: str
```

---

## 8. RepairCatalog

支持哪些 issue 和 patch 不应写死在 service 中，应由 catalog 声明。

```python
@dataclass(frozen=True)
class RepairCatalogEntry:
    entry_id: str
    diagnostic_kind: str
    missing_slot: str | None
    target_kind: str
    handler_id: str
    supported_patch_types: tuple[str, ...]
    auto_apply_supported: bool
    user_facing: bool = True
```

MVP catalog：

```python
REPAIR_CATALOG = [
    RepairCatalogEntry(
        entry_id="missing_handler.exception_flow",
        diagnostic_kind="missing_handler",
        missing_slot="handler_action",
        target_kind="EXCEPTION_FLOW",
        handler_id="missing_handler",
        supported_patch_types=("AddExceptionHandlerStep",),
        auto_apply_supported=True,
    ),
    RepairCatalogEntry(
        entry_id="missing_output_producer.required_output",
        diagnostic_kind="missing_output_producer",
        missing_slot="producer",
        target_kind="REQUIRED_OUTPUT",
        handler_id="missing_output_producer",
        supported_patch_types=("InsertProducerStep", "BindExistingProducerStep"),
        auto_apply_supported=True,
    ),
    RepairCatalogEntry(
        entry_id="type_or_contract_ambiguity.delegation_intent",
        diagnostic_kind="type_or_contract_ambiguity",
        missing_slot="handoff_contract",
        target_kind="DELEGATION_INTENT",
        handler_id="type_or_contract_ambiguity",
        supported_patch_types=(
            "CreateWorkerHandoffContract",
            "ConvertDelegationIntentToMainFlowStep",
            "ConvertDelegationIntentToRequestInput",
        ),
        auto_apply_supported=True,
    ),
]
```

主流程只能查 catalog / registry，不允许出现大量：

```python
if issue.kind == "missing_handler": ...
elif issue.kind == "missing_output_producer": ...
```

---

## 9. Patch 类型

### 9.1 AddExceptionHandlerStep

Payload：

```python
@dataclass(frozen=True)
class AddExceptionHandlerStepPayload:
    worker_id: str
    exception_flow_id: str
    handler_text: str
    command_type: Literal["GENERAL_COMMAND", "REQUEST_INPUT", "DISPLAY_MESSAGE"]
    inputs: list[str]
    outputs: list[str]
    insertion_policy: Literal["append_to_exception_flow"]
```

Apply：

```text
确保 exception-flow-local sequential block 存在；
新增 StepIR；
step.flow_ref = exception_flow_id；
step.block_ref = target block id；
step.metadata.origin = user_confirmed_repair；
更新 WorkerStepPlanIR / WorkerBlockPlanIR；
保存 overlay event。
```

Verification：Lane A。

---

### 9.2 InsertProducerStep

Payload：

```python
@dataclass(frozen=True)
class InsertProducerStepPayload:
    worker_id: str
    output_name: str
    producer_text: str
    command_type: Literal["GENERAL_COMMAND", "REQUEST_INPUT", "CALL_API"]
    insertion_target: Literal["main_flow", "block", "before_output"]
    block_ref: str | None = None
```

Apply：

```text
新增 user_confirmed_repair StepIR；
step.outputs 包含 output_name；
放入 main flow 或指定 block；
不直接修改 ProducerIndex；
由 verification rerun ProducerIndex / post-normalize checker 判定是否成功。
```

Verification：Lane A。

---

### 9.3 BindExistingProducerStep

Payload：

```python
@dataclass(frozen=True)
class BindExistingProducerStepPayload:
    worker_id: str
    step_id: str
    output_name: str
    binding_text: str
```

Apply：

```text
找到已有 renderable step；
用户确认该 step 产物就是 required output；
更新 step.outputs / result binding；
标记 user_confirmed_repair metadata；
不新增 executable behavior。
```

Verification：Lane A。

---

### 9.4 CreateWorkerHandoffContract

Payload：

```python
@dataclass(frozen=True)
class CreateWorkerHandoffContractPayload:
    delegation_intent_id: str
    parent_worker_id: str
    child_worker_name: str
    input_bindings: dict[str, str]
    output_bindings: dict[str, str]
    invocation_point: str
    result_handoff: str
```

Apply：

```text
更新 WorkerPlanIR / WorkerHandoffIR；
补齐 child worker candidate / handoff contract；
可能需要 Stage 9.5 INVOKE_WORKER materialization；
记录 resolution marker。
```

Verification：Lane B。

---

### 9.5 ConvertDelegationIntentToMainFlowStep

Payload：

```python
@dataclass(frozen=True)
class ConvertDelegationIntentToMainFlowStepPayload:
    delegation_intent_id: str
    worker_id: str
    action_text: str
    outputs: list[str]
    insertion_target: Literal["main_flow", "block"]
    block_ref: str | None = None
```

Apply：

```text
新增 main-flow user_confirmed_repair StepIR；
记录 resolution marker: converted_to_main_flow_step；
原 delegation_intent diagnostic 不应继续作为 unresolved handoff_contract gap。
```

Verification：Lane A。

---

### 9.6 ConvertDelegationIntentToRequestInput

Payload：

```python
@dataclass(frozen=True)
class ConvertDelegationIntentToRequestInputPayload:
    delegation_intent_id: str
    worker_id: str
    prompt_text: str
    value_target: str
    insertion_target: Literal["main_flow", "block"]
    block_ref: str | None = None
```

Apply：

```text
新增 REQUEST_INPUT StepIR；
value_target 明确；
标记 user_confirmed_repair；
记录 resolution marker: converted_to_request_input。
```

Verification：Lane A。

---

## 10. 代码目录结构

```text
src/nl2spl/compiler/spl_editing/
  __init__.py

  core/
    model.py
    catalog.py
    service.py
    registry.py
    revision.py
    errors.py

  issues/
    extractor.py
    filters.py
    target_ref.py

  targets/
    exception_flow.py
    required_output.py
    delegation_intent.py
    step.py
    handoff.py

  context/
    registry.py
    exception_flow_context.py
    required_output_context.py
    delegation_intent_context.py

  handlers/
    base.py

    missing_handler/
      handler.py
      prompt.py
      parser.py
      schemas.py

    missing_output_producer/
      handler.py
      prompt.py
      parser.py
      schemas.py

    type_or_contract_ambiguity/
      handler.py
      classifier.py
      context.py
      subhandlers/
        delegation_intent_contract.py
        request_input_contract.py
        call_api_contract.py
        invoke_worker_contract.py

  patches/
    base.py
    registry.py

    add_exception_handler_step/
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

    insert_producer_step/
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

    bind_existing_producer_step/
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

    create_worker_handoff_contract/
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

    convert_delegation_to_main_flow_step/
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

    convert_delegation_to_request_input/
      payload.py
      validator.py
      applier.py
      verifier.py
      preview.py

  evidence/
    model.py
    gate_bridge.py
    provenance_bridge.py

  verification/
    runner.py
    lanes.py
    diagnostic_diff.py
    predicates.py

  storage/
    artifact_snapshot_store.py
    session_store.py
    suggestion_store.py
    overlay_store.py
```

防止文件暴增的规则：

```text
1. 一个 patch type 一个目录。
2. 一个 diagnostic kind 一个 handler package。
3. umbrella diagnostic 必须 subtype 化。
4. service / runner / extractor / CLI 不写 diagnostic-kind if-else。
5. patch-specific verifier 不进入通用 VerificationRunner。
6. prompt / parser / schema 跟对应 handler 放一起。
7. SPL preview 只是 preview，不是 apply authority。
```

---

## 11. Runtime 流程

### 11.1 List issues

```text
PipelineResult
  -> EditableIssueExtractor
  -> RepairCatalog filter
  -> TargetRefParser / subtype resolver
  -> EditableIssue[]
```

### 11.2 Generate suggestions

```text
EditableIssue
  -> IssueTargetResolver
  -> RepairContextBuilder
  -> IssueRepairHandler
  -> LLM candidate RepairPatch payloads
  -> PatchValidator
  -> RepairSuggestion[]
```

LLM 只生成 patch payload，不生成 arbitrary IR。

### 11.3 Apply suggestion

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

### 11.4 Verify

```text
VerificationRunner
  -> select lane
  -> rerun compiler authority chain
  -> DiagnosticDiff
  -> Patch-specific verifier
  -> VerificationResult
```

---

## 12. CLI / API MVP

### CLI

```bash
spl-edit issues --run examples/output/demo

spl-edit suggest \
  --run examples/output/demo \
  --diagnostic irs_xxx \
  --instruction "Ask the requestor to provide an approved template."

spl-edit apply \
  --session edit_001 \
  --suggestion sug_001

spl-edit verify \
  --session edit_001
```

### API

```text
GET  /runs/{run_id}/editable-issues
POST /runs/{run_id}/issues/{issue_id}/suggestions
POST /editing-sessions/{session_id}/apply
GET  /editing-sessions/{session_id}/verification
```

---

## 13. 实施阶段

### Phase 0: Repairable diagnostics foundation

实现：

```text
EditableIssueExtractor
RepairCatalog
TargetRefParser
ArtifactSnapshotStore
EditRevision
```

验收：

```text
只提取 missing_handler / missing_output_producer / type_or_contract_ambiguity。
不提取 route_refinement_corrected / validation warning / ConstructPlan warning。
支持 artifact_snapshot_id + overlay_version stale check。
```

### Phase 0.5: User-confirmed evidence foundation

实现：

```text
EvidenceKind.USER_CONFIRMED_REPAIR
Gate bridge
IRS source evidence predicate bridge
Provenance bridge
```

验收：

```text
metadata.origin=user_confirmed_repair 的 StepIR 不被 Gate 过滤。
该 step 可进入 SPL render。
provenance 标记为 user-confirmed repair。
```

### Phase 1: missing_handler repair

实现：

```text
AddExceptionHandlerStep
exception_flow target resolver
exception_flow context builder
Lane A verification
```

### Phase 2: missing_output_producer repair

实现：

```text
InsertProducerStep
BindExistingProducerStep
required_output target resolver
ProducerIndex-oriented verification predicate
```

### Phase 3: type_or_contract_ambiguity repair

实现最低 demo subtype：

```text
delegation_intent_contract classifier
CreateWorkerHandoffContract
ConvertDelegationIntentToMainFlowStep
ConvertDelegationIntentToRequestInput
resolution marker
Lane A / Lane B selection
```

### Phase 4: CLI / API demo

实现：

```text
spl-edit issues
spl-edit suggest
spl-edit apply
spl-edit verify
updated SPL / diagnostics output
```

---

## 14. 测试矩阵

### 14.1 Unit tests

```text
EditableIssueExtractor:
  extracts only supported final diagnostics.
  excludes internal compiler diagnostics.

TargetRefParser:
  parses worker:worker_main.exception_flow:exc_adapter_01.
  parses required output target.
  resolves delegation_intent target.

RepairCatalog:
  maps each diagnostic kind to correct handler / patch types.

Gate bridge:
  user_confirmed_repair step is renderable.
  unconfirmed AI suggestion remains non-renderable.

Patch validators:
  reject wrong target_ref.
  reject stale revision.
  reject unsupported command type.
```

### 14.2 Patch tests

```text
AddExceptionHandlerStep:
  creates exception-flow-local block if missing.
  creates StepIR with correct flow_ref / block_ref.

InsertProducerStep:
  creates producer step with required output.
  does not fake ProducerIndex.

BindExistingProducerStep:
  binds existing renderable step to required output.
  rejects non-renderable step.

CreateWorkerHandoffContract:
  creates valid handoff contract.
  triggers Lane B verification.

ConvertDelegationIntentToMainFlowStep:
  creates main-flow step.
  records resolution marker.

ConvertDelegationIntentToRequestInput:
  creates REQUEST_INPUT with value target.
  records resolution marker.
```

### 14.3 Integration tests

```text
Demo run with missing_handler:
  apply AddExceptionHandlerStep.
  original missing_handler disappears.
  SPL exception flow has handler block.

Demo run with missing_output_producer:
  apply InsertProducerStep or BindExistingProducerStep.
  ProducerIndex recognizes producer.
  original missing_output_producer disappears.

Demo run with type_or_contract_ambiguity:
  classify delegation_intent_contract.
  apply one of three subtype patches.
  original ambiguity resolved or resolution marker suppresses exact diagnostic.
```

### 14.4 Anti-fabrication tests

```text
Unconfirmed AI suggestions do not affect SPL.
Patch cannot create CALL_API without API contract evidence.
Patch cannot create INVOKE_WORKER without handoff contract.
Patch cannot silently mark required output optional.
Patch cannot modify final SPL text directly.
Patch cannot bypass Gate / IRS / ProducerIndex.
```

---

## 15. 验收标准

MVP 完成时必须满足：

```text
1. Editing 只暴露三类 repairable issue，不暴露内部 compiler health diagnostics。
2. 三类 issue 都能生成 AI suggestions。
3. 三类 issue 都至少有一个 typed patch 可以 apply。
4. LLM 不输出 arbitrary IR，不直接输出 final SPL patch。
5. user_confirmed_repair 被 Gate / IRS / provenance 识别。
6. apply 后产生 patched artifact snapshot 和 overlay record。
7. verification 通过 Lane A / Lane B 明确执行，不默认假设 Stage 9.5 幂等。
8. missing_handler repair 后 exception flow 不再为空。
9. missing_output_producer repair 后 ProducerIndex 能识别 producer。
10. type_or_contract_ambiguity repair 有 subtype classifier 和 resolution marker。
11. no new blocking diagnostic regression。
12. 所有 patch 均可审计、可撤销到上一 artifact snapshot。
```

---

## 16. 最终判断

最新版设计应坚持以下架构原则：

```text
AI-assisted SPL Editing applies user-confirmed, typed repair patches to
compiler IR artifacts, not to rendered SPL text and not through arbitrary
LLM-generated IR replacement. The accepted repair is persisted against a
frozen artifact snapshot as an overlay event and must be re-validated by
existing compiler authorities.
```

中文表述：

```text
AI 辅助 SPL 编辑实际 apply 的是用户确认后的 typed IR repair patch。
它作用于 stage-level IR artifacts，并以 artifact snapshot + overlay event log 的方式持久化。
它不直接修改 SPL 文本，不接受 LLM 任意 IR 替换，也不绕过 IRS、Gate、ProducerIndex、DiagnosticConsolidator 和 Renderer。
```

这版设计相比上一版的关键修正是：

```text
1. MVP 覆盖三类 issue，而不是只覆盖 missing_handler。
2. Gate / IRS / provenance 对 user_confirmed_repair 的识别被前置为 Phase 0.5。
3. base_revision 改为 artifact_snapshot_id + overlay_version。
4. verification 分 Lane A / B / C，不默认 replay Stage 9.5。
5. overlay replay 语义降级为 snapshot-based MVP，full NL replay 是长期 rebase 能力。
6. type_or_contract_ambiguity 被明确 subtype 化，demo delegation_intent_contract 进入 MVP。
```
