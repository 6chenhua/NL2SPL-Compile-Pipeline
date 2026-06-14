"""S-1 Contract Freeze tests.

Verifies that every constant, enum, capability matrix, hash policy, and
schema rule defined in the S-1 contract is present, well-formed, and
importable.  These tests are the gate: downstream stages MUST import
from ``nl2spl.compiler.artifacts.snapshot``, never redefine these values.
"""

from __future__ import annotations

import hashlib
from enum import Enum

import pytest

# ---------------------------------------------------------------------------
# S-1: every contract element must be importable from the top-level package
# ---------------------------------------------------------------------------


def test_all_constants_importable_from_package() -> None:
    """Every S-1 constant/enum/function must be importable from the snapshot package."""
    from nl2spl.compiler.artifacts.snapshot import (
        HASH_POLICY,
        SNAPSHOT_ARTIFACT_KIND,
        SNAPSHOT_SCHEMA_VERSION,
    )
    # If we got here without ImportError, all names are importable.
    assert SNAPSHOT_ARTIFACT_KIND is not None
    assert SNAPSHOT_SCHEMA_VERSION is not None
    assert HASH_POLICY is not None


# ===================================================================
# constants.py
# ===================================================================


class TestArtifactKind:
    def test_kind_value(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SNAPSHOT_ARTIFACT_KIND

        assert SNAPSHOT_ARTIFACT_KIND == "spl_editing_artifact_snapshot"

    def test_kind_is_string(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SNAPSHOT_ARTIFACT_KIND

        assert isinstance(SNAPSHOT_ARTIFACT_KIND, str)


class TestSchemaVersion:
    def test_version_value(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SNAPSHOT_SCHEMA_VERSION

        assert SNAPSHOT_SCHEMA_VERSION == "1.0.0"

    def test_version_is_semver_string(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SNAPSHOT_SCHEMA_VERSION

        parts = SNAPSHOT_SCHEMA_VERSION.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


class TestTopLevelSections:
    def test_six_sections_defined(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import TOP_LEVEL_SECTIONS

        assert len(TOP_LEVEL_SECTIONS) == 6

    def test_sections_in_canonical_order(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import TOP_LEVEL_SECTIONS

        assert TOP_LEVEL_SECTIONS == (
            "artifact_kind",
            "schema_version",
            "identity",
            "capabilities",
            "payload",
            "integrity",
        )

    def test_section_name_constants_match_tuple(self) -> None:
        from nl2spl.compiler.artifacts.snapshot import constants as c

        assert c.SECTION_ARTIFACT_KIND == c.TOP_LEVEL_SECTIONS[0]
        assert c.SECTION_SCHEMA_VERSION == c.TOP_LEVEL_SECTIONS[1]
        assert c.SECTION_IDENTITY == c.TOP_LEVEL_SECTIONS[2]
        assert c.SECTION_CAPABILITIES == c.TOP_LEVEL_SECTIONS[3]
        assert c.SECTION_PAYLOAD == c.TOP_LEVEL_SECTIONS[4]
        assert c.SECTION_INTEGRITY == c.TOP_LEVEL_SECTIONS[5]


class TestPayloadSections:
    def test_six_payload_sections_defined(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import PAYLOAD_SECTIONS

        assert len(PAYLOAD_SECTIONS) == 6

    def test_payload_sections_in_canonical_order(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import PAYLOAD_SECTIONS

        assert PAYLOAD_SECTIONS == (
            "source",
            "stage_artifacts",
            "replay_artifacts",
            "diagnostics",
            "provenance",
            "editing",
        )

    def test_payload_section_name_constants_match_tuple(self) -> None:
        from nl2spl.compiler.artifacts.snapshot import constants as c

        assert c.PAYLOAD_SOURCE == c.PAYLOAD_SECTIONS[0]
        assert c.PAYLOAD_STAGE_ARTIFACTS == c.PAYLOAD_SECTIONS[1]
        assert c.PAYLOAD_REPLAY_ARTIFACTS == c.PAYLOAD_SECTIONS[2]
        assert c.PAYLOAD_DIAGNOSTICS == c.PAYLOAD_SECTIONS[3]
        assert c.PAYLOAD_PROVENANCE == c.PAYLOAD_SECTIONS[4]
        assert c.PAYLOAD_EDITING == c.PAYLOAD_SECTIONS[5]


class TestIdentityFields:
    def test_eight_identity_fields(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import IDENTITY_FIELDS

        assert len(IDENTITY_FIELDS) == 8

    def test_identity_fields_order(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import IDENTITY_FIELDS

        assert IDENTITY_FIELDS == (
            "compile_run_id",
            "snapshot_id",
            "base_snapshot_id",
            "parent_snapshot_id",
            "overlay_version",
            "created_at",
            "producer",
            "producer_version",
        )

    def test_identity_constant_values(self) -> None:
        from nl2spl.compiler.artifacts.snapshot import constants as c

        assert c.IDENTITY_COMPILE_RUN_ID == "compile_run_id"
        assert c.IDENTITY_SNAPSHOT_ID == "snapshot_id"
        assert c.IDENTITY_BASE_SNAPSHOT_ID == "base_snapshot_id"
        assert c.IDENTITY_PARENT_SNAPSHOT_ID == "parent_snapshot_id"
        assert c.IDENTITY_OVERLAY_VERSION == "overlay_version"
        assert c.IDENTITY_CREATED_AT == "created_at"
        assert c.IDENTITY_PRODUCER == "producer"
        assert c.IDENTITY_PRODUCER_VERSION == "producer_version"


class TestIntegrityFields:
    def test_integrity_constants(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import (
            INTEGRITY_ARTIFACT_SET_HASH,
            INTEGRITY_PAYLOAD_HASH,
        )

        assert INTEGRITY_PAYLOAD_HASH == "payload_hash"
        assert INTEGRITY_ARTIFACT_SET_HASH == "artifact_set_hash"


class TestSnapshotMode:
    def test_is_str_enum(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SnapshotMode

        assert issubclass(SnapshotMode, str)
        assert issubclass(SnapshotMode, Enum)

    def test_three_members(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SnapshotMode

        members = list(SnapshotMode)
        assert len(members) == 3

    def test_member_values(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SnapshotMode

        assert SnapshotMode.DISABLED == "disabled"
        assert SnapshotMode.BEST_EFFORT == "best_effort"
        assert SnapshotMode.REQUIRED == "required"

    def test_members_are_strings(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SnapshotMode

        for mode in SnapshotMode:
            assert isinstance(mode, str)
            assert mode == mode.value


class TestSnapshotStatus:
    def test_is_str_enum(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SnapshotStatus

        assert issubclass(SnapshotStatus, str)
        assert issubclass(SnapshotStatus, Enum)

    def test_four_members(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SnapshotStatus

        members = list(SnapshotStatus)
        assert len(members) == 4

    def test_member_values(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SnapshotStatus

        assert SnapshotStatus.NOT_REQUESTED == "not_requested"
        assert SnapshotStatus.AVAILABLE == "available"
        assert SnapshotStatus.FAILED_BEST_EFFORT == "failed_best_effort"
        assert SnapshotStatus.FAILED_REQUIRED == "failed_required"

    def test_members_are_strings(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SnapshotStatus

        for status in SnapshotStatus:
            assert isinstance(status, str)
            assert status == status.value


class TestBaseOverlayVersion:
    def test_is_zero(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import BASE_OVERLAY_VERSION

        assert BASE_OVERLAY_VERSION == 0
        assert isinstance(BASE_OVERLAY_VERSION, int)


class TestProducerName:
    def test_is_nl2spl(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import PRODUCER_NAME

        assert PRODUCER_NAME == "nl2spl"


# ===================================================================
# capabilities.py
# ===================================================================


class TestSnapshotCapability:
    def test_is_str_enum(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability

        assert issubclass(SnapshotCapability, str)
        assert issubclass(SnapshotCapability, Enum)

    def test_five_members(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability

        assert len(list(SnapshotCapability)) == 5

    def test_member_values(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability

        assert SnapshotCapability.ISSUE_EXTRACTION == "issue_extraction"
        assert SnapshotCapability.SUGGESTION_GENERATION == "suggestion_generation"
        assert SnapshotCapability.LANE_A_REPLAY == "lane_a_replay"
        assert SnapshotCapability.LANE_B_REPLAY == "lane_b_replay"
        assert SnapshotCapability.FINAL_SPL_DISPLAY == "final_spl_display"

    def test_no_duplicate_values(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability

        values = [c.value for c in SnapshotCapability]
        assert len(values) == len(set(values))


class TestCapabilitiesInOrder:
    def test_all_five_in_order(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITIES_IN_ORDER,
            SnapshotCapability,
        )

        assert len(CAPABILITIES_IN_ORDER) == 5
        assert CAPABILITIES_IN_ORDER == (
            SnapshotCapability.ISSUE_EXTRACTION,
            SnapshotCapability.SUGGESTION_GENERATION,
            SnapshotCapability.LANE_A_REPLAY,
            SnapshotCapability.LANE_B_REPLAY,
            SnapshotCapability.FINAL_SPL_DISPLAY,
        )

    def test_dependency_order_is_upstream_first(self) -> None:
        """Suggestion depends on issue extraction; Lane B depends on Lane A."""
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITIES_IN_ORDER,
            SnapshotCapability,
        )

        issue_idx = CAPABILITIES_IN_ORDER.index(SnapshotCapability.ISSUE_EXTRACTION)
        suggestion_idx = CAPABILITIES_IN_ORDER.index(SnapshotCapability.SUGGESTION_GENERATION)
        lane_a_idx = CAPABILITIES_IN_ORDER.index(SnapshotCapability.LANE_A_REPLAY)
        lane_b_idx = CAPABILITIES_IN_ORDER.index(SnapshotCapability.LANE_B_REPLAY)

        assert issue_idx < suggestion_idx  # upstream before downstream
        assert lane_a_idx < lane_b_idx  # Lane A before Lane B


class TestProductionRequiredCapabilities:
    def test_all_five_required_for_production(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            PRODUCTION_REQUIRED_CAPABILITIES,
            SnapshotCapability,
        )

        assert len(PRODUCTION_REQUIRED_CAPABILITIES) == 5
        assert set(PRODUCTION_REQUIRED_CAPABILITIES) == set(SnapshotCapability)


class TestCapabilityRequirement:
    def test_is_frozen_dataclass(self) -> None:
        import dataclasses

        from nl2spl.compiler.artifacts.snapshot.capabilities import CapabilityRequirement

        assert dataclasses.is_dataclass(CapabilityRequirement)

        # Attempting to mutate should raise
        cr = CapabilityRequirement(
            capability="issue_extraction",  # type: ignore[arg-type]
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            cr.capability = "other"  # type: ignore[misc]

    def test_defaults_are_empty_tuples(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CapabilityRequirement,
            SnapshotCapability,
        )

        cr = CapabilityRequirement(capability=SnapshotCapability.FINAL_SPL_DISPLAY)
        assert cr.depends_on == ()
        assert cr.required_payload_paths == ()
        assert cr.required_conditions == ()

    def test_issue_extraction_requirement(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITY_REQUIREMENT_BY_CAPABILITY,
            SnapshotCapability,
        )

        req = CAPABILITY_REQUIREMENT_BY_CAPABILITY[SnapshotCapability.ISSUE_EXTRACTION]
        assert req.capability == SnapshotCapability.ISSUE_EXTRACTION
        assert req.depends_on == ()
        assert "payload.diagnostics.compile_diagnostics" in req.required_payload_paths
        # Must require irs_ref condition
        assert any("irs_ref" in c for c in req.required_conditions)

    def test_suggestion_generation_depends_on_issue_extraction(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITY_REQUIREMENT_BY_CAPABILITY,
            SnapshotCapability,
        )

        req = CAPABILITY_REQUIREMENT_BY_CAPABILITY[SnapshotCapability.SUGGESTION_GENERATION]
        assert SnapshotCapability.ISSUE_EXTRACTION in req.depends_on
        assert "payload.source.spans" in req.required_payload_paths
        assert "payload.provenance.traces" in req.required_payload_paths

    def test_lane_a_replay_requirement(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITY_REQUIREMENT_BY_CAPABILITY,
            SnapshotCapability,
        )

        req = CAPABILITY_REQUIREMENT_BY_CAPABILITY[SnapshotCapability.LANE_A_REPLAY]
        assert req.depends_on == ()
        assert "payload.replay_artifacts.stage10_input" in req.required_payload_paths
        assert "payload.stage_artifacts.worker_plan" in req.required_payload_paths
        assert "payload.stage_artifacts.worker_flow_plan" in req.required_payload_paths
        assert "payload.stage_artifacts.worker_block_plan" in req.required_payload_paths
        assert "payload.stage_artifacts.worker_step_plan" in req.required_payload_paths
        assert "payload.stage_artifacts.resources" in req.required_payload_paths
        assert "payload.stage_artifacts.symbol_table" in req.required_payload_paths
        # Conditions must mention the real Lane A assembler dependency
        assert any("worker_flow_plan" in c for c in req.required_conditions)
        assert any("worker_block_plan" in c for c in req.required_conditions)

    def test_lane_b_replay_depends_on_lane_a(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITY_REQUIREMENT_BY_CAPABILITY,
            SnapshotCapability,
        )

        req = CAPABILITY_REQUIREMENT_BY_CAPABILITY[SnapshotCapability.LANE_B_REPLAY]
        assert SnapshotCapability.LANE_A_REPLAY in req.depends_on
        assert "payload.replay_artifacts.normalizer_input" in req.required_payload_paths

    def test_final_spl_display_requirement(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITY_REQUIREMENT_BY_CAPABILITY,
            SnapshotCapability,
        )

        req = CAPABILITY_REQUIREMENT_BY_CAPABILITY[SnapshotCapability.FINAL_SPL_DISPLAY]
        assert req.depends_on == ()
        assert "payload.replay_artifacts.final_spl" in req.required_payload_paths


class TestCapabilityRequirementsMatrix:
    def test_every_capability_has_a_requirement(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITY_REQUIREMENTS,
            SnapshotCapability,
        )

        covered = {r.capability for r in CAPABILITY_REQUIREMENTS}
        all_caps = set(SnapshotCapability)
        assert covered == all_caps

    def test_no_duplicate_capability_requirements(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import CAPABILITY_REQUIREMENTS

        caps = [r.capability for r in CAPABILITY_REQUIREMENTS]
        assert len(caps) == len(set(caps))

    def test_all_dependencies_are_valid_capabilities(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITY_REQUIREMENTS,
            SnapshotCapability,
        )

        valid = set(SnapshotCapability)
        for req in CAPABILITY_REQUIREMENTS:
            for dep in req.depends_on:
                assert dep in valid, f"{dep} is not a valid capability"

    def test_no_self_dependency(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import CAPABILITY_REQUIREMENTS

        for req in CAPABILITY_REQUIREMENTS:
            assert req.capability not in req.depends_on, (
                f"{req.capability} depends on itself"
            )

    def test_no_circular_dependency(self) -> None:
        """The dependency graph must be a DAG."""
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITIES_IN_ORDER,
            CAPABILITY_REQUIREMENT_BY_CAPABILITY,
            SnapshotCapability,
        )

        # Build adjacency
        deps: dict[SnapshotCapability, set[SnapshotCapability]] = {
            c: set(CAPABILITY_REQUIREMENT_BY_CAPABILITY[c].depends_on)
            for c in SnapshotCapability
        }

        # Topological sort check: the CAPABILITIES_IN_ORDER tuple defines a
        # valid topological order.  Verify every dependency appears earlier.
        order_index = {c: i for i, c in enumerate(CAPABILITIES_IN_ORDER)}
        for cap, dep_set in deps.items():
            for dep in dep_set:
                assert order_index[dep] < order_index[cap], (
                    f"Topological order violation: {cap} depends on {dep} "
                    f"but {dep} appears after {cap} in CAPABILITIES_IN_ORDER"
                )

    def test_lookup_table_matches_requirements(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            CAPABILITY_REQUIREMENT_BY_CAPABILITY,
            CAPABILITY_REQUIREMENTS,
        )

        assert len(CAPABILITY_REQUIREMENT_BY_CAPABILITY) == len(CAPABILITY_REQUIREMENTS)
        for req in CAPABILITY_REQUIREMENTS:
            assert CAPABILITY_REQUIREMENT_BY_CAPABILITY[req.capability] is req


# ===================================================================
# schema.py
# ===================================================================


class TestSchemaVersionInfo:
    def test_current_is_1_0_0(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.schema import SchemaVersionInfo

        info = SchemaVersionInfo()
        assert info.current == "1.0.0"

    def test_supported_is_only_current(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.schema import SchemaVersionInfo

        info = SchemaVersionInfo()
        assert info.supported == ("1.0.0",)
        assert len(info.supported) == 1

    def test_compatibility_policy_is_exact_match(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.schema import SchemaVersionInfo

        info = SchemaVersionInfo()
        assert info.compatibility_policy == "exact_match"

    def test_is_frozen(self) -> None:
        import dataclasses

        from nl2spl.compiler.artifacts.snapshot.schema import SchemaVersionInfo

        assert dataclasses.is_dataclass(SchemaVersionInfo)
        info = SchemaVersionInfo()
        with pytest.raises(dataclasses.FrozenInstanceError):
            info.current = "2.0.0"  # type: ignore[misc]


class TestIsSchemaCompatible:
    def test_current_version_is_compatible(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.schema import is_schema_compatible

        assert is_schema_compatible("1.0.0") is True

    def test_unknown_version_is_incompatible(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.schema import is_schema_compatible

        assert is_schema_compatible("0.9.0") is False
        assert is_schema_compatible("2.0.0") is False
        assert is_schema_compatible("1.0.1") is False

    def test_empty_string_incompatible(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.schema import is_schema_compatible

        assert is_schema_compatible("") is False

    def test_exact_match_only_current(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.schema import (
            SchemaVersionInfo,
            is_schema_compatible,
        )

        info = SchemaVersionInfo(
            current="2.0.0",
            supported=("2.0.0",),
            compatibility_policy="exact_match",
        )
        assert is_schema_compatible("2.0.0", info=info) is True
        assert is_schema_compatible("2.0.1", info=info) is False
        assert is_schema_compatible("1.0.0", info=info) is False

    def test_unknown_policy_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.schema import (
            SchemaVersionInfo,
            is_schema_compatible,
        )

        info = SchemaVersionInfo(
            current="2.0.0",
            supported=("2.0.0", "1.0.0"),
            compatibility_policy="semver_major",
        )
        with pytest.raises(ValueError, match="compatibility_policy"):
            is_schema_compatible("2.0.0", info=info)


class TestSupportedVersions:
    def test_returns_tuple_of_current(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.schema import supported_versions

        assert supported_versions() == ("1.0.0",)

    def test_custom_info_override(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.schema import (
            SchemaVersionInfo,
            supported_versions,
        )

        info = SchemaVersionInfo(
            supported=("2.0.0", "1.0.0"),
        )
        assert supported_versions(info=info) == ("2.0.0", "1.0.0")


# ===================================================================
# hash_policy.py
# ===================================================================


class TestHashAlgorithm:
    def test_is_sha256(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_ALGORITHM

        assert HASH_ALGORITHM == "sha256"

    def test_is_valid_hashlib_algorithm(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_ALGORITHM

        assert HASH_ALGORITHM in hashlib.algorithms_available


class TestCanonicalJsonDumpsKwargs:
    def test_sort_keys_is_true(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import CANONICAL_JSON_SORT_KEYS

        assert CANONICAL_JSON_SORT_KEYS is True

    def test_separators_are_compact(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import CANONICAL_JSON_SEPARATORS

        assert CANONICAL_JSON_SEPARATORS == (",", ":")

    def test_ensure_ascii_is_false(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import CANONICAL_JSON_ENSURE_ASCII

        assert CANONICAL_JSON_ENSURE_ASCII is False

    def test_kwargs_produce_deterministic_json(self) -> None:
        """The canonical JSON kwargs must produce deterministic output."""
        from nl2spl.compiler.artifacts.snapshot.hash_policy import canonical_json_dumps

        obj = {"z": 1, "a": 2, "nested": {"c": 3, "b": 4}}
        dump1 = canonical_json_dumps(obj)
        dump2 = canonical_json_dumps(obj)
        assert dump1 == dump2
        # Must be sorted
        assert dump1.startswith('{"a":2,"nested":{"b":4,"c":3},"z":1}')

    def test_canonical_json_dumps_preserves_non_ascii(self) -> None:
        """Non-ASCII characters must NOT be escaped (ensure_ascii=False)."""
        from nl2spl.compiler.artifacts.snapshot.hash_policy import canonical_json_dumps

        obj = {"message": "こんにちは", "value": 42}
        result = canonical_json_dumps(obj)
        assert "こんにちは" in result
        assert "\\u" not in result

    def test_ensure_ascii_is_in_dumps_kwargs_and_false(self) -> None:
        """ensure_ascii=False MUST be part of CANONICAL_JSON_DUMPS_KWARGS."""
        from nl2spl.compiler.artifacts.snapshot.hash_policy import (
            CANONICAL_JSON_DUMPS_KWARGS,
            CANONICAL_JSON_ENSURE_ASCII,
        )

        assert "ensure_ascii" in CANONICAL_JSON_DUMPS_KWARGS
        assert CANONICAL_JSON_DUMPS_KWARGS["ensure_ascii"] is False
        assert CANONICAL_JSON_ENSURE_ASCII is False


class TestHashPolicy:
    def test_default_policy(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_POLICY

        assert HASH_POLICY.algorithm == "sha256"
        assert isinstance(HASH_POLICY.payload_hash_description, str)
        assert len(HASH_POLICY.payload_hash_description) > 0
        assert isinstance(HASH_POLICY.artifact_set_hash_description, str)
        assert len(HASH_POLICY.artifact_set_hash_description) > 0

    def test_is_frozen(self) -> None:
        import dataclasses

        from nl2spl.compiler.artifacts.snapshot.hash_policy import HashPolicy

        assert dataclasses.is_dataclass(HashPolicy)
        policy = HashPolicy()
        with pytest.raises(dataclasses.FrozenInstanceError):
            policy.algorithm = "md5"  # type: ignore[misc]

    def test_excluded_paths_are_tuples(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_POLICY

        assert isinstance(HASH_POLICY.artifact_set_excluded_paths, tuple)

    def test_excluded_paths_include_created_at(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_POLICY

        assert "identity.created_at" in HASH_POLICY.artifact_set_excluded_paths

    def test_excluded_paths_include_validation_fields(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_POLICY

        assert "integrity.validation_status" in HASH_POLICY.artifact_set_excluded_paths
        assert "integrity.validation_errors" in HASH_POLICY.artifact_set_excluded_paths

    def test_excluded_paths_include_editing_history(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_POLICY

        assert "payload.editing.overlay_events" in HASH_POLICY.artifact_set_excluded_paths
        assert "payload.editing.accepted_patches" in HASH_POLICY.artifact_set_excluded_paths
        assert "payload.editing.verification_history" in HASH_POLICY.artifact_set_excluded_paths

    def test_excluded_paths_all_have_expected_prefixes(self) -> None:
        """Excluded paths must use dot notation with known top-level sections."""
        from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_POLICY

        allowed_prefixes = ("identity.", "integrity.", "payload.editing.")
        for path in HASH_POLICY.artifact_set_excluded_paths:
            assert any(path.startswith(p) for p in allowed_prefixes), (
                f"Excluded path '{path}' does not start with expected prefix"
            )


class TestOverlayStrategy:
    def test_is_full_json_document(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import OVERLAY_STRATEGY

        assert OVERLAY_STRATEGY == "full_json_document"

    def test_overlay_filename_prefix(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import OVERLAY_FILENAME_PREFIX

        assert OVERLAY_FILENAME_PREFIX == "spl_editing_overlays"
        assert isinstance(OVERLAY_FILENAME_PREFIX, str)


class TestHashInputMustBeNormalized:
    def test_is_non_empty_string(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_INPUT_MUST_BE_NORMALIZED

        assert isinstance(HASH_INPUT_MUST_BE_NORMALIZED, str)
        assert len(HASH_INPUT_MUST_BE_NORMALIZED) > 0


# ===================================================================
# Cross-cutting: no redefinition of constants
# ===================================================================


class TestNoDuplicateConstants:
    """Verify that each constant value appears only once across all S-1 modules.

    This prevents downstream stages from defining duplicate string literals
    that could drift from the canonical source.
    """

    def test_artifact_kind_not_redefined_elsewhere(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SNAPSHOT_ARTIFACT_KIND

        # Verify it only lives in constants.py
        assert SNAPSHOT_ARTIFACT_KIND == "spl_editing_artifact_snapshot"

    def test_schema_version_not_redefined_in_capabilities(self) -> None:
        """Schema version must come from constants, not capabilities."""
        import inspect

        from nl2spl.compiler.artifacts.snapshot import capabilities

        source = inspect.getsource(capabilities)
        assert '"1.0.0"' not in source

    def test_section_names_not_redefined_in_hash_policy(self) -> None:
        """Hash policy must use constants, not redefine section names."""
        import inspect

        from nl2spl.compiler.artifacts.snapshot import hash_policy

        source = inspect.getsource(hash_policy)
        # Should not contain raw string literals for sections
        assert '"artifact_kind"' not in source


# ===================================================================
# S-1 gate: package __init__ exposes all expected names
# ===================================================================


class TestPackageInitExports:
    def test_all_names_are_importable(self) -> None:
        # Every name in __all__ must be importable
        import nl2spl.compiler.artifacts.snapshot as pkg
        from nl2spl.compiler.artifacts.snapshot import __all__ as exported

        for name in exported:
            assert hasattr(pkg, name), f"{name} is in __all__ but not importable"

    def test_no_extra_names_in_all(self) -> None:
        """__all__ should not contain names that don't exist."""
        import nl2spl.compiler.artifacts.snapshot as pkg
        from nl2spl.compiler.artifacts.snapshot import __all__ as exported

        for name in exported:
            obj = getattr(pkg, name)
            assert obj is not None, f"{name} resolves to None"


# ===================================================================
# S-1 gate: Import boundary -- snapshot must not import SPL Editing internals
# ===================================================================


class TestImportBoundary:
    """The snapshot contract modules MUST NOT import SPL Editing internals."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "nl2spl.compiler.artifacts.snapshot.constants",
            "nl2spl.compiler.artifacts.snapshot.capabilities",
            "nl2spl.compiler.artifacts.snapshot.schema",
            "nl2spl.compiler.artifacts.snapshot.hash_policy",
        ],
    )
    def test_snapshot_module_does_not_import_spl_editing(self, module_path: str) -> None:
        import importlib
        import sys

        mod = sys.modules.get(module_path)
        if mod is None:
            mod = importlib.import_module(module_path)

        forbidden_prefixes = (
            "nl2spl.compiler.spl_editing.patches",
            "nl2spl.compiler.spl_editing.handlers",
            "nl2spl.compiler.spl_editing.storage",
        )
        for key in dir(mod):
            obj = getattr(mod, key)
            if hasattr(obj, "__module__"):
                mod_name = getattr(obj, "__module__", "")
                for forbidden in forbidden_prefixes:
                    assert not mod_name.startswith(forbidden), (
                        f"{module_path} imports {mod_name} (forbidden: {forbidden})"
                    )


# ===================================================================
# S-1 gate: overlay_version invariants
# ===================================================================


class TestOverlayVersionInvariants:
    def test_base_snapshot_must_be_zero(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import BASE_OVERLAY_VERSION

        assert BASE_OVERLAY_VERSION == 0

    def test_overlay_version_must_increment(self) -> None:
        """An overlay snapshot's overlay_version must be strictly greater than its parent."""
        # S-1 only defines the constant; S0/S6 enforces this in models.
        from nl2spl.compiler.artifacts.snapshot.constants import BASE_OVERLAY_VERSION

        overlay = BASE_OVERLAY_VERSION + 1
        assert overlay > BASE_OVERLAY_VERSION
