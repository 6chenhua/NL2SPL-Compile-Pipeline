# ARC0: Role Contract Baseline Audit

## 1. Document Purpose

This audit lists every role-contract-like source currently in the codebase,
its owner module, and the gaps that the ARC migration must close.

Generated: 2026-06-11
Phase: ARC0 (Baseline and Gap Audit)
Status: Complete

## 2. Inventory of Role-Contract-Like Sources

### 2.1 `_ANNOTATION_SEMANTICS` — deterministic packet-type mapping

- **File**: `src/nl2spl/pipeline/stages/stage2_field_router.py`
- **Owner**: `FieldRouter._build_packet_annotation()`
- **Key space**: `packet_type` (adapter concept: `task_family`, `runtime_input`, `required_output`, `process_step`, `policy`, `failure_mode`, `delegation_rule`)
- **Fields**: `field`, `semantic_role`, `route_family`, `executable`, sometimes `construct_target`, `slot_target`
- **Role**: Maps adapter packet types → compiler-facing annotation fields for deterministic (hard-fact) annotations.
- **Gap**: Separate from `ROUTE_PRIOR_ROLE_CONTRACTS` and `_ROLE_CONTRACT`. Contains structural aliases as keys (`task_family`, `runtime_input`, `required_output`) that are not canonical semantic roles.

### 2.2 `ROUTE_PRIOR_ROLE_CONTRACTS` — route-prior normalization contract

- **File**: `src/nl2spl/pipeline/stages/stage2_field_router.py`
- **Owner**: `FieldRouter._normalize_annotation_contract()`, `_build_structural_route_context()`
- **Key space**: `semantic_role` (canonical: `failure_mode`, `input_contract`, `output_contract`, `process_step`, `profile_domain`, etc.)
- **Fields**: `field`, `semantic_role`, `route_family`, `executable`, `construct_target`, `slot_target`
- **Role**: Normalizes LLM-provided annotations to compiler-consistent fields. Used by the LLM refinement merge path.
- **Gap**: Not the same table as validator's `_ROLE_CONTRACT`. Different keys, different field coverage per key.

### 2.3 `_ROLE_CONTRACT` — validator role-specific contract

- **File**: `src/nl2spl/pipeline/stages/stage2_field_router_validator.py`
- **Owner**: `RouteRefinementValidator._validate_one()`
- **Key space**: `semantic_role` (subset: 13 roles)
- **Fields**: `construct_target`, `slot_target`, `executable` (sparse — many roles only have `executable`)
- **Role**: Validates individual LLM annotations against role-specific expectations.
- **Gap**: Missing `construct_target` and `slot_target` for many roles that need them (especially for "expected None" enforcement). Does not cover `process_step` at all. Lacks `field` and `route_family` expectations.

### 2.4 `_OPTIONAL_CONSTRUCT_SLOT_ROLES` — normalization exception set

- **File**: `src/nl2spl/pipeline/stages/stage2_field_router.py`
- **Owner**: `FieldRouter._normalize_annotation_contract()`
- **Key space**: `semantic_role` (`process_step`, `profile_domain`)
- **Role**: Forces `construct_target=None`, `slot_target=None` for roles that should never have them.
- **Gap**: A side-table rather than part of the canonical role contract. Only two roles covered. The validator does not know about this set.

### 2.5 Prompt schema constants (6 frozensets)

- **File**: `src/nl2spl/pipeline/stages/stage2_field_router_prompt.py`
- **Owner**: Prompt builder (`build_adapter_guided_user_prompt`), parser, validator
- **Contents**:
  - `ALLOWED_FIELDS` (7 values)
  - `ALLOWED_SEMANTIC_ROLES` (13 values)
  - `ALLOWED_CONSTRUCT_TARGETS` (5 values)
  - `ALLOWED_SLOT_TARGETS` (6 values)
  - `NON_EXECUTABLE_ROLES` (11 values)
  - `EXECUTABLE_ROLES` (2 values)
- **Role**: Closed-set validation for LLM output. Also embedded in the LLM prompt via `allowed_schema`.
- **Gap**: All six are hand-maintained `frozenset` literals. No derivation from a canonical role contract registry. Adding a new role requires updating both the prompt constants AND `ROUTE_PRIOR_ROLE_CONTRACTS` AND `_ROLE_CONTRACT`.

