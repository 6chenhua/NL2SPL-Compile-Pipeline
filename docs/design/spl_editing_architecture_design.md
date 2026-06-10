# AI-assisted SPL Editing 架构设计文档

日期：2026-06-10  
状态：Draft for architecture planning  
适用范围：NL2SPL 后端核心能力；未来 UI Diagnostics Console / Fix with AI 的后端基础

---

## 1. 背景与定位

NL2SPL 当前已经不是 one-shot “自然语言直接生成 SPL” 的流程，而是一个多阶段编译器：上游 LLM stage 产出 constrained IR，下游确定性代码执行结构一致性检查、IRS 检查、Executable Gate、ProducerIndex、provenance 聚合与最终 SPL rendering。其目标是输出 source-backed partial SPL：源文本可以证明的内容被渲染，缺失的信息通过 diagnostics 暴露，而不是被 compiler 或 LLM 编造。

在这个基础上，`feedback_report.md` / `compile_diagnostics` 已经可以作为 AI-assisted SPL Editing 的入口。未来 UI 中可以有类似编译器的 Diagnostics Console，列出用户可修复的 issue。用户点击 issue 后打开 modal，展示 issue 详情，并提供 `Fix with AI` 按钮。AI 可以给出解释性建议和若干个可预览的 SPL construct 方案，但后端真正应用的修复必须是受控的 typed repair patch，而不是 SPL 文本替换，也不是任意 IR 替换。

本设计将 AI-assisted SPL Editing 定义为：

```text
Final diagnostic driven
+ user-confirmed evidence
+ typed IR repair patch
+ repair overlay persistence
+ existing compiler authority verification
```

而不是：

```text
LLM proposed_ir
+ direct IR replacement
+ best-effort rerender
```

核心原则是：Editing 模块只把用户确认后的修复意图转换成受控 patch，并交回现有 compiler authority 裁决。Editing 本身不成为新的 correctness authority。

---

## 2. 修复边界

### 2.1 只修 IRS / compiler authority 暴露出的用户可行动 requirement gaps

AI-assisted SPL Editing 不修所有 diagnostics。它只修用户可行动的、construct-level requirement gaps，初期限定为：

```text
missing_handler
missing_output_producer
type_or_contract_ambiguity
```

这些 issue 的共同特征是：

1. 来自 final / authoritative diagnostics。
2. 有稳定 `target_ref`。
3. 有 `missing_slot` 或可解析的 contract gap。
4. 用户可以通过补充 requirement evidence 来修复。
5. 修复结果可以被 IRS、Gate、ProducerIndex、DiagnosticConsolidator 或 Renderer 验证。

不进入 AI-assisted Editing 的 issue 包括：

```text
route_refinement_corrected
ConstructPlan ownership fallback warning
validation warning
normalization note
missing_provenance 之类的 compiler health signal
adapter warning
内部 diagnostic consolidation / dedup note
```

这些信息可以在 developer console 或 advanced diagnostics 中展示，但不应出现 `Fix with AI` apply 流程。原因是它们不是用户-facing SPL requirement gap，直接让 AI 修会混淆 compiler 内部健康信号和业务需求缺口。

### 2.2 final diagnostics 是入口，不是修复规则本身

Diagnostics Console 的入口应来自结构化 `PipelineResult.compile_diagnostics`，而不是解析 `feedback_report.md` 文本。`feedback_report.md` 是人类可读报告，不应成为后端修复依据。

`EditableIssueExtractor` 应执行如下过滤：

```text
Input: PipelineResult.compile_diagnostics
Filter:
  - diagnostic.kind in RepairCatalog
  - diagnostic is final / authoritative
  - target_ref parseable
  - user_facing = true
  - supported handler exists
Output:
  EditableIssue[]
```

如果当前 `CompileDiagnostic` 还没有 `diagnostic_authority` 字段，MVP 可以先用 kind allowlist + target_ref shape + missing_slot 判断；长期应显式增加 authority metadata，例如：

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

Editing 初期只接受：

```text
post_normalize_irs
producer_index    # 仅限 missing_output_producer 类 output producer 缺口
```

---

## 3. 对 demo 目录 issue 的修复认知

当前 demo feedback report 中，真正适合 AI-assisted SPL Editing 的问题可以归为三类：

```text
1. missing_handler
2. missing_output_producer
3. type_or_contract_ambiguity
```

