# ResourceContractPlanner 过度设计分析

状态: Draft  
日期: 2026-06-09  
提出者: @6chenhua  
关联: [stage2_llm_construct_target_hallucination.md](stage2_llm_construct_target_hallucination.md)、[resource_contract_annotation_refactor_design.md](../design/resource_contract_annotation_refactor_design.md)

## 核心论点

**`ResourceContractPlanner` 是 `ConstructPlanner` 架构模式的错误复用。** `ConstructPlanner` 解决的是跨 span 配对问题（condition ↔ handler），这个配对逻辑 annotation 自己无法表达，所以需要 planner。`ResourceContractPlanner` 没有做任何配对——input 就是 input，output 就是 output，一个 demand 对应一个 span。它的三条规则中，两条是冗余的，一条是换了马甲的 hardcoding。

## 三条规则逐一审视

### 规则一：annotation evidence（冗余）

```python
# 从 routes.annotations 中筛选 semantic_role 匹配的 annotation
for ann in self._contract_annotations(routes):
    demand = ResourceContractDemandIR(
        demand_id=self._demand_id(direction, ann.span_id),
        direction=direction,
        evidence_text=span.text,
        source_span_ids=[ann.span_id],
        source_section_id=ann.source_section_id,
        source_packet_id=ann.source_packet_id,
        ...
    )
```

**这是纯粹的字段重映射。** `RouteAnnotation` 已经包含了 `span_id`、`source_section_id`、`source_packet_id`、`semantic_role`、`slot_target`。Stage 6 完全可以通过 `routes.get_annotations_by_role("output_contract")` 直接获取这些信息，不需要一个中间 planner 来做"收集"。

**规则一的唯一功能**：把 `RouteAnnotation` 的字段拷贝到 `ResourceContractDemandIR`。这不是"聚合"，这是"透传加改名"。

### 规则二：deterministic section evidence（换了马甲的 hardcoding）

```python
# 检查 span 的 source_section_id 是否对应 known section
if section_title in ("required outputs", "required_outputs"):
    direction = "output"
elif section_title in ("inputs for each run", "inputs_for_each_run"):
    direction = "input"
```

**这和 `StructuralNLAdapter` 的 legacy compatibility path 本质相同**：

```python
# 旧代码（adapter 层）
if title in ("inputs for each run", "inputs_for_each_run"):
    inputs = self._extract_variables(section, source="input")
    hard_facts.inputs.extend(...)
elif title in ("required outputs", "required_outputs"):
    outputs = self._extract_variables(section, source="output")
    hard_facts.outputs.extend(...)
```

两段代码做了同一件事：**硬编码 section 标题的语义**。区别只是旧代码在 adapter 层生成 `VariableFact`，新代码在 planner 层生成 `ResourceContractDemandIR`。形式不同，假设相同——输入一定有这些 section、section 标题的语义是确定的。

### 规则三：去重（实际价值极小）

```python
# 同一 span_id + direction 只保留一个 demand
key = (ann.span_id, direction)
if key in demands_by_key:
    # 合并 evidence_sources
    continue
```

LLM 不会对同一个 span 输出两个 `output_contract` annotation。规则二的 deterministic path 也只会为每个 span 生成一个 demand。这个去重逻辑在当前数据流中没有实际的冲突场景。

**唯一的理论价值**：规则一和规则二指向同一 span 时合并 evidence_sources——但 Stage 6 并不消费 `evidence_sources`，它只看 `demand_id` 和 `evidence_text`。

## 和 ConstructPlanner 的本质区别

`ConstructPlanner` 有独立存在的理由：

```python
# ConstructPlanner 做了一件 annotation 自己做不到的事：配对
condition_annotations = routes.get_construct_slot_candidates("EXCEPTION_FLOW", "condition")
handler_annotations = routes.get_construct_slot_candidates("EXCEPTION_FLOW", "handler")

# 通过 construct_group_id / failure_item_index / source_packet_id 配对
grouped_conditions = _group_annotations(conditions)
grouped_handlers = _group_annotations(handlers)
group_keys = sorted(set(grouped_conditions) | set(grouped_handlers))

for group_key in group_keys:
    # 同一 group 下的 condition 和 handler 配对
    # 1 condition + 1 handler → 完整 demand
    # 1 condition + 0 handler → partial skeleton demand
    # 0 condition + 1 handler → orphan handler demand
    # N conditions + M handlers → ambiguous, 生成 diagnostic
```

