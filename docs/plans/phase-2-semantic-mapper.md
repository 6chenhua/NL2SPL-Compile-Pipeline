# Phase 2: Semantic Mapper — 实施计划

## 目标

实现 condition/handler 拆分逻辑，输出 failure_condition / exception_handler_action 类型的 SemanticPacket 和对应的 RoutePrior。

## 架构决策

**不创建 `RouteAnnotationPrior`**。当前架构已有清晰的两层设计：
- `RoutePrior`（adapter 层，弱提示）
- `ROUTE_PRIOR_ROLE_CONTRACTS`（Stage 2 层，解析为 `RouteAnnotation`）

Phase 2 的做法：添加新的 `suggested_semantic_role` 值，让 Stage 2 的 contract 映射处理 `construct_target` / `slot_target` / `executable`。

## 实施步骤

### Step 1: 添加 condition/handler 拆分逻辑

文件：`src/nl2spl/adapters/structural_nl.py`

在 `_extract_failure_modes()` 旁边新增 `_split_condition_handler()` 方法：
- 检测 `":"` 或 `": "` 分隔符
- 左侧 = condition，右侧 = handler
- 无分隔符 = condition only

### Step 2: 在 adapt() 中生成 failure semantic packets

文件：`src/nl2spl/adapters/structural_nl.py`

对 failure handling section 的每个 list item：
1. 调用 `_split_condition_handler(item)`
2. 生成 `SemanticPacket(packet_type="failure_condition", modality="hint")`
3. 如果有 handler，生成 `SemanticPacket(packet_type="exception_handler_action", modality="hint")`
4. 生成对应的 `RoutePrior`（`suggested_semantic_role="failure_condition"` / `"exception_handler"`）

### Step 3: 扩展 SectionSemanticMapper 允许的新角色

文件：`src/nl2spl/adapters/section_semantic_mapper.py`

- `ALLOWED_ROLES` 添加 `"failure_condition"` 和 `"exception_handler"`
- `EXACT_TITLE_PRIORS` 中 `"failure handling"` 映射改为 `("behavior", "failure_condition")`（从 `"failure_mode"` 改为 `"failure_condition"`）

### Step 4: 扩展 Stage 2 ROUTE_PRIOR_ROLE_CONTRACTS

文件：`src/nl2spl/pipeline/stages/stage2_field_router.py`

添加两个新角色的 contract：
```python
"failure_condition": {
    "field": "behavior",
    "semantic_role": "failure_condition",
    "route_family": "flow_relevant",
    "construct_target": "EXCEPTION_FLOW",
    "slot_target": "condition",
    "executable": False,
},
"exception_handler": {
    "field": "behavior",
    "semantic_role": "exception_handler",
    "route_family": "flow_relevant",
    "construct_target": "EXCEPTION_FLOW",
    "slot_target": "handler",
    "executable": True,
},
```

### Step 5: 保留 FailureModeFact 作为 bridge fallback

`_extract_failure_modes()` 保留不动，`hard_facts.failure_modes` 继续填充。
bridge fallback 机制（orchestrator.py 第 238-254 行）不需要改动。
Phase 6 再清理 bridge。

### Step 6: 添加 Phase 2 测试

测试文件：`tests/unit/test_phase2_semantic_mapper.py`

设计文档要求的测试：
```python
def test_condition_handler_split():
    """'Missing timeframe: ask user' → condition + handler"""
    
def test_condition_only():
    """'Conflicting instructions' → condition only"""
    
def test_failure_condition_route_prior():
    """RoutePrior with suggested_semantic_role='failure_condition'"""
    
def test_exception_handler_route_prior():
    """RoutePrior with suggested_semantic_role='exception_handler'"""
```

### Step 7: 运行全量回归

```bash
pytest tests/unit/test_phase0_baseline.py tests/unit/test_phase1_structure_adapter.py tests/unit/test_phase2_semantic_mapper.py tests/unit/test_input_adapters.py tests/unit/test_failure_mode_bridge.py tests/integration/test_llm_adapter_engine_e2e.py -v
```

## 验收标准

- [ ] `"Missing timeframe: ask user"` 拆分为 condition + handler
- [ ] `"Conflicting instructions"` 识别为 condition only
- [ ] 输出 `RoutePrior` 指向 `behavior` 域（`suggested_semantic_role="failure_condition"` / `"exception_handler"`）
- [ ] `FailureModeFact` 保留作为 bridge fallback
- [ ] 现有测试无回归

## 文件变更

| 操作 | 文件 |
|------|------|
| 修改 | `src/nl2spl/adapters/structural_nl.py` — 拆分逻辑 + failure packets |
| 修改 | `src/nl2spl/adapters/section_semantic_mapper.py` — ALLOWED_ROLES + EXACT_TITLE_PRIORS |
| 修改 | `src/nl2spl/pipeline/stages/stage2_field_router.py` — ROUTE_PRIOR_ROLE_CONTRACTS |
| 新增 | `tests/unit/test_phase2_semantic_mapper.py` |
