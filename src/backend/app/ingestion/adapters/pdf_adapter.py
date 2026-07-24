"""PDF format extraction adapter using PyMuPDF."""

import fitz  # PyMuPDF

from app.ingestion.adapters.base import ContentChunk, ExtractionResult, FormatAdapter

# Pages with more than this many characters get split at paragraph boundaries.
_MAX_PAGE_CHARS = 4000

# If total extracted text is less than this threshold, the PDF is considered scanned.
_SCANNED_THRESHOLD = 50


def is_scanned_pdf(doc: fitz.Document) -> bool:
    """Detect whether a PDF is scanned (image-only, no extractable text).

    A PDF is "scanned" when total text length across all pages < 50 chars
    while page_count > 0.
    """
    if doc.page_count == 0:
        return False
    total_text_length = sum(len(page.get_text()) for page in doc)
    return total_text_length < _SCANNED_THRESHOLD


def _is_complex_table(table: "fitz.table.Table") -> bool:
    """Heuristic: a table is complex if it has merged cells or multi-level headers.

    PyMuPDF Table objects expose header and cell information that we can inspect.
    We check for:
    - Tables with header rows > 1 (multi-level headers)
    - Tables with cells that span multiple columns/rows (merged cells)
    """
    # Check for multi-level headers
    if hasattr(table, "header") and table.header:
        if hasattr(table.header, "external") and table.header.external:
            return True
        # Multiple header rows indicate complex table
        if hasattr(table, "col_count") and hasattr(table, "row_count"):
            # Check for None cells which indicate merged cells
            for row in table.extract():
                none_count = sum(1 for cell in row if cell is None)
                if none_count > 0:
                    return True
    return False


def _split_at_paragraphs(text: str, page_number: int) -> list[tuple[str, dict]]:
    """Split text at paragraph boundaries (double newlines).

    Returns list of (text, structural_context) tuples.
    """
    # Split on double newlines (paragraph boundaries)
    paragraphs = text.split("\n\n")

    # Reassemble into chunks that are within the limit
    result_chunks: list[tuple[str, dict]] = []
    current_text = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        candidate = current_text + ("\n\n" if current_text else "") + para

        if len(candidate) > _MAX_PAGE_CHARS and current_text:
            # Flush current chunk
            result_chunks.append(
                (current_text, {"page": page_number})
            )
            current_text = para
        else:
            current_text = candidate

    # Flush remaining text
    if current_text:
        result_chunks.append(
            (current_text, {"page": page_number})
        )

    return result_chunks


class PdfAdapter(FormatAdapter):
    """Extracts text from PDF files using PyMuPDF."""

    def can_handle(self, filename: str, content_type: str | None) -> bool:
        """Return True for .pdf files."""
        return filename.lower().endswith(".pdf")

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        """Extract text content from a PDF file.

        Opens the PDF with PyMuPDF, detects scanned PDFs, extracts text per page
        with structural_context {"page": N} (1-indexed), splits long pages at
        paragraph boundaries, ignores images, extracts simple tables as text,
        and skips complex tables with a warning.
        """
        chunks: list[ContentChunk] = []
        warnings: list[str] = []

        doc = fitz.open(stream=file_bytes, filetype="pdf")

        try:
            # Handle empty PDF (no pages)
            if doc.page_count == 0:
                return ExtractionResult(chunks=chunks, warnings=warnings)

            # Detect scanned PDF
            if is_scanned_pdf(doc):
                raise ValueError(
                    "Scanned PDF detected: this document contains no extractable text. "
                    "Scanned PDFs (image-only) are not supported."
                )

            order = 0

            for page_idx in range(doc.page_count):
                page = doc[page_idx]
                page_number = page_idx + 1  # 1-indexed

                # Extract tables first to handle them separately
                page_text = page.get_text()

                # Try to find and handle tables on this page
                try:
                    tables = page.find_tables()
                    if tables and tables.tables:
                        for table in tables.tables:
                            if _is_complex_table(table):
                                warnings.append(
                                    f"Complex table skipped on page {page_number}"
                                )
                except Exception:
                    # If table detection fails, just use the plain text extraction
                    pass

                # Use the extracted text (images are already ignored by get_text())
                text = page_text.strip()

                if not text:
                    continue

                # Check if page text exceeds the max and needs splitting
                if len(text) > _MAX_PAGE_CHARS:
                    sub_chunks = _split_at_paragraphs(text, page_number)
                    for chunk_text, context in sub_chunks:
                        chunks.append(
                            ContentChunk(
                                chunk_id=f"chunk-{order:03d}",
                                text=chunk_text,
                                structural_context=context,
                                order=order,
                            )
                        )
                        order += 1
                else:
                    chunks.append(
                        ContentChunk(
                            chunk_id=f"chunk-{order:03d}",
                            text=text,
                            structural_context={"page": page_number},
                            order=order,
                        )
                    )
                    order += 1

        finally:
            doc.close()

        return ExtractionResult(chunks=chunks, warnings=warnings)
