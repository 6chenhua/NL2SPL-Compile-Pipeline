# Worker Handoff Structured Unpack 渲染异常问题记录与修复方案

## 1. 问题摘要

在 `examples/output/internal-comms-2/final_spl.txt` 中，`MainWorker` 的主流程出现了以下异常 SPL：

```text
COMMAND-11 [COMMAND Extract draft_communication_artifact from draft_communication_artifact_structured ...]
COMMAND-12 [COMMAND Extract source_evidence_set from draft_communication_artifact_structured ...]
COMMAND-13 [COMMAND Extract assumptions_log from draft_communication_artifact_structured ...]
COMMAND-14 [COMMAND Extract completion_status from draft_communication_artifact_structured ...]
```

这些命令的问题不是“表达不优雅”，而是语义上不成立：

```text
MainWorker 没有先渲染产生 draft_communication_artifact_structured 的 INVOKE_WORKER / CALL_API / COMMAND，
却直接渲染了从 draft_communication_artifact_structured 解包字段的命令。
```

因此最终 SPL 中存在“凭空解包 structured result”的错误。

本问题不属于 InputAdapter / FieldRoute 前端语义路由问题。当前中间产物显示：

- `Required outputs` 已被正确路由为 `output_contract / resources / executable=false`。
- `Failure handling` 已被正确路由为 `failure_mode / EXCEPTION_FLOW.condition / executable=false`。
- `Delegation policy` 没有直接变成 executable `INVOKE_WORKER`。

真正问题发生在 downstream：

```text
WorkerPlan handoff
-> Stage 7 handoff step materialization
-> Stage 9.5 multi-output structured aggregation
-> Executable gate
-> Stage 11 rendering
```

核心根因是：

```text
Stage 9.5 把 multi-output INVOKE_WORKER 改写为 single structured output，
但 ExecutableElementGate 仍按原始 handoff output bindings 校验，
导致 INVOKE_WORKER 被 gate 过滤；
同时 compiler_unpack steps 被 gate 允许渲染，
于是最终只剩解包命令，缺少其 structured result producer。
```

---

## 2. 复现输入与证据目录

复现目录：

```text
examples/output/internal-comms-2
```

关键文件：

```text
examples/output/internal-comms-2/stage2_field_router.json
examples/output/internal-comms-2/stage3_5_worker_boundary_planner.json
examples/output/internal-comms-2/stage4_flow_assembler.json
examples/output/internal-comms-2/stage5_block_assembler.json
examples/output/internal-comms-2/compile_report.txt
examples/output/internal-comms-2/feedback_report.md
examples/output/internal-comms-2/final_spl.txt
```

---

## 3. 已确认正常的部分

### 3.1 Stage 2 FieldRoute 基本符合预期

`stage2_field_router.json` 中：

- `s6-s10` 是 `input_contract`，`field=resources`，`executable=false`。
- `s11-s14` 是 `output_contract`，`field=resources`，`executable=false`。
- `s24-s29` 是 `failure_mode`，`construct_target=EXCEPTION_FLOW`，`slot_target=condition`，`executable=false`。
- `s30` 是 `delegation_intent`，`executable=false`。
- `s15-s18` 是 `process_step`，可执行。

这说明前端职责边界基本成立：

```text
Adapter/Mapper/FieldRoute 没有把 output contract 当作普通 executable behavior。
Failure handling 也没有落回 bridge-first / rules 路径。
```

### 3.2 Stage 4 ExceptionFlow 也符合预期

`stage4_flow_assembler.json` 中，`worker_main` 下生成了 condition-only exception flows：

```json
{
  "condition_text": "Missing timeframe",
  "spans": ["s24"]
}
```

这是预期行为：

```text
Failure mode -> ExceptionFlow condition skeleton
不虚构 handler。
```

---

## 4. 异常现象的中间产物证据链

### 4.1 WorkerBoundaryPlanner 生成了 child worker 和 handoff

`stage3_5_worker_boundary_planner.json` 中存在 child worker：

```text
worker_id = generate_draft_communication
worker_name = Worker_generate_draft_communication
```

并且存在 handoff：

```text
handoff_id = handoff_generate_draft_communication
from_worker = worker_main
to_worker = generate_draft_communication
mode = invoke
```

handoff output bindings 包含 4 个 parent outputs：

```text
draft_communication_artifact
source_evidence_set
assumptions_log
completion_status
```

这本身是合法的多输出 handoff contract。

### 4.2 Stage 9.5 把 handoff step 聚合成 structured result

