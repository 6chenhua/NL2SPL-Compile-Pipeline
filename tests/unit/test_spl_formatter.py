"""Unit tests for SPLFormatter."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_formatter import SPLFormatter


class TestSPLFormatter:
    """Tests for SPLFormatter."""

    def test_basic_formatting(self) -> None:
        """Test basic SPL formatting."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_PERSONA:]
ROLE: Test
[END_PERSONA]
[END_AGENT]"""

        # Act
        formatted = formatter.format(spl_text)

        # Assert
        lines = formatted.split("\n")
        assert lines[0] == '[DEFINE_AGENT: Test "Test"]'  # 0 level
        assert lines[1] == '    [DEFINE_PERSONA:]'  # 1 level (4 spaces)
        assert lines[2] == '        ROLE: Test'  # 2 level (8 spaces)
        assert lines[3] == '    [END_PERSONA]'  # 1 level (4 spaces)
        assert lines[4] == '[END_AGENT]'  # 0 level

    def test_nested_indentation(self) -> None:
        """Test nested indentation."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[DEFINE_WORKER: "Test" Worker]
[INPUTS]
REQUIRED <REF>input</REF>
[END_INPUTS]
[OUTPUTS]
REQUIRED <REF>output</REF>
[END_OUTPUTS]
[MAIN_FLOW]
[SEQUENTIAL]
COMMAND-1 [COMMAND Test]
[END_SEQUENTIAL]
[END_MAIN_FLOW]
[END_WORKER]"""

        # Act
        formatted = formatter.format(spl_text)

        # Assert
        lines = formatted.split("\n")
        assert lines[0] == '    [DEFINE_WORKER: "Test" Worker]'  # 1 level (4 spaces)
        assert lines[1] == '        [INPUTS]'  # 2 level (8 spaces)
        assert lines[2] == '            REQUIRED <REF>input</REF>'  # 3 level (12 spaces)
        assert lines[3] == '        [END_INPUTS]'  # 2 level (8 spaces)
        assert lines[4] == '        [OUTPUTS]'  # 2 level (8 spaces)
        assert lines[5] == '            REQUIRED <REF>output</REF>'  # 3 level (12 spaces)
        assert lines[6] == '        [END_OUTPUTS]'  # 2 level (8 spaces)
        assert lines[7] == '        [MAIN_FLOW]'  # 2 level (8 spaces)
        assert lines[8] == '            [SEQUENTIAL]'  # 3 level (12 spaces)
        assert lines[9] == '                COMMAND-1 [COMMAND Test]'  # 4 level (16 spaces)
        assert lines[10] == '            [END_SEQUENTIAL]'  # 3 level (12 spaces)
        assert lines[11] == '        [END_MAIN_FLOW]'  # 2 level (8 spaces)
        assert lines[12] == '    [END_WORKER]'  # 1 level (4 spaces)

    def test_empty_lines_removed(self) -> None:
        """Test that empty lines are removed."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[DEFINE_AGENT: Test "Test"]

[DEFINE_PERSONA:]

ROLE: Test

[END_PERSONA]

[END_AGENT]"""

        # Act
        formatted = formatter.format(spl_text)

        # Assert
        lines = [line for line in formatted.split("\n") if line.strip()]
        assert len(lines) == 5  # No empty lines

    def test_indentation_validation(self) -> None:
        """Test indentation validation."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[DEFINE_AGENT: Test "Test"]
    [DEFINE_PERSONA:]
        ROLE: Test
    [END_PERSONA]
