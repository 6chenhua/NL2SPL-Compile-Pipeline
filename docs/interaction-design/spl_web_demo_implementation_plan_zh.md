# SPL Web Demo 实现计划

版本：v0.1
依据文档：

- `docs/interaction-design/spl_web_demo_functional_requirements_zh.md` v0.3
- `docs/interaction-design/spl_web_demo_detailed_design_zh.md` v0.2
- Contract Probe 输出：`apps/spl-web-demo/.probe-output/20260709T185204Z/`

## 1. 实现目标与非目标

### 1.1 目标

实现一个轻量级 SPL Web Demo，用于验证现有 NL2SPL service layer 是否适合被网络 API 和前端消费。

第一阶段实现目标：

- API MVP-A：基于 existing snapshot 或后续 live compile run 展示 run、SPL 初始文本、issues、issue detail、explanation cache。
- API MVP-B：基于已验证的 worker delegation `keep_in_main_flow` 完成 interaction、directive、preview、apply、verification。
- 前端最小工作台：可以输入/加载 run，查看 issue，选择首个可用 repair option，提交 preview/apply，并展示 verification。

### 1.2 非目标

本阶段不做：

- 完整产品化前端。
- 用户系统、项目系统、数据库持久化。
- 所有 repair option 的 preview/apply。
- `reference_select`、`structured_object`、`new_fact_list` 控件。
- apply 后 patched SPL/card projection 的伪实现。
- 从 `final_spl.txt`、`feedback_report.md` 或 diagnostic message 中反推业务状态。

## 2. 已验证 Service Contract 摘要

Contract Probe 已通过以下链路：

```text
SPLEditingService.register_snapshot_file(path)
-> SPLEditingPresentationService.get_run_presentation(editing_run_id)
-> list_issue_presentations(editing_run_id)
-> get_issue_detail_presentation(editing_run_id, issue_id)
-> get_repair_interaction(editing_run_id, issue_id, option_id, revision_token)
-> submit_repair_directive_draft(request)
-> preview_repair_directive(directive_id)
-> apply_repair_preview(directive_id, preview_id)
-> VerificationResult
```

已验证的运行事实：

| 字段 | 值 |
|---|---|
| `editing_run_id` | `demo` |
| `snapshot_id` | `snap_b61a1efdd39c` |
| `revision_token` | `demo:snap_b61a1efdd39c:0` |
| `issue_id` | `irs_b07e4440a217` |
| `option_id` | `keep_in_main_flow` |
| `contract_id` | `worker_delegation.keep_in_main_flow.v1` |
| `directive_id` | `directive_e83400868f090e4b1afc` |
| `verification.accepted` | `true` |
| `verification.lane` | `B` |
| `diagnostic_diff_summary` | `4 resolved, 10 unchanged` |

已验证 interaction 字段：

| field_id | input_type | required |
|---|---|---:|
| `task_selection` | `single_choice` | true |
| `additional_instruction` | `long_text` | false |

实现计划必须以这些事实为初始 API shape 的基线。

## 3. 当前必须接受的缺口

Probe 证实 apply 后：

```text
overlay_version = 1
verification.accepted = true
patched_snapshot.final_spl_available = false
```

因此第一版实现必须接受：

- apply 后可以刷新 run metadata、issues 和 verification。
- apply 后不能声称可以展示 patched SPL text。
- apply 后不能声称可以展示 patched SPL cards，除非实现前又补充并验证了稳定 read-model。
- `GET /runs/{run_id}/spl` 在 `overlay_version > 0` 且无 patched projection 来源时必须返回 `projection_unavailable` 或 `refresh_unavailable`。

这不是前端缺口。前端应展示：

```text
Repair applied and verification accepted.
Patched SPL projection is unavailable in this MVP build.
```

## 4. 后端 API 实现计划

### A1. DemoRunStore

实现最小内存 store：

```text
DemoRunRecord
  api_run_id
  editing_run_id
  snapshot_path
  snapshot_id
  overlay_version
  revision_token
  snapshot_status
  editing_available
  pipeline_result
  last_verification
  projection_status
```

硬规则：

- HTTP `{run_id}` 只作为 `api_run_id`。
- 所有 service 调用必须先查 store，再使用 `record.editing_run_id`。
- `record.editing_run_id is None` 时 repair 相关 API 禁用。

### A2. Snapshot Bootstrapping

先实现 existing snapshot bootstrap，后接 live compile。

建议临时 API：

```http
POST /api/demo/v1/runs/from-snapshot
```

