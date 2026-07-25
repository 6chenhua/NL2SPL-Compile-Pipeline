# SPL Web Demo 功能需求文档

版本：v0.3
状态：Service contract demo 规划稿，已按本地代码事实核查收敛 MVP 范围
目标目录建议：`apps/spl-web-demo/`

> 前端页面信息架构已由 [SPL Web Demo 前端详细设计](./spl_web_demo_frontend_detailed_design_zh.md) 重新规划为“独立生成页 + SPL 工作台页”。该文档取代本文第 6 章中的旧单页布局建议；Service contract、功能需求和 API 边界仍以本文为准。

## 1. 背景

当前 NL2SPL 系统的核心能力主要处于后端业务逻辑层，即 Service 层和编译流水线层。为了验证这些能力是否适合未来对接网络 API 和前端，需要实现一个轻量级 Web Demo。本文档进一步将该 Demo 收敛为 **Service contract demo**：前端只是最小展示面，真正要验证的是后端 service contract、snapshot 注册、presentation DTO、preview/apply/verification 编排，以及必要的薄 API projector 是否足够稳定。

该 Demo 不追求完整产品化体验，也不追求复杂前端架构。它的主要价值是通过一个真实但最小的前后端交互链路，检验现有后端是否满足以下条件：

- 核心编译能力可以被 API 层干净调用。
- SPL Editing 能力可以通过稳定的 Service 层完成 issue 展示、解释、修复预览和确认应用。
- SPL Construct、Issue、Repair、Preview、Provenance 的职责边界清晰。
- API 层不需要解析诊断文本、不需要直接修改 IR、不需要绕过现有业务逻辑。

### 1.1 本地代码事实核查

本需求文档以本地工作区代码为准，而不是以公开 README 为准。README 可能滞后于当前实现。

截至本次核查，本地代码中已经存在以下 SPL Editing 相关组件：

- `src/nl2spl/compiler/spl_editing/core/service.py`
  - `class SPLEditingService`
  - `preview_suggestion(...)`
  - `apply_preview_result(...)`
  - `verify_session(...)`
- `src/nl2spl/compiler/spl_editing/presentation/service.py`
  - `class SPLEditingPresentationService`
  - `get_run_presentation(...)`
  - `list_issue_presentations(...)`
  - `get_issue_detail_presentation(...)`
  - `get_repair_interaction(...)`
  - `submit_repair_directive_draft(...)`
  - `preview_repair_directive(...)`
  - `apply_repair_preview(...)`
- `src/nl2spl/compiler/spl_editing/core/revision.py`
  - `RevisionToken`
  - `ArtifactSnapshot`
  - `overlay_version`
- `src/nl2spl/compiler/spl_editing/interaction/model.py`
  - `revision_token_string(...)`
  - `RepairInteractionView`
  - `SubmitRepairDirectiveDraftRequest`
- `src/nl2spl/compiler/spl_editing/presentation/model/issue.py`
  - `IssueDetailPresentationView`
  - `RepairOptionView`
- `src/nl2spl/compiler/spl_editing/presentation/explanation_cache.py`
  - `read_cached_issue_explanation(...)`
  - `schedule_issue_explanations(...)`
- `src/nl2spl/compiler/spl_editing/presentation/ai_explainer.py`
  - `schema_version="issue_explanation.v1"`

因此，本 Demo 的定位不是从零设计 SPL Editing 服务契约，而是优先验证这些已有 Service / Presentation / Snapshot 能力是否能被轻量 API 层稳定调用。

如果后续实现 API 时发现某个字段或方法签名与本文档不一致，应优先对齐实际代码；只有在实际服务缺少必要的薄展示投影时，才允许新增小型 adapter / projector。

Contract Probe 需要直接调用的入口也已核查如下：

| 入口 | 已核查签名 / 返回 | 对 Demo 的影响 |
|---|---|---|
| `PipelineOrchestrator.run(...)` | `run(self, raw_text: str) -> PipelineResult` | 编译入口是同步方法；`PipelineResult` 带 `spl_text`、`compile_diagnostics`、`traces`、`final_ir_package`、`spl_editing_snapshot_path`、`spl_editing_snapshot_status` 等字段。 |
| `SPLEditingService.register_snapshot_file(...)` | `register_snapshot_file(self, path: Path) -> str` | 该入口要求 canonical snapshot JSON 文件路径，并返回 `run_id`；如果 API 走这个入口，Contract Probe 之后的实现不能只做纯内存 registry，至少需要临时 run 目录保存 snapshot 文件。 |
| `SPLEditingService.register_artifact_snapshot(...)` | `register_artifact_snapshot(self, snapshot: ArtifactSnapshot) -> str` | 这是内存对象入口；MVP 默认不走这条路。仅当 `register_snapshot_file(path)` 方案不可行，且 API 能从编译结果稳定拿到 `ArtifactSnapshot` 时再作为备选。 |
| `SPLEditingService.preview_suggestion(...)` | `preview_suggestion(session_id, suggestion_id, *, user_text=None, ttl_seconds=None) -> PreviewMaterializationResult` | preview 的真实返回对象是 `PreviewMaterializationResult`，包含 `preview_id`、hash 字段、`rendered_preview`、`typed_artifact` 等。 |
| `SPLEditingService.apply_preview_result(...)` | `apply_preview_result(session_id, suggestion_id, preview_id, *, user_text=None) -> EditingSession` | core apply 只返回更新后的 `EditingSession`，不直接返回 verification。 |
| `SPLEditingService.verify_session(...)` | `verify_session(session_id: str) -> VerificationResult` | verification 是独立调用，返回 `accepted`、`lane`、`failure_reasons`、diagnostic diff 字段。 |
| `SPLEditingPresentationService.submit_repair_directive_draft(...)` | `submit_repair_directive_draft(request: SubmitRepairDirectiveDraftRequest) -> RepairDirectiveValidationResult` | 用户选择 option 并提交字段后，先生成 normalized directive；成功时 `normalized_directive_id` 是后续 preview/apply 的 `directive_id`。 |
| `SPLEditingPresentationService.preview_repair_directive(...)` | `preview_repair_directive(directive_id: str) -> WorkerDelegationPreviewHandle` | presentation facade 会把 `directive_id` 编排成 `session_id`、`suggestion_id` 和 preview。 |
| `SPLEditingPresentationService.apply_repair_preview(...)` | `apply_repair_preview(directive_id: str, preview_id: str) -> tuple[EditingSession, VerificationResult]` | presentation facade 已组合 `apply_preview_result(...)` 与 `verify_session(...)`；API 可优先复用它以保持路由层更薄。 |

