"""Compiler‑owned evidence classification.

This package is neutral w.r.t. SPL Editing — it only reads
``StepIR`` metadata fields.  Gate, ProducerIndex, and IRS
all import from here (dependency direction: compiler authority → evidence).
"""

from __future__ import annotations

from nl2spl.compiler.evidence.step_evidence import (
    StepEvidence,
    StepEvidenceKind,
    classify_step_evidence,
)

__all__ = [
    "StepEvidence",
    "StepEvidenceKind",
    "classify_step_evidence",
]
