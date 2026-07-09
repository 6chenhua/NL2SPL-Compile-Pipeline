# Stage 6 变量提取范围与 SymbolTable Declaration Authority 修复计划

## 1. 问题背景

当前 demo 中出现了这类变量：

```text
enough_required_information
user_asks_for_revision
sources_needed
sources_available
```

它们主要来自自然语言中的控制条件或判断语句，例如“当信息足够时”“如果用户要求修改”“如果需要且可用来源”。这些语句表达的是流程分支条件，不是用户显式声明的输入、输出，也不是某个动作明确生产出的结果。

当前错误链路是：

```text
natural-language control predicate
  -> Stage 6 declares a variable
  -> Stage 6.5 resolves the condition against that variable
  -> Stage 9.5 treats it as a valid condition reference
  -> renderer emits DEFINE_VARIABLES / <REF>
```

这条链路不成立。控制条件可以读取已有变量，但它本身不是变量声明来源。

进一步审查后，需要把问题范围从 “Stage 6 prompt 抽错变量” 扩展为：

```text
All SymbolTable entries must have declaration authority.
Stage 6 is one admission point, but not the only possible pollution source.
```

真实污染链可能包括：

```text
Stage 3.5 candidate IO / worker contract
  -> Stage 6 contract merge
  -> SymbolTable pollution
  -> Stage 6.5 existing-symbol resolution
  -> Stage 9.5 semantic ref materialization
  -> renderer emits DEFINE_VARIABLES / <REF>
```

因此，修复不能只管 Stage 6 LLM 输出，还必须管上游 typed artifact 是否具备变量声明 authority。

## 2. 关键澄清：Stage 6 必须与 SPL grammar 解耦

SPL grammar 可以用来解释架构边界：条件文本是引用位置，不是声明位置。但这只是设计论证，不是 Stage 6 的实现语言。

Stage 6 面对的是：

```text
source natural language
adapter facts
resource contract demand view
upstream typed analysis artifacts
```

Stage 6 prompt 和 context 不应要求 LLM 理解这些 SPL grammar / IR 术语：

```text
CONDITION
DESCRIPTION_WITH_REFERENCES
COMMAND_RESULT
IF_BLOCK
ALTERNATIVE_FLOW
EXCEPTION_FLOW
```

Stage 6 的实现语言应是 source-document roles：

```text
run inputs
required deliverables
intermediate artifacts explicitly produced by an action
external call responses
child worker responses
control / guard clauses
rules and constraints
display text
profile/persona descriptions
```

硬规则：

```text
SPL grammar terms may appear in design rationale and tests.
SPL grammar terms must not become Stage 6 prompt authority.
Stage 6 prompt must describe source-document roles, not SPL grammar nodes.
```

## 3. 三类 Authority 必须分开

### 3.1 Variable Declaration Authority

谁有资格让一个名字进入：

```text
SymbolTable
ResourceRegistryIR.variables
DEFINE_VARIABLES
```

Declaration authority 只来自明确的数据声明或生产事实。

### 3.2 Variable Reference Authority

谁有资格把文本片段解析成对已有变量的读取引用。

例如控制条件、action 描述、约束文本、display text 可以引用变量，但引用不是声明。

### 3.3 Variable Availability Authority

谁判断变量在某个 decision point 前是否可见、是否已经可用。

这属于 Stage 9.5 / ProducerIndex / relation plan 的责任，不属于 Stage 6。

当前错误正是把这三类 authority 混在一起：为了让 condition 能 `<REF>` 化，Stage 6 先发明了 boolean predicate variable。

## 4. Stage 6 变量声明准入范围

Stage 6 只能从以下来源声明变量。

### 4.1 显式运行输入

允许来源：

```text
source section describes run inputs
adapter hard fact declares an input
resource contract demand declares a variable input
user-confirmed repair declares an input binding
```

例子类型：

```text
user request
known topics
timeframe
available source repositories
```

### 4.2 显式最终交付物

允许来源：

```text
source section describes required deliverables
adapter hard fact declares an output
resource contract demand declares a variable output
user-confirmed repair declares a required output
```

例子类型：

```text
draft communication artifact
source evidence set
assumptions log
completion status
```

这些变量是否有 producer，由 `ProducerIndex` / `RequiredOutputFulfillmentState` 判断。

### 4.3 明确由动作生产的中间结果

允许来源：

```text
source-level executable action output intent
route/construct metadata explicitly marked as output target
adapter hard fact output declaration
Stage 7 typed step relation plan
user-confirmed repair output declaration
```

禁止仅从任意行为描述中猜测输出变量。

### 4.4 外部调用或子流程响应目标

允许来源：

```text
API contract response target
worker handoff output binding
INVOKE response target
REQUEST_INPUT value target
typed repair response declaration
```

