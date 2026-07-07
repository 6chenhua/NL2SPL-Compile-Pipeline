# SPL Composite Output Lowering 实施计划

本文档严格基于 `docs/design/spl_single_command_result_composite_output_lowering_design_zh.md` 制定。
实施目标：在 Stage 9.5 建立确定性 composite lowering commit boundary，使渲染层输出的每个
`COMMAND_RESULT` 都只有一个绑定目标，消除 renderer 逗号拼接多 outputs 的非法行为。

**适用范围**：`GENERAL_COMMAND`、`CALL_API`、`INVOKE_INSTRUCTION`、`REQUEST_INPUT` 四类
command body 的 RESULT / RESPONSE / VALUE 子句。Worker OUTPUTS 的 qualified reference
支持不在本 MVP 范围内。

---

## 1. 总体目标

最终系统应形成以下职责链路：

```text
Stage 7 (step_extractor)
  -> identifies output intents per step
  -> produces StepVariableRelationPlan (produces/consumes per variable)
  -> may suggest CompositeOutputPlan candidate (不做 final rewrite)

CompositeOutputPlanner  [新组件，Stage 9.5 内部调用]
  -> 读取 StepVariableRelationPlan + StepIR.outputs + SymbolTable
  -> 构建 CompositeOutputPlan typed artifact
  -> 不推断 / 不调用 LLM / 不依赖 metadata dict 作为 authority

Stage 9.5 (IRNormalizer / CompositeOutputPlanApplier)  [唯一 lowering commit point]
  -> 应用 CompositeOutputPlan
  -> 重写 StepIR.outputs -> [composite_name]
  -> 重写 StepVariableRelationPlan: produces(a)+produces(b) -> produces(a_b)
  -> 重写 ResourceRegistryIR: 删除原字段变量，添加 composite 变量和类型
  -> 重写 WorkerPlanIR output_contract: 原字段 -> composite
  -> 重写 SymbolTable
  -> 重写 step.inputs 中的原字段引用 -> composite qualified ref string
  -> 保证 renderable StepIR.outputs <= 1

StaticValidator  [守门 + 格式校验]
  -> 拒绝顶层逗号分隔多 COMMAND_RESULT
  -> 验证 qualified reference 语法合法性
  -> 拒绝 qualified reference 作为 SET/APPEND 目标（MVP）
  -> validate_variables 支持 qualified ref top-tier lookup

Stage 11 Renderer  [仅 render + assert]
  -> assert renderable StepIR.outputs <= 1，否则 fail closed
  -> 不做 lowering / 聚合 / 类型推断
  -> _result_clause 不拼接逗号分隔多输出

ProducerIndex v2
  -> 以 StepVariableRelationPlan.producing_relations() 为权威
  -> 不通过 StepIR.outputs 兼容路径重新注册已被聚合的原字段
```

---

## 2. 全局硬性原则

所有阶段必须遵守：

1. **唯一 lowering commit point**：`CompositeOutputPlanApplier` 在 Stage 9.5 是唯一做聚合
   rewrite 的场所；Renderer（Stage 11）、SPL Editing materializer、StaticValidator 均不做
   composite lowering。
2. **CompositeOutputPlan 是一等 typed artifact**：不得用 `step.metadata["structured_aggregation"]`
   dict 作为 authority；旧 metadata 只作为 backward compatibility payload 保留，直到清理完毕。
3. **relation plan 是 ProducerIndex authority**：ProducerIndex v2 必须通过
   `StepVariableRelationPlan.producing_relations()` 获取 producer 关系，不得回退到直接扫描
   `StepIR.outputs`。
4. **原字段变量默认删除**：聚合后原 top-level field variables (`a`, `b`) 必须从
   `ResourceRegistryIR.variables`、`SymbolTable`、`WorkerPlanIR.output_contract` 中删除，
   除非有显式 `FieldProjectionRelation` artifact 授权保留。
5. **qualified reference 在 MVP 只读**：`<REF>a_b.a</REF>` 不允许作为 `SET`/`APPEND` 目标；
   违反时必须产生 `invalid_field_assignment_target` diagnostic，fail closed。
6. **Worker OUTPUTS 只声明 top-level aggregate**：不支持 `<REF>a_b.field</REF>` 作为
   OUTPUTS 中的声明目标（MVP 范围外）。
7. **Renderer fail-closed**：`_result_clause` 检测到 `len(non_empty_outputs) > 1` 时必须
   抛出异常，不得静默拼接逗号。
8. **无 LLM 调用**：`CompositeOutputPlanner` 和 `CompositeOutputPlanApplier` 是纯确定性
   组件，不调用任何 LLM。
9. **不新增第二套 lowering**：现有 `_normalize_multi_output_steps()` 必须被迁移/重写为
   `CompositeOutputPlanner` + `CompositeOutputPlanApplier`，不得并列两套聚合逻辑。
10. **DEFINE_TYPES 顺序已冻结**：`docs/spl_grammar.txt` 已将 `[TYPES]` 放在 `[VARIABLES]`
    之前，Renderer 输出时 `DEFINE_TYPES` 必须先于 `DEFINE_VARIABLES`。

---

## 3. LLM / Rule-based 决策约束

本计划中默认不允许新增任何 rule-based semantic fallback。

允许的确定性逻辑仅限：

- 从 `StepVariableRelationPlan.producing_relations()` 读取已有结构化关系
- 对 `StepIR.outputs` 做 `len()` presence check
- 从 `SymbolTable.variables` 读取已声明变量的 `data_type`
- 正则解析 `<REF>top.field</REF>` 中的 top-tier name 和 field path
- 对 `ResourceRegistryIR` / `SymbolTable` 做 presence check 和 rewrite
- 通过 `CompositeNamePolicy` 校验命名（见 Phase 3 设计要求）

以下行为必须在实施前向 PM 确认：

1. 修改 Stage 7 LLM prompt/schema（如需让 LLM 输出 `CompositeOutputPlan` 候选）
2. 修改 `DEFINE_TYPES` 的 renderer 输出顺序（已在 grammar 层冻结，renderer 实现时需对齐）
3. 保留任何旧 `structured_aggregation` metadata dict 作为 authority 的兼容路径
4. 修改 ProducerIndex 注册逻辑中的 legacy `StepIR.outputs` 扫描路径
5. 在 SPL Editing apply 中基于 rendered SPL text 做任何 lowering

如果实现中出现"为了兼容先用 metadata dict 兜底"的倾向，应停止并提交设计确认，不允许直接编码。

---

## 4. Phase 0：基线锁定 + Grammar Regression Tests

### 4.1 目标

在改任何生产代码之前，证明当前 `_normalize_multi_output_steps()` 的确未被
`worker_scoped.py` 调用（注释 "Multi-output commands render directly" 已确认），
Renderer 当前确实用逗号拼接多 outputs，StaticValidator 当前确实接受多结果列表，
并建立 grammar regression 测试组锁住本次变更的核心 invariants。

**前置条件**：grammar 层三处修复已完成（SPL_PROMPT 含 [TYPES]，STRUCTURED_TEXT 无重复，
REQUEST_INPUT typo 修正）——已在上次 review 中完成。

### 4.2 可编辑范围

允许新增：

