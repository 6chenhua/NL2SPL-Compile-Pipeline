"""RepairCatalog — runtime index derived from SPLConstructRegistry.

``RepairCatalogBuilder.from_construct_registry()`` scans every slot's
``repair_affordances`` and produces an immutable ``RepairCatalog`` with
multiple lookup axes.  The catalog is pure derivation — no hand-written
mapping, no LLM calls, no patch or verifier imports.

Lookup keys:
    - ``entry_id`` — stable composite key (primary)
    - ``affordance_id``
    - ``construct_type + slot_name + diagnostic_kind``
    - ``DiagnosticIRSRef + diagnostic_kind``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.ir.diagnostics import DiagnosticIRSRef

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairCatalogEntry:
    """One row in the derived repair catalog.

    Each entry links one IRS slot to one repair affordance.  When
    multiple slots share the same ``affordance_id`` (e.g. the four
    ``WORKER_PROMOTION.*`` slots), the catalog produces one entry per
    slot — each with a distinct ``entry_id``.

    Attributes:
        entry_id: Stable composite key
            ``{construct_type}.{slot_name}.{diagnostic_kind}.{affordance_id}``.
        affordance_id: Globally unique repair capability ID.
        construct_type: IRS construct type (e.g. ``EXCEPTION_FLOW``).
        slot_name: Slot within the construct.
        diagnostic_kind: The ``CompileDiagnostic.kind`` this affordance
            addresses (matches ``SlotSpec.missing_diagnostic``).
        handler_id: Identifies the ``IssueRepairHandler``.
        context_id: Identifies the ``RepairContextBuilder``.
        target_resolver_id: Identifies the ``IssueTargetResolver``.
        supported_patch_types: Allowed patch types for the LLM.
        default_patch_type: Default when the user doesn't choose.
        editable_artifacts: Stage-level IRs the applier may modify.
        default_verification_lane: ``"A"`` or ``"B"``.
        required_evidence_kind: Always ``"user_confirmed_repair"``.
        user_facing: Whether exposed in the Diagnostics Console UI.
        description: Human-readable summary.
    """

    entry_id: str
    affordance_id: str
    construct_type: str
    slot_name: str
    diagnostic_kind: str
    handler_id: str | None = None
    context_id: str | None = None
    target_resolver_id: str | None = None
    supported_patch_types: tuple[str, ...] = ()
    default_patch_type: str | None = None
    editable_artifacts: tuple[str, ...] = ()
    default_verification_lane: str = "A"
    required_evidence_kind: str = "user_confirmed_repair"
    user_facing: bool = True
    materialization_plan_id: str | None = None
    selectable_ref_policy_id: str | None = None
    intent_schema_id: str | None = None
    required_context_facts: tuple[str, ...] = ()
    stage_authority: str | None = None
    description: str = ""
    patch_type_metadata: tuple = ()
    """Per-patch-type labels, descriptions, and verification lanes copied from
    ``RepairAffordanceSpec.patch_type_metadata``."""
    repair_strategy_id: str | None = None
    strategy_display_label: str | None = None
    closure_summary: str | None = None
    preview_required: bool = False


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairCatalog:
    """Immutable repair-capability index derived from ``SPLConstructRegistry``.

    Built once at startup / test time.  Provides O(1) lookup by
    ``entry_id``, ``affordance_id``, or
    ``(construct_type, slot_name, diagnostic_kind)``.
    """

    _entries: tuple[RepairCatalogEntry, ...]
    _by_entry_id: dict[str, RepairCatalogEntry] = field(default_factory=dict, compare=False)
    _by_affordance_id: dict[str, list[RepairCatalogEntry]] = field(
        default_factory=dict, compare=False
    )
    _by_construct_slot_kind: dict[tuple[str, str, str], list[RepairCatalogEntry]] = field(
        default_factory=dict, compare=False
    )

    # -- query ---------------------------------------------------------------

    def get(self, entry_id: str) -> RepairCatalogEntry | None:
        """Look up a single entry by its stable composite key."""
        return self._by_entry_id.get(entry_id)

    def find_by_affordance_id(
        self,
        affordance_id: str,
    ) -> tuple[RepairCatalogEntry, ...]:
        """Return all entries for a given affordance ID.

        Multiple entries are returned when several slots share the
        same affordance (e.g. all ``WORKER_PROMOTION.*`` slots).
        """
        return tuple(self._by_affordance_id.get(affordance_id, []))

    def find_by_construct_slot_kind(
        self,
        construct_type: str,
        slot_name: str,
        diagnostic_kind: str,
    ) -> tuple[RepairCatalogEntry, ...]:
        """Return entries matching an exact construct / slot / kind triple."""
        key = (construct_type, slot_name, diagnostic_kind)
        return tuple(self._by_construct_slot_kind.get(key, []))

    def find_by_irs_ref(
        self,
        irs_ref: DiagnosticIRSRef,
        diagnostic_kind: str,
    ) -> tuple[RepairCatalogEntry, ...]:
        """Return entries matching the IRS reference carried by a
        ``CompileDiagnostic.metadata["irs_ref"]`` plus the diagnostic kind.
        """
        return self.find_by_construct_slot_kind(
            construct_type=irs_ref.construct_type,
            slot_name=irs_ref.slot_name,
            diagnostic_kind=diagnostic_kind,
        )

    @property
    def entries(self) -> tuple[RepairCatalogEntry, ...]:
        """All entries in insertion order."""
        return self._entries

    def list_affordance_ids(self) -> tuple[str, ...]:
        """All unique affordance IDs, sorted."""
        return tuple(sorted(self._by_affordance_id))

    def __len__(self) -> int:
        return len(self._entries)

    # -- factory (called by RepairCatalogBuilder) ----------------------------

    @staticmethod
    def _build(
        entries: list[RepairCatalogEntry],
    ) -> RepairCatalog:
        """Build indexes from a flat list of entries."""
        by_entry_id: dict[str, RepairCatalogEntry] = {}
        by_affordance_id: dict[str, list[RepairCatalogEntry]] = {}
        by_csk: dict[tuple[str, str, str], list[RepairCatalogEntry]] = {}

        for e in entries:
            # entry_id must be unique
            if e.entry_id in by_entry_id:
                raise ValueError(
                    f"Duplicate entry_id '{e.entry_id}' — already used by {by_entry_id[e.entry_id]}"
                )
            by_entry_id[e.entry_id] = e

            by_affordance_id.setdefault(e.affordance_id, []).append(e)

            key = (e.construct_type, e.slot_name, e.diagnostic_kind)
            by_csk.setdefault(key, []).append(e)

        return RepairCatalog(
            _entries=tuple(entries),
            _by_entry_id=by_entry_id,
            _by_affordance_id=by_affordance_id,
            _by_construct_slot_kind=by_csk,
        )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class RepairCatalogBuilder:
    """Derive a ``RepairCatalog`` from a ``SPLConstructRegistry``.

    Scans every ``SlotSpec.repair_affordances`` and emits one
    ``RepairCatalogEntry`` per affordance per slot.  No hand-written
    mapping — the registry is the single truth source.
    """

    @staticmethod
    def from_construct_registry(
        registry: SPLConstructRegistry,
        strategy_registry: Any = None,
    ) -> RepairCatalog:
        """Build the catalog by scanning all registered constructs.

        Args:
            registry: A fully populated construct registry (typically
                ``SPLConstructRegistry.default()``).
            strategy_registry: Optional RepairStrategyRegistry.

        Returns:
            An immutable ``RepairCatalog`` with indexed entries.

        Raises:
            ValueError: If an ``entry_id`` collision is detected (should
                never happen with correct registry data).
        """
        entries: list[RepairCatalogEntry] = []

        for construct_type_name in registry.list_constructs():
            irs = registry.get(construct_type_name)
            for slot in irs.slots:
                if not slot.repair_affordances:
                    continue
                diagnostic_kind = slot.missing_diagnostic
                if diagnostic_kind is None:
                    # A slot with repair affordances but no missing_diagnostic
                    # is malformed — skip with a warning in debug, but don't
                    # crash the build.
                    continue
                for aff in slot.repair_affordances:
                    plan_id = aff.materialization_plan_id
                    user_facing = aff.user_facing and bool(plan_id and plan_id.strip())

                    repair_strategy_id = None
                    strategy_display_label = None
                    closure_summary = None
                    preview_required = False

                    if strategy_registry and aff.repair_strategy_id:
                        has_method = getattr(strategy_registry, "has", None)
                        if has_method is not None:
                            if has_method(aff.repair_strategy_id):
                                strategy_spec = strategy_registry.get(aff.repair_strategy_id)
                                if strategy_spec:
                                    repair_strategy_id = aff.repair_strategy_id
                                    strategy_display_label = getattr(strategy_spec, "display_label", None)
                                    closure_summary = getattr(strategy_spec, "closure_summary", None)
                                    preview_required = getattr(strategy_spec, "preview_required", False)
                        else:
                            try:
                                strategy_spec = strategy_registry.get(aff.repair_strategy_id)
                                if strategy_spec:
                                    repair_strategy_id = aff.repair_strategy_id
                                    strategy_display_label = getattr(strategy_spec, "display_label", None)
                                    closure_summary = getattr(strategy_spec, "closure_summary", None)
                                    preview_required = getattr(strategy_spec, "preview_required", False)
                            except Exception as e:
                                if type(e).__name__ not in ("StrategyNotFoundError", "KeyError"):
                                    raise

                    entry = RepairCatalogEntry(
                        entry_id=RepairCatalogBuilder._make_entry_id(
                            construct_type=irs.construct_type,
                            slot_name=slot.slot_name,
                            diagnostic_kind=diagnostic_kind,
                            affordance_id=aff.affordance_id,
                        ),
                        affordance_id=aff.affordance_id,
                        construct_type=irs.construct_type,
                        slot_name=slot.slot_name,
                        diagnostic_kind=diagnostic_kind,
                        handler_id=aff.handler_id,
                        context_id=aff.context_id,
                        target_resolver_id=aff.target_resolver_id,
                        supported_patch_types=aff.supported_patch_types,
                        default_patch_type=aff.default_patch_type,
                        editable_artifacts=aff.editable_artifacts,
                        default_verification_lane=aff.default_verification_lane,
                        required_evidence_kind=aff.required_evidence_kind,
                        user_facing=user_facing,
                        description=aff.description,
                        patch_type_metadata=aff.patch_type_metadata,
                        materialization_plan_id=aff.materialization_plan_id,
                        selectable_ref_policy_id=aff.selectable_ref_policy_id,
                        intent_schema_id=aff.intent_schema_id,
                        required_context_facts=aff.required_context_facts,
                        stage_authority=aff.stage_authority,
                        repair_strategy_id=repair_strategy_id,
                        strategy_display_label=strategy_display_label,
                        closure_summary=closure_summary,
                        preview_required=preview_required,
                    )
                    entries.append(entry)

        return RepairCatalog._build(entries)

    @staticmethod
    def _make_entry_id(
        construct_type: str,
        slot_name: str,
        diagnostic_kind: str,
        affordance_id: str,
    ) -> str:
        """Build the stable composite entry ID.

        Format: ``{construct_type}.{slot_name}.{diagnostic_kind}.{affordance_id}``

        Examples:
            - ``EXCEPTION_FLOW.handler_action.missing_handler.exception_flow.add_handler_step``
            - ``WORKER_PROMOTION.promotion_input_contract.type_or_contract_ambiguity.worker_promotion.resolve_contract``
        """  # noqa: E501
        return ".".join([construct_type, slot_name, diagnostic_kind, affordance_id])
