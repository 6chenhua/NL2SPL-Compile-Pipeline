以这个输入为例，**NL2SPL compiler 第一轮的预期效果不应该是“生成一个看似完整、全部闭合的 SPL”**，而应该是：

```text
source-backed partial SPL draft
+ diagnostics
+ traces
+ assumptions / suggestions
+ readable report
```

这个输入已经比较结构化，所以第一轮应该能生成较多有效结构；但它仍然不是完整需求。最大缺口在于：**Failure handling 只列出了 failure condition，没有说明 handler action**。因此这些 failure 可以 materialize 为 `EXCEPTION_FLOW` condition，但不能编造 handler command。

---

# 1. 第一轮总体状态

预期整体结果：

```text
completeness: partial
```

原因：

```text
1. 用户给出了 task family、inputs、outputs、process、policies、failure conditions、delegation policy。
2. 大部分 Worker / Flow / Variable / Constraint 可以 source-backed 生成。
3. Failure handling 只给出 condition，没有给出处理动作，因此 exception flows 是 partial。
4. Source gathering delegation 有较强证据，可以生成 child worker 或至少 source-backed candidate。
5. Template matching 只有可选 delegated subtask 提及，缺少明确 output / handoff，不应直接生成 executable worker。
```

---

# 2. 应该 materialize 出来的结构

## 2.1 Agent / Persona

可以生成：

```spl
[DEFINE_AGENT: InternalCommsAgent "Generate evidence-grounded internal communication artifacts"]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
    [END_PERSONA]
```

来源：

```text
Task family:
Internal newsletters, announcements, update digests, executive briefs...
```

Trace relation：

```text
normalized
```

因为 “internal-comms artifacts” 被规范化为 persona role，不是新需求。

---

## 2.2 Inputs

应该生成：

```spl
[INPUTS]
    REQUIRED <REF>user_request</REF>
    OPTIONAL <REF>known_topics</REF>
    OPTIONAL <REF>timeframe</REF>
    OPTIONAL <REF>connectors_or_source_repositories</REF>
    OPTIONAL <REF>format_preferences</REF>
[END_INPUTS]
```

其中：

```text
user_request: required
known_topics: optional
timeframe: optional
connectors_or_source_repositories: optional / available list
format_preferences: optional
```

`connectors_or_source_repositories` 虽然原文没有写 optional，但它表达的是“available connectors or source repositories”，实际运行时可能为空，因此建议按 optional input 或 nullable/list input 处理。

Trace relation：

```text
normalized
```

---

## 2.3 Required outputs

应该生成：

```spl
[OUTPUTS]
    REQUIRED <REF>draft_communication_artifact</REF>
    REQUIRED <REF>source_evidence_set</REF>
    REQUIRED <REF>assumptions_log</REF>
    REQUIRED <REF>completion_status</REF>
[END_OUTPUTS]
```

来源：

```text
Required outputs:
A draft communication artifact, a source/evidence set, a short assumptions log..., and a completion status.
```

Trace relation：

```text
normalized
```

注意：这里可以声明 output，但不能因为 output 声明就无来源地合成 producer command。producer 必须来自 process 或其他 source-backed step。

---

## 2.4 Constraints

可以生成约束：

```spl
[DEFINE_CONSTRAINTS:]
    Prohibition: Do not invent links or unseen facts.
    Evidence: Require evidence for sourced claims.
    QuestionLimit: Limit questions per turn.
    SourcePreference: Prefer tool evidence over unnecessary user questioning.
    FinalizationGate: Deny finalization if critical slots are missing or provenance fails.
    Provenance: Maintain provenance for externally sourced facts.
    DelegationBoundary: Delegated subtasks must be bounded.
    DelegationBoundary: Returned evidence must be normalized into approved evidence carriers.
[END_CONSTRAINTS]
```

来源：

```text
Policies
Reusable process
Delegation policy
```

Trace relation：

```text
direct / normalized
```

其中 `Maintain provenance` 来自 reusable process，不是 policies，但也应进入 constraints 或 process enforcement。

