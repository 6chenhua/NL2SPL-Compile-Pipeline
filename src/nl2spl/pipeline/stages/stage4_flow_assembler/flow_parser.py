"""Stage 4: FlowAssembler - FlowParserMixin (parsing alternative, exception, and delegation flows)."""

from __future__ import annotations

from typing import Any

from nl2spl.ir.flow_structure_ir import (
    AlternativeFlow,
    DelegationCandidate,
    ExceptionFlow,
)


class FlowParserMixin:
    """Mixin containing flow parsing methods."""

    def _parse_alternative_flows(self, result: dict[str, Any]) -> list[AlternativeFlow]:
        """Parse alternative flow objects from LLM JSON."""
        alternative_flows: list[AlternativeFlow] = []
        for flow_data in result.get("alternative_flows", []):
            try:
                alternative_flows.append(
                    AlternativeFlow(
                        flow_id=flow_data["flow_id"],
                        condition_text=flow_data["condition_text"],
                        spans=flow_data["spans"],
                    )
                )
            except KeyError as e:
                self.logger.warning("Missing field in alternative flow data: %s", e)
        return alternative_flows

    def _parse_exception_flows(self, result: dict[str, Any]) -> list[ExceptionFlow]:
        """Parse exception flow objects from LLM JSON."""
        exception_flows: list[ExceptionFlow] = []
        for flow_data in result.get("exception_flows", []):
            try:
                exception_flows.append(
                    ExceptionFlow(
                        flow_id=flow_data["flow_id"],
                        condition_text=flow_data["condition_text"],
                        spans=flow_data["spans"],
                    )
                )
            except KeyError as e:
                self.logger.warning("Missing field in exception flow data: %s", e)
        return exception_flows

    def _parse_delegation_candidates(
        self,
        result: dict[str, Any],
    ) -> list[DelegationCandidate]:
        """Parse legacy delegation candidates."""
        delegation_candidates: list[DelegationCandidate] = []
        for cand_data in result.get("delegation_candidates", []):
            try:
                delegation_candidates.append(
                    DelegationCandidate(
                        candidate_id=cand_data["candidate_id"],
                        spans=cand_data["spans"],
                        reason=cand_data["reason"],
                        suggested_type=cand_data["suggested_type"],
                        input_variables=cand_data.get("input_variables", []),
                        output_variables=cand_data.get("output_variables", []),
                    )
                )
            except KeyError as e:
                self.logger.warning(
                    "Missing field in delegation candidate data: %s",
                    e,
                )
        return delegation_candidates
