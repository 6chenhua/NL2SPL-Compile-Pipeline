# T1: WorkerScopedStepIR + Stage 7

**任务 ID**: T1  
**任务名称**: WorkerScopedStepIR + Stage 7  
**预估时间**: 3-5 天  
**前置依赖**: T0  
**状态**: 待启动

---

## 1. 任务概述

让 Stage 7 按 `worker_id` 输出 steps，main worker 的 invoke step 从 `WorkerHandoffIR` 生成。

### 目标
- 实现 `WorkerStepPlanIR` 数据结构
- 修改 Stage 7 支持 worker-scoped extraction
- 从 `WorkerHandoffIR` 生成 `INVOKE_WORKER` / `CALL_API` steps
- 验证 span ownership（D5: error）

### 成功标准
- Stage 7 能按 `worker_id` 输出 steps
- main worker 的 invoke step 从 `WorkerHandoffIR` 生成
- span ownership violation 抛出 error
- 所有现有测试通过

---

## 2. 任务范围

### 可创建文件
- `tests/ir/test_worker_step_plan_ir.py` - WorkerStepPlanIR 测试
- `tests/pipeline/stages/test_stage7_worker_scoped.py` - Stage 7 worker-scoped 测试

### 可编辑文件
- `src/nl2spl/ir/worker_plan_ir.py` - 确认 `WorkerStepPlanIR`（T0 已创建）
- `src/nl2spl/pipeline/stages/stage7_step_extractor.py` - 新增 worker-aware 方法
- `src/nl2spl/pipeline/orchestrator.py` - 新增 worker-aware 调用路径

### 不可编辑文件
- 其他 Stage 实现文件
- IR 文件（除确认外）
- Stage 10/11 文件

---

## 3. 详细工作内容

### 3.1 确认 WorkerStepPlanIR

**文件**: `src/nl2spl/ir/worker_plan_ir.py`

确认 T0 创建的 `WorkerStepPlanIR` 类正确，包含：
- `main_worker_id: str`
- `worker_steps: dict[str, list[StepIR]]`
- `warnings: list[str]`
- `main_worker_steps` 属性
- `get_all_steps()` 方法

### 3.2 修改 Stage 7 StepExtractor

**文件**: `src/nl2spl/pipeline/stages/stage7_step_extractor.py`

**新增方法**:

#### 3.2.1 execute_worker_scoped()

```python
def execute_worker_scoped(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    symbol_table: SymbolTable,
    worker_plan: WorkerPlanIR,
) -> tuple[WorkerStepPlanIR, SymbolTable]:
    """Execute worker-scoped step extraction.
    
    对每个 worker 独立提取 steps：
    - main worker: 从 main flow 提取普通 steps + 从 handoffs 生成 INVOKE_WORKER
    - child worker: 从 child flow 提取自己的 steps
    """
```

#### 3.2.2 _extract_steps_for_worker()

```python
def _extract_steps_for_worker(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    flow: FlowStructureIR,
    blocks: BlockStructureIR,
    symbol_table: SymbolTable,
    worker: WorkerSpecIR,
) -> tuple[list[StepIR], SymbolTable]:
    """Extract steps for a single worker.
    
    关键：prompt 中包含：
    - worker input contract
    - worker output contract
    - already-known global variables
    - current worker known variables
    - handoff-bound parent variables for main worker
    """
```

#### 3.2.3 _generate_handoff_steps()

```python
def _generate_handoff_steps(
    self,
    worker_plan: WorkerPlanIR,
    symbol_table: SymbolTable,
) -> list[StepIR]:
    """Generate INVOKE_WORKER / CALL_API steps from handoffs.
    
    关键：只从 WorkerHandoffIR 生成，不从 decisions 生成。（D1）
    """
```

#### 3.2.4 _build_invoke_step()

```python
def _build_invoke_step(
    self,
    handoff: WorkerHandoffIR,
    worker_plan: WorkerPlanIR,
) -> StepIR:
    """Build INVOKE_WORKER step from handoff."""
```

