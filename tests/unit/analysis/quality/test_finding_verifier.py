"""Unit tests for the FindingVerifier.

Covers: exact match verified, fuzzy match verified, no match not verified,
all_evidence_unverified flag set, empty source_refs handled.

Validates: Requirements 7.1, 7.2, 7.3, 7.5, 7.6, 7.7
"""

import pytest

from app.analysis.quality.finding_verifier import FindingVerifier
from app.models.document import (
    ContentChunkModel,
    DetectedLanguage,
    DocumentFormat,
    DocumentMetadata,
    IntermediateRepresentation,
)
from app.models.quality_analysis import FindingSourceRef, Inconsistency, Suggestion


# --- Fixtures ---


@pytest.fixture
def verifier() -> FindingVerifier:
    return FindingVerifier()


@pytest.fixture
def sample_ir() -> IntermediateRepresentation:
    """IR with multiple chunks for testing verification scenarios."""
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=1024,
            language=DetectedLanguage.ENGLISH,
            upload_timestamp="2026-01-01T00:00:00Z",
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="chunk-001",
                text="All API endpoints must respond within 200ms under normal load conditions.",
                structural_context={"section": "## Performance"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="chunk-002",
                text="The system supports up to 1000 concurrent users with graceful degradation.",
                structural_context={"section": "## Scalability"},
                order=1,
            ),
            ContentChunkModel(
                chunk_id="chunk-003",
                text="Authentication uses OAuth 2.0 with JWT tokens for session management.",
                structural_context={"section": "## Security"},
                order=2,
            ),
        ],
    )


def _make_source_ref(
    chunk_id: str = "chunk-001",
    evidence: str = "All API endpoints must respond within 200ms",
) -> FindingSourceRef:
    """Helper to create a FindingSourceRef."""
    return FindingSourceRef(
        document_id="doc-001",
        chunk_id=chunk_id,
        evidence=evidence,
    )


def _make_inconsistency(
    source_refs: list[FindingSourceRef],
    finding_id: str = "inc-001",
) -> Inconsistency:
    """Helper to create an Inconsistency."""
    return Inconsistency(
        id=finding_id,
        type="contradiction",
        description="Test inconsistency",
        severity="high",
        affected_element_ids=["elem-001", "elem-002"],
        source_refs=source_refs,
    )


def _make_suggestion(
    source_refs: list[FindingSourceRef],
    finding_id: str = "sug-001",
) -> Suggestion:
    """Helper to create a Suggestion."""
    return Suggestion(
        id=finding_id,
        description="Test suggestion",
        category="consistency",
        priority="medium",
        source_refs=source_refs,
    )


# --- Exact Match Tests ---


