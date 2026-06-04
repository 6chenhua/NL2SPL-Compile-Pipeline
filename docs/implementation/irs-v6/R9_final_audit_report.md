# IRS v6 最终审计报告

**审计日期：** 2026-06-04
**审计范围：** R0-R9 全阶段
**全量测试：** 1835 passed, 4 skipped

---

## 1. 总体结论

IRS v6 重构目标已达成。新增 IRS checker 不需要改 orchestrator 主流程，Diagnostic 由 DiagnosticProjector 统一投影，Worker candidate 与 promotion blocked 能被结构化解释，ConstructSatisfactionReport 具备 parent/path/edge/frontier/cutline 字段，Stage 4/7/Post-normalize 兼容，Renderer 不承担 IRS 判断，Gate/ProducerIndex authority 未被替代。

---

## 2. R0-R8 阶段验收追溯

### R0 Baseline Audit

| 项目 | 证据 |
|---|---|
| 关键交付 | `tests/unit/test_irs_v6_r0_baseline.py` (42 tests) |
| Stage 4 EXCEPTION_FLOW baseline | 6 tests: condition satisfied/assumed, no missing_handler, handler_action not_applicable, worker-scoped IDs |
| Stage 7 Step IRS baseline | 8 tests: GENERAL_COMMAND/REQUEST_INPUT/CALL_API/INVOKE_WORKER, worker-scoped IDs |
| Post-normalize baseline | 6 tests: missing_handler, missing_output_producer, assumed_command, condition-only flow |
| xfail/skip | 无 xfail，无 skip |
| 未兑现 acceptance | 无 |

### R1 Report Schema Foundation

| 项目 | 证据 |
|---|---|
| 关键交付 | `src/nl2spl/compiler/irs/graph.py`, `frontier.py` |
| 测试 | `tests/unit/test_irs_v6_r1_report_schema.py` |
| ConstructEdge/ConstructGraph | 10 edge types, mutable field isolation |
| FrontierStatus/CutlineReason | Literal types with 4/5 values |
| ConstructSatisfactionReport 扩展 | parent/path/edge/frontier/cutline fields with defaults |
| xfail/skip | 无 |

### R2 IRS v6 Framework Skeleton

| 项目 | 证据 |
|---|---|
| 关键交付 | `compiler/irs/context.py`, `instance.py`, `checker.py`, `registry.py`, `runner.py`, `projector.py` |
| 测试 | `tests/unit/compiler/irs/test_r2_framework_skeleton.py` (30 tests) |
| IRSCheckContext | frozen dataclass, all fields optional |
| ConstructInstance | materialized/source_demanded/candidate_only |
| IRSChecker Protocol | extract_instances + check_instance |
| IRSCheckerRegistry | register/get_for_stage |
| IRSRunner + IRSRunResult | orchestration with projector |
| 循环导入 | lazy __getattr__ 避免 eager import |
| xfail/skip | 无 |

### R3 DiagnosticProjector

| 项目 | 证据 |
|---|---|
| 关键交付 | `compiler/irs/projector.py` (完整实现) |
| 测试 | `tests/unit/compiler/irs/test_r3_diagnostic_projector.py` (26 tests) |
| slot.diagnostic_kind → CompileDiagnostic | ✅ |
| DiagnosticRegistry severity/blocks_completion | ✅ |
| deterministic diagnostic_id (SHA1) | ✅ |
| dedup by (kind, construct_id, slot_name, sorted spans) | ✅ |
| missing_slot 结构填充 | ✅ |
| source_span_ids 不可变复制 | ✅ |
| xfail/skip | 无 |

### R4 Worker/Delegation Checker

| 项目 | 证据 |
|---|---|
| 关键交付 | `compiler/irs/checkers/worker_delegation.py` |
| 测试 | `tests/unit/compiler/irs/test_r4_worker_delegation_checker.py` (40+ tests) |
| WORKER_CANDIDATE extraction | ✅ from candidates |
| WORKER_PROMOTION readiness | ✅ decision/handoff/output_bindings |
| WORKER_HANDOFF target validation | ✅ _handoff_has_valid_target() |
| 非 worker candidate 过滤 | ✅ candidate_kind filter |
| Graph edges | promotes_to, blocked_by, handoff_to |
| xfail/skip | 无 |

### R5 Runner/Orchestrator Integration

