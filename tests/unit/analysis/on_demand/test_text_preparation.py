"""Unit tests for the shared text preparation utility."""

from datetime import datetime, timezone

import pytest

from app.analysis.on_demand.text_preparation import prepare_document_text
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)


def _make_ir(chunks: list[ContentChunkModel]) -> IntermediateRepresentation:
    """Build a minimal IR for testing."""
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=1024,
            language=DetectedLanguage.SPANISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=chunks,
    )


class TestPrepareDocumentText:
    """Tests for prepare_document_text."""

    def test_single_chunk_with_section(self):
        ir = _make_ir([
            ContentChunkModel(
                chunk_id="c1",
                text="Introduction content here.",
                structural_context={"section": "Introduction"},
                order=0,
            ),
        ])

        result = prepare_document_text(ir)

        assert result == "[Section: Introduction] (chunk 0)\nIntroduction content here."

    def test_multiple_chunks_ordered(self):
        ir = _make_ir([
            ContentChunkModel(
                chunk_id="c2",
                text="Second section text.",
                structural_context={"section": "Details"},
                order=1,
            ),
            ContentChunkModel(
                chunk_id="c1",
                text="First section text.",
                structural_context={"section": "Overview"},
                order=0,
            ),
        ])

        result = prepare_document_text(ir)

        expected = (
            "[Section: Overview] (chunk 0)\n"
            "First section text.\n"
            "\n"
            "[Section: Details] (chunk 1)\n"
            "Second section text."
        )
        assert result == expected

    def test_none_section_uses_untitled(self):
        ir = _make_ir([
            ContentChunkModel(
                chunk_id="c1",
                text="Some text without a section.",
                structural_context={"page": 1},
                order=0,
            ),
        ])

        result = prepare_document_text(ir)

        assert result == "[Section: Untitled] (chunk 0)\nSome text without a section."

    def test_empty_string_section_uses_untitled(self):
        ir = _make_ir([
            ContentChunkModel(
                chunk_id="c1",
                text="Content in unnamed section.",
                structural_context={"section": ""},
                order=0,
            ),
        ])

        result = prepare_document_text(ir)

        assert result == "[Section: Untitled] (chunk 0)\nContent in unnamed section."

    def test_empty_chunks_returns_empty_string(self):
        ir = _make_ir([])

        result = prepare_document_text(ir)

        assert result == ""

    def test_preserves_multiline_text(self):
        ir = _make_ir([
            ContentChunkModel(
                chunk_id="c1",
                text="Line one.\nLine two.\nLine three.",
                structural_context={"section": "Body"},
                order=0,
            ),
        ])

        result = prepare_document_text(ir)

        assert result == "[Section: Body] (chunk 0)\nLine one.\nLine two.\nLine three."

    def test_chunks_sorted_by_order_not_insertion(self):
        """Chunks are sorted by order field regardless of list position."""
        ir = _make_ir([
            ContentChunkModel(
                chunk_id="c3",
                text="Third.",
                structural_context={"section": "C"},
                order=2,
            ),
            ContentChunkModel(
                chunk_id="c1",
                text="First.",
                structural_context={"section": "A"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="c2",
                text="Second.",
                structural_context={"section": "B"},
                order=1,
            ),
        ])

        result = prepare_document_text(ir)

        lines = result.split("\n\n")
        assert lines[0].startswith("[Section: A]")
        assert lines[1].startswith("[Section: B]")
        assert lines[2].startswith("[Section: C]")
