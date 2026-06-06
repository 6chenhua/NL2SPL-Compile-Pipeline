# IRS v6 设计模式

IRS v6 是一个 **metadata-driven、plugin-based、compiler-oriented static analysis framework**。

---

## 1. Specification Pattern

`ConstructIRS` 本质上是 SPL construct 的 specification。

| IRS v6 | Specification Pattern 角色 |
|---|---|
| `ConstructIRS` | specification definition |
| `SlotSpec` | single predicate / rule |
| `ConstructInstance` | candidate object |
| `IRSChecker.check_instance()` | specification evaluation |
| `SlotSatisfaction` | predicate evaluation result |
| `ConstructSatisfactionReport` | validation result object |

但不是普通业务 specification — 带有 compiler 语义：partial rendering、diagnostic kind、source provenance、frontier/cutline、renderability authority。

## 2. Strategy Pattern

`IRSChecker` 是典型 Strategy interface。不同 construct 的检查逻辑封装为不同 checker：

```text
WorkerDelegationIRSChecker   — WORKER_CANDIDATE / WORKER_PROMOTION / CHILD_WORKER / WORKER_HANDOFF
ExceptionFlowIRSChecker      — EXCEPTION_FLOW
StepIRSChecker               — GENERAL_COMMAND / REQUEST_INPUT / CALL_API
```

| IRS v6 | Strategy Pattern 角色 |
|---|---|
| `IRSChecker` Protocol | strategy interface |
| `WorkerDelegationIRSChecker` | concrete strategy |
| `IRSRunner` | context / strategy executor |
| `IRSCheckerRegistry` | strategy lookup / registration |

工程价值：新增 construct IRS 时，不需要改 orchestrator 主流程。

## 3. Registry / Plugin Pattern

`SPLConstructRegistry`、`IRSCheckerRegistry`、`DiagnosticRegistry` 都是 Registry / Plugin 变体。

体现开放封闭原则：
- 对扩展开放：新增 checker / registry entry
- 对修改关闭：不改 orchestrator / renderer / gate 主流程

## 4. Multi-pass Compiler Static Analysis

NL2SPL 是 compiler architecture，IRS 的角色接近 **semantic analysis / static analysis / lint pass**。

Stage 内部形成小 pipeline：
```text
extract ConstructInstance → check slot satisfaction → project diagnostics → consolidate → report
```

## 5. Diagnostic Projection

Checker 不直接拼 `CompileDiagnostic`：
```text
IRSChecker → ConstructSatisfactionReport / SlotSatisfaction → DiagnosticProjector → CompileDiagnostic
```

好处：
1. Checker 只关心 slot 是否满足
2. severity、message、blocks_completion、dedup key 统一处理
3. 未来替换 message template 不影响 checker

## 6. Frontier / Cutline: Fail-fast + Partial Evaluation

| IRS 行为 | 工程思想 |
|---|---|
| 缺 required_for_partial 直接停止 | fail-fast |
| 缺 required_for_complete 但允许 partial | partial evaluation |
| 无 source-backed child evidence 不下钻 | demand-driven / lazy evaluation |
| `frontier_status` 控制遍历 | short-circuit traversal |

## 7. Composite Pattern 只局部适用

SPL grammar 有天然 containment（Worker → Flow → Block → Step），可借鉴 Composite。但全局 construct relation 是 DAG（Step → RequiredOutput、Handoff → ChildWorker），必须用 `ConstructEdge`。

## 8. Worker Promotion: State / Workflow Gate

```text
delegation mention → worker candidate → promotion ready → child worker → handoff → invoke worker
```

`WORKER_CANDIDATE` 与 `WORKER_PROMOTION` 分离后可以表达：
- candidate itself is valid as report-only construct
- promotion to child worker is blocked by missing contracts

## 9. 不应强行套用的模式

- **不是普通 Rule Engine** — checker 不调用 LLM、不修改 IR、不补全 slot
- **不是纯 Composite** — 全局关系是 DAG
- **现在还不是 Visitor** — 未来递归 evaluator 可能接近 Visitor，当前只预留接口
- **不是 Parser Validator** — grammar 管语法，IRS 管信息需求
