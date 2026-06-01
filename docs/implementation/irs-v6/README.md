# IRS v6 可扩展架构设计目录

## 目标

本目录定义 IRS v6 的架构方向：在不立即实现通用递归 IRS checker 的前提下，提高 IRS 新增与接入的可扩展性，并为后续 SPL construct 层级递归检查预留稳定接口。

IRS v6 不推翻 v5。v5 已经提供 `ConstructIRS`、`SlotSpec`、`ConstructSatisfactionReport`、Stage 4 / Stage 7 / Post-normalize checker 等基础。v6 要补齐的是工程接入层：

```text
ConstructIRS = 规则定义层
ConstructInstance = IR 实例标准化层
IRSChecker = 实例检查层
IRSRunner = stage-local 调度层
DiagnosticProjector = diagnostic 投影层
ConstructGraph / ConstructEdge = 未来递归预留层
```

## 核心原则

1. 新增 IRS checker 必须是局部工程动作，不能每次都大面积修改 orchestrator、renderer、gate 和 report。
2. 当前仍采用 stage-local frontier checking，不实现全局递归 evaluator。
3. 新增 report 必须带有 primary parent、path、edge、frontier/cutline 信息，为未来递归检查预留接口。
4. Checker 不调用 LLM、不修改 IR、不补全 slot、不生成新的 SPL construct。
5. Worker / Delegation IRS 是第一轮实践，用来验证架构是否真的可扩展。

## 文档清单

| 文档 | 作用 |
| --- | --- |
| [01_irs_v6_architecture.md](01_irs_v6_architecture.md) | IRS v6 总体架构、authority boundary、DAG/edge 设计 |
| [02_irs_checker_extension_contract.md](02_irs_checker_extension_contract.md) | 新增 IRS checker 的接口、schema、diagnostic 投影契约 |
| [03_recursive_frontier_interface.md](03_recursive_frontier_interface.md) | 为未来递归 IRS 检查预留的 construct graph / frontier / cutline 接口 |
| [04_worker_delegation_irs_task.md](04_worker_delegation_irs_task.md) | Issue 3 的 Worker / Delegation IRS 实践任务与验收标准 |

## 2026-05-31 设计收紧

根据架构审查，本目录已明确以下约束：

1. construct 层级不是严格树。`primary_parent_id` 只表示主包含关系；DAG 关系必须通过 `ConstructEdge` 表达。
2. `ConstructInstance` 必须区分 `materialized`、`source_demanded`、`candidate_only`。
3. `WORKER_CANDIDATE` 的 candidate 完整性和 child-worker promotion readiness 必须分离。
4. checker 不直接拼装完整 diagnostics；应输出 slot/report，由 `DiagnosticProjector` 统一投影为 `CompileDiagnostic`。
5. Stage-local IRS、Post-normalize IRS、Gate、ProducerIndex 的裁决边界必须明确。

## 非目标

本阶段不实现通用递归 IRS checker。

本阶段不一次性补齐所有 SPL construct 的 IRS。

本阶段不放宽 child worker materialization 标准；缺少 input/output/invocation/handoff contract 的 delegation intent 仍不得生成 child worker。
