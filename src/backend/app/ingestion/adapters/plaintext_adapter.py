"""Plain text format extraction adapter."""

import re

from app.ingestion.adapters.base import ContentChunk, ExtractionResult, FormatAdapter

# ALL CAPS heading: line that is entirely uppercase (may contain spaces, numbers, punctuation)
# and has at least 2 alphabetic characters.
_ALL_CAPS_PATTERN = re.compile(r"^([A-Z][A-Z0-9 \t!@#$%^&*()_\-+=\[\]{};:'\",.<>?/\\|`~]*[A-Z][A-Z0-9 \t!@#$%^&*()_\-+=\[\]{};:'\",.<>?/\\|`~]*)$")


def _is_all_caps_heading(line: str) -> bool:
    """Check if a line is an ALL CAPS heading.

    Must be entirely uppercase letters (may contain spaces, numbers, punctuation)
    and have at least 2 alphabetic characters.
    """
    stripped = line.strip()
    if not stripped:
        return False
    # Must have at least 2 alphabetic characters
    alpha_count = sum(1 for c in stripped if c.isalpha())
    if alpha_count < 2:
        return False
    # All alphabetic characters must be uppercase
    for c in stripped:
        if c.isalpha() and not c.isupper():
            return False
    return True


def _is_underline(line: str, char: str) -> bool:
    """Check if a line is an underline consisting entirely of the given char (3+ chars)."""
    stripped = line.strip()
    return len(stripped) >= 3 and all(c == char for c in stripped)


class PlainTextAdapter(FormatAdapter):
    """Extracts text from plain text files, splitting by detected heading patterns."""

    def can_handle(self, filename: str, content_type: str | None) -> bool:
        """Return True for .txt files."""
        return filename.lower().endswith(".txt")

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        """Extract text content from a plain text file.

        Splits by detected heading patterns:
        - ALL CAPS lines (at least 2 alpha characters, all uppercase)
        - Lines followed by === or --- underlines (3+ characters)

        If no headings are detected, returns a single chunk with
        structural_context {"section": "(document)"}.
        """
        text = file_bytes.decode("utf-8")
        chunks: list[ContentChunk] = []
        warnings: list[str] = []

        if not text.strip():
            return ExtractionResult(chunks=chunks, warnings=warnings)

        lines = text.splitlines(keepends=True)
        headings = self._detect_headings(lines)

        if not headings:
            # No headings — entire content is one chunk
            chunks.append(
                ContentChunk(
                    chunk_id="chunk-000",
                    text=text.strip(),
                    structural_context={"section": "(document)"},
                    order=0,
                )
            )
            return ExtractionResult(chunks=chunks, warnings=warnings)

        # Build chunks from heading positions
        order = 0

        # Handle preamble (content before first heading)
        first_heading_line_idx = headings[0][0]
        preamble_text = "".join(lines[:first_heading_line_idx]).strip()

        if preamble_text:
            chunks.append(
                ContentChunk(
                    chunk_id=f"chunk-{order:03d}",
                    text=preamble_text,
                    structural_context={"section": "(document)"},
                    order=order,
                )
            )
            order += 1

        # Process each heading section
        for i, (line_idx, heading_text, heading_type) in enumerate(headings):
            # Determine start of this section's content
            if heading_type == "allcaps":
                # ALL CAPS heading: the heading line IS part of the chunk text
                section_start = line_idx
            else:
                # Underline heading: the heading text line is part of the chunk,
                # but the underline is NOT
                section_start = line_idx

            # Determine end of this section
            if i + 1 < len(headings):
                section_end = headings[i + 1][0]
            else:
                section_end = len(lines)

            # Build chunk text
            if heading_type == "underline":
                # Include the heading text line but skip the underline line
                underline_idx = line_idx + 1
                section_lines = [lines[line_idx]]  # heading text line
                # Skip the underline, include everything after it until next heading
                section_lines.extend(lines[underline_idx + 1:section_end])
            else:
                # ALL CAPS: include everything from heading line to end of section
                section_lines = lines[section_start:section_end]

            section_text = "".join(section_lines).strip()

            if section_text:
                chunks.append(
                    ContentChunk(
                        chunk_id=f"chunk-{order:03d}",
                        text=section_text,
                        structural_context={"section": heading_text},
                        order=order,
                    )
                )
                order += 1

        return ExtractionResult(chunks=chunks, warnings=warnings)

    def _detect_headings(self, lines: list[str]) -> list[tuple[int, str, str]]:
        """Detect heading positions in lines.

        Returns a list of (line_index, heading_text, heading_type) tuples.
        heading_type is either "allcaps" or "underline".
        """
        headings: list[tuple[int, str, str]] = []
        skip_next = False

        for i, line in enumerate(lines):
            if skip_next:
                skip_next = False
                continue

            stripped = line.rstrip("\n\r")

            # Check for underline heading (line followed by === or ---)
            if i + 1 < len(lines):
                next_line = lines[i + 1].rstrip("\n\r")
                if stripped.strip() and (
                    _is_underline(next_line, "=") or _is_underline(next_line, "-")
                ):
                    headings.append((i, stripped.strip(), "underline"))
                    skip_next = True
                    continue

            # Check for ALL CAPS heading
            if _is_all_caps_heading(stripped):
                headings.append((i, stripped.strip(), "allcaps"))

        return headings
