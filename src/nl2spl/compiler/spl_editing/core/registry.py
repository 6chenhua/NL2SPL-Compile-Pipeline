"""SPL Editing runtime registries.

Runtime registries wire service IDs to implementation objects / factories.
All registries are mutable at setup time (``register()``) and read-only
during the editing session (``get()`` / ``has()``).

No registry calls LLM, reads run artifacts, or modifies IR on
construction.  Registry entries are stored as plain objects — no magic
imports, no lazy instantiation that triggers side effects.
"""

from __future__ import annotations

from typing import Any


class _BaseRegistry:
    """Key-value store with duplicate-registration guard."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._items: dict[str, Any] = {}

    def register(self, key: str, item: Any) -> None:
        if key in self._items:
            raise KeyError(f"{self._name} already has entry for '{key}'")
        self._items[key] = item

    def get(self, key: str) -> Any:
        return self._items[key]

    def has(self, key: str) -> bool:
        return key in self._items

    def list_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))

    def __len__(self) -> int:
        return len(self._items)


# ---------------------------------------------------------------------------
# Public registries
# ---------------------------------------------------------------------------


class PatchRegistry(_BaseRegistry):
    """Registry of ``patch_type`` string -> patch implementation bundle.

    Each entry is expected to be a composite object (validator + applier
    + verifier + previewer) keyed by its ``patch_type`` string (e.g.
    ``"AddExceptionHandlerStep"``).

    The bundle shape is defined in ``patches/base.py``.  Registration
    validates that ``bundle.patch_type == key``.
    """

    def __init__(self) -> None:
        super().__init__("PatchRegistry")

    def register(self, key: str, bundle: object) -> None:
        bundle_patch_type = getattr(bundle, "patch_type", None)
        if bundle_patch_type is not None and bundle_patch_type != key:
            raise ValueError(
                f"PatchBundle.patch_type '{bundle_patch_type}' does not match registry key '{key}'"
            )
        # U3.5/U6: enforce PatchTypeContract
        contract = getattr(bundle, "contract", None)
        if contract is not None:
            contract_type = getattr(contract, "patch_type", None)
            if contract_type is not None and contract_type != key:
                raise ValueError(
                    f"PatchTypeContract.patch_type '{contract_type}' does not "
                    f"match registry key '{key}'"
                )
            # Reject unconfigured default contract.
            # A contract is "unconfigured" when it declares no productions
            # AND no evidence targets — the factory default.
            produces_step = bool(getattr(contract, "produces_step_ir", False))
            produces_handoff = bool(getattr(contract, "produces_handoff_ir", False))
            ev_targets = tuple(getattr(contract, "evidence_targets", ()))
            if not produces_step and not produces_handoff and not ev_targets:
                raise ValueError(
                    f"PatchBundle '{key}' has an unconfigured PatchTypeContract "
                    f"(produces_step_ir=False, produces_handoff_ir=False, "
                    f"evidence_targets=()). "
                    f"Every patch must explicitly declare what artifacts it "
                    f"produces or modifies via its PatchTypeContract."
                )
        super().register(key, bundle)


class HandlerRegistry(_BaseRegistry):
    """Registry of ``handler_id`` -> ``IssueRepairHandler`` instance.

    ``handler_id`` comes from ``RepairCatalogEntry.handler_id`` (e.g.
    ``"missing_handler"``, ``"missing_output_producer"``,
    ``"type_or_contract_ambiguity"``).
    """

    def __init__(self) -> None:
        super().__init__("HandlerRegistry")


class TargetResolverRegistry(_BaseRegistry):
    """Registry of ``target_resolver_id`` -> ``IssueTargetResolver`` instance.

    ``target_resolver_id`` comes from ``RepairCatalogEntry.target_resolver_id``
    (e.g. ``"exception_flow_target"``, ``"required_output_target"``).
    """

    def __init__(self) -> None:
        super().__init__("TargetResolverRegistry")


class ContextBuilderRegistry(_BaseRegistry):
    """Registry of ``context_id`` -> ``RepairContextBuilder`` instance.

    ``context_id`` comes from ``RepairCatalogEntry.context_id`` (e.g.
    ``"exception_flow_context"``, ``"required_output_context"``).
    """

    def __init__(self) -> None:
        super().__init__("ContextBuilderRegistry")


class LLMContextBuilderRegistry(_BaseRegistry):
    """Registry of ``handler_id`` -> ``LLMRepairContextBuilder`` instance.

    LLM context construction is service-owned.  Handlers must not carry
    private builder references or construct prompts themselves.
    """

    def __init__(self) -> None:
        super().__init__("LLMContextBuilderRegistry")


class PromptRendererRegistry(_BaseRegistry):
    """Registry of ``handler_id`` -> ``PromptRenderer`` instance."""

    def __init__(self) -> None:
        super().__init__("PromptRendererRegistry")


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


class SPLEditingRuntimeRegistry:
    """Holds all sub-registries for an editing session.

    Built once at service startup.  Individual sub-registries can be
    populated incrementally as patch families are implemented.
    """

    def __init__(self) -> None:
        self.patches = PatchRegistry()
        self.handlers = HandlerRegistry()
        self.target_resolvers = TargetResolverRegistry()
        self.context_builders = ContextBuilderRegistry()
        self.llm_context_builders = LLMContextBuilderRegistry()
        self.prompt_renderers = PromptRendererRegistry()