### 1.2 Service 契约探针要求

在实现 HTTP API 前，必须先写一个不经过 HTTP 的本地 contract probe 脚本，直接调用上述入口并 dump 真实返回对象的字段。

该脚本至少要验证：

- `PipelineOrchestrator.run(...)` 是否在当前配置下生成 `spl_editing_snapshot_path`。
- API 默认使用 `register_snapshot_file(path)` 走通 snapshot 注册，因为 `PipelineResult` 直接暴露 `spl_editing_snapshot_path`；`register_artifact_snapshot(snapshot)` 仅作为文件路径方案不可行时的备选。
- `spl_editing_snapshot_status` 的真实取值和失败策略。
- issue list/detail 的真实 Presentation DTO 字段。
- `submit_repair_directive_draft(...)` 需要的最小可用 request 字段，以及成功/失败时 `RepairDirectiveValidationResult` 的真实字段。
- `normalized_directive_id` 是否可稳定作为 API 层 `directive_id` 暴露。
- preview 的真实 `PreviewMaterializationResult` 字段。
- apply 后是否通过 `SPLEditingPresentationService.apply_repair_preview(...)` 一次拿到 `(session, verification)`，或者需要 API 层显式执行 `apply_preview_result(...)` + `verify_session(...)`。
- verification 的真实 `VerificationResult` 字段。

第 9 章中的 JSON 是 API 投影示例，不是对底层 Service 返回结构的断言。Contract Probe 完成后，应使用真实 dump 结果修订这些 JSON 示例。

## 2. 产品目标

### 2.1 核心目标

用户可以在前端完成以下流程：

1. 输入初始自然语言需求。
2. 后端生成 SPL IR、snapshot、diagnostics、traces。
3. 前端以卡片形式展示 SPL 中的 Construct。
4. 用户可以查看每个 Construct 的溯源信息：来源于哪些 Span，以及每个 Span 的原文内容。
5. 前端展示 Issue Console。
6. 用户点击某个 Issue，查看后端返回的 Issue Detail 和缓存的 AI Issue Explanation。
7. 用户选择某个修复策略。
8. 用户可选择性输入自己的补充建议。
9. 用户点击修复，后端生成修复建议和 SPL Preview。
10. 前端以卡片形式展示修复建议和 Preview 后的 SPL。
11. 用户确认应用修复，或者取消修复。
12. 应用修复后，前端刷新 SPL、Issue、Provenance 状态。

### 2.2 验证目标

该 Demo 应重点验证：

- `PipelineOrchestrator` 是否可以作为编译入口被 API 调用。
- `SPLEditingService` 是否可以作为 repair/session/preview/apply/verify 的业务入口。
- `SPLEditingPresentationService` 是否可以作为 Issue、Repair Option、Interaction View 的展示入口。
- Issue Explanation 是否可以从 snapshot presentation cache 中读取，而不是依赖 demo 脚本或 CLI 输出。
- Construct Provenance 是否可以通过 `TraceRecord` 和 `SpanIR` 结构化返回。
- 用户确认修复后，新增或修改的 Construct 是否能显示 `user_confirmed_repair` 溯源。

### 2.3 MVP 分层

MVP 应按以下层级冻结范围，避免把 Service contract demo 扩成完整 Web 产品：

- MVP-A：编译、snapshot 注册、SPL cards、construct provenance、issue list/detail、explanation cache 展示。该层应覆盖所有 presentation-supported issue。
- MVP-B：repair interaction、directive、preview、apply、verification 闭环。当前优先验证 worker delegation closure flow，因为 `get_repair_interaction(...)`、`submit_repair_directive_draft(...)`、`preview_repair_directive(...)`、`apply_repair_preview(...)` 的已核查实现主要围绕 worker delegation directive。
- MVP-C：`missing_handler`、`missing_output_producer` 等其他 repair option。只有 contract probe 证明其已接入同一 directive presentation facade 时，才纳入 MVP-B 闭环；否则仅展示 issue/detail/repair option，不进入 directive preview/apply。

## 3. 非目标

MVP 阶段不做以下功能：

- 用户登录、权限、团队协作。
- 多项目管理。
- 完整数据库持久化。
- 复杂可视化画布。
- 前端直接编辑 IR。
- 前端解析 `CompileDiagnostic.message`。
- 路由层直接修改 snapshot 或 stage IR。
- 未确认的 LLM 建议直接进入可渲染 SPL。
- 为了前端展示而新增旁路业务逻辑。

## 4. 系统边界

### 4.1 后端分层

建议保持以下职责边界：

| 层级 | 职责 |
|---|---|
| Compiler / Pipeline | 从自然语言需求生成 SPL IR、diagnostics、traces、snapshot |
| IRS | 判断 Construct slot 是否满足，投射 compile diagnostics |
| SPL Editing Core | issue extraction、repair session、suggestion、preview、apply、verify |
| Presentation Service | 生成前端/CLI 可消费的 Issue、Repair Option、Interaction DTO |
| API Layer | HTTP DTO 转换、Service 调用、错误码映射、轻量聚合 |
| Frontend | 展示数据、收集用户输入、驱动交互流程 |

