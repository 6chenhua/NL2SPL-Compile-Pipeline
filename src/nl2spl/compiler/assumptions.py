"""AssumptionBuilder — generate CompileAssumption records from diagnostics.

Each assumption is a compiler suggestion that was NOT rendered into SPL.
Assumptions link back to their source diagnostic via ``related_diagnostic_id``
so the readable report can present them as related items, not duplicates.
"""

from __future__ import annotations

from nl2spl.compiler.compile_result import CompileAssumption
from nl2spl.ir.diagnostics import CompileDiagnostic


class AssumptionBuilder:
    """Build CompileAssumption records from diagnostics.

    Pure, fixture-testable.  One assumption per diagnostic, with a
    user-facing suggestion for resolving the issue.

    Assumptions are NOT executable SPL — they are report-only guidance.
    """

    def build(
        self,
        diagnostics: list[CompileDiagnostic],
    ) -> list[CompileAssumption]:
        """Build assumption records for every diagnostic that warrants one."""
        assumptions: list[CompileAssumption] = []
        for diag in diagnostics:
            assumption = self._build_one(diag, len(assumptions))
            if assumption is not None:
                assumptions.append(assumption)
        return assumptions

    # ------------------------------------------------------------------
    # Per-kind builders
    # ------------------------------------------------------------------

    def _build_one(
        self, diag: CompileDiagnostic, index: int
    ) -> CompileAssumption | None:
        """Dispatch to the appropriate kind-specific builder."""
        builders = {
            "missing_handler": self._missing_handler,
            "missing_output_producer": self._missing_output_producer,
            "type_or_contract_ambiguity": self._contract_ambiguity,
            "assumed_command_not_renderable": self._assumed_command,
            "unmapped_behavior_span": self._unmapped_span,
            "missing_provenance": self._missing_provenance,
        }
        builder = builders.get(diag.kind)
        if builder is None:
            return None
        return builder(diag, index)

    @staticmethod
    def _base(
        diag: CompileDiagnostic,
        index: int,
        text: str,
        reason: str,
        suggested_resolution: str,
    ) -> CompileAssumption:
        return CompileAssumption(
            assumption_id=f"ASM_{index:04d}",
            target_ref=diag.target_ref or "",
            source_span_ids=list(diag.source_span_ids),
            text=text,
            reason=reason,
            suggested_resolution=suggested_resolution,
            related_diagnostic_id=diag.diagnostic_id,
        )

    # ------------------------------------------------------------------
    # missing_handler
    # ------------------------------------------------------------------

    @classmethod
    def _missing_handler(
        cls, diag: CompileDiagnostic, index: int
    ) -> CompileAssumption:
        target = diag.target_ref or "unknown"
        condition = diag.message[:120]
        return cls._base(
            diag, index,
            text="Exception flow has no handler action. "
                 "The compiler suggests specifying what should happen "
                 "when this failure occurs.",
            reason=(
                f"Source describes a failure condition but does not "
                f"specify how to handle it.  The exception flow is "
                f"preserved in SPL, but no handler command was "
                f"rendered. ({condition})"
            ),
            suggested_resolution=(
                f"Specify the handler action for {target}: "
                f"e.g. ask the user for missing information, "
                f"block finalization, or continue with an "
                f"explicit assumption."
            ),
        )

    # ------------------------------------------------------------------
    # missing_output_producer
    # ------------------------------------------------------------------

    @classmethod
    def _missing_output_producer(
        cls, diag: CompileDiagnostic, index: int
    ) -> CompileAssumption:
        target = diag.target_ref or "unknown"
        return cls._base(
            diag, index,
            text="Required output has no source-backed producer. "
                 "The compiler suggests adding a step that explicitly "
                 "produces this output.",
            reason=(
                "The source requires this output but does not "
                "describe how it should be produced.  The output "
                "is kept in the OUTPUTS contract, but no producer "
                "step was rendered."
            ),
            suggested_resolution=(
                f"Add a source-backed step that produces {target}. "
                f"If the source does not specify how to produce it, "
                f"mark it as optional or remove it from the required "
                f"output contract."
            ),
        )

    # ------------------------------------------------------------------
    # type_or_contract_ambiguity
    # ------------------------------------------------------------------

    @classmethod
    def _contract_ambiguity(
        cls, diag: CompileDiagnostic, index: int
    ) -> CompileAssumption:
        target = diag.target_ref or "unknown"
        return cls._base(
            diag, index,
            text="Command has an ambiguous or incomplete contract. "
                 "The compiler suggests providing the missing "
                 "contract detail.",
            reason=(
                "A command references an API, worker, or input "
                "source that is not fully specified.  The compiler "
                "cannot materialize the command without this "
                "information."
            ),
            suggested_resolution=(
                f"For {target}: provide the missing contract detail "
                f"(API name, worker target, IO bindings, or source "
                f"evidence).  See the related diagnostic for specifics."
            ),
        )

    # ------------------------------------------------------------------
    # assumed_command_not_renderable
    # ------------------------------------------------------------------

    @classmethod
    def _assumed_command(
        cls, diag: CompileDiagnostic, index: int
    ) -> CompileAssumption:
        target = diag.target_ref or "unknown"
        return cls._base(
            diag, index,
            text="Executable command was blocked from rendering "
                 "because it lacks source evidence.  The compiler "
                 "suggests backing it with a source span or removing "
                 "it.",
            reason=(
                "A step claiming executable behavior has no source "
                "backing and is not compiler scaffolding.  The gate "
                "prevented it from entering SPL."
            ),
            suggested_resolution=(
                f"For {target}: provide a source span that describes "
                f"this behavior, or remove the step if it is not "
                f"required."
            ),
        )

    # ------------------------------------------------------------------
    # unmapped_behavior_span
    # ------------------------------------------------------------------

    @classmethod
    def _unmapped_span(
        cls, diag: CompileDiagnostic, index: int
    ) -> CompileAssumption:
        target = diag.target_ref or "unknown"
        return cls._base(
            diag, index,
            text="A behavior span from the source was not mapped "
                 "to any executable step.",
            reason=(
                "The source describes behavior that could not be "
                "translated into a concrete command.  This may be "
                "intentional (policy, non-executable description) "
                "or may indicate missing detail."
            ),
            suggested_resolution=(
                f"For {target}: either add a step implementing this "
                f"behavior, or acknowledge it as non-executable "
                f"context."
            ),
        )

    # ------------------------------------------------------------------
    # missing_provenance
    # ------------------------------------------------------------------

    @classmethod
    def _missing_provenance(
        cls, diag: CompileDiagnostic, index: int
    ) -> CompileAssumption:
        target = diag.target_ref or "unknown"
        if target.startswith("profile:") or diag.metadata.get("profile_item") is True:
            rendered = diag.metadata.get("rendered_profile_item") is True
            return cls._base(
                diag, index,
                text=(
                    "Rendered profile item has no source-backed provenance."
                    if rendered
                    else "Unrendered profile item has no source-backed provenance."
                ),
                reason=(
                    (
                        "The compiler rendered this required profile item, "
                        "but could not trace it to a source span."
                    )
                    if rendered
                    else (
                        "The compiler did not render this optional profile item "
                        "because it could not trace it to a source span."
                    )
                ),
                suggested_resolution=(
                    f"For {target}: add source evidence that justifies this "
                    "profile item, or confirm the assumption-bearing draft."
                ),
            )
        return cls._base(
            diag, index,
            text="Variable has no discoverable source provenance.",
            reason=(
                "The compiler could not trace this variable back "
                "to a source span, adapter hard fact, or producer "
                "step.  Its origin is assumed."
            ),
            suggested_resolution=(
                f"For {target}: add source evidence (a span, "
                f"adapter hint, or producer step) that justifies "
                f"this variable's existence."
            ),
        )