class TestExactMatchVerified:
    """Test that exact substring matches in the referenced chunk are verified."""

    def test_exact_match_in_referenced_chunk(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Evidence that exactly matches text in the referenced chunk is verified."""
        ref = _make_source_ref(
            chunk_id="chunk-001",
            evidence="All API endpoints must respond within 200ms",
        )
        inc = _make_inconsistency([ref])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].source_refs[0].evidence_verified is True
        assert verified_incs[0].all_evidence_unverified is False

    def test_exact_match_in_different_chunk(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Evidence that matches text in a chunk OTHER than the referenced one is verified."""
        # Reference chunk-001 but evidence is from chunk-002
        ref = _make_source_ref(
            chunk_id="chunk-001",
            evidence="up to 1000 concurrent users",
        )
        inc = _make_inconsistency([ref])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].source_refs[0].evidence_verified is True

    def test_exact_match_with_whitespace_normalization(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Evidence with extra whitespace is normalized before matching."""
        ref = _make_source_ref(
            chunk_id="chunk-001",
            evidence="All  API   endpoints  must respond   within 200ms",
        )
        inc = _make_inconsistency([ref])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].source_refs[0].evidence_verified is True


# --- Fuzzy Match Tests ---


class TestFuzzyMatchVerified:
    """Test that fuzzy matches (80% threshold) are verified."""

    def test_fuzzy_match_minor_differences(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Evidence with minor character differences is verified via fuzzy match."""
        # Slightly altered version — should still match at 80% threshold
        ref = _make_source_ref(
            chunk_id="chunk-003",
            evidence="Authentication uses OAuth 2.0 with JWT tokens for session mgmt.",
        )
        inc = _make_inconsistency([ref])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].source_refs[0].evidence_verified is True

    def test_fuzzy_match_truncated_evidence(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Evidence that is a slightly truncated/modified version matches fuzzy."""
        # Truncated and slightly changed — should still fuzzy match
        ref = _make_source_ref(
            chunk_id="chunk-002",
            evidence="system supports up to 1000 concurrent users with graceful",
        )
        inc = _make_inconsistency([ref])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        # This is an exact substring match (the evidence is contained in chunk-002)
        assert verified_incs[0].source_refs[0].evidence_verified is True


# --- No Match Tests ---


class TestNoMatchNotVerified:
    """Test that evidence with no match is not verified."""

    def test_completely_different_text(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Evidence not found in any chunk is not verified."""
        ref = _make_source_ref(
            chunk_id="chunk-001",
            evidence="The database should support horizontal sharding across regions",
        )
        inc = _make_inconsistency([ref])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].source_refs[0].evidence_verified is False

    def test_nonexistent_referenced_chunk(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Evidence referencing a non-existent chunk_id falls back to other chunks."""
        ref = _make_source_ref(
            chunk_id="chunk-999",
            evidence="This text does not exist anywhere in the document",
        )
        inc = _make_inconsistency([ref])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].source_refs[0].evidence_verified is False

    def test_empty_evidence_not_verified(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Empty evidence text cannot be verified."""
        ref = FindingSourceRef(
            document_id="doc-001",
            chunk_id="chunk-001",
            evidence="   ",  # whitespace-only normalizes to empty
        )
        inc = _make_inconsistency([ref])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].source_refs[0].evidence_verified is False


# --- all_evidence_unverified Flag Tests ---