```text
tests/unit/test_composite_output_current_behavior.py
  [现状快照测试：不使用 xfail，断言当前 buggy 行为确实存在]

tests/unit/test_composite_output_contract_regression.py
  [未来合同测试：使用 pytest.mark.xfail(strict=True)，写最终期望]
```

允许修改：

```text
无（Phase 0 不改生产代码）
```

### 4.3 禁止改动

Phase 0 禁止修改：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/validator/static_validator.py
src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/
```

### 4.4 设计要求

**必须拆成两个独立测试文件**，不得混用：

**`test_composite_output_current_behavior.py`**（不使用 `xfail`）：

```text
- 断言 StaticValidator 对 "RESULT a: text, b: text SET" 不产生 error（当前 buggy 行为）
- 断言 StaticValidator 对 "RESPONSE a: text, b: text SET" 不产生 error
- 断言 StaticValidator 对 "VALUE a: text, b: text SET" 不产生 error
- 断言 StaticValidator 对 <REF>agg.field</REF> 产生 warning（当前 buggy 行为）
- 断言 renderer._result_clause("RESULT", ["a", "b"]) 返回包含逗号的字符串
- 断言 _normalize_multi_output_steps() 未被 normalize_worker_scoped() 调用

所有断言必须 pass，证明旧行为确实存在。
```

**`test_composite_output_contract_regression.py`**（使用 `pytest.mark.xfail(strict=True)`）：

```text
- 期望 StaticValidator 对 "RESULT a: text, b: text SET" 产生 error（Phase 1 后 pass）
- 期望 StaticValidator 对 "RESPONSE a: text, b: text SET" 产生 error
- 期望 StaticValidator 对 "VALUE a: text, b: text SET" 产生 error
- 期望 StaticValidator 对 <REF>agg.field</REF> 不产生 warning
- 期望 StaticValidator 对 "RESULT <REF>agg.field</REF> SET" 产生 invalid_field_assignment_target error
- 期望 renderer._result_clause("RESULT", ["a", "b"]) 抛出 ValueError

Phase 1 完成后，移除所有 xfail(strict=True) 标注，全部 pass。
```

### 4.5 测试计划

新增单元测试必须覆盖（按文件分）：

`test_composite_output_current_behavior.py`：

1. `StaticValidator` 对 `"RESULT a: text, b: text SET"` 不产生 error（快照 pass）
2. `StaticValidator` 对 `"RESPONSE a: text, b: text SET"` 不产生 error（快照 pass）
3. `StaticValidator` 对 `"VALUE a: text, b: text SET"` 不产生 error（快照 pass）
4. `StaticValidator` 对 `<REF>agg.field</REF>` 产生 warning（快照 pass）
5. `ClauseBuilderMixin._result_clause("RESULT", ["a", "b"])` 返回包含逗号（快照 pass）
6. `_normalize_multi_output_steps()` 未被 `normalize_worker_scoped()` 调用（快照 pass）

`test_composite_output_contract_regression.py`（全部 `xfail(strict=True)`）：

7. `StaticValidator` 对 `"RESULT a: text, b: text SET"` 产生 error（当前 xfail）
8. `StaticValidator` 对 `"RESPONSE a: text, b: text SET"` 产生 error（当前 xfail）
9. `StaticValidator` 对 `"VALUE a: text, b: text SET"` 产生 error（当前 xfail）
10. `StaticValidator` 对 `<REF>agg.field</REF>` 不产生 warning（当前 xfail）
11. `StaticValidator` 对 `"RESULT <REF>agg.field</REF> SET"` 产生 `invalid_field_assignment_target`（当前 xfail）
12. `_result_clause("RESULT", ["a", "b"])` 抛出 `ValueError`（当前 xfail）

### 4.6 验收标准

Phase 0 通过条件：

1. `test_composite_output_current_behavior.py` 中所有测试 pass（无 xfail）。
2. `test_composite_output_contract_regression.py` 中所有测试 xfail（strict=True）。
3. 未改动任何生产代码。
4. 全量已有单测通过，无新增 skip / xfail（Phase 0 两个新文件除外）。

### 4.7 PM 审核清单

审核时必须检查：

1. 两个测试文件是否有明确文件头注释说明各自用途。
2. `test_composite_output_current_behavior.py` 是否 **不含任何** `xfail`。
3. `test_composite_output_contract_regression.py` 是否全部使用 `xfail(strict=True)` 而非普通 `xfail`。
4. 是否有任何生产代码被修改。

---

## 5. Phase 1：StaticValidator 强化

### 5.1 目标

StaticValidator 必须成为 grammar surface 的守门人：
- 拒绝顶层逗号分隔多 COMMAND_RESULT（`RESULT a: text, b: text SET`）
- 正确识别 qualified reference（`<REF>a_b.field</REF>`）为合法语法
- 拒绝 qualified reference 作为 SET/APPEND 目标（`RESULT <REF>a_b.field</REF> SET`）
- 扩展 `ValidationError` 增加 `diagnostic_code` 字段（typed diagnostic contract）
- `validate_variables()` 中的 ref 抽取升级为支持 qualified name

完成后 Phase 0 的 `test_composite_output_contract_regression.py` 中所有 `xfail(strict=True)` 标注必须移除，全部翻转为正式通过。

### 5.2 可编辑范围

允许新增：

```text
src/nl2spl/validator/
  qualified_ref_parser.py   [新增：解析 <REF>top.field</REF>，返回 (top_name, field_path)]
```

允许修改：

```text
src/nl2spl/validator/static_validator.py
  [新增 ValidationError.diagnostic_code 字段]
  [新增 _validate_result_clauses / _validate_ref_tags / _validate_field_assignment_targets]
  [修改 validate_variables() 支持 qualified ref]
tests/unit/test_static_validator.py
tests/unit/test_composite_output_current_behavior.py
  [Phase 0 proof-of-bug 文件，Phase 1 完成后必须退役：
   重命名为 test_composite_output_previous_behavior_retired.py
   并将断言翻转为验证旧行为已消失，不得保留断言旧 buggy 行为仍存在的长期 gate]
tests/unit/test_composite_output_contract_regression.py  [移除 xfail，翻转断言]
```

### 5.3 禁止改动

Phase 1 禁止修改：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/
```

### 5.4 设计要求

**`ValidationError`** 必须扩展 `diagnostic_code` 字段：

```python
@dataclass
class ValidationError:
    line: int
    column: int
    message: str
    severity: str = "error"
    diagnostic_code: str | None = None  # 新增：typed diagnostic contract
```

存量 `ValidationError` 构造调用默认 `diagnostic_code=None`，不破坏现有测试。

**`qualified_ref_parser.py`** 输入必须是：

```text
ref_text: str   # 例如 "a_b.field" 或 "<REF>a_b.field</REF>"
```

应表达：

```text
parse_qualified_ref(ref_text) -> tuple[str, tuple[str, ...]] | None
  # 返回 (top_name, field_path) 或 None（非 qualified）
  # 例：parse_qualified_ref("a_b.field") -> ("a_b", ("field",))
  # 例：parse_qualified_ref("a_b") -> None（无 field path，为 simple name）
  # 例：parse_qualified_ref("a_b.x.y") -> ("a_b", ("x", "y"))
```

不得包含：

```text
- LLM 调用
- symbol table 或 resource registry 依赖（Phase 1 的 parser 是纯语法层）
```

