"""Stage 1: SpanSlicer - Split text into semantic spans."""

from __future__ import annotations

import re

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage

# ──────────────────────────────────────────────────────────────────────────────
# Module-level constants for structural pre-slicing
# ──────────────────────────────────────────────────────────────────────────────

_ORGANIZATIONAL_TITLES: frozenset[str] = frozenset({
    "task family",
    "inputs for each run",
    "required outputs",
    "reusable process",
    "policies",
    "failure handling",
    "delegation policy",
})
# ⚠️ SYNC CONSTRAINT: This set MUST stay identical to the whitelist in
# prompts/stage1_system.txt (Rule 3). Any modification must be applied
# to both locations simultaneously.

_ORGANIZATIONAL_KEYWORDS: re.Pattern = re.compile(
    r'^(inputs?|outputs?|polic(?:y|ies)|process|procedure|'
    r'requirements?|failures?|delegation|prerequisites?|'
    r'steps?|actions?|constraints?)\b',
    re.IGNORECASE,
)

_PLACEHOLDER_VALUES: frozenset[str] = frozenset({
    "none", "n/a", "na", "not applicable",
})

_SECTION_PREFIX_RE: re.Pattern = re.compile(
    r'^\[Section:\s*(.+?)\]\s*\n(.*)$', re.DOTALL
)


def _is_organizational(title: str) -> bool:
    """Return True if title is an organizational header (not semantic content).

    Level 1: exact match against the known-domain whitelist.
    Level 2: keyword-pattern match for new-domain generalisation.
    """
    normalized = title.strip().lower()
    if normalized in _ORGANIZATIONAL_TITLES:
        return True
    return bool(_ORGANIZATIONAL_KEYWORDS.match(normalized))