`compile_report.txt` / `feedback_report.md` 中出现明确 warning：

```text
Aggregated multi-output step st_invoke_handoff_generate_draft_communication
into draft_communication_artifact_structured with 4 unpack steps.
```

这说明 Stage 9.5 的 `_normalize_multi_output_steps()` 对 handoff-generated `INVOKE_WORKER` 做了如下改写：

```text
Before:
    INVOKE_WORKER outputs = [
        draft_communication_artifact,
        source_evidence_set,
        assumptions_log,
        completion_status
    ]

After:
    INVOKE_WORKER outputs = [draft_communication_artifact_structured]
    compiler_unpack steps:
        Extract draft_communication_artifact from draft_communication_artifact_structured
        Extract source_evidence_set from draft_communication_artifact_structured
        Extract assumptions_log from draft_communication_artifact_structured
        Extract completion_status from draft_communication_artifact_structured
```

对应代码：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py
  _normalize_multi_output_steps()
```

### 4.3 Final SPL 只渲染了 unpack steps，未渲染 INVOKE_WORKER

`final_spl.txt` 中 `MainWorker` 主流程为：

```text
[MAIN_FLOW]
    [SEQUENTIAL_BLOCK]
        COMMAND-11 [COMMAND Extract draft_communication_artifact ...]
        COMMAND-12 [COMMAND Extract source_evidence_set ...]
        COMMAND-13 [COMMAND Extract assumptions_log ...]
        COMMAND-14 [COMMAND Extract completion_status ...]
    [END_SEQUENTIAL_BLOCK]
[END_MAIN_FLOW]
```

但没有对应的：

```text
INVOKE Worker_generate_draft_communication ...
```

这证明：

```text
producer step 被过滤或未渲染；
dependent unpack steps 被保留并渲染。
```

### 4.4 系统报告已经发现 downstream producer 缺失

`feedback_report.md` / `compile_report.txt` 中存在：

```text
missing_output_producer on worker:generate_draft_communication.output:source_evidence_set
missing_output_producer on worker:generate_draft_communication.output:completion_status
```

这说明最终 IR 自身已经不完整。

---

## 5. 代码根因

### 5.1 Stage 7 handoff step 的原始输出是多个 parent variables

代码位置：

```text
src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py
  _step_for_invoke_handoff()
```

当前逻辑：

```python
outputs=[
    binding.parent_variable
    for binding in handoff.output_bindings
    if binding.parent_variable
]
```

因此 handoff step 初始状态是：

```text
command_type = INVOKE_WORKER
handoff_id = handoff_generate_draft_communication
outputs = [
    draft_communication_artifact,
    source_evidence_set,
    assumptions_log,
    completion_status
]
```

这是符合 WorkerPlanIR handoff contract 的。

### 5.2 Stage 9.5 对所有 multi-output steps 一视同仁地聚合

代码位置：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py
  normalize_worker_scoped()

src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py
  _normalize_multi_output_steps()
```

当前逻辑：

```python
for steps in worker_step_plan.worker_steps.values():
    warnings.extend(
        self._normalize_multi_output_steps(resources, symbol_table, steps)
    )
```

`_normalize_multi_output_steps()` 不区分：

```text
GENERAL_COMMAND multi-output
INVOKE_WORKER multi-output
CALL_API multi-output
```

它会统一把多输出 step 改写成：

```text
step.outputs = [result_name]
compiler_unpack steps produce original_outputs
```

这会改变 handoff step 与 WorkerPlanIR handoff contract 的形状。

### 5.3 ExecutableElementGate 仍按原始 handoff bindings 校验

代码位置：

```text
src/nl2spl/pipeline/executable_gate.py
  is_renderable()
```

当前逻辑：

```python
expected_outputs = [
    b.parent_variable for b in handoff.output_bindings
]

if list(step.outputs) != expected_outputs:
    return False
```

因此 Stage 9.5 改写后的 handoff step：

```text
step.outputs = [draft_communication_artifact_structured]
```

不再等于：

```text
expected_outputs = [
    draft_communication_artifact,
    source_evidence_set,
    assumptions_log,
    completion_status
]
```

于是 `INVOKE_WORKER` 被 gate 判定为不可渲染。

### 5.4 compiler_unpack steps 被 gate 允许渲染

同一文件中，gate 对 compiler unpack 有特殊放行：

```python
if origin == "compiler_synthetic":
    if step.metadata.get("origin") == "compiler_unpack":
        return True, None
```

因此出现错误组合：

