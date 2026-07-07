"""Builder for SelectableRefSet from ArtifactSnapshot and RepairContext."""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.spl_editing.core.model import RepairContext
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.selectable_refs.errors import SelectableRefCollisionError
from nl2spl.compiler.spl_editing.selectable_refs.model import (
    SelectableRef,
    SelectableRefSet,
    build_ref_id,
)


def _get_symbol_table_variables(symbol_table: Any) -> list[tuple[tuple[str, str | None, str], Any]]:
    """Return symbol-table variables from the compiler's structured storage."""
    results = []
    seen_keys = set()

    # SymbolTable stores scoped variables in a composite-key map. Keep this
    # access isolated here so selectable refs do not guess from prompt text.
    if hasattr(symbol_table, "_variables"):
        for key, var in symbol_table._variables.items():
            results.append((key, var))
            seen_keys.add(key)

    if hasattr(symbol_table, "variables"):
        for name, var in symbol_table.variables.items():
            key = ("global", None, name)
            if key not in seen_keys:
                results.append((key, var))
                seen_keys.add(key)

    return results


def _resource_namespace(scope: str, resource_kind: str) -> tuple[str, tuple[str, ...]]:
    """Return the source ref and scope path for a resource subtype."""
    return f"{scope}.{resource_kind}", tuple(scope.split(".")) + (resource_kind,)


def _append_resource_ref(
    refs: list[SelectableRef],
    *,
    name: str,
    worker_id: str | None,
    source_artifact: str,
    source_artifact_ref: str,
    scope_path: tuple[str, ...],
    ref_role: str = "selectable_input",
) -> None:
    refs.append(
        SelectableRef(
            ref_id=build_ref_id("resource", worker_id, source_artifact_ref, scope_path, name),
            ref_kind="resource",
            ref_role=ref_role,
            canonical_name=name,
            display_label=name,
            worker_id=worker_id,
            source_artifact=source_artifact,
            source_artifact_ref=source_artifact_ref,
            scope_path=scope_path,
        )
    )


