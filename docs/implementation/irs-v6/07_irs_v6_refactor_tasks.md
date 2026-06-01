# IRS v6 重构任务文档

## 1. 文档定位

本文档把 `06_irs_v6_refactor_design.md` 拆解为可执行工程任务。

本文档回答：

```text
按什么顺序改？
每个阶段改哪些文件？
每个阶段验收标准是什么？
每个阶段风险是什么？
如何保证不破坏现有行为？
```

本文档不是架构解释文档。架构原则、设计模式和组件边界见 `06_irs_v6_refactor_design.md`。

## 2. 总体实施原则

```text
1. 兼容式迁移，不做一次性重写。
2. 先补接口和 schema，再迁移 checker。
3. 先用 Worker/Delegation IRS 验证 v6 扩展链路。
4. Stage 4 / Stage 7 / Post-normalize checker 后迁移。
5. 每个阶段必须有单元测试和至少一个集成路径测试。
6. 不允许通过 skip 或弱断言绕过验收。
7. 不允许 checker 调用 LLM、修改 IR、生成 construct。
```

## 3. 阶段总览

| Phase | 名称 | 目标 | 行为风险 |
| --- | --- | --- | --- |
| R0 | Baseline Audit | 锁定当前 IRS 行为与测试基线 | 无生产改动 |
| R1 | Report Schema Foundation | 扩展 `ConstructSatisfactionReport` 和 graph/frontier 类型 | 低 |
| R2 | IRS v6 Framework Skeleton | 新增 `compiler/irs/` 基础接口 | 低 |
| R3 | DiagnosticProjector | 建立 report -> diagnostic 投影链路 | 中 |
| R4 | Worker/Delegation Checker | 首个 v6-style checker 落地 | 中 |
| R5 | Runner Orchestrator Integration | 通过 runner 写入 intermediate/report | 中 |
| R6 | Stage4/Stage7 Compatibility Migration | 旧 checker 包装为 v6 checker | 中高 |
| R7 | Post-normalize Cleanup | 收敛 final IRS diagnostic authority | 中高 |
| R8 | Graph-ready Hardening | 生成 edge/path/frontier snapshot | 中 |
| R9 | Final Audit | 清理 feature flags、文档、测试矩阵 | 低 |

## 4. R0 Baseline Audit

### 目标

锁定当前 IRS 相关行为，避免后续重构无法判断是否回归。

### 可修改文件

```text
tests/unit/
docs/implementation/irs-v6/
```

不修改生产代码。

### 建议任务

```text
R0.1 记录当前 full test count。
R0.2 增加 IRS baseline 测试，覆盖 Stage 4 exception flow、Stage 7 step IRS、Post-normalize IRS。
R0.3 增加 Stage3.5 IRS checklist 当前为空的测试或审计说明。
R0.4 增加 Worker/Delegation 当前报告缺口的 xfail target tests 或 current-behavior tests。
```

### 验收标准

```text
1. 全量测试通过。
2. 没有生产代码改动。
3. 当前 Stage 4 / Stage 7 / Post-normalize 行为有 baseline 测试。
4. internal-comms-3 的 Worker promotion 解释缺口被测试或文档记录。
```

### 注意事项

不要把目标行为写成 pass 测试，除非当前实现已经满足。可使用 current-behavior + target-future 的双层测试结构。

## 5. R1 Report Schema Foundation

### 目标

扩展 IRS report schema，使现有 report 具备 v6 所需 parent/path/edge/frontier/cutline 表达能力。

### 可修改文件

```text
src/nl2spl/compiler/construct_registry.py
tests/unit/test_construct_registry.py
tests/unit/test_irs_*.py
```

### 实现思路

新增类型：

```python
ConstructEdge
FrontierStatus
```

扩展 `ConstructSatisfactionReport`：

```python
primary_parent_id: str | None = None
child_construct_ids: list[str] = field(default_factory=list)
related_edges: list[ConstructEdge] = field(default_factory=list)
construct_path: tuple[str, ...] = ()
source_span_ids: list[str] = field(default_factory=list)
source_section_id: str | None = None
source_packet_id: str | None = None
cutline_reason: str | None = None
frontier_status: str = "leaf"
metadata: dict[str, Any] = field(default_factory=dict)
```

### 验收标准

```text
1. 旧 ConstructSatisfactionReport 构造方式仍然可用。
2. Stage 4 / Stage 7 旧 checker 不需要同步大改。
3. 新字段默认值正确。
4. ConstructEdge 支持 contains / produces / consumes / invokes / handoff_to / handles / applies_to / derived_from / promotes_to / blocked_by。
5. 全量测试通过。
```

