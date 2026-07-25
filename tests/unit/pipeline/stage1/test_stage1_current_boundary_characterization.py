"""Unit test locking the current bad span boundary behavior for Stage 1.

Locking the current behavior where the guard 'When enough required information is available'
is split from the action 'produce a draft'.
"""

from __future__ import annotations

from pathlib import Path

from nl2spl.adapters import StructuralNLAdapter
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer


def test_stage1_current_span_boundary_characterization(pipeline_config, mock_client) -> None:
    # 1. Load the real internal_comms text
    input_path = Path("examples/input/internal_comms.txt")
    assert input_path.exists(), "internal_comms.txt must exist"
    raw_text = input_path.read_text(encoding="utf-8")

    # 2. Run the adapter
    canonical = StructuralNLAdapter(None).adapt(raw_text)

    # 3. Run Stage 1 SpanSlicer
    slicer = SpanSlicer(pipeline_config, mock_client)
    spans = slicer.execute(canonical)

    # 4. Find the spans by matching keywords
    # s16 current: retrieve them using approved source recipes... When enough required information is available
    # s17 current: produce a draft. If the user asks for revision
    s16_candidates = [s for s in spans if "When enough required" in s.text]
    s17_candidates = [s for s in spans if "produce a draft" in s.text]

    assert len(s16_candidates) == 1, "Should find the span containing 'When enough required'"
    assert len(s17_candidates) == 1, "Should find the span containing 'produce a draft'"

    s16 = s16_candidates[0]
    s17 = s17_candidates[0]

    # Current bad behavior locks:
    # 'When enough required information is available' is at the tail of s16
    assert s16.text.endswith("When enough required\ninformation is available")
    # 'produce a draft' is at the head of s17
    assert s17.text.startswith("produce a draft")
