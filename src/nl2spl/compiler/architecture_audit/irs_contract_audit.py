"""Architecture audit for IRS contracts and repair closure."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

from nl2spl.compiler.constructs import (
    ConstructIRS,
    RepairAffordanceSpec,
    SlotSpec,
    SPLConstructRegistry,
)
from nl2spl.compiler.diagnostics import DiagnosticRegistry
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder

AuditScope = Literal["registry", "runtime", "tests", "all"]
FindingSeverity = Literal["P0", "P1", "P2"]


@dataclass(frozen=True)
class AuditWaiver:
    finding_id: str
    construct: str
    expires: date
    reason: str
    owner: str
    issue_ref: str
    created_at: date

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AuditWaiver:
        required = {
            "finding_id",
            "construct",
            "expires",
            "reason",
            "owner",
            "issue_ref",
            "created_at",
        }
        missing = sorted(required - raw.keys())
        if missing:
            raise ValueError(
                "waiver is missing required fields: " + ", ".join(missing)
            )
        text_values = {
            key: raw[key]
            for key in ("finding_id", "construct", "reason", "owner", "issue_ref")
        }
        for key, value in text_values.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"waiver field {key!r} must be a non-empty string")
        expires = date.fromisoformat(str(raw["expires"]))
        created_at = date.fromisoformat(str(raw["created_at"]))
        if created_at > expires:
            raise ValueError("waiver created_at must not be after expires")
        return cls(
            finding_id=text_values["finding_id"],
            construct=text_values["construct"],
            expires=expires,
            reason=text_values["reason"],
            owner=text_values["owner"],
            issue_ref=text_values["issue_ref"],
            created_at=created_at,
        )

@dataclass(frozen=True)
class AuditFinding:
    finding_id: str
    severity: FindingSeverity
    scope: str
    construct: str
    slot: str | None
    message: str
    details: tuple[str, ...] = ()
    waived: bool = False
    waiver_reason: str | None = None
    waiver_expires: str | None = None
    waiver_owner: str | None = None
    waiver_issue_ref: str | None = None
    waiver_created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "scope": self.scope,
            "construct": self.construct,
            "slot": self.slot,
            "message": self.message,
            "details": list(self.details),
            "waived": self.waived,
            "waiver_reason": self.waiver_reason,
            "waiver_expires": self.waiver_expires,
            "waiver_owner": self.waiver_owner,
            "waiver_issue_ref": self.waiver_issue_ref,
            "waiver_created_at": self.waiver_created_at,
        }


@dataclass(frozen=True)
class AuditReport:
    scope: AuditScope
    construct: str | None
    findings: tuple[AuditFinding, ...]

    @property
    def blocking_findings(self) -> tuple[AuditFinding, ...]:
        return tuple(
            finding
            for finding in self.findings
            if not finding.waived and finding.severity in {"P0", "P1"}
        )

    @property
    def verdict(self) -> Literal["pass", "conditional_pass", "fail"]:
        if self.blocking_findings:
            return "fail"
        if self.findings:
            return "conditional_pass"
        return "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "scope": self.scope,
            "construct": self.construct,
            "summary": {
                "total": len(self.findings),
                "blocking": len(self.blocking_findings),
                "waived": sum(finding.waived for finding in self.findings),
                "p0": sum(finding.severity == "P0" for finding in self.findings),
                "p1": sum(finding.severity == "P1" for finding in self.findings),
                "p2": sum(finding.severity == "P2" for finding in self.findings),
            },
            "findings": [finding.to_dict() for finding in self.findings],
        }


def load_waivers(path: Path | None) -> tuple[AuditWaiver, ...]:
    if path is None or not path.exists():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("waiver document root must be a JSON object")
    values = raw.get("waivers", [])
    if not isinstance(values, list):
        raise ValueError("waiver document must contain a 'waivers' list")
    if not all(isinstance(item, dict) for item in values):
        raise ValueError("every waiver entry must be a JSON object")
    waivers = tuple(AuditWaiver.from_dict(item) for item in values)
    identities = [(item.finding_id, item.construct) for item in waivers]
    if len(identities) != len(set(identities)):
        raise ValueError("waiver document contains duplicate finding identities")
    return waivers


def audit_irs_contract(
    *,
    construct: str | None = None,
    scope: AuditScope = "all",
    repo_root: Path | None = None,
    waivers: tuple[AuditWaiver, ...] = (),
    today: date | None = None,
) -> AuditReport:
    registry = SPLConstructRegistry.default()
    if construct is not None and not registry.has(construct):
        finding = AuditFinding(
            finding_id=f"{construct}.unknown_construct",
            severity="P0",
            scope="registry",
            construct=construct,
            slot=None,
            message=f"Construct '{construct}' is not registered.",
        )
        return AuditReport(scope=scope, construct=construct, findings=(finding,))

    names = (construct,) if construct else tuple(registry.list_constructs())
    findings: list[AuditFinding] = []
    selected_scopes = {"registry", "runtime", "tests"} if scope == "all" else {scope}

    if "registry" in selected_scopes:
        findings.extend(_audit_registry(registry, names))
    if "runtime" in selected_scopes:
        findings.extend(_audit_runtime(registry, names))
    if "tests" in selected_scopes:
        root = (repo_root or Path.cwd()).resolve()
        findings.extend(_audit_tests(registry, names, root))

    findings.extend(_expired_waiver_findings(waivers, today=today))
    applied = _apply_waivers(findings, waivers, today=today)
    return AuditReport(
        scope=scope,
        construct=construct,
        findings=tuple(sorted(applied, key=lambda item: item.finding_id)),
    )


def _audit_registry(
    registry: SPLConstructRegistry,
    construct_names: tuple[str, ...],
) -> list[AuditFinding]:
    diagnostics = DiagnosticRegistry.default()
    findings: list[AuditFinding] = []

    for construct_name in construct_names:
        construct = registry.get(construct_name)
        for slot in construct.slots:
            if not slot.requires_actionability_decision():
                continue
            prefix = f"{construct_name}.{slot.slot_name}"
            decision = slot.actionability_decision
            if decision is None:
                findings.append(
                    _finding(
                        prefix + ".missing_actionability_decision",
                        "P0",
                        "registry",
                        construct,
                        slot,
                        "Slot is in audit scope but has no SlotActionabilityDecision.",
                    )
                )
                continue

            if decision.actionability == "editable" and not slot.repair_affordances:
                findings.append(
                    _finding(
                        prefix + ".editable_without_affordance",
                        "P0",
                        "registry",
                        construct,
                        slot,
                        "Editable slot has no repair affordance.",
                    )
                )
            if decision.actionability == "non_editable" and slot.repair_affordances:
                findings.append(
                    _finding(
                        prefix + ".non_editable_with_affordance",
                        "P0",
                        "registry",
                        construct,
                        slot,
                        "Non-editable slot must not declare repair affordances.",
                    )
                )
            if decision.actionability == "optional_enrichment":
                if slot.required_for_partial or slot.required_for_complete:
                    findings.append(
                        _finding(
                            prefix + ".optional_enrichment_blocks_completion",
                            "P0",
                            "registry",
                            construct,
                            slot,
                            "Optional enrichment must not be required for partial "
                            "or complete output.",
                        )
                    )
                if not slot.renderable_without:
                    findings.append(
                        _finding(
                            prefix + ".optional_enrichment_blocks_rendering",
                            "P0",
                            "registry",
                            construct,
                            slot,
                            "Optional enrichment must be explicitly renderable without the slot.",
                        )
                    )
                if slot.missing_diagnostic and diagnostics.has(slot.missing_diagnostic):
                    diagnostic = diagnostics.get(slot.missing_diagnostic)
                    if diagnostic.blocks_completion:
                        findings.append(
                            _finding(
                                prefix + ".optional_enrichment_blocking_diagnostic",
                                "P0",
                                "registry",
                                construct,
                                slot,
                                "Optional enrichment diagnostic must not block completion.",
                            )
                        )
                user_facing = any(item.user_facing for item in slot.repair_affordances)
                if user_facing:
                    findings.append(
                        _finding(
                            prefix + ".optional_enrichment_user_facing",
                            "P1",
                            "registry",
                            construct,
                            slot,
                            "Optional enrichment must not create a mandatory user-facing repair.",
                        )
                    )

            if slot.missing_diagnostic and not diagnostics.has(slot.missing_diagnostic):
                findings.append(
                    _finding(
                        prefix + ".unknown_diagnostic_kind",
                        "P0",
                        "registry",
                        construct,
                        slot,
                        f"Diagnostic kind '{slot.missing_diagnostic}' is not registered.",
                    )
                )

            for affordance in slot.repair_affordances:
                findings.extend(
                    _audit_affordance_shape(construct, slot, affordance)
                )
    return findings


def _audit_affordance_shape(
    construct: ConstructIRS,
    slot: SlotSpec,
    affordance: RepairAffordanceSpec,
) -> list[AuditFinding]:
    prefix = f"{construct.construct_type}.{slot.slot_name}.{affordance.affordance_id}"
    findings: list[AuditFinding] = []
    if slot.missing_diagnostic is None:
        findings.append(
            _finding(
                prefix + ".missing_diagnostic",
                "P0",
                "registry",
                construct,
                slot,
                "Repair affordance requires a missing diagnostic kind.",
            )
        )
    if (
        affordance.default_patch_type is not None
        and affordance.default_patch_type not in affordance.supported_patch_types
    ):
        findings.append(
            _finding(
                prefix + ".invalid_default_patch_type",
                "P0",
                "registry",
                construct,
                slot,
                "default_patch_type is not listed in supported_patch_types.",
            )
        )
    return findings


def _audit_runtime(
    registry: SPLConstructRegistry,
    construct_names: tuple[str, ...],
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    strategy_registry = _build_default_strategy_registry()
    catalog = RepairCatalogBuilder.from_construct_registry(
        registry,
        strategy_registry=strategy_registry,
    )
    runtime, materialization_registry = _load_default_runtime()

    for construct_name in construct_names:
        construct = registry.get(construct_name)
        for slot in construct.slots:
            decision = slot.actionability_decision
            if decision is None or decision.actionability != "editable":
                continue
            missing: list[str] = []
            if decision.decision_status != "confirmed":
                missing.append("actionability decision is unresolved")

            for affordance in slot.repair_affordances:
                missing.extend(
                    _runtime_closure_gaps(
                        construct=construct,
                        slot=slot,
                        affordance=affordance,
                        strategy_registry=strategy_registry,
                        catalog=catalog,
                        runtime=runtime,
                        materialization_registry=materialization_registry,
                    )
                )

            if missing:
                severity: FindingSeverity = (
                    "P1" if decision.decision_status == "unresolved" else "P0"
                )
                findings.append(
                    _finding(
                        f"{construct_name}.{slot.slot_name}.runtime_closure_incomplete",
                        severity,
                        "runtime",
                        construct,
                        slot,
                        "Editable slot does not have a complete repair runtime closure.",
                        details=tuple(dict.fromkeys(missing)),
                    )
                )
    return findings


def _runtime_closure_gaps(
    *,
    construct: ConstructIRS,
    slot: SlotSpec,
    affordance: RepairAffordanceSpec,
    strategy_registry: Any,
    catalog: Any,
    runtime: Any,
    materialization_registry: Any,
) -> list[str]:
    gaps: list[str] = []
    required_ids = {
        "handler_id": affordance.handler_id,
        "context_id": affordance.context_id,
        "target_resolver_id": affordance.target_resolver_id,
        "repair_strategy_id": affordance.repair_strategy_id,
        "materialization_plan_id": affordance.materialization_plan_id,
        "selectable_ref_policy_id": affordance.selectable_ref_policy_id,
        "intent_schema_id": affordance.intent_schema_id,
        "stage_authority": affordance.stage_authority,
    }
    for field_name, value in required_ids.items():
        if value is None or not value.strip():
            gaps.append(f"{field_name} is missing")

    if affordance.handler_id and not runtime.handlers.has(affordance.handler_id):
        gaps.append(f"handler '{affordance.handler_id}' is not registered")
    if affordance.context_id and not runtime.context_builders.has(affordance.context_id):
        gaps.append(f"context builder '{affordance.context_id}' is not registered")
    if (
        affordance.target_resolver_id
        and not runtime.target_resolvers.has(affordance.target_resolver_id)
    ):
        gaps.append(f"target resolver '{affordance.target_resolver_id}' is not registered")
    for patch_type in affordance.supported_patch_types:
        if not runtime.patches.has(patch_type):
            gaps.append(f"patch '{patch_type}' is not registered")

    strategy = None
    if affordance.repair_strategy_id:
        if not strategy_registry.has(affordance.repair_strategy_id):
            gaps.append(
                f"strategy '{affordance.repair_strategy_id}' is not registered"
            )
        else:
            strategy = strategy_registry.get(affordance.repair_strategy_id)
            if strategy.target_construct_type != construct.construct_type:
                gaps.append("strategy target construct does not match owning construct")
            if strategy.diagnostic_kind != slot.missing_diagnostic:
                gaps.append("strategy diagnostic kind does not match owning slot")
            unsupported = set(affordance.supported_patch_types) - set(
                strategy.supported_patch_types
            )
            if unsupported:
                gaps.append(
                    "affordance patch types are not allowed by strategy: "
                    + ", ".join(sorted(unsupported))
                )
            if (
                affordance.selectable_ref_policy_id
                and strategy.selectable_ref_policy_id
                and affordance.selectable_ref_policy_id
                != strategy.selectable_ref_policy_id
            ):
                gaps.append("selectable-ref policy does not match strategy")

    if affordance.materialization_plan_id:
        try:
            plan = materialization_registry.get(affordance.materialization_plan_id)
        except Exception as exc:
            gaps.append(
                f"materialization plan '{affordance.materialization_plan_id}' "
                f"is not registered ({type(exc).__name__})"
            )
        else:
            if plan.target_construct_type != construct.construct_type:
                gaps.append("materialization plan target construct does not match")
            if plan.verification_lane != affordance.default_verification_lane:
                gaps.append("materialization plan verification lane does not match")
            if plan.stage_authority != affordance.stage_authority:
                gaps.append("materialization plan stage authority does not match")

    entries = catalog.find_by_construct_slot_kind(
        construct_type=construct.construct_type,
        slot_name=slot.slot_name,
        diagnostic_kind=slot.missing_diagnostic or "",
    )
    matching = tuple(
        entry for entry in entries if entry.affordance_id == affordance.affordance_id
    )
    if not matching:
        gaps.append("RepairCatalog entry was not derived")
    elif not any(entry.user_facing for entry in matching):
        gaps.append("RepairCatalog entry is not user-facing")

    if strategy is not None and affordance.materialization_plan_id is None:
        gaps.append("strategy-linked affordance has no materialization plan")
    return gaps


def _build_default_strategy_registry() -> Any:
    defaults = import_module(
        "nl2spl.compiler.spl_editing.strategy.defaults"
    )
    return defaults.build_default_strategy_registry()


def _load_default_runtime() -> tuple[Any, Any]:
    from nl2spl.compiler.spl_editing.cli import _build_default_service

    class _AuditSuggestionLLM:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {}

    service = _build_default_service(_AuditSuggestionLLM())
    return service._runtime, service._materialization.registry


def _audit_tests(
    registry: SPLConstructRegistry,
    construct_names: tuple[str, ...],
    repo_root: Path,
) -> list[AuditFinding]:
    test_root = repo_root / "tests"
    if not test_root.exists():
        return [
            AuditFinding(
                finding_id="tests.missing_test_root",
                severity="P1",
                scope="tests",
                construct="*",
                slot=None,
                message=f"Test root does not exist: {test_root}",
            )
        ]

    corpus = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in test_root.rglob("test_*.py")
    )
    findings: list[AuditFinding] = []
    for construct_name in construct_names:
        construct = registry.get(construct_name)
        if construct_name not in corpus:
            findings.append(
                AuditFinding(
                    finding_id=f"{construct_name}.missing_contract_test",
                    severity="P1",
                    scope="tests",
                    construct=construct_name,
                    slot=None,
                    message="No test references this ConstructIRS type.",
                )
            )
        for slot in construct.slots:
            decision = slot.actionability_decision
            if decision is None or decision.actionability != "editable":
                continue
            for affordance in slot.repair_affordances:
                if affordance.affordance_id not in corpus:
                    findings.append(
                        _finding(
                            f"{construct_name}.{slot.slot_name}."
                            f"{affordance.affordance_id}.missing_affordance_test",
                            "P1",
                            "tests",
                            construct,
                            slot,
                            "No test references this repair affordance ID.",
                        )
                    )
    return findings


def _finding(
    finding_id: str,
    severity: FindingSeverity,
    scope: str,
    construct: ConstructIRS,
    slot: SlotSpec,
    message: str,
    *,
    details: tuple[str, ...] = (),
) -> AuditFinding:
    return AuditFinding(
        finding_id=finding_id,
        severity=severity,
        scope=scope,
        construct=construct.construct_type,
        slot=slot.slot_name,
        message=message,
        details=details,
    )


def _expired_waiver_findings(
    waivers: tuple[AuditWaiver, ...],
    *,
    today: date | None,
) -> list[AuditFinding]:
    effective_today = today or date.today()
    return [
        AuditFinding(
            finding_id=f"waiver.expired.{waiver.finding_id}",
            severity="P1",
            scope="waiver",
            construct=waiver.construct,
            slot=None,
            message=f"Waiver expired on {waiver.expires.isoformat()}.",
        )
        for waiver in waivers
        if waiver.expires < effective_today
    ]


def _apply_waivers(
    findings: list[AuditFinding],
    waivers: tuple[AuditWaiver, ...],
    *,
    today: date | None,
) -> list[AuditFinding]:
    effective_today = today or date.today()
    active = {
        (waiver.finding_id, waiver.construct): waiver
        for waiver in waivers
        if waiver.expires >= effective_today
    }
    result: list[AuditFinding] = []
    for finding in findings:
        waiver = active.get((finding.finding_id, finding.construct))
        if waiver is None:
            result.append(finding)
            continue
        result.append(
            replace(
                finding,
                waived=True,
                waiver_reason=waiver.reason,
                waiver_expires=waiver.expires.isoformat(),
                waiver_owner=waiver.owner,
                waiver_issue_ref=waiver.issue_ref,
                waiver_created_at=waiver.created_at.isoformat(),
            )
        )
    return result
