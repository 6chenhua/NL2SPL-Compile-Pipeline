"""Stage 1: SpanSlicer - Split text into semantic spans."""

from __future__ import annotations

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


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

        # 1. Build prompts
        system_prompt = load_prompt("stage1")
        user_prompt = f"""请将以下文本切分为语义完整的 span：

---
{raw_text}
---

输出 JSON："""

        # 2. Call LLM
        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise StageError(
                message=f"LLM call failed in {self.name}: {e}",
                stage=self.name,
            ) from e

        # 3. Parse result
        spans = []
        spans_data = result.get("spans", [])

        for item in spans_data:
            try:
                span = SpanIR(
                    span_id=item["span_id"],
                    text=item["text"],
                )
                spans.append(span)
            except KeyError as e:
                self.logger.warning("Missing field in span data: %s", e)
                continue
            except ValueError as e:
                self.logger.warning("Invalid span data: %s", e)
                continue

        self.logger.info("Created %d spans from %d raw items", len(spans), len(spans_data))

        # 4. Save checkpoint
        self.save_checkpoint({
            "raw_text_length": len(raw_text),
            "spans_count": len(spans),
            "spans": [s.to_dict() for s in spans],
        })

        return spans

    def _execute_canonical(self, canonical_input: CanonicalCompileInput) -> list[SpanIR]:
        """Create packet- and section-aware spans without dropping section text."""
        self.logger.info(
            "Starting adapter-aware span slicing for schema %s",
            canonical_input.source_schema,
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
        self.save_checkpoint({
            "source_schema": canonical_input.source_schema,
            "raw_text_length": len(canonical_input.raw_text),
            "spans_count": len(spans),
            "spans": [s.to_dict() for s in spans],
        })
        return spans
