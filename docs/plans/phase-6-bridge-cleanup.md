# Phase 6: Bridge 清理 — 实施计划

## 目标

标记 `bridge_failure_modes()` 和 `bridge_failure_modes_worker_scoped()` 为 deprecated，添加 DeprecationWarning。

## 实施步骤

### Step 1: 更新 bridge_failure_modes() docstring

文件：`src/nl2spl/pipeline/fact_bridges.py`

- 添加 `.. deprecated::` docstring 标记
- 说明应使用 `materialize_route_exception_flows()` 替代

### Step 2: 添加 DeprecationWarning

在 `bridge_failure_modes()` 函数体中（early return 之后）添加：
```python
_warnings.warn(
    "bridge_failure_modes() is deprecated. Use "
    "materialize_route_exception_flows() for route-annotated input. "
    "This bridge will be removed when all adapters produce RouteAnnotations.",
    DeprecationWarning,
    stacklevel=2,
)
```

### Step 3: 同步更新 bridge_failure_modes_worker_scoped()

同样添加 deprecated docstring 和 DeprecationWarning。

### Step 4: 添加 Phase 6 测试

测试文件：`tests/unit/test_phase6_bridge_cleanup.py`

验证：
- 调用 bridge_failure_modes() 时触发 DeprecationWarning
- 无 failure_modes 时不触发 warning
- bridge 功能仍然正常工作

### Step 5: 运行全量回归

## 验收标准

- [x] bridge_failure_modes() 标记为 deprecated
- [x] bridge_failure_modes_worker_scoped() 标记为 deprecated
- [x] 调用时触发 DeprecationWarning
- [x] bridge 功能不受影响
- [x] 现有测试无回归（deprecation warnings 不影响测试通过）

## 文件变更

| 操作 | 文件 |
|------|------|
| 修改 | `src/nl2spl/pipeline/fact_bridges.py` — deprecated docstring + warning |
| 新增 | `tests/unit/test_phase6_bridge_cleanup.py` — 3 tests |
