"""Dependency closure check and validation."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.materialization.id_allocator import IdAllocator
from nl2spl.compiler.spl_editing.materialization.model import (
    WRITE_LAYER_SPECS,
    DependencyValidationResult,
    MaterializationPlan,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import (
    ResolvedSelectableRef,
    SelectableRef,
    SelectableRefSet,
)


def validate_dependency_closure(
    plan: MaterializationPlan,
    snapshot: ArtifactSnapshot,
    refset: SelectableRefSet,
    target: RepairTarget,
    id_allocator: IdAllocator,
    resolved_refs: tuple[ResolvedSelectableRef, ...] = (),
    target_ref: SelectableRef | None = None,
) -> DependencyValidationResult:
    """Validate dependency closure requirements, constraints, scopes, and allocator namespaces."""
    errors: list[str] = []
    missing_artifacts: list[str] = []
    failed_constraints: list[str] = []

    # 1. Required artifacts exist in snapshot
    for art_name in plan.dependency_closure.required_artifacts:
        if not hasattr(snapshot, art_name) or getattr(snapshot, art_name) is None:
            missing_artifacts.append(art_name)
            errors.append(f"Required artifact '{art_name}' is missing from snapshot.")

    # 2. Required fields exist on artifacts (walking nested attributes dynamically)
    for req_field in plan.dependency_closure.required_artifact_fields:
        art = getattr(snapshot, req_field.artifact_name, None)
        if art is None:
            continue
        current = art
        path_valid = True
        for part in req_field.field_path:
            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, (list, tuple)) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                path_valid = False
                break
        if not path_valid or current is None:
            failed_constraints.append(f"{req_field.artifact_name}.{'.'.join(req_field.field_path)}")
            errors.append(
                f"Required field path '{req_field.field_path}' in artifact '{req_field.artifact_name}' is missing or None."  # noqa: E501
            )

    # 3. Worker scope requirement matches target worker ID
    scope_req = plan.dependency_closure.worker_scope_requirement
    if scope_req:
        if not target.worker_id:
            errors.append(
                f"Target worker_id is missing, but plan requires '{scope_req}' worker scope."
            )
        elif snapshot.worker_plan is None:
            errors.append("worker_plan is missing but target worker scope is required.")
        else:
            worker_ids = {w.worker_id for w in snapshot.worker_plan.workers}
            if target.worker_id not in worker_ids:
                errors.append(f"Target worker '{target.worker_id}' is not defined in worker_plan.")

            main_id = snapshot.worker_plan.main_worker_id
            if scope_req == "main" and target.worker_id != main_id:
                errors.append(
                    f"Target worker '{target.worker_id}' is not the main worker, but plan requires main worker scope."  # noqa: E501
                )
            elif scope_req == "child" and target.worker_id == main_id:
                errors.append(
                    f"Target worker '{target.worker_id}' is the main worker, but plan requires a child worker scope."  # noqa: E501
                )
    elif target.worker_id:
        if snapshot.worker_plan is None:
            errors.append("worker_plan is missing but target worker_id is specified.")
        else:
            worker_ids = {w.worker_id for w in snapshot.worker_plan.workers}
            if target.worker_id not in worker_ids:
                errors.append(f"Target worker '{target.worker_id}' is not defined in worker_plan.")

    # 4. Ref-role count constraints apply to this confirmed materialization,
    # not to every candidate that happened to be available in the refset.
    materialization_refs = [resolved.ref for resolved in resolved_refs]
    if target_ref is not None:
        materialization_refs.append(target_ref)

    for constraint in plan.dependency_closure.required_ref_role_constraints:
        matching_refs = []
        for ref in materialization_refs:
            if ref.ref_role != constraint.role:
                continue
            if constraint.worker_scope is not None:
                expected_scope = (
                    target.worker_id
                    if constraint.worker_scope == "target"
                    else constraint.worker_scope
                )
                if ref.worker_id != expected_scope:
                    continue
            matching_refs.append(ref)

        count = len(matching_refs)
        if count < constraint.min_count:
            failed_constraints.append(f"role_count:{constraint.role}")
            errors.append(
                f"Ref role '{constraint.role}' count {count} is less than min_count {constraint.min_count}."  # noqa: E501
            )
        if constraint.max_count is not None and count > constraint.max_count:
            failed_constraints.append(f"role_count:{constraint.role}")
            errors.append(
                f"Ref role '{constraint.role}' count {count} is greater than max_count {constraint.max_count}."  # noqa: E501
            )

    # 5. ID allocator namespaces are available in id_allocator
    for ns in plan.dependency_closure.required_id_allocator_namespaces:
        if not id_allocator.is_namespace_available(ns):
            failed_constraints.append(f"allocator_namespace:{ns}")
            errors.append(
                f"ID allocator namespace '{ns}' is not available in the provided allocator."
            )

    # 6. Write contract and Lane compatibility matrix checks
    has_pre_normalize = False
    for layer in plan.writes_to:
        if layer not in WRITE_LAYER_SPECS:
            errors.append(f"Invalid write layer: '{layer}'.")
            continue
        spec = WRITE_LAYER_SPECS[layer]
        # writes_to artifact must be in plan.editable_artifacts and plan.output_artifacts
        if spec.catalog_artifact not in plan.editable_artifacts:
            errors.append(
                f"Write layer '{layer}' maps to catalog artifact '{spec.catalog_artifact}' which is not in plan.editable_artifacts."  # noqa: E501
            )
        if spec.catalog_artifact not in plan.output_artifacts:
            errors.append(
                f"Write layer '{layer}' maps to catalog artifact '{spec.catalog_artifact}' which is not in plan.output_artifacts."  # noqa: E501
            )

        if layer in (
            "worker_plan_pre_normalize",
            "worker_block_plan_pre_normalize",
            "worker_step_plan_pre_normalize",
        ):
            has_pre_normalize = True

    if has_pre_normalize:
        if not plan.normalizer_required:
            errors.append("Plan specifies pre-normalize writes but normalizer_required is False.")
        if not plan.stage10_rebuild_required:
            errors.append(
                "Plan specifies pre-normalize writes but stage10_rebuild_required is False."
            )
        if plan.verification_lane != "B":
            errors.append(
                f"Plan specifies pre-normalize writes but verification_lane is '{plan.verification_lane}' (expected 'B')."  # noqa: E501
            )
    else:
        if plan.verification_lane == "A":
            if plan.normalizer_required:
                errors.append("Plan verification_lane is A but normalizer_required is True.")

    is_valid = len(errors) == 0
    return DependencyValidationResult(
        is_valid=is_valid,
        errors=tuple(errors),
        missing_artifacts=tuple(missing_artifacts),
        failed_constraints=tuple(failed_constraints),
        validation_metadata={
            "plan_id": plan.materialization_plan_id,
            "has_pre_normalize": has_pre_normalize,
        },
    )