**`StaticValidator`** 必须新增或修改：

```text
1. _validate_result_clauses(lines) -> list[ValidationError]
   - 提取每行的 RESULT/RESPONSE/VALUE ... SET 子句
   - 调用 _split_result_items() 后检查顶层 item 数量
   - 如果 item 数量 > 1，emit ValidationError(
       severity="error",
       message="Multi COMMAND_RESULT is not allowed: use one structured composite variable",
       diagnostic_code="multi_command_result",
     )

2. _validate_ref_tags(stripped_line, line_idx) -> list[ValidationError]
   - 替换当前的 simple-name-only regex check
   - 调用 qualified_ref_parser.parse_qualified_ref() 验证语法
   - <REF>top.field</REF> -> 合法，不 emit warning
   - <REF>with spaces</REF> -> 仍 emit warning

3. _validate_field_assignment_targets(lines) -> list[ValidationError]
   - 扫描 RESULT/RESPONSE/VALUE ... SET 子句中的 COMMAND_RESULT
   - 如果 item 以 <REF>*.*</REF> 形式出现（qualified ref 作为 write target），emit
     ValidationError(
       severity="error",
       message="Qualified reference cannot be used as SET/APPEND target in MVP",
       diagnostic_code="invalid_field_assignment_target",
     )

4. validate_variables() 中 var_references 抽取：
   - 使用 qualified_ref_parser 分离 top_name 和 field_path
   - symbol table lookup 只针对 top_name
   - field_path 存在时，不单独 emit "Undeclared variable"（field-path validation 在 Phase 1b）
```

**Phase 1 仅做语法层 qualified ref 校验，不做 field-path 类型校验**（延迟到 Phase 1b）。

### 5.5 测试计划

新增单元测试必须覆盖：

1. `"RESULT a: text, b: text SET"` -> `ValidationError(severity="error", diagnostic_code="multi_command_result")` 存在
2. `"RESPONSE a: text, b: text SET"` -> 同上
3. `"VALUE a: text, b: text SET"` -> 同上
4. `"RESULT agg: AggType SET"` -> 无 error（单 COMMAND_RESULT）
5. `"<REF>a_b.field</REF>"` 在 DESCRIPTION 中 -> 无 warning（qualified ref 语法合法）
6. `"<REF>a_b</REF>"` 在 DESCRIPTION 中 -> 无 warning（simple name 仍合法）
7. `"RESULT <REF>a_b.field</REF> SET"` -> `ValidationError(diagnostic_code="invalid_field_assignment_target")`
8. `"RESULT <REF>agg</REF> SET"` -> 无 error（top-level ref 作为 write target 合法）
9. `parse_qualified_ref("a_b.x")` -> `("a_b", ("x",))`
10. `parse_qualified_ref("a_b.x.y")` -> `("a_b", ("x", "y"))`
11. `parse_qualified_ref("a_b")` -> `None`
12. `parse_qualified_ref("")` -> `None`
13. `ValidationError(line=0, column=0, message="x")` -> `diagnostic_code is None`（默认值）
14. 存量 `test_static_validator.py` 全量通过（`ValidationError` 扩展向后兼容）

### 5.6 验收标准

Phase 1 通过条件：

1. `ValidationError.diagnostic_code` 字段存在，默认 `None`，存量测试全量通过。
2. StaticValidator 对三类 multi-result clause 全部 emit `diagnostic_code="multi_command_result"`。
3. StaticValidator 不再对合法 qualified ref 产生 warning。
4. `invalid_field_assignment_target` diagnostic_code 对 qualified write target 正确触发。
5. `parse_qualified_ref` 所有单测通过。
6. `test_composite_output_contract_regression.py` 中所有 `xfail` 已移除，全部 pass。
7. `test_composite_output_current_behavior.py` **已退役**：
   - 重命名为 `test_composite_output_previous_behavior_retired.py`
   - 所有断言已翻转（验证旧 buggy 行为已消失，而非仍存在）
   - 不得保留任何断言旧行为仍存在的长期 pytest gate
8. 全量已有单测通过，无新增 skip / xfail。

### 5.7 PM 审核清单

审核时必须检查：

1. `ValidationError` 是否新增 `diagnostic_code: str | None = None` 字段。
2. `invalid_field_assignment_target` 和 `multi_command_result` 是否作为 `diagnostic_code` 字符串常量（非 magic string 散落）。
3. `_validate_result_clauses` 是否用 `_split_result_items()` 而不是 naive 逗号 split。
4. `_validate_ref_tags` 是否完全替换旧的 `r"^[a-zA-Z_][a-zA-Z0-9_]*$"` 检查。
5. `validate_variables()` 的 ref 抽取是否支持 qualified name（top_name lookup）。
6. `test_composite_output_current_behavior.py` 是否已退役（重命名为 `_retired.py` 且断言已翻转）；
   **不允许**保留任何断言旧 buggy 行为仍存在的长期 pass gate。
7. 是否有任何 stage 9.5 / renderer 生产代码被修改。

---

## 5b. Phase 1b：Typed Qualified Reference Field-Path Validation

### 5b.1 目标

Phase 1 只做语法解析，Phase 1b 补上 **类型语义验证**：StaticValidator 能够校验 `<REF>top.field</REF>` 中 `field` 是否真的存在于 `top` 的 structured type 声明中。

这对齐设计文档 StaticValidator Rule 4（`field path must match structured DATA_TYPE`）。

### 5b.2 可编辑范围

允许新增：

```text
src/nl2spl/validator/
  type_field_validator.py   [新增：解析 DEFINE_TYPES / DEFINE_VARIABLES，验证 field path]

tests/unit/
  test_type_field_validator.py  [新增]
```

允许修改：

```text
src/nl2spl/validator/static_validator.py
  [在 validate_variables() 中调用 type_field_validator]
tests/unit/test_static_validator.py
```

### 5b.3 禁止改动

Phase 1b 禁止修改：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/
```

### 5b.4 设计要求

**`type_field_validator.py`** 必须实现：

```python
def validate_qualified_ref_field(
    top_name: str,
    field_path: tuple[str, ...],
    spl_text: str,          # 完整 SPL 文本，用于提取 DEFINE_TYPES / DEFINE_VARIABLES
) -> list[ValidationError]:
    """
    验证规则：
    1. top_name 必须在 DEFINE_VARIABLES 中声明
    2. top_name 的 data_type 必须是 structured type（{ ... } 或 named structured type）
    3. field_path[0] 必须存在于该 structured type 中
    4. 如果 field_path 有多层，递归验证每层（MVP 只验证第一层即可）
    """
```

验证要求：

```text
- 解析 [DEFINE_TYPES:] ... [END_TYPES] 提取所有 named type 定义
- 解析 [DEFINE_VARIABLES:] ... [END_VARIABLES] 提取 var -> type 映射
- 对 <REF>top.field</REF>：
    top 未声明 -> error, diagnostic_code="undeclared_top_tier_variable"
    top 类型非 structured -> error, diagnostic_code="not_structured_type"
    field 不在 type 定义中 -> error, diagnostic_code="unknown_field_in_structured_type"