### 4.2 API 层禁止事项

API 层不得：

- 解析 diagnostic 文本来判断 issue 类型。
- 自行判断某个 issue 是否可修。
- 自行构造 repair patch payload。
- 直接修改 snapshot、IR、stage artifact。
- 从 `feedback_report.md` 或 `final_spl.txt` 反推业务状态。
- 把未确认的 LLM suggestion 标记为 source-backed 或 renderable。

### 4.3 允许新增的薄投影层

当前后端已有 `ArtifactSnapshot`、`TraceRecord`、`SpanIR`、Presentation DTO 和 preview artifact，但没有核查到一个现成、稳定的 `SplConstructCardProjector`。因此 Demo 允许新增薄投影层，用于把结构化后端对象变成前端卡片 DTO。

允许新增：

- `CardProjector`
- `ProvenanceProjector`
- `PreviewCardProjector`
- API DTO serializer

禁止新增：

- diagnostic message parser
- repair rule / repairability rule
- IR / snapshot / stage artifact mutation logic
- `final_spl.txt` parser
- `feedback_report.md` parser

薄 projector 只能消费结构化对象，例如 `ArtifactSnapshot`、`FinalIRPackage`、`TraceRecord`、`SpanIR`、`PreviewMaterializationResult.typed_artifact`。如果没有稳定 typed artifact，第一版应降级展示 `rendered_preview`，不得解析 SPL 文本来构造业务状态。

## 5. 用户角色

MVP 只有一个用户角色：

- Demo User：输入需求、查看 SPL、查看 issue、选择修复策略、确认或取消修复。

## 6. 页面设计

### 6.1 单页工作台

推荐做成一个单页应用：

```text
---------------------------------------------------------------+
| 需求输入区                                                     |
| [textarea]                                      [Generate]     |
+-----------------------------+---------------------------------+
| SPL Construct Cards          | Issue Console                   |
| - Worker                     | - Editable Issues              |
| - Flow                       | - Review Only                  |
| - Step                       | - Developer / Deferred         |
| - Exception Flow             |                                 |
| - API                        | Issue Detail / Explanation      |
| - Variable / Output          | Repair Options                  |
+-----------------------------+---------------------------------+
| Repair Preview / Provenance Detail Drawer                     |
+---------------------------------------------------------------+
```

### 6.2 前端布局要求

- 功能优先，样式保持简洁。
- 不需要复杂动画。
- Construct、Issue、Repair Option、Preview 都使用卡片展示。
- Provenance Detail 可以使用右侧抽屉或下方面板。
- 移动端只需基本可用，不作为第一阶段重点。

## 7. 核心用户流程

### 7.1 编译生成 SPL

1. 用户输入自然语言需求。
2. 点击 `Generate`。
3. 前端调用 `POST /api/demo/v1/runs`。
4. 后端执行 pipeline。
5. 后端返回 `run_id`、`snapshot_id`、`overlay_version`、`revision_token`、`spl_cards`、`issue_summary`。
6. 前端展示 SPL Construct Cards 和 Issue Console。

### 7.2 查看 Construct 溯源

1. 用户点击某个 Construct 卡片上的 `Provenance`。
2. 前端调用 `GET /api/demo/v1/runs/{run_id}/constructs/{construct_ref}/provenance`。
3. 后端根据 Construct 对应的 `target_ref` 查找 `TraceRecord`。
4. 后端根据 `TraceRecord.source_span_ids` 查找 `SpanIR`。
5. 前端展示：
   - Construct 基本信息。
   - trace relation。
   - trace explanation。
   - source span 列表和原文。
   - 是否需要确认。

### 7.3 查看 Issue Explanation

1. 用户点击 Issue Console 中某个 issue。
2. 前端调用 `GET /api/demo/v1/runs/{run_id}/issues/{issue_id}`。
3. 后端返回：
   - `IssueDetailPresentationView`
   - repair options
   - cached AI issue explanation
4. 前端展示 Explanation JSON 的用户友好视图。

### 7.4 选择修复策略并生成 Preview

1. 用户在 issue detail 中选择 repair option。
2. 前端调用 interaction API 获取该 option 需要的字段。
3. 用户填写可选补充建议或结构化字段。
4. 用户点击 `Submit Repair Input`。
5. 前端调用 directive draft API，后端返回 `directive_id`。
6. 前端调用 directive preview API。
7. 后端基于 `directive_id` 生成修复建议和 typed preview。
8. 前端展示：
   - LLM 修复建议。
   - expected effect。
   - risks。
   - SPL preview cards。
   - preview provenance。

### 7.5 确认或取消修复

确认：

1. 用户点击 `Apply Repair`。
2. 前端调用 `POST /api/demo/v1/runs/{run_id}/repair-directives/{directive_id}/previews/{preview_id}/apply`。
3. 后端应用 preview，并执行 verification。
4. 前端刷新 SPL cards、Issue Console、Construct Provenance。

取消：

1. 用户点击 `Cancel`。
2. MVP 前端本地清理 selected option、interaction、directiveId、preview。
3. snapshot 不发生变化。
4. 后端 DELETE preview endpoint 仅作为后续可选能力，不纳入 MVP 必做范围。

## 8. 功能需求

### FR-1 需求输入与编译运行

系统必须支持用户输入自然语言需求并触发编译。

输入：

- `raw_text`：用户需求文本。
- `language`：默认 `zh-CN`。
- `precompute_issue_explanations`：默认 `false`。MVP 默认按需生成单个 issue explanation，避免加重首屏耗时。

输出：

- `run_id`
- `snapshot_id`
- `overlay_version`
- `revision_token`
- `snapshot_status`
- `snapshot_path`
- `completeness`
- `spl_cards`
- `issue_summary`

Snapshot 状态必须按后端真实状态投射：

