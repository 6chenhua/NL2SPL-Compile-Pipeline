# ProducerIndex 缺少 REQUEST_INPUT producer 类型

日期：2026-06-11  
状态：待解决  
相关文件：`src/nl2spl/compiler/producer_index.py`、`docs/spl_grammar.txt`

---

## 问题描述

`ProducerIndex` 当前定义了 4 种 `ProducerKind`：

```python
ProducerKind = Literal["step", "handoff", "api", "compiler_scaffold"]
```

但 SPL 语法（`docs/spl_grammar.txt`）定义的 `COMMAND_BODY` 有 5 种：

```text
COMMAND_BODY := GENERAL_COMMAND | CALL_API | INVOKE_INSTRUCTION | REQUEST_INPUT | DISPLAY_MESSAGE
```

其中 `REQUEST_INPUT` 语法为：

```text
REQUEST_INPUT := "[INPUT" ["DISPLAY"] DESCRIPTION_WITH_REFERENCE
                 "VALUE" COMMAND_RESULT ["SET" | "APPEND"] "]"
```

这意味着 `REQUEST_INPUT` 命令可以产出变量值（通过 `VALUE` 子句绑定到 `COMMAND_RESULT`），是一个合法的 producer 来源，但当前 `ProducerIndex` 没有将其区分为独立的 producer 类型。

## 影响范围

1. **分类精度不足**：`REQUEST_INPUT` step 目前会被归类为泛化的 `"step"` producer kind，丢失了语义信息。在 SPL Editing 场景中，`ConvertDelegationIntentToRequestInput` patch 创建的就是 `REQUEST_INPUT` step，但 `ProducerIndex` 无法区分它和普通 `GENERAL_COMMAND` step。

2. **与 SPL 语法对齐**：`ProducerIndex` 作为 compiler authority 组件，其 producer 分类应反映 SPL 语法中的 command 类型体系：
   - `GENERAL_COMMAND` → `"step"`（当前有，但命名不够精确）
   - `CALL_API` → `"api"`（当前有）
   - `INVOKE_INSTRUCTION`/`INVOKE_WORKER` → `"handoff"`（当前通过 handoff 间接覆盖）
   - `REQUEST_INPUT` → **缺失**
   - `DISPLAY_MESSAGE` → 不产出变量，可能不需要 producer 类型

3. **`DISPLAY_MESSAGE` 也可能被误分类**：`DISPLAY_MESSAGE` 不产出变量，理论上不应出现在 producer 体系中。但当前 `_step_origin()` 可能将其归类为泛化 `"step"`（如果它有 source_span_ids）。

## 大致解决方向

1. 在 `ProducerKind` 中新增 `"request_input"` 类型。
2. 在 `_step_origin()` 中根据 `StepIR.command_type == "REQUEST_INPUT"` 进行区分。
3. 审计 `ProducerIndex` 的 renderability 判断逻辑：`REQUEST_INPUT` step 的 renderability 条件是否与 `GENERAL_COMMAND` 相同，还是需要特殊处理（比如需要 `value_target` 非空）。
4. 考虑是否需要为 `DISPLAY_MESSAGE` 添加显式的排除逻辑（在 step producer 收集阶段跳过 `DISPLAY_MESSAGE` step）。
5. 考虑是否需要将泛化的 `"step"` kind 重命名为更精确的 `"general_command"`，与 SPL 语法对齐。
6. 同步更新 `SPL Editing` 设计文档中与 `ProducerIndex` 相关的 verification predicate。
