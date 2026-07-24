"""Integration tests for the document upload → status → IR retrieval flow.

Tests exercise the full pipeline end-to-end through the HTTP API layer,
using a FakeStorageService (in-memory) to avoid Supabase dependencies.
"""

import uuid

import fitz  # PyMuPDF — used to generate PDF fixtures programmatically
import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helper: generate a valid PDF with text content
# ---------------------------------------------------------------------------


def _make_text_pdf(text: str = "Hello World") -> bytes:
    """Generate a minimal PDF with extractable text using PyMuPDF.

    Ensures the text is long enough to pass scanned-PDF detection (>50 chars).
    """
    doc = fitz.open()
    page = doc.new_page()
    # Insert enough text to exceed the 50-char scanned-PDF threshold
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_scanned_pdf() -> bytes:
    """Generate a blank PDF with no text — triggers scanned PDF detection."""
    doc = fitz.open()
    # Just add a blank page with no text content
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHappyPathMarkdown:
    """Upload a Markdown file and verify full pipeline."""

    async def test_upload_and_retrieve_ir(self, async_client: AsyncClient):
        content = b"# Introduction\n\nThis is the intro.\n\n## Details\n\nSome details here.\n"

        # 1. Upload
        response = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.md", content, "text/markdown")},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "ready"
        assert data["filename"] == "test.md"
        assert data["format"] == "markdown"
        document_id = data["document_id"]

        # 2. Get status
        status_resp = await async_client.get(
            f"/api/v1/documents/{document_id}/status"
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] == "ready"
        assert status_data["chunk_count"] >= 1

        # 3. Get IR
        ir_resp = await async_client.get(
            f"/api/v1/documents/{document_id}/ir"
        )
        assert ir_resp.status_code == 200
        ir_data = ir_resp.json()
        assert ir_data["document_id"] == document_id
        assert ir_data["metadata"]["format"] == "markdown"
        assert ir_data["metadata"]["original_filename"] == "test.md"
        assert len(ir_data["chunks"]) >= 2

        # Verify structural context contains section info
        sections = [c["structural_context"].get("section") for c in ir_data["chunks"]]
        assert any("Introduction" in s for s in sections if s)


@pytest.mark.asyncio
class TestHappyPathPlaintext:
    """Upload a plain text file and verify full pipeline."""

    async def test_upload_and_retrieve_ir(self, async_client: AsyncClient):
        content = b"This is a simple plain text document.\n\nIt has a couple of paragraphs.\n"

        response = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("readme.txt", content, "text/plain")},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "ready"
        assert data["format"] == "plain_text"
        document_id = data["document_id"]

        # Retrieve IR
        ir_resp = await async_client.get(
            f"/api/v1/documents/{document_id}/ir"
        )
        assert ir_resp.status_code == 200
        ir_data = ir_resp.json()
        assert ir_data["metadata"]["format"] == "plain_text"
        assert len(ir_data["chunks"]) >= 1
        # Plain text with no headings → single chunk with "(document)" context
        assert ir_data["chunks"][0]["structural_context"].get("section") == "(document)"