同时，demo 中还出现 validation warnings、ConstructPlan ownership fallback、unused variable、missing_provenance 等信息。这些不属于第一阶段 AI-assisted Editing 的用户可 apply 修复范围。

### 3.1 missing_handler

Demo 中有三个 `missing_handler` 实例：

```text
worker:worker_main.exception_flow:exc_adapter_01
  condition: Template unavailable
  missing slot: handler_action

worker:worker_main.exception_flow:exc_adapter_00
  condition: Communications lead unresponsive for over two days
  missing slot: handler_action

worker:worker_main.exception_flow:exc_adapter_02
  condition: Topic summary too vague to draft from
  missing slot: handler_action
```

这类 issue 的含义是：源文本明确给出了 failure condition，compiler 已经保留了 partial exception flow，但源文本没有说明发生该异常时应该执行什么 handler action。

这不是 compiler bug。正确行为是：

```text
保留 [EXCEPTION_FLOW: condition]
不生成 handler command
发出 missing_handler diagnostic
等待用户补充 handler requirement
```

MVP 应完整支持这类 issue 的 AI-assisted repair。后端应生成 3 个左右的 handler 建议，用户确认其中一个后，应用 `AddExceptionHandlerStep` typed patch。

可行的 UI preview 例如：

```spl
[EXCEPTION_FLOW: Template unavailable]
    [SEQUENTIAL_BLOCK]
        COMMAND-? [INPUT Ask the requestor to provide an approved template VALUE approved_template:text SET]
    [END_SEQUENTIAL_BLOCK]
[END_EXCEPTION_FLOW]
```

但该 SPL preview 不是 apply authority。后端真正 apply 的是：

```text
AddExceptionHandlerStepPayload(
  worker_id="worker_main",
  exception_flow_id="exc_adapter_01",
  handler_text="Ask the requestor to provide an approved template before continuing.",
  command_type="REQUEST_INPUT",
  outputs=["approved_template"],
  insertion_policy="append_to_exception_flow"
)
```

### 3.2 missing_output_producer

Demo 中有一个 `missing_output_producer`：

```text
resource_contract_demand:rcd_output_s11
  materialized resource: finished_draft
  missing slot: producer
```

含义是：SPL/contract 中声明了 required output，例如 `finished_draft`，但当前 worker 中没有一个可渲染 producer step 能证明该 output 如何被产生。

这类 issue 不能简单通过“修改 OUTPUTS 声明”解决。Output declaration 只是 contract；是否有 producer 需要 ProducerIndex 判断。真正修复可能有多种路径：

```text
1. 新增 source-backed / user-confirmed producer step。
2. 把已有 step 的 output 绑定到 required output。
3. 通过 child worker handoff output binding 产生该 output。
4. 在用户明确确认后调整 output optionality 或移除 required output。
```

因此 Post-MVP 才应支持 auto-apply。MVP 中可提供 clarification suggestions 和 SPL preview，但不应自动应用 IR patch。原因是该问题涉及跨 construct 数据流、producer semantics、Gate 与 ProducerIndex，过早自动 apply 容易制造“看似修复但 ProducerIndex 仍不通过”的假修复。

### 3.3 type_or_contract_ambiguity

Demo 中有一个 `type_or_contract_ambiguity`：

```text
delegation_intent:s22
  missing slot: handoff_contract
```

含义是：源文本表达了委托/调用意图，但没有足够结构化信息证明它应该 materialize 为 `INVOKE_WORKER` 或 `CALL_API`。缺少的信息可能包括：

```text
target worker / API
input binding
output binding
invoke location
handoff contract
API declaration / integration evidence
```

正确行为是：

```text
不生成 INVOKE_WORKER
不生成 CALL_API
不降级成 generic command
报告 type_or_contract_ambiguity
等待用户补充 contract detail
```

MVP 中该类 issue 只生成 human-readable clarification suggestion，不做 auto-apply。后续可以拆成多个 subtype，例如：

```text
request_input_value_target
call_api_integration
invoke_worker_handoff
delegation_contract
api_declaration
```

每个 subtype 对应不同 patch type，而不是让一个巨大的 `type_or_contract_ambiguity.py` 承担所有逻辑。

---

## 4. IR patch 与 repair overlay 的正确关系

### 4.1 apply 应发生在 IR 层，但不是 arbitrary IR replacement

