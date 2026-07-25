"""Compatibility shim for construct frontier/cutline report fields.

New code should import from ``nl2spl.compiler.constructs.satisfaction``.
"""

from nl2spl.compiler.constructs.satisfaction import CutlineReason, FrontierStatus

__all__ = ["CutlineReason", "FrontierStatus"]
