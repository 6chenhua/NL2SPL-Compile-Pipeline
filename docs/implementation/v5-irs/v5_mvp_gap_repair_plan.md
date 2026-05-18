# v5 IRS MVP Gap 修复计划与验收标准

日期：2026-05-18

输入文档：

- `docs/implementation/v5-irs/v5_mvp_alignment_gap_report.md`
- `docs/nl_2_spl_compiler_architecture_irs_v_5 (1).md`

本文用于指导后续分阶段修复 v5/MVP 未对齐项。每个阶段都应可独立实施、独立验收，并尽量保持 public schema 和默认运行行为兼容。

---

## 0. 总体原则

### 0.1 修复目标

完成 gap report 中 5 个 MVP 未对齐项：

| ID | 内容 |
| --- | --- |
| MVP-GAP-01 | 补齐 DataFlow / Redundancy / WorkerGraph analyzer Protocol 与 no-op/minimal 实现 |
| MVP-GAP-02 | 让 `LLMSemanticConflictAnalyzer` 在 flag 打开时真正调用 LLM |
| MVP-GAP-03 | 修复 diagnostic dedup key，区分不同 missing slot |
| MVP-GAP-04 | 收窄 `CALL_API.source_signals`，避免 context mention 污染 prompt |
| MVP-GAP-05 | 建立 Gate 后 `missing_handler` final authority / 覆盖闭环 |

### 0.2 非目标

本计划不实现以下内容：

- 不补 `MAIN_WORKER` ConstructIRS。
- 不实现完整 UseDefAnalyzer。
- 不实现完整 rule-based semantic conflict detector。
- 不实现完整 WorkerGraphValidator，只补 Protocol 与 MVP minimal/no-op 行为。
- 不改 `PipelineResult` / `CompileResult` public field schema。
- 不把 LLMConflictAnalyzer 默认打开。

### 0.3 分阶段策略

推荐顺序：

1. Phase 0：冻结基线与测试准入。
2. Phase 1：补齐 analyzer 接口预留。
3. Phase 2：修复 dedup key。
4. Phase 3：收窄 `CALL_API` IRS prompt 信号。
5. Phase 4：实现 mockable LLM semantic conflict analyzer。
6. Phase 5：补 Gate 后 `missing_handler` final authority。
7. Phase 6：MVP 全量验收与回归。

该顺序先处理低风险结构修复，再处理行为修复，最后处理跨阶段闭环。

---

## Phase 0：基线冻结与测试准入

### 目标

在正式修复前确认当前测试状态和现有行为，避免后续无法判断 regression 来源。

### 修改范围

不修改生产代码。可新增一份临时/正式基线记录文档。

建议新增：

- `docs/implementation/v5-irs/v5_mvp_gap_repair_baseline.md`

### 执行步骤

1. 记录当前工作树状态。
2. 运行与 v5 IRS 相关的单元测试。
3. 记录当前失败项。如果已有失败，标记为 pre-existing，不把它们计入后续阶段 regression。

建议命令：

```powershell
python -m pytest tests/unit/test_construct_registry.py tests/unit/test_irs_prompt_builder.py tests/unit/test_diagnostic_consolidation.py tests/unit/test_semantic_conflict_analyzer.py tests/unit/test_stage7_irs_step_extraction.py tests/unit/test_stage4_irs_exception_flow.py -q
```

如环境允许，再运行：

```powershell
python -m pytest tests/integration/test_v5_irs_pipeline.py -q
```

### 严格验收标准

Phase 0 通过必须满足：

- 已记录测试命令、结果、失败项摘要。
- 若存在失败，必须明确是修复前已存在还是由环境导致。
- 不改动生产代码。
- 不删除或改写用户已有变更。

### 退出条件

形成可引用的 baseline。后续每个 phase 的验收都必须对比该 baseline。

---

## Phase 1：补齐 Analyzer Protocol 与 no-op/minimal 实现

对应 gap：MVP-GAP-01

### 目标

