# 04 Validation and Merge：校验 LLM 输出并合并到 FieldRouteIR

## 目标

实现 adapter-guided FieldRoute LLM 输出的 deterministic validation 和 merge。

本任务是 R3 的安全边界。没有 validator，不能把 LLM refinement 接入生产路径。

## 为什么必须有 validator

LLM 可能：

- 引用不存在的 span；
- 发明 worker / API；
- 把 input contract 变成 executable behavior；
- 把 failure condition 变成 command；
- 给 delegation intent 标 executable；
- 丢失 section / packet provenance；
- 输出不在 schema 内的 role / field / construct；
- 与 adapter hints 冲突。

这些都不能直接进入 `FieldRouteIR`。

## 输入输出

### 输入

Validator 接收：

```text
llm_result
spans
canonical_input
deterministic_priors
allowed_schema
```

### 输出

Validator 输出：

```text
validated_annotations
validated_split_recommendations
route_diagnostics
rejected_items
fallback_annotations
```

最终由 merge helper 生成：

```text
FieldRouteIR(
  old list fields,
  annotations,
  diagnostics
)
```

## 验证规则

### 1. span 存在性

每个 annotation 必须引用已有 `span_id`。

非法：

```json
{"span_id": "s999", "semantic_role": "failure_mode"}
```

处理：

```text
reject + diagnostic
```

### 2. provenance 保留

如果原 span 有：

```text
source_section_id
source_packet_id
```

accepted annotation 必须继承。

LLM 不应负责决定 provenance，validator 应从 span / packet 中补齐或校验。

### 3. field / role / construct / slot 合法

所有值必须在 allowed schema 中。

非法值应：

```text
reject + diagnostic
fallback to prior if possible
```

### 4. executable 约束

必须强制：

```text
input_contract -> executable=false
output_contract -> executable=false
failure_mode condition -> executable=false
delegation_intent without valid contract -> executable=false
constraint -> executable=false
```

只有明确源文本表达 handler action / process action 时才允许 executable。

### 5. Failure handling 特殊规则

允许：

```text
failure_mode + EXCEPTION_FLOW.condition + executable=false
exception_handler_action + EXCEPTION_FLOW.handler + executable=true
constraint / fallback_policy + executable=false
```

不允许：

```text
failure_mode + executable=true
handler action without explicit source text
fabricated handler
```

### 6. Delegation 特殊规则

允许：

```text
delegation_intent + executable=false
worker_handoff_candidate + executable=false
api_candidate + executable=false
delegation_boundary_constraint + executable=false
delegation_prohibition + executable=false
handoff_condition + executable=false
```

不允许：

```text
delegation_intent + executable=true
INVOKE_WORKER materialization in FieldRoute
CALL_API materialization in FieldRoute
unmentioned API
unmentioned worker
```

### 7. hard facts 不可被静默覆盖

LLM 可以指出：

```text
adapter hard fact may be incomplete / mixed / conflicting
```

但不能删除 hard fact。

冲突应进入 diagnostics。

## Merge 策略

建议优先级：

```text
valid LLM annotation
> deterministic prior with non-conflicting LLM enrichment
> deterministic prior fallback
```

但对于安全约束：

```text
validator hard rules > LLM annotation > adapter prior
```

例如：

```text
LLM says input_contract executable=true
```

必须改为：

```text
input_contract executable=false
diagnostic: rejected invalid executable resource contract
```

## 旧 list 字段生成

旧 list 字段应从 validated annotations 派生，或继续由 prior 保持兼容。

注意：

- executable behavior 才应进入后续 Stage 7 candidate helper；
- non-executable failure condition 可以保留在 annotations；
- 如果为了兼容仍放在 old lists，downstream 必须用 helper 排除 non-executable。

## 建议修改文件

可新增：

- `src/nl2spl/pipeline/stages/stage2_field_router_validator.py`
- `tests/unit/test_fieldroute_refinement_validator.py`

可修改：

- `src/nl2spl/pipeline/stages/stage2_field_router.py`
- `src/nl2spl/ir/field_route_ir.py`，如果需要新增 diagnostics / split recommendations 字段
- `tests/unit/test_input_adapter_pipeline.py`
- `tests/unit/test_field_router.py`

谨慎修改：

- `stage3_ambiguity_resolver.py`，仅当 split recommendations 需要接入 Stage 3；
- downstream stages，留到任务 05。

## 注意事项

- Validator 不应调用 LLM。
- Validator 规则应单元测试覆盖。
- 不要把 invalid LLM output 静默丢弃，必须有 diagnostic。
- 不要让 validator 生成新的语义事实，只能校验、修复、降级。
- `source_hint_ids` 与 `source_span_ids` 不要混用。
- 如果 LLM 输出 segment text，必须能在 parent span text 中找到或至少被标为 recommendation，不能当作真实 span。

## 验收标准

本任务通过需满足：

1. 有独立 validator 或清晰隔离的 validation helper。
2. unknown span id 被拒绝并产生 diagnostic。
3. invalid role / field / construct / slot 被拒绝。
4. executable resource contract 被强制修正或拒绝。
5. executable failure condition 被拒绝，除非明确是 handler action。
6. delegation intent without contract 保持 non-executable。
7. LLM provenance 缺失时由 span/packet 补齐或报 diagnostic。
8. LLM 与 adapter prior 冲突时 diagnostic 可见。
9. valid LLM annotation 能进入 `FieldRouteIR.annotations`。
10. deterministic fallback 在 LLM 输出无效时仍可用。

## 最小测试

至少新增：

- `test_validator_rejects_unknown_span`
- `test_validator_rejects_unknown_semantic_role`
- `test_validator_preserves_span_section_packet_provenance`
- `test_validator_rejects_executable_input_contract`
- `test_validator_rejects_executable_failure_condition`
- `test_validator_accepts_explicit_exception_handler_action`
- `test_validator_keeps_delegation_intent_non_executable_without_contract`
- `test_validator_records_prior_conflict_diagnostic`
- `test_merge_falls_back_to_prior_when_llm_invalid`

## 提交审核时说明

提交时请包含：

- validator 文件位置；
- allowed schema；
- hard validation rules；
- conflict diagnostic 示例；
- invalid LLM output 示例；
- merge 策略；
- 测试结果。