### 风险

如果 `ConstructSatisfactionReport` 被序列化到 checkpoint，新增字段可能影响 snapshot。应明确 snapshot 预期并稳定字段顺序。

## 6. R2 IRS v6 Framework Skeleton

### 目标

新增 `src/nl2spl/compiler/irs/` 子包，提供 v6 checker 接入层，但暂不迁移旧 checker。

### 可新增文件

```text
src/nl2spl/compiler/irs/__init__.py
src/nl2spl/compiler/irs/context.py
src/nl2spl/compiler/irs/instance.py
src/nl2spl/compiler/irs/graph.py
src/nl2spl/compiler/irs/checker.py
src/nl2spl/compiler/irs/registry.py
src/nl2spl/compiler/irs/runner.py
src/nl2spl/compiler/irs/projector.py
src/nl2spl/compiler/irs/frontier.py
tests/unit/compiler/irs/
```

### 实现思路

定义：

```text
IRSCheckContext
ConstructInstance
IRSChecker Protocol
IRSCheckerRegistry
IRSRunner skeleton
DiagnosticProjector skeleton
```

`IRSRunner` 可以先支持空 registry：

```text
没有 checker -> reports=[], diagnostics=[]
```

### 验收标准

```text
1. 新模块可 import。
2. 空 runner 不改变 pipeline 行为。
3. checker registry 可注册、查询、按 stage 过滤 checker。
4. ConstructInstance 必须包含 materialized/source_demanded/candidate_only。
5. checker contract 单测覆盖“不允许 checker 修改 IR”的约束至少以文档和协议体现。
6. 全量测试通过。
```

### 注意事项

此阶段不要接 orchestrator，不要改 Stage 4 / Stage 7。

## 7. R3 DiagnosticProjector

### 目标

建立统一 diagnostic 投影机制，避免 checker 直接拼装 `CompileDiagnostic`。

### 可修改文件

```text
src/nl2spl/compiler/irs/projector.py
src/nl2spl/compiler/diagnostic_registry.py
src/nl2spl/ir/diagnostics.py
tests/unit/compiler/irs/test_projector.py
```

### 实现思路

`DiagnosticProjector.project(report)`：

```text
1. 遍历 report.slots。
2. 找出 diagnostic_kind 不为空的 slot。
3. 从 DiagnosticRegistry 获取 default severity / blocks_completion / allowed targets。
4. 生成 CompileDiagnostic。
5. 生成稳定 diagnostic_id / target_ref / suggested_resolution。
```

### 验收标准

```text
1. missing_handler slot 可投影为 CompileDiagnostic(kind="missing_handler")。
2. type_or_contract_ambiguity slot 可投影。
3. source_span_ids/source_section_id/source_packet_id 可保留。
4. checker 不需要知道 severity/blocking 默认值。
5. projector 输出 deterministic id 或 deterministic dedup metadata。
6. 全量测试通过。
```

### 注意事项

不要立刻把所有旧 checker 迁移到 projector。先让新 Worker/Delegation checker 使用 projector。

## 8. R4 Worker/Delegation Checker

### 目标

实现第一个 v6-style checker，解决 Worker candidate 与 promotion readiness 的结构化报告问题。

### 可新增/修改文件

```text
src/nl2spl/compiler/irs/checkers/__init__.py
src/nl2spl/compiler/irs/checkers/worker_delegation.py
src/nl2spl/compiler/construct_registry.py
tests/unit/compiler/irs/test_worker_delegation_checker.py
tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py
```

### 实现思路

新增或完善 construct specs：

```text
WORKER_CANDIDATE
WORKER_PROMOTION
WORKER_HANDOFF
CHILD_WORKER
```

Checker 提取：

```text
WorkerPlanIR.candidates -> WORKER_CANDIDATE instance
WorkerPlanIR.candidates -> WORKER_PROMOTION instance
WorkerPlanIR.workers non-main -> CHILD_WORKER instance
WorkerPlanIR.handoffs -> WORKER_HANDOFF instance
```

检查逻辑：

```text
WORKER_CANDIDATE:
    responsibility / delegation_signal satisfied -> candidate complete

WORKER_PROMOTION:
    promotion_input_contract
    promotion_output_contract
    promotion_invocation_point
    promotion_result_handoff
    all satisfied -> ready
    missing any -> blocked

CHILD_WORKER:
    input_contract / output_contract / invocation / result handoff

WORKER_HANDOFF:
    from_worker / target / input_bindings / output_bindings / invocation_site
```

### 验收标准