- `available`：snapshot 已写入，可进入 SPL Editing。
- `failed_best_effort`：编译成功，但 snapshot 写入失败；可展示 SPL，不可进入 issue repair / preview / apply。
- `failed_required`：snapshot 写入失败且配置要求必须有 snapshot；本 run 的 editing flow 阻塞。
- `not_requested`：未启用 snapshot 写入；可展示 SPL，不可进入 repair。

验收标准：

- 编译成功后前端可以展示 SPL Construct Cards。
- 编译失败时前端展示明确错误，不进入 repair 流程。
- 进入 SPL Editing repair 流程前必须有 `snapshot_status="available"` 和有效 `snapshot_path`。
- 如果编译成功但 `snapshot_status != "available"`，前端仍可展示 SPL 和基础诊断，但必须禁用 Issue repair、Explanation cache、Preview、Apply，并显示 snapshot 不可用原因。
- MVP 允许 `POST /runs` 同步阻塞返回完整结果，但文档必须把这视为取舍：真实编译包含多次 LLM 调用，可能耗时几十秒到数分钟。
- 如果 Contract Probe 发现同步请求在本地验证中频繁超时，应提前改为异步 job + polling，而不是继续扩大同步接口。

### FR-2 SPL Construct 层级展示

系统必须以嵌套卡片形式展示 SPL 的 containment hierarchy，而不是平铺 internal IR。

当前展示层级：

```text
WORKER
  → FLOW / EXCEPTION_FLOW
    → BLOCK
      → COMMAND
```

Block 必须显示真实 subtype：

- `SEQUENTIAL`
- `IF`
- `WHILE`
- `FOR`

其他可展示 Construct：

- `REQUIRED_OUTPUT`
- `CONSTRAINT`
- `PROFILE`

展示规则：

- `StepIR` 是 compiler internal IR，Web Demo 不把它显示为用户可见 `STEP`。
- `StepIR` 必须投影为 SPL `COMMAND`，并保留 `command_type`。
- 每张卡片必须返回 `parent_ref` 和 `construct_path`。
- 无法验证 Flow/Block 归属的 Command 必须标记为 `review_only + unplaced`，不得构造虚假的 Block。

验收标准：

- 前端只按 typed `parent_ref` 组装层级，不解析 `rendered_spl`。
- 卡片数据由薄 `CardProjector` 从结构化 IR / snapshot / trace 投射。
- 每个节点都能关联 provenance detail。
- Flow 的直接 child 只能是 Block；Command 只能位于 Block 下，或显式处于 unplaced 状态。

### FR-3 Construct Provenance 展示

系统必须支持展示每个 Construct 的溯源信息。

Provenance 信息来源：

- `FinalIRPackage.traces`
- `ArtifactSnapshot.traces`
- snapshot payload 中的 `provenance.traces`
- snapshot/source 中的 `spans`

每个 Provenance Detail 至少包含：

- `construct_ref`
- `target_ref`
- `relation`
- `explanation`
- `needs_confirmation`
- `metadata`
- `source_span_ids`
- `spans`

每个 Span 至少包含：

- `span_id`
- `text`
- `source_section_id`
- `source_packet_id`
- `section_context`
- `is_placeholder`
- `ambiguity`
- `guard_text_exact`
- `action_text_exact`
- `segmentation_kind`

验收标准：

- 有 source span 的 Construct 能看到原始 span 文本。
- 鼠标悬停或键盘聚焦 Construct 时，tooltip 只显示具体 source text 或用户确认文本。
- tooltip 不显示 `span_id`、`target_ref`、TraceRecord 标识或内部序号。
- 没有 source span 的 Construct 必须显示 `inferred` 或 `assumed`。
- `user_confirmed_repair` 来源必须展示用户确认文本；完整 repair metadata 仅进入 detail。
- tooltip cache 必须按 `run_id + revision_token` 隔离，迟到响应不得污染新 revision。
- 前端不得从 `feedback_report.md` 或 `final_spl.txt` 反向推断 provenance。
- Provenance API 由薄 `ProvenanceProjector` 投射 `snapshot.traces + snapshot.spans`，不得读取或解析诊断消息。

### FR-4 Problems 统一面板

系统必须在类似 IDE terminal/problems dock 的统一区域展示当前 run 的全部 issue，不按 SPL Construct 拆成独立面板。

Issue 分类建议：

- editable
- review_only
- deferred_validation
- developer_only

Problems 行至少展示：

- repairability/status
- `display_id`
- title
- impact/message
- category
- missing items

验收标准：

- 所有 issue 位于同一个可滚动 Problems 表格，不按 Construct 分组。
- 每一行都可通过鼠标点击或键盘 Enter/Space 打开 Issue Detail。
- Construct/location 只能作为列或 detail metadata，不能决定 issue 面板分区。
- Issue 列表来自 `SPLEditingPresentationService.list_issue_presentations()` 或等价 Presentation DTO。
- API 层不解析 diagnostic message。
- review-only issue 可以展示，但不进入修复流程。

### FR-5 AI Issue Explanation 展示

系统必须支持展示 snapshot 中缓存的 AI issue explanation。

Explanation 示例字段：

- `schema_version`
- `generation_source`
- `generation_warning`
- `headline`
- `impact`
- `issue_id`
- `language`
- `missing_information`
- `options`
- `problem`
- `questions`
- `recommendation_reason`
- `recommended_option`
- `source_interpretation`

Explanation 状态枚举：

- `ready`：缓存已生成，`value` 为完整 explanation。
- `pending`：生成任务已提交但尚未完成。
- `missing`：当前 snapshot 中没有该 issue 的 explanation cache。
- `error`：生成失败，`error_message` 应说明失败原因。

验收标准：