```

不得包含：

```text
- LLM 调用
- 访问 SymbolTable（只解析 SPL 文本静态结构）
```

### 5b.5 测试计划

新增单元测试必须覆盖：

1. `<REF>run_completion_record.assumptions_log</REF>` 合法（type 含此字段）-> 无 error
2. `<REF>run_completion_record.unknown</REF>` -> `unknown_field_in_structured_type` error
3. `<REF>unknown_record.assumptions_log</REF>` -> `undeclared_top_tier_variable` error
4. `<REF>plain_text_var.field</REF>`（plain_text_var 类型为 `text`）-> `not_structured_type` error
5. named type 引用场景：DEFINE_TYPES 中 `RunCompletionRecord = { ... }` 正确解析
6. inline structured type 场景：`var: { a: text, b: text }` 直接内嵌声明正确解析

### 5b.6 验收标准

Phase 1b 通过条件：

1. `type_field_validator.validate_qualified_ref_field` 通过上述 6 个测试场景。
2. `StaticValidator` 在 `validate_variables()` 中调用 field-path 验证。
3. 三类 diagnostic_code（`undeclared_top_tier_variable`、`not_structured_type`、`unknown_field_in_structured_type`）有独立单测。
4. 全量已有单测通过，无新增 skip / xfail。

### 5b.7 PM 审核清单

审核时必须检查：

1. field-path 验证是否覆盖 named type（DEFINE_TYPES 引用）和 inline structured type 两种形式。
2. `diagnostic_code` 是否是常量而非散落 magic string。
3. Phase 1b 是否改动了任何 stage 9.5 / renderer 生产代码（禁止）。
4. 是否在 E2E 验收场景 2（qualified reference 读取合法）中增加了 field-path 合法测试。

---

## 6. Phase 2：CompositeOutputPlan Typed Artifact

### 6.1 目标

引入 `CompositeOutputPlan` 作为一等 typed artifact（`frozen=True` dataclass），完整表达
从多字段输出到聚合变量的一次 lowering 决策，包括所有 rewrite 需求。

这是 Phase 3 实施 `CompositeOutputPlanner` 和 `CompositeOutputPlanApplier` 的前置数据模型。

### 6.2 可编辑范围

允许新增：

```text
src/nl2spl/ir/
  composite_output_plan_ir.py   [新增：CompositeOutputPlan 及配套 dataclass]
```

允许修改：

```text
src/nl2spl/ir/__init__.py       [导出新 IR 类型]
tests/unit/ir/
  test_composite_output_plan_ir.py  [新增]
```

### 6.3 禁止改动

Phase 2 禁止修改：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/compiler/producer_index.py
src/nl2spl/validator/static_validator.py
src/nl2spl/ir/step_ir.py
src/nl2spl/ir/step_variable_relation_ir.py
```

### 6.4 设计要求

**`composite_output_plan_ir.py`** 必须定义以下 dataclass（均 `frozen=True`）：

```python
@dataclass(frozen=True)
class OutputIntent:
    variable_name: str
    data_type: str
    source_span_ids: tuple[str, ...]

@dataclass(frozen=True)
class CompositeFieldMapping:
    original_field_name: str
    original_data_type: str
    composite_field_name: str   # 通常与 original_field_name 相同

@dataclass(frozen=True)
class DeclarationRewrite:
    # 从 ResourceRegistryIR 删除的原变量名
    remove_variable_name: str

@dataclass(frozen=True)
class ReferenceRewrite:
    # step.inputs 中的原字段名 -> composite qualified ref string
    original_ref: str           # e.g. "a"
    rewritten_ref: str          # e.g. "a_b.a"
    top_name: str               # e.g. "a_b"
    field_path: tuple[str, ...]  # e.g. ("a",)

@dataclass(frozen=True)
class WorkerOutputRewrite:
    remove_output_names: tuple[str, ...]
    add_output_name: str
    add_output_type: str
    required: bool

@dataclass(frozen=True)
class FieldProjectionRelation:
    source_variable: str
    field_path: tuple[str, ...]
    target_variable: str

@dataclass(frozen=True)
class CompositeOutputPlan:
    plan_id: str                              # 唯一 ID，格式 "cop_{worker_id}_{step_id}"
    worker_id: str
    step_id: str
    command_type: str                         # CommandType 值
    original_output_intents: tuple[OutputIntent, ...]
    composite_variable_name: str
    composite_type_name: str
    field_mappings: tuple[CompositeFieldMapping, ...]
    declaration_rewrites: tuple[DeclarationRewrite, ...]
    reference_rewrites: tuple[ReferenceRewrite, ...]
    worker_output_rewrite: WorkerOutputRewrite | None
    projection_relations: tuple[FieldProjectionRelation, ...]
    naming_authority: str                     # 记录名字来源，用于 audit
    source_span_ids: tuple[str, ...]
    schema_version: str = "composite_output_plan.v1"  # payload 版本标识，便于迁移
```

`CompositeOutputPlan` 必须实现：

```text
to_payload() -> dict[str, object]
  # 必须包含 schema_version 字段
from_payload(cls, payload) -> CompositeOutputPlan
  # 必须读取并校验 schema_version
```

不得包含：

```text
- 任何可变字段（必须 frozen=True）
- metadata dict 作为权威字段
- LLM 调用或 symbol table 依赖
```

> **MVP frozen**：对于普通 multi-output step，`projection_relations` 必须为空 tuple `()`。
> 只有 handoff-specific 场景才允许非空 projection_relations，且必须在 Gate A 时书面决策是否消费。

### 6.5 测试计划

新增单元测试必须覆盖：

1. `CompositeOutputPlan` 构造成功（所有字段赋值正确）
2. `to_payload()` -> `from_payload()` 往返不丢失数据，包含 `schema_version`
3. `from_payload()` 遇到未知 `schema_version` 时不静默接受（emit warning 或 raise）
4. `frozen=True` 不允许原地修改（期望 `FrozenInstanceError`）
5. `plan_id` 格式符合 `"cop_{worker_id}_{step_id}"` 约定
6. `WorkerOutputRewrite` 为 `None` 时 `to_payload` 序列化正确
7. 普通 composite step 的 `projection_relations == ()`（MVP 冻结验证）

### 6.6 验收标准

Phase 2 通过条件：

1. `composite_output_plan_ir.py` 包含所有指定 dataclass，无语法错误。
2. `to_payload` / `from_payload` 往返测试通过，含 `schema_version`。
3. `frozen=True` 测试通过。
4. 普通 composite step 的 `projection_relations` MVP 冻结验证通过。
5. 全量已有单测通过，无新增 skip / xfail。

### 6.7 PM 审核清单

审核时必须检查：

1. 所有 dataclass 是否 `frozen=True`。
2. `CompositeOutputPlan` 字段名是否与设计文档 Section 12 完全一致。
3. `to_payload` / `from_payload` 是否包含 `schema_version` 字段。
4. `from_payload` 是否验证 `schema_version`（不静默接受未知版本）。
5. 是否有任何非 IR 层文件被修改。

---

## 7. Phase 3：CompositeOutputPlanner + CompositeOutputPlanApplier

### 7.1 目标

将现有 `normalization.py` 中的 `_normalize_multi_output_steps()` 迁移重写为两个独立组件：

- **`CompositeOutputPlanner`**：读取 StepIR、StepVariableRelationPlan、SymbolTable，
  构建 `CompositeOutputPlan` typed artifact
- **`CompositeOutputPlanApplier`**：读取 `CompositeOutputPlan`，确定性地 rewrite 所有 IR

