"""Compatibility shim for compile report rendering.

New code should import from ``nl2spl.compiler.reporting``.
"""

from nl2spl.compiler.reporting.report_renderer import render_report

__all__ = ["render_report"]
