"""Markdown format extraction adapter."""

import re

from app.ingestion.adapters.base import ContentChunk, ExtractionResult, FormatAdapter

# Regex to split on h1 or h2 headings (lines starting with # or ##, but not ### or deeper)
_HEADING_PATTERN = re.compile(r"^(#{1,2})\s+(.+)$", re.MULTILINE)


class MarkdownAdapter(FormatAdapter):
    """Extracts text from Markdown files, splitting by h1/h2 headings."""

    def can_handle(self, filename: str, content_type: str | None) -> bool:
        """Return True for .md files."""
        return filename.lower().endswith(".md")

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        """Extract text content from a Markdown file.

        Splits by h1/h2 headings into chunks. Content before the first heading
        becomes a preamble chunk. h3+ headings stay within their parent chunk.
        """
        text = file_bytes.decode("utf-8")
        chunks: list[ContentChunk] = []
        warnings: list[str] = []

        # Find all h1/h2 heading positions
        headings = list(_HEADING_PATTERN.finditer(text))

        if not headings:
            # No headings — entire content is one chunk
            stripped = text.strip()
            if stripped:
                chunks.append(
                    ContentChunk(
                        chunk_id="chunk-000",
                        text=stripped,
                        structural_context={"section": "(preamble)"},
                        order=0,
                    )
                )
            return ExtractionResult(chunks=chunks, warnings=warnings)

        # Handle preamble (content before first heading)
        preamble_text = text[: headings[0].start()].strip()
        order = 0

        if preamble_text:
            chunks.append(
                ContentChunk(
                    chunk_id=f"chunk-{order:03d}",
                    text=preamble_text,
                    structural_context={"section": "(preamble)"},
                    order=order,
                )
            )
            order += 1

        # Process each heading section
        for i, match in enumerate(headings):
            heading_line = match.group(0)  # e.g., "## Requirements"

            # Determine the end of this section
            if i + 1 < len(headings):
                section_end = headings[i + 1].start()
            else:
                section_end = len(text)

            section_text = text[match.start() : section_end].strip()

            if section_text:
                chunks.append(
                    ContentChunk(
                        chunk_id=f"chunk-{order:03d}",
                        text=section_text,
                        structural_context={"section": heading_line},
                        order=order,
                    )
                )
                order += 1

        return ExtractionResult(chunks=chunks, warnings=warnings)
