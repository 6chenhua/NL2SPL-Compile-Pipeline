"""R12.0 static audit and transition guards for SPL editing repair strategy codebases."""

from __future__ import annotations

import ast
import pathlib

from nl2spl.compiler.construct_registry import SPLConstructRegistry


def test_no_r12_placeholders_in_src() -> None:
    """Ensure no future R12+ models are imported by production code outside allowed model directories.

    This test audits *import statements only* in production source files.
    It does NOT check for name usage via ast.Name nodes because those nodes match
    any Python identifier expression \u2014 including local variables, attribute access
    targets, and string literals parsed by ast.literal_eval \u2014 which would produce
    excessive false positives and is not the actual boundary we need to protect.

    The boundary we protect is:
    - Production code (outside strategy/closure/preview/stage_slices dirs) must
      not import R12+ modules or names directly.
    """
    src_dir = pathlib.Path("src/nl2spl")
    forbidden_names = {
        "RepairStrategySpec",
        "RepairDirective",
        "ConstructClosurePlan",
        "RepairModeStageSlice",
        "PreviewMaterializationResult",
        "StageSliceInput",
        "StageSliceResult",
        "ConstructClosureNode",
    }

    allowed_r12_1_paths = {
        "src/nl2spl/compiler/spl_editing/strategy",
        "src/nl2spl/compiler/spl_editing/preview",
        "src/nl2spl/compiler/spl_editing/closure",
        "src/nl2spl/compiler/spl_editing/stage_slices",
        "src/nl2spl/rendering",
        "src/nl2spl/compiler/spl_editing/materialization",
        "src/nl2spl/compiler/spl_editing/cli.py",
    }

    for py_file in src_dir.glob("**/*.py"):
        # Normalize path separators to forward slash
        file_path_str = py_file.as_posix()
        # If the file is inside the allowed R12.1 model directories, skip it
        if any(file_path_str.startswith(p) for p in allowed_r12_1_paths):
            continue

        content = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    parts = node.module.split(".")
                    if (
                        len(parts) >= 4
                        and parts[0] == "nl2spl"
                        and parts[1] == "compiler"
                        and parts[2] == "spl_editing"
                    ):
                        if parts[3] in (
                            "strategy",
                            "preview",
                            "closure",
                            "stage_slices",
                        ):
                            raise AssertionError(
                                f"Forbidden R12+ module import '{node.module}' in {py_file}"
                            )
                for alias in node.names:
                    assert alias.name not in forbidden_names, (
                        f"Forbidden R12+ entity '{alias.name}' imported in {py_file}"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_names, (
                        f"Forbidden R12+ entity '{alias.name}' imported in {py_file}"
                    )
            # ast.Name nodes are intentionally NOT checked here:
            # they match any identifier expression, not just import violations.



def test_no_r12_strategies_as_patch_types() -> None:
    """Verify that construct registry affordances do not use R12+ strategy names as patch types."""
    registry = SPLConstructRegistry.default()
    forbidden_strategies = {
        "CompleteExceptionHandlerAction",
        "MaterializeRequiredOutputProducer",
        "CompleteWorkerHandoffContract",
        "MaterializeInvocationPoint",
        "CompleteApiActionContract",
    }
    for construct_type in registry.list_constructs():
        construct = registry.get(construct_type)
        for slot in construct.slots:
            for affordance in slot.repair_affordances:
                for patch_type in affordance.supported_patch_types:
                    assert patch_type not in forbidden_strategies, (
                        f"Affordance '{affordance.affordance_id}' uses strategy name '{patch_type}' as patch type."
                    )


def test_no_diagnostic_message_parsing_in_materializer_patches() -> None:
    """Verify that materializers, patches, and stage slices do not parse diagnostic messages."""
    scan_dirs = [
        pathlib.Path("src/nl2spl/compiler/spl_editing/patches"),
        pathlib.Path("src/nl2spl/compiler/spl_editing/materialization"),
        pathlib.Path("src/nl2spl/compiler/spl_editing/stage_slices"),
    ]
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for py_file in scan_dir.glob("**/*.py"):
            content = py_file.read_text(encoding="utf-8")

            # Statically parse the AST to look for re imports
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        if name.name == "re" and py_file.name != "id_allocator.py":
                            raise AssertionError(
                                f"Regex library 're' import detected in {py_file}. "
                                "Materializer/applier/stage-slice code must not parse diagnostic messages."
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module == "re" and py_file.name != "id_allocator.py":
                        raise AssertionError(
                            f"Regex library 're' import detected in {py_file}. "
                            "Materializer/applier/stage-slice code must not parse diagnostic messages."
                        )

            # Assert no references to diagnostic message parsing patterns
            assert "diagnostic.message" not in content, (
                f"Reference to 'diagnostic.message' detected in {py_file}. "
                "Materialization must not depend on parsing diagnostic messages."
            )
            assert ".message" not in content, (
                f"Reference to '.message' detected in {py_file}. "
                "Materialization must not depend on parsing diagnostic messages."
            )