---

# 3. MainWorker 预期结构

MainWorker 应该存在，因为输入中有明确 process/action 描述。

## 3.1 Main flow 应 materialize 的内容

主流程应大致是：

```spl
[MAIN_FLOW]
    [SEQUENTIAL_BLOCK]
        COMMAND-1 [COMMAND Determine the requested communication type from <REF>user_request</REF> RESULT <REF>communication_type</REF> SET]
        COMMAND-2 [COMMAND Identify missing required fields based on request context RESULT <REF>missing_required_fields</REF> SET]
        COMMAND-3 [COMMAND Determine whether critical required fields are missing RESULT <REF>critical_slots_missing</REF> SET]
        COMMAND-4 [COMMAND Determine whether sources are needed RESULT <REF>source_need_status</REF> SET]
        COMMAND-5 [COMMAND Determine whether available connectors or source repositories can support source retrieval RESULT <REF>sources_available</REF> SET]
    [END_SEQUENTIAL_BLOCK]

    DECISION-1 [IF <REF>critical_slots_missing</REF>]
        COMMAND-6 [COMMAND Generate only the highest-value clarifying questions RESULT <REF>clarification_questions</REF> SET]
        COMMAND-7 [INPUT Ask highest-value clarifying questions VALUE <REF>clarification_response</REF> SET]
        COMMAND-8 [COMMAND Update request context with clarification response RESULT <REF>request_context</REF> SET]
    [END_IF]

    DECISION-2 [IF <REF>source_need_status</REF> and <REF>sources_available</REF>]
        COMMAND-9 [INVOKE SourceGatheringWorker WITH request_context=<REF>request_context</REF>, connectors=<REF>connectors_or_source_repositories</REF> RESPONSE <REF>source_evidence_set</REF> SET]
    [END_IF]

    DECISION-3 [IF enough required information is available and provenance requirements pass]
        COMMAND-10 [COMMAND Produce draft communication artifact RESULT <REF>draft_communication_artifact</REF> SET]
        COMMAND-11 [COMMAND Produce assumptions log for unresolved items RESULT <REF>assumptions_log</REF> SET]
        COMMAND-12 [COMMAND Set completion status RESULT <REF>completion_status</REF> SET]
    [END_IF]

    DECISION-4 [IF critical slots remain missing and an assumption-bearing draft is allowed]
        COMMAND-13 [COMMAND Mark draft as assumption-bearing RESULT <REF>draft_communication_artifact</REF> SET]
        COMMAND-14 [INPUT Ask user to confirm assumption-bearing draft VALUE <REF>user_confirmed_assumptions</REF> SET]
    [END_IF]
[END_MAIN_FLOW]
```

这里有几个关键点。

### Clarifying questions 可以生成 `INPUT`

因为原文明确说：

```text
Ask only the highest-value clarifying questions needed to move forward.
```

所以这不是系统擅自发问，而是 source-backed behavior。

但它必须在 `critical_slots_missing` 或类似条件下执行，不能无条件询问。

---

### Assumption-bearing confirmation 可以生成 `INPUT`

因为原文明确说：

```text
unless the draft is explicitly marked as assumption-bearing and the user confirms
```

这里“user confirms”提供了输入意图，所以可以生成确认步骤。

---

### `source_evidence_set` 的 producer 可以来自 SourceGatheringWorker

因为原文同时提供了：

```text
If sources are needed and available, retrieve them using approved source recipes.
Maintain provenance for externally sourced facts.
Required outputs: A source/evidence set.
Delegation policy: source gathering may be delegated if bounded...
```

这足够支持 source gathering 子任务。

---

# 4. SourceGatheringWorker 是否应该生成？

我认为：**可以生成 SourceGatheringWorker，但应保持 bounded，不要扩展过度。**

原因是这个输入给出了比较完整的 worker boundary evidence：