满足 §7.3 / §7.4 / §7.5 / §9.1 / §15.10 的接口预留要求。默认行为必须保持 no-op，不改变 pipeline 输出。

### 修改文件

新增：

- `src/nl2spl/compiler/analyzers/dataflow.py`
- `src/nl2spl/compiler/analyzers/redundancy.py`
- `src/nl2spl/compiler/analyzers/worker_graph_validator.py`
- `tests/unit/test_analyzer_interfaces.py`

修改：

- `src/nl2spl/compiler/analyzers/__init__.py`

### 实现要求

#### `dataflow.py`

必须包含：

- `DataFlowAnalysisContext`
- `DataFlowAnalyzer(Protocol)`
- `NoOpDataFlowAnalyzer`

`NoOpDataFlowAnalyzer.analyze()` 必须返回 `[]`，不得读取环境、不得调用 LLM、不得修改输入。

#### `redundancy.py`

必须包含：

- `RedundancyAnalysisContext`
- `RequirementRedundancyAnalyzer(Protocol)`
- `NoOpRequirementRedundancyAnalyzer`

`NoOpRequirementRedundancyAnalyzer.analyze()` 必须返回 `[]`。

#### `worker_graph_validator.py`

必须包含：

- `WorkerGraphValidationContext`
- `WorkerGraphValidator(Protocol)`
- `MinimalWorkerGraphValidator`

MVP 阶段 `MinimalWorkerGraphValidator.validate()` 可以只返回 `[]`，或只做非常保守的单层 handoff 检查。若实现检查，必须只产生 `worker_graph_inconsistency`，且默认不破坏现有 pipeline。

#### `__init__.py`

必须导出新增 Protocol / context / no-op 类。

### 严格验收标准

Phase 1 通过必须满足：

- `from nl2spl.compiler.analyzers import DataFlowAnalyzer, NoOpDataFlowAnalyzer` 可成功。
- `RequirementRedundancyAnalyzer`、`NoOpRequirementRedundancyAnalyzer` 可成功导入。
- `WorkerGraphValidator`、`MinimalWorkerGraphValidator` 可成功导入。
- 三个 no-op/minimal 实现默认返回 `[]`。
- 调用 no-op/minimal 实现后，输入对象未被修改。
- 不新增 pipeline wiring，不改变 `PipelineOrchestrator.run()` 的最终 diagnostics。
- `analyzers.__all__` 包含新增导出。

### 必跑测试

```powershell
python -m pytest tests/unit/test_analyzer_interfaces.py -q
python -m pytest tests/unit/test_semantic_conflict_analyzer.py -q
```

### 回归检查

```powershell
python -m pytest tests/unit/test_diagnostic_registry.py tests/unit/test_construct_registry.py -q
```

---

## Phase 2：修复 Diagnostic Dedup Key 的 missing slot 维度

对应 gap：MVP-GAP-03

### 目标

让 Stage-local diagnostics consolidation 按 §15.4 区分不同 missing slot，避免同一 target 上不同 slot 的诊断被误删。

### 修改文件

修改：

- `src/nl2spl/pipeline/orchestrator.py`
- `tests/unit/test_diagnostic_consolidation.py`

如需要更方便构造测试，可引用：

- `nl2spl.compiler.compile_result.MissingSlot`
- `nl2spl.ir.diagnostics.CompileDiagnostic`

### 实现要求

当前 `CompileDiagnostic` 有 `missing_slot` 字段，但没有 `metadata` 字段。因此本阶段不得强制新增 metadata schema。

推荐实现：

```python
def _missing_slot_name(diagnostic: Any) -> str | None:
    missing_slot = getattr(diagnostic, "missing_slot", None)
    if missing_slot is not None:
        return getattr(missing_slot, "slot_name", None)
    metadata = getattr(diagnostic, "metadata", None)
    if isinstance(metadata, dict):
        return metadata.get("missing_slot")
    return None
```

然后 `_dedup_key()` 返回四元组：

```python
(
    kind,
    target_ref,
    sorted_source_span_ids,
    missing_slot_name,
)
```

兼容要求：

