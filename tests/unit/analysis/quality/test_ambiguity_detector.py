"""Unit tests for the AmbiguityDetector.

Covers: successful detection, parse failure raises error, LLM failure propagates,
empty results valid.

Requirements validated: 2.1, 2.2, 2.3, 2.4, 2.5, 8.2, 8.4
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.analysis.llm_client import LLMResponse, LLMTransientError
from app.analysis.quality.ambiguity_detector import (
    AmbiguityDetectionError,
    AmbiguityDetector,
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
def mock_llm_client() -> MagicMock:
    """Create a mock LLMClient with an async call method."""
    client = MagicMock()
    client.call = AsyncMock()
    return client


@pytest.fixture
def sample_ir() -> IntermediateRepresentation:
    """Create a sample IntermediateRepresentation for testing."""
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=DocumentMetadata(
            original_filename="test.md",
            format=DocumentFormat.MARKDOWN,
            size_bytes=1024,
            language=DetectedLanguage.ENGLISH,
            upload_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        chunks=[
            ContentChunkModel(
                chunk_id="chunk-001",
                text="The system should respond quickly to all requests.",
                structural_context={"section": "## Performance"},
                order=0,
            ),
            ContentChunkModel(
                chunk_id="chunk-002",
                text="Under certain conditions, the service will retry the operation.",
                structural_context={"section": "## Reliability", "page": 2},
                order=1,
            ),
        ],
    )


@pytest.fixture
def sample_knowledge_model() -> KnowledgeModel:
    """Create a sample KnowledgeModel for testing."""
    return KnowledgeModel(
        document_id="doc-001",
        document_type="technical_spec",
        elements=[
            KnowledgeElement(
                id="elem-001",
                type="restriccion",
                name="Response Time",
                content="The system should respond quickly to all requests.",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-001",
                    section="## Performance",
                    evidence="The system should respond quickly to all requests.",
                ),
                verified=True,
            ),
            KnowledgeElement(
                id="elem-002",
                type="proceso",
                name="Retry Logic",
                content="Under certain conditions, the service will retry the operation.",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-002",
                    section="## Reliability",
                    evidence="Under certain conditions, the service will retry the operation.",
                ),
                verified=False,
            ),
        ],
        extraction_metadata=ExtractionMetadata(
            prompt_version="extraction-v1",
            model_id="gemini/gemini-2.5-flash-preview-05-20",
            temperature=0.1,
            element_count=2,
            relationship_count=0,
            verification_rate=0.5,
            extracted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )


def _make_llm_response(ambiguities: list[dict]) -> LLMResponse:
    """Helper to construct an LLMResponse with ambiguity findings."""
    content = json.dumps({"ambiguities": ambiguities})
    return LLMResponse(content=content, model_id="gemini/gemini-2.5-flash-preview-05-20")


# --- Test Cases ---


class TestAmbiguityDetectorSuccessfulDetection:
    """Tests for successful ambiguity detection (Req 2.1, 2.2, 2.3, 8.4)."""

    @pytest.mark.asyncio
    async def test_detects_ambiguities_from_llm_response(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Successful LLM call produces Inconsistency findings with type=ambiguity."""
        mock_llm_client.call.return_value = _make_llm_response(
            [
                {
                    "id": "amb-001",
                    "category": "vague_quantifier",
                    "description": (
                        "The term 'quickly' is ambiguous. Interpretation 1: "
                        "response within 100ms. Interpretation 2: response within 1s."
                    ),
                    "severity": "medium",
                    "affected_element_ids": ["elem-001"],
                    "source_ref": {
                        "chunk_id": "chunk-001",
                        "section": "## Performance",
                        "evidence": "The system should respond quickly to all requests.",
                    },
                },
                {
                    "id": "amb-002",
                    "category": "unspecified_condition",
                    "description": (
                        "The conditions for retry are unspecified. Interpretation 1: "
                        "network errors. Interpretation 2: all transient errors."
                    ),
                    "severity": "high",
                    "affected_element_ids": ["elem-002"],
                    "source_ref": {
                        "chunk_id": "chunk-002",
                        "page": 2,
                        "section": "## Reliability",
                        "evidence": "Under certain conditions, the service will retry the operation.",
                    },
                },
            ]
        )

        detector = AmbiguityDetector(mock_llm_client)
        findings = await detector.detect(sample_knowledge_model, sample_ir)

        assert len(findings) == 2

        # First finding
        assert findings[0].id == "amb-001"
        assert findings[0].type == "ambiguity"
        assert findings[0].severity == "medium"
        assert "quickly" in findings[0].description
        assert findings[0].affected_element_ids == ["elem-001"]
        assert len(findings[0].source_refs) >= 1
        assert findings[0].source_refs[0].chunk_id == "chunk-001"
        assert findings[0].source_refs[0].document_id == "doc-001"
        assert findings[0].involves_unverified_elements is False  # elem-001 is verified
        assert findings[0].from_explicit_relationship is False

        # Second finding
        assert findings[1].id == "amb-002"
        assert findings[1].type == "ambiguity"
        assert findings[1].severity == "high"
        assert findings[1].affected_element_ids == ["elem-002"]
        assert findings[1].source_refs[0].page == 2
        assert findings[1].involves_unverified_elements is True  # elem-002 is unverified

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_parameters(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """LLM is called with primary model tier and temperature 0.1."""
        mock_llm_client.call.return_value = _make_llm_response([])

        detector = AmbiguityDetector(mock_llm_client)
        await detector.detect(sample_knowledge_model, sample_ir)

        mock_llm_client.call.assert_called_once()
        call_kwargs = mock_llm_client.call.call_args
        assert call_kwargs.kwargs["model_tier"] == "primary"
        assert call_kwargs.kwargs["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_involves_unverified_elements_flag(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Finding sets involves_unverified_elements when referencing unverified KM elements (Req 8.4)."""
        mock_llm_client.call.return_value = _make_llm_response(
            [
                {
                    "id": "amb-001",
                    "category": "vague_quantifier",
                    "description": "Ambiguity in verified element. Interpretation 1: A. Interpretation 2: B.",
                    "severity": "low",
                    "affected_element_ids": ["elem-001"],
                    "source_ref": {
                        "chunk_id": "chunk-001",
                        "evidence": "The system should respond quickly",
                    },
                },
                {
                    "id": "amb-002",
                    "category": "unspecified_condition",
                    "description": "Ambiguity in unverified element. Interpretation 1: A. Interpretation 2: B.",
                    "severity": "medium",
                    "affected_element_ids": ["elem-002"],
                    "source_ref": {
                        "chunk_id": "chunk-002",
                        "evidence": "Under certain conditions",
                    },
                },
            ]
        )

        detector = AmbiguityDetector(mock_llm_client)
        findings = await detector.detect(sample_knowledge_model, sample_ir)

        # elem-001 is verified=True -> involves_unverified_elements=False
        assert findings[0].involves_unverified_elements is False
        # elem-002 is verified=False -> involves_unverified_elements=True
        assert findings[1].involves_unverified_elements is True

    @pytest.mark.asyncio
    async def test_source_ref_populated_from_llm_response(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Source refs are correctly populated from LLM response with document_id from IR."""
        mock_llm_client.call.return_value = _make_llm_response(
            [
                {
                    "id": "amb-001",
                    "category": "undefined_term",
                    "description": "Term X is undefined. Interpretation 1: A. Interpretation 2: B.",
                    "severity": "medium",
                    "affected_element_ids": ["elem-001"],
                    "source_ref": {
                        "chunk_id": "chunk-001",
                        "page": 5,
                        "section": "## Performance",
                        "evidence": "The system should respond quickly",
                    },
                }
            ]
        )

        detector = AmbiguityDetector(mock_llm_client)
        findings = await detector.detect(sample_knowledge_model, sample_ir)

        ref = findings[0].source_refs[0]
        assert ref.document_id == "doc-001"
        assert ref.chunk_id == "chunk-001"
        assert ref.page == 5
        assert ref.section == "## Performance"
        assert ref.evidence == "The system should respond quickly"
        assert ref.evidence_verified is False  # Not yet verified by FindingVerifier


class TestAmbiguityDetectorEmptyResults:
    """Tests for empty results being valid (Req 2.4)."""

    @pytest.mark.asyncio
    async def test_empty_ambiguities_list_is_valid(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Empty ambiguities list from LLM is valid, returns empty list (Req 2.4)."""
        mock_llm_client.call.return_value = _make_llm_response([])

        detector = AmbiguityDetector(mock_llm_client)
        findings = await detector.detect(sample_knowledge_model, sample_ir)

        assert findings == []


class TestAmbiguityDetectorParseFailure:
    """Tests for parse failure raising error (Req 10.3)."""

    @pytest.mark.asyncio
    async def test_invalid_json_raises_error(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Invalid JSON from LLM raises AmbiguityDetectionError."""
        mock_llm_client.call.return_value = LLMResponse(
            content="This is not JSON at all",
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        detector = AmbiguityDetector(mock_llm_client)

        with pytest.raises(AmbiguityDetectionError, match="Failed to parse"):
            await detector.detect(sample_knowledge_model, sample_ir)

    @pytest.mark.asyncio
    async def test_invalid_schema_raises_error(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """JSON that doesn't match the expected schema raises AmbiguityDetectionError."""
        # Missing required field "source_ref" in a finding
        invalid_response = json.dumps(
            {
                "ambiguities": [
                    {
                        "id": "amb-001",
                        "category": "vague_quantifier",
                        "description": "Missing source ref",
                        "severity": "low",
                        "affected_element_ids": ["elem-001"],
                        # Missing "source_ref"
                    }
                ]
            }
        )
        mock_llm_client.call.return_value = LLMResponse(
            content=invalid_response,
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        detector = AmbiguityDetector(mock_llm_client)

        with pytest.raises(AmbiguityDetectionError, match="Failed to parse"):
            await detector.detect(sample_knowledge_model, sample_ir)

    @pytest.mark.asyncio
    async def test_missing_ambiguities_key_raises_error(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """JSON without the 'ambiguities' key raises AmbiguityDetectionError."""
        mock_llm_client.call.return_value = LLMResponse(
            content=json.dumps({"findings": []}),
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        detector = AmbiguityDetector(mock_llm_client)

        with pytest.raises(AmbiguityDetectionError, match="Failed to parse"):
            await detector.detect(sample_knowledge_model, sample_ir)


class TestAmbiguityDetectorLLMFailure:
    """Tests for LLM failure propagation (Req 2.5)."""

    @pytest.mark.asyncio
    async def test_llm_transient_error_propagates(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """LLMTransientError from the client raises AmbiguityDetectionError (Req 2.5)."""
        mock_llm_client.call.side_effect = LLMTransientError(
            "Both primary and fallback failed"
        )

        detector = AmbiguityDetector(mock_llm_client)

        with pytest.raises(AmbiguityDetectionError, match="LLM call failed"):
            await detector.detect(sample_knowledge_model, sample_ir)

    @pytest.mark.asyncio
    async def test_generic_exception_propagates(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Any exception from LLM client raises AmbiguityDetectionError."""
        mock_llm_client.call.side_effect = RuntimeError("Unexpected error")

        detector = AmbiguityDetector(mock_llm_client)

        with pytest.raises(AmbiguityDetectionError, match="LLM call failed"):
            await detector.detect(sample_knowledge_model, sample_ir)

    @pytest.mark.asyncio
    async def test_no_partial_results_on_failure(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """On LLM failure, no partial results are returned (Req 2.5)."""
        mock_llm_client.call.side_effect = LLMTransientError("Service unavailable")

        detector = AmbiguityDetector(mock_llm_client)

        with pytest.raises(AmbiguityDetectionError):
            await detector.detect(sample_knowledge_model, sample_ir)
        # No return value — exception is raised, no partial results possible


class TestAmbiguityDetectorResponseParsing:
    """Tests for response parsing edge cases."""

    @pytest.mark.asyncio
    async def test_handles_markdown_code_block_wrapper(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """LLM response wrapped in ```json ... ``` is correctly parsed."""
        raw_content = '```json\n{"ambiguities": []}\n```'
        mock_llm_client.call.return_value = LLMResponse(
            content=raw_content,
            model_id="gemini/gemini-2.5-flash-preview-05-20",
        )

        detector = AmbiguityDetector(mock_llm_client)
        findings = await detector.detect(sample_knowledge_model, sample_ir)

        assert findings == []

    @pytest.mark.asyncio
    async def test_handles_response_with_optional_null_fields(
        self,
        mock_llm_client: MagicMock,
        sample_knowledge_model: KnowledgeModel,
        sample_ir: IntermediateRepresentation,
    ):
        """Handles source_ref with null page and section fields."""
        mock_llm_client.call.return_value = _make_llm_response(
            [
                {
                    "id": "amb-001",
                    "category": "unclear_pronoun_antecedent",
                    "description": "Pronoun 'it' is ambiguous. Interpretation 1: server. Interpretation 2: client.",
                    "severity": "low",
                    "affected_element_ids": ["elem-001"],
                    "source_ref": {
                        "chunk_id": "chunk-001",
                        "page": None,
                        "section": None,
                        "evidence": "It then processes the result.",
                    },
                }
            ]
        )

        detector = AmbiguityDetector(mock_llm_client)
        findings = await detector.detect(sample_knowledge_model, sample_ir)

        assert len(findings) == 1
        assert findings[0].source_refs[0].page is None
        assert findings[0].source_refs[0].section is None
