# 工程师 A 工作交接文档

**角色**: IR/Stage 专家  
**项目**: nl2spl Worker-Aware Pipeline Migration  
**交接日期**: 2026-05-13  
**状态**: T0/T1/T1.5 全部完成，T2 完成 — 进入维护/审查阶段

---

## 必读文档清单（按优先级）

| # | 文件 | 说明 |
|---|------|------|
| 1 | `docs/migration-worker-aware-pipeline.md` | **主迁移方案** v3.0，含全部 D1-D10 设计决策 |
| 2 | `docs/implementation/worker-aware-migration/TEAM-ASSIGNMENT.md` | 三人团队分配、时间线、依赖关系 |
| 3 | `docs/implementation/worker-aware-migration/ENGINEER-A-CONTEXT.md` | 工程师 A 详细任务说明书 |
| 4 | `docs/spl_nl_to_spl_design_document_v4.md` | 系统设计文档 v4 |
| 5 | `CHANGELOG.md` | 变更日志 |
| 6 | `prompts/stage3_5_system.txt` | Stage 3.5 prompt（本次修改过） |

---

## 1. 总体进度

### 已完成（T0 → T1 → T1.5 → T2）

| 阶段 | 说明 | 状态 |
|------|------|------|
| T0: IR Contract 修正 | WorkerStepPlanIR, ChildWorkerIR 升级, SymbolTable scope 设计, HandoffContractIR | ✅ 完成 |
| T1: Stage 7 Worker-Scoped | execute_worker_scoped, handoff step 生成, span ownership 校验, Orchestrator 双路径 | ✅ 完成 |
| T1.5: Stage 9.5 Worker-Scoped | normalize_worker_scoped, 5 项校验（span/handoff/output/reachability/types） | ✅ 完成 |
| T2: SymbolTable Scope | declare_scoped, get_variables_for_worker/handoff, get_all_declared_variables | ✅ 完成 |

### 关联测试（全部通过）

```
43 passed in 1.48s  (tests/unit/ir/test_*, tests/unit/pipeline/*)
```

所有涉及 Stage 7/9.5/SymbolTable 的单元测试通过。

---

## 2. T0 — IR Contract 修正（已完成）

### 2.1 WorkerStepPlanIR

**文件**: `src/nl2spl/ir/worker_plan_ir.py` (行 261-287)

```python
@dataclass
class WorkerStepPlanIR:
    main_worker_id: str
    worker_steps: dict[str, list[StepIR]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def main_worker_steps(self) -> list[StepIR]: ...
    def get_all_steps(self) -> list[StepIR]: ...
```

已从 `ir/__init__.py` 导出。

### 2.2 ChildWorkerIR 升级（D3 决策）

**文件**: `src/nl2spl/ir/worker_ir.py` (行 78-104)

新增字段：`main_flow`, `alternative_flows`, `exception_flows`, `api_refs`, `steps`。所有新字段都有默认值，保持向后兼容。

### 2.3 SymbolTable Scope 设计（D4 决策）

**文件**: `src/nl2spl/ir/symbol_table.py` (全文件 312 行)

- `VariableSymbol` 新增字段：`scope_kind: Literal["global", "worker", "handoff"]`, `scope_id: str | None`
- `SymbolTable` 使用复合 key `_variables: dict[tuple[str, str|None, str], VariableSymbol]`
- 保留兼容接口 `self.variables: dict[str, VariableSymbol]`（仅存 global 变量）

### 2.4 HandoffContractIR

**文件**: `src/nl2spl/ir/worker_plan_ir.py` (行 290-310)

```python
@dataclass
class HandoffContractIR:
    handoff_id: str
    parent_worker_id: str
    child_worker_id: str
    input_variables: list[ContractFieldIR]
    output_variables: list[ContractFieldIR]
```

### 2.5 设计决策记录

D1-D10 已记录在 `docs/migration-worker-aware-pipeline.md` 第 0 节。

---

## 3. T1 — Stage 7 Worker-Scoped（已完成）

### 3.1 文件结构重组织