[END_AGENT]"""

        # Act
        errors = formatter.validate_indentation(spl_text)

        # Assert
        assert len(errors) == 0  # All indentations are multiples of 4

    def test_indentation_validation_with_tabs(self) -> None:
        """Test indentation validation with tabs."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = "[DEFINE_AGENT: Test \"Test\"]\n\t[DEFINE_PERSONA:]\n[END_AGENT]"

        # Act
        errors = formatter.validate_indentation(spl_text)

        # Assert
        assert len(errors) > 0
        assert any("tabs" in e.lower() for e in errors)

    def test_indentation_validation_invalid(self) -> None:
        """Test indentation validation with invalid indentation."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = "[DEFINE_AGENT: Test \"Test\"]\n  [DEFINE_PERSONA:]\n[END_AGENT]"

        # Act
        errors = formatter.validate_indentation(spl_text)

        # Assert
        assert len(errors) > 0
        assert any("multiple of 4" in e for e in errors)

    def test_minify(self) -> None:
        """Test SPL minification."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[DEFINE_AGENT: Test "Test"]
    [DEFINE_PERSONA:]
        ROLE: Test
    [END_PERSONA]
[END_AGENT]"""

        # Act
        minified = formatter.minify(spl_text)

        # Assert
        lines = minified.split("\n")
        for line in lines:
            assert line == line.strip()  # No leading/trailing spaces

    def test_prettify(self) -> None:
        """Test SPL prettification."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_PERSONA:]
ROLE: Test
[END_PERSONA]
[END_WORKER]
[END_AGENT]"""

        # Act
        prettified = formatter.prettify(spl_text)

        # Assert
        lines = prettified.split("\n")
        # Check for blank lines after major sections
        assert any(line == "" for line in lines)

    def test_format_preserves_content(self) -> None:
        """Test that formatting preserves content."""
        # Arrange
        formatter = SPLFormatter()
        original_content = "ROLE: Test Role with special chars: <>&\"'"
        spl_text = f"[DEFINE_PERSONA:]\n{original_content}\n[END_PERSONA]"

        # Act
        formatted = formatter.format(spl_text)

        # Assert
        assert original_content in formatted

    def test_format_with_multiple_blocks(self) -> None:
        """Test formatting with multiple blocks."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[MAIN_FLOW]
[SEQUENTIAL]
COMMAND-1 [COMMAND Step 1]
[END_SEQUENTIAL]
[IF: condition]
[SEQUENTIAL]
COMMAND-2 [COMMAND Step 2]
[END_SEQUENTIAL]
[END_IF]
[END_MAIN_FLOW]"""

        # Act
        formatted = formatter.format(spl_text)

        # Assert
        assert "[MAIN_FLOW]" in formatted
        assert "[SEQUENTIAL]" in formatted
        assert "[IF: condition]" in formatted
        assert "COMMAND-1" in formatted
        assert "COMMAND-2" in formatted

    def test_is_tag(self) -> None:
        """Test tag detection."""
        # Arrange
        formatter = SPLFormatter()

        # Act & Assert
        assert formatter._is_tag("[DEFINE_AGENT: Test]")
        assert formatter._is_tag("[DEFINE_PERSONA:]")
        assert formatter._is_tag("[INPUTS]")
        assert formatter._is_tag("[MAIN_FLOW]")
        assert formatter._is_tag("[SEQUENTIAL]")
        assert formatter._is_tag("[IF: condition]")
        assert formatter._is_tag("[END_AGENT]")
        assert formatter._is_tag("[END_PERSONA]")
        assert not formatter._is_tag("COMMAND-1 [COMMAND Test]")
        assert not formatter._is_tag("ROLE: Test")
        assert not formatter._is_tag("REQUIRED <REF>input</REF>")

    def test_format_with_constraints(self) -> None:
        """Test formatting with constraints."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[DEFINE_CONSTRAINTS:]
Safety: Do not invent facts
Evidence: Require evidence
[END_CONSTRAINTS]"""

        # Act
        formatted = formatter.format(spl_text)

        # Assert
        assert "[DEFINE_CONSTRAINTS:]" in formatted
        assert "Safety: Do not invent facts" in formatted
        assert "Evidence: Require evidence" in formatted

    def test_format_with_variables(self) -> None:
        """Test formatting with variables."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[DEFINE_VARIABLES:]
"User request" user_request: text
"Draft output" draft: text
[END_VARIABLES]"""

        # Act
        formatted = formatter.format(spl_text)

        # Assert
        assert "[DEFINE_VARIABLES:]" in formatted
        assert '"User request" user_request: text' in formatted
        assert '"Draft output" draft: text' in formatted

    def test_format_with_api(self) -> None:
        """Test formatting with API definition."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[DEFINE_APIS:]
"Google Maps" google_maps <apikey> RETRY 3
{info: {title: "Google Maps API"}}
{functions: [{name: "get_directions"}]}
[END_APIS]"""

        # Act
        formatted = formatter.format(spl_text)

        # Assert
        assert "[DEFINE_APIS:]" in formatted
        assert '"Google Maps" google_maps <apikey> RETRY 3' in formatted
        assert "[END_APIS]" in formatted

    def test_format_with_alternative_flow(self) -> None:
        """Test formatting with alternative flow."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[MAIN_FLOW]
[SEQUENTIAL]
COMMAND-1 [COMMAND Test]
[END_SEQUENTIAL]
[END_MAIN_FLOW]
[ALTERNATIVE_FLOW: Missing input]
[SEQUENTIAL]
COMMAND-2 [COMMAND Request input]
[END_SEQUENTIAL]
[END_ALTERNATIVE_FLOW]"""

        # Act
        formatted = formatter.format(spl_text)

        # Assert
        assert "[MAIN_FLOW]" in formatted
        assert "[ALTERNATIVE_FLOW: Missing input]" in formatted
        assert "[END_ALTERNATIVE_FLOW]" in formatted

    def test_format_with_exception_flow(self) -> None:
        """Test formatting with exception flow."""
        # Arrange
        formatter = SPLFormatter()
        spl_text = """[MAIN_FLOW]
[SEQUENTIAL]
COMMAND-1 [COMMAND Test]
[END_SEQUENTIAL]
[END_MAIN_FLOW]
[EXCEPTION_FLOW: Error occurred]
[SEQUENTIAL]
COMMAND-2 [COMMAND Handle error]
[END_SEQUENTIAL]
[END_EXCEPTION_FLOW]"""

        # Act
        formatted = formatter.format(spl_text)

        # Assert
        assert "[MAIN_FLOW]" in formatted
        assert "[EXCEPTION_FLOW: Error occurred]" in formatted
        assert "[END_EXCEPTION_FLOW]" in formatted
