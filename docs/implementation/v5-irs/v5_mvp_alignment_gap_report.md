# v5 IRS MVP 未对齐实现审计

日期：2026-05-18

对照文档：`docs/nl_2_spl_compiler_architecture_irs_v_5 (1).md`

本文只记录 **MVP/v5 阶段明确要求交付或验收**、但当前实现尚未与设计文档对齐的内容。`MAIN_WORKER` 等全量设计但未列入 v5 必交范围的内容不纳入本报告的主要 gap。

---

## 1. 范围判定

### 1.1 纳入 MVP/v5 gap 的依据

以下文档段落共同定义了本报告的判定口径：

- §7.2 / §8.1 / §8.3 Phase 6：`Semantic conflict` 暂用 LLM analyzer，不实现 rule-based。
- §7.3 / §7.4 / §7.5 / §9.1：复杂分析能力可以不完整实现，但需要保留 Protocol / Analyzer 接口。
- §15.4：Diagnostic dedup key 必须包含 missing slot 信息。
- §15.6：`CALL_API` IRS 必须区分 integration mention 与 executable API call，并收窄 source signals。
- §15.10：列出 v5 新增 analyzer 文件关系。
- §15.12：追加验收标准，包括 stage-local diagnostic dedup、Gate 后 `missing_handler` 覆盖、LLMConflictAnalyzer evidence-bound 输出等。

### 1.2 不纳入本报告的全量设计 gap

以下问题属于全量设计或后续批次，不作为 MVP 未对齐项主线记录：

- `MAIN_WORKER` ConstructIRS 缺失：§4.2 定义了完整 IRS，但 §8.1 v5 目标列举的 construct 不包含 `MAIN_WORKER`。
- 全量 UseDefAnalyzer / 完整 WorkerGraphValidator：§8.2 明确 v5 不实现完整版本；但接口预留仍属于 MVP 范围。
- 所有 Stage output schema 全量改造：§8.2 明确不重写所有 Stage，§15.11 要求保持 public schema 不变。

---

## 2. MVP 未对齐项一览

| ID | Gap | 文档依据 | 当前状态 | 严重度 |
| --- | --- | --- | --- | --- |
| MVP-GAP-01 | DataFlow / Redundancy / WorkerGraph analyzer 接口文件缺失 | §7.3 / §7.4 / §7.5 / §9.1 / §15.10 | 文件不存在 | 中 |
| MVP-GAP-02 | `LLMSemanticConflictAnalyzer` 是 stub，没有调用 LLM | §7.2 / §8.1 / Phase 6 / §15.8 | flag 打开后仍返回空列表 | 高 |
| MVP-GAP-03 | Diagnostic dedup key 缺少 `missing_slot.slot_name` | §15.4 / §15.12 | 只按 kind、target_ref、span_ids 去重 | 中 |
| MVP-GAP-04 | `CALL_API.source_signals` 未按 §15.6 收窄 | §15.6 / §15.12 | 仍包含 mention/context 信号 | 低 |
| MVP-GAP-05 | Gate 后 `missing_handler` 覆盖机制未形成完整闭环 | §15.4 / §15.12 | 当前没有显式覆盖 pre-gate 误判机制 | 低-中 |

---

## 3. MVP-GAP-01：Analyzer Protocol / placeholder 文件缺失

### 3.1 设计要求

§9.1 的原则是：

- 所有 MVP 中由 LLM prompt 完成或未来可 rule-based 化的分析模块，都必须有明确 Protocol / interface。
- LLM 实现类与未来 rule-based 实现类共用同一接口。
- Stage 9.5 只消费接口输出，不关心背后是 LLM 还是 rule-based。

§7.3 明确给出 `DataFlowAnalyzer(Protocol)` 和 `NoOpDataFlowAnalyzer` 的 MVP 形态。

§7.4 明确要求保留 `RequirementRedundancyAnalyzer(Protocol)`。

§7.5 明确要求保留 `WorkerGraphValidator(Protocol)`，并给出 `MinimalWorkerGraphValidator` MVP 形态。

§15.10 明确列出新增文件：

- `src/nl2spl/compiler/analyzers/dataflow.py`
- `src/nl2spl/compiler/analyzers/redundancy.py`

