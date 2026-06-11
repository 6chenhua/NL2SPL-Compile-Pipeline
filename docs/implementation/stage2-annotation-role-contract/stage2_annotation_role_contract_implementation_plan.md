# Stage 2 Annotation Role Contract 实施计划

## 1. 文档目的

本文档基于 `docs/design/Stage 2 Annotation Role Contract 架构设计 (1).pdf` 制定可分阶段验收的实施计划。

本计划的目标不是推翻 `RouteAnnotation`，而是把当前分散的 role contract 机制收敛为单一 source of truth，并确保 Stage 2 输出给下游的是经过 deterministic role contract normalization 与 full-field validation 的 confirmed annotation。

后续代码审核必须以本文档和架构设计 PDF 为准。实现报告只能作为辅助材料，PM 审核必须逐项核验真实代码、测试和中间产物。

## 2. 当前代码事实

当前仓库中已经存在多份 role contract 或 contract-like 逻辑：

- `src/nl2spl/pipeline/stages/stage2_field_router.py`
  - `_ANNOTATION_SEMANTICS`
  - `ROUTE_PRIOR_ROLE_CONTRACTS`
  - `_normalize_annotation_contract()`
  - LLM merge 中的字段校验与覆盖逻辑
- `src/nl2spl/pipeline/stages/stage2_field_router_validator.py`
  - `_ROLE_CONTRACT`
  - allowed schema validation
  - partial role-specific checks
- `src/nl2spl/pipeline/stages/stage2_field_router_prompt.py`
  - `ALLOWED_FIELDS`
  - `ALLOWED_SEMANTIC_ROLES`
  - `ALLOWED_CONSTRUCT_TARGETS`
  - `ALLOWED_SLOT_TARGETS`
  - `NON_EXECUTABLE_ROLES`
  - `EXECUTABLE_ROLES`
- `src/nl2spl/compiler/resource_contract_demand_view/builder.py`
  - `_CONTRACT_ROLES`
  - `_direction_candidates()`
  - defensive consistency checks for resource contracts
- Several downstream consumers still inspect `construct_target`, `route_family`, or `slot_target` as supporting signals.

The implementation must consolidate these into one role contract source, not add another unsynchronized table.

## 3. Product Architecture Principles

The final implementation must preserve these boundaries:

1. `semantic_role` is the primary semantic decision.
2. LLM may propose `semantic_role`, provenance, reason, ambiguity, and split hints.
3. `field`, `route_family`, `construct_target`, `slot_target`, and `executable` are compiler-facing fields derived from `semantic_role` by role contract.
4. Expected `None` is an explicit contract, not "do not check".
5. All annotation generation paths share the same role contract:
   - LLM refinement path
   - deterministic packet annotation path
   - route-prior / adapter-derived path
   - legacy compatibility path while it remains
6. Validator checks full-field consistency using the same role contract.
7. Downstream stages must not infer construct demand from a single field such as `construct_target`, `route_family`, or `slot_target`.
8. Resource contract demand existence is authorized by `semantic_role in {"input_contract", "output_contract"}`.
9. Requiredness is not derived by role contract. It remains independent tri-state metadata from structural sources.
10. CoverageValidator detects missing annotations but must not generate demands.
11. Prompt improvements are allowed only as UX/quality guidance. Correctness must come from role contract and validator.
12. No hidden fallback, no downstream guessing, no silent invalid annotation consumption.
13. Canonical semantic roles and structural/internal aliases are different layers.
14. Prompt-visible LLM semantic roles must not include structural aliases unless explicitly approved.
15. Compile hints are not authoritative for role-contract fields.
16. Requiredness validation must run after requiredness enrichment, not inside the pre-enrichment LLM validator.

## 4. Global Forbidden Changes

Unless a phase explicitly allows it, do not modify:

- `src/nl2spl/compiler/resource_contract_demand_view/**` beyond defensive selector checks listed in ARC5.
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/**`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/**`
- `src/nl2spl/pipeline/stages/stage10_worker_assembler/**`
- `src/nl2spl/pipeline/stages/stage11_spl_renderer/**`
- `src/nl2spl/pipeline/executable_gate.py`
- IRS v6 checker behavior.
- ResourceContract requiredness semantics.
- Generic NL path behavior. This project currently targets structural NL.

Do not add keyword-driven semantic role inference. If a phase appears to require a new semantic decision that can be implemented either with LLM or rules, stop and ask PM for a decision before coding.

## 5. Naming

This migration uses phase prefix `ARC`:

- ARC0: Baseline and Gap Audit
- ARC1: Canonical Role Contract Model
- ARC2: Schema Constants from Role Contract
- ARC3: Annotation Normalization Convergence
- ARC4: Full-Field Validator
- ARC5: DemandView and Downstream Boundary Hardening
- ARC6: Prompt and LLM Output Contract Narrowing
- ARC7: Diagnostics and Report Projection
- ARC8: Final Audit and Migration Cleanup

## 5.1 Mandatory Revisions From Design Review

The following requirements are part of the implementation baseline:

1. **Alias separation is mandatory.**
   `task_family`, `policy`, `exception_handler`, `runtime_input`, and `required_output` are not necessarily LLM-visible semantic roles. They are structural packet/prior aliases that must resolve to canonical semantic roles before role contract lookup.

2. **LLM-visible schema stability is mandatory until ARC6.**
   ARC1/ARC2 must not accidentally expand `ALLOWED_SEMANTIC_ROLES`. If the canonical registry contains internal aliases or roles such as `failure_condition`, those must not become prompt-visible unless PM explicitly approves a schema expansion.

3. **Hint enrichment must be governed by role contract.**
   `_enrich_from_hints()` must not write or override `field`, `route_family`, `construct_target`, `slot_target`, `semantic_role`, or `executable` after role contract normalization. Hints may add provenance, diagnostics, and debug candidate metadata only.

4. **Requiredness validation is post-enrichment.**
   `RouteRefinementValidator` runs before `_enrich_contract_requiredness()`. Therefore it must not reject resource contract annotations simply because requiredness has not yet been injected. Requiredness checks belong to a final annotation validation step after enrichment.

5. **Typed annotation diagnostics begin in ARC4.**
   Do not wait until ARC7 to reconstruct expected/actual role contract conflicts from strings. ARC4 must produce typed diagnostics; ARC7 projects them into compile diagnostics and reports.

6. **Downstream audits must be context-aware.**
   ARC5 must not rely on raw grep alone. Static tests should either use AST or narrow context enough to distinguish illegal demand creation from legal role contract definitions, validator checks, fixtures, and diagnostic messages.

## 6. ARC0: Baseline and Gap Audit

### Goal

Lock current behavior and expose the exact gaps this migration must close without changing production code.

### Editable Files

- `tests/unit/compiler/annotation_role_contract/test_arc0_baseline.py`
- Optional audit document:
  - `docs/implementation/stage2-annotation-role-contract/arc0_role_contract_audit.md`

### Forbidden Files

- All `src/**`
- `prompts/**`

### Required Tests

Add current-behavior and target-future tests for:

1. `profile_domain + construct_target=RESOURCE_CONTRACT + slot_target=input` must currently be shown as a risk/gap if accepted anywhere.
2. Existing `ROUTE_PRIOR_ROLE_CONTRACTS` and validator `_ROLE_CONTRACT` are not the same source.
3. Existing allowed schema constants are not generated from role contract.
4. Current validator does not enforce expected `None` for `profile_domain.construct_target` and `profile_domain.slot_target`.
5. Current deterministic packet annotation path uses `_ANNOTATION_SEMANTICS`, not a shared role contract.
6. DemandView only authorizes demand by `semantic_role`, not by `construct_target` alone. If this is already true, lock it as passing baseline.
7. Existing ResourceContract requiredness path remains independent and must not be changed by role contract migration.

Target-future tests may use `xfail(strict=True)` only when the current behavior genuinely cannot pass before later ARC phases.

### Acceptance Criteria

- No production code modified.
- No prompt modified.
- Current passing baseline tests are strong assertions, not empty metadata tests.
- All xfail tests have explicit phase names in `reason`.
- Audit document lists every role-contract-like source and its owner.
- Full unit suite passes except intentional strict xfail.

### PM Review Checklist

- Verify `git diff` contains only tests and optional ARC0 audit doc.
- Verify tests inspect real modules, not copied sample tables.
- Verify no skip usage.
- Verify no new semantic heuristic was introduced in tests.

## 7. ARC1: Canonical Role Contract Model

### Goal

Create the single role contract source of truth without wiring it into production behavior yet.

This phase must also separate canonical semantic roles from structural/internal aliases. The registry is not just a flat `semantic_role -> contract` table.

### Editable Files

- New package:
  - `src/nl2spl/compiler/annotation_role_contract/__init__.py`
  - `src/nl2spl/compiler/annotation_role_contract/model.py`
  - `src/nl2spl/compiler/annotation_role_contract/registry.py`
  - `src/nl2spl/compiler/annotation_role_contract/diagnostics.py`
- Tests:
  - `tests/unit/compiler/annotation_role_contract/test_arc1_role_contract_model.py`

### Forbidden Files

- `stage2_field_router.py`
- `stage2_field_router_validator.py`
- `stage2_field_router_prompt.py`
- DemandView builder.
- Prompts.

### Required Design

Define a typed contract model similar to:

```python
@dataclass(frozen=True)
class AnnotationRoleContract:
    semantic_role: str
    field: str
    route_family: str | None
    construct_target: str | None
    slot_target: str | None
    executable: bool
    materialization_authority: str = "annotation_role_contract"
    notes: str | None = None
```

The registry must provide:

- `get_role_contract(role: str) -> AnnotationRoleContract | None`
- `require_role_contract(role: str) -> AnnotationRoleContract`
- `resolve_semantic_role(role_or_alias: str) -> str | None`
- `allowed_semantic_roles()`
- `allowed_llm_semantic_roles()`
- `allowed_internal_prior_roles()`
- `allowed_fields()`
- `allowed_construct_targets()`
- `allowed_slot_targets()`
- `non_executable_roles()`
- `executable_roles()`

The implementation may use a separate alias model, for example:

```python
@dataclass(frozen=True)
class AnnotationRoleAlias:
    alias: str
    canonical_semantic_role: str
    source_kind: Literal["packet_type", "route_prior", "section_context", "legacy"]
    llm_visible: bool = False
```

Aliases are not confirmed semantic roles. They must resolve to a canonical semantic role before contract lookup.

Do not include requiredness.

### Initial Required Role Set

At minimum cover roles already present in Stage 2:

- `profile_domain`
- `input_contract`
- `output_contract`
- `process_step`
- `constraint`
- `failure_mode`
- `failure_condition`
- `exception_handler_action`
- `delegation_intent`
- `delegation_boundary_constraint`
- `delegation_prohibition`
- `api_candidate`
- `worker_handoff_candidate`
- `handoff_condition`
- `integration_hint`

If a role lacks stable construct mapping, encode `construct_target=None` and `slot_target=None` conservatively instead of allowing LLM to decide.

### Initial Required Alias Set

At minimum cover aliases currently implied by Stage 2:

- `task_family -> profile_domain`
- `policy -> constraint`
- `exception_handler -> exception_handler_action`
- `runtime_input -> input_contract`
- `required_output -> output_contract`
- Any current packet type or route-prior key that is not a canonical LLM semantic role.

Aliases must be absent from `allowed_llm_semantic_roles()` unless PM explicitly approves exposing them.

### Acceptance Criteria

- Role contract registry is the only new table.
- Canonical role registry and alias resolver are separate concepts.
- All fields are typed; expected `None` is represented explicitly.
- Requiredness is absent from the contract model.
- Tests assert exact contract values for every role.
- Tests assert exact alias resolution for every structural alias.
- Tests assert structural aliases are not LLM-visible by default.
- Tests assert allowed schema values are derived from registry.
- Tests assert prompt-visible semantic role set can be kept identical to the pre-migration set.
- Tests assert no duplicate semantic roles.
- Tests assert `profile_domain.construct_target is None` and `profile_domain.slot_target is None`.
- Full unit suite passes.

### PM Review Checklist

- Reject if implementation uses loose `dict[str, Any]` as the primary public model.
- Reject if requiredness appears in role contract.
- Reject if structural aliases are mixed into canonical semantic role list without explicit visibility flags.
- Reject if `task_family`, `policy`, `exception_handler`, `runtime_input`, or `required_output` become LLM-visible accidentally.
- Reject if role values are duplicated in tests instead of checking registry behavior.
- Reject if a new role is added without an explicit contract and rationale.

## 8. ARC2: Schema Constants from Role Contract

### Goal

Make Stage 2 prompt schema constants depend on the canonical role contract registry, removing one duplicate source.

ARC2 must preserve the current LLM-visible schema unless PM explicitly approves schema expansion. Registry-derived constants must distinguish canonical/internal roles from prompt-visible roles.

### Editable Files

- `src/nl2spl/pipeline/stages/stage2_field_router_prompt.py`
- `tests/unit/compiler/annotation_role_contract/test_arc2_prompt_schema_from_contract.py`
- Existing prompt contract tests may be updated.

### Forbidden Files

- `stage2_field_router.py`
- `stage2_field_router_validator.py`
- DemandView builder.
- Prompt text files, unless a separate PM decision is made.

### Required Changes

- Replace hard-coded role-related allowed sets with values derived from registry:
  - `ALLOWED_SEMANTIC_ROLES`
  - `ALLOWED_FIELDS`
  - `ALLOWED_CONSTRUCT_TARGETS`
  - `ALLOWED_SLOT_TARGETS`
  - `NON_EXECUTABLE_ROLES`
  - `EXECUTABLE_ROLES`
- Keep public constant names temporarily for compatibility, but source them from role contract.
- `ALLOWED_SEMANTIC_ROLES` must be derived from `allowed_llm_semantic_roles()`, not from all canonical roles plus aliases.
- Internal aliases may be exported through separate internal APIs, but must not appear in LLM prompt schema.

### Acceptance Criteria

- Modifying role contract registry changes prompt schema constants automatically.
- Tests prove prompt constants equal registry-derived sets.
- Tests prove the prompt-visible semantic roles are byte-for-byte equivalent to the current pre-ARC2 role set unless PM approved expansion.
- Tests prove aliases are excluded from prompt-visible allowed roles.
- No behavior change in parser.
- No prompt text changes in this phase.
- Full unit suite passes.

### PM Review Checklist

- Reject if any allowed role/target/slot literal remains as a separate source in `stage2_field_router_prompt.py`.
- Reject if ARC2 expands LLM output schema without an approved decision note.
- Reject if `failure_condition` or structural aliases become LLM-visible by accident.
- Verify tests do not merely assert count thresholds.
- Verify no LLM behavior or prompt text changed.

## 9. ARC3: Annotation Normalization Convergence

### Goal

Ensure every RouteAnnotation generation path derives compiler-facing fields from the canonical role contract.

### Editable Files

- `src/nl2spl/pipeline/stages/stage2_field_router.py`
- Optional adapter helper module under:
  - `src/nl2spl/compiler/annotation_role_contract/normalize.py`
- Tests:
  - `tests/unit/compiler/annotation_role_contract/test_arc3_annotation_normalization.py`
  - Existing Stage 2 tests as needed.

### Forbidden Files

- DemandView builder.
- Stage 6 / IRS / renderer.
- Prompt text files.

### Required Changes

Introduce a deterministic normalization API, for example:

```python
normalize_annotation_from_role(
    span_id: str,
    semantic_role: str,
    *,
    source_section_id: str | None,
    source_packet_id: str | None,
    source_hint_ids: Iterable[str] = (),
    primary: bool = True,
    metadata: Mapping[str, Any] | None = None,
) -> RouteAnnotation
```

All paths must use it:

- deterministic packet annotations
- route-prior derived annotations
- LLM accepted annotations after validation
- legacy compatibility annotations that remain in Stage 2
- compile-hint enrichment path

LLM-provided `field`, `route_family`, `construct_target`, `slot_target`, and `executable` are not authoritative. They may be retained only as diagnostic/debug input before normalization.

Compile hints are also not authoritative. `_enrich_from_hints()` must be migrated so that hints may:

- add `source_hint_ids`
- add raw candidate values into diagnostic/debug metadata
- produce typed conflict diagnostics

Hints must not:

- override `field`
- override `route_family`
- fill or override `construct_target`
- fill or override `slot_target`
- change `semantic_role`
- change `executable`

Normalization must preserve raw conflicting fields before overwriting them, so diagnostics can report expected vs actual. Acceptable implementation shapes include:

- `raw_annotation_snapshot`
- `normalization_diagnostics`
- `candidate_fields`
- a typed normalized result object

### Required Tests

1. LLM returns `profile_domain + RESOURCE_CONTRACT/input`; normalized output is not silently accepted as resource demand.
2. LLM returns `input_contract` with wrong `field`; final confirmed annotation uses contract field `resources`.
3. LLM returns `process_step` with `executable=False`; final confirmed annotation is executable according to contract or rejected with visible diagnostic, depending on ARC4 policy.
4. Deterministic packet path and LLM path produce identical annotation shape for the same semantic role and provenance.
5. `requiredness` metadata survives normalization but is not derived by role contract.
6. Multi-label same span still works when roles are distinct and valid.
7. Compile hint proposes `construct_target=RESOURCE_CONTRACT` for `profile_domain`; confirmed annotation keeps `construct_target=None` and emits diagnostic/debug evidence.
8. Compile hint proposes conflicting `slot_target`; confirmed annotation keeps contract slot.

### Acceptance Criteria

- `_ANNOTATION_SEMANTICS` is removed or converted to a compatibility wrapper over the canonical registry.
- `ROUTE_PRIOR_ROLE_CONTRACTS` is removed or converted to a compatibility wrapper over the canonical registry.
- `_normalize_annotation_contract()` no longer contains role mapping literals.
- `_enrich_from_hints()` no longer writes role-contract fields after normalization.
- Confirmed annotation fields match role contract exactly.
- Raw conflicting LLM/hint fields remain observable through typed diagnostics or debug metadata.
- Full unit suite passes.

### PM Review Checklist

- Reject if role mapping still exists as dict literals in `stage2_field_router.py`.
- Reject if LLM fields are treated as authoritative.
- Reject if hint fields are treated as authoritative.
- Reject if normalization overwrites conflicting raw fields with no diagnostic trail.
- Reject if requiredness is changed by role contract normalization.
- Verify all annotation source paths are covered by tests.

## 10. ARC4: Full-Field Validator

### Goal

Make validator enforce full role contract consistency, including expected `None`.

ARC4 validates role-contract fields and introduces typed annotation diagnostics. Requiredness presence checks for resource contract annotations must run only after `_enrich_contract_requiredness()`.

### Editable Files

- `src/nl2spl/pipeline/stages/stage2_field_router_validator.py`
- Optional:
  - `src/nl2spl/compiler/annotation_role_contract/validator.py`
  - `src/nl2spl/compiler/annotation_role_contract/diagnostics.py`
- Tests:
  - `tests/unit/compiler/annotation_role_contract/test_arc4_validator.py`

### Forbidden Files

- DemandView builder.
- Stage 6 / IRS / renderer.
- Prompt text files.

### Required Behavior

Validator must check:

- semantic_role exists and is known.
- field equals contract.field.
- route_family equals contract.route_family.
- construct_target equals contract.construct_target, including expected `None`.
- slot_target equals contract.slot_target, including expected `None`.
- executable equals contract.executable.
- provenance exists or is derivable from span/structural prior.

The pre-enrichment LLM validator must not reject `input_contract` / `output_contract` only because `metadata["requiredness"]` is absent. That metadata is injected later by Stage 2 requiredness enrichment.

Add a distinct post-enrichment finalization validator for resource contract annotations. It must run after role normalization and `_enrich_contract_requiredness()` and check:

- `metadata["requiredness"] in {"required", "optional", "unspecified"}` when present.
- absence is converted to explicit `unspecified` or reported as typed diagnostic according to existing DemandView policy.
- requiredness is never inferred from semantic_role, field, route_family, construct_target, slot_target, source text, or section title.

Conflict must produce structured diagnostics. The validator must not silently drop invalid annotations without diagnostic.

The validator should distinguish:

- normalized annotation validity
- raw-vs-expected conflict visibility

If raw LLM/hint fields are corrected by role contract normalization, typed diagnostics must preserve the original conflicting value.

### Diagnostic Kinds

At minimum:

- `annotation_role_contract_conflict`
- `annotation_invalid_field_for_role`
- `annotation_invalid_route_family_for_role`
- `annotation_invalid_construct_target_for_role`
- `annotation_invalid_slot_target_for_role`
- `annotation_invalid_executable_for_role`
- `annotation_missing_requiredness`
- `annotation_rejected_after_role_contract_validation`
- `annotation_legacy_field_overridden_by_role_contract`

ARC4 diagnostics should be typed objects or structured dictionaries, not opaque strings. ARC7 will project these diagnostics into `CompileDiagnostic` and reports.

### Acceptance Criteria

- `profile_domain + RESOURCE_CONTRACT/input` is rejected or normalized with diagnostic, and never becomes confirmed resource contract demand.
- Expected `None` is tested explicitly.
- Validator imports role contract registry instead of defining `_ROLE_CONTRACT`.
- Pre-enrichment validator does not reject valid resource contract annotations for missing requiredness.
- Post-enrichment finalizer handles missing/invalid requiredness visibly.
- Diagnostics contain `span_id`, `semantic_role`, expected field value, raw field value, source section/packet when available.
- Normalized annotation may be valid while raw conflict diagnostic still exists.
- Existing anti-fabrication checks remain active.
- Full unit suite passes.

### PM Review Checklist

- Reject if `_ROLE_CONTRACT` remains as an independent table.
- Reject if expected `None` is treated as "no check".
- Reject if invalid annotation is silently discarded.
- Reject if requiredness is checked in the wrong pipeline phase.
- Reject if diagnostics are plain strings with no expected/actual field structure.
- Verify diagnostic appears in `routes.route_diagnostics` or `structured_route_diagnostics`.

## 11. ARC5: DemandView and Downstream Boundary Hardening

### Goal

Lock downstream consumption rules so construct demand cannot be inferred from single fields.

### Editable Files

- `src/nl2spl/compiler/resource_contract_demand_view/builder.py`
- `tests/unit/compiler/resource_contract_demand_view/**`
- Audit tests:
  - `tests/unit/compiler/annotation_role_contract/test_arc5_downstream_boundaries.py`

### Conditionally Editable Files

Only if tests reveal production dependency on forbidden single-field inference:

- `src/nl2spl/pipeline/stages/stage3_2_resource_contract_planner/planner.py`
- downstream compatibility shims documented by ResourceContract DemandView migration.

### Forbidden Files

- Stage 6 semantic materialization logic.
- Renderer.
- IRS checkers.
- Prompt text.

### Required Changes

- DemandView selection must remain:
  - `ann.semantic_role in {"input_contract", "output_contract"}`
- Direction must be canonical from semantic_role.
- `slot_target`, `route_family`, and `metadata.direction` are consistency evidence only.
- Transitional tests that accept direction from `slot_target` or metadata alone must be removed or rewritten as negative tests.
- Add static audit tests for production code:
  - no `construct_target == "RESOURCE_CONTRACT"` as demand existence condition.
  - no `route_family == "resource_contract"` as demand existence condition.
  - no `slot_target == "input" / "output"` as direction authority without semantic_role.

Static audit must be AST- or context-aware. Raw grep is insufficient because the same literals legitimately appear in:

- canonical role contract registry
- validator consistency checks
- diagnostic messages
- test fixtures
- prompt schema constants

The audit should focus on control flow that creates, accepts, appends, or materializes a demand/construct based on a single field.

### Acceptance Criteria

- `construct_target=RESOURCE_CONTRACT` without `input_contract/output_contract` yields no demand and a diagnostic.
- `profile_domain + RESOURCE_CONTRACT/input` yields no demand.
- `input_contract + slot_target=output` yields conflict diagnostic and no silent demand.
- `input_contract + slot_target=input` yields demand if other contract fields are consistent.
- Full unit suite passes.

### PM Review Checklist

- Reject if DemandView accepts `construct_target` as an entry point.
- Reject if metadata direction can create demand without semantic_role.
- Verify static audit tests scan real production files and distinguish illegal demand creation from legal validation/registry uses.

## 12. ARC6: Prompt and LLM Output Contract Narrowing

### Goal

Align prompt and LLM schema with the architecture: LLM primarily proposes semantic role, not compiler-facing fields.

ARC6 is intentionally not required before ARC1-ARC5 correctness. It may run after ARC7. Prompt narrowing must not be used as a substitute for role contract normalization and validation.

### Requires PM Confirmation Before Coding

This phase changes the LLM-facing contract. Before implementation, the assignee must submit a short decision note covering:

- Whether to keep legacy fields in LLM output as optional debug hints for one migration phase.
- Whether to remove `field`, `route_family`, `construct_target`, `slot_target`, and `executable` from prompt examples immediately or deprecate them gradually.
- How parse diagnostics should handle old-model responses that still include these fields.

Do not implement ARC6 until PM approves this decision note.

### Editable Files After Approval

- `prompts/stage2_adapter_guided_system.txt`
- `src/nl2spl/pipeline/stages/stage2_field_router_prompt.py`
- Tests:
  - `tests/unit/compiler/annotation_role_contract/test_arc6_prompt_contract.py`
  - Existing prompt contract tests.

### Forbidden Files

- Downstream consumers.
- DemandView semantics.
- Requiredness source logic.

### Required Behavior

Prompt should emphasize:

- LLM outputs `span_id`, `semantic_role`, `reason`, provenance, split hints.
- LLM should not decide final `field`, `route_family`, `construct_target`, `slot_target`, or `executable`.
- If legacy fields are accepted, they are candidate hints only and will be checked/overridden by role contract.

### Acceptance Criteria

- Prompt examples no longer teach `profile_domain + RESOURCE_CONTRACT`-style coupling.
- Prompt schema is generated from registry where possible.
- Parser remains backward compatible if approved by PM.
- No production correctness depends on prompt compliance.
- ARC4 validation still catches bad output even if the prompt instructs the LLM not to produce it.
- Full unit suite passes.

### PM Review Checklist

- Reject if prompt change is treated as the main correctness fix.
- Reject if prompt narrowing is used to justify removing ARC4 validation.
- Verify validator still catches bad output even if prompt says not to produce it.
- Verify no new rule-based semantic inference is introduced to compensate for prompt narrowing.

## 13. ARC7: Diagnostics and Report Projection

### Goal

Ensure annotation role contract conflicts are visible in intermediate output, compile diagnostics, feedback report, and final readable report.

ARC7 consumes typed diagnostics introduced in ARC4. It must not reconstruct expected/actual conflict data by parsing free-form strings.

### Editable Files

- `src/nl2spl/pipeline/orchestrator.py` only for diagnostic projection/merge if needed.
- `src/nl2spl/compiler/diagnostics/**` if existing diagnostic registry needs kinds.
- `src/nl2spl/pipeline/diagnostics/**` if project-specific diagnostics live there.
- Tests:
  - `tests/unit/compiler/annotation_role_contract/test_arc7_diagnostic_projection.py`

### Forbidden Files

- Role contract mapping semantics.
- Prompt behavior.
- Renderer behavior.

### Required Behavior

Diagnostics from ARC4 must be projected as `CompileDiagnostic` with:

- stable `diagnostic_id`
- `kind`
- `severity`
- `target_ref`
- `source_span_ids`
- `source_section_id`
- `source_packet_id`
- expected vs actual role contract fields
- `blocks_completion` set according to severity and existing compiler policy

If a conflict was safely normalized, ARC7 still projects the correction diagnostic so users can see that raw LLM/hint output was inconsistent with the role contract.

### Acceptance Criteria

- A `profile_domain + RESOURCE_CONTRACT/input` conflict appears in:
  - Stage 2 structured diagnostics
  - `result.compile_diagnostics`
  - readable report
- Diagnostics are deduplicated without collapsing different slots or roles.
- No bare string diagnostics enter final compile diagnostics.
- Full unit suite passes.

### PM Review Checklist

- Reject if diagnostics are only stored in `RouteAnnotation.diagnostics` and not surfaced.
- Reject if diagnostics lose source packet/span provenance.
- Reject if projector parses human-readable strings to recover expected/actual fields.
- Verify dedup key includes role and conflicting field.

## 14. ARC8: Final Audit and Migration Cleanup

### Goal

Confirm migration meets the design and remove stale role contract duplication.

### Editable Files

- `docs/implementation/stage2-annotation-role-contract/arc8_final_audit.md`
- `tests/unit/compiler/annotation_role_contract/test_arc8_final_audit.py`
- Cleanup edits in Stage 2 files only if proven redundant by tests.

### Required Audit Tests

1. No independent `_ROLE_CONTRACT` table remains outside canonical registry.
2. No independent `ROUTE_PRIOR_ROLE_CONTRACTS` mapping remains outside canonical registry.
3. No independent `_ANNOTATION_SEMANTICS` role mapping remains outside canonical registry.
4. Prompt allowed schema is derived from role contract registry.
5. Validator uses registry.
6. Deterministic annotation builder uses registry.
7. DemandView does not accept `construct_target` as source of demand existence.
8. Requiredness is not present in role contract.
9. Expected `None` contract is tested for at least `profile_domain`.
10. Structural aliases are not LLM-visible unless explicitly approved.
11. `_enrich_from_hints()` cannot write role-contract fields after normalization.
12. Requiredness validation happens post-enrichment.
13. Typed annotation diagnostics exist before projection.
14. Full suite passes.

### Acceptance Criteria

- The final audit document maps each design success criterion from PDF section 18 to code/test evidence.
- No stale compatibility comments claim LLM owns construct fields.
- All ARC tests pass.
- Full unit suite passes.

### PM Review Checklist

- Verify final audit references real files and tests.
- Verify no stale TODO says role contract remains split.
- Verify no prompt-only fix is presented as correctness guarantee.

## 15. Cross-Phase Test Matrix

The following scenarios must be covered by the end of ARC8:

| Scenario | Expected Result |
|---|---|
| `profile_domain` only | domain/profile annotation, no construct target, no slot |
| `profile_domain + RESOURCE_CONTRACT/input` from LLM | conflict diagnostic, no demand |
| `input_contract` only | resources/resource_contract/RESOURCE_CONTRACT/input/non-executable |
| `input_contract + wrong field` | normalized or rejected with diagnostic; final confirmed fields match contract |
| `output_contract + missing requiredness` | demand with requiredness unspecified plus diagnostic |
| `process_step` | behavior/flow_relevant/executable |
| `process_step + executable=False` from LLM | role contract conflict visible |
| `failure_mode` | EXCEPTION_FLOW.condition/non-executable |
| `exception_handler_action` | EXCEPTION_FLOW.handler/executable |
| `constraint` | no resource contract demand |
| `construct_target=RESOURCE_CONTRACT` without resource semantic role | no demand |
| route prior annotation path | fields derived from registry |
| deterministic packet annotation path | fields derived from registry |
| LLM refinement path | fields derived from registry |
| requiredness metadata | preserved but not role-derived |

## 16. PM Review Protocol

For every phase submission, the implementer must provide:

1. Modified file list.
2. Explicit statement of production code changed vs tests/docs only.
3. Test commands and outputs.
4. Any xfail/skip and reason.
5. Whether prompt changed.
6. Whether any LLM/rule-based semantic decision was added.
7. Evidence that phase-specific forbidden files were not modified.

PM review will:

- Read the actual diff.
- Run targeted tests.
- Run relevant static scans.
- Run full unit suite when the change touches production code.
- Reject reports that only summarize behavior without code evidence.

## 17. Implementation Order

Do not skip phases.

Recommended order:

1. ARC0
2. ARC1
3. ARC2
4. ARC3
5. ARC4
6. ARC5
7. ARC7
8. ARC6 only after explicit PM decision note
9. ARC8

ARC5 can begin only after ARC4 makes invalid annotations visible. ARC6 is deliberately optional in the critical correctness path and can run after ARC7. Correctness must already be guaranteed by ARC1-ARC5 and surfaced by ARC7.