跨 span 配对是 annotation 层面没有表达的关系。两个 span 各自有一个 annotation，但它们之间的 "condition-of" / "handler-for" 关系不存在于单个 annotation 的字段里——它隐含在 `construct_group_id` 或 `failure_item_index` 的 metadata 中。Planner 是把这个隐含关系**显式化**。

`ResourceContractPlanner` 没有做任何配对。一个 output demand 就是一个 span，不需要和任何其他 span 关联。

## 对比表

| 维度 | ConstructPlanner | ResourceContractPlanner |
|------|-----------------|------------------------|
| 核心操作 | **跨 span 配对**（condition ↔ handler） | 字段重映射 + section 标题硬编码 |
| 是否可能用 annotation 替代 | 不能——配对关系 annotation 本身不表达 | **能**——annotation 已有全部信息 |
| 是否存在 section 标题硬编码 | 不依赖 section 标题 | 依赖 `Required Outputs` / `Inputs for each run` |
| 去重价值 | 一对多/多对多配对时有实际去重 | 几乎为零 |
| 为什么存在 | 解决 annotation 无法表达的配对语义 | **架构模式惯性**——照搬了 ConstructPlanner 的结构 |

## 它也没有解决类型提取问题

`ResourceContractPlanner` 的设计前提是：**把类型判断推迟到 Stage 6，让 LLM 看到完整原文后决定。** 但推迟不等于解决。

以 demo 中的 `Status flag` 为例：

```
Required Outputs:
- Status flag (values: 'drafting', 'ready for review', 'approved')
```

### 经过整个新链路后的结果

**第一次 demo 运行**（更新的 Stage 6 prompt）：

```spl
[DEFINE_VARIABLES:]
    "Current drafting status." status_flag: enum
```

正确识别为 enum。✅

**第二次 demo 运行**：

```spl
[DEFINE_VARIABLES:]
    "Current status of the draft." status_flag: text
```

退化为 text。❌

### 问题根源

`status_flag` 的 enum 判断完全依赖 **Stage 6 LLM 能不能在单次调用中稳定识别 `values: 'drafting', 'ready for review', 'approved'` 是一个枚举定义**。没有任何确定性代码做兜底：

- `ResourceContractPlanner` 不分析类型——它只传递原文 `evidence_text`
- Stage 6 prompt 有 enum 推断规则（"Finite set of named states → enum"），但 LLM 输出不稳定
- 没有 post-hoc validator 检查"原文明确列出了枚举值，但 LLM 输出了 `text`"

**这和 `finished_draft` 的问题是同一类**——关键的类型/kind 判断完全依赖 LLM 单次调用的输出质量。换了一层 planner 只是把硬编码从 adapter 移到了 prompt 里，并没有改变"LLM 不稳定时没有兜底"这个根本问题。

### 真正需要的：deterministic type validator

不是在 planner 里做类型推断（那是 adapter 旧错误的重复），而是在 Stage 6 LLM 输出之后加一层确定性校验：

```python
# 伪代码：post-Stage6 deterministic type validator
if "values:" in evidence_text and llm_output.data_type == "text":
    warn("原文明确列出枚举值，但 LLM 输出为 text，可能存在类型降级")

if any(kw in evidence_text.lower() for kw in ["word", "google doc", "pdf"]) \
   and llm_output.resource_kind == "variable":
    warn("原文描述文档产物，但 LLM 输出 resource_kind=variable，可能存在 kind 降级")
```

**Planner 层加再多中间 artifact，也不如 Stage 6 输出后加一层确定性校验来得有效。** 前者只是重新组织了 LLM 的输入，后者才是真正抓住了 LLM 输出的错误。

## 正确的做法

**去掉 ResourceContractPlanner，让 Stage 6 直接消费 annotation。**

