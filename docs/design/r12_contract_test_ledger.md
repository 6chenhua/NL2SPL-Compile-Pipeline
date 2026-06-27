# R12 Contract Test Ledger

This ledger lists target items that must be promoted to executable contract tests in subsequent implementation phases. These items lock in the differences between the current R0-R11 safety baseline and the target R12+ construct-level repair strategy and repair-mode stage slice architecture.

---

## Phase R12.1: Strategy and Directive Model Foundation

### 1. `RepairDirective` Evidence Authority Guard
*   **Gap Description**: Currently, the system has no concept of a `RepairDirective`. User input is translated directly into patch payloads.
*   **Target Test Contract**:
    *   Verify that `RepairDirective` does not possess any evidence authority attributes (e.g. `evidence_kind` or `user_confirmed_repair` status fields).
    *   Verify that `RepairDirective` instances cannot be used as an authorization bypass for rendering steps or binding variables.
    *   Verify that it remains purely provisional prior to user confirmation.

### 2. Reference Hints Separation
*   **Gap Description**: Current patch types conflate user-provided variable hints with materialization authority.
*   **Target Test Contract**:
    *   Verify that `RepairDirective.selected_ref_hints` only serves as passive context hints.
    *   Verify that the materialization planner strictly uses `ConstructRepairIntent.selected_ref_ids` (after verification against `SelectableRefSet`) as the actual reference authority.
    *   Ensure any attempt to materialize using unchecked `selected_ref_hints` fails.

### 3. Construct Closure Actions
*   **Gap Description**: No explicit closure plan exist; the materializers hardcode the actions needed to repair the slot.
*   **Target Test Contract**:
    *   Verify that `ConstructClosureNode.action` supports and validates exactly three actions: `ensure`, `bind_existing`, and `materialize`.
    *   Ensure any invalid action string is rejected at DTO construction time.

---

## Phase R12.2 / R13.0: Strategy Registry and Catalog Integration

### 4. Strategy ID as the Semantic Source
*   **Gap Description**: Patch type is currently treated as the unique strategy indicator in the catalog and UI presentation.
*   **Target Test Contract**:
    *   Verify that when a `repair_strategy_id` is present on a catalog entry, it is used as the primary semantic key in the presentation layer and prompts.
    *   Verify that `supported_patch_types` are demoted to serving solely as execution adapters.
    *   Verify that no R12+ presentation text displays the patch type as the semantic title.

---

## Phase R12.4: Preview / Apply Lifecycle Infrastructure

### 5. Preview Hash-Based Stale Detection
*   **Gap Description**: No preview lifecycle exists; apply is performed directly on the session's active snapshot.
*   **Target Test Contract**:
    *   Verify that `PreviewMaterializationResult` contains all required hashes for stale detection:
        *   `base_snapshot_id`
        *   `intent_hash`
        *   `directive_hash`
        *   `closure_plan_hash`
        *   `selected_refset_id`
        *   `slice_typed_plan_hashes` (when generation is used)
        *   `preview_construct_hashes`
        *   `llm_generation_config_hash`
    *   Verify that hashes are computed deterministically.

### 6. Apply Drift Prevention
*   **Gap Description**: There is no stale check between a previewed state and the applied state.
*   **Target Test Contract**:
    *   Verify that `SPLEditingService.apply_suggestion` (or its R12+ successor) checks all stale detection hashes against the preview result.
    *   Verify that if the active snapshot, directive, or selected references change after preview, the apply operation is rejected.
    *   Verify that `RepairEvidencePacket` is created only after user confirmation of a validated preview.

---

## Phase R13.0: missing_handler Strategy Wiring

### 7. missing_handler Strategy & Stage Slice Chain
*   **Gap Description**: `missing_handler` uses a single monolithic `Stage7ExceptionHandlerStepMaterializer`.
*   **Target Test Contract**:
    *   Verify that the `missing_handler` flow routes through the `CompleteExceptionHandlerAction` strategy.
    *   Verify that the construct closure specifies both a handler block and a handler command.
    *   Verify that the materialization plan invokes both `Stage5ExceptionHandlerBlockRepairSlice` and `Stage7ExceptionHandlerCommandRepairSlice` sequentially.
    *   Verify that if the exception flow already has a handler block, the Stage5 slice binds/ensures it instead of creating a duplicate.