| Worker 条件            | 是否具备 | 来源                                                                |
| -------------------- | ---: | ----------------------------------------------------------------- |
| responsibility       |    有 | source gathering                                                  |
| input                |    有 | request context, connectors/source repositories                   |
| output               |    有 | source/evidence set, provenance                                   |
| invocation condition |    有 | if sources are needed and available                               |
| result handoff       |    有 | returned evidence normalized into approved evidence carriers      |
| failure conditions   |    有 | insufficient source access, evidence shortage, provenance failure |

所以第一轮可以生成：

```spl
[DEFINE_WORKER: "Bounded source gathering worker" SourceGatheringWorker]
    [INPUTS]
        REQUIRED <REF>request_context</REF>
        OPTIONAL <REF>connectors_or_source_repositories</REF>
    [END_INPUTS]

    [OUTPUTS]
        REQUIRED <REF>source_evidence_set</REF>
        REQUIRED <REF>provenance_log</REF>
    [END_OUTPUTS]

    [MAIN_FLOW]
        [SEQUENTIAL_BLOCK]
            COMMAND-15 [COMMAND Retrieve relevant source evidence using approved source recipes RESULT <REF>source_evidence_set</REF> SET]
            COMMAND-16 [COMMAND Normalize returned evidence into approved evidence carriers RESULT <REF>source_evidence_set</REF> SET]
            COMMAND-17 [COMMAND Maintain provenance for externally sourced facts RESULT <REF>provenance_log</REF> SET]
        [END_SEQUENTIAL_BLOCK]
    [END_MAIN_FLOW]

    [EXCEPTION_FLOW: insufficient source access]
    [END_EXCEPTION_FLOW]

    [EXCEPTION_FLOW: evidence shortage]
    [END_EXCEPTION_FLOW]

    [EXCEPTION_FLOW: provenance failure]
    [END_EXCEPTION_FLOW]
[END_WORKER]
```

这些 exception flow 是 partial，因为 handler 缺失。

---

# 5. TemplateMatchingWorker 不应直接生成

原文只说：

```text
Optional delegated subtasks such as source gathering or template matching may be used...
```

但对 template matching 没有给出：

```text
input contract
output contract
invocation condition
handoff target
required result
```

虽然可以猜它输入 `format_preferences`，输出 `template_guidance`，但这属于系统假设。

因此第一轮不应渲染：

```spl
[DEFINE_WORKER: "TemplateMatchingWorker" ...]
```

也不应渲染：

```spl
COMMAND [INVOKE TemplateMatchingWorker ...]
```

而应进入 report：

```text
type_or_contract_ambiguity:
Template matching is mentioned as an optional delegated subtask, but its input, output, invocation condition, and result handoff are not specified. It is kept as a candidate and not rendered as executable SPL.
```

这正是 anti-fabrication。

---

# 6. ExceptionFlow 的预期效果

Failure handling 列出了 6 个 condition：

```text
Missing timeframe
conflicting instructions
insufficient source access
evidence shortage
user refusal to answer
provenance failure
```

这些可以 materialize 为 partial exception flows。

## 6.1 应生成的 partial exception flows

主 worker 可以有：

```spl
[EXCEPTION_FLOW: Missing timeframe]
[END_EXCEPTION_FLOW]

[EXCEPTION_FLOW: conflicting instructions]
[END_EXCEPTION_FLOW]

[EXCEPTION_FLOW: user refusal to answer]
[END_EXCEPTION_FLOW]
```

SourceGatheringWorker 可以有：

```spl
[EXCEPTION_FLOW: insufficient source access]
[END_EXCEPTION_FLOW]

[EXCEPTION_FLOW: evidence shortage]
[END_EXCEPTION_FLOW]

[EXCEPTION_FLOW: provenance failure]
[END_EXCEPTION_FLOW]
```

也可以第一轮全部先挂在 MainWorker，后续 pass 再按 worker ownership 调整。但更好的结果是按语义分配。

## 6.2 不应生成 handler command

不应生成：

```spl
COMMAND [INPUT Ask user for timeframe ...]
COMMAND [COMMAND Resolve conflicting instructions ...]
COMMAND [COMMAND Handle evidence shortage ...]
```

因为原文没有说明这些 failure 发生后怎么处理。