在 `worker_scoped.py` 的 `normalize_worker_scoped()` 中接入，替换被注释掉的
"Multi-output commands render directly" 路径，成为 Stage 9.5 的确定性 lowering commit。

> **重要**：Phase 3 完成后，`_normalize_multi_output_steps()` 的原始实现必须被删除或标注为
> `# DEPRECATED: remove after Phase 3`，不得保留两套并行 lowering。

### 7.2 可编辑范围

允许新增：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/
  composite_output_planner.py    [新增：CompositeOutputPlanner]
  composite_output_applier.py    [新增：CompositeOutputPlanApplier]

tests/unit/pipeline/
  test_composite_output_planner.py
  test_composite_output_applier.py
```

允许修改：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py
  [删除 _normalize_multi_output_steps，保留其他 helper]
  [_aggregate_result_name / _aggregate_type_name 迁移到 planner 或标注 deprecated]

src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py
  [接入 CompositeOutputPlanner + CompositeOutputPlanApplier]
  [删除 "Multi-output commands render directly" 注释及相关绕过逻辑]

src/nl2spl/pipeline/stages/stage9_5_normalizer/__init__.py
```

### 7.3 禁止改动

Phase 3 禁止修改：

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/validator/static_validator.py
src/nl2spl/compiler/producer_index.py
src/nl2spl/ir/step_ir.py
src/nl2spl/ir/step_variable_relation_ir.py
```

### 7.4 设计要求

**`CompositeOutputPlanner`** 输入必须是：

```text
steps: list[StepIR]
symbol_table: SymbolTable
relation_plan: StepVariableRelationPlan
worker_id: str
worker_plan: WorkerPlanIR
```

应返回：

```text
list[CompositeOutputPlan]   # 一个 step 最多产生一个 plan
```

**命名规则（CompositeNamePolicy gate）**：

`CompositeOutputPlanner` 必须内置 `CompositeNamePolicy` 校验，命名流程如下：

```text
1. 候选名来源（按优先级）：
   a. 从 original_output_intents 的字段名生成确定性可读候选
      （例：assumptions_log + completion_status -> assumptions_log_completion_status）
   b. 如果无法生成可读候选，fail closed 并产生 blocking diagnostic：
      diagnostic_code="composite_name_policy_violation"
      不得静默降级到机械名

2. 候选名必须通过 CompositeNamePolicy.validate_variable_name(name)：
   - 禁止模式（正则拒绝）：
       r"^tmp_\d"
       r"^result_\d"
       r"^var_[0-9a-f]+"
       r".*_structured$"
       r".*_st_\d+"
       r".*step.*result"
   - 必须满足：至少 2 个 word segment，每段至少 2 字符

3. metadata 中的旧聚合提示（如 structured_aggregation / composite_output_debug）
   只能作为 debug / compatibility payload 保留，不得作为 naming authority。
   即使 metadata 中出现看似合法的业务名，也不能覆盖由 output intents
   与 CompositeNamePolicy 共同确定的候选名。

composite_type_name 规则同上（CompositeNamePolicy.validate_type_name）：
  优先从 composite_variable_name 推导
  （如 AssumptionsLogCompletionStatus from assumptions_log_completion_status）
  禁止 *_type$、*_structured_type$ 等机械后缀模式
```

不得：

```text
- 调用 LLM
- 访问 ResourceRegistryIR（由 Applier 负责）
- 直接修改 StepIR（只读）
- 在 policy 校验失败时静默使用机械 fallback（必须 fail closed）
```

**`CompositeOutputPlanApplier`** 输入必须是：

```text
plan: CompositeOutputPlan
steps: list[StepIR]           # 可变，apply 后 step.outputs 变为 [composite_name]
resources: ResourceRegistryIR  # 可变，apply 后含 composite 变量/类型，删除原字段变量
symbol_table: SymbolTable      # 可变
worker_plan: WorkerPlanIR      # 可变，output_contract 重写
relation_plan: StepVariableRelationPlan  # 返回新 plan，不可变
```

应返回：

```text
(
  new_relation_plan: StepVariableRelationPlan,  # produces(a)+produces(b)->produces(a_b)
  warnings: list[str],
)
```

`apply()` 执行以下 rewrites，缺一不可：

```text
1. step.outputs = [plan.composite_variable_name]
2. step.inputs: 将 original_ref -> rewritten_ref（qualified ref string，如 "a_b.a"）
3. ResourceRegistryIR.variables: 删除原字段变量，添加 composite 变量
4. ResourceRegistryIR.types: 添加 composite 类型
5. SymbolTable: 删除原字段声明，添加 composite 声明
6. WorkerPlanIR output_contract: 用 WorkerOutputRewrite 替换原字段
7. StepVariableRelationPlan: 生成新 plan，produces(original_fields) -> produces(composite)
```

**`normalize_worker_scoped()` 接入点**：

```python
# 替换原来的注释：
# "5. Multi-output commands render directly. Keep only the narrow cleanup..."

# 新逻辑：
for worker_id, steps in worker_step_plan.worker_steps.items():
    errors.extend(self._validate_command_shapes(worker_id, steps))
    plans = CompositeOutputPlanner().build_plans(
        steps, symbol_table, relation_plan, worker_id, worker_plan
    )
    for plan in plans:
        new_relation_plan, plan_warnings = CompositeOutputPlanApplier().apply(
            plan, steps, resources, symbol_table, worker_plan, relation_plan
        )
        relation_plan = new_relation_plan
        warnings.extend(plan_warnings)
```

### 7.5 测试计划

新增单元测试必须覆盖：

1. **Planner**：单 output step -> 无 plan 产生
2. **Planner**：双 output step -> 产生一个 `CompositeOutputPlan`，字段正确
3. **Planner**：metadata 含机械名 `main_st_7_result_structured` -> `composite_name_policy_violation` blocking diagnostic，不产生 plan
4. **Planner**：metadata 含合法业务名 `run_completion_record` -> 不作为 authority，
   仍从 output intents 生成 `assumptions_log_completion_status`
5. **Planner**：从字段语义生成可读候选，通过 policy
6. **Planner**：无 metadata 且字段语义不足时 -> fail closed，产生 blocking diagnostic
7. **Planner**：无 relation_plan 时降级使用 `StepIR.outputs`（不崩溃）
8. **Planner**：普通 composite step 的 `CompositeOutputPlan.projection_relations == ()`
5. **Applier**：`step.outputs` 变为 `[composite_name]`
6. **Applier**：`step.inputs` 中 `"a"` -> `"a_b.a"`（qualified ref rewrite）
7. **Applier**：`ResourceRegistryIR` 删除原字段变量，添加 composite 变量
8. **Applier**：`ResourceRegistryIR.types` 添加 composite 类型
9. **Applier**：`SymbolTable` 中原字段变量被删除
10. **Applier**：`WorkerPlanIR.output_contract` 原字段被 composite 替换
11. **Applier**：新 `StepVariableRelationPlan.producing_relations()` 只含 composite，不含原字段
12. **集成**：`normalize_worker_scoped()` 完整调用链 E2E，输入双 output step，
    输出 `StepIR.outputs == [composite_name]`

### 7.6 验收标准

Phase 3 通过条件：

1. `_normalize_multi_output_steps()` 从 normalization.py 删除或标注为废弃。
2. `worker_scoped.py` 的 "Multi-output commands render directly" 注释及绕过逻辑删除。
3. `CompositeOutputPlanner` + `CompositeOutputPlanApplier` 新增测试全部通过。
4. `normalize_worker_scoped()` 集成测试通过。
5. 全量已有单测通过（尤其 `test_worker_handoff_structured_unpack_regression.py`）。
6. 无新增 skip / xfail。

### 7.7 PM 审核清单

审核时必须检查：

1. `_normalize_multi_output_steps()` 是否已删除或有 `# DEPRECATED` 标注。
2. `worker_scoped.py` 中是否仍存在 "Multi-output commands render directly" 相关代码。
3. `CompositeOutputPlanApplier.apply()` 的 7 项 rewrite 是否全部实现（逐项核查）。
4. `apply()` 是否返回新的不可变 `StepVariableRelationPlan`（而非原地修改）。
5. `CompositeNamePolicy` 是否拒绝了机械名（grep `_structured`, `_st_`）。
6. metadata 中的旧机械名是否被 policy 拦截而非透传（检查 Planner 测试用例 3）。
7. 普通 composite step 的 `projection_relations` 是否为空 `()`（测试用例 8）。
8. stage 11 renderer 是否被修改（禁止）。

