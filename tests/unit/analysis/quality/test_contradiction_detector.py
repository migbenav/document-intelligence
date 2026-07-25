"""Unit tests for the ContradictionDetector module.

Tests cover:
- Explicit relationships detected as structural contradictions
- LLM findings parsed correctly
- LLM failure returns only structural contradictions
- Empty KM returns empty list
- Unverified elements flagged correctly

Requirements validated: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.2, 8.4, 8.5
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMClient, LLMResponse, LLMTransientError
from app.analysis.quality.contradiction_detector import ContradictionDetector
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
    Relation,
    SourceRef,
)


# --- Fixtures ---


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLMClient."""
    client = MagicMock(spec=LLMClient)
    client.call = AsyncMock()
    return client


@pytest.fixture
def sample_ir() -> IntermediateRepresentation:
    """Create a sample IntermediateRepresentation."""
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=1024,
            language=DetectedLanguage.ENGLISH,
            upload_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="chunk-001",
                text="All API endpoints must respond within 200ms",
                structural_context={"section": "## Performance"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="chunk-002",
                text="Response time SLA: 500ms for standard endpoints",
                structural_context={"section": "## SLA"},
                order=1,
            ),
        ],
    )


@pytest.fixture
def sample_extraction_metadata() -> ExtractionMetadata:
    """Create sample extraction metadata."""
    return ExtractionMetadata(
        prompt_version="extraction-v1",
        model_id="gemini/gemini-2.5-flash",
        temperature=0.1,
        element_count=2,
        relationship_count=1,
        verification_rate=0.5,
        extracted_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def km_with_contradicts(sample_extraction_metadata: ExtractionMetadata) -> KnowledgeModel:
    """Create a KM with an explicit contradicts relationship."""
    return KnowledgeModel(
        document_id="doc-001",
        document_type="prd",
        elements=[
            KnowledgeElement(
                id="elem-001",
                type="restriccion",
                name="Response Time 200ms",
                content="All API endpoints must respond within 200ms",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-001",
                    section="## Performance",
                    evidence="All API endpoints must respond within 200ms",
                ),
                relations=[
                    Relation(
                        target_id="elem-002",
                        type="contradicts",
                        description="Conflicting response time requirements: 200ms vs 500ms",
                    )
                ],
                verified=True,
            ),
            KnowledgeElement(
                id="elem-002",
                type="restriccion",
                name="Response Time SLA 500ms",
                content="Response time SLA: 500ms for standard endpoints",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-002",
                    section="## SLA",
                    evidence="Response time SLA: 500ms for standard endpoints",
                ),
                relations=[],
                verified=True,
            ),
        ],
        extraction_metadata=sample_extraction_metadata,
    )


@pytest.fixture
def km_with_unverified_elements(sample_extraction_metadata: ExtractionMetadata) -> KnowledgeModel:
    """Create a KM with an explicit contradicts relationship involving unverified elements."""
    return KnowledgeModel(
        document_id="doc-001",
        document_type="prd",
        elements=[
            KnowledgeElement(
                id="elem-001",
                type="restriccion",
                name="Response Time 200ms",
                content="All API endpoints must respond within 200ms",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-001",
                    section="## Performance",
                    evidence="All API endpoints must respond within 200ms",
                ),
                relations=[
                    Relation(
                        target_id="elem-002",
                        type="contradicts",
                        description="Conflicting response time",
                    )
                ],
                verified=True,
            ),
            KnowledgeElement(
                id="elem-002",
                type="restriccion",
                name="Response Time SLA 500ms",
                content="Response time SLA: 500ms",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-002",
                    section="## SLA",
                    evidence="Response time SLA: 500ms",
                ),
                relations=[],
                verified=False,  # This element is unverified
            ),
        ],
        extraction_metadata=sample_extraction_metadata,
    )


@pytest.fixture
def km_empty(sample_extraction_metadata: ExtractionMetadata) -> KnowledgeModel:
    """Create an empty KM."""
    return KnowledgeModel(
        document_id="doc-001",
        document_type="generic",
        elements=[],
        extraction_metadata=sample_extraction_metadata,
    )


@pytest.fixture
def km_no_contradictions(sample_extraction_metadata: ExtractionMetadata) -> KnowledgeModel:
    """Create a KM with elements but no contradicts relationships."""
    return KnowledgeModel(
        document_id="doc-001",
        document_type="prd",
        elements=[
            KnowledgeElement(
                id="elem-001",
                type="proposito",
                name="Document Purpose",
                content="This document defines the API design.",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-001",
                    section="## Purpose",
                    evidence="This document defines the API design.",
                ),
                relations=[
                    Relation(
                        target_id="elem-002",
                        type="depends_on",
                        description="Purpose depends on actors",
                    )
                ],
                verified=True,
            ),
            KnowledgeElement(
                id="elem-002",
                type="actor",
                name="Developer",
                content="The primary user is a developer.",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-002",
                    section="## Users",
                    evidence="The primary user is a developer.",
                ),
                relations=[],
                verified=True,
            ),
        ],
        extraction_metadata=sample_extraction_metadata,
    )


