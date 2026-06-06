# Input Adapter 架构完成实施计划

## 当前状态 vs 设计文档

| 设计要求 | 当前状态 | 需要做什么 |
|---------|---------|-----------|
| Adapter 不做语义判断 | ❌ `_split_condition_handler` 仍在 adapter 中 | 删除 |
| Adapter 不生成 failure packets | ❌ `adapt()` 仍生成 `failure_condition`/`exception_handler_action` packets | 删除 |
| Adapter 不生成 failure route priors | ❌ `adapt()` 仍生成 failure route priors | 删除 |
| LLM semantic mapper 是唯一语义来源 | ❌ `EXACT_TITLE_PRIORS` 仍存在 | 删除 |
| `FailureModeFact` 已删除 | ✅ 已从 src/ 删除 | 无需操作 |
| `bridge_failure_modes` 已删除 | ✅ 已从 src/ 删除 | 无需操作 |
| `failure_mode` 作为 semantic role | ✅ 这是规范角色，保留 | 无需操作 |

## 实施步骤

### Step 1: 清理 adapter — 删除 failure 语义逻辑

文件：`src/nl2spl/adapters/structural_nl.py`

删除：
- `_split_condition_handler()` 静态方法
- `adapt()` 中 failure section 的特殊处理（lines 159-200）
- `failure_priors` 列表及其相关逻辑

改为：failure section 的 list items 只产出 neutral `list_item` packets，与其他 section 一样。

### Step 2: 删除 EXACT_TITLE_PRIORS

文件：`src/nl2spl/adapters/section_semantic_mapper.py`

删除：
- `EXACT_TITLE_PRIORS` 字典
- `_exact_title_priors()` 类方法
- `map_sections()` 中的 no-LLM fallback 路径

改为：`map_sections()` 只走 LLM 路径。无 LLM client 时返回空 priors + warning。

### Step 3: 清理 ALLOWED_ROLES

文件：`src/nl2spl/adapters/section_semantic_mapper.py`

保留 `failure_mode`（规范角色），但删除 `failure_condition` 和 `exception_handler_action`（这些不应由 adapter 层定义）。

### Step 4: 更新 tests

需要更新的测试文件：
- `tests/unit/test_phase0_baseline.py` — 移除 failure packet 相关断言
- `tests/unit/test_phase1_structure_adapter.py` — 移除 failure section 特殊处理断言
- `tests/unit/test_phase2_semantic_mapper.py` — 移除 failure_condition 相关断言
- `tests/unit/test_phase3_fieldroute_integration.py` — 移除 adapter 生成的 failure prior 断言
- `tests/unit/test_phase5_handler_materialization.py` — 更新 handler 配对逻辑
- `tests/integration/test_e2e_failure_handling.py` — 更新 e2e 测试

### Step 5: 全量测试验证

```powershell
.venv\Scripts\python.exe -m pytest tests\ -q
```

## 验收标准对照

| 验收标准 | 验证方式 |
|---------|---------|
| `Failure handling:` 通过 LLM route path 识别 | LLM semantic mapper 返回 `failure_mode` prior |
| `Error handling:` 通过 LLM route path 识别 | LLM semantic mapper 返回 `failure_mode` prior |
| `Missing timeframe: ask user` 拆分 condition+handler | LLM semantic mapper 返回两个 annotations |
| condition-only 生成 partial ExceptionFlow + missing_handler | Stage 4 物化 + PostNormalizeIRSChecker |
| mixed bullets 不重复 ExceptionFlow | 只有 neutral packets，无重复 |
| handler 通过 metadata 与 condition 配对 | `failure_item_index` metadata |
| failure handling 进入 `behavior` | RouteAnnotation `field=behavior` |
| `src/` 无 `FailureModeFact` | ✅ 已满足 |
| `HardFacts` 无 `failure_modes` | ✅ 已满足 |
| `fact_bridges.py` 无 failure bridge | ✅ 已满足 |
| orchestrator 不调用 failure bridge | ✅ 已满足 |
| adapter 不生成 failure semantic hard facts | Step 1 完成后满足 |
| Stage 4/5/7 只从 RouteAnnotation 消费 | ✅ 已满足 |
| LLM failure 不触发 semantic fallback | Step 2 完成后满足 |
