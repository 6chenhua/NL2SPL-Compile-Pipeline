# Adapter-Guided LLM FieldRoute Refinement 任务说明

创建日期：2026-05-24

评审角色：PM / Codex

任务性质：后续核心设计修正，不属于原 `F0-F4` 或 `D0-D8` 主线编号。

## 任务文档索引

建议按以下顺序实施：

1. [01_baseline_gap_tests.md](01_baseline_gap_tests.md)
   - 先用测试暴露当前 deterministic structural FieldRoute 的不足。
2. [02_prompt_and_schema_contract.md](02_prompt_and_schema_contract.md)
   - 定义 adapter-enriched LLM prompt 和 route-level 输出 schema。
3. [03_fieldroute_llm_refinement_path.md](03_fieldroute_llm_refinement_path.md)
   - 在 FieldRouter 中增加 adapter-guided LLM refinement 路径。
4. [04_validation_and_merge.md](04_validation_and_merge.md)
   - 增加 validator，将 LLM 输出安全合并进 `FieldRouteIR`。
5. [05_downstream_alignment_regression.md](05_downstream_alignment_regression.md)
   - 验证 Stage 4 / Stage 7 / Stage 9 / diagnostics / provenance 与新 annotations 对齐。
6. [progress_tracker.html](progress_tracker.html)
   - 本任务组专用进度跟踪表，用于记录实施证据、测试结果、审核结论和整改闭环。

## 1. 背景问题

当前重构已经完成了一个重要基础：

```text
InputAdapter -> CanonicalCompileInput
SpanSlicer -> packet-aware spans
FieldRouteIR -> RouteAnnotation
Downstream stages -> consume annotations
```

但当前 `FieldRouter` 对 structural NL 的处理仍然过于确定性。

现状是：

```text
CanonicalCompileInput(source_schema != generic_nl)
-> FieldRouter._execute_canonical()
-> 根据 packet_type / section_title 做 deterministic mapping
-> 生成 RouteAnnotation
```

也就是说，structural NL 路径目前基本不会调用 LLM。测试中也有类似：

```python
mock_client.call_json.assert_not_called()
```

这说明当前实现验证的是：

```text
InputAdapter 的 hints / packets 可以被代码消费
```

但还没有验证：

```text
InputAdapter 的 hints / packets 能帮助 LLM 做更准确的语义分析
```

这与新的设计预期不一致。

## 2. 为什么当前 deterministic FieldRoute 不够

Natural language section 并不保证语义纯净。

### 2.1 Failure handling 可能混合 condition 和 handler

例如：

```text
Failure handling:
Missing timeframe: ask one clarifying question.
If evidence is insufficient, mark the draft as assumption-bearing.
```

这里至少包含：

```text
Missing timeframe
-> exception condition

ask one clarifying question
-> explicit handler action candidate

evidence is insufficient
-> exception condition

mark the draft as assumption-bearing
-> fallback action / output status rule
```

因此不能简单认为：

```text
Failure handling section == 全部都是 EXCEPTION_FLOW.condition
```

### 2.2 Delegation policy 可能混合 worker / API / policy

例如：

```text
Delegation policy:
Use SearchAPI for source lookup.
Delegate source gathering to ResearchWorker when connectors are available.
Only delegate if returned evidence can be normalized.
Do not delegate final approval.
```

这里至少包含：

```text
Use SearchAPI for source lookup
-> API candidate / integration hint

Delegate source gathering to ResearchWorker
-> worker handoff candidate

when connectors are available
-> handoff condition

Only delegate if returned evidence can be normalized
-> delegation boundary constraint

Do not delegate final approval
-> delegation prohibition / policy
```

因此不能简单认为：

```text
Delegation policy section == 一个 non-executable delegation_intent
```

### 2.3 Reusable process 也可能混入 constraint

例如：

```text
Reusable process:
Produce a draft. Do not finalize if required slots are missing.
```

这里应被理解为：

```text
Produce a draft
-> executable process step

Do not finalize if required slots are missing
-> constraint / precondition
```

不能整体当作普通 executable behavior。

## 3. 新设计目标

新的设计原则是：

```text
InputAdapter 提供证据、提示、先验。
LLM 执行语义路由分析。
Validator 负责约束、修复、诊断。
```

不是：

```text
InputAdapter 决定最终语义。
FieldRoute 机械映射 packet_type。
```

目标架构：

```text
Structural NL
-> InputAdapter 解析 sections / packets / hard facts / compile hints
-> SpanSlicer 生成 section-aware / packet-aware spans
-> FieldRouter 构造 deterministic priors
-> FieldRouter 将 adapter-enriched routing packet 发给 LLM
-> LLM 返回 route-level semantic annotations / split recommendations / conflicts
-> deterministic validator 校验和收口
-> FieldRouteIR annotations 成为后续阶段的统一语义契约
```

关键点：

```text
adapter hints 是 priors，不是 final decisions。
LLM 只能输出 route-level JSON，不能生成 SPL。
Validator 必须阻止 hallucination / fabrication。
```