```
src/nl2spl/pipeline/stages/stage7_step_extractor/
├── __init__.py          # from .extractor import StepExtractor
├── extractor.py         # 主类 StepExtractor(PipelineStage, LegacyMethodsMixin, WorkerScopedMethodsMixin)
├── legacy.py            # LegacyMethodsMixin — 非 worker-scoped 辅助方法
└── worker_scoped.py     # WorkerScopedMethodsMixin — 新增方法
```

使用 mix-in 模式，`StepExtractor` 多继承。

### 3.2 新增方法清单

| 方法 | 文件 | 行数 | 说明 |
|------|------|------|------|
| `execute_worker_scoped()` | worker_scoped.py | 29-90 | 入口：按 worker 提取 steps |
| `_extract_steps_for_worker()` | worker_scoped.py | 92-233 | 单 worker LLM 调用 |
| `_build_worker_prompt_variables()` | worker_scoped.py | 235-264 | prompt 变量构建（Phase 1 用 global vars） |
| `_generate_handoff_steps()` | worker_scoped.py | 266-298 | D1：从 handoffs 生成 INVOKE_WORKER/CALL_API |
| `_build_invoke_step()` | worker_scoped.py | 300-331 | 构造 INVOKE_WORKER StepIR |
| `_build_api_call_step()` | worker_scoped.py | 333-353 | 构造 CALL_API StepIR |
| `_get_invoke_source_spans()` | worker_scoped.py | 355-379 | D2：优先 invoke_location_hint，未设置返回空+warn |
| `_validate_step_span_ownership()` | worker_scoped.py | 381-420 | D5：span ownership violation = error |

### 3.3 关键设计要点

- **D1**: `_generate_handoff_steps` 只从 `WorkerHandoffIR` 生成，不从 `decisions` 生成
- **D2**: `_get_invoke_source_spans` 优先 `invoke_location_hint.after_span_id/before_span_id`，无 hint 时返回空列表 + warning（不 fallback 到全部 from_worker.owned_span_ids）
- **D5**: `_validate_step_span_ownership` 对非 handoff 步骤的 span ownership violation 抛出 `StageError`。INVOKE_WORKER/CALL_API 步骤宽容处理（warning）
- **Phase 1**: `_build_worker_prompt_variables` 仍用全局 variables（`symbol_table.variables`），Phase 2（工程师 C）接入 scoped 后需更新

### 3.4 Legacy 方法（`legacy.py`，保留兼容）

| 方法 | 说明 |
|------|------|
| `_flow_for_step_prompt()` | 生成 legacy prompt 用 flow（清除 delegation_candidates） |
| `_assert_legacy_main_view_excludes_child_spans()` | 断言 legacy 路径不包含 child span |
| `_apply_worker_plan_handoffs()` | 从 handoffs 生成 INVOKE_WORKER/CALL_API 步骤，追加到 steps 列表 |
| `_step_for_invoke_handoff()` | 构造单个 INVOKE_WORKER step |
| `_step_for_api_handoff()` | 构造单个 CALL_API step |
| `_matching_handoff_step()` | 查找是否有相同 handoff_id 的已有 step |
| `_declare_handoff_variables()` | 为 handoff 声明 input/output 绑定变量 |

---

## 4. T1.5 — Stage 9.5 Worker-Scoped（已完成）

### 4.1 文件结构

```
src/nl2spl/pipeline/stages/stage9_5_normalizer/
├── __init__.py
├── normalizer.py         # 主类 IRNormalizer（继承 WorkerScopedMixin）
├── worker_scoped.py      # WorkerScopedMixin — normalize_worker_scoped + 5 项校验
├── validation.py
├── helpers.py
├── normalization.py
├── flow_classification.py
└── worker_handoffs.py
```

### 4.2 新增方法清单

| 方法 | 文件 | 说明 |
|------|------|------|
| `normalize_worker_scoped()` | worker_scoped.py:17-80 | 入口：串联 5 项校验 |
| `_validate_span_ownership()` | worker_scoped.py:82-139 | D5：跨 worker span 校验 |
| `_validate_handoffs()` | worker_scoped.py:141-232 | D10：handoff step shape 完整性校验 |
| `_validate_output_binding()` | worker_scoped.py:234-265 | child output 是否被 parent 消费 |
| `_validate_reachability()` | worker_scoped.py:267-311 | producer/consumer reachability（warning） |
| `_validate_handoff_types()` | worker_scoped.py:313-347 | INVOKE_WORKER vs CALL_API 分离校验 |

