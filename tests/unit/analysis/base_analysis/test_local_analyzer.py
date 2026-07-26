"""Unit tests for LocalAnalyzer — deterministic structural analysis of the IR.

Tests title extraction, statistics computation, organization type detection,
existing index detection, file metadata assembly, and performance (<100ms).

All tests use synthetic IntermediateRepresentation objects.

Requirements: Req 2 (criteria 1-7)
"""

import time
from datetime import datetime, timezone

import pytest

from app.analysis.base_analysis.local_analyzer import LocalAnalyzer
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)
from app.models.document_card import OrganizationType


# --- Helpers ---


def _make_metadata(
    filename: str = "test_document.pdf",
    fmt: DocumentFormat = DocumentFormat.PDF,
    size_bytes: int = 50000,
    language: DetectedLanguage = DetectedLanguage.SPANISH,
) -> DocumentMetadata:
    return DocumentMetadata(
        original_filename=filename,
        format=fmt,
        size_bytes=size_bytes,
        language=language,
        upload_timestamp=datetime(2026, 7, 26, 10, 0, 0, tzinfo=timezone.utc),
    )


def _make_chunk(
    order: int,
    text: str = "Some text content.",
    section: str | None = None,
    level: int | None = None,
    page: int = 1,
) -> ContentChunkModel:
    ctx: dict = {"page": page}
    if section is not None:
        ctx["section"] = section
    if level is not None:
        ctx["level"] = level
    return ContentChunkModel(
        chunk_id=f"chunk-{order:03d}",
        text=text,
        structural_context=ctx,
        order=order,
    )


def _make_ir(
    chunks: list[ContentChunkModel],
    filename: str = "test_document.pdf",
    fmt: DocumentFormat = DocumentFormat.PDF,
    size_bytes: int = 50000,
    language: DetectedLanguage = DetectedLanguage.SPANISH,
) -> IntermediateRepresentation:
    return IntermediateRepresentation(
        document_id="doc-test-001",
        metadata=_make_metadata(filename=filename, fmt=fmt, size_bytes=size_bytes, language=language),
        chunks=chunks,
    )


# --- Fixtures ---


@pytest.fixture
def analyzer() -> LocalAnalyzer:
    return LocalAnalyzer()


# --- Title Extraction Tests ---


