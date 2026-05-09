"""Unit tests for StaticValidator."""

from __future__ import annotations

import pytest

from nl2spl.validator.static_validator import StaticValidator, ValidationError, ValidationResult


class TestStaticValidator:
    """Tests for StaticValidator."""

    def test_valid_spl(self) -> None:
        """Test validation of valid SPL."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test worker"]
[DEFINE_PERSONA:]
ROLE: Test
[END_PERSONA]
[DEFINE_WORKER: "Test" TestWorker]
[INPUTS]
REQUIRED <REF>input</REF>
[END_INPUTS]
[OUTPUTS]
REQUIRED <REF>output</REF>
[END_OUTPUTS]
[MAIN_FLOW]
[SEQUENTIAL_BLOCK]
COMMAND-1 [COMMAND Test]
[END_SEQUENTIAL_BLOCK]
[END_MAIN_FLOW]
[END_WORKER]
[END_AGENT]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        assert result.is_valid
        assert len(result.errors) == 0

    def test_missing_define_agent(self) -> None:
        """Test validation without DEFINE_AGENT."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_PERSONA:]
ROLE: Test
[END_PERSONA]
[END_AGENT]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        assert not result.is_valid
        assert any("DEFINE_AGENT" in e.message for e in result.errors)

    def test_missing_end_agent(self) -> None:
        """Test validation without END_AGENT."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_PERSONA:]
ROLE: Test
[END_PERSONA]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        assert not result.is_valid
        assert any("END_AGENT" in e.message for e in result.errors)

    def test_unmatched_opening_bracket(self) -> None:
        """Test validation with unmatched opening bracket."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_PERSONA:]
ROLE: Test
[END_PERSONA]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        assert not result.is_valid
        assert any("Unmatched opening bracket" in e.message for e in result.errors)

    def test_unmatched_closing_bracket(self) -> None:
        """Test validation with unmatched closing bracket."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_PERSONA:]
ROLE: Test
[END_PERSONA]
[END_WORKER]
[END_AGENT]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        assert not result.is_valid
        assert any("Unmatched closing bracket" in e.message for e in result.errors)

    def test_mismatched_brackets(self) -> None:
        """Test validation with mismatched brackets."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_PERSONA:]
ROLE: Test
[END_WORKER]
[END_AGENT]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        assert not result.is_valid
        assert any("Mismatched brackets" in e.message for e in result.errors)

    def test_invalid_ref_tag(self) -> None:
        """Test validation with invalid REF tag."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_WORKER: "Test" TestWorker]
[INPUTS]
REQUIRED <REF>invalid-tag</REF>
[END_INPUTS]
[END_WORKER]
[END_AGENT]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        assert len(result.errors) > 0
        assert any("Invalid REF tag" in e.message for e in result.errors)

    def test_decision_prefixed_if_block(self) -> None:
        """Test grammar-shaped IF blocks with DECISION index."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test worker"]
