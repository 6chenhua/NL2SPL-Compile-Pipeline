"""Patch implementation bundle and runtime registry.

Each entry binds a ``patch_type`` string to its five roles.
"""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.patches.base import (
    PatchApplier,
    PatchPreviewer,
    PatchValidator,
    PatchVerifier,
)


@dataclass(frozen=True)
class PatchBundle:
    """Implementation bundle for one patch type."""

    patch_type: str
    validator: PatchValidator
    applier: PatchApplier
    verifier: PatchVerifier
    previewer: PatchPreviewer
