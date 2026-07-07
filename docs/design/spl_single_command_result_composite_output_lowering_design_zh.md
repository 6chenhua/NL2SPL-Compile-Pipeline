# SPL 单结果命令与聚合输出变量 Lowering 设计

## 1. 背景

`docs/spl_grammar.txt` 已收敛为单结果命令语法：

```text
COMMAND_RESULT := VAR_NAME ":" DATA_TYPE | REFERENCE
```

所有使用 `COMMAND_RESULT` 的 command body 都只能绑定一个结果目标：

```text
GENERAL_COMMAND    -> RESULT COMMAND_RESULT
REQUEST_INPUT      -> VALUE COMMAND_RESULT
CALL_API           -> RESPONSE COMMAND_RESULT
INVOKE_INSTRUCTION -> RESPONSE COMMAND_RESULT
```

这意味着后端不能继续生成 renderable multi-result command：

```text
COMMAND ... RESULT a: A, b: B SET
```

但一个 source-level action 仍可能语义上产生多个输出字段。因此需要在 compiler 内部建立明确的 lowering boundary：

```text
semantic output intents
-> CompositeOutputPlan
-> one structured composite COMMAND_RESULT
-> qualified field references
```

这不是 renderer 格式问题，而是 SPL command surface 与 compiler IR output intent 之间缺少 typed lowering artifact 的问题。

## 2. 当前实现断点

本设计必须正面对齐当前代码中的实际断点。

### 2.1 Renderer 仍可能逗号拼接多 outputs

当前 `StepIR.outputs` 仍是 list：

```python
outputs: list[str]
```

Stage 11 renderer 仍可能把多个 outputs 渲染为：

```text
RESULT a: text, b: text SET
```

这已经违反最新 grammar。后续实现必须把 renderer 改成 assert-only / fail-closed：

```text
if renderable command has more than one COMMAND_RESULT:
    fail closed
```

renderer 不得做 composite lowering。

### 2.2 StaticValidator 仍按 result list 解析

当前 StaticValidator 的 result declaration 逻辑仍有多 result item 列表语义。它必须同步迁移：

```text
RESULT / VALUE / RESPONSE clause 中不得接受顶层逗号分隔的多个 COMMAND_RESULT。
```

否则即使 renderer 修复，validator 仍会放过旧 SPL surface。

### 2.3 StaticValidator 对 qualified reference 支持不足

完整 SPL grammar 允许：

```text
REFERENCE := "<REF>" ["*"] NAME "</REF>"
NAME := SIMPLE_NAME | QUALIFIED_NAME | ARRAY_ACCESS | DICT_ACCESS
QUALIFIED_NAME := NAME "." SIMPLE_NAME | NAME "." ARRAY_ACCESS | NAME "." DICT_ACCESS
```

因此读引用可以是：

```text
<REF>a_b.a</REF>
<REF>a_b.b</REF>
```

但 validator 不能只用 simple-name regex 或 `<REF>(\w+)</REF>` 抽取引用。它必须识别：

```text
top-tier name = a_b
field path = ("a",)
```

并通过 structured DATA_TYPE 验证 field path。

### 2.4 Stage 9.5 已有未接入的多输出聚合 helper

当前代码中已存在接近目标语义的 `_normalize_multi_output_steps()`，但 worker-scoped path 曾明确允许：

```text
Multi-output commands render directly.
```

这与本设计冲突。实施时不应新增第二套 lowering，而应重审、修正并迁移现有 helper：

```text
_normalize_multi_output_steps()
-> CompositeOutputPlanner
-> CompositeOutputPlanApplier
```

旧 metadata 只能作为 compatibility payload，不得作为 authority。

### 2.5 ProducerIndex v2 已有 StepVariableRelationPlan authority

ProducerIndex v2 在 relation plan 存在时应以：

```text
StepVariableRelationPlan.producing_relations()
```

为 producer authority，而不是直接扫描 `StepIR.outputs`。因此 composite lowering 必须同步重写 relation plan：

```text
produces(a), produces(b)
-> produces(a_b)
```

不能只改 `StepIR.outputs`。

## 3. 核心原则

```text
Renderable command body:
  has 0 or 1 COMMAND_RESULT

Pre-lowering StepIR / action plan:
  may carry multiple semantic output intents for compatibility

Post-lowering renderable StepIR:
  must have 0 or 1 result binding

Lowering:
  multi-output fields are aggregated into one structured composite result variable
```

关键边界：

```text
Stage 7 identifies output intents and relations.
Stage 9.5 commits deterministic composite lowering.
Stage 11 only renders and asserts invariants.
```

## 4. 聚合变量模型

如果一个 action 原本需要产生多个输出字段：

