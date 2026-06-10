# Stage 2 LLM 输出字段精简方案

状态: Draft  
日期: 2026-06-09  
提出者: @6chenhua  
关联: [stage2_llm_construct_target_hallucination.md](stage2_llm_construct_target_hallucination.md)

## 核心观点

**LLM 不应该一次生成 13 个字段。只需输出核心语义判断，其余字段由确定性映射表推导。**

## 当前问题

Stage 2 LLM 当前输出的 `RouteAnnotation` 包含 13 个字段：

```
span_id, field, semantic_role, route_family, construct_target,
slot_target, executable, primary, source_section_id, source_packet_id,
source_hint_ids, diagnostics, metadata
```

其中只有 **3 个字段** 真正需要 LLM 的语义理解能力，其余 9 个要么可以从这 3 个推导，要么已经在 adapter/span 层有了准确来源。

让 LLM 同时负责多个维度的标签，本质上是在要求它执行一个**非正交的多维分类任务**。当训练数据中的标签分布不平衡或 prompt 约束不够强时，就出现 [[stage2_llm_construct_target_hallucination]] 中记录的那种矛盾输出。

## 字段分层

### 层 1：必须 LLM 输出（需要语义理解）

| 字段 | 原因 |
|------|------|
| `span_id` | 标识被标注的 span |
| `semantic_role` | 核心语义分类——**这是 LLM 唯一需要判断的事** |
| `reason` | 人类可读的解释，辅助调试和 prompt 迭代 |

`semantic_role` 是单一维度的分类任务："这段文本在描述什么？"。这是 LLM 最擅长的事情。

可选保留 `primary`，由 LLM 标记一个 span 的主标签（一个 span 可能有多个 role）。

### 层 2：确定性推导（semantic_role → derived fields）

```python
_ROLE_TO_DERIVED: dict[str, dict[str, Any]] = {
    # ── Profile / identity ───────────────────────────
    "profile_domain": {
        "field": "domain",
        "route_family": "profile",
        "construct_target": None,
        "slot_target": None,
        "executable": False,
    },
    "profile_persona": {
        "field": "identity",
        "route_family": "profile",
        "construct_target": None,
        "slot_target": None,
        "executable": False,
    },
    "profile_audience": {
        "field": "audience",
        "route_family": "profile",
        "construct_target": None,
        "slot_target": None,
        "executable": False,
    },
    "profile_concept": {
        "field": "domain",
        "route_family": "profile",
        "construct_target": None,
        "slot_target": None,
        "executable": False,
    },

    # ── Exception / failure ───────────────────────────
    "failure_mode": {
        "field": "behavior",
        "route_family": "exception",
        "construct_target": "EXCEPTION_FLOW",
        "slot_target": "condition",
        "executable": False,
    },
    "failure_condition": {
        "field": "behavior",
        "route_family": "exception",
        "construct_target": "EXCEPTION_FLOW",
        "slot_target": "condition",
        "executable": False,
    },
    "exception_handler": {
        "field": "behavior",
        "route_family": "exception",
        "construct_target": "EXCEPTION_FLOW",
        "slot_target": "handler",
        "executable": True,
    },
    "exception_handler_action": {
        "field": "behavior",
        "route_family": "exception",
        "construct_target": "EXCEPTION_FLOW",
        "slot_target": "handler",
        "executable": True,
    },
    "failure_recovery": {
        "field": "behavior",
        "route_family": "exception",
        "construct_target": "EXCEPTION_FLOW",
        "slot_target": "handler",
        "executable": True,
    },

    # ── Process / action ──────────────────────────────
    "process_step": {
        "field": "behavior",
        "route_family": "flow_relevant",
        "construct_target": None,
        "slot_target": None,
        "executable": True,
    },
    "action": {
        "field": "behavior",
        "route_family": "flow_relevant",
        "construct_target": None,
        "slot_target": None,
        "executable": True,
    },

    # ── Resource contract ─────────────────────────────
    "input_contract": {
        "field": "resources",
        "route_family": "resource_contract",
        "construct_target": "RESOURCE_CONTRACT",
        "slot_target": "input",
        "executable": False,
    },
    "output_contract": {
        "field": "resources",
        "route_family": "resource_contract",
        "construct_target": "RESOURCE_CONTRACT",
        "slot_target": "output",
        "executable": False,
    },

    # ── Delegation ────────────────────────────────────
    "delegation_intent": {
        "field": "integrations",
        "route_family": "delegation_boundary",
        "construct_target": None,
        "slot_target": None,
        "executable": False,
    },

    # ── Rules / policies ──────────────────────────────
    "policy": {
        "field": "rules",
        "route_family": "constraint",
        "construct_target": None,
        "slot_target": None,
        "executable": False,
    },
    "constraint": {
        "field": "rules",
        "route_family": "constraint",
        "construct_target": None,
        "slot_target": None,
        "executable": False,
    },

    # ── Neutral / context ─────────────────────────────
    "neutral_context": {
        "field": "domain",
        "route_family": "context",
        "construct_target": None,
        "slot_target": None,
        "executable": False,
    },
}
```