- explanation 优先从 snapshot presentation cache 读取。
- 如果 cache pending，前端显示生成中。
- 如果 cache missing，前端允许针对单个 issue 触发生成，或显示 fallback issue detail。
- explanation 不能成为 repair authority，只能作为解释文本。
- 当前底层已核查到 `read_cached_issue_explanation(snapshot_path, issue_id)` 支持单 issue ready 读取，但 `schedule_issue_explanations(snapshot_path, ...)` 是 snapshot-level 批量调度。9.8 的单 issue trigger 是 API 形态，MVP 实现可触发当前 snapshot 的批量 job，并只返回目标 issue 的状态。
- 若 API 需要区分 `pending`、`missing`、`error`，必须读取完整 explanation cache；不能只依赖 `read_cached_issue_explanation(...)`，因为该函数非 ready 时只返回 `None`。

### FR-6 Repair Option 展示

系统必须展示某个 issue 可用的修复策略。

Repair Option 卡片至少展示：

- label
- description
- option_id
- strategy_id
- interaction_contract_id
- availability
- unavailable_reason
- verification_lane

验收标准：

- 只有 `availability=available` 的 option 可点击修复。
- unavailable option 需要展示原因。
- repair option 必须来自后端 catalog / presentation service。

### FR-7 用户补充输入

系统必须允许用户在修复前输入补充建议。

MVP 支持：

- 一个自由文本输入框：`user_instruction`
- interaction schema 中声明的简单字段

字段类型最低支持：

- `short_text`
- `long_text`
- `single_choice`
- `multi_choice`

MVP 暂不要求实现：

- `reference_select`
- `structured_object`
- `new_fact_list`

如果某个 repair option 的 interaction schema 需要上述复杂字段，前端应将该 option 标记为 `unsupported_in_mvp`，并展示原因。不要为了 UI 简化而伪造字段值或绕过后端 interaction contract。

注意：worker delegation closure 的真实闭环可能需要 `reference_select` 和 `new_fact_list`。如果 Contract Probe 选定的首个闭环样例依赖这些字段，MVP 必须二选一：

- 补最小 UI 支持这些字段；
- 或将该 option 标记为 `unsupported_in_mvp`，另选一个简单字段即可闭环的 option。

不允许提交空的 `selected_ref_ids` / `new_fact_declarations` 来绕过后端 contract。

验收标准：

- 前端根据 interaction API 返回的 schema 渲染输入控件。
- 必填字段缺失时，后端返回 `input_required` 或 `input_invalid`。
- 用户输入必须作为 repair evidence 或 directive input 进入后端流程。

### FR-8 修复建议与 Preview

系统必须支持基于已验证的 repair directive 生成修复建议和 SPL Preview。

MVP-B 的 repair 闭环优先验证 worker delegation closure flow。`missing_handler`、`missing_output_producer` 等其他 repair option 只有在 contract probe 证明已接入同一 directive presentation facade 时，才进入本流程；否则仅展示 issue、explanation 和 repair option，不提供 preview/apply。

真实调用链必须是：

```text
SubmitRepairDirectiveDraftRequest
-> SPLEditingPresentationService.submit_repair_directive_draft(...)
-> RepairDirectiveValidationResult.normalized_directive_id
-> SPLEditingPresentationService.preview_repair_directive(directive_id)
-> WorkerDelegationPreviewHandle
```

Preview Response 至少包含：

- `directive_id`
- `preview_id`
- `session_id`
- `suggestion_id`
- suggestion title
- suggestion explanation
- expected effect
- risks
- rendered preview
- typed preview artifact
- preview SPL cards

验收标准：

- Preview 不改变正式 snapshot。
- Preview 必须带 stale detection 所需的 hash / revision 信息。
- Preview 卡片应尽量复用 SPL Construct Card 展示组件。
- Preview API 的响应字段必须来自 `PreviewMaterializationResult` 或 `WorkerDelegationPreviewHandle` 的真实字段投影。不得在 API 层发明底层对象不存在的 ID。
- API 层不得跳过 directive draft 直接调用需要 `session_id + suggestion_id` 的 core preview，除非 contract probe 证明某个非 directive repair flow 确实只能走 core service。

### FR-9 确认应用修复

系统必须支持用户确认应用某个 preview。

应用后返回：

- `status`
- `run_id`
- `snapshot_id`
- `overlay_version`
- `revision_token`
- verification result
- updated SPL cards
- updated issues

验收标准：

- 只有用户确认后才应用修复。
- 应用后必须执行 verification。可优先调用 `SPLEditingPresentationService.apply_repair_preview(...)`，因为它已组合 apply 和 verify；若直接调用 core service，则 API 层必须显式执行 `apply_preview_result(...)` 后再调用 `verify_session(...)`。
- 应用后的新 Construct 或 Step 应带 `user_confirmed_repair` provenance。
- 如果 preview stale，必须拒绝应用并要求刷新。

### FR-10 取消修复

系统必须支持用户取消 preview。

验收标准：

- 取消不会改变 snapshot。
- 前端清空 preview 状态。
- MVP 默认前端本地取消：清空 selected option、interaction、directiveId、preview，并回到 `run_ready`。
- 后端 preview 可依靠 TTL 或 apply 后 expire。
- 如果后续保留后端 cancel endpoint，应先在 Presentation Service 增加 `cancel_repair_preview(directive_id, preview_id)`；route 不得直接访问 core `_preview_store`。

## 9. API 需求

统一前缀：

```text
/api/demo/v1
```

### 9.0 Health

```http
GET /api/demo/v1/health
```

Response：

```json
{
  "status": "ok",
  "service": "spl-web-demo",
  "editing_service": "ready"
}
```

### 9.1 创建编译运行

```http
POST /api/demo/v1/runs
```

Request：

```json
{
  "raw_text": "用户输入的自然语言需求",
  "language": "zh-CN",
  "precompute_issue_explanations": false
}
```