class SelectableRefSetBuilder:
    """Builder that harvests selectable references from compiler artifacts."""

    @staticmethod
    def build(
        snapshot: ArtifactSnapshot,
        context: RepairContext,
        policy_id: str = "required_output.producer.selectable_refs.v1",
    ) -> SelectableRefSet:
        """Construct a SelectableRefSet from the snapshot and context."""
        try:
            return SelectableRefSetBuilder._build_impl(snapshot, context, policy_id)
        except AttributeError:
            # Graceful degradation for mock/partial snapshots (e.g. integration tests).
            # An AttributeError means the snapshot doesn't have the expected
            # structure --treat it as unavailable.
            return SelectableRefSet(
                set_id=f"set_{context.issue.issue_id}_{snapshot.snapshot_id}_{snapshot.overlay_version}",
                issue_id=context.issue.issue_id,
                snapshot_id=snapshot.snapshot_id,
                worker_scope=context.worker_scope,
                refs=(),
                policy_id=policy_id,
                missing_required_ref_kinds=("worker_input", "step_output", "variable", "resource"),
                is_available=False,
            )

    @staticmethod
    def _build_impl(
        snapshot: ArtifactSnapshot,
        context: RepairContext,
        policy_id: str,
    ) -> SelectableRefSet:
        """Internal implementation --may raise AttributeError on mock objects."""
        worker_id = context.worker_scope
        refs: list[SelectableRef] = []

        missing_kinds: list[str] = []
        if snapshot.worker_plan is None or not hasattr(snapshot.worker_plan, "workers"):
            missing_kinds.append("worker_input")
        if snapshot.worker_step_plan is None or not hasattr(
            snapshot.worker_step_plan, "worker_steps"
        ):
            missing_kinds.append("step_output")
        if snapshot.symbol_table is None:
            missing_kinds.append("variable")
        if snapshot.worker_scoped_resources is None and snapshot.resources is None:
            missing_kinds.append("resource")

        is_available = len(missing_kinds) == 0

        # 1. Harvest target outputs (from context.related_outputs)
        for output_name in context.related_outputs:
            refs.append(
                SelectableRef(
                    ref_id=build_ref_id(
                        "required_output",
                        worker_id,
                        "required_output_context",
                        (),
                        output_name,
                    ),
                    ref_kind="required_output",
                    ref_role="target_output",
                    canonical_name=output_name,
                    display_label=output_name,
                    worker_id=worker_id,
                    source_artifact="required_output_context",
                    source_artifact_ref="required_output_context",
                    scope_path=(),
                )
            )

        # 1a. Harvest target worker promotion candidate.
        if context.target.target_kind == "WORKER_PROMOTION" and context.target.canonical_name:
            refs.append(
                SelectableRef(
                    ref_id=build_ref_id(
                        "worker",
                        worker_id,
                        "worker_promotion_context",
                        (),
                        context.target.canonical_name,
                    ),
                    ref_kind="worker",
                    ref_role="target_worker",
                    canonical_name=context.target.canonical_name,
                    display_label=context.target.canonical_name,
                    worker_id=worker_id,
                    source_artifact="worker_promotion_context",
                    source_artifact_ref="worker_promotion_context",
                    scope_path=(),
                )
            )
        # 1b. Harvest target exception flow.
        if context.target.target_kind == "EXCEPTION_FLOW" and context.target.canonical_name:
            refs.append(
                SelectableRef(
                    ref_id=build_ref_id(
                        "exception_flow",
                        worker_id,
                        "exception_flow_context",
                        (),
                        context.target.canonical_name,
                    ),
                    ref_kind="exception_flow",
                    ref_role="target_exception_flow",
                    canonical_name=context.target.canonical_name,
                    display_label=context.target.canonical_name,
                    worker_id=worker_id,
                    source_artifact="exception_flow_context",
                    source_artifact_ref="exception_flow_context",
                    scope_path=(),
                )
            )
        # 2. Harvest worker inputs (from snapshot.worker_plan)
        if snapshot.worker_plan is not None and hasattr(snapshot.worker_plan, "workers"):
            for worker in snapshot.worker_plan.workers:
                if worker_id is None or worker.worker_id == worker_id:
                    for input_field in worker.input_contract:
                        if not str(input_field.name).strip():
                            continue
                        refs.append(
                            SelectableRef(
                                ref_id=build_ref_id(
                                    "worker_input",
                                    worker.worker_id,
                                    worker.worker_id,
                                    (),
                                    input_field.name,
                                ),
                                ref_kind="worker_input",
                                ref_role="selectable_input",
                                canonical_name=input_field.name,
                                display_label=input_field.name,
                                worker_id=worker.worker_id,
                                source_artifact="worker_plan",
                                source_artifact_ref=worker.worker_id,
                                scope_path=(),
                            )
                        )

        # 3. Harvest step outputs (from snapshot.worker_step_plan)
        if snapshot.worker_step_plan is not None and hasattr(
            snapshot.worker_step_plan, "worker_steps"
        ):
            for wid, steps in snapshot.worker_step_plan.worker_steps.items():
                if worker_id is None or wid == worker_id:
                    for step in steps:
                        if wid == snapshot.worker_plan.main_worker_id:
                            refs.append(
                                SelectableRef(
                                    ref_id=build_ref_id(
                                        "existing_step",
                                        wid,
                                        step.step_id,
                                        ("main_flow", "placement"),
                                        step.step_id,
                                    ),
                                    ref_kind="existing_step",
                                    ref_role="placement_anchor",
                                    canonical_name=step.step_id,
                                    display_label=step.text,
                                    worker_id=wid,
                                    source_artifact="worker_step_plan",
                                    source_artifact_ref=step.step_id,
                                    scope_path=("main_flow", "placement"),
                                )
                            )
                        for out in step.outputs:
                            refs.append(
                                SelectableRef(
                                    ref_id=build_ref_id("step_output", wid, step.step_id, (), out),
                                    ref_kind="step_output",
                                    ref_role="selectable_input",
                                    canonical_name=out,
                                    display_label=out,
                                    worker_id=wid,
                                    source_artifact="worker_step_plan",
                                    source_artifact_ref=step.step_id,
                                    scope_path=(),
                                )
                            )

        # 4. Harvest symbol table variables (from snapshot.symbol_table)
        if snapshot.symbol_table is not None:
            for key, var in _get_symbol_table_variables(snapshot.symbol_table):
                scope_kind, scope_id, name = key
                if (
                    scope_kind == "global"
                    or worker_id is None
                    or (scope_kind == "worker" and scope_id == worker_id)
                ):
                    refs.append(
                        SelectableRef(
                            ref_id=build_ref_id(
                                "variable",
                                scope_id,
                                "symbol_table",
                                (scope_kind,),
                                name,
                            ),
                            ref_kind="variable",
                            ref_role="selectable_input",
                            canonical_name=name,
                            display_label=name,
                            worker_id=scope_id if scope_kind == "worker" else None,
                            source_artifact="symbol_table",
                            source_artifact_ref="symbol_table",
                            scope_path=(scope_kind,),
                            scope=scope_kind,
                            type_hint=getattr(var, "data_type", None),
                        )
                    )
                    # Result bindings are a distinct authority role.  Give the
                    # role its own stable ref identity rather than allowing a
                    # selectable-input ref to be reinterpreted at submission.
                    refs.append(
                        SelectableRef(
                            ref_id=build_ref_id(
                                "variable",
                                scope_id,
                                "symbol_table.binding_target",
                                (scope_kind, "binding_target"),
                                name,
                            ),
                            ref_kind="variable",
                            ref_role="binding_target",
                            canonical_name=name,
                            display_label=name,
                            worker_id=scope_id if scope_kind == "worker" else None,
                            source_artifact="symbol_table",
                            source_artifact_ref="symbol_table.binding_target",
                            scope_path=(scope_kind, "binding_target"),
                            scope=scope_kind,
                            type_hint=getattr(var, "data_type", None),
                        )
                    )

        # 5. Harvest resource registry variables, files, and APIs.
        if snapshot.worker_scoped_resources is not None:
            wsr = snapshot.worker_scoped_resources

            source_ref, scope_path = _resource_namespace("global_resources", "variables")
            for var in wsr.global_resources.variables:
                _append_resource_ref(
                    refs,
                    name=var.name,
                    worker_id=None,
                    source_artifact="worker_scoped_resources",
                    source_artifact_ref=source_ref,
                    scope_path=scope_path,
                )

            source_ref, scope_path = _resource_namespace("global_resources", "files")
            for file in wsr.global_resources.files:
                _append_resource_ref(
                    refs,
                    name=file.name,
                    worker_id=None,
                    source_artifact="worker_scoped_resources",
                    source_artifact_ref=source_ref,
                    scope_path=scope_path,
                )

            source_ref, scope_path = _resource_namespace("global_resources", "apis")
            for api in wsr.global_resources.apis:
                _append_resource_ref(
                    refs,
                    name=api.api_name,
                    worker_id=None,
                    source_artifact="worker_scoped_resources",
                    source_artifact_ref=source_ref,
                    scope_path=scope_path,
                    ref_role="api_resource",
                )

            for wid, registry in wsr.worker_resources.items():
                if worker_id is None or wid == worker_id:
                    source_ref, scope_path = _resource_namespace(
                        f"worker_resources.{wid}", "variables"
                    )
                    for var in registry.variables:
                        _append_resource_ref(
                            refs,
                            name=var.name,
                            worker_id=wid,
                            source_artifact="worker_scoped_resources",
                            source_artifact_ref=source_ref,
                            scope_path=scope_path,
                        )

                    source_ref, scope_path = _resource_namespace(f"worker_resources.{wid}", "files")
                    for file in registry.files:
                        _append_resource_ref(
                            refs,
                            name=file.name,
                            worker_id=wid,
                            source_artifact="worker_scoped_resources",
                            source_artifact_ref=source_ref,
                            scope_path=scope_path,
                        )

                    source_ref, scope_path = _resource_namespace(f"worker_resources.{wid}", "apis")
                    for api in registry.apis:
                        _append_resource_ref(
                            refs,
                            name=api.api_name,
                            worker_id=wid,
                            source_artifact="worker_scoped_resources",
                            source_artifact_ref=source_ref,
                            scope_path=scope_path,
                            ref_role="api_resource",
                        )

        elif snapshot.resources is not None:
            res = snapshot.resources

            source_ref, scope_path = _resource_namespace("resources", "variables")
            for var in res.variables:
                _append_resource_ref(
                    refs,
                    name=var.name,
                    worker_id=None,
                    source_artifact="resources",
                    source_artifact_ref=source_ref,
                    scope_path=scope_path,
                )

            source_ref, scope_path = _resource_namespace("resources", "files")
            for file in res.files:
                _append_resource_ref(
                    refs,
                    name=file.name,
                    worker_id=None,
                    source_artifact="resources",
                    source_artifact_ref=source_ref,
                    scope_path=scope_path,
                )

            source_ref, scope_path = _resource_namespace("resources", "apis")
            for api in res.apis:
                _append_resource_ref(
                    refs,
                    name=api.api_name,
                    worker_id=None,
                    source_artifact="resources",
                    source_artifact_ref=source_ref,
                    scope_path=scope_path,
                    ref_role="api_resource",
                )

        # 6. Harvest source spans as source_evidence role.
        for span in getattr(snapshot, "spans", ()):
            refs.append(
                SelectableRef(
                    ref_id=build_ref_id("source_span", None, "spans", (), span.span_id),
                    ref_kind="source_span",
                    ref_role="source_evidence",
                    canonical_name=span.span_id,
                    display_label=span.text,
                    worker_id=None,
                    source_artifact="spans",
                    source_artifact_ref="spans",
                    scope_path=(),
                )
            )

        # Collision detection: fail loudly instead of silently deduplicating.
        seen_ref_ids: dict[str, SelectableRef] = {}
        for ref in refs:
            if ref.ref_id in seen_ref_ids:
                existing = seen_ref_ids[ref.ref_id]
                raise SelectableRefCollisionError(
                    f"Collision detected for ref_id '{ref.ref_id}'.\n"
                    f"  Existing: kind={existing.ref_kind}, name={existing.canonical_name}, source={existing.source_artifact}\n"  # noqa: E501
                    f"  Duplicate: kind={ref.ref_kind}, name={ref.canonical_name}, source={ref.source_artifact}"  # noqa: E501
                )
            seen_ref_ids[ref.ref_id] = ref

        return SelectableRefSet(
            set_id=f"set_{context.issue.issue_id}_{snapshot.snapshot_id}_{snapshot.overlay_version}",
            issue_id=context.issue.issue_id,
            snapshot_id=snapshot.snapshot_id,
            worker_scope=worker_id,
            refs=tuple(refs),
            policy_id=policy_id,
            missing_required_ref_kinds=tuple(missing_kinds),
            is_available=is_available,
        )
