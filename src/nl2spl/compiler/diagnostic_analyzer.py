"""DiagnosticAnalyzer — centralized, pure compiler diagnostic rules.

Produces structured CompileDiagnostic records from post-compilation IR data.
Does NOT call the LLM and has no side effects — it is fully fixture-testable.

The five diagnostic kinds (all covered by DiagnosticKind):
1. unmapped_behavior_span   — Stage 7 spans not mapped to a step
2. missing_handler          — exception flow with source evidence but no handler
3. missing_output_producer  — required output with no renderable producer
4. type_or_contract_ambiguity — unresolved API/worker/handoff contracts
5. assumed_command_not_renderable — steps with no source evidence
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR


@dataclass
class AnalyzeInput:
    """All context needed by DiagnosticAnalyzer.

    Every field is optional — the analyzer only runs rules that have
    sufficient input data.  This makes it safe to call from tests with
    just the IR fixtures needed for a specific diagnostic kind.
    """

    worker: WorkerIR | None = None
    resources: ResourceRegistryIR | None = None
    symbol_table: SymbolTable | None = None
    producer_index: ProducerIndex | None = None
    steps: list[StepIR] = field(default_factory=list)
    unmapped_behavior_spans: list[dict[str, str]] = field(default_factory=list)
    declared_apis: set[str] | None = None
    valid_handoff_ids: set[str] | None = None


class DiagnosticAnalyzer:
    """Centralized compiler diagnostic rules.

    Pure, fixture-testable analysis.  Takes post-compilation IR data and
    produces structured CompileDiagnostic records for all five MVP kinds.

    The analyzer observes the **no demand, no structure** principle: it
    only checks structures the source actually expressed.  An exception
    flow with empty condition_text is compiler-fabricated and does not
    trigger a missing_handler diagnostic.
    """

    def analyze(self, input: AnalyzeInput) -> list[CompileDiagnostic]:
        """Run all diagnostic rules and return the consolidated list."""
        diags: list[CompileDiagnostic] = []

        # 1. unmapped_behavior_span — pass-through from Stage 7
        diags.extend(self._diagnose_unmapped_spans(input))

        # 2. missing_handler — exception flows without handler steps
        if input.worker is not None:
            diags.extend(self._diagnose_missing_handlers(input))

        # 3. missing_output_producer — required outputs without renderable producer
        if input.resources is not None and input.producer_index is not None:
            diags.extend(
                self._diagnose_missing_output_producers(input)
            )

        # 4. type_or_contract_ambiguity — unresolved API/worker contracts
        if input.steps:
            diags.extend(
                self._diagnose_type_contract_ambiguities(input)
            )

        # 5. assumed_command_not_renderable — steps with no source evidence
        if input.steps:
            diags.extend(self._diagnose_assumed_commands(input))

        return diags

    # ------------------------------------------------------------------
    # 1. unmapped_behavior_span
    # ------------------------------------------------------------------

    @staticmethod
    def _diagnose_unmapped_spans(input: AnalyzeInput) -> list[CompileDiagnostic]:
        """Pass through unmapped-behavior-span records from Stage 7."""
        diags: list[CompileDiagnostic] = []
        for i, item in enumerate(input.unmapped_behavior_spans):
            span_id = item.get("span_id", f"unknown_{i}")
            span_text = item.get("text", "")
            reason = item.get("reason", "No step maps to this behavior span.")
            diags.append(
                CompileDiagnostic(
                    diagnostic_id=f"diag_um_{i:04d}",
                    kind="unmapped_behavior_span",
                    severity="warning",
                    message=(
                        f"Behavior span '{span_id}' "
                        f"('{span_text[:80]}') was not mapped to a "
                        f"step: {reason}"
                    ),
                    target_ref=f"span:{span_id}",
                    source_span_ids=[span_id],
                    blocks_rendering=False,
                    blocks_completion=True,
                )
            )
        return diags

    # ------------------------------------------------------------------
    # 2. missing_handler
    # ------------------------------------------------------------------

    @staticmethod
    def _diagnose_missing_handlers(input: AnalyzeInput) -> list[CompileDiagnostic]:
        """Exception flows that lack a handler step.

        No-demand guard: only exception flows with non-empty condition_text
        are checked.  A flow with empty condition is compiler-fabricated.
        """
        diags: list[CompileDiagnostic] = []
        worker = input.worker
        if worker is None:
            return diags

        for idx, exc in enumerate(worker.exception_flows):
            if not exc.condition_text:
                continue  # compiler-fabricated, not demanded by source

            # Check for a renderable handler step in the (post-gate) worker
            has_handler = any(
                s.flow_ref == exc.flow_id for s in worker.steps
            )
            if has_handler:
                continue

            diags.append(
                CompileDiagnostic(
                    diagnostic_id=f"diag_mh_{len(diags):04d}",
                    kind="missing_handler",
                    severity="warning",
                    message=(
                        f"Exception flow '{exc.flow_id}' "
                        f"('{exc.condition_text[:80]}') has no "
                        f"renderable handler step."
                    ),
                    target_ref=f"exception_flow:{exc.flow_id}",
                    source_span_ids=[],
                    suggested_resolution=(
                        f"Add a handler step for "
                        f"'{exc.condition_text}', or mark this "
                        f"exception as acknowledged without handling."
                    ),
                    blocks_rendering=False,
                    blocks_completion=True,
                )
            )

        # Child workers
        for child in worker.child_workers:
            for exc in child.exception_flows:
                if not exc.condition_text:
                    continue
                has_handler = any(
                    s.flow_ref == exc.flow_id for s in child.steps
                )
                if has_handler:
                    continue

                diags.append(
                    CompileDiagnostic(
                        diagnostic_id=f"diag_mh_{len(diags):04d}",
                        kind="missing_handler",
                        severity="warning",
                        message=(
                            f"Child worker '{child.worker_name}' "
                            f"exception flow '{exc.flow_id}' "
                            f"('{exc.condition_text[:80]}') has no "
                            f"renderable handler step."
                        ),
                        target_ref=(
                            f"worker:{child.worker_name}."
                            f"exception_flow:{exc.flow_id}"
                        ),
                        source_span_ids=[],
                        suggested_resolution=(
                            f"Add a handler step for "
                            f"'{exc.condition_text}' in child worker "
                            f"'{child.worker_name}'."
                        ),
                        blocks_rendering=False,
                        blocks_completion=True,
                    )
                )

        return diags

    # ------------------------------------------------------------------
    # 3. missing_output_producer
    # ------------------------------------------------------------------

    @staticmethod
    def _diagnose_missing_output_producers(
        input: AnalyzeInput,
    ) -> list[CompileDiagnostic]:
        """Required outputs without a renderable producer.

        Uses ProducerIndex for consistent renderability classification.
        No-demand guard: only checks when required outputs exist.
        """
        diags: list[CompileDiagnostic] = []
        resources = input.resources
        producer_index = input.producer_index
        symbol_table = input.symbol_table

        if resources is None or producer_index is None:
            return diags

        required_outputs = [
            v.name for v in resources.variables
            if v.required and v.source == "output"
        ]
        if not required_outputs:
            return diags

        for idx, output in enumerate(required_outputs):
            if producer_index.is_produced(output):
                continue

            var = (symbol_table.variables.get(output)
                   if symbol_table else None)
            description = var.description if var else output

            diags.append(
                CompileDiagnostic(
                    diagnostic_id=f"diag_mp_{idx:04d}",
                    kind="missing_output_producer",
                    severity="warning",
                    message=(
                        f"Required output '{output}' ({description}) "
                        f"has no source-backed or valid-handoff-backed "
                        f"producer."
                    ),
                    target_ref=f"variable:{output}",
                    source_span_ids=[],
                    suggested_resolution=(
                        f"Add a source-backed step that produces "
                        f"'{output}', or mark it as optional."
                    ),
                    blocks_rendering=False,
                    blocks_completion=True,
                )
            )

        return diags

    # ------------------------------------------------------------------
    # 4. type_or_contract_ambiguity
    # ------------------------------------------------------------------

    @staticmethod
    def _diagnose_type_contract_ambiguities(
        input: AnalyzeInput,
    ) -> list[CompileDiagnostic]:
        """Commands with unclear or incomplete contract evidence.

        - CALL_API without a named API reference
        - CALL_API referencing an undeclared API
        - INVOKE_WORKER without a concrete worker target
        - REQUEST_INPUT without source-span evidence
        """
        diags: list[CompileDiagnostic] = []
        declared_apis = input.declared_apis

        for idx, step in enumerate(input.steps):
            kind = ""
            detail = ""
            blocks_render = False

            if step.command_type == "CALL_API" and not step.integration_ref:
                kind = "type_or_contract_ambiguity"
                detail = "CALL_API step has no integration_ref (API name)"
                blocks_render = True
            elif (
                step.command_type == "CALL_API"
                and step.integration_ref
                and declared_apis is not None
                and step.integration_ref not in declared_apis
            ):
                kind = "type_or_contract_ambiguity"
                detail = (
                    f"CALL_API references undeclared API "
                    f"'{step.integration_ref}'"
                )
                blocks_render = True
            elif (
                step.command_type == "INVOKE_WORKER"
                and not step.integration_ref
            ):
                kind = "type_or_contract_ambiguity"
                detail = (
                    "INVOKE_WORKER step has no concrete worker target"
                )
                blocks_render = True
            elif (
                step.command_type == "REQUEST_INPUT"
                and not step.source_span_ids
            ):
                kind = "type_or_contract_ambiguity"
                detail = (
                    "REQUEST_INPUT step has no source-span evidence — "
                    "may be an assumed interaction"
                )
                blocks_render = False

            if not kind:
                continue

            diags.append(
                CompileDiagnostic(
                    diagnostic_id=f"diag_tc_{idx:04d}",
                    kind=kind,
                    severity="warning",
                    message=(
                        f"Step '{step.step_id}' ({step.command_type}): "
                        f"{detail}."
                    ),
                    target_ref=f"step:{step.step_id}",
                    source_span_ids=list(step.source_span_ids),
                    suggested_resolution=(
                        "Provide the missing contract detail, or "
                        "remove this step."
                    ),
                    blocks_rendering=blocks_render,
                    blocks_completion=True,
                )
            )

        return diags

    # ------------------------------------------------------------------
    # 5. assumed_command_not_renderable
    # ------------------------------------------------------------------

    @staticmethod
    def _diagnose_assumed_commands(
        input: AnalyzeInput,
    ) -> list[CompileDiagnostic]:
        """Steps that lack source evidence and are not legitimate scaffolding.

        A step is assumed/synthetic when:
        - source_span_ids is empty, AND
        - handoff_id is not in valid_handoff_ids, AND
        - metadata origin is not compiler_unpack.
        """
        diags: list[CompileDiagnostic] = []
        valid_ids = input.valid_handoff_ids

        for idx, step in enumerate(input.steps):
            if step.source_span_ids:
                continue
            if (
                step.handoff_id is not None
                and valid_ids is not None
                and step.handoff_id in valid_ids
            ):
                continue
            # Legacy: handoff steps with no validity set are accepted
            if step.handoff_id is not None and valid_ids is None:
                continue
            if step.metadata.get("origin") == "compiler_unpack":
                continue

            diags.append(
                CompileDiagnostic(
                    diagnostic_id=f"diag_ac_{idx:04d}",
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
                    suggested_resolution=(
                        "Provide a source span that describes this "
                        "behavior, or remove the step if the behavior "
                        "is not required."
                    ),
                    blocks_rendering=True,
                    blocks_completion=True,
                )
            )

        return diags