- 没有 missing slot 的旧 diagnostics，第四维为 `None`。
- span ids 仍需排序，确保 `["s1", "s2"]` 与 `["s2", "s1"]` 等价。
- 不使用 `diagnostic_id` 参与 dedup。

### 严格验收标准

Phase 2 通过必须满足：

- 同 kind / target_ref / span_ids / same missing slot 的两条 diagnostic 被去重。
- 同 kind / target_ref / span_ids / different missing slot 的两条 diagnostic 都保留。
- 无 missing slot 的旧 diagnostics 维持原有去重行为。
- span ids 顺序不影响 dedup key。
- `None target_ref` 仍可处理，不抛异常。
- 不修改 `CompileDiagnostic` dataclass 字段。

### 必跑测试

```powershell
python -m pytest tests/unit/test_diagnostic_consolidation.py -q
```

### 回归检查

```powershell
python -m pytest tests/integration/test_v5_irs_pipeline.py -q
```

---

## Phase 3：收窄 CALL_API IRS source signals

对应 gap：MVP-GAP-04

### 目标

让 Stage 7 IRS checklist 不再把 `source_repository` / `external_system` 这类 context mention 暗示为 `CALL_API` source signal，符合 §15.6。

### 修改文件

修改：

- `src/nl2spl/compiler/construct_registry.py`
- `tests/unit/test_construct_registry.py`
- `tests/unit/test_irs_prompt_builder.py`
- `tests/unit/test_stage7_irs_step_extraction.py` 如已有 snapshot / prompt 断言需要同步

### 实现要求

将 `CALL_API` 的 `source_signals` 从：

```python
["api", "tool", "connector", "source_repository", "external_system"]
```

改为：

```python
["api_call_action", "tool_call_action", "connector_action"]
```

保留 `call_action` slot。

建议同步强化 `CALL_API.description` 或 slot notes：

- context-only repository mention is not executable
- named API/tool/connector plus executable action is required

注意：本阶段只改 IRS / prompt checklist，不要求重写 Stage 7 LLM parser，也不改变 `StepIR` schema。

### 严格验收标准

Phase 3 通过必须满足：

- `SPLConstructRegistry.default().get("CALL_API").source_signals` 精确等于 `["api_call_action", "tool_call_action", "connector_action"]`。
- Stage 7 IRS prompt 中 `CONSTRUCT: CALL_API` 存在。
- Stage 7 IRS prompt 中不出现 `source_repository` 作为 CALL_API source signal。
- Stage 7 IRS prompt 中不出现 `external_system` 作为 CALL_API source signal。
- `CALL_API` 仍包含 `api_name`、`call_action`、`integration_evidence`、`response_binding` slots。
- 现有 context-only repository integration 测试仍不生成 renderable `CALL_API`。
- named API/tool + executable call action 的已有正向测试不退化。

### 必跑测试

```powershell
python -m pytest tests/unit/test_construct_registry.py tests/unit/test_irs_prompt_builder.py tests/unit/test_stage7_irs_step_extraction.py -q
```

### 回归检查

```powershell
python -m pytest tests/integration/test_v5_irs_pipeline.py -q
```

---

## Phase 4：实现 LLMSemanticConflictAnalyzer MVP

对应 gap：MVP-GAP-02

### 目标

`enable_llm_conflict_analyzer=True` 时，`LLMSemanticConflictAnalyzer` 必须真正调用 LLM，并把结构化结果解析为 `CompileDiagnostic`。flag 关闭时仍完全 NoOp。

### 修改文件

修改：

- `src/nl2spl/compiler/analyzers/semantic_conflict.py`
- `src/nl2spl/pipeline/orchestrator.py`
- `tests/unit/test_semantic_conflict_analyzer.py`

可选新增：

- `tests/unit/test_semantic_conflict_prompt_payload.py`

### 设计约束

#### 默认行为

- `PipelineConfig.enable_llm_conflict_analyzer` 默认仍为 `False`。
- flag 关闭时不得调用 LLM。
- flag 打开时必须调用 LLM。