禁止：

```text
unknown API response -> invent response fields
control predicate -> invent boolean response field
candidate IO without evidence -> SymbolTable variable
```

### 4.5 用户确认 repair 新增的 typed output

SPL Editing repair 可以新增变量，但必须走 typed declaration：

```text
NewOutputDeclarationDraft
admitted output declaration
normalized repair directive
typed materialization plan
```

repair free text 不能直接成为变量声明 authority。

## 5. 禁止作为变量声明来源的文本

以下文本只能作为 read-only context 或 provenance context：

```text
control / guard clauses
branch conditions
rules and constraints
persona/profile descriptions
display messages
stop reasons
exception log text
general descriptive text
```

这些文本可以引用已有变量，但不能创建变量。

典型禁止项：

```text
enough_required_information
user_asks_for_revision
sources_needed
sources_available
required_slots_remain_missing
user_confirms
```

除非 source 明确把它们列为输入/输出，或某个 executable action 明确生产它们，否则不得进入 SymbolTable。

## 6. 上游 Typed Artifact Declaration Authority Gate

### 6.1 为什么必须覆盖上游 artifact

即使 Stage 6 prompt 修好了，污染仍可能来自：

```text
Stage 3.5 candidate possible_inputs / possible_outputs
WorkerSpecIR.input_contract / output_contract
Handoff candidate IO
LLM-generated worker contract skeleton
```

如果这些 artifact 被 Stage 6 无条件合并进 SymbolTable，控制谓词仍会绕过 Stage 6 LLM filter。

因此必须增加硬规则：

```text
WorkerSpecIR.input_contract / output_contract is not automatically declaration evidence.
ContractFieldIR is admissible only when it carries declaration authority.
Candidate IO is advisory unless admitted by a declaration-authority gate.
```

### 6.2 Declaration authority metadata

需要在 `ContractFieldIR`、`VariableSpec`、`VariableSymbol` 或并行 sidecar 中表达：

```python
declaration_authority: Literal[
    "adapter_hard_fact",
    "resource_contract_demand",
    "explicit_action_output_intent",
    "api_contract_response",
    "worker_handoff_binding",
    "request_input_value_target",
    "user_confirmed_repair",
    "llm_candidate_io",
    "control_predicate_guess",
    "read_context_only",
]

admissible_as_symbol: bool
evidence_role: str
source_span_ids: tuple[str, ...]
source_section_id: str | None
source_packet_id: str | None
contract_demand_id: str | None
producer_intent_id: str | None
```

MVP 可以用 sidecar，避免一次性重构所有 IR dataclass。但 SymbolTable admission 必须能读取等价信息。

### 6.3 默认准入规则

```text
adapter_hard_fact              -> admissible
resource_contract_demand       -> admissible
explicit_action_output_intent  -> admissible
api_contract_response          -> admissible only if contract known
worker_handoff_binding         -> admissible only if handoff binding admitted
request_input_value_target     -> admissible
user_confirmed_repair          -> admissible
llm_candidate_io               -> not admissible by default
control_predicate_guess        -> not admissible
read_context_only              -> not admissible
```

### 6.4 Contract merge rule

Stage 6 `_merge_contract_variables()` 或等价逻辑只能合并：

```text
admissible_as_symbol == true
```

禁止：

```text
source_span_ids empty + no contract_demand_id + no explicit authority
  -> silently enter SymbolTable
```

## 7. Stage 6 Prompt 修复

### 7.1 删除错误规则

必须删除当前 prompt 中类似规则：

```text
Every condition variable (used in IF conditions) has been declared
as a step variable.
```

### 7.2 替换为 source-role 规则

建议规则：

```text
Declare variables only when the source or typed context explicitly introduces
data that is provided, required as a deliverable, or produced by an executable
action.

Do not declare variables solely from guard clauses, branch conditions,
rules, constraints, profile text, or display text.

If a guard clause says "when enough information is available", keep it as a
natural-language control condition unless an existing input/output/action
result variable already represents that concept.
```

### 7.3 禁止 demo fixture 泄漏

新的 Stage 6 prompt 不得包含 `examples/usage.py` 或 `examples/input/internal_comms.txt` 的具体答案、变量名或句子。

禁止在 prompt/few-shot 中出现 demo-specific 内容，例如：

```text
enough_required_information
user_asks_for_revision
sources_needed
sources_available
approved source recipes
source evidence set
draft communication artifact
```

如果需要 few-shot，必须使用合成、通用、与 repo demo 无关的例子。

## 8. Stage 6 Context 修复

### 8.1 Context 必须成为 schema contract

不能只靠 Markdown 标题“提示”LLM。Context builder 应输出稳定分区：

