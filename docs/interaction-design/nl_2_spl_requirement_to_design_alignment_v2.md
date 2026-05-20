# NL2SPL 需求对齐与设计诊断增强方案

## 1. 背景

现有 NL2SPL 系统已经建立了编译式转换框架：先由大模型进行语义分析，生成可供代码消费的 IR；再由代码完成 SPL 组装、引用校验、结构校验和渲染。这一方向是正确的，也是实现需求对齐、partial SPL、溯源和诊断的基础设施。

但现有系统仍偏向“将自然语言转换为符合 SPL 语法的文本”。这会带来一个核心风险：当用户需求不完整时，系统可能为了生成完整 SPL 而擅自补全用户没有表达的需求，例如：

- 用户只列出 failure condition，系统却编造 handler command；
- 用户只提到 optional subtask，系统却生成完整 child worker 或 INVOKE_WORKER；
- 用户只声明 required output，系统却编造 producer step；
- 用户没有提到 exception flow，系统却为了填充模板生成空 exception flow。

这与 NL2SPL 的真实定位不一致。

本方案将 NL2SPL 重新定位为：

> 从不完备自然语言需求到 SPL 高层设计草案的渐进式编译过程。系统应最大努力把用户已经表达的信息结构化为 partial/complete SPL；对于缺失、不明确、冲突和系统推断，不得静默补全，而应通过 missing slot、diagnostic、trace、assumption 和 readable report 显式呈现。

---

## 2. 核心设计理念

### 2.1 Complete SPL as Refined Requirement

完整 SPL 可以被视为：

```text
完善后的需求 + 高层系统设计
```

因此，生成 SPL 的过程不是单纯格式转换，而是逐步发现和完善用户需求的过程。

当 SPL 所需的某个必要组成在用户需求中缺失时，系统必须承认缺失，并要求用户补齐，而不能未经用户同意擅自捏造需求。

---

### 2.2 Faithful Materialization

系统应最大努力结构化用户已经表达的信息。

如果用户表达了某个 SPL 结构的一部分，系统应生成该结构的已知部分，并标注缺失部分。

示例：

```text
Failure handling:
Missing timeframe, evidence shortage.
```

系统可以生成：

```spl
[EXCEPTION_FLOW: Missing timeframe]
[END_EXCEPTION_FLOW]

[EXCEPTION_FLOW: Evidence shortage]
[END_EXCEPTION_FLOW]
```

同时输出：

```text
missing_handler: failure mode is listed, but handling action is not specified.
```

系统不应编造：

```spl
COMMAND-1 [INPUT Ask user for timeframe ...]
```

除非用户明确说明了这种处理动作。

---

### 2.3 No Demand, No Structure

对于用户根本没有提及的 SPL 结构，系统应认为用户当前没有表达这方面需求，不得为了填满 SPL 模板而生成空结构。

规则：

```text
No source signal → do not generate structure
Partial source signal → generate partial structure + missing slot + diagnostic
Complete source signal → generate complete structure
```

示例：

| 用户需求 | 编译行为 |
|---|---|
| 用户没有提 failure / error / missing / invalid state | 不生成 EXCEPTION_FLOW |
| 用户只列出 Missing timeframe | 生成 partial EXCEPTION_FLOW condition，并标注 missing_handler |
| 用户说明 If timeframe is missing, ask the user | 生成 EXCEPTION_FLOW + handler command |
| 用户只说 Handle errors properly | 不生成具体 EXCEPTION_FLOW，输出 underspecified_exception_policy |

---

### 2.4 No Silent Fabrication

如果某个 SPL 行为元素没有用户需求支持，系统不得将其渲染为 executable SPL。

行为元素包括：

```text
COMMAND
INPUT
CALL_API
INVOKE_WORKER
EXCEPTION handler command
required output producer step
```

系统可以在 report 中提出建议，但建议不能直接进入 SPL 文本。

例如：

```text
Suggested resolution:
When timeframe is missing, consider asking the user for clarification.
```

这只是编译诊断建议，不是用户确认过的 SPL command。

---

### 2.5 Partial SPL with Missing Slots

Partial SPL 不是残缺文本，也不是无效 SPL。它是：