#### 依赖注入

`LLMSemanticConflictAnalyzer` 必须支持 mockable LLM 调用。推荐：

```python
class LLMSemanticConflictAnalyzer:
    def __init__(self, call_json: Callable[..., dict[str, Any]]):
        self._call_json = call_json
```

`PipelineOrchestrator._make_semantic_conflict_analyzer()` 使用：

```python
return LLMSemanticConflictAnalyzer(self.client.call_json)
```

单元测试用 fake callable 注入，不访问网络。

#### Prompt 输入

`analyze()` 需要构造结构化 JSON payload，至少包含：

- constraints：id、text/type、source spans
- steps：id、text、command_type、inputs、outputs、source spans、target refs
- flows：可序列化摘要
- symbols：变量名与 producer/consumer 摘要
- source spans：span_id/text
- worker context：如果存在 worker_plan，包含 worker ids / handoffs 摘要

不得把不可序列化对象直接传给 LLM。

#### LLM 输出 schema

MVP 输出建议固定为：

```json
{
  "diagnostics": [
    {
      "diagnostic_id": "sc_1",
      "target_ref": "step:st_1",
      "source_span_ids": ["s1"],
      "message": "Policy conflicts with the step.",
      "suggested_resolution": "Clarify whether the step is allowed.",
      "severity": "warning"
    }
  ]
}
```

解析规则：

- `kind` 强制设为 `semantic_conflict`，不要信任 LLM 输出的其他 kind。
- severity 只允许 `info` / `warning`；非法值降级为 `warning`。
- `blocks_rendering=False`。
- `blocks_completion=False`，除非未来显式配置开启。
- 缺 target_ref / source_span_ids / message 的条目丢弃或交给 verifier 拒绝。

#### Evidence verifier

保留 `LLMConflictDiagnosticVerifier`：

- LLM analyzer 产出 raw diagnostics。
- orchestrator 继续调用 verifier。
- verifier 拒绝项进入 adapter warnings，不进入 final diagnostics。

### 严格验收标准

Phase 4 通过必须满足：

- flag 关闭时 `PipelineOrchestrator` 使用 `NoOpSemanticConflictAnalyzer`。
- flag 关闭时 fake LLM callable 调用次数为 0。
- flag 打开时 `LLMSemanticConflictAnalyzer.analyze()` 调用 injected `call_json` 一次。
- mock LLM 返回 evidence-bound diagnostic 时，最终 diagnostics 包含 `semantic_conflict`。
- mock LLM 返回空 diagnostics 时，最终 diagnostics 不增加 conflict。
- mock LLM 返回 unsupported kind 时，最终 diagnostic kind 仍强制为 `semantic_conflict`，或被 verifier 拒绝；不得让未注册 kind 进入 final diagnostics。
- mock LLM 返回缺 source spans 的 diagnostic 时，被 verifier 拒绝。
- mock LLM 返回 invalid target_ref 时，被 verifier 拒绝。
- LLM analyzer 不修改传入的 constraints、steps、flows、symbols。
- LLM API 异常不得让默认关闭路径受影响；flag 打开时异常策略必须明确：
  - 推荐策略：捕获异常，返回空 diagnostics，并将 warning 交给 adapter warnings 或 logger。
  - 如果选择抛错，必须有测试覆盖并在文档中说明。

### 必跑测试

```powershell
python -m pytest tests/unit/test_semantic_conflict_analyzer.py -q
```

### 回归检查

```powershell
python -m pytest tests/unit/test_report_renderer.py tests/unit/test_feedback_report_renderer.py tests/integration/test_v5_irs_pipeline.py -q
```

---

## Phase 5：补 Gate 后 missing_handler final authority

对应 gap：MVP-GAP-05

### 目标

Gate 完成后，以 post-gate worker / child worker steps 为最终依据，重新判定 exception flow 是否有 renderable handler。最终 diagnostics 必须能覆盖 pre-gate 误判。

### 修改文件

可选方案 A：复用现有 analyzer