---

## 8. Decision Gate A：ProducerIndex 兼容路径审查

### 8.1 目标

Phase 3 完成后，`StepVariableRelationPlan` 已被 `CompositeOutputPlanApplier` 重写，
`producing_relations()` 只含 composite 变量的 produces 关系。此时必须通过书面方案评审，
确认 ProducerIndex v2 的 legacy `StepIR.outputs` 路径如何处理。

### 8.2 可选方案

```text
方案 A（激进）：ProducerIndex v2 仅消费 StepVariableRelationPlan
  - relation_plan 为 None 时不注册任何 step producer
  - 最干净，但会打空所有无 relation_plan 的 legacy / test / editing 路径的 producer
  - 可能制造大量非目标 missing_producer 诊断回归

方案 B（保守，推荐）：ProducerIndex v2 分层处理
  if relation_plan exists and is non-empty:
      relation_plan.producing_relations() 是唯一 step producer authority
      不扫描 StepIR.outputs（即使 plan 中遗漏也不 fallback）
  else:
      legacy StepIR.outputs fallback 仍可用，但必须：
        a. 标记为 "legacy_fallback" mode（可 grep）
        b. 产生 compat_warning 可见诊断
        c. 通过 test marker 明确标注哪些测试依赖 legacy 路径
```

**推荐方案 B**。原因：当前工程中存在多条无 relation_plan 的 legacy / test / SPL Editing 路径；
一次性砍掉会制造大量非目标回归，降低 Phase 4 的可验证性。方案 B 同样保证了
"relation_plan 存在时不会注册原字段"的核心不变量，且回归面可控。

**不论选择哪个方案，都必须**：
- 书面记录，PM 批准
- 在 Phase 4 实施前运行并审查下列测试集，确认无非目标回归：

```text
tests/unit/test_producer_index.py
tests/unit/test_post_normalize_resource_contract_irs.py
tests/unit/test_executable_gate.py
tests/integration/  （全量）
```

### 8.3 必须明确的问题

方案确认文档必须回答：

1. 选择方案 A 还是方案 B？理由是什么？
2. 当 `relation_plan` 为 `None` 或 `empty` 时，ProducerIndex 的 fallback 行为是什么（legacy mode or silent skip）？
3. `handoff` 步骤的 producer 注册是否仍通过 `WorkerHandoffIR.output_bindings` 走独立路径，不受方案 A/B 影响？
4. Phase 4 实施后，`test_producer_index.py` 中有哪些测试的 ProducerIndex 行为会改变？逐个列举。
5. `FieldProjectionRelation` 在本 MVP 中是否消费？若否，`projection_relations` 必须始终为空 `()`——此冻结在 Phase 2/3 中已落地，Gate A 必须书面确认仍有效。

### 8.4 验收标准

该决策门禁通过条件：

1. 方案选择（A 或 B）有书面记录，PM 批准。
2. ProducerIndex 的 fallback 行为有明确定义（不得静默无记录 fallback）。
3. 上述 4 个测试集已运行，无非目标回归，或回归已逐个书面分析。
4. `FieldProjectionRelation` 的 MVP 消费决策已书面记录。
5. PM 明确批准后方可进入 Phase 4。

---

## 9. Phase 4：ProducerIndex v2 接入 lowered relation plan

### 9.1 目标

ProducerIndex v2 必须以 `StepVariableRelationPlan.producing_relations()` 为权威，
消费 Phase 3 lowering 后的 relation plan。不再通过 `StepIR.outputs` 兼容路径注册
已被聚合的原字段。

`field_projection` / `handoff_field_projection` 作为 producer_kind 新值，用于标记
来自 `FieldProjectionRelation` 的投影产生关系。

### 9.2 可编辑范围

允许修改：

```text
src/nl2spl/compiler/producer_index.py
tests/unit/test_producer_index.py
```

允许新增：

```text
无
```

### 9.3 禁止改动

Phase 4 禁止修改：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/
src/nl2spl/pipeline/stages/stage11_spl_renderer/
src/nl2spl/validator/static_validator.py
src/nl2spl/ir/
```

### 9.4 设计要求

**`ProducerKind`** 新增值：

```text
"field_projection"          # 来自 FieldProjectionRelation，field 级 producer
"handoff_field_projection"  # 来自 handoff output_bindings 投影
```

**`ProducerIndex`** 注册逻辑：

```text
如果 relation_plan 存在且 non-empty：
  仅使用 relation_plan.producing_relations() 注册 produces 关系
  不扫描 StepIR.outputs（relation_plan 为 authority）

如果 relation_plan 为 None 或 empty：
  [Gate A 已决定的 fallback 行为]

handoff output_bindings：
  仍通过独立路径注册（不受 relation_plan 影响）
  producer_kind = "handoff" 或 "handoff_field_projection"
```

`ProducerIndex` 不得注册：

```text
composite 的原字段（a, b）作为 "step" producer
除非 FieldProjectionRelation 显式授权（Phase 4 暂不实现 projection relation 消费）
```

### 9.5 测试计划

新增单元测试必须覆盖：

1. relation_plan 含 `produces(composite_name)` -> ProducerIndex 注册 composite，不注册原字段
2. relation_plan 为 None -> fallback 行为（按 Gate A 决策）
3. handoff output_bindings 仍正确注册（不受 relation_plan 影响）
4. `producer_kind = "field_projection"` 的 `ProducerRef` 构造正确
5. `test_producer_index.py` 全量通过

### 9.6 验收标准

Phase 4 通过条件：

1. ProducerIndex 在 relation_plan 存在时不扫描 `StepIR.outputs`。
2. 原字段（lowering 前的 `a`, `b`）不出现在 ProducerIndex 的 produces 注册中。
3. composite 变量正确注册为 `producer_kind="step"`。
4. `test_producer_index.py` 全量通过。
5. 全量已有单测通过，无新增 skip / xfail。

### 9.7 PM 审核清单

审核时必须检查：

1. ProducerIndex 中是否还有 `StepIR.outputs` 直接扫描路径（当 relation_plan 存在时）。
2. `field_projection` producer_kind 是否有测试覆盖。
3. handoff 路径是否仍然独立、不被 relation_plan 覆盖。

---

## 10. Phase 5：Renderer fail-closed assert

### 10.1 目标

Stage 11 Renderer 成为 assert-only：
- `_result_clause` 检测到 `len(non_empty_outputs) > 1` 时抛出异常（fail closed）
- 不做任何 lowering、聚合、类型推断
- `DEFINE_TYPES` 在 `DEFINE_VARIABLES` 之前输出

### 10.2 可编辑范围

允许修改：

```text
src/nl2spl/pipeline/stages/stage11_spl_renderer/clause_builder.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py     [TYPES 顺序]
tests/unit/rendering/
  test_renderer_fail_closed.py  [新增]