## 6.3 应生成 diagnostics

应生成：

```text
missing_handler:
- Missing timeframe is listed as a failure condition, but no handler action is specified.
- Conflicting instructions is listed as a failure condition, but no handler action is specified.
- Insufficient source access is listed as a failure condition, but no handler action is specified.
- Evidence shortage is listed as a failure condition, but no handler action is specified.
- User refusal to answer is listed as a failure condition, but no handler action is specified.
- Provenance failure is listed as a failure condition, but no handler action is specified.
```

可以是 6 条，也可以是 grouped diagnostic。MVP 阶段建议先生成 6 条，便于 target_ref 精确。

---

# 7. Alternative flow

原文明确说：

```text
If the user asks for revision, revise while rechecking constraints.
```

所以可以生成：

```spl
[ALTERNATIVE_FLOW: User asks for revision]
    [SEQUENTIAL_BLOCK]
        COMMAND-18 [COMMAND Revise draft communication artifact according to user revision request RESULT <REF>draft_communication_artifact</REF> SET]
        COMMAND-19 [COMMAND Recheck constraints against revised draft RESULT <REF>finalization_ready</REF> SET]
        COMMAND-20 [COMMAND Update completion status after revision RESULT <REF>completion_status</REF> SET]
    [END_SEQUENTIAL_BLOCK]
[END_ALTERNATIVE_FLOW]
```

这是 source-backed，不是捏造。

---

# 8. 第一轮 diagnostics 预期

第一轮至少应输出这些 diagnostics。

## 8.1 `missing_handler`

目标：

```text
exception_flow:missing_timeframe
exception_flow:conflicting_instructions
exception_flow:insufficient_source_access
exception_flow:evidence_shortage
exception_flow:user_refusal_to_answer
exception_flow:provenance_failure
```

原因：

```text
source lists failure condition but does not specify handling action.
```

severity：

```text
warning
```

对 completeness 的影响：

```text
partial
```

---

## 8.2 `type_or_contract_ambiguity`

目标：

```text
candidate_worker:template_matching
```

原因：

```text
Template matching is mentioned as optional delegation, but lacks explicit input/output/handoff evidence.
```

severity：

```text
info 或 warning
```

建议：

```text
Specify whether template matching should be delegated, what input it receives, and what output it returns.
```

---

## 8.3 可能没有 `missing_output_producer`

如果 compiler 能把以下 producer 绑定好，则不需要输出 `missing_output_producer`：

| Output                         | Producer                                     |
| ------------------------------ | -------------------------------------------- |
| `draft_communication_artifact` | Produce draft communication artifact         |
| `source_evidence_set`          | SourceGatheringWorker                        |
| `assumptions_log`              | Produce assumptions log for unresolved items |
| `completion_status`            | Set completion status                        |

但注意：这些 producer 必须有来源支持。

其中：

```text
draft producer ← "produce a draft"
source_evidence producer ← "retrieve sources" + "source/evidence set"
assumptions_log producer ← "Required outputs: a short assumptions log..."
completion_status producer ← "Required outputs: completion status"
```

如果当前实现规定“Required outputs 只能声明 output，不足以生成 producer step”，那么 `assumptions_log` 和 `completion_status` 可能触发 `missing_output_producer`。但我建议第一轮可以允许 **final output assembly steps**，前提是：

```text
source_span_ids 指向 Required outputs section；
command description 不捏造具体业务处理；
只表达 assembling / setting declared output。
```

不能出现无来源的：

```text
COMMAND Produce required output ...
```

---

# 9. TraceRecords 预期

应有类似 trace：

```text
variable:user_request
← normalized from Inputs for each run: "A user request"

variable:draft_communication_artifact
← normalized from Required outputs: "A draft communication artifact"

constraint:no_invented_links
← direct from Policies: "Do not invent links or unseen facts."

main_flow:determine_communication_type
← direct from Reusable process: "First determine what kind of communication is requested."

exception_flow:missing_timeframe
← inferred from Failure handling: "Missing timeframe"

worker:SourceGatheringWorker
← inferred from Reusable process + Delegation policy:
   "retrieve sources using approved source recipes"
   "source gathering may be delegated if bounded"

candidate_worker:TemplateMatchingWorker
← direct/inferred from Delegation policy:
   "template matching may be used"
   not rendered because contract evidence is incomplete.
```

