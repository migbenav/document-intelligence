"""Unit tests for the document ingestion validator module."""

import pytest

from app.ingestion.validator import ValidationResult, Validator
from app.models.document import DocumentFormat


@pytest.fixture
def validator() -> Validator:
    return Validator()


# --- Successful validation tests ---


class TestValidFormats:
    """Tests for files that should pass validation."""

    def test_valid_markdown_file(self, validator: Validator):
        content = b"# Hello World\n\nSome content here."
        result = validator.validate(content, "readme.md")

        assert result.valid is True
        assert result.detected_format == DocumentFormat.MARKDOWN
        assert result.error_code is None
        assert result.error_message is None

    def test_valid_plaintext_file(self, validator: Validator):
        content = b"Just some plain text content."
        result = validator.validate(content, "notes.txt")

        assert result.valid is True
        assert result.detected_format == DocumentFormat.PLAIN_TEXT
        assert result.error_code is None
        assert result.error_message is None

    def test_valid_pdf_file(self, validator: Validator):
        content = b"%PDF-1.4 fake pdf content"
        result = validator.validate(content, "document.pdf")

        assert result.valid is True
        assert result.detected_format == DocumentFormat.PDF
        assert result.error_code is None
        assert result.error_message is None

    def test_extension_case_insensitive(self, validator: Validator):
        content = b"# Title"
        result = validator.validate(content, "README.MD")

        assert result.valid is True
        assert result.detected_format == DocumentFormat.MARKDOWN

    def test_empty_text_file(self, validator: Validator):
        result = validator.validate(b"", "empty.txt")

        assert result.valid is True
        assert result.detected_format == DocumentFormat.PLAIN_TEXT

    def test_file_at_exact_size_limit_text(self, validator: Validator):
        content = b"x" * 1_048_576  # exactly 1 MB
        result = validator.validate(content, "big.md")

        assert result.valid is True
        assert result.detected_format == DocumentFormat.MARKDOWN

    def test_file_at_exact_size_limit_pdf(self, validator: Validator):
        content = b"x" * 10_485_760  # exactly 10 MB
        result = validator.validate(content, "big.pdf")

        assert result.valid is True
        assert result.detected_format == DocumentFormat.PDF


# --- Unsupported format tests (Req 1.4) ---


class TestUnsupportedFormat:
    """Tests for unsupported file formats."""

    def test_docx_rejected(self, validator: Validator):
        result = validator.validate(b"fake docx", "report.docx")

        assert result.valid is False
        assert result.error_code == "unsupported_format"
        assert ".md" in result.error_message
        assert ".txt" in result.error_message
        assert ".pdf" in result.error_message

    def test_xlsx_rejected(self, validator: Validator):
        result = validator.validate(b"fake xlsx", "data.xlsx")

        assert result.valid is False
        assert result.error_code == "unsupported_format"

    def test_no_extension_rejected(self, validator: Validator):
        result = validator.validate(b"some content", "Makefile")

        assert result.valid is False
        assert result.error_code == "unsupported_format"

    def test_html_rejected(self, validator: Validator):
        result = validator.validate(b"<html></html>", "page.html")

        assert result.valid is False
        assert result.error_code == "unsupported_format"


# --- Size limit tests (Req 1.5, 1.6) ---


class TestFileTooLarge:
    """Tests for files exceeding size limits."""

    def test_markdown_exceeds_1mb(self, validator: Validator):
        content = b"x" * (1_048_576 + 1)  # 1 byte over 1 MB
        result = validator.validate(content, "large.md")

        assert result.valid is False
        assert result.error_code == "file_too_large"
        assert "1 MB" in result.error_message

    def test_txt_exceeds_1mb(self, validator: Validator):
        content = b"x" * (1_048_576 + 1)
        result = validator.validate(content, "large.txt")

        assert result.valid is False
        assert result.error_code == "file_too_large"
        assert "1 MB" in result.error_message

    def test_pdf_exceeds_10mb(self, validator: Validator):
        content = b"x" * (10_485_760 + 1)  # 1 byte over 10 MB
        result = validator.validate(content, "huge.pdf")

        assert result.valid is False
        assert result.error_code == "file_too_large"
        assert "10 MB" in result.error_message


# --- Encoding tests (Req 1.7) ---


class TestInvalidEncoding:
    """Tests for non-UTF-8 encoded text files."""

    def test_latin1_markdown_rejected(self, validator: Validator):
        # Latin-1 encoded string with non-UTF-8 byte sequence
        content = "Ñoño résumé".encode("latin-1")
        result = validator.validate(content, "spanish.md")

        assert result.valid is False
        assert result.error_code == "invalid_encoding"
        assert "UTF-8" in result.error_message

    def test_invalid_bytes_txt_rejected(self, validator: Validator):
        # Invalid UTF-8 byte sequence
        content = b"\xff\xfe\x00\x01"
        result = validator.validate(content, "broken.txt")

        assert result.valid is False
        assert result.error_code == "invalid_encoding"
        assert "UTF-8" in result.error_message

    def test_pdf_skips_encoding_check(self, validator: Validator):
        # PDF files should NOT be checked for UTF-8 encoding
        content = b"\xff\xfe\x00\x01" * 10
        result = validator.validate(content, "binary.pdf")

        assert result.valid is True
        assert result.detected_format == DocumentFormat.PDF

    def test_valid_utf8_with_multibyte_chars(self, validator: Validator):
        # UTF-8 with emoji and accented characters should pass
        content = "Héllo 🌍 wörld".encode("utf-8")
        result = validator.validate(content, "unicode.md")

        assert result.valid is True
        assert result.detected_format == DocumentFormat.MARKDOWN