def _make_llm_response(findings: list[dict]) -> LLMResponse:
    """Helper to create an LLMResponse with JSON findings content."""
    content = json.dumps({"findings": findings})
    return LLMResponse(content=content, model_id="gemini/gemini-2.5-flash")


# --- Test: Explicit relationships detected ---


class TestExplicitRelationshipsDetected:
    """Test that explicit contradicts relationships are detected as structural contradictions."""

    @pytest.mark.asyncio
    async def test_explicit_contradicts_produces_finding(
        self,
        mock_llm_client: MagicMock,
        km_with_contradicts: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Explicit contradicts relationship produces a contradiction finding."""
        # LLM returns no additional findings
        mock_llm_client.call.return_value = _make_llm_response([])

        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km_with_contradicts, sample_ir)

        # Should have at least the structural contradiction
        structural = [r for r in results if r.from_explicit_relationship]
        assert len(structural) == 1

        finding = structural[0]
        assert finding.type == "contradiction"
        assert finding.from_explicit_relationship is True
        assert "elem-001" in finding.affected_element_ids
        assert "elem-002" in finding.affected_element_ids
        assert len(finding.source_refs) == 2
        assert finding.severity in ("high", "medium", "low")
        assert len(finding.description) <= 500

    @pytest.mark.asyncio
    async def test_structural_contradiction_has_correct_source_refs(
        self,
        mock_llm_client: MagicMock,
        km_with_contradicts: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Source refs come from the two contradicting elements."""
        mock_llm_client.call.return_value = _make_llm_response([])

        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km_with_contradicts, sample_ir)

        structural = [r for r in results if r.from_explicit_relationship]
        finding = structural[0]

        chunk_ids = [ref.chunk_id for ref in finding.source_refs]
        assert "chunk-001" in chunk_ids
        assert "chunk-002" in chunk_ids

    @pytest.mark.asyncio
    async def test_no_duplicates_for_bidirectional_relationship(
        self,
        mock_llm_client: MagicMock,
        sample_ir: IntermediateRepresentation,
        sample_extraction_metadata: ExtractionMetadata,
    ):
        """A contradicts relationship from A->B and B->A should produce only one finding."""
        km = KnowledgeModel(
            document_id="doc-001",
            document_type="prd",
            elements=[
                KnowledgeElement(
                    id="elem-001",
                    type="restriccion",
                    name="Elem A",
                    content="Content A",
                    source_ref=SourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-001",
                        evidence="Content A",
                    ),
                    relations=[
                        Relation(target_id="elem-002", type="contradicts", description="A vs B")
                    ],
                    verified=True,
                ),
                KnowledgeElement(
                    id="elem-002",
                    type="restriccion",
                    name="Elem B",
                    content="Content B",
                    source_ref=SourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-002",
                        evidence="Content B",
                    ),
                    relations=[
                        Relation(target_id="elem-001", type="contradicts", description="B vs A")
                    ],
                    verified=True,
                ),
            ],
            extraction_metadata=sample_extraction_metadata,
        )

        mock_llm_client.call.return_value = _make_llm_response([])
        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km, sample_ir)

        structural = [r for r in results if r.from_explicit_relationship]
        assert len(structural) == 1


# --- Test: LLM findings parsed ---


