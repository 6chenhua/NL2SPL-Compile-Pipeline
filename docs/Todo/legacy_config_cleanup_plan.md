# Legacy configuration and code cleanup plan

## 背景

当前代码保留了多条迁移期入口：部分通过 `PipelineConfig` feature flag 打开，部分是默认关闭但仍可配置启动的兼容路径，还有一部分是默认配置会走到的旧路径。目标是把不会再使用的 legacy 运行路径整理出来，并为后续删除配置项、代码和测试制定可验证的执行顺序。

本文只制定计划，不直接删除代码。当前仓库有大量未提交变更，执行清理时应继续避免回滚无关改动。

## 清理原则

1. 先固定唯一生产路径，再删配置。
2. 先删 orchestrator 分支，再删 stage 内部 legacy mixin / wrapper。
3. 先用现有 worker-aware 和 post-normalize IRS 测试锁住行为，再删除 legacy 快照测试。
4. 删除配置项时同步删除 README、examples、历史 TODO 中仍鼓励打开旧路径的说明。
5. 对仍有业务价值但不应再由配置控制的行为，改为无配置的默认行为，而不是继续保留开关。

## Legacy 清单

| 类别 | 配置 / 入口 | 当前默认 | 触发位置 | 计划处理 |
| --- | --- | --- | --- | --- |
| 全链路 legacy flat pipeline | `enable_worker_boundary_planner` | `False` | `src/nl2spl/config.py`, `src/nl2spl/pipeline/orchestrator.py` | 改为 worker-aware 唯一路径，删除 flag 和 `else` legacy 分支 |
| Stage 3.5 单调用 planner | `enable_worker_boundary_planner_split` | `True` | `stage3_5_worker_boundary_planner/executor.py` | 固化 split 3.5a/3.5b/3.5c，删除单调用入口 |
| Stage 3.5 split 失败回退 | `enable_worker_boundary_single_call_fallback` | `False` | `stage3_5_worker_boundary_planner/executor.py` | 删除配置和 fallback，split 失败直接报错 |
| Stage-local IRS prompt 注入 | `enable_irs_prompt_builder` | `False` | Stage 3.5 / 4 / 7 prompt builder | 若 post-normalize IRS 是最终权威，删除 prompt 注入开关与 checklist 注入路径 |
| Stage 4 IRS wrapper | `enable_irs_stage4_exception_flow_check` | `False` | `orchestrator.py`, `stage4_flow_assembler/irs_checker.py` | 删除 runtime flag；保留 checker 仅作单测/参考，或合并到 post-normalize 权威后删除 |
| Stage 7 IRS wrapper | `enable_irs_stage7_step_check` | `False` | `orchestrator.py`, `stage7_step_extractor/irs_checker.py` | 同 Stage 4 |
| Stage-local diagnostic merge | `enable_irs_diagnostic_consolidation` | `False` | `orchestrator.py` | 已被 `enable_irs_post_normalize_check=True` 取代，删除 |
| IRS v6 opt-in runner | `enable_irs_v6_runner`, `enable_irs_worker_delegation_check` | `False` | `orchestrator.py`, `compiler/irs/factory.py` | 决策：若 Stage 3.5 worker/delegation IRS 仍需要，改为 worker-aware 路径默认运行；否则删除 runner 接入配置 |
| Post-normalize IRS 总开关 | `enable_irs_post_normalize_check` | `True` | `orchestrator.py` | 固化为默认必跑，删除关闭路径和关闭时的 stage-local 替代路径 |
| LLM conflict analyzer | `enable_llm_conflict_analyzer` | `False` | `orchestrator.py`, `semantic_conflict.py` | 若不再使用 LLM 冲突分析，删除开关与 LLM analyzer；保留 no-op 或直接移除分析器接口 |
| Stage 6 resource prompt V2 | `enable_stage6_resource_context_v2` | `False` | `stage6_resource_extractor/legacy.py`, `worker_scoped.py` | 若 V2 是期望路径，改为无开关默认；删除旧 raw JSON prompt 分支 |
| Stage 6 resource name filter | `enable_resource_name_filter` | `False` | `stage6_resource_extractor/legacy.py`, `worker_scoped.py` | 若过滤规则已确认正确，改为默认开启并删除开关；否则整体删除该实验路径 |
| Adapter LLM engine modes | `adapter_llm_engine` / `NL2SPL_ADAPTER_LLM_ENGINE` | `"off"` | `config.py`, `adapters/registry.py` | 决策：如果不再支持 LLM adapter enrichment，删除 `generic_only` / `structural_enrich` / `all` |
| Adapter-guided route LLM fallback | `allow_adapter_guided_fieldroute_fallback` | `False` | `stage2_field_router.py` | 删除 fallback 开关，失败保持 fail-fast |
| Adapter-guided route LLM disable | `enable_adapter_guided_fieldroute_llm` | `True` | `stage2_field_router.py` | 若已成为标准路径，删除关闭分支；若 LLM 路径不稳定，反向删除 LLM refinement |

