"""LocalAnalyzer — deterministic structural analysis of the IR.

Extracts title, computes statistics, detects organization type, detects existing
index, and assembles file metadata. No network calls, no LLM calls, no external
service calls. Operates exclusively on the in-memory IR data.

See ADR-007 Nivel 1 "Sin LLM (instantáneo)" and Requirement 2.
"""

import re
from dataclasses import dataclass

from app.models.document import IntermediateRepresentation
from app.models.document_card import (
    DocumentCardStatistics,
    FileMetadata,
    OrganizationType,
)

# Regex patterns for organization type detection
_NUMBERED_ARTICLES_PATTERN = re.compile(
    r"Art\.\s*\d+|Artículo\s+\d+|ARTICULO", re.IGNORECASE
)
_HIERARCHICAL_NUMBERING_PATTERN = re.compile(r"\d+\.\d+")

# TOC detection patterns
_TOC_PAGE_NUMBER_PATTERN = re.compile(r"\.{2,}\s*\d+|[-–—]{2,}\s*\d+|\s{2,}\d+\s*$")
_TOC_SECTION_NAMES = re.compile(
    r"índice|contenido|table of contents|contents", re.IGNORECASE
)


@dataclass
class LocalAnalysisResult:
    """Result of deterministic local processing of the IR."""

    title: str
    statistics: DocumentCardStatistics
    organization_type: OrganizationType
    file_metadata: FileMetadata


class LocalAnalyzer:
    """Deterministic structural analysis of the IR. No network calls.

    Extracts title, computes statistics, detects organization type,
    detects existing index, and assembles file metadata from the
    IntermediateRepresentation produced by the ingestion layer.
    """

    def analyze(self, ir: IntermediateRepresentation) -> LocalAnalysisResult:
        """Extract title, statistics, organization type, file metadata from IR.

        Always succeeds. Completes in <100ms for documents up to 10 MB.
        """
        title = self._extract_title(ir)
        has_existing_index = self._detect_existing_index(ir)
        statistics = self._compute_statistics(ir, has_existing_index)
        organization_type = self._detect_organization_type(ir)
        file_metadata = self._build_file_metadata(ir)

        return LocalAnalysisResult(
            title=title,
            statistics=statistics,
            organization_type=organization_type,
            file_metadata=file_metadata,
        )

    def _extract_title(self, ir: IntermediateRepresentation) -> str:
        """First heading (by chunk order) from structural_context.section, or filename without extension."""
        for chunk in sorted(ir.chunks, key=lambda c: c.order):
            section = chunk.structural_context.get("section")
            if section:
                return section
        # Fallback: filename without extension
        filename = ir.metadata.original_filename
        return filename.rsplit(".", 1)[0] if "." in filename else filename

    def _compute_statistics(
        self, ir: IntermediateRepresentation, has_existing_index: bool
    ) -> DocumentCardStatistics:
        """Count total chunks, unique sections, max hierarchy level, detect existing index."""
        total_chunks = len(ir.chunks)

        # Unique sections: distinct values of structural_context.section
        sections: set[str] = set()
        max_level = 1  # Default to 1 if no levels present

        for chunk in ir.chunks:
            ctx = chunk.structural_context
            section = ctx.get("section")
            if section:
                sections.add(section)
            level = ctx.get("level")
            if level is not None and level > max_level:
                max_level = level

        return DocumentCardStatistics(
            total_chunks=total_chunks,
            sections_detected=len(sections),
            hierarchy_levels=max_level,
            has_existing_index=has_existing_index,
        )

    def _detect_organization_type(
        self, ir: IntermediateRepresentation
    ) -> OrganizationType:
        """Detect organization type with priority order.

        Priority: numbered_articles > headed_sections > hierarchical_numbering > free_form.
        """
        has_headed_sections = False

        for chunk in ir.chunks:
            # Check for numbered articles pattern
            if _NUMBERED_ARTICLES_PATTERN.search(chunk.text):
                return OrganizationType.NUMBERED_ARTICLES

            # Track if any chunk has a heading level
            if chunk.structural_context.get("level") is not None:
                has_headed_sections = True

        # Second priority: headed_sections
        if has_headed_sections:
            return OrganizationType.HEADED_SECTIONS

        # Third priority: hierarchical_numbering
        for chunk in ir.chunks:
            if _HIERARCHICAL_NUMBERING_PATTERN.search(chunk.text):
                return OrganizationType.HIERARCHICAL_NUMBERING

        # Default: free_form
        return OrganizationType.FREE_FORM

    def _detect_existing_index(self, ir: IntermediateRepresentation) -> bool:
        """Search first 20% of chunks for TOC patterns.

        Patterns detected:
        - Short lines with trailing page numbers (dot/dash separators)
        - Chunks whose structural_context.section contains "índice", "contenido",
          "table of contents", or "contents" (case-insensitive)
        """
        if not ir.chunks:
            return False

        sorted_chunks = sorted(ir.chunks, key=lambda c: c.order)
        # First 20% of chunks (at least 1 chunk)
        cutoff = max(1, len(sorted_chunks) * 20 // 100)
        first_portion = sorted_chunks[:cutoff]

        for chunk in first_portion:
            # Check section name for TOC indicators
            section = chunk.structural_context.get("section", "")
            if section and _TOC_SECTION_NAMES.search(section):
                return True

            # Check text for TOC patterns (short lines with page numbers, dot/dash separators)
            lines = chunk.text.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped and _TOC_PAGE_NUMBER_PATTERN.search(stripped):
                    return True

        return False

    def _build_file_metadata(self, ir: IntermediateRepresentation) -> FileMetadata:
        """Extract size_bytes, format, language from IR metadata."""
        return FileMetadata(
            size_bytes=ir.metadata.size_bytes,
            format=ir.metadata.format.value,
            language=ir.metadata.language.value,
        )