tests/unit/test_spl_renderer.py
```

### 10.3 禁止改动

Phase 5 禁止修改：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/
src/nl2spl/compiler/producer_index.py
src/nl2spl/validator/static_validator.py
src/nl2spl/ir/
```

### 10.4 设计要求

**`_result_clause`** 修改为：

```python
def _result_clause(self, keyword: str, outputs: list[str]) -> str:
    non_empty = [o for o in outputs if o]
    if len(non_empty) > 1:
        raise ValueError(
            f"Renderer invariant violated: renderable command has {len(non_empty)} outputs "
            f"({non_empty!r}). Composite lowering must have run in Stage 9.5."
        )
    if not non_empty:
        return ""
    output = non_empty[0]
    self._produced_variables.add(output)
    return f" {keyword} {self._result_item(output)} SET"
```

**`renderer.py`** 中 DEFINE_TYPES 输出顺序：

```text
在 render_worker_plan() 或等效的顶层 render 方法中：
  先输出 DEFINE_TYPES 块（如有）
  再输出 DEFINE_VARIABLES 块
```

### 10.5 测试计划

新增单元测试必须覆盖：

1. `_result_clause("RESULT", ["a", "b"])` -> 抛出 `ValueError`（fail closed 验证）
2. `_result_clause("RESULT", ["composite"])` -> 正常渲染
3. `_result_clause("RESULT", [])` -> 返回 `""`
4. `_result_clause("RESULT", ["", "b"])` -> 仅渲染非空（`b`），不触发 fail closed
5. Renderer 输出的 SPL 中 `DEFINE_TYPES` 在 `DEFINE_VARIABLES` 之前

### 10.6 验收标准

Phase 5 通过条件：

1. `_result_clause` 在多 output 时抛出 `ValueError`。
2. `DEFINE_TYPES` 在 `DEFINE_VARIABLES` 之前输出（集成测试验证）。
3. `test_spl_renderer.py` 全量通过。
4. 全量已有单测通过，无新增 skip / xfail。

### 10.7 PM 审核清单

审核时必须检查：

1. `_result_clause` 是否仍有逗号拼接代码（不允许）。
2. `ValueError` 的 message 是否包含足够上下文（outputs 内容）。
3. DEFINE_TYPES 顺序修改是否在 renderer.py 而不是 normalization.py。

---

## 11. Phase 6：SPL Editing 守门

### 11.1 目标

SPL Editing materializer、stage slice、preview 和 apply 不得生成 multi-result command。
apply 只能消费 typed artifact（`CompositeOutputPlan`），不得从 rendered SPL text 做 lowering。

### 11.2 可编辑范围

**开工前必须先搜索所有 `outputs` 多值构造点**：

```bash
grep -rn "outputs.*=.*\[" src/nl2spl/compiler/spl_editing/
grep -rn "\.outputs" src/nl2spl/compiler/spl_editing/
```

允许修改（收窄到已知子目录）：

```text
src/nl2spl/compiler/spl_editing/
  materialization/     [仅守门：assert step.outputs <= 1]
  preview/             [仅守门：assert preview SPL 单 COMMAND_RESULT]
  stage_slices/        [仅守门：传递 CompositeOutputPlan typed artifact，不解析 SPL text]

tests/unit/compiler/
  test_spl_editing_composite_guard.py  [新增]
```

不得修改 `spl_editing/` 以外的任何生产代码。

### 11.3 禁止改动

Phase 6 禁止修改：

```text
src/nl2spl/ir/
src/nl2spl/compiler/producer_index.py
src/nl2spl/validator/static_validator.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/
```

### 11.4 设计要求

SPL Editing 的 apply 路径：

```text
1. 读取 typed artifacts（CompositeOutputPlan）
2. 不对 rendered SPL text 做任何 lowering
3. 生成 StepIR.outputs 时保证 <= 1
4. 生成的 preview SPL 必须满足：单 COMMAND_RESULT per command
```

如果 SPL Editing 发现 `StepIR.outputs` 仍有 > 1 个 output（说明 Stage 9.5 未运行），
必须 fail closed 而非静默修复。

### 11.5 测试计划

新增单元测试必须覆盖：

1. SPL Editing materializer 输入单 output step -> preview 包含单 RESULT
2. SPL Editing materializer 输入已经 lowered 的 composite step -> preview 包含聚合变量
3. SPL Editing apply 不对 rendered text 做 lowering（纯 typed artifact 消费）
4. SPL Editing 发现 > 1 output 时 fail closed（而非静默拼接）

### 11.6 验收标准

Phase 6 通过条件：

1. SPL Editing 的 preview 中无逗号分隔多 COMMAND_RESULT。
2. SPL Editing 的 apply 路径无 rendered text lowering。
3. 新增测试全部通过。
4. 全量已有单测通过，无新增 skip / xfail。

### 11.7 PM 审核清单

审核时必须检查：

1. SPL Editing apply 路径中是否有解析 rendered SPL 的代码（不允许）。
2. 是否有任何 "convenience" lowering 被加入 materializer。
3. fail closed 时的 diagnostic 是否明确说明需要运行 Stage 9.5。

---

## 12. Phase 7：E2E 集成验证

### 12.1 目标

全面验证从 Stage 7 -> Stage 9.5 lowering -> Stage 11 rendering 的完整路径，
确保所有设计不变量在端到端场景中成立。

### 12.2 可编辑范围

允许新增：

```text
tests/integration/
  test_composite_output_e2e.py  [新增]
```

### 12.3 禁止改动

Phase 7 禁止修改：

```text
所有生产代码（仅新增测试）
```

### 12.4 测试计划

E2E 测试必须覆盖：

1. **正常路径**：双 output step -> Stage 9.5 lowering -> Stage 11 单 COMMAND_RESULT 渲染
2. **CALL_API 路径**：CALL_API 双 output -> 聚合为单 structured response -> qualified ref 读取
3. **INVOKE 路径**：INVOKE_WORKER 双 output -> 聚合为单 response -> qualified ref 读取
4. **ProducerIndex 路径**：lowering 后 ProducerIndex 只含 composite producer
5. **StaticValidator 路径**：lowering 后的 SPL 通过 StaticValidator（无 multi-result error）
6. **Regression**：`test_worker_handoff_structured_unpack_regression.py` 场景继续通过

### 12.5 验收标准

Phase 7 通过条件：

1. 全部 E2E 测试通过。
2. 全量已有单测通过，无 regression。
3. 无新增 skip / xfail。

---

## 13. 端到端验收场景

