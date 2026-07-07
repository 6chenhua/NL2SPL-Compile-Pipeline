from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from nl2spl.compiler.construct_plan import APICallDemand, APICallPlacementIR
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage7_step_extractor.action_model import (
    ActionCoverageReportIR,
    ExecutableActionIR,
    SourceRangeIR,
    canonicalize_action_text,
)


@dataclass(frozen=True)
class APIResidualActionProjection:
    call_action: ExecutableActionIR | None
    residual_actions: tuple[ExecutableActionIR, ...]
    coverage_report: ActionCoverageReportIR
    diagnostics: tuple[CompileDiagnostic, ...]


class APIResidualActionProjector:
    def project(
        self,
        *,
        call: APICallDemand,
        span_by_id: Mapping[str, SpanIR],
        placement: APICallPlacementIR | None,
    ) -> APIResidualActionProjection:
        # 1. Validate coverage offsets
        coverage_issue = self._validate_coverage(call, span_by_id)
        if coverage_issue is not None:
            diag = CompileDiagnostic(
                diagnostic_id=self._diagnostic_id(call.demand_id, "coverage_ambiguous"),
                kind="stage7_api_residual_coverage_ambiguous",
                severity="warning",
                message=(
                    f"API call demand {call.demand_id} has ambiguous "
                    f"operation coverage: {coverage_issue}"
                ),
                target_ref=f"api_call_demand:{call.demand_id}",
                source_span_ids=list(call.source_span_ids),
                metadata={
                    "call_demand_id": call.demand_id,
                    "coverage_id": (
                        call.operation_coverage[0].coverage_id
                        if call.operation_coverage
                        else ""
                    ),
                    "source_span_ids": list(call.source_span_ids),
                    "reason": coverage_issue,
                },
                blocks_rendering=False,
                blocks_completion=True,
            )
            report = ActionCoverageReportIR(
                report_id=f"rep_{call.demand_id}",
                source_span_id=list(call.source_span_ids)[0] if call.source_span_ids else "",
                covered_ranges=(),
                uncovered_ranges=(),
                overlapping_ranges=(),
                action_ids=(),
                status="ambiguous",
                diagnostics=(diag,),
            )
            return APIResidualActionProjection(
                call_action=None,
                residual_actions=(),
                coverage_report=report,
                diagnostics=(diag,),
            )

        # 2. Determine placement status
        placement_status: Literal["placed", "unplaced", "ambiguous"] = "unplaced"
        flow_ref: str | None = None
        block_ref: str | None = None
        if placement is not None:
            if placement.status in ("placed", "unplaced", "ambiguous"):
                placement_status = placement.status  # type: ignore[assignment]
            flow_ref = placement.flow_ref
            block_ref = placement.block_ref

        # 3. Build CALL_API action
        covered_ranges_list: list[SourceRangeIR] = []
        for cov in call.operation_coverage:
            covered_ranges_list.append(
                SourceRangeIR(
                    source_span_id=cov.source_span_id,
                    char_start=cov.char_start,
                    char_end=cov.char_end,
                    relation=cov.relation or "direct",  # type: ignore[arg-type]
                )
            )

        call_action_text = ""
        # Get action text from first coverage as reference or use action_text
        if call.operation_coverage:
            first_cov = call.operation_coverage[0]
            first_span = span_by_id[first_cov.source_span_id]
            if first_cov.char_start is not None and first_cov.char_end is not None:
                call_action_text = first_span.text[first_cov.char_start : first_cov.char_end]
        if not call_action_text:
            call_action_text = call.action_text or ""

        call_action = ExecutableActionIR(
            action_id=f"act_api_{call.demand_id}",
            action_kind="source_slice",
            source_span_ids=tuple(call.source_span_ids),
            covered_ranges=tuple(covered_ranges_list),
            action_text=call_action_text,
            normalized_action_key=canonicalize_action_text(call_action_text),
            command_type="CALL_API",
            owning_authority="stage7.api_call_materializer",
            source_construct_demand_id=call.demand_id,
            flow_ref=flow_ref,
            block_ref=block_ref,
            placement_status=placement_status,
            output_policy="no_output",
            coverage_status="exact",
        )

        # 4. Calculate residual ranges and build residual action if policy requires
        residual_actions: list[ExecutableActionIR] = []
        uncovered_ranges_list: list[SourceRangeIR] = []
        diagnostics_list: list[CompileDiagnostic] = []
        report_status: Literal[
            "fully_partitioned",
            "has_uncovered_residual",
            "has_incompatible_overlap",
            "ambiguous",
        ] = "fully_partitioned"

        if call.behavior_lowering_policy in (
            "api_call_augments_behavior",
            "keep_residual_behavior_only",
        ):
            # Group coverages by span
            coverage_by_span: dict[str, list[tuple[int, int]]] = {}
            for cov in call.operation_coverage:
                if cov.char_start is not None and cov.char_end is not None:
                    coverage_by_span.setdefault(cov.source_span_id, []).append(
                        (cov.char_start, cov.char_end)
                    )

            # Define sentence splitter helper
            def split_sentences(text: str) -> list[tuple[str, int, int]]:
                sentences = []
                start = 0
                i = 0
                n = len(text)
                while i < n:
                    if text[i] in (".", "!", "?"):
                        if i + 1 == n or text[i + 1].isspace():
                            end = i + 1
                            sentences.append((text[start:end], start, end))
                            start = end
                            while start < n and text[start].isspace():
                                start += 1
                            i = start
                            continue
                    i += 1
                if start < n:
                    sentences.append((text[start:n], start, n))
                return sentences

            # Process each span sentence-by-sentence
            for span_id in call.source_span_ids:
                span_text = span_by_id[span_id].text
                covers = coverage_by_span.get(span_id, [])
                merged_covers = self._merge_ranges(covers)
                sentences = split_sentences(span_text)

                for sent_text, sent_start, sent_end in sentences:
                    # Find coverages that intersect with this sentence
                    sent_covers = []
                    for c_start, c_end in merged_covers:
                        i_start = max(c_start, sent_start)
                        i_end = min(c_end, sent_end)
                        if i_start < i_end:
                            sent_covers.append((i_start, i_end))

                    if sent_covers:
                        cov_min = min(x[0] for x in sent_covers)
                        cov_max = max(x[1] for x in sent_covers)

                        # Check leading uncovered text in this sentence
                        prefix = sent_text[: cov_min - sent_start]
                        cleaned_prefix = prefix.strip(" ,;.")
                        if cleaned_prefix:
                            # Add to uncovered ranges list for transparency
                            uncovered_ranges_list.append(
                                SourceRangeIR(
                                    source_span_id=span_id,
                                    char_start=sent_start,
                                    char_end=cov_min,
                                    relation="derived",
                                )
                            )
                            # Emit ambiguous diagnostic for unclassified leading clause
                            diag = CompileDiagnostic(
                                diagnostic_id=self._diagnostic_id(
                                    call.demand_id, f"ambig_leading_{sent_start}"
                                ),
                                kind="stage7_api_residual_coverage_ambiguous",
                                severity="warning",
                                message=(
                                    f"Unclassified leading uncovered text '{cleaned_prefix}' "
                                    f"in API-covered sentence of span '{span_id}'."
                                ),
                                target_ref=f"api_call_demand:{call.demand_id}",
                                source_span_ids=[span_id],
                                metadata={
                                    "call_demand_id": call.demand_id,
                                    "coverage_id": (
                                        call.operation_coverage[0].coverage_id
                                        if call.operation_coverage
                                        else ""
                                    ),
                                    "source_span_ids": [span_id],
                                    "reason": f"unclassified_leading_clause: {cleaned_prefix}",
                                },
                                blocks_rendering=False,
                                blocks_completion=True,
                            )
                            diagnostics_list.append(diag)

                        # Check trailing uncovered text in this sentence
                        suffix = sent_text[cov_max - sent_start :]
                        cleaned_suffix = suffix.strip(" ,;.")
                        if cleaned_suffix:
                            uncovered_ranges_list.append(
                                SourceRangeIR(
                                    source_span_id=span_id,
                                    char_start=cov_max,
                                    char_end=sent_end,
                                    relation="derived",
                                )
                            )
                            # Emit ambiguous diagnostic for unclassified trailing clause
                            diag = CompileDiagnostic(
                                diagnostic_id=self._diagnostic_id(
                                    call.demand_id, f"ambig_trailing_{sent_start}"
                                ),
                                kind="stage7_api_residual_coverage_ambiguous",
                                severity="warning",
                                message=(
                                    f"Unclassified trailing uncovered text '{cleaned_suffix}' "
                                    f"in API-covered sentence of span '{span_id}'."
                                ),
                                target_ref=f"api_call_demand:{call.demand_id}",
                                source_span_ids=[span_id],
                                metadata={
                                    "call_demand_id": call.demand_id,
                                    "coverage_id": (
                                        call.operation_coverage[0].coverage_id
                                        if call.operation_coverage
                                        else ""
                                    ),
                                    "source_span_ids": [span_id],
                                    "reason": f"unclassified_trailing_clause: {cleaned_suffix}",
                                },
                                blocks_rendering=False,
                                blocks_completion=True,
                            )
                            diagnostics_list.append(diag)
                    else:
                        # Completely uncovered sentence
                        res_text = self._cleanup_residual(sent_text)
                        if res_text:
                            uncovered_ranges_list.append(
                                SourceRangeIR(
                                    source_span_id=span_id,
                                    char_start=sent_start,
                                    char_end=sent_end,
                                    relation="derived",
                                )
                            )
                            residual_action = ExecutableActionIR(
                                action_id=f"act_general_{call.demand_id}_res_{sent_start}",
                                action_kind="residual_slice",
                                source_span_ids=(span_id,),
                                covered_ranges=(
                                    SourceRangeIR(
                                        source_span_id=span_id,
                                        char_start=sent_start,
                                        char_end=sent_end,
                                        relation="derived",
                                    ),
                                ),
                                action_text=res_text,
                                normalized_action_key=canonicalize_action_text(res_text),
                                command_type="GENERAL_COMMAND",
                                owning_authority="stage7.general_command_materializer",
                                flow_ref=flow_ref,
                                block_ref=block_ref,
                                placement_status=placement_status,
                                output_policy="no_output",
                                coverage_status="residual",
                            )
                            residual_actions.append(residual_action)

        if diagnostics_list:
            report_status = "ambiguous"
        elif residual_actions:
            report_status = "has_uncovered_residual"

        action_ids = [call_action.action_id]
        for act in residual_actions:
            action_ids.append(act.action_id)

        report = ActionCoverageReportIR(
            report_id=f"rep_{call.demand_id}",
            source_span_id=list(call.source_span_ids)[0] if call.source_span_ids else "",
            covered_ranges=tuple(covered_ranges_list),
            uncovered_ranges=tuple(uncovered_ranges_list),
            overlapping_ranges=(),
            action_ids=tuple(action_ids),
            status=report_status,
            diagnostics=tuple(diagnostics_list),
        )

        return APIResidualActionProjection(
            call_action=call_action,
            residual_actions=tuple(residual_actions),
            coverage_report=report,
            diagnostics=tuple(diagnostics_list),
        )

    def _validate_coverage(
        self, call: APICallDemand, span_by_id: Mapping[str, SpanIR]
    ) -> str | None:
        if not call.operation_coverage:
            return "operation_coverage_missing"
        for coverage in call.operation_coverage:
            span_id = coverage.source_span_id
            if span_id not in span_by_id:
                return f"span_not_found:{span_id}"
            span_text = span_by_id[span_id].text
            if coverage.char_start is None or coverage.char_end is None:
                return f"coverage_offsets_missing:{coverage.coverage_id}"
            if (
                coverage.char_start < 0
                or coverage.char_end <= coverage.char_start
                or coverage.char_end > len(span_text)
            ):
                return f"coverage_offsets_invalid:{coverage.coverage_id}"
        return None

    def _merge_ranges(self, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        merged: list[tuple[int, int]] = []
        for start, end in sorted(ranges):
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        return merged

    def _cleanup_residual(self, value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip()
        value = re.sub(r",\s*\.", ".", value)
        value = re.sub(r"^(and|then|,|;|\.)\s+", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+(and|then|,|;)$", "", value, flags=re.IGNORECASE)
        value = value.strip(" ,;.")
        if value and value[-1] not in ".!?":
            value = f"{value}."
        return value

    def _diagnostic_id(self, call_demand_id: str, suffix: str) -> str:
        digest = hashlib.sha1(f"{call_demand_id}|{suffix}".encode()).hexdigest()[:10]
        return f"diag_stage7_api_{digest}"