#### 3.2.5 _build_api_call_step()

```python
def _build_api_call_step(
    self,
    handoff: WorkerHandoffIR,
    worker_plan: WorkerPlanIR,
) -> StepIR:
    """Build CALL_API step from handoff."""
```

#### 3.2.6 _get_invoke_source_spans()

```python
def _get_invoke_source_spans(
    self,
    handoff: WorkerHandoffIR,
    worker_plan: WorkerPlanIR,
) -> list[str]:
    """Get source spans for invoke/api_call step.
    
    优先使用 invoke_location_hint，fallback 到 warning。（D2）
    """
```

#### 3.2.7 _validate_step_span_ownership()

```python
def _validate_step_span_ownership(
    self,
    steps: list[StepIR],
    worker: WorkerSpecIR,
) -> list[str]:
    """Validate that steps only reference worker-owned spans.
    
    D5: span ownership violation 是 error，不是 warning。
    """
```

### 3.3 修改 Orchestrator

**文件**: `src/nl2spl/pipeline/orchestrator.py`

**新增方法**:

```python
def _run_stage7_worker_scoped(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    symbol_table: SymbolTable,
    worker_plan: WorkerPlanIR,
) -> tuple[WorkerStepPlanIR, SymbolTable]:
    """Run Stage 7 with worker-scoped input."""
```

**修改 Stage 7 调用**:

```python
# Stage 7: Step Extraction
if (self.config.enable_worker_boundary_planner
    and worker_flow_plan is not None
    and worker_block_plan is not None
    and worker_plan is not None):
    # Worker-aware path
    worker_step_plan, symbol_table = self._run_stage7_worker_scoped(...)
    steps = worker_step_plan.get_all_steps()
else:
    # Legacy path
    steps, symbol_table = self._run_stage7(...)
```

### 3.4 创建测试

#### 3.4.1 WorkerStepPlanIR 测试

**文件**: `tests/ir/test_worker_step_plan_ir.py`

```python
class TestWorkerStepPlanIR:
    def test_init_with_main_worker_id(self):
        """Test WorkerStepPlanIR initialization with main_worker_id."""
        
    def test_main_worker_steps(self):
        """Test main_worker_steps property."""
        
    def test_get_all_steps(self):
        """Test get_all_steps method."""
        
    def test_empty_worker_steps(self):
        """Test with empty worker_steps."""
```

#### 3.4.2 Stage 7 worker-scoped 测试

**文件**: `tests/pipeline/stages/test_stage7_worker_scoped.py`

```python
class TestStepExtractorWorkerScoped:
    def test_execute_worker_scoped_single_worker(self):
        """Test execute_worker_scoped with single main worker."""
        
    def test_execute_worker_scoped_multiple_workers(self):
        """Test execute_worker_scoped with main + child workers."""
        
    def test_generate_handoff_steps_invoke(self):
        """Test _generate_handoff_steps with invoke handoff."""
        
    def test_generate_handoff_steps_api_call(self):
        """Test _generate_handoff_steps with api_call handoff."""
        
    def test_build_invoke_step(self):
        """Test _build_invoke_step."""
        
    def test_build_api_call_step(self):
        """Test _build_api_call_step."""
        
    def test_get_invoke_source_spans_with_hint(self):
        """Test _get_invoke_source_spans with invoke_location_hint."""
        
    def test_get_invoke_source_spans_without_hint(self):
        """Test _get_invoke_source_spans without invoke_location_hint (fallback)."""
        
    def test_validate_step_span_ownership_valid(self):
        """Test _validate_step_span_ownership with valid spans."""
        
    def test_validate_step_span_ownership_invalid(self):
        """Test _validate_step_span_ownership with invalid spans (D5: error)."""
```

---

## 4. 验收标准

