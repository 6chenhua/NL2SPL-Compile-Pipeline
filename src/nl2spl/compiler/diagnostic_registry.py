"""Diagnostic Registry — structured catalogue of known diagnostic kinds.

Defines ``DiagnosticSpec`` and ``DiagnosticRegistry``.  The registry
separates *enabled* kinds (used by the current compiler) from *reserved*
kinds (defined for future phases but not yet produced).

Phase 1 adds this module as a pure data layer — no pipeline wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["info", "warning", "error"]


@dataclass
class DiagnosticSpec:
    """A single registered diagnostic kind."""

    kind: str
    default_severity: Severity
    blocks_completion: bool
    description: str
    allowed_targets: list[str] = field(default_factory=list)
    enabled: bool = True


class DiagnosticRegistry:
    """Registry of ``DiagnosticSpec`` entries keyed by kind string."""

    def __init__(self) -> None:
        self._specs: dict[str, DiagnosticSpec] = {}

    # -- mutation -----------------------------------------------------------

    def register(self, spec: DiagnosticSpec) -> None:
        self._specs[spec.kind] = spec

    # -- query --------------------------------------------------------------

    def get(self, kind: str) -> DiagnosticSpec:
        if kind not in self._specs:
            raise KeyError(f"Unknown diagnostic kind: {kind}")
        return self._specs[kind]

    def has(self, kind: str) -> bool:
        return kind in self._specs

    def list_kinds(self, *, enabled_only: bool = False) -> list[str]:
        if enabled_only:
            return sorted(k for k, s in self._specs.items() if s.enabled)
        return sorted(self._specs)

    # -- factory ------------------------------------------------------------

    @staticmethod
    def default() -> DiagnosticRegistry:
        """Build the default registry with all v5 diagnostic kinds."""
        registry = DiagnosticRegistry()

        # ---- enabled ----

        registry.register(DiagnosticSpec(
            kind="missing_handler",
            default_severity="warning",
            blocks_completion=True,
            description="Exception flow has a condition but no handler action.",
            allowed_targets=["exception_flow"],
        ))

        registry.register(DiagnosticSpec(
            kind="missing_output_producer",
            default_severity="warning",
            blocks_completion=True,
            description="A required output has no source-backed producer.",
            allowed_targets=["variable", "output"],
        ))

        registry.register(DiagnosticSpec(
            kind="required_output_deferred",
            default_severity="warning",
            blocks_completion=True,
            description=(
                "A required output may be supplied by a deferred API response, "
                "but the API return contract is not yet known."
            ),
            allowed_targets=["variable", "output"],
        ))

        registry.register(DiagnosticSpec(
            kind="required_output_missing_source_backed_producer",
            default_severity="warning",
            blocks_completion=True,
            description="A required output has no source-backed producer relation.",
            allowed_targets=["variable", "output"],
            enabled=False,
        ))

        registry.register(DiagnosticSpec(
            kind="type_or_contract_ambiguity",
            default_severity="warning",
            blocks_completion=True,
            description=(
                "A construct references an incomplete or ambiguous type / API / "
                "worker contract."
            ),
            allowed_targets=["step", "api", "worker", "handoff"],
        ))

        registry.register(DiagnosticSpec(
            kind="assumed_command_not_renderable",
            default_severity="warning",
            blocks_completion=True,
            description="A step has no source evidence and is not compiler scaffolding.",
            allowed_targets=["step"],
        ))

        registry.register(DiagnosticSpec(
            kind="unmapped_behavior_span",
            default_severity="warning",
            blocks_completion=True,
            description="A behaviour span has not been mapped to any construct.",
            allowed_targets=["span"],
        ))

        registry.register(DiagnosticSpec(
            kind="missing_provenance",
            default_severity="warning",
            blocks_completion=False,
            description="A materialised SPL element lacks provenance traces.",
            allowed_targets=["step", "variable", "constraint", "flow"],
        ))

        registry.register(DiagnosticSpec(
            kind="semantic_conflict",
            default_severity="warning",
            blocks_completion=False,
            description=(
                "A likely or possible semantic conflict between constraints, "
                "steps, or policies.  MVP uses LLM prompt analysis; future "
                "phases may add rule-based detection."
            ),
            allowed_targets=["step", "constraint", "policy"],
        ))

        registry.register(DiagnosticSpec(
            kind="deferred_api_contract_validation",
            default_severity="info",
            blocks_completion=False,
            description=(
                "API declaration uses grammar-safe placeholders; semantic contract "
                "validation is deferred to the downstream SPL compiler."
            ),
            allowed_targets=["api"],
        ))

        # ---- reserved (defined but not yet enabled) ----

        registry.register(DiagnosticSpec(
            kind="redundant_requirement",
            default_severity="info",
            blocks_completion=False,
            description="Two or more requirements express the same intent.",
            allowed_targets=["span", "step", "constraint"],
            enabled=False,
        ))

        registry.register(DiagnosticSpec(
            kind="policy_step_conflict",
            default_severity="warning",
            blocks_completion=True,
            description="A step or command violates an explicit policy or constraint.",
            allowed_targets=["step", "constraint"],
            enabled=False,
        ))

        registry.register(DiagnosticSpec(
            kind="use_before_def",
            default_severity="error",
            blocks_completion=True,
            description="A variable is consumed before any producer defines it.",
            allowed_targets=["variable", "step"],
            enabled=False,
        ))

        registry.register(DiagnosticSpec(
            kind="worker_graph_inconsistency",
            default_severity="error",
            blocks_completion=True,
            description="The multi-worker call graph has an inconsistency.",
            allowed_targets=["worker", "handoff"],
            enabled=False,
        ))

        # -- B5: resource contract demand diagnostics --

        registry.register(DiagnosticSpec(
            kind="missing_resource_contract",
            default_severity="warning",
            blocks_completion=True,
            description=(
                "A source-demanded resource contract has no materialized "
                "resource binding in Stage 6."
            ),
            allowed_targets=["resource_contract_demand"],
        ))

        registry.register(DiagnosticSpec(
            kind="resource_kind_mismatch",
            default_severity="warning",
            blocks_completion=True,
            description=(
                "A resource contract binding points to a resource kind that "
                "does not exist in the materialized ResourceRegistryIR."
            ),
            allowed_targets=["resource_contract_demand"],
        ))

        registry.register(DiagnosticSpec(
            kind="unspecified_output_missing_producer",
            default_severity="info",
            blocks_completion=False,
            description=(
                "A source-demanded output with requiredness=unspecified has "
                "no renderable producer.  Review whether this output should "
                "be declared optional or a producer should be added."
            ),
            allowed_targets=["resource_contract_demand"],
        ))

        return registry
