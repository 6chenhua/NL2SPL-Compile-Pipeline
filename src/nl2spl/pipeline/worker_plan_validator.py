"""WorkerPlanValidator - Stage 3.6 worker graph validation helpers."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import get_args

from nl2spl.ir.worker_contract_status import (
    binding_side_satisfied,
    contract_side_satisfied,
    derive_handoff_materialization_status,
)
from nl2spl.ir.worker_plan_ir import (
    BoundaryKind,
    Risk,
    Signal,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)


@dataclass
class WorkerPlanValidationResult:
    """Validation result for WorkerPlanIR."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class WorkerPlanValidator:
    """Validate WorkerPlanIR graph, ownership, handoffs, and candidate consistency."""

    _SPL_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    _BOUNDARY_KINDS = set(get_args(BoundaryKind))
    _SIGNALS = set(get_args(Signal))
    _RISKS = set(get_args(Risk))
    _WORKER_KINDS = {"main", "child", "api_adapter"}
    _DECISIONS = {
        "extract_child_worker",
        "keep_in_main_worker",
        "compile_as_call_api",
        "compile_as_constraint",
        "compile_as_exception_flow",
        "compile_as_alternative_flow",
        "needs_repair_or_warning",
    }
    _BOUNDARY_STRENGTHS = {"strong", "moderate", "weak"}
    _HANDOFF_MODES = {"invoke", "api_call"}
    _HANDOFF_ORDERINGS = {"before", "after", "conditional", "loop_body"}
    _CONTRACT_SOURCES = {"input", "output", "state", "derived"}
    _MERGE_STRATEGIES = {"set", "append", "merge_struct", "ignore_if_empty"}
    _FLOW_KINDS = {"main", "alternative", "exception"}
    _BLOCK_HINTS = {"sequential", "if", "for", "while", "unknown"}
    _FAILURE_POLICIES = {
        "propagate_exception",
        "ask_user",
        "continue_with_assumption",
        "block_finalization",
        "return_empty_result",
        "custom",
    }
    _OUTER_CONTROLS = {"SEQUENTIAL", "IF", "FOR", "WHILE", "unknown"}
    _INNER_CONTROLS = {"IF", "FOR", "WHILE", "multiple", "unknown"}
    _DISCOVERY_PHASES = {"predicted", "confirmed"}
    _SEVERITIES = {"info", "warning", "error"}
    _CONTRACT_SIDE_STATUSES = {"unknown", "known_present", "known_empty"}
    _BINDING_SIDE_STATUSES = {"unknown", "known_present", "known_empty"}
    _HANDOFF_MATERIALIZATION_STATUSES = {
        "complete", "partial_contract_unknown",
        "confirmed_empty_contract", "blocked",
    }
    _SUGGESTED_REPAIRS = {
        "split_blocks",
        "merge_condition",
        "guard_variable",
        "extract_child_worker",
        "compress_to_command",
        "raise_validation_error",
    }

    def validate(
        self,
        plan: WorkerPlanIR,
        known_span_ids: Iterable[str] | None = None,
    ) -> WorkerPlanValidationResult:
        """Validate a worker plan without throwing.

        Implements the second layer (Layer-2) of the two-layer validation
        pipeline. While the first layer (``_validate_planner_decisions`` in
        ``WorkerBoundaryPlanner``) checks *semantic* consistency (e.g.
        accepted candidates must not have rejection reasons), this layer
        checks *structural* and *graph* consistency of the entire plan.

        Layer-2  verification categories (9 in total):
        1. **Enum field validation** -- all typed fields (kind, mode,
           ordering, ...) must belong to their pre-defined allowed sets.
        2. **Main worker existence & uniqueness** -- exactly one ``main``
           worker, referenced by ``main_worker_id``, and it must be a main.
        3. **ID uniqueness** -- no duplicate ``worker_id`` or
           ``handoff_id`` values.
        4. **Worker name safety** -- ``worker_name`` must be a valid
           SPL-safe identifier (``^[A-Za-z_][A-Za-z0-9_]*$``).
        5. **Handoff mode consistency** -- ``invoke`` requires a
           ``to_worker`` (non-main) and no ``api_ref``; ``api_call``
           requires an ``api_ref`` and no ``to_worker``.
        6. **Non-main worker reachability** -- every child or adapter
           must be reachable via at least one ``invoke`` handoff.
        7. **Contract completeness** -- non-main workers must declare
           both input and output contracts; handoff bindings must
           reference fields that actually exist in those contracts.
        8. **Span ownership** -- every span can be owned by at most one
           worker, and all referenced span ids must be known.
        9. **Decision consistency** -- accepted decisions must map to
           exactly one non-main worker with an invoke handoff that has
           bindings; rejected candidates must not appear as real workers
           or be referenced by any handoff.

        Args:
            plan: Worker plan to validate.
            known_span_ids: Optional complete set of resolved span ids.

        Returns:
            Validation result containing errors and warnings.
        """
        errors: list[str] = []
        warnings = list(plan.warnings)
        span_ids = set(known_span_ids) if known_span_ids is not None else None

        worker_ids = [worker.worker_id for worker in plan.workers]
        worker_id_set = set(worker_ids)
        worker_by_id = {worker.worker_id: worker for worker in plan.workers}

        errors.extend(self._validate_enum_fields(plan))
        errors.extend(self._validate_main_worker(plan))
        errors.extend(self._validate_unique_worker_ids(worker_ids))
        errors.extend(self._validate_unique_handoff_ids(plan.handoffs))
        errors.extend(self._validate_worker_names(plan.workers))
        errors.extend(
            self._validate_handoff_modes(
                plan.handoffs,
                worker_id_set,
                plan.main_worker_id,
            )
        )
        errors.extend(
            self._validate_non_main_handoffs(
                plan.workers, plan.handoffs, warnings=warnings,
            )
        )
        errors.extend(
            self._validate_child_contracts(plan.workers, warnings=warnings)
        )
        errors.extend(
            self._validate_handoff_bindings(
                plan.handoffs, worker_by_id, warnings=warnings,
            )
        )
        errors.extend(self._validate_span_ownership(plan.workers, span_ids))
        errors.extend(self._validate_status_list_consistency(plan))
        errors.extend(
            self._validate_accepted_child_decisions(plan, warnings=warnings)
        )
        errors.extend(self._validate_rejected_candidates(plan))

        return WorkerPlanValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
        )

    def _validate_enum_fields(self, plan: WorkerPlanIR) -> list[str]:
        errors: list[str] = []

        for worker in plan.workers:
            errors.extend(
                self._validate_value(
                    "Worker.kind",
                    worker.worker_id,
                    worker.kind,
                    self._WORKER_KINDS,
                )
            )
            errors.extend(
                self._validate_value(
                    "Worker.boundary_kind",
                    worker.worker_id,
                    worker.boundary_kind,
                    self._BOUNDARY_KINDS,
                )
            )
            for contract_field in [*worker.input_contract, *worker.output_contract]:
                errors.extend(
                    self._validate_value(
                        "ContractField.source",
                        f"{worker.worker_id}.{contract_field.name}",
                        contract_field.source,
                        self._CONTRACT_SOURCES,
                    )
                )
            for signal in worker.decision_evidence:
                errors.extend(
                    self._validate_value(
                        "Worker.decision_evidence",
                        worker.worker_id,
                        signal,
                        self._SIGNALS,
                    )
                )
            errors.extend(
                self._validate_value(
                    "Worker.input_contract_status",
                    worker.worker_id,
                    getattr(worker, "input_contract_status", "unknown"),
                    self._CONTRACT_SIDE_STATUSES,
                )
            )
            errors.extend(
                self._validate_value(
                    "Worker.output_contract_status",
                    worker.worker_id,
                    getattr(worker, "output_contract_status", "unknown"),
                    self._CONTRACT_SIDE_STATUSES,
                )
            )

        for candidate in plan.candidates:
            errors.extend(
                self._validate_value(
                    "Candidate.candidate_kind",
                    candidate.candidate_id,
                    candidate.candidate_kind,
                    self._BOUNDARY_KINDS,
                )
            )
            errors.extend(
                self._validate_value(
                    "Candidate.input_contract_status",
                    candidate.candidate_id,
                    getattr(candidate, "input_contract_status", "unknown"),
                    self._CONTRACT_SIDE_STATUSES,
                )
            )
            errors.extend(
                self._validate_value(
                    "Candidate.output_contract_status",
                    candidate.candidate_id,
                    getattr(candidate, "output_contract_status", "unknown"),
                    self._CONTRACT_SIDE_STATUSES,
                )
            )
            for contract_field in [
                *candidate.possible_inputs,
                *candidate.possible_outputs,
            ]:
                errors.extend(
                    self._validate_value(
                        "ContractField.source",
                        f"{candidate.candidate_id}.{contract_field.name}",
                        contract_field.source,
                        self._CONTRACT_SOURCES,
                    )
                )
            for signal in candidate.signals:
                errors.extend(
                    self._validate_value(
                        "Candidate.signal",
                        candidate.candidate_id,
                        signal,
                        self._SIGNALS,
                    )
                )
            for risk in candidate.risks:
                errors.extend(
                    self._validate_value(
                        "Candidate.risk",
                        candidate.candidate_id,
                        risk,
                        self._RISKS,
                    )
                )

        for decision in [*plan.decisions, *plan.rejected_candidates]:
            errors.extend(
                self._validate_value(
                    "Decision.decision",
                    decision.candidate_id,
                    decision.decision,
                    self._DECISIONS,
                )
            )
            errors.extend(
                self._validate_value(
                    "Decision.boundary_strength",
                    decision.candidate_id,
                    decision.boundary_strength,
                    self._BOUNDARY_STRENGTHS,
                )
            )
            errors.extend(
                self._validate_value(
                    "Decision.boundary_kind",
                    decision.candidate_id,
                    decision.boundary_kind,
                    self._BOUNDARY_KINDS,
                )
            )
            if decision.rejection_reason is not None:
                errors.extend(
                    self._validate_value(
                        "Decision.rejection_reason",
                        decision.candidate_id,
                        decision.rejection_reason,
                        self._RISKS,
                    )
                )
            for signal in decision.evidence:
                errors.extend(
                    self._validate_value(
                        "Decision.evidence",
                        decision.candidate_id,
                        signal,
                        self._SIGNALS,
                    )
                )

        for handoff in plan.handoffs:
            errors.extend(
                self._validate_value(
                    "Handoff.mode",
                    handoff.handoff_id,
                    handoff.mode,
                    self._HANDOFF_MODES,
                )
            )
            errors.extend(
                self._validate_value(
                    "Handoff.ordering",
                    handoff.handoff_id,
                    handoff.ordering,
                    self._HANDOFF_ORDERINGS,
                )
            )
            for binding in handoff.output_bindings:
                errors.extend(
                    self._validate_value(
                        "OutputBinding.merge_strategy",
                        f"{handoff.handoff_id}.{binding.child_output}",
                        binding.merge_strategy,
                        self._MERGE_STRATEGIES,
                    )
                )
            hint = handoff.invoke_location_hint
            if hint is None:
                errors.append(
                    f"Handoff {handoff.handoff_id} is missing invoke_location_hint."
                )
            else:
                errors.extend(
                    self._validate_value(
                        "InvokeLocationHint.flow_kind",
                        handoff.handoff_id,
                        hint.flow_kind,
                        self._FLOW_KINDS,
                    )
                )
                errors.extend(
                    self._validate_value(
                        "InvokeLocationHint.block_hint",
                        handoff.handoff_id,
                        hint.block_hint,
                        self._BLOCK_HINTS,
                    )
                )
            failure_policy = handoff.failure_policy
            if failure_policy is None:
                errors.append(f"Handoff {handoff.handoff_id} is missing failure_policy.")
            else:
                errors.extend(
                    self._validate_value(
                        "HandoffFailurePolicy.policy_kind",
                        handoff.handoff_id,
                        failure_policy.policy_kind,
                        self._FAILURE_POLICIES,
                    )
                )
            errors.extend(
                self._validate_value(
                    "Handoff.input_binding_status",
                    handoff.handoff_id,
                    getattr(handoff, "input_binding_status", "unknown"),
                    self._BINDING_SIDE_STATUSES,
                )
            )
            errors.extend(
                self._validate_value(
                    "Handoff.output_binding_status",
                    handoff.handoff_id,
                    getattr(handoff, "output_binding_status", "unknown"),
                    self._BINDING_SIDE_STATUSES,
                )
            )
            errors.extend(
                self._validate_value(
                    "Handoff.materialization_status",
                    handoff.handoff_id,
                    getattr(handoff, "materialization_status", "unknown"),
                    self._HANDOFF_MATERIALIZATION_STATUSES,
                )
            )

        for region in plan.control_complexity_regions:
            errors.extend(
                self._validate_value(
                    "ControlRegion.outer_control",
                    region.region_id,
                    region.outer_control,
                    self._OUTER_CONTROLS,
                )
            )
            errors.extend(
                self._validate_value(
                    "ControlRegion.inner_control",
                    region.region_id,
                    region.inner_control,
                    self._INNER_CONTROLS,
                )
            )
            errors.extend(
                self._validate_value(
                    "ControlRegion.discovery_phase",
                    region.region_id,
                    region.discovery_phase,
                    self._DISCOVERY_PHASES,
                )
            )
            errors.extend(
                self._validate_value(
                    "ControlRegion.severity",
                    region.region_id,
                    region.severity,
                    self._SEVERITIES,
                )
            )
            for repair in region.suggested_repairs:
                errors.extend(
                    self._validate_value(
                        "ControlRegion.suggested_repair",
                        region.region_id,
                        repair,
                        self._SUGGESTED_REPAIRS,
                    )
                )

        return errors

    def _validate_value(
        self,
        field_name: str,
        owner_id: str,
        value: str,
        allowed: set[str],
    ) -> list[str]:
        if value in allowed:
            return []
        allowed_values = ", ".join(sorted(allowed))
        return [
            f"{field_name} has invalid value for {owner_id}: "
            f"{value}. Allowed: {allowed_values}"
        ]

    def _validate_main_worker(self, plan: WorkerPlanIR) -> list[str]:
        """Ensure exactly one main worker exists and is correctly referenced.

        The main worker is the entry point of the plan; every child worker
        is invoked transitively from it. We therefore enforce:
        1. There is exactly one worker whose ``kind == "main"``.
        2. ``plan.main_worker_id`` references a concrete worker.
        3. That referenced worker actually has ``kind == "main"``.
        """
        errors = []
        main_workers = [worker for worker in plan.workers if worker.kind == "main"]
        if len(main_workers) != 1:
            errors.append(
                "WorkerPlanIR must contain exactly one main worker, "
                f"found {len(main_workers)}."
            )

        worker_by_id = {worker.worker_id: worker for worker in plan.workers}
        main_worker = worker_by_id.get(plan.main_worker_id)
        if main_worker is None:
            errors.append(f"main_worker_id does not reference a worker: {plan.main_worker_id}")
        elif main_worker.kind != "main":
            errors.append(f"main_worker_id must reference a main worker: {plan.main_worker_id}")

        return errors

    def _validate_unique_worker_ids(self, worker_ids: list[str]) -> list[str]:
        """Detect duplicate worker identifiers.

        Each worker must have a globally unique ``worker_id`` so that
        handoffs can unambiguously reference their source and target.
        """
        return [
            f"Duplicate worker_id: {worker_id}"
            for worker_id, count in Counter(worker_ids).items()
            if count > 1
        ]

    def _validate_unique_handoff_ids(self, handoffs: list[WorkerHandoffIR]) -> list[str]:
        """Detect duplicate handoff identifiers.

        Every handoff must have a unique ``handoff_id`` so that the
        plan graph remains well-defined and traceable.
        """
        return [
            f"Duplicate handoff_id: {handoff_id}"
            for handoff_id, count in Counter(
                handoff.handoff_id for handoff in handoffs
            ).items()
            if count > 1
        ]

    def _validate_worker_names(self, workers: list[WorkerSpecIR]) -> list[str]:
        """Validate worker names are unique and SPL-safe.

        SPL (the target language) requires identifiers to match
        ``^[A-Za-z_][A-Za-z0-9_]*$``. We also ensure no two workers
        share the same ``worker_name``.
        """
        errors = []
        names = [worker.worker_name for worker in workers]
        for worker_name, count in Counter(names).items():
            if count > 1:
                errors.append(f"Duplicate worker_name: {worker_name}")
        for worker in workers:
            if not self._SPL_SAFE_NAME.fullmatch(worker.worker_name):
                errors.append(f"Worker name is not SPL-safe: {worker.worker_name}")
        return errors

    def _validate_handoff_modes(
        self,
        handoffs: list[WorkerHandoffIR],
        worker_ids: set[str],
        main_worker_id: str,
    ) -> list[str]:
        """Validate handoff mode consistency and reference integrity.

        Two modes are supported:
        - **invoke**: synchronous call to another worker. Must set
          ``to_worker`` (and it must be a non-main worker), and must
          NOT set ``api_ref``.
        - **api_call**: external API invocation. Must set ``api_ref``, and
          must NOT set ``to_worker``.

        Additionally, every handoff's ``from_worker`` must reference a
        known worker in the plan.
        """
        errors = []
        for handoff in handoffs:
            if handoff.from_worker not in worker_ids:
                errors.append(
                    f"Handoff {handoff.handoff_id} references unknown source worker: "
                    f"{handoff.from_worker}"
                )

            if handoff.mode == "invoke":
                if handoff.to_worker is None:
                    errors.append(f"Invoke handoff {handoff.handoff_id} is missing to_worker.")
                elif handoff.to_worker not in worker_ids:
                    errors.append(
                        f"Invoke handoff {handoff.handoff_id} references unknown target worker: "
                        f"{handoff.to_worker}"
                    )
                elif handoff.to_worker == main_worker_id:
                    errors.append(
                        f"Invoke handoff {handoff.handoff_id} must target a non-main worker."
                    )
                if handoff.api_ref is not None:
                    errors.append(f"Invoke handoff {handoff.handoff_id} must not set api_ref.")
                continue

            if handoff.mode == "api_call":
                if not handoff.api_ref:
                    errors.append(f"api_call handoff {handoff.handoff_id} must set api_ref.")
                if handoff.to_worker is not None:
                    errors.append(f"api_call handoff {handoff.handoff_id} must not set to_worker.")

        return errors

    def _validate_non_main_handoffs(
        self,
        workers: list[WorkerSpecIR],
        handoffs: list[WorkerHandoffIR],
        *,
        warnings: list[str] | None = None,
    ) -> list[str]:
        """Ensure every non-main worker is reachable via at least one invoke handoff.

        A child or api_adapter that is never invoked is effectively dead
        code in the plan. We detect these orphan workers and flag them.
        Partial workers (with partial_reason) get a warning instead of error.
        """
        invoked_worker_ids = {
            handoff.to_worker
            for handoff in handoffs
            if handoff.mode == "invoke" and handoff.to_worker is not None
            and getattr(handoff, "materialization_status", "unknown") != "blocked"
        }
        errors: list[str] = []
        for worker in workers:
            if worker.kind != "main" and worker.worker_id not in invoked_worker_ids:
                msg = f"Non-main worker has no handoff: {worker.worker_id}"
                if getattr(worker, "partial_reason", None) and warnings is not None:
                    warnings.append(msg)
                else:
                    errors.append(msg)
        return errors

    def _validate_child_contracts(
        self, workers: list[WorkerSpecIR],
        *,
        warnings: list[str] | None = None,
    ) -> list[str]:
        """Check that non-main worker contract sides are satisfied.

        ``known_empty + []`` is satisfied — no error, no warning.
        ``unknown + []`` is a partial warning.
        ``known_present + []`` is a status-algebra error (caught elsewhere).
        """
        errors = []
        for worker in workers:
            if worker.kind == "main":
                continue
            in_status = getattr(worker, "input_contract_status", "unknown")
            out_status = getattr(worker, "output_contract_status", "unknown")
            in_satisfied = contract_side_satisfied(worker.input_contract, in_status)
            out_satisfied = contract_side_satisfied(worker.output_contract, out_status)
            is_partial = bool(getattr(worker, "partial_reason", None))
            if not in_satisfied:
                msg = f"Accepted child worker has empty input contract: {worker.worker_id}"
                if is_partial and warnings is not None:
                    warnings.append(msg)
                else:
                    errors.append(msg)
            if not out_satisfied:
                msg = f"Accepted child worker has empty output contract: {worker.worker_id}"
                if is_partial and warnings is not None:
                    warnings.append(msg)
                else:
                    errors.append(msg)
        return errors

    def _validate_handoff_bindings(
        self,
        handoffs: list[WorkerHandoffIR],
        worker_by_id: dict[str, WorkerSpecIR],
        *,
        warnings: list[str] | None = None,
    ) -> list[str]:
        """Validate that handoff bindings reference real contract fields.

        When data is passed from a parent worker to a child (or vice
        versa), the binding must name a field that actually exists in
        the target worker's contract. Otherwise the generated code would
        reference an undefined variable.
        """
        errors = []
        for handoff in handoffs:
            if handoff.mode != "invoke" or handoff.to_worker is None:
                continue

            target = worker_by_id.get(handoff.to_worker)
            if target is None:
                continue

            in_contract_unknown = (
                getattr(target, "input_contract_status", "unknown") == "unknown"
                and not target.input_contract
            )
            out_contract_unknown = (
                getattr(target, "output_contract_status", "unknown") == "unknown"
                and not target.output_contract
            )
            input_names = {field.name for field in target.input_contract}
            output_names = {field.name for field in target.output_contract}

            for binding in handoff.input_bindings:
                if binding.child_input not in input_names:
                    msg = (
                        f"Handoff {handoff.handoff_id} input binding references "
                        f"unknown contract field: {binding.child_input}"
                    )
                    if in_contract_unknown:
                        if warnings is not None:
                            warnings.append(msg)
                        else:
                            errors.append(msg)
                    else:
                        errors.append(msg)

            for binding in handoff.output_bindings:
                if binding.child_output not in output_names:
                    msg = (
                        f"Handoff {handoff.handoff_id} output binding references "
                        f"unknown contract field: {binding.child_output}"
                    )
                    if out_contract_unknown:
                        if warnings is not None:
                            warnings.append(msg)
                        else:
                            errors.append(msg)
                    else:
                        errors.append(msg)

        return errors

    def _validate_accepted_child_decisions(
        self, plan: WorkerPlanIR,
        *,
        warnings: list[str] | None = None,
    ) -> list[str]:
        errors: list[str] = []
        candidate_spans = {
            candidate.candidate_id: set(candidate.source_span_ids)
            for candidate in plan.candidates
        }
        non_main_workers = [
            worker for worker in plan.workers if worker.kind in {"child", "api_adapter"}
        ]

        for decision in plan.decisions:
            if decision.decision != "extract_child_worker":
                continue

            matches = [
                worker
                for worker in non_main_workers
                if worker.worker_id == decision.candidate_id
            ]
            if not matches:
                spans = candidate_spans.get(decision.candidate_id, set())
                matches = [
                    worker
                    for worker in non_main_workers
                    if spans and set(worker.owned_span_ids) == spans
                ]

            if len(matches) != 1:
                errors.append(
                    "Accepted child decision must match exactly one non-main worker: "
                    f"{decision.candidate_id}, found {len(matches)}."
                )
                continue

            worker = matches[0]
            invoke_handoffs = [
                handoff
                for handoff in plan.handoffs
                if handoff.mode == "invoke" and handoff.to_worker == worker.worker_id
            ]
            if not invoke_handoffs:
                msg = (
                    "Accepted child decision has no invoke handoff: "
                    f"{decision.candidate_id} -> {worker.worker_id}."
                )
                # Only downgrade when worker is explicitly partial.
                if warnings is not None and getattr(worker, "partial_reason", None):
                    warnings.append(msg)
                else:
                    errors.append(msg)
                continue

            for handoff in invoke_handoffs:
                mat_status = getattr(handoff, "materialization_status", "unknown")
                if mat_status == "blocked":
                    errors.append(
                        "Accepted child handoff is blocked: "
                        f"{decision.candidate_id} -> {handoff.handoff_id}."
                    )
                    continue
                is_partial_handoff = mat_status == "partial_contract_unknown"
                in_b_status = getattr(handoff, "input_binding_status", "unknown")
                out_b_status = getattr(handoff, "output_binding_status", "unknown")
                # Worker-side satisfaction (known_empty + empty = satisfied)
                w_in_satisfied = contract_side_satisfied(
                    worker.input_contract,
                    getattr(worker, "input_contract_status", "unknown"),
                )
                w_out_satisfied = contract_side_satisfied(
                    worker.output_contract,
                    getattr(worker, "output_contract_status", "unknown"),
                )
                # Handoff-side satisfaction
                h_in_satisfied = binding_side_satisfied(
                    handoff.input_bindings, in_b_status,
                )
                h_out_satisfied = binding_side_satisfied(
                    handoff.output_bindings, out_b_status,
                )
                if not h_in_satisfied:
                    msg = (
                        f"Accepted child handoff has empty input bindings: "
                        f"{handoff.handoff_id}"
                    )
                    if warnings is not None and is_partial_handoff and not w_in_satisfied:
                        warnings.append(msg)
                    else:
                        errors.append(msg)
                if not h_out_satisfied:
                    msg = (
                        f"Accepted child handoff has empty output bindings: "
                        f"{handoff.handoff_id}"
                    )
                    if warnings is not None and is_partial_handoff and not w_out_satisfied:
                        warnings.append(msg)
                    else:
                        errors.append(msg)

        return errors

    def _validate_status_list_consistency(self, plan: WorkerPlanIR) -> list[str]:
        """Enforce status/list/source algebra for worker and handoff status fields.

        - ``known_present`` → list must be non-empty.
        - ``known_empty`` → list must be empty and source must be non-empty.
        """
        errors: list[str] = []
        for worker in plan.workers:
            if worker.kind == "main":
                continue
            errors.extend(
                self._check_side_consistency(
                    worker.worker_id,
                    worker.input_contract,
                    getattr(worker, "input_contract_status", "unknown"),
                    getattr(worker, "input_contract_status_source", None),
                    "worker input",
                )
            )
            errors.extend(
                self._check_side_consistency(
                    worker.worker_id,
                    worker.output_contract,
                    getattr(worker, "output_contract_status", "unknown"),
                    getattr(worker, "output_contract_status_source", None),
                    "worker output",
                )
            )
        for handoff in plan.handoffs:
            errors.extend(
                self._check_side_consistency(
                    handoff.handoff_id,
                    handoff.input_bindings,
                    getattr(handoff, "input_binding_status", "unknown"),
                    getattr(handoff, "input_binding_status_source", None),
                    "handoff input",
                )
            )
            errors.extend(
                self._check_side_consistency(
                    handoff.handoff_id,
                    handoff.output_bindings,
                    getattr(handoff, "output_binding_status", "unknown"),
                    getattr(handoff, "output_binding_status_source", None),
                    "handoff output",
                )
            )
            # materialization_status must match derivation
            mat_status = getattr(handoff, "materialization_status", "unknown")
            if mat_status != "blocked":
                expected = derive_handoff_materialization_status(
                    input_bindings=handoff.input_bindings,
                    output_bindings=handoff.output_bindings,
                    input_status=getattr(handoff, "input_binding_status", "unknown"),
                    output_status=getattr(handoff, "output_binding_status", "unknown"),
                )
                if mat_status != expected:
                    errors.append(
                        f"handoff materialization_status mismatch: "
                        f"{handoff.handoff_id} has '{mat_status}', "
                        f"expected '{expected}'"
                    )

        for candidate in plan.candidates:
            errors.extend(
                self._check_side_consistency(
                    candidate.candidate_id,
                    candidate.possible_inputs,
                    getattr(candidate, "input_contract_status", "unknown"),
                    getattr(candidate, "input_contract_status_source", None),
                    "candidate input",
                )
            )
            errors.extend(
                self._check_side_consistency(
                    candidate.candidate_id,
                    candidate.possible_outputs,
                    getattr(candidate, "output_contract_status", "unknown"),
                    getattr(candidate, "output_contract_status_source", None),
                    "candidate output",
                )
            )
        return errors

    @staticmethod
    def _check_side_consistency(
        owner_id: str,
        items: list,
        status: str,
        source: str | None,
        label: str,
    ) -> list[str]:
        errors: list[str] = []
        if status == "known_present" and not items:
            errors.append(
                f"{label}_contract status is 'known_present' but {label} "
                f"list is empty: {owner_id}"
            )
        if status == "known_empty":
            if items:
                errors.append(
                    f"{label}_contract status is 'known_empty' but {label} "
                    f"list is non-empty: {owner_id}"
                )
            if not isinstance(source, str) or not source.strip():
                errors.append(
                    f"{label}_contract status is 'known_empty' but "
                    f"{label}_status_source is missing or empty: {owner_id}"
                )
        return errors

    def _validate_span_ownership(
        self,
        workers: list[WorkerSpecIR],
        known_span_ids: set[str] | None,
    ) -> list[str]:
        errors = []
        owners: dict[str, list[str]] = defaultdict(list)
        for worker in workers:
            for span_id in worker.owned_span_ids:
                owners[span_id].append(worker.worker_id)
                if known_span_ids is not None and span_id not in known_span_ids:
                    errors.append(
                        f"Worker {worker.worker_id} owns unknown span_id: {span_id}"
                    )

        for span_id, owner_ids in owners.items():
            if len(owner_ids) > 1:
                errors.append(
                    f"Duplicate behavior-span ownership for {span_id}: "
                    f"{', '.join(owner_ids)}"
                )

        return errors

    def _validate_rejected_candidates(self, plan: WorkerPlanIR) -> list[str]:
        errors = []
        rejected_ids = {decision.candidate_id for decision in plan.rejected_candidates}
        decision_ids = {decision.candidate_id for decision in plan.decisions}
        accepted_ids = {
            decision.candidate_id
            for decision in plan.decisions
            if decision.decision == "extract_child_worker"
        }

        for candidate_id in rejected_ids - decision_ids:
            errors.append(f"Rejected candidate is missing from decisions: {candidate_id}")

        for candidate_id in rejected_ids & accepted_ids:
            errors.append(f"Accepted decision appears in rejected_candidates: {candidate_id}")

        for decision in plan.rejected_candidates:
            if decision.decision == "extract_child_worker":
                errors.append(
                    f"Rejected candidate has accepted decision: {decision.candidate_id}"
                )

        candidate_spans = {
            candidate.candidate_id: set(candidate.source_span_ids)
            for candidate in plan.candidates
        }
        for worker in plan.workers:
            if worker.kind == "main":
                continue
            if worker.worker_id in rejected_ids:
                errors.append(
                    f"Rejected candidate is present as concrete worker: {worker.worker_id}"
                )
                continue
            worker_spans = set(worker.owned_span_ids)
            for candidate_id in rejected_ids:
                spans = candidate_spans.get(candidate_id, set())
                if spans and worker_spans == spans:
                    errors.append(
                        f"Rejected candidate is present as concrete worker by span ownership: "
                        f"{candidate_id}"
                    )

        for handoff in plan.handoffs:
            if handoff.to_worker in rejected_ids:
                errors.append(
                    f"Handoff {handoff.handoff_id} references rejected candidate: "
                    f"{handoff.to_worker}"
                )
            if handoff.api_ref in rejected_ids:
                errors.append(
                    f"Handoff {handoff.handoff_id} references rejected candidate API: "
                    f"{handoff.api_ref}"
                )

        return errors
