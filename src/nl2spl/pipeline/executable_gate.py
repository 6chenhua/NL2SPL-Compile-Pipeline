"""Executable element gate -- filter non-source-backed steps before rendering."""

from __future__ import annotations

from nl2spl.ir.diagnostics import CompileDiagnostic, StepRenderInfo
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.ir.worker_plan_ir import WorkerHandoffIR, WorkerPlanIR

Origin = str  # "source_backed" | "handoff_generated" | "compiler_synthetic" | "assumed"


class ExecutableElementGate:
    """Classify steps by origin and filter non-renderable commands.

    Runs between Stage 10 (assembly) and Stage 11 (rendering).  Only
    source-backed or valid-handoff-backed steps pass through to the
    renderer.  Blocked steps become diagnostics, not executable SPL.
    """

    def apply(
        self,
        worker: WorkerIR,
        worker_plan: WorkerPlanIR | None = None,
    ) -> tuple[WorkerIR, list[StepRenderInfo], list[CompileDiagnostic]]:
        """Filter worker and child-worker steps through the renderability gate.

        Returns:
            (filtered_worker, render_info, diagnostics)
        """
        diags: list[CompileDiagnostic] = []
        infos: list[StepRenderInfo] = []
        diag_counter = [0]  # mutable counter shared across _filter_steps calls

        # Build lookup sets for handoff validation
        handoff_index = self._build_handoff_index(worker_plan)
        child_worker_names = {cw.worker_name for cw in worker.child_workers}
        worker_by_id = self._build_worker_name_index(worker_plan)

        # Classify and filter main-worker steps
        renderable_steps, blocked_infos, blocked_diags = self._filter_steps(
            worker.steps,
            handoff_index,
            child_worker_names,
            worker_by_id,
            diag_counter,
        )
        infos.extend(renderable_steps)
        infos.extend(blocked_infos)
        diags.extend(blocked_diags)

        # Filter child-worker steps
        # Collect pre-gate handler flows BEFORE mutation for both main
        # and child workers.  Exclude pseudo-handlers (Stage 9.5 metadata).
        def _pre_gate_flows(steps: list) -> set[str]:
            return {
                step.flow_ref
                for step in steps
                if step.flow_ref
                and step.metadata.get("pseudo_exception_handler") != "true"
            }

        pre_gate_main = _pre_gate_flows(worker.steps)
        pre_gate_children: dict[str, set[str]] = {}
        filtered_children = []
        for child in worker.child_workers:
            pre_gate_children[child.worker_name] = _pre_gate_flows(child.steps)
            renderable_child, child_blocked, child_diags = self._filter_steps(
                child.steps,
                handoff_index,
                child_worker_names,
                worker_by_id,
                diag_counter,
            )
            infos.extend(renderable_child)
            infos.extend(child_blocked)
            diags.extend(child_diags)
            child.steps[:] = [s for s in child.steps if s.step_id in {
                ri.step_id for ri in renderable_child
            }]
            filtered_children.append(child)

        worker.steps[:] = [s for s in worker.steps if s.step_id in {
            ri.step_id for ri in renderable_steps
        }]
        worker.child_workers = filtered_children

        # Post-gate: re-check exception-flow handler coverage.  An assumed
        # handler step may have been filtered out, leaving the exception
        # flow without a renderable handler.  Only emits missing_handler
        # when a real handler was present before gate (Stage 9.5 already
        # diagnosed flows that never had handlers).
        diags.extend(
            self._post_gate_missing_handler(
                worker, worker_plan, pre_gate_main, pre_gate_children,
            )
        )

        return worker, infos, diags

    # ------------------------------------------------------------------
    # Step classification
    # ------------------------------------------------------------------

    def classify_origin(self, step: StepIR) -> Origin:
        """Classify a step's origin based on source evidence.

        Handoff-backed steps are checked first -- a step that carries both
        source spans and a handoff_id must still be validated against the
        handoff contract, not silently passed as source_backed.
        """
        if step.handoff_id is not None:
            return "handoff_generated"
        if step.source_span_ids:
            return "source_backed"
        if step.metadata.get("origin") == "compiler_unpack":
            return "compiler_synthetic"
        return "assumed"

    # ------------------------------------------------------------------
    # Renderability rules
    # ------------------------------------------------------------------

    def is_renderable(
        self,
        step: StepIR,
        origin: Origin,
        handoff_index: dict[str, WorkerHandoffIR],
        child_worker_names: set[str],
        worker_by_id: dict[str, str],
    ) -> tuple[bool, str | None]:
        """Determine whether a step may be rendered as executable SPL."""
        # 1. source_backed -> renderable, with command-type guard rails
        if origin == "source_backed":
            return self._source_backed_renderable(step)

        # 2. handoff_generated -> renderable only with valid handoff contract
        if origin == "handoff_generated":
            if not step.handoff_id:
                return False, "Handoff step has no handoff_id"
            handoff = handoff_index.get(step.handoff_id)
            if handoff is None:
                return False, (
                    f"Handoff '{step.handoff_id}' not found in worker plan"
                )
            if step.command_type == "INVOKE_WORKER":
                if handoff.mode != "invoke":
                    return False, (
                        f"Handoff '{step.handoff_id}' mode is "
                        f"'{handoff.mode}', expected 'invoke' for "
                        f"INVOKE_WORKER"
                    )
                if not handoff.to_worker:
                    return False, (
                        f"Handoff '{step.handoff_id}' has no to_worker "
                        f"target"
                    )
                expected_target = worker_by_id.get(handoff.to_worker)
                if expected_target is None:
                    return False, (
                        f"Handoff '{step.handoff_id}' to_worker "
                        f"'{handoff.to_worker}' not found in worker plan"
                    )
                if not step.integration_ref:
                    return False, "INVOKE_WORKER has no concrete worker target"
                if step.integration_ref != expected_target:
                    return False, (
                        f"INVOKE_WORKER target '{step.integration_ref}' "
                        f"does not match handoff to_worker target "
                        f"'{expected_target}'"
                    )
                # Guard: target must also still be a declared child worker
                if step.integration_ref not in child_worker_names:
                    return False, (
                        f"INVOKE_WORKER target '{step.integration_ref}' "
                        f"is not a declared child worker"
                    )
                expected_inputs = [
                    b.parent_variable for b in handoff.input_bindings
                ]
                expected_outputs = [
                    b.parent_variable for b in handoff.output_bindings
                ]
                if not expected_inputs or not expected_outputs:
                    return False, "Handoff has no IO bindings"
                if list(step.inputs) != expected_inputs:
                    return False, (
                        f"INVOKE_WORKER inputs {step.inputs} do not "
                        f"match handoff bindings {expected_inputs}"
                    )
                if list(step.outputs) != expected_outputs:
                    return False, (
                        f"INVOKE_WORKER outputs {step.outputs} do not "
                        f"match handoff bindings {expected_outputs}"
                    )
            elif step.command_type == "CALL_API":
                if handoff.mode != "api_call":
                    return False, (
                        f"Handoff '{step.handoff_id}' mode is "
                        f"'{handoff.mode}', expected 'api_call' for "
                        f"CALL_API"
                    )
                if not step.integration_ref:
                    return False, "CALL_API has no named API ref"
                if not handoff.api_ref:
                    return False, (
                        f"Handoff '{step.handoff_id}' has no api_ref; "
                        f"CALL_API requires a concrete API name"
                    )
                if step.integration_ref != handoff.api_ref:
                    return False, (
                        f"CALL_API target '{step.integration_ref}' "
                        f"does not match handoff api_ref "
                        f"'{handoff.api_ref}'"
                    )
            else:
                return False, (
                    f"Handoff step has unexpected command_type "
                    f"'{step.command_type}'"
                )
            return True, None

        # 3. compiler_synthetic -- renderable only for unpack scaffolding
        if origin == "compiler_synthetic":
            if step.metadata.get("origin") == "compiler_unpack":
                return True, None
            return False, "Compiler-synthetic step is not unpack scaffolding"

        # 4. assumed -> NOT renderable
        return False, "Step has no source evidence and is not handoff-backed"

    @staticmethod
    def _source_backed_renderable(step: StepIR) -> tuple[bool, str | None]:
        """Source-backed steps are generally renderable, but specific command
        types carry extra evidence requirements.
        """
        # INVOKE_WORKER must be handoff-backed -- a source-backed step
        # that claims to invoke a worker without a concrete handoff is
        # not renderable.  (Steps with handoff_id are classified as
        # handoff_generated, so reaching here means no handoff.)
        if step.command_type == "INVOKE_WORKER":
            return False, (
                "INVOKE_WORKER requires a valid handoff contract "
                "(handoff_id)"
            )

        # CALL_API must name a concrete API target.
        if step.command_type == "CALL_API":
            if not step.integration_ref:
                return False, (
                    "CALL_API requires a concrete integration_ref "
                    "(API name)"
                )
            return True, None

        # REQUEST_INPUT must have explicit source evidence that the
        # user is being asked for input.
        if step.command_type == "REQUEST_INPUT":
            return True, None  # presence of source_span_ids is sufficient

        # GENERAL_COMMAND and all other types are renderable when
        # source-backed.
        return True, None

    # ------------------------------------------------------------------
    # Post-gate handler check
    # ------------------------------------------------------------------

    def _post_gate_missing_handler(
        self,
        worker: WorkerIR,
        worker_plan: WorkerPlanIR | None = None,
        pre_gate_handler_flows: set[str] | None = None,
        pre_gate_children: dict[str, set[str]] | None = None,
    ) -> list[CompileDiagnostic]:
        """After gate filtering, check exception flows for missing handlers.

        Only emits missing_handler when a handler WAS present before the
        gate but was filtered out.  Exception flows that had no handler
        before the gate are already diagnosed by Stage 9.5.

        Uses the same scoped target_ref format as Stage 9.5 for dedup.
        """
        diags: list[CompileDiagnostic] = []
        renderable_flow_refs = {
            step.flow_ref for step in worker.steps
            if step.flow_ref
        }
        main_worker_id = (
            worker_plan.main_worker_id if worker_plan is not None else None
        )
        for exc in worker.exception_flows:
            if exc.flow_id in renderable_flow_refs:
                continue
            # Only report when a handler was filtered by gate (not when
            # Stage 9.5 already diagnosed the handler was never present).
            if (
                pre_gate_handler_flows is not None
                and exc.flow_id not in pre_gate_handler_flows
            ):
                continue
            diags.append(
                    CompileDiagnostic(
                        diagnostic_id=f"diag_gate_mh_{len(diags):04d}",
                        kind="missing_handler",
                        severity="warning",
                        message=(
                            f"Exception flow '{exc.flow_id}' "
                            f"('{exc.condition_text[:80]}') has no "
                            f"renderable handler step after the "
                            f"executable-element gate."
                        ),
                        target_ref=(
                            f"worker:{main_worker_id}.exception_flow:{exc.flow_id}"
                            if main_worker_id
                            else f"exception_flow:{exc.flow_id}"
                        ),
                        source_span_ids=list(getattr(exc, "spans", [])),
                        blocks_rendering=False,
                        blocks_completion=True,
                    )
                )
        # Check child workers with per-child pre-gate flows
        for child in worker.child_workers:
            child_pre_gate = (
                pre_gate_children.get(child.worker_name, set())
                if pre_gate_children is not None
                else set()
            )
            renderable_child_refs = {
                step.flow_ref for step in child.steps
                if step.flow_ref
            }
            for exc in child.exception_flows:
                if exc.flow_id in renderable_child_refs:
                    continue
                # Skip if Stage 9.5 already diagnosed (no pre-gate handler).
                if (
                    child_pre_gate is not None
                    and exc.flow_id not in child_pre_gate
                ):
                    continue
                diags.append(
                        CompileDiagnostic(
                            diagnostic_id=f"diag_gate_mh_{len(diags):04d}",
                            kind="missing_handler",
                            severity="warning",
                            message=(
                                f"Child worker '{child.worker_name}' "
                                f"exception flow '{exc.flow_id}' "
                                f"('{exc.condition_text[:80]}') has no "
                                f"renderable handler step after gate."
                            ),
                            target_ref=(
                                f"worker:{child.worker_name}."
                                f"exception_flow:{exc.flow_id}"
                            ),
                            source_span_ids=[],
                            blocks_rendering=False,
                            blocks_completion=True,
                        )
                    )
        return diags

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _filter_steps(
        self,
        steps: list[StepIR],
        handoff_index: dict[str, WorkerHandoffIR],
        child_worker_names: set[str],
        worker_by_id: dict[str, str],
        diag_counter: list[int],
    ) -> tuple[
        list[StepRenderInfo],  # renderable
        list[StepRenderInfo],  # blocked
        list[CompileDiagnostic],
    ]:
        renderable_infos: list[StepRenderInfo] = []
        blocked_infos: list[StepRenderInfo] = []
        diags: list[CompileDiagnostic] = []

        for step in steps:
            origin = self.classify_origin(step)
            ok, reason = self.is_renderable(
                step, origin, handoff_index, child_worker_names,
                worker_by_id,
            )
            info = StepRenderInfo(
                step_id=step.step_id,
                origin=origin,
                renderable=ok,
                render_block_reason=reason if not ok else None,
            )
            if ok:
                renderable_infos.append(info)
            else:
                blocked_infos.append(info)
                diag_id = f"diag_gate_{diag_counter[0]:04d}"
                diag_counter[0] += 1
                diags.append(
                    CompileDiagnostic(
                        diagnostic_id=diag_id,
                        kind="assumed_command_not_renderable",
                        severity="warning",
                        message=(
                            f"Step '{step.step_id}' ({origin}, "
                            f"{step.command_type}) blocked from rendering: "
                            f"{reason}"
                        ),
                        target_ref=f"step:{step.step_id}",
                        source_span_ids=list(step.source_span_ids),
                        suggested_resolution=(
                            "Provide source evidence for this step, or "
                            "remove it from the workflow."
                        ),
                        blocks_rendering=True,
                        blocks_completion=True,
                    )
                )

        return renderable_infos, blocked_infos, diags

    @staticmethod
    def _build_handoff_index(
        worker_plan: WorkerPlanIR | None,
    ) -> dict[str, WorkerHandoffIR]:
        if worker_plan is None:
            return {}
        return {h.handoff_id: h for h in worker_plan.handoffs}

    @staticmethod
    def _build_worker_name_index(
        worker_plan: WorkerPlanIR | None,
    ) -> dict[str, str]:
        """Build worker_id -> worker_name mapping from worker plan."""
        if worker_plan is None:
            return {}
        return {w.worker_id: w.worker_name for w in worker_plan.workers}