class TestExtractTitle:
    """Tests for _extract_title: Req 2 criterion 1."""

    def test_title_from_first_heading(self, analyzer: LocalAnalyzer):
        """Title is extracted from the first chunk with a section heading."""
        chunks = [
            _make_chunk(order=0, text="Preamble text", section=None),
            _make_chunk(order=1, text="Chapter 1 text", section="Capítulo 1"),
            _make_chunk(order=2, text="Chapter 2 text", section="Capítulo 2"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.title == "Capítulo 1"

    def test_title_respects_chunk_order(self, analyzer: LocalAnalyzer):
        """Title comes from the lowest-order chunk with a section, not first in list."""
        chunks = [
            _make_chunk(order=3, text="Later text", section="Late Section"),
            _make_chunk(order=0, text="First text", section="First Section"),
            _make_chunk(order=1, text="Middle text", section="Middle Section"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.title == "First Section"

    def test_title_fallback_to_filename_without_extension(self, analyzer: LocalAnalyzer):
        """When no chunk has a section, title falls back to filename without extension."""
        chunks = [
            _make_chunk(order=0, text="No heading here"),
            _make_chunk(order=1, text="Still no heading"),
        ]
        ir = _make_ir(chunks, filename="reglamento_propiedad.pdf")
        result = analyzer.analyze(ir)
        assert result.title == "reglamento_propiedad"

    def test_title_fallback_filename_no_extension(self, analyzer: LocalAnalyzer):
        """Filename without extension is returned as-is when no dot present."""
        chunks = [_make_chunk(order=0, text="Content")]
        ir = _make_ir(chunks, filename="README")
        result = analyzer.analyze(ir)
        assert result.title == "README"

    def test_title_skips_empty_section(self, analyzer: LocalAnalyzer):
        """Empty string sections are not treated as valid titles."""
        chunks = [
            _make_chunk(order=0, text="Content", section=""),
            _make_chunk(order=1, text="Content", section="Real Title"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.title == "Real Title"


# --- Statistics Tests ---


class TestComputeStatistics:
    """Tests for _compute_statistics: Req 2 criterion 2."""

    def test_chunk_count(self, analyzer: LocalAnalyzer):
        """Total chunks matches the number of chunks in the IR."""
        chunks = [_make_chunk(order=i) for i in range(10)]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.total_chunks == 10

    def test_section_count(self, analyzer: LocalAnalyzer):
        """Sections detected counts unique section values."""
        chunks = [
            _make_chunk(order=0, section="Intro"),
            _make_chunk(order=1, section="Intro"),  # duplicate
            _make_chunk(order=2, section="Chapter 1"),
            _make_chunk(order=3, section="Chapter 2"),
            _make_chunk(order=4),  # no section
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.sections_detected == 3

    def test_hierarchy_levels_from_context(self, analyzer: LocalAnalyzer):
        """Max hierarchy level is the maximum level value from chunks."""
        chunks = [
            _make_chunk(order=0, level=1),
            _make_chunk(order=1, level=3),
            _make_chunk(order=2, level=2),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.hierarchy_levels == 3

    def test_hierarchy_levels_default_when_no_levels(self, analyzer: LocalAnalyzer):
        """Hierarchy levels defaults to 1 when no chunks have level data."""
        chunks = [
            _make_chunk(order=0, text="No level"),
            _make_chunk(order=1, text="Still no level"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.hierarchy_levels == 1

    def test_empty_chunks(self, analyzer: LocalAnalyzer):
        """Zero chunks produces correct stats."""
        ir = _make_ir(chunks=[])
        result = analyzer.analyze(ir)
        assert result.statistics.total_chunks == 0
        assert result.statistics.sections_detected == 0
        assert result.statistics.hierarchy_levels == 1

    def test_has_existing_index_reflects_detection(self, analyzer: LocalAnalyzer):
        """has_existing_index is True when TOC patterns detected in first 20%."""
        chunks = [
            _make_chunk(order=0, section="Índice", text="Capítulo 1..........5"),
        ] + [_make_chunk(order=i, text="Body content") for i in range(1, 10)]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is True


# --- Organization Type Detection Tests ---


class TestDetectOrganizationType:
    """Tests for _detect_organization_type: Req 2 criterion 3."""

    def test_numbered_articles_art_dot(self, analyzer: LocalAnalyzer):
        """Detects numbered_articles from 'Art. N' pattern."""
        chunks = [
            _make_chunk(order=0, text="Art. 1 - Disposiciones generales"),
            _make_chunk(order=1, text="Art. 2 - Obligaciones de propietarios"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.organization_type == OrganizationType.NUMBERED_ARTICLES

    def test_numbered_articles_articulo(self, analyzer: LocalAnalyzer):
        """Detects numbered_articles from 'Artículo N' pattern."""
        chunks = [
            _make_chunk(order=0, text="Artículo 15 - Del uso de áreas comunes"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.organization_type == OrganizationType.NUMBERED_ARTICLES

    def test_numbered_articles_articulo_uppercase(self, analyzer: LocalAnalyzer):
        """Detects numbered_articles from 'ARTICULO' pattern (case-insensitive)."""
        chunks = [
            _make_chunk(order=0, text="ARTICULO PRIMERO"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.organization_type == OrganizationType.NUMBERED_ARTICLES

    def test_headed_sections(self, analyzer: LocalAnalyzer):
        """Detects headed_sections when chunks have level values."""
        chunks = [
            _make_chunk(order=0, text="Introduction text", level=1, section="Introduction"),
            _make_chunk(order=1, text="Details", level=2, section="Details"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.organization_type == OrganizationType.HEADED_SECTIONS

    def test_hierarchical_numbering(self, analyzer: LocalAnalyzer):
        """Detects hierarchical_numbering from 'N.N' patterns."""
        chunks = [
            _make_chunk(order=0, text="1.1 Scope of the document"),
            _make_chunk(order=1, text="1.2 References and normative documents"),
            _make_chunk(order=2, text="2.1 General requirements"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.organization_type == OrganizationType.HIERARCHICAL_NUMBERING

    def test_free_form(self, analyzer: LocalAnalyzer):
        """Detects free_form when no pattern matches."""
        chunks = [
            _make_chunk(order=0, text="This is a simple narrative document."),
            _make_chunk(order=1, text="It has no special structure at all."),
            _make_chunk(order=2, text="Just plain paragraphs of text."),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.organization_type == OrganizationType.FREE_FORM

    def test_priority_articles_over_headed_sections(self, analyzer: LocalAnalyzer):
        """numbered_articles takes priority over headed_sections."""
        chunks = [
            _make_chunk(order=0, text="Art. 1 - Disposiciones", level=1, section="Title"),
            _make_chunk(order=1, text="Art. 2 - Obligaciones", level=2, section="Subtitle"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.organization_type == OrganizationType.NUMBERED_ARTICLES

    def test_priority_articles_over_hierarchical(self, analyzer: LocalAnalyzer):
        """numbered_articles takes priority over hierarchical_numbering."""
        chunks = [
            _make_chunk(order=0, text="Art. 1 - Sección 1.1 del reglamento"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.organization_type == OrganizationType.NUMBERED_ARTICLES

    def test_priority_headed_over_hierarchical(self, analyzer: LocalAnalyzer):
        """headed_sections takes priority over hierarchical_numbering."""
        chunks = [
            _make_chunk(order=0, text="1.1 Introduction", level=1, section="Intro"),
            _make_chunk(order=1, text="1.2 Background", level=2, section="Background"),
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.organization_type == OrganizationType.HEADED_SECTIONS


# --- Index Detection Tests ---


class TestDetectExistingIndex:
    """Tests for _detect_existing_index: Req 2 criterion 4."""

    def test_positive_section_name_indice(self, analyzer: LocalAnalyzer):
        """Detects index from section name 'Índice'."""
        chunks = [
            _make_chunk(order=0, section="Índice", text="Contenido del documento"),
        ] + [_make_chunk(order=i) for i in range(1, 10)]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is True

    def test_positive_section_name_contenido(self, analyzer: LocalAnalyzer):
        """Detects index from section name 'Contenido'."""
        chunks = [
            _make_chunk(order=0, section="Contenido", text="Listado"),
        ] + [_make_chunk(order=i) for i in range(1, 10)]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is True

    def test_positive_section_name_table_of_contents(self, analyzer: LocalAnalyzer):
        """Detects index from section name 'Table of Contents'."""
        chunks = [
            _make_chunk(order=0, section="Table of Contents", text="Chapter list"),
        ] + [_make_chunk(order=i) for i in range(1, 10)]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is True

    def test_positive_section_name_contents_case_insensitive(self, analyzer: LocalAnalyzer):
        """Detects index from section name 'CONTENTS' (case-insensitive)."""
        chunks = [
            _make_chunk(order=0, section="CONTENTS", text="Chapter list"),
        ] + [_make_chunk(order=i) for i in range(1, 10)]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is True

    def test_positive_dot_pattern(self, analyzer: LocalAnalyzer):
        """Detects index from dot-separated page number pattern."""
        toc_text = "Capítulo 1..........5\nCapítulo 2..........12\nCapítulo 3..........25"
        chunks = [
            _make_chunk(order=0, text=toc_text),
        ] + [_make_chunk(order=i) for i in range(1, 10)]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is True

    def test_positive_dash_pattern(self, analyzer: LocalAnalyzer):
        """Detects index from dash-separated page number pattern."""
        toc_text = "Introduction --- 3\nChapter 1 --- 10"
        chunks = [
            _make_chunk(order=0, text=toc_text),
        ] + [_make_chunk(order=i) for i in range(1, 10)]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is True

    def test_positive_space_pattern(self, analyzer: LocalAnalyzer):
        """Detects index from space-separated trailing page number pattern."""
        toc_text = "Introducción          3\nCapítulo 1          10"
        chunks = [
            _make_chunk(order=0, text=toc_text),
        ] + [_make_chunk(order=i) for i in range(1, 10)]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is True

    def test_negative_no_toc(self, analyzer: LocalAnalyzer):
        """No index detected when no TOC patterns are present."""
        chunks = [
            _make_chunk(order=i, text=f"Regular paragraph number {i}.")
            for i in range(10)
        ]
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is False

    def test_negative_toc_pattern_beyond_20_percent(self, analyzer: LocalAnalyzer):
        """TOC patterns beyond the first 20% are not detected."""
        # 10 normal chunks, then TOC in chunk 9 (which is in the last 10%)
        chunks = [_make_chunk(order=i, text="Normal text") for i in range(10)]
        # Add the TOC at position 9 (90% into the document)
        chunks[9] = _make_chunk(order=9, section="Índice", text="Late TOC..........5")
        ir = _make_ir(chunks)
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is False

    def test_empty_chunks_no_index(self, analyzer: LocalAnalyzer):
        """Empty document has no index."""
        ir = _make_ir(chunks=[])
        result = analyzer.analyze(ir)
        assert result.statistics.has_existing_index is False


# --- File Metadata Tests ---


class TestBuildFileMetadata:
    """Tests for _build_file_metadata: Req 2 criterion 5."""

    def test_pdf_metadata(self, analyzer: LocalAnalyzer):
        """File metadata correctly extracts PDF format info."""
        chunks = [_make_chunk(order=0)]
        ir = _make_ir(
            chunks,
            filename="document.pdf",
            fmt=DocumentFormat.PDF,
            size_bytes=150000,
            language=DetectedLanguage.SPANISH,
        )
        result = analyzer.analyze(ir)
        assert result.file_metadata.size_bytes == 150000
        assert result.file_metadata.format == "pdf"
        assert result.file_metadata.language == "es"

    def test_markdown_metadata(self, analyzer: LocalAnalyzer):
        """File metadata correctly extracts Markdown format info."""
        chunks = [_make_chunk(order=0)]
        ir = _make_ir(
            chunks,
            filename="notes.md",
            fmt=DocumentFormat.MARKDOWN,
            size_bytes=5000,
            language=DetectedLanguage.ENGLISH,
        )
        result = analyzer.analyze(ir)
        assert result.file_metadata.size_bytes == 5000
        assert result.file_metadata.format == "markdown"
        assert result.file_metadata.language == "en"

    def test_plain_text_metadata(self, analyzer: LocalAnalyzer):
        """File metadata correctly extracts plain text format info."""
        chunks = [_make_chunk(order=0)]
        ir = _make_ir(
            chunks,
            filename="data.txt",
            fmt=DocumentFormat.PLAIN_TEXT,
            size_bytes=2500,
            language=DetectedLanguage.UNKNOWN,
        )
        result = analyzer.analyze(ir)
        assert result.file_metadata.size_bytes == 2500
        assert result.file_metadata.format == "plain_text"
        assert result.file_metadata.language == "unknown"


# --- Performance Tests ---


class TestPerformance:
    """Tests for performance requirement: Req 2 criterion 7."""

    def test_performance_large_document_under_100ms(self, analyzer: LocalAnalyzer):
        """LocalAnalyzer completes in <100ms for a large synthetic IR (~10MB equivalent).

        A 10MB document at ~200 bytes/chunk = ~50,000 chunks.
        We generate a smaller but representative set (5000 chunks) with various
        structural features to validate the performance bound.
        """
        # Generate 5000 chunks with mixed content to simulate a large document
        chunks = []
        for i in range(5000):
            section = f"Section {i // 100}" if i % 10 == 0 else None
            level = (i % 3) + 1 if i % 20 == 0 else None
            text = f"This is paragraph {i} with content about topic {i % 50}. " * 5
            chunks.append(_make_chunk(order=i, text=text, section=section, level=level))

        ir = _make_ir(chunks, size_bytes=10_000_000)

        start = time.perf_counter()
        result = analyzer.analyze(ir)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 100, f"LocalAnalyzer took {elapsed_ms:.1f}ms, expected <100ms"
        assert result.statistics.total_chunks == 5000
        assert result.title == "Section 0"

    def test_performance_empty_document(self, analyzer: LocalAnalyzer):
        """Empty IR completes nearly instantly."""
        ir = _make_ir(chunks=[], filename="empty.txt", fmt=DocumentFormat.PLAIN_TEXT)

        start = time.perf_counter()
        result = analyzer.analyze(ir)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 10, f"Empty IR took {elapsed_ms:.1f}ms"
        assert result.title == "empty"