```text
语法上尽量合法；
语义上明确标注 incomplete slots；
已知结构尽量 materialize；
缺失行为不强行 invent。
```

Partial SPL 只适用于“用户已经表达了某个结构的一部分，但没有提供完整信息”的情况。

如果用户完全没有表达某类结构需求，则不生成该结构，也不报该结构缺失。

---

### 2.6 Provenance and Traceability

每个主要 SPL/IR 元素都必须能够追溯到原始需求。

系统应区分：

```text
direct      原文直接支持
normalized  原文直接支持，但做了命名、格式或结构规范化
inferred    基于原文线索合理推出
assumed     原文没有明确说明，只是系统假设或建议
```

其中：

- `direct / normalized` 通常可以渲染；
- `inferred` 是否可渲染取决于元素类型；
- `assumed` 的行为元素默认不渲染，只进入 report。

---

### 2.7 Human Confirmation Boundary

用户未确认的系统假设不得进入 executable SPL。

MVP 阶段不要求实现交互 UI，但必须输出 readable report，让用户知道：

- 哪些内容是原文明确支持的；
- 哪些内容是系统推断的；
- 哪些内容是系统假设的；
- 哪些地方缺失；
- 用户需要补充什么。

---

## 3. 输出形态

### 3.1 原输出形态

现有系统主要输出：

```text
SPL 文本 + validation report
```

### 3.2 新输出形态

应改为：

```text
SPL draft + diagnostics + traces + assumptions + readable report
```

建议新增统一结果结构：

```python
@dataclass
class CompileResult:
    spl_text: str
    completeness: Literal["complete", "partial", "blocked"]
    diagnostics: list[CompileDiagnostic]
    traces: list[TraceRecord]
    assumptions: list[CompileAssumption]
    validation_errors: list[str]
    validation_warnings: list[str]
    readable_report: str
```

字段说明：

| 字段 | 说明 |
|---|---|
| `spl_text` | partial or complete SPL draft |
| `completeness` | 整体输出是否完整 |
| `diagnostics` | 编译诊断，说明缺失、歧义、契约问题 |
| `traces` | SPL/IR 元素来源追踪 |
| `assumptions` | 编译阶段提出但未写入 SPL 的假设或建议 |
| `validation_errors` | 阻断渲染或严重语法/引用错误 |
| `validation_warnings` | 不阻断渲染的普通警告 |
| `readable_report` | 人可读编译报告，可命令行输出或写文件 |

---

## 4. 新增核心 IR / 数据结构

## 4.1 TraceRef

`TraceRef` 是挂在 IR 元素上的局部溯源信息。

```python
@dataclass
class TraceRef:
    source_span_id: str
    source_section_id: str | None = None
    source_packet_id: str | None = None
    quoted_text: str | None = None
    relation: Literal["direct", "normalized", "inferred", "assumed"] = "direct"
    explanation: str | None = None
```

### 字段来源

- `source_span_id`：来自 `SpanIR.span_id`，是 Phase 1 的最低必填溯源字段。
- `source_section_id`：来自 InputAdapter 的 `RawSection.section_id`。如果当前 InputAdapter 尚未接入，则允许为空。
- `source_packet_id`：来自 InputAdapter 的 `SemanticPacket.packet_id`。如果当前 InputAdapter 尚未接入，则允许为空。

Phase 1 不阻塞于 InputAdapter。如果上游还没有 `section_id` / `packet_id`，则先只填 `source_span_id`，后续 InputAdapter 完成后再补全 section/packet provenance。

### relation 定义

| relation | 定义 | 示例 |
|---|---|---|
| `direct` | 原文直接支持，语义几乎未变化 | “Require evidence for sourced claims” → Constraint |
| `normalized` | 原文直接支持，但做了格式化、命名规范化或结构化 | “A user request” → `user_request: text` |
| `inferred` | 根据原文线索推出结构，但没有新增行为需求 | failure list → EXCEPTION_FLOW condition |
| `assumed` | 原文没有明确说明，系统做出的设计假设或建议 | missing timeframe → ask user for timeframe |

### relation 填写策略

MVP 采用 **生成时填写** 策略。

也就是说，每个 LLM Stage 在生成 IR 时必须同时输出 `trace_refs`，并说明 relation：

