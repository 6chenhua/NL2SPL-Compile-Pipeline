# AI-assisted SPL Editing 修订设计方案

## 0. 定位

AI-assisted SPL Editing 的目标不是让 AI 重写 SPL 文本，也不是让 AI 直接修改编译器内部任意 IR，而是：

```text
基于 final diagnostics 的、用户确认驱动的、受控 IR Patch 修复系统
```

系统入口来自现有 feedback report / compile diagnostics，例如：

- `missing_handler`
- `missing_output_producer`
- `type_or_contract_ambiguity`

系统出口必须回到现有编译器 authority：

- Post-normalize IRS 判断 construct slot satisfaction。
- `ExecutableElementGate` 判断 step 是否可渲染。
- `ProducerIndex` 判断 required output 是否有合法 producer。
- `DiagnosticConsolidator` 做最终 diagnostic merge / dedup。
- Renderer 只渲染已通过裁决的结构，不负责修补。

因此 Editing 模块本身不成为新的 correctness authority。它只负责把用户确认后的修复意图转换成受控 patch，并交给既有验证链路裁决。

---

## 1. 核心修正

原方案中“LLM 生成 `proposed_ir: Any`，用户确认后替换 `replacement_ir: Any`”需要修正。

### 1.1 不允许任意 IR 替换

LLM 不应直接返回完整 dataclass、任意 IR 子树或 Python 对象。原因：

- 当前编译结果不是单一 Construct IR 树，而是由 `WorkerPlanIR`、`WorkerFlowPlanIR`、`WorkerBlockPlanIR`、`WorkerStepPlanIR`、`ResourceRegistryIR`、`SymbolTable`、Stage 10 `WorkerIR` 等共同构成。
- 直接替换 post-normalize `WorkerIR` 的局部节点，可能无法回写到 stage-level IR，导致 rerun 后丢失。
- 直接插入无 source evidence 的 `StepIR`，可能被 `ExecutableElementGate` 过滤，修复看似应用但 SPL 不渲染。
- 直接修改 output declaration 无法让 `ProducerIndex` 认为 required output 已有 producer。

因此 MVP 必须使用 typed repair patch。

### 1.2 Editing 的真实产物是 RepairPatch

LLM 可以生成候选建议，但后端只接受结构化 patch：

```text
RepairSuggestion
  -> RepairPatch
  -> user confirmation
  -> backend applies patch
  -> verification
```

而不是：

```text
RepairSuggestion
  -> arbitrary proposed_ir
  -> replace construct
```

### 1.3 用户确认必须成为 evidence 语义的一部分

用户确认不只是 UI 状态。对于新增 handler step、producer step、contract detail 等，用户确认本质上是在补充 requirement evidence。

因此 MVP 需要显式引入：

```text
user_confirmed_repair evidence
```

它必须能被 provenance、gate、IRS 或 repair overlay 识别。否则新增 step 没有 `source_span_ids` 时，会被视为 assumption，不能稳定通过 renderability 裁决。

---

## 2. 总体架构

```text
CompileResult / PipelineResult
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
Persist accepted repair overlay / regenerated result
```

关键原则：

1. diagnostics 是入口，不是修复规则的替代品。
2. LLM 生成建议，不直接修改 IR。
3. 后端只应用已注册、已验证的 patch 类型。
4. 用户确认后的修复必须带 evidence/provenance。
5. 最终是否成功由 IRS、Gate、ProducerIndex、DiagnosticConsolidator 判断。

---

## 3. 数据模型

### 3.1 EditableIssue

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
```

来源：final `CompileDiagnostic`。

约束：

- 只允许 final diagnostics 进入 editing。
- stage-local diagnostics 默认不能直接编辑，除非被 final diagnostic 引用或显式暴露。
- `kind` 必须使用现有 diagnostic kind，例如 `type_or_contract_ambiguity`，不新增别名 `contract_ambiguity`。

### 3.2 EditingSession

```python
@dataclass(frozen=True)
class EditingSession:
    session_id: str
    compile_run_id: str
    base_revision: str
    issue: EditableIssue
    created_at: str
```

`base_revision` 用于防止用户在旧 compile result 上应用 patch。

MVP 可以用中间结果 hash 计算：

```text
hash(stage3_5_worker_plan, stage4_worker_flows, stage5_worker_blocks,
     stage6_worker_scoped_resources, stage7_worker_step_plan, stage10_worker,
     final diagnostics)
