# v5 IRS MVP Gap 修复基线

日期：2026-05-18  
用途：Phase 0 基线冻结，后续 Phase 验收均对比本文。

---

## 1. Git 状态

### 1.1 HEAD

```
55c8c7c demo: add env-based LLM config and split planner flag to usage.py
```

### 1.2 工作树

```
 M README.md
 M docs/spl_grammar.txt
 M docs/spl_nl_to_spl_design_document_v4.md
 M examples/usage.py
 M prompts/stage3_5_system.txt
 M prompts/stage3_5a_candidate_extractor_system.txt
 M prompts/stage3_5b_boundary_decision_system.txt
 M prompts/stage6_system.txt
 M src/nl2spl/adapters/generic_nl.py
 M src/nl2spl/adapters/registry.py
 M src/nl2spl/adapters/structural_nl.py
 M src/nl2spl/canonical/__init__.py
 M src/nl2spl/canonical/compile_input.py
 M src/nl2spl/compiler/__init__.py
 M src/nl2spl/compiler/compile_result.py
 M src/nl2spl/config.py
 M src/nl2spl/ir/worker_plan_ir.py
 M src/nl2spl/llm/prompts.py
 M src/nl2spl/main.py
 M src/nl2spl/pipeline/executable_gate.py
 M src/nl2spl/pipeline/orchestrator.py
 M src/nl2spl/pipeline/provenance.py
 M src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py
 M src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/materializer.py
 M src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/plan_parser.py
 M src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/planner.py
 M src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py
 M src/nl2spl/pipeline/stages/stage5_block_assembler/executor.py
 M src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py
 M src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py
 M src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py
 M src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py
 M src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py
 M src/nl2spl/pipeline/stages/stage9_5_normalizer/normalizer.py
 M src/nl2spl/pipeline/stages/stage9_5_normalizer/validation.py
 M tests/integration/test_pipeline.py
 M tests/pipeline/test_worker_aware_integration.py
 M tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py
 M tests/unit/pipeline/test_worker_aware_orchestrator.py
 M tests/unit/test_executable_gate.py
 M tests/unit/test_input_adapter_pipeline.py
 M tests/unit/test_input_adapters.py
 M tests/unit/test_normalizer.py
 M tests/unit/test_orchestrator_result.py
```

新增未跟踪文件（与 v5 IRS 相关）：

```
?? src/nl2spl/compiler/analyzers/
?? src/nl2spl/compiler/construct_registry.py
?? src/nl2spl/compiler/diagnostic_registry.py
?? src/nl2spl/compiler/irs_prompt_builder.py
?? src/nl2spl/compiler/diagnostic_analyzer.py
?? src/nl2spl/pipeline/fact_bridges.py
?? src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py
?? src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py
?? src/nl2spl/pipeline/stages/stage6_resource_extractor/resource_name_filter.py
?? src/nl2spl/pipeline/stages/stage6_resource_extractor/context_builder.py
?? src/nl2spl/pipeline/stages/stage5_block_assembler/block_postprocess.py
?? tests/unit/test_construct_registry.py
?? tests/unit/test_irs_prompt_builder.py
?? tests/unit/test_diagnostic_consolidation.py
?? tests/unit/test_diagnostic_registry.py
?? tests/unit/test_diagnostic_analyzer.py
?? tests/unit/test_semantic_conflict_analyzer.py
?? tests/unit/test_stage4_irs_exception_flow.py
?? tests/unit/test_stage7_irs_step_extraction.py
?? tests/unit/test_failure_mode_bridge.py
?? tests/unit/test_resource_extractor_hardening.py
?? tests/unit/test_stage6_resource_context_v2.py
?? tests/integration/test_v5_irs_pipeline.py
```

---

## 2. 测试结果

### 2.1 v5 IRS 核心单元测试

**命令**：
```
python -m pytest tests/unit/test_construct_registry.py tests/unit/test_irs_prompt_builder.py tests/unit/test_diagnostic_consolidation.py tests/unit/test_diagnostic_registry.py tests/unit/test_diagnostic_analyzer.py tests/unit/test_semantic_conflict_analyzer.py tests/unit/test_stage7_irs_step_extraction.py tests/unit/test_stage4_irs_exception_flow.py -v
```

**结果：277 passed, 0 failed, 1 warning（pytest cache permission, 环境问题）**

### 2.2 v5 IRS 集成测试

**命令**：
```
python -m pytest tests/integration/test_v5_irs_pipeline.py -v
```

**结果：13 passed, 0 failed**

---

## 3. 失败项

**无。** 所有 v5 IRS 相关测试通过。

---

## 4. 环境信息

- Python: 3.14.3
- OS: Windows 11 Home China 10.0.26200
- pytest: 9.0.3
- 工作目录: `C:\WorkingLocation\UGAiForge\nl2spl_improve\nl2spl`
- 分支: main

---

## 5. 已知风险

1. `pytest_cache` 权限 warning — 环境问题，不影响测试结果。
2. `test_analyzer_interfaces.py` 尚不存在 — Phase 1 会创建。
3. 当前 `LLMSemanticConflictAnalyzer` 是 stub（返回 `[]`），`test_semantic_conflict_analyzer.py` 目前测试的是 Protocol/NoOp/Verifier，不测 LLM 调用路径。Phase 4 会新增 mockable LLM 测试。

---

## 6. 基线声明

以下断言成立，后续 Phase 验收以此为基准：

- **B1**: 277 个 v5 IRS 单元测试全通过。
- **B2**: 13 个 v5 IRS 集成测试全通过。
- **B3**: `SPLConstructRegistry.default()` 包含 8 个 construct (EXCEPTION_FLOW, REQUIRED_OUTPUT, GENERAL_COMMAND, REQUEST_INPUT, CALL_API, INVOKE_WORKER, CHILD_WORKER, WORKER_CANDIDATE)。
- **B4**: `DiagnosticRegistry.default()` 包含 11 个 kind（7 enabled, 4 reserved）。
- **B5**: `_dedup_key()` 当前为 3 维 (kind, target_ref, sorted span_ids)。
- **B6**: `CALL_API.source_signals` 当前为 `["api", "tool", "connector", "source_repository", "external_system"]`。
- **B7**: `LLMSemanticConflictAnalyzer.analyze()` 当前返回 `[]`（stub）。
- **B8**: `DiagnosticAnalyzer` 存在但未接入 `PipelineOrchestrator.run()` 主流程。
- **B9**: `analyzers/` 目录只含 `semantic_conflict.py` + `__init__.py`。