```text
Stage 1/2/3: 对 span 切分、路由、拆分结果填写 direct/normalized。
Stage 4/5: 对 flow/block 结构填写 direct/inferred。
Stage 6: 对变量、输入、输出填写 direct/normalized/inferred。
Stage 7: 对 step/command 填写 direct/inferred/assumed。
Stage 9: 对 constraint 填写 direct/normalized/inferred。
Stage 9.5: 代码校验 trace_refs 是否存在，并可将明显不合法的 relation 降级或标记 diagnostic。
```

不采用“完全由后置 TraceAnalyzer 事后判断”的策略，因为事后组件无法可靠恢复 LLM 生成 IR 时的依据。

代码侧责任：

```text
1. 校验 trace_refs 是否存在。
2. 校验 source_span_id 是否有效。
3. 对缺失 relation 的旧 IR 进行保守默认：direct if exact source-backed, otherwise inferred。
4. 对 assumed executable behavior 交给 Executable Element Gate 阻断渲染。
```

### 应添加 trace_refs 的 IR

优先添加到：

```text
VariableSpec
Flow item / ExceptionFlow item / AlternativeFlow item
BlockIR
StepIR
ConstraintIR
WorkerIR / WorkerSpecIR
WorkerHandoffIR
Resource/API/TypeSpec
```

---

## 4.2 TraceRecord

`TraceRecord` 是最终输出报告中的溯源记录。

```python
@dataclass
class TraceRecord:
    target_ref: str
    source_span_ids: list[str]
    relation: Literal["direct", "normalized", "inferred", "assumed"]
    explanation: str
    needs_confirmation: bool
```

职责：

```text
说明某个 SPL/IR 元素从哪里来、如何来、是否需要用户确认。
```

示例：

```json
{
  "target_ref": "exception_flow:missing_timeframe",
  "source_span_ids": ["s_failure_1"],
  "relation": "inferred",
  "explanation": "The source lists 'Missing timeframe' as a failure mode, so it is materialized as an exception condition.",
  "needs_confirmation": false
}
```

---

## 4.3 MissingSlot

`MissingSlot` 表示某个已经 materialized 的 SPL/IR 元素缺少必要组成。

```python
@dataclass
class MissingSlot:
    slot_name: str
    required_for: str
    reason: str
    source_span_ids: list[str]
    suggested_question: str | None = None
```

示例：

```json
{
  "slot_name": "handler_action",
  "required_for": "complete_exception_flow",
  "reason": "The source lists 'Missing timeframe' as a failure mode but does not specify how to handle it.",
  "source_span_ids": ["s_failure_1"],
  "suggested_question": "When timeframe is missing, should the agent ask the user, block finalization, or continue with assumptions?"
}
```

---

## 4.4 ElementStatus

`ElementStatus` 描述 IR 元素是否完整。

```python
@dataclass
class ElementStatus:
    completeness: Literal["complete", "partial", "unknown"]
    missing_slots: list[MissingSlot]
```

注意：

- `ElementStatus` 不包含 derivation/relation；
- 来源关系由 `TraceRef` 和 `TraceRecord` 管理；
- 避免同一信息在两个结构中重复维护。

---

## 4.5 CompileDiagnostic

MVP 只实现 4 类诊断。

```python
@dataclass
class CompileDiagnostic:
    diagnostic_id: str
    kind: Literal[
        "missing_handler",
        "missing_output_producer",
        "type_or_contract_ambiguity",
        "assumed_command_not_renderable",
    ]
    severity: Literal["info", "warning", "error"]
    message: str
    target_ref: str | None
    source_span_ids: list[str]
    suggested_resolution: str | None
```

### diagnostic kind 说明

| kind | 触发条件 |
|---|---|
| `missing_handler` | 已知具体 failure/exception condition，但缺少 handler action |
| `missing_output_producer` | required output 已声明，但没有 producer step |
| `type_or_contract_ambiguity` | 变量类型、worker IO、handoff、API 契约、模糊 exception policy 不清楚或冲突 |
| `assumed_command_not_renderable` | Step/Command 的行为语义只有 assumed 来源，因此不能渲染成 executable SPL |

不进入 MVP 的诊断：

```text
missing_trigger
deep semantic duplicate
policy semantic conflict
semantic drift risk
```

说明：

