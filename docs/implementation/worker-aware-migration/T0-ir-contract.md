# T0: IR Contract 修正

**任务 ID**: T0  
**任务名称**: IR Contract 修正  
**预估时间**: 1 天  
**前置依赖**: 无  
**状态**: 待启动

---

## 1. 任务概述

修正关键设计缺口，冻结 IR contract，确保后续任务有正确的基础。

### 目标
- 修正 `WorkerStepPlanIR` 结构
- 明确 `INVOKE_WORKER` 生成规则
- 明确 `INVOKE_WORKER` source_span_ids 规则
- 决定 `ChildWorkerIR` 升级方案
- 决定 SymbolTable scope 方案
- 决定 span ownership violation 策略

### 成功标准
- 所有设计决策已冻结（D1-D7）
- IR 结构定义完成
- 团队对设计达成共识

---

## 2. 任务范围

### 可编辑文件
- `src/nl2spl/ir/worker_plan_ir.py` - 新增 `WorkerStepPlanIR`
- `src/nl2spl/ir/worker_ir.py` - 升级 `ChildWorkerIR`
- `src/nl2spl/ir/symbol_table.py` - 设计 scope 方案
- `docs/migration-worker-aware-pipeline.md` - 更新设计决策

### 不可编辑文件
- 其他 IR 文件
- Stage 实现文件
- 测试文件（本任务不创建测试）

---

## 3. 详细工作内容

### 3.1 修正 WorkerStepPlanIR

**文件**: `src/nl2spl/ir/worker_plan_ir.py`

**新增类**:

```python
@dataclass
class WorkerStepPlanIR:
    """Worker-scoped step extraction result.
    
    Attributes:
        main_worker_id: Main worker ID (from WorkerPlanIR)
        worker_steps: Steps keyed by worker_id
        warnings: Validation warnings from step extraction
    """
    main_worker_id: str
    worker_steps: dict[str, list[StepIR]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    
    @property
    def main_worker_steps(self) -> list[StepIR]:
        """Get steps for the main worker."""
        return self.worker_steps.get(self.main_worker_id, [])
    
    def get_all_steps(self) -> list[StepIR]:
        """Get all steps across all workers."""
        all_steps = []
        for steps in self.worker_steps.values():
            all_steps.extend(steps)
        return all_steps
```

### 3.2 升级 ChildWorkerIR

**文件**: `src/nl2spl/ir/worker_ir.py`

**修改类**:

```python
@dataclass
class ChildWorkerIR:
    """Concrete child worker with full flow and steps support."""
    worker_name: str
    description: str
    task_text: str
    inputs: list[WorkerInput] = field(default_factory=list)
    outputs: list[WorkerOutput] = field(default_factory=list)
    # 新增：支持 child flow
    main_flow: FlowRef = field(default_factory=FlowRef)
    alternative_flows: list[AlternativeFlowRef] = field(default_factory=list)
    exception_flows: list[ExceptionFlowRef] = field(default_factory=list)
    api_refs: list[str] = field(default_factory=list)
    # 新增：支持 child steps
    steps: list[StepIR] = field(default_factory=list)
```

### 3.3 设计 SymbolTable scope 方案

**文件**: `src/nl2spl/ir/symbol_table.py`

**设计决策** (D4):
- 使用复合 key: `(scope_kind, scope_id, name)`
- `VariableSymbol` 增加 `scope_kind` 和 `scope_id` 字段
- 兼容旧接口：`self.variables` 只包含 global 变量

**不修改代码**，只设计方案，留待 T2 实现。

### 3.4 记录设计决策

**文件**: `docs/migration-worker-aware-pipeline.md`

更新"关键设计决策"部分，确保 D1-D7 已记录。

---

## 4. 验收标准

### 4.1 代码验收
- [ ] `WorkerStepPlanIR` 类定义正确
- [ ] `ChildWorkerIR` 类定义正确（包含新字段）
- [ ] SymbolTable scope 方案设计完成
- [ ] 所有设计决策 D1-D7 已冻结

### 4.2 文档验收
- [ ] 迁移方案文档已更新
- [ ] 设计决策已记录
- [ ] 团队已评审并达成共识

### 4.3 测试验收
- 本任务不创建测试
- 但需要确保现有测试通过

---

## 5. 依赖关系

### 前置依赖
- 无

### 后续任务
- T1: WorkerScopedStepIR + Stage 7
- T1.6: WorkerIR/Renderer child-flow support
- T2: WorkerScopedResourceIR + SymbolTable

---

## 6. 交付物

### 代码交付
1. 修改后的 `worker_plan_ir.py`（新增 `WorkerStepPlanIR`）
2. 修改后的 `worker_ir.py`（升级 `ChildWorkerIR`）

### 文档交付
1. 更新后的迁移方案文档
2. 设计决策记录

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 设计决策争议 | 中 | 组织评审会，达成共识 |
| IR 结构改动影响现有代码 | 低 | 新增字段有默认值，不破坏兼容性 |

---

## 8. 评审要点

### 代码评审
- `WorkerStepPlanIR` 的 `main_worker_id` 字段是否必要
- `ChildWorkerIR` 新增字段是否有默认值
- SymbolTable scope 方案是否合理

### 设计评审
- D1-D7 决策是否合理
- 是否有遗漏的设计点
- 与其他任务的接口是否清晰

---

## 9. 参考资料

- [迁移方案 v3.0](../migration-worker-aware-pipeline.md)
- [WorkerPlanIR 定义](../../src/nl2spl/ir/worker_plan_ir.py)
- [ChildWorkerIR 定义](../../src/nl2spl/ir/worker_ir.py)
- [SymbolTable 定义](../../src/nl2spl/ir/symbol_table.py)