| 项目 | 证据 |
|---|---|
| 关键交付 | `compiler/irs/factory.py`, `config.py` flags, `orchestrator.py` integration |
| 测试 | `test_r5_orchestrator_integration.py` (7), `test_r5_runner_factory.py` (8) |
| Feature flags default False | ✅ |
| Factory 隔离 concrete checker | ✅ |
| Orchestrator 写入 construct_satisfaction/stage_local_diagnostics | ✅ |
| Stage 3.5 IRS diagnostics 合入 compile_diagnostics | ✅ |
| Registry 注入 (construct_registry param) | ✅ |
| xfail/skip | 无 |

### R6 Stage4/Stage7 Compatibility Migration

| 项目 | 证据 |
|---|---|
| 关键交付 | `checkers/exception_flow.py`, `checkers/step.py`, wrapper 重写 |
| 测试 | `test_r6_exception_flow_checker.py` (16), `test_r6_step_checker.py` (19), `test_r6_stage4_stage7_baseline.py` (16), `test_r6_runner_stage4_stage7.py` (10), `test_r6_orchestrator_compatibility.py` (13) |
| Stage4ExceptionFlowIRSChecker | ✅ IRSChecker protocol |
| Stage7StepIRSChecker | ✅ 4 command types |
| Wrapper 内部改用 runner/projector | ✅ |
| diagnostic_id format: irs_{hash} | ✅ |
| missing_slot populated | ✅ |
| dict worker path support | ✅ |
| Registry validation (KeyError on missing) | ✅ |
| xfail/skip | 无 |

### R7 Post-normalize Cleanup

| 项目 | 证据 |
|---|---|
| 关键交付 | `diagnostic_analyzer.py` docstring, `final_irs_checker.py` missing_slot |
| 测试 | `test_r7_authority_baseline.py` (9), `test_final_irs_checker.py` (+5), `test_diagnostic_consolidation.py` (+4), `test_executable_gate.py` (+3) |
| DiagnosticAnalyzer legacy boundary | ✅ docstring updated |
| PostNormalizeIRSChecker missing_slot | ✅ all 4 kinds |
| Gate boundary locked | ✅ no assumed_command, no never-had-handler |
| Consolidation behavior locked | ✅ post-normalize ON suppresses stage-local |
| source_span_ids fallback | ✅ ExceptionFlowRef.spans |
| slot_name IRS alignment | ✅ handler_action not handler_step |
| xfail/skip | 无 |

### R8 Graph-ready Hardening

| 项目 | 证据 |
|---|---|
| 关键交付 | `graph.py` helpers, edge generation in 3 checkers |
| 测试 | `test_construct_graph.py` (11), `test_r8_graph_ready_hardening.py` (19) |
| ConstructEdge.key()/to_snapshot() | ✅ deterministic |
| ConstructGraph.add_edge()/deduped()/edge_snapshots() | ✅ |
| WorkerDelegation edges | promotes_to, blocked_by, handoff_to with source_span_ids |
| ExceptionFlow edges | handles condition, worker contains |
| Step edges | consumes/produces variable, invokes child/api, handoff_to |
| Canonical snapshot (spans+metadata in sort key) | ✅ |
| Mutable list isolation | ✅ each edge independent copy |
| deduped preserves isolated nodes | ✅ |
| xfail/skip | 无 |

---

## 3. Feature Flags 状态

| Flag | 默认值 | 作用 |
|---|---|---|
| `enable_irs_v6_runner` | False | IRS v6 runner 总开关 |
| `enable_irs_worker_delegation_check` | False | Stage 3.5 Worker/Delegation checker |
| `enable_irs_stage4_exception_flow_check` | False | Stage 4 exception flow IRS |
| `enable_irs_stage7_step_check` | False | Stage 7 step IRS |
| `enable_irs_post_normalize_check` | **True** | Post-normalize final authority |
| `enable_irs_diagnostic_consolidation` | False | Stage-local diagnostic merge |
| `enable_irs_prompt_builder` | False | IRS checklist in prompts |

Stage-local / v6 runner opt-in flags 默认关闭。Post-normalize final authority 默认开启。Stage 3.5 IRS 需要 `enable_irs_v6_runner=True` + `enable_irs_worker_delegation_check=True`。

---

## 4. Authority Boundary 状态

