# T3: worker-aware path 去 adapter

**任务 ID**: T3  
**任务名称**: worker-aware path 去 adapter  
**预估时间**: 2-3 天  
**前置依赖**: T1.6 (部分), T2 (完全)  
**状态**: 待启动

---

## 1. 任务概述

让 worker-aware path 不再读取 `delegation_candidates`，legacy path 可以继续保留。

### 目标
- worker-aware path 不再读取 `delegation_candidates`
- legacy path 仍可保留 `delegation_candidates`
- 最终删除 legacy adapter（如果 legacy delegation 已迁完）

### 成功标准
- worker-aware path 不读取 `delegation_candidates`
- legacy path 仍能正常使用 `delegation_candidates`
- 所有现有测试通过

---

## 2. 任务范围

### 可编辑文件
- `src/nl2spl/pipeline/orchestrator.py` - 修改 worker-aware path
- `src/nl2spl/pipeline/worker_plan_adapter.py` - 保留（不删除）

### 不可编辑文件
- IR 文件
- Stage 实现文件

### 可删除文件（条件性）
- `src/nl2spl/pipeline/worker_plan_adapter.py` - 只有在 legacy delegation 已迁完时才删除

---

## 3. 详细工作内容

### 3.1 修改 Orchestrator

**文件**: `src/nl2spl/pipeline/orchestrator.py`

**修改 Stage 4 调用** (D7 - Phase 1.6 后可提前):

```python
# Stage 4: Flow Assembly
self.logger.info("Stage 4: Flow Assembly")
if self.config.enable_worker_boundary_planner:
    # Worker-aware path
    worker_flow_plan = self._run_stage4(resolved_spans, resolved_routes, worker_plan)
    if not isinstance(worker_flow_plan, WorkerFlowPlanIR):
        raise TypeError("Worker-aware Stage 4 must return WorkerFlowPlanIR")
    worker_stage_warnings.extend(worker_flow_plan.warnings)
    intermediate["stage4_worker_flows"] = worker_flow_plan
    
    # 不再调用 worker_flow_plan_to_legacy_main_flow()
    # 不再设置 flow_structure = ...
else:
    # Legacy path
    flow_structure = self._run_stage4(resolved_spans, resolved_routes)
    intermediate["stage4_flow"] = flow_structure
```

**修改 Stage 5 调用**:

```python
# Stage 5: Block Assembly
self.logger.info("Stage 5: Block Assembly")
if self.config.enable_worker_boundary_planner:
    # Worker-aware path
    worker_block_plan = self._run_stage5(resolved_spans, resolved_routes, worker_flow_plan)
    if not isinstance(worker_block_plan, WorkerBlockPlanIR):
        raise TypeError("Worker-aware Stage 5 must return WorkerBlockPlanIR")
    worker_stage_warnings.extend(worker_block_plan.warnings)
    intermediate["stage5_worker_blocks"] = worker_block_plan
    
    # 不再调用 worker_block_plan_to_legacy_main_blocks()
    # 不再设置 block_structure = ...
else:
    # Legacy path
    block_structure = self._run_stage5(resolved_spans, resolved_routes, flow_structure)
    intermediate["stage5_blocks"] = block_structure
```

**修改 Stage 6/7/9.5/10 调用**:

确保所有 Stage 都使用 worker-aware path（如果启用）或 legacy path（如果未启用）。

### 3.2 保留 legacy adapter

**文件**: `src/nl2spl/pipeline/worker_plan_adapter.py`

**保留此文件**，因为：
- legacy path 仍需要 `delegation_candidates`
- 旧测试仍依赖此适配器
- 等 legacy delegation 也迁完，再删除

**不修改此文件**。

### 3.3 条件性删除 legacy adapter（可选）

**条件**：如果 legacy delegation 已迁完，可以删除以下函数：
- `adapt_worker_plan_to_delegation_candidates()`
- `worker_flow_plan_to_legacy_main_flow()`
- `worker_block_plan_to_legacy_main_blocks()`
- `WorkerPlanAdapter` 类

**注意**：这是可选步骤，只有在确认 legacy delegation 已完全迁移后才执行。

### 3.4 清理 Orchestrator 中的 legacy 代码

如果删除了 legacy adapter，需要清理 Orchestrator 中的相关代码：
- 删除 `from nl2spl.pipeline.worker_plan_adapter import ...`
- 删除所有调用适配器的代码

