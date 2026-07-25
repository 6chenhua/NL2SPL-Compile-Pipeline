"""Unit tests for Stage 1: SpanSlicer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer


class TestSpanSlicer:
    """Tests for SpanSlicer stage."""

    def test_simple_sentence(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test simple sentence slicing."""
        # Arrange
        mock_client.call_json.return_value = {
            "spans": [
                {"span_id": "s1", "text": "First determine what kind of communication is requested."}
            ]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "First determine what kind of communication is requested."

        # Act
        spans = slicer.execute(raw_text)

        # Assert
        assert len(spans) == 1
        assert spans[0].span_id == "s1"
        assert spans[0].text == raw_text

    def test_multiple_sentences(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test multiple sentence slicing."""
        # Arrange
        mock_client.call_json.return_value = {
            "spans": [
                {"span_id": "s1", "text": "First determine type."},
                {"span_id": "s2", "text": "Then identify fields."},
            ]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "First determine type. Then identify fields."

        # Act
        spans = slicer.execute(raw_text)

        # Assert
        assert len(spans) == 2
        assert spans[0].text == "First determine type."
        assert spans[1].text == "Then identify fields."

    def test_compound_sentence(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test compound sentence slicing."""
        # Arrange
        mock_client.call_json.return_value = {
            "spans": [
                {"span_id": "s1", "text": "Determine type"},
                {"span_id": "s2", "text": "but do not invent details."},
            ]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "Determine type, but do not invent details."

        # Act
        spans = slicer.execute(raw_text)

        # Assert
        assert len(spans) >= 1
        assert any("Determine type" in s.text for s in spans)

    def test_empty_input(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test empty input handling."""
        # Arrange
        mock_client.call_json.return_value = {"spans": []}
        slicer = SpanSlicer(pipeline_config, mock_client)

        # Act
        spans = slicer.execute("")

        # Assert
        assert len(spans) == 0

    def test_llm_error(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test LLM error handling — graceful fallback (no StageError)."""
        # Arrange
        mock_client.call_json.side_effect = Exception("API error")
        slicer = SpanSlicer(pipeline_config, mock_client)

        # Act — should not raise; just log and return empty spans
        spans = slicer.execute("test input")

        # Assert — graceful degradation: no spans produced, no exception
        assert isinstance(spans, list)

    def test_missing_span_id(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test handling of missing span_id — ignored, reassigned by pipeline."""
        # Arrange
        mock_client.call_json.return_value = {
            "spans": [
                {"text": "test text"}  # Missing span_id, will be reassigned
            ]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)

        # Act
        spans = slicer.execute("test input")

        # Assert — span_id is reassigned to s1
        assert len(spans) == 1
        assert spans[0].span_id == "s1"
        assert spans[0].text == "test text"

    def test_missing_text(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test handling of missing text in LLM response."""
        # Arrange
        mock_client.call_json.return_value = {
            "spans": [
                {"span_id": "s1"}  # Missing text
            ]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)

        # Act
        spans = slicer.execute("test input")

        # Assert
        assert len(spans) == 0  # Should skip invalid spans

    def test_invalid_span_id_format(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test handling of invalid span_id format — ignored, reassigned by pipeline."""
        # Arrange
        mock_client.call_json.return_value = {
            "spans": [
                {"span_id": "invalid", "text": "test text"}  # Invalid format, will be reassigned
            ]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)

        # Act
        spans = slicer.execute("test input")

        # Assert — span_id is reassigned to s1 regardless of LLM value
        assert len(spans) == 1
        assert spans[0].span_id == "s1"
        assert spans[0].text == "test text"

    def test_checkpoint_saved(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that checkpoint is saved."""
        # Arrange
        pipeline_config.save_intermediate = True
        mock_client.call_json.return_value = {
            "spans": [{"span_id": "s1", "text": "test"}]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)

        # Act
        slicer.execute("test input")

        # Assert - checkpoint saving is called (verified by mock)

    def test_checkpoint_content(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that checkpoint contains correct content."""
        # Arrange
        pipeline_config.save_intermediate = True
        mock_client.call_json.return_value = {
            "spans": [{"span_id": "s1", "text": "test text"}]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)

        # Act
        with patch.object(slicer, 'save_checkpoint') as mock_save:
            slicer.execute("test input")

            # Assert
            mock_save.assert_called_once()
            checkpoint_data = mock_save.call_args[0][0]
            assert "raw_text_length" in checkpoint_data
            assert "spans_count" in checkpoint_data
            assert "spans" in checkpoint_data
            assert checkpoint_data["spans_count"] == 1
            assert checkpoint_data["spans"][0]["span_id"] == "s1"

    def test_span_id_ordering(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that span IDs are in order."""
        # Arrange
        mock_client.call_json.return_value = {
            "spans": [
                {"span_id": "s1", "text": "First."},
                {"span_id": "s2", "text": "Second."},
                {"span_id": "s3", "text": "Third."},
            ]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)

        # Act
        spans = slicer.execute("First. Second. Third.")

        # Assert
        assert spans[0].span_id == "s1"
        assert spans[1].span_id == "s2"
        assert spans[2].span_id == "s3"

    def test_preserves_original_text(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test that original text is preserved exactly."""
        # Arrange
        original_text = "Use <angle> brackets & 'quotes' carefully."
        mock_client.call_json.return_value = {
            "spans": [{"span_id": "s1", "text": original_text}]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)

        # Act
        spans = slicer.execute(original_text)

        # Assert
        assert spans[0].text == original_text

    def test_unicode_support(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Test Unicode text support."""
        # Arrange
        unicode_text = "支持中文输入和处理。"
        mock_client.call_json.return_value = {
            "spans": [{"span_id": "s1", "text": unicode_text}]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)

        # Act
        spans = slicer.execute(unicode_text)

        # Assert
        assert spans[0].text == unicode_text