## 4. InputAdapter 的职责

InputAdapter 仍然是 schema-aware 前置理解层。

它应该负责：

- 识别 structural NL 的 section；
- 保留 `raw_sections`；
- 生成 `semantic_packets`；
- 提取安全的 `hard_facts`；
- 生成 `compile_hints`；
- 保留 section / packet / quoted_text provenance；
- 给 FieldRoute LLM 提供 routing priors。

它不应该负责：

- 决定最终 route semantics；
- 生成 SPL IR；
- 假设某个 section 内部一定语义纯净；
- 丢弃不符合 section prior 的文本；
- 直接生成 worker / API / exception flow / command。

## 5. FieldRoute 的新职责

FieldRoute 应从 deterministic router 变成：

```text
adapter-guided LLM semantic routing layer
```

它应该：

- 将 spans、sections、packets、hard facts、compile hints 打包给 LLM；
- 将 deterministic packet mapping 作为 prior 提供给 LLM；
- 要求 LLM 识别混合语义、拆分建议、多标签、冲突；
- 将 LLM 输出规范化成 `RouteAnnotation`；
- 对 LLM 输出做 deterministic validation；
- 保留旧 list 字段作为兼容 fallback；
- 当 LLM 与 adapter hints 冲突时记录 diagnostics。

它不应该：

- 直接信任 LLM 输出；
- 让 LLM 发明 span、packet、section、worker、API；
- 让 LLM 直接生成 SPL、block、step、worker、handoff；
- 把 input/output contract 路由成 executable behavior；
- 把 delegation intent 直接变成 executable handoff；
- 静默覆盖 hard facts。

## 6. LLM 输入应包含什么

FieldRoute 发送给 LLM 的 routing packet 至少应包含：

```text
span_id
span_text
source_section_id
source_packet_id
section canonical title
packet_type prior
semantic packet text
hard facts linked to section / packet / span
compile hints
deterministic prior annotation
allowed semantic roles
allowed construct targets
allowed executable status
anti-fabrication rules
```

示例：

```json
{
  "span_id": "s24",
  "text": "Missing timeframe: ask one clarifying question.",
  "source_section_id": "sec_failure_handling",
  "source_packet_id": "p_failure_mode_missing_timeframe",
  "packet_type_prior": "failure_mode",
  "deterministic_prior": {
    "semantic_role": "failure_mode",
    "construct_target": "EXCEPTION_FLOW",
    "slot_target": "condition",
    "executable": false
  },
  "compile_hints": [
    "May contain exception condition",
    "May contain explicit handler action",
    "Do not invent handler if absent"
  ],
  "allowed_roles": [
    "failure_mode",
    "exception_handler_action",
    "constraint",
    "clarification_action"
  ]
}
```

## 7. LLM 输出只能是 route-level

LLM 可以输出：

- route annotations；
- split recommendations；
- multi-label suggestions；
- route conflicts；
- route diagnostics。

LLM 不可以输出：

- SPL text；
- commands；
- blocks；
- exception flows；
- workers；
- handoffs；
- APIs that were not mentioned or declared。