### 3.2 当前实现

当前 analyzer 目录只有：

- `src/nl2spl/compiler/analyzers/semantic_conflict.py`
- `src/nl2spl/compiler/analyzers/__init__.py`

以下文件不存在：

- `src/nl2spl/compiler/analyzers/dataflow.py`
- `src/nl2spl/compiler/analyzers/redundancy.py`
- `src/nl2spl/compiler/analyzers/worker_graph_validator.py`

`src/nl2spl/compiler/analyzers/__init__.py` 也只导出 semantic conflict 相关接口，没有导出 DataFlow / Redundancy / WorkerGraph analyzer。

### 3.3 影响

- 设计文档要求的 “prompt-first, code-ready” 接口预留没有落地。
- 未来添加 rule-based / LLM-assisted 实现时缺少稳定接入点。
- Stage 9.5 后续统一消费 analyzer 输出的目标没有被完整建模。

### 3.4 建议修复

新增三个轻量文件，保持 no-op 行为，不改变 pipeline 输出：

- `dataflow.py`
  - `DataFlowAnalysisContext`
  - `DataFlowAnalyzer(Protocol)`
  - `NoOpDataFlowAnalyzer`

- `redundancy.py`
  - `RedundancyAnalysisContext`
  - `RequirementRedundancyAnalyzer(Protocol)`
  - `NoOpRequirementRedundancyAnalyzer`

- `worker_graph_validator.py`
  - `WorkerGraphValidationContext`
  - `WorkerGraphValidator(Protocol)`
  - `MinimalWorkerGraphValidator`

同时更新 `analyzers/__init__.py`，导出这些接口和 no-op 实现。

### 3.5 验收建议

- 单元测试确认三个 Protocol / no-op 类可导入。
- no-op analyzer 默认返回 `[]`，不改变现有 v4/v5 行为。
- `analyzers.__all__` 包含新增接口。

---

## 4. MVP-GAP-02：`LLMSemanticConflictAnalyzer` 未调用 LLM

### 4.1 设计要求

§7.2 要求 MVP 使用 LLM prompt 做笼统 conflict 判断。

§8.1 v5 目标第 6 条要求：

- Semantic conflict 暂用 LLM analyzer，不实现 rule-based。

§8.3 Phase 6 要求实现：

- `LLMSemanticConflictAnalyzer`
- 输出 `CompileDiagnostic`
- 不直接修改 IR
- 默认 severity 为 warning / info
- 保留 RuleBasedSemanticConflictAnalyzer 接口位置

§15.8 进一步要求 LLMConflictAnalyzer 输出必须 evidence-bound。

### 4.2 当前实现

文件：`src/nl2spl/compiler/analyzers/semantic_conflict.py`

当前已有：

- `SemanticConflictAnalyzer(Protocol)`
- `NoOpSemanticConflictAnalyzer`
- `LLMSemanticConflictAnalyzer`
- `LLMConflictDiagnosticVerifier`

但 `LLMSemanticConflictAnalyzer.analyze()` 直接返回空列表：

```python
def analyze(...):
    # Stub: no LLM call in MVP.
    return []
```

`PROMPT` 字符串存在，但没有被传入任何 LLM client。`PipelineOrchestrator._make_semantic_conflict_analyzer()` 在 `enable_llm_conflict_analyzer=True` 时确实会返回 `LLMSemanticConflictAnalyzer()`，但由于 analyzer 本身是 stub，开关打开后行为仍等价于 NoOp。

### 4.3 影响

- §8.1 / Phase 6 的核心交付没有形成实际行为。
- `enable_llm_conflict_analyzer` flag 对结果没有实质影响。
- Phase 8 的 “LLM conflict analyzer smoke test” 只能测试 wiring / verifier，不能证明 LLM analyzer 真正工作。
- `semantic_conflict` diagnostic 在真实 pipeline 中不会由 LLM analyzer 产生。

### 4.4 建议修复

将 `LLMSemanticConflictAnalyzer` 改为显式依赖一个 LLM 调用接口，例如：