MVP 说明：该接口可以同步阻塞直到编译完成。若 Contract Probe 发现常规输入会导致 HTTP 超时，应在进入 Repair Preview 阶段前改为异步 job 模型，例如 `POST /runs` 返回 `run_id + status=compiling`，再通过 `GET /runs/{run_id}` 或 `GET /runs/{run_id}/status` 轮询。

Response：

```json
{
  "run_id": "demo_20260710_001",
  "snapshot_id": "snap_xxx",
  "snapshot_status": "available",
  "snapshot_path": "examples/output/demo/spl_editing_snapshot.json",
  "overlay_version": 0,
  "revision_token": "demo_20260710_001:snap_xxx:0",
  "completeness": "partial",
  "editing_available": true,
  "spl_cards": [],
  "issue_summary": {
    "total": 8,
    "editable": 7,
    "review_only": 1,
    "deferred_validation": 0,
    "developer_only": 0
  }
}
```

Service contract expectation：

```text
PipelineOrchestrator.run(raw_text)
-> result.spl_editing_snapshot_status
-> if available:
     SPLEditingService.register_snapshot_file(result.spl_editing_snapshot_path)
     SPLEditingPresentationService.get_run_presentation(...)
-> project SPL cards from snapshot/final_ir/traces
```

### 9.1b 获取 Run 状态

```http
GET /api/demo/v1/runs/{run_id}
```

Response：

```json
{
  "run_id": "demo_20260710_001",
  "status": "run_ready",
  "snapshot_id": "snap_xxx",
  "snapshot_status": "available",
  "overlay_version": 0,
  "revision_token": "demo_20260710_001:snap_xxx:0",
  "editing_available": true,
  "issue_summary": {}
}
```

该接口即使在同步 compile MVP 中也应保留，用于 apply 后统一刷新 run metadata。

### 9.2 获取 SPL

```http
GET /api/demo/v1/runs/{run_id}/spl
```

Response：

```json
{
  "run_id": "demo_20260710_001",
  "snapshot_id": "snap_xxx",
  "overlay_version": 0,
  "revision_token": "demo_20260710_001:snap_xxx:0",
  "rendered_spl": "...",
  "spl_cards": []
}
```

正式 SPL endpoint 不默认返回完整 `spl_ir` 或 snapshot。若需要调试，使用隔离的 debug endpoint：

```http
GET /api/demo/v1/runs/{run_id}/debug/snapshot
```

### 9.3 获取 Construct 列表

```http
GET /api/demo/v1/runs/{run_id}/constructs
```

该接口固定返回 `provenance_summary`。完整 `traces + spans` 不在列表接口内联，必须通过 9.4 的 provenance detail 端点获取。

Response：

```json
{
  "run_id": "demo_20260710_001",
  "items": [
    {
      "construct_ref": "command_a1b2c3d4",
      "construct_type": "COMMAND",
      "title": "st_001: Collect input",
      "status": "available",
      "payload_summary": {
        "command_id": "st_001",
        "command_type": "REQUEST_INPUT",
        "flow_ref": "main",
        "block_ref": "block_01",
        "hierarchy_status": "placed"
      },
      "provenance_summary": {
        "kind": "source_backed",
        "source_span_count": 1
      },
      "source_span_ids": ["s12"],
      "parent_ref": "block_e5f6g7h8",
      "construct_path": [
        "worker_1234",
        "flow_5678",
        "block_e5f6g7h8",
        "command_a1b2c3d4"
      ]
    }
  ]
}
```

### 9.4 获取 Construct Provenance

```http
GET /api/demo/v1/runs/{run_id}/constructs/{construct_ref}/provenance
```

Response：

```json
{
  "construct_ref": "step:st_001",
  "target_ref": "step:st_001",
  "traces": [
    {
      "target_ref": "step:st_001",
      "source_span_ids": ["s12"],
      "source_section_id": "sec_behavior",
      "source_packet_id": "pkt_3",
      "relation": "direct",
      "explanation": "Step 'st_001' maps to source span(s).",
      "needs_confirmation": false,
      "metadata": {}
    }
  ],
  "spans": [
    {
      "span_id": "s12",
      "text": "Ask the user for missing timeframe.",
      "source_section_id": "sec_behavior",
      "source_packet_id": "pkt_3",
      "section_context": "Behavior",
      "is_placeholder": false,
      "ambiguity": {
        "is_ambiguous": false,
        "reasons": [],
        "needs_split": false
      }
    }
  ]
}
```

### 9.5 获取单个 Span

```http
GET /api/demo/v1/runs/{run_id}/spans/{span_id}
```

Response：

```json
{
  "span_id": "s12",
  "text": "Ask the user for missing timeframe.",
  "source_section_id": "sec_behavior",
  "source_packet_id": "pkt_3",
  "section_context": "Behavior",
  "is_placeholder": false
}
```

### 9.6 获取 Issue 列表

```http
GET /api/demo/v1/runs/{run_id}/issues
```

Response：

```json
{
  "summary": {
    "total": 8,
    "editable": 7,
    "review_only": 1,
    "deferred_validation": 0,
    "developer_only": 0
  },
  "sections": [
    {
      "section_id": "editable",
      "title": "Editable issues",
      "visible_by_default": true,
      "items": [
        {
          "display_id": 1,
          "issue_id": "irs_02b0da72bfd4",
          "category": "exception_handling",
          "title": "异常没有处理器",
          "impact": "异常流缺少处理动作。",
          "missing_items": ["handler action"],
          "repairability": "editable",
          "can_fix": true,
          "source_excerpt": "Missing timeframe"
        }
      ]
    }
  ]
}
```

### 9.7 获取 Issue Detail 和 Explanation

本节及后续 repair option 示例仅用于展示 API shape；是否可进入 directive preview/apply 以 Contract Probe 结果为准。MVP-B 首个闭环仍优先选择 worker delegation directive flow。

