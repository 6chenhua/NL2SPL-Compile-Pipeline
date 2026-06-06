# E2E Tests — 实施计划

## 目标

实现设计文档第 5.2 节要求的三个端到端测试，验证从 raw text 到 SPL 的完整 pipeline。

## 设计文档要求

1. `test_e2e_failure_condition_only` — 纯条件，验证 ExceptionFlow + missing_handler + partial SPL
2. `test_e2e_failure_condition_with_handler` — 条件+handler，验证 handler blocks + 无 missing_handler
3. `test_e2e_failure_mixed_cases` — 混合，验证只有 condition-only 触发 missing_handler

## 实施方案

使用现有 e2e 测试模式（`test_llm_adapter_engine_e2e.py`）：
- 真实 adapter + SpanSlicer（无 LLM）
- 真实 route materializer + handler materializer
- 真实 normalizer + assembler + gate + renderer
- 验证 SPL 输出、diagnostics、completeness

### 适配点

设计文档的 `result.compile()` 不存在。实际 pipeline 是：
1. `adapter.adapt(text)` → `canonical_input`
2. `slicer.execute(canonical)` → `spans`
3. `router.execute((spans, canonical))` → `routes`
4. `materialize_route_exception_flows()` → `flow`
5. `materialize_handler_blocks()` → `blocks`
6. `normalizer.normalize()` → normalized IRs
7. `assembler.assemble()` → `WorkerIR`
8. `PostNormalizeIRSChecker.check()` → diagnostics
9. `gate.apply()` → filtered worker + diagnostics
10. `renderer.render()` → SPL text
11. `compute_completeness()` → completeness status

### Handler step 的问题

设计文档期望 handler 生成可执行步骤。但当前 pipeline 中 handler blocks 只包含 span IDs，步骤需要由 Stage 7 生成。由于 e2e 测试不调用 LLM，handler steps 不会自动生成。

解决方案：在 e2e 测试中手动创建 handler steps（与现有 e2e 测试模式一致），验证 handler block 被正确创建且 flow_ref 正确。

## 文件变更

| 操作 | 文件 |
|------|------|
| 新增 | `tests/integration/test_e2e_failure_handling.py` — 3 个 e2e 测试 |