- `missing_trigger` 需要把 failure condition 与可能触发它的 step 做语义关联，MVP 暂不实现。
- “Handle failures properly” 这类泛化异常要求归入 `type_or_contract_ambiguity`，不新增 `underspecified_exception_policy` 诊断类型。

---

## 4.6 CompileAssumption

`CompileAssumption` 记录系统提出但未写入 SPL 的设计假设或建议。

```python
@dataclass
class CompileAssumption:
    assumption_id: str
    target_ref: str
    source_span_ids: list[str]
    text: str
    reason: str
    suggested_resolution: str | None
    related_missing_slot: str | None = None
```

MVP 策略：

```text
CompileAssumption 不进入 SPL 文本，只进入 CompileResult.assumptions 和 readable_report。
```

### 与 MissingSlot 的关系

- `MissingSlot` 描述缺口：缺什么。
- `CompileAssumption` 描述建议：可以怎么补。
- 同一个问题可以同时有 MissingSlot 和 CompileAssumption，但 readable_report 中必须合并展示，不能显示成两条互不相关的问题。

示例：

```json
{
  "assumption_id": "a1",
  "target_ref": "exception_flow:missing_timeframe",
  "source_span_ids": ["s_failure_1"],
  "text": "Missing timeframe may be handled by asking the user for clarification.",
  "reason": "The source lists the failure mode but does not specify a handling action.",
  "suggested_resolution": "Confirm whether the agent should ask for timeframe, block finalization, or continue with assumptions.",
  "related_missing_slot": "handler_action"
}
```

---

## 5. Materialization Rules

## 5.1 通用规则

```python
def materialize(structure_type, evidence):
    if evidence.none:
        return "do_not_generate"
    if evidence.partial:
        return "generate_partial_with_missing_slot"
    if evidence.complete:
        return "generate_complete"
```

---

## 5.2 Worker

| 情况 | 编译行为 |
|---|---|
| 至少存在一个明确 behavior/process/action span | 可生成默认 MainWorker |
| 只有 persona/rule/domain，没有行为或任务动作 | 不生成可执行 MainWorker；输出 blocked 或 partial diagnostic |
| 明确 delegation / subtask，但缺 IO/handoff | 生成 CandidateTaskUnitIR，不生成 child worker |
| 有 purpose + input + output + invocation point + result handoff | 生成 child worker |
| 只是单次 API call | 不生成 child worker，使用 CALL_API |
| 用户没有提子任务 | 不生成 child worker |

MainWorker 不是无条件模板。它至少需要一个可执行任务意图或流程描述。极度欠规格输入，例如只有“Build me an agent”但没有任务行为，应进入 blocked/partial report，而不是生成空 MainWorker。

---

## 5.3 Main Flow

| 情况 | 编译行为 |
|---|---|
| 用户有行为/process/action 描述 | 生成 MAIN_FLOW |
| 用户没有任何行为描述 | 不编造 main flow command；输出缺流程诊断或 partial worker |

---

## 5.4 Alternative Flow

| 情况 | 编译行为 |
|---|---|
| 用户提到 revision / otherwise / alternative path / if user asks | 生成 ALTERNATIVE_FLOW |
| 用户没有替代路径信号 | 不生成 ALTERNATIVE_FLOW |

---

## 5.5 Exception Flow

| 情况 | 编译行为 |
|---|---|
| 用户完全没提 failure / exception | 不生成 EXCEPTION_FLOW |
| 用户只说 handle failures properly | 不生成具体 EXCEPTION_FLOW；输出 `type_or_contract_ambiguity` |
| 用户列出具体 failure condition | 生成 partial EXCEPTION_FLOW condition；标注 missing_handler |
| 用户列出 condition + handler | 生成完整 EXCEPTION_FLOW + COMMAND |
| 用户列出 handler 但 condition 不清楚 | 不生成完整 exception flow；MVP 归入 `type_or_contract_ambiguity` |
| 用户列出多个 failure conditions | 为每个 condition 生成 partial/complete exception flow，或在可证明等价时合并 |

### Empty ExceptionFlow

当前 SPL grammar 中 `EXCEPTION_FLOW` 的 block 部分是 `{BLOCK}`，即 0 个或多个 block。因此 partial mode 下允许：

