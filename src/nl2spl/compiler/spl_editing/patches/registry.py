"""Patch implementation bundle and runtime registry.

Each entry binds a ``patch_type`` string to its five roles.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.compiler.spl_editing.core.model import PatchTypeContract
from nl2spl.compiler.spl_editing.patches.base import (
    PatchApplier,
    PatchPreviewer,
    PatchValidator,
    PatchVerifier,
)


def _default_contract_for(bundle: PatchBundle) -> PatchTypeContract:
    """Derive a minimal contract from the bundle's patch_type.

    Real patch families should override this with explicit
    ``produces_step_ir`` / ``produces_handoff_ir`` / ``evidence_targets``.
    """
    return PatchTypeContract(patch_type=bundle.patch_type)


@dataclass(frozen=True)
class PatchBundle:
    """Implementation bundle for one patch type."""

    patch_type: str
    validator: PatchValidator
    applier: PatchApplier
    verifier: PatchVerifier
    previewer: PatchPreviewer
    contract: PatchTypeContract = field(default=None)  # type: ignore[assignment]
    """Declarative evidence obligation for this patch type.

    Resolution order:
    1. Explicitly provided contract (preferred).
    2. Default-derived from ``patch_type`` (``_default_contract_for``).
    """

    def __post_init__(self) -> None:
        if self.contract is None:
            object.__setattr__(self, "contract", _default_contract_for(self))
