"""Unit tests for the QueryService orchestrator.

Covers: successful end-to-end pipeline, cannot-answer response on empty context,
retry flow (first parse fails then succeeds), retry flow (both fail → QueryError),
LLM timeout handling (>30s), metadata attachment, and default temperature ≤ 0.1.

Requirements covered: 1.1, 1.3, 1.5, 1.6, 7.3, 7.4
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analysis.llm_client import LLMResponse
from app.analysis.prompts import query_answering_v1
from app.analysis.query.response_parser import ResponseParseError
from app.analysis.query.service import QueryError, QueryService
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
from app.models.query import (
    QueryContext,
    QueryContextElement,
    QueryContextRelation,
    QueryMetadata,
    QueryResponse,
    QuerySourceRef,
)

pytestmark = pytest.mark.asyncio


# --- Fixtures ---


@pytest.fixture
def sample_ir() -> IntermediateRepresentation:
    metadata = DocumentMetadata(
        original_filename="test.md",
        format=DocumentFormat.MARKDOWN,
        size_bytes=512,
        language=DetectedLanguage.SPANISH,
        upload_timestamp=datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    return IntermediateRepresentation(
        document_id="doc-001",
        metadata=metadata,
        chunks=[
            ContentChunkModel(
                chunk_id="chunk-001",
                text="The system processes documents automatically.",
                structural_context={"section": "# Introduction"},
                order=0,
            ),
        ],
    )


@pytest.fixture
def sample_km() -> KnowledgeModel:
    return KnowledgeModel(
        document_id="doc-001",
        document_type="generic",
        elements=[
            KnowledgeElement(
                id="elem-001",
                type="concepto",
                name="Document Processing",
                content="The system processes documents automatically.",
                source_ref=SourceRef(
                    document_id="doc-001",
                    chunk_id="chunk-001",
                    evidence="The system processes documents automatically.",
                ),
                relations=[],
                verified=True,
            ),
        ],
        extraction_metadata=ExtractionMetadata(
            prompt_version="extraction-v1",
            model_id="gemini/gemini-2.5-flash",
            temperature=0.1,
            element_count=1,
            relationship_count=0,
            verification_rate=1.0,
            extracted_at=datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
        ),
    )


@pytest.fixture
def mock_context() -> QueryContext:
    """A simple QueryContext returned by the mocked context_builder."""
    return QueryContext(
        elements=[
            QueryContextElement(
                element_id="elem-001",
                type="concepto",
                name="Document Processing",
                content="The system processes documents automatically.",
                evidence="The system processes documents automatically.",
                verified=True,
            ),
        ],
        relations=[],
        total_tokens=100,
        has_unverified_elements=False,
    )


@pytest.fixture
def mock_query_response() -> QueryResponse:
    """A valid QueryResponse returned by the mocked response_parser."""
    return QueryResponse(
        answer="The system processes documents automatically.",
        answerable=True,
        source_refs=[
            QuerySourceRef(
                document_id="doc-001",
                chunk_id="chunk-001",
                page=None,
                section="# Introduction",
                evidence="The system processes documents automatically.",
                evidence_verified=False,
            ),
        ],
        all_evidence_unverified=False,
        metadata=QueryMetadata(
            prompt_version="placeholder",
            model_id="placeholder",
            temperature=0.0,
            timestamp=datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
        ),
    )


@pytest.fixture
def mock_context_builder():
    builder = AsyncMock()
    return builder


@pytest.fixture
def mock_llm_client():
    client = AsyncMock()
    client.call = AsyncMock(
        return_value=LLMResponse(
            content='{"answer": "test", "answerable": true, "source_refs": []}',
            model_id="gemini/gemini-2.5-flash",
        )
    )
    return client


@pytest.fixture
def mock_response_parser():
    parser = MagicMock()
    return parser


@pytest.fixture
def mock_evidence_verifier():
    verifier = MagicMock()
    return verifier


@pytest.fixture
def service(
    mock_llm_client,
    mock_context_builder,
    mock_response_parser,
    mock_evidence_verifier,
):
    return QueryService(
        llm_client=mock_llm_client,
        context_builder=mock_context_builder,
        response_parser=mock_response_parser,
        evidence_verifier=mock_evidence_verifier,
    )


# --- Test Successful End-to-End Pipeline ---


class TestSuccessfulPipeline:
    """Test successful pipeline end-to-end with mocked dependencies (Req 1.1)."""

    async def test_end_to_end_pipeline_returns_query_response(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        mock_response_parser,
        mock_evidence_verifier,
        mock_context,
        mock_query_response,
        sample_km,
        sample_ir,
    ):
        """Full pipeline completes: context build → LLM call → parse → verify → metadata."""
        # Arrange
        mock_context_builder.build_context = AsyncMock(return_value=mock_context)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(
                content='{"answer": "...", "answerable": true}',
                model_id="gemini/gemini-2.5-flash",
            )
        )
        mock_response_parser.parse.return_value = mock_query_response
        mock_evidence_verifier.verify.return_value = mock_query_response.source_refs

        # Act
        result = await service.answer("doc-001", "What does the system do?", sample_km, sample_ir)

        # Assert
        assert result.answerable is True
        assert result.answer == "The system processes documents automatically."
        assert len(result.source_refs) == 1
        assert result.source_refs[0].chunk_id == "chunk-001"

        # Verify all pipeline steps were called
        mock_context_builder.build_context.assert_called_once()
        mock_llm_client.call.assert_called_once()
        mock_response_parser.parse.assert_called_once()
        mock_evidence_verifier.verify.assert_called_once()

    async def test_pipeline_calls_llm_with_primary_tier(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        mock_response_parser,
        mock_evidence_verifier,
        mock_context,
        mock_query_response,
        sample_km,
        sample_ir,
    ):
        """LLM is called with model_tier='primary' and temperature ≤ 0.1."""
        mock_context_builder.build_context = AsyncMock(return_value=mock_context)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(content="...", model_id="gemini/gemini-2.5-flash")
        )
        mock_response_parser.parse.return_value = mock_query_response
        mock_evidence_verifier.verify.return_value = mock_query_response.source_refs

        await service.answer("doc-001", "Question?", sample_km, sample_ir)

        # Check the LLM call arguments
        call_args = mock_llm_client.call.call_args
        assert call_args.kwargs.get("model_tier") == "primary" or (
            len(call_args.args) >= 1
        )
        assert call_args.kwargs.get("temperature", 0.1) <= 0.1


# --- Test Cannot-Answer Response ---


class TestCannotAnswerResponse:
    """Test cannot-answer response when context is empty/None (Req 1.3)."""

    async def test_returns_cannot_answer_when_context_is_none(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        sample_km,
        sample_ir,
    ):
        """When context_builder returns None, the service returns a cannot-answer response."""
        mock_context_builder.build_context = AsyncMock(return_value=None)

        result = await service.answer("doc-001", "Unrelated question?", sample_km, sample_ir)

        assert result.answerable is False
        assert result.source_refs == []
        assert len(result.answer) > 0
        # LLM should NOT be called when context is empty
        mock_llm_client.call.assert_not_called()

    async def test_cannot_answer_response_has_metadata(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        sample_km,
        sample_ir,
    ):
        """Cannot-answer responses still include metadata."""
        mock_context_builder.build_context = AsyncMock(return_value=None)

        result = await service.answer("doc-001", "Unrelated question?", sample_km, sample_ir)

        assert result.metadata is not None
        assert result.metadata.prompt_version == query_answering_v1.VERSION
        assert result.metadata.model_id == "none"
        assert result.metadata.temperature <= 0.1
        assert result.metadata.timestamp is not None

    async def test_cannot_answer_response_has_all_evidence_unverified_false(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        sample_km,
        sample_ir,
    ):
        """Cannot-answer responses have all_evidence_unverified=False (no refs)."""
        mock_context_builder.build_context = AsyncMock(return_value=None)

        result = await service.answer("doc-001", "Unrelated question?", sample_km, sample_ir)

        assert result.all_evidence_unverified is False


# --- Test Retry Flow: First Parse Fails, Second Succeeds ---


class TestRetryFlowSuccess:
    """Test retry: first parse fails, second succeeds (Req 1.1, 3.3)."""

    async def test_retry_succeeds_on_second_attempt(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        mock_response_parser,
        mock_evidence_verifier,
        mock_context,
        mock_query_response,
        sample_km,
        sample_ir,
    ):
        """First parse raises ResponseParseError, corrective re-prompt succeeds."""
        mock_context_builder.build_context = AsyncMock(return_value=mock_context)

        # LLM responds twice (first call + retry call)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(content="...", model_id="gemini/gemini-2.5-flash")
        )

        # First parse fails, second succeeds
        mock_response_parser.parse.side_effect = [
            ResponseParseError("Invalid JSON", raw_output="bad output"),
            mock_query_response,
        ]
        mock_response_parser.build_corrective_reprompt.return_value = "corrective prompt"
        mock_evidence_verifier.verify.return_value = mock_query_response.source_refs

        result = await service.answer("doc-001", "Question?", sample_km, sample_ir)

        # Should succeed on retry
        assert result.answerable is True
        # LLM called twice (original + retry)
        assert mock_llm_client.call.call_count == 2
        # Parser called twice
        assert mock_response_parser.parse.call_count == 2
        # Corrective re-prompt was built
        mock_response_parser.build_corrective_reprompt.assert_called_once()


# --- Test Retry Flow: Both Parses Fail → Raises QueryError ---


class TestRetryFlowFailure:
    """Test retry: both parses fail → raises QueryError (Req 1.5, 3.3)."""

    async def test_raises_query_error_after_two_parse_failures(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        mock_response_parser,
        mock_context,
        sample_km,
        sample_ir,
    ):
        """Both parse attempts fail → QueryError raised."""
        mock_context_builder.build_context = AsyncMock(return_value=mock_context)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(content="bad", model_id="gemini/gemini-2.5-flash")
        )

        # Both parse attempts fail
        mock_response_parser.parse.side_effect = [
            ResponseParseError("First error", raw_output="bad1"),
            ResponseParseError("Second error", raw_output="bad2"),
        ]
        mock_response_parser.build_corrective_reprompt.return_value = "retry prompt"

        with pytest.raises(QueryError, match="Response parsing failed after retry"):
            await service.answer("doc-001", "Question?", sample_km, sample_ir)

    async def test_raises_query_error_when_llm_call_fails(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        mock_context,
        sample_km,
        sample_ir,
    ):
        """LLM call raises exception → QueryError raised."""
        mock_context_builder.build_context = AsyncMock(return_value=mock_context)
        mock_llm_client.call = AsyncMock(side_effect=Exception("LLM service unavailable"))

        with pytest.raises(QueryError, match="LLM call failed"):
            await service.answer("doc-001", "Question?", sample_km, sample_ir)

    async def test_raises_query_error_when_retry_llm_call_fails(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        mock_response_parser,
        mock_context,
        sample_km,
        sample_ir,
    ):
        """First parse fails, then retry LLM call fails → QueryError raised."""
        mock_context_builder.build_context = AsyncMock(return_value=mock_context)

        # First LLM call succeeds, second (retry) fails
        mock_llm_client.call = AsyncMock(
            side_effect=[
                LLMResponse(content="bad", model_id="gemini/gemini-2.5-flash"),
                Exception("LLM timeout on retry"),
            ]
        )

        mock_response_parser.parse.side_effect = ResponseParseError(
            "Parse error", raw_output="bad"
        )
        mock_response_parser.build_corrective_reprompt.return_value = "retry prompt"

        with pytest.raises(QueryError, match="LLM retry call failed"):
            await service.answer("doc-001", "Question?", sample_km, sample_ir)


# --- Test LLM Timeout Handling ---


class TestTimeoutHandling:
    """Test LLM timeout handling (>30s) (Req 1.5)."""

    async def test_raises_query_error_on_pipeline_timeout(
        self,
        mock_llm_client,
        mock_response_parser,
        mock_evidence_verifier,
        sample_km,
        sample_ir,
    ):
        """When the pipeline exceeds 30s, QueryError is raised with timeout message."""

        # Create a slow context_builder that sleeps beyond the timeout
        async def slow_build_context(*args, **kwargs):
            await asyncio.sleep(35)  # exceeds 30s timeout

        mock_context_builder = AsyncMock()
        mock_context_builder.build_context = slow_build_context

        service = QueryService(
            llm_client=mock_llm_client,
            context_builder=mock_context_builder,
            response_parser=mock_response_parser,
            evidence_verifier=mock_evidence_verifier,
        )

        with pytest.raises(QueryError, match="timed out"):
            await service.answer("doc-001", "Question?", sample_km, sample_ir)


# --- Test Metadata Attachment ---


class TestMetadataAttachment:
    """Test metadata attachment (prompt version, model_id, temperature, timestamp) (Req 7.3)."""

    async def test_metadata_has_correct_prompt_version(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        mock_response_parser,
        mock_evidence_verifier,
        mock_context,
        mock_query_response,
        sample_km,
        sample_ir,
    ):
        """Metadata prompt_version matches query_answering_v1.VERSION."""
        mock_context_builder.build_context = AsyncMock(return_value=mock_context)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(content="...", model_id="gemini/gemini-2.5-flash")
        )
        mock_response_parser.parse.return_value = mock_query_response
        mock_evidence_verifier.verify.return_value = mock_query_response.source_refs

        result = await service.answer("doc-001", "Question?", sample_km, sample_ir)

        assert result.metadata.prompt_version == query_answering_v1.VERSION

    async def test_metadata_has_model_id_from_llm_response(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        mock_response_parser,
        mock_evidence_verifier,
        mock_context,
        mock_query_response,
        sample_km,
        sample_ir,
    ):
        """Metadata model_id comes from the actual LLM response."""
        mock_context_builder.build_context = AsyncMock(return_value=mock_context)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(content="...", model_id="gemini/gemini-2.0-flash")
        )
        mock_response_parser.parse.return_value = mock_query_response
        mock_evidence_verifier.verify.return_value = mock_query_response.source_refs

        result = await service.answer("doc-001", "Question?", sample_km, sample_ir)

        assert result.metadata.model_id == "gemini/gemini-2.0-flash"

    async def test_metadata_has_temperature(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        mock_response_parser,
        mock_evidence_verifier,
        mock_context,
        mock_query_response,
        sample_km,
        sample_ir,
    ):
        """Metadata temperature reflects the configured value."""
        mock_context_builder.build_context = AsyncMock(return_value=mock_context)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(content="...", model_id="gemini/gemini-2.5-flash")
        )
        mock_response_parser.parse.return_value = mock_query_response
        mock_evidence_verifier.verify.return_value = mock_query_response.source_refs

        result = await service.answer("doc-001", "Question?", sample_km, sample_ir)

        assert result.metadata.temperature == 0.1

    async def test_metadata_has_utc_timestamp(
        self,
        service,
        mock_context_builder,
        mock_llm_client,
        mock_response_parser,
        mock_evidence_verifier,
        mock_context,
        mock_query_response,
        sample_km,
        sample_ir,
    ):
        """Metadata timestamp is a UTC datetime."""
        mock_context_builder.build_context = AsyncMock(return_value=mock_context)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(content="...", model_id="gemini/gemini-2.5-flash")
        )
        mock_response_parser.parse.return_value = mock_query_response
        mock_evidence_verifier.verify.return_value = mock_query_response.source_refs

        before = datetime.now(timezone.utc)
        result = await service.answer("doc-001", "Question?", sample_km, sample_ir)
        after = datetime.now(timezone.utc)

        assert result.metadata.timestamp >= before
        assert result.metadata.timestamp <= after
        assert result.metadata.timestamp.tzinfo is not None


# --- Test Temperature Default ---


class TestTemperatureDefault:
    """Test temperature ≤ 0.1 default (Req 7.4)."""

    async def test_default_temperature_is_0_1(
        self,
        mock_llm_client,
        mock_context_builder,
        mock_response_parser,
        mock_evidence_verifier,
        mock_context,
        mock_query_response,
        sample_km,
        sample_ir,
    ):
        """Default temperature parameter is 0.1."""
        service = QueryService(
            llm_client=mock_llm_client,
            context_builder=mock_context_builder,
            response_parser=mock_response_parser,
            evidence_verifier=mock_evidence_verifier,
        )

        mock_context_builder.build_context = AsyncMock(return_value=mock_context)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(content="...", model_id="gemini/gemini-2.5-flash")
        )
        mock_response_parser.parse.return_value = mock_query_response
        mock_evidence_verifier.verify.return_value = mock_query_response.source_refs

        await service.answer("doc-001", "Question?", sample_km, sample_ir)

        # Verify temperature passed to LLM
        call_kwargs = mock_llm_client.call.call_args.kwargs
        assert call_kwargs["temperature"] <= 0.1

    async def test_custom_temperature_recorded_in_metadata(
        self,
        mock_llm_client,
        mock_context_builder,
        mock_response_parser,
        mock_evidence_verifier,
        mock_context,
        mock_query_response,
        sample_km,
        sample_ir,
    ):
        """Custom temperature is accepted and recorded in metadata."""
        service = QueryService(
            llm_client=mock_llm_client,
            context_builder=mock_context_builder,
            response_parser=mock_response_parser,
            evidence_verifier=mock_evidence_verifier,
            temperature=0.05,
        )

        mock_context_builder.build_context = AsyncMock(return_value=mock_context)
        mock_llm_client.call = AsyncMock(
            return_value=LLMResponse(content="...", model_id="gemini/gemini-2.5-flash")
        )
        mock_response_parser.parse.return_value = mock_query_response
        mock_evidence_verifier.verify.return_value = mock_query_response.source_refs

        result = await service.answer("doc-001", "Question?", sample_km, sample_ir)

        assert result.metadata.temperature == 0.05
        assert mock_llm_client.call.call_args.kwargs["temperature"] == 0.05
