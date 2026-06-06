# Phase 5: Handler Materialization — 实施计划

## 目标

让 handler annotations (`slot_target="handler"`) 物化为 exception flow 的 handler blocks/steps。

## 架构决策

**在 `route_exception_materializer.py` 中扩展物化逻辑**，而非修改 Stage 5/7。原因：
- D4 guard 已经会保留包含非 condition span 的 blocks
- Stage 7 已经会为 `executable=True` 的 span 创建 steps
- 只需要在物化阶段正确链接 handler spans 到 exception flows

## 实施步骤

### Step 1: 扩展 materialize_route_exception_flows()

文件：`src/nl2spl/pipeline/route_exception_materializer.py`

当前函数只读取 condition annotations。扩展为：
1. 读取 handler annotations (`slot_target="handler"`, `semantic_role="exception_handler"`)
2. 为每个 handler annotation，找到对应的 condition exception flow（同 section，按顺序配对）
3. 将 handler span ID 添加到 `ExceptionFlow.spans`
4. 在 `exception_flow_blocks` 中创建 handler block

### Step 2: 配对逻辑

condition 和 handler 来自同一个 list item，在 adapter 中按顺序创建。配对策略：
- 按 section_id 分组
- 按 span 在 section 中的顺序配对
- 第 N 个 handler 配对第 N 个 condition

### Step 3: 更新 _materialize_worker_exceptions()

文件：`src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py`

同步更新 worker-aware 路径的物化逻辑。

### Step 4: 添加 Phase 5 测试

测试文件：`tests/unit/test_phase5_handler_materialization.py`

设计文档验收标准：
```python
def test_handler_action_generates_executable_step():
    """handler action 生成可执行步骤"""

def test_condition_only_triggers_missing_handler():
    """condition-only 触发 missing_handler 诊断"""

def test_complete_exception_flow_renders_spl():
    """完整 exception flow 渲染为 SPL"""
```

### Step 5: 运行全量回归

## 验收标准

- [ ] handler action 生成可执行步骤
- [ ] condition-only 触发 `missing_handler` 诊断
- [ ] 完整 exception flow 渲染为 SPL
- [ ] 现有测试无回归

## 文件变更

| 操作 | 文件 |
|------|------|
| 修改 | `src/nl2spl/pipeline/route_exception_materializer.py` — handler 物化 |
| 修改 | `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py` — worker-aware handler 物化 |
| 新增 | `tests/unit/test_phase5_handler_materialization.py` |