```text
a: A
b: B
```

则 lowering 后应生成一个聚合变量：

```text
a_b: A_B
```

其中 `A_B` 是结构化类型：

```text
A_B = {
  a: A,
  b: B
}
```

对应 command 只能绑定聚合变量本身：

```text
COMMAND ... RESULT a_b: A_B SET
```

禁止：

```text
COMMAND ... RESULT a: A, b: B SET
```

## 5. 命名规则

聚合变量命名必须可读、稳定、业务化。

推荐：

```text
run_completion_record
source_retrieval_result
request_analysis
draft_quality_assessment
```

不推荐：

```text
tmp_1
result_42
a_b_c_d
worker_main_st_7_result_structured
```

当字段有清晰业务含义时，聚合变量名应表达业务对象，而不是机械拼接所有字段。例如：

```text
assumptions_log + completion_status
```

更适合聚合为：

```text
run_completion_record: RunCompletionRecord
```

## 6. 类型规则与 DEFINE_TYPES

聚合变量必须使用结构化类型。长期推荐 named type：

```text
[DEFINE_TYPES:]
  RunCompletionRecord = {
    assumptions_log: text,
    completion_status: text
  }
[END_TYPES]

[DEFINE_VARIABLES:]
  run_completion_record: RunCompletionRecord
[END_VARIABLES]
```

字段名应保留原输出字段的业务名，字段类型应等于原变量类型。

**已冻结**：`docs/spl_grammar.txt` 已将 `SPL_PROMPT` 更新为：

```text
SPL_PROMPT := PERSONA [AUDIENCE] [CONCEPTS] [CONSTRAINTS] [TYPES] [VARIABLES] [FILES] [APIS] {INSTRUCTION}
```

`[TYPES]` 位于 `[VARIABLES]` 之前，named composite type 无需 forward reference 语义。Renderer 实现时应按此顺序输出 `DEFINE_TYPES` 再输出 `DEFINE_VARIABLES`。

## 7. 原变量声明规则

聚合后，原变量 `a` / `b` 是否从 `DEFINE_VARIABLES` 删除，取决于它们是否仍然是独立的一等变量。

### 7.1 默认规则：删除原 top-level field variables

如果 `a` 和 `b` 只是同一个 action 的多个输出字段，那么聚合后不应继续声明：

```text
a: A
b: B
a_b: A_B
```

否则会形成双 truth source：

```text
a
a_b.a
```

正确状态应是：

```text
a_b: A_B
```

并通过字段引用读取：

```text
<REF>a_b.a</REF>
<REF>a_b.b</REF>
```

### 7.2 例外：保留原变量需要 projection authority

只有存在显式 projection / unpack / alias authority 时，才允许保留原 top-level variables：

```text
a_b.a -> a
a_b.b -> b
```

需要 typed artifact，例如：

```python
FieldProjectionRelation(
    source_variable="a_b",
    field_path=("a",),
    target_variable="a",
)
```

没有这类 authority 时，不能同时保留 top-level `a` / `b`。

## 8. 引用迁移规则

聚合后，所有原来读取 `a` / `b` 的地方都必须迁移。

原引用：

```text
<REF>a</REF>
<REF>b</REF>
```

迁移为：

```text
<REF>a_b.a</REF>
<REF>a_b.b</REF>
```

这不是简单字符串替换。Reference rewrite 必须知道：

```text
top-tier variable
field path
structured type
consumer context
```

短期可以约定 `StepIR.inputs` 在 Stage 9.5 后允许包含 qualified reference string：

```text
a_b.a
```

但必须同时满足：

```text
SymbolTable.lookup("a_b.a") must not be treated as top-level lookup.
Validator validates top-tier "a_b" through symbol table/resources.
Validator validates field path through structured DATA_TYPE.
ProducerIndex never treats "a_b.a" as a producer unless projection relation exists.
```

长期更稳的模型是引入：

```python
VariableReferenceIR(
    top_name="a_b",
    field_path=("a",),
)
```

## 9. 写引用与 field assignment

读引用和写目标必须区分。

MVP 冻结：

```text
<REF>a_b.a</REF> is allowed as a read reference.
<REF>a_b.a</REF> is not allowed as a SET / APPEND target.
```

因此以下都是 invalid：

```text
RESULT <REF>a_b.a</REF> SET
VALUE <REF>a_b.a</REF> SET
RESPONSE <REF>a_b.a</REF> SET
```

MVP 只允许 top-level result target：

```text
RESULT a_b: A_B SET
RESULT <REF>a_b</REF> SET
```

需要新增或使用 diagnostic：

```text
invalid_field_assignment_target
```

## 10. Worker OUTPUTS 规则

MVP 冻结：