---

## 4. 验收标准

### 4.1 代码验收
- [ ] worker-aware path 不读取 `delegation_candidates`
- [ ] legacy path 仍能正常使用 `delegation_candidates`
- [ ] Orchestrator 正确处理 worker-aware 和 legacy path
- [ ] legacy adapter 保留（除非 legacy delegation 已迁完）

### 4.2 测试验收
- [ ] 所有现有测试通过（回归测试）
- [ ] worker-aware path 端到端测试通过
- [ ] legacy path 端到端测试通过

### 4.3 集成验收
- [ ] 端到端测试：worker-aware path 不读取 `delegation_candidates`
- [ ] 端到端测试：legacy path 仍能正常使用 `delegation_candidates`

---

## 5. 依赖关系

### 前置依赖
- T1.6: WorkerIR/Renderer child-flow support（部分依赖）
- T2: WorkerScopedResourceIR + SymbolTable（完全依赖）

### 后续任务
- 无（这是最后一个任务）

### 与其他任务的接口

#### 从 T1.6 接收的接口
- `ChildWorkerIR` 数据结构
- Stage 10/11 worker-aware 实现

#### 从 T2 接收的接口
- `WorkerScopedResourceIR` 数据结构
- `SymbolTable` scoped 接口
- Stage 6 worker-aware 实现

---

## 6. 交付物

### 代码交付
1. 修改后的 `orchestrator.py`（worker-aware path 去 adapter）
2. 保留的 `worker_plan_adapter.py`（除非 legacy delegation 已迁完）

### 文档交付
1. 更新迁移方案文档（标记为已完成）

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 删除 adapter 影响 legacy path | 高 | 保留 adapter，不删除 |
| 清理代码遗漏 | 中 | 运行完整测试套件 |
| 与其他任务接口不清晰 | 低 | 参考 T1.6 和 T2 的接口文档 |

---

## 8. 评审要点

### 代码评审
- worker-aware path 是否不读取 `delegation_candidates`
- legacy path 是否仍能正常使用 `delegation_candidates`
- Orchestrator 是否正确处理两种 path
- 是否有遗漏的清理

### 测试评审
- 所有现有测试是否通过
- worker-aware path 端到端测试是否通过
- legacy path 端到端测试是否通过

---

## 9. 开发建议

### 开发顺序
1. 修改 Stage 4 调用（worker-aware path 去 adapter）
2. 修改 Stage 5 调用（worker-aware path 去 adapter）
3. 确认 Stage 6/7/9.5/10 都使用正确的 path
4. 运行完整测试套件
5. 条件性删除 legacy adapter（可选）
6. 清理 Orchestrator 中的 legacy 代码（可选）
7. 再次运行完整测试套件

### 调试建议
- 使用配置开关切换 worker-aware 和 legacy path
- 分别测试两种 path
- 使用 logging 输出 path 选择

---

## 10. 参考资料

- [迁移方案 v3.0](../migration-worker-aware-pipeline.md)
- [Orchestrator 实现](../../src/nl2spl/pipeline/orchestrator.py)
- [Worker Plan Adapter 实现](../../src/nl2spl/pipeline/worker_plan_adapter.py)
- [T1.6 任务文档](T1.6-child-worker-flow.md)
- [T2 任务文档](T2-scoped-resources-symboltable.md)

---

## 11. 附录：迁移完成检查清单

在任务完成前，使用以下检查清单确认迁移已完成：

### 功能检查
- [ ] worker-aware path 不读取 `delegation_candidates`
- [ ] legacy path 仍能正常使用 `delegation_candidates`
- [ ] Stage 7 能按 `worker_id` 输出 steps
- [ ] Stage 9.5 能校验 worker-scoped IR 的完整性
- [ ] Stage 10 能从 worker-scoped 数据组装 WorkerIR
- [ ] Stage 11 能渲染 child worker 的完整 flow
- [ ] SymbolTable 支持 worker scope

### 测试检查
- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 所有回归测试通过
- [ ] 测试覆盖率达标（新增代码 100%，修改代码 90%）

### 文档检查
- [ ] 迁移方案文档已更新
- [ ] 设计决策已记录
- [ ] 任务文档已更新状态

### 代码检查
- [ ] 无类型错误
- [ ] 无 lint 错误
- [ ] 代码审查通过
- [ ] PR 已合并
