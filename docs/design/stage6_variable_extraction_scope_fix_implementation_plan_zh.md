# Stage 6 变量提取范围与 SymbolTable Declaration Authority 实施计划

本文档严格基于 `docs/design/stage6_variable_extraction_scope_fix_plan_zh.md` 制定。实施目标是：建立 **SymbolTable declaration authority gate**，确保所有进入 `SymbolTable` / `ResourceRegistryIR.variables` / `[DEFINE_VARIABLES:]` 的变量都有明确声明 authority，并阻止 control/guard/read-only context 被误提升为变量声明。

本计划覆盖 S6V0-S6V6，并新增 S6V4.5 作为 P0 hard gate。它不是单纯 prompt 修复，而是一次跨 Stage 3.5 candidate IO、worker contract、Stage 6 resource extraction、Stage 7 SymbolTable writes、Stage 9.5 composite rewrite、SPL Editing repair writes、Stage 6.5 condition reference、Stage 9.5 validation/render closure 的 authority 收口。

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
Declaration-authoritative source roles
  -> VariableDeclarationAuthority metadata / sidecar
  -> Stage6VariableDeclarationPolicy
  -> admitted VariableSpec / VariableSymbol
  -> SymbolTable / ResourceRegistryIR.variables

Read-only source roles
  -> read-only context only
  -> no SymbolTable admission
  -> optional Stage 6 audit diagnostic

Stage 6.5 condition reference resolver
  -> resolves only against existing SymbolTable
  -> never creates symbols
  -> emits source-sensitive diagnostics

Stage 9.5 condition validator
  -> validates scope visibility / execution availability / rewrites
  -> does not invent variables

Renderer
  -> renders existing typed artifacts only
  -> never declares variables or repairs references
```

核心 invariant：

```text
Every SymbolTable variable has declaration authority.
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. **SymbolTable admission 必须有 authority**：任何进入 `SymbolTable` 的变量必须能追溯到 declaration-authoritative source role 或 typed artifact。
2. **Stage 6 与 SPL grammar 解耦**：Stage 6 prompt/context 不使用 `CONDITION`、`DESCRIPTION_WITH_REFERENCES`、`COMMAND_RESULT`、`IF_BLOCK` 等 grammar/IR 术语作为实现 authority。
3. **禁止 demo answer leakage**：Stage 6 prompt/few-shot 不得包含 `usage.py` / `internal_comms.txt` 的具体变量名、句子或答案。
4. **不做变量名 blacklist**：不得以 `enough_required_information`、`user_asks_for_revision` 等具体名字作为永久黑名单。测试必须验证 authority，不验证名字本身。
5. **Stage 7 不能成为 Stage 6 前置依赖**：Stage 6 只消费 pre-Stage7 explicit action output intent；Stage 7 / post-Stage7 可以补充 typed relation authority，但必须走同一 declaration authority gate。
6. **Worker contract 不天然可信**：`WorkerSpecIR.input_contract` / `output_contract`、Stage 3.5 candidate IO、handoff candidate IO 默认只是 advisory，除非有 declaration authority。
7. **Condition/read-only text 不声明变量**：control/guard clauses、rules/constraints、profile/persona、display text、stop reason、exception log 只能作为 read-only context。
8. **Stage 6.5 existing-symbol-only**：Stage 6.5 可以解析已有 symbol 的引用，但不得创建 SymbolTable 变量。
9. **所有 SymbolTable write path 都必须审计**：任何 `symbol_table.declare(...)` / `declare_scoped(...)` 调用点都必须映射到 declaration authority category，不能只管 Stage 6。
10. **Diagnostics 分层**：Stage 6 rejection 默认 audit/info；explicit missing `<REF>` 可 completion-blocking；LLM unresolved/rejected semantic match 默认非 completion-blocking。
11. **Renderer 不兜底**：Renderer 不修复变量声明、不解析未决引用、不做 semantic fallback。

---

## 3. LLM / Rule-based 决策约束

本计划允许修改 Stage 6 prompt 和 context schema，但 prompt 不是 correctness authority。

允许的确定性逻辑：

```text
- 从结构化 declaration authority metadata 读取 admissibility。
- 从 resource contract demand / adapter fact / explicit output intent 做 presence check。
- 对 Stage 6 LLM candidate 做 deterministic admission/rejection。
- 对 Stage 6.5 explicit <REF> 做 parser-level validation。
- 对 condition reference diagnostic 按来源分类。
```