```text
DECLARATION_EVIDENCE:
  run_inputs:
  required_deliverables:
  resource_contract_demands:
  explicit_action_output_intents:
  confirmed_response_targets:

READ_ONLY_CONTEXT:
  control_clauses:
  branch_descriptions:
  rules_constraints:
  profile_persona:
  display_text:
```

硬规则：

```text
Only DECLARATION_EVIDENCE may introduce variables.
READ_ONLY_CONTEXT may only refine descriptions of already admitted variables.
```

### 8.2 Source spans 也要分角色

当前直接把 behavior spans 给 Stage 6，容易诱导 LLM 从行为文本抽变量。应区分：

```text
source spans with declaration role
source spans with executable output role
source spans with behavior/control/read-only role
```

只有前两类可以支持新变量声明。

## 9. Deterministic Post-filter

Prompt 不是 correctness authority。即使 LLM 仍输出错误变量，也必须由 deterministic gate 拒绝。

建议新增：

```text
Stage6VariableDeclarationPolicy
```

职责：

```text
input:
  LLM variable candidates
  declaration evidence set
  read-only context evidence set
  declaration authority metadata / sidecar
  resource contract demand view
  route/action output intent view
  worker contract fields

output:
  accepted VariableSpec
  rejected candidate audit diagnostics
```

拒绝规则：

```text
candidate supported only by control/read-only context
  -> reject control_clause_only

candidate source == "step" but no executable output intent supports it
  -> reject unbacked_step_variable

candidate from worker contract but authority == llm_candidate_io
  -> reject inadmissible_candidate_io

candidate is boolean predicate normalized from guard clause
  -> reject predicate_as_variable_without_declaration_authority

candidate has no source_span_ids / contract_demand_id / explicit authority
  -> reject missing_declaration_authority
```

Diagnostics:

```text
kind = stage6_variable_candidate_rejected
severity = info
blocks_rendering = false
blocks_completion = false
```

这些 diagnostics 不进入 SPL Editing editable issue。

## 10. Stage 6.5 关系

Stage 6.5 的 invariant：

```text
Stage 6.5 resolves references only against existing SymbolTable.
Stage 6.5 must not add variables to SymbolTable.
```

### 10.1 自然语言 guard

如果条件是自然语言：

```text
sources are needed and available
```

且没有对应已声明变量：

```text
keep natural language
do not rewrite to <REF>sources_needed</REF>
do not create sources_needed
```

### 10.2 显式引用

如果条件中已经存在：

```text
<REF>x</REF>
```

但 `x` 不在 SymbolTable：

```text
emit unresolved explicit reference diagnostic
do not create x
```

### 10.3 LLM semantic match

LLM 可以建议自然语言条件对应某个已有 symbol，但只能从已有 SymbolTable 选择。

禁止：

```text
LLM proposes a new symbol
Stage 6.5 admits it
SymbolTable mutates
```

## 11. Stage 6.5 / Stage 9.5 Diagnostic Blocking Policy

需要区分不同来源，避免 Stage 6.5 成为新的噪声源。

### 11.1 Explicit missing REF

```text
condition text contains <REF>x</REF>
x not visible / unresolved
```

建议：

```text
severity = warning
blocks_rendering = false
blocks_completion = true
```

原因：SPL 可渲染，但语义完整性不足。

### 11.2 LLM unresolved variable-like mention

```text
natural-language condition mentions a variable-like concept
no existing symbol selected
```

默认：

```text
report/audit only
blocks_completion = false
```

除非 source role 明确要求该条件必须由 declared variable 表达。

### 11.3 LLM rejected semantic match

```text
LLM suggested matching condition to a symbol
validator rejected it
```

默认：

```text
diagnostic/report only
blocks_completion = false
```

### 11.4 Pure static condition

```text
condition remains natural language
no variable-like reference admitted
```

默认：

```text
no diagnostic
```

## 12. Stage 9.5 关系

Stage 9.5 负责最终检查：

```text
scope visibility
execution availability before decision point
qualified reference rewrite
composite output field rewrite
final condition text rewrite
```

Stage 9.5 不负责发明变量，也不应把 unresolved natural-language condition 强行变量化。

## 13. 分阶段实施计划

### S6V0: Characterization

目标：

```text
锁定当前错误行为。
```

证据：

```text
Stage 6 prompt currently instructs condition variable declaration.
Demo currently defines condition-derived variables.
Stage 3.5 candidate IO / worker contract may carry predicate-like names.
Stage 6.5 currently resolves those generated symbols.
```

### S6V1: Prompt 修复

修改范围：

```text
prompts/stage6_system.txt
prompt anti-leak tests
```

验收：

```text
No rule tells Stage 6 to declare condition variables.
Prompt uses source-document vocabulary, not SPL grammar vocabulary.
Prompt contains no usage.py/internal_comms fixture-specific answers.
```