```spl
[EXCEPTION_FLOW: Missing timeframe]
[END_EXCEPTION_FLOW]
```

Renderer 和 Validator 应支持这种 partial 表达，并通过 `missing_handler` 诊断提示它语义不完整。

---

## 5.6 Constraint

| 情况 | 编译行为 |
|---|---|
| 用户提到 must / must not / require / deny / policy / rule | 生成 constraint |
| 用户没有规则信号 | 不生成空 constraints block，除非 SPL grammar 强制要求 |
| policy 同时包含 action | 拆分为 rule + behavior，保留 trace |

---

## 5.7 Variable / Required Output

| 情况 | 编译行为 |
|---|---|
| 用户声明 input | 生成 input variable |
| 用户声明 required output | 生成 output variable + Worker output |
| required output 无 producer | 不编造 producer；输出 missing_output_producer |
| 用户没有声明 output | 不报 missing output |

---

## 5.8 API / CALL_API

| 情况 | 编译行为 |
|---|---|
| 用户明确提 API/tool/connector/repository | 可生成 API resource 或 CALL_API candidate |
| 用户只说 retrieve sources，但没有 source binding | 可生成 retrieval behavior，但标注 missing integration/source binding |
| 用户没有外部系统信号 | 不生成 API 声明，不生成 CALL_API |

---

## 6. Executable Element Gate

### 6.1 目的

防止用户没有表达的行为被系统渲染成可执行 SPL。

### 6.2 适用对象

```text
StepIR
COMMAND
INPUT
CALL_API
INVOKE_WORKER
exception handler command
required output producer step
```

### 6.3 渲染门控规则

一个 executable element 只有满足以下条件才允许渲染：

1. 有明确 `trace_refs`；
2. 其行为语义不是纯 `assumed`；
3. 如果是 `INPUT`，原文必须明确表达询问用户、请求澄清或提示用户提供信息的行为意图，例如 `ask the user`、`request clarification`、`prompt the user`；否则不得渲染为 INPUT，只能进入 CompileAssumption / readable report；
4. 如果是 `CALL_API`，必须有明确 API / integration / connector / source repository 证据；
5. 如果是 `INVOKE_WORKER`，必须有 concrete WorkerPlanIR handoff；
6. 如果是 exception handler command，必须有 handler action 来源；
7. 如果是 required output producer，必须有 source-backed production behavior；
8. 如果只是系统建议、假设、候选子任务，不渲染为 executable SPL。

说明：

```text
“系统允许提出问题”不是合法门槛。
MVP 中，只有用户原文明确表达询问/澄清意图，才允许生成 INPUT command。
```

### 6.4 处理结果

| 情况 | 处理 |
|---|---|
| 可渲染 | 进入 SPL |
| assumed behavior | 不渲染，进入 CompileAssumption / readable report |
| 缺契约 | 不渲染，输出 type_or_contract_ambiguity |
| unresolved worker/API target | 阻断或 partial report，不能降级成普通 COMMAND |

---

## 7. Pipeline 接入设计

## 7.1 三轮 Pass 定位

不重构现有 pipeline，但重新定义其 pass 语义：

```text
Pass 1: Draft IR Generation
Stage 1-9

Pass 2: Normalization + Diagnostic Analysis
Stage 9.5

Pass 3: Assembly + Render + Report
Stage 10-11
```

### Pass 1：Draft IR Generation

职责：

- 切片、路由、消歧；
- 生成 Worker / Flow / Block / Resource / Step / Profile / Constraint 初稿；
- 最大努力 materialize 用户已经表达的信息；
- 为每个 IR 元素保留 trace_refs。

### Pass 2：Normalization + Diagnostic Analysis

职责：

- 修正结构不一致；
- 检查 missing slots；
- 生成 CompileDiagnostic；
- 生成 TraceRecord；
- 执行 Executable Element Gate；
- 标记 partial / complete / blocked。

### Pass 3：Assembly + Render + Report

职责：

- 组装 WorkerIR；
- 渲染 partial/complete SPL；
- 生成 validation report；
- 生成 readable compile report。

---

## 7.2 InputAdapter

InputAdapter 不是最终诊断组件，但必须保留 provenance 链。

职责：

