# Fix Acceptance Gaps — 实施计划

## 根因分析

### Bug 1: Duplicate ExceptionFlows
- `list_item` span 和 `failure_condition` span 都拿到了 `failure_condition` annotation
- 导致同一个 item 产生 2 个 ExceptionFlow
- **根因**：adapt() 同时产出 `list_item` packet + `failure_condition` packet，两者都变成 spans，都拿到 condition annotation
- **修复**：`failure_condition` packets 不应与 `list_item` packets 重复。只在 colon-split 时产出 `failure_condition`/`exception_handler_action` packets，无 colon 的 item 保留 `list_item` packet 即可

### Bug 2: Bullet parsing error
- `- Evidence shortage: request additional sources.` 被 KEY_VALUE pattern 匹配为独立 section
- **根因**：`_parse_sections()` 不排除 `- ` 开头的行
- **修复**：KEY_VALUE 匹配前检查行首是否为 bullet marker

### Bug 3: `Error handling:` not recognized
- `adapt()` 只对 `"failure handling"` / `"anticipated failures"` / `"blocking failures"` 做特殊处理
- **根因**：标题硬编码
- **修复**：`EXACT_TITLE_PRIORS` 添加 `error handling` → `failure_mode` 映射，`adapt()` 的标题检查也添加别名

### Bug 4: EXACT_TITLE_PRIORS 改了 `failure_mode` → `failure_condition` 导致旧测试失败
- 10 个旧测试期望 `failure_mode` role
- **修复**：还原 EXACT_TITLE_PRIORS 为 `failure_mode`，`failure_condition` 只由 adapt() 的 colon-split 路径产出

### Bug 5: LLM client not connected to registry
- `InputAdapterRegistry` 不传 `llm_client` 给 adapter
- **修复**：registry 传递 `llm_client`

## 修复步骤

### Step 1: 修复 bullet parsing
文件：`structural_nl.py` — `_parse_sections()`
- KEY_VALUE 匹配前检查 `stripped.startswith(("- ", "* "))`

### Step 2: 还原 EXACT_TITLE_PRIORS
文件：`section_semantic_mapper.py`
- `"failure handling"` 映射回 `("behavior", "failure_mode")`
- 添加 `"error handling"` → `("behavior", "failure_mode")`

### Step 3: 修复 adapt() duplicate packets
文件：`structural_nl.py` — `adapt()`
- 无 colon 的 failure item：只产出 `list_item` packet（现有行为）
- 有 colon 的 failure item：产出 `failure_condition` + `exception_handler_action` packets（替代 list_item）
- `FailureModeFact` 继续保留（bridge fallback 需要）

### Step 4: 扩展 adapt() 标题识别
文件：`structural_nl.py` — `adapt()`
- 添加 `"error handling"` 到 failure handling 标题列表

### Step 5: 修复 LLM client 接入
文件：`registry.py`
- 传递 `llm_client` 给 `StructuralNLAdapter` 和 `GenericNLAdapter`

### Step 6: 修复现有测试
- 更新 phase 0/2/3 测试以匹配新行为
- 确保旧测试全部通过

### Step 7: 全量测试验证
