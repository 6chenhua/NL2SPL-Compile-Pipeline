# T2: WorkerScopedResourceIR + SymbolTable

**任务 ID**: T2  
**任务名称**: WorkerScopedResourceIR + SymbolTable  
**预估时间**: 4-7 天  
**前置依赖**: T1.6  
**状态**: 待启动

---

## 1. 任务概述

让 Stage 6 支持 worker scope，明确 global/main/child/handoff 变量可见性。

### 目标
- 实现 `WorkerScopedResourceIR` 数据结构
- 修改 `SymbolTable` 支持 worker scope
- 修改 Stage 6 支持 worker-scoped 资源提取

### 成功标准
- SymbolTable 支持 worker scope（D4: 复合 key）
- Stage 6 能提取 worker-scoped 资源
- 同名不同 scope 的变量可以共存
- 所有现有测试通过

---

## 2. 任务范围

### 可创建文件
- `tests/ir/test_worker_scoped_resource_ir.py` - WorkerScopedResourceIR 测试
- `tests/ir/test_symbol_table_scoped.py` - SymbolTable scoped 测试
- `tests/pipeline/stages/test_stage6_worker_scoped.py` - Stage 6 worker-scoped 测试

### 可编辑文件
- `src/nl2spl/ir/resource_registry_ir.py` - 新增 `WorkerScopedResourceIR`
- `src/nl2spl/ir/worker_plan_ir.py` - 新增 `HandoffContractIR`
- `src/nl2spl/ir/symbol_table.py` - 修改 SymbolTable 支持 scope
- `src/nl2spl/pipeline/stages/stage6_resource_extractor.py` - 新增 worker-aware 方法
- `src/nl2spl/pipeline/orchestrator.py` - 新增 worker-aware 调用路径

### 不可编辑文件
- Stage 7/9.5/10/11 文件
- 其他 IR 文件

---

## 3. 详细工作内容

### 3.1 新增 WorkerScopedResourceIR

**文件**: `src/nl2spl/ir/resource_registry_ir.py`

**新增类**:

```python
@dataclass
class WorkerScopedResourceIR:
    """Worker-scoped resource extraction result.
    
    Attributes:
        global_resources: Resources visible to all workers
        worker_resources: Resources keyed by worker_id
        handoff_contracts: Handoff contracts between workers
    """
    global_resources: ResourceRegistryIR = field(default_factory=ResourceRegistryIR)
    worker_resources: dict[str, ResourceRegistryIR] = field(default_factory=dict)
    handoff_contracts: dict[str, HandoffContractIR] = field(default_factory=dict)
```

### 3.2 新增 HandoffContractIR

**文件**: `src/nl2spl/ir/worker_plan_ir.py`

**新增类**:

```python
@dataclass
class HandoffContractIR:
    """Handoff contract between parent and child worker.
    
    Attributes:
        handoff_id: Unique identifier
        parent_worker_id: Parent worker ID
        child_worker_id: Child worker ID
        input_variables: Variables passed from parent to child
        output_variables: Variables returned from child to parent
    """
    handoff_id: str
    parent_worker_id: str
    child_worker_id: str
    input_variables: list[ContractFieldIR] = field(default_factory=list)
    output_variables: list[ContractFieldIR] = field(default_factory=list)
```

### 3.3 修改 SymbolTable 支持 scope

**文件**: `src/nl2spl/ir/symbol_table.py`

**修改类** (D4 - Frozen):

