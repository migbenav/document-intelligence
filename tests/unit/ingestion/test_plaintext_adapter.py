"""Unit tests for the Plain Text format extraction adapter."""

from pathlib import Path

import pytest

from app.ingestion.adapters.base import ContentChunk, ExtractionResult, FormatAdapter
from app.ingestion.adapters.plaintext_adapter import PlainTextAdapter

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "ingestion" / "plaintext"


@pytest.fixture
def adapter() -> PlainTextAdapter:
    return PlainTextAdapter()


# --- Base class contract tests ---


class TestFormatAdapterContract:
    """Tests that PlainTextAdapter implements the FormatAdapter ABC correctly."""

    def test_is_format_adapter_subclass(self):
        assert issubclass(PlainTextAdapter, FormatAdapter)

    def test_instance_is_format_adapter(self, adapter: PlainTextAdapter):
        assert isinstance(adapter, FormatAdapter)


# --- can_handle tests ---


class TestCanHandle:
    """Tests for PlainTextAdapter.can_handle method."""

    def test_handles_txt_extension(self, adapter: PlainTextAdapter):
        assert adapter.can_handle("readme.txt", None) is True

    def test_handles_txt_extension_case_insensitive(self, adapter: PlainTextAdapter):
        assert adapter.can_handle("README.TXT", None) is True

    def test_handles_txt_with_content_type(self, adapter: PlainTextAdapter):
        assert adapter.can_handle("doc.txt", "text/plain") is True

    def test_rejects_md_extension(self, adapter: PlainTextAdapter):
        assert adapter.can_handle("file.md", None) is False

    def test_rejects_pdf_extension(self, adapter: PlainTextAdapter):
        assert adapter.can_handle("file.pdf", None) is False

    def test_rejects_no_extension(self, adapter: PlainTextAdapter):
        assert adapter.can_handle("Makefile", None) is False


# --- extract tests: no headings ---


class TestExtractNoHeadings:
    """Tests for plain text files without any detectable headings."""

    def test_no_headings_single_chunk(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "simple_no_headings.txt").read_bytes()
        result = adapter.extract(content, "simple_no_headings.txt")

        assert isinstance(result, ExtractionResult)
        assert len(result.chunks) == 1

    def test_no_headings_structural_context(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "simple_no_headings.txt").read_bytes()
        result = adapter.extract(content, "simple_no_headings.txt")

        assert result.chunks[0].structural_context == {"section": "(document)"}

    def test_no_headings_chunk_id(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "simple_no_headings.txt").read_bytes()
        result = adapter.extract(content, "simple_no_headings.txt")

        assert result.chunks[0].chunk_id == "chunk-000"
        assert result.chunks[0].order == 0

    def test_no_headings_contains_text(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "simple_no_headings.txt").read_bytes()
        result = adapter.extract(content, "simple_no_headings.txt")

        assert "simple plain text document" in result.chunks[0].text


# --- extract tests: ALL CAPS headings ---


class TestExtractAllCapsHeadings:
    """Tests for plain text files with ALL CAPS headings."""

    def test_splits_by_all_caps_headings(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "all_caps_headings.txt").read_bytes()
        result = adapter.extract(content, "all_caps_headings.txt")

        assert len(result.chunks) == 3

    def test_chunk_ids_sequential(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "all_caps_headings.txt").read_bytes()
        result = adapter.extract(content, "all_caps_headings.txt")

        assert result.chunks[0].chunk_id == "chunk-000"
        assert result.chunks[1].chunk_id == "chunk-001"
        assert result.chunks[2].chunk_id == "chunk-002"

    def test_chunk_orders_sequential(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "all_caps_headings.txt").read_bytes()
        result = adapter.extract(content, "all_caps_headings.txt")

        orders = [c.order for c in result.chunks]
        assert orders == [0, 1, 2]

    def test_structural_context_has_heading_text(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "all_caps_headings.txt").read_bytes()
        result = adapter.extract(content, "all_caps_headings.txt")

        assert result.chunks[0].structural_context == {"section": "INTRODUCTION"}
        assert result.chunks[1].structural_context == {"section": "REQUIREMENTS AND DESIGN"}
        assert result.chunks[2].structural_context == {"section": "CONCLUSION"}

    def test_heading_included_in_chunk_text(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "all_caps_headings.txt").read_bytes()
        result = adapter.extract(content, "all_caps_headings.txt")

        assert "INTRODUCTION" in result.chunks[0].text
        assert "overview of the content" in result.chunks[0].text


# --- extract tests: underline headings ---