### 当前链路（多一层无用的 planner）

```
RouteAnnotation → ResourceContractPlanner → ResourceContractDemandIR → Stage 6
                   ↑ 纯字段重映射 + section 标题硬编码
```

### 建议链路（去掉 planner）

```
RouteAnnotation → Stage 6 context builder → Stage 6 LLM
                   ↑ 直接列举 output_contract / input_contract annotation 的 span 原文
```

Stage 6 context builder 只需要加一小段逻辑：

```python
def _build_contract_annotations_section(routes: FieldRouteIR, spans: list[SpanIR]) -> str:
    """直接从 annotation 中提取 resource contract evidence，不需要 planner 中间层。"""
    contract_anns = [
        a for a in routes.annotations
        if a.semantic_role in ("input_contract", "output_contract")
    ]
    if not contract_anns:
        return "Resource contract annotations\n- none"

    span_by_id = {s.span_id: s for s in spans}
    lines = ["Resource contract annotations (from Stage 2)"]
    for ann in contract_anns:
        span = span_by_id.get(ann.span_id)
        text = span.text if span else "(no span text)"
        lines.append(
            f"- direction={ann.slot_target}, span={ann.span_id}, "
            f"text=\"{text[:200]}\", "
            f"section={ann.source_section_id}, packet={ann.source_packet_id}"
        )
    return "\n".join(lines)
```

### 对于"LLM 漏标"的兜底

规则二的真正价值是兜底：当 Stage 2 LLM 没有输出 `output_contract` annotation 时，仍然能从 section 标题知道这里有 output demand。

但这个兜底**不需要一个独立的 planner stage**。两种更轻量的方案：

**方案 A**：在 Stage 6 context builder 里直接列出所有 section 标题和 packet 文本，让 LLM 自己判断哪些是 resource contract——不硬编码 section 语义。

**方案 B**：在 Stage 2 的 structural prior 中已经标记了 `suggested_semantic_role=output_contract`（见 `conftest.py` mock priors）——直接把这些 prior 透传给 Stage 6，不需要额外处理。

**方案 C**：改进 Stage 2 LLM prompt，降低漏标率。漏标本身是 LLM 质量问题，不应该用一个确定性 planner 来掩盖。

## 历史原因

`ResourceContractPlanner` 的设计来自重构设计文档 v1.2 的 4.3 节：

> 它的职责是把 span-level route evidence 聚合为稳定的 source-demanded resource contract instances。

设计文档在 `RouteAnnotation` 不够可靠的前提下，选择了一个中间 artifact 作为稳定层。但问题在于：

1. 这个中间层只是把 annotation 字段重命名，没有增加任何新的语义信息
2. 确定性 section 证据（规则二）等价于 adapter 层的 hardcoding，换了个位置而已
3. 如果 annotation 真的不可靠，应该修复 annotation（prompt 改进 + deterministic validator），而不是加一层透传

## 建议

1. **短期但不改代码**：本分析作为设计决策记录，标记此 planner 的模式复用有问题
2. **中期**：在 Stage 6 context builder 中直接读取 annotation 和 span，不再经过 planner
3. **长期**：删除 `ResourceContractPlanner` 和 `ResourceContractPlanIR`，简化为 annotation → Stage 6 的直达链路。`ContractFieldIR.contract_demand_id` 可以直接引用 `span_id` + `semantic_role` 组合，不需要独立的 demand_id

`ResourceContractPlanIR` 的 checkpoint（`stage3_2_resource_contract_plan.json`）有一定的调试价值——可以快速看到 pipeline 认定哪些 input/output demand 存在。如果删掉 planner，可以在 Stage 6 执行前单独保存一份 annotation 的 contract 子集作为替代。

## 相关文档

- [[stage2_llm_construct_target_hallucination]] — annotation 质量问题的具体实例
- [[stage2_llm_output_simplification]] — 如果 annotation 只用 2-3 字段，planner 的"字段重映射"价值进一步降低
- [[resource_contract_annotation_refactor_design]] — 原始设计文档，本分析质疑其中 4.3 节的设计
