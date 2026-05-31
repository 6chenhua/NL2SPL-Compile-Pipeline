# IRS v6 可扩展架构设计目录

## 目标

本目录用于定义 IRS v6 的架构方向：在不立即实现通用递归 IRS checker 的前提下，提高 IRS 新增与接入的可扩展性，并为后续构件层级递归检查预留稳定接口。

当前阶段的核心原则是：

1. IRS checker 必须易于新增，不能每新增一个 SPL construct 就大面积改 orchestrator、report、prompt 和 gate。
2. 当前仍采用 stage-local frontier checking，不实现全局递归引擎。
3. 所有 stage-local report 必须带有足够的 parent/child/path 信息，以便未来升级为递归检查。
4. Worker / Delegation IRS 作为第一轮实践，用来验证架构是否真的能扩展。

## 文档清单

| 文档 | 作用 |
| --- | --- |
| [01_irs_v6_architecture.md](01_irs_v6_architecture.md) | IRS v6 总体架构、边界、设计原则 |
| [02_irs_checker_extension_contract.md](02_irs_checker_extension_contract.md) | 新增 IRS checker 的统一接口、注册、输出规范 |
| [03_recursive_frontier_interface.md](03_recursive_frontier_interface.md) | 为未来递归 IRS 检查预留的 construct graph / frontier 接口 |
| [04_worker_delegation_irs_task.md](04_worker_delegation_irs_task.md) | Issue 3 的 Worker / Delegation IRS 实践任务与验收标准 |

## 与 v5 IRS 的关系

v5 已经提供了 `ConstructIRS`、`SlotSpec`、`ConstructSatisfactionReport`、Stage 4/Stage 7/Post-normalize checker 等基础能力。v6 不推翻 v5，而是在 v5 上补齐三个缺口：

1. 缺少统一的 IRS checker 接入模型。
2. 缺少 construct parent/child/path 表达。
3. Worker/Delegation 仍主要靠 prompt 与 `WorkerPlanValidator`，没有正式以 IRS satisfaction report 暴露。

## 非目标

本阶段不实现通用递归 IRS checker。

本阶段不要求一次性补齐所有 SPL construct 的 IRS。

本阶段不放宽 child worker materialization 标准；缺少 input/output/invocation/handoff contract 的 delegation intent 仍不得生成 child worker。