```python
@dataclass
class VariableSymbol:
    """Variable symbol information."""
    name: str
    data_type: str
    source: str
    description: str
    # 新增：scope 支持
    scope_kind: Literal["global", "worker", "handoff"] = "global"
    scope_id: str | None = None  # worker_id 或 handoff_id
    # 保留原有字段兼容性
    flow_ref: str = "main"
    block_ref: str | None = None
    producer_step: str | None = None
    consumer_steps: list[str] = field(default_factory=list)
    declared: bool = True


class SymbolTable:
    """Symbol table for variable management.
    
    支持 worker-scoped variables。
    """

    def __init__(self) -> None:
        """Initialize empty symbol table."""
        # 使用复合 key：(scope_kind, scope_id, name)
        self._variables: dict[tuple[str, str | None, str], VariableSymbol] = {}
        # 兼容旧接口
        self.variables: dict[str, VariableSymbol] = {}

    def declare_scoped(
        self,
        name: str,
        data_type: str,
        source: str,
        description: str,
        scope_kind: Literal["global", "worker", "handoff"] = "global",
        scope_id: str | None = None,
    ) -> None:
        """Declare a variable with scope."""
        key = (scope_kind, scope_id, name)
        self._variables[key] = VariableSymbol(
            name=name,
            data_type=data_type,
            source=source,
            description=description,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )
        
        # 兼容旧接口：global 变量也加入 self.variables
        if scope_kind == "global":
            self.variables[name] = self._variables[key]

    def get_variables_for_worker(self, worker_id: str) -> dict[str, VariableSymbol]:
        """Get variables visible to a worker.
        
        Returns global + worker-scoped variables.
        """
        result = {}
        
        # Global variables
        for key, var in self._variables.items():
            if key[0] == "global":
                result[var.name] = var
        
        # Worker-scoped variables
        for key, var in self._variables.items():
            if key[0] == "worker" and key[1] == worker_id:
                result[var.name] = var
        
        return result

    def get_variables_for_handoff(self, handoff_id: str) -> dict[str, VariableSymbol]:
        """Get variables visible to a handoff."""
        result = {}
        
        # Global variables
        for key, var in self._variables.items():
            if key[0] == "global":
                result[var.name] = var
        
        # Handoff-scoped variables
        for key, var in self._variables.items():
            if key[0] == "handoff" and key[1] == handoff_id:
                result[var.name] = var
        
        return result

    def get_variable_list_for_worker_prompt(self, worker_id: str) -> str:
        """Generate variable list text for a specific worker's LLM prompt."""
        visible_vars = self.get_variables_for_worker(worker_id)
        if not visible_vars:
            return "No variables available."
        
        lines = []
        for var in visible_vars.values():
            scope_info = ""
            if var.scope_kind == "worker":
                scope_info = f" [worker: {var.scope_id}]"
            elif var.scope_kind == "handoff":
                scope_info = f" [handoff: {var.scope_id}]"
            lines.append(
                f"- {var.name}: {var.data_type} ({var.source}){scope_info} - {var.description}"
            )
        return "\n".join(lines)

    def get_all_declared_variables(self) -> dict[str, VariableSymbol]:
        """Get all declared variables for SPL DEFINE_VARIABLES.
        
        包含：
        - global variables
        - all contract variables (input/output)
        - all rendered step variables
        
        不包含：
        - worker-internal variables (除非被声明为 contract)
        """
        result = {}
        
        for key, var in self._variables.items():
            # global 变量 always included
            if key[0] == "global":
                result[var.name] = var
            # contract variables (input/output) always included
            elif var.source in ("input", "output"):
                result[var.name] = var
            # rendered step variables included if declared
            elif var.declared:
                result[var.name] = var
        
        return result
```

### 3.4 修改 Stage 6 ResourceExtractor

**文件**: `src/nl2spl/pipeline/stages/stage6_resource_extractor.py`

**新增方法**:

#### 3.4.1 execute_worker_scoped()

```python
def execute_worker_scoped(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    worker_plan: WorkerPlanIR,
    canonical_input: CanonicalCompileInput,
) -> tuple[WorkerScopedResourceIR, SymbolTable]:
    """Execute worker-scoped resource extraction."""
```

#### 3.4.2 _extract_resources_for_scope()

```python
def _extract_resources_for_scope(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    flow: FlowStructureIR,
    blocks: BlockStructureIR,
    symbol_table: SymbolTable,
    canonical_input: CanonicalCompileInput,
    scope_kind: Literal["global", "worker", "handoff"] = "global",
    scope_id: str | None = None,
) -> tuple[ResourceRegistryIR, SymbolTable]:
    """Extract resources for a specific scope."""
```

#### 3.4.3 _build_handoff_contract()

```python
def _build_handoff_contract(
    self,
    handoff: WorkerHandoffIR,
    symbol_table: SymbolTable,
) -> HandoffContractIR:
    """Build HandoffContractIR from WorkerHandoffIR."""
```

