"""Unit tests for the IRBuilder module."""

from datetime import datetime, timezone

import pytest

from app.ingestion.ir_builder import IRBuilder
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)


@pytest.fixture
def builder() -> IRBuilder:
    return IRBuilder()


@pytest.fixture
def sample_metadata() -> DocumentMetadata:
    return DocumentMetadata(
        original_filename="report.md",
        format=DocumentFormat.MARKDOWN,
        size_bytes=1024,
        language=DetectedLanguage.ENGLISH,
        upload_timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    )


def _make_chunk(chunk_id: str, order: int, text: str = "Some text") -> ContentChunkModel:
    """Helper to create a ContentChunkModel with minimal boilerplate."""
    return ContentChunkModel(
        chunk_id=chunk_id,
        text=text,
        structural_context={"section": "Introduction"},
        order=order,
    )


# --- Happy path tests ---


class TestBuildSuccess:
    """Tests for successful IR assembly."""

    def test_build_single_chunk(self, builder: IRBuilder, sample_metadata: DocumentMetadata):
        chunks = [_make_chunk("chunk-0", order=0)]

        result = builder.build("doc-123", sample_metadata, chunks)

        assert isinstance(result, IntermediateRepresentation)
        assert result.document_id == "doc-123"
        assert result.metadata == sample_metadata
        assert len(result.chunks) == 1
        assert result.chunks[0].chunk_id == "chunk-0"

    def test_build_multiple_chunks(self, builder: IRBuilder, sample_metadata: DocumentMetadata):
        chunks = [
            _make_chunk("chunk-0", order=0, text="First paragraph"),
            _make_chunk("chunk-1", order=1, text="Second paragraph"),
            _make_chunk("chunk-2", order=2, text="Third paragraph"),
        ]

        result = builder.build("doc-456", sample_metadata, chunks)

        assert result.document_id == "doc-456"
        assert len(result.chunks) == 3
        assert [c.order for c in result.chunks] == [0, 1, 2]

    def test_build_empty_chunks_list(self, builder: IRBuilder, sample_metadata: DocumentMetadata):
        result = builder.build("doc-789", sample_metadata, [])

        assert isinstance(result, IntermediateRepresentation)
        assert result.document_id == "doc-789"
        assert result.chunks == []

    def test_build_preserves_metadata(self, builder: IRBuilder, sample_metadata: DocumentMetadata):
        chunks = [_make_chunk("c-0", order=0)]

        result = builder.build("doc-meta", sample_metadata, chunks)

        assert result.metadata.original_filename == "report.md"
        assert result.metadata.format == DocumentFormat.MARKDOWN
        assert result.metadata.size_bytes == 1024
        assert result.metadata.language == DetectedLanguage.ENGLISH


# --- Chunk ordering validation tests ---


class TestChunkOrderingValidation:
    """Tests for sequential chunk ordering enforcement."""

    def test_non_sequential_order_starting_at_1(
        self, builder: IRBuilder, sample_metadata: DocumentMetadata
    ):
        chunks = [_make_chunk("chunk-0", order=1)]  # Should start at 0

        with pytest.raises(ValueError, match="not sequential"):
            builder.build("doc-err", sample_metadata, chunks)

    def test_gap_in_order(self, builder: IRBuilder, sample_metadata: DocumentMetadata):
        chunks = [
            _make_chunk("chunk-0", order=0),
            _make_chunk("chunk-1", order=1),
            _make_chunk("chunk-2", order=3),  # Gap: skipped 2
        ]

        with pytest.raises(ValueError, match="not sequential"):
            builder.build("doc-err", sample_metadata, chunks)

    def test_duplicate_order_values(self, builder: IRBuilder, sample_metadata: DocumentMetadata):
        chunks = [
            _make_chunk("chunk-a", order=0),
            _make_chunk("chunk-b", order=0),  # Duplicate order
        ]

        with pytest.raises(ValueError, match="not sequential"):
            builder.build("doc-err", sample_metadata, chunks)

    def test_reversed_order(self, builder: IRBuilder, sample_metadata: DocumentMetadata):
        chunks = [
            _make_chunk("chunk-a", order=2),
            _make_chunk("chunk-b", order=1),
            _make_chunk("chunk-c", order=0),
        ]

        with pytest.raises(ValueError, match="not sequential"):
            builder.build("doc-err", sample_metadata, chunks)


# --- Unique chunk_id validation tests ---


class TestUniqueChunkIdValidation:
    """Tests for unique chunk_id enforcement."""

    def test_duplicate_chunk_ids(self, builder: IRBuilder, sample_metadata: DocumentMetadata):
        chunks = [
            _make_chunk("same-id", order=0),
            _make_chunk("same-id", order=1),  # Duplicate chunk_id
        ]

        with pytest.raises(ValueError, match="Duplicate chunk_id"):
            builder.build("doc-err", sample_metadata, chunks)

    def test_duplicate_among_many(self, builder: IRBuilder, sample_metadata: DocumentMetadata):
        chunks = [
            _make_chunk("chunk-0", order=0),
            _make_chunk("chunk-1", order=1),
            _make_chunk("chunk-0", order=2),  # Duplicate of first
        ]

        with pytest.raises(ValueError, match="Duplicate chunk_id"):
            builder.build("doc-err", sample_metadata, chunks)