```

### 3.3 RepairContext

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

`RepairContext` 是 issue-specific 的。不能把整个 pipeline dump 给 LLM。

### 3.4 RepairTarget

```python
@dataclass(frozen=True)
class RepairTarget:
    target_ref: str
    target_kind: str
    construct_path: tuple[str, ...]
    worker_id: str | None
    editable_artifacts: list[str]
```

示例：

```text
target_ref = worker:worker_main.exception_flow:exc_adapter_01
target_kind = EXCEPTION_FLOW
editable_artifacts = ["worker_step_plan", "worker_block_plan"]
```

`missing_handler` 的 target 是 exception flow，但真实 patch 通常修改的是 worker-scoped step/block plan，而不是给 `ExceptionFlowRef` 填一个不存在的 `handler` 字段。

### 3.5 RepairSuggestion

```python
@dataclass(frozen=True)
class RepairSuggestion:
    suggestion_id: str
    session_id: str
    title: str
    explanation: str
    patch: RepairPatch
    expected_effect: list[str]
    risks: list[str]
```

### 3.6 RepairPatch

```python
@dataclass(frozen=True)
class RepairPatch:
    patch_id: str
    patch_type: str
    target_ref: str
    base_revision: str
    preconditions: list[PatchPrecondition]
    operations: list[PatchOperation]
    evidence: RepairEvidence
```

### 3.7 RepairEvidence

```python
@dataclass(frozen=True)
class RepairEvidence:
    evidence_kind: Literal["user_confirmed_repair"]
    user_text: str
    related_source_span_ids: list[str]
    related_diagnostic_id: str
```

说明：

- `related_source_span_ids` 表示修复关联的问题来源。
- `user_text` 表示用户确认的新需求内容。
- 这不是原始 source evidence，但应成为后续 gate/provenance 可识别的 confirmed evidence。

---

## 4. Patch 类型

### 4.1 MVP: AddExceptionHandlerStep

目标：修复 `missing_handler`。

适用条件：

- diagnostic kind 是 `missing_handler`。
- target_ref 指向 `worker:{worker_id}.exception_flow:{flow_id}`。
- 当前 exception flow 存在 condition。
- 当前 worker 中没有 `flow_ref == flow_id` 的 handler step。

Patch schema：

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

Patch effect：

- 在对应 `WorkerStepPlanIR` 或 repair overlay 中新增一个 `StepIR`。
- `flow_ref` 设置为 `exception_flow_id`。
- `block_ref` 指向该 exception flow 的 sequential block；若 block 不存在，新增一个 exception-flow-local sequential block。
- step metadata 标注：

```python
metadata = {
    "origin": "user_confirmed_repair",
    "repair_patch_id": patch_id,
    "related_diagnostic_id": diagnostic_id,
}
```

验证目标：

- 重新运行 assembly / post-normalize IRS 后，原 `missing_handler` diagnostic 消失。
- 新 step 不被 `ExecutableElementGate` 过滤。
- 没有新增 blocking diagnostic。

### 4.2 Post-MVP: InsertProducerStep

目标：修复 `missing_output_producer`。

风险：

- output 没 producer 通常不是 OutputIR 自身问题。
- 可能需要新增 command、绑定已有 command output、修改 handoff output binding、或调整 output optionality。
- `ProducerIndex` 是最终 authority，不能绕过。

因此第一版只定义 context/resolver，不实现 apply。

### 4.3 Post-MVP: UpdateHandoffContract

目标：修复 `type_or_contract_ambiguity` 中 worker/API contract 缺失。

风险：

- 可能涉及 `WorkerPlanIR`、`WorkerHandoffIR`、child worker spec、input/output bindings、invoke location。
- 修改一个 contract 可能影响 WorkerAssembler、Gate、ProducerIndex 和 renderer。

因此第一版只生成 human-readable clarification suggestions，不应用 IR patch。

---

## 5. Handler 设计

```text
spl_editing/
    __init__.py
    model.py
    issues.py
    context.py
    patches.py
    suggestions.py
    apply.py
    verify.py
    handlers/
        missing_handler.py
        missing_output_producer.py
        type_or_contract_ambiguity.py
