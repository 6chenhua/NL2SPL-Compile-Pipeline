# v5 IRS MVP Gap 闭合报告

日期：2026-05-19  
基准输入：
- `docs/implementation/v5-irs/v5_mvp_alignment_gap_report.md`
- `docs/implementation/v5-irs/v5_mvp_gap_repair_plan.md`
- `docs/nl_2_spl_compiler_architecture_irs_v_5 (1).md`

---

## 1. 闭合状态

| ID | 内容 | 状态 |
|----|------|------|
| MVP-GAP-01 | Analyzer Protocol / placeholder 文件缺失 | **已闭合** |
| MVP-GAP-02 | `LLMSemanticConflictAnalyzer` stub，flag 无效 | **已闭合** |
| MVP-GAP-03 | Diagnostic dedup key 缺少 slot name | **已闭合** |
| MVP-GAP-04 | `CALL_API.source_signals` 未收窄 | **已闭合** |
| MVP-GAP-05 | Gate 后 `missing_handler` 覆盖机制未闭合 | **已闭合（Gate 已有该机制）** |

---

## 2. 逐 Phase 交付

### Phase 1: Analyzer 接口补齐

**文件**：
- 新增 `dataflow.py`、`redundancy.py`、`worker_graph_validator.py`
- 更新 `analyzers/__init__.py`（14 个符号导出）
- 新增 `tests/unit/test_analyzer_interfaces.py`（10 tests）

**行为**：零变化。所有 NoOp/minimal 实现返回 `[]`，未接入 orchestrator。

### Phase 2: Dedup key 扩展

**文件**：
- `orchestrator.py`：新增 `_missing_slot_name()` helper + `_dedup_key()` 3→4 维
- `test_diagnostic_consolidation.py`：+5 missing_slot 区分测试

**行为**：同 `(kind, target_ref, span_ids)` 但 `missing_slot.slot_name` 不同 → 两条都保留。

### Phase 3: CALL_API IRS 严格收窄

**文件**：
- `construct_registry.py`：`source_signals` → `["api_call_action", "tool_call_action", "connector_action"]`
- `construct_registry.py`：`integration_evidence.evidence_kinds` → `["api_ref", "tool_ref", "connector_ref", "integration_ref"]`
- `construct_registry.py`：`integration_evidence.notes` → 明确 `context-only mention must remain a resource candidate`
- `test_construct_registry.py`：+5 evidence_kinds / source_signals 断言
- `test_irs_prompt_builder.py`：+3 prompt 内容断言（含 case-insensitive）

**行为**：prompt checklist 不再将 `repository`/`source_repository` 暗示为 CALL_API evidence。

### Phase 4: LLMSemanticConflictAnalyzer 接入 LLM

**文件**：
- `semantic_conflict.py`：重写 `LLMSemanticConflictAnalyzer` — 注入 `call_json`，构建结构化 payload，按真实 `LLMClient.call_json` 签名调用
- `orchestrator.py`：`_make_semantic_conflict_analyzer()` 注入 `self.client.call_json`
- `test_semantic_conflict_analyzer.py`：13 mock LLM tests + 2 factory tests + strict-signature fake

**行为**：`enable_llm_conflict_analyzer=True` → 真正调用 LLM（签名：`call_json(stage_name, system_prompt, user_prompt, max_tokens=2048)`）。异常安全，`blocks_completion=False`。

### Phase 5: Post-gate missing_handler authority

**发现**：`ExecutableElementGate._post_gate_missing_handler()` 在 Gate 过滤后已做 handler 覆盖检查。无需额外 orchestrator 接线。

**文件**：
- `test_diagnostic_analyzer.py`：+2 gate-removed-handler 单元测试
- `test_v5_irs_pipeline.py`：+2 `TestPostGateMissingHandler` 集成测试

**行为**：Gate 过滤 handler step → `missing_handler` 进入 `gate_diags` → 汇入最终 diagnostics。

---

## 3. 全量验收结果

### 3.1 测试

| 层级 | 结果 |
|------|------|
| 全部单元测试 | **1154 passed** |
| 全部集成测试 | **63 passed, 4 skipped** |

### 3.2 静态检查

| 目标 | 结果 |
|------|------|
| `ruff check` 全部 touched production 文件 | **All checks passed!** |

### 3.3 Public result / dataclass field structure

`PipelineResult` / `CompileResult` / `CompileDiagnostic` / `MissingSlot` 字段结构未变化。`DiagnosticKind` Literal 新增了 `"semantic_conflict"`（设计内的诊断 kind 扩展，由 DiagnosticRegistry 注册管理）。

### 3.4 默认行为

所有新增 analyzer 默认 no-op 或 flag-off。`enable_llm_conflict_analyzer=False` 时不调用 LLM。

---

## 4. 已知预存问题

1. `test_v5_irs_pipeline.py` 16 个 E501/E702 — pre-existing，非本修复引入。
2. `pytest_cache` permission warning — 环境问题，不影响结果。

---

## 5. 结论

全部 5 个 MVP gap 已闭合。v5 IRS 的实现现在与设计文档 §8.1/§8.2 的 MVP 范围对齐。

- `enable_llm_conflict_analyzer` 开关打开后有真实行为。
- `CALL_API` prompt checklist 不再包含 context-only mention 信号。
- Dedup key 能区分不同 missing slot。
- Analyzer Protocol 接口已预留，未来 rule-based 实现有接入点。
- Gate 是 post-gate `missing_handler` 的 final authority。