禁止的逻辑：

```text
- 根据变量名字符串 blacklist/allowlist 判定合法性。
- 根据关键词猜测某个 natural-language guard 必须变成变量。
- 为了通过 demo 在 prompt 中加入 internal_comms 特定答案。
- 让 Stage 6.5 LLM 输出创建新 SymbolTable entry。
- 让 renderer 或 final SPL 文本反向修正 SymbolTable。
```

---

## 4. S6V0：Characterization 与 Baseline Lock

### 4.1 目标

锁定当前错误链路，作为后续修复的证据基线：

```text
Stage 6 prompt requires condition variable declarations.
Demo final SPL defines condition-only predicates.
Stage 3.5 / worker contract may carry predicate-like candidate IO.
Stage 6.5 resolves generated symbols because SymbolTable is polluted.
```

S6V0 不修复行为，只产出 characterization tests / reports。

### 4.2 可编辑范围

允许新增：

```text
tests/characterization/pipeline/
tests/unit/pipeline/stage6/
artifacts/reviews/stage6_variable_authority/S6V0/
```

允许修改：

```text
docs/design/stage6_variable_extraction_scope_fix_implementation_plan_zh.md
```

### 4.3 禁止改动

S6V0 禁止修改：

```text
prompts/stage6_system.txt
src/nl2spl/pipeline/**
src/nl2spl/ir/**
examples/usage.py
examples/output/spl_editing_demo/run_demo.py
```

### 4.4 设计要求

Characterization 应记录：

```text
1. prompt 中仍有 condition variable declaration 规则。
2. final_spl.txt 当前出现 condition-only DEFINE_VARIABLES。
3. condition_variable_reference_plan 当前引用这些变量。
4. Stage 3.5 candidate IO / worker contract 中是否已有 predicate-like variable。
```

目标行为断言若当前会失败，不得放入默认 pytest 伪装通过；可以作为 helper 或 review artifact。

### 4.5 测试计划

新增或记录：

1. `test_stage6_prompt_current_condition_variable_rule_present`
2. `test_demo_current_condition_predicates_in_define_variables`
3. `test_demo_current_condition_refs_use_generated_symbols`
4. `test_stage3_5_candidate_io_current_authority_inventory`

### 4.6 验收标准

S6V0 通过条件：

1. 当前错误链路有可复验证据。
2. 无 production code 行为修改。
3. 无 skip/xfail 掩盖目标行为。
4. Review artifact 记录当前 demo 变量清单与 source artifact 路径。

### 4.7 PM 审核清单

PM 必须检查：

1. S6V0 是否只锁定行为，未修复行为。
2. 是否记录 Stage 6 prompt、final SPL、Stage 6.5 plan、Stage 3.5 candidate IO 四类证据。
3. 是否没有将 target behavior failure 作为通过测试提交。

---

## 5. S6V1：Stage 6 Prompt Authority 修复

### 5.1 目标

删除 Stage 6 prompt 中“condition variable 必须声明为 step variable”的错误规则，并以 source-document roles 重写变量声明规则。

### 5.2 可编辑范围

允许修改：

```text
prompts/stage6_system.txt
tests/unit/pipeline/stage6/test_stage6_prompt_contract.py
```

允许新增：

```text
tests/unit/pipeline/stage6/
```

### 5.3 禁止改动

