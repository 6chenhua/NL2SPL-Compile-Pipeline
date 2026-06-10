# Internal-Comms Expected Behavior

本文档描述 internal-comms 示例在 NL2SPL 中的预期行为。它不是逐字 golden SPL，而是行为验收标准：只要输出满足这些条件，就认为系统符合“source-backed partial SPL + diagnostics + provenance + feedback report”的目标。

---

## 1. Overall Expected Result

预期编译状态：

```text
completeness: partial
```

原因：

1. 输入已经提供 task family、inputs、required outputs、reusable process、policies、failure handling 和 delegation policy。
2. 大部分 worker、flow、variable、constraint 可以 source-backed materialize。
3. Failure handling 主要提供 failure condition，没有提供明确 handler action，因此 exception flows 应保留为 partial。
4. Source gathering delegation 有较强证据，可以生成 source-backed child worker 或 worker candidate。
5. Template matching 只是可选 delegated subtask，缺少明确 input/output/handoff，不应生成 executable child worker。

运行后应至少生成：

```text
final_spl.txt
feedback_report.md
```

MVP 阶段只生成 `feedback_report.md` 作为 human-readable report；内部 compiler diagnostics 保留在 stage checkpoint JSON / intermediate results 中。

---

## 2. SPL Draft Behavior

### 2.1 Agent / Persona

系统应能 materialize internal communications 相关 agent/persona。

允许：

```spl
[DEFINE_AGENT: ...]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
    [END_PERSONA]
```

要求：

- persona / role 必须来自 task family 或 task description。
- 可以进行 normalized 命名，例如 `InternalCommsAgent`、`MainWorker`。
- 不应编造输入中没有的专业身份、组织背景或具体公司上下文。

### 2.2 Inputs

应声明用户明确给出的输入槽，例如：

```text
user_request
known_topics
timeframe
connectors_or_source_repositories
format_preferences
```

要求：

- required / optional 的区分应尽量遵循源文本。
- 输入变量可以规范化命名，但应有 provenance trace。
- 不应把 IR schema 字段误抽成用户变量，例如 `span_id`、`source_section_id`、`main_flow_spans`、`exception_flows`。

### 2.3 Required Outputs

应声明 internal comms artifact 相关 required outputs，例如：

```text
draft artifact / announcement / newsletter / digest / executive brief
source notes / provenance summary
clarifying questions if needed
```

要求：

- required output 可以声明在 SPL contract 中。
- 如果没有 source-backed producer step，不得合成 `Produce required output ...` 之类 command。
- 缺 producer 时应输出 `missing_output_producer` diagnostic，并使 completeness 保持 `partial`。

### 2.4 Constraints / Policies

应 materialize 输入中明确给出的 policies，例如：

```text
Do not invent links or unseen facts.
Require evidence for sourced claims.
Ask only high-value clarifying questions.
Prefer tool evidence over unnecessary user questioning.
Do not finalize if critical slots remain missing.
```

要求：

- policies 应作为 constraints / profile / report guidance 出现。
- 不应把 policy 误转成无条件 executable command。
- 如果 policy 与某个 command 冲突，v5 可通过 `semantic_conflict` diagnostic 报告；v4/MVP 可先不做深层冲突检测。

---

## 3. Main Process Behavior

Reusable process 中的明确步骤可以 materialize 为 main flow steps，例如：

```text
understand request
identify missing slots
gather or normalize evidence
draft internal communication artifact
check provenance / policy compliance
return result
```

要求：

- executable step 必须有 source evidence。
- vague goal 不应被强制展开为具体 command。
- 如果 LLM 生成了无来源 step，Gate 应阻止它进入 rendered SPL，并产生 `assumed_command_not_renderable` diagnostic。

---

## 4. Failure Handling Behavior

Failure handling 是本示例最重要的 partial SPL 验收点。

如果输入只给出 failure condition，例如：

```text
missing timeframe
missing source
provenance failure
insufficient context
```

预期行为：

```spl
[EXCEPTION_FLOW: Missing timeframe]
[END_EXCEPTION_FLOW]
```

同时 diagnostics 应包含：

```text
kind: missing_handler
target_ref: exception_flow:...
blocks_completion: true
```

禁止行为：

```spl
[REQUEST_INPUT: Please provide the timeframe]
[COMMAND: Ask the user for missing context]
[COMMAND: Recover from provenance failure]
```

除非源文本明确要求 ask/request/prompt/confirm user，否则不得把缺失信息自动转成 `REQUEST_INPUT`。

---

## 5. Delegation Behavior