```

Handler 不是用户插件扩展点，只是内部代码组织。

### 5.1 Handler 职责

每个 handler 负责：

1. 判断 issue 是否支持。
2. 构建 issue-specific context。
3. 构建 prompt。
4. 调 LLM 生成 candidate patch JSON。
5. 校验 patch schema。
6. 返回 `RepairSuggestion`。

Handler 不负责：

- 应用 patch。
- 修改 IR。
- 做最终 verification。
- 重写 diagnostics。

---

## 6. Missing Handler MVP 流程

### 6.1 Generate Suggestions

输入：

```json
{
  "diagnostic_id": "irs_38cc1fbf4aa1",
  "target_ref": "worker:worker_main.exception_flow:exc_adapter_01",
  "user_instruction": "Ask the requestor to provide an approved template."
}
```

后端解析：

```text
worker_id = worker_main
exception_flow_id = exc_adapter_01
condition = Template unavailable
missing_slot = handler_action
```

LLM 输出候选 patch，不输出任意 IR：

```json
{
  "patch_type": "AddExceptionHandlerStep",
  "handler_text": "Ask the requestor to provide an approved template before continuing.",
  "command_type": "REQUEST_INPUT",
  "inputs": [],
  "outputs": ["approved_template"],
  "insertion_policy": "append_to_exception_flow"
}
```

后端包装为 `RepairSuggestion` 并存储。

### 6.2 Confirm Suggestion

输入：

```json
{
  "session_id": "edit_001",
  "suggestion_id": "sug_002",
  "confirmed": true
}
```

后端动作：

1. 校验 session 和 `base_revision`。
2. 重新校验 patch preconditions。
3. 应用 typed patch。
4. 重新运行最小验证链路。
5. 如果原 issue resolved 且无新 blocking regression，则 accept。
6. 否则 reject，并返回 verification failure。

---

## 7. Verification

MVP verification 不能只看 patch 是否成功写入。必须看最终编译语义。

### 7.1 必跑检查

```text
RepairPatchApplier
  -> Stage 10 Worker assembly if patch applied to stage-level IR
  -> Post-normalize IRS
  -> ExecutableElementGate
  -> SPLRenderer
  -> DiagnosticConsolidator
```

### 7.2 成功条件

对 `missing_handler`：

- 原 diagnostic target 的 `missing_handler` 消失。
- 对应 exception flow 至少有一个可渲染 handler step。
- 新增 handler step 不产生 `assumed_command_not_renderable`。
- final SPL 中 exception flow 不再是空 skeleton。
- 不新增 error 或 blocking completion diagnostic。

### 7.3 失败条件

- patch precondition 不成立。
- patch target 不存在。
- base revision 过期。
- Gate 过滤了新增 step。
- IRS 仍报告同一个 missing slot。
- 新增 patch 导致 producer、contract、provenance 等更严重问题。

---

## 8. Persistence

MVP 不建议直接覆盖原始 source NL，也不建议只修改 final SPL。

建议引入 repair overlay：

```text
Compile input
  + UserConfirmedRepairOverlay
  -> replay compile / partial replay
```

Overlay 示例：

```json
{
  "overlay_id": "repair_overlay_001",
  "base_compile_run_id": "run_001",
  "repairs": [
    {
      "patch_id": "patch_001",
      "patch_type": "AddExceptionHandlerStep",
      "target_ref": "worker:worker_main.exception_flow:exc_adapter_01",
      "evidence_kind": "user_confirmed_repair",
      "user_text": "Ask the requestor to provide an approved template before continuing."
    }
  ]
}
```

后续可以把 overlay 作为 canonical input 的补充 evidence 注入 pipeline。这样不会污染原始需求，也能稳定 replay。

---

## 9. CLI MVP

由于 MVP 没有 UI，CLI 应模拟完整 generate -> confirm -> verify 流程。

### 9.1 list issues

```bash
spl-edit issues --run examples/output/demo
```

输出 editable diagnostics：

```text
irs_38cc1fbf4aa1  missing_handler  worker:worker_main.exception_flow:exc_adapter_01
irs_6c75ca545d04  missing_handler  worker:worker_main.exception_flow:exc_adapter_00
irs_b8f9448384d5  missing_handler  worker:worker_main.exception_flow:exc_adapter_02
```

### 9.2 suggest

```bash
spl-edit suggest \
  --run examples/output/demo \
  --diagnostic irs_38cc1fbf4aa1 \
  --instruction "Ask the requestor to provide an approved template."
```

输出：

```text
Suggestion sug_001
Patch type: AddExceptionHandlerStep
Handler: Ask the requestor to provide an approved template before continuing.
Expected effect: resolves missing handler for Template unavailable.
```

### 9.3 apply

```bash
spl-edit apply \
  --session edit_001 \
  --suggestion sug_001
```

输出：

```text
Patch applied: yes
Verification: passed
Resolved diagnostics:
  - irs_38cc1fbf4aa1