- 构造函数接受 `client` 或 `call_json` callable。
- `analyze()` 组装结构化 payload：constraints、steps、flows、symbols、source spans、worker context。
- 调用 LLM，要求返回 JSON diagnostics。
- 将返回项解析为 `CompileDiagnostic`。
- 经 `LLMConflictDiagnosticVerifier.verify()` 过滤后再进入 final diagnostics。

建议保持默认关闭：

- `PipelineConfig.enable_llm_conflict_analyzer=False`
- flag 关闭时仍使用 `NoOpSemanticConflictAnalyzer`

### 4.5 验收建议

- 单元测试：mock LLM 返回一条 evidence-bound conflict，最终产生 `semantic_conflict`。
- 单元测试：mock LLM 返回缺少 source evidence 的 conflict，被 verifier 拒绝。
- 集成测试：flag 关闭时不调用 LLM；flag 打开时调用 LLM。
- 回归测试：LLM analyzer 不修改 steps / constraints / flows / symbols。

---

## 5. MVP-GAP-03：Diagnostic dedup key 缺少 slot name

### 5.1 设计要求

§15.4 规定 dedup key：

```python
dedup_key = (
    diagnostic.kind,
    diagnostic.target_ref,
    tuple(sorted(normalize_span_ids(diagnostic.source_span_ids))),
    diagnostic.missing_slot.slot_name if diagnostic.missing_slot else diagnostic.metadata.get("missing_slot"),
)
```

该规则用于避免同一 target 上不同 slot 的 diagnostics 被误判为重复。

§15 开头说明补充规则优先级高于前文歧义表述。§15.12 也把 dedup 行为列入追加验收标准。

### 5.2 当前实现

文件：`src/nl2spl/pipeline/orchestrator.py`

当前 `_dedup_key()` 只有三项：

```python
return (
    getattr(diagnostic, "kind", ""),
    getattr(diagnostic, "target_ref", None),
    tuple(sorted(getattr(diagnostic, "source_span_ids", []) or [])),
)
```

没有读取：

- `diagnostic.missing_slot.slot_name`
- `diagnostic.metadata["missing_slot"]`
- 其他 slot-level marker

### 5.3 影响

如果同一个 construct / target_ref 上多个 slot 产生相同 kind 和 span_ids 的 diagnostic，后进入 consolidation 的 diagnostic 会被丢弃。

潜在例子：

- 同一个 `CALL_API` step 同时缺 `api_name` 和 `call_action`，都产生 `type_or_contract_ambiguity`。
- 同一个 `EXCEPTION_FLOW` 的不同 slot 未来同时产生 `missing_handler` / `type_or_contract_ambiguity` 类诊断。
- 同一 worker handoff 的 `input_bindings` 和 `output_bindings` 都不完整。

当前 Stage 7 IRS checker 为部分 diagnostics 在 `diagnostic_id` suffix 中加入 slot 名，但 dedup key 不使用 `diagnostic_id`，因此不能避免该问题。

### 5.4 建议修复

扩展 `_dedup_key()`：

```python
def _missing_slot_name(diagnostic: Any) -> str | None:
    missing_slot = getattr(diagnostic, "missing_slot", None)
    if missing_slot is not None:
        return getattr(missing_slot, "slot_name", None)
    metadata = getattr(diagnostic, "metadata", None) or {}
    return metadata.get("missing_slot")
```

然后将 slot name 作为第四维加入 key。

如果当前 `CompileDiagnostic` 没有 metadata 字段，需要先确认其 dataclass 结构，或以兼容方式使用 `getattr`。

### 5.5 验收建议

- 单元测试：同 kind / target_ref / source_span_ids、不同 `metadata["missing_slot"]` 的两条 diagnostic 都保留。
- 单元测试：完全相同 missing_slot 的重复 diagnostic 被去重。
- 回归测试：无 missing_slot 的旧 diagnostic 去重行为保持不变。

---

## 6. MVP-GAP-04：`CALL_API.source_signals` 未按 §15.6 收窄

### 6.1 设计要求

§15.6 要求 `CALL_API` 必须区分：

- integration mention
- executable API call

并明确要求 `source_signals` 缩小为：

```text
api_call_action
tool_call_action
connector_action
```

