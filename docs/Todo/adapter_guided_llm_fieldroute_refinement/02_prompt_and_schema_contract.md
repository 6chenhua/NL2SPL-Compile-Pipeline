# 02 Prompt and Schema Contract：定义 adapter-enriched FieldRoute LLM 契约

## 目标

定义 FieldRoute structural NL refinement 的 LLM prompt 和输出 schema。

本任务重点是契约设计，不要求完整接入 `FieldRouter._execute_canonical()`。

目标是明确：

```text
InputAdapter evidence / hints / priors
-> 打包给 LLM
-> LLM 只返回 route-level semantic JSON
-> 后续 validator 可严格校验
```

## 设计原则

### 1. Adapter hints 是先验，不是最终裁决

Prompt 必须明确：

```text
Use adapter hints as priors, not final decisions.
```

例如：

```text
source_section=failure_handling
packet_type=failure_mode
```

只能说明该 span 更可能包含 exception condition，不能证明它不含 handler action。

### 2. LLM 不能生成 SPL

LLM 输出范围限制在：

- route annotations；
- split recommendations；
- conflict diagnostics；
- multi-label suggestions。

LLM 不得输出：

- SPL text；
- command；
- block；
- worker；
- handoff；
- exception flow；
- 未在输入中出现的 API。

### 3. 输出必须可验证

Schema 必须让 validator 能检查：

- span 是否存在；
- section / packet provenance 是否匹配；
- role 是否允许；
- executable 是否合理；
- 是否有 fabrication；
- 是否与 adapter prior 冲突。

## LLM 输入契约

FieldRoute 发给 LLM 的 JSON 建议包含：

```json
{
  "task": "adapter_guided_field_route_refinement",
  "source_schema": "structural_nl",
  "spans": [],
  "sections": [],
  "semantic_packets": [],
  "hard_facts": {},
  "compile_hints": {},
  "deterministic_priors": [],
  "allowed_schema": {}
}
```

### spans

每个 span 至少包含：

```json
{
  "span_id": "s24",
  "text": "Missing timeframe: ask one clarifying question.",
  "source_section_id": "sec_failure_handling",
  "source_packet_id": "p_failure_mode_missing_timeframe"
}
```

### sections

每个 section 至少包含：

```json
{
  "section_id": "sec_failure_handling",
  "canonical_title": "failure_handling",
  "original_title": "Failure handling",
  "text": "Missing timeframe: ask one clarifying question."
}
```

### semantic_packets

每个 packet 至少包含：

```json
{
  "packet_id": "p_failure_mode_missing_timeframe",
  "source_section_id": "sec_failure_handling",
  "packet_type": "failure_mode",
  "text": "Missing timeframe: ask one clarifying question.",
  "compile_targets": ["flow.exception.condition"],
  "metadata": {}
}
```

### hard_facts

只传必要字段：

```json
{
  "failure_modes": [
    {
      "name": "missing_timeframe",
      "text": "Missing timeframe",
      "evidence": [
        {
          "source_section_id": "sec_failure_handling",
          "source_packet_id": "p_failure_mode_missing_timeframe",
          "quoted_text": "Missing timeframe"
        }
      ]
    }
  ]
}
```

### deterministic_priors

由当前 deterministic mapping 生成，但标记为 prior：

```json
{
  "span_id": "s24",
  "prior_source": "packet_type=failure_mode",
  "field": "behavior",
  "semantic_role": "failure_mode",
  "route_family": "flow_relevant",
  "construct_target": "EXCEPTION_FLOW",
  "slot_target": "condition",
  "executable": false
}
```

## LLM 输出契约

建议 schema：

```json
{
  "annotations": [
    {
      "span_id": "s24",
      "field": "behavior",
      "semantic_role": "failure_mode",
      "route_family": "flow_relevant",
      "construct_target": "EXCEPTION_FLOW",
      "slot_target": "condition",
      "executable": false,
      "reason": "The text names a failure condition."
    }
  ],
  "split_recommendations": [
    {
      "parent_span_id": "s24",
      "reason": "Condition and handler action are mixed.",
      "segments": [
        {
          "text": "Missing timeframe",
          "semantic_role": "failure_mode",
          "construct_target": "EXCEPTION_FLOW",
          "slot_target": "condition",
          "executable": false
        },
        {
          "text": "ask one clarifying question",
          "semantic_role": "exception_handler_action",
          "construct_target": "EXCEPTION_FLOW",
          "slot_target": "handler",
          "executable": true
        }
      ]
    }
  ],
  "diagnostics": [
    {
      "span_id": "s30",
      "kind": "mixed_delegation_policy",
      "message": "The span contains API, worker, and boundary semantics."
    }
  ]
}
```

## Allowed Schema

Prompt 中必须列出允许值。

### field

```text
identity
audience
rules
domain
integrations
behavior
resources
```

### semantic_role

初始允许集合建议：

```text
profile_domain
input_contract
output_contract
process_step
constraint
failure_mode
exception_handler_action
delegation_intent
delegation_boundary_constraint
delegation_prohibition
api_candidate
worker_handoff_candidate
handoff_condition
integration_hint
```

### construct_target

```text
EXCEPTION_FLOW
WORKER_HANDOFF
API_CALL
RESOURCE_CONTRACT
CONSTRAINT
```

### slot_target

```text
condition
handler
input
output
target
boundary
prohibition
```

具体集合可根据现有 IR 收敛，但必须显式。

## 建议修改文件

可新增：

- `prompts/stage2_adapter_guided_system.txt`
- `prompts/stage2_adapter_guided_user_template.txt`，如果项目已有 prompt template 习惯
- `src/nl2spl/pipeline/stages/stage2_field_router.py` 中的 prompt builder helper
- 可选新增：`src/nl2spl/pipeline/stages/stage2_field_router_prompt.py`
- `tests/unit/test_field_router.py`
- `tests/unit/test_input_adapter_pipeline.py`

不建议在本任务中修改：

- downstream materializers；
- Stage 7；
- Stage 9；
- renderer；
- bridge fallback。

## 注意事项

- Prompt 必须强调 LLM 输出只到 route-level。
- Prompt 不能要求 LLM 生成 SPL。
- Prompt 不能让 LLM 新增不存在的 span。
- Prompt 必须要求保留 provenance。
- Prompt 必须说明 adapter hint 是 prior，不是最终事实。
- 输出 schema 要尽量稳定，方便 validator 和测试。
- 示例要包含 mixed failure handling 和 mixed delegation policy。

## 验收标准

本任务通过需满足：

1. 新增 adapter-guided Stage 2 prompt 或 prompt builder。
2. Prompt 输入包含 spans、sections、packets、hard facts、compile hints、deterministic priors。
3. Prompt 明确 adapter hints 是 priors。
4. Prompt 明确禁止生成 SPL / commands / workers / handoffs。
5. Prompt 明确要求 split 或 multi-label mixed spans。
6. Prompt 明确要求 provenance。
7. 输出 schema 有测试覆盖。
8. mixed failure handling 示例在 prompt 或测试中出现。
9. mixed delegation policy 示例在 prompt 或测试中出现。

## 提交审核时说明

提交时请包含：

- 新增 prompt 文件或 builder 文件；
- prompt 输入字段说明；
- LLM 输出 schema；
- anti-fabrication 规则；
- 示例输入输出；
- 测试命令和结果。
