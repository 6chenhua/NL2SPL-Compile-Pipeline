# Stage 2 LLM construct_target / semantic_role 矛盾输出

状态: Draft  
日期: 2026-06-09  
发现者: @6chenhua  
范围: Stage 2 Field Router LLM refinement, `ResourceContractPlanner`

## 问题描述

在 `_call_adapter_guided_llm` 运行过程中，Stage 2 LLM 输出了一个内部矛盾的 `RouteAnnotation`：

```json
{
  "span_id": "s1",
  "field": "domain",
  "semantic_role": "profile_domain",
  "construct_target": "RESOURCE_CONTRACT",
  "slot_target": "input",
  "executable": false,
  "primary": true,
  "source_section_id": "sec_task_family",
  "source_packet_id": "p_sentence_name_internal_communications_drafting",
  "reason": "Names the task family as internal communications drafting."
}
```

### 矛盾点

| 字段 | 值 | 实际语义 |
|------|-----|---------|
| `semantic_role` | `profile_domain` | 任务领域/背景描述 ✅ 正确 |
| `construct_target` | `RESOURCE_CONTRACT` | 资源合约 | ❌ 与 semantic_role 矛盾 |
| `slot_target` | `input` | 输入 slot | ❌ 此 span 不涉及任何输入 |
| `source_section_id` | `sec_task_family` | — | 此 section 描述任务领域，非资源 |

**核心矛盾**：`semantic_role=profile_domain` 表明这是一个 domain/context span，但 `construct_target=RESOURCE_CONTRACT` 和 `slot_target=input` 把它错误地标记为资源合约输入。这两个维度在语义上不可调和。

### 可能的 LLM 混淆原因

1. **"Inputs" 关键词过拟合**：`slot_target=input` 表明 LLM 可能因为 prompt 中出现了 "Inputs for each run" section 而泛化地给其他 span 也打上 `input` slot 标签
2. **construct_target 约束不足**：Stage 2 LLM prompt 中对 `construct_target` 与 `semantic_role` 的一致性约束不够强
3. **多标签学习不收敛**：LLM 需要同时为 `semantic_role`、`route_family`、`construct_target`、`slot_target` 四个维度打标签，当标注 schema 不完全正交时容易产生跨维度混淆

## 影响范围

### 直接影响：ResourceContractPlanner（Phase 1 新增）

`ResourceContractPlanner._contract_annotations()` 的规则二是：

```python
if (
    ann.route_family == "resource_contract"
    or ann.construct_target == "RESOURCE_CONTRACT"
):
    result.append(ann)
```

这个错误的 annotation 会命中 `construct_target == "RESOURCE_CONTRACT"` 分支，将 `s1`（"internal communications drafting"）误判为一个 resource contract demand。

### 下游影响

- `ResourceContractPlanIR` 会产生一个无意义的 demand（方向不确定，因为 `semantic_role` 不是 `input_contract`/`output_contract`）
- 该 demand 会进入 Stage 3.5 prompt、Stage 6 context builder，浪费 token
- 最终在 IRS 检查时由于找不到 binding 而触发 `missing_resource_contract` diagnostic，产生误报警

### 当前缓解

`_contract_annotations()` 规则一要求 `semantic_role in {"input_contract", "output_contract"}`，但规则二 `construct_target == "RESOURCE_CONTRACT"` 是独立的 OR 条件。只要 LLM 错误地设了 `construct_target`，planner 就会上当。

## 推荐修复方向

### 短期（planner 防御性加固，不改 LLM prompt）

在 `ResourceContractPlanner._contract_annotations()` 中收紧规则二：

```python
# 规则二：construct_target == "RESOURCE_CONTRACT" 时，
# semantic_role 必须是 contract 语义族的才接受
if ann.construct_target == "RESOURCE_CONTRACT":
    if ann.semantic_role in ("input_contract", "output_contract"):
        result.append(ann)
    # else: 拒绝——construct_target 与 semantic_role 不一致
```

**优点**：一行代码，确定性防御，不影响 LLM 行为  
**缺点**：不解决 Stage 2 LLM 输出本身的错误

### 中期（Stage 2 LLM prompt 约束强化）

在 Stage 2 的 system prompt 或 user prompt 中添加约束：

```
construct_target MUST be consistent with semantic_role:
- If semantic_role is profile_domain or profile_* → construct_target must NOT be RESOURCE_CONTRACT
- If semantic_role is input_contract or output_contract → construct_target must be RESOURCE_CONTRACT
```

**优点**：从源头减少错误  
**缺点**：prompt 修改需要回归测试，且 LLM 输出不完全可控

### 长期（deterministic post-hoc validator）

在 Stage 2 输出后添加 deterministic schema validator：

```python
_INCONSISTENT_PAIRS = {
    ("profile_domain", "RESOURCE_CONTRACT"),
    ("failure_mode", "RESOURCE_CONTRACT"),
    # ... 更多禁止组合
}

def _validate_annotation_consistency(ann: RouteAnnotation) -> bool:
    key = (ann.semantic_role, ann.construct_target)
    return key not in _INCONSISTENT_PAIRS
```

**优点**：全面、可扩展、不依赖 LLM  
**缺点**：需要枚举所有禁止组合，维护成本高

## 建议的下一步

1. **立即**：在 `ResourceContractPlanner._contract_annotations()` 中实施短期修复，收紧 `construct_target == "RESOURCE_CONTRACT"` 的 semantic_role 约束
2. **本 Phase**：将此问题加入 Stage 2 route refinement diagnostic，作为 `structured_route_diagnostics` 的一项
3. **后续**：收集更多 LLM 输出样本，统计 `semantic_role` / `construct_target` 不一致的频率，决定是否需要中期 prompt 修复

## 相关文件

- `src/nl2spl/pipeline/stages/stage3_2_resource_contract_planner/planner.py` — `_contract_annotations()`
- `src/nl2spl/pipeline/stages/stage2_field_router/` — LLM refinement prompt
- `src/nl2spl/ir/field_route_ir.py` — `RouteAnnotation` 数据模型

## 关联文档

- [[stage2_llm_output_simplification]] — 从根本上解决此问题的架构方案：LLM 只输出 `semantic_role`，其余字段确定性推导
