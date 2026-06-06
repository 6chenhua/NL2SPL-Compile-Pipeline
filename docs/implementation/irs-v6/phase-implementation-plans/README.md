# IRS v6 分阶段实施计划目录

本目录用于存放 IRS v6 重构的逐阶段实施计划与进度跟踪材料。

上层文档分工：

```text
../06_irs_v6_refactor_design.md
    解释目标架构、设计模式、组件边界、兼容策略和非目标。

../07_irs_v6_refactor_tasks.md
    定义 R0-R9 总任务拆分、验收标准和测试矩阵。

phase-implementation-plans/
    为每个阶段补充更细的实施计划、审核清单和进度记录槽位。
```

## 文件清单

| 文件 | 作用 |
| --- | --- |
| [R0_baseline_audit_implementation_plan.md](R0_baseline_audit_implementation_plan.md) | R0 Baseline Audit 的详细实施计划 |
| [R1_report_schema_foundation_implementation_plan.md](R1_report_schema_foundation_implementation_plan.md) | R1 Report Schema Foundation 的详细实施计划 |
| [R2_irs_v6_framework_skeleton_implementation_plan.md](R2_irs_v6_framework_skeleton_implementation_plan.md) | R2 IRS v6 Framework Skeleton 的详细实施计划 |
| [R3_diagnostic_projector_implementation_plan.md](R3_diagnostic_projector_implementation_plan.md) | R3 DiagnosticProjector 的详细实施计划 |
| [R4_worker_delegation_checker_implementation_plan.md](R4_worker_delegation_checker_implementation_plan.md) | R4 Worker/Delegation Checker 的详细实施计划 |
| [R5_runner_orchestrator_integration_implementation_plan.md](R5_runner_orchestrator_integration_implementation_plan.md) | R5 Runner Orchestrator Integration 的详细实施计划 |
| [R6_stage4_stage7_compatibility_migration_implementation_plan.md](R6_stage4_stage7_compatibility_migration_implementation_plan.md) | R6 Stage4 / Stage7 Compatibility Migration 的详细实施计划 |
| [R7_post_normalize_cleanup_implementation_plan.md](R7_post_normalize_cleanup_implementation_plan.md) | R7 Post-normalize Cleanup 的详细实施计划 |
| [R8_graph_ready_hardening_implementation_plan.md](R8_graph_ready_hardening_implementation_plan.md) | R8 Graph-ready Hardening 的详细实施计划 |
| [R9_final_audit_implementation_plan.md](R9_final_audit_implementation_plan.md) | R9 Final Audit 的详细实施计划 |
| [irs_v6_refactor_progress_tracker.html](irs_v6_refactor_progress_tracker.html) | R0-R9 重构进度跟踪 HTML |

## 审核原则

后续每个阶段提交审核时，审核必须基于真实代码逐条核验，不接受只看实施报告。

审核至少检查：

```text
1. 实际修改文件是否符合阶段允许范围。
2. 验收测试是否真实覆盖阶段目标。
3. 是否有 skip / xfail / 弱断言掩盖问题。
4. 是否改变了非本阶段允许改变的生产行为。
5. 是否引入新的 rule-based 语义判断。
6. 如果存在 LLM/rule-based 双路径选择，是否已有用户确认。
7. full test suite 或阶段要求的测试命令是否执行并通过。
```
