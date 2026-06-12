# Stage 2 annotation contract 冲突导致主流程为空

日期：2026-06-11  
状态：已解决  
相关文件：`src/nl2spl/pipeline/stages/stage2_field_router.py`、`src/nl2spl/pipeline/stages/stage2_field_router_validator.py`、`src/nl2spl/pipeline/stages/stage3_ambiguity_resolver.py`、`src/nl2spl/ir/field_route_ir.py`、`src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py`、`prompts/stage2_adapter_guided_system.txt`

---

## 问题描述

运行 `examples/usage.py` 后，`examples/output/demo/final_spl.txt` 中 `[MAIN_FLOW]` 为空。

本问题不包括 `partial` 状态本身。当前输入中的 failure handling 只列出失败条件、没有 handler action，因此 SPL 为 `partial` 是正常且符合 IRS anti-fabrication 约束的。需要修复的是：源文档中的 reusable process 已经描述了可执行流程，但这些流程没有进入 Stage 4，因此主流程为空。

---

## 已验证的中间过程现象

1. `examples/output/demo/stage2_field_router.json` 中 `routes.behavior` 为空。
2. 同一文件中，`s15`、`s16`、`s17` 的 `process_step` annotation 被拒绝，原因是：
   - `process_step requires construct_target=None, got 'RESOURCE_CONTRACT'`
3. `s18` 到 `s23` 的普通 `constraint` annotation 也被拒绝，原因是：
   - `constraint requires construct_target=None, got 'CONSTRAINT'`
4. `examples/output/demo/stage3_ambiguity_resolver.json` 中，Stage 3 已经把 reusable process 拆成 `s15a`、`s15b`、`s15c`、`s16a`、`s16b`、`s16c`、`s17a`、`s17b`、`s18a`，并把它们放进 `resolved_routes.behavior`。
5. 但这些 split child span 没有对应的 `executable=True, field="behavior"` annotation。
6. `examples/output/demo/stage4_flow_assembler.json` 中，Stage 4 产出：
   - `main_flow_spans: []`
   - warning: `Worker worker_main has no owned behavior spans for Stage 4.`

---

## 根本原因

根因是 Stage 2 的 LLM-facing schema / prompt 与 canonical annotation role contract 不一致，并且 validator 与 normalizer 的执行顺序使冲突无法被纠正。

### 1. Prompt/schema 迫使 LLM 输出非空 construct/slot

`prompts/stage2_adapter_guided_system.txt` 把 `construct_target` 和 `slot_target` 定义为 annotation 字段，并要求从 `allowed_schema.construct_targets` / `allowed_schema.slot_targets` 选择。

这些 allowed schema 来自：

```python
ROLE_CONTRACT_REGISTRY.allowed_construct_targets()
ROLE_CONTRACT_REGISTRY.allowed_slot_targets()
```

而 registry 的实现明确排除了 `None`，因为 `None` 是 contract 的显式期望值，不是 allowed-schema literal。

结果是：LLM 在为 `process_step`、`profile_domain`、普通 `constraint` 这类本应无 construct/slot 的 role 输出时，仍会被 schema 诱导填写某个非空值。

### 2. Canonical contract 又要求这些 role 的 construct/slot 为 None

`ROLE_CONTRACT_REGISTRY` 中：

- `process_step` 的 contract 是 `field="behavior"`、`route_family="flow_relevant"`、`construct_target=None`、`slot_target=None`、`executable=True`
- `profile_domain` 的 `construct_target=None`、`slot_target=None`
- 普通 `constraint` 的 `construct_target=None`、`slot_target=None`

因此，LLM 输出 `process_step + construct_target=RESOURCE_CONTRACT` 或 `constraint + construct_target=CONSTRAINT` 时，语义 role 是对的，但 compiler-facing field 与 canonical contract 冲突。

### 3. Validator 先拒绝，normalizer 后执行

`Stage 2` 的 `_merge_llm_refinement()` 先调用：

```python
validated = validator.validate(...)
```

`RouteRefinementValidator._check_against_registry()` 会在 raw annotation 上检查完整 role contract。一旦看到 `ann.construct_target is not None and ann.construct_target != contract.construct_target`，就直接拒绝 annotation。

但是 `_normalize_annotation_contract()` 位于后续 `for llm_ann in validated.accepted` 分支内。被 validator 拒绝的 annotation 永远进不到 normalization，因此 `process_step + RESOURCE_CONTRACT` 没有机会被纠正成 canonical `process_step + construct_target=None`。

### 4. Stage 2 清空旧 behavior fallback，只从 accepted annotations 重建

Stage 2 早期 `_route_packet_span()` 仍会按 packet type 把 `process_step` 放进旧的 `routes.behavior`。

但 `_execute_canonical()` 后段执行：

```python
routes.annotations = priors
self._sync_legacy_routes_from_annotations(routes)
```

`_sync_legacy_routes_from_annotations()` 会先清空所有 legacy route list，再只根据 accepted annotations 重建。由于 `s15`、`s16`、`s17` 的 `process_step` annotation 已被拒绝，重建后的 `routes.behavior` 为空。

### 5. Stage 3 不能从 split recommendation 独立生成 child annotations