| 组件 | 职责 | IRS 是否越权 |
|---|---|---|
| Renderer | SPL 文本渲染 | 否 — 不读取 IRS 模块 |
| Gate | step-level renderability | 否 — 只发 post-gate missing_handler |
| ProducerIndex | output producer authority | 否 — IRS 不替代 |
| PostNormalizeIRSChecker | construct-level final authority | 是 — 这是 IRS 的最终权威 |
| DiagnosticAnalyzer | legacy fixture utility | 否 — 不在生产路径 |

---

## 5. Test Matrix 覆盖

| 场景 | 覆盖测试 | 层级 |
|---|---|---|
| failure condition only | test_final_irs_checker::test_exception_flow_without_handler_emits_missing_handler | PostNormalize checker |
| failure condition + handler evidence | test_flow_assembler::test_handler_action_not_materialized_as_condition | Flow assembler |
| required output no producer | test_r0_post_normalize_required_output_without_producer | R0 baseline |
| incomplete delegation | test_r9 test_worker_promotion_blocked_explained | R9 audit |
| worker candidate only | test_r4 blocked promotion tests | R4 checker |
| complete source-backed delegation | test_r4 complete promotion tests | R4 checker |
| REQUEST_INPUT without ask signal | test_r0_stage7_request_input_without_source | R0 baseline |
| CALL_API with repository mention only | test_r0_stage7_call_api_requires_integration_ref | R0 baseline |
| assumed command | test_r0_stage7_general_command_without_source | R0 baseline |
| compiler unpack without renderable producer | test_compiler_unpack_blocked_when_source_step_not_renderable | Gate |
| gate-filtered handler | test_vague_handler_gate_chain | Gate |

---

## 6. internal-comms-3 Issue 3 解释能力

IRS v6 能解释 "识别到 delegation / worker candidate，但不能晋升 child worker"：

1. **WORKER_CANDIDATE report** — `candidate_satisfaction=complete`, `renderable=False`, `frontier_status=leaf`
2. **WORKER_PROMOTION report** — `promotion_status=blocked`, `promotion_missing_slots=[promotion_input_contract, promotion_output_contract, promotion_invocation_point, promotion_result_handoff]`
3. **blocked_by edges** — 每个 missing slot 一条 `blocked_by` edge
4. **DiagnosticProjector** — 投影 `type_or_contract_ambiguity` diagnostic
5. **不生成 child worker** — 材料化行为不变

测试证据：
- `test_r9_final_audit.py::test_worker_promotion_blocked_explained` — report + blocked_by edges
- `test_r9_final_audit.py::test_diagnostic_projector_projects_promotion_diagnostics` — DiagnosticProjector 投影 type_or_contract_ambiguity + missing_slot
- `test_r9_final_audit.py::test_no_child_worker_generated_for_incomplete_delegation` — 不生成 child worker

---

## 7. Test Hygiene 审计

| 检查项 | 结果 |
|---|---|
| pytest.skip | 无 |
| pytest.mark.skip | 无 |
| pytest.mark.xfail | 无（R0 docstring 中有说明性注释，非实际 xfail） |
| 空测试 | 无 |
| 弱断言 (len > 0) | 6 处，全部作为 guard check 后跟强断言，可接受 |

---

## 8. 残余工作

| 项目 | 说明 | 优先级 |
|---|---|---|
| Recursive IRS traversal | R8 已准备 graph 数据，未实现 traversal | 后续 |
| 更多 SPL construct IRS checker | BLOCK/CONSTRAINT/RESOURCE 等 | 后续 |
| 更精细 evidence_kinds | 当前 slot 未使用 evidence_kinds 匹配 | 后续 |
| Gate missing_slot 填充 | R7 审核建议给 Gate post-gate missing_handler 也填 missing_slot | 低 |
| DiagnosticAnalyzer 完全移除 | 当前保留为 legacy utility | 低 |

---

## 9. 后续方向（非 R9）

1. **Recursive IRS traversal** — 基于 R8 ConstructGraph 实现 RecursiveIRSEvaluator
2. **更多 construct IRS** — BLOCK/CONSTRAINT/RESOURCE 等 construct 的 checker
3. **Graph visualizer** — construct graph 可视化工具
4. **Evidence kind matching** — slot 的 evidence_kinds 与 source span 的 evidence kind 匹配
5. **Stage-local → projector 统一** — PostNormalizeIRSChecker 迁移到 v6 checker + projector