Request：

```json
{
  "snapshot_path": "examples/output/demo/spl_editing_snapshot.json"
}
```

该接口只用于本地 demo 和 Contract Probe 对齐。后续 `POST /runs` live compile 接入后可以保留为 debug/local endpoint。

约束：

- 该 endpoint 只用于本地 demo、Contract Probe 对齐和开发调试。
- 生产化路径仍是 `POST /api/demo/v1/runs`。
- 如果后续需要更严格隔离，可以移动为 `POST /api/demo/v1/debug/runs/from-snapshot`。

### A3. Run APIs

实现：

```http
GET /api/demo/v1/runs/{run_id}
GET /api/demo/v1/runs/{run_id}/spl
```

`GET /spl` 规则：

```text
overlay_version == 0:
  返回 initial SPL text + initial cards

overlay_version > 0:
  如果 patched projection source 可用:
    返回 patched SPL/cards
  否则:
    返回 projection_status = projection_unavailable
    不返回 stale PipelineResult.spl_text
```

当 `projection_status="projection_unavailable"` 时，这是业务展示状态，不是 HTTP error。API 固定返回 HTTP 200，并使用以下响应形态：

```json
{
  "overlay_version": 1,
  "projection_status": "projection_unavailable",
  "rendered_spl": null,
  "spl_cards": [],
  "message": "Repair applied and verification accepted, but patched SPL projection is unavailable in this MVP build."
}
```

该状态下禁止返回 stale `rendered_spl`，也禁止伪造 cards。

### A4. Issue APIs

实现：

```http
GET /api/demo/v1/runs/{run_id}/issues
GET /api/demo/v1/runs/{run_id}/issues/{issue_id}
POST /api/demo/v1/runs/{run_id}/issues/{issue_id}/explanation
```

行为：

- issue list/detail 直接来自 `SPLEditingPresentationService`。
- explanation reader 使用真实签名：
  - `read_explanation_cache(snapshot_path)`
  - `read_cached_issue_explanation(snapshot_path, issue_id)`
- explanation trigger 可用 snapshot-level scheduling，API 只返回目标 issue status。

### B1. Repair Interaction API

实现：

```http
GET /api/demo/v1/runs/{run_id}/issues/{issue_id}/repair-options/{option_id}/interaction
```

首个支持闭环固定：

```text
option_id = keep_in_main_flow
contract_id = worker_delegation.keep_in_main_flow.v1
```

MVP 支持字段：

- `single_choice`
- `long_text`
- `short_text`
- `multi_choice`

遇到复杂字段时返回：

```json
{
  "availability": "available",
  "demo_availability": "unsupported_in_mvp",
  "unsupported_fields": ["reference_select"]
}
```

### B2. Directive API

实现：

```http
POST /api/demo/v1/runs/{run_id}/repair-directives
```

请求投影到：

```text
SubmitRepairDirectiveDraftRequest
```

首个闭环的最小 payload：

```json
{
  "issue_id": "irs_b07e4440a217",
  "strategy_id": "worker_delegation.complete_closure.v2",
  "option_id": "keep_in_main_flow",
  "contract_id": "worker_delegation.keep_in_main_flow.v1",
  "contract_version": "1",
  "revision_token": "demo:snap_b61a1efdd39c:0",
  "field_values": {
    "task_selection": "source gathering"
  },
  "selected_ref_ids": {},
  "new_fact_declarations": [],
  "additional_instruction": null
}
```

### B3. Preview API

实现：

```http
POST /api/demo/v1/runs/{run_id}/repair-directives/{directive_id}/preview
```

调用：

```text
SPLEditingPresentationService.preview_repair_directive(directive_id)
```

返回：

- `directive_id`
- `session_id`
- `suggestion_id`
- `preview_id`
- `rendered_preview`
- typed preview summary

### B4. Apply API

实现：

```http
POST /api/demo/v1/runs/{run_id}/repair-directives/{directive_id}/previews/{preview_id}/apply
```

调用：

```text
SPLEditingPresentationService.apply_repair_preview(directive_id, preview_id)
```

返回：

- `status`
- `overlay_version`
- `verification`
- updated issue summary
- `projection_status`

第一版 apply response 中必须允许：

```json
{
  "status": "applied",
  "verification": {
    "accepted": true,
    "lane": "B"
  },
  "projection_status": "projection_unavailable"
}
```

## 5. Projector 实现计划

### 5.1 IssueProjector

优先实现，因为 DTO 已由 presentation service 提供。

输入：