实际 apply 应是 IR 层面的 typed semantic repair，而不是 SPL text patch。原因：

1. SPL text 是 render result，不是 compiler authority。
2. 直接改 final SPL 会绕过 IRS、Gate、ProducerIndex、provenance 和 diagnostic consolidation。
3. 当前 compile result 不是单一 IR 树，而是多阶段、多 artifact 组合。
4. 直接替换 Stage 10 `WorkerIR` 节点无法稳定 replay。
5. 直接插入无 evidence 的 `StepIR` 会被 Gate 判定为 assumed，从而可能不渲染。

正确关系是：

```text
LLM suggestion
  -> typed RepairPatch payload
  -> user confirmation
  -> deterministic PatchApplier modifies stage-level IR artifacts
  -> VerificationRunner reruns compiler authority checks
  -> accepted patch persisted as RepairOverlay
```

### 4.2 Runtime apply 与 Persistence 分离

MVP 可以先在当前 run 的 `intermediate_results` 上做 in-memory patch，然后 partial replay Stage 9.5+ / Stage 10+。但长期持久化不应保存“被改过的中间 IR”作为唯一事实源，而应保存用户确认的 repair overlay。

推荐模型：

```text
Runtime apply:
  RepairPatch -> patched stage-level IR -> verification

Persistence:
  AcceptedRepairPatch -> UserConfirmedRepairOverlay

Replay:
  original compile input + repair overlay -> regenerated compile result
```

这样不会污染原始 NL requirement，也能支持版本控制、撤销、多轮编辑、重新编译和 UI 审计。

### 4.3 user_confirmed_repair 是 evidence，不是 UI 状态

用户确认后的修复不是 AI assumption，而是用户补充的 requirement evidence。系统必须区分：

```text
source_backed_original_requirement
user_confirmed_repair
compiler_synthetic_scaffold
AI_suggested_but_unconfirmed
assumed_unconfirmed
```

因此 `RepairEvidence` 必须被 Gate / provenance / IRS 或 overlay projector 识别。否则新增 handler step 即使写入 `WorkerStepPlanIR`，仍可能被 Gate 判定为 assumed command，从而被过滤。

推荐证据类型：

```python
class EvidenceKind(str, Enum):
    SOURCE_BACKED = "source_backed"
    USER_CONFIRMED_REPAIR = "user_confirmed_repair"
    COMPILER_SYNTHETIC = "compiler_synthetic"
    HANDOFF_GENERATED = "handoff_generated"
    ASSUMED = "assumed"
```

`StepIR.metadata.origin = "user_confirmed_repair"` 只是 MVP 兼容表示；长期应进入更结构化的 evidence / provenance model。

---

## 5. 总体后端架构

### 5.1 端到端流程

```text
PipelineResult / CompileResult
        |
        v
EditableIssueExtractor
        |
        v
IssueTargetResolver
        |
        v
RepairContextBuilder
        |
        v
IssueRepairHandler
        |
        v
LLM generates candidate RepairPatch payloads
        |
        v
RepairPatchValidator
        |
        v
SuggestionStore
        |
        v
User confirms suggestion_id
        |
        v
RepairPatchApplier
        |
        v
VerificationRunner
        |
        v
Persist accepted RepairOverlay / regenerated result
```

### 5.2 关键职责边界

`EditableIssueExtractor`：只从 final diagnostics 提取可编辑 issue，不判断如何修。

`IssueTargetResolver`：把 `target_ref` 定位到具体 construct 和可编辑 artifact。

`RepairContextBuilder`：构建 issue-specific context，不把整个 pipeline dump 给 LLM。

`IssueRepairHandler`：生成候选建议和 patch payload，不修改 IR。

`RepairPatchValidator`：验证 patch schema、target、preconditions 和 evidence。

`RepairPatchApplier`：确定性修改 stage-level IR artifact，不调用 LLM。

`VerificationRunner`：重新运行 compiler authority，并做 diagnostic diff，不生成 patch。

`RepairOverlayStore`：保存用户确认后的 repair overlay，不覆盖原始 NL。

---

## 6. 推荐代码目录结构

为了避免后续新增 repair type 时文件暴增，目录必须从第一版就按 registry + per-issue package + per-patch package 设计。

