"""Stage 1 Span Segmentation Support Package."""

from __future__ import annotations

from nl2spl.pipeline.stages.stage1_segmentation.config import Stage1SegmentationConfig
from nl2spl.pipeline.stages.stage1_segmentation.source_buffer import (
    SourcePacketRange,
    SourceNormalizationMap,
    SectionSourceBuffer,
    SourceSectionReconstructor,
)
from nl2spl.pipeline.stages.stage1_segmentation.segmentation_payload import (
    LLMSpanSegment,
    SpanSegmentationRecord,
    Stage1SegmentationPayload,
)
from nl2spl.pipeline.stages.stage1_segmentation.llm_segment_parser import LLMSegmentParser
from nl2spl.pipeline.stages.stage1_segmentation.llm_segmenter import LLMSourceConstrainedSegmenter
from nl2spl.pipeline.stages.stage1_segmentation.segmentation_validator import Stage1SegmentationValidator
from nl2spl.pipeline.stages.stage1_segmentation.diagnostics import make_diagnostic
from nl2spl.pipeline.stages.stage1_segmentation.shadow_report import Stage1ShadowReporter
