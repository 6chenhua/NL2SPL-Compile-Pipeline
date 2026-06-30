"""Materialization service layer."""

from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from typing import Any

from nl2spl.compiler.spl_editing.core.model import RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent
from nl2spl.compiler.spl_editing.materialization.dependency_closure import (
    validate_dependency_closure,
)
from nl2spl.compiler.spl_editing.materialization.errors import (
    DependencyClosureValidationError,
    MaterializationConsistencyError,
)
from nl2spl.compiler.spl_editing.materialization.id_allocator import IdAllocator
from nl2spl.compiler.spl_editing.materialization.model import (
    MaterializationInput,
    MaterializationRequest,
    MaterializationResult,
)
from nl2spl.compiler.spl_editing.materialization.registry import MaterializationPlanRegistry
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRefSet


class RepairMaterializationService:
    """Manages validation, consistency checks, and materialization execution."""

    def __init__(self, registry: MaterializationPlanRegistry) -> None:
        self.registry = registry

    def materialize(self, request: MaterializationRequest) -> MaterializationResult:
        """Verify request consistency, execute dependency checks, and run the materializer."""
        # 1. Look up plan and materializer
        plan = self.registry.get(request.intent.materialization_plan_id)
        materializer = self.registry.get_materializer(request.intent.materialization_plan_id)

        # 2. Tri-party plan ID consistency check
        if request.catalog_entry.materialization_plan_id != request.intent.materialization_plan_id:
            raise MaterializationConsistencyError(
                f"Plan ID mismatch: catalog expects '{request.catalog_entry.materialization_plan_id}' "  # noqa: E501
                f"but intent has '{request.intent.materialization_plan_id}'."
            )
        if plan.materialization_plan_id != request.intent.materialization_plan_id:
            raise MaterializationConsistencyError(
                f"Plan ID mismatch: registry has '{plan.materialization_plan_id}' "
                f"but intent has '{request.intent.materialization_plan_id}'."
            )

        # 2b. ID relationship validation (intent, issue, evidence packet, refset, snapshot)
        if request.intent.issue_id != request.issue.issue_id:
            raise MaterializationConsistencyError(
                f"Issue ID mismatch: intent has '{request.intent.issue_id}' but issue has '{request.issue.issue_id}'."  # noqa: E501
            )
        if request.evidence_packet.confirmed_intent_id != request.intent.intent_id:
            raise MaterializationConsistencyError(
                f"Intent ID mismatch: evidence packet confirms '{request.evidence_packet.confirmed_intent_id}' "  # noqa: E501
                f"but intent has '{request.intent.intent_id}'."
            )
        if request.refset.issue_id != request.issue.issue_id:
            raise MaterializationConsistencyError(
                f"Issue ID mismatch: refset has '{request.refset.issue_id}' but issue has '{request.issue.issue_id}'."  # noqa: E501
            )
        if request.refset.snapshot_id != request.snapshot.snapshot_id:
            raise MaterializationConsistencyError(
                f"Snapshot ID mismatch: refset has '{request.refset.snapshot_id}' but snapshot has '{request.snapshot.snapshot_id}'."  # noqa: E501
            )
        if request.evidence_packet.related_diagnostic_id != request.issue.primary_diagnostic_id:
            raise MaterializationConsistencyError(
                f"Diagnostic ID mismatch: evidence packet related diagnostic is '{request.evidence_packet.related_diagnostic_id}' "  # noqa: E501
                f"but issue primary diagnostic is '{request.issue.primary_diagnostic_id}'."
            )

        # 2c. Target binding validation. RepairTarget.target_ref and selectable
        # ref IDs intentionally use different namespaces, so compare their
        # structured construct identity instead of serialized strings.
        if request.target.target_kind != plan.target_construct_type:
            raise MaterializationConsistencyError(
                f"Target kind mismatch: target has '{request.target.target_kind}' "
                f"but plan targets '{plan.target_construct_type}'."
            )
        target_ref_obj = request.refset.get_ref(request.intent.target_ref_id)
        if target_ref_obj is None:
            raise MaterializationConsistencyError(
                f"Target ref '{request.intent.target_ref_id}' not found in refset."
            )
        expected_target_role = "target_output"
        if plan.target_construct_type == "EXCEPTION_FLOW":
            expected_target_role = "target_exception_flow"
        elif plan.target_construct_type == "WORKER_PROMOTION":
            expected_target_role = "target_worker"
        if target_ref_obj.ref_role != expected_target_role:
            raise MaterializationConsistencyError(
                f"Target ref '{request.intent.target_ref_id}' has role '{target_ref_obj.ref_role}' "
                f"instead of expected '{expected_target_role}'."
            )
        if request.target.worker_id != target_ref_obj.worker_id:
            raise MaterializationConsistencyError(
                f"Target worker mismatch: target has '{request.target.worker_id}' "
                f"but target ref has '{target_ref_obj.worker_id}'."
            )
        if not request.target.canonical_name:
            raise MaterializationConsistencyError("Repair target canonical_name is missing.")
        if request.target.canonical_name != target_ref_obj.canonical_name:
            raise MaterializationConsistencyError(
                f"Target canonical name mismatch: target has '{request.target.canonical_name}' "
                f"but target ref has '{target_ref_obj.canonical_name}'."
            )

        # 2d. Reference lineage reconciliation
        intent_selected = request.intent.selected_ref_ids
        evidence_confirmed = request.evidence_packet.confirmed_selected_ref_ids
        resolved_ids = tuple(resolved.ref.ref_id for resolved in request.resolved_refs)
        if len(set(intent_selected)) != len(intent_selected):
            raise MaterializationConsistencyError("Intent selected_ref_ids contains duplicates.")
        if len(set(evidence_confirmed)) != len(evidence_confirmed):
            raise MaterializationConsistencyError(
                "Evidence packet confirmed_selected_ref_ids contains duplicates."
            )
        if len(set(resolved_ids)) != len(resolved_ids):
            raise MaterializationConsistencyError("Resolved refs contains duplicate ref IDs.")
        if intent_selected != evidence_confirmed:
            raise MaterializationConsistencyError(
                f"Ref lineage mismatch: intent selected_ref_ids {intent_selected} does not match "
                f"evidence packet confirmed_selected_ref_ids {evidence_confirmed}."
            )
        if intent_selected != resolved_ids:
            raise MaterializationConsistencyError(
                f"Ref lineage mismatch: intent selected_ref_ids {intent_selected} does not match "
                f"resolved_refs IDs {resolved_ids}."
            )
        for resolved in request.resolved_refs:
            canonical_ref = request.refset.get_ref(resolved.ref.ref_id)
            if canonical_ref is None:
                raise MaterializationConsistencyError(
                    f"Resolved ref '{resolved.ref.ref_id}' is not present in the refset."
                )
            if resolved.ref != canonical_ref:
                raise MaterializationConsistencyError(
                    f"Resolved ref '{resolved.ref.ref_id}' does not match the canonical refset entry."  # noqa: E501
                )
            if canonical_ref.ref_role != "selectable_input":
                raise MaterializationConsistencyError(
                    f"Resolved ref '{resolved.ref.ref_id}' has role '{canonical_ref.ref_role}', "
                    "expected 'selectable_input'."
                )
            if resolved.resolved_role != "selectable_input":
                raise MaterializationConsistencyError(
                    f"Resolved ref '{resolved.ref.ref_id}' resolved as '{resolved.resolved_role}', "
                    "expected 'selectable_input'."
                )
            if not resolved.scope_matched:
                raise MaterializationConsistencyError(
                    f"Resolved ref '{resolved.ref.ref_id}' did not match the target worker scope."
                )
            if (
                request.target.worker_id is not None
                and canonical_ref.worker_id is not None
                and canonical_ref.worker_id != request.target.worker_id
            ):
                raise MaterializationConsistencyError(
                    f"Resolved ref '{resolved.ref.ref_id}' belongs to worker "
                    f"'{canonical_ref.worker_id}', expected '{request.target.worker_id}'."
                )

        # 3. Validation metadata consistency
        if request.intent.patch_type != plan.patch_type:
            worker_promotion_plan = plan.target_construct_type == "WORKER_PROMOTION"
            if not (
                worker_promotion_plan
                and request.intent.patch_type in request.catalog_entry.supported_patch_types
            ):
                raise MaterializationConsistencyError(
                    f"Patch type mismatch: intent expects '{request.intent.patch_type}' but plan has '{plan.patch_type}'."  # noqa: E501
                )
        if request.catalog_entry.construct_type != request.intent.target_construct_type:
            raise MaterializationConsistencyError(
                f"Construct type mismatch: catalog has '{request.catalog_entry.construct_type}' "
                f"but intent has '{request.intent.target_construct_type}'."
            )
        if request.intent.target_construct_type != plan.target_construct_type:
            raise MaterializationConsistencyError(
                f"Construct type mismatch: intent has '{request.intent.target_construct_type}' "
                f"but plan has '{plan.target_construct_type}'."
            )
        if request.catalog_entry.slot_name != request.intent.target_slot_name:
            raise MaterializationConsistencyError(
                f"Slot name mismatch: catalog has '{request.catalog_entry.slot_name}' "
                f"but intent has '{request.intent.target_slot_name}'."
            )
        if request.intent.target_slot_name != plan.target_slot_name:
            worker_promotion_plan = plan.target_construct_type == "WORKER_PROMOTION"
            if not (
                worker_promotion_plan and request.intent.target_slot_name.startswith("promotion_")
            ):
                raise MaterializationConsistencyError(
                    f"Slot name mismatch: intent has '{request.intent.target_slot_name}' but plan has '{plan.target_slot_name}'."  # noqa: E501
                )
        if request.catalog_entry.stage_authority != plan.stage_authority:
            raise MaterializationConsistencyError(
                f"Authority mismatch: catalog has '{request.catalog_entry.stage_authority}' "
                f"but plan has '{plan.stage_authority}'."
            )
        if request.catalog_entry.default_verification_lane != plan.verification_lane:
            raise MaterializationConsistencyError(
                f"Verification lane mismatch: catalog has '{request.catalog_entry.default_verification_lane}' "  # noqa: E501
                f"but plan has '{plan.verification_lane}'."
            )
        if set(plan.editable_artifacts) != set(request.catalog_entry.editable_artifacts):
            raise MaterializationConsistencyError(
                f"Editable artifacts mismatch: plan has {plan.editable_artifacts} "
                f"but catalog entry has {request.catalog_entry.editable_artifacts}."
            )

        # 4. Policy and refset availability validation
        if (
            not request.catalog_entry.selectable_ref_policy_id
            or not request.catalog_entry.selectable_ref_policy_id.strip()
        ):
            raise MaterializationConsistencyError(
                "Catalog entry selectable_ref_policy_id is missing or empty."
            )
        if not request.refset.is_available:
            raise MaterializationConsistencyError("Refset is marked as unavailable.")
        if request.catalog_entry.selectable_ref_policy_id != request.refset.policy_id:
            raise MaterializationConsistencyError(
                f"Policy mismatch: catalog specifies '{request.catalog_entry.selectable_ref_policy_id}' "  # noqa: E501
                f"but refset has '{request.refset.policy_id}'."
            )

        # 5. Stateful ID Allocator creation and dependency validation
        id_allocator = IdAllocator.from_snapshot(
            request.snapshot, plan.dependency_closure.required_id_allocator_namespaces
        )
        val_res = validate_dependency_closure(
            plan,
            request.snapshot,
            request.refset,
            request.target,
            id_allocator,
            resolved_refs=request.resolved_refs,
            target_ref=target_ref_obj,
        )
        if not val_res.is_valid:
            raise DependencyClosureValidationError(
                f"Dependency closure validation failed: {', '.join(val_res.errors)}"
            )

        # 6. Execute materializer
        input_data = MaterializationInput(
            snapshot=request.snapshot,
            issue=request.issue,
            target=request.target,
            catalog_entry=request.catalog_entry,
            intent=request.intent,
            refset=request.refset,
            resolved_refs=request.resolved_refs,
            evidence_packet=request.evidence_packet,
            plan=plan,
            id_allocator=id_allocator,
        )

        result = materializer.materialize(input_data)

        # 7. Strict return consistency validation
        if result.materialization_plan_id != plan.materialization_plan_id:
            raise MaterializationConsistencyError(
                f"Materializer returned invalid plan ID: '{result.materialization_plan_id}' (expected '{plan.materialization_plan_id}')."  # noqa: E501
            )
        if result.materializer_id != plan.materializer_id:
            raise MaterializationConsistencyError(
                f"Materializer returned invalid materializer ID: '{result.materializer_id}' (expected '{plan.materializer_id}')."  # noqa: E501
            )
        if result.materialization_authority != plan.stage_authority:
            raise MaterializationConsistencyError(
                f"Materializer returned invalid stage authority: '{result.materialization_authority}' (expected '{plan.stage_authority}')."  # noqa: E501
            )
        if result.evidence_packet_id != request.evidence_packet.evidence_packet_id:
            raise MaterializationConsistencyError(
                f"Materializer returned invalid evidence packet ID: '{result.evidence_packet_id}' (expected '{request.evidence_packet.evidence_packet_id}')."  # noqa: E501
            )

        # 7b. Consumed refs subset check
        consumed_ids = set(result.consumed_selected_ref_ids)
        if not consumed_ids.issubset(set(resolved_ids)):
            raise MaterializationConsistencyError(
                f"Consumed selected ref IDs {consumed_ids} must be a subset of resolved ref IDs {resolved_ids}."  # noqa: E501
            )

        return replace(
            result,
            dependency_validation_metadata=dict(val_res.validation_metadata),
        )

    def dry_run_materialize(
        self,
        intent: ConstructRepairIntent,
        target: RepairTarget,
        refset: SelectableRefSet,
        snapshot: ArtifactSnapshot,
        closure_plan: Any,
        directive: Any,
    ) -> str:
        """Execute the repair stage-slice chain in dry-run mode and render its result."""
        plan = self.registry.get(intent.materialization_plan_id)
        id_allocator = IdAllocator.from_snapshot(
            snapshot,
            plan.dependency_closure.required_id_allocator_namespaces,
        )
        stage_slices = import_module("nl2spl.compiler.spl_editing.stage_slices")
        selected_ref_ids = tuple(intent.selected_ref_ids)
        results: list[Any] = []

        def _input(slice_obj, authority: str, policy_id: str, allowed: tuple[str, ...]):
            return stage_slices.StageSliceInput(
                slice_id=slice_obj.slice_id,
                stage_authority=authority,
                snapshot=snapshot,
                target=target,
                refset=refset,
                directive=directive,
                intent=intent,
                dependency_closure=plan.dependency_closure,
                stage_policy=stage_slices.StagePolicy(
                    policy_id=policy_id,
                    stage_authority=authority,
                    allowed_typed_plan_kinds=allowed,
                    generation_mode="none",
                ),
                selected_ref_ids=selected_ref_ids,
                id_allocator=id_allocator,
                upstream_stage_results=tuple(results),
                dry_run=True,
            )

        if intent.patch_type == "AddExceptionHandlerStep":
            stage5 = stage_slices.Stage5ExceptionHandlerBlockRepairSlice()
            results.append(
                stage5.execute(
                    _input(
                        stage5,
                        "stage5.worker_block_plan",
                        "exception_handler.block_shape.v1",
                        ("BlockShapePlan",),
                    )
                )
            )
            stage7 = stage_slices.Stage7ExceptionHandlerCommandRepairSlice()
            results.append(
                stage7.execute(
                    _input(
                        stage7,
                        "stage7.worker_step_plan",
                        "exception_handler.command_intent.v1",
                        ("CommandIntentPlan",),
                    )
                )
            )
        elif intent.patch_type == "InsertProducerStep":
            stage7 = stage_slices.Stage7RequiredOutputProducerCommandRepairSlice()
            results.append(
                stage7.execute(
                    _input(
                        stage7,
                        "stage7.worker_step_plan",
                        "required_output.producer_command.v1",
                        ("CommandIntentPlan",),
                    )
                )
            )
        elif intent.patch_type == "CreateWorkerHandoffContract":
            stage35 = stage_slices.Stage35WorkerHandoffContractRepairSlice()
            results.append(
                stage35.execute(
                    _input(
                        stage35,
                        "stage3_5.worker_boundary",
                        "worker_delegation.handoff_contract.v1",
                        ("HandoffContractPlan",),
                    )
                )
            )
            stage7 = stage_slices.Stage7WorkerInvokeCommandRepairSlice()
            results.append(
                stage7.execute(
                    _input(
                        stage7,
                        "stage7.worker_step_plan",
                        "worker_delegation.invoke_worker_command.v1",
                        ("InvokeWorkerPlan",),
                    )
                )
            )
        elif intent.patch_type in {
            "ConvertDelegationIntentToMainFlowStep",
            "ConvertDelegationIntentToRequestInput",
        }:
            if hasattr(intent.payload, "option_id"):
                if intent.payload.option_id != "keep_in_main_flow":
                    raise DependencyClosureValidationError("Invalid main-flow directive option")
                action_text = intent.payload.delegated_responsibility
                return "\n".join(
                    (
                        "[MAIN_FLOW]",
                        "  " + self._command_line("GENERAL_COMMAND", action_text),
                        "[END_MAIN_FLOW]",
                    )
                )
            stage7 = stage_slices.Stage7WorkerDelegationResolutionCommandRepairSlice()
            results.append(
                stage7.execute(
                    _input(
                        stage7,
                        "stage7.worker_step_plan",
                        "worker_delegation.resolution_command.v1",
                        ("CommandIntentPlan",),
                    )
                )
            )
        elif intent.patch_type == "DefineChildWorkerClosure":
            directive_payload = intent.payload
            if not hasattr(directive_payload, "admitted_outputs"):
                raise DependencyClosureValidationError(
                    "DefineChildWorkerClosure preview requires normalized directive"
                )
            return self._render_define_child_preview(directive_payload)
        else:
            raise DependencyClosureValidationError(
                f"No dry-run stage-slice chain for patch type '{intent.patch_type}'."
            )

        return self._render_dry_run_preview(intent, target, tuple(results))

    @staticmethod
    def _render_define_child_preview(directive: Any) -> str:
        inputs = tuple(item.ref.canonical_name for item in directive.selected_input_refs)
        outputs = tuple(item.canonical_name for item in directive.admitted_outputs)
        invoke_outputs = tuple(
            item.parent_ref.ref.canonical_name
            if item.parent_ref is not None
            else item.parent_temporary_name
            for item in directive.result_usage
        )
        command = RepairMaterializationService._command_line(
            "GENERAL_COMMAND",
            directive.delegated_responsibility,
            inputs=inputs,
            outputs=outputs,
        )
        invoke = RepairMaterializationService._command_line(
            "INVOKE_WORKER",
            "Child worker",
            inputs=inputs,
            outputs=invoke_outputs,
            integration_ref="ChildWorker",
        )
        return "\n".join(
            (
                "[WORKER: ChildWorker]",
                f"  PURPOSE {directive.delegated_responsibility}",
                "  [MAIN_FLOW]",
                "    [SEQUENTIAL_BLOCK]",
                f"      {command}",
                "    [END_SEQUENTIAL_BLOCK]",
                "  [END_MAIN_FLOW]",
                "[END_WORKER]",
                "[MAIN_FLOW]",
                f"  {invoke}",
                "[END_MAIN_FLOW]",
            )
        )

    @staticmethod
    def _render_dry_run_preview(
        intent: ConstructRepairIntent,
        target: RepairTarget,
        stage_results: tuple[Any, ...],
    ) -> str:
        """Render the user-facing construct preview for confirmation.

        Stage-slice traces contain backend audit details. The default preview is
        deliberately limited to the result the user is being asked to confirm.
        """
        payload = intent.payload
        if intent.patch_type == "AddExceptionHandlerStep":
            command_text = RepairMaterializationService._first_payload_text(
                payload, ("handler_goal",), default="Handle the exception"
            )
            command_family = RepairMaterializationService._last_command_family(
                stage_results, default="GENERAL_COMMAND"
            )
            flow_label = RepairMaterializationService._exception_flow_label(target)
            header = f"[EXCEPTION_FLOW: {flow_label}]" if flow_label else "[EXCEPTION_FLOW]"
            command_line = RepairMaterializationService._command_line(
                command_family, command_text
            )
            return "\n".join(
                (
                    header,
                    "  [SEQUENTIAL_BLOCK]",
                    f"    {command_line}",
                    "  [END_SEQUENTIAL_BLOCK]",
                    "[END_EXCEPTION_FLOW]",
                )
            )

        if intent.patch_type == "InsertProducerStep":
            command_text = RepairMaterializationService._first_payload_text(
                payload, ("producer_goal",), default="Produce required output"
            )
            output_name = target.canonical_name or "required_output"
            selected_inputs = RepairMaterializationService._selected_ref_names(
                stage_results
            )
            return "\n".join(
                (
                    "[SEQUENTIAL_BLOCK]",
                    "  "
                    + RepairMaterializationService._command_line(
                        "GENERAL_COMMAND",
                        command_text,
                        inputs=selected_inputs,
                        outputs=(output_name,),
                    ),
                    "[END_SEQUENTIAL_BLOCK]",
                )
            )

        if intent.patch_type == "CreateWorkerHandoffContract":
            child_worker = (
                getattr(payload, "child_worker_id", None)
                or target.canonical_name
                or "worker"
            )
            parent_inputs = tuple(
                parent for parent, _child in getattr(payload, "input_bindings", ())
            )
            parent_outputs = tuple(
                parent for _child, parent in getattr(payload, "output_bindings", ())
            )
            return "\n".join(
                (
                    "[MAIN_FLOW]",
                    "  "
                    + RepairMaterializationService._command_line(
                        "INVOKE_WORKER",
                        f"Invoke worker: {child_worker}",
                        inputs=parent_inputs,
                        outputs=parent_outputs,
                        integration_ref=str(child_worker),
                    ),
                    "[END_MAIN_FLOW]",
                )
            )

        if intent.patch_type == "ConvertDelegationIntentToMainFlowStep":
            action_text = RepairMaterializationService._first_payload_text(
                payload, ("action_text",), default="Complete delegated work in the main flow"
            )
            outputs = tuple(getattr(payload, "outputs", ()) or ())
            return "\n".join(
                (
                    "[MAIN_FLOW]",
                    "  "
                    + RepairMaterializationService._command_line(
                        "GENERAL_COMMAND", action_text, outputs=outputs
                    ),
                    "[END_MAIN_FLOW]",
                )
            )

        if intent.patch_type == "ConvertDelegationIntentToRequestInput":
            prompt_text = RepairMaterializationService._first_payload_text(
                payload, ("prompt_text",), default="Ask the user for the missing information"
            )
            value_target = getattr(payload, "value_target", None) or "user_response"
            return "\n".join(
                (
                    "[MAIN_FLOW]",
                    "  "
                    + RepairMaterializationService._command_line(
                        "REQUEST_INPUT", prompt_text, outputs=(str(value_target),)
                    ),
                    "[END_MAIN_FLOW]",
                )
            )

        return RepairMaterializationService._first_payload_text(
            payload, ("handler_goal", "producer_goal", "action_text", "prompt_text"),
            default="Repair preview unavailable.",
        )

    @staticmethod
    def _first_payload_text(payload: Any, field_names: tuple[str, ...], *, default: str) -> str:
        for field_name in field_names:
            value = getattr(payload, field_name, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return default

    @staticmethod
    def _last_command_family(stage_results: tuple[Any, ...], *, default: str) -> str:
        for result in reversed(stage_results):
            family = getattr(result, "trace", {}).get("command_family")
            if isinstance(family, str) and family.strip():
                return family.strip()
        return default

    @staticmethod
    def _exception_flow_label(target: RepairTarget) -> str:
        label = target.canonical_name or ""
        normalized = label.casefold()
        generated_prefixes = ("exc_", "exc-adapter", "exc_adapter", "exception_flow:")
        if not label or normalized.startswith(generated_prefixes):
            return ""
        return label

    @staticmethod
    def _selected_ref_names(stage_results: tuple[Any, ...]) -> tuple[str, ...]:
        for result in reversed(stage_results):
            names = getattr(result, "trace", {}).get("selected_ref_canonical_names")
            if isinstance(names, (list, tuple)):
                return tuple(str(name) for name in names if str(name).strip())
        return ()

    @staticmethod
    def _command_line(
        command_family: str,
        text: str,
        *,
        inputs: tuple[str, ...] = (),
        outputs: tuple[str, ...] = (),
        integration_ref: str | None = None,
    ) -> str:
        clean_text = " ".join(text.split())
        if command_family == "REQUEST_INPUT":
            output = outputs[0] if outputs else "user_response"
            return f"COMMAND-X [INPUT DISPLAY {clean_text} VALUE {output}:text SET]"
        if command_family == "DISPLAY_MESSAGE":
            return f"COMMAND-X [DISPLAY {clean_text}]"
        if command_family == "INVOKE_WORKER":
            worker = integration_ref or clean_text
            parts = [f"COMMAND-X [INVOKE_WORKER {worker}"]
            if inputs:
                parts.append("WITH " + ", ".join(inputs))
            if outputs:
                parts.append("RESULT " + ", ".join(outputs) + " SET")
            return " ".join(parts) + "]"
        parts = [f"COMMAND-X [COMMAND {clean_text}"]
        if inputs:
            parts.append("USING " + ", ".join(inputs))
        if outputs:
            parts.append("RESULT " + ", ".join(f"{name}:text" for name in outputs) + " SET")
        return " ".join(parts) + "]"
