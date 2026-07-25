"""Unit tests for the VerificationService.

Covers: exact match in referenced chunk, exact match in different chunk,
fuzzy match, no match, whitespace normalization, and verification rate calculation.
"""

from datetime import datetime, timezone

import pytest

from app.analysis.verification import (
    VerificationResult,
    VerificationService,
    _fuzzy_match,
    _normalize_whitespace,
)
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)
from app.models.knowledge_model import (
    ExtractionMetadata,
    KnowledgeElement,
    KnowledgeModel,
    SourceRef,
)


# --- Fixtures ---


@pytest.fixture
def sample_metadata() -> DocumentMetadata:
    return DocumentMetadata(
        original_filename="test.md",
        format=DocumentFormat.MARKDOWN,
        size_bytes=1024,
        language=DetectedLanguage.SPANISH,
        upload_timestamp=datetime(2026, 7, 24, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_extraction_metadata() -> ExtractionMetadata:
    return ExtractionMetadata(
        prompt_version="extraction-v1",
        model_id="gemini/gemini-2.5-flash-preview-05-20",
        temperature=0.1,
        element_count=1,
        relationship_count=0,
        verification_rate=0.0,
        extracted_at=datetime(2026, 7, 24, 15, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def ir_with_chunks(sample_metadata: DocumentMetadata) -> IntermediateRepresentation:
    """IR with three chunks containing different text."""
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


def _make_element(
    element_id: str, evidence: str, chunk_id: str = "chunk-001"
) -> KnowledgeElement:
    """Helper to create a KnowledgeElement with given evidence and chunk_id."""
    return KnowledgeElement(
        id=element_id,
        type="concepto",
        name="Test Element",
        content="Test content",
        source_ref=SourceRef(
            document_id="doc-001",
            chunk_id=chunk_id,
            evidence=evidence,
        ),
    )


def _make_knowledge_model(
    elements: list[KnowledgeElement], extraction_metadata: ExtractionMetadata
) -> KnowledgeModel:
    """Helper to build a KnowledgeModel from elements."""
    return KnowledgeModel(
        document_id="doc-001",
        document_type="generic",
        elements=elements,
        extraction_metadata=extraction_metadata,
    )


# --- Whitespace Normalization Tests ---


class TestNormalizeWhitespace:
    def test_collapses_multiple_spaces(self):
        assert _normalize_whitespace("hello   world") == "hello world"

    def test_collapses_tabs_and_newlines(self):
        assert _normalize_whitespace("hello\t\n\r  world") == "hello world"

    def test_strips_leading_trailing(self):
        assert _normalize_whitespace("  hello world  ") == "hello world"

    def test_preserves_single_spaces(self):
        assert _normalize_whitespace("hello world") == "hello world"

    def test_empty_string(self):
        assert _normalize_whitespace("") == ""

    def test_whitespace_only(self):
        assert _normalize_whitespace("   \t\n  ") == ""


# --- Fuzzy Match Tests ---


class TestFuzzyMatch:
    def test_identical_strings(self):
        assert _fuzzy_match("hello world", "hello world") is True

    def test_minor_difference(self):
        # One character different in a string — still above 80%
        assert _fuzzy_match("hello world", "hello warld") is True

    def test_no_match(self):
        assert _fuzzy_match("completely different", "nothing in common here at all xyz") is False

    def test_empty_evidence(self):
        assert _fuzzy_match("", "some text") is False

    def test_empty_text(self):
        assert _fuzzy_match("some evidence", "") is False

    def test_evidence_substring_with_typo(self):
        evidence = "process documents automatically"
        text = "The system shall procss documents automatically and efficiently."
        # "procss" vs "process" — close enough for fuzzy match
        assert _fuzzy_match(evidence, text, threshold=0.8) is True


# --- VerificationService Tests ---


class TestVerificationServiceExactMatchInReferencedChunk:
    """Req 7.2: Exact match found in the referenced chunk."""

    def test_exact_substring_in_referenced_chunk(
        self, ir_with_chunks, sample_extraction_metadata
    ):
        element = _make_element(
            "elem-001",
            evidence="process documents automatically",
            chunk_id="chunk-001",
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 1
        assert result.total_count == 1
        assert result.verification_rate == 1.0
        assert result.unverified_element_ids == []
        assert km.elements[0].verified is True

    def test_full_chunk_text_as_evidence(self, ir_with_chunks, sample_extraction_metadata):
        element = _make_element(
            "elem-001",
            evidence="The system shall process documents automatically and efficiently.",
            chunk_id="chunk-001",
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 1
        assert km.elements[0].verified is True


class TestVerificationServiceExactMatchInDifferentChunk:
    """Req 7.2: Exact match found in a different chunk than referenced."""

    def test_evidence_in_different_chunk(self, ir_with_chunks, sample_extraction_metadata):
        # Evidence references chunk-001 but the text exists in chunk-002
        element = _make_element(
            "elem-001",
            evidence="upload files in PDF",
            chunk_id="chunk-001",
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 1
        assert result.verification_rate == 1.0
        assert km.elements[0].verified is True

    def test_evidence_in_nonexistent_referenced_chunk_found_elsewhere(
        self, ir_with_chunks, sample_extraction_metadata
    ):
        # Referenced chunk doesn't exist, but evidence found in another chunk
        element = _make_element(
            "elem-001",
            evidence="server side with no client computation",
            chunk_id="chunk-999",  # doesn't exist
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 1
        assert km.elements[0].verified is True


class TestVerificationServiceFuzzyMatch:
    """Req 7.2: Fuzzy match (80% threshold) when exact match fails."""

    def test_fuzzy_match_with_minor_whitespace_variation(
        self, ir_with_chunks, sample_extraction_metadata
    ):
        # Evidence with slightly different formatting but semantically same
        element = _make_element(
            "elem-001",
            evidence="process documents  automatically",  # extra space normalized
            chunk_id="chunk-001",
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        # After whitespace normalization, this becomes an exact match
        assert result.verified_count == 1
        assert km.elements[0].verified is True

    def test_fuzzy_match_with_minor_text_difference(
        self, sample_metadata, sample_extraction_metadata
    ):
        # Create an IR where evidence is close but not exact
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
        element = _make_element(
            "elem-001",
            evidence="The system shall process documents automatically and efficiently.",
            chunk_id="chunk-001",
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir)

        assert result.verified_count == 1
        assert km.elements[0].verified is True


class TestVerificationServiceNoMatch:
    """Req 7.3: Element not found anywhere — marked as not verified."""

    def test_no_match_anywhere(self, ir_with_chunks, sample_extraction_metadata):
        element = _make_element(
            "elem-001",
            evidence="This text does not exist anywhere in the document at all whatsoever.",
            chunk_id="chunk-001",
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 0
        assert result.total_count == 1
        assert result.verification_rate == 0.0
        assert result.unverified_element_ids == ["elem-001"]
        assert km.elements[0].verified is False

    def test_empty_evidence_not_verified(self, ir_with_chunks, sample_extraction_metadata):
        element = _make_element(
            "elem-001",
            evidence="   ",  # whitespace-only evidence normalizes to empty
            chunk_id="chunk-001",
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 0
        assert km.elements[0].verified is False
        assert "elem-001" in result.unverified_element_ids


class TestVerificationServiceWhitespaceNormalization:
    """Whitespace normalization before matching."""

    def test_evidence_with_newlines_matches(self, ir_with_chunks, sample_extraction_metadata):
        # Evidence has newlines but normalized matches chunk text
        element = _make_element(
            "elem-001",
            evidence="process\ndocuments\nautomatically",
            chunk_id="chunk-001",
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 1
        assert km.elements[0].verified is True

    def test_evidence_with_tabs_matches(self, ir_with_chunks, sample_extraction_metadata):
        element = _make_element(
            "elem-001",
            evidence="process\t\tdocuments\tautomatically",
            chunk_id="chunk-001",
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 1
        assert km.elements[0].verified is True

    def test_chunk_text_with_extra_whitespace(
        self, sample_metadata, sample_extraction_metadata
    ):
        """When the chunk text itself has irregular whitespace."""
        ir = IntermediateRepresentation(
            document_id="doc-001",
            metadata=sample_metadata,
            chunks=[
                ContentChunkModel(
                    chunk_id="chunk-001",
                    text="The  system   shall  process   documents  automatically.",
                    structural_context={"section": "# Intro"},
                    order=0,
                ),
            ],
        )
        element = _make_element(
            "elem-001",
            evidence="system shall process documents",
            chunk_id="chunk-001",
        )
        km = _make_knowledge_model([element], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir)

        assert result.verified_count == 1
        assert km.elements[0].verified is True


class TestVerificationServiceRate:
    """Req 7.4: Verification rate calculation."""

    def test_all_verified(self, ir_with_chunks, sample_extraction_metadata):
        elements = [
            _make_element("elem-001", "process documents automatically", "chunk-001"),
            _make_element("elem-002", "upload files in PDF", "chunk-002"),
            _make_element("elem-003", "server side", "chunk-003"),
        ]
        km = _make_knowledge_model(elements, sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 3
        assert result.total_count == 3
        assert result.verification_rate == 1.0
        assert result.unverified_element_ids == []

    def test_partial_verification(self, ir_with_chunks, sample_extraction_metadata):
        elements = [
            _make_element("elem-001", "process documents automatically", "chunk-001"),
            _make_element("elem-002", "this text does not exist anywhere at all in document", "chunk-002"),
            _make_element("elem-003", "server side", "chunk-003"),
        ]
        km = _make_knowledge_model(elements, sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 2
        assert result.total_count == 3
        assert abs(result.verification_rate - 2 / 3) < 0.001
        assert result.unverified_element_ids == ["elem-002"]

    def test_no_elements_gives_zero_rate(self, ir_with_chunks, sample_extraction_metadata):
        km = _make_knowledge_model([], sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 0
        assert result.total_count == 0
        assert result.verification_rate == 0.0
        assert result.unverified_element_ids == []

    def test_none_verified(self, ir_with_chunks, sample_extraction_metadata):
        elements = [
            _make_element("elem-001", "completely unrelated gibberish xyz abc 123 not in document", "chunk-001"),
            _make_element("elem-002", "another fake evidence string not present anywhere here", "chunk-002"),
        ]
        km = _make_knowledge_model(elements, sample_extraction_metadata)

        service = VerificationService()
        result = service.verify(km, ir_with_chunks)

        assert result.verified_count == 0
        assert result.total_count == 2
        assert result.verification_rate == 0.0
        assert set(result.unverified_element_ids) == {"elem-001", "elem-002"}


class TestVerificationResultDataclass:
    """VerificationResult structure tests."""

    def test_fields_present(self):
        result = VerificationResult(
            verified_count=5,
            total_count=10,
            verification_rate=0.5,
            unverified_element_ids=["e1", "e2", "e3", "e4", "e5"],
        )
        assert result.verified_count == 5
        assert result.total_count == 10
        assert result.verification_rate == 0.5
        assert len(result.unverified_element_ids) == 5