### 3.5 修改 Orchestrator

**文件**: `src/nl2spl/pipeline/orchestrator.py`

**新增方法**:

```python
def _run_stage6_worker_scoped(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    worker_plan: WorkerPlanIR,
    canonical_input: CanonicalCompileInput,
) -> tuple[WorkerScopedResourceIR, SymbolTable]:
    """Run Stage 6 with worker-scoped input."""
```

**修改 Stage 6 调用**:

```python
# Stage 6: Resource Extraction
if (self.config.enable_worker_boundary_planner
    and worker_flow_plan is not None
    and worker_block_plan is not None
    and worker_plan is not None):
    # Worker-aware path
    worker_scoped_resources, symbol_table = self._run_stage6_worker_scoped(...)
    resources = worker_scoped_resources.global_resources
else:
    # Legacy path
    resources, symbol_table = self._run_stage6(...)
```

### 3.6 创建测试

#### 3.6.1 WorkerScopedResourceIR 测试

**文件**: `tests/ir/test_worker_scoped_resource_ir.py`

```python
class TestWorkerScopedResourceIR:
    def test_init_with_defaults(self):
        """Test WorkerScopedResourceIR initialization with default values."""
        
    def test_init_with_global_resources(self):
        """Test WorkerScopedResourceIR initialization with global resources."""
        
    def test_init_with_worker_resources(self):
        """Test WorkerScopedResourceIR initialization with worker resources."""
        
    def test_init_with_handoff_contracts(self):
        """Test WorkerScopedResourceIR initialization with handoff contracts."""
```

#### 3.6.2 SymbolTable scoped 测试

**文件**: `tests/ir/test_symbol_table_scoped.py`

```python
class TestSymbolTableScoped:
    def test_declare_scoped_global(self):
        """Test declare_scoped with global scope."""
        
    def test_declare_scoped_worker(self):
        """Test declare_scoped with worker scope."""
        
    def test_declare_scoped_handoff(self):
        """Test declare_scoped with handoff scope."""
        
    def test_get_variables_for_worker(self):
        """Test get_variables_for_worker."""
        
    def test_get_variables_for_handoff(self):
        """Test get_variables_for_handoff."""
        
    def test_get_variable_list_for_worker_prompt(self):
        """Test get_variable_list_for_worker_prompt."""
        
    def test_get_all_declared_variables(self):
        """Test get_all_declared_variables."""
        
    def test_same_name_different_scope(self):
        """Test same variable name with different scope."""
        
    def test_backward_compatibility(self):
        """Test backward compatibility with old interface."""
```

#### 3.6.3 Stage 6 worker-scoped 测试

**文件**: `tests/pipeline/stages/test_stage6_worker_scoped.py`

```python
class TestResourceExtractorWorkerScoped:
    def test_execute_worker_scoped_single_worker(self):
        """Test execute_worker_scoped with single main worker."""
        
    def test_execute_worker_scoped_multiple_workers(self):
        """Test execute_worker_scoped with main + child workers."""
        
    def test_extract_resources_for_scope_global(self):
        """Test _extract_resources_for_scope with global scope."""
        
    def test_extract_resources_for_scope_worker(self):
        """Test _extract_resources_for_scope with worker scope."""
        
    def test_build_handoff_contract(self):
        """Test _build_handoff_contract."""
```

---

## 4. 验收标准

### 4.1 代码验收
- [ ] `WorkerScopedResourceIR` 类定义正确
- [ ] `HandoffContractIR` 类定义正确
- [ ] `SymbolTable` 支持 worker scope（D4: 复合 key）
- [ ] `VariableSymbol` 包含 `scope_kind` 和 `scope_id` 字段
- [ ] `declare_scoped()` 方法实现正确
- [ ] `get_variables_for_worker()` 方法实现正确
- [ ] `get_variables_for_handoff()` 方法实现正确
- [ ] `get_all_declared_variables()` 方法实现正确
- [ ] `ResourceExtractor.execute_worker_scoped()` 实现正确
- [ ] `ResourceExtractor._extract_resources_for_scope()` 实现正确
- [ ] `ResourceExtractor._build_handoff_contract()` 实现正确
- [ ] Orchestrator 正确处理 worker-aware 和 legacy path

