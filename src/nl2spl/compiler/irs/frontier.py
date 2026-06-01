"""Frontier and cutline types for IRS v6.

Provides FrontierStatus and CutlineReason for expressing partial construct
evaluation boundaries in future recursive IRS checking.
"""

from typing import Literal

FrontierStatus = Literal[
    "continue",
    "leaf",
    "cutline_partial",
    "cutline_blocked",
]

CutlineReason = Literal[
    "missing_required_for_complete",
    "no_source_demand",
    "promotion_blocked",
    "non_renderable_candidate",
    "blocked_by_gate",
]
