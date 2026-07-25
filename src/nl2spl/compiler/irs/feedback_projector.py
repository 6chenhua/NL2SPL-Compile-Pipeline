"""Compatibility shim for construct satisfaction feedback rendering.

New code should import from ``nl2spl.compiler.reporting``.
"""

from nl2spl.compiler.reporting.construct_satisfaction_renderer import (
    ConstructSatisfactionFeedbackProjector,
)

__all__ = ["ConstructSatisfactionFeedbackProjector"]