- 修改 `src/nl2spl/pipeline/orchestrator.py`
- 使用 `src/nl2spl/compiler/diagnostic_analyzer.py` 的 `DiagnosticAnalyzer`
- 更新 `tests/unit/test_diagnostic_analyzer.py`
- 更新 `tests/integration/test_v5_irs_pipeline.py`

可选方案 B：新增专用 post-gate helper

- 新增 `src/nl2spl/compiler/post_gate_diagnostics.py`
- 修改 `src/nl2spl/pipeline/orchestrator.py`
- 新增 `tests/unit/test_post_gate_diagnostics.py`

推荐方案 A，减少新模块。

### 实现要求

在 `ExecutableElementGate.apply()` 之后、final diagnostics 汇总之前，运行 post-gate handler analysis。

需要确保输入是 gate 后的 `worker`：

```python
worker, render_info, gate_diags = gate.apply(worker, worker_plan)
```

然后：

```python
post_gate_diags = DiagnosticAnalyzer().analyze(
    AnalyzeInput(worker=worker)
)
```

但要避免引入 DiagnosticAnalyzer 的其他规则重复执行。推荐新增更窄的方法，例如：

```python
DiagnosticAnalyzer().diagnose_missing_handlers(AnalyzeInput(worker=worker))
```

或把 `_diagnose_missing_handlers` 变成明确 public method。

### Consolidation 要求

- post-gate `missing_handler` 必须进入 final diagnostics。
- 如果存在 pre-gate 同 target 的 `missing_handler`，不得重复。
- 如果 pre-gate 判断没有 missing handler，但 Gate 后 handler step 被过滤，必须新增 post-gate `missing_handler`。
- dedup 必须依赖 Phase 2 的 slot-aware key。

### 严格验收标准

Phase 5 通过必须满足：

- Exception flow 有 condition，且 Gate 后没有任何 `s.flow_ref == exc.flow_id` 的 renderable handler step：最终 diagnostics 包含 `missing_handler`。
- Exception flow 有 condition，且 Gate 后存在 renderable handler step：最终 diagnostics 不包含该 flow 的 `missing_handler`。
- Child worker exception flow 同样适用。
- Handler step 在 Gate 前存在、Gate 后被过滤：最终 diagnostics 包含 `missing_handler`。
- Pre-gate / stage-local 已有同 target `missing_handler`：最终只保留一条。
- Empty condition_text 的 compiler-fabricated exception flow 不产生 `missing_handler`。
- `missing_handler` 的 `blocks_completion=True`、`blocks_rendering=False`。
- 不改变 ExecutableElementGate 的 renderability 裁决职责。

### 必跑测试

```powershell
python -m pytest tests/unit/test_diagnostic_analyzer.py tests/unit/test_diagnostic_consolidation.py -q
```

### 回归检查

```powershell
python -m pytest tests/integration/test_v5_irs_pipeline.py tests/integration/test_partial_spl_mvp.py -q
```

---

## Phase 6：MVP 全量验收

### 目标

确认所有 MVP gap 均关闭，且未引入 public schema regression、v4 behavior regression 或 prompt regression。

### 全量验收标准

Phase 6 通过必须满足全部条件：

#### Gap closure

- MVP-GAP-01：三个 analyzer interface 文件存在，no-op/minimal 测试通过。
- MVP-GAP-02：flag 打开时 LLMConflictAnalyzer 调用 LLM，flag 关闭时 NoOp。
- MVP-GAP-03：dedup key 区分 `missing_slot.slot_name`。
- MVP-GAP-04：`CALL_API.source_signals` 精确收窄。
- MVP-GAP-05：Gate 后 `missing_handler` final authority 生效。

#### Public schema

- `PipelineResult` 字段不变。
- `CompileResult` 字段不变。
- `CompileDiagnostic` 不新增必填字段。
- 现有调用方不需要修改输入输出 schema。

#### Default behavior

- 所有新增 analyzer 默认 no-op 或 flag-off。
- `enable_llm_conflict_analyzer=False` 时不访问 LLM。
- 非 worker-aware 路径不应因新增接口失败。