- `RunPresentationView`
- `IssueListPresentationView`
- `IssueDetailPresentationView`

输出：

- run summary
- issue sections
- issue detail
- repair options

### 5.2 ExplanationProjector

输入：

- full cache envelope
- selected issue explanation dict or `None`

输出：

```text
ready | pending | missing | error
```

### 5.3 RepairProjector

输入：

- `RepairInteractionView`
- `RepairDirectiveValidationResult`
- `WorkerDelegationPreviewHandle`
- `VerificationResult`

输出：

- interaction response
- directive response
- preview response
- apply response

### 5.4 CardProjector

第一版只要求 initial snapshot / initial pipeline result cards。

要求：

- 不解析 rendered SPL。
- 不读取 `final_spl.txt`。
- overlay version > 0 时若无 patched read-model，返回 projection unavailable。

## 6. Frontend 实现计划

### F1. API-first 验证页面

先做一个最小工作台，不追求视觉完整：

- Run loader / snapshot bootstrap。
- Issue list。
- Issue detail。
- Repair interaction form。
- Preview panel。
- Apply result / verification panel。

### F2. Repair Form

首个闭环只需要：

- `single_choice` 控件：`task_selection`
- `long_text` 控件：`additional_instruction`

不支持复杂字段时禁用 submit。

### F3. Apply 后展示

apply 后前端展示三部分：

- verification accepted/lane/failure reasons。
- updated issue summary。
- projection status。

如果 `projection_status="projection_unavailable"`：

```text
Repair 已应用，verification 已通过；当前 MVP 暂不能展示 patched SPL/cards。
```

## 7. Apply 后 Refresh 策略

这是独立实现主题，不得埋在普通 API 逻辑中。

### 7.1 MVP 默认策略

```text
apply success
-> refresh run metadata
-> refresh issue list
-> return verification
-> set projection_status = projection_unavailable if patched SPL/cards unavailable
```

### 7.2 禁止策略

- 禁止返回 stale `PipelineResult.spl_text`。
- 禁止从 `rendered_preview` 伪造 applied SPL。
- 禁止解析 preview text 生成 cards。

### 7.3 后续增强路径

后续可选择其一：

- 在 SPL Editing presentation 增加 patched snapshot 只读 getter。
- 在 overlay replay 后生成 patched final SPL read-model。
- 在 CardProjector 增加基于 patched snapshot stage artifacts 的 read-only projection。

这些增强必须先通过新的 Contract Probe case 验证。

### 7.4 Probe 与 API 的 private access 边界

Contract Probe 可以读取 private/internal fields 以发现事实，例如 `_get_snapshot` 或 `_snapshots.get(...)`。Demo API 不能依赖 private service fields 作为正式 read path。

如果 public / presentation read-model 不足，API 必须返回 `projection_unavailable`，不得访问 `_snapshots`、`_get_snapshot` 等 private 成员来伪造稳定接口。

## 8. 测试计划

### 8.1 API 测试

必测：

- `from-snapshot` 能注册 existing snapshot。
- HTTP `{run_id}` 不直接传给 service，必须经 `editing_run_id`。
- issue list/detail 来自 presentation service。
- explanation cache reader 使用真实签名。
- repair interaction 返回 `task_selection` 与 `additional_instruction`。
- directive submit 返回 `input_complete` 和 `directive_id`。
- preview 返回 `preview_id`、`session_id`、`suggestion_id`。
- apply 返回 verification accepted。
- overlay version > 0 且 patched projection unavailable 时，`GET /spl` 不返回旧 SPL。

### 8.2 Probe 回归

每次修改 repair API 或 projector 后运行：

```text
.venv\Scripts\python.exe apps\spl-web-demo\backend\contract_probe\probe.py
```

### 8.3 前端验证

用浏览器或轻量测试确认：

- 可以加载 run。
- 可以打开 issue detail。
- 可以填写 `task_selection`。
- 可以 preview。
- 可以 apply。
- apply 后显示 verification 与 projection unavailable。

## 9. 分阶段交付顺序

1. A1/A2：RunStore + from-snapshot bootstrap。
2. A3/A4：run/spl/issues/explanation APIs。
3. B1/B2：repair interaction + directive。
4. B3/B4：preview + apply + verification。
5. F1：API-first 前端工作台。
6. F2/F3：repair form + apply 后状态展示。
7. 补充 live compile smoke probe，不阻塞 SPL Editing contract 开发。

每个阶段结束都必须能独立运行当前 API 或 probe，不允许只堆代码不验证。