```text
src/nl2spl/compiler/spl_editing/
    __init__.py

    core/
        model.py
        errors.py
        catalog.py
        registry.py
        service.py

    issues/
        extractor.py
        filters.py
        target_ref.py

    targets/
        base.py
        exception_flow.py
        required_output.py
        step.py
        handoff.py
        api.py

    context/
        base.py
        builder_registry.py
        exception_flow_context.py
        required_output_context.py
        handoff_context.py
        api_context.py

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
            prompt.py
            parser.py
            schemas.py
            subhandlers/
                request_input.py
                call_api.py
                invoke_worker.py
                delegation_contract.py

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
        update_handoff_contract/
            payload.py
            validator.py
            applier.py
            verifier.py
            preview.py

    evidence/
        model.py
        overlay.py
        provenance_bridge.py

    verification/
        runner.py
        diagnostic_diff.py
        predicates.py

    storage/
        run_store.py
        session_store.py
        suggestion_store.py
        overlay_store.py

    cli.py
```

### 6.1 为什么不能保持扁平结构

以下扁平文件会快速暴增：

```text
patches.py
verify.py
context.py
type_or_contract_ambiguity.py
```

因为每一种 issue / patch 的 target 解析、context、prompt、payload、validation、apply、verification predicate 都不同。如果全部堆在一个文件里，后续维护会退化成大型 if-else。

### 6.2 主流程文件必须保持稳定

以下文件只做 orchestration / registry lookup，不写具体 issue 逻辑：

```text
core/service.py
issues/extractor.py
patches/registry.py
verification/runner.py
cli.py
```

禁止在这些文件中出现大量：

```python
if issue.kind == "missing_handler":
    ...
elif issue.kind == "missing_output_producer":
    ...
elif issue.kind == "type_or_contract_ambiguity":
    ...
```

主流程只能通过 catalog / registry 分派。

---

## 7. RepairCatalog

### 7.1 设计目的

`RepairCatalog` 是 issue kind 与 handler / patch type 的声明式映射。它防止主流程硬编码 issue 类型，也使 UI 能知道哪些 issue 可以 auto-apply、哪些只能 suggestion-only。

### 7.2 Catalog entry

```python
@dataclass(frozen=True)
class RepairCatalogEntry:
    diagnostic_kind: str
    missing_slot: str | None
    target_kind: str
    handler_id: str
    supported_patch_types: tuple[str, ...]
    auto_apply_supported: bool
    user_facing: bool = True
```

### 7.3 初始 catalog

```python
REPAIR_CATALOG = [
    RepairCatalogEntry(
        diagnostic_kind="missing_handler",
        missing_slot="handler_action",
        target_kind="EXCEPTION_FLOW",
        handler_id="missing_handler",
        supported_patch_types=("AddExceptionHandlerStep",),
        auto_apply_supported=True,
    ),
    RepairCatalogEntry(
        diagnostic_kind="missing_output_producer",
        missing_slot="producer",
        target_kind="REQUIRED_OUTPUT",
        handler_id="missing_output_producer",
        supported_patch_types=("InsertProducerStep", "BindExistingProducerStep"),
        auto_apply_supported=False,
    ),
    RepairCatalogEntry(
        diagnostic_kind="type_or_contract_ambiguity",
        missing_slot=None,
        target_kind="STEP_OR_HANDOFF_OR_API_OR_DELEGATION",
        handler_id="type_or_contract_ambiguity",
        supported_patch_types=(
            "AddRequestInputValueTarget",
            "BindCallApiIntegration",
            "UpdateHandoffContract",
            "AddApiDeclaration",
        ),
        auto_apply_supported=False,
    ),
]
```

---

## 8. 数据模型

### 8.1 EditableIssue

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
    diagnostic_authority: str | None = None
```

来源：final `CompileDiagnostic`。

### 8.2 EditingSession

```python
@dataclass(frozen=True)
class EditingSession:
    session_id: str
    compile_run_id: str
    base_revision: str
    issue: EditableIssue
    created_at: str
```

`base_revision` 用于防止用户在旧 compile result 上应用 patch。MVP 可基于关键 intermediate artifacts 与 final diagnostics hash 计算。

### 8.3 RepairTarget

```python
@dataclass(frozen=True)
class RepairTarget:
    target_ref: str
    target_kind: str
    construct_path: tuple[str, ...]
    worker_id: str | None
    editable_artifacts: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 8.4 RepairContext

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
    user_instruction: str | None