#### Diagnostics

- 所有新增 diagnostics kind 必须在 `DiagnosticRegistry` / allowed diagnostic kind 中已有或已登记。
- LLM 不能输出未注册 kind 进入 final diagnostics。
- Evidence-bound verifier 必须过滤无 source evidence 的 semantic conflict。
- `semantic_conflict` 默认不阻断 rendering，不阻断 completion。

#### Prompt

- Stage 7 IRS checklist 包含 `CALL_API`。
- Stage 7 `CALL_API` checklist 不包含 context-only source signal。
- Stage 4 / Stage 7 prompt injection flag 行为不变。

### 必跑测试组合

#### 单元测试

```powershell
python -m pytest tests/unit/test_analyzer_interfaces.py tests/unit/test_construct_registry.py tests/unit/test_irs_prompt_builder.py tests/unit/test_diagnostic_consolidation.py tests/unit/test_semantic_conflict_analyzer.py tests/unit/test_diagnostic_analyzer.py tests/unit/test_stage4_irs_exception_flow.py tests/unit/test_stage7_irs_step_extraction.py -q
```

#### 集成测试

```powershell
python -m pytest tests/integration/test_v5_irs_pipeline.py tests/integration/test_partial_spl_mvp.py -q
```

#### 建议全量回归

```powershell
python -m pytest tests -q
```

如果全量回归存在 pre-existing failure，必须在验收记录中列明：

- 失败测试名
- 是否 Phase 0 已存在
- 是否与本轮修改有关
- 后续处理建议

---

## 7. 阶段完成记录模板

每个 phase 完成后建议在 PR / commit / 验收记录中填写：

```text
Phase:
Scope:
Files changed:
Behavior changed:
Public schema changed: No
Feature flags affected:
Tests run:
Test result:
Known pre-existing failures:
Residual risk:
Next phase:
```

---

## 8. 风险与依赖

### 8.1 主要风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| LLM analyzer 引入不稳定输出 | 测试 flaky / diagnostics 不确定 | 单元测试全部 mock LLM；live LLM 只做可选验收 |
| Dedup key 变更导致 diagnostics 数量增加 | 报告中出现之前被误删的诊断 | 明确这是预期修复；测试覆盖 exact duplicate 仍去重 |
| CALL_API prompt 变化影响 Stage 7 LLM 输出 | 可能减少 CALL_API candidate | 保留 executable call 正向测试；context-only 负向测试 |
| post-gate missing_handler 与已有 Stage 9.5 diagnostics 重复 | final report 重复 warning | 依赖 Phase 2 slot-aware dedup，并增加重复测试 |
| 新 Protocol 文件未接入 pipeline | 看似无行为变化 | 这是 Phase 1 的目标；只要求 interface readiness |

### 8.2 阶段依赖

- Phase 2 应早于 Phase 5：Gate 后 `missing_handler` consolidation 依赖 slot-aware dedup。
- Phase 1 应早于 Phase 4：Semantic conflict analyzer 已有接口，但统一 analyzer 风格应先补齐。
- Phase 3 可独立执行，但建议在 Phase 4 前完成，避免 LLM prompt 仍含错误 CALL_API signal。

---

## 9. 最小可合并切片

如果需要更小 PR，可以按以下切片拆分：

1. PR-A：Phase 1，只补接口文件和 import 测试。
2. PR-B：Phase 2，只修 `_dedup_key()` 和 consolidation 测试。
3. PR-C：Phase 3，只修 `CALL_API` IRS source signals 和 prompt snapshot。
4. PR-D：Phase 4，实现 LLMConflictAnalyzer mockable call path。
5. PR-E：Phase 5，接入 post-gate `missing_handler` final check。
6. PR-F：Phase 6，全量验收文档和剩余回归修正。

每个 PR 都必须满足：

- 不混入无关 refactor。
- 不修改非本 phase 目标文件，除非测试或 import 必需。
- 有对应测试证明本 phase 的验收标准。