```text
Raw text
→ RawSection(source offsets / section id)
→ SemanticPacket(source_section_id / packet_id)
→ HardFact / CompileHint(source_section_id / packet_id)
```

规则：

- 不生成 SPL；
- 不生成 WorkerPlanIR；
- 不生成 final diagnostics；
- 可生成 adapter warnings；
- 必须保证后续 TraceRecord 能追溯到原始文本。

---

## 7.3 Stage 1：SpanSlicer

新增职责：

- SpanIR 增加 `source_section_id`、`source_packet_id`、`trace_refs`；
- adapter path 中，semantic packets 生成 packet-aware spans；
- raw_sections 中未被 packet 覆盖的文本仍需生成 section-aware spans；
- generic path 保持旧逻辑。

---

## 7.4 Stage 2：FieldRouter

新增职责：

- 对每个 route decision 记录 trace；
- input/output hard fact packet 不强行路由为 behavior；
- 被 adapter 消费的 hard fact span 应记录为 `adapter_consumed`，避免误判为未路由；
- 对跨字段 span 继续标记 ambiguity。

---

## 7.5 Stage 3：AmbiguityResolver

新增职责：

- 拆分 span 后保留原始 trace；
- 每个拆分子 span 应说明 relation：通常为 `normalized`；
- 如果无法拆分，输出 warning 或保留 partial ambiguity。

---

## 7.6 Stage 3.5：WorkerBoundaryPlanner（Multi-Worker 路线）

新增职责：

- 只在有 worker boundary evidence 时生成 child worker；
- subtask/delegate 只是 signal，不是 decision；
- 缺 input/output/handoff 时生成 candidate + diagnostic，不生成 executable worker；
- child worker 必须满足 responsibility、input contract、output contract、invocation point、result handoff。

与本方案关系：

- WorkerPlanIR 中的 WorkerSpecIR / HandoffIR 应有 trace_refs；
- rejected candidate 应进入 readable report；
- assumed worker boundary 不应渲染。

---

## 7.7 Stage 4：FlowAssembler

新增职责：

- 只生成有 source signal 的 flow；
- 不因 SPL 支持某种 flow 就生成空 flow；
- failure condition 可生成 partial exception flow；
- handler action 不明确时不生成 command；
- 每个 flow 带 trace_refs 和 ElementStatus。

---

## 7.8 Stage 5：BlockAssembler

新增职责：

- 不制造无来源 block；
- 对 partial flow 可允许 block 为空；
- 发现无法表达的 nested control 时，不直接生成 child worker，而是输出 complexity region / diagnostic。

---

## 7.9 Stage 6：ResourceExtractor

新增职责：

- hard fact input/output 优先注册；
- required output 无 producer 不自动补 producer；
- 变量同名/类型冲突时输出 type_or_contract_ambiguity；
- 每个变量保存 trace_refs。

---

## 7.10 Stage 7：StepExtractor

新增职责：

- StepIR 必须有 source_span_ids / trace_refs；
- 如果 step 是系统为了补齐 required output 或 handler 而猜测的，应标记为 `assumed`；
- assumed behavior 不应直接进入 renderable SPL；
- INVOKE_WORKER 必须来自 concrete handoff；
- CALL_API 必须来自明确 integration/source evidence。

---

## 7.11 Stage 9：ConstraintExtractor

新增职责：

- constraint_hints 不是 ConstraintIR；
- 只有 source-backed rule 才生成 ConstraintIR；
- gate constraint 如果缺 enforcement point，可生成 constraint，但输出 diagnostic 或 trace explanation；
- 每个 constraint 保存 trace_refs。

---

## 7.12 Stage 9.5：IRNormalizer + Diagnostic Analyzer

Stage 9.5 是第二轮 pass，不只是格式 normalization。

新增职责：

1. 结构归一化；
2. missing slot 检测；
3. diagnostic 生成；
4. trace 聚合；
5. executable element gate；
6. completeness 标记；
7. readable report 数据准备。

MVP 检测：

```text
missing_handler
missing_output_producer
type_or_contract_ambiguity
assumed_command_not_renderable
```

暂不实现：

```text
missing_trigger
semantic duplicate
policy conflict
```

---

## 7.13 Stage 10：WorkerAssembler

新增职责：