```text
Worker OUTPUTS only declare top-level aggregate outputs.
Worker OUTPUTS do not declare qualified references.
```

即：

```text
[OUTPUTS]
  REQUIRED <REF>run_completion_record</REF>
[END_OUTPUTS]
```

不支持：

```text
[OUTPUTS]
  REQUIRED <REF>run_completion_record.assumptions_log</REF>
  REQUIRED <REF>run_completion_record.completion_status</REF>
[END_OUTPUTS]
```

原因是当前 `WorkerOutput`、RequiredOutput IRS、ProducerIndex、SPL Editing target resolver 都主要以 top-level output name 为 contract target。直接允许 qualified output contract 会扩大为 output contract type-system refactor。

原字段可作为 `CompositeOutputPlan.field_mappings` 展示给 feedback/report/UI，但 final RequiredOutput IRS 只检查 top-level aggregate output。

如果产品层必须保留原 required output 语义，需要后续显式引入：

```python
RequiredOutputFulfillmentState(
    output_name="assumptions_log",
    status="produced",
    reason="fulfilled_by_composite_field",
    metadata={
        "composite_variable": "run_completion_record",
        "field_path": ("assumptions_log",),
    },
)
```

这不进入 MVP。

## 11. CALL_API / INVOKE / handoff bindings

`CALL_API` 和 `INVOKE_INSTRUCTION` 不能通过重复调用制造多个结果。

错误：

```text
CALL SomeAPI RESPONSE a: A SET
CALL SomeAPI RESPONSE b: B SET
```

正确：

```text
CALL SomeAPI RESPONSE api_result: APIResult SET
```

然后通过 qualified references 使用字段：

```text
<REF>api_result.a</REF>
<REF>api_result.b</REF>
```

Worker handoff / invoke 还需要特殊处理。当前 handoff producer authority 可能来自 `WorkerHandoffIR.output_bindings`，而不是 `StepIR.outputs`。Lowering 后，handoff output bindings 应解释为 aggregate response field projection authority：

```text
worker_x_result.child_output_a -> parent_a
worker_x_result.child_output_b -> parent_b
```

但 rendered `INVOKE` 仍只能有一个 response target：

```text
INVOKE WorkerX RESPONSE worker_x_result: WorkerXResult SET
```

ProducerIndex 可以继续支持 parent outputs，但必须把 producer kind 标记为：

```text
field_projection
handoff_field_projection
```

不得伪装成 step direct output。

## 12. CompositeOutputPlan

`CompositeOutputPlan` 必须是一等 typed artifact，而不是 metadata dict。

建议模型：

```python
@dataclass(frozen=True)
class CompositeOutputPlan:
    plan_id: str
    worker_id: str
    step_id: str
    command_type: str
    original_output_intents: tuple[OutputIntent, ...]
    composite_variable_name: str
    composite_type_name: str
    field_mappings: tuple[CompositeFieldMapping, ...]
    declaration_rewrites: tuple[DeclarationRewrite, ...]
    reference_rewrites: tuple[ReferenceRewrite, ...]
    worker_output_rewrite: WorkerOutputRewrite | None
    projection_relations: tuple[FieldProjectionRelation, ...]
    naming_authority: str
    source_span_ids: tuple[str, ...]
```

最小 required data：

```text
original_output_intents
composite_variable_name
composite_type_name
field_mappings
declaration_rewrites
reference_rewrites
worker_output_rewrite
relation_plan_rewrite
```

`structured_aggregation` metadata 可以保留为 backward compatibility，但不能作为 authority。

## 13. Stage Boundary

责任分层：

```text
Stage 7:
  identify step/output relations;
  produce StepVariableRelationPlan;
  may produce CompositeOutputPlan candidate;
  must not rewrite global type/symbol/output contracts as final authority.

CompositeOutputPlanner:
  builds CompositeOutputPlan from StepVariableRelationPlan, StepIR.outputs,
  SymbolTable, ResourceRegistryIR, WorkerPlanIR, and source evidence.

Stage 9.5:
  deterministic lowering commit point;
  applies CompositeOutputPlan;
  rewrites WorkerStepPlanIR / ResourceRegistryIR / SymbolTable /
  WorkerPlanIR output contracts / StepVariableRelationPlan;
  guarantees renderable StepIR.outputs <= 1 before Stage 10/11.

Stage 11:
  render/assert only;
  must not lower, aggregate, or rewrite variables.
```

## 14. ProducerIndex Rules

After lowering, relation plan should say:

```text
st7 produces run_completion_record
```

It should not retain:

```text
st7 produces assumptions_log
st7 produces completion_status
```

unless explicit projection relation exists.