最终必须具备以下 E2E 或高保真集成覆盖：

1. **双字段聚合正常路径**
   - 输入：StepIR with `outputs=["assumptions_log", "completion_status"]`，
     SymbolTable 均为 `text` 类型
   - Stage 9.5 运行后：`outputs=["assumptions_log_completion_status"]`，
     类型为结构化 `AssumptionsLogCompletionStatus`
   - Stage 11 渲染：
     `RESULT assumptions_log_completion_status: AssumptionsLogCompletionStatus SET`
     （单 COMMAND_RESULT）
   - StaticValidator 验证通过

2. **qualified reference 读取合法**
   - 输入：lowering 后 step B 的 inputs 中含
     `"assumptions_log_completion_status.assumptions_log"`
   - StaticValidator 对
     `<REF>assumptions_log_completion_status.assumptions_log</REF>` 无 error/warning
   - ProducerIndex 不将
     `"assumptions_log_completion_status.assumptions_log"` 注册为直接 producer

3. **qualified reference 写目标拒绝**
   - 输入 SPL：
     `RESULT <REF>assumptions_log_completion_status.assumptions_log</REF> SET`
   - StaticValidator emit `invalid_field_assignment_target` error
   - 测试验证 error 存在且 severity="error"

4. **Renderer fail-closed**
   - 构造 StepIR with `outputs=["a", "b"]`（模拟 Stage 9.5 未运行）
   - 直接调用 Stage 11 Renderer
   - 期望：`ValueError` 抛出，包含 outputs 信息

5. **Worker OUTPUTS 单一聚合输出**
   - lowering 后 worker output_contract 中只含 `assumptions_log_completion_status`
   - 不含 `assumptions_log` 或 `completion_status`
   - 渲染 `[OUTPUTS]` 区域只含
     `REQUIRED <REF>assumptions_log_completion_status</REF>`

6. **ProducerIndex 不注册原字段**
   - lowering 后调用 ProducerIndex 构建
   - `produces("assumptions_log")` 返回空
   - `produces("assumptions_log_completion_status")` 返回正确 ProducerRef

7. **handoff 回归场景**
   - `test_worker_handoff_structured_unpack_regression.py` 中所有场景继续通过
   - handoff producer 注册不被 relation_plan 干扰

---

## 14. PM 总审核清单

每个阶段提交审核时，PM 必须逐项检查：

1. 是否严格对齐 `spl_single_command_result_composite_output_lowering_design_zh.md`。
2. 是否扩大了原定范围边界（如意外实现 qualified Worker OUTPUTS）。
3. 是否新增未确认的 LLM prompt/schema 改动。
4. 是否新增未确认的 rule-based semantic fallback。
5. `_normalize_multi_output_steps()` 在 Phase 3 后是否已删除或标注废弃。
6. Stage 11 `_result_clause` 是否仍有逗号拼接代码。
7. StaticValidator 是否已拒绝顶层多 COMMAND_RESULT（`diagnostic_code="multi_command_result"`）。
8. `ValidationError` 是否有 `diagnostic_code` 字段，且关键 code 均为常量（非散落 magic string）。
9. `CompositeOutputPlan` 是否 `frozen=True`（不得有可变字段）。
10. `CompositeOutputPlan.schema_version` 是否在 payload 中序列化。
11. `StepVariableRelationPlan` 在 lowering 后是否只含 composite 的 produces 关系。
12. ProducerIndex 在 relation_plan 存在时是否仍扫描 `StepIR.outputs`（不允许）。
13. `CompositeNamePolicy` 是否拒绝了机械名（grep `_structured$`, `_st_\d+`, `_step.*result`）。
14. metadata 旧机械名是否被 policy 拦截（Planner 测试 3 通过）。
15. 普通 composite step 的 `projection_relations` 是否为空 `()`。
16. `FieldProjectionRelation` 是否在 MVP 中被消费（Gate A 书面决策需覆盖）。
17. SPL Editing apply 路径是否有 rendered text lowering（不允许）。
18. SPL Editing editable scope 是否超出 `materialization/`、`preview/`、`stage_slices/`（不允许）。
19. diagnostics 是否进入 compile_diagnostics / report（不仅留在 intermediate）。
20. 是否有新代码路径没有测试覆盖。
21. 是否有过期注释（如 "Multi-output commands render directly"）。
22. `step.metadata["structured_aggregation"]` 是否仍作为 authority 被消费（不允许）。
23. `test_worker_handoff_structured_unpack_regression.py` 是否通过。
24. `DEFINE_TYPES` 是否在 `DEFINE_VARIABLES` 之前渲染。
25. Phase 0 `test_composite_output_current_behavior.py` 在 Phase 1 后是否已退役：已重命名为 `test_composite_output_previous_behavior_retired.py`；所有断言已翻转为验证旧 buggy 行为已消失；不再保留任何断言旧行为仍存在的长期 pytest gate。
26. Phase 0 `test_composite_output_contract_regression.py` 在 Phase 1 后 xfail 是否全部移除并 pass。
27. Phase 1b field-path validation 三类 diagnostic_code 是否有独立单测。
28. Gate A 书面决策（方案 A/B、fallback 行为、FieldProjectionRelation MVP 消费决策）是否存在并经 PM 批准。
29. 是否有 skip / xfail / 弱断言（Phase 0 两个新文件除外，Phase 1 后必须全部移除）。

---

## 15. 阶段完成顺序

推荐顺序：

```text
Phase 0    基线锁定（两文件：current-behavior + contract-regression）  [可立即开工]
Phase 1    StaticValidator 强化 + ValidationError.diagnostic_code     [依赖 Phase 0]
Phase 1b   Typed Qualified Reference Field-Path Validation            [依赖 Phase 1]
Phase 2    CompositeOutputPlan Typed Artifact                         [可与 Phase 1 并行]
Phase 3    CompositeOutputPlanner + Applier + CompositeNamePolicy     [依赖 Phase 1 + Phase 1b + Phase 2]
Gate A     ProducerIndex 兼容路径审查（含 FieldProjectionRelation 决策） [依赖 Phase 3 完成]
Phase 4    ProducerIndex v2 接入                                      [依赖 Gate A]
Phase 5    Renderer fail-closed assert                                [依赖 Phase 3，可与 Phase 4 并行]
Phase 6    SPL Editing 守门（scope 收窄到三个子目录）                   [依赖 Phase 3 + Phase 5]
Phase 7    E2E 集成验证                                               [依赖所有 Phase 完成]
```

其中：

- Phase 0 可立即开工，不改生产代码。
- Phase 1 与 Phase 2 可并行（均为独立新组件或修改不相交文件）。
- Phase 1b 依赖 Phase 1（qualified_ref_parser），可在 Phase 1 PR 合并后开工。
- Phase 3 必须在 Phase 1 + Phase 1b + Phase 2 完成后开工（依赖 StaticValidator 守门、IR 模型、NamePolicy）。
- Gate A 必须在 Phase 3 完成后评审，不得跳过直接进入 Phase 4；Gate A 必须书面回答 5 个问题。
- Phase 5 可与 Phase 4 并行进行（修改不同文件）。
- Phase 6 必须在 Phase 3 + Phase 5 完成后开工；开工前必须先 grep `outputs` 多值构造点。
- Phase 7 必须等所有 Phase 完成后运行。
