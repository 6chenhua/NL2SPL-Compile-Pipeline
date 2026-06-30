from __future__ import annotations

from nl2spl.compiler.annotation_role_contract.normalize import (
    normalize_annotation_from_role,
)
from nl2spl.compiler.annotation_role_contract.registry import ROLE_CONTRACT_REGISTRY
from nl2spl.pipeline.stages.stage2_field_router_validator import (
    RouteRefinementValidator,
)


def test_api_candidate_routes_to_api_declaration_source_evidence() -> None:
    contract = ROLE_CONTRACT_REGISTRY.require_role_contract("api_candidate")

    assert contract.field == "integrations"
    assert contract.route_family == "integration_candidate"
    assert contract.construct_target == "API_DECLARATION"
    assert contract.slot_target == "source_evidence"
    assert contract.executable is False


def test_integration_hint_stays_declaration_candidate_not_call_api() -> None:
    annotation = normalize_annotation_from_role(
        "s1",
        "integration_hint",
        metadata={"api_group_id": "approved-sources"},
    ).annotation

    assert annotation.construct_target == "API_DECLARATION"
    assert annotation.slot_target == "source_evidence"
    assert annotation.executable is False
    assert annotation.metadata["api_group_id"] == "approved-sources"


def test_process_step_api_action_requires_explicit_metadata_scope() -> None:
    ordinary = normalize_annotation_from_role("s1", "process_step").annotation
    api_action = normalize_annotation_from_role(
        "s2",
        "process_step",
        metadata={"api_action": True, "api_group_id": "search"},
    ).annotation

    assert ordinary.construct_target is None
    assert ordinary.slot_target is None
    assert ordinary.executable is True

    assert api_action.construct_target == "CALL_API"
    assert api_action.slot_target == "call_action"
    assert api_action.executable is True
    assert api_action.metadata["api_group_id"] == "search"


def test_plain_search_is_not_api_mechanism_evidence() -> None:
    assert RouteRefinementValidator._api_mentioned("search approved sources") is False
    assert RouteRefinementValidator._api_mentioned("retrieve approved sources") is False
    assert RouteRefinementValidator._api_mentioned("rapid response workflow") is False
    assert RouteRefinementValidator._api_mentioned("call WeatherAPI") is True
    assert RouteRefinementValidator._api_mentioned("use searchapi") is True
    assert RouteRefinementValidator._api_mentioned("call weather_api") is True
    assert RouteRefinementValidator._api_mentioned("use the connector") is True