class TestExtractUnderlineHeadings:
    """Tests for plain text files with === and --- underlined headings."""

    def test_splits_by_underline_headings(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "underline_headings.txt").read_bytes()
        result = adapter.extract(content, "underline_headings.txt")

        assert len(result.chunks) == 2

    def test_structural_context_has_heading_text(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "underline_headings.txt").read_bytes()
        result = adapter.extract(content, "underline_headings.txt")

        assert result.chunks[0].structural_context == {"section": "Introduction"}
        assert result.chunks[1].structural_context == {"section": "Implementation Details"}

    def test_underline_not_in_chunk_text(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "underline_headings.txt").read_bytes()
        result = adapter.extract(content, "underline_headings.txt")

        assert "============" not in result.chunks[0].text
        assert "---------------------" not in result.chunks[1].text

    def test_heading_text_in_chunk(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "underline_headings.txt").read_bytes()
        result = adapter.extract(content, "underline_headings.txt")

        assert "Introduction" in result.chunks[0].text
        assert "explanatory text" in result.chunks[0].text


# --- extract tests: mixed headings ---


class TestExtractMixedHeadings:
    """Tests for plain text files with both ALL CAPS and underlined headings."""

    def test_detects_both_heading_types(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "mixed_headings.txt").read_bytes()
        result = adapter.extract(content, "mixed_headings.txt")

        assert len(result.chunks) == 3

    def test_structural_contexts_correct(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "mixed_headings.txt").read_bytes()
        result = adapter.extract(content, "mixed_headings.txt")

        assert result.chunks[0].structural_context == {"section": "Overview"}
        assert result.chunks[1].structural_context == {"section": "REQUIREMENTS"}
        assert result.chunks[2].structural_context == {"section": "Design Notes"}

    def test_chunk_ids_sequential(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "mixed_headings.txt").read_bytes()
        result = adapter.extract(content, "mixed_headings.txt")

        for i, chunk in enumerate(result.chunks):
            assert chunk.chunk_id == f"chunk-{i:03d}"
            assert chunk.order == i


# --- extract tests: preamble ---


class TestExtractPreamble:
    """Tests for plain text files with content before the first heading."""

    def test_preamble_creates_document_chunk(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "preamble_then_headings.txt").read_bytes()
        result = adapter.extract(content, "preamble_then_headings.txt")

        assert result.chunks[0].structural_context == {"section": "(document)"}

    def test_preamble_chunk_id_is_first(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "preamble_then_headings.txt").read_bytes()
        result = adapter.extract(content, "preamble_then_headings.txt")

        assert result.chunks[0].chunk_id == "chunk-000"
        assert result.chunks[0].order == 0

    def test_preamble_text_content(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "preamble_then_headings.txt").read_bytes()
        result = adapter.extract(content, "preamble_then_headings.txt")

        assert "preamble content" in result.chunks[0].text

    def test_headings_follow_preamble(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "preamble_then_headings.txt").read_bytes()
        result = adapter.extract(content, "preamble_then_headings.txt")

        # Preamble + 2 headings = 3 chunks
        assert len(result.chunks) == 3
        assert result.chunks[1].structural_context == {"section": "FIRST SECTION"}
        assert result.chunks[2].structural_context == {"section": "SECOND SECTION"}


# --- extract tests: empty file ---


class TestExtractEmptyFile:
    """Tests for empty plain text files."""

    def test_empty_file_returns_no_chunks(self, adapter: PlainTextAdapter):
        content = (FIXTURES_DIR / "empty.txt").read_bytes()
        result = adapter.extract(content, "empty.txt")

        assert len(result.chunks) == 0
        assert result.warnings == []


# --- extract tests: dataclass structure ---


class TestExtractionResultStructure:
    """Tests that the extraction result has the correct structure."""

    def test_result_has_chunks_and_warnings(self, adapter: PlainTextAdapter):
        content = b"Hello world"
        result = adapter.extract(content, "test.txt")

        assert isinstance(result, ExtractionResult)
        assert isinstance(result.chunks, list)
        assert isinstance(result.warnings, list)

    def test_chunks_are_content_chunk_instances(self, adapter: PlainTextAdapter):
        content = b"Hello world"
        result = adapter.extract(content, "test.txt")

        for chunk in result.chunks:
            assert isinstance(chunk, ContentChunk)
            assert isinstance(chunk.chunk_id, str)
            assert isinstance(chunk.text, str)
            assert isinstance(chunk.structural_context, dict)
            assert isinstance(chunk.order, int)