同时要求：

- `source_repository as input/context` 只能作为 resource candidate，不应自动成为 `CALL_API`。
- `named API/tool + executable action` 才能成为 `CALL_API` candidate。
- 缺少 `api_name` / `integration_evidence` / `call_action` 时，不渲染 `CALL_API`，产生 `type_or_contract_ambiguity`。

### 6.2 当前实现

文件：`src/nl2spl/compiler/construct_registry.py`

当前 `CALL_API` registry 仍使用：

```python
source_signals=["api", "tool", "connector", "source_repository", "external_system"]
```

同时实现已经添加 `call_action` slot：

```python
slot_name="call_action"
evidence_kinds=["call_action", "invoke_action"]
```

也就是说，slot 层面对 executable call 有约束，但 construct-level `source_signals` 仍包含 mention/context 类信号。

### 6.3 影响

- IRS prompt checklist 会告诉 LLM `source_repository` / `external_system` 也是 `CALL_API` source signal。
- 这与 §15.6 的 “context mention 不自动生成 CALL_API” 方向相反。
- 后置 checker / ExecutableElementGate 能降低最终渲染风险，但 prompt 端仍可能生成更多错误 candidate，增加后续诊断和过滤压力。

### 6.4 建议修复

将 `CALL_API` registry 改为：

```python
source_signals=[
    "api_call_action",
    "tool_call_action",
    "connector_action",
]
```

并考虑同步调整 `integration_evidence.evidence_kinds`：

- 保留 `api_ref` / `integration_ref` 用于 named integration。
- 将 repository/context mention 从 executable evidence 中移除，或在 notes 中明确 “context only is not executable”。

### 6.5 验收建议

- `IRSDrivenPromptBuilder.render_for_stage("stage7")` 中 `CALL_API` source signals 不包含 `source_repository`。
- context-only repository mention 不生成 renderable `CALL_API`。
- named API/tool + executable action 仍可生成 `CALL_API`。

---

## 7. MVP-GAP-05：Gate 后 `missing_handler` 覆盖机制未形成完整闭环

### 7.1 设计要求

§15.4 要求：

- Gate 后 `missing_handler` 优先级高于 Stage 4 pre-gate 判断。
- 如果 Stage 4 认为 handler 存在，但 handler step 后续被 ExecutableElementGate 过滤，则最终仍应产生 `missing_handler`。

§15.12 第 3 条也将其列为追加验收标准：

- Gate 后 `missing_handler` 能覆盖 pre-gate 误判。

### 7.2 当前实现

当前 Stage 4 IRS checker 的策略是：

- 检查 `condition` slot。
- `handler_action` 被标记为 cross-stage slot / `not_applicable`。
- Stage 4 本身不产 `handler_action` 的 `missing_handler`。

文件：`src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py`

当前 pipeline 的 diagnostics 汇总路径为：

- Stage 7 local diagnostics
- Stage 9.5 normalizer diagnostics
- semantic conflict diagnostics
- gate diagnostics
- provenance diagnostics
- delegation diagnostics
- 可选 `_consolidate_compile_diagnostics()` 合并 stage-local IRS diagnostics

文件：`src/nl2spl/pipeline/orchestrator.py`

另外，`src/nl2spl/compiler/diagnostic_analyzer.py` 中存在 `_diagnose_missing_handlers()`，其逻辑基于 post-gate `worker.steps` 判断 handler 是否 renderable。但 orchestrator 主流程当前没有直接调用 `DiagnosticAnalyzer.analyze()` 作为最终 diagnostics 汇总的一部分。

### 7.3 影响

当前实现因为 Stage 4 不做 pre-gate handler 判断，所以不太会出现 “Stage 4 已产 missing_handler 又被后续覆盖” 的重复问题。

但从验收标准看，缺少一个显式的 Gate 后重算 / 覆盖机制：

- 如果未来 Stage 4 或 Stage 7 开始产生 handler slot diagnostic，当前 consolidation 没有专门的 override 语义。
- 如果 handler step 在 Gate 前存在、Gate 后被过滤，最终是否一定产生 `missing_handler` 依赖 Stage 9.5 / 其他路径，而不是一个清晰的 post-gate authority。