```

---

## 10. MVP 范围

### 10.1 支持

- 从 final diagnostics 提取 editable issues。
- 支持 `missing_handler`。
- 支持用户可选 instruction。
- 生成多个 typed repair suggestions。
- 用户确认后应用 `AddExceptionHandlerStep` patch。
- 运行 verification。
- 输出 updated SPL、updated diagnostics、repair overlay。

### 10.2 暂不支持

- 直接编辑 SPL text。
- 任意 `proposed_ir` 替换。
- 自动修复 `missing_output_producer`。
- 自动修复 `type_or_contract_ambiguity`。
- 多 issue 批量修复。
- 无用户确认自动应用。
- 直接修改原始 NL requirement。

### 10.3 预留

- `IssueTargetResolver` 支持 candidate targets。
- `RepairContextBuilder` 支持 issue-specific context。
- `RepairPatch` registry 支持新 patch type。
- `RepairOverlay` 支持 replay。

---

## 11. 关键设计决策

### 11.1 为什么不是 SPL text patch

SPL text 是 render result，不是 authority。文本 patch 会绕过 IRS、Gate、ProducerIndex 和 provenance，破坏现有 anti-fabrication 设计。

### 11.2 为什么不是 arbitrary IR patch

当前 IR 是多阶段、多 artifact 的结构。任意替换 post-normalize 节点无法保证 replay、provenance、renderability、producer semantics 一致。

### 11.3 为什么用户确认要进入 evidence

用户确认后的修复不是 AI assumption，而是用户补充需求。系统必须能区分：

```text
AI suggested but unconfirmed
user confirmed repair
source backed original requirement
compiler synthetic scaffold
```

否则新增 handler step 会被当成 assumed command，无法稳定渲染。

### 11.4 为什么 MVP 只做 missing_handler

`missing_handler` 的 target 清晰，修复动作可以限制为新增 exception-flow-local handler step。

`missing_output_producer` 和 `type_or_contract_ambiguity` 涉及跨 construct 数据流、handoff contract、producer semantics，不适合作为第一版自动 apply。

---

## 12. 实施顺序

### Phase 0: Read-only issue extraction

- `EditableIssueExtractor`
- final diagnostic filter
- target_ref parser
- issue list CLI

### Phase 1: Context + Suggestion

- `RepairContextBuilder`
- `MissingHandlerRepairHandler`
- typed patch JSON schema
- suggestion store
- prompt + parser tests

### Phase 2: Patch apply

- `RepairPatchValidator`
- `AddExceptionHandlerStepApplier`
- repair overlay model
- user-confirmed evidence metadata

### Phase 3: Verification

- post-normalize IRS rerun
- gate rerun
- renderer rerun
- diagnostic consolidation diff
- reject-on-regression rules

### Phase 4: CLI demo

- `spl-edit issues`
- `spl-edit suggest`
- `spl-edit apply`
- output updated SPL/report

---

## 13. 验收标准

### 13.1 Unit tests

- Can parse `worker:worker_main.exception_flow:exc_adapter_01`.
- Can extract editable `missing_handler` issue from final diagnostics.
- Can build missing-handler context from worker-scoped artifacts.
- LLM candidate JSON is rejected if patch type or target mismatches.
- `AddExceptionHandlerStep` creates step with correct `flow_ref`.
- Patch is rejected when base revision is stale.

### 13.2 Integration tests

- Demo report with three `missing_handler` diagnostics.
- Apply one handler repair.
- Rerun verification.
- The repaired target no longer emits `missing_handler`.
- Other two missing handlers remain.
- New handler renders inside the correct `[EXCEPTION_FLOW: ...]`.
- No synthetic handler is applied without user confirmation.

### 13.3 Anti-fabrication tests

- Generated suggestions are not persisted before confirmation.
- Unconfirmed AI suggestions do not affect SPL.
- Repair patch cannot create `CALL_API` or `INVOKE_WORKER` without required contract evidence.
- Repair patch cannot silently mark required output optional unless using a dedicated patch type and explicit user confirmation.

---

## 14. 最终结论

修订后的 AI-assisted SPL Editing 应定义为：

```text
Final diagnostic driven
+ typed repair patch
+ user-confirmed evidence
+ existing compiler authority verification
```

而不是：

```text
LLM proposed_ir
+ direct IR replacement
+ best-effort rerender
```

MVP 只实现 `missing_handler -> AddExceptionHandlerStep` 是合理的。它足够小，可以验证完整闭环：

```text
Issue -> Suggestion -> Confirmation -> Patch -> IRS/Gate/Render verification
```

一旦这个闭环成立，再扩展 `missing_output_producer` 和 `type_or_contract_ambiguity` 才有可靠基础。