```http
GET /api/demo/v1/runs/{run_id}/issues/{issue_id}
```

Response：

```json
{
  "issue": {
    "issue_id": "irs_02b0da72bfd4",
    "title": "异常没有处理器",
    "what_was_detected": "编译器检测到异常流，但没有处理动作。",
    "missing_items": ["handler action"],
    "why_it_matters": "异常流不完整。",
    "available_repairs": [
      {
        "option_id": "exception_flow.add_handler_step",
        "strategy_id": "exception_flow.add_handler_step",
        "interaction_contract_id": "exception_flow.add_handler_step.v1",
        "label": "Add handler step",
        "description": "Add an explicit action inside the exception flow.",
        "availability": "available",
        "verification_lane": "B",
        "patch_types": ["AddExceptionHandlerStep"]
      }
    ]
  },
  "explanation": {
    "status": "ready",
    "value": {
      "schema_version": "issue_explanation.v1",
      "generation_source": "llm",
      "headline": "异常没有处理器：缺少“timeframe”",
      "problem": "...",
      "options": []
    }
  }
}
```

### 9.8 按需触发单个 Issue Explanation 生成

```http
POST /api/demo/v1/runs/{run_id}/issues/{issue_id}/explanation
```

Request：

```json
{
  "language": "zh-CN",
  "force": false
}
```

Response：

```json
{
  "status": "pending",
  "issue_id": "irs_02b0da72bfd4"
}
```

Explanation status 必须是以下值之一：

- `ready`
- `pending`
- `missing`
- `error`

MVP 行为约束：当前后端可通过 snapshot-level explanation scheduling 支撑单 issue trigger 的 API 形态；API 只返回目标 issue 的状态。若后续确实需要单 issue 调度，再新增 `schedule_single_issue_explanation(...)` 类型的 helper。

### 9.8b 可选批量预生成 Issue Explanation

```http
POST /api/demo/v1/runs/{run_id}/issues/explanations
```

该接口用于手动预热当前 run 的所有可见 issue explanations。MVP 默认不在 `POST /runs` 中自动调用它。

Request：

```json
{
  "language": "zh-CN",
  "force": false
}
```

Response：

```json
{
  "status": "pending",
  "cached_issue_ids": []
}
```

### 9.9 获取 Repair Interaction

```http
GET /api/demo/v1/runs/{run_id}/issues/{issue_id}/repair-options/{option_id}/interaction?revision_token=demo_20260710_001:snap_xxx:0
```

Response：

```json
{
  "issue_id": "irs_02b0da72bfd4",
  "strategy_id": "exception_flow.add_handler_step",
  "option_id": "exception_flow.add_handler_step",
  "contract_id": "exception_flow.add_handler_step.v1",
  "contract_version": "1",
  "revision_token": "demo_20260710_001:snap_xxx:0",
  "interaction_kind": "structured_with_notes",
  "availability": "available",
  "input_readiness": "not_evaluated",
  "fields": [],
  "schemas": []
}
```

如果后端 schema 包含 MVP 不支持的字段类型，API 可以附加展示态：

```json
{
  "availability": "unsupported_in_mvp",
  "unsupported_fields": ["reference_select", "new_fact_list"]
}
```

该展示态不能覆盖后端 option 的真实 `availability`；它只表示当前 Web Demo 前端没有实现对应控件。

### 9.10 提交 Repair Directive Draft

```http
POST /api/demo/v1/runs/{run_id}/repair-directives
```

Request：

```json
{
  "issue_id": "irs_02b0da72bfd4",
  "strategy_id": "exception_flow.add_handler_step",
  "option_id": "exception_flow.add_handler_step",
  "contract_id": "exception_flow.add_handler_step.v1",
  "contract_version": "1",
  "revision_token": "demo_20260710_001:snap_xxx:0",
  "field_values": {},
  "selected_ref_ids": {},
  "new_fact_declarations": [],
  "additional_instruction": "如果缺少 timeframe，就提示用户补充时间范围。"
}
```

该请求是 `SubmitRepairDirectiveDraftRequest` 的 API 投影。成功时，后端返回 `normalized_directive_id`，API 层将其命名为 `directive_id`。

Response：

以下为 API 投影示例；最终字段以 Contract Probe 的真实返回为准。

```json
{
  "input_readiness": "input_complete",
  "directive_id": "directive_xxx",
  "errors": []
}
```

MVP 约束：该接口优先服务只需要自由文本或简单字段的 repair option。若实际 `RepairInteractionView` 返回 `reference_select`、`structured_object` 或 `new_fact_list`，前端应拒绝提交 directive 并显示 `unsupported_in_mvp`，除非后续阶段显式补齐这些复杂控件和对应 DTO。

### 9.11 创建 Repair Preview

```http
POST /api/demo/v1/runs/{run_id}/repair-directives/{directive_id}/preview
```

Request：

```json
{
  "ttl_seconds": 600
}
```

Response：

以下为 API 投影示例；最终字段以 Contract Probe 的真实返回为准。

```json
{
  "directive_id": "directive_xxx",
  "preview_id": "prev_xxx",
  "session_id": "sess_xxx",
  "suggestion_id": "suggestion_xxx",
  "suggestion": {
    "title": "Add handler step",
    "explanation": "为异常流补充一个处理动作。",
    "expected_effect": ["异常流将具备明确处理步骤。"],
    "risks": []
  },
  "preview": {
    "rendered_preview": "...",
    "spl_cards": [],
    "typed_artifact": {}
  }
}
```

### 9.12 应用 Repair Preview

```http
POST /api/demo/v1/runs/{run_id}/repair-directives/{directive_id}/previews/{preview_id}/apply
```

Request：

```json
{
  "user_confirmation": true
}
```

Response：

以下为 API 投影示例；`verification` 必须来自真实 `VerificationResult`。

