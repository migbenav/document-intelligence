"""Unit tests for the Markdown format extraction adapter."""

from pathlib import Path

import pytest

from app.ingestion.adapters.base import ContentChunk, ExtractionResult, FormatAdapter
from app.ingestion.adapters.markdown_adapter import MarkdownAdapter

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "ingestion" / "markdown"


@pytest.fixture
def adapter() -> MarkdownAdapter:
    return MarkdownAdapter()


# --- Base class contract tests ---


class TestFormatAdapterContract:
    """Tests that MarkdownAdapter implements the FormatAdapter ABC correctly."""

    def test_is_format_adapter_subclass(self):
        assert issubclass(MarkdownAdapter, FormatAdapter)

    def test_instance_is_format_adapter(self, adapter: MarkdownAdapter):
        assert isinstance(adapter, FormatAdapter)


# --- can_handle tests ---


class TestCanHandle:
    """Tests for MarkdownAdapter.can_handle method."""

    def test_handles_md_extension(self, adapter: MarkdownAdapter):
        assert adapter.can_handle("readme.md", None) is True

    def test_handles_md_extension_case_insensitive(self, adapter: MarkdownAdapter):
        assert adapter.can_handle("README.MD", None) is True

    def test_handles_md_with_content_type(self, adapter: MarkdownAdapter):
        assert adapter.can_handle("doc.md", "text/markdown") is True

    def test_rejects_txt_extension(self, adapter: MarkdownAdapter):
        assert adapter.can_handle("file.txt", None) is False

    def test_rejects_pdf_extension(self, adapter: MarkdownAdapter):
        assert adapter.can_handle("file.pdf", None) is False

    def test_rejects_no_extension(self, adapter: MarkdownAdapter):
        assert adapter.can_handle("Makefile", None) is False


# --- extract tests: simple headings ---


class TestExtractSimpleHeadings:
    """Tests for extraction of Markdown files with h1/h2 headings."""

    def test_splits_by_h1_and_h2(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "simple_headings.md").read_bytes()
        result = adapter.extract(content, "simple_headings.md")

        assert isinstance(result, ExtractionResult)
        assert len(result.chunks) == 3

    def test_chunk_ids_are_sequential(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "simple_headings.md").read_bytes()
        result = adapter.extract(content, "simple_headings.md")

        assert result.chunks[0].chunk_id == "chunk-000"
        assert result.chunks[1].chunk_id == "chunk-001"
        assert result.chunks[2].chunk_id == "chunk-002"

    def test_chunk_order_is_sequential(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "simple_headings.md").read_bytes()
        result = adapter.extract(content, "simple_headings.md")

        orders = [c.order for c in result.chunks]
        assert orders == [0, 1, 2]

    def test_structural_context_contains_heading(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "simple_headings.md").read_bytes()
        result = adapter.extract(content, "simple_headings.md")

        assert result.chunks[0].structural_context == {"section": "# Introduction"}
        assert result.chunks[1].structural_context == {"section": "## Requirements"}
        assert result.chunks[2].structural_context == {"section": "## Design"}

    def test_chunk_text_includes_heading_and_body(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "simple_headings.md").read_bytes()
        result = adapter.extract(content, "simple_headings.md")

        assert "# Introduction" in result.chunks[0].text
        assert "This is the introduction section." in result.chunks[0].text


# --- extract tests: preamble ---


class TestExtractPreamble:
    """Tests for Markdown files with content before the first heading."""

    def test_preamble_creates_separate_chunk(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "preamble_and_headings.md").read_bytes()
        result = adapter.extract(content, "preamble_and_headings.md")

        assert result.chunks[0].structural_context == {"section": "(preamble)"}

    def test_preamble_chunk_id_is_first(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "preamble_and_headings.md").read_bytes()
        result = adapter.extract(content, "preamble_and_headings.md")

        assert result.chunks[0].chunk_id == "chunk-000"
        assert result.chunks[0].order == 0

    def test_preamble_text_content(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "preamble_and_headings.md").read_bytes()
        result = adapter.extract(content, "preamble_and_headings.md")

        assert "This is preamble content" in result.chunks[0].text
        assert "It has multiple lines." in result.chunks[0].text

    def test_headings_follow_preamble(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "preamble_and_headings.md").read_bytes()
        result = adapter.extract(content, "preamble_and_headings.md")

        # Preamble + h1 + h2 = 3 chunks
        assert len(result.chunks) == 3
        assert result.chunks[1].structural_context == {"section": "# First Section"}
        assert result.chunks[2].structural_context == {"section": "## Subsection"}


# --- extract tests: no headings ---


class TestExtractNoHeadings:
    """Tests for Markdown files without any headings."""

    def test_no_headings_single_preamble_chunk(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "no_headings.md").read_bytes()
        result = adapter.extract(content, "no_headings.md")

        assert len(result.chunks) == 1
        assert result.chunks[0].structural_context == {"section": "(preamble)"}

    def test_no_headings_chunk_id(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "no_headings.md").read_bytes()
        result = adapter.extract(content, "no_headings.md")

        assert result.chunks[0].chunk_id == "chunk-000"
        assert result.chunks[0].order == 0


# --- extract tests: nested headings (h3+) ---


class TestExtractNestedHeadings:
    """Tests that h3+ headings stay within their parent h2 chunk."""

    def test_h3_stays_within_parent_chunk(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "nested_headings.md").read_bytes()
        result = adapter.extract(content, "nested_headings.md")

        # h1, h2 (with h3 and h4 inside), h2 = 3 chunks
        assert len(result.chunks) == 3

    def test_h3_content_included_in_parent(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "nested_headings.md").read_bytes()
        result = adapter.extract(content, "nested_headings.md")

        # The second chunk (## Second Level) should contain h3 and h4 content
        second_chunk = result.chunks[1]
        assert "### Third Level" in second_chunk.text
        assert "This should stay within the parent h2 chunk." in second_chunk.text
        assert "#### Fourth Level" in second_chunk.text

    def test_structural_context_only_h1_h2(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "nested_headings.md").read_bytes()
        result = adapter.extract(content, "nested_headings.md")

        contexts = [c.structural_context for c in result.chunks]
        assert contexts == [
            {"section": "# Top Level"},
            {"section": "## Second Level"},
            {"section": "## Another Second Level"},
        ]


# --- extract tests: empty file ---


class TestExtractEmptyFile:
    """Tests for empty Markdown files."""

    def test_empty_file_returns_no_chunks(self, adapter: MarkdownAdapter):
        content = (FIXTURES_DIR / "empty.md").read_bytes()
        result = adapter.extract(content, "empty.md")

        assert len(result.chunks) == 0
        assert result.warnings == []


# --- extract tests: dataclass structure ---


class TestExtractionResultStructure:
    """Tests that the extraction result has the correct structure."""

    def test_result_has_chunks_and_warnings(self, adapter: MarkdownAdapter):
        content = b"# Hello\n\nWorld"
        result = adapter.extract(content, "test.md")

        assert isinstance(result, ExtractionResult)
        assert isinstance(result.chunks, list)
        assert isinstance(result.warnings, list)

    def test_chunks_are_content_chunk_instances(self, adapter: MarkdownAdapter):
        content = b"# Hello\n\nWorld"
        result = adapter.extract(content, "test.md")

        for chunk in result.chunks:
            assert isinstance(chunk, ContentChunk)
            assert isinstance(chunk.chunk_id, str)
            assert isinstance(chunk.text, str)
            assert isinstance(chunk.structural_context, dict)
            assert isinstance(chunk.order, int)