```text
INVOKE_WORKER producer 被过滤
compiler_unpack consumers 被保留
```

### 5.5 structured result 名称发生跨 worker / 跨 step 碰撞

`compile_report.txt` 中同时存在：

```text
Aggregated multi-output step st_invoke_handoff_generate_draft_communication into draft_communication_artifact_structured with 4 unpack steps.
Aggregated multi-output step st_6 into draft_communication_artifact_structured with 3 unpack steps.
```

两个不同 worker / 不同 step 都产生了同名：

```text
draft_communication_artifact_structured
```

代码位置：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py
  _aggregate_result_name()
```

当前逻辑：

```python
base = step.outputs[0] if step.outputs else "result"
return f"{self._safe_name(base)}_structured"
```

它只基于第一个 output 命名，未包含：

```text
worker_id
step_id
handoff_id
scope
```

这会造成 structured variable collision。

---

## 6. 设计判断

`INVOKE_WORKER` 的多输出处理有两种合理设计。

### 方案 A：允许 INVOKE_WORKER 直接多输出

如果 SPL 语法允许 worker invoke 返回多个 outputs，则应避免对 `INVOKE_WORKER` 做 structured aggregation。

优点：

- 保持 handoff contract 与 StepIR outputs 一致。
- Gate 不需要理解 structured response。
- Renderer 可直接渲染：

```text
INVOKE Worker_generate_draft_communication ... RESPONSE draft_communication_artifact, source_evidence_set, assumptions_log, completion_status SET
```

缺点：

- 如果当前 SPL grammar 只允许单 RESULT/RESPONSE，需要改 renderer grammar。

### 方案 B：保留 structured aggregation，但让 handoff/gate/renderer 全链路理解 structured response

如果 SPL 语法只允许单 `RESPONSE`，则 handoff aggregation 是合理的，但必须满足：

```text
INVOKE_WORKER structured response step 可渲染；
compiler_unpack steps 只有在 producer 可渲染时才可渲染；
structured result 命名必须 scope-safe；
gate 校验必须接受 handoff structured response 等价于原始 output bindings。
```

推荐方案：**方案 B**。

理由：

1. 当前 normalizer 已经明确表达“multi-output commands must be represented as structured result plus unpack commands”。
2. 修复范围集中在 normalizer/gate/provenance/render path，不需要扩展 SPL grammar。
3. 保留 compiler_unpack scaffolding 的设计，但修正它的依赖关系和 contract 校验。

---

## 7. 详细解决方案

### Phase 1：给 structured aggregation 添加来源 metadata

修改文件：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py
```

在 `_normalize_multi_output_steps()` 聚合 step 前保存原始信息：

```python
original_outputs = list(step.outputs)
result_name = self._aggregate_result_name(step, worker_id=..., scope=...)
```

对被聚合的 producer step 添加 metadata：

```python
step.metadata["origin"] = step.metadata.get("origin") or "source_backed"
step.metadata["structured_aggregation"] = {
    "result_name": result_name,
    "original_outputs": original_outputs,
    "type_name": type_name,
}
```

对于 handoff step，额外记录：

```python
step.metadata["handoff_output_bindings"] = [
    {
        "child_output": binding.child_output,
        "parent_variable": binding.parent_variable,
        "required": binding.required,
    }
    for binding in handoff.output_bindings
]
```

注意：

- `_normalize_multi_output_steps()` 当前不知道 `worker_id` / `worker_plan` / `handoff_index`。
- 因此需要扩展函数签名，至少传入 `worker_id`。
- 如果要写入 handoff bindings metadata，则需要传入 `handoff_index` 或在 worker-scoped caller 侧预处理。

验收标准：

- 聚合后的 `INVOKE_WORKER` step 仍保留 `handoff_id`。
- 聚合后的 step metadata 能追溯原始 outputs。
- compiler_unpack step metadata 能指向 producer step / result variable。

建议 metadata：

```python
unpack_step.metadata = {
    "origin": "compiler_unpack",
    "structured_source_step_id": step.step_id,
    "structured_result": result_name,
    "unpacked_output": output_name,
}
```

---

### Phase 2：修复 structured result 命名碰撞

修改文件：

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py
```

当前：

```python
def _aggregate_result_name(self, step):
    base = step.outputs[0] if step.outputs else "result"
    return f"{self._safe_name(base)}_structured"
```

建议改为：

```python
def _aggregate_result_name(
    self,
    step: StepIR,
    worker_id: str | None = None,
) -> str:
    if step.handoff_id:
        base = f"{step.handoff_id}_response"
    elif worker_id:
        base = f"{worker_id}_{step.step_id}_result"
    else:
        base = f"{step.step_id}_result"
    return f"{self._safe_name(base)}_structured"