### 层 3：来自 span / adapter context（不需要 LLM 输出）

| 字段 | 来源 |
|------|------|
| `source_section_id` | `SpanIR.source_section_id` |
| `source_packet_id` | `SpanIR.source_packet_id` |
| `source_hint_ids` | 由 deterministic layer 根据 span provenance 关联 |

### 层 4：默认值或可选项

| 字段 | 建议 |
|------|------|
| `primary` | LLM 可选输出；未输出时默认 `True` |
| `diagnostics` | 永远不由 LLM 填写——由 deterministic validator 生成 |
| `metadata` | 由 deterministic layer 注入（如 `construct_group_id`、`failure_item_index`） |

## 改造后的 LLM 输出 schema

```json
{
  "annotations": [
    {
      "span_id": "s1",
      "semantic_role": "profile_domain",
      "reason": "Names the task family as internal communications drafting."
    },
    {
      "span_id": "s11",
      "semantic_role": "output_contract",
      "reason": "Describes the finished draft as a required output artifact."
    }
  ]
}
```

**从 13 字段 → 2-3 字段。**

## 收益分析

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| LLM 输出字段数 | 13 | 2-3 |
| 跨维度矛盾 bug | 可能发生 | **不可能发生**（只有一维） |
| Token 消耗（输出侧） | ~200 tokens/span | ~50 tokens/span |
| 行为可预测性 | LLM 多标签不稳定 | derived fields 100% 确定性 |
| 新增 semantic_role | 需调 prompt + 映射表 | **只改映射表** |
| 向后兼容 | — | 现有旧格式 parser 继续工作 |

## 实施路径

### Phase A：定义映射表 + deterministic expander

1. 新建 `src/nl2spl/pipeline/stages/stage2_field_router/role_mapper.py`
2. 实现 `expand_semantic_role(span_id, semantic_role, reason, span_context) → RouteAnnotation`
3. 单元测试覆盖所有 role 的映射正确性

### Phase B：更新 Stage 2 LLM prompt

1. 修改 `prompts/stage2_*.txt`，要求 LLM 只输出 `span_id` + `semantic_role` + `reason`
2. `semantic_role` 值限定为枚举列表，减少 LLM 造词概率

### Phase C：Parser 兼容旧格式

1. Stage 2 parser 支持旧格式（直接解析完整 annotation）和新格式（parse + expand）
2. 过渡期两种格式共存，旧测试不受影响

### Phase D：切换到新格式

1. 默认使用新 prompt + expander
2. 旧格式作为 fallback（feature flag）
3. 更新相关测试

## 风险

| 风险 | 缓解 |
|------|------|
| 现有 `semantic_role` 枚举不完整 | 先收集当前所有 LLM 输出的 role 值，补全映射表 |
| `primary` 字段丢失——一个 span 可能有多个 role | 保留 `primary` 作为 LLM 可选输出，或由代码按优先级决定 |
| 某些 role 的 derived fields 确实需要 LLM 判断 | 保留 `metadata` 作为 LLM 可选附加上下文 |
| 旧 parser 依赖完整 annotation 格式 | Phase C 兼容过渡 |

## 与 ResourceContractPlanner 的交互

实施此方案后，[[stage2_llm_construct_target_hallucination]] 中描述的 `profile_domain` + `RESOURCE_CONTRACT` 矛盾**在架构层面变得不可能**——因为 `profile_domain` 的 `construct_target` 永远为 `None`，`output_contract` 的 `construct_target` 永远为 `RESOURCE_CONTRACT`。映射表只允许合法的组合。

同时，`ResourceContractPlanner._contract_annotations()` 可以简化——不再需要检查 `construct_target`，只需要检查 `semantic_role`，因为 `construct_target` 的赋值已经是确定性的了。
