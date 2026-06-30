"""CI guardrails for typed IRS actionability and audit closure."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from nl2spl.compiler.construct_registry import (
    ConstructIRS,
    SlotActionabilityDecision,
    SlotSpec,
    SPLConstructRegistry,
)
from nl2spl.compiler.irs.audit import (
    _audit_registry,
    audit_irs_contract,
    load_waivers,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
WAIVER_PATH = (
    REPO_ROOT / ".agents" / "skills" / "audit-irs-contract" / "waivers.json"
)
CLI_PATH = (
    REPO_ROOT
    / ".agents"
    / "skills"
    / "audit-irs-contract"
    / "scripts"
    / "audit_irs_contract.py"
)


def test_actionability_decision_enforces_disposition_invariants() -> None:
    with pytest.raises(ValueError, match="requires a non_editable_disposition"):
        SlotActionabilityDecision(
            actionability="non_editable",
            non_editable_disposition=None,
            rationale_code="test",
            decision_source_ref="test",
        )

    with pytest.raises(ValueError, match="forbids non_editable_disposition"):
        SlotActionabilityDecision(
            actionability="editable",
            non_editable_disposition="review_only",
            rationale_code="test",
            decision_source_ref="test",
        )



def test_actionability_decision_rejects_unknown_literal_values() -> None:
    with pytest.raises(ValueError, match="Unknown actionability"):
        SlotActionabilityDecision(
            actionability="invalid",  # type: ignore[arg-type]
            non_editable_disposition=None,
            rationale_code="test",
            decision_source_ref="test",
        )

    with pytest.raises(ValueError, match="Unknown decision_status"):
        SlotActionabilityDecision(
            actionability="editable",
            non_editable_disposition=None,
            rationale_code="test",
            decision_source_ref="test",
            decision_status="invalid",  # type: ignore[arg-type]
        )

@pytest.mark.parametrize(
    ("slot", "expected"),
    [
        (SlotSpec(slot_name="plain"), False),
        (SlotSpec(slot_name="partial", required_for_partial=True), True),
        (SlotSpec(slot_name="complete", required_for_complete=True), True),
        (SlotSpec(slot_name="diagnostic", missing_diagnostic="missing_handler"), True),
    ],
)
def test_slot_actionability_audit_scope(slot: SlotSpec, expected: bool) -> None:
    assert slot.requires_actionability_decision() is expected


def test_default_registry_has_decisions_for_every_audited_slot() -> None:
    registry = SPLConstructRegistry.default()
    audited = [
        (construct_name, slot)
        for construct_name in registry.list_constructs()
        for slot in registry.get(construct_name).slots
        if slot.requires_actionability_decision()
    ]

    assert len(audited) == 41
    assert [
        f"{construct_name}.{slot.slot_name}"
        for construct_name, slot in audited
        if slot.actionability_decision is None
    ] == []


def test_api_declaration_schema_and_functions_are_deferred_non_editable() -> None:
    construct = SPLConstructRegistry.default().get("API_DECLARATION")
    for slot_name in ("openapi_schema", "functions"):
        slot = construct.get_slot(slot_name)
        assert slot is not None
        decision = slot.actionability_decision
        assert decision is not None
        assert decision.actionability == "non_editable"
        assert decision.non_editable_disposition == "deferred_validation"
        assert slot.repair_affordances == ()


def test_call_api_smoke_test_reports_real_runtime_closure_gap() -> None:
    report = audit_irs_contract(
        construct="CALL_API",
        scope="all",
        repo_root=REPO_ROOT,
    )

    finding = next(
        item
        for item in report.findings
        if item.finding_id
        == "CALL_API.integration_evidence.runtime_closure_incomplete"
    )
    assert finding.severity == "P1"
    assert finding.waived is False
    assert "repair_strategy_id is missing" in finding.details
    assert report.verdict == "fail"


@pytest.mark.parametrize(
    "construct",
    ("EXCEPTION_FLOW", "REQUIRED_OUTPUT", "WORKER_PROMOTION"),
)
def test_r12_strategy_backed_repairs_have_no_audit_findings(construct: str) -> None:
    report = audit_irs_contract(
        construct=construct,
        scope="all",
        repo_root=REPO_ROOT,
    )
    assert report.findings == ()
    assert report.verdict == "pass"


def test_registry_wide_guardrail_has_only_explicit_active_waivers() -> None:
    waivers = load_waivers(WAIVER_PATH)
    report = audit_irs_contract(
        scope="all",
        repo_root=REPO_ROOT,
        waivers=waivers,
    )

    assert report.blocking_findings == ()
    assert report.verdict == "conditional_pass"
    assert len(report.findings) == 10
    assert all(finding.waived for finding in report.findings)


def test_expired_waivers_fail_the_guardrail() -> None:
    waivers = load_waivers(WAIVER_PATH)
    report = audit_irs_contract(
        construct="CALL_API",
        scope="all",
        repo_root=REPO_ROOT,
        waivers=waivers,
        today=date(2026, 8, 2),
    )

    assert report.verdict == "fail"
    assert any(
        finding.finding_id
        == "waiver.expired.CALL_API.integration_evidence.runtime_closure_incomplete"
        for finding in report.blocking_findings
    )


def test_optional_enrichment_cannot_block_rendering_or_completion() -> None:
    registry = SPLConstructRegistry()
    registry.register(
        ConstructIRS(
            construct_type="OPTIONAL_TEST",
            existence_policy="source_signal_required",
            source_signals=["optional"],
            slots=[
                SlotSpec(
                    slot_name="enrichment",
                    required_for_complete=True,
                    renderable_without=False,
                    missing_diagnostic="missing_handler",
                    actionability_decision=SlotActionabilityDecision(
                        actionability="optional_enrichment",
                        non_editable_disposition=None,
                        rationale_code="test",
                        decision_source_ref="test",
                    ),
                )
            ],
        )
    )

    findings = _audit_registry(registry, ("OPTIONAL_TEST",))
    ids = {finding.finding_id for finding in findings}
    assert "OPTIONAL_TEST.enrichment.optional_enrichment_blocks_completion" in ids
    assert "OPTIONAL_TEST.enrichment.optional_enrichment_blocks_rendering" in ids
    assert "OPTIONAL_TEST.enrichment.optional_enrichment_blocking_diagnostic" in ids
    assert all(finding.severity == "P0" for finding in findings)


def test_waiver_governance_fields_are_loaded_and_reported() -> None:
    waivers = load_waivers(WAIVER_PATH)
    assert all(waiver.owner for waiver in waivers)
    assert all(waiver.issue_ref for waiver in waivers)
    assert all(waiver.created_at <= waiver.expires for waiver in waivers)

    report = audit_irs_contract(
        construct="CALL_API",
        scope="all",
        repo_root=REPO_ROOT,
        waivers=waivers,
    )
    finding = next(item for item in report.findings if item.waived)
    assert finding.waiver_owner == "compiler-irs"
    assert finding.waiver_issue_ref == "R12-api-affordance-closure"
    assert finding.waiver_created_at == "2026-06-30"


def test_malformed_waiver_fails_loading(tmp_path: Path) -> None:
    path = tmp_path / "waivers.json"
    path.write_text(
        json.dumps(
            {
                "waivers": [
                    {
                        "finding_id": "x",
                        "construct": "X",
                        "expires": "2026-08-01",
                        "reason": "missing governance fields",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required fields"):
        load_waivers(path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "root must be a JSON object"),
        ({"waivers": ["invalid"]}, "every waiver entry must be a JSON object"),
    ],
)
def test_non_object_waiver_shapes_fail_loading(
    tmp_path: Path,
    payload: object,
    message: str,
) -> None:
    path = tmp_path / "waivers.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_waivers(path)


def test_duplicate_waiver_identity_fails_loading(tmp_path: Path) -> None:
    waiver = {
        "finding_id": "x",
        "construct": "X",
        "expires": "2026-08-01",
        "reason": "duplicate",
        "owner": "compiler-irs",
        "issue_ref": "issue",
        "created_at": "2026-06-30",
    }
    path = tmp_path / "waivers.json"
    path.write_text(json.dumps({"waivers": [waiver, waiver]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate finding identities"):
        load_waivers(path)


def test_cli_text_output_renders_waived_findings() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "--construct",
            "CALL_API",
            "--scope",
            "all",
            "--format",
            "text",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Waiver owner: compiler-irs" in completed.stdout
    assert "issue: R12-api-affordance-closure" in completed.stdout


def test_cli_help_and_missing_backend_outside_repository(tmp_path: Path) -> None:
    copied_cli = tmp_path / "audit_irs_contract.py"
    copied_cli.write_bytes(CLI_PATH.read_bytes())

    help_result = subprocess.run(
        [sys.executable, str(copied_cli), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "Audit ConstructIRS contract" in help_result.stdout

    audit_result = subprocess.run(
        [sys.executable, str(copied_cli), "--scope", "all"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert audit_result.returncode == 2
    assert "IRS audit configuration error" in audit_result.stderr
    assert "Could not locate repository root" in audit_result.stderr


def test_skill_mirrors_match_exactly() -> None:
    canonical_root = REPO_ROOT / ".agents" / "skills"
    mirror_root = REPO_ROOT / ".codex" / "skills"

    for skill_name in ("irs-knowledge", "audit-irs-contract"):
        canonical_files = {
            path.relative_to(canonical_root / skill_name): path.read_bytes()
            for path in (canonical_root / skill_name).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        mirror_files = {
            path.relative_to(mirror_root / skill_name): path.read_bytes()
            for path in (mirror_root / skill_name).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        assert mirror_files == canonical_files