```

示例结果：

```text
handoff_generate_draft_communication_response_structured
generate_draft_communication_st_6_result_structured
```

验收标准：

- MainWorker handoff aggregation 和 child worker internal aggregation 不再生成同名 variable。
- `draft_communication_artifact_structured` 不再被多个 unrelated producers 复用。
- Type name 也跟随 result name 唯一化。

---

### Phase 3：修复 ExecutableElementGate 对 structured handoff response 的校验

修改文件：

```text
src/nl2spl/pipeline/executable_gate.py
```

当前 gate 对 handoff step 做严格输出相等校验：

```python
if list(step.outputs) != expected_outputs:
    return False
```

需要改成：

```text
普通 handoff step:
    step.outputs == expected_outputs

structured handoff step:
    len(step.outputs) == 1
    step.metadata.structured_aggregation.original_outputs == expected_outputs
    或者 compiler_unpack coverage == expected_outputs
```

建议实现 helper：

```python
def _handoff_outputs_match(
    self,
    step: StepIR,
    expected_outputs: list[str],
) -> bool:
    if list(step.outputs) == expected_outputs:
        return True

    aggregation = step.metadata.get("structured_aggregation")
    if not isinstance(aggregation, dict):
        return False

    original_outputs = aggregation.get("original_outputs") or []
    return list(original_outputs) == expected_outputs and len(step.outputs) == 1
```

然后替换现有输出比较：

```python
if not self._handoff_outputs_match(step, expected_outputs):
    return False, ...
```

验收标准：

- structured `INVOKE_WORKER` 不会因为 `step.outputs` 被改写为单 structured result 而被 gate 过滤。
- 原始 outputs 不匹配时仍然失败。
- 没有 metadata 的 arbitrary single-output handoff 不应伪装成合法 multi-output handoff。

---

### Phase 4：compiler_unpack 必须依赖 producer 可渲染性

修改文件：

```text
src/nl2spl/pipeline/executable_gate.py
```

当前：

```python
if step.metadata.get("origin") == "compiler_unpack":
    return True, None
```

这过于宽松。应改为：

```text
compiler_unpack renderable iff:
    1. metadata.structured_source_step_id 存在；
    2. 对应 source step 在同一 worker 内仍然 renderable；
    3. unpack input == source step output structured result；
    4. unpack output 属于 source step metadata.structured_aggregation.original_outputs。
```

由于 `is_renderable()` 当前逐 step 判断，不能直接知道 producer 是否最终保留。建议在 `apply()` 的 worker filtering 阶段做两遍过滤：

```text
Pass 1:
    classify/filter non-unpack producer steps
    record renderable_step_ids

Pass 2:
    classify compiler_unpack
    only keep if structured_source_step_id in renderable_step_ids
```

也可以先实现局部 helper：

```python
def _compiler_unpack_renderable(
    self,
    step: StepIR,
    renderable_step_ids: set[str],
) -> tuple[bool, str | None]:
    source_step_id = step.metadata.get("structured_source_step_id")
    if not source_step_id:
        return False, "compiler_unpack missing structured_source_step_id"
    if source_step_id not in renderable_step_ids:
        return False, "compiler_unpack source step is not renderable"
    return True, None
```

验收标准：

- 如果 structured producer 被 gate 过滤，所有 dependent unpack steps 也必须被过滤。
- 不允许最终 SPL 中出现没有 producer 的 `Extract ... from structured_result`。
- 现有合法 compiler_unpack 仍可渲染。

---

### Phase 5：Stage 10/Renderer 输出应保留 INVOKE + unpack 顺序

涉及文件：

```text
src/nl2spl/pipeline/stages/stage10_worker_assembler/block_utils.py
src/nl2spl/pipeline/stages/stage11_spl_renderer/block_renderer.py
```

当 structured handoff producer 和 unpack steps 都合法时，最终 block 中应该同时包含：

```text
INVOKE Worker_generate_draft_communication ... RESPONSE handoff_generate_draft_communication_response_structured SET
COMMAND Extract draft_communication_artifact from handoff_generate_draft_communication_response_structured ...
COMMAND Extract source_evidence_set from handoff_generate_draft_communication_response_structured ...
...
```

需要确认：

- `_ensure_renderable_blocks()` 不会只把 unpack steps 放入 fallback block，而漏掉 producer。
- `_steps_for_block()` 能同时选中 producer 和 unpack steps。
- ordering 中 producer 必须在 unpack steps 前。

如果 unpack steps 没有 source spans，需要依赖 `block_ref` 与 producer 同 block：

```python
unpack_step.block_ref = step.block_ref
unpack_step.flow_ref = step.flow_ref
```

当前 normalizer 已经复制了 `flow_ref` / `block_ref`，但如果 producer 是 fallback block 后才获得 `block_ref`，unpack steps 可能不会同步更新。需要测试锁住。

验收标准：

- MainWorker 中 `INVOKE` 出现在 unpack commands 之前。
- unpack commands 和 producer 在同一 flow/block 中。
- 没有 producer 的 unpack command 不渲染。

---

## 8. 推荐测试矩阵

### Test 1：multi-output handoff structured response 可渲染

构造：

```text
WorkerPlanIR:
    main -> child handoff
    output_bindings = out_a, out_b