```

### 8.5 RepairSuggestion

```python
@dataclass(frozen=True)
class RepairSuggestion:
    suggestion_id: str
    session_id: str
    title: str
    explanation: str
    patch: RepairPatch
    preview: RepairPreview
    expected_effect: list[str]
    risks: list[str]
```

### 8.6 RepairPatch

```python
@dataclass(frozen=True)
class RepairPatch:
    patch_id: str
    patch_type: str
    target_ref: str
    base_revision: str
    payload: RepairPatchPayload
    evidence: RepairEvidence
    preconditions: list[PatchPrecondition]
```

### 8.7 RepairEvidence

```python
@dataclass(frozen=True)
class RepairEvidence:
    evidence_kind: Literal["user_confirmed_repair"]
    user_text: str
    related_source_span_ids: list[str]
    related_diagnostic_id: str
```

### 8.8 RepairOverlay

```python
@dataclass(frozen=True)
class UserConfirmedRepairOverlay:
    overlay_id: str
    base_compile_run_id: str
    base_revision: str
    repairs: list[AcceptedRepairPatch]
```

```python
@dataclass(frozen=True)
class AcceptedRepairPatch:
    patch_id: str
    patch_type: str
    target_ref: str
    evidence_kind: Literal["user_confirmed_repair"]
    user_text: str
    payload: dict[str, Any]
    related_diagnostic_id: str
    related_source_span_ids: list[str]
```

---

## 9. Patch 类型设计

### 9.1 MVP: AddExceptionHandlerStep

目标：修复 `missing_handler`。

适用条件：

```text
diagnostic.kind == missing_handler
target_ref == worker:{worker_id}.exception_flow:{flow_id}
missing_slot == handler_action
exception flow exists
current worker has no renderable handler step with flow_ref == flow_id
```

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

Apply effect：

```text
1. 在 WorkerBlockPlanIR 中确保 exception-flow-local SEQUENTIAL block 存在。
2. 在 WorkerStepPlanIR 中新增 StepIR。
3. StepIR.flow_ref = exception_flow_id。
4. StepIR.block_ref = exception-flow-local block_id。
5. StepIR.metadata.origin = user_confirmed_repair。
6. StepIR.metadata.repair_patch_id = patch_id。
7. StepIR.metadata.related_diagnostic_id = diagnostic_id。
8. 写入 repair overlay。
```

Verification：

```text
1. 原 target 的 missing_handler 消失。
2. 对应 exception flow 至少有一个 renderable handler step。
3. 新 handler step 未产生 assumed_command_not_renderable。
4. final SPL 中目标 exception flow 不再是空 skeleton。
5. 未新增 error 或新的 completion-blocking regression。
6. 其他未修复的 missing_handler 仍然保留。
```

### 9.2 Post-MVP: InsertProducerStep

目标：修复 `missing_output_producer`。

MVP 状态：suggestion-only；不 auto-apply。

后续可能 patch：

```text
InsertProducerStep
BindExistingProducerStep
BindHandoffOutputProducer
AdjustOutputOptionalityWithConfirmation
```

必须由 ProducerIndex 验证 producer 是否成立。Patch 不能直接修改 ProducerIndex 结果，也不能直接把 output 标记为 produced。

### 9.3 Post-MVP: UpdateHandoffContract / Contract Subtypes

目标：修复 `type_or_contract_ambiguity`。

MVP 状态：clarification suggestion-only；不 auto-apply。

后续应先 classifier，再 subhandler：

```text
type_or_contract_ambiguity/classifier.py
  -> request_input_value_target
  -> call_api_integration
  -> invoke_worker_handoff
  -> delegation_contract
  -> api_declaration
```

每个 subtype 对应独立 patch type。禁止把所有 contract ambiguity 写进一个大 handler。

---

## 10. VerificationRunner

### 10.1 统一验证链路

MVP verification 不能只看 patch 是否写入。必须看最终编译语义。

推荐最小链路：

```text
patched worker-scoped stage artifacts
  -> Stage 9.5 normalization / or minimal normalization bridge
  -> Stage 10 Worker assembly
  -> Post-normalize IRS
  -> ExecutableElementGate
  -> SPLRenderer
  -> DiagnosticConsolidator
  -> DiagnosticDiff