### 4.2 测试验收
- [ ] `tests/ir/test_worker_scoped_resource_ir.py` 所有测试通过
- [ ] `tests/ir/test_symbol_table_scoped.py` 所有测试通过
- [ ] `tests/pipeline/stages/test_stage6_worker_scoped.py` 所有测试通过
- [ ] 所有现有测试通过（回归测试）

### 4.3 集成验收
- [ ] 端到端测试：输入包含 child worker 的场景
- [ ] 验证 global variables 对所有 worker 可见
- [ ] 验证 worker-scoped variables 只对对应 worker 可见
- [ ] 验证 handoff contracts 正确提取
- [ ] 验证同名不同 scope 的变量可以共存

---

## 5. 依赖关系

### 前置依赖
- T1.6: WorkerIR/Renderer child-flow support（必须完成）

### 后续任务
- T3: worker-aware path 去 adapter

### 与其他任务的接口

#### 从 T1.6 接收的接口
- `ChildWorkerIR` 数据结构
- `WorkerAssembler.assemble_from_worker_scoped()` 方法

#### 提供给 T3 的接口
- `WorkerScopedResourceIR` 数据结构
- `SymbolTable` scoped 接口
- `ResourceExtractor.execute_worker_scoped()` 方法

---

## 6. 交付物

### 代码交付
1. 修改后的 `resource_registry_ir.py`（新增 `WorkerScopedResourceIR`）
2. 修改后的 `worker_plan_ir.py`（新增 `HandoffContractIR`）
3. 修改后的 `symbol_table.py`（支持 worker scope）
4. 修改后的 `stage6_resource_extractor.py`（新增 worker-aware 方法）
5. 修改后的 `orchestrator.py`（新增 worker-aware 调用路径）

### 测试交付
1. `tests/ir/test_worker_scoped_resource_ir.py`
2. `tests/ir/test_symbol_table_scoped.py`
3. `tests/pipeline/stages/test_stage6_worker_scoped.py`

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| SymbolTable 改动影响现有代码 | 高 | 保留旧接口兼容性 |
| 同名变量处理复杂 | 中 | 使用复合 key 解决 |
| SPL 语法不支持 worker-local DEFINE_VARIABLES | 中 | 设计合理的 DEFINE_VARIABLES 策略 |
| 性能问题 | 低 | SymbolTable 操作简单，性能影响小 |

---

## 8. 评审要点

### 代码评审
- `WorkerScopedResourceIR` 是否正确封装 worker-scoped 资源
- `HandoffContractIR` 是否正确封装 handoff contract
- `SymbolTable` 是否支持 worker scope（D4: 复合 key）
- `declare_scoped()` 是否正确处理不同 scope
- `get_variables_for_worker()` 是否正确返回可见变量
- `execute_worker_scoped()` 是否正确提取 worker-scoped 资源
- Orchestrator 是否正确处理 worker-aware 和 legacy path

### 测试评审
- 测试覆盖是否充分
- 边界条件是否测试
- 同名变量场景是否测试

---

## 9. 开发建议

### 开发顺序
1. 新增 `HandoffContractIR`
2. 新增 `WorkerScopedResourceIR`
3. 修改 `VariableSymbol`（新增 scope 字段）
4. 修改 `SymbolTable`（新增 scoped 方法）
5. 实现 `_extract_resources_for_scope()`
6. 实现 `_build_handoff_contract()`
7. 实现 `execute_worker_scoped()`
8. 修改 Orchestrator
9. 编写测试
10. 运行回归测试

### 调试建议
- 使用简单的测试场景（单 worker）
- 逐步增加复杂度（多 worker、复杂 handoff）
- 使用 logging 输出资源提取结果

---

## 10. 参考资料

- [迁移方案 v3.0](../migration-worker-aware-pipeline.md)
- [ResourceRegistryIR 定义](../../src/nl2spl/ir/resource_registry_ir.py)
- [SymbolTable 定义](../../src/nl2spl/ir/symbol_table.py)
- [Stage 6 实现](../../src/nl2spl/pipeline/stages/stage6_resource_extractor.py)
- [T1.6 任务文档](T1.6-child-worker-flow.md)