class TestAllEvidenceUnverifiedFlag:
    """Test the all_evidence_unverified finding-level flag (Req 7.7)."""

    def test_all_refs_unverified_sets_flag(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """When ALL source_refs are unverified, all_evidence_unverified = True."""
        ref1 = _make_source_ref(
            chunk_id="chunk-001",
            evidence="Completely fabricated text that does not exist",
        )
        ref2 = _make_source_ref(
            chunk_id="chunk-002",
            evidence="Another hallucinated evidence span nowhere in the document",
        )
        inc = _make_inconsistency([ref1, ref2])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].all_evidence_unverified is True
        assert verified_incs[0].source_refs[0].evidence_verified is False
        assert verified_incs[0].source_refs[1].evidence_verified is False

    def test_some_refs_verified_no_flag(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """When at least one source_ref is verified, all_evidence_unverified = False."""
        ref_verified = _make_source_ref(
            chunk_id="chunk-001",
            evidence="All API endpoints must respond within 200ms",
        )
        ref_unverified = _make_source_ref(
            chunk_id="chunk-002",
            evidence="Text that does not exist in the document at all",
        )
        inc = _make_inconsistency([ref_verified, ref_unverified])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].all_evidence_unverified is False
        assert verified_incs[0].source_refs[0].evidence_verified is True
        assert verified_incs[0].source_refs[1].evidence_verified is False

    def test_all_refs_verified_no_flag(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """When all source_refs are verified, all_evidence_unverified = False."""
        ref1 = _make_source_ref(
            chunk_id="chunk-001",
            evidence="All API endpoints must respond within 200ms",
        )
        ref2 = _make_source_ref(
            chunk_id="chunk-002",
            evidence="up to 1000 concurrent users",
        )
        inc = _make_inconsistency([ref1, ref2])

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].all_evidence_unverified is False
        assert verified_incs[0].source_refs[0].evidence_verified is True
        assert verified_incs[0].source_refs[1].evidence_verified is True

    def test_suggestion_all_refs_unverified(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """all_evidence_unverified flag works for Suggestion findings too (Req 7.6)."""
        ref = _make_source_ref(
            chunk_id="chunk-001",
            evidence="Invented suggestion context not in the document",
        )
        sug = _make_suggestion([ref])

        _, verified_sugs = verifier.verify_all([], [sug], sample_ir)

        assert verified_sugs[0].all_evidence_unverified is True
        assert verified_sugs[0].source_refs[0].evidence_verified is False


# --- Empty Source Refs Tests ---


class TestEmptySourceRefs:
    """Test handling of findings with empty source_refs lists."""

    def test_inconsistency_empty_source_refs(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Inconsistency with empty source_refs: all_evidence_unverified = False."""
        inc = Inconsistency(
            id="inc-empty",
            type="ambiguity",
            description="Ambiguous statement",
            severity="low",
            affected_element_ids=["elem-001"],
            source_refs=[],
        )

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        assert verified_incs[0].source_refs == []
        assert verified_incs[0].all_evidence_unverified is False

    def test_suggestion_empty_source_refs(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Suggestion with empty source_refs: all_evidence_unverified = False."""
        sug = Suggestion(
            id="sug-empty",
            description="General improvement",
            category="structure",
            priority="low",
            source_refs=[],
        )

        _, verified_sugs = verifier.verify_all([], [sug], sample_ir)

        assert verified_sugs[0].source_refs == []
        assert verified_sugs[0].all_evidence_unverified is False


# --- Suggestion Verification Tests ---


class TestSuggestionVerification:
    """Test that suggestions are verified with the same algorithm (Req 7.6)."""

    def test_suggestion_exact_match(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Suggestion source_ref with exact match is verified."""
        ref = _make_source_ref(
            chunk_id="chunk-003",
            evidence="OAuth 2.0 with JWT tokens",
        )
        sug = _make_suggestion([ref])

        _, verified_sugs = verifier.verify_all([], [sug], sample_ir)

        assert verified_sugs[0].source_refs[0].evidence_verified is True
        assert verified_sugs[0].all_evidence_unverified is False

    def test_suggestion_no_match(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Suggestion source_ref with no match is not verified."""
        ref = _make_source_ref(
            chunk_id="chunk-001",
            evidence="Text that doesn't appear in any chunk at all",
        )
        sug = _make_suggestion([ref])

        _, verified_sugs = verifier.verify_all([], [sug], sample_ir)

        assert verified_sugs[0].source_refs[0].evidence_verified is False
        assert verified_sugs[0].all_evidence_unverified is True


# --- Multiple Findings Tests ---


class TestMultipleFindings:
    """Test verification across multiple findings simultaneously."""

    def test_multiple_inconsistencies(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Multiple inconsistencies are each verified independently."""
        inc1 = _make_inconsistency(
            [_make_source_ref(evidence="All API endpoints must respond within 200ms")],
            finding_id="inc-001",
        )
        inc2 = _make_inconsistency(
            [_make_source_ref(evidence="Text not in document at all")],
            finding_id="inc-002",
        )

        verified_incs, _ = verifier.verify_all([inc1, inc2], [], sample_ir)

        assert verified_incs[0].source_refs[0].evidence_verified is True
        assert verified_incs[0].all_evidence_unverified is False
        assert verified_incs[1].source_refs[0].evidence_verified is False
        assert verified_incs[1].all_evidence_unverified is True

    def test_empty_inputs(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Empty lists of findings return empty lists."""
        verified_incs, verified_sugs = verifier.verify_all([], [], sample_ir)

        assert verified_incs == []
        assert verified_sugs == []

    def test_does_not_mutate_originals(
        self, verifier: FindingVerifier, sample_ir: IntermediateRepresentation
    ):
        """Verify that the original findings are not mutated."""
        ref = _make_source_ref(
            chunk_id="chunk-001",
            evidence="All API endpoints must respond within 200ms",
        )
        inc = _make_inconsistency([ref])

        # Original should have evidence_verified=False (default)
        assert inc.source_refs[0].evidence_verified is False

        verified_incs, _ = verifier.verify_all([inc], [], sample_ir)

        # Verified copy should have True
        assert verified_incs[0].source_refs[0].evidence_verified is True
        # Original should remain unchanged
        assert inc.source_refs[0].evidence_verified is False