```

如果 MVP 只 patch Stage 10+ 可验证 artifact，也必须确保最终不绕过 Post-normalize IRS 和 Gate。

### 10.2 通用 runner 与 patch-specific verifier 分离

`verification/runner.py` 只负责跑统一链路，不写 patch-specific 成功条件。

Patch-specific 成功条件放在：

```text
patches/<patch_type>/verifier.py
```

例如：

```text
AddExceptionHandlerStepVerifier
InsertProducerStepVerifier
UpdateHandoffContractVerifier
```

这样 `verification/runner.py` 不会随着 repair type 增加而暴涨。

---

## 11. UI / API 语义

### 11.1 UI 展示 SPL construct preview，但后端 apply patch

UI modal 可以展示：

```text
issue summary
source span
current SPL fragment
missing slot
compiler reason
AI explanation
3 个 SPL construct preview
Apply 按钮
```

但后端语义是：

```text
Apply the typed RepairPatch that regenerates this SPL construct
```

不是：

```text
Insert this SPL text
```

### 11.2 API 草案

```text
GET  /runs/{run_id}/editable-issues
POST /runs/{run_id}/issues/{issue_id}/suggestions
POST /editing-sessions/{session_id}/apply
GET  /editing-sessions/{session_id}/verification
```

### 11.3 CLI MVP

```bash
spl-edit issues --run examples/output/demo

spl-edit suggest \
  --run examples/output/demo \
  --diagnostic irs_38cc1fbf4aa1 \
  --instruction "Ask the requestor to provide an approved template."

spl-edit apply \
  --session edit_001 \
  --suggestion sug_001
```

---

## 12. 新增 issue 修复的扩展流程

未来新增一个 repair type，应遵守固定流程：

```text
1. 确认 diagnostic 是否是 final authority 下的 user-facing requirement gap。
2. 在 RepairCatalog 增加 entry。
3. 增加或复用 TargetResolver。
4. 增加或复用 RepairContextBuilder。
5. 增加 IssueRepairHandler / subhandler。
6. 增加 Patch payload schema。
7. 增加 PatchValidator。
8. 增加 PatchApplier。
9. 增加 PatchVerifier。
10. 增加 PreviewRenderer。
11. 增加 unit / integration / anti-fabrication tests。
```

如果某个 repair 只能建议、不能安全 apply，则实现到 handler + preview，并在 catalog 中声明：

```python
auto_apply_supported = False
```

---

## 13. 防止文件暴增的工程规则

### 13.1 一个 patch type 一个目录

禁止把所有 patch payload、validator、applier、verifier 都塞进 `patches.py`。

### 13.2 一个 diagnostic kind 一个 handler package

普通 diagnostic 一个 handler package。Umbrella diagnostic 必须用 subhandlers。

### 13.3 主流程不得出现 diagnostic-kind if-else

主流程只能通过 RepairCatalog / Registry 查找 handler 和 patch type。

### 13.4 Verification runner 不写 patch-specific predicate

统一 replay 与 diagnostic diff 放在 runner；具体成功条件放在 patch verifier。

### 13.5 ContextBuilder 不 dump 全部 intermediate

每个 context builder 只收集 issue-specific 信息，包括目标 construct、相关 source spans、相关 diagnostics、相关 traces、相关 steps / outputs。

### 13.6 Prompt 与 parser 跟 handler 放一起

不同 issue 的 prompt 会快速分化，不能集中塞进一个 `prompts.py`。

### 13.7 Preview 不是 apply

Preview 只服务 UI。Apply 只走 typed patch。

---

## 14. 实施阶段

### Phase 0: Read-only editable issue extraction

目标：

```text
EditableIssueExtractor
RepairCatalog
TargetRefParser
spl-edit issues
```

范围：只列出 `missing_handler`、`missing_output_producer`、`type_or_contract_ambiguity`；其中只有 `missing_handler` 标记为 apply-supported。

### Phase 1: MissingHandler suggestion

目标：

```text
MissingHandlerRepairHandler
AddExceptionHandlerStepPayload schema
SuggestionStore
SPL preview generation
```

LLM 只输出 patch payload，不输出 arbitrary IR。

### Phase 2: AddExceptionHandlerStep apply

目标：

```text
PatchValidator
AddExceptionHandlerStepApplier
RepairOverlay model
user_confirmed_repair metadata
```

需要补充 Gate / provenance / IRS 对 `user_confirmed_repair` 的识别。

### Phase 3: Verification

目标：

```text
Stage 10 assembly rerun / or minimal replay
Post-normalize IRS rerun
Gate rerun
Renderer rerun
DiagnosticConsolidator diff
reject-on-regression
```

### Phase 4: CLI demo

目标：

```text
spl-edit issues
spl-edit suggest
spl-edit apply
updated SPL
updated diagnostics
repair overlay
```

### Phase 5: Post-MVP suggestion-only expansion

目标：

```text
missing_output_producer suggestion-only
 type_or_contract_ambiguity clarification-only
 subtype classifier scaffold