[DEFINE_PERSONA:]
ROLE: Test
[END_PERSONA]
[DEFINE_WORKER: "Test" TestWorker]
[INPUTS]
[END_INPUTS]
[OUTPUTS]
[END_OUTPUTS]
[MAIN_FLOW]
DECISION-1 [IF condition]
COMMAND-1 [COMMAND Test]
[END_IF]
[END_MAIN_FLOW]
[END_WORKER]
[END_AGENT]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        assert result.is_valid

    def test_empty_role_is_invalid(self) -> None:
        """Test that ROLE is required to be non-empty."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test worker"]
[DEFINE_PERSONA:]
ROLE:
[END_PERSONA]
[DEFINE_WORKER: "Test" TestWorker]
[INPUTS]
[END_INPUTS]
[OUTPUTS]
[END_OUTPUTS]
[MAIN_FLOW]
[END_MAIN_FLOW]
[END_WORKER]
[END_AGENT]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        assert not result.is_valid
        assert any("ROLE must not be empty" in e.message for e in result.errors)

    def test_validate_structure(self) -> None:
        """Test structure validation."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[END_AGENT]"""

        # Act
        errors = validator.validate_structure(spl_text)

        # Assert
        assert len(errors) > 0
        assert any("DEFINE_WORKER" in e for e in errors)
        assert any("INPUTS" in e for e in errors)
        assert any("OUTPUTS" in e for e in errors)
        assert any("MAIN_FLOW" in e for e in errors)

    def test_validate_variables_undeclared(self) -> None:
        """Test variable validation with undeclared variable."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_WORKER: "Test" TestWorker]
[INPUTS]
REQUIRED <REF>undeclared_var</REF>
[END_INPUTS]
[END_WORKER]
[END_AGENT]"""

        # Act
        errors = validator.validate_variables(spl_text)

        # Assert
        assert len(errors) > 0
        assert any("Undeclared variable" in e for e in errors)

    def test_validate_variables_unused(self) -> None:
        """Test variable validation with unused variable."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_VARIABLES:]
"Unused variable" unused_var: text
[END_VARIABLES]
[DEFINE_WORKER: "Test" TestWorker]
[INPUTS]
REQUIRED <REF>used_var</REF>
[END_INPUTS]
[END_WORKER]
[END_AGENT]"""

        # Act
        errors = validator.validate_variables(spl_text)

        # Assert
        assert len(errors) > 0
        assert any("Unused variable" in e for e in errors)

    def test_validate_variables_valid(self) -> None:
        """Test variable validation with valid configuration."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_VARIABLES:]
"Input variable" input_var: text
"Output variable" output_var: text
[END_VARIABLES]
[DEFINE_WORKER: "Test" TestWorker]
[INPUTS]
REQUIRED <REF>input_var</REF>
[END_INPUTS]
[OUTPUTS]
REQUIRED <REF>output_var</REF>
[END_OUTPUTS]
[END_WORKER]
[END_AGENT]"""

        # Act
        errors = validator.validate_variables(spl_text)

        # Assert
        assert len(errors) == 0

    def test_get_validation_summary_valid(self) -> None:
        """Test validation summary for valid result."""
        # Arrange
        validator = StaticValidator()
        result = ValidationResult(is_valid=True, errors=[])

        # Act
        summary = validator.get_validation_summary(result)

        # Assert
        assert "✓ Validation passed" in summary

    def test_get_validation_summary_invalid(self) -> None:
        """Test validation summary for invalid result."""
        # Arrange
        validator = StaticValidator()
        result = ValidationResult(
            is_valid=False,
            errors=[
                ValidationError(line=0, column=0, message="Error 1", severity="error"),
                ValidationError(line=1, column=0, message="Warning 1", severity="warning"),
            ],
        )

        # Act
        summary = validator.get_validation_summary(result)

        # Assert
        assert "✗ Validation failed" in summary
        assert "1 error(s)" in summary
        assert "1 warning(s)" in summary
        assert "Error 1" in summary
        assert "Warning 1" in summary

    def test_validation_error_severity(self) -> None:
        """Test that validation result considers severity."""
        # Arrange
        validator = StaticValidator()

        # Create a result with only warnings (no errors)
        result = ValidationResult(
            is_valid=True,  # Only warnings, no errors
            errors=[
                ValidationError(line=0, column=0, message="Warning", severity="warning"),
            ],
        )

        # Assert
        assert result.is_valid  # Only warnings, no errors

        # Create a result with errors
        result_with_error = ValidationResult(
            is_valid=False,
            errors=[
                ValidationError(line=0, column=0, message="Error", severity="error"),
            ],
        )

        # Assert
        assert not result_with_error.is_valid  # Has errors

    def test_validation_with_multiple_errors(self) -> None:
        """Test validation with multiple errors."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_PERSONA:]
ROLE: Test
[END_WORKER]
[END_AGENT]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        assert not result.is_valid
        assert len(result.errors) >= 2  # At least 2 errors

    def test_ref_tag_valid_identifier(self) -> None:
        """Test that valid REF tags pass validation."""
        # Arrange
        validator = StaticValidator()
        spl_text = """[DEFINE_AGENT: Test "Test"]
[DEFINE_WORKER: "Test" TestWorker]
[INPUTS]
REQUIRED <REF>valid_identifier</REF>
REQUIRED <REF>anotherValid123</REF>
[END_INPUTS]
[END_WORKER]
[END_AGENT]"""

        # Act
        result = validator.validate(spl_text)

        # Assert
        # Should not have REF tag errors
        ref_errors = [e for e in result.errors if "REF tag" in e.message]
        assert len(ref_errors) == 0