```text
1. incomplete delegation 产生 WORKER_CANDIDATE report。
2. candidate complete 不等于 promotion ready。
3. 缺 input/output/invocation/result handoff 时，WORKER_PROMOTION promotion_status=blocked。
4. DiagnosticProjector 生成 type_or_contract_ambiguity。
5. 不生成新的 child worker。
6. 不生成新的 INVOKE_WORKER。
7. 不改变 WorkerPlanIR。
8. internal-comms-3 可以解释为什么没有晋升 child worker。
9. 全量测试通过。
```

### 注意事项

Worker/Delegation IRS 是解释与诊断机制，不是 worker materializer。

## 9. R5 Runner Orchestrator Integration

### 目标

把 v6 runner 接入 orchestrator，但先只用于 Worker/Delegation IRS。

### 可修改文件

```text
src/nl2spl/config.py
src/nl2spl/pipeline/orchestrator.py
tests/unit/test_pipeline_orchestrator.py
tests/unit/compiler/irs/test_runner_integration.py
```

### 建议 feature flags

```python
enable_irs_v6_runner: bool = False
enable_irs_worker_delegation_check: bool = False
enable_irs_diagnostic_projector: bool = False
```

### 接入点

建议在 Stage 3.5 / Stage 3.6 worker plan validation 后运行：

```text
Stage 3.5 WorkerBoundaryPlanner
-> WorkerPlanValidator
-> IRSRunner.run_stage("stage3_5", context)
-> intermediate["construct_satisfaction"]["stage3_5"]
-> intermediate["stage_local_diagnostics"]["stage3_5"]
```

### 验收标准

```text
1. flags 默认关闭时 pipeline 输出完全不变。
2. 开启 worker delegation IRS 后，intermediate 有 stage3_5 construct_satisfaction。
3. compile diagnostics/report 中可见 promotion blocked 原因。
4. orchestrator 不 import WorkerDelegationIRSChecker 具体类。
5. 全量测试通过。
```

### 注意事项

orchestrator 可以 import `IRSRunner` 和默认 registry factory，但不应 import concrete checker。

## 10. R6 Stage4 / Stage7 Compatibility Migration

### 目标

将 Stage 4 / Stage 7 现有函数式 checker 逐步包装为 v6-style checker。

### 可修改文件

```text
src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py
src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py
src/nl2spl/compiler/irs/checkers/exception_flow.py
src/nl2spl/compiler/irs/checkers/step.py
src/nl2spl/pipeline/orchestrator.py
tests/unit/test_flow_assembler.py
tests/unit/test_step_extractor.py
```

### 实现思路

短期保留 compatibility wrappers：

```python
check_exception_flows_irs(...)
check_steps_irs(...)
```

内部逐步改为：

```text
IRSCheckContext
-> Stage4ExceptionFlowIRSChecker
-> DiagnosticProjector
```

### 验收标准

```text
1. Stage 4 condition-only exception flow 行为不变。
2. Stage 4 不提前报 missing_handler。
3. Stage 7 assumed command not renderable 行为不变。
4. REQUEST_INPUT 无 ask signal 不被渲染。
5. CALL_API 只有 API mention 但无 call action 不被渲染。
6. 旧 public function tests 仍通过。
7. 新 runner-level tests 通过。
8. 全量测试通过。
```

### 注意事项

此阶段不要同时重写 PostNormalizeIRSChecker。

## 11. R7 Post-normalize Cleanup

### 目标

收敛 final construct-level diagnostic authority，减少 DiagnosticAnalyzer / PostNormalizeIRSChecker / Gate 之间的职责重叠。

### 可修改文件

```text
src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py
src/nl2spl/compiler/diagnostic_analyzer.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/irs/projector.py
tests/unit/test_normalizer.py
tests/unit/test_executable_gate.py
tests/unit/test_diagnostics_*.py
```

### 实现思路

```text
1. 梳理 missing_handler / missing_output_producer / type_or_contract_ambiguity / assumed_command_not_renderable 的唯一权威来源。
2. 保留 PostNormalizeIRSChecker 作为 construct-level final authority。
3. Gate 只负责 post-gate renderability。
4. DiagnosticAnalyzer 若保留，应降级为 legacy compatibility 或非 IRS analyzer。
5. CompileDiagnostic 创建逐步迁移到 DiagnosticProjector。
```

### 验收标准

```text
1. missing_handler 不重复。
2. missing_output_producer 不重复。
3. type_or_contract_ambiguity 不重复。
4. assumed_command_not_renderable 不重复。
5. final completeness 计算不变。
6. readable report 信息不减少。
7. 全量测试通过。
```