- 只组装可渲染 worker；
- 不组装 unresolved child worker；
- 保留 trace_refs 到 WorkerIR；
- 对 partial worker 保留 ElementStatus。

---

## 7.14 Stage 11：SPLRenderer + ReportRenderer

新增职责：

- 渲染 partial or complete SPL；
- 支持 partial mode；
- 支持 empty EXCEPTION_FLOW；
- 跳过 assumed behavior command；
- 不渲染无来源结构；
- 输出 readable_report。

---

## 8. Readable Report 设计

### 8.1 目的

Readable report 是 MVP 必须输出的人工可读诊断结果。

它可以输出到：

```text
CLI
日志
JSON旁边的 .txt 文件
前端 UI 的诊断面板
```

### 8.2 生成方式

Readable report 由代码模板渲染生成，不依赖额外 LLM 调用。

输入：

```text
CompileResult.spl_text
CompileResult.completeness
CompileResult.diagnostics
CompileResult.traces
CompileResult.assumptions
CompileResult.validation_errors
CompileResult.validation_warnings
```

原因：

```text
1. 成本可控；
2. 格式稳定；
3. 便于测试；
4. 不引入新的语义漂移风险。
```

### 8.3 内容结构

```text
NL2SPL Compile Report

Status: partial | complete | blocked

Summary:
- Generated workers: ...
- Generated flows: ...
- Partial elements: ...
- Diagnostics: ...

Diagnostics:
[W001 missing_handler]
Target: exception_flow:missing_timeframe
Source: s12 "Missing timeframe"
Message: Failure mode is listed, but no handling action is specified.
Suggested resolution: Specify whether to ask the user for timeframe, block finalization, or continue with assumptions.

Trace:
- variable:user_request ← normalized from s2 "A user request"
- exception_flow:missing_timeframe ← inferred from s12 "Missing timeframe"
- constraint:evidence_required ← direct from s9 "Require evidence for sourced claims"

Assumptions / Suggestions:
- Related to W001 / missing slot handler_action:
  The system suggests asking the user for timeframe, but this was not rendered into SPL because the source did not specify this behavior.
```

### 8.4 MissingSlot 与 CompileAssumption 的展示规则

如果一个 `CompileAssumption` 关联到某个 `MissingSlot`，readable report 应合并展示为同一个诊断项的 “Suggested resolution / Possible assumption”，避免用户看到两条重复问题。

---

## 9. MVP 范围

## 9.1 MVP 必做

1. 核心 IR 加 `trace_refs`；
2. 新增 `TraceRef`、`TraceRecord`、`MissingSlot`、`ElementStatus`、`CompileDiagnostic`、`CompileAssumption`、`CompileResult`；
3. Stage 9.5 生成 4 类 diagnostic；
4. Renderer 支持 partial mode；
5. 支持 empty EXCEPTION_FLOW；
6. assumed behavior 不渲染；
7. required output 无 producer 输出 diagnostic；
8. failure condition 无 handler 输出 diagnostic；
9. assumed command 不可渲染时输出 diagnostic；
10. 输出 readable report。

---

## 9.2 MVP 不做

1. 深层语义重复检测；
2. 深层 policy conflict 检测；
3. `missing_trigger` 语义关联检测；
4. 多轮交互 UI；
5. 自动把用户未确认的 assumption 写回 SPL；
6. 复杂 semantic drift 自动检测；
7. 多 schema 冲突处理；
8. 完整用户补齐闭环。

---

## 9.3 MVP 验收标准

```text
1. 能生成语法上合法的 partial or complete SPL draft。
2. 用户提及 failure condition 时，能 materialize 为 EXCEPTION_FLOW condition。
3. handler action 缺失时，不编造 COMMAND，而是输出 missing_handler diagnostic。
4. required output 能进入 Worker outputs。
5. required output 没有 producer step 时，输出 missing_output_producer diagnostic。
6. 变量/契约/API/worker handoff/泛化 exception policy 存在类型或结构不明确时，输出 type_or_contract_ambiguity diagnostic。
7. StepIR / COMMAND 只有 assumed 来源时，不渲染，并输出 assumed_command_not_renderable diagnostic。
8. 用户没有提到某类 SPL 结构时，不生成该结构，也不报该结构缺失。
9. 每个主要 Worker/Flow/Step/Constraint/Variable 有 TraceRecord，说明 direct / normalized / inferred / assumed。
10. 输出人可读 compile report，包含 target_ref、kind、message、source span、suggested_resolution。
11. readable_report 由代码模板渲染生成，不依赖 LLM。
```