class SpanSlicer(PipelineStage[str | CanonicalCompileInput, list[SpanIR]]):
    """Split raw text into semantic spans.

    This stage takes raw text and splits it into semantic spans,
    where each span represents a complete semantic unit.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage1_span_slicer"

    def execute(self, input_data: str | CanonicalCompileInput) -> list[SpanIR]:
        """Execute span slicing.

        Args:
            input_data: Raw text to split into spans

        Returns:
            List of SpanIR objects

        Raises:
            StageError: If slicing fails
        """
        if isinstance(input_data, CanonicalCompileInput):
            if input_data.source_schema == "generic_nl":
                raw_text = input_data.raw_text
            else:
                return self._execute_canonical(input_data)
        else:
            raw_text = input_data
        self.logger.info("Starting span slicing for text of length %d", len(raw_text))

        # ── Stage A: Deterministic pre-slicing ───────────────────────────────
        try:
            pre_slices, residual_blocks = self._pre_slice_structural(raw_text)
            self.logger.info(
                "Pre-slicing: %d spans, %d residual blocks",
                len(pre_slices), len(residual_blocks),
            )
        except Exception as exc:
            self.logger.warning(
                "Pre-slicing failed (%s); falling back to full LLM path.", exc
            )
            pre_slices, residual_blocks = [], [raw_text]

        # ── Stage B: LLM for residual blocks (per-block calls) ───────────────
        llm_spans: list[SpanIR] = []
        if any(b.strip() for b in residual_blocks):
            try:
                llm_spans = self._call_llm_for_residual(residual_blocks)
                self.logger.info("LLM residual slicing: %d spans", len(llm_spans))
            except Exception as exc:
                self.logger.warning(
                    "Residual LLM call failed (%s); skipping residual spans.", exc
                )
                llm_spans = []

        # ── Stage C: Merge and renumber ───────────────────────────────────────
        all_spans = pre_slices + llm_spans
        for i, span in enumerate(all_spans):
            span.span_id = f"s{i + 1}"

        # ── Stage D: Coverage validation ─────────────────────────────────────
        coverage_diags = self._validate_coverage(raw_text, all_spans)

        # ── Checkpoint ────────────────────────────────────────────────────────
        self.save_checkpoint({
            "raw_text_length": len(raw_text),
            "spans_count": len(all_spans),
            "pre_slices_count": len(pre_slices),
            "llm_spans_count": len(llm_spans),
            "spans": [s.to_dict() for s in all_spans],
            "diagnostics": coverage_diags,
        })

        self.logger.info(
            "Created %d spans (%d pre-sliced, %d LLM residual) from text of length %d",
            len(all_spans), len(pre_slices), len(llm_spans), len(raw_text),
        )

        return all_spans

    def _execute_canonical(self, canonical_input: CanonicalCompileInput) -> list[SpanIR]:
        """Create packet- and section-aware spans without dropping section text."""
        self.logger.info(
            "Starting adapter-aware span slicing for schema %s",
            canonical_input.source_schema,
        )
        self.validated_records = []
        self.stage1_segmentation_diagnostics = []
        self.stage1_segmentation_warnings = []

        # Active Mode (Phase E)
        mode = getattr(self.config.stage1, "mode", "legacy_packet_passthrough")
        if mode == "llm_source_constrained":
            try:
                self.logger.info("Running active mode LLM span segmentation...")
                from nl2spl.pipeline.stages.stage1_segmentation import (
                    LLMSourceConstrainedSegmenter,
                    SourceSectionReconstructor,
                    Stage1SegmentationValidator,
                )
                reconstructor = SourceSectionReconstructor()
                source_buffers = reconstructor.reconstruct(canonical_input)
                segmenter = LLMSourceConstrainedSegmenter(self.client)

                validator = Stage1SegmentationValidator()
                validated_records = []
                diags = []
                warnings = []
                validation_feedback: str | None = None
                max_retries = max(0, int(getattr(self.config.stage1, "max_retries", 0)))
                for attempt in range(max_retries + 1):
                    raw_proposals = segmenter.segment(
                        canonical_input,
                        source_buffers,
                        validation_feedback=validation_feedback,
                    )
                    validated_records, diags, warnings = validator.validate(
                        raw_proposals, source_buffers
                    )
                    if not diags:
                        break
                    if attempt >= max_retries:
                        break
                    validation_feedback = "\n".join(
                        f"- {d.kind}: {d.message}" for d in diags
                    )
                    self.logger.warning(
                        "Stage 1 segmentation validation failed on attempt %d/%d; retrying.",
                        attempt + 1,
                        max_retries + 1,
                    )
                self.stage1_segmentation_warnings = list(warnings)

                if diags:
                    self.stage1_segmentation_diagnostics = list(diags)
                    self.logger.error(
                        "Stage 1 segmentation validation failed with %d errors.",
                        len(diags),
                    )
                    for d in diags:
                        self.logger.error("Diagnostic [%s]: %s", d.kind, d.message)
                    self.logger.warning(
                        "Ignoring invalid LLM segmentation and falling back to "
                        "legacy span slicing. Downstream guard-only filters remain active."
                    )
                else:
                    spans: list[SpanIR] = []
                    for record in validated_records:
                        span = SpanIR(
                            span_id=record.span_id,
                            text=record.span_text,
                            source_section_id=record.source_section_id,
                            source_packet_id=(
                                record.parent_packet_ids[0]
                                if record.parent_packet_ids
                                else None
                            ),
                            guard_text_exact=record.guard_text_exact,
                            action_text_exact=record.action_text_exact,
                            segmentation_kind=record.segmentation_kind,
                        )
                        spans.append(span)

                    self.validated_records = validated_records
                    self.logger.info("Created %d validated LLM spans", len(spans))
                    checkpoint_content = {
                        "source_schema": canonical_input.source_schema,
                        "raw_text_length": len(canonical_input.raw_text),
                        "spans_count": len(spans),
                        "spans": [s.to_dict() for s in spans],
                        "stage1_segmentation_records": [
                            r.to_dict() for r in validated_records
                        ],
                        "span_segmentation_records": [
                            r.to_dict() for r in validated_records
                        ],
                    }
                    self.save_checkpoint(checkpoint_content)
                    return spans
            except Exception as exc:
                self.logger.warning("LLM segmentation active path failed. Error: %s", exc)
                self.stage1_segmentation_diagnostics = [
                    CompileDiagnostic(
                        diagnostic_id="diag_stage1_llm_segmentation_failed",
                        kind="stage1_llm_segmentation_failed",
                        severity="warning",
                        message=(
                            "Stage 1 LLM source-constrained segmentation failed; "
                            f"legacy packet passthrough fallback was used. Error: {exc}"
                        ),
                        target_ref="stage1:source_segmentation",
                        source_span_ids=[],
                        blocks_rendering=False,
                        blocks_completion=True,
                    )
                ]
                self.logger.warning(
                    "Falling back to legacy span slicing due to execution failure."
                )

        spans: list[SpanIR] = []
        next_id = 1
        covered_section_ids: set[str] = set()

        for packet in canonical_input.semantic_packets:
            spans.append(
                SpanIR(
                    span_id=f"s{next_id}",
                    text=packet.text,
                    source_section_id=packet.source_section_id,
                    source_packet_id=packet.packet_id,
                )
            )
            next_id += 1
            covered_section_ids.add(packet.source_section_id)

        for section in canonical_input.raw_sections:
            if section.section_id in covered_section_ids:
                continue
            if not section.text.strip():
                continue
            spans.append(
                SpanIR(
                    span_id=f"s{next_id}",
                    text=section.text,
                    source_section_id=section.section_id,
                )
            )
            next_id += 1

        self.logger.info("Created %d adapter-aware spans", len(spans))

        # Integrate shadow mode logic (Phase B & D)
        mode = getattr(self.config.stage1, "mode", "legacy_packet_passthrough")
        shadow_checkpoint_data = {}
        if mode == "llm_source_constrained_shadow":
            try:
                self.logger.info("Running shadow mode span segmentation...")
                from nl2spl.pipeline.stages.stage1_segmentation import (
                    LLMSourceConstrainedSegmenter,
                    SourceSectionReconstructor,
                    Stage1SegmentationValidator,
                    Stage1ShadowReporter,
                )
                reconstructor = SourceSectionReconstructor()
                source_buffers = reconstructor.reconstruct(canonical_input)
                segmenter = LLMSourceConstrainedSegmenter(self.client)
                raw_proposals = segmenter.segment(canonical_input, source_buffers)

                validator = Stage1SegmentationValidator()
                shadow_records, shadow_diags, shadow_warnings = validator.validate(
                    raw_proposals, source_buffers
                )

                shadow_report = Stage1ShadowReporter.generate_report(
                    spans, shadow_records, shadow_diags, source_buffers
                )

                self.logger.info(
                    "Shadow mode segmentation completed. Match: %s",
                    shadow_report["internal_comms_guarded_action_match"],
                )

                # Format source buffers dict for serialization
                buffers_serializable = {
                    sec_id: {
                        "source_section_id": buf.source_section_id,
                        "normalized_text": buf.normalized_text,
                        "packet_ranges": [
                            {
                                "packet_id": pr.packet_id,
                                "source_section_id": pr.source_section_id,
                                "normalized_char_start": pr.normalized_char_start,
                                "normalized_char_end": pr.normalized_char_end,
                            }
                            for pr in buf.packet_ranges
                        ]
                    }
                    for sec_id, buf in source_buffers.items()
                }

                shadow_checkpoint_data = {
                    "stage1_shadow_segmentation_records": [r.to_dict() for r in shadow_records],
                    "stage1_shadow_segmentation_payload": {
                        "records": [r.to_dict() for r in shadow_records],
                        "diagnostics": [
                            {
                                "diagnostic_id": d.diagnostic_id,
                                "kind": d.kind,
                                "message": d.message,
                                "severity": d.severity,
                                "target_ref": d.target_ref,
                                "metadata": d.metadata,
                            }
                            for d in shadow_diags
                        ],
                        "warnings": shadow_warnings,
                    },
                    "stage1_shadow_segmentation_report": shadow_report,
                    "stage1_shadow_source_buffers": buffers_serializable,
                }
            except Exception as exc:
                self.logger.warning("Stage 1 shadow mode execution failed: %s", exc)

        checkpoint_content = {
            "source_schema": canonical_input.source_schema,
            "raw_text_length": len(canonical_input.raw_text),
            "spans_count": len(spans),
            "spans": [s.to_dict() for s in spans],
        }
        checkpoint_content.update(shadow_checkpoint_data)
        self.save_checkpoint(checkpoint_content)
        return spans

    # ──────────────────────────────────────────────────────────────────────
    # Helper methods for deterministic pre-slicing (Phase 2)
    # ──────────────────────────────────────────────────────────────────────

    def _pre_slice_structural(
        self, raw_text: str
    ) -> tuple[list[SpanIR], list[str]]:
        """Deterministically slice structurally-marked content.

        Returns:
            pre_slices: SpanIR list with span_id="" (reassigned by execute()).
            residual_blocks: Natural-language blocks prepended with
                             "[Section: X]\\n" headers for LLM context.
        """
        section_context: str | None = None
        pre_slices: list[SpanIR] = []
        residual_blocks: list[str] = []
        current_block_lines: list[str] = []
        current_block_context: str | None = None

        def _flush_block() -> None:
            nonlocal current_block_lines, current_block_context
            if current_block_lines:
                block_text = "\n".join(current_block_lines)
                if current_block_context:
                    residual_blocks.append(
                        f"[Section: {current_block_context}]\n{block_text}"
                    )
                else:
                    residual_blocks.append(block_text)
            current_block_lines.clear()
            current_block_context = None

        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped:
                _flush_block()
                continue

            # ── Markdown headers ──────────────────────────────────────────────
            if m := re.match(r'^#{1,6}\s+(.+)$', stripped):
                _flush_block()
                title = m.group(1).strip()
                if _is_organizational(title):
                    section_context = title  # track context, no span
                else:
                    span = SpanIR(span_id="", text=title,
                                  section_context=section_context)
                    pre_slices.append(span)
                continue

            # ── Bold **Label:** (same-line content only) ──────────────────────
            if m := re.match(r'^\*\*(.+?):\*\*\s*(.+)$', stripped):
                _flush_block()
                label_text = m.group(2).strip()
                span = SpanIR(span_id="", text=label_text,
                              section_context=section_context)
                if label_text.lower() in _PLACEHOLDER_VALUES:
                    span.is_placeholder = True
                pre_slices.append(span)
                continue

            # ── Bold **Label:** with no same-line content → residual ──────────
            if re.match(r'^\*\*(.+?):\*\*\s*$', stripped):
                _flush_block()
                # Multi-line Label: content will be accumulated as residual
                if not current_block_lines:
                    current_block_context = section_context
                # Don't append the label line itself; subsequent content lines
                # will be flushed to residual_blocks
                continue

            # ── Bullet items ──────────────────────────────────────────────────
            if m := re.match(r'^[-*+]\s+(.+)$', stripped):
                _flush_block()
                item_text = m.group(1).strip()
                span = SpanIR(span_id="", text=item_text,
                              section_context=section_context)
                if item_text.lower() in _PLACEHOLDER_VALUES:
                    span.is_placeholder = True
                pre_slices.append(span)
                continue

            # ── Ordered list items ────────────────────────────────────────────
            if m := re.match(r'^\d+\.\s+(.+)$', stripped):
                _flush_block()
                step_text = m.group(1).strip()
                span = SpanIR(span_id="", text=step_text,
                              section_context=section_context)
                pre_slices.append(span)
                continue

            # ── Unmatched line → accumulate as residual block ─────────────────
            if not current_block_lines:
                current_block_context = section_context
            current_block_lines.append(stripped)

        _flush_block()
        return pre_slices, residual_blocks

    def _call_llm_for_residual(
        self, residual_blocks: list[str]
    ) -> list[SpanIR]:
        """Process each residual block with a separate LLM call.

        Per-block calls ensure each span's section_context comes from
        exactly one source (its own block's [Section: X] prefix),
        eliminating cross-section fallback ambiguity.
        """
        all_spans: list[SpanIR] = []

        for block in residual_blocks:
            if not block.strip():
                continue

            # Extract section context and text from the block prefix
            m = _SECTION_PREFIX_RE.match(block.strip())
            if m:
                block_context: str | None = m.group(1)
                block_text = m.group(2).strip()
            else:
                block_context = None
                block_text = block.strip()

            if not block_text:
                continue

            system_prompt = load_prompt("stage1")
            user_prompt = (
                f"Split the following text into semantically complete spans.\n\n"
                f"---\n{block_text}\n---\n\nOutput valid JSON:"
            )

            try:
                result = self.client.call_json(
                    stage_name=self.name,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
            except Exception as exc:
                self.logger.warning(
                    "LLM call for residual block failed (%s); skipping block.",
                    exc,
                )
                continue

            for item in result.get("spans", []):
                try:
                    text = item["text"]
                except KeyError:
                    self.logger.warning("Residual span missing 'text' field: %s", item)
                    continue
                # LLM output takes priority; null falls back to this block's prefix
                ctx = item.get("section_context") or block_context
                all_spans.append(SpanIR(span_id="", text=text, section_context=ctx))

        return all_spans

    def _validate_coverage(
        self, raw_text: str, all_spans: list[SpanIR]
    ) -> list[dict]:
        """Validate that spans cover raw_text content sufficiently.

        Uses single-direction Jaccard coverage (raw→span).
        Only punctuation/marker tokens are exempt; organisational-title
        words are NOT exempt (avoiding false-high coverage scores).

        Returns a list of diagnostic dicts (may be empty).
        """
        structural_tokens = {"##", "#", ":", "**", "-", "*", "+"}

        raw_tokens = set(raw_text.lower().split())
        span_tokens = set(" ".join(s.text for s in all_spans).lower().split())

        effective_raw = raw_tokens - structural_tokens
        effective_span = span_tokens - structural_tokens
        overlap = effective_raw & effective_span

        denominator = max(len(effective_raw), 1)
        coverage = len(overlap) / denominator

        diagnostics: list[dict] = []

        if coverage < 0.80:
            missing_sample = list(effective_raw - effective_span)[:20]
            diagnostics.append({
                "kind": "coverage_error",
                "severity": "error",
                "coverage": round(coverage, 4),
                "missing_tokens_sample": missing_sample,
                "message": (
                    f"Span coverage is {coverage:.0%} (threshold: 80%). "
                    "Significant content may be missing from spans."
                ),
            })
            self.logger.error("Coverage error: %.0f%% (< 80%%)", coverage * 100)
        elif coverage < 0.90:
            missing_sample = list(effective_raw - effective_span)[:10]
            diagnostics.append({
                "kind": "coverage_warning",
                "severity": "warning",
                "coverage": round(coverage, 4),
                "missing_tokens_sample": missing_sample,
                "message": (
                    f"Span coverage is {coverage:.0%} (threshold: 90%)."
                ),
            })
            self.logger.warning("Coverage warning: %.0f%% (< 90%%)", coverage * 100)

        return diagnostics