### 2.6 `_CONTRACT_ROLES` — DemandView contract role set

- **File**: `src/nl2spl/compiler/resource_contract_demand_view/builder.py`
- **Owner**: `DemandViewBuilder._select_contract_annotations()`
- **Contents**: `frozenset({"input_contract", "output_contract"})`
- **Role**: Defines which semantic roles authorize resource contract demand projection.
- **Gap**: None directly — this is the correct definition. However, it is a module-local constant, not derived from the same registry as other role-contract sources.

### 2.7 `_SECTION_CONTEXT_TO_STRUCTURAL_ROLE` — section-title to role mapping

- **File**: `src/nl2spl/pipeline/stages/stage2_field_router.py`
- **Owner**: `FieldRouter._section_structural_role()`
- **Key space**: Section canonical titles (`task family`, `inputs for each run`, etc.)
- **Maps to**: Structural aliases (`task_family`, `input_contract`, `output_contract`, `process_step`, `policy`, `failure_mode`, `delegation_intent`)
- **Role**: Provides structural role hints from section titles.
- **Gap**: Maps to structural aliases (e.g., `task_family`) that are NOT canonical semantic roles. The aliases are then resolved through `ROUTE_PRIOR_ROLE_CONTRACTS`.

### 2.8 `_enrich_from_hints()` — CompileHint-driven annotation mutation

- **File**: `src/nl2spl/pipeline/stages/stage2_field_router.py` (lines 1372–1458)
- **Owner**: `FieldRouter._enrich_from_hints()`, called by `_build_packet_annotation()`
- **Role**: Enriches a newly constructed `RouteAnnotation` with metadata from adapter `CompileHint` objects. Runs immediately after `_ANNOTATION_SEMANTICS` lookup in `_build_packet_annotation()`.
- **Mutation points** (all write role-contract fields in-place, bypassing any role contract):
  - **Line 1411**: `annotation.slot_target = hint_slot` — writes `slot_target` from `hint.metadata["slot_target"]` when current value is `None`
  - **Line 1422**: `annotation.route_family = hint_rf` — writes `route_family` from `hint.metadata["route_family"]` when current value is `None`
  - **Line 1433**: `annotation.semantic_role = hint_role` — writes `semantic_role` from `hint.metadata["semantic_role"]` when current value is `None`
  - **Line 1453**: `annotation.construct_target = hint_target` — writes `construct_target` from `hint.target` or `hint.metadata["target"]` when current value is `None`
  - **Line 1441-1447**: `executable` conflict is recorded as diagnostic only (not mutated), but the diagnostic is issued *after* the fact rather than preventing the inconsistency
- **Call path**: `_build_packet_annotation()` → `_enrich_from_hints()` runs AFTER `_ANNOTATION_SEMANTICS` lookup, so hints can silently overwrite role-contract-derived fields
- **Gap**: This is a **role-contract bypass path**. After a `RouteAnnotation` is constructed from `_ANNOTATION_SEMANTICS`, `_enrich_from_hints()` can mutate `slot_target`, `route_family`, `semantic_role`, and `construct_target` without going through any role contract normalization or validation. The implementation plan's mandatory revision #3 requires that hints must not write or override role-contract fields; ARC3 must converge this path.

## 3. Gap Summary

| Gap ID | Description | Owner(s) | Fix Phase |
|--------|-------------|----------|-----------|
| GAP-01 | Three independent role-contract tables (`_ANNOTATION_SEMANTICS`, `ROUTE_PRIOR_ROLE_CONTRACTS`, `_ROLE_CONTRACT`) | FieldRouter, Validator | ARC1, ARC3, ARC4 |
| GAP-02 | Prompt schema constants are hand-maintained frozensets, not registry-derived | stage2_field_router_prompt.py | ARC2 |
| GAP-03 | Validator does not enforce expected `None` for `construct_target`/`slot_target` | Validator `_ROLE_CONTRACT` | ARC4 |
| GAP-04 | `_ROLE_CONTRACT` uses `None`-key-absence as "skip check" semantics | Validator | ARC4 |
| GAP-05 | Deterministic path uses `_ANNOTATION_SEMANTICS` (packet_type keys), not a shared role contract | `_build_packet_annotation()` | ARC3 |
| GAP-06 | Structural aliases (`task_family`, `policy`, `runtime_input`, `required_output`) exist in `_ANNOTATION_SEMANTICS` and `_SECTION_CONTEXT_TO_STRUCTURAL_ROLE` but are not formally resolved through an alias registry | FieldRouter | ARC1 |
| GAP-07 | `_OPTIONAL_CONSTRUCT_SLOT_ROLES` is a separate set, not integrated into the role contract | `_normalize_annotation_contract()` | ARC1, ARC3 |
| GAP-08 | `_CONTRACT_ROLES` is a module-local constant, not registry-derived | DemandView builder | ARC5 |
| GAP-09 | `_enrich_from_hints()` can mutate `slot_target`, `route_family`, `semantic_role`, `construct_target` on a `RouteAnnotation` after construction, bypassing any role contract normalization or validation | `_enrich_from_hints()` → `_build_packet_annotation()` | ARC3 |

