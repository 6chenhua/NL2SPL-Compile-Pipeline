# Input Adapter 架构完成设计

版本: 2.0  
日期: 2026-06-05  
状态: Current design after legacy failure path deletion

## 1. 目标

系统目标是保持 NL2SPL 与初始自然语言表达形式解耦。结构化 NL、普通 NL、模板化 NL 都应先被转换成统一的结构证据和语义路由，再进入 SPL IR 生成。

本设计的核心结论:

1. Adapter 只负责输入结构读取、字段规范化、provenance 和中性结构证据。
2. 涉及业务语义理解的任务交给 LLM semantic mapper，并由 validator fail-fast。
3. 不保留默认 fallback。LLM 调用失败或 validator reject 不应被 rule-based semantic fallback 掩盖。
4. Failure handling 的唯一主路径是 `RouteAnnotation`，不再存在 `FailureModeFact` / failure bridge 主路径。
5. Rule-based 只能处理稳定结构，不处理开放语义。

## 2. 已删除的 legacy failure path

以下 legacy 机制不再属于当前架构:

1. `FailureModeFact`
2. `HardFacts.failure_modes`
3. `bridge_failure_modes()`
4. `bridge_failure_modes_worker_scoped()`
5. adapter 直接把 section/list item 判定为 failure mode
6. orchestrator 在 Stage 4/5 后通过 hard fact bridge 补 exception flow

验收口径:

```powershell
rg -n "FailureModeFact|hard_facts\.failure_modes|bridge_failure_modes|enable_legacy_failure" src tests
```

除测试中验证“旧字段被忽略”的字符串外，不应存在生产依赖。

## 3. LLM 与 rule-based 职责边界

| 任务 | 方式 | 说明 |
|---|---|---|
| Markdown heading/list/key-value/colon pair 解析 | rule-based | 结构稳定、可复现 |
| offset、section id、packet id、pair id、source span | rule-based | 必须确定且可追踪 |
| section 标题是否表示 error/failure/delegation/policy | LLM | 属于开放语义，不应靠标题枚举 |
| `left: right` 中 left/right 的语义关系 | LLM | colon 只是结构，不代表 condition/handler |
| handler 是否可执行 | LLM + validator | LLM 判断语义，validator 检查契约 |
| 非法 LLM 输出 | fail-fast validator | 不 fallback |
| Stage 4/5/7 消费 exception semantics | RouteAnnotation only | 不读 adapter-specific semantic facts |

新增或修改这张职责表中的决策前，需要先给用户过目确认。

## 4. 当前主路径

```text
Raw NL
  ->
InputAdapter
  - parse structure
  - normalize canonical fields
  - emit neutral structural packets
  - preserve source spans and pair metadata
  ->
LLM Semantic Mapper
  - consume structural evidence
  - decide field / semantic_role / slot / executable
  - split condition and handler when needed
  ->
Route Validator
  - reject invalid fields, roles, slots, packet ids
  - reject fabricated evidence
  - fail fast on invalid mapper output
  ->
Stage 2 FieldRouter
  - materialize RouteAnnotation
  ->
Stage 4/5/7
  - assemble flow, blocks, steps from RouteAnnotation
```

Failure handling:

```text
failure condition -> field=behavior, construct=EXCEPTION_FLOW, slot=condition, executable=false
failure handler   -> field=behavior, construct=EXCEPTION_FLOW, slot=handler,   executable=true
```

## 5. Adapter 约束

Adapter 可以输出:

1. `RawSection`
2. neutral structural packets
3. list item metadata
4. key/value or colon pair metadata
5. source span and evidence ids
6. canonical input/output/delegation hard facts that are genuinely structural

Adapter 不可以输出:

1. failure semantic route prior
2. exception-flow semantic decision
3. condition/handler semantic split
4. `FailureModeFact`
5. hidden fallback facts for downstream bridges

## 6. Fail-fast 策略

LLM semantic mapper 失败时，系统应暴露错误:

1. model call failed
2. response is invalid JSON
3. response violates schema
4. response references unknown packet/span
5. response emits illegal field/role/slot/executable combination

不允许静默执行 rule-based semantic fallback。这样做的原因是 fallback 会隐藏 prompt、schema、model 输出和 validator 的真实问题，降低 MVP 阶段调试效率。

## 7. Stage 9.5 说明

当前 Stage 9.5 是 worker-scoped structural normalizer。它可以做:

1. worker-local multi-output step 结构化聚合
2. handoff/contract shape validation
3. duplicate producer structural validation
4. span ownership validation

它不应做:

1. 根据 DISPLAY_MESSAGE 文本推断 REQUEST_INPUT
2. 根据文本推断 exception semantics
3. 合成 missing output producer
4. 恢复 flat legacy semantic repair path

missing output producer 等最终 construct 诊断由 PostNormalizeIRSChecker 负责。

## 8. 验收标准

功能验收:

1. `Failure handling:` 和 `Error handling:` 均可通过 LLM route path 识别。
2. `Missing timeframe: ask user` 拆成 condition + handler。
3. condition-only failure 生成 partial exception flow，并暴露 missing handler diagnostic。
4. mixed failure bullets 不重复生成 ExceptionFlow。
5. handler 通过 item/pair metadata 与 condition 精确配对。
6. failure handling 进入 `behavior`，不进入 `rules`。

架构验收:

1. `src` 中不存在 `FailureModeFact`。
2. `HardFacts` 不包含 `failure_modes`。
3. `fact_bridges.py` 不包含 failure bridge。
4. orchestrator 不调用 failure bridge。
5. adapter 不直接生成 failure semantic hard facts。
6. Stage 4/5/7 只从 `RouteAnnotation` 消费 exception semantics。
7. LLM failure / validator reject 不触发 semantic fallback。
8. LLM vs rule-based 的职责边界变更已先让用户过目。

建议回归命令:

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\test_phase1_structure_adapter.py tests\unit\test_phase2_semantic_mapper.py tests\unit\test_phase3_fieldroute_integration.py tests\unit\test_phase4_stage4_integration.py tests\unit\test_phase5_handler_materialization.py tests\integration\test_e2e_failure_handling.py -q --basetemp=.pytest-tmp-no-legacy-smoke
```

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\test_input_adapters.py tests\unit\test_generic_nl_llm_adapter.py tests\unit\test_llm_adapter_engine_parser.py tests\unit\test_adapter_fact_verifier.py tests\integration\test_llm_adapter_engine_e2e.py -q --basetemp=.pytest-tmp-no-legacy-adapters
```

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp-no-legacy-full
```