## 可删除或重构的代码区域

### 1. Orchestrator 双路径

重点文件：

- `src/nl2spl/pipeline/orchestrator.py`
- `src/nl2spl/config.py`
- `tests/integration/test_multi_worker_orchestrator_rollout.py`
- `tests/pipeline/test_worker_aware_integration.py`
- `tests/integration/test_v5_irs_pipeline.py`

清理动作：

1. 把 Stage 3.5 worker boundary planning 设为必经路径。
2. 删除 `worker_plan is None` 相关 legacy flow/block/resource/step/normalizer/assembler 分支。
3. 删除 `_run_stage10()` legacy assemble 入口，只保留 `_run_stage10_worker_scoped()`。
4. 删除 `enable_worker_boundary_planner=False` 的集成测试，保留 worker-aware 回归测试。
5. 更新 README 中 “Dual execution paths” 和配置表。

### 2. Stage 3.5 legacy single-call planner

重点文件：

- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py`
- `prompts/stage3_5_system.txt`
- `tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py`
- `tests/integration/test_multi_worker_pipeline.py`

清理动作：

1. 删除 `enable_worker_boundary_planner_split` 和 `enable_worker_boundary_single_call_fallback`。
2. 删除 `_execute_legacy_single_call()`。
3. 删除 `prompts/stage3_5_system.txt`，保留 `stage3_5a_candidate_extractor_system.txt` 与 `stage3_5b_boundary_decision_system.txt`。
4. 删除 split disabled / fallback 相关测试。
5. 验证 Stage 3.5 split 的错误路径仍有明确 `StageError`。

### 3. Stage 6 / Stage 7 legacy mixin

重点文件：

- `src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/extractor.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py`

清理动作：

1. 删除 Stage 6 `LegacyMethodsMixin`，让 `ResourceExtractor` 只暴露 worker-scoped 执行入口。
2. 把 hard fact variable merge 中仍有价值的逻辑移到 worker-scoped helper，避免随 legacy 文件一起误删。
3. 删除 Stage 7 `LegacyMethodsMixin` 中只服务 legacy main view 的 guard / handoff materialization。
4. 确认 `execute_worker_scoped()` 已覆盖 handoff step 生成和 scoped symbol table 更新。
5. 删除直接调用 `stage.execute(...)` 的 legacy 单元测试，迁移为 worker-scoped fixture。

### 4. Bridge compatibility fallback

重点文件：

- `src/nl2spl/pipeline/fact_bridges.py`
- `src/nl2spl/pipeline/orchestrator.py`
- `src/nl2spl/adapters/structural_nl.py`
- `src/nl2spl/pipeline/route_exception_materializer.py`

清理动作：

1. 确认 route annotation 已是 failure mode / delegation intent 的唯一生产证据来源。
2. 删除 `bridge_failure_modes()` legacy global bridge。
3. 删除 `bridge_failure_modes_worker_scoped()` 的 hard-fact fallback 调用；如果仍需补洞，应迁移到 route-driven materializer。
4. 删除 `bridge_delegation_intents()` fallback diagnostics，使用 `diagnose_delegation_intents_from_routes()`。
5. 删除 structural adapter 中 “bridge fallback” 注释和只为 bridge 生成的 hard fact 兼容字段。

注意：`src/nl2spl/adapters/structural_nl.py` 中的 exact-schema hard fact 代码不能整段一次性删除。`failure handling` / `delegation policy` 分支只服务 bridge fallback，属于本 phase 的删除范围；但 `inputs for each run` / `required outputs` 分支仍为 Stage 3.5 worker contract、Stage 6 resource context / hard fact merge、provenance 和 required-output diagnostics 提供权威变量事实。删除 inputs/outputs 分支前，必须先确定 route annotations 或 semantic packets 已能完整替代 hard input/output 的下游契约。

### 5. IRS stage-local 与最终权威重复路径

重点文件：

- `src/nl2spl/compiler/irs/factory.py`
- `src/nl2spl/compiler/irs/checkers/exception_flow.py`
- `src/nl2spl/compiler/irs/checkers/step.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py`
- `src/nl2spl/compiler/diagnostic_analyzer.py`

清理动作：

1. 固化 `PostNormalizeIRSChecker` 为构件级诊断最终权威。
2. 删除 `enable_irs_post_normalize_check=False` 的替代执行路径。
3. 删除 `enable_irs_diagnostic_consolidation`。
4. 决定 Stage 4 / Stage 7 checker 是否仅保留为 IRS framework 单测样例；若不保留，删除 checker、wrapper 与 factory 注册参数。
5. 删除或归档 `DiagnosticAnalyzer` legacy reference；它已声明不在 production orchestrator path。

### 6. Adapter LLM 与 fallback 配置

重点文件：

- `src/nl2spl/config.py`
- `src/nl2spl/adapters/registry.py`
- `src/nl2spl/adapters/generic_nl.py`
- `src/nl2spl/adapters/structural_nl.py`
- `src/nl2spl/pipeline/stages/stage2_field_router.py`
- `tests/unit/test_input_adapters.py`
- `tests/unit/test_input_adapter_pipeline.py`
- `tests/unit/test_adapter_guided_fieldroute_refinement.py`

清理动作：

1. 先确定输入适配器策略：纯 deterministic structural/generic，或默认 LLM enrich。
2. 删除不再允许的 `adapter_llm_engine` mode 和 `NL2SPL_ADAPTER_LLM_ENGINE` 环境变量。
3. 若 adapter-guided field route LLM 是标准能力，删除 `enable_adapter_guided_fieldroute_llm=False` 路径。
4. 删除 `allow_adapter_guided_fieldroute_fallback=True`，失败保持显式错误。
5. 更新测试名称，避免继续把 fallback 行为当目标行为。

## 推荐执行顺序

### Phase 0: 基线确认

1. 运行当前 worker-aware 主路径测试：
   `python -m pytest tests/pipeline/test_worker_aware_integration.py tests/unit/pipeline/test_worker_aware_orchestrator.py -q`
2. 运行 IRS post-normalize 权威测试：
   `python -m pytest tests/unit/pipeline/stages/test_final_irs_checker.py tests/unit/compiler/irs/test_r9_final_audit.py -q`
3. 记录失败项，不在 cleanup PR 中混入行为修复。

### Phase 1: 固化 worker-aware pipeline

1. 删除 `enable_worker_boundary_planner` 配置。
2. orchestrator 无条件运行 Stage 3.5。
3. 删除所有 `worker_plan is None` 的生产分支。
4. 删除 legacy path integration tests。
5. 更新 README 和 examples，使示例不再传 `enable_worker_boundary_planner=True`。

### Phase 2: 删除 Stage 3.5 单调用兼容

1. 删除 split / fallback 配置项。
2. 删除 `_execute_legacy_single_call()` 和 `stage3_5_system` prompt。
3. 删除 split disabled / single-call fallback 测试。
4. 验证 split planner 单元测试和 orchestrator worker-aware 测试。

### Phase 3: 收敛 Stage 6 / Stage 7 worker-scoped 接口

1. 删除 Stage 6 `legacy.py` 并更新 `ResourceExtractor` 继承关系。
2. 删除 Stage 7 `legacy.py` 或把仍需的纯 helper 移入 `worker_scoped.py`。
3. 删除 legacy `execute()` 调用测试，改为 worker-scoped 测试。
4. 验证 Stage 6/7 worker-scoped、Stage 10 assembler 和 renderer 测试。

### Phase 4: 删除 bridge fallback

1. 先补 route-driven failure/delegation 覆盖测试。
2. 删除 hard-fact bridge fallback 调用。
3. 删除 `fact_bridges.py` 中不再被引用的 bridge 函数。
4. 更新 structural adapter 注释与 hard fact 兼容输出。

### Phase 5: 固化 IRS final authority

1. 删除 post-normalize IRS 关闭路径。
2. 删除 stage-local diagnostic consolidation。
3. 删除 Stage 4 / Stage 7 IRS runtime flags。
4. 决定是否保留 Stage 4 / Stage 7 checker 作为 IRS framework examples；若删除，同步清理 factory 和 tests。

### Phase 6: 清理 adapter / experimental flags

1. 删除 adapter LLM engine 中不再使用的 mode。
2. 删除 adapter-guided field route fallback 配置。
3. 对默认启用的 field route LLM，保留 fail-fast；或完全回退 deterministic，但不能继续保留双模式。
4. 更新 `.env.example`、README、examples。

## 测试与验收

每个 phase 至少运行：

```powershell
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest tests/pipeline -q
```

最终验收还需要：

```powershell
python -m pytest -q
rg -n "legacy|Legacy|compatibility fallback|enable_worker_boundary_planner|enable_worker_boundary_planner_split|enable_worker_boundary_single_call_fallback|enable_irs_diagnostic_consolidation|enable_irs_stage4_exception_flow_check|enable_irs_stage7_step_check|enable_irs_post_normalize_check=False|allow_adapter_guided_fieldroute_fallback" src tests README.md examples docs
```

验收标准：

1. `PipelineConfig` 不再暴露已删除路径的配置项。
2. README 配置表不再列出删除的 flag。
3. examples 不再显式打开“当前应为默认”的路径。
4. `src` 中不再有 production legacy flat pipeline 分支。
5. 所有保留的 `fallback` 文字都必须是局部算法 fallback，而不是旧运行路径 fallback。

## 风险点

1. 测试中仍有大量直接调用 stage `execute()` 的 fixture。这些测试可能不是生产路径，但会阻碍删除 mixin，需要按 worker-scoped fixture 重写。
2. `FieldRouteIR` 的六个 legacy list 仍是很多 stage 的兼容输入。删除它们应单独立项，不能和本次配置清理混在同一个 PR。
3. `SymbolTable` 的 global variables 兼容接口仍被多处使用。删除 legacy pipeline 不等于可以立即删除全局查询接口。
4. `bridge_failure_modes_worker_scoped()` 仍在补 failure mode coverage。删除前必须证明 route annotation materializer 对 structural 与 generic 输入都覆盖。
5. Stage-local IRS checker 可能仍有 framework regression 价值。删除 runtime flag 后，可选择把 checker 测试降级为 framework-level unit tests。

## 建议最终配置面

清理完成后，`PipelineConfig` 应只保留运行必需和真正稳定的操作配置：

- LLM 连接配置：`llm`
- 输出与 trace 配置：`output_dir`, `run_name`, `final_spl_filename`, `save_intermediate`, `trace_dir`
- 日志配置：`log_level`, `log_file`
- 验证配置：`validate_spl`, `strict_mode`
- 重试配置：`max_retries`, `retry_delay`

不应继续保留迁移期开关、兼容 fallback 开关和默认应为唯一行为的开关。