ProducerIndex v2 must consume the lowered `StepVariableRelationPlan`. It must not re-register original fields through the legacy `StepIR.outputs` compatibility path.

## 15. StaticValidator Rules

StaticValidator must enforce:

```text
1. RESULT / VALUE / RESPONSE cannot contain top-level comma-separated COMMAND_RESULT list.
2. Qualified references are syntactically valid.
3. Top-tier variable in qualified reference must be declared.
4. Field path must match structured DATA_TYPE.
5. Qualified field reference is read-only in MVP.
6. Qualified field assignment target emits invalid_field_assignment_target.
```

## 16. Renderer Rules

Renderer must be assert-only:

```text
if len(non_empty_outputs) > 1:
    fail closed
```

It must not:

```text
- join outputs with commas;
- invent composite variables;
- rewrite references;
- repair StepIR.outputs;
- infer structured types.
```

## 17. SPL Editing Rules

SPL Editing materializer、stage slice、preview 和 apply 不得生成 multi-result command。

合法：

```text
StepIR.outputs = ("run_completion_record",)
Typed artifact includes CompositeOutputPlan
Rendered preview shows one RESULT target
```

非法：

```text
StepIR.outputs = ("assumptions_log", "completion_status")
rendered_preview = "RESULT assumptions_log: text, completion_status: text SET"
```

SPL Editing apply 只能消费 typed artifact，不得根据 rendered SPL text 做 lowering。

## 18. Fail-Closed Rules

以下情况必须 fail closed 或产生 blocking diagnostic：

```text
- renderable StepIR has more than one output after Stage 9.5;
- renderer sees more than one COMMAND_RESULT;
- StaticValidator accepts multi-result RESULT / VALUE / RESPONSE;
- composite variable name is unreadable or collision-prone;
- composite type is missing fields or field types;
- original top-level field variables remain declared without projection authority;
- references to removed variables are not rewritten;
- qualified reference targets an unknown field;
- qualified field reference is used as write target;
- Worker OUTPUTS contain qualified reference in MVP;
- ProducerIndex registers composite fields as direct producers without projection authority;
- CALL_API / INVOKE duplicate execution to manufacture multiple outputs.
```

## 19. Implementation Sequence

Recommended implementation sequence:

```text
P0 Current behavior locks + grammar regression:
  renderer currently joins StepIR.outputs;
  StaticValidator currently accepts/parses result lists;
  StaticValidator qualified ref support gap;
  worker-scoped Stage 9.5 does not commit composite lowering;
  ProducerIndex relation-plan behavior baseline.
  [DONE] docs/spl_grammar.txt: [TYPES] added to SPL_PROMPT before [VARIABLES];
  [DONE] docs/spl_grammar.txt: duplicate STRUCTURED_TEXT definition removed;
  [DONE] docs/spl_grammar.txt: REQUEST_INPUT DESCRIPTION_WITH_REFERENCE typo fixed.
  Grammar regression tests must prove:
    "RESULT a: text, b: text SET" is invalid;
    "RESPONSE a: text, b: text SET" is invalid;
    "VALUE a: text, b: text SET" is invalid;
    "<REF>aggregate.field</REF>" is valid as read reference;
    "RESULT <REF>aggregate.field</REF> SET" is invalid.

P1 StaticValidator:
  forbid multi COMMAND_RESULT;
  parse qualified references;
  reject field assignment target in MVP.

P2 CompositeOutputPlan model:
  add typed artifact and serialization.

P3 Refactor existing _normalize_multi_output_steps:
  migrate into CompositeOutputPlanner / CompositeOutputPlanApplier;
  wire into worker-scoped Stage 9.5.

P4 Reference rewrite:
  a -> aggregate.a for read contexts;
  forbid aggregate.a write contexts.

P5 Resource / symbol / worker output rewrite:
  add composite type and variable;
  remove/demote original field variables unless projected;
  rewrite Worker OUTPUTS to top-level aggregate.

P6 StepVariableRelationPlan / ProducerIndex:
  rewrite produces(original_field) to produces(composite);
  handle projection relations explicitly.

P7 Renderer assert-only:
  fail closed on multi-output renderable command.

P8 SPL Editing:
  enforce the same typed artifact invariant.

P9 E2E:
  no rendered multi RESULT;
  qualified read refs valid;
  source/output diagnostics stable;
  API/INVOKE aggregate response semantics stable.
```

## 20. Final Decision

```text
SPL command remains single-result.
Multi-field output is represented as one readable structured composite variable.
Original top-level field variables are removed unless explicit projection authority keeps them.
Read references migrate to qualified references.
Field assignment and qualified Worker OUTPUTS are out of MVP.
Stage 9.5 is the deterministic lowering commit point.
Renderer and validator enforce the single-result surface.
```