### 4.1 代码验收
- [ ] `WorkerStepPlanIR` 类定义正确（T0 已完成）
- [ ] `StepExtractor.execute_worker_scoped()` 实现正确
- [ ] `_generate_handoff_steps()` 从 `WorkerHandoffIR` 生成 steps（D1）
- [ ] `_get_invoke_source_spans()` 优先使用 `invoke_location_hint`（D2）
- [ ] `_validate_step_span_ownership()` 抛出 error（D5）
- [ ] Orchestrator 新增 worker-aware 调用路径

### 4.2 测试验收
- [ ] `tests/ir/test_worker_step_plan_ir.py` 所有测试通过
- [ ] `tests/pipeline/stages/test_stage7_worker_scoped.py` 所有测试通过
- [ ] 所有现有测试通过（回归测试）

### 4.3 集成验收
- [ ] 端到端测试：输入包含 child worker 的场景
- [ ] 验证 main worker steps 包含 INVOKE_WORKER step
- [ ] 验证 INVOKE_WORKER step 的 source_span_ids 来自 invoke_location_hint
- [ ] 验证 child worker steps 只引用 child-owned spans
- [ ] 验证 span ownership violation 抛出 error

---

## 5. 依赖关系

### 前置依赖
- T0: IR Contract 修正（必须完成）

### 后续任务
- T1.5: Worker-aware Stage 9.5
- T1.6: WorkerIR/Renderer child-flow support

### 与其他任务的接口

#### 提供给 T1.5 的接口
- `WorkerStepPlanIR` 数据结构
- `StepExtractor.execute_worker_scoped()` 方法

#### 提供给 T1.6 的接口
- `WorkerStepPlanIR` 数据结构（用于 Stage 10）

---

## 6. 交付物

### 代码交付
1. 确认后的 `worker_plan_ir.py`（包含 `WorkerStepPlanIR`）
2. 修改后的 `stage7_step_extractor.py`（新增 worker-aware 方法）
3. 修改后的 `orchestrator.py`（新增 worker-aware 调用路径）

### 测试交付
1. `tests/ir/test_worker_step_plan_ir.py`
2. `tests/pipeline/stages/test_stage7_worker_scoped.py`

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Stage 7 核心逻辑改动 | 高 | 保留 legacy path，通过配置开关控制 |
| LLM prompt 设计不当 | 中 | 先用简单 prompt，后续优化 |
| span ownership 校验过严 | 低 | 可调整为 warning（但 D5 规定是 error） |

---

## 8. 评审要点

### 代码评审
- `execute_worker_scoped()` 是否正确遍历 workers
- `_generate_handoff_steps()` 是否只从 `WorkerHandoffIR` 生成（D1）
- `_get_invoke_source_spans()` 是否优先使用 `invoke_location_hint`（D2）
- `_validate_step_span_ownership()` 是否抛出 error（D5）
- Orchestrator 是否正确处理 worker-aware 和 legacy path

### 测试评审
- 测试覆盖是否充分
- 边界条件是否测试
- 错误场景是否测试

---

## 9. 开发建议

### 开发顺序
1. 先确认 `WorkerStepPlanIR`（T0 已完成）
2. 实现 `_generate_handoff_steps()` 和相关方法
3. 实现 `_extract_steps_for_worker()`
4. 实现 `execute_worker_scoped()`
5. 修改 Orchestrator
6. 编写测试
7. 运行回归测试

### 调试建议
- 使用简单的测试场景（单 worker）
- 逐步增加复杂度（多 worker、复杂 handoff）
- 使用 logging 输出中间结果

---

## 10. 参考资料

- [迁移方案 v3.0](../migration-worker-aware-pipeline.md)
- [Stage 7 实现](../../src/nl2spl/pipeline/stages/stage7_step_extractor.py)
- [Orchestrator 实现](../../src/nl2spl/pipeline/orchestrator.py)
- [WorkerHandoffIR 定义](../../src/nl2spl/ir/worker_plan_ir.py)
