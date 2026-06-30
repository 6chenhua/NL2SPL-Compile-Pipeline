"""IRS v6 Diagnostic Projector — project ConstructSatisfactionReport to CompileDiagnostic.

R2 provides only a skeleton. R3 implements full projection semantics:
- Slot diagnostic_kind -> CompileDiagnostic mapping
- DiagnosticRegistry integration for severity/blocks_completion
- Deterministic diagnostic_id generation
- Deduplication within projection
- Unknown/disabled diagnostic kind handling
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.construct_registry import ConstructSatisfactionReport
from nl2spl.compiler.diagnostic_registry import DiagnosticRegistry
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.ir.diagnostics import CompileDiagnostic

_SAFE_REPORT_METADATA_KEYS = (
    "issue_group_id",
    "repairability",
    "presentation_disposition",
    "validation_authority",
    "nl2spl_renderable",
    "api_contract_validation_status",
    "placeholder_fields",
)


@dataclass
class DiagnosticProjectionResult:
    """Result of projecting IRS reports to compile diagnostics.

    Attributes:
        diagnostics: Projected compile diagnostics
        warnings: Non-fatal warnings during projection
    """

    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DiagnosticProjector:
    """Projects ConstructSatisfactionReport to CompileDiagnostic.

    R3 implementation:
        - Reads slot.diagnostic_kind from reports
        - Uses DiagnosticRegistry for severity/blocks_completion
        - Generates deterministic diagnostic_id
        - Deduplicates within projection
        - Handles unknown/disabled diagnostic kinds with warnings

    Design notes:
        - Projector is stateless, can be reused across runs
        - Context provides additional info for diagnostic formatting
        - Warnings capture projection issues without failing the run
        - Does not infer diagnostic_kind from slot status or report completeness
    """

    def __init__(
        self,
        diagnostic_registry: DiagnosticRegistry | None = None,
    ) -> None:
        """Initialize projector with diagnostic registry.

        Args:
            diagnostic_registry: Registry for diagnostic specs. Defaults to
                DiagnosticRegistry.default() if not provided.
        """
        self._diagnostic_registry = diagnostic_registry or DiagnosticRegistry.default()

    def project(
        self,
        reports: list[ConstructSatisfactionReport],
        context: IRSCheckContext,
    ) -> DiagnosticProjectionResult:
        """Project IRS reports to compile diagnostics.

        Args:
            reports: Construct satisfaction reports from checkers
            context: Pipeline context for additional diagnostic info

        Returns:
            Projection result with diagnostics and warnings

        Notes:
            - Only projects slots with diagnostic_kind set
            - Does not infer diagnostics from missing status or completeness
            - Deduplicates diagnostics within this projection
        """
        diagnostics: list[CompileDiagnostic] = []
        warnings: list[str] = []
        seen_keys: set[tuple] = set()

        for report in reports:
            for slot in report.slots:
                if not slot.diagnostic_kind:
                    continue

                kind = slot.diagnostic_kind

                # Check if diagnostic kind is known
                if not self._diagnostic_registry.has(kind):
                    warnings.append(
                        f"Unknown diagnostic kind '{kind}' for construct={report.construct_id}, "
                        f"slot={slot.slot_name}. Skipping."
                    )
                    continue

                spec = self._diagnostic_registry.get(kind)

                # Check if diagnostic kind is enabled
                if not spec.enabled:
                    warnings.append(
                        f"Disabled diagnostic kind '{kind}' for construct={report.construct_id}, "
                        f"slot={slot.slot_name}. Skipping."
                    )
                    continue

                # Determine source spans (slot takes priority over report)
                # Copy to avoid sharing mutable list with input reports
                source_span_ids = list(slot.source_span_ids or report.source_span_ids)

                # Build dedup key
                dedup_key = (
                    kind,
                    report.construct_id,
                    slot.slot_name,
                    tuple(sorted(source_span_ids)),
                )

                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                # Generate deterministic diagnostic_id
                diagnostic_id = self._generate_diagnostic_id(
                    kind,
                    report.construct_id,
                    slot.slot_name,
                    source_span_ids,
                )

                # Build message
                message = self._build_message(
                    spec.description,
                    slot.explanation,
                    report.construct_id,
                    slot.slot_name,
                )

                # Build missing_slot for structured diagnostic
                missing_slot = MissingSlot(
                    slot_name=slot.slot_name,
                    required_for=(
                        slot.diagnostic_required_for
                        or "complete"
                    ),
                    reason=slot.explanation or spec.description,
                    source_span_ids=source_span_ids,
                )

                # Create diagnostic
                diagnostic = CompileDiagnostic(
                    diagnostic_id=diagnostic_id,
                    kind=kind,
                    severity=spec.default_severity,
                    message=message,
                    target_ref=slot.diagnostic_target_ref or report.construct_id,
                    source_span_ids=source_span_ids,
                    missing_slot=missing_slot,
                    blocks_rendering=(
                        slot.diagnostic_blocks_rendering
                        if slot.diagnostic_blocks_rendering is not None
                        else not report.renderable
                    ),
                    blocks_completion=spec.blocks_completion,
                    suggested_resolution=slot.suggested_resolution,
                )

                # R10 Phase 4A: Project delegation provenance metadata from
                # the construct satisfaction report to the diagnostic so
                # orchestrator selective promotion can use it.
                # Only copies safe provenance keys — does not infer
                # diagnostic kind, severity, or construct semantics.
                safe_provenance_keys = (
                    "original_semantic_role",
                    "original_route_annotation_id",
                    "original_route_annotation_ids",
                    "original_source_span_ids",
                    "synthetic_from_route_annotation",
                    "promotion_candidate_id",
                    "promotion_status",
                )
                for _key in safe_provenance_keys:
                    if _key in report.metadata:
                        diagnostic.metadata[_key] = report.metadata[_key]

                for _key in _SAFE_REPORT_METADATA_KEYS:
                    if _key in report.metadata:
                        diagnostic.metadata[_key] = report.metadata[_key]

                # R1: Write structured IRS reference so SPL Editing can
                # reverse-lookup the construct type, slot, and authority
                # that produced this diagnostic.
                authority = self._authority_from_context(context)
                diagnostic.metadata["irs_ref"] = {
                    "construct_type": report.construct_type,
                    "construct_id": report.construct_id,
                    "slot_name": slot.slot_name,
                    "construct_path": list(report.construct_path),
                    "source_authority": authority,
                }
                diagnostic.metadata["authority"] = authority

                diagnostics.append(diagnostic)

        return DiagnosticProjectionResult(
            diagnostics=diagnostics,
            warnings=warnings,
        )

    def _generate_diagnostic_id(
        self,
        kind: str,
        construct_id: str,
        slot_name: str,
        source_span_ids: list[str],
    ) -> str:
        """Generate deterministic diagnostic ID.

        Args:
            kind: Diagnostic kind
            construct_id: Construct identifier
            slot_name: Slot name
            source_span_ids: Source span IDs

        Returns:
            Deterministic diagnostic ID with 'irs_' prefix
        """
        key = {
            "kind": kind,
            "construct_id": construct_id,
            "slot_name": slot_name,
            "source_span_ids": sorted(source_span_ids),
        }
        key_str = json.dumps(key, sort_keys=True)
        digest = hashlib.sha1(key_str.encode()).hexdigest()[:12]
        return f"irs_{digest}"

    def _build_message(
        self,
        spec_description: str,
        slot_explanation: str | None,
        construct_id: str,
        slot_name: str,
    ) -> str:
        """Build diagnostic message.

        Args:
            spec_description: Default description from diagnostic spec
            slot_explanation: Optional slot-specific explanation
            construct_id: Construct identifier
            slot_name: Slot name

        Returns:
            Formatted diagnostic message
        """
        base_message = slot_explanation if slot_explanation else spec_description
        return f"{base_message} [construct={construct_id}, slot={slot_name}]"

    @staticmethod
    def _authority_from_context(context: IRSCheckContext) -> str:
        """Derive the source authority from the IRS check context.

        Maps stage names to authority labels:
        - ``"post_normalize"`` → ``"post_normalize_irs"``
        - everything else → ``"stage_local_irs"``

        The orchestrator may later promote selected stage-local diagnostics
        to ``"selected_promoted_stage_local_irs"`` by overwriting
        ``metadata["authority"]`` and ``metadata["irs_ref"]["source_authority"]``.
        """
        if context.stage_name == "post_normalize":
            return "post_normalize_irs"
        return "stage_local_irs"