```

---

## 15. 测试矩阵

### 15.1 Unit tests

```text
EditableIssueExtractor:
  - extracts only catalog-supported final diagnostics
  - ignores validation warnings and internal diagnostics
  - ignores missing_provenance unless explicitly supported later

TargetRefParser:
  - parses worker:worker_main.exception_flow:exc_adapter_01
  - parses resource_contract_demand:rcd_output_s11
  - parses delegation_intent:s22

RepairContextBuilder:
  - builds missing-handler context without dumping full intermediate
  - includes source span, target flow, worker scope, related diagnostics

PatchValidator:
  - rejects mismatched patch_type
  - rejects stale base_revision
  - rejects target mismatch
  - rejects unsupported command_type

AddExceptionHandlerStepApplier:
  - creates exception-local block if missing
  - creates StepIR with correct flow_ref
  - creates StepIR with correct block_ref
  - attaches user_confirmed_repair metadata
```

### 15.2 Integration tests

```text
Demo run:
  - initial report has three missing_handler diagnostics
  - apply one AddExceptionHandlerStep repair
  - target missing_handler disappears
  - other two missing_handler diagnostics remain
  - final SPL renders handler inside correct EXCEPTION_FLOW
  - no new blocking diagnostic appears
  - repair overlay records accepted patch
```

### 15.3 Anti-fabrication tests

```text
Unconfirmed suggestions do not modify SPL.
LLM-generated arbitrary IR is rejected.
Patch cannot create CALL_API without API contract evidence.
Patch cannot create INVOKE_WORKER without handoff contract evidence.
Patch cannot silently mark required output optional.
Patch without user_confirmed_repair evidence is blocked by Gate or verifier.
```

---

## 16. 验收标准

MVP 完成时必须满足：

```text
1. Editing 只暴露 IRS / authority-backed user-facing requirement gaps。
2. missing_handler 支持 suggestion -> confirm -> apply -> verify 闭环。
3. AI 不直接修改 IR，不输出 arbitrary dataclass。
4. 后端只应用已注册 typed patch。
5. Apply 修改 stage-level worker-scoped IR artifact，而不是 final SPL。
6. 用户确认进入 user_confirmed_repair evidence。
7. Verification 通过 IRS、Gate、Renderer 和 diagnostic diff 判断成功。
8. Repair overlay 可保存 accepted patch。
9. missing_output_producer 与 type_or_contract_ambiguity 初期只 suggestion-only。
10. 新增 patch type 不需要修改主流程文件。
11. UI 展示 SPL preview，但后端 apply typed patch。
12. 未确认建议不会影响 SPL 输出。
```

---

## 17. 最终判断

AI-assisted SPL Editing 的价值不是让 AI “补写 SPL”，而是把 compiler 已经发现的 IRS requirement gaps 转化为用户可确认、可验证、可回放的 repair workflow。

最小可落地闭环应从 `missing_handler -> AddExceptionHandlerStep` 开始，因为它 target 清晰、patch 范围小、验证条件明确。`missing_output_producer` 和 `type_or_contract_ambiguity` 虽然同样属于用户可行动 gap，但涉及 producer semantics、handoff contract、API/worker binding 等跨 construct 问题，第一阶段应只做 suggestion / clarification，不做 auto-apply。

最终架构必须坚持：

```text
Diagnostics identify repairable gaps.
AI proposes typed repair candidates.
User confirmation becomes evidence.
Backend applies deterministic IR patch.
Compiler authorities verify correctness.
Repair overlay preserves replayability.
```

这条边界可以同时保护 NL2SPL 的 anti-fabrication 原则、partial-first 输出语义，以及未来 UI 中可交互 SPL editing 的可维护性。
