"""First-pass provenance aggregation from existing source_span_ids.

Builds TraceRecord entries for the major SPL element types without
requiring full TraceRef fields on every IR.

Resolves source_section_id / source_packet_id through SpanIR where
available for all element types: flows, workers, handoffs, steps,
constraints, and variables.
"""

from __future__ import annotations

from typing import Any

from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.ir.worker_plan_ir import WorkerHandoffIR


class ProvenanceAggregator:
    """First-pass provenance aggregator.

    Builds TraceRecord entries from existing source_span_ids on IR types,
    resolving source_section_id / source_packet_id through SpanIR where
    available.

    Variable provenance is recovered from producer-step spans, worker
    contracts, and resource sections -- never from VariableSpec.source alone.
    """

    def aggregate(
        self,
        worker: WorkerIR,
        steps: list[StepIR],
        constraints: list[ConstraintIR],
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        spans: list[SpanIR],
        profile: AgentProfileIR | None = None,
        worker_var_scopes: dict[str, str] | None = None,
        handoffs: list[WorkerHandoffIR] | None = None,
        known_child_worker_ids: set[str] | None = None,
        declared_apis: set[str] | None = None,
        worker_owned_spans: dict[str, list[str]] | None = None,
        variable_facts: list[Any] | None = None,
        delegation_intents: list[Any] | None = None,
    ) -> tuple[list[TraceRecord], list[CompileDiagnostic]]:
        """Produce traces and missing-provenance diagnostics.

        Args:
            worker_owned_spans: worker_name -> owned_span_ids from
                WorkerSpecIR (for worker trace section/packet resolution).
            variable_facts: VariableFact objects from the adapter, carrying
                source_section_id for hard-fact variable provenance.
            delegation_intents: DelegationIntentFact objects from the
                adapter (non-executable, trace-only).

        Returns:
            (traces, diagnostics) -- traces link elements to source evidence;
            diagnostics flag elements with no discoverable provenance.
        """
        span_index: dict[str, SpanIR] = {s.span_id: s for s in spans}
        traces: list[TraceRecord] = []
        diags: list[CompileDiagnostic] = []

        # 1. Worker provenance
        self._trace_worker(worker, span_index, traces, diags, worker_owned_spans)

        # 2. Flow provenance
        self._trace_flows(worker, span_index, traces, diags)

        # 3. Step provenance
        self._trace_steps(steps, span_index, traces, diags)

        # 4. Constraint provenance
        self._trace_constraints(constraints, span_index, traces, diags)

        # 5. Handoff provenance
        if handoffs:
            self._trace_handoffs(handoffs, span_index, traces)

        # 5b. Delegation intent provenance (non-executable, trace-only)
        if delegation_intents:
            self._trace_delegation_intents(
                delegation_intents, span_index, traces,
            )

        # 6. Variable provenance
        self._trace_variables(
            resources, symbol_table, steps, span_index, traces, diags,
            worker_var_scopes=worker_var_scopes,
            handoffs=handoffs,
            known_child_worker_ids=known_child_worker_ids,
            declared_apis=declared_apis,
            variable_facts=variable_facts,
        )

        # 7. Profile provenance
        if profile is not None:
            self._trace_profile(profile, traces)

        return traces, diags

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    def _trace_worker(
        self,
        worker: WorkerIR,
        span_index: dict[str, SpanIR],
        traces: list[TraceRecord],
        diags: list[CompileDiagnostic],
        worker_owned_spans: dict[str, list[str]] | None = None,
    ) -> None:
        owned = worker_owned_spans or {}

        # Main worker
        main_span_ids = owned.get(worker.worker_name, [])
        section_id, packet_id = self._resolve_span_origin(
            main_span_ids, span_index,
        )
        traces.append(
            TraceRecord(
                target_ref=f"worker:{worker.worker_name}",
                source_span_ids=list(main_span_ids),
                source_section_id=section_id,
                source_packet_id=packet_id,
                relation="direct" if main_span_ids else "inferred",
                explanation=(
                    f"Main worker '{worker.worker_name}' assembled from "
                    f"flow and step IRs."
                ),
            )
        )
        for child in worker.child_workers:
            child_span_ids = owned.get(child.worker_name, [])
            c_section, c_packet = self._resolve_span_origin(
                child_span_ids, span_index,
            )
            traces.append(
                TraceRecord(
                    target_ref=f"worker:{child.worker_name}",
                    source_span_ids=list(child_span_ids),
                    source_section_id=c_section,
                    source_packet_id=c_packet,
                    relation="direct" if child_span_ids else "inferred",
                    explanation=(
                        f"Child worker '{child.worker_name}' extracted "
                        f"from delegation pattern."
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Flows
    # ------------------------------------------------------------------

    def _trace_flows(
        self,
        worker: WorkerIR,
        span_index: dict[str, SpanIR],
        traces: list[TraceRecord],
        diags: list[CompileDiagnostic],
    ) -> None:
        # Main flow spans are collected from blocks
        main_span_ids: list[str] = []
        for block in worker.main_flow.blocks:
            if block.spans:
                main_span_ids.extend(block.spans)
        m_section, m_packet = self._resolve_span_origin(
            main_span_ids, span_index,
        )
        traces.append(
            TraceRecord(
                target_ref="flow:main",
                source_span_ids=main_span_ids,
                source_section_id=m_section,
                source_packet_id=m_packet,
                relation="direct" if main_span_ids else "inferred",
                explanation=(
                    f"Main flow with {len(worker.main_flow.blocks)} "
                    f"block(s)."
                ),
            )
        )

        for alt in worker.alternative_flows:
            alt_span_ids: list[str] = []
            for block in alt.blocks:
                if block.spans:
                    alt_span_ids.extend(block.spans)
            a_section, a_packet = self._resolve_span_origin(
                alt_span_ids, span_index,
            )
            traces.append(
                TraceRecord(
                    target_ref=f"flow:{alt.flow_id}",
                    source_span_ids=alt_span_ids,
                    source_section_id=a_section,
                    source_packet_id=a_packet,
                    relation="direct" if alt_span_ids else "inferred",
                    explanation=(
                        f"Alternative flow '{alt.flow_id}': "
                        f"{alt.condition_text}"
                    ),
                )
            )

        for exc in worker.exception_flows:
            exc_span_ids: list[str] = list(exc.spans) if exc.spans else []
            for block in exc.blocks:
                if block.spans:
                    exc_span_ids.extend(block.spans)
            e_section, e_packet = self._resolve_span_origin(
                exc_span_ids, span_index,
            )
            traces.append(
                TraceRecord(
                    target_ref=f"flow:{exc.flow_id}",
                    source_span_ids=exc_span_ids,
                    source_section_id=e_section,
                    source_packet_id=e_packet,
                    relation=(
                        "direct" if exc_span_ids else "inferred"
                    ),
                    explanation=(
                        f"Exception flow '{exc.flow_id}': "
                        f"{exc.condition_text}"
                    ),
                )
            )

        # D7: trace child worker exception flows
        for child in worker.child_workers:
            for exc in child.exception_flows:
                exc_span_ids: list[str] = list(exc.spans) if exc.spans else []
                for block in exc.blocks:
                    if block.spans:
                        exc_span_ids.extend(block.spans)
                e_section, e_packet = self._resolve_span_origin(
                    exc_span_ids, span_index,
                )
                traces.append(
                    TraceRecord(
                        target_ref=(
                            f"worker:{child.worker_name}."
                            f"exception_flow:{exc.flow_id}"
                        ),
                        source_span_ids=exc_span_ids,
                        source_section_id=e_section,
                        source_packet_id=e_packet,
                        relation=(
                            "direct" if exc_span_ids else "inferred"
                        ),
                        explanation=(
                            f"Child worker '{child.worker_name}' "
                            f"exception flow '{exc.flow_id}': "
                            f"{exc.condition_text}"
                        ),
                    )
                )

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _trace_steps(
        self,
        steps: list[StepIR],
        span_index: dict[str, SpanIR],
        traces: list[TraceRecord],
        diags: list[CompileDiagnostic],
    ) -> None:
        for step in steps:
            if step.source_span_ids:
                relation = "direct"
                explanation = (
                    f"Step '{step.step_id}' maps to source span(s)."
                )
            elif step.handoff_id is not None:
                relation = "direct"
                explanation = (
                    f"Step '{step.step_id}' is materialised from "
                    f"handoff '{step.handoff_id}'."
                )
            elif step.metadata.get("origin") == "compiler_unpack":
                relation = "normalized"
                explanation = (
                    f"Step '{step.step_id}' is compiler unpack "
                    f"scaffolding."
                )
            else:
                relation = "assumed"
                explanation = (
                    f"Step '{step.step_id}' has no source evidence."
                )

            section_id, packet_id = self._resolve_span_origin(
                step.source_span_ids, span_index
            )
            traces.append(
                TraceRecord(
                    target_ref=f"step:{step.step_id}",
                    source_span_ids=list(step.source_span_ids),
                    source_section_id=section_id,
                    source_packet_id=packet_id,
                    relation=relation,
                    explanation=explanation,
                    needs_confirmation=(relation == "assumed"),
                )
            )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def _trace_constraints(
        self,
        constraints: list[ConstraintIR],
        span_index: dict[str, SpanIR],
        traces: list[TraceRecord],
        diags: list[CompileDiagnostic],
    ) -> None:
        for constraint in constraints:
            has_source = bool(constraint.source_span_ids)
            section_id, packet_id = self._resolve_span_origin(
                constraint.source_span_ids, span_index
            )
            traces.append(
                TraceRecord(
                    target_ref=f"constraint:{constraint.constraint_id}",
                    source_span_ids=list(constraint.source_span_ids),
                    source_section_id=section_id,
                    source_packet_id=packet_id,
                    relation="direct" if has_source else "assumed",
                    explanation=(
                        f"Constraint '{constraint.constraint_id}' "
                        f"({constraint.kind}): "
                        f"{constraint.text[:80] if hasattr(constraint, 'text') else 'n/a'}"
                    ),
                    needs_confirmation=not has_source,
                )
            )

    # ------------------------------------------------------------------
    # Handoffs
    # ------------------------------------------------------------------

    def _trace_handoffs(
        self,
        handoffs: list[WorkerHandoffIR],
        span_index: dict[str, SpanIR],
        traces: list[TraceRecord],
    ) -> None:
        """Produce trace records for worker handoff contracts.

        Resolves section/packet from invoke_location_hint spans and
        failure_policy source spans where available.
        """
        for h in handoffs:
            # Collect span evidence from location hints and failure policy
            hint_span_ids: list[str] = []
            hint = h.invoke_location_hint
            if hint.after_span_id:
                hint_span_ids.append(hint.after_span_id)
            if hint.before_span_id:
                hint_span_ids.append(hint.before_span_id)
            fp_span_ids = list(h.failure_policy.source_span_ids)
            source_span_ids = hint_span_ids + fp_span_ids

            section_id, packet_id = self._resolve_span_origin(
                source_span_ids, span_index,
            )
            mode_desc = (
                f"invoke to {h.to_worker}" if h.mode == "invoke"
                else f"api_call to {h.api_ref or 'unnamed'}"
            )
            traces.append(
                TraceRecord(
                    target_ref=f"handoff:{h.handoff_id}",
                    source_span_ids=source_span_ids,
                    source_section_id=section_id,
                    source_packet_id=packet_id,
                    relation="direct" if source_span_ids else "inferred",
                    explanation=(
                        f"Handoff '{h.handoff_id}' "
                        f"({h.from_worker} {mode_desc}) "
                        f"with {len(h.input_bindings)} input(s) and "
                        f"{len(h.output_bindings)} output(s)."
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Delegation intents
    # ------------------------------------------------------------------

    @staticmethod
    def _trace_delegation_intents(
        intents: list[Any],
        span_index: dict[str, SpanIR],
        traces: list[TraceRecord],
    ) -> None:
        """Produce non-executable trace records for delegation intent facts.

        These are provenance-only -- the compiler does NOT create
        INVOKE_WORKER from delegation intents without a valid handoff.
        """
        for intent in intents:
            # Resolve section/packet from evidence
            ev_span_ids: list[str] = []
            section_id = None
            packet_id = None
            for ev in getattr(intent, "evidence", []):
                if getattr(ev, "source_span_ids", None):
                    ev_span_ids.extend(ev.source_span_ids)
                sid = getattr(ev, "source_section_id", None)
                pid = getattr(ev, "source_packet_id", None)
                if sid and section_id is None:
                    section_id = sid
                if pid and packet_id is None:
                    packet_id = pid
            # Resolve from span_index if no direct evidence
            if not ev_span_ids and section_id:
                ev_span_ids = [
                    s.span_id for s in span_index.values()
                    if s.source_section_id == section_id
                ]
            if not section_id and ev_span_ids:
                for sid in ev_span_ids:
                    span = span_index.get(sid)
                    if span and span.source_section_id:
                        section_id = span.source_section_id
                        break

            worker_hint = getattr(intent, "suggested_worker_name", None) or ""
            traces.append(
                TraceRecord(
                    target_ref=f"delegation_intent:{intent.name}",
                    source_span_ids=ev_span_ids,
                    source_section_id=section_id,
                    source_packet_id=packet_id,
                    relation="inferred",
                    explanation=(
                        f"Delegation intent '{intent.name}': "
                        f"{getattr(intent, 'text', '')[:120]}"
                        + (f" (suggested worker: {worker_hint})"
                           if worker_hint else "")
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def _trace_variables(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
        span_index: dict[str, SpanIR],
        traces: list[TraceRecord],
        diags: list[CompileDiagnostic],
        worker_var_scopes: dict[str, str] | None = None,
        handoffs: list[WorkerHandoffIR] | None = None,
        known_child_worker_ids: set[str] | None = None,
        declared_apis: set[str] | None = None,
        variable_facts: list[Any] | None = None,
    ) -> None:
        """Recover variable provenance from producer steps, contracts, etc.

        VariableSpec.source is only a resource category ("input"/"output"/
        "step"), NOT provenance. Real provenance comes from:
        - Producer step source spans
        - Adapter VariableFact hard facts (source_section_id)
        - Worker input/output contract sections (via adapter)
        - Resource-extraction spans
        """
        # Index adapter hard facts by variable name
        fact_index: dict[str, Any] = {}
        if variable_facts:
            for f in variable_facts:
                fact_index[f.name] = f
        producer_index: dict[str, StepIR] = {}
        for step in steps:
            for output in step.outputs:
                producer_index.setdefault(output, step)

        scopes = worker_var_scopes or {}

        for var in resources.variables:
            var_name = var.name
            sym = symbol_table.lookup(var_name)
            source_span_ids: list[str] = []
            relation = "assumed"
            explanation = ""
            scope_worker_id = scopes.get(var_name)
            var_target_ref = (
                f"worker:{scope_worker_id}.variable:{var_name}"
                if scope_worker_id is not None
                else f"variable:{var_name}"
            )

            # 1. Producer step provenance (strongest evidence)
            producer = producer_index.get(var_name)
            if producer is not None and producer.source_span_ids:
                source_span_ids = list(producer.source_span_ids)
                relation = "direct"
                explanation = (
                    f"Variable '{var_name}' is produced by source-backed "
                    f"step '{producer.step_id}'."
                )
            elif producer is not None and producer.handoff_id is not None:
                relation = "direct"
                explanation = (
                    f"Variable '{var_name}' is produced by handoff "
                    f"step '{producer.step_id}'."
                )
            elif producer is not None and producer.metadata.get(
                "origin"
            ) == "compiler_unpack":
                relation = "normalized"
                explanation = (
                    f"Variable '{var_name}' is an unpacked field from "
                    f"a structured result produced by step "
                    f"'{producer.step_id}'."
                )

            # 1b. Adapter VariableFact hard fact
            elif var_name in fact_index:
                fact = fact_index[var_name]
                source_span_ids = []
                relation = "normalized"
                explanation = (
                    f"Variable '{var_name}' is declared by adapter hard "
                    f"fact in section '{fact.source_section_id}'."
                )
                # We carry source_section_id directly on the trace record
                # via _resolve_span_origin below (source_span_ids is empty,
                # so the call returns None/None).  We set it explicitly.
                section_id = fact.source_section_id
                packet_id = None
                traces.append(
                    TraceRecord(
                        target_ref=var_target_ref,
                        source_span_ids=[],
                        source_section_id=section_id,
                        source_packet_id=packet_id,
                        relation=relation,
                        explanation=explanation,
                        needs_confirmation=False,
                    )
                )
                continue  # skip the generic _resolve_span_origin path below

            # 2. Input / output contract variable -- may have handoff binding
            elif var.source in ("input", "output"):
                if handoffs is not None:
                    binding = self._find_handoff_output_binding(
                        var_name, handoffs
                    )
                else:
                    binding = None

                if binding is not None and self._handoff_has_valid_evidence(
                    binding, known_child_worker_ids, declared_apis
                ):
                    relation = "direct"
                    explanation = (
                        f"Variable '{var_name}' is produced by valid handoff "
                        f"'{binding.handoff_id}' output binding."
                    )
                elif binding is not None:
                    # Handoff exists but lacks evidence -- inferred, not direct
                    relation = "inferred"
                    explanation = (
                        f"Variable '{var_name}' is bound to handoff "
                        f"'{binding.handoff_id}' which has incomplete "
                        f"evidence (missing target or IO bindings)."
                    )
                    diags.append(
                        CompileDiagnostic(
                            diagnostic_id=f"diag_prov_{len(diags):04d}",
                            kind="missing_provenance",
                            severity="warning",
                            message=(
                                f"Variable '{var_name}' ({var.data_type}) "
                                f"is bound to handoff '{binding.handoff_id}' "
                                f"with incomplete contract evidence."
                            ),
                            target_ref=var_target_ref,
                            source_span_ids=[],
                            blocks_rendering=False,
                            blocks_completion=False,
                        )
                    )
                else:
                    relation = "assumed"
                    explanation = (
                        f"Variable '{var_name}' is declared as worker "
                        f"{var.source} contract with no source evidence."
                    )
                    diags.append(
                        CompileDiagnostic(
                            diagnostic_id=f"diag_prov_{len(diags):04d}",
                            kind="missing_provenance",
                            severity="warning",
                            message=(
                                f"Variable '{var_name}' ({var.data_type}) "
                                f"is a contract {var.source} with no "
                                f"source-backed producer or adapter evidence."
                            ),
                            target_ref=var_target_ref,
                            source_span_ids=[],
                            blocks_rendering=False,
                            blocks_completion=False,
                        )
                    )
                source_span_ids = []

            # 3. Step variable with declared symbol -- no evidence
            elif sym is not None and sym.declared:
                relation = "assumed"
                explanation = (
                    f"Variable '{var_name}' is a declared step variable "
                    f"with no discoverable source provenance."
                )
                diags.append(
                    CompileDiagnostic(
                        diagnostic_id=f"diag_prov_{len(diags):04d}",
                        kind="missing_provenance",
                        severity="warning",
                        message=(
                            f"Variable '{var_name}' ({var.data_type}) "
                            f"has no source-backed producer and no "
                            f"contract section evidence."
                        ),
                        target_ref=var_target_ref,
                        source_span_ids=[],
                        blocks_rendering=False,
                        blocks_completion=False,
                    )
                )

            # 4. No evidence found -- report as assumed
            else:
                relation = "assumed"
                explanation = (
                    f"Variable '{var_name}' has no discoverable source "
                    f"provenance."
                )
                diags.append(
                    CompileDiagnostic(
                        diagnostic_id=f"diag_prov_{len(diags):04d}",
                        kind="missing_provenance",
                        severity="warning",
                        message=(
                            f"Variable '{var_name}' ({var.data_type}) "
                            f"has no discoverable source provenance."
                        ),
                        target_ref=var_target_ref,
                        source_span_ids=[],
                        blocks_rendering=False,
                        blocks_completion=False,
                    )
                )

            section_id, packet_id = self._resolve_span_origin(
                source_span_ids, span_index
            )
            traces.append(
                TraceRecord(
                    target_ref=var_target_ref,
                    source_span_ids=source_span_ids,
                    source_section_id=section_id,
                    source_packet_id=packet_id,
                    relation=relation,
                    explanation=explanation,
                    needs_confirmation=(relation == "assumed"),
                )
            )

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def _trace_profile(
        self,
        profile: AgentProfileIR,
        traces: list[TraceRecord],
    ) -> None:
        traces.append(
            TraceRecord(
                target_ref="profile:persona",
                source_span_ids=[],
                relation="inferred",
                explanation=f"Persona: {profile.persona.role}",
            )
        )
        for i, aspect in enumerate(profile.audience_aspects):
            traces.append(
                TraceRecord(
                    target_ref=f"profile:audience_{i}",
                    source_span_ids=[],
                    relation="inferred",
                    explanation=f"Audience: {aspect.name}",
                )
            )
        for i, concept in enumerate(profile.concepts):
            traces.append(
                TraceRecord(
                    target_ref=f"profile:concept_{i}",
                    source_span_ids=[],
                    relation="normalized",
                    explanation=f"Concept: {concept.term} -- "
                    f"{concept.definition}",
                )
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_handoff_output_binding(
        variable_name: str,
        handoffs: list[WorkerHandoffIR],
    ) -> WorkerHandoffIR | None:
        """Return the first handoff whose output bindings produce *variable_name*."""
        for h in handoffs:
            for b in h.output_bindings:
                if b.parent_variable == variable_name:
                    return h
        return None

    @staticmethod
    def _handoff_has_valid_evidence(
        handoff: WorkerHandoffIR,
        known_child_worker_ids: set[str] | None = None,
        declared_apis: set[str] | None = None,
    ) -> bool:
        """Check whether a handoff has sufficient contract evidence to serve as
        provenance.  Mirrors the ProducerIndex / Gate renderability rules."""
        if handoff.mode == "invoke":
            if not handoff.to_worker:
                return False
            if known_child_worker_ids is not None:
                if handoff.to_worker not in known_child_worker_ids:
                    return False
            if not handoff.input_bindings or not handoff.output_bindings:
                return False
            return True
        if handoff.mode == "api_call":
            if not handoff.api_ref:
                return False
            if declared_apis is not None:
                if handoff.api_ref not in declared_apis:
                    return False
            return True
        return False

    @staticmethod
    def _resolve_span_origin(
        span_ids: list[str],
        span_index: dict[str, SpanIR],
    ) -> tuple[str | None, str | None]:
        """Resolve source_section_id / source_packet_id from the first
        span that has adapter provenance data.
        """
        for span_id in span_ids:
            span = span_index.get(span_id)
            if span is None:
                continue
            if span.source_section_id or span.source_packet_id:
                return span.source_section_id, span.source_packet_id
        return None, None