### S6V2: Context Schema 修复

修改范围：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/context_builder.py
tests/unit/test_stage6_resource_context_v2.py
```

验收：

```text
Context has DECLARATION_EVIDENCE and READ_ONLY_CONTEXT.
Control/guard clauses are not declaration evidence.
Behavior/control spans are separated from declaration/action-output spans.
```

### S6V2.5: Declaration Authority Metadata

目标：

```text
让上游 typed artifacts 携带或映射 declaration authority。
```

可能修改范围：

```text
ContractFieldIR / VariableSpec / VariableSymbol sidecar
Stage 3.5 worker candidate IO projection
WorkerSpecIR contract materialization
Stage 6 contract merge adapter
artifact serializers
```

验收：

```text
1. Contract fields can express declaration_authority or equivalent sidecar.
2. Stage 3.5 candidate possible_inputs are not admissible_as_symbol by default.
3. _merge_contract_variables() merges only admissible fields.
4. Candidate IO without source_span_ids / contract_demand_id / explicit authority
   does not enter SymbolTable.
```

### S6V3: Stage6VariableDeclarationPolicy

建议新增：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/variable_declaration_policy.py
```

验收：

```text
candidate from input contract -> accepted
candidate from required deliverable -> accepted
candidate from executable output intent -> accepted
candidate from guard/control/read-only context only -> rejected
candidate from inadmissible worker contract IO -> rejected
```

### S6V4: Stage 6 Integration

修改范围：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py
```

验收：

```text
Rejected variables never enter ResourceRegistryIR or SymbolTable.
Filter warnings/diagnostics are persisted in stage artifacts.
Contract merge uses declaration authority metadata.
```

### S6V5: Stage 6.5 Existing-symbol-only hardening

修改范围：

```text
src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver
```

验收：

```text
Natural-language guards without existing symbol remain natural language.
Explicit missing <REF> emits diagnostic.
Rejected semantic match is not completion-blocking by default.
Stage 6.5 does not mutate SymbolTable.
```

### S6V6: Demo E2E

验收：

```text
examples/output/demo/final_spl.txt does not define condition-only predicates.
examples/output/demo/final_spl.txt does not render <REF> for condition-only predicates.
feedback_report.md no longer reports missing_provenance for removed condition-only variables.
Required-output producer diagnostics are unchanged.
```

## 14. 回归测试矩阵

### Prompt tests

```text
assert stage6 prompt does not contain:
  Every condition variable
  internal_comms fixture sentences
  usage.py fixture-specific variable names

assert stage6 prompt contains:
  Do not declare variables solely from guard/control clauses
```

### Context tests

```text
DECLARATION_EVIDENCE contains only inputs / deliverables / output intents / admitted targets.
READ_ONLY_CONTEXT contains guard/control/rule/profile/display context.
```

### Metadata tests

```text
ContractFieldIR or sidecar can represent declaration_authority.
candidate IO defaults to inadmissible unless authority is explicit.
contract merge rejects inadmissible candidate IO.
```

### Policy tests

```text
candidate from input contract -> accepted
candidate from required deliverable -> accepted
candidate from executable output intent -> accepted
candidate from guard clause only -> rejected
candidate from display/profile/rule text only -> rejected
candidate from llm_candidate_io without evidence -> rejected
```

### Stage 6.5 tests

```text
natural-language guard + no symbol -> no ref rewrite
explicit <REF>x</REF> + no symbol -> unresolved diagnostic
semantic match can only select existing symbol
rejected semantic match is not completion-blocking by default
```

### Demo tests

```text
condition-only predicates absent from DEFINE_VARIABLES
condition-only predicates absent from <REF>
real required outputs still tracked
```

## 15. 非目标

本修复不处理：

```text
1. 是否所有自然语言控制条件都必须结构化为变量。
2. ELSEIF branch condition IR 扩展。
3. StepVariableRelationPlan 全量重构。
4. ProducerIndex required output policy 改动。
5. SPL Editing issue inventory 是否展示 condition-reference diagnostics。
```

## 16. 最终验收标准

完成后必须满足：

```text
1. Every SymbolTable variable has declaration authority.
2. Stage 6 variable declaration authority is source-role based, not grammar-term based.
3. Stage 6 prompt has no usage.py/internal_comms answer leakage.
4. Stage 6 does not declare variables solely from control/guard/read-only context.
5. Stage 3.5 / worker contract candidate IO cannot bypass declaration authority.
6. Stage 6.5 resolves only existing variables and never mutates SymbolTable.
7. Condition-only predicates are not rendered as DEFINE_VARIABLES or <REF>.
8. Required output producer diagnostics remain intact.
9. Renderer does not participate in variable declaration or reference resolution.
```

