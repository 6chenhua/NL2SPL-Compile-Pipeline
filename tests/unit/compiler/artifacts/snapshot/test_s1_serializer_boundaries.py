"""S1 serializer boundary tests: import safety, no asdict, no fallback."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]

_SERIALIZER_MODULES = [
    "nl2spl.compiler.artifacts.snapshot.serialization.serializers_dto",
    "nl2spl.compiler.artifacts.snapshot.serialization.serializers_diagnostics",
    "nl2spl.compiler.artifacts.snapshot.serialization.serializers_compile",
    "nl2spl.compiler.artifacts.snapshot.serialization.serializers_symbol",
    "nl2spl.compiler.artifacts.snapshot.serialization.serializers_resource",
    "nl2spl.compiler.artifacts.snapshot.serialization.serializers_source",
    "nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan",
    "nl2spl.compiler.artifacts.snapshot.serialization.serializers_assembly",
]

_SERIALIZER_FILES = [
    "src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_dto.py",
    "src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_diagnostics.py",
    "src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_compile.py",
    "src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_symbol.py",
    "src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_resource.py",
    "src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_source.py",
    "src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_plan.py",
    "src/nl2spl/compiler/artifacts/snapshot/serialization/serializers_assembly.py",
    "src/nl2spl/compiler/artifacts/snapshot/serialization/registry.py",
]


def _read_repo_file(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


class TestImportBoundary:
    """S1 serializers MUST NOT import SPL Editing runtime internals."""

    FORBIDDEN = (
        "nl2spl.compiler.spl_editing.patches",
        "nl2spl.compiler.spl_editing.handlers",
        "nl2spl.compiler.spl_editing.storage",
    )

    @pytest.mark.parametrize("module_path", _SERIALIZER_MODULES)
    def test_serializer_does_not_import_spl_editing(self, module_path: str) -> None:
        import importlib
        import sys

        mod = sys.modules.get(module_path)
        if mod is None:
            mod = importlib.import_module(module_path)

        for key in dir(mod):
            obj = getattr(mod, key)
            if hasattr(obj, "__module__"):
                mod_name = getattr(obj, "__module__", "")
                for forbidden in self.FORBIDDEN:
                    assert not mod_name.startswith(forbidden), (
                        f"{module_path} imports {mod_name} (forbidden: {forbidden})"
                    )

    @pytest.mark.parametrize("module_path", _SERIALIZER_MODULES)
    def test_serializer_does_not_import_llm(self, module_path: str) -> None:
        import importlib
        import sys

        mod = sys.modules.get(module_path)
        if mod is None:
            mod = importlib.import_module(module_path)

        source = inspect.getsource(mod)
        assert "LLMClient" not in source, f"{module_path} must not call LLM"
        assert "llm_client" not in source.lower(), f"{module_path} must not call LLM"

    @pytest.mark.parametrize("relative_path", _SERIALIZER_FILES)
    def test_serializer_does_not_import_report_modules(self, relative_path: str) -> None:
        source = _read_repo_file(relative_path)
        assert "feedback_report_renderer" not in source
        assert "report_renderer" not in source

    @pytest.mark.parametrize("relative_path", _SERIALIZER_FILES)
    def test_serializer_does_not_import_persistence(self, relative_path: str) -> None:
        source = _read_repo_file(relative_path)
        assert "load_intermediate_result" not in source
        assert "save_intermediate_result" not in source

    @pytest.mark.parametrize("relative_path", _SERIALIZER_FILES)
    def test_serializer_does_not_read_final_spl_txt(self, relative_path: str) -> None:
        source = _read_repo_file(relative_path)
        assert "final_spl.txt" not in source


class TestNoAsdictInProductionCode:
    @pytest.mark.parametrize("relative_path", _SERIALIZER_FILES)
    def test_no_asdict_import(self, relative_path: str) -> None:
        """dataclasses.asdict must not be imported in any serializer file."""
        source = _read_repo_file(relative_path)
        assert "from dataclasses import" not in source or "asdict" not in source.split("from dataclasses import")[-1].split("\n")[0], (  # noqa: E501
            f"{relative_path} must not import asdict"
        )
        # Broader check: import asdict from anywhere
        lines = source.split("\n")
        import_lines = [ln for ln in lines if "import" in ln and "asdict" in ln]
        assert len(import_lines) == 0, (
            f"{relative_path} imports asdict: {import_lines}"
        )

    @pytest.mark.parametrize("relative_path", _SERIALIZER_FILES)
    def test_no_dict_attribute_fallback(self, relative_path: str) -> None:
        """__dict__ must not be used as serialization fallback."""
        source = _read_repo_file(relative_path)
        assert ".__dict__" not in source, (
            f"{relative_path} must not use __dict__ for serialization"
        )

    @pytest.mark.parametrize("relative_path", _SERIALIZER_FILES)
    def test_no_str_obj_fallback(self, relative_path: str) -> None:
        """str(obj) must not be used as serialization fallback."""
        source = _read_repo_file(relative_path)
        # Allow str() for path, but not as generic fallback
        assert "default=str" not in source, (
            f"{relative_path} must not use default=str fallback"
        )


class TestNoFallbackInSerializer:
    def test_registry_has_no_fallback_for_unknown(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
            SerializerRegistry,
        )

        r = SerializerRegistry()
        with pytest.raises(ValueError):
            r.deserialize({"$type": "Anything"})

    def test_registry_has_no_fallback_class(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
            SerializerRegistry,
        )

        r = SerializerRegistry()
        with pytest.raises(ValueError):
            r.serialize("plain_string")  # type: ignore[arg-type]


class TestCanonicalJsonCompat:
    """Serializer output must be JSON-serializable with canonical kwargs."""

    def test_all_serializers_produce_json_safe_output(self) -> None:
        import json

        from nl2spl.compiler.artifacts.snapshot.hash_policy import (
            CANONICAL_JSON_DUMPS_KWARGS,
        )
        from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
            build_default_registry,
        )
        from nl2spl.ir.span_ir import SpanIR

        reg = build_default_registry()
        span = SpanIR(span_id="s_test", text="Test content")
        data = reg.serialize(span)
        # Must not raise TypeError
        result = json.dumps(data, **CANONICAL_JSON_DUMPS_KWARGS)
        assert len(result) > 0
        # Verify no Python repr leaked
        assert "SpanIR(" not in result
        assert "object at 0x" not in result

    def test_agent_profile_serializer_preserves_provenance(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
            build_default_registry,
        )
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, Concept, PersonaIR

        reg = build_default_registry()
        profile = AgentProfileIR(
            persona=PersonaIR(
                role="Internal communications specialist",
                aspects=[
                    Aspect(
                        name="EvidenceDriven",
                        text="Maintains provenance.",
                        source_span_ids=["s1"],
                        source_section_id="sec_profile",
                        source_packet_id="p_profile",
                        provenance_relation="direct",
                    )
                ],
                source_span_ids=["s1"],
                source_section_id="sec_profile",
                source_packet_id="p_profile",
                provenance_relation="inferred",
            ),
            audience_aspects=[
                Aspect(
                    name="Executives",
                    text="Senior leaders.",
                    source_span_ids=["s2"],
                    provenance_relation="direct",
                )
            ],
            concepts=[
                Concept(
                    term="Provenance",
                    definition="Traceable origin.",
                    source_span_ids=["s3"],
                    provenance_relation="normalized",
                )
            ],
        )

        restored = reg.deserialize(reg.serialize(profile))

        assert restored == profile

    def test_legacy_agent_profile_payload_defaults_to_assumed_without_spans(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_compile import (
            PersonaIRSerializer,
        )

        restored = PersonaIRSerializer().from_canonical(
            {
                "$type": "PersonaIR",
                "role": "General Assistant",
                "aspects": [],
            }
        )

        assert restored.source_span_ids == []
        assert restored.provenance_relation == "assumed"


class TestNoPythonReprInPayload:
    """Verify canonical payloads contain no Python object representations."""

    def test_dto_payload_no_repr(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotOverlayEventDTO,
        )
        from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
            build_default_registry,
        )

        reg = build_default_registry()
        dto = SnapshotOverlayEventDTO(
            overlay_id="ov", base_compile_run_id="r", base_artifact_snapshot_id="s",
            overlay_version=1, patch_type="t", affordance_id="a", patch_id="p",
            accepted=True,
        )
        data = reg.serialize(dto)
        payload_str = str(data)
        assert "<" not in payload_str or "$type" in payload_str

    def test_diagnostics_payload_no_repr(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
            build_default_registry,
        )
        from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef

        reg = build_default_registry()
        diag = CompileDiagnostic(
            diagnostic_id="D", kind="missing_handler", severity="warning",
            message="test", metadata={"irs_ref": DiagnosticIRSRef("T", "id", "slot")},
        )
        data = reg.serialize(diag)
        payload_str = str(data)
        assert "CompileDiagnostic(" not in payload_str
        assert "object at 0x" not in payload_str