S6V1 禁止修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/**
src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/**
src/nl2spl/ir/**
examples/output/demo/**
```

### 5.4 设计要求

Prompt 必须表达：

```text
Declare variables only from run inputs, required deliverables,
explicit action outputs, confirmed response targets, or admitted repair outputs.
Do not declare variables solely from guard/control clauses, rules,
constraints, profile text, or display text.
```

Prompt 不得包含：

```text
CONDITION
DESCRIPTION_WITH_REFERENCES
COMMAND_RESULT
IF_BLOCK
ALTERNATIVE_FLOW
EXCEPTION_FLOW
```

Prompt 不得包含 demo fixture 答案：

```text
enough_required_information
user_asks_for_revision
sources_needed
sources_available
approved source recipes
source evidence set
draft communication artifact
```

### 5.5 测试计划

新增单元测试：

1. prompt 不含 `Every condition variable`。
2. prompt 不含 grammar authority terms。
3. prompt 不含 `internal_comms` fixture-specific variables/sentences。
4. prompt 包含 source-document role 规则。

### 5.6 验收标准

S6V1 通过条件：

1. Prompt 使用自然语言 source roles，而不是 SPL grammar roles。
2. Prompt 无 demo answer leakage。
3. Prompt 明确禁止 guard/control/read-only text 声明变量。
4. S6V0 characterization 不要求被修复。

### 5.7 PM 审核清单

PM 必须检查：

1. 是否只改 prompt 与 prompt tests。
2. 是否没有把 demo 变量名写进 prompt/few-shot。
3. 是否没有引入 keyword blacklist 规则。

---

## 6. S6V2：Stage 6 Context Schema 修复

### 6.1 目标

将 Stage 6 prompt context 改为稳定 schema contract，区分：

```text
DECLARATION_EVIDENCE
READ_ONLY_CONTEXT
```

控制条件、规则、profile、display 等 read-only context 不得作为变量声明证据。

### 6.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/context_builder.py
tests/unit/test_stage6_resource_context_v2.py
```

允许新增：

```text
tests/unit/pipeline/stage6/test_stage6_context_schema.py
```

### 6.3 禁止改动

S6V2 禁止修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py
src/nl2spl/ir/**
prompts/stage6_system.txt
```

### 6.4 设计要求

Context builder 输出结构必须包含等价分区：

```text
DECLARATION_EVIDENCE:
  run_inputs
  required_deliverables
  resource_contract_demands
  explicit_action_output_intents
  confirmed_response_targets

READ_ONLY_CONTEXT:
  control_clauses
  branch_descriptions
  rules_constraints
  profile_persona
  display_text
```

如果仍保留 flow/block condition summary，必须只出现在 `READ_ONLY_CONTEXT`。

行为/control spans 应与 declaration/action-output spans 分区呈现。不得继续将全部 source spans 作为同等变量提取上下文。

### 6.5 测试计划

新增单元测试：

1. run inputs 进入 `DECLARATION_EVIDENCE.run_inputs`。
2. required deliverables 进入 `DECLARATION_EVIDENCE.required_deliverables`。
3. flow/block guard text 只进入 `READ_ONLY_CONTEXT.control_clauses`。
4. rules/constraints 只进入 `READ_ONLY_CONTEXT.rules_constraints`。
5. context 中出现硬文本：`Only DECLARATION_EVIDENCE may introduce variables` 或等价 schema instruction。

### 6.6 验收标准

S6V2 通过条件：

1. Context schema 可由测试稳定断言。
2. Guard/control clauses 不在 declaration evidence。
3. 旧 `Flow summary` / `Block summary` 若保留，必须明确 read-only。

### 6.7 PM 审核清单

PM 必须检查：

1. 是否只有 context builder 与测试变更。
2. 是否没有在 context builder 中通过关键词判断变量。
3. 是否没有改变 Stage 6 extractor admission 行为。

---

## 7. S6V2.5：Declaration Authority Metadata / Sidecar

### 7.1 目标

为所有可能进入 SymbolTable 的 typed artifacts 建立 declaration authority 表达能力。MVP 可使用 sidecar，不强制一次性修改所有 dataclass。

这是本计划的 hard gate。没有 S6V2.5，不允许进入 S6V3/S6V4。

### 7.2 可编辑范围

允许新增：

```text
src/nl2spl/ir/variable_declaration_authority_ir.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/declaration_authority.py
tests/unit/pipeline/stage6/test_variable_declaration_authority.py
```

允许修改：

```text
src/nl2spl/ir/resource_registry_ir.py
src/nl2spl/ir/symbol_table.py
src/nl2spl/ir/flow_structure_ir.py
src/nl2spl/ir/worker_plan_ir.py
src/nl2spl/compiler/artifacts/snapshot/serialization/**
src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/**
src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py
```

实际实现应优先选择最小可行 sidecar，减少 IR dataclass churn。

### 7.3 禁止改动

S6V2.5 禁止修改：

```text
src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/**
src/nl2spl/pipeline/stages/stage9_5_normalizer/**
src/nl2spl/rendering/**
```

### 7.4 设计要求

需要表达等价字段：

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

准入默认值：

```text
adapter_hard_fact              -> true
resource_contract_demand       -> true
explicit_action_output_intent  -> true
api_contract_response          -> true only if response contract known
worker_handoff_binding         -> true only if binding admitted
request_input_value_target     -> true
user_confirmed_repair          -> true
llm_candidate_io               -> false
control_predicate_guess        -> false
read_context_only              -> false
```

Stage 3.5 candidate `possible_inputs` / `possible_outputs` 默认：

```text
declaration_authority = llm_candidate_io
admissible_as_symbol = false
```

除非被 adapter hard fact、resource demand、explicit action output intent、handoff binding 或 user-confirmed repair admission 覆盖。

### 7.5 测试计划

新增单元测试：

1. Authority sidecar 可序列化/反序列化。
2. Stage 3.5 candidate IO 默认 inadmissible。
3. Resource contract demand 变量 admissible。
4. Adapter hard fact 变量 admissible。
5. Worker handoff binding 只有 admitted 时 admissible。
6. 无 `source_span_ids`、无 `contract_demand_id`、无 explicit authority 的 candidate IO 不 admissible。

### 7.6 验收标准

S6V2.5 通过条件：

1. Contract fields 或 sidecar 可表达 declaration authority。
2. Candidate IO 默认不进入 SymbolTable。
3. `_merge_contract_variables()` 可读取 authority metadata 或 sidecar。
4. Artifact serializers 覆盖新增 metadata/sidecar。
5. 无 renderer / Stage 6.5 / Stage 9.5 变更。

### 7.7 PM 审核清单

PM 必须检查：

1. 是否真的有 authority metadata/sidecar，而不是只改 prompt。
2. 是否没有让 `llm_candidate_io` 默认 admissible。
3. 是否没有通过变量名 blacklist 处理 demo 变量。
4. 是否没有把 Stage 7 relation plan 作为 Stage 6 前置输入。

---

## 8. S6V3：Stage6VariableDeclarationPolicy

### 8.1 目标

新增 deterministic admission gate，在变量进入 `ResourceRegistryIR` / `SymbolTable` 前执行。

### 8.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/variable_declaration_policy.py
tests/unit/pipeline/stage6/test_variable_declaration_policy.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/__init__.py
```

### 8.3 禁止改动

S6V3 禁止修改：

```text
prompts/stage6_system.txt
src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py
src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/**
```

### 8.4 设计要求

`Stage6VariableDeclarationPolicy` 输入：

```text
LLM variable candidates
declaration evidence set
read-only context evidence set
declaration authority metadata / sidecar
resource contract demand view
route/action output intent view
worker contract fields
```

输出：

```text
accepted VariableSpec list
rejected candidate audit records
diagnostics / warnings
```

拒绝原因枚举：

```text
control_clause_only
read_context_only
unbacked_step_variable
inadmissible_candidate_io
predicate_as_variable_without_declaration_authority
missing_declaration_authority
```

注意：`predicate_as_variable_without_declaration_authority` 不得实现为变量名 blacklist。它必须基于 evidence role / source role / authority metadata。

### 8.5 测试计划

新增单元测试：

1. input contract candidate accepted。
2. required deliverable candidate accepted。
3. explicit action output intent candidate accepted。
4. guard/control context only candidate rejected。
5. display/profile/rule text only candidate rejected。
6. `llm_candidate_io` without evidence rejected。
7. 同名变量在有 explicit authority 时可 accepted，证明不是 blacklist。

### 8.6 验收标准

S6V3 通过条件：

1. Policy 可独立测试。
2. 所有 reject 都有结构化 reason。
3. 无 LLM 调用。
4. 无变量名黑名单。

### 8.7 PM 审核清单

PM 必须检查：

1. 是否存在 raw keyword/variable-name blacklist。
2. 是否每个 reject reason 都有测试。
3. 是否未接入生产路径；生产接入留给 S6V4。

---

## 9. S6V4：Stage 6 Extractor Integration

### 9.1 目标

将 `Stage6VariableDeclarationPolicy` 接入 Stage 6 worker-scoped 和 legacy extraction，使 rejected variables 永不进入 `ResourceRegistryIR` / `SymbolTable`。

### 9.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py
src/nl2spl/pipeline/orchestrator.py
tests/unit/pipeline/stage6/
tests/integration/pipeline/
```

### 9.3 禁止改动

S6V4 禁止修改：

```text
src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/**
src/nl2spl/pipeline/stages/stage9_5_normalizer/**
src/nl2spl/rendering/**
```

### 9.4 设计要求

接入点：

```text
LLM result variables
  -> Stage6VariableDeclarationPolicy
  -> accepted variables only
  -> ResourceRegistryIR / SymbolTable
```

Contract merge：

```text
WorkerSpecIR.input_contract / output_contract
  -> authority metadata lookup
  -> merge only if admissible_as_symbol
```

Audit：

```text
Rejected variables must be persisted in stage artifacts or diagnostics.
Audit diagnostics are info/report-only unless separately escalated.
```

### 9.5 测试计划

新增/更新：

1. LLM emits condition-only boolean -> not in SymbolTable。
2. LLM emits input contract variable -> in SymbolTable。
3. Worker contract candidate IO without authority -> not in SymbolTable。
4. Resource contract output -> in SymbolTable。
5. Rejection audit appears in stage artifact。
6. Existing API extraction tests still pass。

### 9.6 验收标准

S6V4 通过条件：

1. Stage 6 production path uses policy。
2. `_merge_contract_variables()` respects authority metadata。
3. No condition-only variables enter SymbolTable via LLM variables or worker contract merge。
4. Focused Stage 6 tests pass。

### 9.7 PM 审核清单

PM 必须检查：

1. 是否所有 `declare` / `declare_scoped` 调用路径都有 authority admission。
2. 是否没有新 fallback 在 policy 失败时放行变量。
3. 是否保存 rejection evidence。

---

## 10. S6V4.5：SymbolTable Write-path Authority Audit / Guard

### 10.1 目标

建立全量 SymbolTable 写入路径审计与 guard。该阶段是 P0 hard gate：在进入 S6V5 / S6V6 前，必须证明所有 `symbol_table.declare(...)` / `symbol_table.declare_scoped(...)` 调用点都有 declaration authority 分类、测试或明确 waiver。

目标不是把 Stage 7 / Stage 9.5 / SPL Editing 全部重构进 Stage 6，而是确保全局 invariant 成立：

```text
Every SymbolTable variable has declaration authority.
```

### 10.2 当前已知写入点

实施时必须用静态扫描刷新列表。当前至少包括：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py
  symbol_table.declare(...)

src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py
  symbol_table.declare_scoped(...)

src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
  symbol_table.declare(...)

src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py
  symbol_table.declare(...)

src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
  symbol_table.declare_scoped(...)

src/nl2spl/pipeline/stages/stage9_5_normalizer/composite_output_applier.py
  symbol_table.declare(...)

src/nl2spl/compiler/spl_editing/stage_slices/worker_delegation_closure.py
  symbols.declare_scoped(...)
```

### 10.3 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/symbol_table_write_audit.py
tests/unit/pipeline/test_symbol_table_write_authority_audit.py
artifacts/reviews/stage6_variable_authority/S6V4_5/
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py
src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/composite_output_applier.py
src/nl2spl/compiler/spl_editing/stage_slices/worker_delegation_closure.py
tests/unit/pipeline/stage7/
tests/unit/pipeline/stage9_5/
tests/unit/compiler/spl_editing/
```

修改应优先添加 authority metadata / guard / tests，不应重写 Stage 7 extraction 或 Stage 9.5 normalization 语义。

### 10.4 禁止改动

S6V4.5 禁止修改：

```text
src/nl2spl/rendering/**
src/nl2spl/compiler/producer_index.py
src/nl2spl/compiler/irs/**
prompts/**
```

### 10.5 Authority 分类要求

每个写入点必须映射到以下分类之一：

```text
stage6_llm_variable
  -> must pass Stage6VariableDeclarationPolicy

stage6_worker_contract_merge
  -> must pass declaration authority metadata / sidecar

stage7_new_variable
  -> must carry explicit_action_output_intent or post_stage7_relation_authority

stage7_handoff_output_binding
  -> worker_handoff_binding

stage9_5_composite_output_rewrite
  -> derived_from_admitted_output / producer_intent_id

spl_editing_repair
  -> user_confirmed_repair

legacy_compat_waiver
  -> explicit owner, reason, removal condition
```

### 10.6 设计要求

必须提供 write-path inventory：

```text
call_site
stage
owner
authority_category
accepted_inputs
guard_function_or_metadata
tests
waiver_if_any
```

所有写入点必须满足至少一项：

```text
1. Passes Stage6VariableDeclarationPolicy.
2. Carries declaration authority metadata / sidecar.
3. Is covered by explicitly documented post-stage7 authority gate.
4. Has a temporary legacy waiver with owner, reason, and removal condition.
```

禁止：

```text
symbol_table.declare(source="step") with no authority trace
symbol_table.declare_scoped(...) from candidate IO by default
Stage 7 LLM result.get("new_variables") directly entering SymbolTable
Composite output rewrite declaring variables without admitted source output trace
Repair stage declaring variables without user_confirmed_repair trace
```

### 10.7 测试计划

新增测试：

1. Static scan lists all `declare` / `declare_scoped` call sites。
2. Every call site appears in write-path inventory。
3. Stage 7 `new_variables` without explicit output intent is rejected or not declared。
4. Stage 7 handoff output binding writes with `worker_handoff_binding` authority。
5. Stage 9.5 composite output write requires admitted original output / producer intent。
6. SPL Editing repair write carries `user_confirmed_repair` authority。
7. Any legacy waiver has owner/reason/removal condition。

### 10.8 验收标准

S6V4.5 通过条件：

1. `rg -n "\\.declare(_scoped)?\\(" src/nl2spl -S` 的所有 production hits 都被分类。
2. 每个 call site 都有 authority guard、metadata trace、测试或 waiver。
3. 无未分类 SymbolTable write path。
4. Stage 7 / Stage 9.5 / SPL Editing 合法写入不被误判，但均可追溯 declaration authority。
5. S6V4.5 review artifact 保存 scan output 与 mapping table。

### 10.9 PM 审核清单

PM 必须检查：

1. Static scan 是否覆盖所有 production write paths。
2. 是否存在未分类 `declare` / `declare_scoped`。
3. 是否有 ownerless waiver。
4. Stage 7 是否仍有 LLM `new_variables` 直接写 SymbolTable。
5. Stage 9.5 composite rewrite 是否有 admitted output trace。
6. SPL Editing repair 是否明确 `user_confirmed_repair`。

---

## 11. S6V5：Stage 6.5 Existing-symbol-only Hardening

### 11.1 目标

收紧 Stage 6.5，确保它只解析已有变量引用，不创建变量，不把 LLM unresolved mention 默认变成 completion-blocking user-facing issue。

### 11.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver/**
src/nl2spl/pipeline/stages/stage9_5_normalizer/condition_variable_validator.py
tests/unit/pipeline/stage6_5/
tests/unit/pipeline/stage9_5/
```

### 11.3 禁止改动

S6V5 禁止修改：

```text
src/nl2spl/pipeline/stages/stage6_resource_extractor/**
src/nl2spl/ir/symbol_table.py
src/nl2spl/rendering/**
```

### 11.4 设计要求

场景规则：

```text
natural-language guard + no existing symbol
  -> no ref rewrite
  -> no SymbolTable mutation
  -> no completion-blocking diagnostic

explicit <REF>x</REF> + no existing symbol
  -> unresolved explicit reference diagnostic
  -> blocks_completion = true

LLM semantic match rejected
  -> report/audit diagnostic
  -> blocks_completion = false by default
```

### 11.5 测试计划

新增测试：

1. natural-language guard without symbol remains natural language。
2. explicit missing `<REF>` emits completion-blocking diagnostic。
3. rejected semantic match is not completion-blocking。
4. Stage 6.5 does not mutate SymbolTable。
5. Semantic match can only select existing symbol。

### 11.6 验收标准

S6V5 通过条件：

1. Stage 6.5 existing-symbol-only invariant 有测试。
2. Diagnostic blocking policy 按来源区分。
3. No SymbolTable write occurs in Stage 6.5。

### 11.7 PM 审核清单

PM 必须检查：

1. Stage 6.5 是否仍有任何 path 创建变量。
2. 是否把 LLM unresolved mention 默认 completion-blocking。
3. 是否没有改 Stage 6 policy。

---

## 12. S6V6：Demo E2E 与 Regression Freeze

### 12.1 目标

在真实 `examples/usage.py` demo 上证明 condition-only predicates 不再进入 `DEFINE_VARIABLES` / `<REF>`，同时 required output producer diagnostics 不回退。

### 12.2 可编辑范围

允许修改：

```text
tests/integration/pipeline/
artifacts/reviews/stage6_variable_authority/S6V6/
```

允许运行生成：

```text
examples/usage.py
examples/output/demo/**
```

### 12.3 禁止改动

S6V6 禁止修改：

```text
src/nl2spl/rendering/**
src/nl2spl/compiler/spl_editing/**
```

除非前序阶段已有明确变更需求。

### 12.4 设计要求

E2E 必须断言：

```text
final_spl.txt does not define condition-only predicates.
final_spl.txt does not render <REF> for condition-only predicates.
feedback_report.md no longer reports missing_provenance for removed condition-only variables.
required output diagnostics remain present where appropriate.
condition text remains renderable as natural language.
```

不得通过 renderer 过滤文本来隐藏问题；必须证明 SymbolTable / condition plan 本身正确。

### 12.5 测试计划

新增 E2E / integration：

1. `internal_comms` final SPL no condition-only `DEFINE_VARIABLES`。
2. `condition_variable_reference_plan` no refs for removed condition-only predicates。
3. `feedback_report` no missing_provenance for removed predicates。
4. `source_evidence_set` / required outputs still tracked by required-output mechanism。
5. Static scan: renderer contains no semantic fix for these variables。

### 12.6 验收标准

S6V6 通过条件：

1. Focused Stage 6 / Stage 6.5 / Stage 9.5 tests pass。
2. Demo E2E passes。
3. Artifact bundle includes final_spl, SymbolTable, condition plan, feedback_report, rejection audit。
4. No renderer semantic fix。
5. No variable-name blacklist。

### 12.7 PM 审核清单

PM 必须检查：

1. E2E 是否证明 source artifact 层正确，而不是只看 rendered SPL。
2. Required output diagnostics 是否仍在。
3. 是否有 artifact manifest/hash。
4. 是否存在 `enough_required_information` 等 demo-specific denylist。

---

## 13. Decision Gate：Future Post-Stage7 SymbolTable Enrichment

### 13.1 目标

明确 Stage 7 typed relation plan 如何在 Stage 6 之后补充 SymbolTable / variable visibility，避免错误地把 Stage 7 作为 Stage 6 的前置依赖。

### 13.2 可选方案

```text
方案 A：Stage 7 relation plan 只供 ProducerIndex / availability 使用，不回写 SymbolTable。
方案 B：Stage 9.5 根据 Stage 7 relation plan 生成 post-stage7 symbol enrichment sidecar。
方案 C：Stage 9.5 回写 SymbolTable，但必须记录 declaration authority trace。
```

推荐方案 B。理由：

```text
SymbolTable 原始声明与 post-Stage7 executable relation enrichment 分离；
不会引入 Stage 6 -> Stage 7 时序倒置；
便于审计变量是 pre-Stage7 declaration 还是 post-Stage7 production-derived。
```

### 13.3 必须明确的问题

实施前必须回答：

1. Stage 7 produced variables 是否需要进入 renderer 的 `[DEFINE_VARIABLES:]`。
2. 如果进入，由谁提供 declaration authority trace。
3. 是否允许 Stage 9.5 直接修改 SymbolTable，还是只输出 sidecar。
4. Post-stage7 enrichment 是否影响 SPL Editing snapshot serialization。

### 13.4 验收标准

该 gate 通过条件：

1. 不把 Stage 7 relation plan 作为 Stage 6 input。
2. 所有 post-stage7 variable enrichment 仍有 declaration authority。
3. PM 明确批准方案后，才能实施超出 S6V0-S6V6 的 SymbolTable enrichment。

---

## 14. E2E 验收场景

### 14.1 internal_comms condition-only predicate removal

步骤：

1. 运行 `examples/usage.py`。
2. 检查 `examples/output/demo/final_spl.txt`。
3. 检查 `condition_variable_reference_plan.json`。
4. 检查 `feedback_report.md`。

期望：

```text
No DEFINE_VARIABLES for condition-only predicates.
No <REF> for condition-only predicates.
Natural-language conditions remain renderable.
Required output diagnostics unchanged.
```

### 14.2 Explicit input predicate accepted

构造 fixture：

```text
Inputs:
- sources needed: boolean

Process:
If sources needed, retrieve sources.
```

期望：

```text
sources_needed enters SymbolTable because input contract authorizes it.
Condition may reference sources_needed.
```

### 14.3 Explicit produced predicate accepted

构造 fixture：

```text
Determine whether sources are needed.
If sources are needed, retrieve sources.
```

期望：

```text
Pre-Stage7 Stage 6 does not invent the variable unless explicit output intent exists.
Post-Stage7 relation authority may admit/track the produced predicate only through approved gate.
```

### 14.4 Worker contract candidate IO rejected by default

构造 fixture 或 mock：

```text
Stage 3.5 candidate possible_inputs = ["sources_needed"]
authority = llm_candidate_io
admissible_as_symbol = false
```

期望：

```text
_merge_contract_variables() does not add sources_needed to SymbolTable.
```

---

## 15. PM 总审核清单

每个阶段提交时，PM 必须检查：

1. 是否严格对齐设计文档。
2. 是否扩大范围到 ProducerIndex policy / renderer / SPL Editing issue inventory。
3. 是否新增未批准的 LLM prompt/schema 行为。
4. 是否新增 rule-based semantic fallback。
5. 是否存在 demo-specific variable denylist。
6. 是否把 Stage 7 relation plan 当作 Stage 6 input。
7. 是否让 worker contract / candidate IO 默认进入 SymbolTable。
8. 是否每个 SymbolTable entry 都可追踪 declaration authority。
9. 是否所有 `symbol_table.declare` / `declare_scoped` production call site 都被静态扫描列出。
10. 是否每个 SymbolTable write path 都映射到 declaration authority category。
11. 是否存在未分类 write path 或 ownerless waiver。
12. 是否每个 rejected variable candidate 都有结构化 reason。
13. 是否 Stage 6.5 仍只读 SymbolTable。
14. 是否 explicit missing `<REF>` 和 LLM rejected match 的 blocking policy 区分清楚。
15. 是否存在 renderer semantic fix。
16. 是否存在 skip / xfail / 弱断言。
17. 是否 artifacts 包含 before/after proof。
18. 是否 required output diagnostics 保持不回退。

---

## 16. 阶段完成顺序

推荐顺序：

```text
S6V0   Characterization
S6V1   Prompt Authority Fix
S6V2   Context Schema Fix
S6V2.5 Declaration Authority Metadata
S6V3   Stage6VariableDeclarationPolicy
S6V4   Stage 6 Extractor Integration
S6V4.5 SymbolTable Write-path Authority Audit / Guard
S6V5   Stage 6.5 Existing-symbol-only Hardening
S6V6   Demo E2E / Regression Freeze
Gate   Future Post-Stage7 SymbolTable Enrichment Decision
```

依赖关系：

```text
S6V1 and S6V2 may be implemented after S6V0.
S6V2.5 must complete before S6V3/S6V4.
S6V3 must complete before S6V4.
S6V4.5 must complete before S6V5/S6V6.
S6V5 should run after S6V4.5 so all SymbolTable write paths are classified.
S6V6 must run last.
Post-Stage7 enrichment is not part of S6V0-S6V6 unless PM explicitly expands scope.
```

---

## 17. Release Freeze 条件

本计划完成时必须提供：

```text
1. S6V0-S6V6 review reports, including S6V4.5 write-path audit report.
2. Focused pytest output for Stage 6 / Stage 6.5 / Stage 9.5.
3. Demo E2E output from examples/usage.py.
4. Artifact bundle:
   - final_spl.txt
   - SymbolTable / ResourceRegistryIR payload
   - declaration authority sidecar or metadata payload
   - condition_variable_reference_plan.json
   - feedback_report.md
   - Stage 6 rejected variable audit
   - SymbolTable write-path authority inventory
5. Ruff output for modified files.
6. Static scan showing no demo-specific denylist.
7. Static scan showing all `declare` / `declare_scoped` call sites are classified.
8. Statement that renderer did not participate in semantic fix.
```

最终判定：

```text
pass only if every SymbolTable variable has declaration authority
and condition-only predicates no longer enter DEFINE_VARIABLES / <REF>.
```
