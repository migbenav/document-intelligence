"""Unit tests for the QueryEvidenceVerifier.

Covers: exact match in referenced chunk, exact match in different chunk,
fuzzy match at/above/below 80% threshold, empty evidence text handling,
missing chunk_id in IR, and all_evidence_unverified flag computation.

Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7
"""

from datetime import datetime, timezone

import pytest

from app.analysis.query.evidence_verifier import QueryEvidenceVerifier
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)
from app.models.query import QuerySourceRef


# --- Fixtures ---


@pytest.fixture
def sample_metadata() -> DocumentMetadata:
    return DocumentMetadata(
        original_filename="test.md",
        format=DocumentFormat.MARKDOWN,
        size_bytes=2048,
        language=DetectedLanguage.SPANISH,
        upload_timestamp=datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def ir_with_chunks(sample_metadata: DocumentMetadata) -> IntermediateRepresentation:
    """IR with three chunks containing different text for verification tests."""
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=sample_metadata,
        chunks=[
            ContentChunkModel(
                chunk_id="chunk-001",
                text="The system shall process documents automatically and efficiently.",
                structural_context={"section": "# Introduction"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="chunk-002",
                text="Users can upload files in PDF, Markdown, or plain text format.",
                structural_context={"section": "# Features"},
                order=1,
            ),
            ContentChunkModel(
                chunk_id="chunk-003",
                text="All processing happens on the server side with no client computation.",
                structural_context={"section": "# Architecture"},
                order=2,
            ),
        ],
    )


def _make_source_ref(
    evidence: str, chunk_id: str = "chunk-001", document_id: str = "doc-001"
) -> QuerySourceRef:
    """Helper to create a QuerySourceRef with given evidence and chunk_id."""
    return QuerySourceRef(
        document_id=document_id,
        chunk_id=chunk_id,
        evidence=evidence,
    )


# --- Exact Match in Referenced Chunk Tests ---


class TestExactMatchInReferencedChunk:
    """Req 4.1, 4.2: Exact substring match found in the referenced chunk_id."""

    def test_exact_substring_in_referenced_chunk(self, ir_with_chunks):
        """Evidence that is a substring of the referenced chunk should be verified."""
        source_ref = _make_source_ref(
            evidence="process documents automatically",
            chunk_id="chunk-001",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert len(result) == 1
        assert result[0].evidence_verified is True

    def test_full_chunk_text_as_evidence(self, ir_with_chunks):
        """Evidence matching the full chunk text should be verified."""
        source_ref = _make_source_ref(
            evidence="The system shall process documents automatically and efficiently.",
            chunk_id="chunk-001",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is True

    def test_evidence_at_end_of_chunk(self, ir_with_chunks):
        """Evidence matching the tail of the referenced chunk should be verified."""
        source_ref = _make_source_ref(
            evidence="automatically and efficiently.",
            chunk_id="chunk-001",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is True


# --- Exact Match in Different Chunk Tests ---


class TestExactMatchInDifferentChunk:
    """Req 4.1, 4.2: Exact match found in a chunk other than the referenced one."""

    def test_evidence_in_different_chunk(self, ir_with_chunks):
        """Evidence found in a chunk other than referenced should still verify."""
        source_ref = _make_source_ref(
            evidence="upload files in PDF",
            chunk_id="chunk-001",  # references chunk-001 but text is in chunk-002
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is True

    def test_evidence_in_third_chunk_when_referencing_first(self, ir_with_chunks):
        """Evidence in chunk-003 found even when referencing chunk-001."""
        source_ref = _make_source_ref(
            evidence="server side with no client computation",
            chunk_id="chunk-001",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is True


# --- Fuzzy Match Tests ---


class TestFuzzyMatch:
    """Req 4.1, 4.2, 4.3: Fuzzy match at/above/below 80% threshold."""

    def test_fuzzy_match_above_threshold(self, sample_metadata):
        """Evidence with minor differences should pass fuzzy matching at 80%."""
        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=sample_metadata,
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="The system processes documents automatically and efficiently.",
                    structural_context={"section": "# Intro"},
                    order=0,
                ),
            ],
        )
        # "shall process" vs "processes" — close enough for fuzzy
        source_ref = _make_source_ref(
            evidence="The system shall process documents automatically and efficiently.",
            chunk_id="chunk-001",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir)

        assert result[0].evidence_verified is True

    def test_fuzzy_match_at_threshold_boundary(self, sample_metadata):
        """Evidence that just meets the 80% threshold should be verified."""
        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=sample_metadata,
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="The system shall process documents automatically and efficiently.",
                    structural_context={"section": "# Intro"},
                    order=0,
                ),
            ],
        )
        # Minor typo differences that should still be above 80% similarity
        source_ref = _make_source_ref(
            evidence="The system shall procss documents automaticaly and efficiently.",
            chunk_id="chunk-001",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir)

        assert result[0].evidence_verified is True

    def test_fuzzy_match_below_threshold(self, ir_with_chunks):
        """Evidence that is too different should NOT be verified."""
        source_ref = _make_source_ref(
            evidence="This text does not exist anywhere in the document at all whatsoever.",
            chunk_id="chunk-001",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is False

    def test_custom_fuzzy_threshold(self, sample_metadata):
        """A custom threshold can change what passes fuzzy matching."""
        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=sample_metadata,
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="The system processes documents automatically and efficiently.",
                    structural_context={"section": "# Intro"},
                    order=0,
                ),
            ],
        )
        source_ref = _make_source_ref(
            evidence="The system shall process documents automatically and efficiently.",
            chunk_id="chunk-001",
        )
        # Very high threshold should reject the match
        verifier = QueryEvidenceVerifier(fuzzy_threshold=0.99)
        result = verifier.verify([source_ref], ir)

        assert result[0].evidence_verified is False