---

# 10. Assumptions / Suggestions 预期

Assumptions 不进入 SPL 文本，只进入 report。

可能包括：

```text
Suggestion:
For missing timeframe, specify whether the agent should ask the user, block finalization, or continue with an assumption-bearing draft.

Suggestion:
For conflicting instructions, specify whether the agent should ask for clarification or prioritize one instruction source.

Suggestion:
For evidence shortage, specify whether the agent should request more sources, produce an assumption-bearing draft, or block finalization.

Suggestion:
For template matching, specify whether it should be a child worker and what output it should return.
```

这些不能渲染成 command。

---

# 11. Readable report 预期摘要

报告应该类似：

```text
NL2SPL Compile Report

Status: partial

Summary:
- SPL draft generated: yes
- Main worker: generated
- Child workers: SourceGatheringWorker generated; TemplateMatchingWorker kept as candidate
- Diagnostics: 7 warnings
- Assumptions / suggestions: 4
- Trace records: generated for main variables, flows, constraints, and workers

Diagnostics:
[W001 missing_handler]
Target: exception_flow:missing_timeframe
Source: Failure handling / "Missing timeframe"
Message: Failure condition is present, but no handler action is specified.
Suggested resolution: Specify whether to ask the user for timeframe, block finalization, or continue with an explicit assumption.

[W002 missing_handler]
Target: exception_flow:evidence_shortage
Source: Failure handling / "evidence shortage"
Message: Failure condition is present, but no handler action is specified.
Suggested resolution: Specify the handling policy for evidence shortage.

[W007 type_or_contract_ambiguity]
Target: candidate_worker:template_matching
Source: Delegation policy / "template matching may be used"
Message: Template matching is mentioned as optional delegation, but its input/output/handoff contract is not specified.
Suggested resolution: Specify whether template matching should be delegated and what result it should return.

Trace:
- variable:user_request <- normalized from Inputs for each run
- constraint:evidence_required <- direct from Policies
- exception_flow:missing_timeframe <- inferred from Failure handling
- worker:SourceGatheringWorker <- inferred from Reusable process + Delegation policy
```

---

# 12. 第一轮不应该出现的内容

这个例子最重要的是看系统没有生成什么。

不应该出现：

```text
1. 无来源的 “Handle missing timeframe” command。
2. 无来源的 “Resolve conflicting instructions” command。
3. 无来源的 “Ask user for missing timeframe” input command。
4. 无来源的 TemplateMatchingWorker。
5. 无来源的 INVOKE TemplateMatchingWorker。
6. 无来源的 generic “Produce required output” command。
7. 没有 source evidence 的 CALL_API。
8. 用户未提及的新 exception flow。
9. 用户未提及的新 constraint。
```

---

# 13. 最终结论

对于这个输入，第一轮理想输出应该是：

```text
partial SPL draft
```

但它不是残缺失败，而是一个已经很有价值的高层设计草案：

```text
可完整生成：
- Agent / Persona
- Inputs
- Required outputs
- MainWorker
- Main flow skeleton
- SourceGatheringWorker
- Constraints
- Revision alternative flow

可 partial 生成：
- Failure handling exception flows
  condition 有来源
  handler 缺失

不应生成：
- TemplateMatchingWorker executable worker
- failure handler commands
- synthetic producer commands
- ungrounded API calls

必须输出：
- missing_handler diagnostics
- template matching contract ambiguity diagnostic
- TraceRecords
- assumptions / suggestions
- readable report
```

因此它的状态应是：

```text
completeness = partial
```

而不是：

```text
complete
```

也不是：

```text
blocked
```

因为它已经有足够信息生成有用的 SPL draft，但还缺少 failure handlers 等完善需求所必需的信息。