@pytest.mark.asyncio
class TestHappyPathPdf:
    """Upload a programmatically-generated PDF and verify full pipeline."""

    async def test_upload_and_retrieve_ir(self, async_client: AsyncClient):
        pdf_bytes = _make_text_pdf(
            "This is a test PDF document with enough content to pass the scanned detection threshold easily."
        )

        response = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("report.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "ready"
        assert data["format"] == "pdf"
        document_id = data["document_id"]

        # Retrieve IR
        ir_resp = await async_client.get(
            f"/api/v1/documents/{document_id}/ir"
        )
        assert ir_resp.status_code == 200
        ir_data = ir_resp.json()
        assert ir_data["metadata"]["format"] == "pdf"
        assert len(ir_data["chunks"]) >= 1
        # PDF chunks have page structural context
        assert "page" in ir_data["chunks"][0]["structural_context"]
        assert ir_data["chunks"][0]["structural_context"]["page"] == 1


# ---------------------------------------------------------------------------
# Error scenario tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestErrorUnsupportedFormat:
    """Upload an unsupported file format (.docx)."""

    async def test_returns_400_with_error_code(self, async_client: AsyncClient):
        response = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("document.docx", b"fake docx content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "unsupported_format"
        assert "supported_formats" in data
        assert ".md" in data["supported_formats"]
        assert ".txt" in data["supported_formats"]
        assert ".pdf" in data["supported_formats"]


@pytest.mark.asyncio
class TestErrorOversizedFile:
    """Upload a text file exceeding the 1 MB size limit."""

    async def test_returns_400_with_error_code(self, async_client: AsyncClient):
        # Create content just over 1 MB
        oversized_content = b"x" * (1_048_576 + 1)

        response = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("big.txt", oversized_content, "text/plain")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "file_too_large"
        assert "max_size_bytes" in data
        assert data["max_size_bytes"] == 1_048_576


@pytest.mark.asyncio
class TestErrorNonUtf8:
    """Upload a text file with non-UTF-8 encoding."""

    async def test_returns_400_with_error_code(self, async_client: AsyncClient):
        # Latin-1 encoded content that is not valid UTF-8
        latin1_content = "café résumé naïve".encode("latin-1")

        response = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("notes.txt", latin1_content, "text/plain")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_encoding"
        assert "required_encoding" in data
        assert data["required_encoding"] == "utf-8"


@pytest.mark.asyncio
class TestErrorScannedPdf:
    """Upload a scanned (image-only) PDF with no extractable text."""

    async def test_returns_400_with_error_code(self, async_client: AsyncClient):
        scanned_pdf = _make_scanned_pdf()

        response = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("scan.pdf", scanned_pdf, "application/pdf")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "scanned_pdf"


@pytest.mark.asyncio
class TestErrorNonExistentDocumentStatus:
    """GET /status with a random UUID that doesn't exist."""

    async def test_returns_404(self, async_client: AsyncClient):
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/v1/documents/{fake_id}/status"
        )
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"


@pytest.mark.asyncio
class TestErrorNonExistentDocumentIr:
    """GET /ir with a random UUID that doesn't exist."""

    async def test_returns_404(self, async_client: AsyncClient):
        fake_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/v1/documents/{fake_id}/ir"
        )
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"


# ---------------------------------------------------------------------------
# Format-independent output verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFormatIndependentOutput:
    """Same content uploaded as .md and .txt produces equivalent IR text."""

    async def test_equivalent_text_content(self, async_client: AsyncClient):
        # Content with no headings so both formats produce a single-ish chunk
        content_text = "This is a simple document about testing.\n\nIt has two paragraphs of content.\n"

        # Upload as .md
        md_resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("doc.md", content_text.encode(), "text/markdown")},
        )
        assert md_resp.status_code == 202
        md_id = md_resp.json()["document_id"]

        # Upload as .txt
        txt_resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("doc.txt", content_text.encode(), "text/plain")},
        )
        assert txt_resp.status_code == 202
        txt_id = txt_resp.json()["document_id"]

        # Retrieve both IRs
        md_ir = (await async_client.get(f"/api/v1/documents/{md_id}/ir")).json()
        txt_ir = (await async_client.get(f"/api/v1/documents/{txt_id}/ir")).json()

        # Concatenated text should be equivalent
        md_text = " ".join(c["text"] for c in md_ir["chunks"])
        txt_text = " ".join(c["text"] for c in txt_ir["chunks"])

        # Normalize whitespace for comparison (adapters may differ on trailing newlines)
        assert md_text.strip() == txt_text.strip()

        # Both should have the same set of IR fields (format-independent structure)
        assert set(md_ir.keys()) == set(txt_ir.keys())
        assert set(md_ir["metadata"].keys()) == set(txt_ir["metadata"].keys())

        # Chunk structure keys should be identical
        if md_ir["chunks"] and txt_ir["chunks"]:
            assert set(md_ir["chunks"][0].keys()) == set(txt_ir["chunks"][0].keys())
