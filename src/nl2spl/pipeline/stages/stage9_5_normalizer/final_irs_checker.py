"""Post-normalize IRS checker — final authority for construct-level diagnostics.

Runs AFTER Stage 9.5 normalization and Stage 10 assembly, consuming the
fully assembled WorkerIR.  Produces authoritative diagnostics for:
- missing_handler
- missing_output_producer
- type_or_contract_ambiguity
- assumed_command_not_renderable

Gate is the downstream consumer — it only emits post-gate missing_handler.
"""

from __future__ import annotations

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, WorkerScopedResourceIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR


class PostNormalizeIRSChecker:
    """Final IRS diagnostic pass consuming normalized, assembled IR.

    Runs between Stage 10 (assembly) and the executable-element gate.
    Produces the definitive set of compile diagnostics for requirement
    incompleteness.
    """

    def check(
        self,
        worker: WorkerIR,
        worker_plan: WorkerPlanIR | None = None,
        symbol_table: SymbolTable | None = None,
        resources: ResourceRegistryIR | None = None,
        *,
        worker_scoped_resources: WorkerScopedResourceIR | None = None,
        construct_findings: dict[str, list[dict]] | None = None,
    ) -> list[CompileDiagnostic]:
        """Run all post-normalize checks and return diagnostics.

        Args:
            worker: Assembled WorkerIR from Stage 10 (pre-gate).
            worker_plan: WorkerPlanIR from Stage 3.5.
            symbol_table: Symbol table with producer/consumer links.
            resources: Global resource registry.
            worker_scoped_resources: Worker-scoped resources for merged view.
            construct_findings: Deprecated compatibility parameter. Stage 9.5
                no longer records semantic findings.

        Returns:
            List of CompileDiagnostic records.
        """
        self._diagnostics: list[CompileDiagnostic] = []

        # Build merged resource view for worker-aware path.
        merged_resources = self._merge_resources(resources, worker_scoped_resources)
        declared_apis = {a.api_name for a in merged_resources.apis}
        extra_api_names = self._collect_extra_api_names(worker_plan)
        api_handoff_refs = self._build_api_handoff_refs(worker_plan)
        valid_handoff_ids = {
            h.handoff_id for h in (worker_plan.handoffs if worker_plan else [])
        }
        child_ids = self._child_worker_ids(worker_plan)

        # Collect all steps including child worker steps.
        all_steps = list(worker.steps)
        for child in worker.child_workers:
            all_steps.extend(child.steps)

        # 1. missing_handler
        self._check_missing_handlers(worker, worker_plan)

        # 2. missing_output_producer
        self._check_missing_output_producers(
            worker, all_steps, worker_plan, symbol_table,
            merged_resources, declared_apis, extra_api_names,
            api_handoff_refs, child_ids,
        )

        # 3. type_or_contract_ambiguity
        self._check_type_contract_ambiguities(
            all_steps, symbol_table, merged_resources,
            declared_apis, extra_api_names, api_handoff_refs,
        )

        # 4. assumed_command_not_renderable
        self._check_assumed_commands(all_steps, valid_handoff_ids)

        return self._diagnostics

    # ------------------------------------------------------------------
    # 1. missing_handler
    # ------------------------------------------------------------------

    def _check_missing_handlers(
        self,
        worker: WorkerIR,
        worker_plan: WorkerPlanIR | None,
    ) -> None:
        """Emit missing_handler for exception flows without real handler steps.

        Iterates main worker + child worker exception flows. This checker
        intentionally does not infer whether a matching step is a "real"
        handler from its text; that semantic judgment belongs in LLM stages.
        """
        main_worker_id = worker_plan.main_worker_id if worker_plan else None

        # Build name→id map so child findings recorded with worker_id
        # from the plan can be found when we iterate with worker_name.
        name_to_id: dict[str, str] = {}
        if worker_plan is not None:
            for w in worker_plan.workers:
                if w.worker_name and w.worker_name != w.worker_id:
                    name_to_id[w.worker_name] = w.worker_id

        # Main worker exception flows.
        self._check_exception_flow_handlers_for_scope(
            worker.exception_flows,
            worker.steps,
            worker_id=main_worker_id,
        )

        # Child worker exception flows.
        for child in worker.child_workers:
            child_plan_id = name_to_id.get(child.worker_name)
            self._check_exception_flow_handlers_for_scope(
                child.exception_flows,
                child.steps,
                worker_id=child.worker_name,
                worker_plan_id=child_plan_id,
            )

    def _check_exception_flow_handlers_for_scope(
        self,
        exception_flows: list,
        steps: list[StepIR],
        worker_id: str | None = None,
        worker_plan_id: str | None = None,
    ) -> None:
        for exc_flow in exception_flows:
            handler_steps = [
                s for s in steps
                if s.flow_ref == exc_flow.flow_id
            ]

            if handler_steps:
                continue

            source_span_ids = list(getattr(exc_flow, "spans", []))

            condition_snippet = exc_flow.condition_text[:80]
            if worker_id is not None:
                scope_note = f" in worker '{worker_id}'"
                target_ref = (
                    f"worker:{worker_id}.exception_flow:{exc_flow.flow_id}"
                )
            else:
                scope_note = ""
                target_ref = f"exception_flow:{exc_flow.flow_id}"

            self._diagnostics.append(
                CompileDiagnostic(
                    diagnostic_id=self._next_diag_id(),
                    kind="missing_handler",
                    severity="warning",
                    message=(
                        f"Exception flow '{exc_flow.flow_id}' "
                        f"('{condition_snippet}') has no handler "
                        f"step{scope_note}."
                    ),
                    target_ref=target_ref,
                    source_span_ids=list(source_span_ids),
                    missing_slot=self._make_missing_slot(
                        slot_name="handler_action",
                        required_for=exc_flow.flow_id,
                        reason=(
                            f"Exception flow '{exc_flow.flow_id}' has "
                            f"condition but no handler step."
                        ),
                        source_span_ids=list(source_span_ids),
                    ),
                    suggested_resolution=(
                        f"Add a handler step for "
                        f"'{exc_flow.condition_text}', or mark this "
                        f"exception as acknowledged without handling."
                    ),
                    blocks_rendering=False,
                    blocks_completion=True,
                )
            )

    # ------------------------------------------------------------------
    # 2. missing_output_producer
    # ------------------------------------------------------------------

    def _check_missing_output_producers(
        self,
        worker: WorkerIR,
        all_steps: list[StepIR],
        worker_plan: WorkerPlanIR | None,
        symbol_table: SymbolTable | None,
        merged_resources: ResourceRegistryIR,
        declared_apis: set[str],
        extra_api_names: set[str],
        api_handoff_refs: dict[str, str],
        child_ids: set[str],
    ) -> None:
        """Emit missing_output_producer for required outputs without a producer."""
        if worker_plan is None:
            # Legacy path: check resource variables with source="output".
            index = ProducerIndex(
                steps=all_steps,
                handoffs=None,
                declared_apis=declared_apis,
                extra_api_names=extra_api_names,
                api_handoff_refs=api_handoff_refs,
                known_child_worker_ids=child_ids,
            )
            for variable in merged_resources.variables:
                if not (variable.required and variable.source == "output"):
                    continue
                if index.is_produced(variable.name):
                    continue
                self._diagnostics.append(
                    CompileDiagnostic(
                        diagnostic_id=self._next_diag_id(),
                        kind="missing_output_producer",
                        severity="warning",
                        message=(
                            f"Required output '{variable.name}' "
                            f"({variable.description}) has no "
                            f"source-backed producer step."
                        ),
                        target_ref=f"variable:{variable.name}",
                        source_span_ids=[],
                        missing_slot=self._make_missing_slot(
                            slot_name=variable.name,
                            required_for="complete",
                            reason=(
                                f"Required output '{variable.name}' has "
                                f"no renderable producer step."
                            ),
                        ),
                        suggested_resolution=(
                            f"Add a step that produces '{variable.name}'. "
                            f"If the source requirement does not specify how "
                            f"to produce this output, mark it as optional or "
                            f"remove it from the output contract."
                        ),
                        blocks_rendering=False,
                        blocks_completion=True,
                    )
                )
            return

        # Build a scope map so each worker only sees its own steps.
        # WorkerIR already separates scopes — use them directly.
        scope_map: dict[str, list[StepIR]] = {}
        scope_map[worker_plan.main_worker_id] = list(worker.steps)
        for child in worker.child_workers:
            scope_map[child.worker_name] = list(child.steps)

        def _lookup_scope(spec: WorkerSpecIR) -> list[StepIR]:
            # Try worker_id first, then worker_name.
            steps = scope_map.get(spec.worker_id)
            if steps is not None:
                return steps
            return scope_map.get(spec.worker_name, [])

        for worker_spec in worker_plan.workers:
            required_outputs = [
                f.name for f in worker_spec.output_contract if f.required
            ]
            if not required_outputs:
                continue

            scope_steps = _lookup_scope(worker_spec)

            worker_handoffs = [
                h for h in worker_plan.handoffs
                if h.from_worker == worker_spec.worker_id
            ] if worker_plan.handoffs else None

            own_child_ids = {
                w.worker_id for w in worker_plan.workers
                if w.worker_id != worker_spec.worker_id
                and w.worker_id != worker_plan.main_worker_id
                and w.boundary_kind != "main_worker"
                and w.boundary_kind != "not_a_worker"
            }

            index = ProducerIndex(
                steps=scope_steps,
                handoffs=worker_handoffs if worker_handoffs else None,
                declared_apis=declared_apis,
                extra_api_names=extra_api_names,
                api_handoff_refs=api_handoff_refs,
                known_child_worker_ids=own_child_ids,
            )

            for output in required_outputs:
                if index.is_produced(output):
                    continue

                variable = (
                    symbol_table.variables.get(output) if symbol_table else None
                )
                description = variable.description if variable else output

                if worker_spec.worker_id != worker_plan.main_worker_id:
                    target_ref = (
                        f"worker:{worker_spec.worker_id}.output:{output}"
                    )
                elif worker_plan.main_worker_id:
                    target_ref = (
                        f"worker:{worker_plan.main_worker_id}.output:{output}"
                    )
                else:
                    target_ref = f"variable:{output}"

                suggestion = self._completion_step_text(output)
                self._diagnostics.append(
                    CompileDiagnostic(
                        diagnostic_id=self._next_diag_id(),
                        kind="missing_output_producer",
                        severity="warning",
                        message=(
                            f"Required output '{output}' ({description}) "
                            f"has no source-backed producer step."
                        ),
                        target_ref=target_ref,
                        source_span_ids=[],
                        missing_slot=self._make_missing_slot(
                            slot_name=output,
                            required_for="complete",
                            reason=(
                                f"Required output '{output}' has "
                                f"no renderable producer step."
                            ),
                        ),
                        suggested_resolution=(
                            f"Add a step that produces '{output}', "
                            f"e.g. '{suggestion}'. If the source "
                            f"requirement does not specify how to produce "
                            f"this output, mark it as optional or remove it "
                            f"from the output contract."
                        ),
                        blocks_rendering=False,
                        blocks_completion=True,
                    )
                )

    # ------------------------------------------------------------------
    # 3. type_or_contract_ambiguity
    # ------------------------------------------------------------------

    def _check_type_contract_ambiguities(
        self,
        all_steps: list[StepIR],
        symbol_table: SymbolTable | None,
        merged_resources: ResourceRegistryIR,
        declared_apis: set[str],
        extra_api_names: set[str],
        api_handoff_refs: dict[str, str],
    ) -> None:
        """Emit type_or_contract_ambiguity for commands with unclear contracts."""
        declared = declared_apis
        extra = extra_api_names or set()
        refs = api_handoff_refs or {}

        for step in all_steps:
            kind = ""
            detail = ""
            slot_name = ""
            blocks_render = False

            if step.command_type == "CALL_API" and not step.integration_ref:
                kind = "type_or_contract_ambiguity"
                detail = "CALL_API step has no integration_ref (API name)"
                slot_name = "api_name"
                blocks_render = True
            elif step.command_type == "CALL_API" and step.integration_ref:
                if not self._call_api_is_declared(
                    step, declared, extra, refs,
                ):
                    kind = "type_or_contract_ambiguity"
                    detail = (
                        f"CALL_API references undeclared API "
                        f"'{step.integration_ref}'"
                    )
                    slot_name = "api_name"
                    blocks_render = True
            elif (
                step.command_type == "INVOKE_WORKER"
                and not step.integration_ref
            ):
                kind = "type_or_contract_ambiguity"
                detail = "INVOKE_WORKER step has no concrete worker target"
                slot_name = "target_worker"
                blocks_render = True
            elif (
                step.command_type == "INVOKE_WORKER"
                and step.integration_ref
                and not step.handoff_id
            ):
                kind = "type_or_contract_ambiguity"
                detail = (
                    f"INVOKE_WORKER step targets '{step.integration_ref}' "
                    f"but has no handoff_id — not linked to an accepted handoff"
                )
                slot_name = "handoff_id"
                blocks_render = True
            elif (
                step.command_type == "REQUEST_INPUT"
                and not step.source_span_ids
            ):
                kind = "type_or_contract_ambiguity"
                detail = (
                    "REQUEST_INPUT step has no source-span evidence -- "
                    "may be an assumed interaction"
                )
                slot_name = "value_target"
                blocks_render = False

            if kind:
                self._diagnostics.append(
                    CompileDiagnostic(
                        diagnostic_id=self._next_diag_id(),
                        kind=kind,
                        severity="warning",
                        message=(
                            f"Step '{step.step_id}' "
                            f"({step.command_type}): {detail}."
                        ),
                        target_ref=f"step:{step.step_id}",
                        source_span_ids=list(step.source_span_ids),
                        missing_slot=self._make_missing_slot(
                            slot_name=slot_name,
                            required_for=step.step_id,
                            reason=detail,
                            source_span_ids=list(step.source_span_ids),
                        ),
                        blocks_rendering=blocks_render,
                        blocks_completion=True,
                    )
                )

    # ------------------------------------------------------------------
    # 4. assumed_command_not_renderable
    # ------------------------------------------------------------------

    def _check_assumed_commands(
        self,
        all_steps: list[StepIR],
        valid_handoff_ids: set[str],
    ) -> None:
        """Emit assumed_command_not_renderable for steps without source evidence."""
        for step in all_steps:
            if step.source_span_ids:
                continue
            if (
                step.handoff_id is not None
                and step.handoff_id in valid_handoff_ids
            ):
                continue
            # Legacy path: handoff steps with non-None handoff_id without a
            # validity set are accepted for backward compatibility.
            if step.handoff_id is not None and not valid_handoff_ids:
                continue
            if step.metadata.get("origin") == "compiler_unpack":
                continue

            self._diagnostics.append(
                CompileDiagnostic(
                    diagnostic_id=self._next_diag_id(),
                    kind="assumed_command_not_renderable",
                    severity="warning",
                    message=(
                        f"Step '{step.step_id}' "
                        f"('{step.text[:80]}') has no source evidence "
                        f"and is not compiler scaffolding — it should "
                        f"not be rendered as executable SPL."
                    ),
                    target_ref=f"step:{step.step_id}",
                    source_span_ids=[],
                    missing_slot=self._make_missing_slot(
                        slot_name="source_evidence",
                        required_for=step.step_id,
                        reason=(
                            f"Step '{step.step_id}' has no "
                            f"source-span evidence."
                        ),
                    ),
                    suggested_resolution=(
                        "Provide a source span that describes this "
                        "behavior, or remove the step if the behavior "
                        "is not required."
                    ),
                    blocks_rendering=True,
                    blocks_completion=True,
                )
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_missing_slot(
        slot_name: str,
        required_for: str,
        reason: str,
        source_span_ids: list[str] | None = None,
    ) -> MissingSlot:
        """Build a MissingSlot for a diagnostic."""
        return MissingSlot(
            slot_name=slot_name,
            required_for=required_for,
            reason=reason,
            source_span_ids=source_span_ids or [],
        )

    @staticmethod
    def _merge_resources(
        resources: ResourceRegistryIR | None,
        worker_scoped_resources: WorkerScopedResourceIR | None,
    ) -> ResourceRegistryIR:
        """Merge global + worker-scoped resources into a single view."""
        if resources is None:
            return ResourceRegistryIR()
        if worker_scoped_resources is None:
            return resources
        return ResourceRegistryIR(
            variables=worker_scoped_resources.get_all_variables(),
            apis=worker_scoped_resources.get_all_apis(),
            files=resources.files + [
                f for wr in worker_scoped_resources.worker_resources.values()
                for f in wr.files
            ],
            types=resources.types,
        )

    @staticmethod
    def _child_worker_ids(worker_plan: WorkerPlanIR | None) -> set[str]:
        if worker_plan is None:
            return set()
        return {
            w.worker_id for w in worker_plan.workers
            if w.worker_id != worker_plan.main_worker_id
            and w.boundary_kind != "main_worker"
            and w.boundary_kind != "not_a_worker"
        }

    @staticmethod
    def _call_api_is_declared(
        step: StepIR,
        declared_apis: set[str],
        extra_api_names: set[str],
        api_handoff_refs: dict[str, str],
    ) -> bool:
        if (
            step.handoff_id is not None
            and step.handoff_id in api_handoff_refs
        ):
            return step.integration_ref == api_handoff_refs[step.handoff_id]
        if step.integration_ref in declared_apis:
            return True
        if step.integration_ref in extra_api_names:
            return True
        return False

    @staticmethod
    def _collect_extra_api_names(
        worker_plan: WorkerPlanIR | None,
    ) -> set[str]:
        """Collect API names from accepted api_call-mode handoffs."""
        if worker_plan is None:
            return set()
        return {
            h.api_ref for h in worker_plan.handoffs
            if h.mode == "api_call" and h.api_ref
        }

    @staticmethod
    def _build_api_handoff_refs(
        worker_plan: WorkerPlanIR | None,
    ) -> dict[str, str]:
        """Build handoff_id -> api_ref lookup from api_call-mode handoffs."""
        if worker_plan is None:
            return {}
        return {
            h.handoff_id: h.api_ref for h in worker_plan.handoffs
            if h.mode == "api_call" and h.api_ref
        }

    def _next_diag_id(self) -> str:
        idx = len(self._diagnostics)
        return f"diag_post_norm_{idx:04d}"

    @staticmethod
    def _completion_step_text(output: str) -> str:
        text_by_output = {
            "assumptions_log": "Record assumptions for unresolved items",
            "completion_status": "Set completion status for the normal completion path",
            "source_evidence_set": "Produce the source evidence set for normal completion",
            "draft": "Produce the draft for normal completion",
        }
        return text_by_output.get(output, f"Produce required output {output}")