### 4.3 校验规则汇总

| 校验项 | 级别 | 规则 |
|--------|------|------|
| span ownership | **error** | 非 handoff 步骤引用非本 worker span |
| main→child span leakage | **error** | main worker 普通步骤引用 child-owned span |
| handoff 步骤存在 | **error** | 每个 handoff 必须有对应步骤 |
| handoff step shape | **error** (D10) | command_type、target、inputs、outputs 全量匹配 |
| output binding | **error** | child output 在 handoff.output_bindings 中绑定 |
| reachability | warning | consumer variable 无 local producer 且不在 input_contract 中 |
| handoff types | **error** | INVOKE_WORKER 有 to_worker，CALL_API 有 api_ref |

---

## 5. T2 — SymbolTable Scope 支持（已完成）

### 5.1 已实现方法

| 方法 | 行数 | 说明 |
|------|------|------|
| `SymbolTable.__init__()` | 51-56 | `_variables`（复合 key）+ `variables`（兼容） |
| `SymbolTable.declare()` | 58-90 | 声明 global scope 变量 |
| `SymbolTable.declare_scoped()` | 171-211 | 声明任意 scope 变量 |
| `SymbolTable.get_variables_for_worker(worker_id)` | 213-236 | 获取 worker 可见变量（global + worker-scoped） |
| `SymbolTable.get_variables_for_handoff(handoff_id)` | 238-261 | 获取 handoff 可见变量（global + handoff-scoped） |
| `SymbolTable.get_variable_list_for_worker_prompt(worker_id)` | 263-286 | 为 LLM prompt 生成带 scope 信息的变量列表 |
| `SymbolTable.get_all_declared_variables()` | 288-312 | 获取所有已声明变量（用于 SPL DEFINE_VARIABLES） |

### 5.2 Phase 1 限制

当前 `Stage 7._build_worker_prompt_variables()` **仍使用 `symbol_table.variables`（global only）**，未接入 `get_variables_for_worker()`。

**TODO（工程师 C）**: 在 Stage 6 完成 worker-scoped 资源提取后，更新 Stage 7 的 `_build_worker_prompt_variables` 使用 scoped 接口。

---

## 6. Orchestrator 修改

**文件**: `src/nl2spl/pipeline/orchestrator.py`

### 6.1 Stage 7 双路径（行 221-251）

```python
if (config.enable_worker_boundary_planner and worker_flow_plan and worker_block_plan and worker_plan):
    # Worker-aware path
    worker_step_plan, symbol_table = self._run_stage7_worker_scoped(...)
    steps = worker_step_plan.get_all_steps()
else:
    # Legacy path
    steps, symbol_table = self._run_stage7(...)
```

### 6.2 Stage 9.5 双路径（行 271-319）

```python
if (config.enable_worker_boundary_planner and worker_flow_plan and worker_block_plan and worker_step_plan and worker_plan):
    # Worker-aware path
    (...worker_step_plan..., normalization_errors, normalization_warnings) = self._run_normalization_worker_scoped(...)
else:
    # Legacy path
    (flow_structure, block_structure, steps, constraints, symbol_table, normalization_errors, ...) = self._run_normalization(...)
```

### 6.3 配置开关

- `config.enable_worker_boundary_planner` — 控制是否走 worker-aware 路径
- worker_aware path 入口：Stage 3.5 → Stage 4/5 → Stage 6 → Stage 7 → Stage 9.5 → Stage 10 → Stage 11
- legacy path fallback：所有阶段均保留

---

## 7. 测试覆盖

### 7.1 已通过测试

| 测试文件 | 内容 |
|----------|------|
| `tests/unit/ir/test_symbol_table_scope.py` (351行) | SymbolTable scope 全覆盖 |
| `tests/unit/ir/test_worker_step_plan_ir.py` | WorkerStepPlanIR 单元测试 |
| `tests/unit/ir/test_worker_plan_ir.py` | WorkerPlanIR 单元测试 |
| `tests/ir/test_child_worker_ir.py` | ChildWorkerIR 升级测试 |
| `tests/unit/pipeline/stages/test_worker_handoff_step_extraction.py` (238行) | Stage 7 handoff 生成测试 |
| `tests/unit/pipeline/test_worker_aware_orchestrator.py` | Orchestrator 双路径测试 |