```json
{
  "status": "applied",
  "run_id": "demo_20260710_001",
  "snapshot_id": "snap_xxx",
  "overlay_version": 1,
  "revision_token": "demo_20260710_001:snap_xxx:1",
  "verification": {
    "accepted": true,
    "lane": "B",
    "failure_reasons": []
  },
  "spl_cards": [],
  "issues": []
}
```

### 9.13 取消 Repair Preview

MVP 推荐不做后端接口，前端本地取消即可：

```text
clear selectedOptionId
clear interaction
clear directiveId
clear preview
status -> run_ready
```

如果后续确实需要后端 cancel，再增加可选接口：

```http
DELETE /api/demo/v1/runs/{run_id}/repair-directives/{directive_id}/previews/{preview_id}
```

Response：

```json
{
  "status": "cancelled"
}
```

## 10. 前端状态模型

前端至少需要表达以下粗粒度状态。本文档不规定完整前端状态模型，`selected issue`、`selected construct`、`preview`、`repair input` 等作为局部 UI 状态处理即可。

```ts
type DemoStatus =
  | "idle"
  | "compiling"
  | "run_ready"
  | "preview_ready"
  | "applying"
  | "error";
```

`issue_selected`、`previewing_repair`、`applied` 可以作为派生 UI 状态，而不要求成为全局状态机的一等状态。

## 11. 错误码

建议错误码：

| HTTP | code | 含义 |
|---|---|---|
| 400 | invalid_request | 请求字段不合法 |
| 404 | run_not_found | run 不存在 |
| 404 | issue_not_found | issue 不存在 |
| 404 | construct_not_found | construct 不存在 |
| 404 | preview_not_found | preview 不存在 |
| 409 | stale_revision | revision token 已过期 |
| 409 | preview_stale | preview 已过期或不匹配 |
| 422 | option_unavailable | 修复策略不可用 |
| 422 | input_required | 缺少必填修复输入 |
| 422 | input_invalid | 修复输入无效 |
| 422 | compile_failed | 编译完成但输入或业务前置条件导致无法生成有效结果 |
| 422 | repair_failed | 修复流程完成但未通过业务校验或 verification |
| 500 | internal_error | 未预期的服务端异常 |
| 502 | llm_backend_error | LLM 或外部后端调用失败 |
| 504 | compile_timeout | 同步编译请求超时；应切换异步 job 或缩短输入 |

## 12. 验收标准

### 12.1 功能验收

- 用户输入需求后可以看到 SPL Construct Cards。
- `snapshot_status="available"` 时才能进入 SPL Editing repair。
- 每个有 source span 的 Construct 可以展开看到 span 原文。
- 无 source span 的 Construct 明确显示 `inferred` 或 `assumed`。
- Issue Console 可以展示 editable 和 review-only issue。
- Issue detail 来自 Presentation DTO。
- 点击 Issue 后可以展示 cached AI explanation。
- Repair option 来自 backend catalog / presentation。
- Interaction fields 来自 backend schema。
- 用户可以选择 repair option 并输入补充建议。
- 用户可以生成 SPL Preview。
- 用户可以确认应用修复。
- 应用修复后 `overlay_version` 增加。
- 应用修复后 `verification.accepted/lane/failure_reasons` 可见。
- 应用修复后 issue list 刷新，已解决 issue 消失或状态变化。
- 应用修复后刷新 SPL、Issue 和 Provenance。
- 应用后的修复内容显示 `user_confirmed_repair` provenance。

### 12.2 架构验收

- API 层没有 diagnostic message parsing。
- API 层没有 final_spl parsing。
- API 层没有 feedback_report parsing。
- API 层没有直接 IR mutation。
- API 层不自行判断 repairability。
- API 层不直接生成 patch。
- Repair 流程仍然经过现有 Service 层。
- Explanation 读取 snapshot presentation cache。
- Construct Provenance 从 `TraceRecord` 和 `SpanIR` 投射。
- Preview 需要确认后才 apply。
- Apply 后执行 verification。
- 前端不消费完整 internal IR。
- 前端不绕过 revision_token。

### 12.3 调试验收

Demo 应能帮助定位以下问题：

- 某个 Construct 为什么被渲染。
- 某个 Construct 来源于哪个 span。
- 某个 Issue 为什么可修或不可修。
- 某个 repair option 为什么不可用。
- Preview 和 apply 是否发生 revision drift。
- 用户确认修复后是否产生正确 provenance。

## 13. MVP 交付优先级

1. Contract Probe：验证已有 service contract、snapshot 产物、presentation DTO、directive preview/apply 返回结构和常规输入耗时。
2. Compile + SPL Cards：完成编译运行、snapshot 注册、run 状态、SPL 展示和 construct card 投影。
3. Provenance + Issue Console：完成 construct provenance、span detail、issue list 和 issue detail。
4. Explanation + Repair Interaction：接入 explanation cache、按需 explanation trigger、repair option interaction，并处理 `unsupported_in_mvp`。
5. Preview + Apply + Verification：完成一个 worker delegation directive repair 闭环，包括 directive draft、preview、apply、verification 和刷新后的 SPL/Issue/Provenance。

实现目录建议保持一句话即可：代码放在 `apps/spl-web-demo/` 下，后端可使用轻量 API 目录和薄 projector，前端使用一个简洁单页工作台。

## 14. 关键设计约束

- `feedback_report.md` 是人工可读报告，不是 API 数据源。
- `final_spl.txt` 是展示结果，不是 provenance authority。
- snapshot、traces、spans 才是 Construct Provenance 的结构化来源。
- IRS 只负责诊断 Construct slot，不负责修复。
- SPL Editing 负责修复策略、预览、应用和验证。
- Presentation DTO 应作为 API 返回结构的主要来源。
- Demo 应暴露后端职责边界问题，而不是通过前端补丁掩盖问题。