示例输出：

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
      "executable": false
    }
  ],
  "split_recommendations": [
    {
      "parent_span_id": "s24",
      "reason": "condition and handler action are mixed",
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
  "diagnostics": []
}
```

## 8. Validator 必须做什么

LLM 输出进入 `FieldRouteIR` 前必须经过 validator。

Validator 至少要检查：

- annotation 引用的 `span_id` 必须存在；
- annotation 不能引用不存在的 section / packet；
- annotation 必须保留 provenance；
- field / semantic_role / construct_target / slot_target 必须在允许集合内；
- `failure_mode` 默认不能 executable；
- `exception_handler_action` 必须有明确源文本；
- `delegation_intent` 没有 valid contract 时不能 executable；
- input/output contract 不能 executable；
- LLM 不得新增 hard fact；
- LLM 与 adapter prior 冲突时必须产生 diagnostic；
- 无效 LLM 输出应降级为 safe prior，而不是进入后续阶段。

## 9. 推荐实现步骤

### Step 1: 增加当前缺陷的 baseline tests

先写测试暴露当前 deterministic routing 的不足。

必须覆盖：

1. Failure handling 同时包含 condition + handler：

```text
Failure handling:
Missing timeframe: ask one clarifying question.
```

期望：

- `Missing timeframe` 是 `EXCEPTION_FLOW.condition`；
- `ask one clarifying question` 是 handler action candidate 或 split recommendation；
- 如果没有 handler 文本，不能虚构 handler。

2. Delegation policy 混合 API / worker / policy：

```text
Delegation policy:
Use SearchAPI for source lookup.
Delegate source gathering to ResearchWorker when connectors are available.
Only delegate if returned evidence can be normalized.
Do not delegate final approval.
```

期望：

- SearchAPI 被识别为 API candidate / integration hint；
- ResearchWorker 被识别为 worker handoff candidate；
- returned evidence normalization 是 boundary constraint；
- final approval prohibition 是 policy；
- 不直接生成 executable `INVOKE_WORKER`。

3. Reusable process 混入 constraint：

```text
Reusable process:
Produce a draft. Do not finalize if required slots are missing.
```

期望：

- `Produce a draft` 是 executable process material；
- `Do not finalize...` 是 constraint / precondition。

### Step 2: 定义 adapter-enriched FieldRoute prompt

新增或修改 Stage 2 prompt。

Prompt 必须明确：

```text
Use adapter hints as priors, not final decisions.
Do not invent facts, handlers, workers, or APIs.
Split or multi-label mixed spans.
Preserve provenance.
Return route-level JSON only.
```

### Step 3: 增加可控开关

建议先加配置开关：

```text
enable_adapter_guided_fieldroute_llm = true
```

启用时：

```text
_execute_canonical()
-> build deterministic priors
-> call LLM refinement
-> validate output
-> merge into FieldRouteIR
```

关闭时：

```text
保留当前 deterministic routing fallback
```

### Step 4: 实现 validator

Validator 应独立于 prompt。

不能依赖“LLM 会听话”。

### Step 5: 更新 downstream regression tests

确保新 annotations 不破坏：

- Stage 4 exception materialization；
- Stage 5 partial skeleton；
- Stage 7 executable filtering；
- Stage 9 constraint extraction；
- D10 route-driven delegation diagnostics；
- provenance / feedback report。

## 10. 验收标准

任务通过必须满足以下条件：

1. Structural canonical FieldRoute 路径可以调用 LLM。
2. LLM prompt 包含 spans、sections、packets、hard facts、compile hints、deterministic priors。
3. deterministic packet mapping 被当作 prior，而不是最终裁决。
4. `Failure handling` 中 condition + handler 能拆分或多标签表达。
5. 只有 condition 的 `Failure handling` 仍生成 condition-only `EXCEPTION_FLOW.condition`，不虚构 handler。
6. `Delegation policy` 中 API / worker / policy 能被区分。
7. 没有 valid handoff contract 的 delegation policy 仍然 non-executable。
8. `Reusable process` 中的 constraint 不会变成普通 executable command。
9. input/output contracts 即使 wording 混乱也保持 non-executable resource contract。
10. 所有 LLM 输出进入 `FieldRouteIR` 前必须经过 validator。
11. invalid / conflicting LLM output 产生 diagnostics，不静默覆盖。
12. 每个 accepted annotation 保留 `span_id`、`source_section_id`、`source_packet_id` where available。
13. Generic NL path 仍然可用。
14. Deterministic structural fallback 在迁移期仍可用，除非已有等价测试覆盖。
15. 全量单元测试通过。

## 11. 最小测试要求

至少新增以下测试：

- `test_structural_fieldroute_calls_llm_with_adapter_evidence`
- `test_failure_handling_condition_plus_handler_split`
- `test_failure_handling_condition_only_no_fabricated_handler`
- `test_delegation_policy_api_worker_policy_mixed_semantics`
- `test_reusable_process_constraint_not_executable_command`
- `test_input_output_contracts_remain_non_executable_under_llm`
- `test_invalid_llm_annotation_rejected_with_diagnostic`
- `test_llm_cannot_reference_unknown_span`
- `test_generic_nl_fieldrouter_still_works`

推荐集成测试：

- Internal-Comms happy path 仍稳定；
- 一个 deliberately mixed structural NL 示例能正确 route；
- Stage 4 / Stage 7 / Stage 9 仍与新 annotations 对齐。

## 12. 非目标

本任务不做：

- 在 FieldRouter 中生成 SPL；
- 在 FieldRouter 中生成 worker / handoff；
- 删除 downstream materialization stages；
- 删除 bridge fallback；
- 让 LLM 成为无 validator 的唯一真相来源；
- 引入 confidence scores。

## 13. 提交审核时必须说明

提交时请包含：

1. 改动文件列表；
2. 是否新增配置开关；
3. FieldRoute LLM prompt 的输入字段摘要；
4. LLM 输出 schema；
5. validator 规则清单；
6. mixed failure handling 示例输出；
7. mixed delegation policy 示例输出；
8. downstream regression 结果；
9. 全量测试结果；
10. 仍保留 deterministic fallback 的原因或删除依据。

## 14. 审核清单

- [ ] Structural FieldRoute 路径使用 adapter-guided LLM refinement。
- [ ] Prompt 包含 adapter evidence 和 deterministic priors。
- [ ] LLM 只输出 route-level JSON。
- [ ] Validator 拒绝 fabrication 和 invalid references。
- [ ] Failure handling mixed content 能拆分或多标签。
- [ ] Delegation policy mixed content 能拆分或多标签。
- [ ] Input/output contracts 仍然 non-executable。
- [ ] Failure condition 不会变 command。
- [ ] Delegation intent 没有 contract 不会变 `INVOKE_WORKER`。
- [ ] Provenance 保留。
- [ ] 全量测试通过。
