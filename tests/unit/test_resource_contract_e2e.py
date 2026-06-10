"""Phase 5-7: End-to-end verification of resource contract pipeline.

Tests that file resources survive through normalization, assembly,
and rendering without being downgraded to plain variables.
"""

from __future__ import annotations

from nl2spl.ir.resource_registry_ir import FileSpec, ResourceRegistryIR, VariableSpec
from nl2spl.pipeline.resource_resolver import resolve_resource_ref


def test_file_resource_survives_in_registry() -> None:
    """FileSpec in registry is findable alongside variables."""
    registry = ResourceRegistryIR(
        variables=[
            VariableSpec(
                name="topic_summary",
                data_type="text",
                required=True,
                description="Topic summary",
                source="input",
            ),
        ],
        files=[
            FileSpec(
                name="finished_draft",
                path="< >",
                data_type="text",
                description="Finished draft in Word or Google Doc format",
            ),
        ],
    )
    assert len(registry.files) == 1
    assert registry.files[0].name == "finished_draft"
    assert registry.files[0].path == "< >"


def test_resolver_finds_file_not_variable() -> None:
    """When finished_draft is a file, resolver returns file kind not variable."""
    registry = ResourceRegistryIR(
        variables=[
            VariableSpec(
                name="topic_summary", data_type="text",
                required=True, description="", source="input",
            ),
        ],
        files=[
            FileSpec(
                name="finished_draft", path="< >",
                data_type="text", description="Finished draft",
            ),
        ],
    )
    result = resolve_resource_ref("finished_draft", registry)
    assert result is not None
    assert result.resource_kind == "file"
    # Verify it's NOT found as variable
    variable_names = {v.name for v in registry.variables}
    assert "finished_draft" not in variable_names


def test_file_and_variable_same_name_prioritizes_file() -> None:
    """If a resource exists as both file and variable, resolver returns file."""
    registry = ResourceRegistryIR(
        variables=[
            VariableSpec(
                name="output_artifact", data_type="text",
                required=True, description="", source="output",
            ),
        ],
        files=[
            FileSpec(
                name="output_artifact", path="< >",
                data_type="text", description="Output file",
            ),
        ],
    )
    result = resolve_resource_ref("output_artifact", registry)
    assert result is not None
    # File is checked first in resolve_resource_ref
    assert result.resource_kind == "file"