class TestLLMFindingsParsed:
    """Test that LLM-detected contradictions are parsed correctly."""

    @pytest.mark.asyncio
    async def test_llm_findings_converted_to_inconsistency(
        self,
        mock_llm_client: MagicMock,
        km_no_contradictions: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """LLM findings are parsed and converted to Inconsistency models."""
        llm_findings = [
            {
                "type": "contradiction",
                "description": "Element A says X, element B says Y.",
                "severity": "medium",
                "affected_element_ids": ["elem-001", "elem-002"],
                "source_refs": [
                    {
                        "chunk_id": "chunk-001",
                        "page": None,
                        "section": "## Purpose",
                        "evidence": "This document defines the API design.",
                    },
                    {
                        "chunk_id": "chunk-002",
                        "page": None,
                        "section": "## Users",
                        "evidence": "The primary user is a developer.",
                    },
                ],
            }
        ]
        mock_llm_client.call.return_value = _make_llm_response(llm_findings)

        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km_no_contradictions, sample_ir)

        llm_results = [r for r in results if not r.from_explicit_relationship]
        assert len(llm_results) == 1

        finding = llm_results[0]
        assert finding.type == "contradiction"
        assert finding.severity == "medium"
        assert finding.description == "Element A says X, element B says Y."
        assert len(finding.affected_element_ids) == 2
        assert len(finding.source_refs) == 2
        assert finding.from_explicit_relationship is False

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_parameters(
        self,
        mock_llm_client: MagicMock,
        km_no_contradictions: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """LLM is called with primary model tier and temperature 0.1."""
        mock_llm_client.call.return_value = _make_llm_response([])

        detector = ContradictionDetector(mock_llm_client)
        await detector.detect(km_no_contradictions, sample_ir)

        mock_llm_client.call.assert_called_once()
        call_kwargs = mock_llm_client.call.call_args
        assert call_kwargs.kwargs["model_tier"] == "primary"
        assert call_kwargs.kwargs["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_llm_parse_failure_raises_value_error(
        self,
        mock_llm_client: MagicMock,
        km_no_contradictions: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Invalid LLM response raises ValueError (Req 10.2, 10.3)."""
        mock_llm_client.call.return_value = LLMResponse(
            content="not valid json at all",
            model_id="gemini/gemini-2.5-flash",
        )

        detector = ContradictionDetector(mock_llm_client)
        with pytest.raises(ValueError, match="Pydantic validation"):
            await detector.detect(km_no_contradictions, sample_ir)


# --- Test: LLM failure returns only structural ---


class TestLLMFailureReturnsStructural:
    """Test that LLM failure results in only structural contradictions being returned."""

    @pytest.mark.asyncio
    async def test_transient_error_returns_structural_only(
        self,
        mock_llm_client: MagicMock,
        km_with_contradicts: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """LLMTransientError results in only structural contradictions (Req 1.6)."""
        mock_llm_client.call.side_effect = LLMTransientError("Service unavailable")

        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km_with_contradicts, sample_ir)

        assert len(results) == 1
        assert all(r.from_explicit_relationship for r in results)

    @pytest.mark.asyncio
    async def test_generic_exception_returns_structural_only(
        self,
        mock_llm_client: MagicMock,
        km_with_contradicts: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Any exception during LLM call returns only structural contradictions."""
        mock_llm_client.call.side_effect = RuntimeError("Unexpected failure")

        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km_with_contradicts, sample_ir)

        assert len(results) == 1
        assert all(r.from_explicit_relationship for r in results)

    @pytest.mark.asyncio
    async def test_llm_failure_with_no_structural_returns_empty(
        self,
        mock_llm_client: MagicMock,
        km_no_contradictions: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """LLM failure with no structural contradictions returns empty list."""
        mock_llm_client.call.side_effect = LLMTransientError("Timeout")

        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km_no_contradictions, sample_ir)

        assert results == []


# --- Test: Empty KM returns empty ---


class TestEmptyKMReturnsEmpty:
    """Test that an empty Knowledge Model returns an empty findings list."""

    @pytest.mark.asyncio
    async def test_empty_km_returns_empty_list(
        self,
        mock_llm_client: MagicMock,
        km_empty: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Empty KM produces no findings and doesn't call LLM."""
        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km_empty, sample_ir)

        assert results == []
        # LLM should not be called for empty KM
        mock_llm_client.call.assert_not_called()


# --- Test: Unverified elements flagged ---


class TestUnverifiedElementsFlagged:
    """Test that involves_unverified_elements is set correctly."""

    @pytest.mark.asyncio
    async def test_structural_finding_flags_unverified(
        self,
        mock_llm_client: MagicMock,
        km_with_unverified_elements: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Structural contradiction involving unverified element gets flagged (Req 8.4)."""
        mock_llm_client.call.return_value = _make_llm_response([])

        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km_with_unverified_elements, sample_ir)

        structural = [r for r in results if r.from_explicit_relationship]
        assert len(structural) == 1
        assert structural[0].involves_unverified_elements is True

    @pytest.mark.asyncio
    async def test_verified_elements_not_flagged(
        self,
        mock_llm_client: MagicMock,
        km_with_contradicts: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Structural contradiction with all verified elements is not flagged."""
        mock_llm_client.call.return_value = _make_llm_response([])

        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km_with_contradicts, sample_ir)

        structural = [r for r in results if r.from_explicit_relationship]
        assert len(structural) == 1
        assert structural[0].involves_unverified_elements is False

    @pytest.mark.asyncio
    async def test_llm_finding_flags_unverified_element(
        self,
        mock_llm_client: MagicMock,
        km_with_unverified_elements: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """LLM finding involving unverified element gets flagged (Req 8.4)."""
        llm_findings = [
            {
                "type": "contradiction",
                "description": "Found a contradiction between elements.",
                "severity": "high",
                "affected_element_ids": ["elem-002"],  # elem-002 is unverified
                "source_refs": [
                    {
                        "chunk_id": "chunk-002",
                        "page": None,
                        "section": "## SLA",
                        "evidence": "Response time SLA: 500ms",
                    },
                    {
                        "chunk_id": "chunk-001",
                        "page": None,
                        "section": "## Performance",
                        "evidence": "Must respond within 200ms",
                    },
                ],
            }
        ]
        mock_llm_client.call.return_value = _make_llm_response(llm_findings)

        detector = ContradictionDetector(mock_llm_client)
        results = await detector.detect(km_with_unverified_elements, sample_ir)

        llm_results = [r for r in results if not r.from_explicit_relationship]
        assert len(llm_results) == 1
        assert llm_results[0].involves_unverified_elements is True
