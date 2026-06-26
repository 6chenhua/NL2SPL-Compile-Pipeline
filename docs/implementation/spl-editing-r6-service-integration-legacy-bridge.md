# R6 Service Integration and Legacy Bridge — 实施文档

日期：2026-06-26  
状态：Implemented  
前置：R0-R5

---

## 1. 目标

将 `missing_output_producer / InsertProducerStep` 的生产路径切换到 R1-R5 materialization 架构。

---

## 2. 核心设计决策

### 2.1 Insert 零 Fallback

`InsertProducerStep` 决不因 refset/catalog/policy 缺失回退 dict payload。缺失条件 → `generation_blocked` 或 parse failure。

### 2.2 Confirmation Context 状态机

```
seal()          → SEALED
begin_apply()   → SEALED → APPLYING      (RLock 原子)
abort_apply()   → APPLYING → SEALED      (transient 失败可重试)
commit_consumed() → APPLYING → CONSUMED  (tombstone)
expire()        → SEALED|APPLYING → EXPIRED    (tombstone)
reject()        → SEALED|APPLYING → REJECTED   (tombstone)
```

状态存储于独立 `_states: dict`，DTO 无 state 字段。

### 2.3 Apply 持久化带 Rollback

顺序写入 stores，失败时逆序回滚 (`remove`/`remove_event`)。仅在全部持久化成功后 `commit_consumed()`。

### 2.4 失败状态分类

| 失败类型 | 状态转移 |
|---------|---------|
| materialization 内部错误 | abort_apply → SEALED |
| persistence 写入失败（已回滚） | abort_apply → SEALED |
| stale revision | expire → EXPIRED |
| cross-session | reject → REJECTED |
| payload/intent/refs contract violation | reject → REJECTED |

### 2.5 Suggestion 先校验再保存

Ref resolution + context seal 在 `_suggestions.put()` 之前。失败不写 store。

### 2.6 Catalog 唯一匹配

`_resolve_catalog_entry(issue, affordance_id, patch_type)` — 零个或多个匹配均 fail-fast。Helper 方法验证所有 entries 的 handler_id/target_resolver_id/context_id 一致。

### 2.7 Apply Dispatch

Insert 路径先于 legacy precheck（stale/cross-session）执行，使这些检查进入 context 状态机（expire/reject）而非裸异常。

---

## 3. 新增文件

| 文件 | 说明 |
|------|------|
| `core/confirmation_context.py` | `RepairConfirmationContext`, `ConfirmationContextState`, `ConfirmationContextTombstone`, `ConfirmationContextStore` |
| `llm_context/selectable_ref_adapter.py` | R1 SelectableRef → LLM context SelectableReference（仅暴露 target_output + selectable_input） |
| `tests/.../test_r6_confirmation_context.py` | 31 tests |

## 4. 修改文件

| 文件 | 关键变更 |
|------|---------|
| `core/model.py` | `PatchApplyResult.audit_metadata` |
| `core/service.py` | DI `materialization_service`, `ConfirmationContextStore`, `generate_suggestions` refset+seal, `apply_suggestion` dispatch, `_apply_via_materialization` + rollback, `_apply_via_legacy_applier` + audit marker, `_resolve_catalog_entry` |
| `storage/artifact_snapshot_store.py` | `remove()` |
| `storage/overlay_store.py` | `remove_event()` |
| `handlers/base.py` | 签名新增 `selectable_refset`, `catalog_entry` |
| `handlers/missing_output_producer/handler.py` | Insert→intent（零 fallback）, Bind→legacy |
| `handlers/missing_output_producer/prompt.py` | 分离 Insert/Bind prompt |
| `handlers/missing_handler/handler.py` | 签名更新 |
| `handlers/type_or_contract_ambiguity/handler.py` | 签名更新 |
| `handlers/parser.py` | `SuggestionEnvelope` + `parse_suggestion_envelope()` |
| `patches/insert_producer_step/validator.py` | 拒绝 dict，接受 ConstructRepairIntent |
| `patches/insert_producer_step/applier.py` | `apply()` 永远抛错 |
| `patches/insert_producer_step/verifier.py` | 兼容 dict 和 ConstructRepairIntent |
| `llm_context/common_facts.py` | `build_repair_action_facts` 接受 `selectable_refset` |
| `llm_context/builder.py` | 传递 `selectable_refset` |
| `presentation/model/confirmation.py` | 扩展 `ApplyConfirmationView` + `ConfirmationRefItem` |
| `presentation/builders/confirmation_builder.py` | 接受 `confirmation_context` |
| `presentation/service.py` | `present_apply_confirmation` 接受 `confirmation_context` |
| `selectable_refs/builder.py` | mock snapshot 优雅降级 |
| 测试文件 | R0 gap, B6 handler, B6 patch, U3 stamping, B8 service, stub LLM |

---

## 5. 验收状态

- [x] Insert 零 fallback — 无 refset 时不产生 suggestion
- [x] Suggestion 先校验后保存 — ref resolution 失败不写 store
- [x] Context 状态机 RLock 原子转移
- [x] Rollback 能力 — `ArtifactSnapshotStore.remove()` + `OverlayStore.remove_event()`
- [x] 失败状态分类一致 — transient→SEALED, contract→EXPIRED/REJECTED
- [x] Catalog 唯一匹配 — `_resolve_catalog_entry()` + helper 一致性验证
- [x] Insert dispatch 先于 legacy precheck — context 状态机覆盖 stale/cross-session
- [x] `InsertProducerStepApplier.apply()` 永远抛错
- [x] 742 unit tests pass