## 12. R8 Graph-ready Hardening

### 目标

补齐未来递归 IRS checker 所需的 graph 数据，但不实现递归 traversal。

### 可修改文件

```text
src/nl2spl/compiler/irs/graph.py
src/nl2spl/compiler/irs/checkers/worker_delegation.py
src/nl2spl/compiler/irs/checkers/exception_flow.py
src/nl2spl/compiler/irs/checkers/step.py
tests/unit/compiler/irs/test_construct_graph.py
```

### 实现思路

生成关键 edge：

```text
WORKER contains FLOW
FLOW contains BLOCK
BLOCK contains STEP
STEP produces VARIABLE
STEP consumes VARIABLE
INVOKE_WORKER invokes CHILD_WORKER
WORKER_HANDOFF handoff_to CHILD_WORKER
EXCEPTION_FLOW handles CONDITION
WORKER_CANDIDATE promotes_to WORKER_PROMOTION
WORKER_PROMOTION blocked_by missing slot
```

### 验收标准

```text
1. report.related_edges 可表达主要 DAG 关系。
2. construct_path 可表达 primary containment path。
3. edge snapshot 稳定。
4. 不执行 recursive traversal。
5. 不改变 renderer。
6. 不改变 final SPL。
7. 全量测试通过。
```

## 13. R9 Final Audit

### 目标

确认 IRS v6 扩展路径达到设计目标。

### 检查项

```text
1. 新增 checker 是否不需要改 orchestrator 主流程？
2. Diagnostic 是否能通过 projector 统一生成？
3. Worker candidate 和 promotion blocked 是否被结构化解释？
4. ConstructSatisfactionReport 是否具备 parent/path/edge/frontier/cutline 字段？
5. Stage 4 / Stage 7 / Post-normalize 是否仍兼容？
6. Renderer 是否没有承担 IRS 判断？
7. Gate / ProducerIndex authority 是否没有被替代？
8. internal-comms-3 Issue 3 是否能解释？
9. full test suite 是否通过？
```

### 验收标准

```text
1. 所有 R0-R8 验收项通过。
2. 文档与代码一致。
3. 无 stale feature flag 描述。
4. 无 skipped IRS tests。
5. 无弱断言 baseline 测试。
6. 生成最终审计报告。
```

## 14. 测试矩阵

| 场景 | 预期 |
| --- | --- |
| failure condition only | partial exception flow + missing_handler |
| failure condition + handler evidence | handler 可作为 action，但不被误当 condition |
| required output no producer | missing_output_producer |
| incomplete delegation | no child worker + WORKER_PROMOTION blocked |
| worker candidate only | candidate report + promotion blocked |
| complete source-backed delegation | child worker / handoff / invoke allowed |
| REQUEST_INPUT without ask signal | no REQUEST_INPUT rendered |
| CALL_API with repository mention only | resource/integration candidate, no CALL_API |
| assumed command | not rendered |
| compiler unpack without renderable producer | blocked + diagnostic |
| gate-filtered handler | gate-after missing_handler remains visible |

测试层级：

```text
Unit:
    ConstructInstance / registry / runner / projector / checker

Integration:
    orchestrator intermediate_results

Golden:
    final_spl.txt / compile_report / feedback_report
```

## 15. 任务模板

每个具体任务应使用以下模板：

```text
### Rx.y Task Name

Priority:
Status:
Depends on:

Goal:

Files:

Implementation notes:

Acceptance criteria:

Regression tests:

Risks:

Rollback:
```

示例：

```text
### R4.2 Extract WORKER_PROMOTION ConstructInstance

Priority: P1
Status: Todo
Depends on: R1, R2

Goal:
从 WorkerPlanIR.candidates 中提取 WORKER_PROMOTION instance，用于表达 candidate 是否具备晋升 child worker 的条件。

Files:
- src/nl2spl/compiler/irs/checkers/worker_delegation.py
- tests/unit/compiler/irs/test_worker_delegation_checker.py

Implementation notes:
- materialized=False
- source_demanded=True
- candidate_only=True
- 不修改 WorkerPlanIR
- 不生成 child worker

Acceptance criteria:
- 每个 delegation candidate 产生一个 WORKER_PROMOTION report
- 缺 input/output/invocation/result_handoff 时 promotion_status=blocked
- DiagnosticProjector 产生 type_or_contract_ambiguity

Regression tests:
- internal-comms-3 incomplete delegation
- complete source-backed delegation

Risks:
- candidate complete 与 promotion ready 被混淆

Rollback:
- 关闭 enable_irs_worker_delegation_check
```