# --- Empty Evidence Tests ---


class TestEmptyEvidenceHandling:
    """Req 4.6: Empty evidence text should be marked unverified without running algorithm."""

    def test_empty_string_evidence(self, ir_with_chunks):
        """Empty evidence should be marked unverified."""
        source_ref = _make_source_ref(evidence="", chunk_id="chunk-001")
        # Bypass pydantic validation for empty evidence by constructing manually
        source_ref_obj = QuerySourceRef(
            document_id="doc-001",
            chunk_id="chunk-001",
            evidence="",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref_obj], ir_with_chunks)

        assert result[0].evidence_verified is False

    def test_whitespace_only_evidence(self, ir_with_chunks):
        """Whitespace-only evidence normalizes to empty, should be marked unverified."""
        source_ref = QuerySourceRef(
            document_id="doc-001",
            chunk_id="chunk-001",
            evidence="   \t\n  ",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is False


# --- Missing Chunk ID Tests ---


class TestMissingChunkId:
    """Req 4.7: Missing chunk_id should skip the referenced-chunk step."""

    def test_nonexistent_chunk_id_falls_through_to_any_chunk(self, ir_with_chunks):
        """When chunk_id doesn't exist in IR, evidence can still be found in other chunks."""
        source_ref = _make_source_ref(
            evidence="upload files in PDF",
            chunk_id="chunk-999",  # doesn't exist in the IR
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is True

    def test_nonexistent_chunk_id_with_no_match_anywhere(self, ir_with_chunks):
        """When chunk_id doesn't exist and evidence is not in any chunk, mark unverified."""
        source_ref = _make_source_ref(
            evidence="completely fabricated text that exists nowhere in the document.",
            chunk_id="chunk-999",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is False


# --- All Evidence Unverified Flag Tests ---


class TestAllEvidenceUnverifiedFlag:
    """Req 4.5: all_evidence_unverified is computed from individual evidence_verified flags.

    Note: The QueryEvidenceVerifier itself does NOT compute the all_evidence_unverified
    flag — that is done by QueryService. These tests verify that evidence_verified is
    set correctly on each source_ref so the flag CAN be computed correctly.
    """

    def test_all_verified(self, ir_with_chunks):
        """When all source_refs verify, all have evidence_verified=True."""
        source_refs = [
            _make_source_ref("process documents automatically", "chunk-001"),
            _make_source_ref("upload files in PDF", "chunk-002"),
            _make_source_ref("server side", "chunk-003"),
        ]
        verifier = QueryEvidenceVerifier()
        result = verifier.verify(source_refs, ir_with_chunks)

        assert all(ref.evidence_verified is True for ref in result)
        # all_evidence_unverified would be False
        assert not all(ref.evidence_verified is False for ref in result)

    def test_all_unverified(self, ir_with_chunks):
        """When no source_refs verify, all have evidence_verified=False."""
        source_refs = [
            _make_source_ref(
                "completely fabricated text number one not in document xyz", "chunk-001"
            ),
            _make_source_ref(
                "another fabricated piece of evidence not found anywhere abc", "chunk-002"
            ),
        ]
        verifier = QueryEvidenceVerifier()
        result = verifier.verify(source_refs, ir_with_chunks)

        assert all(ref.evidence_verified is False for ref in result)
        # all_evidence_unverified would be True
        assert all(ref.evidence_verified is False for ref in result)

    def test_mixed_verification(self, ir_with_chunks):
        """When some verify and some don't, correctly flag each one."""
        source_refs = [
            _make_source_ref("process documents automatically", "chunk-001"),
            _make_source_ref(
                "fabricated text that does not appear in the document at all anywhere",
                "chunk-002",
            ),
            _make_source_ref("server side", "chunk-003"),
        ]
        verifier = QueryEvidenceVerifier()
        result = verifier.verify(source_refs, ir_with_chunks)

        assert result[0].evidence_verified is True
        assert result[1].evidence_verified is False
        assert result[2].evidence_verified is True
        # all_evidence_unverified would be False (not all unverified)
        assert not all(ref.evidence_verified is False for ref in result)

    def test_empty_source_refs_list(self, ir_with_chunks):
        """An empty source_refs list should return an empty list."""
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([], ir_with_chunks)

        assert result == []


# --- Whitespace Normalization Tests ---


class TestWhitespaceNormalization:
    """Evidence with whitespace variations should match after normalization."""

    def test_evidence_with_newlines_matches(self, ir_with_chunks):
        """Evidence containing newlines that normalizes to matching text."""
        source_ref = _make_source_ref(
            evidence="process\ndocuments\nautomatically",
            chunk_id="chunk-001",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is True

    def test_evidence_with_tabs_matches(self, ir_with_chunks):
        """Evidence containing tabs that normalizes to matching text."""
        source_ref = _make_source_ref(
            evidence="process\t\tdocuments\tautomatically",
            chunk_id="chunk-001",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is True

    def test_evidence_with_multiple_spaces_matches(self, ir_with_chunks):
        """Evidence with extra spaces that normalizes to matching text."""
        source_ref = _make_source_ref(
            evidence="process   documents   automatically",
            chunk_id="chunk-001",
        )
        verifier = QueryEvidenceVerifier()
        result = verifier.verify([source_ref], ir_with_chunks)

        assert result[0].evidence_verified is True


# --- Return Value Tests ---


class TestReturnValue:
    """Verify that the verifier returns the modified source_refs list."""

    def test_returns_same_list_reference(self, ir_with_chunks):
        """The verify() method returns the same list (modified in place)."""
        source_refs = [
            _make_source_ref("process documents automatically", "chunk-001"),
        ]
        verifier = QueryEvidenceVerifier()
        result = verifier.verify(source_refs, ir_with_chunks)

        assert result is source_refs

    def test_multiple_source_refs_processed(self, ir_with_chunks):
        """All source_refs in the list are processed."""
        source_refs = [
            _make_source_ref("process documents automatically", "chunk-001"),
            _make_source_ref("upload files in PDF", "chunk-002"),
            _make_source_ref("server side", "chunk-003"),
        ]
        verifier = QueryEvidenceVerifier()
        result = verifier.verify(source_refs, ir_with_chunks)

        assert len(result) == 3
        assert all(ref.evidence_verified is True for ref in result)
