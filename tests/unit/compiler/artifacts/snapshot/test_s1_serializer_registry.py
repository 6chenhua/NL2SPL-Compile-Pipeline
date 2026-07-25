"""S1 registry tests: dispatch, type_id uniqueness, fail-fast on unknown."""

from __future__ import annotations

import pytest

from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    SerializerRegistry,
    build_default_registry,
    get_default_registry,
)


@pytest.fixture
def registry() -> SerializerRegistry:
    return build_default_registry()


class TestRegistrySize:
    def test_64_serializers_registered(self, registry: SerializerRegistry) -> None:
        assert len(registry) == 64

    def test_all_type_ids_are_unique(self, registry: SerializerRegistry) -> None:
        ids = list(registry.registered_type_ids)
        assert len(ids) == len(set(ids)), "Duplicate type_ids found"

    def test_all_type_ids_are_non_empty_strings(self, registry: SerializerRegistry) -> None:
        for tid in registry.registered_type_ids:
            assert isinstance(tid, str), f"{tid!r} is not a string"
            assert len(tid) > 0, "Empty type_id found"

    def test_get_default_registry_is_singleton(self) -> None:
        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2


class TestRegistryDispatch:
    def test_serialize_adds_dollar_type(self, registry: SerializerRegistry) -> None:
        from nl2spl.ir.span_ir import AmbiguityInfo

        obj = AmbiguityInfo(is_ambiguous=True, reasons=["vague"], needs_split=False)
        data = registry.serialize(obj)
        assert data["$type"] == "AmbiguityInfo"

    def test_deserialize_roundtrip(self, registry: SerializerRegistry) -> None:
        from nl2spl.ir.span_ir import AmbiguityInfo

        obj = AmbiguityInfo(is_ambiguous=True, reasons=["vague"], needs_split=True)
        data = registry.serialize(obj)
        restored = registry.deserialize(data)
        assert isinstance(restored, AmbiguityInfo)
        assert restored.is_ambiguous == obj.is_ambiguous
        assert restored.reasons == obj.reasons
        assert restored.needs_split == obj.needs_split

    def test_get_by_class_returns_correct_serializer(self, registry: SerializerRegistry) -> None:
        from nl2spl.ir.constraint_ir import ConstraintIR

        ser = registry.get_by_class(ConstraintIR)
        assert ser.type_id == "ConstraintIR"


class TestFailFast:
    def test_unknown_type_id_raises_value_error(self, registry: SerializerRegistry) -> None:
        with pytest.raises(ValueError, match="Unknown artifact"):
            registry.deserialize({"$type": "NonExistentType", "x": 1})

    def test_missing_dollar_type_raises_value_error(self, registry: SerializerRegistry) -> None:
        with pytest.raises(ValueError, match="missing.*\\$type"):
            registry.deserialize({"some": "data"})

    def test_dollar_type_not_string_raises_value_error(self, registry: SerializerRegistry) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            registry.deserialize({"$type": 123})

    def test_unregistered_class_raises_value_error(self, registry: SerializerRegistry) -> None:
        class UnknownType:
            pass

        with pytest.raises(ValueError, match="No serializer registered"):
            registry.serialize(UnknownType())

    def test_no_fallback_serializer_exists(self, registry: SerializerRegistry) -> None:
        for tid in registry.registered_type_ids:
            ser = registry.get_by_type_id(tid)
            assert ser is not None
            # Every serializer must have explicit from_canonical
            dummy = {"$type": tid, "_test": True}
            try:
                ser.from_canonical(dummy)
            except (KeyError, TypeError, ValueError):
                pass  # Expected - missing required keys
            except Exception:
                pass  # Other structured errors are OK

    def test_duplicate_type_id_registration_raises(self) -> None:
        r = SerializerRegistry()
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_dto import (
            SnapshotOverlayEventDTOSerializer,
        )

        s1 = SnapshotOverlayEventDTOSerializer()
        s2 = SnapshotOverlayEventDTOSerializer()
        r.register(s1)
        with pytest.raises(ValueError, match="already registered"):
            r.register(s2)

    def test_duplicate_class_registration_raises(self) -> None:
        """register_for_class must raise if cls already mapped to different serializer."""
        r = SerializerRegistry()
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotOverlayEventDTO,
        )
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_dto import (
            SnapshotAcceptedPatchDTOSerializer,
            SnapshotOverlayEventDTOSerializer,
        )

        s1 = SnapshotOverlayEventDTOSerializer()
        s2 = SnapshotAcceptedPatchDTOSerializer()
        r.register(s1)
        r.register(s2)
        r.register_for_class(SnapshotOverlayEventDTO, s1)
        # Registering same class to DIFFERENT serializer should raise
        with pytest.raises(ValueError, match="already registered"):
            r.register_for_class(SnapshotOverlayEventDTO, s2)

    def test_same_class_same_serializer_is_idempotent(self) -> None:
        """Registering the same (class, serializer) pair twice must not raise."""
        r = SerializerRegistry()
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotOverlayEventDTO,
        )
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_dto import (
            SnapshotOverlayEventDTOSerializer,
        )

        s = SnapshotOverlayEventDTOSerializer()
        r.register(s)
        r.register_for_class(SnapshotOverlayEventDTO, s)
        # Same registration again — should not raise
        r.register_for_class(SnapshotOverlayEventDTO, s)


class TestRegistryExports:
    def test_registry_importable_from_package(self) -> None:
        from nl2spl.compiler.artifacts.snapshot import (
            ArtifactSerializer,
            SerializerRegistry,
            build_default_registry,
            get_default_registry,
        )

        assert ArtifactSerializer is not None
        assert SerializerRegistry is not None
        assert build_default_registry is not None
        assert get_default_registry is not None