| Gap ID | Description | Owner(s) | Fix Phase |
|--------|-------------|----------|-----------|
| GAP-01 | Three independent role-contract tables (`_ANNOTATION_SEMANTICS`, `ROUTE_PRIOR_ROLE_CONTRACTS`, `_ROLE_CONTRACT`) | FieldRouter, Validator | ARC1, ARC3, ARC4 |
| GAP-02 | Prompt schema constants are hand-maintained frozensets, not registry-derived | stage2_field_router_prompt.py | ARC2 |
| GAP-03 | Validator does not enforce expected `None` for `construct_target`/`slot_target` | Validator `_ROLE_CONTRACT` | ARC4 |
| GAP-04 | `_ROLE_CONTRACT` uses `None`-key-absence as "skip check" semantics | Validator | ARC4 |
| GAP-05 | Deterministic path uses `_ANNOTATION_SEMANTICS` (packet_type keys), not a shared role contract | `_build_packet_annotation()` | ARC3 |
| GAP-06 | Structural aliases (`task_family`, `policy`, `runtime_input`, `required_output`) exist in `_ANNOTATION_SEMANTICS` and `_SECTION_CONTEXT_TO_STRUCTURAL_ROLE` but are not formally resolved through an alias registry | FieldRouter | ARC1 |
| GAP-07 | `_OPTIONAL_CONSTRUCT_SLOT_ROLES` is a separate set, not integrated into the role contract | `_normalize_annotation_contract()` | ARC1, ARC3 |
| GAP-08 | `_CONTRACT_ROLES` is a module-local constant, not registry-derived | DemandView builder | ARC5 |

## 4. Baseline Test Coverage

The ARC0 test file (`tests/unit/compiler/annotation_role_contract/test_arc0_baseline.py`)
contains 42 tests in 8 classes:

| # | Test Class | Tests | XFAIL | Description |
|---|-----------|-------|-------|-------------|
| 1 | `TestProfileDomainResourceContractGap` | 5 | 2 | profile_domain + RESOURCE_CONTRACT gap |
| 2 | `TestRoleContractSourcesNotUnified` | 4 | 0 | Three independent tables |
| 3 | `TestSchemaConstantsAreHardcoded` | 7 | 0 | Prompt constants are literals |
| 4 | `TestValidatorMissingExpectedNone` | 3 | 0 | Validator skips expected-None |
| 5 | `TestDeterministicPathNotUsingSharedContract` | 5 | 0 | `_ANNOTATION_SEMANTICS` is separate |
| 6 | `TestDemandViewSemanticRoleAuthorization` | 4 | 0 | DemandView uses semantic_role (CORRECT) |
| 7 | `TestRequirednessIndependentFromRoleContract` | 5 | 0 | Requiredness is separate (CORRECT) |
| 8 | `TestEnrichFromHintsRoleContractBypass` | 9 | 0 | `_enrich_from_hints()` mutates role-contract fields without contract |

**XFAIL tests** (2) — both will be resolved in ARC4 (Full-Field Validator):
- `test_validator_enforces_none_construct_target_for_profile_domain`
- `test_validator_enforces_none_slot_target_for_profile_domain`

## 5. Verified Non-Modifications

Per ARC0 rules, the following were NOT modified:
- All `src/**` — no production code changed
- All `prompts/**` — no prompt text changed
- Only `tests/unit/compiler/annotation_role_contract/` was added (new directory)