---

## 10. 测试矩阵

| 测试场景 | 预期结果 |
|---|---|
| 用户没有 failure section | 不生成 EXCEPTION_FLOW |
| 用户列出 Missing timeframe | 生成 partial EXCEPTION_FLOW + missing_handler |
| 用户列出 condition + handler | 生成完整 EXCEPTION_FLOW + COMMAND |
| 用户只说 Handle failures properly | 不生成具体 exception flow，输出 type_or_contract_ambiguity |
| 用户声明 required output | 生成 Worker output |
| required output 无 producer | missing_output_producer |
| 用户只提 optional subtask | 生成 candidate/report，不生成 child worker command |
| child worker 缺 IO/handoff | 不渲染 INVOKE_WORKER，输出 type_or_contract_ambiguity |
| 用户未提 API | 不生成 API/CALL_API |
| 用户提 connector/source repository | 可生成 integration/resource hint |
| assumed behavior step | 不渲染，输出 assumed_command_not_renderable，并进入 assumptions/report |
| variable text vs metadata conflict | type_or_contract_ambiguity |
| InputAdapter duplicate section | adapter warning，不阻断 |
| Generic NL 输入 | 走 legacy path，仍输出 trace 尽可能记录 |
| TraceRef 只有 source_span_id | Phase 1 合法，source_section_id/source_packet_id 可为空 |
| readable_report | 由代码模板生成，包含 diagnostics、trace、assumptions |

---

## 11. 实施计划

### Phase 1：Trace 基础设施

- 新增 `TraceRef`、`TraceRecord`；
- 给 SpanIR、VariableSpec、StepIR、ConstraintIR、Flow/Block、WorkerIR 加 trace 字段；
- 保证 InputAdapter → Span → IR 的 provenance 不断链。

### Phase 2：Partial Element + Missing Slot

- 新增 `ElementStatus`、`MissingSlot`；
- 支持 partial EXCEPTION_FLOW；
- required output 无 producer 记录 missing slot；
- worker/subtask 缺 IO/handoff 记录 missing slot。

### Phase 3：Diagnostic Analyzer

- 在 Stage 9.5 中实现 4 类 diagnostic；
- 输出 CompileDiagnostic；
- 与 validation_errors / validation_warnings 区分。

### Phase 4：Executable Element Gate

- 阻止 assumed behavior 渲染；
- 阻止 unresolved INVOKE_WORKER 渲染；
- 阻止缺 API evidence 的 CALL_API 渲染；
- 阻止缺 handler source 的 exception command 渲染。

### Phase 5：Report Renderer

- 新增 readable_report；
- 输出 summary、diagnostics、trace、assumptions；
- CLI/日志可直接展示。

---

## 12. 与现有系统的关系

本方案不推翻现有 pipeline。

现有系统仍然负责：

```text
Span slicing
Field routing
Ambiguity resolving
Worker / Flow / Block / Step / Resource / Constraint IR generation
Worker assembly
SPL rendering
```

本方案新增的是：

```text
需求忠实性约束
溯源
partial completeness
missing slot
diagnostics
anti-fabrication gate
readable report
```

换句话说，现有 pipeline 是基础设施；本方案使该基础设施从“格式编译器”升级为“需求到设计的编译诊断系统”。

---

## 13. 最终原则总结

```text
1. Complete SPL is a refined requirement and high-level system design.
2. Materialize all structurally clear information from the source NL.
3. Do not generate SPL structures without source demand.
4. Generate partial structures only when the user expressed part of that structure.
5. Do not silently fabricate handler actions, producer steps, worker contracts, API calls, or executable commands.
6. Trace every major SPL/IR element back to source spans.
7. Mark inferred and assumed content explicitly.
8. Keep unconfirmed assumptions out of executable SPL.
9. Emit diagnostics and readable reports so users can complete the requirement.
10. Preserve the existing compiler-style pipeline, but add requirement-fidelity gates and design diagnostics.
```