### 7.2 相关但不属于工程师 A 的测试

| 文件 | 负责人 |
|------|--------|
| `tests/pipeline/stages/test_stage10_worker_scoped.py` | 工程师 B |
| `tests/pipeline/stages/test_stage11_child_worker_render.py` | 工程师 B |
| `tests/unit/pipeline/stages/test_stage6_worker_scoped.py` | 工程师 C |
| `tests/integration/test_multi_worker_pipeline.py` | 所有 |
| `tests/integration/test_multi_worker_orchestrator_rollout.py` | 所有 |

---

## 8. 待办事项（TODO）

### 8.1 工程师 A 剩余工作

- [x] T0: IR Contract 修正
- [x] T1: Stage 7 Worker-Scoped
- [x] T1.5: Stage 9.5 Worker-Scoped
- [x] T2: SymbolTable Scope 支持
- [ ] **代码审查**：审查工程师 B 的 T1.6 PR 和工程师 C 的 T2 PR
- [ ] **Phase 1→Phase 2 衔接**：当工程师 C 完成 Stage 6 scoped 后，更新 `Stage 7._build_worker_prompt_variables()` 从 `symbol_table.variables` 切换到 `symbol_table.get_variables_for_worker()`
- [ ] **T3 辅助**：协助移除 adapter（D6 决策）

### 8.2 依赖其他工程师

| 任务 | 依赖方 | 状态 |
|------|--------|------|
| T1.6: Stage 10/11 worker-aware | 工程师 B | 未知（需确认） |
| T2: Stage 6 worker-scoped | 工程师 C | 未知（需确认） |
| T3: adapter 移除 | 工程师 B + C | 未开始 |

---

## 9. 关键注意事项

### 9.1 设计决策约束

接任工程师必须遵守 `docs/migration-worker-aware-pipeline.md` 中冻结的 D1-D10 决策。特别强调：

- **D1**: INVOKE_WORKER 只从 `WorkerHandoffIR` 生成，不从 `decisions` 生成
- **D2**: `invoke_location_hint` 缺失时返回空 source_span_ids + warning，不 fallback
- **D5**: span ownership violation 是 **error**，不是 warning。StageError 会中断 pipeline
- **D6**: 保留 legacy path，等全部迁移完再删除
- **D10**: handoff step 校验必须是全量 shape 匹配

### 9.2 Phase 划分

- **Phase 1** (当前): Stage 7/9.5 worker-scoped，SymbolTable scope 接口就绪，但 Stage 7 仍用 global vars
- **Phase 2** (工程师 C): Stage 6 scoped resource + SymbolTable scope 接入
- **Phase 3** (工程师 B + 全队): 移除 adapter，全链路 worker-aware

### 9.3 常见陷阱

1. `WorkerStepPlanIR` 的 `main_worker_id` 是字符串，不要硬编码 `"worker_main"`
2. `symbol_table.variables` 只存 global 变量，worker-scoped 变量在 `symbol_table._variables` 中
3. Stage 7 的 `_build_worker_prompt_variables` 标注了 "Phase 1 暂用全局"，未来需更新
4. handoff step 的 `kind="invoke"` 或 `kind="tool"`，在后续 Stage 10/11 中会被识别

---

## 10. 运行命令

```bash
# 运行工程师 A 相关全部测试
pytest tests/unit/ir/test_symbol_table_scope.py tests/unit/ir/test_worker_step_plan_ir.py tests/unit/ir/test_worker_plan_ir.py tests/ir/test_child_worker_ir.py tests/unit/pipeline/stages/test_worker_handoff_step_extraction.py tests/unit/pipeline/test_worker_aware_orchestrator.py -v

# 运行全量单元测试（当前可能部分失败，因工程师 B/C 工作未完成）
pytest tests/unit/ tests/ir/ -v

# 运行集成测试（需配置 LLM mock 或真实 API）
pytest tests/integration/ -v
```
