"""Unit tests for the AnalysisService pipeline orchestrator.

Tests cover:
- Full happy path (start_analysis + confirm_and_extract)
- Document not found
- Document not ready
- Analysis already exists
- Wrong session state for confirm
- Invalid document type
- Extraction failure cleanup
- Type inference failure cleanup

Requirements validated: 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.7, 10.2, 10.4
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analysis.extraction import ExtractionError, ExtractionService
from app.analysis.service import (
    AnalysisAlreadyExistsError,
    AnalysisService,
    AnalysisStorageService,
    DocumentNotFoundError,
    DocumentNotReadyError,
    InvalidDocumentTypeError,
    InvalidSessionStateError,
    VALID_DOCUMENT_TYPES,
)
from app.analysis.type_inference import TypeInferenceService
from app.analysis.verification import VerificationResult, VerificationService
from app.models.knowledge_model import TypeSuggestion


# --- Fixtures ---

_NOW = datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
_NOW_ISO = _NOW.isoformat()


def _make_document_row(document_id: str = "doc-001", status: str = "ready") -> dict:
    """Create a mock document database row."""
    return {
        "document_id": document_id,
        "original_filename": "test.md",
        "format": "markdown",
        "size_bytes": 1024,
        "language": "en",
        "status": status,
        "upload_timestamp": _NOW_ISO,
        "warnings": "[]",
    }


def _make_session_row(
    session_id: str = "session-001",
    document_id: str = "doc-001",
    status: str = "awaiting_confirmation",
    **kwargs,
) -> dict:
    """Create a mock analysis session database row."""
    row = {
        "id": session_id,
        "document_id": document_id,
        "status": status,
        "suggested_type": kwargs.get("suggested_type", "prd"),
        "suggested_type_justification": kwargs.get(
            "suggested_type_justification", "Contains user stories."
        ),
        "confirmed_type": kwargs.get("confirmed_type"),
        "knowledge_model": kwargs.get("knowledge_model"),
        "extraction_metadata": kwargs.get("extraction_metadata"),
        "error_message": kwargs.get("error_message"),
        "created_at": _NOW_ISO,
        "updated_at": _NOW_ISO,
    }
    return row


def _make_chunks_data() -> list[dict]:
    """Create mock chunk rows from the database."""
    return [
        {
            "chunk_id": "chunk-000",
            "text": "This is a product requirements document.",
            "structural_context": json.dumps({"section": "# Introduction"}),
            "order": 0,
        },
        {
            "chunk_id": "chunk-001",
            "text": "As a user, I want to upload documents.",
            "structural_context": json.dumps({"section": "# User Stories"}),
            "order": 1,
        },
    ]


@pytest.fixture
def mock_storage():
    """Create a mock AnalysisStorageService."""
    storage = MagicMock(spec=AnalysisStorageService)
    return storage


@pytest.fixture
def mock_type_inference():
    """Create a mock TypeInferenceService."""
    service = AsyncMock(spec=TypeInferenceService)
    return service


@pytest.fixture
def mock_extraction():
    """Create a mock ExtractionService."""
    service = AsyncMock(spec=ExtractionService)
    return service


@pytest.fixture
def mock_verification():
    """Create a mock VerificationService."""
    service = MagicMock(spec=VerificationService)
    return service


@pytest.fixture
def analysis_service(
    mock_type_inference, mock_extraction, mock_verification, mock_storage
):
    """Create an AnalysisService with all mocked dependencies."""
    return AnalysisService(
        type_inference_service=mock_type_inference,
        extraction_service=mock_extraction,
        verification_service=mock_verification,
        storage=mock_storage,
    )


# --- Happy Path Tests ---


class TestStartAnalysisHappyPath:
    """Tests for successful start_analysis flow."""

    @pytest.mark.asyncio
    async def test_full_happy_path(
        self, analysis_service, mock_storage, mock_type_inference
    ):
        """start_analysis creates session, infers type, returns awaiting_confirmation."""
        # Setup mocks
        mock_storage.get_document.return_value = _make_document_row()
        mock_storage.get_session_by_document.return_value = None
        mock_storage.create_session.return_value = _make_session_row(
            status="inferring_type"
        )
        mock_storage.get_ir.return_value = _make_chunks_data()

        mock_type_inference.infer.return_value = TypeSuggestion(
            document_type="prd",
            suggested_type="prd",
            justification="Contains user stories and acceptance criteria.",
        )

        # The update_session call after inference
        mock_storage.update_session.return_value = _make_session_row(
            status="awaiting_confirmation",
            suggested_type="prd",
            suggested_type_justification="Contains user stories and acceptance criteria.",
        )

        result = await analysis_service.start_analysis("doc-001")

        assert result.status == "awaiting_confirmation"
        assert result.suggested_type == "prd"
        assert result.suggested_type_justification == "Contains user stories and acceptance criteria."
        assert result.document_id == "doc-001"

    @pytest.mark.asyncio
    async def test_session_created_with_inferring_type_status(
        self, analysis_service, mock_storage, mock_type_inference
    ):
        """Session is initially created with status 'inferring_type' (Req 8.1)."""
        mock_storage.get_document.return_value = _make_document_row()
        mock_storage.get_session_by_document.return_value = None
        mock_storage.create_session.return_value = _make_session_row(
            status="inferring_type"
        )
        mock_storage.get_ir.return_value = _make_chunks_data()
        mock_type_inference.infer.return_value = TypeSuggestion(
            document_type="prd", suggested_type="prd", justification="reason"
        )
        mock_storage.update_session.return_value = _make_session_row(
            status="awaiting_confirmation"
        )

        await analysis_service.start_analysis("doc-001")

        mock_storage.create_session.assert_called_once_with("doc-001")


# --- Document Not Found Tests ---


class TestDocumentNotFound:
    """Tests for when document does not exist."""

    @pytest.mark.asyncio
    async def test_start_analysis_document_not_found(
        self, analysis_service, mock_storage
    ):
        """Raises DocumentNotFoundError when document does not exist."""
        mock_storage.get_document.return_value = None

        with pytest.raises(DocumentNotFoundError):
            await analysis_service.start_analysis("nonexistent-doc")

    @pytest.mark.asyncio
    async def test_confirm_session_not_found(
        self, analysis_service, mock_storage
    ):
        """Raises DocumentNotFoundError when no session exists for confirm."""
        mock_storage.get_session_by_document.return_value = None

        with pytest.raises(DocumentNotFoundError):
            await analysis_service.confirm_and_extract("doc-001", "prd")


# --- Document Not Ready Tests ---


class TestDocumentNotReady:
    """Tests for when document is not in 'ready' status (Req 9.1)."""

    @pytest.mark.asyncio
    async def test_document_processing_status(
        self, analysis_service, mock_storage
    ):
        """Raises DocumentNotReadyError when status is 'processing'."""
        mock_storage.get_document.return_value = _make_document_row(status="processing")

        with pytest.raises(DocumentNotReadyError):
            await analysis_service.start_analysis("doc-001")

    @pytest.mark.asyncio
    async def test_document_failed_status(
        self, analysis_service, mock_storage
    ):
        """Raises DocumentNotReadyError when status is 'failed'."""
        mock_storage.get_document.return_value = _make_document_row(status="failed")

        with pytest.raises(DocumentNotReadyError):
            await analysis_service.start_analysis("doc-001")


# --- Analysis Already Exists Tests (Req 9.7) ---


class TestAnalysisAlreadyExists:
    """Tests for when analysis already exists for the document."""

    @pytest.mark.asyncio
    async def test_raises_when_session_exists(
        self, analysis_service, mock_storage
    ):
        """Raises AnalysisAlreadyExistsError when session already exists."""
        mock_storage.get_document.return_value = _make_document_row()
        mock_storage.get_session_by_document.return_value = _make_session_row()

        with pytest.raises(AnalysisAlreadyExistsError):
            await analysis_service.start_analysis("doc-001")


# --- Wrong Session State Tests (Req 4.4) ---


class TestWrongSessionState:
    """Tests for invalid session state during confirm_and_extract."""

    @pytest.mark.asyncio
    async def test_confirm_on_extracting_state(
        self, analysis_service, mock_storage
    ):
        """Raises InvalidSessionStateError when session is in 'extracting' state."""
        mock_storage.get_session_by_document.return_value = _make_session_row(
            status="extracting"
        )

        with pytest.raises(InvalidSessionStateError):
            await analysis_service.confirm_and_extract("doc-001", "prd")

    @pytest.mark.asyncio
    async def test_confirm_on_completed_state(
        self, analysis_service, mock_storage
    ):
        """Raises InvalidSessionStateError when session is already completed (Req 4.4)."""
        mock_storage.get_session_by_document.return_value = _make_session_row(
            status="completed"
        )

        with pytest.raises(InvalidSessionStateError):
            await analysis_service.confirm_and_extract("doc-001", "prd")

    @pytest.mark.asyncio
    async def test_confirm_on_failed_state(
        self, analysis_service, mock_storage
    ):
        """Raises InvalidSessionStateError when session is in 'failed' state."""
        mock_storage.get_session_by_document.return_value = _make_session_row(
            status="failed"
        )

        with pytest.raises(InvalidSessionStateError):
            await analysis_service.confirm_and_extract("doc-001", "prd")

    @pytest.mark.asyncio
    async def test_confirm_on_inferring_type_state(
        self, analysis_service, mock_storage
    ):
        """Raises InvalidSessionStateError when session is still inferring."""
        mock_storage.get_session_by_document.return_value = _make_session_row(
            status="inferring_type"
        )

        with pytest.raises(InvalidSessionStateError):
            await analysis_service.confirm_and_extract("doc-001", "prd")


# --- Invalid Document Type Tests (Req 4.5) ---


class TestInvalidDocumentType:
    """Tests for invalid document type values."""

    @pytest.mark.asyncio
    async def test_invalid_type_raises_error(
        self, analysis_service, mock_storage
    ):
        """Raises InvalidDocumentTypeError for unknown type value."""
        with pytest.raises(InvalidDocumentTypeError) as exc_info:
            await analysis_service.confirm_and_extract("doc-001", "invalid_type")

        assert exc_info.value.invalid_type == "invalid_type"
        assert "prd" in exc_info.value.valid_types
        assert "technical_spec" in exc_info.value.valid_types
        assert "policy_process" in exc_info.value.valid_types
        assert "generic" in exc_info.value.valid_types

    @pytest.mark.asyncio
    async def test_empty_type_raises_error(
        self, analysis_service, mock_storage
    ):
        """Raises InvalidDocumentTypeError for empty string type."""
        with pytest.raises(InvalidDocumentTypeError):
            await analysis_service.confirm_and_extract("doc-001", "")

    @pytest.mark.asyncio
    async def test_valid_types_are_accepted(self):
        """All valid types are in the VALID_DOCUMENT_TYPES set."""
        expected = {"prd", "technical_spec", "policy_process", "generic"}
        assert VALID_DOCUMENT_TYPES == expected


# --- Confirm and Extract Happy Path ---


class TestConfirmAndExtractHappyPath:
    """Tests for successful confirm_and_extract flow."""

    @pytest.mark.asyncio
    async def test_full_extraction_flow(
        self,
        analysis_service,
        mock_storage,
        mock_extraction,
        mock_verification,
    ):
        """Full confirm_and_extract flow: extract, verify, persist, complete."""
        from app.models.knowledge_model import (
            ExtractionMetadata,
            KnowledgeElement,
            KnowledgeModel,
            SourceRef,
        )

        # Session is in awaiting_confirmation
        mock_storage.get_session_by_document.return_value = _make_session_row(
            status="awaiting_confirmation"
        )
        mock_storage.get_document.return_value = _make_document_row()
        mock_storage.get_ir.return_value = _make_chunks_data()

        # Mock extraction result
        km = KnowledgeModel(
            document_id="doc-001",
            document_type="prd",
            elements=[
                KnowledgeElement(
                    id="elem-001",
                    type="proposito",
                    name="Purpose",
                    content="Build an analysis platform.",
                    source_ref=SourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-000",
                        evidence="This is a product requirements document.",
                    ),
                )
            ],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash-preview-05-20",
                temperature=0.1,
                element_count=1,
                relationship_count=0,
                verification_rate=0.0,
                extracted_at=_NOW,
            ),
        )
        mock_extraction.extract.return_value = km

        # Mock verification result
        mock_verification.verify.return_value = VerificationResult(
            verified_count=1,
            total_count=1,
            verification_rate=1.0,
            unverified_element_ids=[],
        )

        # Final update returns completed session
        mock_storage.update_session.return_value = _make_session_row(
            status="completed",
            confirmed_type="prd",
            knowledge_model={"document_id": "doc-001"},
        )

        result = await analysis_service.confirm_and_extract("doc-001", "prd")

        assert result.status == "completed"
        assert result.confirmed_type == "prd"

    @pytest.mark.asyncio
    async def test_user_can_change_type(
        self,
        analysis_service,
        mock_storage,
        mock_extraction,
        mock_verification,
    ):
        """User can provide a different type than suggested (Req 4.2)."""
        from app.models.knowledge_model import (
            ExtractionMetadata,
            KnowledgeElement,
            KnowledgeModel,
            SourceRef,
        )

        mock_storage.get_session_by_document.return_value = _make_session_row(
            status="awaiting_confirmation", suggested_type="prd"
        )
        mock_storage.get_document.return_value = _make_document_row()
        mock_storage.get_ir.return_value = _make_chunks_data()

        km = KnowledgeModel(
            document_id="doc-001",
            document_type="technical_spec",
            elements=[
                KnowledgeElement(
                    id="elem-001",
                    type="proposito",
                    name="Purpose",
                    content="Technical design.",
                    source_ref=SourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-000",
                        evidence="This is a product requirements document.",
                    ),
                )
            ],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash-preview-05-20",
                temperature=0.1,
                element_count=1,
                relationship_count=0,
                verification_rate=0.0,
                extracted_at=_NOW,
            ),
        )
        mock_extraction.extract.return_value = km
        mock_verification.verify.return_value = VerificationResult(
            verified_count=1,
            total_count=1,
            verification_rate=1.0,
            unverified_element_ids=[],
        )
        mock_storage.update_session.return_value = _make_session_row(
            status="completed", confirmed_type="technical_spec"
        )

        result = await analysis_service.confirm_and_extract("doc-001", "technical_spec")

        # Verify extraction was called with user's chosen type, not the suggested one
        mock_extraction.extract.assert_called_once()
        call_args = mock_extraction.extract.call_args
        assert call_args.args[1] == "technical_spec"


# --- Extraction Failure Cleanup Tests (Req 8.4) ---


class TestExtractionFailureCleanup:
    """Tests for failure handling during extraction."""

    @pytest.mark.asyncio
    async def test_extraction_error_marks_session_failed(
        self, analysis_service, mock_storage, mock_extraction
    ):
        """ExtractionError marks session as failed with error message (Req 8.4)."""
        mock_storage.get_session_by_document.return_value = _make_session_row(
            status="awaiting_confirmation"
        )
        mock_storage.get_document.return_value = _make_document_row()
        mock_storage.get_ir.return_value = _make_chunks_data()

        mock_extraction.extract.side_effect = ExtractionError(
            "Complete parse failure: LLM response is not valid JSON."
        )

        # update_session called for status changes + failure
        mock_storage.update_session.return_value = _make_session_row(status="failed")

        with pytest.raises(ExtractionError):
            await analysis_service.confirm_and_extract("doc-001", "prd")

        # Verify the failure cleanup was called
        failure_calls = [
            call
            for call in mock_storage.update_session.call_args_list
            if call.kwargs.get("status") == "failed"
        ]
        assert len(failure_calls) == 1
        assert failure_calls[0].kwargs.get("knowledge_model") is None
        assert failure_calls[0].kwargs.get("extraction_metadata") is None
        assert "error_message" in failure_calls[0].kwargs

    @pytest.mark.asyncio
    async def test_verification_error_marks_session_failed(
        self, analysis_service, mock_storage, mock_extraction, mock_verification
    ):
        """Verification error also marks session as failed (Req 8.4)."""
        from app.models.knowledge_model import (
            ExtractionMetadata,
            KnowledgeElement,
            KnowledgeModel,
            SourceRef,
        )

        mock_storage.get_session_by_document.return_value = _make_session_row(
            status="awaiting_confirmation"
        )
        mock_storage.get_document.return_value = _make_document_row()
        mock_storage.get_ir.return_value = _make_chunks_data()

        km = KnowledgeModel(
            document_id="doc-001",
            document_type="prd",
            elements=[
                KnowledgeElement(
                    id="elem-001",
                    type="proposito",
                    name="Purpose",
                    content="Content.",
                    source_ref=SourceRef(
                        document_id="doc-001",
                        chunk_id="chunk-000",
                        evidence="evidence text",
                    ),
                )
            ],
            extraction_metadata=ExtractionMetadata(
                prompt_version="extraction-v1",
                model_id="gemini/gemini-2.5-flash",
                temperature=0.1,
                element_count=1,
                relationship_count=0,
                verification_rate=0.0,
                extracted_at=_NOW,
            ),
        )
        mock_extraction.extract.return_value = km
        mock_verification.verify.side_effect = RuntimeError("Verification crashed")
        mock_storage.update_session.return_value = _make_session_row(status="failed")

        with pytest.raises(RuntimeError):
            await analysis_service.confirm_and_extract("doc-001", "prd")

        # Verify cleanup was called
        failure_calls = [
            call
            for call in mock_storage.update_session.call_args_list
            if call.kwargs.get("status") == "failed"
        ]
        assert len(failure_calls) == 1
        assert failure_calls[0].kwargs.get("knowledge_model") is None


# --- Type Inference Failure Cleanup Tests ---


class TestTypeInferenceFailureCleanup:
    """Tests for failure handling during type inference."""

    @pytest.mark.asyncio
    async def test_type_inference_error_marks_session_failed(
        self, analysis_service, mock_storage, mock_type_inference
    ):
        """Type inference error marks session as failed (Req 8.4)."""
        mock_storage.get_document.return_value = _make_document_row()
        mock_storage.get_session_by_document.return_value = None
        mock_storage.create_session.return_value = _make_session_row(
            session_id="session-001", status="inferring_type"
        )
        mock_storage.get_ir.return_value = _make_chunks_data()

        mock_type_inference.infer.side_effect = RuntimeError("LLM call failed")
        mock_storage.update_session.return_value = _make_session_row(status="failed")

        with pytest.raises(RuntimeError):
            await analysis_service.start_analysis("doc-001")

        # Verify the session was marked as failed
        failure_calls = [
            call
            for call in mock_storage.update_session.call_args_list
            if call.kwargs.get("status") == "failed"
        ]
        assert len(failure_calls) == 1
        assert "Type inference failed" in failure_calls[0].kwargs["error_message"]
        assert failure_calls[0].kwargs.get("knowledge_model") is None

    @pytest.mark.asyncio
    async def test_ir_retrieval_error_marks_session_failed(
        self, analysis_service, mock_storage, mock_type_inference
    ):
        """Failure to retrieve IR marks session as failed."""
        mock_storage.get_document.return_value = _make_document_row()
        mock_storage.get_session_by_document.return_value = None
        mock_storage.create_session.return_value = _make_session_row(
            session_id="session-001", status="inferring_type"
        )
        # get_document returns None inside _get_ir (second call)
        mock_storage.get_document.side_effect = [_make_document_row(), None]
        mock_storage.update_session.return_value = _make_session_row(status="failed")

        with pytest.raises(DocumentNotFoundError):
            await analysis_service.start_analysis("doc-001")

        # Verify the session was marked as failed
        failure_calls = [
            call
            for call in mock_storage.update_session.call_args_list
            if call.kwargs.get("status") == "failed"
        ]
        assert len(failure_calls) == 1


# --- Data Minimization Tests (Req 10.4) ---


class TestDataMinimization:
    """Tests verifying no user metadata is stored."""

    @pytest.mark.asyncio
    async def test_no_user_metadata_in_session(
        self,
        analysis_service,
        mock_storage,
        mock_type_inference,
    ):
        """Session creation and updates do not include user metadata (Req 10.4)."""
        mock_storage.get_document.return_value = _make_document_row()
        mock_storage.get_session_by_document.return_value = None
        mock_storage.create_session.return_value = _make_session_row(
            status="inferring_type"
        )
        mock_storage.get_ir.return_value = _make_chunks_data()
        mock_type_inference.infer.return_value = TypeSuggestion(
            document_type="prd", suggested_type="prd", justification="reason"
        )
        mock_storage.update_session.return_value = _make_session_row(
            status="awaiting_confirmation"
        )

        await analysis_service.start_analysis("doc-001")

        # Verify update_session was called without any user metadata fields
        for call in mock_storage.update_session.call_args_list:
            kwargs = call.kwargs
            # These fields should never appear in session updates
            assert "user_id" not in kwargs
            assert "user_email" not in kwargs
            assert "account_id" not in kwargs
            assert "session_cookie" not in kwargs