Stage7 StepIR:
    INVOKE_WORKER outputs=[out_a, out_b]
```

执行：

```text
Stage9.5 normalization
ExecutableElementGate
Stage11 renderer
```

断言：

```text
final SPL contains INVOKE Worker_child
final SPL contains Extract out_a from <structured_result>
final SPL contains Extract out_b from <structured_result>
INVOKE appears before Extract
```

### Test 2：producer 被过滤时 unpack 也被过滤

构造非法 handoff：

```text
INVOKE_WORKER handoff_id 不存在
compiler_unpack references that step
```

断言：

```text
INVOKE_WORKER not rendered
compiler_unpack not rendered
gate diagnostics include source step missing/not renderable
```

### Test 3：structured result 命名不碰撞

构造：

```text
main handoff step outputs=[draft, evidence]
child internal step outputs=[draft, assumptions]
```

断言：

```text
two structured result variable names differ
two type names differ
no duplicate variable declarations
```

### Test 4：gate 不接受伪 structured handoff

构造：

```text
INVOKE_WORKER outputs=[some_structured]
metadata lacks structured_aggregation.original_outputs
handoff output_bindings=[out_a, out_b]
```

断言：

```text
step not renderable
diagnostic explains output binding mismatch
```

### Test 5：internal-comms-2 回归

使用当前 internal-comms 输入或 fixture。

断言最终 SPL：

```text
must contain INVOKE Worker_generate_draft_communication
must not contain Extract ... from draft_communication_artifact_structured unless the producer is also rendered
must not have duplicate draft_communication_artifact_structured producers
```

---

## 9. 修复顺序建议

建议按以下顺序实施：

```text
1. Add failing tests for current bug.
2. Add structured aggregation metadata.
3. Make aggregate result names scope-safe.
4. Update ExecutableElementGate handoff output matching.
5. Make compiler_unpack depend on renderable producer.
6. Verify Stage10 block fallback preserves producer + unpack ordering.
7. Re-run internal-comms-2 and compare final SPL.
```

不要先改 renderer 文本输出。当前问题不是 renderer 文案问题，而是 IR/gate 合同问题。

---

## 10. 最终验收标准

修复完成必须同时满足：

1. `pytest tests/unit/ -q` 全绿。
2. 新增 handoff structured aggregation 测试覆盖：
   - producer preserved；
   - unpack depends on producer；
   - output binding equivalence；
   - scoped structured result naming。
3. `examples/output/internal-comms-2/final_spl.txt` 不再出现无 producer 的 unpack commands。
4. 如果出现：

```text
COMMAND Extract x from y_structured
```

则同一 worker/flow 中必须存在更早的：

```text
INVOKE / CALL / COMMAND ... RESULT|RESPONSE y_structured SET
```

5. `compile_report.txt` 不再包含同名 structured result 被两个不同 step 聚合的 warning。
6. `missing_output_producer` 不应由 compiler unpack/gate 断裂造成；如果源需求确实没有生产某 output，应该以 diagnostic 留下，而不是虚构 extract command。

---

## 11. 与最初设计理念的关系

这个问题再次体现了同一个原则：

```text
不能为了让 SPL 完整而生成没有上游证据或没有 producer 的命令。
```

`compiler_unpack` 是合法 scaffolding，但它必须依附于一个已验证、可渲染的 structured producer。它不能独立成为补全 required outputs 的手段。

因此本修复的边界是：

```text
允许 compiler 规范化多输出结果；
禁止 compiler 在 producer 被过滤后仍渲染 unpack；
禁止 unpack 被误用为 required output fabrication。
```