### 7.4 建议修复

推荐将 Gate 后 handler 检查做成显式 final analysis pass：

1. Gate 完成后，使用 post-gate `worker.steps` / `child.steps` 重新判断每个 exception flow 是否有 renderable handler。
2. 产生 final `missing_handler` diagnostics。
3. consolidation 中以 post-gate diagnostic 为准：
   - 同 target 的 pre-gate `missing_handler` 可被替换或保留但不重复。
   - 不同 slot 的 diagnostics 不被误删，依赖 MVP-GAP-03 的 dedup key 修复。

可以复用 `DiagnosticAnalyzer._diagnose_missing_handlers()`，但需要将它接入 orchestrator 主流程，或把逻辑迁入 Stage 9.5 / post-gate final diagnostics 层。

### 7.5 验收建议

- 构造 exception flow + handler step，但 handler step 因无 source evidence 被 Gate 过滤。
- 最终 diagnostics 必须包含 `missing_handler`。
- 如果 handler step Gate 后仍 renderable，则最终不产生 `missing_handler`。
- 如果存在 pre-gate `missing_handler`，post-gate consolidation 不重复生成同一问题。

---

## 8. 建议修复优先级

### P0：先修行为开关无效问题

1. MVP-GAP-02：让 `LLMSemanticConflictAnalyzer` 在 flag 打开时真正调用 LLM，至少支持 mockable JSON path。

原因：当前 `enable_llm_conflict_analyzer=True` 与 NoOp 行为等价，属于最明显的 v5 Phase 6 功能缺口。

### P1：修接口预留和诊断正确性

2. MVP-GAP-01：补齐 analyzer Protocol / NoOp 文件。
3. MVP-GAP-03：扩展 dedup key，避免 slot-level diagnostics 被误删。

原因：这两项都是低风险、低代码量、收益明确的结构性修复。

### P2：修 prompt 语义和 post-gate 闭环

4. MVP-GAP-04：收窄 `CALL_API.source_signals`。
5. MVP-GAP-05：补 Gate 后 `missing_handler` final authority。

原因：当前已有 checker / gate 降低最终错误渲染风险，但 prompt 约束和 post-gate authority 仍应补齐，才能满足 §15 追加验收标准。

---

## 9. 建议验收清单

修复后建议至少增加或更新以下测试：

- `tests/unit/test_analyzer_interfaces.py`
  - DataFlow / Redundancy / WorkerGraph Protocol 和 NoOp 类可导入。
  - NoOp 类返回空 diagnostics。

- `tests/unit/test_semantic_conflict_analyzer.py`
  - flag 打开时 mock LLM 被调用。
  - evidence-bound diagnostic 被接受。
  - 缺 source evidence / target_ref 的 diagnostic 被拒绝。

- `tests/unit/test_diagnostic_consolidation.py`
  - dedup key 区分不同 `missing_slot`。
  - 无 `missing_slot` 的旧 diagnostic 去重行为不变。

- `tests/unit/test_irs_prompt_builder.py`
  - Stage 7 `CALL_API` source signals 不再包含 `source_repository` / `external_system`。

- `tests/integration/test_v5_irs_pipeline.py`
  - context-only repository mention 不生成 renderable `CALL_API`。
  - Gate 过滤 handler step 后最终产生 `missing_handler`。

---

## 10. 当前非 MVP gap 记录

以下项目虽然与全量设计存在差距，但不建议计入 MVP 未对齐主表：

| Gap | 原因 |
| --- | --- |
| `MAIN_WORKER` ConstructIRS 缺失 | §8.1 v5 construct 范围未列入；当前 Stage 3.5 靠专用 prompt / notes 约束 |
| 完整 UseDefAnalyzer 缺失 | §8.2 明确 v5 不实现完整 DataFlowAnalyzer / UseDefAnalyzer |
| 完整 WorkerGraphValidator 缺失 | §8.2 明确 v5 不实现完整 WorkerGraphValidator；但 Protocol / Minimal placeholder 仍应补 |
| 全量 Stage 输出 schema 改造 | §8.2 / §15.11 要求保持 public schema 不变 |

