# Phase 3: FieldRoute 集成 — 实施计划

## 目标

Stage 2 的 `ROUTE_PRIOR_ROLE_CONTRACTS` 接受 `failure_condition` 和 `exception_handler` 角色，使 failure handling 始终路由到 `behavior` 域。

## 实施步骤

### Step 1: 更新 ROUTE_PRIOR_ROLE_CONTRACTS

文件：`src/nl2spl/pipeline/stages/stage2_field_router.py`

添加两个新角色的 contract：
- `"failure_condition"` → `field=behavior, construct_target=EXCEPTION_FLOW, slot_target=condition, executable=False`
- `"exception_handler"` → `field=behavior, construct_target=EXCEPTION_FLOW, slot_target=handler, executable=True`

### Step 2: 更新 Stage 4 filter

文件：`src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py`

`_filter_non_condition_exception_flows()` 和 `_materialize_worker_exceptions()` 的 filter 从 `semantic_role == "failure_mode"` 扩展为 `semantic_role in ("failure_mode", "failure_condition")`。

文件：`src/nl2spl/pipeline/route_exception_materializer.py`

`materialize_route_exception_flows()` 的 filter 同步更新。

### Step 3: 添加 Phase 3 测试

测试文件：`tests/unit/test_phase3_fieldroute_integration.py`

验证：
- failure_condition annotations 路由到 behavior/EXCEPTION_FLOW/condition
- exception_handler annotations 路由到 behavior/EXCEPTION_FLOW/handler
- failure handling 始终在 behavior 域，不在 rules

### Step 4: 运行全量回归

## 验收标准

- [x] failure_condition → `field=behavior, construct_target=EXCEPTION_FLOW, slot_target=condition`
- [x] exception_handler → `field=behavior, construct_target=EXCEPTION_FLOW, slot_target=handler`
- [x] failure handling 始终在 behavior 域
- [x] 现有测试无回归

## 文件变更

| 操作 | 文件 |
|------|------|
| 修改 | `src/nl2spl/pipeline/stages/stage2_field_router.py` — ROUTE_PRIOR_ROLE_CONTRACTS |
| 修改 | `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py` — filter 更新 |
| 修改 | `src/nl2spl/pipeline/route_exception_materializer.py` — filter 更新 |
| 新增 | `tests/unit/test_phase3_fieldroute_integration.py` — 5 tests |