### 5.1 Source Gathering

如果 source gathering 有明确 responsibility、input、output、handoff 证据，则允许生成 child worker 和 `INVOKE_WORKER`。

要求：

- child worker 必须有明确 responsibility。
- invocation 必须基于 accepted handoff。
- input/output bindings 必须完整。
- provenance 应指向 delegation policy 或 reusable process 相关 section/span。

### 5.2 Template Matching

如果 template matching 只是 optional delegated subtask mention，预期行为是：

```text
worker candidate / delegation intent trace
no executable child worker
no [INVOKE_WORKER ...]
type_or_contract_ambiguity if contract incomplete
```

禁止行为：

- 不得因为出现 “can delegate template matching” 就生成完整 child worker。
- 不得生成缺少 input/output/handoff 的 executable `INVOKE_WORKER`。
- 不得将 unresolved delegation 降级为 generic command。

---

## 6. CALL_API / Tool Behavior

如果输入只提到 connectors、repositories 或 source repositories 作为上下文，系统可以生成 resource/API candidate 或 compile hint。

只有同时满足以下条件时，才允许 executable `CALL_API`：

```text
named API/tool/connector evidence
+ explicit call/action evidence
+ valid response/output binding if output is consumed
```

否则：

```text
no CALL_API rendered
type_or_contract_ambiguity diagnostic if an executable call was attempted
```

---

## 7. Diagnostics Expected

本示例至少可能出现：

```text
missing_handler
missing_output_producer
type_or_contract_ambiguity
assumed_command_not_renderable
missing_provenance
semantic_conflict  # only if v5 LLMConflictAnalyzer is enabled
```

诊断要求：

- 每条 diagnostic 应有 `kind`、`message`、`target_ref`。
- 能关联源文本时，应有 `source_span_ids` 或 section/packet provenance。
- completion-blocking diagnostic 应使 overall completeness 为 `partial`。
- validation errors 不应吞掉 compile diagnostics；两者应分开展示。

---

## 8. Provenance Expected

主要 SPL 元素应有 `TraceRecord`：

```text
worker:...
flow:...
step:...
variable:...
constraint:...
handoff:...
delegation_intent:...
```

要求：

- trace 应尽量包含 `source_span_ids`。
- structural NL 输入下，应尽量包含 `source_section_id` 和 `source_packet_id`。
- assumed / inferred trace 应标记 `needs_confirmation`，或在 report 中说明 relation。
- variable provenance 优先来自 producer step / handoff binding / adapter hard fact，而不是仅依赖 `VariableSpec.source` 类别字段。

---

## 9. Feedback Report Expected

`feedback_report.md` 应解释：

```text
1. 为什么 completeness 是 partial。
2. 哪些 SPL 构件已经 materialize。
3. 哪些构件没有 materialize。
4. 哪些 slot 缺失。
5. 哪些 command 被 Gate 阻止。
6. 哪些 assumptions/suggestions 只进入 report，不进入 SPL。
7. 每个主要 SPL 元素的 provenance。
8. 系统明确没有脑补哪些内容。
```

报告中应能看到类似信息：

```text
missing_handler -> failure condition exists, but handler action is missing
missing_output_producer -> required output has no source-backed producer
type_or_contract_ambiguity -> delegation/API contract is incomplete
assumed_command_not_renderable -> command lacks source evidence
```

---

## 10. Anti-Fabrication Rules

本示例中系统必须避免：

1. 发明 exception handler。
2. 发明 required output producer。
3. 把 missing slot 自动变成 `REQUEST_INPUT`。
4. 把 optional delegation 自动升级成 child worker。
5. 把 unresolved API/worker contract 降级成 generic command。
6. 把 schema/internal field 抽成业务变量。
7. 把没有 provenance 的事实当作 hard fact。

---

## 11. Pass / Fail Summary

通过条件：

```text
SPL draft exists.
completeness is partial.
Failure conditions are represented as partial exception flows when source-backed.
No invented handler commands.
No synthetic required-output producer commands.
Incomplete delegation remains diagnostic/report-only.
Diagnostics, traces, assumptions, and feedback_report are generated. Internal compiler diagnostics remain in checkpoint JSON / intermediate results.
```

失败条件：

```text
Generated SPL appears complete while known missing handlers/producers remain.
System silently invents handler actions or producer steps.
System emits executable REQUEST_INPUT without explicit ask/request/prompt source.
System emits executable INVOKE_WORKER without accepted handoff.
Report does not explain why result is partial.
Provenance is missing for major materialized elements.
```
