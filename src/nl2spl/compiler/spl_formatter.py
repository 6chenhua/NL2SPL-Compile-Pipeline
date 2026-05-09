"""SPLFormatter - Format SPL text according to specification."""

from __future__ import annotations


class SPLFormatter:
    """SPL text formatter.

    This class formats SPL text according to the fixed indentation rule:
    - Each element has a fixed indent level based on its position in SPL structure
    - Each indent level = 4 spaces
    """

    # Define fixed indent levels for tags
    # Format: tag_prefix -> indent_level
    TAG_INDENT_LEVEL: dict[str, int] = {
        # 0 level (top level)
        "[DEFINE_AGENT:": 0,
        "[END_AGENT]": 0,

        # 1 level (wrapped by DEFINE_AGENT)
        "[DEFINE_PERSONA:]": 1,
        "[END_PERSONA]": 1,
        "[DEFINE_AUDIENCE:]": 1,
        "[END_AUDIENCE]": 1,
        "[DEFINE_CONCEPTS:]": 1,
        "[END_CONCEPTS]": 1,
        "[DEFINE_CONSTRAINTS:]": 1,
        "[END_CONSTRAINTS]": 1,
        "[DEFINE_VARIABLES:]": 1,
        "[END_VARIABLES]": 1,
        "[DEFINE_FILES:]": 1,
        "[END_FILES]": 1,
        "[DEFINE_TYPES:]": 1,
        "[END_TYPES]": 1,
        "[DEFINE_APIS:]": 1,
        "[END_APIS]": 1,
        "[DEFINE_WORKER:": 1,
        "[END_WORKER]": 1,

        # 2 level (wrapped by section tags)
        "[INPUTS]": 2,
        "[END_INPUTS]": 2,
        "[CONTROLLED_INPUTS]": 2,
        "[END_CONTROLLED_INPUTS]": 2,
        "[OUTPUTS]": 2,
        "[END_OUTPUTS]": 2,
        "[CONTROLLED_OUTPUTS]": 2,
        "[END_CONTROLLED_OUTPUTS]": 2,
        "[MAIN_FLOW]": 2,
        "[END_MAIN_FLOW]": 2,
        "[ALTERNATIVE_FLOW:": 2,
        "[END_ALTERNATIVE_FLOW]": 2,
        "[EXCEPTION_FLOW:": 2,
        "[END_EXCEPTION_FLOW]": 2,
        "[EXAMPLES]": 2,
        "[END_EXAMPLES]": 2,

        # 3 level (wrapped by flow/block tags)
        "[SEQUENTIAL_BLOCK]": 3,
        "[END_SEQUENTIAL_BLOCK]": 3,
        "[SEQUENTIAL]": 3,
        "[END_SEQUENTIAL]": 3,
        "[IF": 3,
        "[END_IF]": 3,
        "[ELSEIF": 3,
        "[ELSE]": 3,
        "[FOR": 3,
        "[END_FOR]": 3,
        "[WHILE": 3,
        "[END_WHILE]": 3,
    }

    # Content indent levels (relative to parent tag)
    # parent_tag -> content_indent_level
    CONTENT_INDENT_LEVEL: dict[str, int] = {
        "[DEFINE_PERSONA:]": 2,
        "[DEFINE_AUDIENCE:]": 2,
        "[DEFINE_CONCEPTS:]": 2,
        "[DEFINE_CONSTRAINTS:]": 2,
        "[DEFINE_VARIABLES:]": 2,
        "[DEFINE_FILES:]": 2,
        "[DEFINE_TYPES:]": 2,
        "[DEFINE_APIS:]": 2,
        "[INPUTS]": 3,
        "[CONTROLLED_INPUTS]": 3,
        "[OUTPUTS]": 3,
        "[CONTROLLED_OUTPUTS]": 3,
        "[MAIN_FLOW]": 3,
        "[ALTERNATIVE_FLOW:": 3,
        "[EXCEPTION_FLOW:": 3,
        "[EXAMPLES]": 3,
        "[SEQUENTIAL_BLOCK]": 4,
        "[SEQUENTIAL]": 4,
        "[IF": 4,
        "[ELSEIF": 4,
        "[ELSE]": 4,
        "[FOR": 4,
        "[WHILE": 4,
    }

    def format(self, spl_text: str) -> str:
        """Format SPL text with fixed indentation.

        Args:
            spl_text: Raw SPL text

        Returns:
            Formatted SPL text
        """
        lines = spl_text.split("\n")
        formatted_lines = []
        # Track parent context for content indentation
        context_stack: list[tuple[str, int]] = []  # (tag, indent_level)

        for line in lines:
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                continue

            # Check if this is a tag
            tag_indent = self._get_tag_indent(stripped)

            if tag_indent is not None:
                # This is a tag
                indent = "    " * tag_indent
                formatted_lines.append(indent + stripped)

                # Update context stack
                if stripped.startswith("[END_"):
                    # Closing tag - pop context
                    if context_stack:
                        context_stack.pop()
                elif not stripped.startswith("[END_"):
                    # Opening tag - push context
                    context_stack.append((self._tag_lookup_line(stripped), tag_indent))
            else:
                # This is content - use parent's content indent level
                if context_stack:
                    parent_tag, _ = context_stack[-1]
                    content_indent = self._get_content_indent(parent_tag)
                else:
                    content_indent = 2  # Default

                indent = "    " * content_indent
                formatted_lines.append(indent + stripped)

        return "\n".join(formatted_lines)

    def _get_tag_indent(self, line: str) -> int | None:
        """Get the indent level for a tag.

        Args:
            line: Line to check

        Returns:
            Indent level or None if not a tag
        """
        line = self._tag_lookup_line(line)
        for tag_prefix, indent_level in self.TAG_INDENT_LEVEL.items():
            if line.startswith(tag_prefix):
                return indent_level
        return None

    def _get_content_indent(self, parent_tag: str) -> int:
        """Get the fixed content indent level for a parent tag."""
        parent_tag = self._tag_lookup_line(parent_tag)
        for tag_prefix, indent_level in self.CONTENT_INDENT_LEVEL.items():
            if parent_tag.startswith(tag_prefix):
                return indent_level
        return 2

    def _tag_lookup_line(self, line: str) -> str:
        """Normalize indexed decision lines before looking up SPL tags."""
        line = line.strip()
        if line.startswith("DECISION-"):
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                return parts[1]
        return line

    def _is_tag(self, line: str) -> bool:
        """Check if line is a tag.

        Args:
            line: Line to check

        Returns:
            True if line is a tag
        """
        return self._get_tag_indent(line) is not None

    def validate_indentation(self, spl_text: str) -> list[str]:
        """Validate indentation in SPL text.

        Args:
            spl_text: SPL text to validate

        Returns:
            List of validation errors
        """
        errors = []
        lines = spl_text.split("\n")

        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue

            # Check for tabs (should use spaces)
            if "\t" in line:
                errors.append(f"Line {i}: Contains tabs, use spaces instead")

            # Check indentation is multiple of 4
            leading_spaces = len(line) - len(line.lstrip())
            if leading_spaces % 4 != 0:
                errors.append(f"Line {i}: Indentation not multiple of 4 spaces")

        return errors

    def minify(self, spl_text: str) -> str:
        """Minify SPL text by removing unnecessary whitespace.

        Args:
            spl_text: SPL text to minify

        Returns:
            Minified SPL text
        """
        lines = spl_text.split("\n")
        minified_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped:
                minified_lines.append(stripped)

        return "\n".join(minified_lines)

    def prettify(self, spl_text: str) -> str:
        """Prettify SPL text with consistent formatting.

        Args:
            spl_text: SPL text to prettify

        Returns:
            Prettified SPL text
        """
        # First format with proper indentation
        formatted = self.format(spl_text)

        # Add blank lines between major sections
        lines = formatted.split("\n")
        prettified_lines = []

        for i, line in enumerate(lines):
            prettified_lines.append(line)

            # Add blank line after major section ends
            if line.strip().startswith("[END_") and any(
                tag in line
                for tag in [
                    "[END_AGENT]",
                    "[END_PERSONA]",
                    "[END_AUDIENCE]",
                    "[END_CONCEPTS]",
                    "[END_VARIABLES]",
                    "[END_CONSTRAINTS]",
                    "[END_WORKER]",
                    "[END_MAIN_FLOW]",
                ]
            ):
                if i < len(lines) - 1:  # Don't add at the end
                    prettified_lines.append("")

        return "\n".join(prettified_lines)
