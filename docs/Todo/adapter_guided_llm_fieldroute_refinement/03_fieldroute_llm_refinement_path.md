# 03 FieldRoute LLM Refinement Path：接入 adapter-guided LLM 路径

## 目标

在 `FieldRouter` 的 structural canonical 路径中接入 adapter-guided LLM refinement。

当前路径：

```text
CanonicalCompileInput(structural_nl)
-> _execute_canonical()
-> deterministic mapping
-> FieldRouteIR
```

目标路径：

```text
CanonicalCompileInput(structural_nl)
-> _execute_canonical()
-> deterministic priors
-> adapter-enriched LLM refinement
-> validator
-> FieldRouteIR
```

## 实现策略

建议以可控开关方式渐进接入。

新增配置项，例如：

```text
enable_adapter_guided_fieldroute_llm = true / false
```

迁移期行为：

```text
false:
  使用当前 deterministic structural routing

true:
  使用 adapter-guided LLM refinement
  如果 LLM 失败或输出非法，可降级到 deterministic priors 并记录 diagnostic
```

是否默认启用由项目测试稳定性决定。初期可以默认关闭，但必须有测试覆盖开启路径。

## 建议代码结构

### FieldRouter 主流程

建议拆成几个 helper：

```python
def _execute_canonical(self, spans, canonical_input):
    priors = self._build_deterministic_priors(spans, canonical_input)
    if not self._adapter_guided_refinement_enabled():
        return self._materialize_priors(priors)

    llm_payload = self._build_adapter_guided_payload(
        spans=spans,
        canonical_input=canonical_input,
        priors=priors,
    )
    llm_result = self._call_adapter_guided_router(llm_payload)
    validated = self._validate_adapter_guided_result(
        llm_result=llm_result,
        spans=spans,
        canonical_input=canonical_input,
        priors=priors,
    )
    return self._merge_validated_routes(validated, priors)
```

### Deterministic priors

当前 `_ANNOTATION_SEMANTICS` 不应删除，而应从 final mapping 降级为 prior builder。

输出可以是内部结构或 `RouteAnnotation` 列表，但必须标记清楚来源：

```text
prior_source = packet_type / section_title / hard_fact / compile_hint
```

### LLM call

调用应使用独立 stage name 或 metadata，例如：

```python
self.client.call_json(
    stage_name="stage2_field_router_adapter_guided",
    system_prompt=...,
    user_prompt=...,
)
```

不要复用 generic NL prompt。

## LLM 失败处理

LLM 调用失败时，不应直接让整个 structural pipeline 崩溃，除非配置要求严格模式。

建议行为：

```text
LLM failure
-> fallback to deterministic priors
-> add route diagnostic: adapter_guided_refinement_failed
```

可选配置：

```text
fieldroute_llm_failure_policy = "fallback" | "raise"
```

初期建议 `fallback`。

## 与 Generic NL 路径的关系

Generic NL 路径仍可使用现有 Stage 2 LLM prompt。

不要把 adapter-guided structural prompt 混入 generic path。

目标是形成两个入口：

```text
generic_nl:
  raw spans -> generic FieldRouter LLM

structural_nl:
  adapter-enriched spans -> adapter-guided FieldRouter LLM
```

## 建议修改文件

可修改：

- `src/nl2spl/pipeline/stages/stage2_field_router.py`
- `src/nl2spl/config.py` 或相关配置定义文件
- `prompts/stage2_adapter_guided_system.txt`
- `tests/unit/test_field_router.py`
- `tests/unit/test_input_adapter_pipeline.py`

可新增：

- `src/nl2spl/pipeline/stages/stage2_field_router_prompt.py`
- `src/nl2spl/pipeline/stages/stage2_field_router_refinement.py`
- `tests/unit/test_adapter_guided_fieldroute_refinement.py`

不建议修改：

- `StructuralNLAdapter`，除非 prompt 发现现有 hints 不足；
- downstream stages；
- bridge fallback。

## 必须保留的兼容性

- 旧 `FieldRouteIR` list 字段仍可用；
- downstream 已迁移的地方继续优先使用 annotations；
- deterministic fallback 可运行；
- generic NL route tests 仍通过；
- existing Internal-Comms path 不退化。

## 注意事项

- 不要把 LLM 输出直接写入 `routes.behavior` 等旧 list；必须先验证。
- LLM 输出可以提出 split recommendations，但不一定在 Stage 2 立即改写 spans。
- 如果 split 需要真实 child spans，应交给 Stage 3 / AmbiguityResolver，或明确新增数据结构。
- 对 mixed span，annotation 可多标签，但旧 list 要避免把 non-executable 内容暴露给 Stage 7。
- 不要让 LLM 判断“是否生成 worker”；这里只能标注 worker/API candidate。

## 验收标准

本任务通过需满足：

1. 存在配置开关控制 adapter-guided FieldRoute LLM refinement。
2. 开启时，structural canonical FieldRoute 路径会调用 LLM。
3. LLM payload 包含 adapter evidence 和 deterministic priors。
4. 关闭时，当前 deterministic fallback 仍可用。
5. Generic NL 路径不受影响。
6. LLM 调用失败时有明确 fallback 或 raise 策略。
7. 相关 checkpoint / intermediate result 能记录 LLM refinement 输入摘要和输出摘要。
8. 测试覆盖开启路径和关闭路径。

## 最小测试

至少新增：

- `test_structural_fieldroute_calls_llm_when_enabled`
- `test_structural_fieldroute_does_not_call_llm_when_disabled`
- `test_adapter_guided_prompt_contains_sections_packets_hints_priors`
- `test_generic_nl_fieldrouter_still_uses_existing_path`
- `test_llm_failure_falls_back_to_deterministic_priors`

## 提交审核时说明

提交时请包含：

- 新配置项；
- 默认值；
- 开启/关闭行为；
- LLM payload 示例；
- fallback 行为；
- 测试结果。