Stage 3 虽然使用 split recommendation 拆出了 child spans，但 annotation 派生逻辑只从父 span 的 accepted annotations 继承：

```python
parent_anns = routes.get_annotations(parent_span_id)
if not parent_anns:
    continue
```

因为父 span 的 `process_step` annotation 已经在 Stage 2 被拒绝，`s15a` 到 `s18a` 只进入 `resolved_routes.behavior`，没有获得 executable annotation。

### 6. Stage 4 只消费 executable behavior annotations

`FieldRouteIR.get_executable_behavior_span_ids()` 在存在 annotations 时，只返回：

```python
a.span_id for a in self.annotations
if a.executable and a.field == "behavior"
```

Stage 4 worker-aware path 使用该方法计算 `behavior_span_ids`。由于 split children 没有 executable annotation，Stage 4 得到的 worker-local behavior span 数量为 0，最终 `main_flow_spans` 为空。

---

## 解决方案方向

推荐修复思路：LLM 只负责判断 `semantic_role`；compiler-facing fields 由 `ROLE_CONTRACT_REGISTRY` 决定。

### 方案 1：调整 Stage 2 prompt/schema

将 `allowed_schema.construct_targets` / `allowed_schema.slot_targets` 的全局枚举改为 role-aware contract table。

示例：

```json
{
  "role_contracts": {
    "process_step": {
      "field": "behavior",
      "route_family": "flow_relevant",
      "construct_target": null,
      "slot_target": null,
      "executable": true
    },
    "failure_mode": {
      "field": "behavior",
      "route_family": "flow_relevant",
      "construct_target": "EXCEPTION_FLOW",
      "slot_target": "condition",
      "executable": false
    }
  }
}
```

Prompt 应明确：

- `semantic_role` 是 LLM 的主要输出。
- `construct_target`、`slot_target` 不允许自由选择。
- 如果输出这些字段，必须等于该 role 的 contract。
- 对 contract 值为 `null` 的 role，应省略该字段或输出 `null`。

### 方案 2：Stage 2 先 normalize，再 validate

当前顺序是：

```text
parse raw LLM annotation
-> validate raw annotation against registry
-> only accepted annotation enters normalize
```

应改为：

```text
parse raw LLM annotation
-> resolve semantic_role
-> normalize_annotation_from_role()
-> record correction diagnostics for raw/canonical mismatch
-> validate normalized annotation for downstream safety
```

这样 `process_step + construct_target=RESOURCE_CONTRACT` 应变成：

- accepted canonical annotation: `semantic_role=process_step`、`field=behavior`、`construct_target=None`、`slot_target=None`、`executable=True`
- diagnostic: raw `construct_target=RESOURCE_CONTRACT` was corrected by role contract

只有未知 role、未知 span、malformed executable 等无法确定语义的情况才应 reject。

### 方案 3：Stage 3 使用 split segment 生成 child annotations

Stage 3 不应只依赖父 span 的 accepted annotation。`ambiguity_updates` 中已经携带 split recommendation segments，每个 segment 有 `semantic_role`。

应在 Stage 3 中：

1. 将 LLM split segment 与生成的 child span 对齐。
2. 对 segment.semantic_role 调用 `normalize_annotation_from_role()`。
3. 为 child span 创建 canonical `RouteAnnotation`。
4. 父 annotation 继承只作为 fallback，而不是唯一来源。

这样即使父 span annotation 被 Stage 2 拒绝，`s15a`、`s15b`、`s15c` 仍可得到 `executable=True, field="behavior"` 的 canonical annotations。

### 方案 4：保留 Stage 4 的严格消费规则

不建议让 Stage 4 回退消费 `routes.behavior`。Stage 4 当前只使用 executable behavior annotations 是合理的：它避免把 contract、constraint、failure condition、delegation boundary 等非执行内容混进主流程。

可以增加防御性诊断：

```text
routes.behavior is non-empty but executable behavior annotations are missing
```

用于定位 Stage 2/3 annotation 丢失，但不作为主修复路径。

---

## 最小可接受修复

1. 在 Stage 2 中将 role-contract normalization 前移到 validator reject 之前。
2. 对 raw/canonical mismatch 记录 correction diagnostic，而不是直接 reject。
3. 在 Stage 3 中基于 split segment 的 `semantic_role` 生成 child annotations。
4. 保持 Stage 4 只消费 executable behavior annotations。

---

## 回归测试建议

1. LLM 输出 `process_step + construct_target=RESOURCE_CONTRACT` 时，最终 accepted annotation 应为 canonical `process_step`，且 `construct_target is None`。
2. LLM 输出 `constraint + construct_target=CONSTRAINT` 时，普通 `constraint` 应 normalize 为 `construct_target is None`；如果是 delegation boundary，应使用 `delegation_boundary_constraint`。
3. s15 拆分成 s15a/s15b/s15c 后，child spans 应有 `executable=True, field="behavior"` annotation。
4. `examples/usage.py` 的 demo 输入应产生非空 `stage4_worker_flows.worker_main.main_flow_spans`。
5. `profile_domain + construct_target=RESOURCE_CONTRACT` 不应进入 DemandView，不应产生 resource contract demand。
